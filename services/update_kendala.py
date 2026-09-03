from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from telegram import Message, Update
from telegram.ext import ContextTypes

from database import Database
from services.google_sheet_reference import (
    current_sheet_url,
    get_reference_statuses,
    status_for_order,
)

PENDING_KEY = "pending_kendala_update"
UPDATE_RE = re.compile(r"^/update(?:@\w+)?\s+(\d{6,})\s+(.+)$", re.IGNORECASE | re.DOTALL)
CANCEL_RE = re.compile(r"^/batalupdate(?:@\w+)?$", re.IGNORECASE)
KENDALA_GROUP_CANONICAL = "REPLACEMENT 200K MANJA"
DEFAULT_EVIDENCE_BASE_URL = "https://app.botkerja.web.id"
HEADERS = [
    "TANGGAL",
    "INET",
    "NAMA PELANGGAN",
    "ALAMAT",
    "CP",
    "TIKET",
    "TEKNISI",
    "STATUS",
    "RCA",
    "KETERANGAN",
    "EVIDEN",
]


def _canonical_title(value: str | None) -> str:
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).split())


def _group_allowed(
    chat_id: int,
    chat_type: str,
    chat_title: str | None,
    message_thread_id: int | None,
    is_topic_message: bool,
) -> bool:
    """Allow /update only in the Manyar parent supergroup and a forum topic.

    Telegram exposes the parent group name as chat.title, not the topic name.
    KENDALA_TOPIC_ID can optionally lock this to one specific topic thread.
    """
    if chat_type not in {"group", "supergroup"}:
        return False
    if _canonical_title(chat_title) != KENDALA_GROUP_CANONICAL:
        return False

    raw_group_id = os.getenv("KENDALA_GROUP_ID", "").strip()
    if raw_group_id:
        try:
            if chat_id != int(raw_group_id):
                return False
        except ValueError:
            logging.error("KENDALA_GROUP_ID tidak valid: %r", raw_group_id)
            return False

    if not is_topic_message or not message_thread_id:
        return False

    raw_topic_id = os.getenv("KENDALA_TOPIC_ID", "").strip()
    if not raw_topic_id:
        return True
    try:
        return message_thread_id == int(raw_topic_id)
    except ValueError:
        logging.error("KENDALA_TOPIC_ID tidak valid: %r", raw_topic_id)
        return False


def _classify(description: str) -> tuple[str, str]:
    value = " ".join(description.upper().split())
    done_keywords = (
        "SUDAH GANTI",
        "SUDAH DIGANTI",
        "SELESAI",
        "DONE",
        "SUDAH SELESAI",
    )
    if any(keyword in value for keyword in done_keywords):
        return "CLOSE", "DONE"
    if "MENOLAK" in value or "TIDAK MAU" in value or "TIDAK BERKENAN" in value:
        return "UPDATE", "MENOLAK"
    if "RUKOS" in value or "RUMAH KOSONG" in value or "TIDAK ADA PENGHUNI" in value:
        return "UPDATE", "RUKOS"
    if (
        "ALAMAT NOK" in value
        or "ALAMAT TIDAK" in value
        or "ALAMAT TIDAK DITEMUKAN" in value
        or "ALAMAT SALAH" in value
        or "ALAMAT TIDAK SESUAI" in value
        or "RUMAH TIDAK DITEMUKAN" in value
    ):
        return "UPDATE", "ALAMAT NOK"
    if "LEPAS DC" in value:
        return "UPDATE", "LEPAS DC"
    if "CABUT" in value or "PUTUS LANGGANAN" in value or "PUTUS INTERNET" in value:
        return "UPDATE", "CABUT"
    if "2 VOIP" in value or "ONT 2 VOIP" in value or "VOIP ADA 2" in value:
        return "UPDATE", "ONT 2 VOIP"
    if "MANJA" in value or "RESCHEDULE" in value or "JADWAL" in value or "BESOK" in value or "LUAR KOTA" in value:
        return "UPDATE", "MANJA"
    if (
        "RNA" in value
        or "TIDAK RESPON" in value
        or "NO RESPON" in value
        or "TIDAK ADA RESPON" in value
        or "TIDAK BISA DIHUBUNGI" in value
        or "CP NOK" in value
        or "CP NO WA" in value
        or "HISTORY NOK" in value
    ):
        return "UPDATE", "RNA"
    if "SALBON" in value:
        return "UPDATE", "SALBON"
    return "UPDATE", "UNSPEC"


def _spreadsheet_id() -> str:
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", current_sheet_url())
    if not match:
        raise RuntimeError("Spreadsheet ORDER belum dikonfigurasi.")
    return match.group(1)


def _credentials_path() -> Path:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/app/secrets/google-service-account.json").strip()
    path = Path(raw)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path


def _sheet_name() -> str:
    return os.getenv("KENDALA_SHEET_NAME", "Kendala").strip() or "Kendala"


def _evidence_base_url() -> str:
    return os.getenv("EVIDENCE_BASE_URL", DEFAULT_EVIDENCE_BASE_URL).strip().rstrip("/")


