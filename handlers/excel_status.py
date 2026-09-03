from __future__ import annotations

from pathlib import Path

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from services.auth import require_technician
from services.excel_update import update_order_excel
from services.order_repository import OrderRepository


def _orders(context: ContextTypes.DEFAULT_TYPE) -> OrderRepository:
    return context.application.bot_data["orders"]


async def selesai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return

    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Format:\n/selesai TIKET_ATAU_INET SN_ONT_BARU\n\n"
            "Contoh:\n/selesai INC51203521 ZTEGDE25AB46"
        )
        return

    query = context.args[0].strip()
    new_sn = context.args[1].strip().upper()
    results = await _orders(context).search(query, limit=10)

    exact = [
        order for order in results
        if order.ticket_id.upper() == query.upper()
        or order.service_number == query
    ]

    if not exact:
        await update.effective_message.reply_text("Order tidak ditemukan.")
        return

    if len(exact) > 1:
        await update.effective_message.reply_text(
            "Ditemukan lebih dari satu order. Gunakan TIKET ID atau NO INET yang lebih spesifik."
        )
        return

    order = exact[0]
    updated_order = await _orders(context).update_fields(
        order.id,
        {"new_sn": new_sn, "result": "SELESAI"},
    )

    settings = context.application.bot_data["settings"]
    excel_path = settings.database_path.parent / "imports" / updated_order.source_file

    try:
        count = update_order_excel(
            excel_path,
            ticket_id=updated_order.ticket_id,
            service_number=updated_order.service_number,
            new_sn=new_sn,
            status="CLOSE",
        )
    except Exception as exc:
        await update.effective_message.reply_text(
            "Data bot sudah diperbarui, tetapi Excel gagal diperbarui:\n"
            f"{exc}"
        )
        return

    await update.effective_message.reply_text(
        "✅ Order selesai diperbarui\n\n"
        f"Tiket      : {updated_order.ticket_id or '-'}\n"
        f"No. INET   : {updated_order.service_number or '-'}\n"
        f"SN ONT NEW : {new_sn}\n"
        "Status     : CLOSE\n"
        f"Baris Excel: {count}\n\n"
        "Kirim /exportorder untuk mengambil Excel terbaru."
    )


async def exportorder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    technician = await require_technician(update, context)
    if technician is None or update.effective_message is None:
        return

    settings = context.application.bot_data["settings"]
    import_dir = settings.database_path.parent / "imports"
    files = sorted(
        import_dir.glob("*.xlsx"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ) if import_dir.exists() else []

    if not files:
        await update.effective_message.reply_text(
            "Belum ada Excel order. Upload terlebih dahulu melalui /importorder."
        )
        return

    latest = files[0]
    with latest.open("rb") as file_handle:
        await update.effective_message.reply_document(
            document=file_handle,
            filename=f"UPDATED_{latest.name}",
            caption="Excel order terbaru dengan pembaruan STATUS dan SN ONT NEW.",
        )


def build_excel_status_handlers() -> list[CommandHandler]:
    return [
        CommandHandler("selesai", selesai),
        CommandHandler("exportorder", exportorder),
    ]
