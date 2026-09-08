from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS injoko_close_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL DEFAULT '',
    technician_nik TEXT NOT NULL DEFAULT '',
    technician_name TEXT NOT NULL DEFAULT '',
    ticket_id TEXT NOT NULL DEFAULT '',
    service_number TEXT NOT NULL,
    old_sn TEXT NOT NULL DEFAULT '',
    new_sn TEXT NOT NULL DEFAULT '',
    valins_id TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT 'CLOSE',
    description TEXT NOT NULL DEFAULT '',
    source_message_id INTEGER,
    source_message_date TEXT,
    UNIQUE(service_number, report_date, source_message_id)
)
CREATE INDEX IF NOT EXISTS idx_injoko_close_service ON injoko_close_reports(service_number);
CREATE INDEX IF NOT EXISTS idx_injoko_close_ticket ON injoko_close_reports(ticket_id);
"""


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()


def _ticket(value: Any) -> str:
    value = _norm(value)
    if value.upper() in {"", "MANUAL", "N/A", "NA", "NONE", "-"}:
        return ""
    if re.match(r"^(?:NO INET|SN ONT LAMA|SN ONT BARU|VALINS ID)\s*[:：=]", value, re.I):
        return ""
    return value


def ensure_table(database_path: Path) -> None:
    with sqlite3.connect(database_path) as conn:
        conn.executescript(TABLE_SQL)


def import_reports(database_path: Path, reports: list[dict[str, Any]]) -> tuple[int, int]:
    ensure_table(database_path)
    inserted = 0
    skipped = 0
    with sqlite3.connect(database_path) as conn:
        for item in reports:
            service = re.sub(r"\D", "", _norm(item.get("service_number")))
            if len(service) < 8:
                skipped += 1
                continue
            result = _norm(item.get("result") or "CLOSE").upper()
            if result not in {"CLOSE", "CLOSED", "DONE", "SELESAI", "COMPLETED"}:
                skipped += 1
                continue
            ticket = _ticket(item.get("ticket_id"))
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO injoko_close_reports
                (report_date, technician_nik, technician_name, ticket_id, service_number,
                 old_sn, new_sn, valins_id, result, description, source_message_id, source_message_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _norm(item.get("report_date")),
                    _norm(item.get("nik")),
                    _norm(item.get("name")),
                    ticket,
                    service,
                    _norm(item.get("old_sn")),
                    _norm(item.get("new_sn")),
                    _norm(item.get("valins_id")),
                    "CLOSE",
                    _norm(item.get("description")),
                    item.get("source_message_id"),
                    _norm(item.get("source_message_date")),
                ),
            )
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1
    return inserted, skipped


def import_json_file(database_path: Path, json_path: Path) -> tuple[int, int]:
    payload = json.loads(json_path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        payload = payload.get("messages", [])
    if not isinstance(payload, list):
        raise ValueError("Format history INJOKO harus berupa array report atau export Telegram JSON.")
    return import_reports(database_path, payload)


def apply_to_local_orders(database_path: Path) -> int:
    ensure_table(database_path)
    updated = 0
    with sqlite3.connect(database_path) as conn:
        conn.execute("PRAGMA busy_timeout=5000")
        rows = conn.execute(
            """
            SELECT o.id
            FROM orders o
            WHERE (UPPER(TRIM(COALESCE(o.sto,'')))='IJK' OR UPPER(TRIM(COALESCE(o.source_file,''))) LIKE '%INJOKO%')
              AND EXISTS (
                  SELECT 1 FROM injoko_close_reports r
                  WHERE (r.service_number<>'' AND r.service_number=o.service_number)
                     OR (r.ticket_id<>'' AND UPPER(TRIM(r.ticket_id))=UPPER(TRIM(o.ticket_id)))
              )
              AND UPPER(TRIM(COALESCE(o.result,''))) NOT IN ('CLOSE','CLOSED','DONE','SELESAI','COMPLETED')
            """
        ).fetchall()
        for (order_id,) in rows:
            conn.execute("UPDATE orders SET result='CLOSE', updated_at=datetime('now') WHERE id=?", (order_id,))
            updated += 1
    return updated


def close_match(database_path: Path, ticket_id: str = "", service_number: str = "") -> dict[str, Any] | None:
    ensure_table(database_path)
    ticket = _ticket(ticket_id).upper()
    service = re.sub(r"\D", "", _norm(service_number))
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM injoko_close_reports
            WHERE (?<>'' AND service_number=?)
               OR (?<>'' AND UPPER(TRIM(ticket_id))=?)
            ORDER BY id DESC LIMIT 1
            """,
            (service, service, ticket, ticket),
        ).fetchone()
    return dict(row) if row else None
