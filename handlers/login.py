from __future__ import annotations

import logging

from telegram import ReplyKeyboardRemove, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from database import Database
from utils.keyboards import main_menu_keyboard


NIK, NAME, STO, EXISTING_STO = range(4)


def normalize_sto(value: str) -> str:
    return value.strip().upper()


def valid_sto(value: str) -> bool:
    normalized = normalize_sto(value)
    return 2 <= len(normalized) <= 10 and normalized.replace("-", "").isalnum()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message:
        return ConversationHandler.END

    db: Database = context.application.bot_data["db"]
    technician = await db.get_technician(update.effective_user.id)
    if technician:
        logging.info(
            "Login recognized telegram_id=%s nik=%s",
            technician.telegram_id,
            technician.nik,
        )
        if not technician.sto.strip():
            await update.message.reply_text(
                "Profil lama Anda belum memiliki STO.\n\n"
                "Masukkan STO Anda agar CONFIG, REPORT, dan STO berikutnya "
                "tidak menanyakan poin STO lagi.\n"
                "Contoh: MYR, KRP, RKT",
                reply_markup=ReplyKeyboardRemove(),
            )
            return EXISTING_STO

        await update.message.reply_text(
            f"Selamat datang kembali, {technician.name}.\n"
            f"STO: {technician.sto}\n\nSilakan pilih menu.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Selamat datang di Bot Replacement ONT IndiHome.\n\nInput NIK:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NIK


async def input_nik(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return NIK
    nik = update.message.text.strip()
    if len(nik) < 4:
        await update.message.reply_text("NIK terlalu pendek. Input NIK yang benar:")
        return NIK
    context.user_data["login_nik"] = nik
    await update.message.reply_text("Input Full Name:")
    return NAME


async def input_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return NAME
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("Nama terlalu pendek. Input Full Name:")
        return NAME
    context.user_data["login_name"] = name
    await update.message.reply_text(
        "Masukkan STO Anda.\nContoh: MYR, KRP, RKT"
    )
    return STO


async def input_sto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_user or not update.message or not update.message.text:
        return STO

    sto = normalize_sto(update.message.text)
    if not valid_sto(sto):
        await update.message.reply_text(
            "Format STO tidak valid. Masukkan kode STO, contoh: MYR, KRP, RKT"
        )
        return STO

    db: Database = context.application.bot_data["db"]
    technician = await db.create_technician(
        telegram_id=update.effective_user.id,
        nik=context.user_data["login_nik"],
        name=context.user_data["login_name"],
        sto=sto,
    )
    context.user_data.pop("login_nik", None)
    context.user_data.pop("login_name", None)
    logging.info(
        "New login saved telegram_id=%s nik=%s name=%s sto=%s",
        technician.telegram_id,
        technician.nik,
        technician.name,
        technician.sto,
    )
    await update.message.reply_text(
        f"Login berhasil.\n"
        f"NIK: {technician.nik}\n"
        f"Nama: {technician.name}\n"
        f"STO: {technician.sto}\n\n"
        "STO ini akan digunakan otomatis untuk CONFIG, REPORT, dan STO.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def input_existing_sto(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    if not update.effective_user or not update.message or not update.message.text:
        return EXISTING_STO

    sto = normalize_sto(update.message.text)
    if not valid_sto(sto):
        await update.message.reply_text(
            "Format STO tidak valid. Masukkan kode STO, contoh: MYR, KRP, RKT"
        )
        return EXISTING_STO

    db: Database = context.application.bot_data["db"]
    technician = await db.update_technician_sto(update.effective_user.id, sto)
    if technician is None:
        await update.message.reply_text("Profil tidak ditemukan. Silakan /start ulang.")
        return ConversationHandler.END

    await update.message.reply_text(
        f"✅ STO berhasil disimpan: {technician.sto}\n\n"
        "Mulai sekarang poin STO akan terisi otomatis.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


def build_login_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NIK: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_nik)],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_name)],
            STO: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_sto)],
            EXISTING_STO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, input_existing_sto)
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        name="login_conversation",
        persistent=False,
    )
