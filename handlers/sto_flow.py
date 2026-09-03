from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ConversationHandler, ContextTypes, MessageHandler, filters

from database import Database
from handlers.common import cancel
from services.auth import require_technician
from services.formatters import generate_sto
from utils.keyboards import MAIN_MENU, cancel_keyboard, main_menu_keyboard
from utils.telegram_format import pre_block


(
    STO,
    TICKET_ID,
    SERVICE_NUMBER,
    OLD_SN,
    NEW_SN,
    ONT_TYPE,
    VALINS_ID,
    DESCRIPTION,
    CUSTOMER_NAME,
    ADDRESS,
    CUSTOMER_PHONE,
) = range(300, 311)


async def start_sto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    technician = await require_technician(update, context)
    if not technician or not update.message:
        return ConversationHandler.END
    context.user_data["sto"] = dict(context.user_data.get("last_replacement", {}))
    await update.message.reply_text("STO:", reply_markup=cancel_keyboard())
    return STO


async def step(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, prompt: str, next_state: int) -> int:
    if not update.message or not update.message.text:
        return next_state
    text = update.message.text.strip()
    if text != "-":
        context.user_data["sto"][key] = text
    await update.message.reply_text(prompt)
    return next_state


def prompt_with_default(label: str, current: str | None) -> str:
    if current:
        return f"{label} [{current}]\nKetik - untuk pakai data ini, atau input baru:"
    return f"{label}:"


async def sto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["sto"]["sto"] = update.message.text.strip().upper()
    await update.message.reply_text("TIKET:")
    return TICKET_ID


async def ticket_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await step(update, context, "ticket_id", "NO SERVICE:", SERVICE_NUMBER)


async def service_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data["sto"]
    data["service_number"] = update.message.text.strip()
    await update.message.reply_text(prompt_with_default("SN ONT LAMA", data.get("old_sn")))
    return OLD_SN


async def old_sn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != "-":
        context.user_data["sto"]["old_sn"] = text.upper()
    await update.message.reply_text(prompt_with_default("SN ONT BARU", context.user_data["sto"].get("new_sn")))
    return NEW_SN


async def new_sn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != "-":
        context.user_data["sto"]["new_sn"] = text.upper()
    await update.message.reply_text(prompt_with_default("TYPE ONT", context.user_data["sto"].get("ont_type")))
    return ONT_TYPE


async def ont_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await step(update, context, "ont_type", "VALIN ID:", VALINS_ID)


async def valins_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await step(update, context, "valins_id", "KETERANGAN:", DESCRIPTION)


async def description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await step(update, context, "description", "NAMA:", CUSTOMER_NAME)


async def customer_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await step(update, context, "customer_name", "ALAMAT:", ADDRESS)


async def address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await step(update, context, "address", "CP:", CUSTOMER_PHONE)


async def customer_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    technician = await require_technician(update, context)
    if not technician or not update.message or not update.message.text:
        return CUSTOMER_PHONE
    data = context.user_data["sto"]
    data["customer_phone"] = update.message.text.strip()
    content = generate_sto(technician, data)
    db: Database = context.application.bot_data["db"]
    await db.save_history(technician, "STO", data, content)
    context.user_data.pop("sto", None)
    await update.message.reply_text(pre_block(content), parse_mode="HTML", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_sto_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("sto", start_sto),
            MessageHandler(filters.Regex(f"^{MAIN_MENU['sto']}$"), start_sto),
        ],
        states={
            STO: [MessageHandler(filters.TEXT & ~filters.COMMAND, sto)],
            TICKET_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_id)],
            SERVICE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, service_number)],
            OLD_SN: [MessageHandler(filters.TEXT & ~filters.COMMAND, old_sn)],
            NEW_SN: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_sn)],
            ONT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ont_type)],
            VALINS_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, valins_id)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description)],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_name)],
            ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, address)],
            CUSTOMER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_phone)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="sto_conversation",
        persistent=False,
    )
