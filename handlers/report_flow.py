from __future__ import annotations

from telegram import Update
from telegram.ext import CommandHandler, ConversationHandler, ContextTypes, MessageHandler, filters

from database import Database
from handlers.common import cancel
from services.auth import require_technician
from services.formatters import generate_report
from utils.keyboards import MAIN_MENU, cancel_keyboard, main_menu_keyboard
from utils.telegram_format import pre_block


TICKET_ID, INTERNET_NUMBER, CUSTOMER_NAME, OLD_SN, NEW_SN, VALINS_ID, RESULT, DESCRIPTION = range(200, 208)


async def start_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    technician = await require_technician(update, context)
    if not technician or not update.message:
        return ConversationHandler.END
    context.user_data["report"] = dict(context.user_data.get("last_replacement", {}))
    await update.message.reply_text("TIKET ID:", reply_markup=cancel_keyboard())
    return TICKET_ID


async def step(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, prompt: str, next_state: int) -> int:
    if not update.message or not update.message.text:
        return next_state
    context.user_data["report"][key] = update.message.text.strip()
    await update.message.reply_text(prompt)
    return next_state


async def ticket_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await step(update, context, "ticket_id", "NO INET:", INTERNET_NUMBER)


async def internet_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data["report"]
    data["internet_number"] = update.message.text.strip()
    if data.get("customer_name"):
        await update.message.reply_text(
            f"NAMA [{data['customer_name']}]\nKetik - untuk pakai data ini, atau input baru:"
        )
    else:
        await update.message.reply_text("NAMA:")
    return CUSTOMER_NAME


async def customer_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    data = context.user_data["report"]
    if text != "-":
        data["customer_name"] = text
    if data.get("old_sn"):
        await update.message.reply_text(f"SN ONT LAMA [{data['old_sn']}]\nKetik - untuk pakai data ini, atau input baru:")
    else:
        await update.message.reply_text("SN ONT LAMA:")
    return OLD_SN


async def old_sn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != "-":
        context.user_data["report"]["old_sn"] = text.upper()
    data = context.user_data["report"]
    if data.get("new_sn"):
        await update.message.reply_text(f"SN ONT BARU [{data['new_sn']}]\nKetik - untuk pakai data ini, atau input baru:")
    else:
        await update.message.reply_text("SN ONT BARU:")
    return NEW_SN


async def new_sn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if text != "-":
        context.user_data["report"]["new_sn"] = text.upper()
    await update.message.reply_text("VALINS ID:")
    return VALINS_ID


async def valins_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await step(update, context, "valins_id", "RESULT:", RESULT)


async def result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await step(update, context, "result", "KETERANGAN:", DESCRIPTION)


async def description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    technician = await require_technician(update, context)
    if not technician or not update.message or not update.message.text:
        return DESCRIPTION
    data = context.user_data["report"]
    data["description"] = update.message.text.strip()
    settings = context.application.bot_data["settings"]
    content = generate_report(technician, data, settings.timezone)
    db: Database = context.application.bot_data["db"]
    await db.save_history(technician, "REPORT", data, content)
    context.user_data.pop("report", None)
    await update.message.reply_text(pre_block(content), parse_mode="HTML", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def build_report_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("report", start_report),
            MessageHandler(filters.Regex(f"^{MAIN_MENU['report']}$"), start_report),
        ],
        states={
            TICKET_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_id)],
            INTERNET_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, internet_number)],
            CUSTOMER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, customer_name)],
            OLD_SN: [MessageHandler(filters.TEXT & ~filters.COMMAND, old_sn)],
            NEW_SN: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_sn)],
            VALINS_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, valins_id)],
            RESULT: [MessageHandler(filters.TEXT & ~filters.COMMAND, result)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="report_conversation",
        persistent=False,
    )
