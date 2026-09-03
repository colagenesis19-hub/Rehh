from __future__ import annotations

import json
import mimetypes
import os
import re
import sqlite3
import sys
import threading
import time
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services import google_sheet_reference as sheet_ref

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "/app/database/bot.sqlite3"))
HOST = "0.0.0.0"
PORT = int(os.getenv("MINIAPP_PORT", "8080"))

MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
DAYS = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
CLOSED_STATUSES = {"CLOSE", "CLOSED", "SELESAI", "DONE", "COMPLETED"}
UPDATE_STATUSES = {"UPDATE", "UPDATED", "PROGRESS", "ON PROGRESS", "PENDING"}
AREA_ALIASES: dict[str, tuple[str, ...]] = {
    "KERTAJAYA": ("KERTAJAYA INDAH TIMUR", "KERTAJAYA INDAH", "KERTAJAYA"),
    "MULYOREJO": ("MULYOREJO",),
    "KEPUTIH": ("KEPUTIH",),
}
ADDRESS_PREFIXES = {
    "JL", "JLN", "JALAN", "GG", "GANG", "PERUM", "PERUMAHAN", "KOMP", "KOMPLEK",
    "KOMPLEKS", "KP", "KAMPUNG",
}

_sheet_cache: dict[str, sheet_ref.ReferenceStatus] = {}
_sheet_cache_time = 0.0
_sheet_cache_lock = threading.Lock()
SHEET_CACHE_SECONDS = 30


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def period_bounds(day: date) -> tuple[date, date]:
    days_since_friday = (day.weekday() - 4) % 7
    start = day - timedelta(days=days_since_friday)
    return start, start + timedelta(days=6)


