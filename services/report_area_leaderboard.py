from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes

from database import Database
from services.report_area_tracking import area_order_condition, ensure_area_tracking_table

MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]
DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def _period_bounds(day: date) -> tuple[date, date]:
    days_since_friday = (day.weekday() - 4) % 7
    start = day - timedelta(days=days_since_friday)
    return start, start + timedelta(days=6)


def _format_date(value: date) -> str:
    return f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}"


def _registered_area_topics(database_path: Path) -> list[tuple[int, int, str, str]]:
    with sqlite3.connect(database_path) as conn:
        try:
            rows = conn.execute(
                """
                SELECT chat_id, thread_id,
                       UPPER(TRIM(area_label)) AS area_label,
                       UPPER(TRIM(sto_code)) AS sto_code
                FROM report_topics
                WHERE TRIM(area_label) != '' AND TRIM(sto_code) != ''
                ORDER BY added_at ASC, chat_id ASC, thread_id ASC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    return [
        (int(chat_id), int(thread_id), str(area), str(sto))
        for chat_id, thread_id, area, sto in rows
    ]


def _leaderboard_rows(
    database_path: Path,
    period_start: date,
    sto_code: str,
) -> list[tuple[str, int]]:
    with sqlite3.connect(database_path) as conn:
        ensure_area_tracking_table(conn)
        predicate, params = area_order_condition(sto_code, "r")
        rows = conn.execute(
            f"""
            SELECT MAX(r.technician_name) AS technician_name,
                   COUNT(DISTINCT r.service_number) AS total
            FROM report_group_orders r
            WHERE r.period_start = ?
              AND {predicate}
            GROUP BY r.technician_nik
            ORDER BY total DESC, UPPER(MAX(r.technician_name)) ASC
            """,
            (period_start.isoformat(), *params),
        ).fetchall()
    return [(str(name), int(total)) for name, total in rows]


def _daily_close_rows(
    database_path: Path,
    day: date,
    sto_code: str,
) -> list[tuple[str, int]]:
    with sqlite3.connect(database_path) as conn:
        ensure_area_tracking_table(conn)
        predicate, params = area_order_condition(sto_code, "r")
        rows = conn.execute(
            f"""
            SELECT MAX(r.technician_name) AS technician_name,
                   COUNT(DISTINCT r.service_number) AS total
            FROM report_group_orders r
            WHERE substr(r.message_date, 1, 10) = ?
              AND {predicate}
            GROUP BY r.technician_nik
            ORDER BY total DESC, UPPER(MAX(r.technician_name)) ASC
            """,
            (day.isoformat(), *params),
        ).fetchall()
    return [(str(name), int(total)) for name, total in rows]


def build_leaderboard_text(rows: list[tuple[str, int]], today: date, area: str) -> str:
    period_start, period_end = _period_bounds(today)
    lines = [
        f"🏆 LEADERBOARD {area.upper()}",
        f"📆 {_format_date(period_start)} - {_format_date(period_end)}",
        f"📅 Update: {DAY_NAMES[today.weekday()]}, {_format_date(today)}",
        "",
    ]
    if rows:
        width = max(len(name.upper()) for name, _ in rows)
        for index, (name, total) in enumerate(rows, start=1):
            lines.append(f"{index}. {name.upper().ljust(width)} : {total} order")
    else:
        lines.append(f"Belum ada order STO {area.upper()} yang tercatat pada periode ini.")

    lines.append("")
    remaining = (period_end - today).days
    if remaining <= 0:
        lines.append("🏁 Periode selesai. Terima kasih atas kerja keras semuanya!")
    else:
        lines.append(f"🔥 Masih ada {remaining} hari lagi. Tetap semangat! 💪")
    return "\n".join(lines)


def build_daily_close_text(rows: list[tuple[str, int]], today: date, area: str) -> str:
    lines = [
        f"📊 CLOSE HARI INI - {area.upper()}",
        f"📅 {DAY_NAMES[today.weekday()]}, {_format_date(today)}",
        "",
    ]
    if rows:
        width = max(len(name.upper()) for name, _ in rows)
        for index, (name, total) in enumerate(rows, start=1):
            lines.append(f"{index}. {name.upper().ljust(width)} : {total} close")
        lines.extend(["", f"TOTAL CLOSE {area.upper()} HARI INI : {sum(total for _, total in rows)}"])
    else:
        lines.append(f"Belum ada close {area.upper()} yang tercatat hari ini.")
    lines.extend(["", "💪 Terima kasih untuk kerja keras hari ini."])
    return "\n".join(lines)


async def send_report_leaderboard(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    period_start, _ = _period_bounds(today)
    topics = await asyncio.to_thread(_registered_area_topics, db.db_path)
    if not topics:
        logging.warning("Leaderboard area belum dikirim: belum ada topic REPORT ber-area yang terdaftar")
        return

    for chat_id, thread_id, area, sto_code in topics:
        rows = await asyncio.to_thread(_leaderboard_rows, db.db_path, period_start, sto_code)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                message_thread_id=thread_id,
                text=build_leaderboard_text(rows, today, area),
            )
        except Exception:
            logging.exception(
                "Gagal mengirim leaderboard area=%s sto=%s chat_id=%s thread_id=%s",
                area, sto_code, chat_id, thread_id,
            )


async def send_daily_close(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    topics = await asyncio.to_thread(_registered_area_topics, db.db_path)
    if not topics:
        logging.warning("Close harian area belum dikirim: belum ada topic REPORT ber-area yang terdaftar")
        return

    for chat_id, thread_id, area, sto_code in topics:
        rows = await asyncio.to_thread(_daily_close_rows, db.db_path, today, sto_code)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                message_thread_id=thread_id,
                text=build_daily_close_text(rows, today, area),
            )
        except Exception:
            logging.exception(
                "Gagal mengirim close harian area=%s sto=%s chat_id=%s thread_id=%s",
                area, sto_code, chat_id, thread_id,
            )
