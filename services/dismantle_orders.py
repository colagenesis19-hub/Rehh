from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SIGNATURE = "OPEN WO DISMANTLING NTE CRASH"
TARGET_GROUP_FRAGMENT = "PLACEMENT NTE MANYAR"

SEED_ORDERS = [
    ("M****", "MULYOREJO TENGAH 1 NO 26 SURABAYA Jalan Ngagel Surabaya 60246 Surabaya Indonesia", "152303278616", "JAWA TIMUR", "26050138", "THOMAS GUSTIAN BAGYO", "ThomasGustian"),
    ("S****", "Mulyorejo Tengah 1/30 Jalan Dokter Ir. Haji Soekarno Surabaya 60115 Surabaya Indonesia", "152303277738", "JAWA TIMUR", "26050138", "THOMAS GUSTIAN BAGYO", "ThomasGustian"),
    ("B*******", "Mulyorejo Tengah Gang V No. 14 Mulyorejo Tengah Gang V Surabaya 00000 Surabaya Indonesia", "152303272481", "JAWA TIMUR", "26050138", "THOMAS GUSTIAN BAGYO", "ThomasGustian"),
    ("D****", "Mulyorejo Tengah Gang V Surabaya", "152303271125", "JAWA TIMUR", "26050138", "THOMAS GUSTIAN BAGYO", "ThomasGustian"),
    ("N****", "mulyorejo tengah gg 1 no 16", "152303272779", "JAWA TIMUR", "26050138", "THOMAS GUSTIAN BAGYO", "ThomasGustian"),
    ("M********", "MULYOREJO TENGAH NO 51 SURABAYA", "152303279918", "JAWA TIMUR", "26050138", "THOMAS GUSTIAN BAGYO", "ThomasGustian"),
    ("*****", "MULYOREJO TENGAH NO.37", "152303277003", "JAWA TIMUR", "26050138", "THOMAS GUSTIAN BAGYO", "ThomasGustian"),

    ("H*****", "RAYA SEMAMPIR NO.2 (KEDAI PYJAH", "152303279073", "JAWA TIMUR", "26970105", "VICO INDIRA PURNOMO", ""),
    ("ME*************", "RAYA SEMAMPIR NO.95 /", "152303270561", "JAWA TIMUR", "26970105", "VICO INDIRA PURNOMO", "Vico_ip"),
    ("M********", "Raya Semolowaru 151", "152303271464", "JAWA TIMUR", "26970105", "VICO INDIRA PURNOMO", "Vico_ip"),
    ("M********", "RAYA SEMOLOWARU NO 89", "152303279530", "JAWA TIMUR", "26970105", "VICO INDIRA PURNOMO", "Vico_ip"),
    ("*****", "RAYA SEMOLOWARU NO.56", "152303278994", "JAWA TIMUR", "26970105", "VICO INDIRA PURNOMO", "Vico_ip"),
    ("C*********", "RAYA SUTOREJO NO.6, MULYOREJO", "152303279420", "JAWA TIMUR", "26970105", "VICO INDIRA PURNOMO", "Vico_ip"),
    ("F*****", "Ruko 21 klampis blok F 19", "152303272328", "JAWA TIMUR", "26970105", "VICO INDIRA PURNOMO", "Vico_ip"),
    ("P******", "RUKO KLAMPIS 21 F-2", "152303201639", "JAWA TIMUR", "26970105", "VICO INDIRA PURNOMO", "Vico_ip"),

    ("L*********", "SEMAMPIR AWS 2 NO 17 B JALAN MEDOKAN SEMAMPIR", "152303277849", "JAWA TIMUR", "26880016", "SENDRY FIRMANSYAH", "Msbajoel"),
    ("LU*************", "Semampir barat 2 no 26", "152303277762", "JAWA TIMUR", "26880016", "SENDRY FIRMANSYAH", "Msbajoel"),
    ("R*****", "SEMAMPIR KELURAHAN NO 12", "152303279317", "JAWA TIMUR", "26880016", "SENDRY FIRMANSYAH", "Msbajoel"),
    ("N****", "semampir tengah 2 no 41A belakang Jalan Dokter Ir. Haji Soekarno Surabaya 60115 Surabaya Indonesia", "152303272655", "JAWA TIMUR", "26880016", "SENDRY FIRMANSYAH", "Msbajoel"),
    ("A*****", "SEMAMPIR TENGAH 5A NO 19 SURABAYA", "152303270978", "JAWA TIMUR", "26880016", "SENDRY FIRMANSYAH", "Msbajoel"),
    ("N****", "Semampir tengah 8 blok E no 4", "152303271755", "JAWA TIMUR", "26880016", "SENDRY FIRMANSYAH", "Msbajoel"),
    ("C*****", "SEMAMPIR TENGAH GANG 6A NO 22", "152303280382", "JAWA TIMUR", "26880016", "SENDRY FIRMANSYAH", "Msbajoel"),
    ("W*****", "SEMAMPIR TENGAH VIII C NO.13", "152303203053", "JAWA TIMUR", "26880016", "SENDRY FIRMANSYAH", "Msbajoel"),
    ("G*******", "Semampir Utara NO.20", "152303278337", "JAWA TIMUR", "26880016", "SENDRY FIRMANSYAH", "Msbajoel"),
    ("*****", "semanpir selatan 3a/71 Jalan Semolowaru Elok Surabaya 60119 Surabaya Indonesia", "152303277832", "JAWA TIMUR", "26880016", "SENDRY FIRMANSYAH", "Msbajoel"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_schema_sync(db_path: Path | str) -> None:
    with _connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dismantle_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_number TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                customer_phone TEXT NOT NULL DEFAULT '',
                assigned_nik TEXT NOT NULL DEFAULT '',
                assigned_name TEXT NOT NULL DEFAULT '',
                assigned_username TEXT NOT NULL DEFAULT '',
                assigned_telegram_id INTEGER,
                source_chat_id INTEGER,
                source_message_id INTEGER,
                status TEXT NOT NULL DEFAULT 'OPEN',
                raw_source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_dismantle_assignee ON dismantle_orders(assigned_telegram_id, assigned_nik, status);
            CREATE INDEX IF NOT EXISTS idx_dismantle_completed ON dismantle_orders(completed_at);
            """
        )
        now = _utc_now()
        for name, address, inet, cp, nik, technician, username in SEED_ORDERS:
            telegram_id = _resolve_telegram_id(conn, nik, username)
            conn.execute(
                """
                INSERT OR IGNORE INTO dismantle_orders (
                    service_number, customer_name, address, customer_phone,
                    assigned_nik, assigned_name, assigned_username, assigned_telegram_id,
                    status, raw_source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', 'SEED OSA MYR', ?, ?)
                """,
                (inet, name, address, cp, nik, technician, username, telegram_id, now, now),
            )


async def initialize_dismantle_orders(db_path: Path | str) -> None:
    await asyncio.to_thread(_ensure_schema_sync, db_path)


def _field(block: str, label: str) -> str:
    m = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.*?)\s*$", block)
    return (m.group(1).strip() if m else "")


def parse_dismantle_message(text: str) -> list[dict[str, str]]:
    if SIGNATURE not in (text or "").upper():
        return []
    blocks = re.split(rf"(?i)(?={re.escape(SIGNATURE)})", text)
    result: list[dict[str, str]] = []
    for block in blocks:
        if SIGNATURE not in block.upper():
            continue
        service = re.sub(r"\D", "", _field(block, "NO. INET") or _field(block, "NO INET"))
        if not service:
            continue
        petugas = _field(block, "PETUGAS 1")
        nik = ""
        name = ""
        if "|" in petugas:
            nik, name = [part.strip() for part in petugas.split("|", 1)]
        else:
            name = petugas.strip()
        username = _field(block, "USERNAME").lstrip("@").strip()
        result.append(
            {
                "service_number": service,
                "customer_name": _field(block, "NAMA"),
                "address": _field(block, "ALAMAT"),
                "customer_phone": _field(block, "CP PELANGGAN"),
                "assigned_nik": re.sub(r"\D", "", nik),
                "assigned_name": name,
                "assigned_username": username,
                "raw_source": block.strip(),
            }
        )
    return result


def _resolve_telegram_id(conn: sqlite3.Connection, nik: str, username: str) -> int | None:
    if nik:
        row = conn.execute("SELECT telegram_id FROM technicians WHERE TRIM(nik)=? LIMIT 1", (nik,)).fetchone()
        if row:
            return int(row[0])
    if username:
        try:
            row = conn.execute(
                "SELECT telegram_id FROM technician_usernames WHERE LOWER(TRIM(username))=? LIMIT 1",
                (username.lower(),),
            ).fetchone()
            if row:
                return int(row[0])
        except sqlite3.OperationalError:
            pass
    return None


def _save_orders_sync(db_path: Path | str, orders: list[dict[str, str]], chat_id: int | None, message_id: int | None) -> int:
    _ensure_schema_sync(db_path)
    now = _utc_now()
    saved = 0
    with _connect(db_path) as conn:
        for order in orders:
            telegram_id = _resolve_telegram_id(conn, order["assigned_nik"], order["assigned_username"])
            conn.execute(
                """
                INSERT INTO dismantle_orders (
                    service_number, customer_name, address, customer_phone,
                    assigned_nik, assigned_name, assigned_username, assigned_telegram_id,
                    source_chat_id, source_message_id, status, raw_source, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?)
                ON CONFLICT(service_number) DO UPDATE SET
                    customer_name=excluded.customer_name,
                    address=excluded.address,
                    customer_phone=excluded.customer_phone,
                    assigned_nik=excluded.assigned_nik,
                    assigned_name=excluded.assigned_name,
                    assigned_username=excluded.assigned_username,
                    assigned_telegram_id=COALESCE(excluded.assigned_telegram_id, dismantle_orders.assigned_telegram_id),
                    source_chat_id=excluded.source_chat_id,
                    source_message_id=excluded.source_message_id,
                    raw_source=excluded.raw_source,
                    updated_at=excluded.updated_at
                """,
                (
                    order["service_number"], order["customer_name"], order["address"], order["customer_phone"],
                    order["assigned_nik"], order["assigned_name"], order["assigned_username"], telegram_id,
                    chat_id, message_id, order["raw_source"], now, now,
                ),
            )
            saved += 1
    return saved


def _normalize_group_title(title: str) -> str:
    return " ".join((title or "").upper().split())


async def capture_dismantle_order(update, context) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if not chat or not message or chat.type not in {"group", "supergroup"}:
        return
    if TARGET_GROUP_FRAGMENT not in _normalize_group_title(chat.title or ""):
        return

    text = message.text or message.caption or ""
    orders = parse_dismantle_message(text)
    if not orders:
        return

    db_path = context.application.bot_data["settings"].database_path
    try:
        saved = await asyncio.to_thread(
            _save_orders_sync,
            db_path,
            orders,
            chat.id,
            message.message_id,
        )
        logging.info(
            "Captured dismantle work orders from %s: %s",
            chat.title,
            saved,
        )
    except Exception:
        logging.exception("Failed to capture dismantle work order")
