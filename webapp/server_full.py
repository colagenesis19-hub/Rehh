from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from webapp import server_ext as ext
# Side-effect extension: merges WORK ORDER JAGIR into Orderanku and global INET search.
from webapp import jagir_ext  # noqa: F401

base = ext.base
_original_get = base.Handler.do_GET
_original_post = base.Handler.do_POST


def _history_rows(telegram_id: int, service_number: str) -> list[dict]:
    technician = base._technician_by_telegram_id(telegram_id)
    if not technician:
        return []
    with base.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, kind, ticket_id, service_number, old_sn, new_sn, ont_type,
                   sto, valins_id, content, created_at
            FROM histories
            WHERE telegram_id=? AND service_number=?
            ORDER BY created_at ASC, id ASC
            """,
            (telegram_id, service_number),
        ).fetchall()
    return [dict(row) for row in rows]


def _update_history(telegram_id: int, history_id: int, content: str) -> bool:
    technician = base._technician_by_telegram_id(telegram_id)
    if not technician:
        return False
    with base.connect() as conn:
        cur = conn.execute(
            "UPDATE histories SET content=? WHERE id=? AND telegram_id=?",
            (content, history_id, telegram_id),
        )
        conn.commit()
        return cur.rowcount > 0


def _ensure_completed_workflows(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS miniapp_completed_workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            technician_id INTEGER NOT NULL,
            telegram_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            service_number TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            UNIQUE(telegram_id, action, service_number)
        )
        """
    )


