from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from database import Database
from services.order_repository import OrderRepository


def _greeting(hour: int) -> str:
    if 4 <= hour < 11:
        return "Selamat pagi"
    if 11 <= hour < 15:
        return "Selamat siang"
    if 15 <= hour < 18:
        return "Selamat sore"
    return "Selamat malam"


def _dash(value: str) -> str:
    value = str(value or "").strip()
    return value if value else "-"


def build_customer_whatsapp_text(
    *,
    greeting: str,
    technician_name: str,
    customer_name: str,
    inet: str,
    address: str,
    phone: str,
) -> str:
    """WhatsApp customer template aligned with the Kerja BOT Mini App."""
    return (
        f"{greeting} Bapak/Ibu {customer_name}.\n\n"
        f"Perkenalkan, saya {technician_name}, teknisi resmi IndiHome.\n\n"
        "Mohon maaf mengganggu waktunya. Saya mendapat penugasan dari pihak Telkom "
        "untuk melakukan penggantian ONT/Modem pada layanan Bapak/Ibu sebagai bagian "
        "dari pembaruan perangkat jaringan.\n\n"
        f"No. Internet: {inet}\n"
        f"Alamat: {address}\n"
        f"No. HP: {phone}\n\n"
        "Dengan penggantian perangkat ini, Bapak/Ibu akan mendapatkan beberapa benefit:\n"
        "• Jaringan lebih stabil\n"
        "• Perangkat kompatibel dengan jaringan WiFi 5 GHz\n"
        "• Biaya langganan tetap, tidak berubah\n"
        "• Tidak ada biaya pemasangan / GRATIS\n\n"
        "Pekerjaan penggantian perangkat akan dilakukan oleh teknisi resmi IndiHome/Telkom "
        "yang mendapat penugasan.\n\n"
        "Apabila Bapak/Ibu berkenan, mohon konfirmasi waktu yang sesuai agar saya dapat "
        "melakukan kunjungan.\n\n"
        "Jika terdapat kendala atau membutuhkan konfirmasi terkait layanan, Bapak/Ibu "
        "dapat menghubungi layanan resmi Telkom melalui 188.\n\n"
        "Terima kasih atas perhatian dan kerja sama Bapak/Ibu. 🙏🏼"
    )


async def format_customer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    if not chat or chat.type != "private" or not user or not message:
        return

    if not context.args:
        await message.reply_text("Format: /format <INET>\nContoh: /format 152303339740")
        return

    inet = context.args[0].strip()
    if not inet.isdigit():
        await message.reply_text("Nomor INET tidak valid.\nContoh: /format 152303339740")
        return

    db: Database = context.application.bot_data["db"]
    orders: OrderRepository = context.application.bot_data["orders"]

    technician = await db.get_technician(user.id)
    if technician is None:
        await message.reply_text("Silakan daftar/login sebagai teknisi terlebih dahulu.")
        return

    matches = await orders.search(inet, limit=10)
    order = next((item for item in matches if item.service_number.strip() == inet), None)
    if order is None:
        await message.reply_text(f"Order dengan INET {inet} tidak ditemukan.")
        return

    settings = context.application.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    greeting = _greeting(datetime.now(tz).hour)

    text = build_customer_whatsapp_text(
        greeting=greeting,
        technician_name=_dash(technician.name),
        customer_name=_dash(order.customer_name),
        inet=inet,
        address=_dash(order.address),
        phone=_dash(order.customer_phone),
    )

    await message.reply_text(text)
