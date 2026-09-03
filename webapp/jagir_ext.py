from __future__ import annotations

import re
import sqlite3
from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from webapp import server_ext as ext

base = ext.base
_original_load_my_open_orders = base.load_my_open_orders
_original_get = base.Handler.do_GET


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().upper().split())


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


def _wo_payload(row: sqlite3.Row) -> dict:
    return {
        "customer_name": str(row["customer_name"] or "-").strip() or "-",
        "ticket_id": str(row["ticket_id"] or "MANUAL").strip() or "MANUAL",
        "service_number": str(row["service_number"] or "-").strip() or "-",
        "customer_phone": str(row["customer_phone"] or "-").strip() or "-",
        "package": str(row["package"] or "-").strip() or "-",
        "onu_rx": str(row["onu_rx"] or "-").strip() or "-",
        "rca": str(row["description"] or "-").strip() or "-",
        "address": str(row["address"] or "-").strip() or "-",
        "voip_number": "",
        "old_sn": "",
        "new_sn": "",
        "ont_type": str(row["order_type"] or "").strip(),
        "sto": "JGR",
        "valins_id": "",
        "config_description": "",
        "report_description": str(row["description"] or "").strip(),
        "result": "",
        "assigned_technician": str(row["assigned_name"] or ("@" + str(row["assigned_username"] or ""))).strip() or "-",
        "assigned_username": str(row["assigned_username"] or "").strip(),
        "odp_name": str(row["odp_name"] or "").strip(),
        "area": "JAGIR",
        "source": "WORK ORDER JAGIR",
    }


def _my_jagir_rows(telegram_id: int, technician: dict) -> list[sqlite3.Row]:
    nik = str(technician.get("nik") or "").strip()
    name = _norm(technician.get("name"))
    with base.connect() as conn:
        _ensure_tables(conn)
        username_row = conn.execute(
            "SELECT username FROM technician_usernames WHERE telegram_id=?",
            (telegram_id,),
        ).fetchone()
        username = str(username_row["username"] or "").strip().lower() if username_row else ""
        rows = conn.execute(
            """
            SELECT * FROM jagir_work_orders
            WHERE UPPER(TRIM(status))='OPEN'
              AND (
                    assigned_telegram_id=?
                 OR (? != '' AND TRIM(assigned_nik)=?)
                 OR (? != '' AND UPPER(TRIM(assigned_name))=?)
                 OR (? != '' AND LOWER(TRIM(assigned_username))=?)
              )
            ORDER BY address ASC, service_number ASC
            """,
            (telegram_id, nik, nik, name, name, username, username),
        ).fetchall()
    return rows


def load_my_open_orders(telegram_id: int, force: bool = False) -> dict:
    payload = _original_load_my_open_orders(telegram_id, force=force)
    if not payload.get("ok"):
        return payload

    technician = payload.get("technician") or {}
    # Google Sheet adalah sumber MANYAR saja. Kunci semua order Sheet ke MYR.
    for area in payload.get("areas", []):
        for order in area.get("orders", []):
            order["sto"] = "MYR"
            order["source"] = "ORDER SHEET"

    wo_rows = _my_jagir_rows(telegram_id, technician)
    wo_orders = [_wo_payload(row) for row in wo_rows]
    if wo_orders:
        existing_area = next((item for item in payload.get("areas", []) if _norm(item.get("area")) == "JAGIR"), None)
        if existing_area is None:
            existing_area = {"area": "JAGIR", "open": 0, "close": 0, "update": 0, "orders": []}
            payload.setdefault("areas", []).append(existing_area)
        existing_services = {str(item.get("service_number") or "").strip() for item in existing_area.get("orders", [])}
        for order in wo_orders:
            if order["service_number"] not in existing_services:
                existing_area["orders"].append(order)
        existing_area["orders"].sort(key=lambda item: (str(item.get("address") or ""), str(item.get("service_number") or "")))
        existing_area["open"] = len(existing_area["orders"])

    payload["areas"] = sorted(payload.get("areas", []), key=lambda item: (0 if _norm(item.get("area")) != "JAGIR" else 1, _norm(item.get("area"))))
    payload["total_open"] = sum(len(item.get("orders", [])) for item in payload["areas"])
    payload["active_areas"] = len([item for item in payload["areas"] if item.get("orders")])
    payload["source"] = "ORDER SHEET (MYR) + WORK ORDER JAGIR (JGR)"
    return payload


def _search_jagir(query: str) -> list[dict]:
    wanted = re.sub(r"\D", "", str(query or ""))
    if len(wanted) < 6:
        return []
    with base.connect() as conn:
        _ensure_tables(conn)
        rows = conn.execute(
            """
            SELECT * FROM jagir_work_orders
            WHERE UPPER(TRIM(status))='OPEN' AND service_number LIKE ?
            ORDER BY CASE WHEN service_number=? THEN 0 ELSE 1 END, service_number
            LIMIT 20
            """,
            (f"%{wanted}%", wanted),
        ).fetchall()
    return [_wo_payload(row) for row in rows]


base.load_my_open_orders = load_my_open_orders


def do_get(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path == "/api/open-order-search":
        query = parse_qs(parsed.query)
        raw_id = (query.get("telegram_id") or [""])[0].strip()
        wanted = (query.get("q") or [""])[0].strip()
        if not raw_id.isdigit():
            self._send_json({"ok": False, "error": "telegram_id_required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            sheet_payload = ext.search_open_orders(int(raw_id), wanted, force=(query.get("force") or ["0"])[0] == "1")
            if not sheet_payload.get("ok"):
                self._send_json(sheet_payload, HTTPStatus.BAD_REQUEST)
                return
            merged: dict[str, dict] = {}
            for item in sheet_payload.get("orders", []):
                item["sto"] = "MYR"
                item["source"] = "ORDER SHEET"
                merged[str(item.get("service_number") or "")] = item
            for item in _search_jagir(wanted):
                merged[str(item.get("service_number") or "")] = item
            orders = list(merged.values())
            orders.sort(key=lambda item: (str(item.get("service_number") or "") != re.sub(r"\D", "", wanted), str(item.get("service_number") or "")))
            sheet_payload["orders"] = orders[:20]
            sheet_payload["count"] = len(sheet_payload["orders"])
            sheet_payload["source"] = "ORDER SHEET (MYR) + WORK ORDER JAGIR (JGR)"
            self._send_json(sheet_payload)
        except Exception as exc:
            print(f"[miniapp] gagal mencari order gabungan: {exc}")
            self._send_json({"ok": False, "error": "order_search_error", "message": "Gagal mencari order."}, HTTPStatus.INTERNAL_SERVER_ERROR)
        return
    _original_get(self)


base.Handler.do_GET = do_get