def _save_completed_workflow(payload: dict) -> dict:
    raw_id = str(payload.get("telegram_id") or "").strip()
    action = str(payload.get("action") or "").strip().lower()
    service = base.sheet_ref.normalize_key(payload.get("service_number"))
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    outputs = payload.get("outputs") if isinstance(payload.get("outputs"), list) else []

    if not raw_id.isdigit() or action not in {"lengkap", "config", "report", "sto"} or not service:
        return {"ok": False, "error": "invalid_request", "message": "Teknisi, workflow, atau INET tidak valid."}

    clean_outputs: list[tuple[str, str]] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().upper()
        content = str(item.get("content") or "").strip()
        if kind in {"CONFIG", "REPORT", "STO"} and content:
            clean_outputs.append((kind, content))
    if not clean_outputs:
        return {"ok": False, "error": "outputs_required", "message": "Output CONFIG/REPORT/STO belum tersedia."}

    telegram_id = int(raw_id)
    now = datetime.now().isoformat(timespec="seconds")
    with base.connect() as conn:
        technician = conn.execute(
            "SELECT id, telegram_id, nik, name, sto FROM technicians WHERE telegram_id=?",
            (telegram_id,),
        ).fetchone()
        if not technician:
            return {"ok": False, "error": "technician_not_registered", "message": "Akun Telegram belum terdaftar sebagai teknisi."}

        # Sumber order menentukan STO secara tegas: WO JAGIR selalu JGR.
        try:
            jagir_order = conn.execute(
                "SELECT service_number FROM jagir_work_orders WHERE service_number=? LIMIT 1",
                (service,),
            ).fetchone()
        except Exception:
            jagir_order = None
        effective_sto = "JGR" if jagir_order else str(data.get("sto") or technician["sto"] or "MYR").strip().upper()

        _ensure_completed_workflows(conn)
        history_ids: list[int] = []
        for kind, content in clean_outputs:
            existing = conn.execute(
                """
                SELECT id FROM histories
                WHERE telegram_id=? AND service_number=? AND kind=?
                ORDER BY id DESC LIMIT 1
                """,
                (telegram_id, service, kind),
            ).fetchone()
            values = (
                str(data.get("ticket_id") or "MANUAL").strip() or "MANUAL",
                service,
                str(data.get("old_sn") or "").strip(),
                str(data.get("new_sn") or "").strip(),
                str(data.get("ont_type") or "").strip(),
                effective_sto,
                str(data.get("valins_id") or "").strip(),
                content,
            )
            if existing:
                conn.execute(
                    """
                    UPDATE histories
                    SET ticket_id=?, service_number=?, old_sn=?, new_sn=?, ont_type=?,
                        sto=?, valins_id=?, content=?
                    WHERE id=? AND telegram_id=?
                    """,
                    (*values, int(existing["id"]), telegram_id),
                )
                history_ids.append(int(existing["id"]))
            else:
                cur = conn.execute(
                    """
                    INSERT INTO histories (
                        technician_id, telegram_id, kind, ticket_id, service_number,
                        old_sn, new_sn, ont_type, sto, valins_id, content, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(technician["id"]), telegram_id, kind,
                        *values[:-1], content, now,
                    ),
                )
                history_ids.append(int(cur.lastrowid))

        conn.execute(
            """
            INSERT INTO miniapp_completed_workflows
                (technician_id, telegram_id, action, service_number, completed_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id, action, service_number) DO UPDATE SET
                technician_id=excluded.technician_id,
                completed_at=excluded.completed_at
            """,
            (int(technician["id"]), telegram_id, action, service, now),
        )

        if jagir_order:
            # Setelah tombol SUDAH DIKERJAKAN, WO keluar dari daftar OPEN Orderanku.
            conn.execute(
                """
                UPDATE jagir_work_orders
                SET status='DONE', assigned_telegram_id=?, assigned_nik=?, assigned_name=?,
                    sto='JGR', area='JAGIR', updated_at=?
                WHERE service_number=?
                """,
                (telegram_id, str(technician["nik"] or ""), str(technician["name"] or ""), now, service),
            )

        try:
            conn.execute(
                "DELETE FROM miniapp_workflow_drafts WHERE telegram_id=? AND action=? AND service_number=?",
                (telegram_id, action, service),
            )
        except Exception:
            pass
        conn.commit()

    return {
        "ok": True,
        "action": action,
        "service_number": service,
        "history_ids": history_ids,
        "completed_at": now,
        "sto": effective_sto,
        "source": "WORK ORDER JAGIR" if jagir_order else "ORDER SHEET",
    }


def _date_label(raw_day: str) -> str:
    try:
        return datetime.fromisoformat(raw_day).strftime("%d %b %Y")
    except Exception:
        return raw_day or "-"


def _load_my_report_with_completed(telegram_id: int) -> dict:
    """Merge REPORT records with Mini App jobs marked SUDAH DIKERJAKAN.

    This keeps a job visible in Laporan even when the technician has not yet sent
    the generated REPORT message to the Telegram report group.
    """
    payload = ext.load_my_report(telegram_id)
    if not payload.get("ok"):
        return payload

    by_service: dict[str, dict] = {}
    for item in payload.get("orders", []):
        service = base.sheet_ref.normalize_key(item.get("service_number"))
        if not service:
            continue
        row = dict(item)
        row["service_number"] = service
        by_service[service] = row

    try:
        with base.connect() as conn:
            _ensure_completed_workflows(conn)
            completed = conn.execute(
                """
                SELECT service_number, MAX(completed_at) AS completed_at
                FROM miniapp_completed_workflows
                WHERE telegram_id=?
                GROUP BY service_number
                ORDER BY completed_at DESC
                """,
                (telegram_id,),
            ).fetchall()

            for done in completed:
                service = base.sheet_ref.normalize_key(done["service_number"])
                if not service:
                    continue
                completed_at = str(done["completed_at"] or "")
                raw_day = completed_at[:10]

                history = conn.execute(
                    """
                    SELECT ticket_id, sto, created_at
                    FROM histories
                    WHERE telegram_id=? AND service_number=?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (telegram_id, service),
                ).fetchone()

                current = by_service.get(service, {})
                current_day = str(current.get("raw_day") or current.get("message_day") or "")[:10]
                if not current_day or raw_day >= current_day:
                    current["raw_day"] = raw_day
                    current["message_day"] = raw_day
                    current["date_label"] = _date_label(completed_at)
                current["service_number"] = service
                current["ticket_id"] = str(current.get("ticket_id") or (history["ticket_id"] if history else "") or "MANUAL")
                current["sto"] = str(current.get("sto") or (history["sto"] if history else "") or payload.get("technician", {}).get("sto") or "")
                current["area_label"] = str(current.get("area_label") or current.get("sto") or "-")
                current["source"] = "miniapp+report" if service in by_service else "miniapp"
                by_service[service] = current
    except Exception as exc:
        print(f"[miniapp] gagal menggabungkan pekerjaan selesai ke laporan: {exc}")

    orders = sorted(
        by_service.values(),
        key=lambda item: (str(item.get("raw_day") or ""), str(item.get("service_number") or "")),
        reverse=True,
    )

    today = datetime.now().date()
    days_since_friday = (today.weekday() - 4) % 7
    week_start = today - timedelta(days=days_since_friday)
    week_end = week_start + timedelta(days=6)

    def order_day(item: dict):
        raw = str(item.get("raw_day") or item.get("message_day") or "")[:10]
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except Exception:
            return None

    payload["orders"] = orders
    payload["daily"] = sum(1 for item in orders if order_day(item) == today)
    payload["weekly"] = sum(1 for item in orders if (d := order_day(item)) is not None and week_start <= d <= week_end)
    payload["all"] = len(orders)

    trend = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        total = sum(1 for item in orders if order_day(item) == day)
        trend.append({"date": day.isoformat(), "label": base.DAYS[day.weekday()], "total": total})
    payload["trend"] = trend
    return payload


