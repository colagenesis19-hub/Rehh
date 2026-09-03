from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import handlers.order_flow as order_flow_module
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from config import settings
from database import Database
from handlers.admin import build_admin_handlers
from handlers.common import cancel, delete_history, export_history, history, profile, search, settings_menu
from handlers.customer_format import format_customer_command
from handlers.excel_status import build_excel_status_handlers
from handlers.google_sheet import build_google_sheet_handlers
from handlers.login import build_login_conversation, start
from handlers.my_orders import build_my_orders_handlers, orderanku
from handlers.order_flow import build_order_conversation
from services.assign_request_miniapp import handle_assign_message
from services.auto_close import install_auto_close
from services.bot_commands_guide import perintah_command
from services.daily_recap import initialize_recap_delivery_log, recap_harian_command, recap_mingguan_command, send_daily_recaps, send_previous_week_recaps_once, send_weekly_recaps
from services.dismantle_orders import capture_dismantle_order, initialize_dismantle_orders
from services.google_sheet_reference import get_reference_statuses, initialize_sheet_config, sync_missing_orders_from_sheet
from services.jagir_work_orders import capture_jagir_work_order, remember_technician_username
from services.logic_dispatch import detect_logic_group, ignore_group_message
from services.manja_reminder import send_manja_reminders
from services.order_repository import OrderRepository
from services.report_area_leaderboard import _leaderboard_rows, _period_bounds as _area_period_bounds, _registered_area_topics, build_leaderboard_text, send_daily_close, send_report_leaderboard
from services.report_history_export import exportreport_command
from services.report_history_import import import_history_document, importhistory_cancel, importhistory_command
from services.report_hourly_progress import remember_report_manyar_group, send_hourly_report_progress
from services.report_laporan import capture_report_ticket_metadata, laporan_command, laporan_group_command
from services.report_leaderboard import capture_report_group_message, capture_sto_recap_group_message
from services.report_multi_topic import get_topic_identity, handle_multi_report_topic
from services.report_name_only_sto import handle_name_only_sto
from services.report_universal_sto import handle_universal_sto
from services.update_kendala import handle_update_message, migrate_existing_evidence_urls
from utils.keyboards import MAIN_MENU
from utils.logging import setup_logging

AUTO_SHEET_SYNC_SECONDS = 180
REPORT_PROGRESS_SECONDS = 3600
MANJA_REMINDER_SECONDS = 900

async def auto_sync_google_sheet(context) -> None:
    try:
        app = context.application
        database_path = app.bot_data["settings"].database_path
        statuses = await get_reference_statuses(force=True, raise_errors=True)
        total, inserted, updated, unchanged = await sync_missing_orders_from_sheet(database_path, statuses)
        logging.info("Google Sheet auto-sync complete: total=%s inserted=%s updated=%s unchanged=%s", total, inserted, updated, unchanged)
    except Exception:
        logging.exception("Google Sheet auto-sync failed; keeping previous data")

async def leaderboard_command(update, context) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message:
        return
    db: Database = context.application.bot_data["db"]
    app_settings = context.application.bot_data["settings"]
    today = datetime.now(ZoneInfo(app_settings.timezone)).date()
    period_start, _ = _area_period_bounds(today)
    if chat.type == "private":
        topics = await asyncio.to_thread(_registered_area_topics, db.db_path)
        if not topics:
            await message.reply_text("Belum ada topic REPORT yang terdaftar untuk leaderboard.")
            return
        seen: set[tuple[str, str]] = set()
        for _, _, area, sto_code in topics:
            key = (area, sto_code)
            if key in seen:
                continue
            seen.add(key)
            rows = await asyncio.to_thread(_leaderboard_rows, db.db_path, period_start, sto_code)
            await message.reply_text(build_leaderboard_text(rows, today, area))
        return
    if chat.type in {"group", "supergroup"} and message.message_thread_id is not None:
        identity = await asyncio.to_thread(get_topic_identity, db.db_path, chat.id, message.message_thread_id)
        if identity is None:
            return
        area, sto_code = identity
        rows = await asyncio.to_thread(_leaderboard_rows, db.db_path, period_start, sto_code)
        await message.reply_text(build_leaderboard_text(rows, today, area))

async def closeharian_command(update, context) -> None:
    chat = update.effective_chat
    user = update.effective_user
    app_settings = context.application.bot_data["settings"]
    if not chat or chat.type != "private" or not user or user.id not in app_settings.admin_ids:
        return
    await send_daily_close(context)

