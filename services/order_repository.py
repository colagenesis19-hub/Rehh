from __future__ import annotations

import asyncio
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass(frozen=True)
class Order:
    id: int
    ticket_id: str
    service_number: str
    voip_number: str
    customer_name: str
    address: str
    customer_phone: str
    old_sn: str
    new_sn: str
    ont_type: str
    sto: str
    valins_id: str
    result: str
    config_description: str
    report_description: str
    assigned_technician: str
    source_file: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": str(self.id),
            "ticket_id": self.ticket_id,
            "service_number": self.service_number,
            "internet_number": self.service_number,
            "voip": self.voip_number,
            "voip_number": self.voip_number,
            "customer_name": self.customer_name,
            "address": self.address,
            "customer_phone": self.customer_phone,
            "old_sn": self.old_sn,
            "new_sn": self.new_sn,
            "ont_type": self.ont_type,
            "sto": self.sto,
            "valins_id": self.valins_id,
            "result": self.result,
            "config_description": self.config_description,
            "report_description": self.report_description,
            "assigned_technician": self.assigned_technician,
        }


class OrderRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    @contextmanager
    def connection(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticket_id TEXT NOT NULL DEFAULT '',
                        service_number TEXT NOT NULL DEFAULT '',
                        voip_number TEXT NOT NULL DEFAULT '',
                        customer_name TEXT NOT NULL DEFAULT '',
                        address TEXT NOT NULL DEFAULT '',
                        customer_phone TEXT NOT NULL DEFAULT '',
                        old_sn TEXT NOT NULL DEFAULT '',
                        new_sn TEXT NOT NULL DEFAULT '',
                        ont_type TEXT NOT NULL DEFAULT '',
                        sto TEXT NOT NULL DEFAULT '',
                        valins_id TEXT NOT NULL DEFAULT '',
                        result TEXT NOT NULL DEFAULT '',
                        config_description TEXT NOT NULL DEFAULT '',
                        report_description TEXT NOT NULL DEFAULT '',
                        assigned_technician TEXT NOT NULL DEFAULT '',
                        source_file TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_ticket_service
                    ON orders(ticket_id, service_number);
                    CREATE INDEX IF NOT EXISTS idx_orders_service ON orders(service_number);
                    CREATE INDEX IF NOT EXISTS idx_orders_ticket ON orders(ticket_id);
                    CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_name);
                    """
                )
                columns = {
                    row["name"]
                    for row in conn.execute("PRAGMA table_info(orders)").fetchall()
                }
                if "assigned_technician" not in columns:
                    conn.execute(
                        "ALTER TABLE orders ADD COLUMN assigned_technician TEXT NOT NULL DEFAULT ''"
                    )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_orders_assigned ON orders(assigned_technician)"
                )

    @staticmethod
    def _row_to_order(row: sqlite3.Row | None) -> Order | None:
        return Order(**dict(row)) if row else None

    async def upsert(self, data: dict[str, Any], source_file: str = "") -> str:
        normalized = {
            "ticket_id": str(data.get("ticket_id") or "").strip(),
            "service_number": str(
                data.get("service_number") or data.get("internet_number") or ""
            ).strip(),
            "voip_number": str(data.get("voip_number") or data.get("voip") or "").strip(),
            "customer_name": str(data.get("customer_name") or "").strip(),
            "address": str(data.get("address") or "").strip(),
            "customer_phone": str(data.get("customer_phone") or "").strip(),
            "old_sn": str(data.get("old_sn") or "").strip().upper(),
            "new_sn": str(data.get("new_sn") or "").strip().upper(),
            "ont_type": str(data.get("ont_type") or "").strip().upper(),
            "sto": str(data.get("sto") or "").strip().upper(),
            "valins_id": str(data.get("valins_id") or "").strip(),
            "result": str(data.get("result") or "").strip(),
            "config_description": str(data.get("config_description") or "").strip(),
            "report_description": str(data.get("report_description") or "").strip(),
            "assigned_technician": str(data.get("assigned_technician") or "").strip(),
            "source_file": source_file.strip(),
        }

        if not normalized["ticket_id"] and not normalized["service_number"]:
            raise ValueError("Order harus memiliki TIKET ID atau NO SERVICE.")

        now = utc_now()
        async with self._lock:
            with self.connection() as conn:
                ticket_id = normalized["ticket_id"]
                service_number = normalized["service_number"]
                is_manual_ticket = ticket_id.strip().upper() in {
                    "", "-", "MANUAL", "N/A", "NA", "NONE"
                }

                if is_manual_ticket:
                    existing = conn.execute(
                        """
                        SELECT id FROM orders
                        WHERE service_number != '' AND service_number = ?
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (service_number,),
                    ).fetchone()
                else:
                    existing = conn.execute(
                        """
                        SELECT id FROM orders
                        WHERE (ticket_id != '' AND ticket_id = ?)
                           OR (service_number != '' AND service_number = ?)
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (ticket_id, service_number),
                    ).fetchone()

                if existing:
                    assignments = ", ".join(
                        f"{key} = CASE WHEN ? != '' THEN ? ELSE {key} END"
                        for key in normalized
                    )
                    params: list[Any] = []
                    for value in normalized.values():
                        params.extend([value, value])
                    params.extend([now, existing["id"]])
                    conn.execute(
                        f"UPDATE orders SET {assignments}, updated_at = ? WHERE id = ?",
                        params,
                    )
                    return "updated"

                conn.execute(
                    """
                    INSERT INTO orders (
                        ticket_id, service_number, voip_number, customer_name,
                        address, customer_phone, old_sn, new_sn, ont_type, sto,
                        valins_id, result, config_description, report_description,
                        assigned_technician, source_file, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized["ticket_id"], normalized["service_number"],
                        normalized["voip_number"], normalized["customer_name"],
                        normalized["address"], normalized["customer_phone"],
                        normalized["old_sn"], normalized["new_sn"],
                        normalized["ont_type"], normalized["sto"],
                        normalized["valins_id"], normalized["result"],
                        normalized["config_description"], normalized["report_description"],
                        normalized["assigned_technician"], normalized["source_file"],
                        now, now,
                    ),
                )
                return "inserted"

    async def get(self, order_id: int) -> Order | None:
        async with self._lock:
            with self.connection() as conn:
                row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        return self._row_to_order(row)

    async def search(self, query: str, limit: int = 10) -> list[Order]:
        query = query.strip()
        like = f"%{query}%"
        async with self._lock:
            with self.connection() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM orders
                    WHERE ticket_id LIKE ? OR service_number LIKE ? OR customer_name LIKE ?
                       OR address LIKE ? OR customer_phone LIKE ? OR old_sn LIKE ? OR new_sn LIKE ?
                    ORDER BY CASE WHEN ticket_id = ? THEN 0 WHEN service_number = ? THEN 1 ELSE 2 END,
                             updated_at DESC
                    LIMIT ?
                    """,
                    (like, like, like, like, like, like, like, query, query, limit),
                ).fetchall()
        return [Order(**dict(row)) for row in rows]

    async def list_for_technician(
        self, technician_name: str, status: str = "all", limit: int = 50
    ) -> list[Order]:
        name = technician_name.strip()
        status = status.lower().strip()
        status_sql = ""
        params: list[Any] = [name]
        if status == "open":
            status_sql = "AND UPPER(TRIM(result)) NOT IN ('CLOSE', 'CLOSED', 'SELESAI', 'DONE')"
        elif status == "close":
            status_sql = "AND UPPER(TRIM(result)) IN ('CLOSE', 'CLOSED', 'SELESAI', 'DONE')"
        params.append(limit)
        async with self._lock:
            with self.connection() as conn:
                rows = conn.execute(
                    f"""
                    SELECT * FROM orders
                    WHERE LOWER(TRIM(assigned_technician)) = LOWER(TRIM(?))
                    {status_sql}
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
        return [Order(**dict(row)) for row in rows]

    async def technician_stats(self, technician_name: str) -> dict[str, int]:
        async with self._lock:
            with self.connection() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS total,
                           SUM(CASE WHEN UPPER(TRIM(result)) IN ('CLOSE','CLOSED','SELESAI','DONE') THEN 1 ELSE 0 END) AS closed
                    FROM orders
                    WHERE LOWER(TRIM(assigned_technician)) = LOWER(TRIM(?))
                    """,
                    (technician_name.strip(),),
                ).fetchone()
        total = int(row["total"] or 0)
        closed = int(row["closed"] or 0)
        return {"total": total, "open": total - closed, "close": closed}

    async def update_fields(self, order_id: int, fields: dict[str, str]) -> Order:
        allowed = {
            "ticket_id", "service_number", "voip_number", "customer_name",
            "address", "customer_phone", "old_sn", "new_sn", "ont_type",
            "sto", "valins_id", "result", "config_description",
            "report_description", "assigned_technician",
        }
        cleaned: dict[str, str] = {}
        for key, raw_value in fields.items():
            if key not in allowed:
                continue
            value = str(raw_value or "").strip()
            if key in {"old_sn", "new_sn", "ont_type", "sto"}:
                value = value.upper()
            cleaned[key] = value

        if not cleaned:
            order = await self.get(order_id)
            if order is None:
                raise ValueError("Order tidak ditemukan.")
            return order

        assignments = ", ".join(f"{key} = ?" for key in cleaned)
        values = list(cleaned.values())
        values.extend([utc_now(), order_id])

        async with self._lock:
            with self.connection() as conn:
                conn.execute(
                    f"UPDATE orders SET {assignments}, updated_at = ? WHERE id = ?",
                    values,
                )
                row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

        order = self._row_to_order(row)
        if order is None:
            raise ValueError("Order tidak ditemukan.")
        return order
