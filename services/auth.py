from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from database import Database, Technician


async def current_technician(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Technician | None:
    db: Database = context.application.bot_data["db"]
    if not update.effective_user:
        return None
    return await db.get_technician(update.effective_user.id)


async def require_technician(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Technician | None:
    technician = await current_technician(update, context)
    if technician is None and update.effective_chat:
        await update.effective_chat.send_message("Silakan /start dan login terlebih dahulu.")
    return technician
