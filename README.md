# Sentimena – Dashboard Analisis Sentimen dan Ranking Teknikal Saham IDX

Dashboard fullstack untuk skripsi Sistem Informasi yang menggabungkan agregasi berita saham Indonesia, analisis sentimen, evaluasi model, relative technical strength ranking, backtest DSS, dan trade journal. Aplikasi utama dibangun dengan Laravel 13, Blade, TailwindCSS, Alpine.js, Chart.js, dan MySQL; komponen machine learning dijalankan melalui service Python/FastAPI untuk endpoint `/predict` dan `/rank-stocks`.

## Fitur Utama
- Auth (Breeze) dengan role `admin` dan `user`, session database, serta modul admin CRUD.
- Dashboard utama dengan chart harga, ringkasan berita, insight sentimen, dan polling quote live/snapshot.
- Berita terkini multi-provider (`rss_local`, `ojk`, `newsapi`, `gnews`, `gdelt`, `finnhub`) dengan filter relevansi, quality score, dedup, dan label sentimen.
- Watchlist pribadi dengan panel **Relative Strength Ranking (5-Day Horizon)** yang menampilkan ranking teknikal lintas ticker, score, dan label kandidat teknikal.
- Evaluasi model, evaluasi sentimen, evaluasi sistem, dan backtest DSS untuk analisis perilaku model dan hubungan harga-sentimen.
- Hybrid sentiment engine: rule-based + optional Python API + fallback, lengkap dengan confidence, matched terms, method, dan metadata kualitas artikel.
- Baseline Prediction & Technical Ranking: feature builder harian, walk-forward model (v1-v5, terbaik: ranking random_forest Spearman=0.037), integrasi FastAPI di `quant/prediction_api.py`, panel ranking teknikal di halaman watchlist, dan paper trading log harian otomatis.
- Trade Journal untuk pencatatan trade manual, serta utilitas paper trading manual yang tetap diposisikan sebagai tooling riset non-strategy.

## Matriks Fitur, Implementasi, dan Bukti Pengujian
| Fitur | File Utama | Test/Artifact Bukti |
|-------|-----------|---------------------|
| Auth + Role | `app/Http/Middleware/AdminMiddleware.php` | `tests/Feature/AdminMiddlewareTest.php` |
| Hybrid Sentiment | `app/Services/Sentiment/HybridSentimentAnalyzer.php` | `tests/Unit/SentimentAnalyzerTest.php` |
| Analytics | `app/Services/Analytics/SentimentPriceAnalyticsService.php` | `tests/Feature/AnalyticsPageTest.php`, `tests/Unit/SentimentPriceAnalyticsServiceTest.php` |
| Decision Support | `app/Services/Analytics/DecisionSupportService.php` | `tests/Unit/DecisionSupportServiceTest.php`, `tests/Feature/EvaluationReportTest.php` |
| Ranking Teknikal | `app/Services/Prediction/ResearchRankingService.php` | `tests/Unit/ResearchRankingServiceTest.php` |
| Paper Trading Log | `app/Services/PaperTrading/PaperTradingLogService.php` | `tests/Unit/PaperTradingLogServiceTest.php` |
| Model Prediksi v5 | `quant/prediction_api.py` | `output/prediction_research/baseline_v5_ranking_scorecard.json` |
| Walk-Forward Eval | `quant/train_prediction_models.py` | `output/prediction_research/model_comparison_v3.txt`, `output/prediction_research/model_comparison_v4b.txt`, `output/prediction_research/model_ranking_v5.txt` |

## Modul UI Aktif
- `Dashboard`: ringkasan pasar, chart, berita, dan insight otomatis.
- `Berita Terkini`: listing berita hasil agregasi multi-source dengan metadata sentimen.
- `Watchlist`: watchlist pribadi dan panel ranking teknikal v5.
- `Prediksi`: pembacaan arah model `/predict` untuk satu ticker.
- `Evaluasi Model`: evaluasi performa prediksi dan DSS.
- `Evaluasi Sentimen`: evaluasi hubungan sentimen terhadap return.
- `Backtest DSS`: simulasi historis berbasis window terbatas dan cache hasil.
- `Evaluasi Sistem`: laporan ringkas kualitas sistem/evidence evaluasi.
- `Trade Journal`: pencatatan trade manual dan hasil penutupan trade.

