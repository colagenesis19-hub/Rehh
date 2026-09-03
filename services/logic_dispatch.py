from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from database import Database


DEFAULT_LOGIC_GROUP_TITLE = "LOGIC REPLACEMENT ONT"
LOGIC_GROUP_SETTING_KEY = "logic_group_id"


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _normalized_title(value: str | None) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _target_group_title() -> str:
    return _normalized_title(os.getenv("LOGIC_GROUP_TITLE", DEFAULT_LOGIC_GROUP_TITLE))


def _env_logic_group_id() -> int | None:
    raw = os.getenv("LOGIC_GROUP_ID", "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logging.error("LOGIC_GROUP_ID tidak valid: %r", raw)
        return None


def _ensure_logic_tables(conn: sqlite3.Connection) -> None:
    # Gunakan tabel khusus agar tidak bentrok dengan tabel bot_settings lama
    # yang sudah dipakai fitur lain dengan skema berbeda.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS logic_bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS logic_config_dispatches (
            service_number TEXT PRIMARY KEY,
            sent_at TEXT NOT NULL
        )
        """
    )


def _save_logic_group_id(database_path: Path, group_id: int) -> None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_logic_tables(conn)
        conn.execute(
            """
            INSERT INTO logic_bot_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (LOGIC_GROUP_SETTING_KEY, str(group_id), _utc_now()),
        )
        conn.commit()
    finally:
        conn.close()


def _stored_logic_group_id(database_path: Path) -> int | None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_logic_tables(conn)
        row = conn.execute(
            "SELECT value FROM logic_bot_settings WHERE key = ?",
            (LOGIC_GROUP_SETTING_KEY,),
        ).fetchone()
        conn.commit()
    finally:
        conn.close()

    if not row:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError):
        logging.error("logic_group_id tersimpan tidak valid: %r", row[0])
        return None


def _claim_service(database_path: Path, service_number: str) -> bool:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_logic_tables(conn)
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO logic_config_dispatches (service_number, sent_at)
            VALUES (?, ?)
            """,
            (service_number, _utc_now()),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def _release_service(database_path: Path, service_number: str) -> None:
    conn = sqlite3.connect(database_path)
    try:
        _ensure_logic_tables(conn)
        conn.execute(
            "DELETE FROM logic_config_dispatches WHERE service_number = ?",
            (service_number,),
        )
        conn.commit()
    finally:
        conn.close()


async def detect_logic_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deteksi grup Logic dari pesan masuk dan simpan chat ID tanpa membalas di grup."""
    chat = update.effective_chat
    if not chat or chat.type not in {"group", "supergroup"}:
        return
    if _normalized_title(chat.title) != _target_group_title():
        return

    db: Database = context.application.bot_data["db"]
    current = await asyncio.to_thread(_stored_logic_group_id, db.db_path)
    if current == chat.id:
        return

    await asyncio.to_thread(_save_logic_group_id, db.db_path, chat.id)
    logging.info("Grup Logic terdeteksi otomatis: title=%s chat_id=%s", chat.title, chat.id)


async def ignore_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sengaja kosong: grup tidak dipakai untuk interaksi bot."""
    return None


async def send_config_to_logic_once(
    context: ContextTypes.DEFAULT_TYPE,
    db: Database,
    service_number: str,
    config_text: str,
) -> bool:
    """Kirim CONFIG murni ke grup Logic sekali untuk setiap NO SERVICE / INET."""
    group_id = _env_logic_group_id()
    if group_id is None:
        group_id = await asyncio.to_thread(_stored_logic_group_id, db.db_path)
    if group_id is None:
        logging.warning(
            "CONFIG belum dikirim: grup Logic belum terdeteksi. Target title=%s",
            _target_group_title(),
        )
        return False

    service = str(service_number or "").strip()
    if not service:
        logging.warning("CONFIG tidak dikirim ke Logic karena NO SERVICE / INET kosong")
        return False

    claimed = await asyncio.to_thread(_claim_service, db.db_path, service)
    if not claimed:
        logging.info("CONFIG INET %s sudah pernah dikirim ke Logic; dilewati", service)
        return False

    try:
        # Grup Logic hanya menerima isi CONFIG, tanpa header/status/pesan tambahan.
        await context.bot.send_message(chat_id=group_id, text=config_text)
        return True
    except Exception:
        # Jika Telegram gagal menerima pesan, izinkan percobaan berikutnya untuk INET yang sama.
        await asyncio.to_thread(_release_service, db.db_path, service)
        logging.exception("Gagal mengirim CONFIG INET %s ke grup Logic", service)
        return False
