# Telegram ONT Replacement Bot

Bot Telegram production-ready untuk teknisi Telkom IndiHome replacement ONT. Bot menyimpan login teknisi, membaca label ONT dengan OCR, membuat CONFIG, REPORT, STO, menyimpan history ke SQLite, dan menyediakan command admin.

## Fitur

- Login permanen dengan NIK dan nama teknisi.
- Menu utama: 📋 CONFIG, 📄 REPORT, 📡 STO, 👤 Profile, ⚙ Settings.
- OCR label ONT dengan OpenCV, EasyOCR, dan Pillow.
- Deteksi Huawei, ZTE, Fiberhome, Nokia, Raisecom, Fiberlink.
- Deteksi GPON SN, PON No, SN, Serial Number, model ZXHN, HG8145V5, HG8245H, F609, F670L, F670Y, F660, F6600P, EG8145V5, dan pola umum lain.
- Huawei `PON No` otomatis disimpan sebagai `SN ONT BARU`.
- Fallback manual bila OCR gagal atau confidence rendah.
- Semua CONFIG, REPORT, dan STO disimpan ke SQLite.
- Command history, search, delete, export CSV.
- Admin: view users, broadcast, statistics, delete user, backup database.
- Logging untuk login, error, OCR success/failure.

## Struktur

```text
telegram-ont-bot/
  main.py
  config.py
  database.py
  requirements.txt
  .env.example
  README.md
  Dockerfile
  docker-compose.yml
  railway.json
  deploy/
    telegram-ont-bot.service
  handlers/
  services/
  ocr/
  utils/
  database/
  logs/
```

## Instalasi Lokal

Gunakan Python 3.12.

```bash
cd telegram-ont-bot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

```env
BOT_TOKEN=token_bot_dari_botfather
ADMIN_IDS=telegram_id_admin
OCR_GPU=false
TIMEZONE=Asia/Jakarta
```

Jalankan:

```bash
python main.py
```

## Command User

- `/start` login atau kembali ke menu.
- `/history` menampilkan 10 history terakhir.
- `/search kata_kunci` mencari tiket, service number, SN, STO, atau isi output.
- `/delete id_history` menghapus history milik user.
- `/export` export history user ke CSV.
- `/profile` melihat profile teknisi.
- `/settings` melihat bantuan singkat.
- `/cancel` membatalkan input berjalan.

## Command Admin

Admin adalah Telegram ID yang masuk di `ADMIN_IDS`.

- `/admin_users`
- `/admin_broadcast pesan`
- `/admin_stats`
- `/admin_delete_user telegram_id`
- `/admin_backup`

## Format Output

Bot menghasilkan format CONFIG, REPORT, dan STO sesuai template replacement ONT yang diminta. Output yang dikirim ke Telegram adalah output yang sama dengan yang disimpan di SQLite.

## Docker

```bash
cd telegram-ont-bot
cp .env.example .env
docker compose up -d --build
```

Lihat log:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

## systemd Ubuntu VPS

```bash
sudo useradd --system --home /opt/telegram-ont-bot --shell /usr/sbin/nologin telegrambot
sudo mkdir -p /opt/telegram-ont-bot
sudo chown -R telegrambot:telegrambot /opt/telegram-ont-bot
```

Upload project ke `/opt/telegram-ont-bot`, lalu:

```bash
cd /opt/telegram-ont-bot
sudo -u telegrambot python3.12 -m venv .venv
sudo -u telegrambot .venv/bin/pip install -r requirements.txt
sudo -u telegrambot cp .env.example .env
sudo nano .env
sudo cp deploy/telegram-ont-bot.service /etc/systemd/system/telegram-ont-bot.service
sudo systemctl daemon-reload
sudo systemctl enable telegram-ont-bot
sudo systemctl start telegram-ont-bot
sudo systemctl status telegram-ont-bot
```

Log:

```bash
journalctl -u telegram-ont-bot -f
```

## Railway Deployment

1. Push folder `telegram-ont-bot` ke GitHub.
2. Buat project baru di Railway.
3. Pilih repo GitHub.
4. Tambahkan variable:
   - `BOT_TOKEN`
   - `ADMIN_IDS`
   - `OCR_GPU=false`
   - `TIMEZONE=Asia/Jakarta`
5. Railway akan memakai `Dockerfile`.

Catatan: SQLite di Railway cocok untuk percobaan. Untuk produksi jangka panjang, gunakan volume/persistent storage Railway agar database tidak hilang saat redeploy.

## Oracle Cloud Deployment

1. Buat VM Ubuntu 22.04 atau 24.04.
2. Buka akses internet keluar default.
3. Install Docker:

```bash
sudo apt update
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc > /dev/null
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

4. Upload project, isi `.env`, lalu:

```bash
docker compose up -d --build
```

## Ubuntu VPS Tanpa Docker

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv libgl1 libglib2.0-0 libgomp1
cd telegram-ont-bot
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python main.py
```

Untuk 24/7 gunakan systemd seperti bagian di atas.

## Database

SQLite tersimpan di:

```text
database/bot.sqlite3
```

Foto OCR tersimpan di:

```text
database/photos/
```

Backup manual:

```bash
cp database/bot.sqlite3 database/backup.sqlite3
```

Atau gunakan `/admin_backup`.

## Catatan OCR

Kualitas OCR tergantung foto. Hasil terbaik:

- Label terang dan tidak blur.
- Kamera tegak lurus.
- SN/model tidak tertutup refleksi.
- Foto cukup dekat tetapi tidak terpotong.

Jika confidence rendah atau serial tidak terbaca, bot otomatis meminta teknisi mengetik manual.
