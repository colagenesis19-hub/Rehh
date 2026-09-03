from __future__ import annotations

import asyncio
import csv
import io
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from database import Database
from services.google_sheet_reference import (
    HEADER_ALIASES,
    cell,
    current_csv_url,
    find_column,
    normalize_ticket,
)
from services.report_leaderboard import NO_SERVICE_RE, _period_bounds
from services.report_multi_topic import get_topic_identity

TICKET_RE = re.compile(r"(?:TIKET|TICKET)\s*:\s*([^\n\r]+)", re.IGNORECASE)
MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _command_from_text(text: str) -> str:
    token = text.split(maxsplit=1)[0].lower().split("@", 1)[0]
    return token.rstrip(":")


def _norm_name(value: str) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _ensure_metadata_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_ticket_metadata (
            service_number TEXT NOT NULL,
            period_start TEXT NOT NULL,
            ticket_id TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (service_number, period_start)
        )
        """
    )


def _save_ticket_metadata(
    database_path: Path,
    service_number: str,
    period_start: date,
    ticket_id: str,
) -> None:
    clean_ticket = ticket_id.strip()
    with sqlite3.connect(database_path) as conn:
        _ensure_metadata_table(conn)
        conn.execute(
            """
            INSERT INTO report_ticket_metadata(service_number, period_start, ticket_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(service_number, period_start) DO UPDATE SET
                ticket_id = excluded.ticket_id,
                updated_at = excluded.updated_at
            """,
            (
                service_number.strip(),
                period_start.isoformat(),
                clean_ticket,
                datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            ),
        )


def _read_sheet_ticket_priority() -> dict[str, str]:
    """Read Order Sheet tickets with explicit priority: INSERA TODAY -> TIKET."""
    request = Request(current_csv_url(), headers={"User-Agent": "Kerja-Bot/1.0"})
    with urlopen(request, timeout=20) as response:
        rows = list(csv.reader(io.StringIO(response.read().decode("utf-8-sig", errors="replace"))))
    if not rows:
        return {}

    header_index = -1
    service_col = ticket_col = insera_col = None
    for index, row in enumerate(rows[:20]):
        service_col = find_column(row, HEADER_ALIASES["service_number"])
        ticket_col = find_column(row, HEADER_ALIASES["ticket"])
        insera_col = find_column(row, HEADER_ALIASES["insera_ticket"])
        if service_col is not None:
            header_index = index
            break
    if header_index < 0 or service_col is None:
        return {}

    result: dict[str, str] = {}
    for row in rows[header_index + 1 :]:
        service = cell(row, service_col).strip()
        if not service:
            continue
        insera_ticket = normalize_ticket(cell(row, insera_col))
        primary_ticket = normalize_ticket(cell(row, ticket_col))
        ticket = insera_ticket or primary_ticket
        if ticket:
            result[service] = ticket
    return result


def _backfill_sheet_ticket_metadata(
    database_path: Path,
    sheet_tickets: dict[str, str],
) -> int:
    """Fill only missing/MANUAL report ticket metadata using Order Sheet."""
    if not sheet_tickets:
        return 0

    updated = 0
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    with sqlite3.connect(database_path) as conn:
        _ensure_metadata_table(conn)
        rows = conn.execute(
            """
            SELECT r.service_number, r.period_start,
                   COALESCE(TRIM(m.ticket_id), '') AS metadata_ticket
            FROM report_group_orders r
            LEFT JOIN report_ticket_metadata m
              ON m.service_number = r.service_number
             AND m.period_start = r.period_start
            GROUP BY r.service_number, r.period_start
            """
        ).fetchall()

        for service_number, period_start, metadata_ticket in rows:
            current = str(metadata_ticket or "").strip()
            if current and current.upper() not in {"MANUAL", "-", "N/A", "NA", "NONE"}:
                continue
            ticket = sheet_tickets.get(str(service_number or "").strip(), "").strip()
            if not ticket:
                continue
            conn.execute(
                """
                INSERT INTO report_ticket_metadata(service_number, period_start, ticket_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(service_number, period_start) DO UPDATE SET
                    ticket_id = CASE
                        WHEN TRIM(report_ticket_metadata.ticket_id) = ''
                          OR UPPER(TRIM(report_ticket_metadata.ticket_id)) IN ('MANUAL','-','N/A','NA','NONE')
                        THEN excluded.ticket_id
                        ELSE report_ticket_metadata.ticket_id
                    END,
                    updated_at = CASE
                        WHEN TRIM(report_ticket_metadata.ticket_id) = ''
                          OR UPPER(TRIM(report_ticket_metadata.ticket_id)) IN ('MANUAL','-','N/A','NA','NONE')
                        THEN excluded.updated_at
                        ELSE report_ticket_metadata.updated_at
                    END
                """,
                (str(service_number).strip(), str(period_start), ticket, now),
            )
            updated += 1
    return updated


async def _sync_manual_tickets_from_sheet(db: Database) -> int:
    """On every /laporan: INSERA TODAY first, then TIKET, otherwise keep MANUAL."""
    try:
        sheet_tickets = await asyncio.to_thread(_read_sheet_ticket_priority)
    except Exception:
        return 0
    return await asyncio.to_thread(_backfill_sheet_ticket_metadata, db.db_path, sheet_tickets)


async def capture_report_ticket_metadata(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remember ticket numbers from every /sto in a registered REPORT topic."""
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return

    text = (message.text or message.caption or "").strip()
    if not text or _command_from_text(text) != "/sto" or message.message_thread_id is None:
        return

    service_match = NO_SERVICE_RE.search(text)
    if not service_match:
        return

    db: Database = context.application.bot_data["db"]
    identity = await asyncio.to_thread(
        get_topic_identity,
        db.db_path,
        chat.id,
        message.message_thread_id,
    )
    if identity is None:
        return

    settings = context.application.bot_data["settings"]
    local_dt = message.date.astimezone(ZoneInfo(settings.timezone))
    period_start, _ = _period_bounds(local_dt.date())
    ticket_match = TICKET_RE.search(text)
    ticket_id = ticket_match.group(1).strip() if ticket_match else ""
    if ticket_id.upper() in {"-", "N/A", "NA", "NONE"}:
        ticket_id = ""

    await asyncio.to_thread(
        _save_ticket_metadata,
        db.db_path,
        service_match.group(1).strip(),
        period_start,
        ticket_id,
    )


def _format_period(start_iso: str) -> str:
    start = date.fromisoformat(start_iso)
    end = start + timedelta(days=6)
    return f"{start.day:02d} {MONTH_SHORT[start.month - 1]} {start.year} - {end.day:02d} {MONTH_SHORT[end.month - 1]} {end.year}"


def _registered_exact_name(database_path: Path, query: str) -> tuple[str, str] | None:
    """Return the unique registered technician for an exact normalized name."""
    wanted = _norm_name(query)
    if not wanted:
        return None
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute("SELECT nik, name FROM technicians WHERE TRIM(name) != ''").fetchall()

    matches: list[tuple[str, str]] = []
    seen_nik: set[str] = set()
    for nik, name in rows:
        clean_nik = str(nik or "").strip()
        clean_name = " ".join(str(name or "").strip().split())
        if not clean_nik or _norm_name(clean_name) != wanted or clean_nik in seen_nik:
            continue
        seen_nik.add(clean_nik)
        matches.append((clean_nik, clean_name))
    return matches[0] if len(matches) == 1 else None


def _merge_legacy_name_rows(
    database_path: Path,
    canonical_nik: str,
    canonical_name: str,
) -> int:
    """Move old rows with the same explicit technician name to the registered NIK.

    This repairs records created by the old name-only /sto fallback that borrowed
    the Telegram sender's NIK. Only rows whose stored technician name exactly
    normalizes to the registered name are touched, so unrelated work on the same
    sender NIK remains intact.
    """
    wanted = _norm_name(canonical_name)
    changed = 0
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            "SELECT service_number, period_start, technician_nik, technician_name FROM report_group_orders"
        ).fetchall()
        for service_number, period_start, old_nik, old_name in rows:
            if _norm_name(str(old_name or "")) != wanted:
                continue
            if str(old_nik or "").strip() == canonical_nik and str(old_name or "").strip() == canonical_name:
                continue
            conn.execute(
                """
                UPDATE report_group_orders
                SET technician_nik = ?, technician_name = ?
                WHERE service_number = ? AND period_start = ?
                """,
                (canonical_nik, canonical_name, str(service_number), str(period_start)),
            )
            changed += 1
    return changed


def _find_technicians(database_path: Path, query: str) -> list[tuple[str, str]]:
    query = query.strip()
    with sqlite3.connect(database_path) as conn:
        if query.isdigit():
            rows = conn.execute(
                """
                SELECT technician_nik, MAX(technician_name)
                FROM report_group_orders
                WHERE technician_nik = ?
                GROUP BY technician_nik
                """,
                (query,),
            ).fetchall()
            return [(str(nik), str(name)) for nik, name in rows]

    # Untuk pencarian nama, registry teknisi adalah sumber identitas utama. Jika
    # nama cocok persis dan unik, satukan otomatis histori legacy yang dulu salah
    # memakai NIK akun Telegram pengirim.
    registered = _registered_exact_name(database_path, query)
    if registered is not None:
        canonical_nik, canonical_name = registered
        _merge_legacy_name_rows(database_path, canonical_nik, canonical_name)
        return [(canonical_nik, canonical_name)]

    normalized = " ".join(query.upper().split())
    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            """
            SELECT technician_nik, MAX(technician_name)
            FROM report_group_orders
            WHERE UPPER(TRIM(technician_name)) LIKE ?
            GROUP BY technician_nik
            ORDER BY UPPER(MAX(technician_name))
            LIMIT 10
            """,
            (f"%{normalized}%",),
        ).fetchall()
    return [(str(nik), str(name)) for nik, name in rows]


