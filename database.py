from __future__ import annotations

import asyncio
import csv
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass(frozen=True)
class Technician:
    id: int
    telegram_id: int
    nik: str
    name: str
    sto: str
    role: str
    created_at: str


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    @contextmanager
    def connection(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    async def initialize(self) -> None:
        async with self._lock:
            with self.connection() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS technicians (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER NOT NULL UNIQUE,
                        nik TEXT NOT NULL,
                        name TEXT NOT NULL,
                        sto TEXT NOT NULL DEFAULT '',
                        role TEXT NOT NULL DEFAULT 'TECHNICIAN',
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS histories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        technician_id INTEGER NOT NULL,
                        telegram_id INTEGER NOT NULL,
                        kind TEXT NOT NULL CHECK(kind IN ('CONFIG', 'REPORT', 'STO')),
                        ticket_id TEXT,
                        service_number TEXT,
                        old_sn TEXT,
                        new_sn TEXT,
                        ont_type TEXT,
                        sto TEXT,
                        valins_id TEXT,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (technician_id) REFERENCES technicians(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS ocr_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        technician_id INTEGER,
                        telegram_id INTEGER NOT NULL,
                        image_path TEXT NOT NULL,
                        raw_text TEXT NOT NULL,
                        serial_number TEXT,
                        model TEXT,
                        manufacturer TEXT,
                        confidence REAL NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (technician_id) REFERENCES technicians(id) ON DELETE SET NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_histories_telegram ON histories(telegram_id);
                    CREATE INDEX IF NOT EXISTS idx_histories_ticket ON histories(ticket_id);
                    CREATE INDEX IF NOT EXISTS idx_histories_service ON histories(service_number);
                    CREATE INDEX IF NOT EXISTS idx_histories_sn ON histories(old_sn, new_sn);
                    """
                )

                # Migrasi aman untuk database lama yang belum memiliki kolom STO/ROLE.
                columns = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(technicians)").fetchall()
                }
                if "sto" not in columns:
                    conn.execute("ALTER TABLE technicians ADD COLUMN sto TEXT NOT NULL DEFAULT ''")
                if "role" not in columns:
                    conn.execute("ALTER TABLE technicians ADD COLUMN role TEXT NOT NULL DEFAULT 'TECHNICIAN'")

                # Registrasi role yang sudah dikonfirmasi.
                conn.execute(
                    "UPDATE technicians SET role='HSA' WHERE TRIM(nik)='86240021'"
                )
                # INJOKO (IJK) starts with no technicians. Technicians are
                # registered by their own /start flow in the Telegram bot.
                # This one-time cleanup removes legacy IJK rows only; HSA is not
                # inserted into or treated as an IJK technician.
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS system_flags (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )"""
                )
                reset_key = "injoko_empty_technician_roster_v1"
                if not conn.execute("SELECT 1 FROM system_flags WHERE key=?", (reset_key,)).fetchone():
                    conn.execute("DELETE FROM technicians WHERE UPPER(TRIM(COALESCE(sto,'')))='IJK'")
                    conn.execute("INSERT INTO system_flags(key,value) VALUES (?,?)", (reset_key, utc_now()))

    async def get_technician(self, telegram_id: int) -> Technician | None:
        async with self._lock:
            with self.connection() as conn:
                row = conn.execute(
                    "SELECT * FROM technicians WHERE telegram_id = ?",
                    (telegram_id,),
                ).fetchone()
        return Technician(**dict(row)) if row else None

    async def create_technician(
        self,
        telegram_id: int,
        nik: str,
        name: str,
        sto: str,
    ) -> Technician:
        async with self._lock:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO technicians (telegram_id, nik, name, sto, role, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        telegram_id,
                        nik.strip(),
                        name.strip(),
                        sto.strip().upper(),
                        'HSA' if nik.strip() == '86240021' else 'TECHNICIAN',
                        utc_now(),
                    ),
                )
                row = conn.execute(
                    "SELECT * FROM technicians WHERE telegram_id = ?",
                    (telegram_id,),
                ).fetchone()
        return Technician(**dict(row))

    async def update_technician_sto(self, telegram_id: int, sto: str) -> Technician | None:
        normalized_sto = sto.strip().upper()
        async with self._lock:
            with self.connection() as conn:
                conn.execute(
                    "UPDATE technicians SET sto = ? WHERE telegram_id = ?",
                    (normalized_sto, telegram_id),
                )
                row = conn.execute(
                    "SELECT * FROM technicians WHERE telegram_id = ?",
                    (telegram_id,),
                ).fetchone()
        return Technician(**dict(row)) if row else None

    async def list_technicians(self) -> list[sqlite3.Row]:
        async with self._lock:
            with self.connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM technicians ORDER BY created_at DESC"
                ).fetchall()
        return rows

    async def delete_technician(self, telegram_id: int) -> bool:
        async with self._lock:
            with self.connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM technicians WHERE telegram_id = ?",
                    (telegram_id,),
                )
                return cursor.rowcount > 0

    async def save_history(self, technician: Technician, kind: str, data: dict[str, Any], content: str) -> int:
        async with self._lock:
            with self.connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO histories (
                        technician_id, telegram_id, kind, ticket_id, service_number,
                        old_sn, new_sn, ont_type, sto, valins_id, content, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        technician.id,
                        technician.telegram_id,
                        kind,
                        data.get("ticket_id"),
                        data.get("service_number") or data.get("internet_number"),
                        data.get("old_sn"),
                        data.get("new_sn"),
                        data.get("ont_type"),
                        data.get("sto"),
                        data.get("valins_id"),
                        content,
                        utc_now(),
                    ),
                )
                return int(cursor.lastrowid)

    async def list_history(self, telegram_id: int, limit: int = 10) -> list[sqlite3.Row]:
        async with self._lock:
            with self.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM histories
                    WHERE telegram_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (telegram_id, limit),
                ).fetchall()
        return rows

    async def search_history(self, telegram_id: int, query: str) -> list[sqlite3.Row]:
        like = f"%{query}%"
        async with self._lock:
            with self.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM histories
                    WHERE telegram_id = ?
                      AND (
                        ticket_id LIKE ? OR service_number LIKE ? OR old_sn LIKE ?
                        OR new_sn LIKE ? OR sto LIKE ? OR content LIKE ?
                      )
                    ORDER BY created_at DESC
                    LIMIT 25
                    """,
                    (telegram_id, like, like, like, like, like, like),
                ).fetchall()
        return rows

    async def delete_history(self, telegram_id: int, history_id: int) -> bool:
        async with self._lock:
            with self.connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM histories WHERE id = ? AND telegram_id = ?",
                    (history_id, telegram_id),
                )
                return cursor.rowcount > 0

    async def export_history_csv(self, telegram_id: int, output_path: Path) -> Path:
        async with self._lock:
            with self.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT id, kind, ticket_id, service_number, old_sn, new_sn,
                           ont_type, sto, valins_id, content, created_at
                    FROM histories
                    WHERE telegram_id = ?
                    ORDER BY created_at DESC
                    """,
                    (telegram_id,),
                ).fetchall()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(rows[0].keys() if rows else [
                "id", "kind", "ticket_id", "service_number", "old_sn", "new_sn",
                "ont_type", "sto", "valins_id", "content", "created_at",
            ])
            for row in rows:
                writer.writerow([row[key] for key in row.keys()])
        return output_path

    async def save_ocr_log(
        self,
        telegram_id: int,
        technician_id: int | None,
        image_path: str,
        raw_text: str,
        serial_number: str | None,
        model: str | None,
        manufacturer: str | None,
        confidence: float,
        status: str,
    ) -> None:
        async with self._lock:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO ocr_logs (
                        technician_id, telegram_id, image_path, raw_text, serial_number,
                        model, manufacturer, confidence, status, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        technician_id,
                        telegram_id,
                        image_path,
                        raw_text,
                        serial_number,
                        model,
                        manufacturer,
                        float(confidence),
                        status,
                        utc_now(),
                    ),
                )

    async def statistics(self) -> dict[str, int]:
        async with self._lock:
            with self.connection() as conn:
                users = conn.execute("SELECT COUNT(*) AS total FROM technicians").fetchone()["total"]
                histories = conn.execute("SELECT COUNT(*) AS total FROM histories").fetchone()["total"]
                ocr_failures = conn.execute(
                    "SELECT COUNT(*) AS total FROM ocr_logs WHERE status != 'success'"
                ).fetchone()["total"]
        return {"users": users, "histories": histories, "ocr_failures": ocr_failures}
