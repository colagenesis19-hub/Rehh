from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from database import Database
from services.report_area_tracking import record_area_order
from services.report_leaderboard import (
    NO_SERVICE_RE,
    REPORT_GROUP_SETTING_KEY,
    REPORT_THREAD_SETTING_KEY,
    TECH_RE,
    _period_bounds,
    _save_report_target,
    _store_order,
    _stored_setting,
    _target_group_title,
    _technician_daily_total,
    _technician_period_total,
    _normalized_title,
)

MAX_REPORT_TOPICS = 2
BIND_COMMANDS = {"/setreport", "/setreportmanyar", "/setreportjagir"}
AREA_BY_COMMAND = {
    "/setreportmanyar": ("MANYAR", "MYR"),
    "/setreportjagir": ("JAGIR", "JGR"),
}


def _command_from_text(text: str) -> str:
    token = text.split(maxsplit=1)[0].lower().split("@", 1)[0]
    return token.rstrip(":")


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _ensure_topic_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_topics (
            chat_id INTEGER NOT NULL,
            thread_id INTEGER NOT NULL,
            added_at TEXT NOT NULL,
            area_label TEXT NOT NULL DEFAULT '',
            sto_code TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (chat_id, thread_id)
        )
        """
    )
    columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(report_topics)").fetchall()
    }
    if "area_label" not in columns:
        conn.execute("ALTER TABLE report_topics ADD COLUMN area_label TEXT NOT NULL DEFAULT ''")
    if "sto_code" not in columns:
        conn.execute("ALTER TABLE report_topics ADD COLUMN sto_code TEXT NOT NULL DEFAULT ''")


def _repair_legacy_topic_identities(conn: sqlite3.Connection) -> None:
    """Backfill old two-topic rows that predate area_label/sto_code columns."""
    _ensure_topic_table(conn)
    rows = conn.execute(
        """
        SELECT chat_id, thread_id, UPPER(TRIM(area_label)), UPPER(TRIM(sto_code))
        FROM report_topics
        ORDER BY added_at ASC, chat_id ASC, thread_id ASC
        """
    ).fetchall()
    if not rows:
        return

    used = {str(sto or "").strip().upper() for _, _, _, sto in rows if str(sto or "").strip()}
    missing = [row for row in rows if not str(row[2] or "").strip() or not str(row[3] or "").strip()]

    for chat_id, thread_id, _, _ in missing:
        if "MYR" not in used:
            area_label, sto_code = "MANYAR", "MYR"
        elif "JGR" not in used:
            area_label, sto_code = "JAGIR", "JGR"
        else:
            break
        conn.execute(
            """
            UPDATE report_topics
            SET area_label = ?, sto_code = ?
            WHERE chat_id = ? AND thread_id = ?
            """,
            (area_label, sto_code, chat_id, thread_id),
        )
        used.add(sto_code)
        logging.info(
            "Legacy REPORT topic identity repaired: chat_id=%s thread_id=%s area=%s sto=%s",
            chat_id,
            thread_id,
            area_label,
            sto_code,
        )


def _seed_legacy_target(database_path: Path) -> None:
    group_id = _stored_setting(database_path, REPORT_GROUP_SETTING_KEY)
    thread_id = _stored_setting(database_path, REPORT_THREAD_SETTING_KEY)
    with sqlite3.connect(database_path) as conn:
        _ensure_topic_table(conn)
        if group_id is not None and thread_id is not None:
            conn.execute(
                """
                INSERT OR IGNORE INTO report_topics (
                    chat_id, thread_id, added_at, area_label, sto_code
                ) VALUES (?, ?, ?, '', '')
                """,
                (group_id, thread_id, _utc_now()),
            )
        _repair_legacy_topic_identities(conn)


def _topic_identity(
    database_path: Path,
    chat_id: int,
    thread_id: int,
) -> tuple[str, str] | None:
    _seed_legacy_target(database_path)
    with sqlite3.connect(database_path) as conn:
        _ensure_topic_table(conn)
        row = conn.execute(
            """
            SELECT area_label, sto_code
            FROM report_topics
            WHERE chat_id = ? AND thread_id = ?
            """,
            (chat_id, thread_id),
        ).fetchone()
    if not row:
        return None
    area_label = str(row[0] or "").strip().upper()
    sto_code = str(row[1] or "").strip().upper()
    if not area_label or not sto_code:
        return None
    return area_label, sto_code


def get_topic_identity(
    database_path: Path,
    chat_id: int,
    thread_id: int,
) -> tuple[str, str] | None:
    return _topic_identity(database_path, chat_id, thread_id)


def _default_identity_for_topic(
    database_path: Path,
    chat_id: int,
    thread_id: int,
) -> tuple[str, str]:
    existing = _topic_identity(database_path, chat_id, thread_id)
    if existing:
        return existing

    primary_group = _stored_setting(database_path, REPORT_GROUP_SETTING_KEY)
    primary_thread = _stored_setting(database_path, REPORT_THREAD_SETTING_KEY)
    if primary_group == chat_id and primary_thread == thread_id:
        return "MANYAR", "MYR"
    return "JAGIR", "JGR"


def _add_topic(
    database_path: Path,
    chat_id: int,
    thread_id: int,
    area_label: str,
    sto_code: str,
) -> tuple[str, int]:
    _seed_legacy_target(database_path)
    area_label = area_label.strip().upper()
    sto_code = sto_code.strip().upper()
    with sqlite3.connect(database_path) as conn:
        _ensure_topic_table(conn)
        exists = conn.execute(
            "SELECT 1 FROM report_topics WHERE chat_id = ? AND thread_id = ?",
            (chat_id, thread_id),
        ).fetchone()
        if exists:
            conn.execute(
                """
                UPDATE report_topics
                SET area_label = ?, sto_code = ?
                WHERE chat_id = ? AND thread_id = ?
                """,
                (area_label, sto_code, chat_id, thread_id),
            )
            total = int(conn.execute("SELECT COUNT(*) FROM report_topics").fetchone()[0])
            return "UPDATED", total

        total = int(conn.execute("SELECT COUNT(*) FROM report_topics").fetchone()[0])
        if total >= MAX_REPORT_TOPICS:
            return "FULL", total

        conn.execute(
            """
            INSERT INTO report_topics (
                chat_id, thread_id, added_at, area_label, sto_code
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (chat_id, thread_id, _utc_now(), area_label, sto_code),
        )
        total += 1
        return "ADDED", total