def _evidence_public_url(path_or_url: str) -> str:
    value = str(path_or_url or "").strip().replace("\\", "/")
    if not value:
        return value
    if value.startswith("http://") or value.startswith("https://"):
        return value

    marker = "evidence/"
    lowered = value.lower()
    marker_index = lowered.find(marker)
    if marker_index >= 0:
        relative = value[marker_index:].lstrip("/")
    else:
        relative = value.lstrip("/")
    return f"{_evidence_base_url()}/{relative}"


def _google_service():
    credentials_path = _credentials_path()
    if not credentials_path.exists():
        raise RuntimeError(f"Credential Google Sheets belum ada di {credentials_path}.")
    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=credentials, cache_discovery=False)


def _upsert_sheet_row(row: list[str]) -> str:
    service = _google_service()
    spreadsheet_id = _spreadsheet_id()
    sheet_name = _sheet_name().replace("'", "''")
    range_prefix = f"'{sheet_name}'"

    current = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{range_prefix}!A:K",
    ).execute().get("values", [])

    if not current:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{range_prefix}!A1:K1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()
        current = [HEADERS]

    target_inet = str(row[1]).strip()
    for row_number, existing in enumerate(current[1:], start=2):
        existing_inet = str(existing[1]).strip() if len(existing) > 1 else ""
        if existing_inet == target_inet:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{range_prefix}!A{row_number}:K{row_number}",
                valueInputOption="RAW",
                body={"values": [row]},
            ).execute()
            return "UPDATED"

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{range_prefix}!A:K",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
    return "INSERTED"


def _migrate_existing_sheet_evidence_urls() -> int:
    """Convert old local evidence paths in Sheet Kendala column K to public URLs."""
    service = _google_service()
    spreadsheet_id = _spreadsheet_id()
    sheet_name = _sheet_name().replace("'", "''")
    range_prefix = f"'{sheet_name}'"
    current = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{range_prefix}!K2:K",
    ).execute().get("values", [])

    updates = []
    for row_number, row in enumerate(current, start=2):
        value = str(row[0]).strip() if row else ""
        if not value or value.startswith("http://") or value.startswith("https://"):
            continue
        new_value = _evidence_public_url(value)
        if new_value == value:
            continue
        updates.append(
            {
                "range": f"{range_prefix}!K{row_number}",
                "values": [[new_value]],
            }
        )

    if not updates:
        return 0

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": updates},
    ).execute()
    return len(updates)


async def migrate_existing_evidence_urls() -> int:
    return await asyncio.to_thread(_migrate_existing_sheet_evidence_urls)


