from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

INET_RE = re.compile(r"\b\d{10,15}\b")
EXPECTED_GROUP = "REPLACEMENT NTE MANYAR"


def canonical(value: str | None) -> str:
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", str(value or "").upper()).split())


def flatten_text(value) -> str:
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


def infer_bot_chat_id(export_id) -> int:
    raw = str(export_id or "").strip()
    if not raw or not raw.lstrip("-").isdigit():
        raise ValueError("ID grup export tidak valid")
    value = int(raw)
    if value < 0:
        return value
    return int(f"-100{value}")


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS assign_group_seen (
            chat_id INTEGER NOT NULL,
            service_number TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            source_message_id INTEGER,
            PRIMARY KEY (chat_id, service_number)
        )
        """
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import history Replacement NTE MANYAR ke proteksi duplikat /assign"
    )
    parser.add_argument("export_json", type=Path)
    parser.add_argument("--database", type=Path, default=Path("database/bot.sqlite3"))
    parser.add_argument("--chat-id", type=int, default=None,
                        help="Bot API chat id. Jika kosong, diinfer dari id export Telegram.")
    args = parser.parse_args()

    payload = json.loads(args.export_json.read_text(encoding="utf-8"))
    group_name = str(payload.get("name", ""))
    if canonical(group_name) != EXPECTED_GROUP:
        raise SystemExit(f"Export bukan grup Replacement NTE MANYAR: {group_name!r}")

    chat_id = args.chat_id if args.chat_id is not None else infer_bot_chat_id(payload.get("id"))

    unique: dict[str, tuple[str, int | None]] = {}
    message_hits = 0
    for message in payload.get("messages", []):
        if not isinstance(message, dict) or message.get("type") != "message":
            continue
        text = flatten_text(message.get("text"))
        inets = list(dict.fromkeys(INET_RE.findall(text)))
        if not inets:
            continue
        message_hits += 1
        seen_at = str(message.get("date") or datetime.utcnow().replace(microsecond=0).isoformat())
        message_id = message.get("id")
        for inet in inets:
            unique.setdefault(inet, (seen_at, message_id if isinstance(message_id, int) else None))

    args.database.parent.mkdir(parents=True, exist_ok=True)
    inserted = 0
    skipped = 0
    with sqlite3.connect(args.database) as conn:
        ensure_table(conn)
        for inet, (seen_at, message_id) in unique.items():
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO assign_group_seen (
                    chat_id, service_number, first_seen_at, source_message_id
                ) VALUES (?, ?, ?, ?)
                """,
                (chat_id, inet, seen_at, message_id),
            )
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1

    print(f"Grup                  : {group_name}")
    print(f"Chat ID Bot API       : {chat_id}")
    print(f"Pesan berisi INET     : {message_hits}")
    print(f"INET unik ditemukan   : {len(unique)}")
    print(f"Berhasil ditambahkan  : {inserted}")
    print(f"Sudah ada/dilewati    : {skipped}")


if __name__ == "__main__":
    main()
