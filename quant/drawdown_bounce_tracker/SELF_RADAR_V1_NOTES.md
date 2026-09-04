# SELF_RADAR_V1 Notes

File ini sumber memori utama SELF_RADAR_V1. `plan.md` cukup pointer/changelog singkat.

## Status

- Status: experimental fallback, bukan sinyal resmi.
- Tujuan: pantau pola overnight continuation dari saham pilihan, lalu kumpulkan bukti sebelum naik jadi strategi resmi.
- Larangan: jangan campur win rate/return dengan `GABUNGAN`, `MOMENTUM`, atau `BOTTOM_REBOUND` sampai minimal 20-30 closed trades.

## Rule Live

- Universe: daftar `SELF_RADAR_TICKERS` di `app/Services/Trading/SignalRadarService.php`.
- Trigger: `RSI14 >= 60`, `ret_5d >= 5%`, `dd_20d >= -5%`.
- Entry plan: beli sore dekat close, ideal pantau 15:00-15:15 WIB.
- Risk plan: trailing stop 1% aktif hari bursa berikutnya 09:30 WIB.
- Label strategi: `SELF_RADAR_V1`.
- Label kualitas: `experimental` atau `paper` kalau belum pakai uang sungguhan.

## Tampilan Web

- Halaman: `/trades/radar`.
- Data refresh: `/trades/radar-data`.
- Seksi UI: `resources/views/trades/radar.blade.php`, blok `SELF_RADAR_V1`.
- Output kartu: `WAIT` atau `BUY SORE INI (EXPERIMENTAL)`.
- Catatan: angka kartu radar adalah estimasi live saat render/fetch, bukan bukti fill entry.

## Logging

- Tabel: `self_radar_signal_logs`.
- Model: `app/Models/SelfRadarSignalLog.php`.
- Migration: `database/migrations/2026_09_04_111500_create_self_radar_signal_logs_table.php`.
- Auto-log: top 5 kandidat yang `triggered` saat `SignalRadarService->build()` berjalan.
- Tidak dilog: semua ticker `WAIT`.
- Wajib migrate sebelum logging aktif: `php artisan migrate`.

## Cara Pakai Harian

- Buka `/trades/radar` dekat sore.
- Kalau ada `BUY SORE INI (EXPERIMENTAL)`, catat kandidat dan cek manual harga aktual.
- Preview Telegram: `php artisan research:send-self-radar-alert`.
- Kirim Telegram: `php artisan research:send-self-radar-alert --send`.
- Catat fill: `php artisan research:self-radar-log TICKER --fill=HARGA`.
- Catat exit: `php artisan research:self-radar-log TICKER --exit=HARGA`.

## Data Wajib Dicatat

- Ticker, tanggal sinyal, rank, `price_at_first_seen`, `latest_price`.
- `RSI14`, `ret_5d`, `dd_20d`, score.
- `first_seen_at`, `last_seen_at`, waktu entry aktual, harga fill aktual.
- Waktu exit, harga exit, alasan exit, hasil `WIN`/`LOSS`/`DRAW`, `pnl_pct`.

## Batasan Sengaja

- Belum auto-open Trade Journal.
- Belum tulis `open_positions.json`.
- Belum masuk scheduler.
- Belum jadi sinyal resmi Telegram harian.

## Naik Kelas Kalau Data Cukup

- Tambah tombol Telegram Konfirmasi/Skip.
- Tambah bridge ke Trade Journal.
- Tambah evaluator terpisah dari strategi resmi.
- Tambah filter ranking/liquidity kalau all-stock scan diuji lagi.

## Audit Penting

- CUAN 2026-09-03: angka radar historis bukan bukti fill; entry manual user sekitar `905-910`, bukan otomatis `925`.
- All-stock scan 2026-09-04: subset pilihan user lebih baik dari semua saham pada tes 1 hari; jangan perluas universe tanpa ranking/filter likuiditas dan log `first_seen_at`.
