from __future__ import annotations

import asyncio
import json
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from services.injoko_close_history import apply_to_local_orders, import_reports
from services.legacy_replacement_import import _flatten, _messages, parse_replacement

PENDING_KEY = "injoko_close_history_import"


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
        data = parse_replacement(_flatten(item.get("text")))
        if not data:
            continue
        if data.get("result", "").upper() not in {"CLOSE", "CLOSED", "DONE", "SELESAI", "COMPLETED"}:
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
