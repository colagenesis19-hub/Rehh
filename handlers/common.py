from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from database import Database
from services.auth import require_technician
from utils.keyboards import main_menu_keyboard
from utils.telegram_format import pre_block


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.message:
        await update.message.reply_text("Proses dibatalkan.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if not technician or not update.effective_chat:
        return
    await update.effective_chat.send_message(
        f"👤 Profile\n\n"
        f"NIK: {technician.nik}\n"
        f"Nama: {technician.name}\n"
        f"STO: {technician.sto or '-'}\n"
        f"Telegram ID: {technician.telegram_id}",
        reply_markup=main_menu_keyboard(),
    )


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if not technician or not update.effective_chat:
        return
    await update.effective_chat.send_message(
        "⚙ Settings\n\nGunakan /history, /search kata_kunci, /delete id, atau /export.",
        reply_markup=main_menu_keyboard(),
    )


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if not technician or not update.effective_chat:
        return
    db: Database = context.application.bot_data["db"]
    rows = await db.list_history(technician.telegram_id)
    if not rows:
        await update.effective_chat.send_message("History masih kosong.")
        return
    lines = ["History terakhir:"]
    for row in rows:
        lines.append(
            f"#{row['id']} {row['kind']} | Tiket: {row['ticket_id'] or '-'} | Service: {row['service_number'] or '-'} | {row['created_at']}"
        )
    await update.effective_chat.send_message("\n".join(lines))


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if not technician or not update.effective_chat:
        return
    query = " ".join(context.args).strip()
    if not query:
        await update.effective_chat.send_message("Format: /search kata_kunci")
        return
    db: Database = context.application.bot_data["db"]
    rows = await db.search_history(technician.telegram_id, query)
    if not rows:
        await update.effective_chat.send_message("Data tidak ditemukan.")
        return
    for row in rows[:10]:
        await update.effective_chat.send_message(
            f"#{row['id']} {row['kind']}\n\n{pre_block(row['content'])}",
            parse_mode="HTML",
        )


async def delete_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if not technician or not update.effective_chat:
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_chat.send_message("Format: /delete id_history")
        return
    db: Database = context.application.bot_data["db"]
    deleted = await db.delete_history(technician.telegram_id, int(context.args[0]))
    await update.effective_chat.send_message("History dihapus." if deleted else "History tidak ditemukan.")


async def export_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if not technician or not update.effective_chat:
        return
    db: Database = context.application.bot_data["db"]
    output_path = Path(context.application.bot_data["settings"].database_path).parent / f"history_{technician.telegram_id}.csv"
    path = await db.export_history_csv(technician.telegram_id, output_path)
    await update.effective_chat.send_document(document=path.open("rb"), filename=path.name, caption="Export history CSV.")