## Stack
- PHP 8.3, Laravel 13, MySQL, Eloquent ORM
- Blade, TailwindCSS, Alpine.js, Chart.js, Vite
- Python 3, FastAPI, pandas, scikit-learn, joblib
- Laravel HTTP Client, Queue (database), Scheduler, file cache untuk route berat

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
- `NEWS_PROVIDER` (`mock|rss|manual|newsapi|finnhub|rss_local|gdelt|ojk|multi`), `NEWS_API_KEY`, `NEWS_API_BASE_URL`
- `GNEWS_API_KEY`, `GNEWS_BASE_URL`, `GNEWS_LANGUAGE`, `GNEWS_COUNTRY`
- `NEWS_RSS_SOURCES`, `NEWS_RSS_TIMEOUT`, `NEWS_RSS_USER_AGENT`
- `NEWS_RELEVANCE_THRESHOLD`, `NEWS_RELEVANCE_HIGH`, `NEWS_FINAL_QUALITY_THRESHOLD`
- `STOCK_CHART_MODE`, `TRADINGVIEW_DEFAULT_EXCHANGE`
- Sentimen: `SENTIMENT_ENGINE=rule_based|python|hybrid`, `PYTHON_SENTIMENT_ENDPOINT`, `PYTHON_SENTIMENT_TIMEOUT`
- Prediksi arah: `PREDICTION_ENGINE=baseline`, `PYTHON_PREDICTION_ENDPOINT`, `PYTHON_PREDICTION_TIMEOUT`
- Ranking teknikal: `PYTHON_RANKING_ENDPOINT`, `PREDICTION_RANKING_MODEL_DIR`, `PREDICTION_RANKING_MODEL_VERSION`
- FastAPI model dir fallback: `PREDICTION_MODEL_DIR` untuk `/predict`

`PYTHON_RANKING_ENDPOINT` secara default bisa diturunkan dari `PYTHON_PREDICTION_ENDPOINT` dengan mengganti suffix `/predict` menjadi `/rank-stocks`.

### Contoh Endpoint Python
**Sentiment (POST ke `PYTHON_SENTIMENT_ENDPOINT`)**
```json
{
  "text": "Laba tumbuh dan dividen diumumkan",
  "context": {
    "title": "Laba tumbuh",
    "summary": "Perusahaan mencatat kenaikan laba",
    "body": "..."
  },
  "language": "id"
}
```
Respon yang valid:
```json
{
  "label": "positive",          // wajib: positive|neutral|negative
  "score": 0.72,                // -1..1
  "confidence": 0.88,           // 0..1
  "matched_positive_terms": ["laba tumbuh"],
  "matched_negative_terms": [],
  "reason_summary": "Model yakin karena kata laba tumbuh"
}
```

**Prediction (POST ke `PYTHON_PREDICTION_ENDPOINT`)**
```json
{
  "features": {
    "return_5d": 0.021,
    "return_20d": 0.084,
    "atr_ratio": 0.031,
    "price_vs_ema20_pct": 0.014,
    "regime_duration": 7
  }
}
```
Respon yang valid:
```json
{
  "predicted_direction": "up",  // wajib: up|down|flat
  "probability": 0.78,          // atau "confidence"
  "basis": "Model logistic_regression/random_forest",
  "scenario_bullish": "...",
  "scenario_neutral": "...",
  "scenario_bearish": "..."
}
```

**Ranking teknikal (POST ke `PYTHON_RANKING_ENDPOINT`)**
```json
{
  "stocks": [
    {
      "ticker": "BBCA",
      "features": {
        "return_5d": 0.021,
        "return_20d": 0.084,
        "atr_ratio": 0.031,
        "price_vs_ema20_pct": 0.014,
        "regime_duration": 7
      }
    },
    {
      "ticker": "BBRI",
      "features": {
        "return_5d": 0.015,
        "return_20d": 0.062,
        "atr_ratio": 0.028,
        "price_vs_ema20_pct": 0.010,
        "regime_duration": 5
      }
    }
  ]
}
```
Respon yang valid:
```json
{
  "ranked": [
    { "ticker": "BBCA", "rank": 1, "score": 0.6123, "signal": "strong_candidate" },
    { "ticker": "BBRI", "rank": 2, "score": 0.5341, "signal": "candidate" }
  ],
  "model_version": "v5_ranking",
  "horizon_days": 5,
  "generated_at": "2026-04-26"
}
```