async def post_init(application: Application) -> None:
    db: Database = application.bot_data["db"]
    orders: OrderRepository = application.bot_data["orders"]
    await db.initialize()
    await orders.initialize()
    await initialize_sheet_config(application.bot_data["settings"].database_path)
    await initialize_dismantle_orders(application.bot_data["settings"].database_path)
    await initialize_recap_delivery_log(db)
    try:
        migrated = await migrate_existing_evidence_urls()
        logging.info("Kendala evidence URL migration complete: updated=%s", migrated)
    except Exception:
        logging.exception("Kendala evidence URL migration failed; bot startup continues")
    await send_previous_week_recaps_once(application)
    if application.job_queue is None:
        logging.warning("JobQueue unavailable; scheduled sync/recap/leaderboard/reminder jobs are disabled.")
    else:
        application.job_queue.run_repeating(auto_sync_google_sheet, interval=AUTO_SHEET_SYNC_SECONDS, first=5, name="google-sheet-auto-sync")
        application.job_queue.run_repeating(send_manja_reminders, interval=MANJA_REMINDER_SECONDS, first=60, name="manja-reminders")
        recap_tz = ZoneInfo(application.bot_data["settings"].timezone)
        now = datetime.now(recap_tz)
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        first_progress = max(1, int((next_hour - now).total_seconds()))
        application.job_queue.run_repeating(send_hourly_report_progress, interval=REPORT_PROGRESS_SECONDS, first=first_progress, name="hourly-report-manyar-progress")
        application.job_queue.run_daily(send_report_leaderboard, time=time(hour=22, minute=0, tzinfo=recap_tz), name="daily-report-leaderboard")
        application.job_queue.run_daily(send_daily_close, time=time(hour=23, minute=59, tzinfo=recap_tz), name="daily-report-close")
        application.job_queue.run_daily(send_daily_recaps, time=time(hour=23, minute=59, tzinfo=recap_tz), name="daily-technician-recap")
        application.job_queue.run_daily(send_weekly_recaps, time=time(hour=20, minute=0, tzinfo=recap_tz), days=(4,), name="weekly-technician-recap")
    logging.info("Clean Telegram bot template started; Google Sheets, technician, order, report, leaderboard, recap and Mini App workflows initialized")

def build_application() -> Application:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    settings.photo_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(settings.log_dir)
    db = Database(settings.database_path)
    orders = OrderRepository(settings.database_path)
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=60.0, write_timeout=60.0, pool_timeout=30.0)
    app = Application.builder().token(settings.bot_token).request(request).get_updates_request(request).post_init(post_init).build()
    app.bot_data["db"] = db
    app.bot_data["orders"] = orders
    app.bot_data["settings"] = settings
    install_auto_close(order_flow_module)
    app.add_handler(MessageHandler(filters.ALL, remember_technician_username), group=-20)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, capture_dismantle_order), group=-13)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, capture_jagir_work_order), group=-12)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, laporan_group_command), group=-11)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, handle_universal_sto), group=-10)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, capture_report_ticket_metadata), group=-9)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, handle_name_only_sto), group=-8)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, handle_multi_report_topic), group=-7)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, remember_report_manyar_group), group=-6)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, capture_sto_recap_group_message), group=-5)
    app.add_handler(MessageHandler(filters.ALL, handle_assign_message), group=-4)
    app.add_handler(MessageHandler(filters.ALL, handle_update_message), group=-3)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, capture_report_group_message), group=-2)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, detect_logic_group), group=-1)
    app.add_handler(MessageHandler(filters.ChatType.GROUPS, ignore_group_message), group=0)
    app.add_handler(build_login_conversation())
    app.add_handler(build_order_conversation())
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("perintah", perintah_command))
    app.add_handler(CommandHandler("daftar_teknisi", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("delete", delete_history))
    app.add_handler(CommandHandler("export", export_history))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("settings", settings_menu))
    app.add_handler(CommandHandler("format", format_customer_command))
    app.add_handler(CommandHandler("rekapharian", recap_harian_command))
    app.add_handler(CommandHandler("rekapmingguan", recap_mingguan_command))
    app.add_handler(CommandHandler("leaderboard", leaderboard_command))
    app.add_handler(CommandHandler("closeharian", closeharian_command))
    app.add_handler(CommandHandler("laporan", laporan_command))
    app.add_handler(CommandHandler("importhistory", importhistory_command))
    app.add_handler(CommandHandler("cancelimporthistory", importhistory_cancel))
    app.add_handler(CommandHandler("exportreport", exportreport_command))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Document.ALL, import_history_document))
    for handler in build_excel_status_handlers(): app.add_handler(handler)
    for handler in build_my_orders_handlers(): app.add_handler(handler)
    for handler in build_google_sheet_handlers(): app.add_handler(handler)
    for handler in build_admin_handlers(): app.add_handler(handler)
    app.add_handler(MessageHandler(filters.Regex(f"^({MAIN_MENU['orders']})$"), orderanku))
    app.add_handler(MessageHandler(filters.Regex(f"^({MAIN_MENU['profile']})$"), profile))
    app.add_handler(MessageHandler(filters.Regex(f"^({MAIN_MENU['settings']})$"), settings_menu))
    app.add_error_handler(error_handler)
    return app

async def error_handler(update, context) -> None:
    logging.exception("Unhandled bot error", exc_info=context.error)
    if not update or not update.effective_chat or update.effective_chat.type != "private":
        return
    await update.effective_chat.send_message("Terjadi error. Silakan coba lagi atau hubungi admin.")

def main() -> None:
    app = build_application()
    app.run_polling(allowed_updates=["message", "callback_query"], drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    main()
