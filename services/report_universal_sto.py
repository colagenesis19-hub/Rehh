from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from database import Database
from services.report_area_tracking import record_area_order
from services.report_laporan import _save_ticket_metadata
from services.report_leaderboard import (
    _period_bounds,
    _store_order,
    _technician_daily_total,
    _technician_period_total,
)
from services.report_multi_topic import get_topic_identity


COMMAND_RE = re.compile(r"^\s*/\s*sto(?:@\w+)?\b\s*:?[\s]*(.*)$", re.IGNORECASE)
FIELD_RE = re.compile(r"^\s*([^:：=]+?)\s*[:：=]\s*(.*?)\s*$")
DIGITS_RE = re.compile(r"\d{6,}")
TECH_WITH_NIK_RE = re.compile(r"^\s*(\d{4,})\s*[|/;,-]\s*(.+?)\s*$")

SERVICE_KEYS = {
    "NO SERVICE", "NO. SERVICE", "NOSERVICE", "SERVICE", "SERVICE NUMBER",
    "NO INET", "NO. INET", "INET", "INTERNET", "NO INTERNET", "NO. INTERNET",
}
TICKET_KEYS = {"TIKET", "TICKET", "TIKET ID", "TICKET ID", "INC", "NO TIKET", "NO. TIKET"}
STO_KEYS = {"STO", "KODE STO", "/STO"}
TECH_FULL_KEYS = {
    "NIK NAMA TEKNISI", "NIK/NAMA TEKNISI", "NIK - NAMA TEKNISI",
    "NIK NAMA PETUGAS", "NIK/NAMA PETUGAS", "TEKNISI", "PETUGAS",
}
TECH_NAME_KEYS = {"NAMA TEKNISI", "NAMA PETUGAS", "NAMA TEK", "TECHNICIAN"}
EMPTY_VALUES = {"", "-", "N/A", "NA", "NONE", "NULL"}
VALID_STO = {"MYR", "JGR"}


@dataclass(frozen=True)
class ParsedSto:
    service_number: str
    ticket_id: str
    sto_code: str
    technician_nik: str
    technician_name: str
    technician_has_nik: bool


def _norm_key(value: str) -> str:
    value = value.upper().replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _norm_name(value: str) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _registered_identity_by_name(database_path, technician_name: str) -> tuple[str, str] | None:
    """Resolve a name-only /sto to a registered technician when the name is unique."""
    wanted = _norm_name(technician_name)
    if not wanted:
        return None

    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            "SELECT nik, name FROM technicians WHERE TRIM(name) != ''"
        ).fetchall()

    matches: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for nik, name in rows:
        clean_name = _clean_value(str(name or ""))
        clean_nik = str(nik or "").strip()
        if _norm_name(clean_name) != wanted or not clean_nik:
            continue
        key = (clean_nik, _norm_name(clean_name))
        if key in seen:
            continue
        seen.add(key)
        matches.append((clean_nik, clean_name))

    if len(matches) == 1:
        return matches[0]
    return None


def _name_identity_key(technician_name: str) -> str:
    """Stable fallback identity for explicit names that are not registered yet."""
    normalized = _norm_name(technician_name)
    return f"NAME-{normalized}" if normalized else "NAME-UNKNOWN"


