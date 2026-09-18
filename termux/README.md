# 📱 Termux Alert — Sentimena Trading

Jalankan trailing stop alert dari HP Android walau Mac mati.

## Setup (sekali saja)

### 1. Install Termux di HP
Download dari F-Droid (bukan Play Store): https://f-droid.org/packages/com.termux/

### 2. Install dependensi di Termux
```bash
pkg update && pkg upgrade -y
pkg install python git -y
pip install yfinance pandas requests
```

### 3. Clone / copy file ke HP
```bash
mkdir -p ~/sentimena
cd ~/sentimena
# Copy file-file berikut dari Mac ke HP:
# - open_positions.json
# - trailing_alert_termux.py
# - .env (berisi TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID)
```

### 4. Copy file dari Mac ke HP via SSH/ADB/WhatsApp
Cara termudah: kirim file via WhatsApp ke diri sendiri, lalu download di HP.

### 5. Set cron otomatis di Termux
```bash
pkg install cronie termux-services -y
sv-enable crond
crontab -e
```
Tambahkan baris ini:
```
*/15 9-16 * * 1-5 cd ~/sentimena && python trailing_alert_termux.py >> ~/sentimena/alert.log 2>&1
35 15 * * 1-5 cd ~/sentimena && python trailing_alert_termux.py --radar >> ~/sentimena/alert.log 2>&1
```

### 6. Sync open_positions.json tiap hari
Sebelum market buka, update `open_positions.json` dari Mac atau edit manual.

## File yang Dibutuhkan di HP
- `trailing_alert_termux.py` — script utama
- `open_positions.json` — posisi yang dipantau
- `.env` — TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID
