from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ConversationHandler, ContextTypes, MessageHandler, filters

from database import Database
from handlers.common import cancel
from handlers.config_flow import MIN_OCR_CONFIDENCE, process_ocr_photo
from services.auth import require_technician
from services.formatters import generate_config, generate_report, generate_sto
from services.logic_dispatch import send_config_to_logic_once
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
    VALINS_ID,
    RESULT,
    DESCRIPTION,
    CUSTOMER_NAME,
    ADDRESS,
    CUSTOMER_PHONE,
) = range(400, 417)


async def start_full(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    technician = await require_technician(update, context)
    if not technician or not update.message:
        return ConversationHandler.END
    context.user_data["full"] = {}
    await update.message.reply_text(
        "Mode LENGKAP: isi sekali, bot langsung buat CONFIG, REPORT, dan STO.\n\nTIKET ID:",
        reply_markup=cancel_keyboard(),
    )
    return TICKET_ID


async def text_step(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, prompt: str, next_state: int) -> int:
    if not update.message or not update.message.text:
        return next_state
    context.user_data["full"][key] = update.message.text.strip()
    await update.message.reply_text(prompt)
    return next_state


async def ticket_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "ticket_id", "NO SERVICE / NO INET:", SERVICE_NUMBER)


async def service_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return SERVICE_NUMBER
    service = update.message.text.strip()
    data = context.user_data["full"]
    data["service_number"] = service
    data["internet_number"] = service
    await update.message.reply_text("NO VOIP:")
    return VOIP


async def voip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "voip", "Upload foto ONT LAMA atau ketik SN ONT LAMA:", OLD_PHOTO)


async def old_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        await update.message.reply_text("Kirim foto label ONT LAMA.")
        return OLD_PHOTO
    await update.message.reply_text("Membaca label ONT LAMA dengan OCR, tunggu sebentar...")
    parsed = await process_ocr_photo(update, context, "full_old")
    data = context.user_data["full"]
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
    context.user_data["full"]["old_sn"] = update.message.text.strip().upper()
    await update.message.reply_text("Upload foto ONT BARU atau ketik SN ONT BARU:")
    return NEW_PHOTO


async def old_sn_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return OLD_SN_CONFIRM
    text = update.message.text.strip()
    if text != "-":
        context.user_data["full"]["old_sn"] = text.upper()
    await update.message.reply_text("Upload foto ONT BARU atau ketik SN ONT BARU:")
    return NEW_PHOTO


async def old_sn_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return OLD_SN_MANUAL
    context.user_data["full"]["old_sn"] = update.message.text.strip().upper()
    await update.message.reply_text("Upload foto ONT BARU atau ketik SN ONT BARU:")
    return NEW_PHOTO


async def new_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.photo:
        await update.message.reply_text("Kirim foto label ONT BARU.")
        return NEW_PHOTO
    await update.message.reply_text("Membaca label ONT BARU dengan OCR, tunggu sebentar...")
    parsed = await process_ocr_photo(update, context, "full_new")
    data = context.user_data["full"]
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
    context.user_data["full"]["new_sn"] = update.message.text.strip().upper()
    if not context.user_data["full"].get("ont_type"):
        await update.message.reply_text("TYPE ONT:")
        return TYPE_ONT_MANUAL
    await update.message.reply_text("STO:")
    return STO


async def new_sn_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return NEW_SN_CONFIRM
    text = update.message.text.strip()
    if text != "-":
        context.user_data["full"]["new_sn"] = text.upper()
    if not context.user_data["full"].get("ont_type"):
        await update.message.reply_text("TYPE ONT:")
        return TYPE_ONT_MANUAL
    await update.message.reply_text("STO:")
    return STO


async def new_sn_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return NEW_SN_MANUAL
    context.user_data["full"]["new_sn"] = update.message.text.strip().upper()
    if not context.user_data["full"].get("ont_type"):
        await update.message.reply_text("TYPE ONT:")
        return TYPE_ONT_MANUAL
    await update.message.reply_text("STO:")
    return STO


async def type_ont_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message or not update.message.text:
        return TYPE_ONT_MANUAL
    context.user_data["full"]["ont_type"] = update.message.text.strip().upper()
    await update.message.reply_text("STO:")
    return STO


async def sto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "sto", "VALINS / VALIN ID:", VALINS_ID)


async def valins_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "valins_id", "RESULT REPORT:", RESULT)


async def result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "result", "KETERANGAN:", DESCRIPTION)


async def description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "description", "NAMA:", CUSTOMER_NAME)


async def customer_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "customer_name", "ALAMAT:", ADDRESS)


async def address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await text_step(update, context, "address", "CP / NO HP CUSTOMER:", CUSTOMER_PHONE)


async def customer_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    technician = await require_technician(update, context)
    if not technician or not update.message or not update.message.text:
        return CUSTOMER_PHONE

    data = context.user_data["full"]
    data["customer_phone"] = update.message.text.strip()

    settings = context.application.bot_data["settings"]
    db: Database = context.application.bot_data["db"]

    config_text = generate_config(technician, data)
    report_text = generate_report(technician, data, settings.timezone)
    sto_text = generate_sto(technician, data)

    await db.save_history(technician, "CONFIG", data, config_text)
    await db.save_history(technician, "REPORT", data, report_text)
    await db.save_history(technician, "STO", data, sto_text)

    context.user_data["last_replacement"] = data.copy()
    context.user_data.pop("full", None)

    await update.message.reply_text(pre_block(config_text), parse_mode="HTML")
    await update.message.reply_text(pre_block(report_text), parse_mode="HTML")
    await update.message.reply_text(pre_block(sto_text), parse_mode="HTML", reply_markup=main_menu_keyboard())
    await send_config_to_logic_once(context, db, data.get("service_number", ""), config_text)
    return ConversationHandler.END


def build_full_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("lengkap", start_full),
            MessageHandler(filters.Regex(f"^{MAIN_MENU['full']}$"), start_full),
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
            VALINS_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, valins_id)],
            RESULT: [MessageHandler(filters.TEXT & ~filters.COMMAND, result)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description)],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_name)],
            ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, address)],
            CUSTOMER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="full_conversation",
        persistent=False,
    )
