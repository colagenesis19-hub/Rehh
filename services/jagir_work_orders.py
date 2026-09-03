from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from database import Database
from services.dismantle_orders import capture_dismantle_order

TARGET_GROUP = "WORK ORDER JAGIR"
BLOCK_SPLIT_RE = re.compile(r"\n\s*==\s*\n", re.IGNORECASE)
FIELD_RE = re.compile(r"^\s*([^:]+?)\s*:\s*(.*?)\s*$")
TAG_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{4,32})")
SERVICE_RE = re.compile(r"\d{6,}")
EMPTY = {"", "-", "N/A", "NA", "NONE", "NULL", "NO TIKET", "****"}


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _norm_username(value: object) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(value or "").strip().lower().lstrip("@"))


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS technician_usernames (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT NOT NULL DEFAULT '',
            nik TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_technician_usernames_username ON technician_usernames(username) WHERE username != ''")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jagir_work_orders (
            service_number TEXT PRIMARY KEY,
            ticket_id TEXT NOT NULL DEFAULT 'MANUAL',
            order_type TEXT NOT NULL DEFAULT '',
            customer_name TEXT NOT NULL DEFAULT '',
            customer_phone TEXT NOT NULL DEFAULT '',
            address TEXT NOT NULL DEFAULT '',
            odp_name TEXT NOT NULL DEFAULT '',
            package TEXT NOT NULL DEFAULT '',
            onu_rx TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            assigned_username TEXT NOT NULL DEFAULT '',
            assigned_telegram_id INTEGER,
            assigned_nik TEXT NOT NULL DEFAULT '',
            assigned_name TEXT NOT NULL DEFAULT '',
            sto TEXT NOT NULL DEFAULT 'JGR',
            area TEXT NOT NULL DEFAULT 'JAGIR',
            status TEXT NOT NULL DEFAULT 'OPEN',
            source_chat_id INTEGER,
            source_message_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _remember_username_sync(database_path, telegram_id: int, username: str, nik: str, name: str) -> None:
    username = _norm_username(username)
    if not username:
        return
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    with sqlite3.connect(database_path) as conn:
        _ensure_tables(conn)
        conn.execute("DELETE FROM technician_usernames WHERE username=? AND telegram_id<>?", (username, telegram_id))
        conn.execute(
            """
            INSERT INTO technician_usernames(telegram_id, username, nik, name, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username=excluded.username, nik=excluded.nik, name=excluded.name, updated_at=excluded.updated_at
            """,
            (telegram_id, username, nik, name, now),
        )
        conn.commit()


async def remember_technician_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not user.username:
        return
    db: Database = context.application.bot_data["db"]
    registered = await db.get_technician(user.id)
    if registered is None:
        return
    await asyncio.to_thread(
        _remember_username_sync,
        db.db_path,
        user.id,
        user.username,
        registered.nik,
        registered.name,
    )


def _resolve_tag(conn: sqlite3.Connection, username: str) -> tuple[int | None, str, str]:
    username = _norm_username(username)
    row = conn.execute(
        "SELECT telegram_id, nik, name FROM technician_usernames WHERE username=?",
        (username,),
    ).fetchone()
    if row:
        return int(row[0]), str(row[1] or ""), str(row[2] or "")

    candidates = conn.execute("SELECT telegram_id, nik, name FROM technicians WHERE TRIM(name) != ''").fetchall()
    compact_tag = re.sub(r"[^a-z0-9]", "", username)
    exact = []
    for telegram_id, nik, name in candidates:
        compact_name = re.sub(r"[^a-z0-9]", "", str(name or "").lower())
        if compact_name == compact_tag:
            exact.append((telegram_id, nik, name))
    if len(exact) == 1:
        item = exact[0]
        return int(item[0]), str(item[1] or ""), str(item[2] or "")
    return None, "", ""


def _parse_block(block: str) -> dict | None:
    fields: dict[str, str] = {}
    for raw in block.strip().strip('"').splitlines():
        line = raw.strip().strip('"')
        if not line or line == "****":
            continue
        match = FIELD_RE.match(line)
        if match:
            fields[_norm(match.group(1))] = match.group(2).strip().strip('"')

    raw_service = fields.get("SERVICE NO", "") or fields.get("NO SERVICE", "") or fields.get("INET", "")
    service_match = SERVICE_RE.search(raw_service)
    if not service_match:
        return None

    raw_ticket = fields.get("TICKET", "")
    ticket = raw_ticket.strip().strip("|")
    if _norm(ticket) in EMPTY:
        ticket = "MANUAL"

    name_cp = fields.get("NAMA / CP", "").strip()
    customer_name = ""
    customer_phone = ""
    if name_cp and _norm(name_cp) not in EMPTY:
        parts = [part.strip() for part in re.split(r"\s*[|/]\s*", name_cp, maxsplit=1)]
        if parts:
            customer_name = parts[0]
        if len(parts) > 1:
            customer_phone = parts[1]

    speed = fields.get("SPEED_MB", "") or fields.get("SPEED MB", "")
    package = f"{speed} Mbps" if speed and "MBPS" not in _norm(speed) else speed
    return {
        "service_number": service_match.group(0),
        "ticket_id": ticket or "MANUAL",
        "order_type": fields.get("TYPE", ""),
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "address": fields.get("ALAMAT", ""),
        "odp_name": fields.get("NAMA ODP", ""),
        "package": package,
        "onu_rx": fields.get("REDAMAN", ""),
        "description": fields.get("KETERANGAN", ""),
    }


def _store_batch(database_path, text: str, chat_id: int, message_id: int) -> tuple[int, str]:
    tags = TAG_RE.findall(text)
    assigned_username = _norm_username(tags[-1]) if tags else ""
    if not assigned_username:
        return 0, "TAG teknisi (@username) tidak ditemukan."

    blocks = BLOCK_SPLIT_RE.split(text)
    orders = [item for item in (_parse_block(block) for block in blocks) if item]
    if not orders:
        return 0, "Tidak ada SERVICE NO yang terbaca."

    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    with sqlite3.connect(database_path) as conn:
        _ensure_tables(conn)
        assigned_telegram_id, assigned_nik, assigned_name = _resolve_tag(conn, assigned_username)
        for item in orders:
            conn.execute(
                """
                INSERT INTO jagir_work_orders(
                    service_number, ticket_id, order_type, customer_name, customer_phone,
                    address, odp_name, package, onu_rx, description, assigned_username,
                    assigned_telegram_id, assigned_nik, assigned_name, sto, area, status,
                    source_chat_id, source_message_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'JGR', 'JAGIR', 'OPEN', ?, ?, ?, ?)
                ON CONFLICT(service_number) DO UPDATE SET
                    ticket_id=excluded.ticket_id, order_type=excluded.order_type,
                    customer_name=excluded.customer_name, customer_phone=excluded.customer_phone,
                    address=excluded.address, odp_name=excluded.odp_name, package=excluded.package,
                    onu_rx=excluded.onu_rx, description=excluded.description,
                    assigned_username=excluded.assigned_username,
                    assigned_telegram_id=excluded.assigned_telegram_id,
                    assigned_nik=excluded.assigned_nik, assigned_name=excluded.assigned_name,
                    sto='JGR', area='JAGIR', status='OPEN',
                    source_chat_id=excluded.source_chat_id, source_message_id=excluded.source_message_id,
                    updated_at=excluded.updated_at
                """,
                (
                    item["service_number"], item["ticket_id"], item["order_type"],
                    item["customer_name"], item["customer_phone"], item["address"],
                    item["odp_name"], item["package"], item["onu_rx"], item["description"],
                    assigned_username, assigned_telegram_id, assigned_nik, assigned_name,
                    chat_id, message_id, now, now,
                ),
            )
        conn.commit()
    owner = assigned_name.upper() if assigned_name else f"@{assigned_username}"
    return len(orders), owner


async def capture_jagir_work_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Handler ini sudah berada di jalur awal semua pesan grup. Gunakan jalur yang sama
    # untuk menangkap WO dismantling dari grup Replacement NTE MANYAR.
    await capture_dismantle_order(update, context)

    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return
    if _norm(chat.title) != TARGET_GROUP:
        return
    text = (message.text or message.caption or "").strip()
    if "SERVICE NO" not in _norm(text) or "==" not in text:
        return

    db: Database = context.application.bot_data["db"]
    try:
        total, owner = await asyncio.to_thread(_store_batch, db.db_path, text, chat.id, message.message_id)
    except Exception:
        logging.exception("Gagal menyimpan WORK ORDER JAGIR")
        return
    if total:
        await message.reply_text(f"✅ {total} WO JAGIR tersimpan\n👷 Assign: {owner}\n🏢 STO: JGR")
    else:
        await message.reply_text(f"⚠️ WO JAGIR belum tersimpan: {owner}")