Sinyal ranking dibaca sebagai indikator probabilistik relative technical strength, bukan janji harga akan naik. Jika endpoint Python gagal, Laravel akan menandai ranking sebagai unavailable dan tidak memaksakan fallback ranking semu.

## Perintah CLI & Test
- `php artisan news:fetch --limit=5` – tarik berita untuk semua saham aktif via provider konfigurasi (opsi: `--provider=newsapi|rss_local|gnews`, `--debug` untuk ringkasan skor/band).
- `php artisan news:fetch-ojk --limit=20` – tarik berita OJK terbaru sebagai **macro/global news** (`stock_id = null`).
- `php artisan news:fetch-ojk --backfill --from=2026-02-01 --to=2026-04-15 --limit=100 --scan-limit=200 --debug` – backfill historis OJK dari halaman resmi OJK untuk evaluasi/backtest.
- `php artisan news:analyze` – analisis sentimen artikel baru (gunakan `--all` untuk reprocess semua).
- `php artisan stocks:update-snapshots --days=1` – buat snapshot harga demo harian.
- `php artisan news:rescore-quality --days=180 [--stock=BBCA] [--force]` – backfill metadata kualitas & provider untuk artikel yang belum lengkap.
- `php artisan news:rescore-sentiment` – reskor sentimen seluruh artikel dengan leksikon finansial terkini.
- `php artisan stocks:fetch-history --days=90` – tarik harga historis 1D (Yahoo Finance) untuk semua saham aktif.
- Test: `./vendor/bin/phpunit --testsuite Unit,Feature` (pastikan DB testing siap).
- Evaluasi ringkas (laporan JSON/console): `php artisan evaluate:report BBCA --period=30 --output=bbca-30.json`
- Evaluasi tanpa macro OJK: `php artisan evaluate:report BBCA --period=30 --no-macro`
- Checklist QA manual UI: `docs/QA_CHECKLIST.md`
- Komparasi weighted vs average sentiment: `php artisan evaluation:sentiment-compare BBCA --period=30 --save=bbca-weighted.json`
- Komparasi tanpa macro OJK: `php artisan evaluation:sentiment-compare BBCA --period=30 --no-macro`
- Coverage berita: `php artisan news:coverage-report --days=30 [--stock=BBCA] [--save=coverage.json]` (melaporkan artikel per saham, band kualitas, sentimen, provider terbanyak, kelayakan evaluasi)
- Metadata berita: setiap artikel menyimpan `source_provider`, `relevance_score`, `final_quality_score`, `quality_band`, dan skor konteks lain. Jika coverage report menampilkan `unknown`, jalankan `news:rescore-quality` untuk melengkapi metadata atau periksa provider yang belum terkonfigurasi.
- Tuning kualitas: threshold default disetel (`final_quality_threshold` 0.40, `quality_high` 0.55, `quality_medium` 0.40) dengan bobot final quality yang menaikkan entity/market context. Jika data terlalu ketat/longgar, sesuaikan env `NEWS_FINAL_QUALITY_THRESHOLD`, `NEWS_QUALITY_HIGH`, `NEWS_QUALITY_MEDIUM`.
- Provider & debugging:
  - Provider yang didukung: `rss_local`, `ojk`, `newsapi`, `gnews`, `finnhub`, `gdelt` (opsional legacy `api` akan dinormalisasi sebagai `newsapi_legacy`).
  - Gunakan `php artisan news:fetch --provider=newsapi --debug` untuk melihat query kosong atau status gagal; log akan menampilkan attempt, query, language, status code jika respon kosong/gagal.
  - Coverage report mengelompokkan provider secara spesifik; `unknown` hanya muncul jika provider tidak tersedia di payload.
- Quote live vs snapshot:
  - Endpoint JSON: `GET /api/stocks/{CODE}/quote` (mengembalikan last/open/high/low/volume/change/change_percent + source + is_live + fetched_at). Menggunakan live provider jika ada, fallback ke snapshot `stock_prices`.
  - Polling frontend: dashboard akan memanggil endpoint ini tiap ~20 detik untuk memperbarui kartu harga; badge “Backend Live/Snapshot” menunjukkan sumber, “Live Chart: TradingView” tetap menjadi acuan live visual.
  - Pastikan env: `STOCK_DATA_SOURCE=live`, `LIVE_MARKET_PROVIDER=http|demo`, `MARKET_DATA_BASE_URL=...`, `MARKET_DATA_API_KEY=...`, `MARKET_DATA_TIMEOUT=8`, `FALLBACK_TO_SNAPSHOT=true`. Uji dengan `curl http://localhost/api/stocks/BBCA/quote` dan lihat `is_live`.

