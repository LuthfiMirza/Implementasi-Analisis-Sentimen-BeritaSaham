<?php

use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Schedule;

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote');

// ═══════════════════════════════════════════
// JADWAL BEI — Semi-Realtime Hybrid System
// Senin–Jumat (hari bursa Indonesia)
// ═══════════════════════════════════════════

// PRE-MARKET: 08.45 WIB
// Ambil snapshot indikator harian sebelum pasar buka
Schedule::command('stocks:fetch-history --days=1')
    ->weekdays()
    ->dailyAt('08:45')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// PRE-MARKET: 08.50 WIB
// Refresh berita pre-market -- limit dinaikkan dari 20 ke 40 (Fase R7a) karena rss_local sudah
// terbukti sumber full_text paling andal (cakupan 99%, dominan CNBC Indonesia + Antara News),
// dan RssLocalFetcher sudah tetap fetch semua feed penuh per run -- limit cuma memangkas berapa
// banyak dari hasil yang sudah diambil itu yang disimpan per saham, jadi menaikkannya tidak
// menambah beban request ke publisher.
Schedule::command('news:fetch --limit=40 --provider=rss_local')
    ->weekdays()
    ->dailyAt('08:50')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

Schedule::command('news:fetch-ojk --limit=50')
    ->everyTwoHours()
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// SESI 1: 09.00–11.30 WIB
// Sync harga live setiap 5 menit saat sesi 1
Schedule::command('stocks:sync-live --all-active')
    ->weekdays()
    ->between('09:00', '11:30')
    ->everyFiveMinutes()
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// SESI 1 NEWS: 10.00 WIB
Schedule::command('news:fetch --limit=30')
    ->weekdays()
    ->dailyAt('10:00')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// MENJELANG BREAK: 11.15 WIB
Schedule::command('news:fetch --limit=20')
    ->weekdays()
    ->dailyAt('11:15')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// AWAL SESI 2: 13.30 WIB
Schedule::command('news:fetch --limit=20 --provider=gnews')
    ->weekdays()
    ->dailyAt('13:30')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// SESI 2: 13.30–15.00 WIB
// Sync harga live setiap 5 menit saat sesi 2
Schedule::command('stocks:sync-live --all-active')
    ->weekdays()
    ->between('13:30', '15:00')
    ->everyFiveMinutes()
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// SESI 2 NEWS: 14.30 WIB
Schedule::command('news:fetch --limit=20')
    ->weekdays()
    ->dailyAt('14:30')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// END-OF-DAY: 15.10 WIB
// Simpan snapshot harian final + hitung ulang indikator
Schedule::command('stocks:fetch-history --days=1')
    ->weekdays()
    ->dailyAt('15:10')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// END-OF-DAY: 15.15 WIB
// Fase X (eksploratif, BUKAN fitur produksi): kumpulkan snapshot top-5 net foreign buy/sell
// hari ini dari infovesta.com. Sumber ini live-only (tanpa riwayat, ?date= diabaikan) dan cuma
// top-5 saham -- tujuannya cuma membangun riwayat sendiri secara bertahap, bukan input model.
// Lihat quant/foreign_flow_tracker/README.md.
Schedule::command('research:collect-foreign-flow')
    ->weekdays()
    ->dailyAt('15:15')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// END-OF-DAY: 15.18 WIB
// Fase AC (prospektif, BUKAN fitur produksi): deteksi otomatis aturan "IHSG+saham crash bareng"
// (Fase AB) untuk BUMI/DEWA, lalu isi outcome sinyal yang horizon-nya sudah lewat. Dijalankan
// setelah harga EOD final (15.10) supaya data hari itu sudah settle. Lihat
// quant/drawdown_bounce_tracker/PROTOCOL.md -- protokol dikunci SEBELUM sinyal live pertama.
Schedule::command('research:detect-drawdown-bounce-signal')
    ->weekdays()
    ->dailyAt('15:18')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

Schedule::command('research:evaluate-drawdown-bounce-signal')
    ->weekdays()
    ->dailyAt('15:19')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// END-OF-DAY: 15.21 WIB
// Alert-only (BUKAN eksekusi order) untuk posisi BUMI/DEWA yang sedang open, terdaftar manual di
// quant/drawdown_bounce_tracker/open_positions.json. User pasang trailing stop-nya sendiri secara
// manual di StockBit -- ini cuma mengirim notifikasi Telegram begitu harga mundur >=4% dari titik
// tertinggi sejak entry.
Schedule::command('research:check-trailing-stop-alert')
    ->weekdays()
    ->dailyAt('15:21')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// END-OF-DAY ML REANALYSIS: 15.20 WIB
