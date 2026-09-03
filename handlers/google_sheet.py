from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from handlers.admin import admin_guard
from services.google_sheet_reference import (
    CLOSED_STATUSES,
    configure_sheet,
    current_sheet_url,
    get_reference_statuses,
    sync_missing_orders_from_sheet,
)


async def setsheet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or update.effective_message is None:
        return
    if not context.args:
        await update.effective_message.reply_text(
            "Format:\n/setsheet LINK_GOOGLE_SHEETS"
        )
        return

    url = context.args[0].strip()
    database_path = context.application.bot_data["settings"].database_path
    await update.effective_message.reply_text("Mengecek Google Sheets...")
    try:
        _, gid = await configure_sheet(database_path, url)
        statuses = await get_reference_statuses()
    except Exception as exc:
        await update.effective_message.reply_text(
            "❌ Google Sheets tidak dapat digunakan.\n\n"
            f"Alasan: {exc}\n\n"
            "Pastikan akses link disetel menjadi siapa saja yang memiliki link dapat melihat."
        )
        return

    await update.effective_message.reply_text(
        "✅ Google Sheets berhasil disimpan.\n\n"
        f"GID: {gid}\n"
        f"Data referensi terbaca: {len(statuses)} kunci\n\n"
        "Bot hanya membaca Google Sheets dan tidak dapat mengeditnya."
    )


async def getsheet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or update.effective_message is None:
        return
    await update.effective_message.reply_text(
        "📄 Google Sheets referensi\n\n"
        f"{current_sheet_url()}\n\n"
        "Mode: read-only"
    )


async def testsheet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or update.effective_message is None:
        return
    await update.effective_message.reply_text("Membaca Google Sheets...")
    try:
        statuses = await get_reference_statuses(force=True, raise_errors=True)
    except Exception as exc:
        await update.effective_message.reply_text(
            f"❌ Gagal membaca Google Sheets.\nAlasan: {exc}"
        )
        return

    closed = sum(1 for item in statuses.values() if item.status in CLOSED_STATUSES)
    await update.effective_message.reply_text(
        "✅ Google Sheets berhasil dibaca.\n\n"
        f"Kunci tiket/INET terbaca: {len(statuses)}\n"
        f"Kunci berstatus selesai: {closed}\n\n"
        "Catatan: satu order dapat menghasilkan dua kunci, yaitu tiket dan nomor internet."
    )


async def syncsheet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or update.effective_message is None:
        return

    await update.effective_message.reply_text(
        "🔄 Membaca Google Sheets terbaru dan menyinkronkan database..."
    )
    try:
        statuses = await get_reference_statuses(force=True, raise_errors=True)
        database_path = context.application.bot_data["settings"].database_path
        total, inserted, updated, unchanged = await sync_missing_orders_from_sheet(
            database_path,
            statuses,
        )
    except Exception as exc:
        await update.effective_message.reply_text(
            "❌ Sinkronisasi Google Sheets gagal.\n"
            f"Alasan: {exc}"
        )
        return

    await update.effective_message.reply_text(
        "✅ Sinkronisasi selesai.\n\n"
        f"Order unik di Sheet : {total}\n"
        f"Order baru masuk DB : {inserted}\n"
        f"Order diperbarui    : {updated}\n"
        f"Tidak berubah       : {unchanged}\n\n"
        "Database diperbarui dari Google Sheets, termasuk NAMA PETUGAS.\n"
        "Google Sheets tetap read-only."
    )


def build_google_sheet_handlers() -> list[CommandHandler]:
    return [
        CommandHandler("setsheet", setsheet),
        CommandHandler("getsheet", getsheet),
        CommandHandler("testsheet", testsheet),
        CommandHandler("syncsheet", syncsheet),
    ]
