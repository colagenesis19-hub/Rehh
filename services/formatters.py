from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database import Technician


def value(data: dict, key: str) -> str:
    return str(data.get(key) or "-").strip()


def technician_sto(technician: Technician, data: dict) -> str:
    return (technician.sto or value(data, "sto")).strip().upper() or "-"


def line(label: str, text: str, width: int = 17) -> str:
    return f"{label:<{width}}: {text}"


def generate_config(technician: Technician, data: dict) -> str:
    rows = [
        "===========================",
        "/CONFIG REPLACEMENT ONT",
        "===========================",
        "",
        line("NIK", technician.nik),
        line("NAMA", technician.name),
        line("TIKET ID", value(data, "ticket_id")),
        line("NO SERVICE", value(data, "service_number")),
        line("NO VOIP", value(data, "voip")),
        line("SN ONT LAMA", value(data, "old_sn")),
        line("SN ONT BARU", value(data, "new_sn")),
        line("TYPE ONT", value(data, "ont_type")),
        line("STO", technician_sto(technician, data)),
        line("KETERANGAN", value(data, "config_description")),
    ]
    return "\n".join(rows)


def generate_report(technician: Technician, data: dict, timezone: str) -> str:
    try:
        today = datetime.now(ZoneInfo(timezone)).strftime("%d/%m/%Y")
    except ZoneInfoNotFoundError:
        today = datetime.now().strftime("%d/%m/%Y")

    rows = [
        "=============================",
        "/REPORT REPLACEMENT ONT",
        "=============================",
        line("TANGGAL", today),
        line("NIK", technician.nik),
        line("NAMA", technician.name),
        line("TIKET ID", value(data, "ticket_id")),
        line("NO INET", value(data, "service_number")),
        line("SN ONT LAMA", value(data, "old_sn")),
        line("SN ONT BARU", value(data, "new_sn")),
        line("VALINS ID", value(data, "valins_id")),
        line("RESULT", value(data, "result")),
        line("KETERANGAN", value(data, "report_description")),
        line("ALAMAT", value(data, "address")),
        line("CP", value(data, "customer_phone")),
        "=============================",
    ]
    return "\n".join(rows)


def generate_sto(technician: Technician, data: dict) -> str:
    sto = technician_sto(technician, data)
    rows = [
        f"/STO : {sto}",
        f"TIKET : {value(data, 'ticket_id')}",
        f"NO SERVICE : {value(data, 'service_number')}",
        f"SN ONT LAMA : {value(data, 'old_sn')}",
        f"SN ONT BARU : {value(data, 'new_sn')}",
        f"TYPE ONT : {value(data, 'ont_type')}",
        f"STO : {sto}",
        f"VALIN ID : {value(data, 'valins_id')}",
        f"KETERANGAN : {value(data, 'report_description')}",
        f"NAMA : {value(data, 'customer_name')}",
        f"ALAMAT : {value(data, 'address')}",
        f"CP : {value(data, 'customer_phone')}",
        f"NIK NAMA TEKNISI : {technician.nik} | {technician.name}",
    ]
    return "\n".join(rows)