def date_label(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def _norm_name(value: str) -> str:
    text = str(value or "").upper().strip()
    text = re.sub(r"^(?:NAME|NAMA)\s*[-:=]\s*", "", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return " ".join(text.split())


def _norm_nik(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper().strip())


def _technician_registry(conn: sqlite3.Connection) -> dict[str, dict]:
    by_name: dict[str, dict] = {}
    try:
        rows = conn.execute("SELECT nik, name, sto FROM technicians ORDER BY id ASC").fetchall()
    except sqlite3.OperationalError:
        return by_name
    for row in rows:
        item = {
            "nik": str(row["nik"] or "").strip(),
            "name": str(row["name"] or "").strip(),
            "sto": str(row["sto"] or "").strip().upper(),
        }
        key = _norm_name(item["name"])
        if key:
            by_name[key] = item
    return by_name


def _identity_for(row: sqlite3.Row, by_name: dict[str, dict]) -> dict:
    raw_nik = str(row["nik"] or "").strip()
    raw_name = str(row["name"] or "").strip()
    name_key = _norm_name(raw_name)
    if name_key:
        registered = by_name.get(name_key) or {}
        return {
            "key": f"NAME:{name_key}",
            "nik": str(registered.get("nik") or raw_nik).strip(),
            "name": str(registered.get("name") or raw_name or "-").strip(),
            "sto": str(registered.get("sto") or "").strip().upper(),
        }
    nik_key = _norm_nik(raw_nik)
    return {"key": f"NIK:{nik_key or raw_nik}", "nik": raw_nik, "name": raw_nik or "-", "sto": ""}


def area_condition(area: str) -> tuple[str, tuple[str, ...]]:
    area = area.upper().strip()
    if area == "JGR":
        return (
            "EXISTS (SELECT 1 FROM report_area_orders ra WHERE ra.service_number=r.service_number AND ra.period_start=r.period_start AND UPPER(TRIM(ra.sto_code))=?)",
            ("JGR",),
        )
    if area == "MYR":
        return (
            "(EXISTS (SELECT 1 FROM report_area_orders ra WHERE ra.service_number=r.service_number AND ra.period_start=r.period_start AND UPPER(TRIM(ra.sto_code))=?) OR (NOT EXISTS (SELECT 1 FROM report_area_orders ra0 WHERE ra0.service_number=r.service_number AND ra0.period_start=r.period_start) AND EXISTS (SELECT 1 FROM orders o WHERE o.service_number=r.service_number AND UPPER(TRIM(o.sto))=?)))",
            ("MYR", "MYR"),
        )
    return "1=1", ()


def time_condition(period: str, today: date) -> tuple[str, tuple[str, ...], str]:
    start, end = period_bounds(today)
    period = period.lower().strip()
    if period == "daily":
        return "substr(r.message_date,1,10)=?", (today.isoformat(),), date_label(today)
    if period == "weekly":
        return "r.period_start=?", (start.isoformat(),), f"{date_label(start)} - {date_label(end)}"
    return "1=1", (), "Keseluruhan"


def _report_rows(conn: sqlite3.Connection, where_sql: str, params: tuple[str, ...]) -> list[sqlite3.Row]:
    return conn.execute(
        f"""
        SELECT r.technician_nik AS nik,
               r.technician_name AS name,
               r.service_number,
               r.period_start,
               r.message_date,
               UPPER(TRIM(COALESCE(NULLIF(ra.area_label,''), ra.sto_code, o.sto, ''))) AS area_label,
               UPPER(TRIM(COALESCE(ra.sto_code, o.sto, ''))) AS sto
        FROM report_group_orders r
        LEFT JOIN report_area_orders ra
          ON ra.service_number=r.service_number AND ra.period_start=r.period_start
        LEFT JOIN orders o ON o.id=(SELECT o2.id FROM orders o2 WHERE o2.service_number=r.service_number ORDER BY o2.id DESC LIMIT 1)
        WHERE {where_sql}
        """,
        params,
    ).fetchall()


def _group_rows(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict]:
    by_name = _technician_registry(conn)
    grouped: dict[str, dict] = {}
    for row in rows:
        identity = _identity_for(row, by_name)
        item = grouped.setdefault(identity["key"], {**identity, "services": set(), "area_label": "", "area_sto": "", "latest": "", "nik_candidates": []})
        service = str(row["service_number"] or "").strip()
        if service:
            item["services"].add(service)
        raw_nik = str(row["nik"] or "").strip()
        if raw_nik and raw_nik not in item["nik_candidates"]:
            item["nik_candidates"].append(raw_nik)
        message_date = str(row["message_date"] or "")
        if message_date >= item["latest"]:
            item["latest"] = message_date
            item["area_label"] = str(row["area_label"] or "")
            item["area_sto"] = str(row["sto"] or "")
    result: list[dict] = []
    for item in grouped.values():
        if not item["nik"] or item["nik"].upper().startswith(("NAME-", "TG-")):
            item["nik"] = next((v for v in item["nik_candidates"] if not v.upper().startswith(("NAME-", "TG-"))), item["nik_candidates"][0] if item["nik_candidates"] else item["nik"])
        result.append({"key": item["key"], "nik": item["nik"], "name": item["name"], "total": len(item["services"]), "area_label": item["area_label"], "sto": item["area_sto"] or item.get("sto", "")})
    result.sort(key=lambda item: (-item["total"], _norm_name(item["name"])))
    return result


def load_dashboard(area: str, period: str) -> dict:
    today = datetime.now().date()
    area_sql, area_params = area_condition(area)
    time_sql, time_params, label = time_condition(period, today)
    try:
        with connect() as conn:
            leaderboard = _group_rows(conn, _report_rows(conn, f"{time_sql} AND {area_sql}", (*time_params, *area_params)))
            trend = []
            week_start, _ = period_bounds(today)
            for offset in range(7):
                day = week_start + timedelta(days=offset)
                day_rows = _report_rows(conn, f"substr(r.message_date,1,10)=? AND {area_sql}", (day.isoformat(), *area_params))
                total = len({str(r["service_number"] or "").strip() for r in day_rows if str(r["service_number"] or "").strip()})
                trend.append({"date": day.isoformat(), "label": DAYS[day.weekday()], "total": total})
    except sqlite3.Error:
        leaderboard, trend = [], []
    total_close = sum(item["total"] for item in leaderboard)
    active = len(leaderboard)
    try:
        rca_summary = load_rca_summary(area)
    except Exception as exc:
        print(f"[miniapp] gagal membuat RCA summary: {exc}")
        rca_summary = {"total": 0, "items": [], "source": "Sheet + Grup Kendala"}
    return {
        "area": area.upper(), "period": period, "period_label": label,
        "summary": {"total_close": total_close, "active_technicians": active, "average_close": round(total_close / active, 1) if active else 0},
        "trend": trend, "leaderboard": leaderboard, "rca_summary": rca_summary,
    }


def _identity_members(conn: sqlite3.Connection, identity_key: str, area: str) -> tuple[dict, list[sqlite3.Row]]:
    area_sql, area_params = area_condition(area)
    rows = _report_rows(conn, area_sql, area_params)
    by_name = _technician_registry(conn)
    members: list[sqlite3.Row] = []
    chosen = {"key": identity_key, "nik": "", "name": "-", "sto": ""}
    for row in rows:
        identity = _identity_for(row, by_name)
        if identity["key"] == identity_key:
            members.append(row)
            chosen = identity
    return chosen, members


def load_technician(identity_key: str, area: str) -> dict:
    today = datetime.now().date()
    week_start, _ = period_bounds(today)
    try:
        with connect() as conn:
            identity, rows = _identity_members(conn, identity_key, area)
            all_services = {str(r["service_number"] or "").strip() for r in rows if str(r["service_number"] or "").strip()}
            daily = {str(r["service_number"] or "").strip() for r in rows if str(r["message_date"] or "")[:10] == today.isoformat() and str(r["service_number"] or "").strip()}
            weekly = {str(r["service_number"] or "").strip() for r in rows if str(r["period_start"] or "") == week_start.isoformat() and str(r["service_number"] or "").strip()}
            service_periods = {(str(r["service_number"] or "").strip(), str(r["period_start"] or "").strip()) for r in rows}
            payload_orders = []
            for service_number, period_start in sorted(service_periods):
                if not service_number:
                    continue
                row = conn.execute(
                    """
                    SELECT r.service_number, substr(MAX(r.message_date),1,10) AS message_day,
                           COALESCE(NULLIF(TRIM(m.ticket_id),''), NULLIF(TRIM(o.ticket_id),''), 'MANUAL') AS ticket_id,
                           UPPER(TRIM(COALESCE(NULLIF(ra.area_label,''), ra.sto_code, o.sto, ''))) AS area_label,
                           UPPER(TRIM(COALESCE(ra.sto_code, o.sto, ''))) AS sto
                    FROM report_group_orders r
                    LEFT JOIN report_ticket_metadata m ON m.service_number=r.service_number AND m.period_start=r.period_start
                    LEFT JOIN report_area_orders ra ON ra.service_number=r.service_number AND ra.period_start=r.period_start
                    LEFT JOIN orders o ON o.id=(SELECT o2.id FROM orders o2 WHERE o2.service_number=r.service_number ORDER BY o2.id DESC LIMIT 1)
                    WHERE r.service_number=? AND r.period_start=? GROUP BY r.service_number, r.period_start
                    """,
                    (service_number, period_start),
                ).fetchone()
                if not row:
                    continue
                raw_day = str(row["message_day"] or "")
                try:
                    formatted = date_label(date.fromisoformat(raw_day))
                except ValueError:
                    formatted = raw_day or "-"
                ticket = str(row["ticket_id"] or "MANUAL").strip()
                if ticket.upper() in {"", "-", "N/A", "NA", "NONE"}:
                    ticket = "MANUAL"
                payload_orders.append({"service_number": str(row["service_number"] or "-"), "ticket_id": ticket, "area_label": str(row["area_label"] or ""), "sto": str(row["sto"] or ""), "date_label": formatted, "raw_day": raw_day})
            payload_orders.sort(key=lambda item: item["raw_day"], reverse=True)
            for item in payload_orders:
                item.pop("raw_day", None)
            payload_orders = payload_orders[:100]
    except sqlite3.Error:
        return {"key": identity_key, "nik": "", "name": "-", "daily": 0, "weekly": 0, "all": 0, "orders": []}
    return {"key": identity_key, "nik": identity["nik"], "name": identity["name"], "daily": len(daily), "weekly": len(weekly), "all": len(all_services), "orders": payload_orders}


def normalize_address(address: str) -> str:
    text = sheet_ref.normalize(address)
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_area(address: str) -> str:
    text = normalize_address(address)
    if not text:
        return "LAINNYA"
    for area, aliases in AREA_ALIASES.items():
        if any(alias in text for alias in aliases):
            return area
    tokens = text.split()
    while tokens and (tokens[0] in ADDRESS_PREFIXES or tokens[0].isdigit()):
        tokens.pop(0)
    for token in tokens:
        if token in ADDRESS_PREFIXES or token.isdigit() or len(token) < 4 or re.fullmatch(r"\d+[A-Z]?", token):
            continue
        return token
    return "LAINNYA"


def sheet_status_bucket(reference: sheet_ref.ReferenceStatus) -> str:
    status = sheet_ref.normalize(reference.status)
    if status in CLOSED_STATUSES:
        return "close"
    if status in UPDATE_STATUSES or "UPDATE" in status or "PROGRESS" in status:
        return "update"
    return "open"


def _configured_sheet_statuses(force: bool = False) -> dict[str, sheet_ref.ReferenceStatus]:
    global _sheet_cache, _sheet_cache_time
    now = time.monotonic()
    if not force and _sheet_cache and now - _sheet_cache_time < SHEET_CACHE_SECONDS:
        return _sheet_cache
    with _sheet_cache_lock:
        now = time.monotonic()
        if not force and _sheet_cache and now - _sheet_cache_time < SHEET_CACHE_SECONDS:
            return _sheet_cache
        spreadsheet_id, gid = sheet_ref._load_config(DATABASE_PATH)
        sheet_ref._spreadsheet_id = spreadsheet_id
        sheet_ref._sheet_gid = gid
        _sheet_cache = sheet_ref.download_statuses()
        _sheet_cache_time = time.monotonic()
        return _sheet_cache


def _normalize_rca(value: str) -> str:
    text = " ".join(str(value or "").upper().replace("_", " ").split())
    if text in {"", "-", "N/A", "NA", "NONE", "#N/A"}:
        return ""
    aliases = (
        (("MENOLAK", "TIDAK MAU", "TIDAK BERKENAN"), "MENOLAK"),
        (("RUKOS", "RUMAH KOSONG", "TIDAK ADA PENGHUNI"), "RUKOS"),
        (("ALAMAT NOK", "ALAMAT TIDAK", "ALAMAT SALAH", "RUMAH TIDAK DITEMUKAN"), "ALAMAT NOK"),
        (("LEPAS DC",), "LEPAS DC"),
        (("CABUT", "PUTUS LANGGANAN", "PUTUS INTERNET"), "CABUT"),
        (("2 VOIP", "ONT 2 VOIP", "VOIP ADA 2"), "ONT 2 VOIP"),
        (("MANJA", "RESCHEDULE", "JADWAL", "BESOK", "LUAR KOTA"), "MANJA"),
        (("RNA", "TIDAK RESPON", "NO RESPON", "TIDAK BISA DIHUBUNGI", "CP NOK", "CP NO WA", "HISTORY NOK"), "RNA"),
        (("SALBON",), "SALBON"),
        (("DYING GASP",), "DYING GASP"),
        (("REDAMAN", "LOS", "RX TINGGI", "REDAMAN TINGGI"), "REDAMAN TINGGI"),
        (("KONEKTOR KOTOR", "CONNECTOR KOTOR"), "KONEKTOR KOTOR"),
        (("PUTUS", "RUSAK"), "PUTUS / RUSAK"),
    )
    for needles, label in aliases:
        if any(needle in text for needle in needles):
            return label
    return text[:60]


def _service_sto(conn: sqlite3.Connection, service: str) -> str:
    row = conn.execute(
        "SELECT UPPER(TRIM(COALESCE(sto,''))) AS sto FROM orders WHERE service_number=? ORDER BY id DESC LIMIT 1",
        (service,),
    ).fetchone()
    return str(row["sto"] or "").strip().upper() if row else ""


def load_rca_summary(area: str) -> dict:
    area = area.upper().strip()
    statuses = _configured_sheet_statuses(force=False)
    references = sheet_ref.unique_reference_orders(statuses)
    merged: dict[str, dict[str, str]] = {}

    for reference in references:
        service = str(reference.service_number or "").strip()
        if not service:
            continue
        sto = str(reference.sto or "").strip().upper()
        if area in {"MYR", "JGR"} and sto and sto != area:
            continue
        rca = _normalize_rca(reference.rca)
        if rca:
            merged[service] = {"rca": rca, "source": "SHEET", "sto": sto}

    with connect() as conn:
        try:
            rows = conn.execute(
                """
                SELECT k.service_number, k.rca, k.created_at
                FROM kendala_updates k
                JOIN (
                    SELECT service_number, MAX(id) AS max_id
                    FROM kendala_updates
                    GROUP BY service_number
                ) latest ON latest.max_id=k.id
                ORDER BY k.id DESC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []

        for row in rows:
            service = str(row["service_number"] or "").strip()
            if not service:
                continue
            sto = _service_sto(conn, service)
            if area in {"MYR", "JGR"} and sto != area:
                continue
            rca = _normalize_rca(row["rca"])
            if not rca:
                continue
            merged[service] = {"rca": rca, "source": "KENDALA", "sto": sto}

    counts: dict[str, int] = {}
    sheet_count = 0
    kendala_count = 0
    for item in merged.values():
        counts[item["rca"]] = counts.get(item["rca"], 0) + 1
        if item["source"] == "KENDALA":
            kendala_count += 1
        else:
            sheet_count += 1

    total = sum(counts.values())
    items = [
        {"label": label, "count": count, "percent": round(count * 100 / total, 1) if total else 0}
        for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "total": total,
        "items": items,
        "source": "Google Sheet + Grup Kendala",
        "sheet_count": sheet_count,
        "kendala_count": kendala_count,
    }


def _technician_by_telegram_id(telegram_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT telegram_id, nik, name, sto FROM technicians WHERE telegram_id=?", (telegram_id,)).fetchone()
    return dict(row) if row else None


def load_my_open_orders(telegram_id: int, force: bool = False) -> dict:
    technician = _technician_by_telegram_id(telegram_id)
    if not technician:
        return {"ok": False, "error": "technician_not_registered", "message": "Akun Telegram belum terdaftar sebagai teknisi."}

    statuses = _configured_sheet_statuses(force=force)
    wanted = sheet_ref.normalize(technician["name"])
    references = [
        reference for reference in sheet_ref.unique_reference_orders(statuses)
        if sheet_ref.normalize(reference.assigned_technician) == wanted
    ]

    summary: dict[str, dict[str, int]] = {}
    grouped_open: dict[str, list[sheet_ref.ReferenceStatus]] = {}
    for reference in references:
        area = classify_area(reference.address)
        counts = summary.setdefault(area, {"open": 0, "close": 0, "update": 0})
        bucket = sheet_status_bucket(reference)
        counts[bucket] += 1
        if bucket == "open":
            grouped_open.setdefault(area, []).append(reference)

    areas = []
    total_open = 0
    for area in sorted(grouped_open):
        orders = sorted(grouped_open[area], key=lambda r: sheet_ref.address_route_sort_key(r.address))
        payload_orders = []
        for reference in orders:
            ticket = sheet_ref.normalize_ticket(reference.ticket_id) or "MANUAL"
            package = str(reference.package or "").strip()
            if package and re.fullmatch(r"\d+(?:[.,]\d+)?", package):
                package = f"{package} Mbps"
            payload_orders.append({
                "customer_name": str(reference.customer_name or "-").strip() or "-",
                "ticket_id": ticket,
                "service_number": str(reference.service_number or "-").strip() or "-",
                "customer_phone": str(reference.customer_phone or "-").strip() or "-",
                "package": package or "-",
                "onu_rx": str(reference.onu_rx or "-").strip() or "-",
                "rca": str(reference.rca or "-").strip() or "-",
                "address": str(reference.address or "-").strip() or "-",
            })
        counts = summary.get(area, {"open": len(payload_orders), "close": 0, "update": 0})
        total_open += len(payload_orders)
        areas.append({"area": area, "open": counts["open"], "close": counts["close"], "update": counts["update"], "orders": payload_orders})

    return {
        "ok": True,
        "technician": {"telegram_id": technician["telegram_id"], "nik": technician["nik"], "name": technician["name"], "sto": technician["sto"]},
        "source": "Google Sheets",
        "total_open": total_open,
        "active_areas": len(areas),
        "areas": areas,
    }


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: object, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            if BASE_DIR not in resolved.parents and resolved != BASE_DIR:
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            body = resolved.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime, _ = mimetypes.guess_type(str(resolved))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)

        if route == "/health":
            self._send_json({"ok": True, "database": str(DATABASE_PATH)})
            return
        if route == "/api/dashboard":
            self._send_json(load_dashboard((query.get("area") or ["ALL"])[0], (query.get("period") or ["daily"])[0]))
            return
        if route == "/api/rca-summary":
            self._send_json(load_rca_summary((query.get("area") or ["ALL"])[0]))
            return
        if route == "/api/technician":
            identity_key = (query.get("key") or query.get("nik") or [""])[0].strip()
            area = (query.get("area") or ["ALL"])[0]
            if not identity_key:
                self._send_json({"error": "key required"}, HTTPStatus.BAD_REQUEST)
                return
            if not identity_key.startswith(("NIK:", "NAME:")):
                identity_key = f"NIK:{_norm_nik(identity_key)}"
            self._send_json(load_technician(identity_key, area))
            return
        if route == "/api/my-open-orders":
            raw_id = (query.get("telegram_id") or [""])[0].strip()
            if not raw_id.isdigit():
                self._send_json({"ok": False, "error": "telegram_id_required"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                payload = load_my_open_orders(int(raw_id), force=(query.get("force") or ["0"])[0] == "1")
                self._send_json(payload, HTTPStatus.OK if payload.get("ok") else HTTPStatus.NOT_FOUND)
            except Exception as exc:
                print(f"[miniapp] gagal membaca Orderanku Google Sheet: {exc}")
                self._send_json({"ok": False, "error": "sheet_error", "message": "Gagal membaca Google Sheets terbaru."}, HTTPStatus.BAD_GATEWAY)
            return
        if route in {"/", "/index.html"}:
            self._serve_file(BASE_DIR / "index.html")
            return
        self._serve_file(BASE_DIR / route.lstrip("/"))

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[miniapp] {self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    print(f"Kerja Bot Mini App listening on http://{HOST}:{PORT}")
    print(f"Database: {DATABASE_PATH}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
