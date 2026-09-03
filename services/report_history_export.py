from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import ContextTypes

from database import Database
from services.report_area_tracking import area_order_condition, ensure_area_tracking_table

AREA_BY_STO = {
    "MYR": "MANYAR",
    "JGR": "JAGIR",
}
EMPTY_TICKETS = {"", "-", "MANUAL", "N/A", "NA", "NONE"}


def _clean_ticket(value: object) -> str:
    ticket = str(value or "").strip()
    return "" if ticket.upper() in EMPTY_TICKETS else ticket


def _order_ticket(conn: sqlite3.Connection, service_number: str) -> str:
    row = conn.execute(
        """
        SELECT ticket_id
        FROM orders
        WHERE service_number = ?
          AND TRIM(COALESCE(ticket_id, '')) != ''
        ORDER BY id DESC
        LIMIT 20
        """,
        (service_number,),
    ).fetchall()
    for item in row:
        ticket = _clean_ticket(item[0])
        if ticket:
            return ticket
    return ""


def _export_rows(database_path: Path, sto_code: str) -> list[dict[str, object]]:
    sto_code = sto_code.strip().upper()
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_area_tracking_table(conn)
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

        predicate, params = area_order_condition(sto_code, "r")
        rows = conn.execute(
            f"""
            SELECT r.service_number,
                   r.period_start,
                   r.technician_nik,
                   r.technician_name,
                   r.message_date,
                   r.chat_id,
                   r.message_id,
                   COALESCE(m.ticket_id, '') AS metadata_ticket
            FROM report_group_orders r
            LEFT JOIN report_ticket_metadata m
              ON m.service_number = r.service_number
             AND m.period_start = r.period_start
            WHERE {predicate}
            ORDER BY r.message_date ASC, r.service_number ASC
            """,
            params,
        ).fetchall()

        result: list[dict[str, object]] = []
        for row in rows:
            service_number = str(row["service_number"] or "").strip()
            ticket = _clean_ticket(row["metadata_ticket"])
            if not ticket:
                ticket = _order_ticket(conn, service_number)
            result.append(
                {
                    "service_number": service_number,
                    "period_start": str(row["period_start"] or "").strip(),
                    "technician_nik": str(row["technician_nik"] or "").strip(),
                    "technician_name": str(row["technician_name"] or "").strip(),
                    "date": str(row["message_date"] or "").strip(),
                    "chat_id": int(row["chat_id"] or 0),
                    "message_id": int(row["message_id"]) if row["message_id"] is not None else None,
                    "ticket_id": ticket or "MANUAL",
                }
            )
    return result


def _telegram_like_payload(rows: list[dict[str, object]], sto_code: str, timezone: str) -> dict[str, object]:
    area = AREA_BY_STO[sto_code]
    messages: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        ticket = str(row["ticket_id"] or "MANUAL")
        nik = str(row["technician_nik"] or "")
        name = str(row["technician_name"] or "")
        text = (
            f"/STO : {sto_code}\n"
            f"TIKET : {ticket}\n"
            f"NO SERVICE : {row['service_number']}\n"
            f"NIK NAMA TEKNISI : {nik} | {name}"
        )
        messages.append(
            {
                "id": row["message_id"] if row["message_id"] is not None else index,
                "type": "message",
                "date": row["date"],
                "text": text,
                "internal": {
                    "period_start": row["period_start"],
                    "chat_id": row["chat_id"],
                },
            }
        )

    return {
        "name": f"REPORT {area}",
        "type": "internal_bot_report_export",
        "area": area,
        "sto": sto_code,
        "timezone": timezone,
        "exported_at": datetime.now(ZoneInfo(timezone)).isoformat(),
        "total_messages": len(messages),
        "messages": messages,
    }


async def _send_export_document(message, temp_path: Path, filename: str, caption: str) -> None:
    """Send export file with longer timeouts and retries for unstable VPS->Telegram links."""
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with temp_path.open("rb") as document:
                await message.reply_document(
                    document=document,
                    filename=filename,
                    caption=caption,
                    connect_timeout=60,
                    read_timeout=180,
                    write_timeout=180,
                    pool_timeout=60,
                )
            return
        except (TimedOut, NetworkError) as exc:
            last_error = exc
            if attempt < 3:
                await asyncio.sleep(attempt * 2)

    if last_error is not None:
        raise last_error


async def exportreport_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    settings = context.application.bot_data["settings"]

    if not chat or chat.type != "private" or not user or not message:
        return
    if user.id not in settings.admin_ids:
        await message.reply_text("Perintah admin saja.")
        return

    sto_code = (context.args[0] if context.args else "").strip().upper()
    if sto_code not in AREA_BY_STO:
        await message.reply_text(
            "Format:\n/exportreport JGR\n/exportreport MYR\n\n"
            "File JSON hanya berisi report yang sudah pernah tercatat oleh bot."
        )
        return

    db: Database = context.application.bot_data["db"]
    rows = await asyncio.to_thread(_export_rows, db.db_path, sto_code)
    if not rows:
        await message.reply_text(
            f"Belum ada report internal {AREA_BY_STO[sto_code]} ({sto_code}) untuk diexport."
        )
        return

    payload = _telegram_like_payload(rows, sto_code, settings.timezone)
    filename = f"report_{sto_code.lower()}_{datetime.now(ZoneInfo(settings.timezone)).strftime('%Y%m%d_%H%M%S')}.json"
    caption = (
        f"📤 EXPORT REPORT {AREA_BY_STO[sto_code]}\n"
        f"🏢 STO : {sto_code}\n"
        f"📊 TOTAL : {len(rows)} report\n\n"
        "File ini berasal dari history internal bot dan kompatibel untuk /importhistory."
    )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            prefix=f"report_{sto_code.lower()}_",
            encoding="utf-8",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            temp_path = Path(handle.name)

        try:
            await _send_export_document(message, temp_path, filename, caption)
        except (TimedOut, NetworkError):
            await message.reply_text(
                "❌ File export sudah berhasil dibuat, tetapi koneksi VPS ke Telegram timeout saat mengirim file.\n"
                "Silakan coba /exportreport lagi beberapa saat lagi."
            )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
