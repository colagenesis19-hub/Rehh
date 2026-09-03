from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_path: Path
    log_dir: Path
    photo_dir: Path
    admin_ids: set[int]
    ocr_languages: list[str]
    ocr_gpu: bool
    timezone: str

    @staticmethod
    def from_env() -> "Settings":
        token = os.getenv("BOT_TOKEN", os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        if not token:
            raise RuntimeError("BOT_TOKEN is missing. Copy .env.example to .env and set BOT_TOKEN.")

        admin_ids = {
            int(item.strip())
            for item in os.getenv("ADMIN_IDS", "").split(",")
            if item.strip().isdigit()
        }

        db_path = Path(os.getenv("DATABASE_PATH", BASE_DIR / "database" / "bot.sqlite3"))
        if not db_path.is_absolute():
            db_path = BASE_DIR / db_path

        log_dir = Path(os.getenv("LOG_DIR", BASE_DIR / "logs"))
        if not log_dir.is_absolute():
            log_dir = BASE_DIR / log_dir

        photo_dir = Path(os.getenv("PHOTO_DIR", BASE_DIR / "database" / "photos"))
        if not photo_dir.is_absolute():
            photo_dir = BASE_DIR / photo_dir

        languages = [
            lang.strip()
            for lang in os.getenv("OCR_LANGUAGES", "en,id").split(",")
            if lang.strip()
        ]

        return Settings(
            bot_token=token,
            database_path=db_path,
            log_dir=log_dir,
            photo_dir=photo_dir,
            admin_ids=admin_ids,
            ocr_languages=languages,
            ocr_gpu=os.getenv("OCR_GPU", "false").lower() == "true",
            timezone=os.getenv("TIMEZONE", "Asia/Jakarta"),
        )


settings = Settings.from_env()
