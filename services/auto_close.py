from __future__ import annotations

import logging
from functools import wraps

from services.excel_update import update_order_excel
from services.google_sheet_reference import (
    CLOSED_STATUSES,
    get_reference_statuses,
    normalize,
    status_for_order,
)

GENERIC_ONT_TYPES = {
    "ONT", "ONT PREMIUM", "ONT DUALBAND", "ONT DUAL BAND",
    "ONT REPLACEMENT", "REPLACEMENT", "PREMIUM", "DUALBAND", "DUAL BAND",
}
EMPTY_VALUES = {"", "-", "N/A", "NA", "NONE", "NULL"}


def install_auto_close(order_flow_module) -> None:
    """Sinkronkan data referensi Sheet, validasi, lalu auto-close output baru."""
    original_continue_order = order_flow_module.continue_order
    original_send_outputs = order_flow_module.send_outputs

    order_flow_module.FIELD_LABELS["ont_type"] = (
        "MODEL / TYPE ONT BARU (contoh: HG8145V5, HG8245H5, F609)"
    )

    def is_missing(field: str, value: object) -> bool:
        normalized = normalize(value)
        if normalized in EMPTY_VALUES:
            return True
        if field == "ticket_id" and normalized == "MANUAL":
            return True
        if field == "ont_type" and normalized in GENERIC_ONT_TYPES:
            return True
        return False

    def missing_fields_with_real_ont(order, action: str) -> list[str]:
        data = order_flow_module.order_data(order)
        return [
            field for field in order_flow_module.REQUIRED_FIELDS[action]
            if is_missing(field, data.get(field, ""))
        ]

    order_flow_module.missing_fields = missing_fields_with_real_ont

    @wraps(original_continue_order)
    async def continue_order_with_validation(update, context, order) -> int:
        message = update.effective_message
        if message is None:
            return order_flow_module.ConversationHandler.END

        # STO adalah profil teknisi dan selalu dipakai lebih dahulu daripada
        # data order maupun Google Sheets.
        technician = await order_flow_module.require_technician(update, context)
        if technician is None:
            return order_flow_module.ConversationHandler.END
        if not technician.sto.strip():
            await message.reply_text(
                "Profil Anda belum memiliki STO. Silakan /start lalu isi STO satu kali."
            )
            return order_flow_module.ConversationHandler.END

        try:
            current_sto = normalize(order.sto)
            profile_sto = technician.sto.strip().upper()
            if current_sto != normalize(profile_sto):
                order = await context.application.bot_data["orders"].update_fields(
                    order.id, {"sto": profile_sto}
                )
        except Exception:
            logging.exception("Gagal mengisi STO order dari profil teknisi")

        # Google Sheets hanya dibaca. Data teknisi yang sudah tersimpan tidak ditimpa.
        try:
            statuses = await get_reference_statuses()
            reference = status_for_order(
                statuses,
                ticket_id=order.ticket_id,
                service_number=order.service_number,
            )
            if reference is not None:
                current = order.to_dict()
                updates: dict[str, str] = {}
                for field, sheet_value in reference.order_fields().items():
                    if field == "sto":
                        continue
                    if sheet_value and is_missing(field, current.get(field, "")):
                        updates[field] = sheet_value

                if updates:
                    order = await context.application.bot_data["orders"].update_fields(
                        order.id, updates
                    )
        except Exception:
            logging.exception("Gagal menyinkronkan data order dari Google Sheets")

        action = context.user_data.get("order_action", "lengkap")
        missing = order_flow_module.missing_fields(order, action)
        if missing:
            context.user_data["active_order_id"] = order.id
            context.user_data["missing_fields"] = missing
            lines = [
                "Data order ditemukan.", "",
                "Isi HANYA data yang masih kosong atau belum benar, satu jawaban per baris:", "",
            ]
            for index, field in enumerate(missing, start=1):
                lines.append(f"{index}. {order_flow_module.FIELD_LABELS[field]}")
            lines.extend([
                "",
                "Data dari Google Sheets sudah diambil otomatis. Isi hanya yang tetap kosong.",
                "STO diambil otomatis dari profil teknisi.",
                "Data akan disimpan dan permintaan berikutnya langsung dikirim jika sudah lengkap.",
                f"Jumlah jawaban harus {len(missing)} baris.",
            ])
            await message.reply_text(
                "\n".join(lines), reply_markup=order_flow_module.cancel_keyboard()
            )
            return order_flow_module.FILL_MISSING

        return await original_continue_order(update, context, order)

    @wraps(original_send_outputs)
    async def send_outputs_with_auto_close(update, context, order, action) -> None:
        technician = await order_flow_module.require_technician(update, context)
        if technician is None or not technician.sto.strip():
            if update.effective_message:
                await update.effective_message.reply_text(
                    "Profil Anda belum memiliki STO. Silakan /start lalu isi STO satu kali."
                )
            return

        profile_sto = technician.sto.strip().upper()
        if normalize(order.sto) != normalize(profile_sto):
            order = await context.application.bot_data["orders"].update_fields(
                order.id, {"sto": profile_sto}
            )

        await original_send_outputs(update, context, order, action)
        if normalize(order.result) in CLOSED_STATUSES:
            return

        message = update.effective_message
        if message is None:
            return
        new_sn = (order.new_sn or "").strip().upper()
        if not new_sn or new_sn == "-":
            await message.reply_text(
                "⚠️ Status belum diubah menjadi CLOSE karena SN ONT BARU belum tersedia."
            )
            return

        try:
            updated_order = await context.application.bot_data["orders"].update_fields(
                order.id, {"new_sn": new_sn, "result": "CLOSE"}
            )
            settings = context.application.bot_data["settings"]
            excel_path = settings.database_path.parent / "imports" / updated_order.source_file
            changed_rows = update_order_excel(
                excel_path,
                ticket_id=updated_order.ticket_id,
                service_number=updated_order.service_number,
                new_sn=new_sn,
                status="CLOSE",
            )
            await message.reply_text(
                "✅ Order otomatis ditandai selesai\n\n"
                f"SN ONT NEW : {new_sn}\nSTATUS     : CLOSE\n"
                f"Baris Excel: {changed_rows}\n\n"
                "Gunakan /exportorder untuk mengambil Excel terbaru."
            )
        except Exception as exc:
            logging.exception("Gagal memperbarui Excel order secara otomatis")
            await message.reply_text(
                "⚠️ Format laporan berhasil dibuat, tetapi pembaruan Excel gagal:\n"
                f"{exc}"
            )

    order_flow_module.continue_order = continue_order_with_validation
    order_flow_module.send_outputs = send_outputs_with_auto_close
