from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database
from services.auth import require_technician


DAY_NAMES = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

MOTIVATION_MESSAGES = [
    "💪 Tetap semangat! Setiap order yang selesai adalah satu langkah maju.",
    "🔥 Kerja bagus hari ini. Jaga ritme, jaga kualitas, dan tetap semangat!",
    "🚀 Sedikit demi sedikit, hasil besar terbentuk dari konsistensi setiap hari.",
    "⚡ Tetap fokus dan semangat. Pekerjaan rapi hari ini memudahkan langkah berikutnya.",
    "🌟 Terima kasih untuk kerja kerasnya. Istirahat yang cukup dan lanjutkan besok dengan semangat baru!",
    "🛠️ Kerja tuntas, data rapi, hati tenang. Semangat terus!",
    "🏆 Konsisten lebih penting daripada terburu-buru. Mantap, lanjutkan!",
]


def _format_date(value: date) -> str:
    return f"{value.day} {MONTH_NAMES[value.month - 1]} {value.year}"


def _motivation(seed_day: date) -> str:
    # Deterministik per tanggal agar semua teknisi mendapat pesan yang sama pada hari itu.
    index = seed_day.toordinal() % len(MOTIVATION_MESSAGES)
    return MOTIVATION_MESSAGES[index]


def _period_bounds(day: date) -> tuple[date, date]:
    days_since_friday = (day.weekday() - 4) % 7
    start = day - timedelta(days=days_since_friday)
    end = start + timedelta(days=6)
    return start, end


def _previous_period_bounds(day: date) -> tuple[date, date]:
    current_start, _ = _period_bounds(day)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=6)
    return previous_start, previous_end


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat() + "Z"


def _local_day_bounds(day: date, tz: ZoneInfo) -> tuple[str, str]:
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return _utc_iso(start_local), _utc_iso(end_local)


def _local_period_bounds(start_day: date, end_day: date, tz: ZoneInfo) -> tuple[str, str]:
    start_local = datetime.combine(start_day, time.min, tzinfo=tz)
    end_local = datetime.combine(end_day + timedelta(days=1), time.min, tzinfo=tz)
    return _utc_iso(start_local), _utc_iso(end_local)


async def initialize_recap_delivery_log(db: Database) -> None:
    async with db._lock:
        with db.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recap_delivery_log (
                    telegram_id INTEGER NOT NULL,
                    recap_type TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (telegram_id, recap_type, period_start, period_end)
                )
                """
            )


async def _history_rows(
    db: Database,
    telegram_id: int,
    start_utc: str,
    end_utc: str,
):
    async with db._lock:
        with db.connection() as conn:
            return conn.execute(
                """
                SELECT kind, ticket_id, service_number, created_at
                FROM histories
                WHERE telegram_id = ?
                  AND created_at >= ?
                  AND created_at < ?
                ORDER BY created_at ASC
                """,
                (telegram_id, start_utc, end_utc),
            ).fetchall()


def _service_key(row) -> str:
    service = (row["service_number"] or "").strip()
    if service and service != "-":
        return service
    ticket = (row["ticket_id"] or "").strip()
    if ticket and ticket != "-":
        return f"TICKET:{ticket}"
    return f"ROW:{row['created_at']}:{row['kind']}"


def _summarize(rows) -> tuple[list[tuple[str, str]], int]:
    jobs: dict[str, tuple[str, str]] = {}
    for row in rows:
        key = _service_key(row)
        service = (row["service_number"] or "-").strip() or "-"
        ticket = (row["ticket_id"] or "-").strip() or "-"
        jobs.setdefault(key, (service, ticket))
    return list(jobs.values()), len(jobs)


def _append_jobs(lines: list[str], jobs: list[tuple[str, str]]) -> None:
    if not jobs:
        return
    lines.append("")
    for index, (service, ticket) in enumerate(jobs, start=1):
        lines.append(f"{index}. {service} | {ticket}")


def _append_motivation(lines: list[str], seed_day: date) -> None:
    lines.extend(["", _motivation(seed_day)])


async def build_daily_recap_text(
    db: Database,
    telegram_id: int,
    technician_name: str,
    day: date,
    timezone_name: str,
) -> str:
    tz = ZoneInfo(timezone_name)
    day_start, day_end = _local_day_bounds(day, tz)
    rows = await _history_rows(db, telegram_id, day_start, day_end)
    jobs, total = _summarize(rows)

    lines = [
        "📊 REKAP PEKERJAAN HARIAN",
        f"📅 {DAY_NAMES[day.weekday()]}, {_format_date(day)}",
        f"👷 {technician_name}",
        "",
        f"Total pekerjaan : {total}",
    ]
    _append_jobs(lines, jobs)
    _append_motivation(lines, day)
    return "\n".join(lines)


async def build_weekly_recap_text_for_period(
    db: Database,
    telegram_id: int,
    technician_name: str,
    period_start: date,
    period_end: date,
    timezone_name: str,
) -> str:
    tz = ZoneInfo(timezone_name)
    start_utc, end_utc = _local_period_bounds(period_start, period_end, tz)
    rows = await _history_rows(db, telegram_id, start_utc, end_utc)
    jobs, total = _summarize(rows)

    lines = [
        "📈 REKAP PEKERJAAN MINGGUAN",
        f"📆 Periode: {_format_date(period_start)} - {_format_date(period_end)}",
        f"👷 {technician_name}",
        "",
        f"Total pekerjaan : {total}",
    ]
    _append_jobs(lines, jobs)
    _append_motivation(lines, period_end)
    return "\n".join(lines)


async def build_weekly_recap_text(
    db: Database,
    telegram_id: int,
    technician_name: str,
    day: date,
    timezone_name: str,
) -> str:
    period_start, period_end = _period_bounds(day)
    return await build_weekly_recap_text_for_period(
        db,
        telegram_id,
        technician_name,
        period_start,
        period_end,
        timezone_name,
    )


async def _was_recap_sent(
    db: Database,
    telegram_id: int,
    recap_type: str,
    period_start: date,
    period_end: date,
) -> bool:
    async with db._lock:
        with db.connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM recap_delivery_log
                WHERE telegram_id = ?
                  AND recap_type = ?
                  AND period_start = ?
                  AND period_end = ?
                LIMIT 1
                """,
                (
                    telegram_id,
                    recap_type,
                    period_start.isoformat(),
                    period_end.isoformat(),
                ),
            ).fetchone()
    return row is not None


