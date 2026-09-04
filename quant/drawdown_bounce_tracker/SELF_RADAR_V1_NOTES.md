# SELF_RADAR_V1 Notes

Status: experimental fallback, bukan sinyal resmi.

Rule live:
- Universe: daftar `SELF_RADAR_TICKERS` di `app/Services/Trading/SignalRadarService.php`.
- Trigger: `RSI14 >= 60`, `ret_5d >= 5%`, `dd_20d >= -5%`.
- Entry plan: beli sore dekat close.
- Risk plan: trailing stop 1% aktif besok 09:30 WIB.

Cara catat dulu:
- Pisah dari `GABUNGAN`, `MOMENTUM`, dan `BOTTOM_REBOUND`.
- Label strategi: `SELF_RADAR_V1`.
- Label kualitas: `experimental` atau `paper` kalau belum pakai uang sungguhan.
- Jangan campur win rate/return dengan strategi resmi sampai minimal 20-30 closed trades.
- Catat alasan entry persis: harga, RSI14, ret_5d, dd_20d, waktu alert, waktu beli aktual, exit, alasan exit.

Telegram test:
- Preview: `php artisan research:send-self-radar-alert`
- Kirim: `php artisan research:send-self-radar-alert --send`

Batasan sengaja:
- Belum auto-open Trade Journal.
- Belum tulis `open_positions.json`.
- Belum masuk scheduler.

Naik kelas kalau sudah cukup data:
- Tambah tabel append-only khusus `self_radar_signals`.
- Tambah tombol Telegram Konfirmasi/Skip.
- Tambah bridge ke Trade Journal.
- Tambah evaluator terpisah dari strategi resmi.
