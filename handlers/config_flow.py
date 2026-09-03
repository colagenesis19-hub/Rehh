from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from database import Database
from handlers.common import cancel
from ocr.reader import OntOcrReader
from services.auth import require_technician
from services.formatters import generate_config
from services.logic_dispatch import send_config_to_logic_once
from services.photos import download_largest_photo
from utils.keyboards import MAIN_MENU, cancel_keyboard, main_menu_keyboard
from utils.telegram_format import pre_block


(
    TICKET_ID,
    SERVICE_NUMBER,
    VOIP,
    OLD_PHOTO,
    OLD_SN_CONFIRM,
    OLD_SN_MANUAL,
    NEW_PHOTO,
    NEW_SN_CONFIRM,
    NEW_SN_MANUAL,
    TYPE_ONT_MANUAL,
    STO,
    DESCRIPTION,
    CUSTOMER_NAME,
    ADDRESS,
    CUSTOMER_PHONE,
) = range(100, 115)

MIN_OCR_CONFIDENCE = 0.55


async def start_config(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    technician = await require_technician(update, context)
    if not technician or not update.message:
        return ConversationHandler.END
    context.user_data["config"] = {}
    await update.message.reply_text("TIKET ID:", reply_markup=cancel_keyboard())
    return TICKET_ID


async def text_step(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, prompt: str, next_state: int) -> int:
    if not update.message or not update.message.text:
        return next_state
    context.user_data["config"][key] = update.message.text.strip()
    await update.message.reply_text(prompt)
    return next_state


async def ticket_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "ticket_id", "NO SERVICE:", SERVICE_NUMBER)


async def service_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "service_number", "NO VOIP:", VOIP)


async def voip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "voip", "Upload foto ONT LAMA atau ketik SN ONT LAMA:", OLD_PHOTO)


async def old_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        await update.message.reply_text("Kirim foto label ONT LAMA.")
        return OLD_PHOTO
    await update.message.reply_text("Membaca label ONT LAMA dengan OCR, tunggu sebentar...")
    parsed = await process_ocr_photo(update, context, "old")
    data = context.user_data["config"]
    if parsed.model and not data.get("ont_type"):
        data["ont_type"] = parsed.model
    if parsed.serial_number and parsed.confidence >= MIN_OCR_CONFIDENCE:
        data["old_sn"] = parsed.serial_number
        await update.message.reply_text(
            f"SN ONT LAMA terbaca: {parsed.serial_number}\nTYPE ONT: {data.get('ont_type', '-')}\n\n"
            "Ketik - jika benar, atau ketik SN yang benar:"
        )
        return OLD_SN_CONFIRM
    await update.message.reply_text("I couldn't read the serial number.\nPlease type manually.")
    return OLD_SN_MANUAL


async def old_sn_direct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return OLD_PHOTO
    context.user_data["config"]["old_sn"] = update.message.text.strip().upper()
    await update.message.reply_text("Upload foto ONT BARU atau ketik SN ONT BARU:")
    return NEW_PHOTO


async def old_sn_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return OLD_SN_CONFIRM
    text = update.message.text.strip()
    if text != "-":
        context.user_data["config"]["old_sn"] = text.upper()
    await update.message.reply_text("Upload foto ONT BARU atau ketik SN ONT BARU:")
    return NEW_PHOTO


async def old_sn_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return OLD_SN_MANUAL
    context.user_data["config"]["old_sn"] = update.message.text.strip().upper()
    await update.message.reply_text("Upload foto ONT BARU atau ketik SN ONT BARU:")
    return NEW_PHOTO


async def new_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        await update.message.reply_text("Kirim foto label ONT BARU.")
        return NEW_PHOTO
    await update.message.reply_text("Membaca label ONT BARU dengan OCR, tunggu sebentar...")
    parsed = await process_ocr_photo(update, context, "new")
    data = context.user_data["config"]
    if parsed.model:
        data["ont_type"] = parsed.model
    if parsed.serial_number and parsed.confidence >= MIN_OCR_CONFIDENCE:
        data["new_sn"] = parsed.serial_number
        await update.message.reply_text(
            f"SN ONT BARU terbaca: {parsed.serial_number}\nTYPE ONT: {data.get('ont_type', '-')}\n\n"
            "Ketik - jika benar, atau ketik SN yang benar:"
        )
        return NEW_SN_CONFIRM
    await update.message.reply_text("I couldn't read the serial number.\nPlease type manually.")
    return NEW_SN_MANUAL


