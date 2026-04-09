# Sentimena – Dashboard Analisis Sentimen Berita Saham IDX

Dashboard fullstack untuk skripsi Sistem Informasi: analisis sentimen berita terhadap pergerakan harga saham Indonesia (IDX). Dibangun dengan Laravel 11, Blade, TailwindCSS (dark), Alpine.js, Chart.js, dan MySQL, dengan role **admin** dan **user**, watchlist pribadi, chart harga (TradingView/internal), agregasi berita multi-sumber, **hybrid sentiment engine**, analytics harga–sentimen, baseline prediksi, serta modul admin CRUD.

## Fitur Utama
- Auth (Breeze) dengan role `admin` / `user`, session database.
- Dashboard desktop-first: watchlist kiri, chart tengah (TradingView/internal Chart.js), berita & ringkasan sentimen kanan, insight otomatis.
- Pencarian & autocomplete saham (kode/nama), default saham BBCA.
- Watchlist pribadi tambah/hapus, sparkline sentimen mini, badge status keputusan, alert lonjakan berita negatif 24 jam.
- Berita multi-source dengan label sentimen, summary, sumber, tautan, metode sentiment + confidence.
- **Hybrid Sentiment Engine**: rule-based (lexicon finansial + negasi) + optional Python API + fallback; simpan meta (confidence, matched terms, reason, method, analyzed_at).
- Analytics harga–sentimen: komposisi, tren harian, korelasi same-day & lag (H+1/H+3/H+7), event study, volume impact, weighted sentiment (sumber/headline/recency).
- Decision Support transparan: MA5/MA20, RSI, support/resistance, breakout/breakdown, scoring berbobot (sentimen 35%, tren 30%, momentum 20%, volume berita 15%), faktor pendukung/pelemah/risiko/invalidation, narasi & skenario.
- Baseline Prediction: feature builder harian, heuristic direction (up/flat/down) + integrasi siap Python prediction endpoint, skenario bullish/netral/bearish.
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
- `NEWS_PROVIDER` (`mock|rss|manual|newsapi|finnhub|rss_local|gdelt|multi`), `NEWS_API_KEY`, `NEWS_API_BASE_URL`
- `FINNHUB_API_KEY`, `FINNHUB_BASE_URL` (contoh: https://finnhub.io/api/v1/company-news), set `NEWS_PROVIDER=finnhub` untuk pakai sumber ini
- `NEWS_RSS_SOURCES` (opsional, pisah `;`/`,`, jika kosong akan pakai default: CNBC Indonesia market RSS, Kontan finansial, Bisnis finansial)
- `GDELT_BASE_URL` (default: https://api.gdeltproject.org/api/v2/doc/doc)
- `NEWS_DOMAIN_BLACKLIST` / `NEWS_DOMAIN_WHITELIST` (opsional, pisah `;`/`,` untuk memaksa filter domain)
- `STOCK_CHART_MODE` (`tradingview|internal`)
- `TRADINGVIEW_DEFAULT_EXCHANGE` (default `IDX`)
- Sentimen: `SENTIMENT_ENGINE=rule_based|python|hybrid`, `PYTHON_SENTIMENT_ENDPOINT`, `PYTHON_SENTIMENT_TIMEOUT`
- Prediksi: `PREDICTION_ENGINE=baseline`, `PYTHON_PREDICTION_ENDPOINT`, `PYTHON_PREDICTION_TIMEOUT`

## Perintah CLI & Test
- `php artisan news:fetch --limit=5` – tarik berita untuk semua saham aktif via provider konfigurasi.
- `php artisan news:analyze` – analisis sentimen artikel baru (gunakan `--all` untuk reprocess semua).
- `php artisan stocks:update-snapshots --days=1` – buat snapshot harga demo harian.
- Test: `./vendor/bin/phpunit --testsuite Unit,Feature` (pastikan DB testing siap).

## Arsitektur Berita & Sentimen (Multi-Source)
- **Fetcher sumber**:
  - `NewsApiFetcher` (NewsAPI, bahasa id → en → fallback)
  - `FinnhubNewsFetcher` (ticker otomatis tambah `.JK`)
  - `RssLocalFetcher` (RSS CNBC Indonesia, Kontan, Bisnis; bisa override via `NEWS_RSS_SOURCES`)
  - `GdeltFetcher` (filter bahasa Indonesia/English)
  - `Mock/Manual/RSS` bawaan untuk demo
- **Aggregator**: `NewsAggregationService`
  - `NEWS_PROVIDER=multi` akan memanggil berurutan: `newsapi`, `rss_local`, `gdelt`, `finnhub`, deduplikasi `source_url`
  - Analisis sentimen rule-based otomatis saat simpan (jika label/score belum ada)
  - Filter relevansi: wajib mengandung kata kunci emiten; ada pengecualian per emiten (mis. GOTO skip “goto islands”, “camellia”, dll)
  - Dukungan whitelist/blacklist domain via env
- **Mapping saham**: `StockKeywordMapper`
  - Kata kunci: kode + nama emiten (dibersihkan) + alias override per saham populer (BBCA, BBRI, BMRI, TLKM, ASII, GOTO, UNVR, INDF, ICBP, ADRO)
  - Query builder: `"kw1" OR "kw2" ...` untuk API/news search
  - Exclusion keywords per saham untuk hindari konteks salah
- **Alur**: Fetch → filter relevan (keyword + exclusion + domain) → dedup → simpan `news_articles` → analisis sentimen → tampil di dashboard/news/analytics → masuk ke model decision support.
- **Bahasa**: prioritas Indonesia & English (NewsAPI: id → en; GDELT: sourcelang indonesia/english).
- **Caching**: Finnhub memakai cache 5 menit untuk hindari rate limit.

## Cara Menarik Berita yang Relevan
1) Set `.env` untuk sumber yang diinginkan:
```
NEWS_PROVIDER=multi
NEWS_API_KEY=isi_key
NEWS_API_BASE_URL=https://newsapi.org/v2/everything
FINNHUB_API_KEY=isi_key
NEWS_RSS_SOURCES=https://www.cnbcindonesia.com/market/rss;https://www.kontan.co.id/rss/finansial;https://www.bisnis.com/rss/finansial
GDELT_BASE_URL=https://api.gdeltproject.org/api/v2/doc/doc
# Opsional
NEWS_DOMAIN_BLACKLIST=japantrends.com
```
2) Bersihkan cache: `php artisan config:clear && php artisan cache:clear`
3) Jalankan: `php artisan news:fetch --limit=5`
4) Cek `/news` atau `/dashboard`; sumber mock tidak dipakai jika provider bukan `mock`.

