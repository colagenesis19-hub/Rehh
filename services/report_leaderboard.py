from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database


DEFAULT_REPORT_GROUP_TITLE = "REPLACEMENT 200K | MANJA"
DEFAULT_STO_RECAP_GROUP_TITLE = "REPORT MANYAR"
REPORT_GROUP_SETTING_KEY = "report_group_id"
REPORT_THREAD_SETTING_KEY = "report_thread_id"
REPORT_BIND_COMMANDS = {"/setreport", "/setreportmanyar"}
REPORT_MANUAL_COMMANDS = {"/leaderboard", "/closeharian"}

MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]
DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

NO_SERVICE_RE = re.compile(r"(?:NO\s*SERVICE|INET)\s*:\s*(\d{6,})", re.IGNORECASE)
TECH_RE = re.compile(
    r"(?:NIK\s*NAMA\s*TEKNISI|TEKNISI)\s*:\s*(\d+)\s*\|\s*([^\n\r]+)",
    re.IGNORECASE,
)


def _normalized_title(value: str | None) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _target_group_title() -> str:
    return _normalized_title(os.getenv("REPORT_GROUP_TITLE", DEFAULT_REPORT_GROUP_TITLE))


def _sto_recap_group_title() -> str:
    return _normalized_title(
        os.getenv("STO_RECAP_GROUP_TITLE", DEFAULT_STO_RECAP_GROUP_TITLE)
    )


def _period_bounds(day: date) -> tuple[date, date]:
    days_since_friday = (day.weekday() - 4) % 7
    start = day - timedelta(days=days_since_friday)
    end = start + timedelta(days=6)
    return start, end


def _format_date(value: date) -> str:
    return f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}"


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_group_orders (
            service_number TEXT NOT NULL,
            period_start TEXT NOT NULL,
            technician_nik TEXT NOT NULL,
            technician_name TEXT NOT NULL,
            message_date TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            message_id INTEGER,
            created_at TEXT NOT NULL,
            PRIMARY KEY (service_number, period_start)
        )
        """
    )


def _stored_setting(database_path: Path, key: str) -> int | None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_tables(conn)
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
        logging.error("Setting %s tidak valid: %r", key, row[0])
        return None


def _save_report_target(database_path: Path, group_id: int, thread_id: int) -> None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_tables(conn)
        now = _utc_now()
        conn.execute(
            """
            INSERT INTO report_bot_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (REPORT_GROUP_SETTING_KEY, str(group_id), now),
        )
        conn.execute(
            """
            INSERT INTO report_bot_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (REPORT_THREAD_SETTING_KEY, str(thread_id), now),
        )
        conn.commit()
    finally:
        conn.close()


def _store_order(
    database_path: Path,
    service_number: str,
    period_start: date,
    technician_nik: str,
    technician_name: str,
    message_date: datetime,
    chat_id: int,
    message_id: int | None,
) -> str:
    """Store one /sto per INET/period and let the latest real /sto correct ownership."""
    conn = sqlite3.connect(database_path)
    try:
        _ensure_tables(conn)
        period_iso = period_start.isoformat()
        clean_name = technician_name.strip()
        message_iso = message_date.isoformat()
        existing = conn.execute(
            """
            SELECT technician_nik, technician_name, message_date, chat_id, message_id
            FROM report_group_orders
            WHERE service_number = ? AND period_start = ?
            """,
            (service_number, period_iso),
        ).fetchone()

        if existing is None:
            conn.execute(
                """
                INSERT INTO report_group_orders (
                    service_number, period_start, technician_nik, technician_name,
                    message_date, chat_id, message_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    service_number,
                    period_iso,
                    technician_nik,
                    clean_name,
                    message_iso,
                    chat_id,
                    message_id,
                    _utc_now(),
                ),
            )
            conn.commit()
            return "INSERTED"

        same_report = (
            str(existing[0]) == technician_nik
            and str(existing[1]).strip() == clean_name
            and str(existing[2]) == message_iso
            and int(existing[3]) == chat_id
            and existing[4] == message_id
        )
        if same_report:
            return "UNCHANGED"

        conn.execute(
            """
            UPDATE report_group_orders
            SET technician_nik = ?,
                technician_name = ?,
                message_date = ?,
                chat_id = ?,
                message_id = ?,
                created_at = ?
            WHERE service_number = ? AND period_start = ?
            """,
            (
                technician_nik,
                clean_name,
                message_iso,
                chat_id,
                message_id,
                _utc_now(),
                service_number,
                period_iso,
            ),
        )
        conn.commit()
        return "UPDATED"
    finally:
        conn.close()