def do_get(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path == "/api/workflow-history":
        query = parse_qs(parsed.query)
        raw_id = (query.get("telegram_id") or [""])[0].strip()
        service = (query.get("service_number") or [""])[0].strip()
        if not raw_id.isdigit() or not service:
            self._send_json({"ok": False, "error": "invalid_request"}, HTTPStatus.BAD_REQUEST)
            return
        rows = _history_rows(int(raw_id), service)
        self._send_json({"ok": True, "service_number": service, "items": rows})
        return

    if parsed.path == "/api/my-report":
        query = parse_qs(parsed.query)
        raw_id = (query.get("telegram_id") or [""])[0].strip()
        if not raw_id.isdigit():
            self._send_json({"ok": False, "error": "telegram_id_required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = _load_my_report_with_completed(int(raw_id))
            self._send_json(payload, HTTPStatus.OK if payload.get("ok") else HTTPStatus.NOT_FOUND)
        except Exception as exc:
            print(f"[miniapp] gagal membaca laporan gabungan: {exc}")
            self._send_json({"ok": False, "error": "report_error", "message": "Gagal membaca laporan pribadi."}, HTTPStatus.INTERNAL_SERVER_ERROR)
        return

    _original_get(self)


def do_post(self) -> None:
    parsed = urlparse(self.path)
    if parsed.path == "/api/workflow-complete":
        try:
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length) if length else b"{}"
            payload = json.loads(body.decode("utf-8") or "{}")
            result = _save_completed_workflow(payload if isinstance(payload, dict) else {})
            self._send_json(result, HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            print(f"[miniapp] gagal menyimpan workflow selesai: {exc}")
            self._send_json({"ok": False, "error": "workflow_complete_error", "message": "Gagal menyimpan pekerjaan ke history."}, HTTPStatus.INTERNAL_SERVER_ERROR)
        return

    if parsed.path != "/api/workflow-history":
        _original_post(self)
        return
    try:
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length) if length else b"{}"
        payload = json.loads(body.decode("utf-8") or "{}")
        raw_id = str(payload.get("telegram_id") or "").strip()
        raw_history_id = str(payload.get("history_id") or "").strip()
        content = str(payload.get("content") or "")
        if not raw_id.isdigit() or not raw_history_id.isdigit():
            self._send_json({"ok": False, "error": "invalid_request"}, HTTPStatus.BAD_REQUEST)
            return
        ok = _update_history(int(raw_id), int(raw_history_id), content)
        self._send_json({"ok": ok}, HTTPStatus.OK if ok else HTTPStatus.NOT_FOUND)
    except Exception as exc:
        print(f"[miniapp] gagal update history: {exc}")
        self._send_json({"ok": False, "error": "history_update_error"}, HTTPStatus.INTERNAL_SERVER_ERROR)


base.Handler.do_GET = do_get
base.Handler.do_POST = do_post


if __name__ == "__main__":
    print(f"Kerja Bot Mini App listening on http://{base.HOST}:{base.PORT}")
    print(f"Database: {base.DATABASE_PATH}")
    ThreadingHTTPServer((base.HOST, base.PORT), base.Handler).serve_forever()
