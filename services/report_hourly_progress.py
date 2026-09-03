from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database
from services.report_area_tracking import area_order_condition, ensure_area_tracking_table
from services.report_multi_topic import get_topic_identity, list_registered_topics


DEFAULT_GROUP_TITLE = "REPORT MANYAR"
TARGET_SETTING_KEY = "report_manyar_progress_group_id"
REPORT_GROUP_SETTING_KEY = "report_group_id"
REPORT_THREAD_SETTING_KEY = "report_thread_id"
AUTO_PROGRESS_START_HOUR = 6
AUTO_PROGRESS_END_HOUR = 23
PRIMARY_PROGRESS_LABEL = "MANYAR"
SECONDARY_PROGRESS_LABEL = "JAGIR"
PRIMARY_STO_CODE = "MYR"
SECONDARY_STO_CODE = "JGR"


def _normalized(value: str | None) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _clean_technician_name(value: str | None) -> str:
    text = _normalized(value)
    text = re.sub(r"^(?:(?:NAME|NAMA)\s*)?[-:=|]+\s*", "", text).strip()
    text = re.sub(r"^(?:NAME|NAMA)\s*[-:=|]*\s*", "", text).strip()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return _normalized(text)


def _digits(value: object) -> str:
    raw = str(value or "").strip()
    return raw if raw.isdigit() else ""


def _target_title() -> str:
    return _normalized(os.getenv("STO_RECAP_GROUP_TITLE", DEFAULT_GROUP_TITLE))