def _technician_period_total(
    database_path: Path,
    period_start: date,
    technician_nik: str,
) -> int:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_tables(conn)
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM report_group_orders
            WHERE period_start = ? AND technician_nik = ?
            """,
            (period_start.isoformat(), technician_nik),
        ).fetchone()
        conn.commit()
        return int(row[0] or 0)
    finally:
        conn.close()


def _technician_daily_total(
    database_path: Path,
    day: date,
    technician_nik: str,
) -> int:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_tables(conn)
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT service_number)
            FROM report_group_orders
            WHERE substr(message_date, 1, 10) = ? AND technician_nik = ?
            """,
            (day.isoformat(), technician_nik),
        ).fetchone()
        conn.commit()
        return int(row[0] or 0)
    finally:
        conn.close()


def _leaderboard_rows(database_path: Path, period_start: date) -> list[tuple[str, int]]:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_tables(conn)
        rows = conn.execute(
            """
            SELECT MAX(technician_name) AS technician_name, COUNT(*) AS total
            FROM report_group_orders
            WHERE period_start = ?
            GROUP BY technician_nik
            ORDER BY total DESC, UPPER(MAX(technician_name)) ASC
            """,
            (period_start.isoformat(),),
        ).fetchall()
        conn.commit()
        return [(str(name), int(total)) for name, total in rows]
    finally:
        conn.close()


def _daily_close_rows(database_path: Path, day: date) -> list[tuple[str, int]]:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_tables(conn)
        rows = conn.execute(
            """
            SELECT MAX(technician_name) AS technician_name,
                   COUNT(DISTINCT service_number) AS total
            FROM report_group_orders
            WHERE substr(message_date, 1, 10) = ?
            GROUP BY technician_nik
            ORDER BY total DESC, UPPER(MAX(technician_name)) ASC
            """,
            (day.isoformat(),),
        ).fetchall()
        conn.commit()
        return [(str(name), int(total)) for name, total in rows]
    finally:
        conn.close()


async def _notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    settings = context.application.bot_data["settings"]
    if not settings.admin_ids:
        logging.warning("Tidak ada ADMIN_IDS untuk menerima notifikasi binding REPORT MANYAR")
        return

    for admin_id in settings.admin_ids:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text)
        except Exception:
            logging.exception("Gagal mengirim notifikasi binding REPORT MANYAR ke admin_id=%s", admin_id)


async def capture_sto_recap_group_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return
    if _normalized_title(chat.title) != _sto_recap_group_title():
        return

    text = (message.text or message.caption or "").strip()
    if not text:
        return
    command = text.split(maxsplit=1)[0].lower().split("@", 1)[0]
    if command != "/sto":
        return

    service_match = NO_SERVICE_RE.search(text)
    tech_match = TECH_RE.search(text)
    if not service_match or not tech_match:
        await message.reply_text(
            "❌ STO belum bisa direkap. Pastikan ada NO SERVICE dan NIK NAMA TEKNISI."
        )
        return

    db: Database = context.application.bot_data["db"]
    settings = context.application.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    message_dt = message.date.astimezone(tz)
    period_start, period_end = _period_bounds(message_dt.date())

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
        status = "✅ STO TEREKAP"
    elif action == "UPDATED":
        status = "♻️ STO DIPERBARUI"
    else:
        status = "ℹ️ STO SUDAH TEREKAP"

    await message.reply_text(
        f"{status}\n"
        f"🌐 INET : {service_number}\n"
        f"👷 TEKNISI : {technician_name.upper()}\n"
        f"📊 HARI INI : {total_today} order\n"
        f"📊 TOTAL PERIODE : {total_period} order\n"
        f"📅 PERIODE : {_format_date(period_start)} - {_format_date(period_end)}"
    )

    logging.info(
        "STO recap group: inet=%s teknisi=%s (%s) action=%s today=%s period=%s",
        service_number,
        technician_name,
        technician_nik,
        action,
        total_today,
        total_period,
    )


