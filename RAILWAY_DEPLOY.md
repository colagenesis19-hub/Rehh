# Railway Deployment

Panduan singkat deploy bot Telegram ONT ke Railway.

## 1. Push ke GitHub

Jangan upload `.env`, database lokal, `.venv`, atau backup. File `.gitignore` sudah disiapkan.

```bash
git init
git add .
git commit -m "Deploy Telegram ONT bot"
git branch -M main
git remote add origin https://github.com/USERNAME/telegram-ont-bot.git
git push -u origin main
```

## 2. Buat Project Railway

1. Buka Railway.
2. New Project.
3. Deploy from GitHub repo.
4. Pilih repo bot.
5. Railway akan build dari `Dockerfile`.

## 3. Tambahkan Variables

Di service Railway, buka tab Variables lalu isi:

```env
BOT_TOKEN=isi_token_botfather
ADMIN_IDS=1189386983
DATABASE_PATH=/app/data/bot.sqlite3
LOG_DIR=/app/data/logs
PHOTO_DIR=/app/data/photos
OCR_LANGUAGES=en,id
OCR_GPU=false
TIMEZONE=Asia/Jakarta
```

## 4. Tambahkan Volume

Di service Railway:

1. Buka Settings.
2. Cari Volumes.
3. Add Volume.
4. Mount Path:

```text
/app/data
```

Volume ini menyimpan SQLite, foto OCR, dan log agar tidak hilang saat redeploy.

## 5. Redeploy

Setelah Variables dan Volume dibuat, redeploy service.

Bot ini memakai polling, jadi tidak perlu generate public domain.

## 6. Test

Buka Telegram lalu kirim:

```text
/start
```

Jika gagal, cek Deploy Logs di Railway.