def _close_jagir_work_order(database_path, service_number: str, technician_nik: str, technician_name: str) -> bool:
    """Mark matching JAGIR WO DONE after its /sto is accepted in REPORT JAGIR."""
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    with sqlite3.connect(database_path) as conn:
        try:
            row = conn.execute(
                "SELECT status, assigned_nik, assigned_name FROM jagir_work_orders WHERE service_number=?",
                (service_number.strip(),),
            ).fetchone()
        except sqlite3.OperationalError:
            return False
        if not row:
            return False

        status, assigned_nik, assigned_name = row
        if str(status or "").strip().upper() == "DONE":
            return False

        # /sto yang diterima di topic JAGIR adalah bukti penutupan WO. Ownership
        # tidak dipakai sebagai blocker karena REPORT dapat dikirim oleh akun lain;
        # NAMA TEKNISI pada /sto tetap disimpan sebagai identitas report.
        cur = conn.execute(
            "UPDATE jagir_work_orders SET status='DONE', updated_at=? WHERE service_number=? AND UPPER(TRIM(status))!='DONE'",
            (now, service_number.strip()),
        )
        conn.commit()
        if cur.rowcount:
            logging.info(
                "JAGIR WO auto-closed by REPORT /sto: inet=%s report_technician=%s (%s) assigned=%s (%s)",
                service_number,
                technician_name,
                technician_nik,
                str(assigned_name or ""),
                str(assigned_nik or ""),
            )
            return True
    return False


def _command_sto_value(text: str) -> str:
    first_line = text.splitlines()[0] if text else ""
    match = COMMAND_RE.match(first_line)
    if not match:
        return ""
    tail = _clean_value(match.group(1))
    if not tail:
        return ""
    token = re.split(r"\s+", tail, maxsplit=1)[0].strip(" :;|,-").upper()
    return token if token in VALID_STO else ""


def _is_sto_command(text: str) -> bool:
    first_line = text.splitlines()[0] if text else ""
    return bool(COMMAND_RE.match(first_line))


def _field_map(text: str) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = FIELD_RE.match(line)
        if not match:
            continue
        key = _norm_key(match.group(1).lstrip("/"))
        value = _clean_value(match.group(2))
        fields.setdefault(key, []).append(value)
    return fields


def _first(fields: dict[str, list[str]], keys: set[str]) -> str:
    normalized_keys = {_norm_key(key) for key in keys}
    for key, values in fields.items():
        if key not in normalized_keys:
            continue
        for value in values:
            if value.upper() not in EMPTY_VALUES:
                return value
    return ""


def _service_number(fields: dict[str, list[str]], text: str) -> str:
    value = _first(fields, SERVICE_KEYS)
    if value:
        match = DIGITS_RE.search(value)
        if match:
            return match.group(0)

    # Fallback hanya pada baris dengan label service/inet supaya nomor CP/SN tidak salah terbaca.
    for raw_line in text.splitlines():
        upper = _norm_key(raw_line)
        if any(alias in upper for alias in ("NO SERVICE", "NO INET", "INET", "NO INTERNET")):
            match = DIGITS_RE.search(raw_line)
            if match:
                return match.group(0)
    return ""


def _technician(fields: dict[str, list[str]]) -> tuple[str, str, bool]:
    full = _first(fields, TECH_FULL_KEYS)
    if full:
        match = TECH_WITH_NIK_RE.match(full)
        if match:
            return match.group(1).strip(), _clean_value(match.group(2)), True
        # Kadang label TEKNISI hanya berisi nama, perlakukan sebagai name-only.
        if not full.isdigit():
            return "", full, False

    name = _first(fields, TECH_NAME_KEYS)
    return "", name, False


def parse_sto(text: str) -> ParsedSto | None:
    if not _is_sto_command(text):
        return None

    fields = _field_map(text)
    service = _service_number(fields, text)
    ticket = _first(fields, TICKET_KEYS)
    sto = _first(fields, STO_KEYS).upper() or _command_sto_value(text)
    nik, name, has_nik = _technician(fields)

    if ticket.upper() in EMPTY_VALUES:
        ticket = ""
    if sto not in VALID_STO:
        sto = ""

    return ParsedSto(
        service_number=service,
        ticket_id=ticket,
        sto_code=sto,
        technician_nik=nik,
        technician_name=name,
        technician_has_nik=has_nik,
    )


