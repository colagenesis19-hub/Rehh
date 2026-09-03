from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database
from services.report_area_tracking import record_area_order
from services.report_laporan import _save_ticket_metadata
from services.report_leaderboard import _period_bounds, _store_order
from services.report_universal_sto import parse_sto

AREA_BY_STO = {
    "MYR": "MANYAR",
    "JGR": "JAGIR",
}
PENDING_KEY = "telegram_report_history_import_sto"
TICKET_FALLBACK_RE = re.compile(
    r"(?im)^\s*(?:TIKET|TICKET|TIKET\s+ID|TICKET\s+ID|NO\.?\s*TIKET|INC)\s*[:：=]\s*([^\n\r]+)"
)
INC_RE = re.compile(r"\bINC\d{5,}\b", re.IGNORECASE)
EMPTY_TICKET_VALUES = {"", "-", "MANUAL", "N/A", "NA", "NONE", "NULL"}


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _messages_from_export(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if isinstance(messages, list):
            return [item for item in messages if isinstance(item, dict)]

        chats = payload.get("chats") or payload.get("list")
        if isinstance(chats, list):
            result: list[dict[str, Any]] = []
            for chat in chats:
                if isinstance(chat, dict):
                    result.extend(_messages_from_export(chat))
            return result
    return []


def _parse_export_date(raw: Any, tz: ZoneInfo) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _ticket_from_text(text: str, parsed_ticket: str) -> str:
    ticket = str(parsed_ticket or "").strip()
    if ticket.upper() not in EMPTY_TICKET_VALUES:
        inc = INC_RE.search(ticket)
        return inc.group(0).upper() if inc else ticket

    match = TICKET_FALLBACK_RE.search(text)
    if match:
        value = match.group(1).strip()
        if value.upper() not in EMPTY_TICKET_VALUES:
            inc = INC_RE.search(value)
            return inc.group(0).upper() if inc else value

    # Last fallback: only accept an explicit INC token anywhere in the /sto text.
    inc = INC_RE.search(text)
    return inc.group(0).upper() if inc else ""


def _existing_report(
    database_path,
    service_number: str,
    period_start: str,
) -> tuple[str, str] | None:
    with sqlite3.connect(database_path) as conn:
        try:
            row = conn.execute(
                """
                SELECT technician_nik, technician_name
                FROM report_group_orders
                WHERE service_number = ? AND period_start = ?
                """,
                (service_number, period_start),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
    if not row:
        return None
    return str(row[0]), str(row[1])


def _resolve_name_only_key(database_path, technician_name: str) -> str:
    normalized = " ".join(technician_name.upper().split())
    with sqlite3.connect(database_path) as conn:
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT technician_nik
                FROM report_group_orders
                WHERE UPPER(TRIM(technician_name)) = ?
                LIMIT 3
                """,
                (normalized,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if len(rows) == 1:
            return str(rows[0][0])

        try:
            tech = conn.execute(
                """
                SELECT nik FROM technicians
                WHERE UPPER(TRIM(name)) = ?
                ORDER BY id DESC LIMIT 1
                """,
                (normalized,),
            ).fetchone()
        except sqlite3.OperationalError:
            tech = None
        if tech:
            return str(tech[0])
    return f"NAME-{normalized}"


async def _private_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[int, Any] | None:
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    settings = context.application.bot_data["settings"]
    if not chat or chat.type != "private" or not user or not message:
        return None
    if user.id not in settings.admin_ids:
        return None
    return user.id, message


async def _dm(context: ContextTypes.DEFAULT_TYPE, admin_id: int, text: str) -> None:
    await context.bot.send_message(chat_id=admin_id, text=text)


async def importhistory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    private = await _private_admin(update, context)
    if private is None:
        return
    admin_id, _ = private

    sto = (context.args[0] if context.args else "").strip().upper()
    if sto not in AREA_BY_STO:
        await _dm(
            context,
            admin_id,
            "Format:\n/importhistory JGR\n/importhistory MYR\n\n"
            "Setelah itu kirim file JSON hasil Export Telegram ke chat pribadi bot ini.",
        )
        return

    context.user_data[PENDING_KEY] = sto
    await _dm(
        context,
        admin_id,
        "📥 IMPORT HISTORY SIAP\n"
        f"📍 AREA : {AREA_BY_STO[sto]}\n"
        f"🏢 STO : {sto}\n\n"
        "Sekarang kirim file JSON hasil Export Telegram di chat pribadi ini.\n"
        "Bot hanya mengambil pesan /sto dan tidak menghapus data lama.",
    )


async def importhistory_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    private = await _private_admin(update, context)
    if private is None:
        return
    admin_id, _ = private
    context.user_data.pop(PENDING_KEY, None)
    await _dm(context, admin_id, "Import history dibatalkan.")


async def import_history_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    private = await _private_admin(update, context)
    if private is None:
        return
    admin_id, message = private
    document = message.document
    if document is None:
        return

    settings = context.application.bot_data["settings"]
    target_sto = str(context.user_data.get(PENDING_KEY) or "").strip().upper()
    if target_sto not in AREA_BY_STO:
        return

    filename = (document.file_name or "").lower()
    mime = (document.mime_type or "").lower()
    if not filename.endswith(".json") and "json" not in mime:
        await _dm(context, admin_id, "❌ File harus JSON hasil Export Telegram.")
        return

    await _dm(context, admin_id, "⏳ Membaca history Telegram...")
    try:
        telegram_file = await context.bot.get_file(document.file_id)
        raw = bytes(await telegram_file.download_as_bytearray())
        payload = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:
        await _dm(context, admin_id, f"❌ Gagal membaca JSON: {exc}")
        return

    messages = _messages_from_export(payload)
    if not messages:
        await _dm(context, admin_id, "❌ Tidak menemukan daftar messages pada export Telegram.")
        return

    db: Database = context.application.bot_data["db"]
    tz = ZoneInfo(settings.timezone)
    area_label = AREA_BY_STO[target_sto]

    imported = 0
    mapped_existing = 0
    tickets_saved = 0
    tickets_missing = 0
    skipped_not_sto = 0
    skipped_mismatch = 0
    skipped_invalid = 0

    for item in messages:
        text = _flatten_text(item.get("text"))
        parsed = parse_sto(text.strip())
        if parsed is None:
            skipped_not_sto += 1
            continue
        if parsed.sto_code and parsed.sto_code != target_sto:
            skipped_mismatch += 1
            continue
        if not parsed.service_number or not parsed.technician_name:
            skipped_invalid += 1
            continue

        message_dt = _parse_export_date(item.get("date"), tz)
        if message_dt is None:
            skipped_invalid += 1
            continue
        period_start, _ = _period_bounds(message_dt.date())
        period_iso = period_start.isoformat()

        existing = await asyncio.to_thread(
            _existing_report,
            db.db_path,
            parsed.service_number,
            period_iso,
        )

        if existing is None:
            technician_nik = parsed.technician_nik.strip()
            if not technician_nik:
                technician_nik = await asyncio.to_thread(
                    _resolve_name_only_key,
                    db.db_path,
                    parsed.technician_name,
                )
            message_id_raw = item.get("id")
            try:
                message_id = int(message_id_raw)
            except (TypeError, ValueError):
                message_id = None

            await asyncio.to_thread(
                _store_order,
                db.db_path,
                parsed.service_number,
                period_start,
                technician_nik,
                parsed.technician_name,
                message_dt,
                0,
                message_id,
            )
            imported += 1
        else:
            mapped_existing += 1

        await asyncio.to_thread(
            record_area_order,
            db.db_path,
            parsed.service_number,
            period_iso,
            target_sto,
            area_label,
        )

        ticket_id = _ticket_from_text(text, parsed.ticket_id)
        if ticket_id:
            await asyncio.to_thread(
                _save_ticket_metadata,
                db.db_path,
                parsed.service_number,
                period_start,
                ticket_id,
            )
            tickets_saved += 1
        else:
            tickets_missing += 1

    context.user_data.pop(PENDING_KEY, None)
    await _dm(
        context,
        admin_id,
        "✅ IMPORT HISTORY SELESAI\n"
        f"📍 AREA : {area_label}\n"
        f"🏢 STO : {target_sto}\n"
        f"➕ Report baru : {imported}\n"
        f"🔗 Data lama dipetakan : {mapped_existing}\n"
        f"🎫 Tiket tersimpan : {tickets_saved}\n"
        f"📝 /sto tanpa tiket : {tickets_missing}\n"
        f"↪️ Bukan /sto : {skipped_not_sto}\n"
        f"⚠️ STO berbeda : {skipped_mismatch}\n"
        f"❌ Data tidak lengkap : {skipped_invalid}\n\n"
        "Data existing tidak dihapus atau didobel. Tiket existing akan dilengkapi dari JSON bila ditemukan.",
    )
