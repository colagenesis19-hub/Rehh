from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


GUIDE_PARTS = [
    """🤖 KERJA BOT — PANDUAN PERINTAH

Gunakan /perintah kapan saja di chat pribadi bot untuk melihat panduan fitur yang tersedia.

━━━━━━━━━━━━━━━━━━
📦 ORDER TEKNISI
━━━━━━━━━━━━━━━━━━

📦 /orderanku
📍 Digunakan di: CHAT PRIBADI BOT

Fungsi:
Melihat daftar order yang di-assign ke teknisi.

Data yang ditampilkan antara lain:
• Nomor INET
• Nama pelanggan
• Nomor HP / CP
• Alamat
• Paket internet
• ONU RX
• RCA
• Tiket
• Status order

Fitur:
• Menampilkan order OPEN per area
• Area tanpa OPEN otomatis disembunyikan
• Area muncul kembali jika ada order OPEN baru
• Alamat diurutkan agar gang/blok/lokasi yang berdekatan tampil berurutan

Riwayat:
/orderanku close
→ Melihat order yang sudah selesai.

/orderanku semua
→ Melihat seluruh order OPEN dan CLOSE.

━━━━━━━━━━━━━━━━━━
📝 FORMAT PEKERJAAN
━━━━━━━━━━━━━━━━━━

📍 Digunakan di: CHAT PRIBADI BOT

Gunakan menu utama:

🔹 LENGKAP
Membuat CONFIG + REPORT + STO sekaligus.

🔹 CONFIG
Membuat format konfigurasi penggantian ONT.

🔹 REPORT
Membuat format laporan pekerjaan.

🔹 STO
Membuat format /sto yang nantinya dikirim ke topic REPORT.

Jika data belum lengkap, bot akan menanyakan data yang masih dibutuhkan terlebih dahulu.""",

    """━━━━━━━━━━━━━━━━━━
📊 LAPORAN PEKERJAAN
━━━━━━━━━━━━━━━━━━

📊 /laporan
📍 Digunakan di:
• CHAT PRIBADI BOT
• TOPIC REPORT MANYAR
• TOPIC REPORT JAGIR

👤 DI CHAT PRIBADI

/laporan
→ Menampilkan laporan milik teknisi yang sedang menggunakan bot.

Bisa juga mencari berdasarkan NIK atau nama:
/laporan 26050138
/laporan Thomas Gustian

Data yang ditampilkan:
• NIK teknisi
• Nama teknisi
• Maksimal 3 periode terakhir
• Nomor INET
• Nomor tiket
• Tanggal report
• Total CLOSE

Periode report dihitung Jumat sampai Kamis.

📡 DI TOPIC REPORT

Gunakan:
/laporan <NIK/NAMA>

Contoh:
/laporan 26050138
/laporan Thomas Gustian

Bisa digunakan oleh teknisi maupun atasan yang berada di topic REPORT, walaupun atasan tidak terdaftar sebagai teknisi.

⚠️ Di grup, /laporan hanya aktif pada topic REPORT yang sudah didaftarkan ke bot.

━━━━━━━━━━━━━━━━━━
🎫 SISTEM TIKET /LAPORAN
━━━━━━━━━━━━━━━━━━

Jika tiket tersedia:
152303xxxxxx | INCxxxxxxxx | 24/08/2026

Jika tiket belum tersedia:
152303xxxxxx | MANUAL | 24/08/2026

Saat /laporan digunakan kembali, bot akan mencoba melengkapi tiket yang masih MANUAL.

Urutan pengecekan tiket:
1. Tiket dari report /sto
2. INSERA TODAY pada Order Sheet
3. Kolom TIKET pada Order Sheet
4. Jika semuanya kosong → MANUAL

Jika tiket baru muncul di Sheet kemudian hari, cukup jalankan /laporan lagi. Tidak perlu report ulang hanya untuk memperbarui tiket.""",

    """━━━━━━━━━━━━━━━━━━
🏆 LEADERBOARD
━━━━━━━━━━━━━━━━━━

🏆 /leaderboard
📍 Digunakan di:
• CHAT PRIBADI BOT
• TOPIC REPORT MANYAR
• TOPIC REPORT JAGIR

🔓 Akses: UNIVERSAL
Tidak harus admin dan tidak harus terdaftar sebagai teknisi.

Fungsi:
Melihat ranking teknisi berdasarkan jumlah report/CLOSE yang tersimpan pada periode berjalan.

Periode leaderboard:
Jumat sampai Kamis.

👤 DI CHAT PRIBADI
/leaderboard
→ Bot menampilkan leaderboard semua area REPORT yang sudah terdaftar, seperti MANYAR dan JAGIR.

📡 DI TOPIC REPORT
/leaderboard
→ Bot hanya menampilkan leaderboard area topic tersebut.

Contoh:
Jika diketik di REPORT MANYAR, bot menampilkan leaderboard MANYAR.
Jika diketik di REPORT JAGIR, bot menampilkan leaderboard JAGIR.

Data ranking menggunakan report internal bot dan satu INET dihitung satu pekerjaan dalam satu periode.

━━━━━━━━━━━━━━━━━━
📱 FORMAT WHATSAPP PELANGGAN
━━━━━━━━━━━━━━━━━━

📱 /format <INET>
📍 Digunakan di: CHAT PRIBADI BOT

Contoh:
/format 152303339740

Fungsi:
Membuat pesan WhatsApp pelanggan untuk kunjungan penggantian ONT/Modem.

Pesan dapat mencakup:
• Nama pelanggan
• Nomor Internet
• Alamat
• Nomor HP
• Tujuan kunjungan
• Informasi penggantian ONT/Modem
• Informasi GRATIS
• Tidak mengubah biaya langganan""",

    """━━━━━━━━━━━━━━━━━━
📡 REPORT /STO
━━━━━━━━━━━━━━━━━━

📡 /sto
📍 Digunakan di:
• TOPIC REPORT MANYAR → STO MYR
• TOPIC REPORT JAGIR → STO JGR

Fungsi:
Menyimpan pekerjaan teknisi ke database report.

Bot membaca:
• STO
• Tiket
• Nomor INET / NO SERVICE
• NIK teknisi
• Nama teknisi

Contoh:
/STO : MYR
TIKET : INCxxxxxxxx
NO SERVICE : 152303xxxxxx
...
NIK NAMA TEKNISI : 26050138 | THOMAS GUSTIAN

Aturan:
MYR → REPORT MANYAR
JGR → REPORT JAGIR

Jika STO tidak sesuai topic, bot akan menolak report.

Satu INET dihitung satu pekerjaan dalam satu periode Jumat–Kamis. INET yang sama pada periode yang sama tidak dihitung dua kali sebagai pekerjaan baru.

━━━━━━━━━━━━━━━━━━
🛠 UPDATE KENDALA
━━━━━━━━━━━━━━━━━━

🛠 /update
📍 Digunakan di: GRUP/TOPIC PEKERJAAN YANG SUDAH DIKONFIGURASI UNTUK UPDATE KENDALA

Fungsi:
Mencatat perkembangan atau kendala order.

Bot dapat mencatat data seperti:
• Nomor INET
• Kendala / RCA
• Status pekerjaan
• Bukti / evidence
• Foto pekerjaan
• Link evidence

⚠️ /update bukan command untuk chat pribadi bot.""",

    """━━━━━━━━━━━━━━━━━━
📨 REQUEST ASSIGN
━━━━━━━━━━━━━━━━━━

📨 /assign
📍 Digunakan di: GRUP NTE MANYAR YANG SUDAH DIKONFIGURASI

Fungsi:
Membantu request assign tiket/order sesuai format grup pekerjaan.

━━━━━━━━━━━━━━━━━━
📅 REKAP PEKERJAAN
━━━━━━━━━━━━━━━━━━

📅 /rekapharian
📍 Digunakan di: CHAT PRIBADI BOT

Melihat rekap pekerjaan harian teknisi.

📅 /rekapmingguan
📍 Digunakan di: CHAT PRIBADI BOT

Melihat rekap pekerjaan mingguan teknisi.

Bot juga memiliki pengiriman rekap otomatis sesuai jadwal.

━━━━━━━━━━━━━━━━━━
👤 PROFILE TEKNISI
━━━━━━━━━━━━━━━━━━

👤 /profile
📍 Digunakan di: CHAT PRIBADI BOT

Melihat data teknisi yang terdaftar, seperti:
• NIK
• Nama
• STO
• Telegram ID""",

    """━━━━━━━━━━━━━━━━━━
🔎 FITUR LAIN
━━━━━━━━━━━━━━━━━━

🔎 /history
📍 Digunakan di: CHAT PRIBADI BOT
Melihat histori pekerjaan yang tersimpan.

🔍 /search
📍 Digunakan di: CHAT PRIBADI BOT
Mencari data pekerjaan.

⚙️ /settings
📍 Digunakan di: CHAT PRIBADI BOT
Membuka pengaturan bot.

▶️ /start
📍 Digunakan di: CHAT PRIBADI BOT
Memulai bot / pendaftaran teknisi.

📖 /perintah
📍 Digunakan di: CHAT PRIBADI BOT
Membuka panduan lengkap ini.

━━━━━━━━━━━━━━━━━━
📍 RINGKASAN LOKASI COMMAND
━━━━━━━━━━━━━━━━━━

🤖 CHAT PRIBADI BOT
/start
/orderanku
/orderanku close
/orderanku semua
/laporan
/laporan <NIK/NAMA>
/leaderboard
/format <INET>
/profile
/rekapharian
/rekapmingguan
/history
/search
/settings
/perintah

Menu:
• LENGKAP
• CONFIG
• REPORT
• STO

📡 TOPIC REPORT MANYAR
/sto → MYR
/laporan <NIK/NAMA>
/leaderboard

📡 TOPIC REPORT JAGIR
/sto → JGR
/laporan <NIK/NAMA>
/leaderboard

🛠 GRUP/TOPIC UPDATE KENDALA
/update

📨 GRUP NTE MANYAR
/assign

━━━━━━━━━━━━━━━━━━
⚠️ CATATAN PENTING
━━━━━━━━━━━━━━━━━━

• Pastikan nomor INET benar.
• Pastikan NIK dan nama teknisi pada /sto benar.
• Pastikan STO sesuai topic REPORT.
• MYR → REPORT MANYAR.
• JGR → REPORT JAGIR.
• Tiket yang belum tersedia tampil MANUAL sementara.
• Tiket MANUAL akan dicek kembali saat /laporan digunakan.
• /leaderboard dapat digunakan semua orang di private bot atau topic REPORT terdaftar.
• Gunakan command sesuai chat/grup/topic yang ditentukan.

🤖 KERJA BOT
Membantu teknisi mengelola order, membuat format, mencatat report, memantau progres, dan merapikan histori pekerjaan.""",
]


async def perintah_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the technician guide in private chat; registration is not required."""
    chat = update.effective_chat
    message = update.effective_message
    if not chat or chat.type != "private" or not message:
        return

    for part in GUIDE_PARTS:
        await message.reply_text(part)
