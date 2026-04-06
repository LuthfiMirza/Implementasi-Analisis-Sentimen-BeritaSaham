# Sentimena – Dashboard Analisis Sentimen Berita Saham IDX

Dashboard fullstack untuk skripsi Sistem Informasi: analisis sentimen berita terhadap pergerakan harga saham Indonesia (IDX). Dibangun dengan Laravel 11, Blade, TailwindCSS (dark), Alpine.js, Chart.js, dan MySQL, dengan role **admin** dan **user**, watchlist pribadi, chart harga (TradingView/internal), agregasi berita, sentimen rule-based, serta modul admin CRUD.

## Fitur Utama
- Auth (Breeze) dengan role `admin` / `user`, session database.
- Dashboard desktop-first: watchlist kiri, chart tengah (TradingView/internal Chart.js), berita & ringkasan sentimen kanan, insight otomatis.
- Pencarian & autocomplete saham (kode/nama), default saham BBCA.
- Watchlist pribadi tambah/hapus.
- Berita dengan label sentimen, summary, sumber, dan tautan.
- Analisis sentimen rule-based (lexicon ID) + placeholder Python API.
- Analytics: komposisi sentimen, tren per hari, top emiten diberitakan.
- Admin: CRUD saham, sumber berita, artikel; pengaturan provider & mode chart; log fetch.
- Commands & scheduler: fetch berita mock/RSS/manual, analisis sentimen, update snapshot harga.
- Seeder demo: admin, user, 10 saham populer IDX, harga 30 hari, berita multi-sentimen, watchlist contoh.

## Stack
- PHP 8.3, Laravel 11, MySQL, Eloquent ORM
- Blade, TailwindCSS, Alpine.js, Chart.js
- Laravel HTTP Client, Queue (database), Scheduler
- PHPUnit test minimal (sentiment analyzer)

## Instalasi Lokal
1) **Persiapan**: PHP 8.3+, MySQL, Composer, Node 18+ & npm.  
2) **Clone & masuk folder**: `cd laravel-app`  
3) **Env**: salin `.env.example` ke `.env`, set DB MySQL (`sentimena_dashboard`) dan kredensial.  
4) **Composer**: `composer install` (sudah diunduh saat scaffold, jalankan lagi jika perlu).  
5) **Key**: `php artisan key:generate` (sudah otomatis, aman untuk re-run).  
6) **Migrate & seed**: `php artisan migrate --seed` (membuat user, data saham, harga, berita).  
7) **Assets**: `npm install` lalu `npm run dev` (atau `npm run build` untuk produksi).  
8) **Queue**: `php artisan queue:work` (driver database).  
9) **Scheduler (dev)**: `php artisan schedule:work` atau cron `* * * * * php artisan schedule:run >> /dev/null 2>&1`.

### Akun Demo
- Admin: `admin@sentimena.test` / `password`  
- User: `user@sentimena.test` / `password`

## Konfigurasi Penting
- `NEWS_PROVIDER` (`mock|rss|manual`), `NEWS_API_KEY`, `NEWS_API_BASE_URL`
- `FINNHUB_API_KEY`, `FINNHUB_BASE_URL` (contoh: https://finnhub.io/api/v1/company-news), set `NEWS_PROVIDER=finnhub` untuk pakai sumber ini
- `STOCK_CHART_MODE` (`tradingview|internal`)
- `TRADINGVIEW_DEFAULT_EXCHANGE` (default `IDX`)
- `PYTHON_SENTIMENT_ENDPOINT` (opsional, fallback ke rule-based)

## Perintah CLI
- `php artisan news:fetch --limit=5` – tarik berita untuk semua saham aktif via provider konfigurasi.
- `php artisan news:analyze` – analisis sentimen artikel baru (gunakan `--all` untuk reprocess semua).
- `php artisan stocks:update-snapshots --days=1` – buat snapshot harga demo harian.

## Arsitektur Singkat
- **Services**:  
  - `Services/News` (fetcher interface + Mock/RSS/Manual, agregator simpan DB).  
  - `Services/Sentiment` (interface, rule-based analyzer, Python API placeholder, summary builder).  
  - `Services/Stocks` (price series, dashboard builder), `WatchlistService`.
- **Controllers**: dashboard, stocks, watchlist, analytics, news, admin CRUD, system settings.
- **Jobs/Commands**: fetch berita, analisis sentimen, update harga; dijadwalkan via scheduler.
- **UI**: Blade dark layout, grid watchlist–chart–news, Chart.js internal mode, TradingView iframe mode, reusable glass panels.

## Pengembangan Lanjutan
1. **Integrasi API berita Indonesia**: tambahkan fetcher baru yang memanfaatkan `NEWS_API_BASE_URL/NEWS_API_KEY`, map payload ke `NewsArticle`, gunakan `NewsAggregationService`.
2. **Integrasi data saham IDX real**: hubungkan API harga (IDX/data vendor), simpan ke `stock_prices`, jalankan `stocks:update-snapshots` custom via scheduler.
3. **Sentimen Python**: deploy service NLP (FastAPI), set `PYTHON_SENTIMENT_ENDPOINT`, binding ke `PythonApiSentimentAnalyzer` untuk hasil model.
4. **Prediksi harga**: tambahkan modul ML sederhana (regresi/LSTM) yang membaca seri harga & sentimen rata-rata harian; simpan hasil ke tabel baru untuk backtesting.
5. **Deploy di Hostinger**: gunakan PHP 8.3, set `.env` produksi, jalankan `php artisan migrate --force`, `npm run build`, set cron untuk `schedule:run`, daemon queue via `supervisor`/`nohup php artisan queue:work`.
# Implementasi-Analisis-Sentimen-Berita