def _ensure_settings_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _save_target(database_path: Path, chat_id: int) -> None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_settings_table(conn)
        now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        conn.execute(
            """
            INSERT INTO report_bot_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (TARGET_SETTING_KEY, str(chat_id), now),
        )
        conn.commit()
    finally:
        conn.close()


def _get_setting(database_path: Path, key: str) -> int | None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_settings_table(conn)
        row = conn.execute(
            "SELECT value FROM report_bot_settings WHERE key = ?",
            (key,),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()
    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return None


def _get_target(database_path: Path) -> int | None:
    return _get_setting(database_path, TARGET_SETTING_KEY)


def _technician_registry(conn: sqlite3.Connection) -> tuple[dict[str, dict[str, str]], dict[int, dict[str, str]], list[dict[str, str]]]:
    try:
        rows = conn.execute(
            "SELECT telegram_id, nik, name, sto FROM technicians WHERE TRIM(COALESCE(nik,'')) <> '' AND TRIM(COALESCE(name,'')) <> ''"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}, {}, []

    by_nik: dict[str, dict[str, str]] = {}
    by_telegram: dict[int, dict[str, str]] = {}
    all_rows: list[dict[str, str]] = []
    for row in rows:
        nik = _digits(row["nik"])
        name = _clean_technician_name(row["name"])
        if not nik or not name:
            continue
        item = {
            "nik": nik,
            "name": name,
            "sto": _normalized(row["sto"]),
        }
        by_nik[nik] = item
        telegram_id = int(row["telegram_id"] or 0)
        if telegram_id:
            by_telegram[telegram_id] = item
        all_rows.append(item)
    return by_nik, by_telegram, all_rows


def _resolve_by_name(name: str, registry: list[dict[str, str]]) -> dict[str, str] | None:
    key = _clean_technician_name(name)
    if not key:
        return None
    matches: dict[str, dict[str, str]] = {}
    for item in registry:
        canonical = item["name"]
        if canonical == key or canonical.startswith(key + " ") or key.startswith(canonical + " "):
            matches[item["nik"]] = item
    if len(matches) != 1:
        return None
    return next(iter(matches.values()))


def _canonical_identity(
    raw_nik: object,
    raw_name: object,
    by_nik: dict[str, dict[str, str]],
    registry: list[dict[str, str]],
) -> tuple[str, str, str]:
    nik = _digits(raw_nik)
    if nik and nik in by_nik:
        item = by_nik[nik]
        return f"NIK:{nik}", item["name"], nik
    match = _resolve_by_name(str(raw_name or ""), registry)
    if match:
        return f"NIK:{match['nik']}", match["name"], match["nik"]
    clean = _clean_technician_name(str(raw_name or "")) or "-"
    return f"NAME:{clean}", clean, nik


def _today_progress_rows(
    database_path: Path,
    day_iso: str,
    sto_code: str,
) -> list[tuple[str, int, int]]:
    """Return CLOSE/UPDATE per canonical technician for one local day and one STO."""
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    sto_code = _normalized(sto_code)
    try:
        ensure_area_tracking_table(conn)
        by_nik, by_telegram, registry = _technician_registry(conn)
        try:
            area_predicate, area_params = area_order_condition(sto_code, "r")
            close_rows = conn.execute(
                f"""
                SELECT r.technician_nik,
                       MAX(r.technician_name) AS technician_name,
                       COUNT(DISTINCT r.service_number) AS total
                FROM report_group_orders r
                WHERE substr(r.message_date, 1, 10) = ?
                  AND {area_predicate}
                GROUP BY r.technician_nik
                """,
                (day_iso, *area_params),
            ).fetchall()
        except sqlite3.OperationalError:
            close_rows = []

        if sto_code == "JGR":
            update_rows = []
        else:
            try:
                update_rows = conn.execute(
                    """
                    SELECT k.telegram_id,
                           MAX(k.technician_name) AS technician_name,
                           COUNT(DISTINCT k.service_number) AS total
                    FROM kendala_updates k
                    WHERE substr(k.created_at, 1, 10) = ?
                      AND UPPER(TRIM(k.status)) = 'UPDATE'
                      AND EXISTS (
                          SELECT 1
                          FROM orders o
                          WHERE o.service_number = k.service_number
                            AND UPPER(TRIM(o.sto)) = ?
                      )
                    GROUP BY k.telegram_id
                    """,
                    (day_iso, sto_code),
                ).fetchall()
            except sqlite3.OperationalError:
                update_rows = []

        combined: dict[str, dict[str, object]] = {}

        for row in close_rows:
            key, name, nik = _canonical_identity(
                row["technician_nik"], row["technician_name"], by_nik, registry
            )
            item = combined.setdefault(
                key,
                {"name": name, "nik": nik, "close": 0, "update": 0},
            )
            item["close"] = int(item["close"]) + int(row["total"] or 0)

        for row in update_rows:
            telegram_id = int(row["telegram_id"] or 0)
            registered = by_telegram.get(telegram_id)
            if registered:
                key = f"NIK:{registered['nik']}"
                name = registered["name"]
                nik = registered["nik"]
            else:
                key, name, nik = _canonical_identity("", row["technician_name"], by_nik, registry)
            item = combined.setdefault(
                key,
                {"name": name, "nik": nik, "close": 0, "update": 0},
            )
            item["update"] = int(item["update"]) + int(row["total"] or 0)

        rows = [
            (str(item["name"]), int(item["close"]), int(item["update"]))
            for item in combined.values()
        ]
        rows.sort(key=lambda item: (-(item[1] + item[2]), -item[1], item[0]))
        return rows
    finally:
        conn.close()


def _progress_identity_for_topic(
    database_path: Path,
    chat_id: int,
    thread_id: int | None,
) -> tuple[str, str]:
    if thread_id is not None:
        identity = get_topic_identity(database_path, chat_id, thread_id)
        if identity:
            return identity

    primary_group = _get_setting(database_path, REPORT_GROUP_SETTING_KEY)
    primary_thread = _get_setting(database_path, REPORT_THREAD_SETTING_KEY)
    if (
        thread_id is not None
        and primary_group == chat_id
        and primary_thread == thread_id
    ):
        return PRIMARY_PROGRESS_LABEL, PRIMARY_STO_CODE
    return SECONDARY_PROGRESS_LABEL, SECONDARY_STO_CODE


def build_hourly_progress_text(
    rows: list[tuple[str, int, int]],
    now: datetime,
    area_label: str = PRIMARY_PROGRESS_LABEL,
) -> str:
    total_close = sum(close for _, close, _ in rows)
    total_update = sum(update for _, _, update in rows)
    total_reports = total_close + total_update

    lines = [f"📊 PROGRESS {area_label.upper()}", ""]

    if rows:
        for index, (name, close, update) in enumerate(rows):
            if index:
                lines.append("")
            lines.extend(
                [
                    f"👨 {name.upper()}",
                    f"✅ Close : {close}",
                    f"🔄 Update : {update}",
                ]
            )
    else:
        lines.append("Belum ada laporan hari ini.")

    lines.extend(
        [
            "",
            "============================",
            f"📌 TOTAL CLOSE : {total_close}",
            f"📌 TOTAL UPDATE : {total_update}",
            f"📌 TOTAL LAPORAN : {total_reports}",
            "",
            f"⏰ Auto update {now.strftime('%H:%M')} WIB",
        ]
    )
    return "\n".join(lines)


async def remember_report_manyar_group(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return

    db: Database = context.application.bot_data["db"]
    text = (message.text or message.caption or "").strip()
    command = text.split(maxsplit=1)[0].lower().split("@", 1)[0] if text else ""

    standalone_report_group = _normalized(chat.title) == _target_title()
    registered_topics = await asyncio.to_thread(list_registered_topics, db.db_path)
    current_topic = (chat.id, message.message_thread_id) if message.message_thread_id is not None else None
    bound_report_topic = current_topic in registered_topics if current_topic is not None else False

    if not standalone_report_group and not bound_report_topic:
        return

    await asyncio.to_thread(_save_target, db.db_path, chat.id)

    if command != "/progres":
        return

    settings = context.application.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    area_label, sto_code = await asyncio.to_thread(
        _progress_identity_for_topic,
        db.db_path,
        chat.id,
        message.message_thread_id,
    )
    rows = await asyncio.to_thread(
        _today_progress_rows,
        db.db_path,
        now.date().isoformat(),
        sto_code,
    )
    await message.reply_text(build_hourly_progress_text(rows, now, area_label))


async def send_hourly_report_progress(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)

    if now.hour < AUTO_PROGRESS_START_HOUR or now.hour > AUTO_PROGRESS_END_HOUR:
        logging.debug(
            "Auto progress REPORT dilewati di luar jam aktif: %s",
            now.strftime("%H:%M"),
        )
        return

    topics = await asyncio.to_thread(list_registered_topics, db.db_path)
    if topics:
        sent = 0
        for chat_id, thread_id in topics:
            area_label, sto_code = await asyncio.to_thread(
                _progress_identity_for_topic,
                db.db_path,
                chat_id,
                thread_id,
            )
            rows = await asyncio.to_thread(
                _today_progress_rows,
                db.db_path,
                now.date().isoformat(),
                sto_code,
            )
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    message_thread_id=thread_id,
                    text=build_hourly_progress_text(rows, now, area_label),
                )
                sent += 1
            except Exception:
                logging.exception(
                    "Gagal mengirim auto progress %s (%s) ke chat_id=%s thread_id=%s",
                    area_label,
                    sto_code,
                    chat_id,
                    thread_id,
                )
        logging.info("Auto progress REPORT terkirim ke %s/%s topic", sent, len(topics))
        return

    chat_id = await asyncio.to_thread(_get_target, db.db_path)
    if chat_id is None:
        logging.warning(
            "Auto progress REPORT belum dikirim: target REPORT belum tersimpan."
        )
        return

    rows = await asyncio.to_thread(
        _today_progress_rows,
        db.db_path,
        now.date().isoformat(),
        PRIMARY_STO_CODE,
    )
    await context.bot.send_message(
        chat_id=chat_id,
        text=build_hourly_progress_text(rows, now, PRIMARY_PROGRESS_LABEL),
    )
