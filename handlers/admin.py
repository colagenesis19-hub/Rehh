from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from database import Database


def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = context.application.bot_data["settings"]
    return bool(update.effective_user and update.effective_user.id in settings.admin_ids)


async def admin_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if is_admin(update, context):
        return True
    if update.effective_chat:
        await update.effective_chat.send_message("Perintah admin saja.")
    return False


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or not update.effective_chat:
        return
    db: Database = context.application.bot_data["db"]
    rows = await db.list_technicians()
    if not rows:
        await update.effective_chat.send_message("Belum ada user.")
        return
    lines = ["Daftar user:"]
    for row in rows[:50]:
        lines.append(f"{row['telegram_id']} | {row['nik']} | {row['name']} | {row['created_at']}")
    await update.effective_chat.send_message("\n".join(lines))


async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or not update.effective_chat:
        return
    text = " ".join(context.args).strip()
    if not text:
        await update.effective_chat.send_message("Format: /admin_broadcast pesan")
        return
    db: Database = context.application.bot_data["db"]
    rows = await db.list_technicians()
    success = 0
    for row in rows:
        try:
            await context.bot.send_message(chat_id=row["telegram_id"], text=text)
            success += 1
        except Exception:
            continue
    await update.effective_chat.send_message(f"Broadcast terkirim ke {success} user.")


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or not update.effective_chat:
        return
    db: Database = context.application.bot_data["db"]
    stats = await db.statistics()
    await update.effective_chat.send_message(
        f"Statistik\n\nUsers: {stats['users']}\nGenerated: {stats['histories']}\nOCR failures: {stats['ocr_failures']}"
    )


def _find_user_by_identifier(database_path: Path, identifier: str) -> sqlite3.Row | None:
    identifier = identifier.strip()
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        # Angka bisa merupakan Telegram ID maupun NIK. Prioritaskan Telegram ID,
        # lalu fallback ke NIK agar kedua bentuk dapat dipakai oleh admin.
        if identifier.isdigit():
            row = conn.execute(
                "SELECT * FROM technicians WHERE telegram_id = ?",
                (int(identifier),),
            ).fetchone()
            if row:
                return row
        return conn.execute(
            "SELECT * FROM technicians WHERE TRIM(nik) = ? ORDER BY id DESC LIMIT 1",
            (identifier,),
        ).fetchone()


def _delete_user_by_identifier(database_path: Path, identifier: str) -> sqlite3.Row | None:
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        row = _find_user_by_identifier(database_path, identifier)
        if row is None:
            return None
        conn.execute("DELETE FROM technicians WHERE id = ?", (row["id"],))
        return row


def _edit_user(
    database_path: Path,
    identifier: str,
    new_nik: str,
    new_name: str,
    new_sto: str | None,
) -> tuple[sqlite3.Row, sqlite3.Row] | None:
    old = _find_user_by_identifier(database_path, identifier)
    if old is None:
        return None

    clean_nik = new_nik.strip()
    clean_name = " ".join(new_name.strip().split())
    clean_sto = (new_sto or str(old["sto"] or "")).strip().upper()
    if not clean_nik or not clean_name:
        raise ValueError("NIK dan nama baru wajib diisi.")

    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE technicians SET nik = ?, name = ?, sto = ? WHERE id = ?",
            (clean_nik, clean_name, clean_sto, old["id"]),
        )

        # Jika NIK/nama sebelumnya pernah digunakan untuk /sto, rapikan histori
        # report agar /laporan dan leaderboard tidak pecah menjadi dua identitas.
        try:
            conn.execute(
                """
                UPDATE report_group_orders
                SET technician_nik = ?, technician_name = ?
                WHERE technician_nik = ?
                """,
                (clean_nik, clean_name, str(old["nik"])),
            )
        except sqlite3.OperationalError:
            pass

        updated = conn.execute(
            "SELECT * FROM technicians WHERE id = ?",
            (old["id"],),
        ).fetchone()
    return old, updated


async def admin_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or not update.effective_chat:
        return
    if not context.args:
        await update.effective_chat.send_message(
            "Format: /admin_delete_user TELEGRAM_ID_ATAU_NIK"
        )
        return
    db: Database = context.application.bot_data["db"]
    row = await __import__("asyncio").to_thread(
        _delete_user_by_identifier,
        db.db_path,
        context.args[0],
    )
    if row is None:
        await update.effective_chat.send_message("User tidak ditemukan.")
        return
    await update.effective_chat.send_message(
        "✅ User dihapus.\n"
        f"Telegram ID : {row['telegram_id']}\n"
        f"NIK : {row['nik']}\n"
        f"Nama : {row['name']}"
    )


async def admin_edit_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or not update.effective_chat:
        return

    raw = " ".join(context.args).strip()
    if not raw:
        await update.effective_chat.send_message(
            "Format:\n"
            "/admin_edit_user TELEGRAM_ID_ATAU_NIK NIK_BARU | NAMA BARU\n"
            "/admin_edit_user TELEGRAM_ID_ATAU_NIK NIK_BARU | NAMA BARU | STO\n\n"
            "Contoh:\n"
            "/admin_edit_user 7692707862 26940071 | DEDE MUHAMMAD SAFRIYANI | MYR"
        )
        return

    first, sep, remainder = raw.partition(" ")
    parts = [part.strip() for part in remainder.split("|")] if sep else []
    if len(parts) < 2 or not parts[0] or not parts[1]:
        await update.effective_chat.send_message(
            "❌ Format salah. Contoh:\n"
            "/admin_edit_user 7692707862 26940071 | DEDE MUHAMMAD SAFRIYANI | MYR"
        )
        return

    identifier = first.strip()
    new_nik = parts[0]
    new_name = parts[1]
    new_sto = parts[2] if len(parts) >= 3 and parts[2] else None

    db: Database = context.application.bot_data["db"]
    try:
        result = await __import__("asyncio").to_thread(
            _edit_user,
            db.db_path,
            identifier,
            new_nik,
            new_name,
            new_sto,
        )
    except ValueError as exc:
        await update.effective_chat.send_message(f"❌ {exc}")
        return

    if result is None:
        await update.effective_chat.send_message("❌ User tidak ditemukan.")
        return

    old, new = result
    await update.effective_chat.send_message(
        "✅ DATA USER DIPERBARUI\n\n"
        f"Telegram ID : {new['telegram_id']}\n"
        f"NIK : {old['nik']} → {new['nik']}\n"
        f"Nama : {old['name']} → {new['name']}\n"
        f"STO : {old['sto'] or '-'} → {new['sto'] or '-'}"
    )


async def admin_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await admin_guard(update, context) or not update.effective_chat:
        return
    db_path: Path = context.application.bot_data["settings"].database_path
    backup_path = db_path.parent / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
    shutil.copy2(db_path, backup_path)
    await update.effective_chat.send_document(
        document=backup_path.open("rb"),
        filename=backup_path.name,
        caption="Backup database.",
    )


def build_admin_handlers() -> list[CommandHandler]:
    return [
        CommandHandler("admin_users", admin_users),
        CommandHandler("admin_broadcast", admin_broadcast),
        CommandHandler("admin_stats", admin_stats),
        CommandHandler("admin_delete_user", admin_delete_user),
        CommandHandler("admin_edit_user", admin_edit_user),
        CommandHandler("admin_backup", admin_backup),
    ]