## Ranking Teknikal dan Paper Trading
- Ranking teknikal v5 dipakai untuk membandingkan kekuatan relatif antarticker pada horizon 5 hari, bukan untuk mengklaim rekomendasi investasi.
- Panel watchlist menggunakan `ResearchRankingService` yang mengirim payload live ke endpoint `/rank-stocks` lalu menampilkan rank, score, dan signal `strong_candidate|candidate|neutral|avoid`.
- Baseline research saat ini menempatkan model ranking sebagai basket selector. Precision top-3 historis yang dicantumkan di UI adalah konteks evaluasi, bukan jaminan performa live.
- Utilitas paper trading tetap manual dan tidak dijadwalkan otomatis pada current roadmap karena strategy path masih berada dalam documented pause.
- Snapshot paper trading harian: `php artisan paper-trading:record-snapshot --date=YYYY-MM-DD`
- Evaluasi hasil snapshot: `php artisan paper-trading:evaluate-result --date=YYYY-MM-DD`
- Ringkasan paper trading: `php artisan paper-trading:summarize`
- Log paper trading disimpan di `output/paper_trading/` untuk snapshot JSON dan `results_log.csv` untuk evaluasi lintas siklus.

## Evaluasi Ilmiah (Sentimen & Prediksi)
- Jalankan `php artisan evaluate:report BBCA --period=30` untuk ringkasan korelasi, distribusi metode sentimen (python vs fallback), tren harga/sentimen, status decision support, dan prediksi saat ini. Tambahkan `--output=nama.json` untuk menyimpan ke `storage/app/evaluations/`.
- Analisis korelasi: lihat same-day dan lag H+1/H+3/H+7 pada laporan untuk indikasi hubungan sentimen-return.
- Event study: cek hitungan event positif/negatif dan impact H+1/H+3/H+7 pada laporan.
- Jika punya label ground-truth sentimen atau arah harga, Anda bisa memperluas evaluator dengan perhitungan akurasi/F1, hit rate prediksi, atau metrik ranking seperti top-k precision dan long-short spread.

## Status Riset Sentimen
- Roadmap resmi saat ini menempatkan proyek pada `technical_prediction_research` lane, bukan strategy promotion path.
- Evaluasi sentimen di UI saat ini terutama mengukur konsistensi internal `ML vs rule-based`, distribusi label, disagreement, dan coverage berita.
- Untuk prediction research, fitur sentimen belum menjadi driver utama karena coverage efektif historis sangat rendah dibanding total baris dataset teknikal.
- Implikasi praktisnya: sentimen tetap berguna untuk layer informasi, monitoring berita, dan evaluasi kualitas artikel, tetapi baseline ranking/prediction saat ini lebih bertumpu pada fitur teknikal.
- Paper trading, retest, dan strategy promotion claim tetap tidak terbuka otomatis hanya karena hasil prediction research atau ranking membaik.

## Arsitektur Berita & Sentimen (Multi-Source)
- **Fetcher sumber**:
  - `NewsApiFetcher` (NewsAPI, bahasa id → en → fallback)
  - `GNewsFetcher` (GNews search, language/country filter)
  - `FinnhubNewsFetcher` (ticker otomatis tambah `.JK`)
  - `OjkRssFetcher` (RSS + halaman resmi OJK; berita regulator disimpan sebagai macro/global news)
  - `RssLocalFetcher` (RSS CNBC Indonesia, Kontan, Bisnis; bisa override via `NEWS_RSS_SOURCES`)
  - `GdeltFetcher` (filter bahasa Indonesia/English)
  - `Mock/Manual/RSS` bawaan untuk demo