async def _mark_recap_sent(
    db: Database,
    telegram_id: int,
    recap_type: str,
    period_start: date,
    period_end: date,
) -> None:
    async with db._lock:
        with db.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO recap_delivery_log (
                    telegram_id, recap_type, period_start, period_end, sent_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    telegram_id,
                    recap_type,
                    period_start.isoformat(),
                    period_end.isoformat(),
                    datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                ),
            )


async def send_daily_recaps(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()

    technicians = await db.list_technicians()
    for technician in technicians:
        telegram_id = int(technician["telegram_id"])
        try:
            text = await build_daily_recap_text(
                db,
                telegram_id,
                technician["name"],
                today,
                settings.timezone,
            )
            await context.bot.send_message(chat_id=telegram_id, text=text)
        except Exception:
            logging.exception("Gagal mengirim rekap harian ke telegram_id=%s", telegram_id)


async def send_weekly_recaps(context: ContextTypes.DEFAULT_TYPE) -> None:
    app = context.application
    db: Database = app.bot_data["db"]
    settings = app.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    period_start, period_end = _period_bounds(today)

    technicians = await db.list_technicians()
    for technician in technicians:
        telegram_id = int(technician["telegram_id"])
        try:
            text = await build_weekly_recap_text_for_period(
                db,
                telegram_id,
                technician["name"],
                period_start,
                period_end,
                settings.timezone,
            )
            await context.bot.send_message(chat_id=telegram_id, text=text)
            await _mark_recap_sent(db, telegram_id, "WEEKLY", period_start, period_end)
        except Exception:
            logging.exception("Gagal mengirim rekap mingguan ke telegram_id=%s", telegram_id)


async def send_previous_week_recaps_once(application) -> None:
    db: Database = application.bot_data["db"]
    settings = application.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    period_start, period_end = _previous_period_bounds(today)

    technicians = await db.list_technicians()
    for technician in technicians:
        telegram_id = int(technician["telegram_id"])
        try:
            if await _was_recap_sent(db, telegram_id, "WEEKLY", period_start, period_end):
                continue
            text = await build_weekly_recap_text_for_period(
                db,
                telegram_id,
                technician["name"],
                period_start,
                period_end,
                settings.timezone,
            )
            await application.bot.send_message(chat_id=telegram_id, text=text)
            await _mark_recap_sent(db, telegram_id, "WEEKLY", period_start, period_end)
            logging.info(
                "Rekap minggu sebelumnya terkirim otomatis: telegram_id=%s periode=%s..%s",
                telegram_id,
                period_start,
                period_end,
            )
        except Exception:
            logging.exception(
                "Gagal mengirim rekap minggu sebelumnya ke telegram_id=%s",
                telegram_id,
            )


async def recap_harian_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return

    settings = context.application.bot_data["settings"]
    db: Database = context.application.bot_data["db"]
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    text = await build_daily_recap_text(
        db,
        technician.telegram_id,
        technician.name,
        today,
        settings.timezone,
    )
    await update.effective_message.reply_text(text)


async def recap_mingguan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return

    settings = context.application.bot_data["settings"]
    db: Database = context.application.bot_data["db"]
    tz = ZoneInfo(settings.timezone)
    today = datetime.now(tz).date()
    text = await build_weekly_recap_text(
        db,
        technician.telegram_id,
        technician.name,
        today,
        settings.timezone,
    )
    await update.effective_message.reply_text(text)