def _ensure_log_table(database_path: Path) -> None:
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kendala_updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                technician_name TEXT NOT NULL,
                service_number TEXT NOT NULL,
                ticket_id TEXT,
                customer_name TEXT,
                address TEXT,
                customer_phone TEXT,
                status TEXT NOT NULL,
                rca TEXT NOT NULL,
                description TEXT NOT NULL,
                evidence_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def _save_local_log(database_path: Path, data: dict[str, str]) -> None:
    _ensure_log_table(database_path)
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            """
            INSERT INTO kendala_updates (
                telegram_id, technician_name, service_number, ticket_id,
                customer_name, address, customer_phone, status, rca,
                description, evidence_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(data["telegram_id"]),
                data["technician_name"],
                data["service_number"],
                data["ticket_id"],
                data["customer_name"],
                data["address"],
                data["customer_phone"],
                data["status"],
                data["rca"],
                data["description"],
                data["evidence_path"],
                data["created_at"],
            ),
        )


def _safe_suffix(filename: str | None, fallback: str) -> str:
    if not filename:
        return fallback
    suffix = Path(filename).suffix.lower()
    if not suffix or len(suffix) > 10 or not re.fullmatch(r"\.[a-z0-9]+", suffix):
        return fallback
    return suffix


async def _download_evidence(message: Message, context: ContextTypes.DEFAULT_TYPE, inet: str) -> str:
    settings = context.application.bot_data["settings"]
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    root = Path(os.getenv("EVIDENCE_DIR", "/app/evidence"))
    if not root.is_absolute():
        root = Path(__file__).resolve().parents[1] / root
    directory = root / f"{now.year:04d}" / f"{now.month:02d}" / inet
    directory.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%d-%H%M%S-%f")

    if message.photo:
        tg_file = await message.photo[-1].get_file()
        suffix = ".jpg"
    elif message.document:
        tg_file = await message.document.get_file()
        suffix = _safe_suffix(message.document.file_name, ".bin")
    else:
        raise ValueError("Eviden harus berupa foto atau file.")

    filename = f"evidence_{stamp}{suffix}"
    destination = directory / filename
    await tg_file.download_to_drive(custom_path=destination)
    return destination.relative_to(root.parent).as_posix()


async def _find_reference(inet: str):
    statuses = await get_reference_statuses()
    reference = status_for_order(statuses, "", inet)
    if reference is not None:
        return reference
    statuses = await get_reference_statuses(force=True, raise_errors=True)
    return status_for_order(statuses, "", inet)


async def _finalize_update(update: Update, context: ContextTypes.DEFAULT_TYPE, pending: dict[str, str]) -> None:
    message = update.effective_message
    if message is None:
        return

    try:
        status, rca = _classify(pending["description"])
        if rca == "DONE":
            context.user_data.pop(PENDING_KEY, None)
            await message.reply_text("ℹ️ Tidak disimpan ke Sheet Kendala karena pekerjaan sudah selesai/DONE.")
            return

        evidence_path = await _download_evidence(message, context, pending["service_number"])
        evidence_url = _evidence_public_url(evidence_path)
        settings = context.application.bot_data["settings"]
        tz = ZoneInfo(settings.timezone)
        now = datetime.now(tz)
        created_at = now.isoformat(timespec="seconds")
        date_text = now.strftime("%d/%m/%Y")
        row = [
            date_text,
            pending["service_number"],
            pending["customer_name"],
            pending["address"],
            pending["customer_phone"],
            pending["ticket_id"],
            pending["technician_name"],
            status,
            rca,
            pending["description"],
            evidence_url,
        ]
        sheet_action = await asyncio.to_thread(_upsert_sheet_row, row)

        db: Database = context.application.bot_data["db"]
        log_data = dict(pending)
        log_data.update({
            "status": status,
            "rca": rca,
            "evidence_path": evidence_path,
            "created_at": created_at,
        })
        await asyncio.to_thread(_save_local_log, db.db_path, log_data)
        context.user_data.pop(PENDING_KEY, None)

        action_text = "BARIS KENDALA DIPERBARUI" if sheet_action == "UPDATED" else "KENDALA BARU DISIMPAN"
        await message.reply_text(
            f"✅ {action_text}\n\n"
            f"🌐 INET : {pending['service_number']}\n"
            f"🎫 TIKET: {pending['ticket_id'] or '-'}\n"
            f"📌 STATUS: {status}\n"
            f"🧩 RCA   : {rca}\n"
            f"📝 KET   : {pending['description']}\n"
            f"📎 EVIDEN: {evidence_url}"
        )
    except Exception as exc:
        logging.exception("Gagal menyimpan /update kendala")
        await message.reply_text(
            "❌ Update belum berhasil disimpan ke Sheet Kendala.\n"
            f"Alasan: {exc}"
        )


async def handle_update_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if message is None or chat is None or user is None:
        return
    if not _group_allowed(
        chat.id,
        chat.type,
        chat.title,
        message.message_thread_id,
        bool(message.is_topic_message),
    ):
        return

    text = (message.text or message.caption or "").strip()
    if CANCEL_RE.match(text):
        if context.user_data.pop(PENDING_KEY, None) is not None:
            await message.reply_text("✅ Proses /update dibatalkan.")
        return

    match = UPDATE_RE.match(text)
    if match:
        inet = match.group(1).strip()
        description = " ".join(match.group(2).strip().split())
        if not description:
            await message.reply_text("Format: /update INET KETERANGAN")
            return

        _, preliminary_rca = _classify(description)
        if preliminary_rca == "DONE":
            context.user_data.pop(PENDING_KEY, None)
            await message.reply_text("ℹ️ Tidak disimpan ke Sheet Kendala karena pekerjaan sudah selesai/DONE.")
            return

        db: Database = context.application.bot_data["db"]
        technician = await db.get_technician(user.id)
        if technician is None:
            await message.reply_text(
                "❌ Telegram kamu belum terdaftar sebagai teknisi. Daftar/login dulu di private bot."
            )
            return

        try:
            reference = await _find_reference(inet)
        except Exception as exc:
            logging.exception("Gagal membaca ORDER untuk /update")
            await message.reply_text(f"❌ Gagal membaca Sheet ORDER.\nAlasan: {exc}")
            return

        if reference is None:
            await message.reply_text(f"❌ INET {inet} tidak ditemukan di Sheet ORDER.")
            return

        pending = {
            "telegram_id": str(user.id),
            "technician_name": technician.name,
            "service_number": reference.service_number or inet,
            "ticket_id": reference.ticket_id or "",
            "customer_name": reference.customer_name or "",
            "address": reference.address or "",
            "customer_phone": reference.customer_phone or "",
            "description": description,
            "chat_id": str(chat.id),
            "thread_id": str(message.message_thread_id or 0),
        }
        context.user_data[PENDING_KEY] = pending

        if message.photo or message.document:
            await _finalize_update(update, context, pending)
        else:
            await message.reply_text(
                "📎 Kirim eviden minimal 1 foto/file untuk menyelesaikan update.\n"
                "Ketik /batalupdate jika ingin membatalkan."
            )
        return

    pending = context.user_data.get(PENDING_KEY)
    if not pending or not (message.photo or message.document):
        return
    if str(chat.id) != pending.get("chat_id"):
        return
    if str(message.message_thread_id or 0) != pending.get("thread_id"):
        return

    await _finalize_update(update, context, pending)