async def handle_universal_sto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return
    if message.message_thread_id is None:
        return

    text = (message.text or message.caption or "").strip()
    parsed = parse_sto(text)
    if parsed is None:
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

    area_label, expected_sto = identity
    if parsed.sto_code and parsed.sto_code != expected_sto:
        await message.reply_text(
            "❌ STO TIDAK SESUAI TOPIC\n"
            f"🏢 STO pesan : {parsed.sto_code}\n"
            f"📍 Topic : {area_label} ({expected_sto})\n\n"
            "Perbaiki STO lalu kirim ulang /sto."
        )
        raise ApplicationHandlerStop

    if not parsed.service_number:
        await message.reply_text(
            "❌ REPORT belum bisa disimpan. Nomor INET/NO SERVICE tidak ditemukan."
        )
        raise ApplicationHandlerStop

    technician_nik = parsed.technician_nik
    technician_name = parsed.technician_name
    if not technician_name:
        await message.reply_text(
            "❌ REPORT belum bisa disimpan. Nama teknisi tidak ditemukan.\n"
            "Gunakan `NIK NAMA TEKNISI : NIK | NAMA` atau `NAMA TEKNISI : NAMA`."
        )
        raise ApplicationHandlerStop

    # NAMA TEKNISI di isi /sto adalah sumber identitas utama. Jangan otomatis
    # memakai NIK akun Telegram pengirim bila nama pada isi /sto berbeda, karena
    # satu akun Telegram bisa dipakai untuk mengirim pekerjaan teknisi lain.
    if not technician_nik:
        resolved = await asyncio.to_thread(
            _registered_identity_by_name,
            db.db_path,
            technician_name,
        )
        if resolved is not None:
            technician_nik, canonical_name = resolved
            technician_name = canonical_name
        else:
            user = update.effective_user
            registered = await db.get_technician(user.id) if user is not None else None
            if registered and _norm_name(registered.name) == _norm_name(technician_name):
                technician_nik = registered.nik.strip() or _name_identity_key(technician_name)
            else:
                technician_nik = _name_identity_key(technician_name)

    settings = context.application.bot_data["settings"]
    message_dt = message.date.astimezone(ZoneInfo(settings.timezone))
    period_start, _ = _period_bounds(message_dt.date())

    action = await asyncio.to_thread(
        _store_order,
        db.db_path,
        parsed.service_number,
        period_start,
        technician_nik,
        technician_name,
        message_dt,
        chat.id,
        message.message_id,
    )
    await asyncio.to_thread(
        record_area_order,
        db.db_path,
        parsed.service_number,
        period_start.isoformat(),
        expected_sto,
        area_label,
    )
    await asyncio.to_thread(
        _save_ticket_metadata,
        db.db_path,
        parsed.service_number,
        period_start,
        parsed.ticket_id,
    )

    wo_closed = False
    if expected_sto == "JGR":
        wo_closed = await asyncio.to_thread(
            _close_jagir_work_order,
            db.db_path,
            parsed.service_number,
            technician_nik,
            technician_name,
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

    wo_line = "\n📦 WO JAGIR : ✅ SELESAI" if wo_closed else ""
    await message.reply_text(
        f"{status}\n"
        f"📍 AREA : {area_label}\n"
        f"🏢 STO : {expected_sto}\n"
        f"🌐 INET : {parsed.service_number}\n"
        f"🎫 TIKET : {parsed.ticket_id or 'MANUAL'}\n"
        f"👷 TEKNISI : {technician_name.upper()}\n"
        f"📊 HARI INI : {total_today} order\n"
        f"📊 TOTAL PERIODE : {total_period} order"
        f"{wo_line}"
    )
    logging.info(
        "Universal /sto captured: inet=%s tiket=%s teknisi=%s (%s) area=%s sto=%s action=%s jagir_wo_closed=%s",
        parsed.service_number,
        parsed.ticket_id or "MANUAL",
        technician_name,
        technician_nik,
        area_label,
        expected_sto,
        action,
        wo_closed,
    )
    raise ApplicationHandlerStop
