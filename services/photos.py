from __future__ import annotations

from pathlib import Path

from telegram import PhotoSize, Update
from telegram.ext import ContextTypes


async def download_largest_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    photo_dir: Path,
    prefix: str,
) -> Path:
    if not update.message or not update.message.photo:
        raise ValueError("No photo found in message")
    photo: PhotoSize = update.message.photo[-1]
    telegram_id = update.effective_user.id if update.effective_user else 0
    user_dir = photo_dir / str(telegram_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    file_path = user_dir / f"{prefix}_{photo.file_unique_id}.jpg"
    file = await context.bot.get_file(photo.file_id)
    await file.download_to_drive(custom_path=file_path)
    return file_path
