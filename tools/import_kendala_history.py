from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from services.google_sheet_reference import (
    DEFAULT_SPREADSHEET_ID,
    download_statuses,
    status_for_order,
)

INET_RE = re.compile(r"\b15\d{10,13}\b")
LABEL_PATTERNS = (
    re.compile(r"NO\s*INET\s*[:\-]?\s*(15\d{10,13})", re.IGNORECASE),
    re.compile(r"INET\s*/\s*VOIP\s*[:\-]?\s*(15\d{10,13})", re.IGNORECASE),
    re.compile(r"NO\s*SERVICE\s*[:\-]?\s*(15\d{10,13})", re.IGNORECASE),
)

KENDALA_KEYWORDS = (
    "NOK", "MANJA", "MENOLAK", "TIDAK MAU", "TIDAK BERKENAN",
    "RUKOS", "RUMAH KOSONG", "RNA", "ALAMAT NOK", "LEPAS DC",
    "CABUT", "SALBON", "HISTORY NOK", "CP NOK", "CP NO WA", "KENDALA",
    "RESCHEDULE", "JADWAL", "BESOK", "TIDAK RESPON", "NO RESPON",
    "TIDAK ADA RESPON", "TIDAK BISA DIHUBUNGI", "PUTUS LANGGANAN",
    "PUTUS INTERNET", "LUAR KOTA", "SUDAH DIGANTI", "SUDAH GANTI",
    "ONT OFF", "NO INET DAN SN BEDA", "2 VOIP", "VOIP ADA 2",
)

IGNORE_MARKERS = (
    "/STO", "/CONFIG", "/REPORT", "#REQOPENTIKET", "MOBAN ASSIGN LENSA CHAT",
)

ORDER_METADATA_MARKERS = (
    "DOWN-", "UP-", "ONT DUALBAND", "ONT PREMIUM", "REPLACEMENT",
    "ONU RX", "SPEED BY TACPRO", "SN ONT", "GANTI KE", "VALIN",
    "HG8245", "HG8145", "F609", "ZXHN", "GPON", "INC5", " OPEN ",
)