- **Aggregator**: `NewsAggregationService`
  - `NEWS_PROVIDER=multi` akan memanggil berurutan: `rss_local`, `ojk`, `gnews`, `newsapi`, `gdelt`, `finnhub`, deduplikasi berlapis (source_url/canonical → hash judul ternormalisasi → judul+domain+jendela tanggal)
  - Analisis sentimen rule-based otomatis saat simpan (jika label/score belum ada)
  - Filter relevansi: wajib mengandung kata kunci emiten; ada pengecualian per emiten (mis. GOTO skip “goto islands”, “camellia”, dll)
  - Filter bahasa: hanya id/en yang diterima; bahasa lain ditolak
  - Market context filter: wajib ada konteks pasar modal (saham, emiten, IHSG, laba, dividen, rights issue, buyback, dll)
  - Quality scoring transparan: relevance_score, entity_match_score, market_context_score, language_score, source_weight → final_quality_score + band high/medium/low. Artikel di bawah `NEWS_FINAL_QUALITY_THRESHOLD` dibuang; default sorting /news berdasarkan final_quality_score desc lalu published_at desc.
  - Artikel `ojk_rss` yang lolos disimpan sebagai **macro/global news** (`stock_id = null`) agar dapat dibaca semua saham aktif tanpa duplikasi per emiten.
  - Dukungan whitelist/blacklist domain via env
  - Relevance scoring transparan: ticker/nama/alias di judul/badan, konteks kata kunci (saham, emiten, idx, bei, ihsg, dividen, laba, pendapatan, rights issue, buyback, target harga, rekomendasi), bobot sumber, kualitas struktur (judul/published/summary/url). Output: `relevance_score`, `relevance_band`, `source_weight`, `matched_keywords`. Artikel di bawah `NEWS_RELEVANCE_THRESHOLD` di-drop.
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

### Debug RSS Lokal
- Pastikan feed mengembalikan XML/RSS/Atom; jika HTML/redirect/empty, sistem otomatis skip dan log per feed.
- Set `NEWS_RSS_USER_AGENT` bila feed menolak UA default; atur `NEWS_RSS_TIMEOUT` jika sering timeout.
- Gunakan `NEWS_RSS_SOURCES` untuk override daftar feed; pisahkan dengan `;` atau `,`.

### Relevance Scoring & Threshold
- Skor dihitung dari: kemunculan ticker/nama/alias di judul/badan, kata kunci konteks pasar, bobot sumber, kualitas struktur (judul/published/summary/url).
- Output: `relevance_score` (0..1), `relevance_band` (high/medium/low), `source_weight`, `matched_keywords`.
- Artikel dengan skor < `NEWS_RELEVANCE_THRESHOLD` tidak disimpan; band high jika skor >= `NEWS_RELEVANCE_HIGH`.
- Prioritas sumber multi: NewsAPI, GNews, RSS lokal, GDELT, Finnhub (dapat diubah via `config/news.php`).

### Evaluasi Weighted vs Average Sentiment
- Command: `php artisan evaluation:sentiment-compare {CODE} --period=30 [--save=report.json]`
- Metrik: korelasi same-day & lag H+1/H+3/H+7 (avg vs weighted), event study lonjakan sentimen (avg vs weighted), backtest sinyal arah bullish/netral/bearish di H+1/H+3/H+7 (directional accuracy, hit rate, avg return per sinyal).
- Prediction impact (heuristik): Mode A (tanpa weighted_sentiment_quality) vs Mode B (dengan), dibandingkan dengan arah return H+1 terakhir.
- Output JSON + narasi ringkas; bisa disimpan ke `storage/app/evaluations/`.

## OJK Macro News
- `ojk_rss` diposisikan sebagai berita regulator resmi OJK, sehingga diperlakukan sebagai **macro/global news** dan disimpan dengan `stock_id = null`.
- Artikel global ini ikut terbaca oleh analytics, evaluation report, sentiment comparison, dashboard/news listing, dan backtest melalui scope konteks saham.
- Untuk uji dampak OJK di evaluasi:
  - Backtest UI: gunakan query `?include_macro_news=1` atau `?include_macro_news=0`
  - Evaluation CLI: gunakan `--no-macro` untuk membandingkan hasil tanpa OJK
  - Sentiment comparison CLI: gunakan `--no-macro` untuk membandingkan hasil tanpa OJK

