from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from services.injoko_close_history import apply_to_local_orders, import_reports

PENDING_KEY = "injoko_close_history_import"
FIELD_RE = re.compile(r"(?im)^\s*(TANGGAL|NIK|NAMA|TIKET\s*ID|NO\s*INET|SN\s*ONT\s*LAMA|SN\s*ONT\s*BARU|VALINS\s*ID|RESULT|KETERANGAN)\s*[:：=]\s*(.*)$")


def _flatten(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(x if isinstance(x, str) else x.get("text", "") if isinstance(x, dict) else "" for x in value)
    return ""


def _messages(payload: Any) -> list[dict[str, Any]]:
    return [x for x in payload.get("messages", []) if isinstance(x, dict)] if isinstance(payload, dict) else []


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


def _parse_close_report(text: str) -> dict[str, str] | None:
    normalized = text.replace("\u00a0", " ")
    upper = normalized.upper()
    if "/REPORT" not in upper or "REPLACEMENT ONT" not in upper:
        return None
    if not re.search(r"(?im)RESULT\s*[:：=]\s*CLOSE\b", normalized):
        return None

    fields: dict[str, str] = {}
    for key, value in FIELD_RE.findall(normalized):
        fields[re.sub(r"\s+", " ", key.upper()).strip()] = _clean(value)

    service = re.sub(r"\D", "", fields.get("NO INET", ""))
    if len(service) < 8 or not fields.get("NAMA"):
        return None

    ticket = fields.get("TIKET ID", "")
    if re.match(r"^(?:NO INET|SN ONT LAMA|SN ONT BARU|VALINS ID)\s*[:：=]", ticket, re.I):
        ticket = ""
    if ticket.upper() in {"MANUAL", "N/A", "NA", "NONE", "-"}:
        ticket = ""

    valins = fields.get("VALINS ID", "")
    if re.match(r"^(?:RESULT|KETERANGAN)\s*[:：=]", valins, re.I):
        valins = ""

    return {
        "report_date": fields.get("TANGGAL", ""),
        "nik": fields.get("NIK", ""),
        "name": fields.get("NAMA", ""),
        "ticket_id": ticket,
        "service_number": service,
        "old_sn": fields.get("SN ONT LAMA", ""),
        "new_sn": fields.get("SN ONT BARU", ""),
        "valins_id": valins,
        "result": "CLOSE",
        "description": fields.get("KETERANGAN", ""),
    }


async def importinjokohistory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    settings = context.application.bot_data["settings"]
    if not chat or chat.type != "private" or not user or user.id not in settings.admin_ids or not message:
        return
    context.user_data[PENDING_KEY] = True
    await message.reply_text(
        "📥 IMPORT HISTORY CLOSE INJOKO SIAP\n\n"
        "Kirim JSON export grup REPLACEMENT ONT SA INJOKO.\n"
        "Bot hanya mengambil report /REPORT REPLACEMENT ONT dengan RESULT CLOSE."
    )


async def importinjokohistory_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get(PENDING_KEY):
        return
    message = update.effective_message
    user = update.effective_user
    settings = context.application.bot_data["settings"]
    if not message or not message.document or not user or user.id not in settings.admin_ids:
        return
    if not (message.document.file_name or "").lower().endswith(".json"):
        await message.reply_text("❌ File harus JSON hasil Export Telegram.")
        return

    await message.reply_text("⏳ Membaca history CLOSE INJOKO...")
    try:
        tg_file = await context.bot.get_file(message.document.file_id)
        payload: Any = json.loads(bytes(await tg_file.download_as_bytearray()).decode("utf-8-sig"))
    except Exception as exc:
        await message.reply_text(f"❌ Gagal membaca JSON: {exc}")
        return

    if str(payload.get("name", "")).strip().upper() != "REPLACEMENT ONT SA INJOKO":
        context.user_data.pop(PENDING_KEY, None)
        await message.reply_text("❌ File ini bukan export grup REPLACEMENT ONT SA INJOKO.")
        return

    reports: list[dict[str, Any]] = []
    scanned = 0
    for item in _messages(payload):
        scanned += 1
        data = _parse_close_report(_flatten(item.get("text")))
        if not data:
            continue
        reports.append({
            **data,
            "source_message_id": item.get("id"),
            "source_message_date": item.get("date", ""),
        })

    db_path = settings.database_path
    inserted, skipped = await asyncio.to_thread(import_reports, db_path, reports)
    updated_orders = await asyncio.to_thread(apply_to_local_orders, db_path)
    context.user_data.pop(PENDING_KEY, None)

    await message.reply_text(
        "✅ IMPORT HISTORY CLOSE INJOKO SELESAI\n\n"
        f"📨 Pesan diperiksa : {scanned}\n"
        f"🔒 Report CLOSE terdeteksi : {len(reports)}\n"
        f"➕ CLOSE baru disimpan : {inserted}\n"
        f"🔁 CLOSE sudah ada : {skipped}\n"
        f"📦 WO lokal diubah CLOSE : {updated_orders}"
    )
