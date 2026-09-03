# Kerja-Bot Clean Template

Template ini mempertahankan arsitektur Telegram Bot + Mini App dari Kerja-Bot.

## Yang sudah dihapus
- OCR / EasyOCR
- Hermes AI / agent
- Hermes bridge service
- seed data / data historis yang ada di repository

## Yang disiapkan
- Telegram bot handlers dan services
- SQLite database yang dibuat otomatis saat pertama start
- Google Sheets integration
- Report / leaderboard / recap workflows
- Mini App webapp
- Docker + docker-compose

## Setup
1. Copy `.env.example` menjadi `.env`.
2. Isi `BOT_TOKEN` dan `ADMIN_IDS`.
3. Isi konfigurasi Google Sheets bila diperlukan.
4. Jalankan `docker compose up -d --build`.
5. Masukkan data baru melalui alur bot / Google Sheet yang digunakan.

Database baru akan dibuat otomatis dan tidak membawa data dari instance lama.