def _is_registered_topic(database_path: Path, chat_id: int, thread_id: int) -> bool:
    _seed_legacy_target(database_path)
    with sqlite3.connect(database_path) as conn:
        _ensure_topic_table(conn)
        row = conn.execute(
            "SELECT 1 FROM report_topics WHERE chat_id = ? AND thread_id = ?",
            (chat_id, thread_id),
        ).fetchone()
        return row is not None


def _topic_count(database_path: Path) -> int:
    return len(list_registered_topics(database_path))


def list_registered_topics(database_path: Path) -> list[tuple[int, int]]:
    """Return all active REPORT topics, including the legacy primary target."""
    _seed_legacy_target(database_path)
    with sqlite3.connect(database_path) as conn:
        _ensure_topic_table(conn)
        rows = conn.execute(
            "SELECT chat_id, thread_id FROM report_topics ORDER BY added_at ASC, chat_id ASC, thread_id ASC"
        ).fetchall()
    return [(int(chat_id), int(thread_id)) for chat_id, thread_id in rows]


async def handle_multi_report_topic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bind up to two REPORT topics and accept /sto without double-counting."""
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return
    if _normalized_title(chat.title) != _target_group_title():
        return

    text = (message.text or message.caption or "").strip()
    if not text:
        return
    command = _command_from_text(text)
    db: Database = context.application.bot_data["db"]

    if command in BIND_COMMANDS:
        thread_id = message.message_thread_id
        if thread_id is None:
            await message.reply_text("❌ /setreport harus dikirim dari dalam topic REPORT.")
            raise ApplicationHandlerStop

        identity = AREA_BY_COMMAND.get(command)
        if identity is None:
            identity = await asyncio.to_thread(
                _default_identity_for_topic,
                db.db_path,
                chat.id,
                thread_id,
            )
        area_label, sto_code = identity

        action, total = await asyncio.to_thread(
            _add_topic,
            db.db_path,
            chat.id,
            thread_id,
            area_label,
            sto_code,
        )
        primary_group = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_GROUP_SETTING_KEY)
        primary_thread = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_THREAD_SETTING_KEY)
        if primary_group is None or primary_thread is None:
            await asyncio.to_thread(_save_report_target, db.db_path, chat.id, thread_id)

        if action == "FULL":
            await message.reply_text(
                f"❌ Maksimal {MAX_REPORT_TOPICS} topic REPORT. Saat ini sudah terdaftar {total} topic."
            )
        elif action == "UPDATED":
            await message.reply_text(
                "✅ TOPIC REPORT DIPERBARUI\n"
                f"📍 AREA : {area_label}\n"
                f"🏢 STO : {sto_code}\n"
                f"📌 TOTAL TOPIC : {total}/{MAX_REPORT_TOPICS}"
            )
        else:
            await message.reply_text(
                "✅ TOPIC REPORT BERHASIL DITAMBAHKAN\n"
                f"📍 AREA : {area_label}\n"
                f"🏢 STO : {sto_code}\n"
                f"📌 TOTAL TOPIC : {total}/{MAX_REPORT_TOPICS}"
            )
        logging.info(
            "REPORT topic bind: chat_id=%s thread_id=%s area=%s sto=%s action=%s total=%s",
            chat.id,
            thread_id,
            area_label,
            sto_code,
            action,
            total,
        )
        raise ApplicationHandlerStop

    if command != "/sto" or message.message_thread_id is None:
        return

    registered = await asyncio.to_thread(
        _is_registered_topic,
        db.db_path,
        chat.id,
        message.message_thread_id,
    )
    if not registered:
        return

    primary_group = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_GROUP_SETTING_KEY)
    primary_thread = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_THREAD_SETTING_KEY)
    if chat.id == primary_group and message.message_thread_id == primary_thread:
        return

    service_match = NO_SERVICE_RE.search(text)
    tech_match = TECH_RE.search(text)
    if not service_match or not tech_match:
        await message.reply_text(
            "❌ REPORT belum bisa disimpan. Pastikan /sto berisi NO SERVICE dan NIK NAMA TEKNISI."
        )
        raise ApplicationHandlerStop

    settings = context.application.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    message_dt = message.date.astimezone(tz)
    period_start, _ = _period_bounds(message_dt.date())
    service_number = service_match.group(1).strip()
    technician_nik = tech_match.group(1).strip()
    technician_name = tech_match.group(2).strip()

    action = await asyncio.to_thread(
        _store_order,
        db.db_path,
        service_number,
        period_start,
        technician_nik,
        technician_name,
        message_dt,
        chat.id,
        message.message_id,
    )

    identity = await asyncio.to_thread(
        _topic_identity,
        db.db_path,
        chat.id,
        message.message_thread_id,
    )
    if identity:
        area_label, sto_code = identity
        await asyncio.to_thread(
            record_area_order,
            db.db_path,
            service_number,
            period_start.isoformat(),
            sto_code,
            area_label,
        )

    total_today = await asyncio.to_thread(
        _technician_daily_total,
        db.db_path,
        message_dt.date(),
        technician_nik,
    )
    total_period = await asyncio.to_thread(
        _technician_period_total,
        db.db_path,
        period_start,
        technician_nik,
    )

    if action == "INSERTED":
        status = "✅ REPORT SUDAH TERSIMPAN"
    elif action == "UPDATED":
        status = "♻️ REPORT DIPERBARUI"
    else:
        status = "ℹ️ REPORT SUDAH TERSIMPAN"

    await message.reply_text(
        f"{status}\n"
        f"🌐 INET : {service_number}\n"
        f"👷 TEKNISI : {technician_name.upper()}\n"
        f"📊 HARI INI : {total_today} order\n"
        f"📊 TOTAL PERIODE : {total_period} order"
    )
    logging.info(
        "Secondary REPORT /sto: inet=%s teknisi=%s action=%s chat_id=%s thread_id=%s topics=%s",
        service_number,
        technician_nik,
        action,
        chat.id,
        message.message_thread_id,
        await asyncio.to_thread(_topic_count, db.db_path),
    )
    raise ApplicationHandlerStop
