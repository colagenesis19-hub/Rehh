from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from services.report_laporan import _save_ticket_metadata
from services.report_leaderboard import _period_bounds, _store_order

PENDING_KEY = "legacy_replacement_report_import"
MARKER = "/REPORT"
FIELD_RE = re.compile(
    r"(?im)^\s*(TANGGAL|NIK|NAMA|TIKET\s*ID|NO\s*INET|SN\s*ONT\s*LAMA|SN\s*ONT\s*BARU|VALINS\s*ID|RESULT|KETERANGAN)\s*[:：=]\s*(.*)$"
)

def _flatten(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                out.append(item["text"])
        return "".join(out)
    return ""

def _messages(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("messages"), list):
        return [x for x in payload["messages"] if isinstance(x, dict)]
    return []

def _clean(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split()).strip()

def parse_replacement(text: str) -> dict[str, str] | None:
    normalized = text.replace("\u00a0", " ")
    upper = normalized.upper()
    if MARKER not in upper or "REPLACEMENT" not in upper or "ONT" not in upper:
        return None
    data: dict[str, str] = {}
    aliases = {
        "TANGGAL": "report_date", "NIK": "nik", "NAMA": "name",
        "TIKET ID": "ticket_id", "NO INET": "service_number",
        "SN ONT LAMA": "old_sn", "SN ONT BARU": "new_sn",
        "VALINS ID": "valins_id", "RESULT": "result",
        "KETERANGAN": "description",
    }
    for key, value in FIELD_RE.findall(normalized):
        data[aliases[" ".join(key.upper().split())]] = _clean(value)
    if not data.get("service_number") or not data.get("name"):
        return None
    data["service_number"] = re.sub(r"\D", "", data["service_number"])
    if len(data["service_number"]) < 8:
        return None
    return data

def _ensure_detail_table(path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS legacy_replacement_reports (
            service_number TEXT NOT NULL,
            period_start TEXT NOT NULL,
            report_date TEXT NOT NULL,
            technician_nik TEXT NOT NULL DEFAULT '',
            technician_name TEXT NOT NULL,
            ticket_id TEXT NOT NULL DEFAULT '',
            old_sn TEXT NOT NULL DEFAULT '',
            new_sn TEXT NOT NULL DEFAULT '',
            valins_id TEXT NOT NULL DEFAULT '',
            result TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            source_message_id INTEGER,
            source_message_date TEXT,
            PRIMARY KEY(service_number, period_start)
        )""")

def _store_detail(path, data: dict[str, str], period_start, source_id: int | None, source_date: str) -> bool:
    _ensure_detail_table(path)
    with sqlite3.connect(path) as conn:
        exists = conn.execute("SELECT 1 FROM legacy_replacement_reports WHERE service_number=? AND period_start=?",
            (data["service_number"], period_start.isoformat())).fetchone()
        if exists:
            return False
        conn.execute("""INSERT INTO legacy_replacement_reports
        (service_number,period_start,report_date,technician_nik,technician_name,ticket_id,old_sn,new_sn,valins_id,result,description,source_message_id,source_message_date)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (data["service_number"], period_start.isoformat(), data.get("report_date",""), data.get("nik",""),
         data.get("name",""), data.get("ticket_id",""), data.get("old_sn",""), data.get("new_sn",""),
         data.get("valins_id",""), data.get("result",""), data.get("description",""), source_id, source_date))
        return True

async def importreplacementhistory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat, user, message = update.effective_chat, update.effective_user, update.effective_message
    settings = context.application.bot_data["settings"]
    if not chat or chat.type != "private" or not user or user.id not in settings.admin_ids or not message:
        return
    context.user_data[PENDING_KEY] = True
    await message.reply_text("📥 IMPORT REPORT REPLACEMENT SIAP\n\nKirim file JSON hasil Export Telegram. Bot hanya mengambil /REPORT REPLACEMENT ONT dan mengabaikan chat lain.")

async def import_legacy_replacement_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get(PENDING_KEY):
        return
    message = update.effective_message
    if not message or not message.document:
        return
    settings = context.application.bot_data["settings"]
    if update.effective_user.id not in settings.admin_ids:
        return
    if not (message.document.file_name or "").lower().endswith(".json"):
        await message.reply_text("❌ File harus JSON hasil Export Telegram.")
        return
    await message.reply_text("⏳ Membaca dan memvalidasi report historis...")
    try:
        f = await context.bot.get_file(message.document.file_id)
        payload = json.loads(bytes(await f.download_as_bytearray()).decode("utf-8-sig"))
    except Exception as exc:
        await message.reply_text(f"❌ Gagal membaca JSON: {exc}")
        return

    tz = ZoneInfo(settings.timezone)
    db_path = context.application.bot_data["settings"].database_path
    scanned = valid = imported = duplicate = invalid = 0
    for item in _messages(payload):
        scanned += 1
        data = parse_replacement(_flatten(item.get("text")))
        if data is None:
            continue
        valid += 1
        raw_date = data.get("report_date") or str(item.get("date") or "")
        dt = None
        for fmt in ("%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(raw_date[:19], fmt).replace(tzinfo=tz)
                break
            except ValueError:
                pass
        if dt is None:
            try:
                dt = datetime.fromisoformat(str(item.get("date")).replace("Z","+00:00")).astimezone(tz)
            except Exception:
                invalid += 1
                continue
        period_start, _ = _period_bounds(dt.date())
        try:
            message_id = int(item.get("id"))
        except Exception:
            message_id = None
        created = await asyncio.to_thread(_store_detail, db_path, data, period_start, message_id, str(item.get("date") or ""))
        if not created:
            duplicate += 1
            continue
        await asyncio.to_thread(_store_order, db_path, data["service_number"], period_start,
            data.get("nik","") or "NAME-" + data["name"].upper(), data["name"], dt, 0, message_id)
        ticket = data.get("ticket_id","").strip()
        if ticket and ticket.upper() not in {"MANUAL","-","N/A","NA","NONE"}:
            await asyncio.to_thread(_save_ticket_metadata, db_path, data["service_number"], period_start, ticket)
        imported += 1

    context.user_data.pop(PENDING_KEY, None)
    await message.reply_text(
        "✅ IMPORT REPORT REPLACEMENT SELESAI\n"
        f"📨 Pesan diperiksa : {scanned}\n"
        f"📋 Report terdeteksi : {valid}\n"
        f"➕ Report baru : {imported}\n"
        f"🔁 Duplikat : {duplicate}\n"
        f"❌ Tanggal/data invalid : {invalid}\n\n"
        "Detail legacy disimpan tanpa menghapus data yang sudah ada. Data report dapat dipakai oleh /laporan."
    )