## Decision Support & Analytics
- `SentimentPriceAnalyticsService`: average/weighted sentiment, dominasi, hitung volume berita, return harian/kumulatif, volatilitas, tren harga/sentimen, korelasi same-day & lag (H+1/H+3/H+7), event study lonjakan sentimen, volume→volatilitas.
- `DecisionSupportService`: kombinasikan sentimen & teknikal (MA5/20, RSI, support/resistance, breakout), scoring berbobot, status (Bullish Support / Wait and See / Warning), confidence (Rendah/Sedang/Tinggi), faktor pendukung/pelemah/risiko, invalidation rules, narasi & skenario.
- `FeatureBuilderService` + `BaselinePredictionService`: dataset fitur harian + prediksi arah (up/flat/down) berbasis heuristik, siap integrasi Python prediction endpoint. `PREDICTION_ENGINE=python` akan mencoba endpoint Python, fallback ke baseline.
- Halaman `/analytics?code=BBCA&period=30` menampilkan overlay harga–sentimen–volume, korelasi lag, event marker, panel keputusan, prediksi indikatif, headline positif/risk, insight hubungan sentimen vs return.

## Arsitektur Singkat
- **Services**:  
  - `Services/News` (fetcher multi-sumber + agregator simpan DB).  
  - `Services/Sentiment` (Hybrid analyzer + Python optional + rule-based upgrade, summary).  
  - `Services/Analytics` (SentimentPriceAnalyticsService, DecisionSupportService).  
  - `Services/Prediction` (FeatureBuilderService, BaselinePredictionService).  
  - `Services/Stocks` (price series, dashboard builder), `WatchlistService` (analytics + alert).
- **Controllers**: dashboard, stocks, watchlist, analytics, news, admin CRUD, system settings.
- **Jobs/Commands**: fetch berita, analisis sentimen, update harga; dijadwalkan via scheduler.
- **UI**: Blade dark layout, watchlist sparkline + alert, analytics lengkap (korelasi lag, event), Chart.js internal mode, TradingView iframe mode.

## Pengembangan Lanjutan
1. **Integrasi API berita Indonesia**: tambahkan fetcher baru yang memanfaatkan `NEWS_API_BASE_URL/NEWS_API_KEY`, map payload ke `NewsArticle`, gunakan `NewsAggregationService`.
2. **Integrasi data saham IDX real**: hubungkan API harga (IDX/data vendor), simpan ke `stock_prices`, jalankan `stocks:update-snapshots` custom via scheduler.
3. **Sentimen Python**: deploy service NLP (FastAPI), set `PYTHON_SENTIMENT_ENDPOINT`, binding ke `PythonApiSentimentAnalyzer` untuk hasil model.
4. **Prediksi harga**: tambahkan modul ML sederhana (regresi/LSTM) yang membaca seri harga & sentimen rata-rata harian; simpan hasil ke tabel baru untuk backtesting.
5. **Deploy di Hostinger**: gunakan PHP 8.3, set `.env` produksi, jalankan `php artisan migrate --force`, `npm run build`, set cron untuk `schedule:run`, daemon queue via `supervisor`/`nohup php artisan queue:work`.
# Implementasi-Analisis-Sentimen-Berita