### Live Fetch OJK
1. Jalankan `php artisan news:fetch-ojk --limit=20 --debug`
2. Verifikasi artikel OJK masuk ke DB:
```bash
php artisan tinker --execute="
echo App\Models\NewsArticle::where('source_provider','ojk_rss')->count();
"
```
3. Artikel yang tersimpan seharusnya `stock_id = null` dan `source_provider = ojk_rss`.

### Backfill Historis OJK
Gunakan backfill jika Anda ingin menguji dampak macro news OJK pada periode backtest tertentu, misalnya `Februari 2026` sampai `April 2026`.

```bash
php artisan news:fetch-ojk \
  --backfill \
  --from=2026-02-01 \
  --to=2026-04-15 \
  --limit=100 \
  --scan-limit=200 \
  --debug
```

Catatan:
- Backfill hanya memakai domain resmi `ojk.go.id`.
- Fetcher akan membaca listing resmi OJK yang memiliki tanggal publikasi, lalu memproses hanya artikel dalam rentang tanggal yang diminta.
- Command aman dijalankan berulang karena penyimpanan menggunakan dedup berbasis `source_url`.

### Rerun Backtest Sesudah Backfill
1. Ambil atau backfill berita OJK.
2. Bersihkan view cache jika perlu: `php artisan view:clear`
3. Bandingkan backtest:
   - Dengan macro: `/backtest?code=BBCA&include_macro_news=1`
   - Tanpa macro: `/backtest?code=BBCA&include_macro_news=0`
4. Untuk evaluasi console:
```bash
php artisan evaluate:report BBCA --period=30
php artisan evaluate:report BBCA --period=30 --no-macro
```

### Narasi Skripsi untuk Macro OJK
- Berita `ojk_rss` digunakan sebagai sinyal regulasi makro yang dapat memengaruhi seluruh saham, sehingga tidak diikat ke satu emiten tertentu.
- Artikel OJK disimpan sebagai berita global (`stock_id = null`) dan diikutsertakan dalam analisis hanya ketika mode evaluasi `include_macro_news` aktif.
- Dengan pendekatan ini, peneliti dapat membandingkan performa model sebelum dan sesudah memasukkan konteks berita regulator resmi pada rentang waktu yang sama.

## Phase A Close-Out Operasional
- Baseline final Phase A dibekukan ke `output/phase_a_baseline_final.json` dan fallback statisnya tersedia di `config/phase_a_baseline.json`.
- Baseline memuat threshold volume spike default, strict mode default, adaptive threshold by group, min trade floor, readiness, dan status baseline (`draft|provisional|final`).
- Generate baseline final dari artifact sweep/tuning:
```bash
python3 -m quant.freeze_phase_a_baseline --output-dir output
```
- Evaluasi Python dapat membaca baseline final secara opsional tanpa memecahkan perilaku lama:
```bash
python3 -m quant.evaluate_phase_a_real_data \
  --data-dir data \
  --output-dir output \
  --baseline-config output/phase_a_baseline_final.json \
  --metadata-file data/ticker_metadata.csv
```
- Macro OJK neutral tidak dipaksa menjadi bullish/bearish. Sistem memakai `macro_regulatory_signal` untuk memberi konteks regulasi: menurunkan confidence directional yang terlalu ekstrem, menaikkan risk/caution overlay, dan mengencangkan threshold entry saat rezim regulasi sedang tinggi.
- Feature flag default ada di `config/analytics.php` (`analytics.macro_regulatory_signal.enabled`) dan bisa dioverride per request/command:
```bash
php artisan evaluate:report BBCA --period=30 --macro-regulatory-signal=1
php artisan evaluate:report BBCA --period=30 --macro-regulatory-signal=0
php artisan evaluation:sentiment-compare BBCA --period=30 --macro-regulatory-signal=1
```
- Backtest/UI comparison tetap kompatibel:
  - Dengan moderation: `/backtest?code=BBCA&include_macro_news=1&macro_regulatory_signal=1`
  - Tanpa moderation: `/backtest?code=BBCA&include_macro_news=1&macro_regulatory_signal=0`
- Close-out final Phase A:
```bash
php artisan phase-a:closeout
```
- Command close-out akan membekukan baseline jika perlu, memeriksa artifact baseline, status threshold/strict mode, kesiapan backfill OJK historis, kesiapan `macro_regulatory_signal`, menjalankan suite inti, lalu menulis:
  - `output/phase_a_closeout_report.txt`
  - `output/phase_a_closeout_status.json`

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