HEADERS = [
    "TANGGAL", "INET", "NAMA PELANGGAN", "ALAMAT", "CP", "TIKET",
    "TEKNISI", "STATUS", "RCA", "KETERANGAN", "EVIDEN",
]


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def extract_inets(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern in LABEL_PATTERNS:
        for match in pattern.findall(text):
            if match not in seen:
                seen.add(match)
                found.append(match)
    if found:
        return found
    for match in INET_RE.findall(text):
        if match not in seen:
            seen.add(match)
            found.append(match)
    return found


def looks_like_kendala(text: str) -> bool:
    upper = " ".join(text.upper().split())
    if not upper or any(marker in upper for marker in IGNORE_MARKERS):
        return False
    return any(keyword in upper for keyword in KENDALA_KEYWORDS)


def _has_issue_meaning(value: str) -> bool:
    upper = " ".join(value.upper().split())
    return any(keyword in upper for keyword in KENDALA_KEYWORDS)


def _looks_like_order_metadata(value: str) -> bool:
    upper = f" {' '.join(value.upper().split())} "
    hits = sum(1 for marker in ORDER_METADATA_MARKERS if marker in upper)
    if hits >= 2:
        return True
    if re.search(r"\bINC\d{6,}\b", upper) and re.search(r"\b(?:100|150|200|300)\b", upper):
        return True
    if re.search(r"\b-?\d{1,2}\.\d{1,2}\b", upper) and ("ONT" in upper or "DOWN-" in upper):
        return True
    return False


def _clean_segment(segment: str, inet: str) -> str:
    original = " ".join(segment.split()).strip()
    if not original:
        return ""

    upper = original.upper()
    if re.fullmatch(r"(?:ID|I['’]?D)?\s*PELANGGAN\s*[:\-]?", original, flags=re.IGNORECASE):
        return ""
    if re.fullmatch(r"(?:NO\s*)?(?:INET|SERVICE)\s*[:\-]?", original, flags=re.IGNORECASE):
        return ""
    if re.match(r"^(?:NAMA|NAMA PELANGGAN|ALAMAT|CP|TEKNISI|TYPE|NAMA ODP|REDAMAN|LINK SCC)\s*:", original, flags=re.IGNORECASE):
        return ""
    if upper in {"VISIT", "KENDALA", "KETERANGAN"}:
        return ""

    escaped = re.escape(inet)
    value = re.sub(rf"\b(?:ID|I['’]?D|NO)?\s*PELANGGAN\s*[:\-]?\s*{escaped}\b", " ", original, flags=re.IGNORECASE)
    value = re.sub(rf"\b(?:NO\s*)?(?:INET|SERVICE)\s*[:\-]?\s*{escaped}\b", " ", value, flags=re.IGNORECASE)
    value = re.sub(rf"\b{escaped}\b", " ", value)
    value = re.sub(r"\b(?:ID|I['’]?D|NO)?\s*PELANGGAN\s*[:\-]?", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:NO\s*)?(?:INET|SERVICE)\s*[:\-]?", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"^\s*(?:ID|I['’]?D)\s*[:\-]?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^\s*(?:KENDALA|KETERANGAN|VISIT)\s*[:\-]?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" |,:;-~")

    if not value or _looks_like_order_metadata(value):
        return ""

    if not _has_issue_meaning(value):
        if re.search(r"\b(?:SBY|SURABAYA|JL\.?|JALAN|KEPUTIH|MULYOREJO|KERTAJAYA|NGINDEN|MOJO|SUKOLILO|MANYAR|DHARMA|SUTOREJO|JOJORAN|KEDUNG|KALIWARON|LAGUNA|VILLA|ROYAL)\b", value, flags=re.IGNORECASE):
            return ""
        if re.search(r"\b628\d{7,13}\b", value):
            return ""
    return value


def compact_description(text: str, inet: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    raw_parts: list[str] = []
    for line in lines:
        upper = line.upper()
        if upper.startswith(("TYPE :", "NAMA / CP :", "ALAMAT :", "NAMA ODP :", "REDAMAN :", "LINK SCC :", "TEKNISI :")):
            continue
        if "KETERANGAN :" in upper:
            line = re.split(r"KETERANGAN\s*:\s*", line, flags=re.IGNORECASE, maxsplit=1)[-1]
        raw_parts.extend(part for part in re.split(r"\s*\|\s*", line) if part.strip())

    cleaned: list[str] = []
    for part in raw_parts:
        value = _clean_segment(part, inet)
        if value and value not in cleaned:
            cleaned.append(value)

    issue_parts = [part for part in cleaned if _has_issue_meaning(part)]
    selected = issue_parts if issue_parts else cleaned
    return " | ".join(selected).strip(" |")[:500]


def classify(description: str) -> tuple[str, str]:
    value = " ".join(description.upper().split())
    if any(keyword in value for keyword in ("SUDAH GANTI", "SUDAH DIGANTI", "SELESAI", "DONE", "SUDAH SELESAI")):
        return "CLOSE", "DONE"
    if "MENOLAK" in value or "TIDAK MAU" in value or "TIDAK BERKENAN" in value:
        return "UPDATE", "MENOLAK"
    if "RUKOS" in value or "RUMAH KOSONG" in value or "TIDAK ADA PENGHUNI" in value:
        return "UPDATE", "RUKOS"
    if "ALAMAT NOK" in value or "ALAMAT TIDAK" in value or "ALAMAT TIDAK DITEMUKAN" in value:
        return "UPDATE", "ALAMAT NOK"
    if "LEPAS DC" in value:
        return "UPDATE", "LEPAS DC"
    if "CABUT" in value or "PUTUS LANGGANAN" in value or "PUTUS INTERNET" in value:
        return "UPDATE", "CABUT"
    if "2 VOIP" in value or "ONT 2 VOIP" in value or "VOIP ADA 2" in value:
        return "UPDATE", "ONT 2 VOIP"
    if "MANJA" in value or "RESCHEDULE" in value or "JADWAL" in value or "BESOK" in value or "LUAR KOTA" in value:
        return "UPDATE", "MANJA"
    if ("RNA" in value or "TIDAK RESPON" in value or "NO RESPON" in value or "TIDAK ADA RESPON" in value or "TIDAK BISA DIHUBUNGI" in value or "CP NOK" in value or "CP NO WA" in value or "HISTORY NOK" in value):
        return "UPDATE", "RNA"
    if "SALBON" in value:
        return "UPDATE", "SALBON"
    return "UPDATE", "UNSPEC"


def _parse_message_date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def scan(export_path: Path, since: datetime | None = None, until: datetime | None = None) -> tuple[dict[str, int], list[dict[str, Any]], Counter[str]]:
    data = json.loads(export_path.read_text(encoding="utf-8"))
    messages = data.get("messages", [])
    latest_by_inet: dict[str, dict[str, Any]] = {}
    messages_in_range = 0
    skipped_done = 0
    total_active_updates = 0

    for message in messages:
        if message.get("type") != "message":
            continue
        message_date = _parse_message_date(message.get("date", ""))
        if since is not None and (message_date is None or message_date < since):
            continue
        if until is not None and (message_date is None or message_date >= until):
            continue
        messages_in_range += 1

        text = flatten_text(message.get("text", ""))
        if not looks_like_kendala(text):
            continue
        inets = extract_inets(text)
        if not inets:
            continue

        photo = message.get("photo") or ""
        for inet in inets:
            description = compact_description(text, inet)
            status, rca = classify(description)
            if rca == "DONE":
                skipped_done += 1
                continue
            total_active_updates += 1
            item = {
                "message_id": message.get("id"),
                "date": message.get("date", ""),
                "from": message.get("from", ""),
                "from_id": message.get("from_id", ""),
                "inet": inet,
                "description": description,
                "status": status,
                "rca": rca,
                "photo": photo,
            }
            previous = latest_by_inet.get(inet)
            previous_date = _parse_message_date(previous["date"]) if previous else None
            if previous is None or previous_date is None or (message_date is not None and message_date >= previous_date):
                latest_by_inet[inet] = item

    candidates = sorted(latest_by_inet.values(), key=lambda item: item["date"])
    stats = {
        "messages": len(messages),
        "messages_in_range": messages_in_range,
        "skipped_done": skipped_done,
        "active_updates": total_active_updates,
        "older_updates_skipped": total_active_updates - len(candidates),
        "candidates": len(candidates),
        "unique_inets": len(candidates),
        "with_evidence_messages": sum(1 for item in candidates if item["photo"]),
    }
    return stats, candidates, Counter(item["rca"] for item in candidates)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _credentials_path() -> Path:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    options: list[Path] = []
    if raw:
        options.append(Path(raw))
    options.extend([_repo_root() / "secrets" / "google-service-account.json", Path("/app/secrets/google-service-account.json")])
    for path in options:
        if path.exists():
            return path
    raise RuntimeError("Credential Google Service Account tidak ditemukan.")


def _database_path() -> Path:
    raw = os.getenv("DATABASE_PATH", "/app/database/bot.sqlite3").strip()
    path = Path(raw)
    return path if path.is_absolute() else _repo_root() / path


def _registered_technicians() -> dict[int, str]:
    path = _database_path()
    if not path.exists():
        return {}
    try:
        with sqlite3.connect(path) as conn:
            rows = conn.execute("SELECT telegram_id, name FROM technicians").fetchall()
    except sqlite3.Error:
        return {}
    return {int(telegram_id): str(name or "").strip() for telegram_id, name in rows if name}


def _telegram_id_from_export(value: Any) -> int | None:
    match = re.fullmatch(r"user(\d+)", str(value or "").strip(), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _sheet_name() -> str:
    return os.getenv("KENDALA_SHEET_NAME", "Kendala").strip() or "Kendala"


def _copy_history_evidence(export_path: Path, item: dict[str, Any]) -> str:
    photo = str(item.get("photo") or "").strip()
    if not photo:
        return "-"
    source = export_path.parent / photo
    if not source.exists():
        return "-"
    parsed = _parse_message_date(item["date"]) or datetime.now()
    directory = _repo_root() / "evidence" / f"{parsed.year:04d}" / f"{parsed.month:02d}" / item["inet"]
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"history_{item['message_id']}{source.suffix.lower() or '.jpg'}"
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination.relative_to(_repo_root()).as_posix()


def _format_date(value: str) -> str:
    parsed = _parse_message_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else value


def _clean_sheet_description(description: str, customer_name: str) -> str:
    value = " ".join(str(description or "").split())
    if not value:
        return "-"

    # Mention Telegram bukan bagian dari inti kendala.
    value = re.sub(r"(?<!\w)@[A-Za-z0-9_]+", " ", value)

    # Nama pelanggan sudah memiliki kolom sendiri, jadi buang dari keterangan.
    name = " ".join(str(customer_name or "").split()).strip()
    if name:
        value = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", " ", value, flags=re.IGNORECASE)

    # Emoji/simbol dekoratif export Telegram tidak perlu disimpan di Sheet.
    value = "".join(ch for ch in value if ord(ch) < 0x1F000)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s+([,.;:])", r"\1", value)
    value = value.strip(" |,:;-~")
    return value or "-"


def _build_rows(export_path: Path, candidates: list[dict[str, Any]], apply: bool) -> tuple[list[list[str]], list[str]]:
    statuses = download_statuses()
    technician_names = _registered_technicians()
    rows: list[list[str]] = []
    missing: list[str] = []

    for item in candidates:
        reference = status_for_order(statuses, "", item["inet"])
        if reference is None:
            missing.append(item["inet"])
            continue

        evidence = _copy_history_evidence(export_path, item) if apply else (item["photo"] or "-")
        telegram_id = _telegram_id_from_export(item.get("from_id"))
        technician_name = technician_names.get(telegram_id or -1, "")
        if not technician_name:
            technician_name = (reference.assigned_technician or "").strip()
        if not technician_name:
            technician_name = str(item.get("from") or "").strip()

        description = _clean_sheet_description(item["description"], reference.customer_name or "")
        rows.append([
            _format_date(item["date"]),
            item["inet"],
            reference.customer_name or "",
            reference.address or "",
            reference.customer_phone or "",
            reference.ticket_id or "",
            technician_name,
            "UPDATE",
            item["rca"],
            description,
            evidence,
        ])
    return rows, missing


def _apply_rows(rows: list[list[str]]) -> tuple[int, int]:
    credentials = service_account.Credentials.from_service_account_file(str(_credentials_path()), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID).strip() or DEFAULT_SPREADSHEET_ID
    sheet = _sheet_name().replace("'", "''")
    prefix = f"'{sheet}'"

    current = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=f"{prefix}!A:K").execute().get("values", [])
    if not current:
        service.spreadsheets().values().update(spreadsheetId=spreadsheet_id, range=f"{prefix}!A1:K1", valueInputOption="RAW", body={"values": [HEADERS]}).execute()
        current = [HEADERS]

    existing_rows: dict[str, int] = {}
    for index, row in enumerate(current[1:], start=2):
        if len(row) > 1 and str(row[1]).strip():
            existing_rows[str(row[1]).strip()] = index

    updates: list[dict[str, Any]] = []
    appends: list[list[str]] = []
    for row in rows:
        row_number = existing_rows.get(row[1])
        if row_number:
            updates.append({"range": f"{prefix}!A{row_number}:K{row_number}", "values": [row]})
        else:
            appends.append(row)

    if updates:
        service.spreadsheets().values().batchUpdate(spreadsheetId=spreadsheet_id, body={"valueInputOption": "RAW", "data": updates}).execute()
    if appends:
        service.spreadsheets().values().append(spreadsheetId=spreadsheet_id, range=f"{prefix}!A:K", valueInputOption="RAW", insertDataOption="INSERT_ROWS", body={"values": appends}).execute()
    return len(appends), len(updates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import history WORK ORDER MANYAR ke Sheet Kendala, 1 INET = update terbaru.")
    parser.add_argument("export_json", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview aman, tidak menulis apa pun.")
    mode.add_argument("--apply", action="store_true", help="Tulis/update data ke Sheet Kendala.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--since", type=lambda value: datetime.strptime(value, "%Y-%m-%d"))
    parser.add_argument("--until", type=lambda value: datetime.strptime(value, "%Y-%m-%d"))
    args = parser.parse_args()

    if not args.export_json.exists():
        raise SystemExit(f"File tidak ditemukan: {args.export_json}")

    stats, candidates, rca_counts = scan(args.export_json, args.since, args.until)
    print("=== PREVIEW KENDALA AKTIF TERBARU PER INET ===")
    print(f"Total pesan export         : {stats['messages']}")
    print(f"Pesan dalam rentang        : {stats['messages_in_range']}")
    if args.since:
        print(f"Mulai tanggal              : {args.since.date().isoformat()}")
    if args.until:
        print(f"Sebelum tanggal            : {args.until.date().isoformat()}")
    print(f"DONE/CLOSE diabaikan       : {stats['skipped_done']}")
    print(f"Update kendala ditemukan   : {stats['active_updates']}")
    print(f"Update lama diabaikan      : {stats['older_updates_skipped']}")
    print(f"Kandidat kendala terbaru   : {stats['candidates']}")
    print(f"INET unik                  : {stats['unique_inets']}")
    print(f"Kandidat dgn eviden        : {stats['with_evidence_messages']}")
    print()

    if rca_counts:
        print("RCA hasil klasifikasi:")
        for rca, count in sorted(rca_counts.items(), key=lambda item: (-item[1], item[0])):
            print(f"  {rca:<12} : {count}")
        print()

    rows, missing = _build_rows(args.export_json, candidates, apply=args.apply)
    if missing:
        print(f"INET tidak ditemukan di ORDER: {len(missing)}")
        for inet in missing:
            print(f"  - {inet}")
        if args.apply:
            raise SystemExit("APPLY DIBATALKAN agar tidak terjadi import parsial. Perbaiki INET ORDER di atas dulu.")
        print()

    limit = max(0, args.limit)
    row_by_inet = {row[1]: row for row in rows}
    for idx, item in enumerate(candidates[:limit], 1):
        preview_row = row_by_inet.get(item["inet"])
        description = preview_row[9] if preview_row else item["description"] or "-"
        print(f"[{idx}] {item['date']} | {item['from']}")
        print(f"INET    : {item['inet']}")
        print(f"STATUS  : {item['status']}")
        print(f"RCA     : {item['rca']}")
        print(f"KENDALA : {description}")
        print(f"EVIDEN  : {item['photo'] or '-'}")
        print()

    if len(candidates) > limit:
        print(f"... {len(candidates) - limit} kandidat lain tidak ditampilkan.")

    if args.dry_run:
        print("DRY RUN SELESAI. Tidak ada database atau Google Sheet yang diubah.")
        return

    inserted, updated = _apply_rows(rows)
    print("=== APPLY SELESAI ===")
    print(f"Baris baru ditambahkan : {inserted}")
    print(f"Baris INET diperbarui  : {updated}")
    print(f"Total aktif diolah     : {inserted + updated}")
    print("Satu INET hanya memiliki satu baris; apply ulang aman karena baris lama akan diperbarui.")


if __name__ == "__main__":
    main()