def _report_rows(
    database_path: Path,
    technician_nik: str,
    max_periods: int = 3,
) -> list[tuple[str, list[tuple[str, str, str]]]]:
    with sqlite3.connect(database_path) as conn:
        _ensure_metadata_table(conn)
        periods = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT DISTINCT period_start
                FROM report_group_orders
                WHERE technician_nik = ?
                ORDER BY period_start DESC
                LIMIT ?
                """,
                (technician_nik, max_periods),
            ).fetchall()
        ]

        result: list[tuple[str, list[tuple[str, str, str]]]] = []
        for period_start in periods:
            rows = conn.execute(
                """
                SELECT r.service_number,
                       COALESCE(
                           NULLIF(TRIM(m.ticket_id), ''),
                           NULLIF(TRIM((
                               SELECT o.ticket_id
                               FROM orders o
                               WHERE o.service_number = r.service_number
                                 AND TRIM(o.ticket_id) != ''
                               ORDER BY o.id DESC
                               LIMIT 1
                           )), ''),
                           'MANUAL'
                       ) AS ticket_id,
                       substr(r.message_date, 1, 10) AS report_date
                FROM report_group_orders r
                LEFT JOIN report_ticket_metadata m
                  ON m.service_number = r.service_number
                 AND m.period_start = r.period_start
                WHERE r.technician_nik = ? AND r.period_start = ?
                ORDER BY r.message_date DESC, r.service_number ASC
                """,
                (technician_nik, period_start),
            ).fetchall()
            result.append(
                (
                    period_start,
                    [(str(service), str(ticket), str(report_date)) for service, ticket, report_date in rows],
                )
            )
    return result


def _build_report_text(nik: str, name: str, periods: list[tuple[str, list[tuple[str, str, str]]]]) -> str:
    lines = [f"📊 Report : {nik}", f"👷 {name.upper()}", ""]
    if not periods:
        lines.append("Belum ada report yang tercatat.")
        return "\n".join(lines)

    for period_index, (period_start, rows) in enumerate(periods, start=1):
        lines.append(f"{period_index}. 📅 {_format_period(period_start)}")
        for index, (service, ticket, report_date) in enumerate(rows, start=1):
            try:
                report_day = date.fromisoformat(report_date).strftime("%d/%m/%Y")
            except ValueError:
                report_day = report_date
            lines.append(f"{index}. {service} | {ticket} | {report_day}")
        lines.append(f"TOTAL CLOSE : {len(rows)} TIKET")
        if period_index != len(periods):
            lines.append("")
    return "\n".join(lines)


async def _send_laporan(message, db: Database, query: str) -> None:
    matches = await asyncio.to_thread(_find_technicians, db.db_path, query)
    if not matches:
        await message.reply_text(f"❌ Teknisi tidak ditemukan untuk: {query}")
        return
    if len(matches) > 1:
        lines = ["Ditemukan beberapa teknisi. Gunakan NIK agar pasti:"]
        lines.extend(f"{nik} | {name}" for nik, name in matches)
        await message.reply_text("\n".join(lines))
        return

    await _sync_manual_tickets_from_sheet(db)

    nik, name = matches[0]
    periods = await asyncio.to_thread(_report_rows, db.db_path, nik, 3)
    text = _build_report_text(nik, name, periods)

    if len(text) <= 4000:
        await message.reply_text(text)
        return

    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > 3900:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    for chunk in chunks:
        await message.reply_text(chunk)


async def laporan_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return

    text = (message.text or message.caption or "").strip()
    if not text or _command_from_text(text) != "/laporan":
        return
    if message.message_thread_id is None:
        return

    db: Database = context.application.bot_data["db"]
    identity = await asyncio.to_thread(get_topic_identity, db.db_path, chat.id, message.message_thread_id)
    if identity is None:
        return

    parts = text.split(maxsplit=1)
    query = parts[1].strip() if len(parts) > 1 else ""
    if not query:
        await message.reply_text(
            "Format:\n/laporan NIK\n/laporan NAMA TEKNISI\n\n"
            "Contoh:\n/laporan 268800163\n/laporan Agam Rizky"
        )
        raise ApplicationHandlerStop

    await _send_laporan(message, db, query)
    raise ApplicationHandlerStop


async def laporan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    if not chat or chat.type != "private" or not user or not message:
        return

    db: Database = context.application.bot_data["db"]
    technician = await db.get_technician(user.id)
    if technician is None:
        await message.reply_text("❌ Perintah /laporan hanya untuk teknisi yang sudah terdaftar di bot.")
        return

    query = " ".join(context.args).strip()
    if not query:
        query = technician.nik.strip() or technician.name.strip()

    await _send_laporan(message, db, query)