async def new_sn_direct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return NEW_PHOTO
    context.user_data["config"]["new_sn"] = update.message.text.strip().upper()
    if not context.user_data["config"].get("ont_type"):
        await update.message.reply_text("TYPE ONT:")
        return TYPE_ONT_MANUAL
    await update.message.reply_text("STO:")
    return STO


async def new_sn_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return NEW_SN_CONFIRM
    text = update.message.text.strip()
    if text != "-":
        context.user_data["config"]["new_sn"] = text.upper()
    if not context.user_data["config"].get("ont_type"):
        await update.message.reply_text("TYPE ONT:")
        return TYPE_ONT_MANUAL
    await update.message.reply_text("STO:")
    return STO


async def new_sn_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return NEW_SN_MANUAL
    context.user_data["config"]["new_sn"] = update.message.text.strip().upper()
    if not context.user_data["config"].get("ont_type"):
        await update.message.reply_text("TYPE ONT:")
        return TYPE_ONT_MANUAL
    await update.message.reply_text("STO:")
    return STO


async def type_ont_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return TYPE_ONT_MANUAL
    context.user_data["config"]["ont_type"] = update.message.text.strip().upper()
    await update.message.reply_text("STO:")
    return STO


async def sto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "sto", "KETERANGAN:", DESCRIPTION)


async def description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "description", "NAMA CUSTOMER:", CUSTOMER_NAME)


async def customer_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "customer_name", "ALAMAT:", ADDRESS)


async def address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "address", "CP / NO HP CUSTOMER:", CUSTOMER_PHONE)


async def customer_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    technician = await require_technician(update, context)
    if not technician or not update.message or not update.message.text:
        return CUSTOMER_PHONE
    data = context.user_data["config"]
    data["customer_phone"] = update.message.text.strip()
    content = generate_config(technician, data)
    db: Database = context.application.bot_data["db"]
    await db.save_history(technician, "CONFIG", data, content)
    context.user_data["last_replacement"] = data.copy()
    context.user_data.pop("config", None)
    await update.message.reply_text(pre_block(content), parse_mode="HTML", reply_markup=main_menu_keyboard())
    await send_config_to_logic_once(context, db, data.get("service_number", ""), content)
    return ConversationHandler.END


async def process_ocr_photo(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str):
    settings = context.application.bot_data["settings"]
    db: Database = context.application.bot_data["db"]
    technician = await require_technician(update, context)
    image_path = await download_largest_photo(update, context, settings.photo_dir, prefix)
    reader = context.application.bot_data.get("ocr_reader")
    if reader is None:
        reader = OntOcrReader(settings.ocr_languages, settings.ocr_gpu)
        context.application.bot_data["ocr_reader"] = reader
    parsed = await reader.read_label(image_path)
    status = "success" if parsed.serial_number and parsed.confidence >= MIN_OCR_CONFIDENCE else "failed"
    await db.save_ocr_log(
        telegram_id=update.effective_user.id,
        technician_id=technician.id if technician else None,
        image_path=str(image_path),
        raw_text=parsed.raw_text,
        serial_number=parsed.serial_number,
        model=parsed.model,
        manufacturer=parsed.manufacturer,
        confidence=parsed.confidence,
        status=status,
    )
    if status != "success":
        logging.warning("OCR failure telegram_id=%s image=%s raw=%s", update.effective_user.id, image_path, parsed.raw_text)
    return parsed


def build_config_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("config", start_config),
            MessageHandler(filters.Regex(f"^{MAIN_MENU['config']}$"), start_config),
        ],
        states={
            TICKET_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_id)],
            SERVICE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, service_number)],
            VOIP: [MessageHandler(filters.TEXT & ~filters.COMMAND, voip)],
            OLD_PHOTO: [
                MessageHandler(filters.PHOTO, old_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, old_sn_direct),
            ],
            OLD_SN_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, old_sn_confirm)],
            OLD_SN_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, old_sn_manual)],
            NEW_PHOTO: [
                MessageHandler(filters.PHOTO, new_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, new_sn_direct),
            ],
            NEW_SN_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_sn_confirm)],
            NEW_SN_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_sn_manual)],
            TYPE_ONT_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, type_ont_manual)],
            STO: [MessageHandler(filters.TEXT & ~filters.COMMAND, sto)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description)],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_name)],
            ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, address)],
            CUSTOMER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="config_conversation",
        persistent=False,
    )