// Catatan: 'news:rescore-sentiment' (full-corpus, tanpa filter) sengaja TIDAK
// dijadwalkan lagi -- dulu jalan 2x/hari (12:00 & 15:15) tapi redundan dan makin
// mahal seiring korpus bertambah (rescore ML utk SEMUA artikel, bukan cuma yang
// perlu). 'news:analyze' (hourly, di bawah) dan 'sentiment:reanalyze' di bawah ini
// sudah cukup karena keduanya hanya memroses baris yang field sentimennya NULL.
// Kalau butuh paksa rescore total (mis. lexicon rule-based berubah), jalankan
// manual: php artisan news:rescore-sentiment atau sentiment:reanalyze --force.
Schedule::command('sentiment:reanalyze --include-global')
    ->weekdays()
    ->dailyAt('15:20')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// WEEKEND: Fetch berita seminggu sekali Sabtu pagi
Schedule::command('news:fetch --limit=50')
    ->weekly()
    ->saturdays()
    ->at('09:00')
    ->timezone('Asia/Jakarta')
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// MAINTENANCE: Analisis ulang berita tersimpan setiap jam
// Dipusatkan di file ini agar tidak dobel dengan definisi scheduler lain.
Schedule::command('news:analyze')
    ->hourly()
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// SNAPSHOT DEMO: Perbarui snapshot harga sederhana di luar jam pasar
// Sebelumnya jadwal ini hidup di bootstrap/app.php dan efektif berjalan 23:15 WIB
// karena timezone app masih UTC. Sekarang dieksplisitkan di source-of-truth scheduler.
Schedule::command('stocks:update-snapshots')
    ->dailyAt('23:15')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// WEEKLY PRICE HISTORY REFRESH: data/stocks/*.csv (sumber fitur teknikal training V6A/V6B/BUMI/DEWA)
// ternyata tidak pernah dijadwalkan sama sekali -- ditemukan mentok ~2026-04-22 saat verifikasi
// Fase N (retrain otomatis sudah aman tapi belum benar-benar menyerap harga terbaru). Dijadwalkan
// 1 jam SEBELUM retrain-volatile di bawah supaya kedua jalur retrain (volatile Minggu 02:00,
// produksi Senin 07:00) sama-sama dapat data segar dari satu refresh mingguan ini.
Schedule::command('prediction:refresh-price-history')
    ->weekly()
    ->sundays()
    ->at('01:00')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->runInBackground()
    ->appendOutputTo(storage_path('logs/refresh-price-history.log'));

// WEEKLY ML RETRAIN: model khusus saham volatil BUMI/DEWA.
// Aman/idempotent: command skip otomatis jika belum ada data baru sejak training terakhir.
Schedule::command('prediction:retrain-volatile')
    ->weekly()
    ->sundays()
    ->at('02:00')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->runInBackground()
    ->appendOutputTo(storage_path('logs/retrain-volatile.log'));

// AUTO-RECOVERY: setiap 30 menit, cek apakah scheduler.log stale (proxy scheduler/DB sempat mati)
// dan otomatis backfill berita untuk rentang yang terlewat -- supaya outage MySQL/scheduler tidak
// perlu ditambal manual tiap kali ketahuan (sudah 2x terjadi: 2026-07-10..13, 2026-07-18..19).
Schedule::command('news:auto-recover-gap')
    ->everyThirtyMinutes()
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// FUNDAMENTALS SYNC: mingguan (fundamental tidak berubah harian) -- menggantikan
// FundamentalStockSeeder yang cuma snapshot sekali (2025-12-31, ditemukan basi saat audit
// 2026-07-20 -- harga BBCA saja sudah bergerak -11% sejak itu, PBV/PER yang tampil salah).
Schedule::command('stocks:sync-fundamentals')
    ->weekly()
    ->mondays()
    ->at('06:00')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->appendOutputTo(storage_path('logs/scheduler.log'));

// WEEKLY ML RETRAIN: model produksi V6A/V6B (10 saham resmi). Sebelumnya beku sejak 2026-06-21/22
// tanpa jadwal retrain sama sekali (ditemukan saat audit 2026-07-20) -- berbeda dari BUMI/DEWA yang
// sudah punya prediction:retrain-volatile. Dijadwalkan 1 jam setelah sync fundamental di atas supaya
// tidak berebut resource. Aman/idempotent: command skip otomatis jika belum ada data baru.
Schedule::command('prediction:retrain-production')
    ->weekly()
    ->mondays()
    ->at('07:00')
    ->timezone('Asia/Jakarta')
    ->withoutOverlapping()
    ->runInBackground()
    ->appendOutputTo(storage_path('logs/retrain-production.log'));
