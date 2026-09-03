from __future__ import annotations

import asyncio
import logging
import re

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from database import Database
from services.report_area_tracking import record_area_order
from services.report_leaderboard import (
    NO_SERVICE_RE,
    TECH_RE,
    _period_bounds,
    _store_order,
    _technician_daily_total,
    _technician_period_total,
)
from services.report_multi_topic import get_topic_identity

NAME_TECH_RE = re.compile(r"NAMA\s*TEKNISI\s*:\s*([^\n\r]+)", re.IGNORECASE)


def _command_from_text(text: str) -> str:
    """Normalize Telegram-style commands, including `/STO:` and `/STO :`."""
    token = text.split(maxsplit=1)[0].lower().split("@", 1)[0]
    return token.rstrip(":")


async def handle_name_only_sto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Accept /sto messages that only contain `NAMA TEKNISI : <name>`.

    Older/external STO formats do not always include `NIK NAMA TEKNISI : NIK | NAME`.
    For registered bot users we resolve the NIK from the sender account. If the sender
    is not registered, their Telegram user id is used as a stable grouping key.
    """
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return

    text = (message.text or message.caption or "").strip()
    if not text:
        return
    command = _command_from_text(text)
    if command != "/sto":
        return

    # Format lengkap tetap ditangani handler /sto yang sudah ada.
    if TECH_RE.search(text):
        return

    service_match = NO_SERVICE_RE.search(text)
    name_match = NAME_TECH_RE.search(text)
    if not service_match or not name_match or message.message_thread_id is None:
        return

    db: Database = context.application.bot_data["db"]
    identity = await asyncio.to_thread(
        get_topic_identity,
        db.db_path,
        chat.id,
        message.message_thread_id,
    )
    if identity is None:
        return

    user = update.effective_user
    technician_name = name_match.group(1).strip()
    technician_nik: str
    if user is not None:
        registered = await db.get_technician(user.id)
        if registered is not None:
            technician_nik = registered.nik.strip()
        else:
            technician_nik = f"TG-{user.id}"
    else:
        technician_nik = f"NAME-{technician_name.upper()}"

    settings = context.application.bot_data["settings"]
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(settings.timezone)
    message_dt = message.date.astimezone(tz)
    period_start, _ = _period_bounds(message_dt.date())
    service_number = service_match.group(1).strip()

    action = await asyncio.to_thread(
        _store_order,
        db.db_path,
        service_number,
        period_start,
        technician_nik,
        technician_name,
        message_dt,
        chat.id,
        message.message_id,
    )

    area_label, sto_code = identity
    await asyncio.to_thread(
        record_area_order,
        db.db_path,
        service_number,
        period_start.isoformat(),
        sto_code,
        area_label,
    )

    total_today = await asyncio.to_thread(
        _technician_daily_total,
        db.db_path,
        message_dt.date(),
        technician_nik,
    )
    total_period = await asyncio.to_thread(
        _technician_period_total,
        db.db_path,
        period_start,
        technician_nik,
    )

    if action == "INSERTED":
        status = "✅ REPORT SUDAH TERSIMPAN"
    elif action == "UPDATED":
        status = "♻️ REPORT DIPERBARUI"
    else:
        status = "ℹ️ REPORT SUDAH TERSIMPAN"

    await message.reply_text(
        f"{status}\n"
        f"📍 AREA : {area_label}\n"
        f"🏢 STO : {sto_code}\n"
        f"🌐 INET : {service_number}\n"
        f"👷 TEKNISI : {technician_name.upper()}\n"
        f"📊 HARI INI : {total_today} order\n"
        f"📊 TOTAL PERIODE : {total_period} order"
    )
    logging.info(
        "Name-only /sto captured: inet=%s teknisi=%s key=%s area=%s sto=%s action=%s",
        service_number,
        technician_name,
        technician_nik,
        area_label,
        sto_code,
        action,
    )
    raise ApplicationHandlerStop
