from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from services.report_laporan import _save_ticket_metadata
from services.report_leaderboard import _period_bounds, _store_order

PENDING_KEY = "legacy_replacement_report_import"
MARKER = "/REPORT"
SHEET_HEADERS = ["TANGGAL","NIK","NAMA","TIKET ID","NO INET","SN ONT LAMA","SN ONT BARU","VALINS ID","RESULT","KETERANGAN","SUMBER"]
FIELD_RE = re.compile(r"(?im)^\s*(TANGGAL|NIK|NAMA|TIKET\s*ID|NO\s*INET|SN\s*ONT\s*LAMA|SN\s*ONT\s*BARU|VALINS\s*ID|RESULT|KETERANGAN)\s*[:：=]\s*(.*)$")

def _flatten(value: Any) -> str:
    if isinstance(value, str): return value
    if isinstance(value, list):
        return "".join(x if isinstance(x, str) else x.get("text","") if isinstance(x, dict) else "" for x in value)
    return ""

def _messages(payload: Any) -> list[dict[str, Any]]:
    return [x for x in payload.get("messages", []) if isinstance(x, dict)] if isinstance(payload, dict) else []

def _clean(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").split()).strip()

def parse_replacement(text: str) -> dict[str, str] | None:
    normalized = text.replace("\u00a0", " ")
    upper = normalized.upper()
    if MARKER not in upper or "REPLACEMENT" not in upper or "ONT" not in upper: return None
    aliases = {"TANGGAL":"report_date","NIK":"nik","NAMA":"name","TIKET ID":"ticket_id","NO INET":"service_number","SN ONT LAMA":"old_sn","SN ONT BARU":"new_sn","VALINS ID":"valins_id","RESULT":"result","KETERANGAN":"description"}
    data = {aliases[" ".join(k.upper().split())]: _clean(v) for k,v in FIELD_RE.findall(normalized)}
    data["service_number"] = re.sub(r"\D", "", data.get("service_number",""))
    return data if data.get("service_number") and data.get("name") and len(data["service_number"]) >= 8 else None

def _ensure_detail_table(path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS legacy_replacement_reports (
        service_number TEXT NOT NULL, period_start TEXT NOT NULL, report_date TEXT NOT NULL,
        technician_nik TEXT NOT NULL DEFAULT '', technician_name TEXT NOT NULL, ticket_id TEXT NOT NULL DEFAULT '',
        old_sn TEXT NOT NULL DEFAULT '', new_sn TEXT NOT NULL DEFAULT '', valins_id TEXT NOT NULL DEFAULT '',
        result TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '', source_message_id INTEGER,
        source_message_date TEXT, PRIMARY KEY(service_number, period_start))""")

def _store_detail(path, data, period_start, source_id, source_date) -> bool:
    _ensure_detail_table(path)
    with sqlite3.connect(path) as conn:
        if conn.execute("SELECT 1 FROM legacy_replacement_reports WHERE service_number=? AND period_start=?", (data["service_number"], period_start.isoformat())).fetchone(): return False
        conn.execute("""INSERT INTO legacy_replacement_reports
        (service_number,period_start,report_date,technician_nik,technician_name,ticket_id,old_sn,new_sn,valins_id,result,description,source_message_id,source_message_date)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (data["service_number"],period_start.isoformat(),data.get("report_date",""),data.get("nik",""),data.get("name",""),data.get("ticket_id",""),data.get("old_sn",""),data.get("new_sn",""),data.get("valins_id",""),data.get("result",""),data.get("description",""),source_id,source_date))
    return True

def _spreadsheet_id() -> str:
    raw = (os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_SPREADSHEET_ID") or "").strip()
    if "/spreadsheets/d/" in raw:
        match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", raw)
        raw = match.group(1) if match else ""
    if raw: return raw
    from services.google_sheet_reference import DEFAULT_SPREADSHEET_ID
    return DEFAULT_SPREADSHEET_ID

def _sheet_name() -> str:
    return os.getenv("REPLACEMENT_REPORT_SHEET_NAME", "Report Replacement Historis").strip() or "Report Replacement Historis"

def _google_client():
    import gspread
    path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/app/secrets/google-service-account.json").strip()
    if not path: raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE belum dikonfigurasi")
    if not Path(path).exists(): raise RuntimeError(f"Credential service account tidak ditemukan: {path}")
    return gspread.service_account(filename=path)

def _worksheet():
    book = _google_client().open_by_key(_spreadsheet_id())
    try: return book.worksheet(_sheet_name())
    except Exception:
        ws = book.add_worksheet(title=_sheet_name(), rows=1000, cols=len(SHEET_HEADERS))
        ws.append_row(SHEET_HEADERS, value_input_option="USER_ENTERED")
        return ws

def _sheet_key(data: dict[str,str]) -> tuple[str,str]:
    return (data.get("report_date",""), data["service_number"])

def _sync_sheet(rows: list[dict[str,str]]) -> tuple[int,int]:
    if not rows: return 0,0
    ws = _worksheet()
    values = ws.get_all_values()
    if not values:
        ws.append_row(SHEET_HEADERS, value_input_option="USER_ENTERED"); values=[SHEET_HEADERS]
    header = values[0]
    if header != SHEET_HEADERS:
        ws.update("A1:K1", [SHEET_HEADERS])
    existing = {(r[0].strip(), re.sub(r"\D","",r[4])) for r in values[1:] if len(r) >= 5}
    append=[]; skipped=0
    for d in rows:
        if _sheet_key(d) in existing: skipped += 1; continue
        append.append([d.get("report_date",""),d.get("nik",""),d.get("name",""),d.get("ticket_id",""),d.get("service_number",""),d.get("old_sn",""),d.get("new_sn",""),d.get("valins_id",""),d.get("result",""),d.get("description",""),"Telegram legacy import"])
    if append: ws.append_rows(append, value_input_option="USER_ENTERED")
    return len(append), skipped

async def importreplacementhistory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat,user,message=update.effective_chat,update.effective_user,update.effective_message
    settings=context.application.bot_data["settings"]
    if not chat or chat.type!="private" or not user or user.id not in settings.admin_ids or not message: return
    context.user_data[PENDING_KEY]=True
    await message.reply_text("📥 IMPORT REPORT REPLACEMENT SIAP\n\nKirim JSON Export Telegram. Data valid akan disimpan ke database dan disinkronkan ke Google Sheet.")

async def import_legacy_replacement_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get(PENDING_KEY): return
    message=update.effective_message
    if not message or not message.document: return
    settings=context.application.bot_data["settings"]
    if update.effective_user.id not in settings.admin_ids: return
    if not (message.document.file_name or "").lower().endswith(".json"):
        await message.reply_text("❌ File harus JSON hasil Export Telegram."); return
    await message.reply_text("⏳ Membaca, memvalidasi, dan menyiapkan sinkronisasi Google Sheet...")
    try:
        f=await context.bot.get_file(message.document.file_id)
        payload=json.loads(bytes(await f.download_as_bytearray()).decode("utf-8-sig"))
    except Exception as exc:
        await message.reply_text(f"❌ Gagal membaca JSON: {exc}"); return
    tz=ZoneInfo(settings.timezone); db_path=settings.database_path
    scanned=valid=imported=duplicate=invalid=0; sheet_rows=[]
    for item in _messages(payload):
        scanned += 1; data=parse_replacement(_flatten(item.get("text")))
        if data is None: continue
        valid += 1; raw=data.get("report_date") or str(item.get("date") or ""); dt=None
        for fmt in ("%d/%m/%Y","%Y-%m-%dT%H:%M:%S"):
            try: dt=datetime.strptime(raw[:19],fmt).replace(tzinfo=tz); break
            except ValueError: pass
        if dt is None:
            try: dt=datetime.fromisoformat(str(item.get("date")).replace("Z","+00:00")).astimezone(tz)
            except Exception: invalid += 1; continue
        period_start,_=_period_bounds(dt.date())
        try: message_id=int(item.get("id"))
        except Exception: message_id=None
        created=await asyncio.to_thread(_store_detail,db_path,data,period_start,message_id,str(item.get("date") or ""))
        if not created: duplicate += 1; continue
        await asyncio.to_thread(_store_order,db_path,data["service_number"],period_start,data.get("nik","") or "NAME-"+data["name"].upper(),data["name"],dt,0,message_id)
        ticket=data.get("ticket_id","").strip()
        if ticket and ticket.upper() not in {"MANUAL","-","N/A","NA","NONE"}: await asyncio.to_thread(_save_ticket_metadata,db_path,data["service_number"],period_start,ticket)
        sheet_rows.append(data); imported += 1
    sheet_added=sheet_skipped=0; sheet_error=""
    try: sheet_added,sheet_skipped=await asyncio.to_thread(_sync_sheet,sheet_rows)
    except Exception as exc: sheet_error=str(exc)
    context.user_data.pop(PENDING_KEY,None)
    text=("✅ IMPORT REPORT REPLACEMENT SELESAI\n"+f"📨 Pesan diperiksa : {scanned}\n📋 Report terdeteksi : {valid}\n➕ Database baru : {imported}\n🔁 Database duplikat : {duplicate}\n❌ Invalid : {invalid}\n\n"+f"📊 Google Sheet ditambahkan : {sheet_added}\n🔁 Sheet sudah ada : {sheet_skipped}")
    if sheet_error: text += f"\n⚠️ Sinkronisasi Sheet gagal: {sheet_error}"
    await message.reply_text(text)