async def capture_report_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return
    if _normalized_title(chat.title) != _target_group_title():
        return

    db: Database = context.application.bot_data["db"]
    settings = context.application.bot_data["settings"]
    text = (message.text or message.caption or "").strip()
    command = text.split(maxsplit=1)[0].lower().split("@", 1)[0] if text else ""

    if command in REPORT_BIND_COMMANDS:
        thread_id = message.message_thread_id
        if thread_id is None:
            await _notify_admins(
                context,
                "❌ Binding REPORT MANYAR gagal. /setreportmanyar harus dikirim dari topic REPORT MANYAR.",
            )
            return
        await asyncio.to_thread(_save_report_target, db.db_path, chat.id, thread_id)
        await _notify_admins(
            context,
            "✅ Topic REPORT MANYAR berhasil dikunci untuk leaderboard.\n"
            f"Chat ID: {chat.id}\n"
            f"Thread ID: {thread_id}",
        )
        logging.info("REPORT MANYAR bound: chat_id=%s thread_id=%s", chat.id, thread_id)
        return

    stored_group_id = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_GROUP_SETTING_KEY)
    stored_thread_id = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_THREAD_SETTING_KEY)
    if stored_group_id is None or stored_thread_id is None:
        return
    if chat.id != stored_group_id or message.message_thread_id != stored_thread_id:
        return

    if command in REPORT_MANUAL_COMMANDS:
        user = update.effective_user
        if not user or user.id not in settings.admin_ids:
            return
        if command == "/leaderboard":
            await send_report_leaderboard(context)
        else:
            await send_daily_close(context)
        return

    # Hanya /sto yang boleh menambah/memperbarui hitungan report.
    # Pesan /report, reply bot, atau teks lain yang kebetulan punya INET/TEKNISI diabaikan.
    if command != "/sto":
        return

    service_match = NO_SERVICE_RE.search(text)
    tech_match = TECH_RE.search(text)
    if not service_match or not tech_match:
        await message.reply_text(
            "❌ REPORT belum bisa disimpan. Pastikan /sto berisi NO SERVICE dan NIK NAMA TEKNISI."
        )
        return

    tz = ZoneInfo(settings.timezone)
    message_dt = message.date.astimezone(tz)
    period_start, period_end = _period_bounds(message_dt.date())

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
        "Report /sto captured: inet=%s teknisi=%s (%s) action=%s today=%s period=%s range=%s..%s thread_id=%s",
        service_number,
        technician_name,
        technician_nik,
        action,
        total_today,
        total_period,
        period_start,
        period_end,
        message.message_thread_id,
    )


def build_leaderboard_text(rows: list[tuple[str, int]], today: date) -> str:
    period_start, period_end = _period_bounds(today)
    lines = [
        "🏆 LEADERBOARD PERIODE BERJALAN",
        f"📆 {_format_date(period_start)} - {_format_date(period_end)}",
        f"📅 Update: {DAY_NAMES[today.weekday()]}, {_format_date(today)}",
        "",
    ]

    if rows:
        width = max(len(name.upper()) for name, _ in rows)
        for index, (name, total) in enumerate(rows, start=1):
            lines.append(f"{index}. {name.upper().ljust(width)} : {total} order")
    else:
        lines.append("Belum ada order yang tercatat pada periode ini.")

    lines.append("")
    remaining = (period_end - today).days
    if remaining <= 0:
        lines.append("🏁 Periode selesai. Terima kasih atas kerja keras semuanya!")
    else:
        lines.append(
            f"🔥 Masih ada {remaining} hari lagi. Tetap semangat, setiap order adalah langkah menuju hasil terbaik! 💪"
        )
    return "\n".join(lines)


def build_daily_close_text(rows: list[tuple[str, int]], today: date) -> str:
    lines = [
        "📊 CLOSE HARI INI",
        f"📅 {DAY_NAMES[today.weekday()]}, {_format_date(today)}",
        "",
    ]
    if rows:
        width = max(len(name.upper()) for name, _ in rows)
        for index, (name, total) in enumerate(rows, start=1):
            lines.append(f"{index}. {name.upper().ljust(width)} : {total} close")
        lines.extend(["", f"TOTAL CLOSE HARI INI : {sum(total for _, total in rows)}"])
    else:
        lines.append("Belum ada close yang tercatat hari ini.")
    lines.extend(["", "💪 Terima kasih untuk kerja keras hari ini. Tetap jaga semangat dan kualitas pekerjaan!"])
    return "\n".join(lines)


async def _report_target(db: Database) -> tuple[int | None, int | None]:
    group_id = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_GROUP_SETTING_KEY)
    thread_id = await asyncio.to_thread(_stored_setting, db.db_path, REPORT_THREAD_SETTING_KEY)
    return group_id, thread_id


async def send_report_leaderboard(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    period_start, _ = _period_bounds(today)

    group_id, thread_id = await _report_target(db)
    if group_id is None or thread_id is None:
        logging.warning("Leaderboard belum dikirim: topic REPORT MANYAR belum di-bind dengan /setreport")
        return

    rows = await asyncio.to_thread(_leaderboard_rows, db.db_path, period_start)
    await context.bot.send_message(
        chat_id=group_id,
        message_thread_id=thread_id,
        text=build_leaderboard_text(rows, today),
    )


async def send_daily_close(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()

    group_id, thread_id = await _report_target(db)
    if group_id is None or thread_id is None:
        logging.warning("Close harian belum dikirim: topic REPORT MANYAR belum di-bind dengan /setreport")
        return

    rows = await asyncio.to_thread(_daily_close_rows, db.db_path, today)
    await context.bot.send_message(
        chat_id=group_id,
        message_thread_id=thread_id,
        text=build_daily_close_text(rows, today),
    )