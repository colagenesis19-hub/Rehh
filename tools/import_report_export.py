from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

NO_SERVICE_RE = re.compile(r"(?:NO\s*SERVICE|INET)\s*:\s*(\d{6,})", re.IGNORECASE)
TECH_RE = re.compile(
    r"(?:NIK\s*NAMA\s*TEKNISI|TEKNISI)\s*:\s*(\d+)\s*\|\s*([^\n\r]+)",
    re.IGNORECASE,
)


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    return ""


def period_start_for(day: date) -> date:
    days_since_friday = (day.weekday() - 4) % 7
    return day - timedelta(days=days_since_friday)


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS report_group_orders (
            service_number TEXT NOT NULL,
            period_start TEXT NOT NULL,
            technician_nik TEXT NOT NULL,
            technician_name TEXT NOT NULL,
            message_date TEXT NOT NULL,
            chat_id INTEGER NOT NULL,
            message_id INTEGER,
            created_at TEXT NOT NULL,
            PRIMARY KEY (service_number, period_start)
        )
        """
    )


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import histori Telegram REPORT MANYAR ke database leaderboard."
    )
    parser.add_argument("export_json", type=Path, help="File result.json dari Telegram Desktop")
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("database/bot.sqlite3"),
        help="Path SQLite bot (default: database/bot.sqlite3)",
    )
    parser.add_argument("--from-date", help="Tanggal awal YYYY-MM-DD (opsional)")
    parser.add_argument("--to-date", help="Tanggal akhir YYYY-MM-DD (opsional)")
    args = parser.parse_args()

    from_date = parse_date(args.from_date)
    to_date = parse_date(args.to_date)

    payload = json.loads(args.export_json.read_text(encoding="utf-8"))
    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        raise SystemExit("Format export tidak valid: field messages tidak ditemukan.")

    candidates: list[tuple[str, str, str, str, str, int | None]] = []
    for message in messages:
        if not isinstance(message, dict) or message.get("type") != "message":
            continue

        raw_date = message.get("date")
        if not raw_date:
            continue
        try:
            message_dt = datetime.fromisoformat(str(raw_date))
        except ValueError:
            continue

        message_day = message_dt.date()
        if from_date and message_day < from_date:
            continue
        if to_date and message_day > to_date:
            continue

        text = flatten_text(message.get("text", ""))
        service_match = NO_SERVICE_RE.search(text)
        tech_match = TECH_RE.search(text)
        if not service_match or not tech_match:
            continue

        service_number = service_match.group(1).strip()
        technician_nik = tech_match.group(1).strip()
        technician_name = tech_match.group(2).strip()
        period_start = period_start_for(message_day).isoformat()
        message_id = message.get("id") if isinstance(message.get("id"), int) else None

        candidates.append(
            (
                service_number,
                period_start,
                technician_nik,
                technician_name,
                message_dt.isoformat(),
                message_id,
            )
        )

    # Dedupe di file export lebih dulu. Pesan original dan balasan bot sering memuat INET sama.
    unique: dict[tuple[str, str], tuple[str, str, str, str, str, int | None]] = {}
    for row in candidates:
        unique.setdefault((row[0], row[1]), row)

    args.database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.database)
    try:
        ensure_tables(conn)
        inserted = 0
        skipped = 0
        now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        for service_number, period_start, nik, name, message_date, message_id in unique.values():
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO report_group_orders (
                    service_number, period_start, technician_nik, technician_name,
                    message_date, chat_id, message_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    service_number,
                    period_start,
                    nik,
                    name,
                    message_date,
                    0,
                    message_id,
                    now,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        conn.commit()
    finally:
        conn.close()

    print(f"Pesan report terdeteksi : {len(candidates)}")
    print(f"INET unik             : {len(unique)}")
    print(f"Berhasil ditambahkan  : {inserted}")
    print(f"Sudah ada/dilewati    : {skipped}")


if __name__ == "__main__":
    main()
