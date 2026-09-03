from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def _ensure_tables(database_path: Path) -> None:
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS miniapp_manja (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                technician_nik TEXT NOT NULL DEFAULT '',
                technician_name TEXT NOT NULL DEFAULT '',
                service_number TEXT NOT NULL,
                appointment_date TEXT NOT NULL DEFAULT '',
                appointment_time TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                source TEXT NOT NULL DEFAULT 'MINI APP',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(telegram_id, service_number)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS manja_reminder_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                service_number TEXT NOT NULL,
                reminder_key TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                UNIQUE(telegram_id, service_number, reminder_key)
            )
            """
        )


def _ts(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _latest_manja(database_path: Path) -> list[dict]:
    _ensure_tables(database_path)
    merged: dict[tuple[int, str], dict] = {}
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row

        try:
            rows = conn.execute(
                """
                SELECT k.* FROM kendala_updates k
                JOIN (
                    SELECT telegram_id, service_number, MAX(id) max_id
                    FROM kendala_updates
                    GROUP BY telegram_id, service_number
                ) x ON x.max_id=k.id
                """
            ).fetchall()
            for row in rows:
                key = (int(row["telegram_id"]), str(row["service_number"]).strip())
                active = str(row["rca"] or "").upper().strip() == "MANJA" and str(row["status"] or "").upper().strip() not in {"CLOSE", "DONE", "SELESAI", "COMPLETED"}
                merged[key] = {
                    "telegram_id": key[0],
                    "service_number": key[1],
                    "note": str(row["description"] or "").strip(),
                    "appointment_date": "",
                    "appointment_time": "",
                    "source": "WORK ORDER MANYAR /update",
                    "updated_at": str(row["created_at"] or ""),
                    "active": active,
                }
        except sqlite3.OperationalError:
            pass

        rows = conn.execute("SELECT * FROM miniapp_manja").fetchall()
        for row in rows:
            key = (int(row["telegram_id"]), str(row["service_number"]).strip())
            candidate = {
                "telegram_id": key[0],
                "service_number": key[1],
                "note": str(row["note"] or "").strip(),
                "appointment_date": str(row["appointment_date"] or "").strip(),
                "appointment_time": str(row["appointment_time"] or "").strip(),
                "source": "MINI APP",
                "updated_at": str(row["updated_at"] or ""),
                "active": str(row["status"] or "").upper().strip() == "ACTIVE",
            }
            if key not in merged or _ts(candidate["updated_at"]) >= _ts(merged[key]["updated_at"]):
                merged[key] = candidate

        # /STO yang lebih baru dari status MANJA menghentikan reminder.
        try:
            for key, item in list(merged.items()):
                if not item["active"]:
                    continue
                done = conn.execute(
                    "SELECT message_date FROM report_group_orders WHERE service_number=? ORDER BY message_date DESC LIMIT 1",
                    (item["service_number"],),
                ).fetchone()
                if done and _ts(str(done[0] or "")) >= _ts(item["updated_at"]):
                    item["active"] = False
                    if item["source"] == "MINI APP":
                        conn.execute(
                            "UPDATE miniapp_manja SET status='DONE', updated_at=? WHERE telegram_id=? AND service_number=?",
                            (datetime.now().astimezone().isoformat(timespec="seconds"), item["telegram_id"], item["service_number"]),
                        )
        except sqlite3.OperationalError:
            pass

    return [item for item in merged.values() if item["active"] and item["service_number"]]


def _already_sent(database_path: Path, telegram_id: int, service: str, key: str) -> bool:
    with sqlite3.connect(database_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM manja_reminder_log WHERE telegram_id=? AND service_number=? AND reminder_key=?",
            (telegram_id, service, key),
        ).fetchone()
        return row is not None


def _mark_sent(database_path: Path, telegram_id: int, service: str, key: str, sent_at: str) -> None:
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO manja_reminder_log (telegram_id,service_number,reminder_key,sent_at) VALUES (?,?,?,?)",
            (telegram_id, service, key, sent_at),
        )


def _reminder_stage(item: dict, now: datetime) -> tuple[str, str] | None:
    date = item.get("appointment_date", "")
    clock = item.get("appointment_time", "")
    if not date:
        if now.hour < 8:
            return None
        return (f"daily-{now.date().isoformat()}", "MANJA aktif masih belum selesai")

    raw = f"{date}T{clock or '09:00'}"
    try:
        appointment = datetime.fromisoformat(raw).replace(tzinfo=now.tzinfo)
    except ValueError:
        return None
    seconds = (appointment - now).total_seconds()
    if seconds <= 0:
        return ("overdue", "Waktu janji sudah lewat")
    if seconds <= 30 * 60:
        return ("m30", "Janji pelanggan kurang dari 30 menit")
    if seconds <= 2 * 3600:
        return ("h2", "Janji pelanggan kurang dari 2 jam")
    if seconds <= 24 * 3600:
        return ("h24", "Ada janji pelanggan dalam 24 jam")
    return None


async def send_manja_reminders(context) -> None:
    app = context.application
    settings = app.bot_data["settings"]
    database_path = settings.database_path
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    items = _latest_manja(database_path)

    for item in items:
        stage = _reminder_stage(item, now)
        if not stage:
            continue
        key, headline = stage
        telegram_id = int(item["telegram_id"])
        service = item["service_number"]
        if _already_sent(database_path, telegram_id, service, key):
            continue

        schedule = ""
        if item.get("appointment_date"):
            schedule = f"\n🕒 JANJI : {item['appointment_date']} {item.get('appointment_time') or '09:00'}"
        note = item.get("note") or "-"
        text = (
            f"📅 <b>PENGINGAT MANJA</b>\n"
            f"⚠️ {headline}\n\n"
            f"🌐 INET : <code>{service}</code>{schedule}\n"
            f"📝 KET : {note}\n"
            f"📍 SUMBER : {item.get('source','MANJA')}\n\n"
            "Buka <b>Orderanku</b> di Mini App untuk melihat detail."
        )
        try:
            await app.bot.send_message(chat_id=telegram_id, text=text, parse_mode="HTML")
            _mark_sent(database_path, telegram_id, service, key, now.isoformat(timespec="seconds"))
        except Exception:
            logging.exception("Gagal mengirim reminder MANJA telegram_id=%s inet=%s", telegram_id, service)
