# Plan Perbaikan Coverage Sentimen & Kualitas ML Sentimen — Log Eksekusi

Dibuat: 2026-07-19. Dokumen ini mencatat apa saja yang benar-benar diubah di sistem pada sesi ini, per fase, supaya bisa ditelusuri ulang (untuk skripsi maupun sesi lanjutan).

## Latar belakang masalah

Dua gap utama yang jadi target:
1. **Coverage sentimen rendah** di dataset training model prediksi harga — window agregasi sentimen di-hardcode 5 hari, dan backfill berita historis sudah nyaris mentok (GDELT cuma index ~2017+, sumber lain "historical fetch"-nya ternyata cuma filter hasil live by-date, bukan query historis asli).
2. **Model ML sentimen lemah** — `w11wo/indonesian-roberta-base-sentiment-classifier` dipanggil mentah via HuggingFace hosted API tanpa fine-tuning sama sekali, akurasinya cuma 35.6% vs label manusia (di bawah tebak-acak), sementara 801 label manual yang sudah dikumpulkan belum pernah dipakai untuk memperbaiki modelnya.

---

## Fase 0 — Perbaikan operasional (ditemukan di tengah jalan, bukan direncanakan)

Saat mengerjakan Fase A, ditemukan **scheduler mati 35 jam** (2026-07-18 06:00 → 2026-07-19 17:28, MySQL down karena masalah permission log file yang berulang). Ditambal dengan:
- `php artisan news:backfill-historical --from=2026-07-18 --to=2026-07-19` — 15/30 sumber berhasil dapat data baru, 10 gagal (GDELT rate-limited 429, auto-retry di run berikutnya).

**Belum diselesaikan secara permanen**: MySQL tetap manual (sesuai keputusan awal user menolak auto-start), jadi risiko outage berulang masih ada. Ini bukan bagian dari Fase A/B, cuma mitigasi sesaat.

---

## Fase A — Lebarkan window agregasi sentimen (5d → 10d/20d)

**Tujuan:** naikkan coverage `has_sentiment_data` tanpa scraping baru, ukur apakah sentimen mulai berkontribusi ke akurasi model prediksi harga.

### Perubahan kode
- [`app/Services/Prediction/ResearchPredictionFeatureService.php`](app/Services/Prediction/ResearchPredictionFeatureService.php) — `buildForDate()` sudah punya parameter `$sentimentLookbackDays` (ternyata sudah ada sebelumnya, cuma belum tersambung ke command).
- [`app/Console/Commands/ExportPredictionResearchDatasetCommand.php`](app/Console/Commands/ExportPredictionResearchDatasetCommand.php) — tambah opsi `--sentiment-lookback-days` (default 5, backward-compatible), diteruskan ke `buildForDate()`.
- Script baru [`quant/run_sentiment_window_experiment.py`](quant/run_sentiment_window_experiment.py) — reuse primitives dari `train_prediction_models.py` (`build_folds`, `evaluate_predictions`, `mean_metrics`, `V2_ALL_FEATURE_COLUMNS`/`V2_NO_SENTIMENT_FEATURE_COLUMNS`), uji fair-comparison 5-seed untuk RandomForest.

### Data yang di-generate
- `output/prediction_research/window_experiment/dataset_full_w{5,10,20}.csv` — full-history (25 tahun, 12 ticker termasuk BUMI/DEWA), untuk ukur coverage sistemik.
- `output/prediction_research/window_experiment/narrowed/dataset_narrowed_w{5,10,20}.csv` — subset 2024-08-01..2026-04-15 (10 ticker resmi), untuk uji akurasi apples-to-apples (subset yang sama persis dipakai di uji Gap 1 sebelumnya).

### Hasil

**Coverage naik konsisten di semua window** (dan baseline sendiri sudah naik 6x dari catatan lama berkat kerja sesi-sesi sebelumnya):

| Window | Coverage full-history | Coverage subset 2024-08+ |
|---|---|---|
| 5d (baseline) | 1.37% | 17.43% |
| 10d | 1.83% | 23.65% |
| 20d | 2.19% | 28.35% |

**Akurasi: tidak ada window yang menang di kedua metrik sekaligus** (lihat `output/prediction_research/window_experiment/sentiment_window_experiment.txt`):
- Window 5 & 10 (RandomForest): delta f1/dir_acc dalam rentang noise (std ~0.005-0.012).
- Window 20 (RandomForest): dir_acc naik +0.027 (melebihi noise) tapi f1_macro turun -0.021 (juga melebihi noise) — pola klasik model condong ke kelas mayoritas, bukan sinyal prediktif asli.

**Verdict: coverage naik ≠ sentimen mulai berkontribusi.** Konsisten dengan temuan Gap 1 sebelumnya. Fold tetap cuma 1 (sample kecil, keterbatasan metodologis yang sudah didisclosure).

### Status: SELESAI, tidak ada perubahan default production (window tetap 5 hari kecuali dipromosikan lebih lanjut).

---

## Fase B — Fine-tune IndoBERT dari 801 label manual

**Tujuan:** perbaiki akurasi sentimen itu sendiri, bukan cuma coverage-nya.

### B1: Setup environment
- venv baru `quant/.venv-sentiment/` (terisolasi dari environment global yang dipakai script `quant/` lain).
- Install: `torch` (CPU wheel), `transformers`, `datasets`, `accelerate`, `scikit-learn`.
- **Bug ditemukan & diperbaiki**: `numpy 2.x` ter-install otomatis tapi tidak kompatibel dengan `torch 2.2.2` (crash `RuntimeError: Numpy is not available`). Fix: pin `numpy<2` (jadi 1.26.4).

### B2: Export data training
- Command baru [`app/Console/Commands/ExportSentimentFinetuneDatasetCommand.php`](app/Console/Commands/ExportSentimentFinetuneDatasetCommand.php) (`sentiment:export-finetune-dataset`).
- Join `sentiment_manual_labels` (801 baris, 801 artikel unik, 1 user, tanpa konflik) + `news_articles`, bentuk teks **persis meniru** `PythonApiSentimentAnalyzer::analyze()` (title+summary, truncate 512 karakter) — supaya distribusi training match distribusi serving produksi.
- Split stratified train/val/test (561/120/120), plus sertakan `ml_sentiment_label` & `rule_sentiment_label` di tiap baris supaya baseline bisa dihitung ulang di test-set yang sama persis (bukan pakai angka agregat lama dari 801 sampel penuh).
- Output: `storage/app/sentiment_finetune/{train,val,test}.jsonl`.

### B3: Fine-tuning
- Script baru [`quant/finetune_sentiment_model.py`](quant/finetune_sentiment_model.py) — load `w11wo/indonesian-roberta-base-sentiment-classifier`, `Trainer` API, 6 epoch, early-model-selection by val macro-F1.
- **Bug ditemukan & diperbaiki**: mesin ini ternyata punya discrete GPU AMD Radeon Pro 5500M (bukan cuma CPU seperti dugaan awal), `Trainer` otomatis pakai backend MPS dan **OOM di step 31/426** (VRAM cuma ~6.77GB, tidak cukup untuk roberta-base fine-tuning). Fix: `TrainingArguments(use_cpu=True)` paksa CPU-only, training selesai ~57 menit tanpa crash.

### Hasil (held-out test set 120 baris, sama persis untuk ketiga metode)

| Metode | Macro-F1 |
|---|---|
| **Fine-tuned IndoBERT** | **0.5816** |
| Rule-based (baseline lama) | 0.5482 |
| ML mentah (tanpa fine-tune) | 0.3183 |

Per-kelas fine-tuned: neutral F1=0.747 (kuat), negative F1=0.621 (baik meski support kecil, n=14), positive F1=0.377 (masih lemah, recall cuma 32.3% — sering meleset mengenali artikel positif).

Spot-check pola kegagalan lama (listicle rekomendasi saham, n=8 di test set): fine-tuned 62.5% vs ML mentah 50% — membaik tapi sample kecil.

**Gate (fine-tuned harus > rule-based di test-set yang sama): PASSED.** Model tersimpan di `storage/app/sentiment_model/indobert_finetuned_v1/` (~500MB).

### B4: Serving — SELESAI
Replikasi pola `quant/prediction_api.py` yang sudah proven di proyek ini (FastAPI + uvicorn, auto-restart via LaunchAgent):
- [`quant/sentiment_api.py`](quant/sentiment_api.py) — endpoint `GET /health`, `POST /sentiment` (kontrak response kompatibel dengan `PythonApiSentimentAnalyzer.php`, **tidak perlu ubah kode PHP**).
- [`start_sentiment_api.sh`](start_sentiment_api.sh) — jalankan via venv `.venv-sentiment`, port **8002** (beda dari prediction API di 8001).
- **Bug ditemukan & diperbaiki**: `fastapi`/`uvicorn`/`pydantic` sempat lupa terinstall di venv (torch/transformers dkk sudah, tapi server-nya sendiri belum) — ditambahkan.
- LaunchAgent `~/Library/LaunchAgents/com.sentimena.sentiment-api.plist` — **dipasang & aktif** (`RunAtLoad`+`KeepAlive`, sama seperti prediction-api). Terverifikasi jalan otomatis setelah `launchctl load`.
- `.env` `PYTHON_SENTIMENT_ENDPOINT` — **sudah diarahkan** ke `http://127.0.0.1:8002/sentiment` (dari endpoint HuggingFace hosted lama). Reversibel — tinggal ganti balik kalau perlu rollback.
- **Verifikasi end-to-end lolos**: `PythonApiSentimentAnalyzer::analyze()` (Laravel) berhasil manggil server lokal dan parsing response dengan benar. Test suite 404 passed setelah cutover.
- **Spot-check 3 pola kegagalan lama, semua membaik**:
  - Listicle rekomendasi saham → dulu ML salah bilang "positive", sekarang **neutral** (99.9% yakin) ✓
  - Berita PR/CSR ("GoTo Luncurkan Bakti GoTo...") → dulu ML salah bilang "positive" 86%, sekarang **neutral** (99.7% yakin) ✓
  - Berita institusional ("Vanguard dan BlackRock Borong Saham BCA") → dulu ML salah arah total "negative" 93%, sekarang **neutral** (96.4% yakin) ✓

### Status: Fase B SELESAI TUNTAS (B1-B4). Model fine-tuned sudah live di produksi.

---

## Fase C — Selaraskan kebijakan tie-break dengan kualitas ML yang sudah membaik

**Ditemukan setelah Fase B selesai:** `SentimentTiebreakResolver.php` masih hardcode "rule-based menang saat ML vs rule disagree", dengan docblock yang mengutip angka **lama** (rule-based 59.4% vs ML mentah 35.6%, dari validasi 2026-07-07). Setelah fine-tuning (Fase B), ML tidak lagi mentah — jadi kebijakan ini berpotensi sudah usang.

### Analisis empiris (bukan asumsi)
Script baru [`quant/analyze_tiebreak_policy.py`](quant/analyze_tiebreak_policy.py) — pada 120 baris test-set held-out, ambil prediksi **fine-tuned ML** untuk tiap baris via server lokal, lalu ukur akurasi **khusus di kondisi yang persis sama dengan yang dieksekusi resolver** (fine-tuned ML vs rule disagree, n=52/120):

| | Akurasi vs label manusia (di 52 kasus disagreement) |
|---|---|
| **Fine-tuned ML** | **55.77%** (29/52) |
| Rule-based | 32.69% (17/52) |

Fine-tuned ML menang +23 poin — kebijakan lama (favor rule-based) sekarang justru **salah arah**. Laporan: `output/prediction_research/sentiment_tiebreak_policy_analysis.json`.

**Catatan metodologis:** angka lama (35.6%) TIDAK bisa dibandingkan langsung dengan yang baru (55.77%) karena base rate berbeda — populasi "ML lama vs rule disagree" (dipakai membuat 801 label) beda dari populasi "ML fine-tuned vs rule disagree" yang diukur di sini (setelah fine-tuning, ML sudah setuju dengan rule di sebagian kasus yang dulu disagreement). Perbandingan yang valid adalah within kondisi disagreement yang SAMA yang dijalankan resolver saat ini — itulah yang diukur di atas.

### Perubahan kode
- [`app/Services/Sentiment/SentimentTiebreakResolver.php`](app/Services/Sentiment/SentimentTiebreakResolver.php) — dibalik: saat disagree, **ML menang** (bukan rule lagi). `method` tag baru `ml_tiebreak` (dulu `rule_based_tiebreak`). Docblock diupdate dengan angka & tanggal baru.
- Test diupdate: `SentimentAnalysisServiceTest::test_ml_label_wins_as_final_when_ml_and_rule_disagree` (dulu `test_rule_based_label_wins_...`), `NewsAggregationServiceTest::test_ml_tiebreak_wins_over_rule_based_label_during_ingestion` (dulu `test_rule_based_tiebreak_wins_...`). Full suite 404 passed.
- **Verifikasi**: command lama `news:apply-rule-tiebreak` (pemaksa rule-label, dari fix Gap 2 lama) dicek **tidak terjadwal** di `routes/console.php` — aman, tidak akan diam-diam membalikkan kebijakan baru ini.

### Backfill artikel lama
`php artisan sentiment:reanalyze --force --include-global` — re-run pipeline lengkap (ML fine-tuned + rule + resolver baru) untuk **semua 1796 artikel** yang sudah ada. Hasil: 100% berhasil (0 gagal/fallback), agreement rate 72.4% (1301/1796), 495 artikel disagreement sekarang pakai label ML (`ml_tiebreak`) bukan rule lagi. Distribusi label final: neutral 1391, positive 275, negative 130.

### Uji ulang kontribusi sentimen ke akurasi prediksi (dengan skor yang sudah dikoreksi)

Re-export dataset narrowed (2024-08-01..2026-04-15, window 5/10/20) dan ulangi `quant/run_sentiment_window_experiment.py` — sekarang `sentiment_score` di DB sudah reflect fine-tuning+tiebreak-flip (bukan skor lama). Laporan lengkap: `output/prediction_research/window_experiment/sentiment_window_experiment_before_after_finetune_comparison.txt` (hasil lama di-backup ke `*_OLD_pre_finetune.txt`/`.json`).

**Hasil: PRAKTIS TIDAK BERUBAH.** RandomForest (model primer, tervalidasi 5-seed) — semua delta with-vs-without-sentiment tetap dalam rentang noise di window 5 & 10; window 20 tetap pola sama (dir_acc naik tapi f1_macro turun, ciri model condong ke kelas mayoritas bukan sinyal asli). LogisticRegression (sekunder, 1-seed) window=10 sedikit membaik (+0.0395 f1, +0.0111 dir_acc, dulu negatif) tapi ini model lebih lemah tanpa validasi multi-seed — dicatat sebagai observasi, bukan bukti kuat.

**Kesimpulan: dua sumber perbaikan independen (kualitas model Fase B + kebijakan tie-break Fase C) sama-sama TIDAK mengubah kontribusi prediktif sentimen ke harga.** Ini memperkuat (bukan melemahkan) hipotesis bahwa akar masalah adalah **coverage berita**, bukan kualitas analisis sentimen — bahkan setelah macro-F1 sentimen naik dari 35.6% ke 58.16%, model prediksi harga tidak terpengaruh, karena ~72-83% baris (tergantung window) tetap tanpa data sentimen sama sekali.

### Status Fase C: SELESAI TUNTAS (analisis, flip kebijakan, backfill, DAN uji ulang kontribusi ke akurasi).

### Rekomendasi untuk skripsi (belum dieksekusi, keputusan scope)
Reframe klaim: bukan "sentimen memperbaiki prediksi harga" (terbukti tidak, dua kali diuji dengan kualitas sentimen berbeda), tapi **"kualitas analisis sentimen berhasil ditingkatkan signifikan secara independen, namun kontribusi prediktifnya ke harga tetap dibatasi coverage berita yang struktural (berita baru ada sejak ~2024, harga sejak 2001)"**. Ini konsisten dengan keputusan `DecisionSupportService.php` (di luar sesi ini) yang sudah menurunkan bobot sentimen di skor DSS dari 0.20 ke 0.05.

---

## Fase D — Validasi walk-forward fitur "buying pressure" (3 file uncommitted)

**Konteks:** review manual menemukan 3 file uncommitted (`DecisionSupportService.php`, `BaselinePredictionService.php`, `FeatureBuilderService.php`, bukan dari sesi Claude manapun) berisi fitur baru "buying pressure" dengan klaim di komentar kode: "buying_pressure >= 0.55 → naik, <= 0.45 → turun, ~59% akurasi arah pada validasi held-out 10 saham vs ~50% baseline". Tidak ada artefak riset apa pun yang membuktikan klaim ini (dicek `output/prediction_research/`, `quant/*.py`, git log/branches — nihil). User konfirmasi: **"itu belum divalidasi, jangan di-commit dulu"**, lalu minta divalidasi pakai walk-forward.

### Metodologi
Script baru [`quant/validate_buying_pressure_feature.py`](quant/validate_buying_pressure_feature.py) — replikasi PERSIS logika `buyingPressure()` PHP (rasio volume hari-naik vs total volume trailing 20 hari, pakai `close` mentah bukan `adj_close`) dihitung dari `data/stocks/*.csv`, digabung ke dataset full-history 10 ticker resmi (`target_direction_5d`). Walk-forward OOS **8 fold** (setting resmi proyek: `min_train_days=252, test_window_days=126`, jauh lebih robust dari uji sentimen yang cuma dapat 1 fold — buying_pressure tidak kena constraint coverage berita jadi bisa pakai full history). Reuse `MajorityClassModel`/`RandomBaselineModel`/`build_folds`/`evaluate_predictions` dari `train_prediction_models.py`.

Dua uji:
- **Test A** (nilai tambah fitur ML): RandomForest 5-seed, `technical_only` vs `technical_only + buying_pressure`.
- **Test B** (uji literal klaim di kode): aturan persis `>=0.55→naik, <=0.45→turun` sebagai classifier, dibanding majority-class & random baseline, per-fold OOS.

### Hasil: KLAIM TIDAK TERBUKTI, BAHKAN TERBALIK

**Test A** — menambah buying_pressure ke fitur ML **menurunkan** performa: delta f1_macro **-0.0126**, delta dir_acc **-0.0136** (keduanya jauh di luar std ~0.002-0.003, bukan noise).

**Test B** — aturan literal dari kode:
| | Directional accuracy |
|---|---|
| Aturan buying_pressure (kode) | **33.06%** |
| Majority-class baseline | 38.80% |
| Random baseline | 35.53% |
| *Klaim di komentar kode* | *59% vs 50%* |

Aturan **kalah dari majority-class di 7 dari 8 fold**, kalah dari random baseline di 6 dari 8 fold. Laporan lengkap: `output/prediction_research/buying_pressure_walkforward_validation.txt` + `.json` (detail per-fold).

### Kesimpulan
Klaim "~59% vs ~50%" **tidak bisa direproduksi** dan **terbalik** di bawah metodologi walk-forward yang benar — pola data-snooping yang sama seperti kasus kandidat trading DEWA yang dulu gagal graduation test OOS di proyek ini. Threshold 0,55/0,45 dan probabilitas presisi (0,60/0,58/0,55/0,54) kemungkinan besar hasil tuning manual pada sampel terbatas, bukan validasi out-of-sample.

**Rekomendasi ke user: JANGAN commit ketiga file dalam bentuk sekarang.** Kalau fitur ini mau dilanjutkan, perlu didesain ulang dari nol dengan disiplin yang sama seperti fitur lain di proyek ini (derive threshold HANYA dari train split, uji di test yang benar-benar tidak tersentuh) — bukan berarti rasio volume ini pasti tidak ada sinyal sama sekali, tapi implementasi & threshold yang ada SEKARANG terbukti salah.

### Status Fase D: SELESAI. Keputusan akhir (commit/revisi/buang 3 file) di tangan user.

**Update 2026-07-19 malam**: user konfirmasi "belum divalidasi, jangan di-commit dulu" → 3 file di-`git checkout --` (dikembalikan ke state committed terakhir, backup diff tersimpan di `storage/app/discarded_experiments/buying_pressure_discarded_20260719.patch` untuk referensi kalau mau redesign nanti). Working tree bersih.

---

## Fase E — Audit infra: root cause outage MySQL & auto-recovery gap berita

**Konteks:** user minta audit menyeluruh dimulai dari infra MySQL, karena sudah 2x outage nyata (2026-07-10..13, 2026-07-18..19) yang menghentikan pengumpulan berita tanpa gejala sampai `scheduler:healthcheck` dicek manual.

### Temuan root cause
- MySQL **sebenarnya SEDANG JALAN** saat dicek (PID aktif), tapi `mysql.server status`/`start` CLI **selalu gagal** untuk user `mac` — root cause: `/Applications/XAMPP/xamppfiles/var/mysql/` dan isinya dimiliki grup `_mysql:702` (`rw-rw----`), dan `mac` **bukan anggota grup itu**. User selama ini menyalakan MySQL lewat **XAMPP Application Manager (GUI)**, yang elevate ke root lalu drop privilege ke `_mysql` sesuai `my.cnf` (`user=mysql`) — bukan lewat CLI.
- **Tidak ada mekanisme auto-start sama sekali** (tidak ada LaunchDaemon) — akar sebab langsung dari kedua outage: begitu Mac restart / app XAMPP Manager tidak dibuka lagi, MySQL mati total tanpa gejala lain.
- **Log error MySQL membengkak lagi ke 1.3GB** (`macs-MacBook-Pro.local.err`) — sempat "diperbaiki" di sesi lama (1.25GB) tapi ternyata cuma dibersihkan sekali, bukan dicegah tumbuh lagi. Plus ada 5 file `.err` sisa hostname lama (jaringan/nama Mac berubah-ubah) menumpuk ~1.4GB total di direktori itu. **Belum dibersihkan** (belum diminta user, opsional).

### Perbaikan: LaunchDaemon auto-start MySQL
User pilih opsi paling tuntas. Plist disiapkan di scratchpad (`com.sentimena.mysql.plist`) — jalankan `mysqld_safe` langsung sebagai `root` (`UserName: root`), `RunAtLoad`+`KeepAlive`, replikasi persis mekanisme privilege-drop yang sudah terbukti jalan via GUI XAMPP (root → drop ke `_mysql` sesuai `my.cnf`). **Instalasi butuh `sudo` yang tidak bisa dieksekusi dari tool ini** (non-interactive sudo gagal, perlu password) — user diberi 4 command copy-paste untuk dijalankan sendiri di terminal:
```
sudo cp <scratchpad>/com.sentimena.mysql.plist /Library/LaunchDaemons/com.sentimena.mysql.plist
sudo chown root:wheel /Library/LaunchDaemons/com.sentimena.mysql.plist
sudo chmod 644 /Library/LaunchDaemons/com.sentimena.mysql.plist
sudo launchctl load /Library/LaunchDaemons/com.sentimena.mysql.plist
```
**Status: menunggu user eksekusi command di atas, belum diverifikasi jalan.** Kalau sesi depan mau lanjut/verifikasi: cek `ps aux | grep mysqld`, `scheduler:healthcheck`, dan coba `php artisan tinker` konek DB tanpa perlu buka app XAMPP Manager dulu.

### Fitur baru: auto-detect-gap + auto-backfill (self-healing)
User minta (bagian dari audit infra): daripada nambal manual tiap kali ketahuan ada gap, buat mekanisme otomatis. Command baru [`app/Console/Commands/AutoRecoverNewsGapCommand.php`](app/Console/Commands/AutoRecoverNewsGapCommand.php) (`news:auto-recover-gap`):
- **Reuse mekanisme yang sudah proven**: baca mtime `storage/logs/scheduler.log` (proxy yang sama dipakai `scheduler:healthcheck`, sudah terbukti akurat mendeteksi 2 outage nyata sebelumnya).
- Kalau gap > `--threshold-hours` (default 1 jam): otomatis panggil `news:backfill-historical` untuk rentang tanggal yang terlewat, dibatasi `--max-gap-days` (default 14 hari) supaya tidak backfill kelewat jauh.
- Dijadwalkan tiap 30 menit di `routes/console.php` (`->everyThirtyMinutes()`), `withoutOverlapping()`, log ke `scheduler.log` yang sama (jadi run command ini sendiri juga jadi bukti "scheduler sehat").
- Idempotent secara alami: `news:backfill-historical` yang dipanggil sudah punya resume/skip logic sendiri (`Cache` per source+ticker+month), jadi aman dipanggil berulang tanpa kerja duplikat.
- Test baru `tests/Feature/AutoRecoverNewsGapCommandTest.php` (4 test: no-gap, gap-detected, log-missing, max-gap-days-cap). Full suite 408 passed (dari 404).

### Status Fase E: SELESAI (keputusan final).
- ✅ Root cause outage MySQL ditemukan & didokumentasikan.
- ✅ Auto-recovery gap berita: kode selesai, tertest, terjadwal, sudah live (jalan tiap 30 menit).
- ❌ **LaunchDaemon MySQL: DITOLAK, keputusan final user (2026-07-20).** Sudah dijelaskan plus-minus lengkap (auto-start selalu-nyala vs kontrol manual, risiko rebutan start/stop dengan GUI XAMPP, butuh sudo) — user pilih **tetap manual**, sadar akan trade-off-nya (auto-recovery tetap menutup celah begitu MySQL dinyalakan manual kapan pun, cuma tidak "benar-benar tanpa perlu diingat sama sekali"). **JANGAN diusulkan lagi di sesi berikutnya kecuali user yang mengangkat topik ini duluan.** File plist di scratchpad (`com.sentimena.mysql.plist`) tidak jadi dipasang — aman diabaikan/dihapus kalau perlu beres-beres.
- ⏳ Belum dikerjakan (belum diminta, prioritas rendah): bersihkan log MySQL 1.3GB, tambah `mac` ke grup `_mysql` untuk akses CLI (opsi B dari diskusi Fase E, juga belum diminta).

---

## Fase F — Audit bobot skor Decision Support System (tahap 5 dari alur audit)

**Konteks:** setelah buying_pressure (Fase D) terbukti gagal validasi, dicurigai bobot-bobot LAIN di `DecisionSupportService` yang **sudah live di produksi** (bukan eksperimen baru) mungkin juga belum pernah divalidasi empiris. Beda dari Fase D, kali ini alat validasinya **sudah ada** di proyek (`BacktestService::runAll()`, halaman `/backtest`) — audit ini menjalankan alat yang sudah ada dengan sample lebih besar, bukan membuat validator baru.

### Metodologi
`BacktestService::runAll(lookback=30, forward=5, step=3, threshold=1.0%, maxWindows=60)` — parameter default produksi, `maxWindows` dinaikkan dari default 5 (terlalu kecil untuk statistik) ke 60 per saham. 720 prediksi total, 12 saham (termasuk BUMI/DEWA). Window rolling, entry/exit price selalu setelah signal date (out-of-sample secara alami).

### Hasil — pola yang sama seperti buying_pressure, kali ini di fitur yang SUDAH LIVE
- **Akurasi arah keseluruhan: 33.3%** (persis baseline tebak-acak 3-kelas).
- **Korelasi `final_score` vs return aktual negatif di 8 dari 12 saham** (BBCA -0.048, BBRI -0.263, BMRI -0.052, TLKM -0.164, ASII -0.004, ICBP -0.230, INDF -0.149, DEWA -0.352; positif hanya GOTO +0.12, ADRO +0.05, UNVR -0.023≈0, BUMI +0.375).
- **Status "Bullish Support" (score≥65, n=45): median return historis -1,2% (NEGATIF)**. Rata-rata terlihat +1,25% tapi itu semata diseret outlier ekstrem (rentang -32,95% s/d +39,59%; trimmed mean cuma +0,86%).
- **Rasio naik/turun nyaris rata di semua status** (Bullish 33,3%, Wait-and-See 35,4%, Warning 36,8%) — status Warning bahkan sedikit LEBIH TINGGI rasio naiknya dibanding Bullish. Status DSS praktis tidak membedakan probabilitas arah sama sekali.

Laporan lengkap: `output/prediction_research/dss_scoring_weights_audit.txt`.

### Kesimpulan
Tidak ditemukan bukti (komentar kode, artefak riset, test) bahwa bobot 0.20/0.22/0.18/0.13/0.12/0.15 atau puluhan threshold internal (trendScore/momentumScore/volumeScore/fundamentalScore/status 65/40) pernah di-tuning berdasarkan backtest ini — pola yang SAMA seperti buying_pressure: desain dari intuisi, tidak pernah divalidasi, dan begitu diuji dengan alat proyek sendiri, tidak lolos.

**Catatan penting**: ini BUKAN berarti komponen individualnya salah — RSI/MACD/Bollinger/ADX dihitung benar secara matematis. Masalahnya ada di BOBOT AGREGAT & THRESHOLD STATUS yang menggabungkannya jadi satu skor "Bullish/Warning" yang diklaim ke pengguna.

**Pola berulang lintas 2 fase audit (D & F)**: proyek ini punya kecenderungan membangun fitur scoring dari intuisi/eyeball, lalu — kalau diaudit dengan disiplin walk-forward yang sama seperti dipakai di model prediksi resmi — ternyata tidak tervalidasi. Ini pelajaran metodologis besar yang layak jadi temuan tersendiri di skripsi, bukan sekadar 2 bug terpisah.

### Rekomendasi (belum dieksekusi, keputusan user)
1. Disclaimer "referensi, bukan rekomendasi final" yang sudah ada di DSS makin penting dipertahankan mengingat temuan ini — jangan dilonggarkan.
2. Kalau DSS mau dipertahankan sebagai fitur andalan, bobot & threshold perlu didesain ulang dengan disiplin walk-forward yang sama seperti model prediksi resmi (derive dari train split, uji OOS, bandingkan naive baseline) — bukan sekadar dihapus.
3. Fundamental score (PBV/PER/ROE/DER) belum diuji terpisah di audit ini (yang diuji skor gabungan akhir) — kalau mau lanjut, itu area yang belum tersentuh.

### Status Fase F: Audit SELESAI (temuan didokumentasikan). Keputusan tindak lanjut (redesign bobot / biarkan dengan disclaimer lebih kuat / lainnya) di tangan user.

---

## Fase G — Audit tahap 4 (Model Prediksi): engine produksi ternyata bukan yang tervalidasi

**Konteks:** lanjutan audit alur (tahap 4, setelah tahap 5/DSS di Fase F). `DecisionSupportService::analyze()` memanggil `BaselinePredictionService::predict()` untuk field `prediction`/`prediction_confidence` yang juga menggerakkan validitas `trading_signal` (TP/SL). Berbeda dari kartu prediksi dual-model di `/analytics` (`StockPredictionCardsService`, manggil Python langsung, tidak terpengaruh), jalur DSS ini tunduk ke config `PREDICTION_ENGINE`.

### Temuan
`.env` production: **`PREDICTION_ENGINE=baseline`** — padahal model ML resmi (`prediction_api.py`, RandomForest `model_technical_v6a.joblib`, sudah tervalidasi walk-forward di sesi-sesi sebelumnya, ~40.5% dir_acc tercatat) **sedang jalan sehat** (`model_ready: true`) via LaunchAgent yang sama seperti sentiment-api. Jalur DSS malah pakai `BaselinePredictionService::baselineHeuristic()` — heuristik hand-tuned lain (bobot `sentimentWeight`/`newsFlowWeight` dinamis + `maSignal*0.18 + lag1Signal*0.14 + lag3Signal*0.20 + lag7Signal*0.10 + rsiSignal*0.10 + cumSignal*0.06 + trendSignal*0.10 + corrSignal*0.06`, pola sama seperti DSS/buying-pressure) — yang **inilah** yang diam-diam sudah teruji ikut kena angka 33.3% (random-baseline) di backtest Fase F, karena `accuracy` di backtest itu mengukur field `prediction` yang datang dari service ini.

### Verifikasi perbandingan apples-to-apples
Backtest SAMA PERSIS (`runAll`, maxWindows=60, 720 prediksi) dijalankan ulang dengan `Config::set('prediction.engine','python')`:

| Engine | Akurasi arah (n=720) |
|---|---|
| `baseline` (heuristik, aktif sebelumnya) | 33.3% |
| `python` (model ML resmi v6a) | **39.6%** |

+6.3 poin, korelasi per-saham juga lebih seimbang (7 positif/netral vs 5 negatif, dibanding 4 vs 8 sebelumnya). Konsisten dengan baseline V6A resmi (~40.5%) yang sudah tercatat di sesi lama.

### Perubahan diterapkan
- `.env` **`PREDICTION_ENGINE` diubah dari `baseline` ke `python`**.
- Verifikasi teknis: skema fitur `FeatureBuilderService::build()` kompatibel dengan `/predict` endpoint (`method: 'python'` di response, bukan fallback).
- Verifikasi test suite: **aman** — `phpunit.xml` sudah override `PREDICTION_ENGINE=baseline` khusus testing (baris terpisah dari `.env`), jadi switch ini tidak memengaruhi test suite. Full suite tetap 408 passed.
- **Verifikasi visual di browser**: `/analytics?code=BBRI` — panel DSS menampilkan "Prediksi: UP (0.35)" dengan benar, seluruh halaman (trading signal, indikator teknikal, faktor pendukung) render normal tanpa error.

### Berbeda dari Fase D & F (temuan negatif/reject)
Ini temuan **positif dan actionable** — bukan buang fitur yang gagal, tapi ganti komponen lemah dengan komponen yang SUDAH ADA dan SUDAH tervalidasi (bukan bikin baru).

### Status Fase G: SELESAI. `.env` sudah diubah & diverifikasi end-to-end. (`.env` tidak masuk git — perubahan ini cuma berlaku di mesin lokal ini, perlu direplikasi manual kalau pindah/deploy ke environment lain.)

---

## Fase H — Audit tahap 3 (Fitur Gabungan): konsistensi training vs live serving

**Konteks:** cek apakah fitur yang dipakai training `model_technical_v6a` (baru dipromosikan produksi di Fase G) konsisten dengan fitur yang dikirim saat live inference.

### Desain yang sudah baik (dikonfirmasi, tidak perlu diubah)
- `FeatureBuilderService` & `ExportPredictionResearchDatasetCommand` sama-sama pakai `ResearchPredictionFeatureService::seriesForStock()`/`buildForDate()` — satu sumber kode untuk semua indikator teknikal, otomatis konsisten training vs serving by construction.
- `prediction_api.py` self-describing (baca `feature_columns` dari metadata model sendiri) — menghindari kelas bug "kolom tertukar urutan".
- `StockPredictionCardsService` reuse array fitur yang sama dari caller — tidak ada divergensi antara panel DSS dan kartu prediksi dual-model.

### Bug ditemukan: `return_5d_cross_section_rank` selalu `null` di live inference
Fitur ini = ranking return 5-hari suatu saham relatif ke 9 saham lain di tanggal sama. Perhitungan aslinya HANYA ada di `ExportPredictionResearchDatasetCommand::applyCrossSectionalReturnRanks()` — post-processing di level dataset gabungan SEMUA ticker, tidak bisa dihitung per-saham tunggal. `ResearchPredictionFeatureService.php:236` (dipakai baik training maupun serving) hardcode `null` untuk fitur ini. Akibatnya SETIAP prediksi live (panel DSS + kartu prediksi) mengirim `null`, diam-diam di-imputasi model ke nilai median training — tidak ada gejala/error yang terlihat.

**Dampak terukur (feature importance `model_technical_v6a`)**: fitur ini cuma **2.44%** (peringkat 13 dari 15). Dua fitur dominan `atr14_pct` (20.2%) + `atr_ratio` (18.1%) — **dihitung KONSISTEN**, bukan kena bug ini. Laporan lengkap + tabel importance penuh: `output/prediction_research/feature_consistency_audit.txt`.

### Kesimpulan
Bug nyata & terverifikasi, tapi dampak kecil — bukan penyebab utama akurasi tipis (39.6%). Keputusan Fase G (switch ke `python` engine) tetap valid, upside-nya sudah terukur nyata terlepas dari bug minor ini.

### Rekomendasi (belum dieksekusi, effort vs impact kurang menarik untuk dikejar sekarang)
1. Precompute ranking cross-sectional harian sebagai bagian scheduler (`stocks:update-snapshots`), live serving tinggal lookup.
2. Atau: drop fitur ini kalau retrain model berikutnya (importance rendah, tidak banyak kehilangan sinyal).
3. Tidak mendesak — dicatat sebagai temuan audit, bukan bug kritis.

### Status Fase H: SELESAI. Bug terdokumentasi, tidak diperbaiki (impact rendah, keputusan user kalau mau lanjut).

---

## Ringkasan Audit Menyeluruh (Tahap 1-5)

| Tahap | Area | Status |
|---|---|---|
| 1 | Infra MySQL | Root cause ditemukan (Fase E), auto-recovery gap berita LIVE, LaunchDaemon menunggu aksi manual user |
| 2 | Analisis Sentimen | Solid — fine-tuned, tie-break diperbaiki berdasar data, di-backfill (Fase B/C) |
| 3 | Fitur Gabungan | Diaudit (Fase H) — desain konsisten, 1 bug minor ditemukan (importance 2.44%, tidak mendesak) |
| 4 | Model Prediksi | **Bug ditemukan & diperbaiki** (Fase G) — engine production diganti dari heuristik tak-tervalidasi (33.3%) ke model resmi tervalidasi (39.6%) |
| 5 | Decision Support System | **Temuan besar** (Fase F) — bobot skor live tidak lolos backtest sendiri (median "Bullish" -1.2%), keputusan tindak lanjut di user |

Audit menyeluruh SELESAI tuntas 5 tahap. Pola lintas-fase yang konsisten: proyek ini punya kecenderungan membangun fitur/bobot dari intuisi tanpa validasi empiris (buying_pressure, bobot DSS, cross-section-rank) — tapi begitu diaudit dengan disiplin yang sama seperti model resmi (walk-forward, backtest, feature importance), masalahnya bisa ditemukan dan sebagian diperbaiki (Fase G). Ini pelajaran metodologis besar yang layak jadi bagian tersendiri di skripsi.

---

## Fase I — Tindak lanjut temuan Fase F (bobot DSS): Opsi B+C diterapkan

**Konteks:** setelah didiskusikan, user pilih kombinasi **Opsi B (perkuat disclaimer)** + **Opsi C (pindahkan basis status ke model ML tervalidasi)** — BUKAN Opsi A (redesign bobot komposit via walk-forward, ditolak karena risiko tinggi mengulang pola data-snooping buying_pressure/DEWA), dan bukan Opsi D (hapus status sepenuhnya).

### Kalibrasi threshold confidence (bukan tebakan)
Cek sebaran probabilitas aktual dari 360 prediksi live (engine `python`): median **0.35** (nyaris baseline 3-kelas 33%), p75 **0.41**, max 0.95 — sangat miring ke kanan. Threshold confidence baru: Rendah <0.36, Sedang 0.36–0.45, Tinggi ≥0.45 — dipilih berdasar sebaran nyata, bukan angka bulat sembarang.

### Perubahan kode
- [`app/Services/Analytics/DecisionSupportService.php`](app/Services/Analytics/DecisionSupportService.php):
  - Panggilan `$predictor->predict()` dipindah ke SEBELUM `statusAndConfidence()` (dulu di bawah, terpisah — menyebabkan `status` dan `prediction` bisa KONTRADIKTIF, contoh nyata terlihat sebelum fix: status "Wait and See" tapi `prediction` "UP" bersamaan).
  - `statusAndConfidence()` ditulis ulang: terima `$predictionResult` (bukan `$finalScore`). `up`→Bullish Support, `down`→Warning, `flat`→Wait and See. Confidence dari `probability` model pakai threshold hasil kalibrasi di atas.
  - `$rawFinalScore` (skor komposit 0.20/0.22/dst) **tetap dihitung & ditampilkan** (Opsi B, bukan D) — sekarang murni informational/deskriptif, dengan docblock jelas mengutip hasil audit Fase F.
- [`resources/views/analytics/index.blade.php`](resources/views/analytics/index.blade.php) — UI diupdate: judul cuma tampilkan status+confidence (skor dipisah ke bagian sendiri berlabel "Skor faktor (deskriptif, bukan penggerak status)"), plus disclaimer baru: *"Status berdasarkan model prediksi arah tervalidasi (walk-forward, akurasi ~40%). Bukan rekomendasi final — selalu lakukan riset mandiri."*
- Test baru: 3 test di `DecisionSupportServiceTest.php` mengunci perilaku baru (`up`→Bullish Support+Tinggi, `down`→Warning+Sedang, `flat`→Wait and See+Rendah), pakai container binding untuk fake `BaselinePredictionService::predict()`. Full suite **411 passed** (dari 408).

### Verifikasi
- **Test suite**: 411 passed, tidak ada regresi.
- **Browser** (`/analytics?code=BBRI`): status sekarang **konsisten** dengan prediksi — "Bullish Support • Rendah" sejalan dengan "Prediksi: UP (0.35)" (sebelumnya kontradiktif: "Wait and See" + "UP" bersamaan). Skor faktor tampil terpisah dengan label deskriptif jelas.

### Status Fase I: SELESAI. Temuan Fase F sudah ditindaklanjuti — status DSS sekarang berbasis komponen tervalidasi, bukan komposit yang gagal backtest, dan transparan ke user soal apa yang sebenarnya menggerakkan keputusan.

---

## Fase J — Pendalaman bobot DSS: cek komponen individual (bukan asal redesign)

**Konteks:** setelah Fase F/I, user minta didalami lagi — apakah ada cara yang BENAR untuk mencoba memperbaiki bobot DSS, bukan sekadar menyerah. Disepakati: sebelum coba redesign bobot (Opsi A, ditolak sebelumnya karena risiko data-snooping tinggi), cek dulu apakah komponen INDIVIDUAL (sentimen/trend/momentum/volume/volatilitas/fundamental) punya sinyal sama sekali — diagnostik murni, tanpa optimasi apa pun, jadi tidak ada risiko overfitting.

### Perubahan kode (aditif, tidak mengubah perilaku)
- `DecisionSupportService::analyze()` — tambah `component_scores` ke return array (6 skor individual sebelum digabung jadi `final_score`).
- `BacktestService::runForStock()` — tambah passthrough `component_scores` ke `$results[]`.
- Full suite tetap 411 passed setelah perubahan.

### Diagnostik: korelasi tiap komponen vs return aktual, 3 horizon (5d/20d/60d)
n=480 per horizon (40 window × 12 ticker), `BacktestService::runAll()`.

| Komponen | 5 hari | 20 hari | 60 hari |
|---|---|---|---|
| Sentimen | -0.09 | -0.23 | -0.13 |
| Trend | -0.15 | -0.16 | +0.17 |
| Momentum | -0.09 | -0.03 | +0.08 |
| Volume | 0.00 | 0.01 | +0.18 |
| Volatilitas | 0.03 | 0.02 | -0.05 |
| **Fundamental** | +0.13 | +0.23 | **+0.31** |

Sekilas fundamental terlihat menjanjikan: korelasi positif, menguat monoton seiring horizon memanjang — pola yang biasanya jadi ciri sinyal asli (bukan noise), sesuai dugaan awal user bahwa sinyal fundamental bergerak lambat.

### Investigasi lanjut: fundamental TERNYATA statis, bukan deret waktu — temuan gugur
Dicek: `calculateFundamentalScore()` membaca `$stock->pbv/per/roe/der` **langsung dari tabel `stocks`** (`fundamentals_updated_at` = snapshot tunggal, 2025-12-30), BUKAN data historis per tanggal. Artinya nilai fundamentalScore **identik** di semua window backtest untuk saham yang sama, terlepas dari `signalDate`-nya 2010 atau 2025.

**Implikasi (3 masalah sekaligus):**
1. **Sample sesungguhnya cuma n=12** (jumlah saham unik), bukan n=480 — korelasi dari 12 titik data sangat rentan kebetulan.
2. **Risiko sebab-akibat terbalik**: saham dengan histori harga bagus sering JUGA punya fundamental bagus SEKARANG (karena histori sukses itu sendiri membentuk fundamental saat ini) — bukan bukti fundamental "memprediksi" apa pun.
3. **Pola "korelasi menguat seiring horizon" adalah artefak statistik** dari memakai variabel konstan-per-saham (window lebih panjang → return ter-smoothing → efek tetap-per-saham APAPUN, bukan cuma fundamental, akan terlihat "menguat") — bukan bukti skill prediktif genuine.

**Kenapa validasi OOS tidak applicable:** split kronologis tidak menolong karena nilai fundamentalnya SAMA di kedua sisi split (cuma 1 snapshot). Untuk benar-benar menguji fundamental historis vs return ke depan, dibutuhkan **data fundamental historis per tanggal** (PBV/PER/ROE dari waktu ke waktu) — database ini cuma simpan snapshot terkini, bukan deret waktu. Ini keterbatasan data struktural, sama seperti coverage sentimen — bukan soal desain uji yang bisa diperbaiki.

### Kesimpulan Fase J
Tidak ada satu pun dari 6 komponen DSS yang lolos uji dengan disiplin penuh (sentimen/trend/momentum/volume/volatilitas: noise jelas; fundamental: sekilas menjanjikan tapi gugur karena artefak statistik + keterbatasan data). Ini memperkuat kesimpulan Fase F: skor komposit DSS memang tidak punya dasar empiris yang kuat pada data yang tersedia saat ini. Keputusan Fase I (status DSS berbasis model ML tervalidasi, bukan komposit) tetap pilihan paling tepat — tidak ada alasan baru untuk mengubahnya.

**Follow-up potensial (belum dieksekusi, butuh data baru yang belum ada)**: kalau proyek ini suatu saat mulai menyimpan data fundamental historis (bukan cuma snapshot terkini), pengujian fundamental yang benar baru bisa dilakukan. Sampai saat itu, klaim "fundamental scoring" di DSS sebaiknya dipahami sebagai info deskriptif kondisi SAAT INI (rating "fair"/"attractive"/"expensive"), bukan sinyal prediktif return.

### Status Fase J: SELESAI. Tidak ada perubahan kode lebih lanjut diperlukan — temuan mengonfirmasi keputusan Fase I sudah tepat.

---

## Fase K — Data fundamental live via yfinance (menutup follow-up Fase J)

**Konteks:** user minta jelaskan seluruh halaman `/analytics` secara detail ("pertanggung jawabkan datanya"). Saat menjelaskan bagian fundamental, ditemukan masalah baru yang lebih dalam dari sekadar "belum divalidasi" (Fase J): datanya **statis tanpa jalur update sama sekali**.

### Temuan
`database/seeders/FundamentalStockSeeder.php` — array hardcode 12 saham, `fundamentals_updated_at` **ditulis literal** `'2025-12-31'` di kode (bukan timestamp asli, jadi label "terakhir update" itu sendiri menyesatkan). Tidak ada command terjadwal atau integrasi API — beda total dari harga (`yahoo_finance`, live) dan berita (scheduler tiap menit).

**Dampak terukur**: harga BBCA sudah turun **-11.15%** sejak snapshot itu diambil → PBV/PER yang ditampilkan (3.8x/18.5x) sudah salah, seharusnya sekitar 3.38x/16.4x (perkiraan kasar berbasis harga saja — realisasinya lebih kompleks lagi karena EPS/book value juga berubah, lihat di bawah).

### Riset sumber data (sebelum bangun apa pun)
Endpoint harga yang sudah dipakai proyek ini (`v8/chart` Yahoo Finance) **tidak** menyediakan fundamental. Endpoint `quoteSummary` yang biasa dipakai butuh crumb/cookie (`curl` langsung gagal "Invalid Crumb"). **Solusi**: library `yfinance` (Python) — yang historinya SUDAH dipakai proyek ini untuk data harga historis (`data/stocks/*.csv`, kolom `source=yfinance_raw_daily`) — menangani crumb/cookie secara otomatis dan **terbukti punya data fundamental live** untuk semua 12 saham (dites langsung, bukan asumsi).

**2 masalah kualitas data ditemukan & ditangani saat riset:**
1. `debtToEquity` dari yfinance dalam **persen** (mis. TLKM=44.1 berarti DER=0.441x), sementara kode `calculateFundamentalScore()` mengharapkan rasio desimal (0.8, 1.0, dst) — kalau tidak dikonversi, salah skala 100x dan akan merusak total skor fundamental semua saham non-bank.
2. Data anomali dari upstream: ADRO `priceToBook` sempat kembali **14.823x** (jelas bukan angka wajar) — perlu validasi batas wajar (sanity bounds), bukan percaya mentah-mentah ke sumber eksternal.

### Perubahan kode
- Migration baru: `book_value_per_share` ditambahkan ke tabel `stocks` (untuk referensi/masa depan, di luar 6 field fundamental utama).
- [`quant/fetch_fundamentals.py`](quant/fetch_fundamentals.py) — fetch via yfinance untuk 12 ticker, konversi satuan DER (÷100), validasi batas wajar tiap rasio (PBV 0-100, PER 0-300, ROE ±500%, DER 0-50, dst) — nilai di luar batas di-null-kan, bukan disimpan mentah.
- [`app/Console/Commands/SyncStockFundamentalsCommand.php`](app/Console/Commands/SyncStockFundamentalsCommand.php) (`stocks:sync-fundamentals`) — panggil script Python via `Process`, update `stocks` table, **field null dari fetch baru FALLBACK ke nilai lama** (tidak menghapus info yang sudah ada, mis. DER bank yang memang tidak disediakan yfinance tetap dipertahankan dari input manual lama).
- Dijadwalkan **mingguan** (Senin 06:00 WIB) — fundamental tidak perlu refresh secepat harga/berita.
- Venv baru `quant/.venv-fundamentals/` (gitignored), cuma `yfinance` — terisolasi dari venv sentimen (torch dkk).
- Teks disclaimer di 3 halaman (`analytics/index`, `evaluasi/index`, `evaluasi/show`) diupdate dari "belum real-time" (kesan permanen tidak bisa di-update) jadi "sinkron mingguan via yfinance" (akurat).
- 4 test baru (`SyncStockFundamentalsCommandTest`, pakai `Process::fake()` — tidak panggil Python asli saat testing): update normal, fallback saat null, skip saat error per-ticker, filter `--ticker`. Full suite **415 passed** (dari 411).

### Verifikasi
- Dijalankan nyata: semua 12 saham ter-update, `fundamentals_updated_at` sekarang **2026-07-20** (bukan hardcode lagi).
- ADRO/BUMI (PBV anomali dari yfinance) otomatis fallback ke nilai lama, bukan tersimpan rusak.
- **Verifikasi visual** (`/analytics?code=BBCA`): Fundamental Score berubah nyata dari 69/100 "FAIR" → **78/100 "ATTRACTIVE"** dengan data segar (PER 18.5x→13.9x, PBV 3.8x→3.1x) — bukti data lama memang sudah bikin kategori salah.

### Status Fase K: SELESAI. Data fundamental sekarang punya jalur update otomatis mingguan yang tervalidasi, bukan snapshot statis selamanya.

---

## Fase L — Audit Trading Signal (TP/SL): sinyal "VALID" ternyata underperform baseline

**Konteks:** melanjutkan penjelasan `/analytics` field-by-field, giliran bagian "Trading Signal" (entry zone, stop loss, target 2R/3R) digali. Ini beda dari temuan sebelumnya (skor DSS, buying-pressure) — bagian ini paling langsung mengarah ke aksi nyata (user bisa entry beneran berdasar harga spesifik yang ditampilkan).

### Mekanisme (`DecisionSupportService::calculateTradingSignal()`)
- Stop loss: `min(stopConservative=entry-1.5×ATR, stopBBLower=BBLower-0.3×ATR)` — ambil yang LEBIH DEKAT ke entry (stop lebih ketat), bukan yang lebih longgar.
- Quality tier dari jumlah confirmation/warning teknikal: `strong` (≥4 confirm, 0 warning), `moderate` (≥3 confirm, ≤1 warning), `weak` (≥2 confirm), `invalid` (sisanya).
- `valid = true` HANYA jika: prediction='up' DAN quality∈{strong,moderate} DAN R:R₂ᵣ≥1.5.
- **Tidak ada bukti (komentar kode/test/artefak) bahwa gerbang validitas ini pernah divalidasi** — pola yang sama seperti fitur-fitur lain di sesi ini.

### Perubahan kode (aditif)
`BacktestService::runForStock()` — tambah capture `trading_signal` ke `$results[]` (field sudah ada di return `DecisionSupportService::analyze()`, cuma belum ditangkap backtest). Full suite tetap 415 passed.

### Hasil pengujian (4 percobaan terpisah, semua konsisten)

**Percobaan awal** (forward 5d/10d/20d, n kecil per horizon karena sinyal VALID jarang muncul):
| Horizon | n VALID | Win rate VALID | Avg return VALID | Win rate sisanya |
|---|---|---|---|---|
| 5 hari | 7 | 28.6% | -0.174% | 42.3% |
| 10 hari | 3 | 0% | -3.787% | 39.0% |
| 20 hari | 7 | 14.3% | -2.814% | 27.9% |

**Percobaan sample besar** (forward=5d, step=1, maxWindows=200 → n=2400 window total, jauh lebih meyakinkan):
| | VALID (n=28) | Sisanya (n=2372) |
|---|---|---|
| Frekuensi sinyal | 1.17% dari semua kesempatan | — |
| Win rate | 39.3% | 44.8% |
| Avg return | **-0.249%** | +0.527% |
| Median return | **-0.36%** | — |
| Return ≥+3% (≈kena target) | 4 dari 28 | — |
| Return ≤-2% (≈kena stop) | 8 dari 28 | — |

### Kesimpulan
Sinyal **"✅ VALID — ENTRY ZONE"**:
1. **Sangat jarang muncul** (~1.2% dari semua kesempatan).
2. **Saat muncul, historisnya justru lebih buruk** dari tidak ada sinyal sama sekali di semua horizon yang diuji (win rate lebih rendah, average & median return negatif).
3. Kerugian besar (~2x) lebih sering terjadi dibanding keuntungan besar di antara sinyal yang ditandai "valid".

**Catatan kejujuran metodologis**: sample sinyal VALID tetap kecil (n=28 di uji terbesar) karena sinyal ini memang jarang terpicu — jadi presisi angka win-rate tidak bisa diklaim sangat tinggi. TAPI arah temuannya (lebih buruk, bukan cuma "tidak lebih baik") konsisten di 4 percobaan terpisah dengan horizon berbeda-beda, jadi pola ini bukan kebetulan satu kali ukur.

**Ini bagian paling serius dari seluruh audit sesi ini** — beda dari skor DSS/fundamental yang sifatnya informasional, Trading Signal menampilkan harga entry/stop/target spesifik yang bisa langsung dieksekusi sebagai transaksi nyata.

### Tindak lanjut: Opsi B diterapkan (2026-07-20)
User pilih Opsi B — hapus klaim "VALID/WAIT" (yang terbukti salah arah), tapi TETAP tampilkan entry/stop/target sebagai referensi teknikal (matematisnya benar, cuma klaim "ini sinyal untuk entry"-nya yang dibuang).

**Perubahan kode:**
- `DecisionSupportService::calculateTradingSignal()` — docblock baru menjelaskan `valid`/`quality` tidak boleh dipakai sebagai "go signal" tervalidasi (mengutip temuan Fase L), field tetap dihitung (masih dipakai internal/backtest) tapi TIDAK lagi didesain untuk mendorong keputusan user.
- `resources/views/analytics/index.blade.php`:
  - Header diubah dari "✅ VALID — ENTRY ZONE" / "⏸ WAIT — Belum Ada Signal" (binary, hijau/abu) jadi netral: **"Level Referensi Teknikal (bukan sinyal rekomendasi)"**.
  - Disclaimer eksplisit ditambahkan, mengutip angka temuan Fase L langsung (avg return -0.25% vs +0.53%, n=28).
  - Card border/warna tidak lagi berubah berdasar `valid`+`quality` (dulu hijau kalau valid+strong) — sekarang netral konsisten.
  - Tombol "📝 Catat Trade" — dulu cuma muncul kalau `valid=true` (menyiratkan endorsement); sekarang **selalu tampil**, dilabel ulang "Catat Trade Manual (isi sendiri, bukan rekomendasi otomatis)" — alat pencatatan manual, bukan ajakan.
  - Entry zone/stop loss/target 2R-3R/position sizing/level kunci/confirmations-warnings — **semua tetap tampil** (matematis benar, informasinya tetap berguna).
- Full suite tetap 415 passed (tidak ada test yang bergantung ke teks/logika lama).

**Verifikasi visual** (`/analytics?code=BBCA`): header baru, disclaimer lengkap dengan angka audit, tombol "Catat Trade Manual" selalu tampil, semua level referensi tetap ada — dikonfirmasi lewat browser langsung.

### Status Fase L: SELESAI TUNTAS (temuan didokumentasikan + Opsi B diterapkan + diverifikasi).

---

## Fase M — Sisa halaman `/analytics`: Event Study membingungkan + klaim V6B basi

**Konteks:** lanjutan "cek bagian lain di halaman ini juga" setelah Fase K/L. Dua temuan lebih kecil tapi tetap layak diperbaiki (bukan cuma disclaimer, ada 1 klaim yang faktual salah).

### Temuan 1: Label "Event Positif/Negatif" membingungkan (bukan bug logika)
`SentimentPriceAnalyticsService::eventStudy()` — "positive_events"/"negative_events" berarti **hari dengan SENTIMEN kuat** (positif/negatif), BUKAN hasil ke harga. Kolom "impact" jujur menunjukkan return aktual sesudahnya apa adanya. Untuk BBCA baris data saat dicek: "Event Positif" nunjukin impact H+1/H+3/H+7 semuanya **negatif** (-1.61%/-3.21%/-4.82%) — logikanya benar (memang begitu yang terjadi setelah hari sentimen positif), tapi label "Positif" di sebelah angka negatif gampang disalahartikan sebagai bug.
- **Perbaikan**: label diubah jadi "Event Sentimen Positif/Negatif" (eksplisit ini soal sentimen, bukan hasil), ditambah kalimat penjelas: "Kolom impact... return AKTUAL sesudahnya apa adanya — termasuk kalau arahnya berlawanan dengan sentimen... Ini sengaja dilaporkan jujur, bukan bug."

### Temuan 2: Klaim "V6B naik 1-2%" sudah basi & sekarang TERBALIK
Footer disclaimer & subtitle kartu V6B masih mengutip klaim lama ("V6B menunjukkan peningkatan ~1-2% pada sebagian konfigurasi") — diukur ulang head-to-head di baris held-out yang sama persis (split kronologis 80/20, `output/prediction_research/dataset_v6a.csv` vs `dataset_v6b_10ticker.csv`, dijoin by ticker+reference_date):

| Model | Akurasi | Macro-F1 |
|---|---|---|
| V6A (technical-only, RandomForest) | **44.0%** | **42.6%** |
| V6B (technical+sentiment, LogisticRegression) | 40.6% | 37.1% |

**V6B sekarang justru lebih buruk** (-3.4pp akurasi, -5.5pp F1), bukan lebih baik — konsisten dengan seluruh temuan sesi ini bahwa sentimen belum terbukti membantu prediksi harga (Fase A/C). Catatan: model beda algoritma juga (RF vs LR, bukan cuma ablasi fitur murni), tapi ini tetap perbandingan yang fair karena keduanya model PRODUKSI yang benar-benar ditampilkan ke user apa adanya.
- **Perbaikan**: footer disclaimer & subtitle kartu V6B diupdate dengan angka baru + kutip temuan sesi ini, bukan klaim lama yang sudah salah arah.

### Verifikasi
Full suite 415 passed. Verifikasi visual (`/analytics?code=BBCA`): label event study baru tampil jelas, disclaimer V6A/V6B akurat dengan angka terkini — bahkan hari ini V6A bilang UP sementara V6B bilang DOWN untuk BBCA, ilustrasi nyata kenapa konteks akurasi ini penting ditampilkan.

### Status Fase M: SELESAI.

---

## Fase N — Retrain otomatis model produksi V6A/V6B + housekeeping dokumentasi Claude Code

**Konteks:** saat menyusun laporan status keseluruhan sesi (setelah Fase M), ditemukan gap operasional yang belum tersentuh audit tahap 4: `model_technical_v6a.joblib`/`model_technical_sentiment_v6b.joblib` (yang baru dipromosikan jadi engine produksi di Fase G) **beku sejak dilatih terakhir 2026-06-21/22**, tanpa jadwal retrain otomatis sama sekali — berbeda dari BUMI/DEWA yang sudah punya `prediction:retrain-volatile` (mingguan, aman dengan gating). User minta dibangun mekanisme yang setara.

### Temuan arsitektur (mengubah scope sebelum implementasi)
`quant/train_production_models.py` (trainer V6A/V6B) ternyata **tidak pernah menghitung metrik evaluasi baru** — field `official_baseline`/`research_metrics_reference` di metadata cuma menyalin angka STATIS dari laporan riset lama (`model_comparison_v6a.json`) atau konstanta hardcode. Kalau retrain otomatis langsung dibangun di atas ini, gerbang "jangan promosikan kalau lebih buruk" (pola yang sudah proven di BUMI/DEWA) **tidak akan pernah benar-benar berfungsi** — akan selalu membandingkan angka statis lama dengan dirinya sendiri.

### Perubahan kode
- [`quant/train_production_models.py`](quant/train_production_models.py) — tambah `evaluate_walk_forward()` (reuse `build_folds`/`evaluate_predictions`/`mean_metrics` dari `train_prediction_models.py`, setting resmi `min_train_days=252, test_window_days=126`, dibatasi 8 fold terbaru untuk performa). Hasilnya disimpan sebagai field metadata BARU `retrain_evaluation` (terpisah dari `official_baseline` yang tetap dipertahankan sebagai jejak riset historis, tidak dihapus).
- [`app/Console/Commands/RetrainProductionPredictionModelsCommand.php`](app/Console/Commands/RetrainProductionPredictionModelsCommand.php) (`prediction:retrain-production`) — mengikuti pola `RetrainVolatilePredictionModelsCommand` persis: `--dry-run`/`--force`/`--variant`, cek data baru di StockPrice+NewsArticle SELURUH 10 ticker resmi, regenerasi dataset via `Artisan::call('prediction:export-research-dataset', ...)`, gating degradasi macro-F1 (ambang 0.05, konsisten dengan BUMI/DEWA), archive+promote, log ke `retrain_history.jsonl` yang SAMA (tabel "Status Retrain Model" di `/analytics` otomatis ikut menampilkan baris baru karena baca file JSONL yang sama, tidak perlu perubahan UI).
- Jadwal baru mingguan, Senin 07:00 WIB (`routes/console.php`) — 1 jam setelah sync fundamental (06:00) supaya tidak berebut resource.
- Test baru [`tests/Feature/RetrainProductionPredictionModelsCommandTest.php`](tests/Feature/RetrainProductionPredictionModelsCommandTest.php) — 6 test (dry-run, skip-no-data, scoping `--variant`, reject-saat-memburuk, promote-saat-membaik, promote-tanpa-baseline-lama). Dataset export di test pakai data historis ASLI (`data/stocks/BBCA.csv`, sudah ada di repo) via `Stock::factory()->create(['code'=>'BBCA'])` — tidak perlu fabrikasi OHLCV sintetis, training-nya sendiri di-fake via `PYTHON_BINARY=php` (pola sama seperti test BUMI/DEWA). Full suite naik jadi **421 passed** (dari 415).

### Bug ditemukan & diperbaiki saat verifikasi retrain nyata
Percobaan `--force` pertama GAGAL: trainer minta kolom `label_v2_h5d`, tapi `prediction:export-research-dataset` cuma menghasilkan `label_v2`. Investigasi: `label_v2_h5d` ternyata dulu dibuat oleh script riset one-off `run_v6a_prediction_research.py` (enrichment terpisah, bukan bagian dari alur retrain). Dicek numerik: `label_v2` dan `label_v2_h5d` **identik 100% di 50.196 baris** (keduanya label arah 5-hari dengan threshold 1.5%) — jadi `MODEL_SPECS["technical"]["label_column"]` diubah ke `label_v2` langsung, tanpa perlu replikasi langkah enrichment terpisah. Dataset canonical (`output/prediction_research/dataset_v6a.csv`/`dataset_v6b_10ticker.csv`) yang sempat tertimpa saat percobaan gagal berhasil dipulihkan via `git checkout --` sebelum percobaan kedua.

### Verifikasi end-to-end (retrain nyata, bukan simulasi)
`php artisan prediction:retrain-production --force` dijalankan sungguhan (durasi ~9,5 menit, dataset 50.196 baris × 2 varian × 8 fold walk-forward):

| Variant | macro-F1 (retrain_evaluation, genuine) | directional accuracy | Decision |
|---|---|---|---|
| technical (V6A) | 0.3673 | 40.50% | `promoted_no_prior_baseline` |
| technical_sentiment (V6B) | 0.3457 | 40.48% | `promoted_no_prior_baseline` |

Decision `promoted_no_prior_baseline` (bukan `promoted` biasa) karena ini run pertama dengan field `retrain_evaluation` — metadata produksi lama belum punya angka ini untuk dibandingkan, jadi promosi berjalan tanpa gerbang degradasi (baseline akan tersedia mulai retrain berikutnya). Model lama otomatis diarsipkan ke `storage/app/prediction/archive/`. **Terverifikasi visual** di `/analytics?code=BBCA`: tabel "Status Retrain Model Volatil" menampilkan 2 baris baru ini otomatis, tanpa perubahan kode UI.

### Temuan tambahan (limitation, bukan bug baru — dicatat untuk sesi lanjutan)
Deteksi "ada data baru" di command retrain memakai tabel DB `stock_prices`/`news_articles` (yang memang aktif ter-update tiap menit), TAPI fitur teknikal aktual dihitung `ResearchPredictionFeatureService` dari file statis `data/stocks/{TICKER}.csv` — dan file itu ternyata **mentok di tanggal 2026-04-15** (dikonfirmasi dari `date_end` hasil export di atas). Artinya: mekanisme retrain sudah aman & otomatis, gerbang degradasi berfungsi genuine, TAPI selama `data/stocks/*.csv` tidak di-refresh, retrain mingguan tidak benar-benar menyerap pergerakan harga terbaru — cuma refit ulang model di rentang data yang sama. **Belum diperbaiki, prioritas untuk sesi berikutnya** kalau mau retrain benar-benar reflect data terkini (perlu cari/bangun jalur update `data/stocks/*.csv`, di luar scope Fase N).

### Housekeeping non-metodologi (di luar pipeline riset, tapi disepakati bareng di sesi ini)
- [`CLAUDE.md`](CLAUDE.md) — dokumentasi project untuk sesi Claude Code berikutnya (pipeline 5 tahap, tech stack, konvensi repo, hal yang sudah diputuskan final seperti "MySQL manual" dan "Opsi A DSS ditolak") supaya tidak perlu re-derive konteks dari nol tiap sesi.
- [`.claudeignore`](.claudeignore) — kecualikan folder besar dari auto-scan (`storage/logs` 600MB+, `output/`, `data/stocks/`, `vendor/`, `node_modules/`).
- Ini murni efisiensi tooling, tidak memengaruhi hasil riset/metodologi skripsi.

### Status Fase N: SELESAI untuk mekanisme retrain otomatis (kode, jadwal, test, verifikasi nyata). Staleness `data/stocks/*.csv` dicatat sebagai temuan terbuka, belum dikerjakan — kandidat item pertama untuk sesi lanjutan.

---

## Fase O — Tutup gap staleness `data/stocks/*.csv` (tindak lanjut Fase N)

**Konteks:** langsung menindaklanjuti temuan terbuka Fase N. Root cause dicek dulu (bukan asumsi): script pembangun `data/stocks/{TICKER}.csv` sudah ADA dan sudah teruji — [`quant/rebuild_yfinance_ohlcv.py`](quant/rebuild_yfinance_ohlcv.py) (fetch via yfinance, validasi ketat: reject gap/weekend-row/frekuensi campur, py-test sendiri) — tapi **tidak pernah dijadwalkan sama sekali** (`grep -rn "rebuild_yfinance_ohlcv" routes/ app/` nihil sebelum fase ini). Murni terlewat saat proyek dibangun.

### Perubahan kode
- [`quant/rebuild_yfinance_ohlcv.py`](quant/rebuild_yfinance_ohlcv.py) — `main()` sekarang juga print ringkasan JSON ke stdout (pola sama seperti `fetch_fundamentals.py`), supaya Laravel bisa parse hasil tanpa baca file dari disk. Dicek aman: `quant/test_rebuild_yfinance_ohlcv.py` tidak menguji stdout `main()` sama sekali (cuma unit test fungsi individual), py-test tetap 6/6 lulus setelah perubahan.
- [`app/Console/Commands/RefreshPriceHistoryCommand.php`](app/Console/Commands/RefreshPriceHistoryCommand.php) (`prediction:refresh-price-history`) — reuse venv yang sudah ada (`quant/.venv-fundamentals`, sudah punya yfinance+pandas), panggil `rebuild_yfinance_ohlcv.py` via `Process` facade (pola `SyncStockFundamentalsCommand`, lebih simpel dari command retrain karena tidak butuh candidate-gating). Scope: 10 ticker resmi V6A/V6B + BUMI/DEWA (12 total), opsi `--ticker=*` untuk subset. Toleran kegagalan sebagian (1-2 ticker gagal fetch tidak menggagalkan seluruh command, file lama yang gagal divalidasi tidak tertimpa — perilaku bawaan `rebuild_series()`).
- Jadwal baru mingguan **Minggu 01:00 WIB** (`routes/console.php`) — 1 jam sebelum `prediction:retrain-volatile` (Minggu 02:00), jauh sebelum `stocks:sync-fundamentals`/`prediction:retrain-production` (Senin 06:00/07:00). Satu refresh mingguan menutup kebutuhan KEDUA jalur retrain sekaligus.
- Test baru [`tests/Feature/RefreshPriceHistoryCommandTest.php`](tests/Feature/RefreshPriceHistoryCommandTest.php) — 6 test (`Process::fake()`, tidak sentuh DB): sukses semua, filter `--ticker`, IHSG selalu ikut refresh meski ticker di-subset, partial-invalid tidak gagalkan command, semua-invalid gagal, output non-JSON gagal graceful. Full suite naik jadi **427 passed** (dari 421).

### Temuan tambahan saat verifikasi nyata (ditemukan, langsung diperbaiki — masih dalam scope yang sama)
Percobaan pertama (`--force --variant=technical`) selesai TAPI `date_end` cuma maju ke 2026-04-22 (dari 2026-04-15), padahal `data/stocks/*.csv` sudah segar sampai 2026-07-21. Investigasi: `data/IHSG.csv` (dipakai `ResearchPredictionFeatureService` untuk fitur `market_regime_bullish`/`regime_duration`, keduanya wajib ada — `ExportPredictionResearchDatasetCommand::hasMissingCoreFeature()`) **juga stale di 2026-04-22** dan belum ikut direfresh — bottleneck pindah ke file ini begitu 12 ticker saham sudah segar. Diperbaiki: `RefreshPriceHistoryCommand` sekarang SELALU ikut refresh `IHSG=^JKSE` ke `data/IHSG.csv` (via panggilan `rebuild_yfinance_ohlcv.py` kedua, output-dir berbeda), terlepas dari filter `--ticker`, karena IHSG adalah dependency bersama semua varian, bukan "ticker" dalam arti retrain per-saham.

### Verifikasi end-to-end (real run, bukan simulasi)
- `prediction:refresh-price-history --ticker=BBCA` → BBCA maju dari 2026-04-22 ke **2026-07-21** (5453 rows), IHSG maju ke 2026-07-21 juga (8831 rows).
- `prediction:refresh-price-history` (12 ticker penuh) → semua sukses, ~6 detik total (jauh lebih cepat dari dugaan awal, tidak perlu timeout 300s sebesar itu tapi dibiarkan sebagai margin aman).
- `prediction:retrain-production --force --variant=technical` (re-run kedua kalinya) → `date_end` maju **2026-04-15 → 2026-07-14** (gap sisa ~1 minggu wajar, efek trimming horizon 5-hari untuk label). macro-F1 naik tipis 0.3648→0.3701 dengan data segar, dipromosikan otomatis (gating jalan normal).
- Full suite tetap hijau (427 passed) setelah seluruh perubahan.

### Catatan untuk sesi lanjutan (bukan bug, tapi disclosure)
- `data/stocks/*.csv`, `data/IHSG.csv`, `output/prediction_research/dataset_v6a.csv`/`dataset_v6b_10ticker.csv` semuanya ter-track di git — refresh mingguan otomatis akan menghasilkan diff besar tiap kali jadwal jalan (bukan cuma sekali seperti hari ini). Belum diputuskan apakah ini didiamkan (riwayat penuh di git) atau di-gitignore ke depannya — keputusan user.
- **Temuan terpisah yang SENGAJA TIDAK dikerjakan di fase ini** (di luar scope, didiskusikan dengan user sebelum mulai): `prediction:retrain-volatile` (BUMI/DEWA) punya gap yang lebih dalam — trainer-nya membaca dataset statis `output/prediction_research/dataset_bumi_special.csv`/`dataset_dewa_special.csv` yang cuma pernah dibuat sekali oleh script riset one-off `quant/run_special_volatile_stock_research.py`, dan command retrain volatile TIDAK PERNAH memanggil script itu ulang untuk regenerasi dataset (beda dari V6A/V6B yang sudah regenerasi tiap retrain sejak Fase N). Refresh `data/stocks/BUMI.csv`/`DEWA.csv` di fase ini TIDAK menutup gap ini — dataset khusus BUMI/DEWA-nya sendiri tetap statis. Kandidat kerjaan berikutnya kalau user mau lanjut.

### Status Fase O: SELESAI TUNTAS (kode, jadwal, test, 2 real run terverifikasi, gap IHSG yang baru ditemukan langsung ditutup). Gap dataset khusus BUMI/DEWA dicatat sebagai temuan terbuka baru, belum dikerjakan.

## Fase Q1 — Regenerasi dataset khusus BUMI/DEWA sebelum retrain volatile

**Konteks:** menindaklanjuti temuan Fase O. `prediction:retrain-volatile` sudah punya gating aman untuk artefak BUMI/DEWA, tapi trainer `quant/train_volatile_stock_models.py` membaca `output/prediction_research/dataset_bumi_special.csv` dan `dataset_dewa_special.csv` yang sebelumnya hanya dibuat oleh script riset one-off `quant/run_special_volatile_stock_research.py`. Akibatnya refresh `data/stocks/BUMI.csv`/`DEWA.csv` belum otomatis masuk ke dataset khusus volatile saat retrain.

### Investigasi sebelum perubahan
`quant/run_special_volatile_stock_research.py` dicek aman untuk diotomasi: script membangun ulang dataset BUMI/DEWA secara deterministik dari file harga statis, menulis ulang CSV + report JSON/TXT di `output/prediction_research/`, dan menghasilkan label yang memang dipakai trainer produksi volatile (`label_bumi_fixed_2_7pct`, `label_dewa_move_0_5pct`, `label_dewa_atr0_5_h5d`). Script tidak butuh input interaktif dan bisa dipanggil satu kali sebelum semua varian training.

### Perubahan kode
- `app/Console/Commands/RetrainVolatilePredictionModelsCommand.php` — tambah langkah refresh dataset volatile sebelum loop training jika ada minimal satu varian yang benar-benar akan retrain (`--force` atau ada data baru). Dry-run dan skip-no-new-data tetap tidak memanggil Python. Kalau refresh dataset gagal, command berhenti sebelum membuat/mempromosikan artefak apa pun, sehingga gating produksi tetap utuh.
- `tests/Feature/RetrainVolatilePredictionModelsCommandTest.php` — tambah fake dataset-refresh script via `PREDICTION_VOLATILE_DATASET_SCRIPT`, verifikasi dry-run/skip tidak refresh, retrain refresh dulu, dan kegagalan refresh membatalkan training tanpa menyentuh artefak produksi.

### Verifikasi
- `php artisan test tests/Feature/RetrainVolatilePredictionModelsCommandTest.php` → 6 passed, 34 assertions.
- `php artisan test` → **428 passed**, 1879 assertions.
- Real run: `PYTHON_BINARY=quant/.venv-sentiment/bin/python3 php artisan prediction:retrain-volatile --force` berhasil. Dataset khusus volatile diregenerasi sampai **2026-07-21**: BUMI 2744 rows (`2001-06-30`–`2026-07-21`), DEWA 2669 rows (`2007-09-30`–`2026-07-21`). Tiga model dipromosikan oleh gating karena tidak memburuk: `bumi_technical` macro-F1 0.3742→0.3742, `dewa_regime` 0.5751→0.5751, `dewa_technical` 0.4102→0.4102. `retrain_history.jsonl` berisi 3 baris promoted baru dengan `latest_data_at=2026-07-21T00:00:00+07:00`.

### Status Fase Q1: SELESAI. Gap dataset statis BUMI/DEWA tertutup; retrain volatile sekarang mengambil dataset khusus yang diregenerasi dari harga terbaru sebelum training, tanpa melemahkan gerbang degradasi/candidate-only.

## Fase P — Evaluasi eksperimen sentimen berbobot

**Konteks:** eksperimen class-weighted fine-tune IndoBERT dari sesi sebelumnya mati di tengah karena proses background tidak bertahan lintas-sesi. Tiga model sweep seed 42 sudah ada di `storage/app/sentiment_model/_weighted_sweep/`, tetapi metrik lama hilang; sesuai handoff, eksperimen dilanjutkan dengan resume/evaluasi ulang, lalu konfirmasi multi-seed untuk pemenang validasi.

### Perubahan dan artefak
- `quant/finetune_sentiment_weighted_experiment.py` — script eksperimen standalone dengan resume logic: model sweep yang sudah punya `model.safetensors` tidak dilatih ulang, hanya dievaluasi ulang.
- `output/prediction_research/sentiment_weighted_experiment_report.json` dan `.txt` — report akhir eksperimen.
- Candidate model tersimpan di `storage/app/sentiment_model/indobert_finetuned_v2_weighted`; produksi `storage/app/sentiment_model/indobert_finetuned_v1` tidak disentuh.

### Hasil evaluasi
Sweep dipilih hanya dari validation macro-F1: `sqrt_inverse` menang dengan val macro-F1 **0.7564**. Angka test sweep hanya dicatat untuk transparansi: `none` 0.5816, `inverse` 0.5814, `sqrt_inverse` 0.5549. Konfirmasi pemenang `sqrt_inverse` pada seed `[42, 0, 123]` menghasilkan test macro-F1 `[0.5549, 0.5233, 0.5875]`, mean **0.5552**, std **0.0262**, dan akurasi `[0.6250, 0.6083, 0.6750]`. F1 per kelas pada selection seed: positive **0.3860**, neutral **0.7333**, negative **0.5455**.

### Verdict gate
Gate mensyaratkan mean test macro-F1 mengalahkan produksi 0.5816 lebih besar dari std sendiri. Margin `0.5552 - 0.5816 = -0.0264`, std 0.0262, sehingga verdict report = **NO IMPROVEMENT**. Candidate **tidak dipromosikan**; model produksi v1 tetap acuan sentimen. Temuan negatif dicatat apa adanya: class weighting sedikit menaikkan positive F1 pada selection seed dibanding produksi (0.3860 vs 0.3774), tetapi menurunkan macro-F1 rata-rata dan tidak cukup stabil untuk mengganti model.

### Verifikasi
- Eksperimen dijalankan sampai selesai dengan 3 seed konfirmasi; report JSON/TXT terbentuk.
- Produksi `indobert_finetuned_v1` tidak ditimpa.
- Catatan eksekusi: sandbox memblokir DNS ke HuggingFace sehingga loader beberapa kali retry, lalu memakai cache lokal dan training/evaluasi tetap selesai.

### Status Fase P: SELESAI. Eksperimen berbobot gagal melewati gate; tidak ada promosi model sentimen.

## Fase Q2-prep — Siapkan active learning label positif

**Konteks:** Fase P membuktikan class weighting tidak menaikkan kualitas sentimen secara stabil. Jalur Q2 yang valid bukan membuat label sintetis atau reweight data lama, tetapi menambah label manusia baru, khususnya artikel yang condong positif/ambigu karena kelas positive tetap paling lemah.

### Perubahan kode
- `app/Console/Commands/ExportSentimentActiveLearningCandidatesCommand.php` — command baru `sentiment:export-active-learning-candidates` untuk mengekspor artikel belum dilabel manual yang condong positif atau dekat dengan batas positif. Output CSV punya kolom `human_label` kosong agar manusia mengisi `positive|neutral|negative`; skor kandidat hanya prioritas sampling, bukan ground truth.
- `tests/Feature/ExportSentimentActiveLearningCandidatesCommandTest.php` — memastikan kandidat unlabeled positif/ambigu masuk, artikel yang sudah punya label manual tidak ikut.

### Cara pakai untuk pelabelan manusia
Jalankan saat MySQL lokal menyala:
```bash
php artisan sentiment:export-active-learning-candidates --limit=250
```
File keluaran default: `storage/app/sentiment_finetune/active_learning_positive_candidates.csv`. Label manusia harus diisi manual di kolom `human_label`, lalu baru boleh diimpor/merge ke `sentiment_manual_labels` dengan audit duplikat. Tidak ada label otomatis dari model/LLM yang dipakai sebagai kebenaran.

### Verifikasi
- `php artisan test tests/Feature/ExportSentimentActiveLearningCandidatesCommandTest.php` → 1 passed, 5 assertions.
- Percobaan ekspor real diblokir karena MySQL lokal tidak menyala (`Connection refused` pada 2026-07-22). Ini bukan bug command; MySQL memang keputusan final tetap manual.

### Status Fase Q2-prep: SELESAI. Infrastruktur kandidat active learning siap; Q2 utama masih menunggu pelabelan manusia sebelum retrain/evaluasi baru.

## Fase Q2-ui — UI klik cepat untuk label active learning

**Konteks:** CSV kandidat Q2 sulit dilabel manual oleh user. Agar pelabelan manusia tetap valid dan praktis, active learning dipindahkan ke UI klik cepat yang memakai tabel `sentiment_manual_labels` existing; tidak ada label sintetis dan tidak ada schema baru.

### Perubahan kode
- `routes/web.php` — tambah `/sentiment-validation/active-learning` dan `/sentiment-validation/active-learning/next`.
- `app/Http/Controllers/SentimentValidationController.php` — tambah mode active-learning: artikel belum dilabel manual yang condong positif atau ambigu dekat kelas positif, urut dari probabilitas positif tertinggi.
- `resources/views/sentiment-validation/index.blade.php` — view label manual dibuat reusable untuk mode disagreement dan Q2 active-learning, menampilkan stock, tanggal, ML/rule label, probabilitas P/N/Neg, link sumber, tombol Positif/Netral/Negatif, dan shortcut keyboard 1/2/3.
- `tests/Feature/SentimentValidationTest.php` — tambah test halaman Q2 dan endpoint kandidat berikutnya.

### Cara pakai
Buka aplikasi lokal lalu masuk login user biasa:
```text
/sentiment-validation/active-learning
```
Klik `Positif`, `Netral`, atau `Negatif`; label langsung tersimpan ke `sentiment_manual_labels`. Jika ragu lebih dari ±30 detik, pilih `Netral`. Setelah cukup label baru terkumpul, baru lanjut Q2 utama: export finetune dataset, retrain, dan ukur test split yang sama.

### Verifikasi
- `php artisan test tests/Feature/SentimentValidationTest.php` → 6 passed, 25 assertions.
- `php artisan test` → **430 passed**, 1890 assertions.

### Status Fase Q2-ui: SELESAI. Pelabelan Q2 sekarang bisa lewat UI klik cepat; retrain Q2 tetap menunggu label manusia terkumpul.

## Fase Q2 — Active-learning label positif dan retrain kandidat sentimen

**Konteks:** setelah UI Q2 selesai, user melabel semua kandidat active-learning positif/ambigu. Dataset manual naik dari 801 menjadi **988 label**: negative 105, neutral 576, positive 307. Dataset finetune diekspor ulang dengan split stratified: train 692, val 148, test 148.

### Perubahan kode
- `quant/finetune_sentiment_model.py` — tambah opsi CLI `--model-out-dir`, `--report-json`, dan `--report-txt` agar retrain Q2 bisa menulis ke candidate directory tanpa menyentuh produksi `indobert_finetuned_v1`.

### Hasil retrain Q2
Candidate dilatih ke `storage/app/sentiment_model/indobert_finetuned_q2_candidate` selama 6 epoch CPU. Report Q2 tersimpan di `output/prediction_research/sentiment_finetune_q2_report.{json,txt}`. Pada test split Q2: candidate macro-F1 **0.6739**, accuracy **0.7297**, per-class F1: positive **0.6292**, neutral **0.8000**, negative **0.5926**. Rule baseline di test Q2 **0.5519** sehingga gate lama `finetuned > rule` memang PASSED.

### Verdict tambahan sebelum promosi
Karena test Q2 adalah distribusi baru hasil active learning dan banyak kandidat berasal dari kasus yang sudah condong positif menurut model produksi, gate lama lawan rule saja tidak cukup untuk promosi. Evaluasi eksplisit model produksi `indobert_finetuned_v1` pada test Q2 menghasilkan macro-F1 **0.8929**, accuracy **0.8919**, per-class F1: positive **0.8333**, neutral **0.9121**, negative **0.9333**. Jadi candidate Q2 **kalah jauh** dari produksi v1 pada test Q2 dan **tidak dipromosikan**.

### Temuan negatif
Penambahan label active-learning membantu coverage label positif, tetapi retrain dari checkpoint mentah justru menurunkan performa terhadap model produksi yang sudah ada. Kemungkinan besar banyak label baru adalah kasus yang produksi v1 sudah prediksi benar; retraining dengan split baru tidak memberi bukti perbaikan OOS. Untuk skripsi, hasil jujur: Q2 memperbaiki fasilitas pelabelan dan menambah data, tetapi belum menghasilkan model sentimen pengganti.

### Verifikasi
- `php artisan sentiment:export-finetune-dataset` → 988 rows; train/val/test 692/148/148.
- `quant/.venv-sentiment/bin/python3 quant/finetune_sentiment_model.py --model-out-dir storage/app/sentiment_model/indobert_finetuned_q2_candidate --report-json output/prediction_research/sentiment_finetune_q2_report.json --report-txt output/prediction_research/sentiment_finetune_q2_report.txt` → selesai.
- Evaluasi tambahan v1 vs candidate pada test Q2: v1 0.8929 > candidate 0.6739 macro-F1.

### Status Fase Q2: SELESAI DENGAN TEMUAN NEGATIF. Label bertambah dan pipeline UI/retrain jalan, tetapi candidate tidak layak promosi; produksi v1 tetap dipakai.

## Fase Q4 — Hentikan tracking file data regeneratif besar

**Konteks:** sejak Fase O/Q1, `data/stocks/*.csv`, `data/IHSG.csv`, dan dataset training di `output/prediction_research/` diregenerasi otomatis mingguan. Jika tetap tracked Git, setiap refresh akan membuat diff besar ratusan ribu baris meskipun itu artefak data, bukan perubahan kode/metodologi.

### Keputusan
File data regeneratif besar tidak lagi dilacak Git. File lokal tidak dihapus; hanya di-`git rm --cached`, sehingga aplikasi lokal dan scheduler tetap bisa memakai CSV yang sudah ada. Clone baru harus menjalankan refresh sebelum retrain penuh.

### Perubahan
- `.gitignore` — tambah ignore untuk `data/IHSG.csv`, `data/stocks/*.csv`, `output/prediction_research/dataset_v6a.csv`, `dataset_v6b_10ticker.csv`, `dataset_bumi_special.csv`, dan `dataset_dewa_special.csv`.
- Metadata kecil tetap tracked lewat pengecualian: `data/stocks/ticker_metadata.csv` dan `data/stocks/rebuild_ticker_metadata.csv`.
- File CSV lokal tetap ada di disk; yang berubah hanya status tracking Git.

### Cara regenerasi bila clone baru kosong
```bash
php artisan prediction:refresh-price-history
php artisan prediction:export-research-dataset
PYTHON_BINARY=quant/.venv-sentiment/bin/python3 php artisan prediction:retrain-volatile --force
```
Command scheduler mingguan tetap source of truth untuk menjaga data segar.

### Verifikasi
- `git rm --cached` dipakai, bukan hapus file lokal; contoh `data/stocks/BBCA.csv` masih ada setelah untrack.
- `php artisan test` tetap hijau.

### Status Fase Q4: SELESAI. Repo tidak lagi akan menerima diff mingguan besar dari artefak data regeneratif; data tetap diregenerasi lokal oleh command/scheduler.

## Fase Q3 — Perbaiki `return_5d_cross_section_rank` di live inference

**Konteks:** Fase H menemukan `return_5d_cross_section_rank` selalu `null` di live inference karena fitur rank hanya dihitung saat export dataset gabungan. Model produksi masih bisa jalan karena imputasi median, tetapi fitur ini tetap mismatch training-vs-live meski importance kecil (~2.44%).

### Perubahan kode
- `app/Services/Prediction/ResearchPredictionFeatureService.php` — live inference sekarang menghitung rank return 5-hari lintas semua CSV saham lokal untuk tanggal referensi yang sama. Rank dihitung dengan aturan sama seperti exporter: urut ascending, tie pakai average rank, dinormalisasi 0..1, single ticker = 0.5.
- Implementasi dibuat cache sekali per instance service dari return_5d saja, bukan menyimpan seluruh feature series semua saham, agar tidak meledakkan memori saat full test/UI analytics.
- `tests/Feature/ResearchPredictionFeatureServiceTest.php` — regression test tiga CSV sintetis memastikan saham dengan return_5d tertinggi mendapat rank 1.0 dan fitur tidak lagi null.

### Verifikasi
- Cek live real BBCA 2026-07-21: `return_5d=0.065306`, `return_5d_cross_section_rank=0.545455`.
- `php artisan test tests/Feature/ResearchPredictionFeatureServiceTest.php` → 1 passed, 2 assertions.
- Percobaan full suite pertama menemukan OOM karena desain awal membaca semua feature series penuh lintas CSV; diperbaiki menjadi precompute return_5d saja.
- `php artisan test` → **431 passed**, 1892 assertions.

### Status Fase Q3: SELESAI. Gap null live inference tertutup tanpa retrain dan tanpa mengubah artefak produksi.

## Fase Q5 — Bersihkan log error MySQL besar

**Konteks:** Fase E mencatat file `.err` MySQL XAMPP membengkak sampai sekitar 1.3–1.4GB. Ini housekeeping, bukan data DB. MySQL tetap keputusan final manual; tindakan hanya membersihkan log yang menumpuk.

### Tindakan yang dicoba
Agent mencoba mengosongkan file `.err` di `/Applications/XAMPP/xamppfiles/var/mysql/` tanpa menghapus path file. Percobaan non-sudo ditolak permission OS karena file dimiliki `_mysql`; percobaan `sudo -n` juga gagal karena membutuhkan password interaktif.

### Verifikasi
- File terbesar masih `macs-MacBook-Pro.local.err` sekitar **1.3GB**; total `.err` masih sekitar **1.4GB**.
- Tidak ada file DB/data yang dihapus.
- Command manual aman untuk user jalankan di Terminal lokal:
```bash
sudo sh -c 'for f in /Applications/XAMPP/xamppfiles/var/mysql/*.err; do : > "$f"; done'
```
Lalu cek:
```bash
ls -lh /Applications/XAMPP/xamppfiles/var/mysql/*.err
```

### Status Fase Q5: SELESAI (2026-07-22). User menjalankan command truncate manual di Terminal lokal. Verifikasi: seluruh file `.err` di `/Applications/XAMPP/xamppfiles/var/mysql/` sekarang 0B, kecuali log aktif (`macs-MacBook-Pro.local.err`, 712B — wajar, baru mulai lagi). Dari total ~1.4GB menjadi hampir kosong. Tidak ada file DB/data yang tersentuh; MySQL tetap jalan normal, auto-start tetap tidak diubah (keputusan final Fase E).

---

## Fase R6 — Benahi fondasi evaluasi sentimen: official test set terkunci menggantikan 0.5816

**Konteks:** saat menyusun rencana ablation input-konteks (kenapa akurasi sentimen mentok 58,16%), ditemukan audit evaluasi independen yang sudah berjalan paralel (uncommitted di working tree: `docs/sentiment_evaluation_contract.md`, `scripts/*.py`, `data/evaluation/`, `reports/*.json`). Temuan audit itu: file test aktif (`storage/app/sentiment_finetune/test.jsonl`, 148 baris, dipakai berulang di Fase Q2/R5b) berstatus **"likely_contaminated"** — 14 overlap exact + 13 near-duplicate + 2 label conflict dengan train/validation. Angka `0.5816` sendiri cuma "historical_reference" — dihitung di split 120-baris yang sudah tidak ada lagi fisiknya (tertimpa saat export ulang Fase Q2, tidak pernah ter-tracking git karena di-gitignore). Audit itu sudah membangun 3 kandidat official test set (`scripts/build_official_evaluation_split.py`) tapi **semua gagal gate kualitas** (`exact_leak==0 and crossing==0 and unresolved==0 and min_support>=5 and prev==0`).

### Investigasi akar penyebab gate gagal
Dugaan awal (di `CODEX_HANDOFF.md` §4c, sebelum dieksekusi): kandidat gagal karena script berjalan "tanpa akses DB penuh" (fallback inventory). **Dugaan ini SALAH** — dicek langsung: `data/evaluation/source_population_v2.csv` (sumber data candidate lama) identik byte-per-byte dengan hasil jalan ulang `scripts/build_sentiment_source_inventory.py --require-database` (dikonfirmasi koneksi MySQL live, bukan fallback). Jadi data source sudah lengkap sejak awal.

**Akar penyebab sebenarnya:** grouping v1 (`data/evaluation/sentiment_groups_v1.csv`, dipakai default oleh `build_official_evaluation_split.py`) punya **1.131 dari 1.856 baris (61%) berstatus `conflict_status=mixed_label_conflict`**, dengan pool bersih tersisa cuma 685 baris dan **HANYA 3 contoh negative bersih di seluruh dataset** — mustahil memenuhi `min_support>=5`. Dicek `reports/mixed_label_group_root_cause_summary.json` (laporan audit yang sudah ada): **241 dari 253 grup "konflik" (95%) sebenarnya `same_text_different_entity_valid`** — artikel multi-emiten yang sama (mis. "Rekomendasi Saham BMRI, ANTM, AMRT") dilabeli berbeda per saham (VALID, karena sentimen memang bisa beda per emiten), tapi grouping v1 salah menganggapnya konflik label. Cuma 9/253 (`same_text_same_entity_true_conflict`) yang genuinely konflik nyata. Grouping v2 (`sentiment_groups_v2.csv`, sudah dibangun oleh audit sebelumnya, pakai `classification_instance_group_id` yang sadar target-entity) memperbaiki ini: **true conflict cuma 19/1888 (1%)**, pool bersih 1596 baris dengan distribusi kelas sehat (neutral 1209, positive 273, negative 114).

### Perubahan/artefak
- Adapter kolom (`data/evaluation/sentiment_groups_v2_adapted.csv`, sekali pakai) memetakan skema `sentiment_groups_v2.csv` (`classification_instance_group_id`, `true_conflict_status`, `canonical_target_entity`) ke skema yang diharapkan `scripts/build_official_evaluation_split.py` (`group_id`, `conflict_status`, `target_entity`) — **script asli TIDAK dimodifikasi**, cuma datanya diadaptasi.
- Re-run `scripts/build_official_evaluation_split.py --groups data/evaluation/sentiment_groups_v2_adapted.csv --seed 42` → **3 dari 3 kandidat lolos gate** (`exact_leak=0, crossing=0, unresolved=0, prev=0` untuk semua). Kandidat-a dipilih (rekomendasi otomatis script sendiri).
- `data/evaluation/official/sentiment-test-v1/` — official test terkunci: `test.jsonl` (283 baris), `train.jsonl` (1348 baris), `val.jsonl` (238 baris), `SHA256SUMS`, `README.md` (penjelasan lengkap root cause + cara build, supaya bisa direproduksi/diaudit ulang). Teks dibangun dari join `news_articles` pakai formula input produksi persis (`ExportSentimentFinetuneDatasetCommand::buildProductionInputText()`).
- `output/prediction_research/sentiment_official_test_v1_eval_report.json` — hasil evaluasi.
- `docs/sentiment_evaluation_contract.md` — status diubah `draft` → `locked`, tambah §12 (resolusi) dan §13 (ground-truth attestation, formalisasi konfirmasi verbal user soal independensi labeling manual).

### Hasil evaluasi produksi di official test baru
**`indobert_finetuned_v1` (model produksi, TIDAK diubah): macro-F1 = 0.8096, accuracy = 0.894** (positive F1 0.7209, neutral F1 0.9388, negative F1 0.7692), n=283 (neutral 215, positive 49, negative 19). Diverifikasi 2 kali independen dengan hasil identik (run inline + run background terpisah).

**Temuan penting:** kelemahan kelas positif yang didokumentasikan sepanjang Fase B/C/P/Q2 (F1 0.377 di test hard-case 120-baris lama) ternyata mencerminkan performa di subset yang SENGAJA sulit/ambigu, bukan performa nyata model. Di test representatif yang bersih ini, positive F1 = 0.7209 — jauh lebih sehat. **Angka `0.8096` ini menggantikan `0.5816` sebagai baseline acuan resmi untuk semua perbandingan model sentimen ke depan.**

### Verifikasi
- SHA256 checksum tervalidasi (`shasum -a 256 -c SHA256SUMS` → OK untuk ketiga file).
- File official test **di-commit ke git, TIDAK di-gitignore** (pelajaran dari insiden R5b sebelumnya).
- Model produksi tidak disentuh (tidak ada retrain di Fase R6).

### Status Fase R6: SELESAI. Official test set `sentiment-test-v1` terkunci & diverifikasi, baseline baru (0.8096) ditetapkan, ground-truth attestation diformalkan. R7 (ablation title/summary/full_text/entity) sekarang bisa mulai dengan fondasi evaluasi yang valid.

---

## Fase R7 (sebagian) — Ablation input konteks: title vs title+summary (R7c/R7d belum tuntas)

**Konteks:** setelah R6 menetapkan `sentiment-test-v1` sebagai official test yang valid, lanjut ke pertanyaan awal: apakah konstruksi teks input (judul saja / judul+ringkasan / diberi prefix nama emiten / teks penuh artikel) mempengaruhi kualitas klasifikasi sentimen. Semua varian dilatih dari pool training YANG SAMA (`data/evaluation/official/sentiment-test-v1`, train=1348, val=238) — cuma cara membangun teksnya yang beda — supaya perbandingan adil (bukan seperti membandingkan ke produksi v1 yang dilatih dari pool berbeda/lebih lama).

### Perubahan kode
- `quant/run_r7_ablation.py` — script eksperimen baru, 3 varian teks (`title_only`, `title_summary`, `entity_prefix`), reuse pola training standar proyek (Trainer API, CPU-only, `load_best_model_at_end` by val macro-F1).
- Data varian: `data/evaluation/ablation/{variant}/{train,val,test}.jsonl` — teks dibangun ulang dari `news_articles` per varian, label & article_id tetap sama persis dengan `sentiment-test-v1` (row selection tidak berubah, cuma representasi teksnya). Sanity check: varian `title_summary` diverifikasi identik byte-per-byte dengan `sentiment-test-v1/test.jsonl` asli sebelum eksperimen jalan.

### Bug ditemukan & diperbaiki: resume checkpoint gagal karena versi torch
Percobaan awal sempat disangka "proses mati diam-diam" berkali-kali (pola familiar dari insiden serupa sebelumnya) — ternyata **bukan mati**, tapi butuh waktu jauh lebih lama dari estimasi smoke-test (1 epoch smoke test 5,4 menit tidak merepresentasikan run penuh; run nyata 6 epoch = 58 menit s/d 164 menit tergantung panjang teks varian). Resume-logic yang ditambahkan (mirror pola Fase P) ternyata **gagal** saat benar-benar dipakai: `trainer.train(resume_from_checkpoint=...)` butuh `torch>=2.6` untuk load state optimizer (pembatasan keamanan CVE-2025-32434), sementara environment ini `torch==2.2.2`. Diperbaiki: resume-from-checkpoint-mid-training dihapus (tidak reliable di versi torch ini) — kalau training terganggu di tengah, terima sunk cost dan ulang dari awal, bukan coba resume paksa.

### Insiden operasional: laptop sleep menghentikan training
User melaporkan proses training tidak maju setelah 3 jam 40 menit — dicek: benar berhenti total (0 progress), penyebabnya laptop masuk sleep (background process dibekukan OS saat sleep, bukan lanjut otomatis). Solusi: bungkus training dengan `caffeinate -i` (mencegah idle sleep) untuk run selanjutnya. Catatan: `caffeinate -i` tidak bisa mencegah sleep kalau lid laptop ditutup fisik — itu di luar kendalinya.

### Hasil (3 dari 3 varian selesai)

| Varian | test macro-F1 | accuracy | positive F1 | neutral F1 | negative F1 | Waktu latih |
|---|---|---|---|---|---|---|
| `title_summary` (formula produksi, baseline lokal ablation ini) | **0.7018** | 0.8163 | 0.5106 | 0.892 | 0.7027 | 164 menit |
| `title_only` | 0.6998 | 0.8198 | 0.5833 | 0.8874 | 0.6286 | 58 menit |
| `entity_prefix` | 0.6663 | 0.8021 | 0.5306 | 0.8802 | 0.5882 | ~30 menit |

**Delta vs `title_summary`:** `title_only` -0,0020 (noise, bukan perbedaan nyata), `entity_prefix` **-0,0355 (nyata, terukur — LEBIH BURUK, bukan lebih baik)**.

**Kesimpulan R7b/R7c:** Tidak satu pun dari 3 varian input mengalahkan formula produksi (title+summary). `title_only` secara statistik tidak berbeda dari `title_summary`. `entity_prefix` justru **menurunkan** performa — menambahkan prefix nama saham/ticker di depan teks TIDAK membantu, berlawanan dengan hipotesis awal "target entity tidak jelas". Temuan ini konsisten dengan hasil audit R2 sebelumnya: rate mismatch label-vs-model TIDAK lebih tinggi di artikel multi-emiten (4,5%) dibanding artikel single-emiten (5,5%) — hipotesis "ambiguitas entity" memang sejak awal tidak didukung kuat oleh data.

**Rekomendasi:** pertahankan formula input produksi (title+summary) apa adanya — dari 3 varian yang diuji, tidak ada yang jadi tuas perbaikan akurasi sentimen lebih lanjut. Satu-satunya arah yang belum tuntas dieksplorasi dari diagnosis awal adalah cakupan `full_text` (R7a/R7d) — itu butuh investasi scraping nyata dan sudah terbukti tidak bisa diuji murah dengan data saat ini (0 contoh negative di antara 102 artikel yang punya `full_text`).

### R7a — Investigasi kelayakan scraping `full_text` (temuan, belum ada keputusan eksekusi)
Ditemukan kode uncommitted (`app/Console/Commands/ResolveGoogleNewsUrlsCommand.php`, `GoogleNewsRssFetcher::resolvePublisherUrl()`) yang menyelesaikan SETENGAH masalah: resolve URL redirect Google News ke URL publisher asli (prasyarat scraping), tapi BELUM ada scraper yang benar-benar ambil isi artikel. Diskusi dengan user mengoreksi asumsi awal ("perlu parser HTML per-situs, effort besar") — pendekatan generic content-extraction (algoritma model "readability", tanpa aturan per-situs) jauh lebih murah dan itu yang biasa dipakai industri. Risiko yang TETAP ada terlepas dari metode ekstraksi: paywall (teks memang tidak ada di HTML) dan rate-limit/robots.txt per-domain. **Keputusan bangun scraper belum diambil — effort masih perlu didiskusikan lagi.**

### R7d — Ablation full_text: TIDAK LAYAK dijalankan dengan data saat ini
Dicek: dari 102 artikel yang punya `full_text` terisi (semua dari `ojk_rss`, siaran pers regulasi), yang berlabel manual cuma 95 neutral + 7 positive + **0 negative**. Macro-F1 tidak bisa dihitung valid tanpa kelas negative sama sekali. Data terlalu bias (gaya bahasa OJK sangat formal/netral) untuk kesimpulan bermakna. **Ditunda sampai full_text diperluas (tergantung keputusan R7a) atau tidak dikerjakan sama sekali.**

### Status Fase R7: SELESAI TUNTAS. R7b/R7c (ablation title_only/title_summary/entity_prefix) selesai 3/3 varian — tidak ada yang mengalahkan formula produksi, `entity_prefix` malah terbukti lebih buruk. R7a (investigasi scraper full_text) selesai investigasi, keputusan bangun belum diambil (di luar scope Fase R). R7d ditutup sebagai tidak layak dengan data sekarang. **Model produksi `indobert_finetuned_v1` TIDAK diganti** — tidak ada kandidat dari eksperimen R7 yang layak dipromosikan. Sentimen ML dianggap sudah pada titik wajar untuk skripsi ini: 0,8096 macro-F1 di official test representatif (`sentiment-test-v1`, Fase R6), dengan tiga jalur perbaikan lanjutan (class weighting/Fase P, active learning/Fase Q2, ablation input/Fase R7) semuanya sudah dicoba dan didokumentasikan jujur (baik yang berhasil maupun gagal).

## Fase R1–R4 — Infrastruktur sampel label, audit, tipe berita, dan guideline

**Konteks:** setelah Fase P dan Q2 gagal mengalahkan produksi, akar masalah metodologis bergeser ke bias sampling: 988 label manual existing berasal dari hard cases/disagreement/ambigu, bukan sampel representatif populasi berita. Fase R1–R4 menyiapkan data lineage dan alat audit tanpa retrain dan tanpa menyentuh model produksi.

### R1 — Tag sumber sampling label
- `database/migrations/2026_07_22_000001_add_sample_method_to_sentiment_manual_labels.php` — tambah kolom nullable `sample_method` dan backfill label existing ke `legacy_hard_case`.
- `app/Models/SentimentManualLabel.php` — tambah whitelist `SAMPLE_METHODS` dan fillable `sample_method`.
- `app/Http/Controllers/SentimentValidationController.php` + `resources/views/sentiment-validation/index.blade.php` — label baru dari mode disagreement/Q2 menyimpan `sample_method=legacy_hard_case`; mode representatif masa depan disiapkan lewat nilai `representative_random` tapi belum dibuka.
- Verifikasi DB real setelah migrasi: 988 manual labels, 988 `legacy_hard_case`.

### R2 — Audit label manual berisiko salah/ambigu
- `app/Console/Commands/AuditSentimentManualLabelsCommand.php` — command `sentiment:audit-manual-labels` membandingkan label manusia dengan prediksi ML produksi yang tersimpan, flag mismatch ber-confidence tinggi, dan tidak mengoreksi label otomatis.
- Output real: `output/prediction_research/sentiment_label_audit_report.csv` dan `.txt`.
- Hasil real threshold 0.85: audit 988 label, flag 91 kandidat re-review. Breakdown tipe: macro 3, emiten_spesifik 82, multi_emiten_recommendation 6. Breakdown mismatch: positive→neutral 51, neutral→negative 6, negative→neutral 5, neutral→positive 22, negative→positive 6, positive→negative 1.

### R3 — Klasifikasi jenis berita diagnostik
- `app/Services/Sentiment/NewsArticleTypeClassifier.php` — classifier aturan ringan: `stock_id` null = `macro`; keyword rekomendasi/top pick/multi ticker = `multi_emiten_recommendation`; selain itu = `emiten_spesifik`.
- Classifier hanya lensa audit/guideline, tidak masuk fitur prediksi harga dan tidak mengubah pipeline live inference.
- Test: `tests/Unit/NewsArticleTypeClassifierTest.php`.

### R4 — Guideline labeling
- `docs/sentiment_labeling_guideline.md` — guideline label `positive|neutral|negative`, aturan ambigu, jenis berita, contoh nyata dari audit R2 dan sesi labeling Q2, plus cara memakai report re-review.

### Verifikasi
- `php artisan migrate --force` → migration R1 applied.
- `php artisan test tests/Feature/SentimentValidationTest.php` → 7 passed, 27 assertions.
- `php artisan test tests/Unit/NewsArticleTypeClassifierTest.php tests/Feature/AuditSentimentManualLabelsCommandTest.php` → 2 passed, 8 assertions.
- `php artisan sentiment:audit-manual-labels` → report R2 terbentuk; tidak ada label diubah otomatis.

### Status Fase R1–R4: SELESAI. Data lineage label, audit re-review, klasifikasi diagnostik, dan guideline siap. R5a BELUM dimulai karena wajib tanya user dulu kapan mulai label representatif.

## Fase R5a — UI label sampel representatif

**Konteks:** R1–R4 menyiapkan data lineage, audit, klasifikasi diagnostik, dan guideline. Sesuai aturan Fase R, R5a baru dimulai setelah user setuju mulai labeling representatif. Tujuan R5a adalah membuat jalur labeling acak dari populasi berita, bukan hard-case/disagreement/positive-biased seperti label lama.

### Perubahan kode
- `routes/web.php` — tambah `/sentiment-validation/representative` dan `/sentiment-validation/representative/next`.
- `app/Http/Controllers/SentimentValidationController.php` — tambah `representativeSample()` dan `representativeSampleNext()`; query mengambil artikel belum dilabel user dengan title + summary/content, `inRandomOrder()`, tanpa filter `ml_rule_agree`, tanpa filter probabilitas positif, dan tanpa prioritas label tertentu.
- Reuse view `resources/views/sentiment-validation/index.blade.php`; label yang dikirim dari mode ini menyimpan `sample_method=representative_random`.
- `tests/Feature/SentimentValidationTest.php` — tambah regression test bahwa mode representatif bisa mengambil artikel negatif biasa dan menyimpan `representative_random`.

### Verifikasi
- Cek DB real sebelum labeling: `representative_existing=0`, pool unlabeled user pertama `1888` artikel.
- `php artisan test tests/Feature/SentimentValidationTest.php` → 8 passed, 35 assertions.
- `php artisan test` → **435 passed**, 1910 assertions.

### Cara pakai
Buka:
```text
/sentiment-validation/representative
```
Label dengan tombol Positif/Netral/Negatif atau keyboard 1/2/3 mengikuti `docs/sentiment_labeling_guideline.md`. Target awal: **150–200 label representatif**. R5b tidak boleh dimulai sampai user eksplisit menyatakan label representatif sudah cukup terkumpul.

### Status Fase R5a: SIAP LABELING. UI representatif sudah tersedia; R5b DITAHAN sampai ada konfirmasi eksplisit bahwa label representatif cukup.

## Fase R5b — Export test representatif terkunci + evaluasi ganda

**Konteks:** user sudah mengumpulkan label representatif jauh di atas target awal. Cek DB real sebelum eksekusi: `representative_random=865`, `legacy_hard_case=1023`, total manual label `1888`. R5b boleh lanjut karena jeda manusia sudah terpenuhi.

### Perubahan kode
- `app/Console/Commands/ExportSentimentFinetuneDatasetCommand.php` — filter `--sample-method=`/`--exclude-sample-method=` tersedia untuk memisahkan split berdasarkan lineage label.
- `quant/finetune_sentiment_model.py` — reuse opsi `--model-out-dir`, `--data-dir`, `--report-json`, dan `--report-txt` agar candidate R5b tersimpan terpisah.
- `quant/evaluate_sentiment_models.py` — evaluasi produksi vs candidate di dua populasi terpisah: `legacy_hard_case` dan `representative_random`; gate memakai perbandingan candidate vs produksi pada file locked `legacy_hard_case` yang sama, sementara angka representatif dilaporkan sebagai metrik kedua.

### Artefak
- Dataset training/evaluasi hard-case: `storage/app/sentiment_finetune/r5b_train/` (`716/154/153`).
- Test representatif terkunci: `storage/app/sentiment_finetune/r5b_representative/test.jsonl` (`865` baris; train/val kosong karena semua label representatif saat ini ditahan untuk evaluasi populasi kedua).
- Salinan test set permanen yang di-commit: `output/prediction_research/sentiment_r5b_locked_tests/legacy_hard_case_test.jsonl`, `output/prediction_research/sentiment_r5b_locked_tests/representative_random_test.jsonl`, dan `SHA256SUMS`. Evaluasi R5b berikutnya wajib memakai path locked ini, bukan path `storage/app/sentiment_finetune/` yang bisa tertimpa export ulang.
- Candidate model: `storage/app/sentiment_model/indobert_finetuned_r5b_candidate/`.
- Report training: `output/prediction_research/sentiment_r5b_train_report.json` dan `.txt`.
- Report evaluasi ganda: `output/prediction_research/sentiment_r5b_dual_eval_report.json` dan `.txt`.

### Hasil evaluasi ganda
- `legacy_hard_case` (`n=153`, positive 47 / neutral 88 / negative 18): produksi `0.8768`, candidate `0.7141`, rule-based `0.4876`, stored ML `0.8768` macro-F1.
- `representative_random` (`n=865`, positive 55 / neutral 789 / negative 21): produksi `0.4624`, candidate `0.5443`, rule-based `0.4954`, stored ML `0.4624` macro-F1.
- Gate R5b dikoreksi setelah audit metodologi: **FAILED**. Perbandingan wajib apples-to-apples pada file test yang sama, yaitu candidate hard-case `0.7141` vs produksi hard-case `0.8768` (delta `-0.1627`). Konstanta lama `0.5816` tidak boleh dipakai untuk gate R5b karena file test R5b berbeda.
- Candidate terlihat lebih baik pada `representative_random` (`0.5443` vs produksi `0.4624`), tetapi ini metrik populasi kedua dan tidak cukup untuk promosi karena gate hard-case gagal.

### Verifikasi
- `quant/.venv-sentiment/bin/python quant/evaluate_sentiment_models.py` → report evaluasi ganda terbentuk ulang dari locked test files; gate `FAILED`.

### Status Fase R5b: SELESAI DENGAN TEMUAN NEGATIF. Candidate R5b **TIDAK BOLEH DIPROMOSIKAN** karena kalah dari produksi pada locked hard-case test yang sama. Produksi tetap `indobert_finetuned_v1`; candidate disimpan hanya sebagai artefak riset.

## Fase R7a (lanjutan) — Bangun command scraping `full_text`

**Konteks:** setelah R7a (investigasi kelayakan) melaporkan bahwa scraping generic content-extraction layak dicoba, user minta lanjut membangun scraper-nya secara langsung (bukan didiskusikan/direncanakan dulu). Hanya `ojk_rss` (90 artikel) yang punya `full_text` asli; 4 sumber lain (`rss_local`, `gnews`, `newsapi`, `business_site_search`, total ~470 artikel) menyimpan `source_url` langsung ke publisher (dicek dari kode fetcher masing-masing, bukan asumsi); `google_news_rss` (1.316 dari 1.888 artikel, 70%) menyimpan URL redirect Google News yang perlu diresolve dulu ke URL publisher asli sebelum bisa di-scrape.

### Keputusan desain
- Library ekstraksi: `fivefilters/readability.php` (v3.3) — dipasang sebelumnya di sesi ini setelah `andreskrey/readability.php` ditandai **abandoned** oleh composer.
- Resolusi URL redirect Google News: **TIDAK menulis ulang** logikanya. Ditemukan `app/Console/Commands/ResolveGoogleNewsUrlsCommand.php` + `GoogleNewsRssFetcher::resolvePublisherUrl()` sudah ada (uncommitted, kerjaan proses lain yang berjalan paralel) dan sudah solid: HTTP GET ke link Google News, ambil `effectiveUri` hasil redirect atau parse `<link rel="canonical">`/`og:url` dari HTML respons. Command baru `news:scrape-full-text` cukup **melewati (skip)** baris yang `source_url`-nya masih `https://news.google.com/%` — dijalankan `news:resolve-google-news-urls` dulu sebagai prasyarat, bukan didepend langsung di kode (menghindari fragility kalau proses lain itu berubah/belum final).
- Command baru TIDAK menyentuh/mengubah file uncommitted milik proses lain tersebut.

### Perubahan kode
- `app/Console/Commands/ScrapeArticleFullTextCommand.php` — command baru `news:scrape-full-text` (`--limit=100`, `--dry-run`, `--provider=*`, `--min-length=200`). Query artikel `full_text` kosong dengan `source_url` terisi dan bukan redirect Google News, fetch via `Http` (timeout & user-agent dari `config/news.php`, sama seperti fetcher lain), ekstrak isi dengan `Readability::parse()`, simpan hasil strip-tags + whitespace-normalized (limit 8000 char) ke `full_text`. Toleran-kegagalan per baris (fetch gagal/hasil terlalu pendek → skip & lanjut, tidak menghentikan batch), jeda 300ms antar-request untuk sopan ke publisher.
- `composer.json`/`composer.lock` — dependency `fivefilters/readability.php` (di-commit terpisah dari file uncommitted proses lain).
- `tests/Feature/ScrapeArticleFullTextCommandTest.php` — 7 test baru (`Http::fake`): fetch+simpan sukses, `--dry-run` tidak menyimpan, skip artikel yang sudah punya `full_text`, skip URL redirect Google News yang belum diresolve, toleransi kegagalan fetch (satu baris gagal tidak menghentikan baris lain), penolakan hasil ekstraksi di bawah `--min-length`, filter `--provider`.

### Verifikasi
- `php artisan test --filter=ScrapeArticleFullTextCommandTest` → 7 passed, 16 assertions.
- `php artisan test` → **449 passed** (baseline 442 + 7 baru), 1942 assertions.
- Smoke test dengan data DB nyata (`--dry-run` lalu `--limit` kecil) **BELUM dijalankan** — MySQL sedang tidak aktif di environment ini (`Connection refused`), sesuai konvensi proyek (MySQL manual-start, LaunchDaemon sudah ditolak user sebelumnya) tidak dinyalakan otomatis. Menunggu user menyalakan MySQL lewat XAMPP Control Panel untuk lanjut smoke test nyata.
- Command ini **belum dijadwalkan** di `routes/console.php` — sengaja belum, karena scraping ke publisher eksternal berulang otomatis punya risiko rate-limit/etika yang belum didiskusikan; dijalankan manual dulu sampai ada keputusan eksplisit soal jadwal.

### Smoke test nyata + 2 bug ditemukan & diperbaiki

MySQL kembali aktif. Dry-run kecil (8-16 baris) di `rss_local`/`gnews`/`newsapi`/`business_site_search` sukses tinggi (7/8, 8/8) — lanjut run penuh 470 baris tanpa `--dry-run`.

**Bug 1 — crash batch di baris ke-~240/470**: `fivefilters\Readability\Readability::_cleanStyles()` melempar `TypeError` internal (bukan `ParseException`) untuk HTML dengan struktur DOM comment tak lazim (`slashdot.org`, false-positive keyword match dari sumber lain). Catch block sempit (`catch (ParseException $e)`) tidak menangkapnya, seluruh proses artisan crash. Diperbaiki: `catch (\Throwable $e)` — satu halaman rusak tidak boleh menghentikan batch. Test lolos ulang (7/7), batch dilanjutkan dari titik terhenti (idempotent, query hanya ambil baris `full_text` masih kosong).

**Bug 2 (lebih serius, pre-existing, bukan kode baru) — `full_text` yang baru di-scrape terhapus lagi oleh `news:backfill-historical`**: dijalankan berbarengan untuk menutup gap berita akibat MySQL mati lama. `NewsAggregationService::refreshFromProvider()` di baris `updateOrCreate(...)` menulis `'full_text' => $rawArticle['full_text'] ?? null` tanpa syarat — begitu artikel yang SAMA (matched by `source_url`) di-refetch/dedup ulang dan payload fetcher tidak membawa `full_text` (berlaku untuk hampir semua fetcher, cuma `ojk_rss` yang bawa full_text sendiri), field itu ditimpa `null`, menghapus hasil scraping. Terverifikasi nyata: `with_full_text` turun dari 521 ke 508 setelah backfill jalan. Diperbaiki: fallback ke `$existingArticle?->full_text` (pola sama seperti `published_at` yang sudah benar 2 baris di atasnya). Regression test baru `test_refetching_existing_article_does_not_wipe_backfilled_full_text` di `tests/Unit/NewsAggregationServiceTest.php`. Baris yang sempat terhapus (~13-14) sudah dipulihkan lewat run ulang scraper (idempotent).

**Kegagalan sah (bukan bug)**: `tribunnews.com` mengembalikan HTTP 403 untuk User-Agent bot proyek (`SentimenaBot/1.0`), 200 untuk User-Agent browser — dites manual via curl. **Diputuskan tidak menyamar sebagai browser** untuk membypass ini (konsisten dengan konvensi semua fetcher lain di proyek yang identitas bot-nya jujur, dan menghormati keputusan publisher memblokir bot). Beberapa URL dari `newsapi`/`gnews` juga bukan berita saham sama sekali (`pypi.org/project/astra-tools`, artikel gosip `justjared.com`) — false-positive keyword match dari proses fetch berita lama, di luar scope Fase R7a.

### Hasil coverage `full_text` setelah smoke test + backfill gap berita

| Sumber | punya `full_text` |
|---|---|
| `ojk_rss` | 90/90 (sudah dari awal) |
| `rss_local` | 289/292 |
| `business_site_search` | 106/110 |
| `newsapi` | 17/30 (banyak diblokir tribunnews) |
| `gnews` | 9/40 (banyak diblokir tribunnews) |
| `google_news_rss` | 0/1.349 (masih perlu `news:resolve-google-news-urls` dulu — BELUM dijalankan) |
| **Total** | **523/1.923** |

Bonus: `news:backfill-historical --from=2026-07-22 --to=2026-07-24` juga dijalankan untuk menutup gap berita akibat MySQL mati lama (18 done_with_data, 4 done_empty, 8 failed_retry_next_run) — total artikel naik dari 1.890 ke 1.923.

### Status Fase R7a (lanjutan): COMMAND SIAP DAN TERVERIFIKASI DENGAN DATA NYATA. 2 bug ditemukan lewat run sungguhan (bukan cuma unit test) dan diperbaiki + diberi regression test. 523/1.923 artikel (27%) sekarang punya `full_text`, naik dari 90 (ojk_rss saja) sebelumnya. Langkah berikut yang BELUM dikerjakan: (1) jalankan `news:resolve-google-news-urls` untuk buka akses ke 1.349 artikel `google_news_rss` (70% dari total, potensi dampak terbesar), (2) setelah full_text coverage lebih luas, ulang R7d (ablation full_text) yang sebelumnya gagal karena 0 contoh kelas negative di 102 baris lama.

### R7a lanjutan — `google_news_rss` (70% korpus) terbukti jalan buntu, bukan sekadar sulit

Dicoba jalankan `news:resolve-google-news-urls` (command uncommitted milik proses lain) untuk buka 1.349 artikel `google_news_rss` yang URL-nya masih redirect Google. Hasil investigasi DB + tes langsung:

- **1.072/1.349 (79%) URL sudah permanen tidak bisa di-resolve**: ini bukan link Google News asli, tapi hash SHA1 buatan sendiri (`GoogleNewsRssFetcher::normalizeSourceUrl()` memotong URL asli yang >240 karakter dan menyimpan hash 32-char sebagai gantinya saat ingest — URL aslinya tidak pernah disimpan, jadi tidak ada cara mundur ke link asli lagi).
- **277/1.349 (21%) sisanya punya link Google asli** (format panjang `CBMi...`), tapi diuji dengan `GoogleNewsRssFetcher::resolvePublisherUrl()` di seluruh 277-nya (`--dry-run --limit=277`): **0 berhasil di-resolve**. Diverifikasi manual juga via `curl -L` + inspeksi HTML: Google sekarang mengarahkan balik ke `news.google.com` sendiri (bukan situs publisher) dan tag `<link rel="canonical">`/`<meta property="og:url">` di HTML statis juga menunjuk balik ke `news.google.com`, bukan URL publisher. Kesimpulan: Google sudah mengubah arsitektur halaman News jadi client-side-rendered (JS) — URL publisher asli tidak lagi tersedia di respons HTTP statis sama sekali, cuma bisa didapat lewat eksekusi JavaScript (headless browser). Ini perubahan di sisi Google, bukan bug di kode resolver.
- **Kesimpulan: `google_news_rss` (70% dari 1.923 artikel) sekarang 0% dapat diresolve lewat pendekatan HTTP biasa.** Bukan sekadar effort besar seperti dugaan awal R7a — benar-benar jalan buntu tanpa headless browser (investasi jauh lebih besar, di luar scope saat ini, tidak direkomendasikan untuk dikejar).
- Command `news:resolve-google-news-urls` dan `GoogleNewsRssFetcher::resolvePublisherUrl()` (uncommitted, milik proses lain) TIDAK diubah — temuan ini murni dari observasi perilaku live Google, bukan bug di kode itu sendiri.

### Status akhir cakupan `full_text`: 523/1.923 (27%) adalah PLAFON PRAKTIS saat ini
Dengan `google_news_rss` (70% populasi) terbukti buntu, dan 4 sumber lain sudah nyaris tuntas (`ojk_rss` 100%, `rss_local` 99%, `business_site_search` 96%, sisanya dibatasi blokir bot tribunnews.com), 523/1.923 adalah plafon realistis tanpa investasi headless browser atau sumber berita tambahan (mis. RSS CNBC Indonesia/Antara News yang sudah diverifikasi bekerja tapi belum diintegrasikan sebagai fetcher baru).

## Fase R7a (lanjutan) — Sumber pengganti `google_news_rss`: CNBC/Antara sudah terintegrasi, GDELT ternyata mati total (2 bug), Currents API sebagai kandidat baru

**Konteks:** setelah `google_news_rss` terbukti jalan buntu, user minta cari sumber berita lain untuk naikkan cakupan `full_text`. Investigasi bertahap: (1) cek CNBC Indonesia/Antara News — ternyata SUDAH terintegrasi sejak awal lewat `RssLocalFetcher::DEFAULT_FEEDS`, bukan sumber baru (185/292 dan 16/292 artikel `rss_local` sudah dari domain ini). (2) Cek `GdeltFetcher` — terdaftar di `config('news.multi_providers')` tapi kontribusinya **0 artikel** di DB. (3) Riset proyek serupa di GitHub + API berita gratis lain.

### rss_local: limit fetch dinaikkan
`routes/console.php` — jadwal pre-market `news:fetch --limit=20 --provider=rss_local` dinaikkan ke `--limit=40`. `RssLocalFetcher` selalu fetch semua feed penuh per run terlepas dari limit (limit cuma memangkas berapa yang disimpan per saham dari hasil yang sudah ditarik) — jadi menaikkan ini tidak menambah beban request ke publisher, cuma menyimpan lebih banyak dari yang sudah didapat.

### GdeltFetcher: 2 bug nyata ditemukan & diperbaiki (root cause kontribusi 0 artikel)
- **Bug 1 — query salah bentuk**: `fetchForStock()`/`fetchHistorical()` menggabungkan `AND (sourcelang:...)` langsung ke OR-chain kata kunci dari `StockKeywordMapper` (`"A" OR "B" OR "C" AND (...)`) tanpa membungkus OR-chain-nya dengan kurung. Diverifikasi langsung ke `api.gdeltproject.org`: GDELT menolak dengan pesan eksplisit `"Boolean OR's may only appear inside of a () clause."` — SETIAP request gdelt sejak awal gagal validasi ini, diam-diam.
- **Bug 2 — tanpa timeout/try-catch**: `fetchForStock()` (beda dari semua fetcher lain di proyek) tidak punya `->timeout()` maupun `try/catch`. GDELT terbukti bisa lambat (10-15 detik respons). Karena `refreshFromProvider()` di `NewsAggregationService` tidak membungkus per-provider call dalam try/catch, exception timeout yang tidak tertangkap ini **menggagalkan seluruh fetch untuk saham itu di siklus itu** — bukan cuma provider gdelt, provider lain yang sudah berhasil di-fetch untuk saham yang sama ikut hilang.
- **Bug 3 (ditemukan saat verifikasi live) — ambang panjang frasa**: setelah bug 1 diperbaiki, GDELT menolak lagi dengan pesan baru `"The specified phrase is too short"` — frasa `"BCA"` (3 char) dan bahkan `"BBCA"` (4 char) masih ditolak. Diverifikasi live 2x (ambang 4 masih gagal, ambang 5 berhasil lolos tanpa error) — `dropShortPhrases()` sekarang buang frasa terkutip di bawah 5 karakter sebelum OR-chain dibangun ulang.
- Perbaikan: `app/Services/News/GdeltFetcher.php` (`wrapQuery()` + `dropShortPhrases()`, dipakai di `fetchForStock()` dan `fetchHistorical()`). Test baru: `tests/Unit/GdeltFetcherTest.php` (7 test: mapping normal, toleransi timeout/exception, toleransi response error, toleransi payload invalid, pembungkusan kurung, pembuangan frasa pendek untuk kedua method).
- Verifikasi live: request query yang sudah diperbaiki dites langsung ke `api.gdeltproject.org` lewat kode asli (`GdeltFetcher::fetchForStock()`, bukan simulasi) — berhasil diterima (HTTP 200, tanpa pesan error), meski 0 artikel untuk BBCA di jendela waktu spesifik itu (variasi cakupan GDELT, bukan tanda gagal).
- **Catatan penting**: bug ini juga berarti `news:backfill-historical --source=gdelt` yang dijalankan sebelumnya (Fase R7a lanjutan, backfill gap MySQL) kemungkinan besar juga gagal senyap untuk provider gdelt — tidak diverifikasi ulang karena backfill itu sudah lewat, tapi perbaikan ini otomatis berlaku untuk backfill berikutnya.

### Riset kandidat sumber lain (GitHub + API gratis)
- **Currents API** (`currentsapi.services`) — free tier 1.000 request/hari, dukung Bahasa Indonesia, JSON bersih. Kandidat paling masuk akal untuk fetcher baru berikutnya (belum dibangun — butuh daftar API key dulu).
- NewsCatcher/Mediastack — free tier terlalu ketat (100/hari; Mediastack malah larang pemakaian non-komersial) — tidak direkomendasikan.
- `ExRonin/Stock-Scrapper-IDX` (GitHub) — proyek lain yang scrape `idx.co.id` **pakai Selenium (headless browser)**, mengonfirmasi independen temuan sebelumnya bahwa `idx.co.id` diblokir Cloudflare untuk HTTP biasa.
- Trafilatura (Python) dicek sebagai alternatif `fivefilters/readability.php` — benchmark independen menunjukkan F1 sedikit lebih tinggi (0,937 vs varian readability), tapi selisihnya tipis dan hasil ekstraksi kita sudah baik — tidak direkomendasikan ganti sekarang.
- Proyek Indonesia lain di GitHub (`idx-bei`, `idx-fundamental-analysis`, dll) mayoritas fokus data fundamental, bukan sentimen berita — tidak ditemukan proyek publik dengan metodologi evaluasi (walk-forward, test set terkunci, fine-tuned IndoBERT) sekelas proyek ini.

### Verifikasi
- `php artisan test --filter=GdeltFetcherTest` → 7 passed, 8 assertions.
- `php artisan test` → **457 passed** (450 + 7 baru), 1951 assertions.
- Live verification `api.gdeltproject.org` via kode asli → request diterima tanpa error (dilakukan 2x: setelah fix bug 1+2, lalu setelah fix bug 3/ambang 5 karakter).

### Status Fase R7a (lanjutan, sumber pengganti): GDELT DIPERBAIKI DAN AKTIF, limit rss_local dinaikkan, CNBC/Antara dikonfirmasi sudah terintegrasi (bukan pekerjaan baru). Currents API diidentifikasi sebagai kandidat fetcher baru berikutnya, BELUM dibangun (butuh API key). `idx.co.id` resmi dan Trafilatura dicek dan diputuskan TIDAK dikejar sekarang.

## Fase R7a (penutup) — Verifikasi `news:fetch` nyata: bug ke-4 ditemukan & diperbaiki, GDELT ditutup sebagai keterbatasan eksternal

**Konteks:** setelah GDELT diperbaiki (3 bug: query salah bentuk, tanpa timeout/try-catch, ambang frasa), user minta jalankan `news:fetch` sungguhan untuk 12 saham aktif supaya perbaikannya benar-benar terpakai. Dua kali run nyata dilakukan, masing-masing mengungkap temuan baru.

### Bug ke-4 ditemukan: `RssLocalFetcher` — pola sama persis dengan bug GDELT
Run pertama: `error 2` (BBCA dan TLKM gagal total). Dicek `storage/logs/laravel.log`: `rss.tempo.co/bisnis` (satu dari ~16 feed yang di-iterasi `RssLocalFetcher` per saham) timeout, dan karena tidak ada `try/catch` di sekitar `Http::get($feedUrl)`, exception yang tidak tertangkap menggagalkan `refreshFromProvider()` **untuk seluruh saham itu** — bukan cuma `rss_local`, provider lain (google_news_rss, business_site_search, newsapi, dst) yang sudah berhasil di-fetch untuk BBCA/TLKM di siklus itu ikut hilang. Pola identik dengan bug GDELT sebelumnya (satu request lambat meracuni semua provider lain via exception tak tertangani di level `refreshFromProvider()`).
- Perbaikan: `app/Services/News/RssLocalFetcher.php` — bungkus `Http::get($feedUrl)` per-feed dalam `try/catch`, log warning dan lanjut ke feed berikutnya (bukan menghentikan seluruh saham).
- Test baru: `tests/Unit/RssLocalFetcherTest.php::test_one_feed_timeout_does_not_abort_the_others`.
- Verifikasi run kedua: `error 0` (dari 2) — BBCA dan TLKM berhasil diproses penuh.

### GDELT: throttle ditambahkan, tapi hasil real-world tetap 0 — ditutup sebagai keterbatasan eksternal
Query GDELT sudah terbukti valid (fase sebelumnya), tapi run pertama tetap `gdelt: 0` di seluruh 10-12 saham — dicek log: **429 rate-limit di HAMPIR SEMUA request**, karena 12 saham diproses berurutan dalam satu proses PHP tanpa jeda, melanggar kebijakan GDELT "satu request per 5 detik". Diperbaiki: `GdeltFetcher::throttle()` — static timestamp per-proses, jeda minimum ~5,5 detik antar-request, dilewati saat test (`app()->runningUnitTests()`).
- Run kedua (dengan throttle aktif): `gdelt` **masih 0**. Dicek log: kombinasi 429 (rate-limit) dan **timeout koneksi ~10 detik** yang berulang — padahal `config('news.gdelt.timeout', 20)` di kode minta 20 detik. Ketidakcocokan ini (kode minta 20 detik, tapi log konsisten mentok di ~10 detik) mengindikasikan batasan di luar kode kita — kemungkinan pembatas jaringan sandbox ke `gdeltproject.org`, atau rate-limit GDELT di praktiknya jauh lebih ketat dari dokumentasi publik mereka ("1x/5 detik").
- **Keputusan: GDELT ditutup sebagai keterbatasan eksternal, bukan dikejar lebih jauh.** Ketiga bug di kode kita (query salah bentuk, tanpa timeout/try-catch, ambang frasa) sudah terbukti tuntas dan diverifikasi live sebelumnya — itu tanggung jawab kita dan sudah selesai. Sisa masalah (429/timeout dari sisi GDELT) di luar kendali kode, dan value tambahan yang didapat GDELT terhadap 5 provider lain yang sudah stabil (rss_local, google_news_rss, business_site_search, ojk_rss, gnews/newsapi) diperkirakan marginal. Tidak ada perbaikan kode lebih lanjut direncanakan untuk GDELT di proyek ini.

### Hasil akhir run nyata
- Total artikel naik dari 1.923 → **1.972** (+49) lewat provider yang sudah stabil (bukan gdelt).
- `php artisan test` → **458 passed** (457 + 1 baru), 1952 assertions.

### Status Fase R7a: DITUTUP TUNTAS. 4 bug fetcher ditemukan & diperbaiki lewat kombinasi live-verification dan run produksi nyata (bukan cuma unit test) sepanjang fase ini: GdeltFetcher (query salah bentuk, tanpa timeout, ambang frasa), RssLocalFetcher (tanpa try/catch per-feed). GDELT ditutup sebagai keterbatasan eksternal (rate-limit/network di luar kendali kode). Currents API tetap jadi kandidat sumber baru berikutnya kalau user mau lanjut (butuh API key, belum dibangun).

## Fase R7a (tambahan) — Integrasi CurrentsFetcher sebagai sumber tambahan (bukan pengganti)

**Konteks:** user eksplisit meminta klarifikasi dulu sebelum implementasi: Currents API **bukan pengganti** `google_news_rss` (buntu) atau `gdelt` (rate-limited) — cuma tambahan variasi sumber kecil, mirip `gnews`/`newsapi`. Setelah dikonfirmasi, diimplementasikan.

### Perubahan kode
- `app/Services/News/CurrentsFetcher.php` — fetcher baru, pola sama seperti `GNewsFetcher`: request ke `https://api.currentsapi.services/v1/search` (endpoint dikonfirmasi dari dokumentasi resmi + repo wrapper Python resmi mereka), `try/catch` + skip aman kalau `api_key` kosong (tidak crash, konsisten dengan pola fetcher lain).
- `config/services.php` — section `currents` baru (`api_key`, `api_base_url`, `language`, `timeout`, `user_agent`), pola identik `gnews`.
- `config/news.php` — `currents` ditambah ke `source_weights` (0.9, sejajar `gnews`), `multi_providers`, dan `source_priority`.
- `app/Services/News/NewsAggregationService.php` — fetcher `currents` didaftarkan ke `$this->fetchers`, otomatis ikut siklus fetch multi-provider yang sudah ada tanpa perlu ubah command/jadwal.
- `.env.example` dan `.env` — `CURRENTS_API_KEY=` (kosong) + config lain, pola sama `GNEWS_*`.
- Test baru: `tests/Unit/CurrentsFetcherTest.php` (5 test: mapping normal, tanpa API key, error response, exception jaringan, payload invalid).

### Catatan penting: BELUM AKTIF, butuh API key
`CURRENTS_API_KEY` di `.env` sengaja dikosongkan — mendaftar API key butuh membuat akun di `currentsapi.services`, itu tindakan milik user (bukan sesuatu yang bisa dilakukan otomatis). Selama kosong, `CurrentsFetcher::fetchForStock()` langsung `return []` tanpa request (perilaku aman, sama seperti `GNewsFetcher` tanpa key) — tidak mengganggu provider lain. Begitu user isi key-nya di `.env`, fetcher langsung aktif tanpa perubahan kode lagi.

### Verifikasi
- `php artisan test --filter=CurrentsFetcherTest` → 5 passed, 8 assertions.
- `php artisan test` → **463 passed** (458 + 5 baru), 1960 assertions.

### Status: KODE SIAP, MENUNGGU API KEY DARI USER UNTUK AKTIF DI PRODUKSI.

### Update: API key diisi user, Currents API terverifikasi hidup
User mendaftar dan mengisi `CURRENTS_API_KEY` di `.env`. Diverifikasi langsung lewat `CurrentsFetcher::fetchForStock()` untuk BBCA: **3 artikel nyata berhasil diambil** (judul + URL valid, mis. `republika.co.id`, `viva.co.id`). Currents API resmi AKTIF di produksi, ikut siklus fetch multi-provider otomatis.

## Fase R7d — Ablation full_text: dijalankan ulang, LAYAK dan menunjukkan hasil positif

**Konteks:** R7d sebelumnya ditutup sebagai tidak layak (0 contoh negative di antara 102 artikel `full_text`, semua dari `ojk_rss`). Setelah backfill R7a, dicek ulang distribusi kelas pada 523 artikel yang kini punya `full_text`.

### Cek kelayakan
Join `sentiment_manual_labels` × `news_articles.full_text IS NOT NULL`: **521 baris berlabel** dengan `full_text`, distribusi kelas **negative=28, neutral=423, positive=70** (naik drastis dari 0/95/7 sebelumnya). Sumbernya juga sudah beragam, bukan cuma `ojk_rss` yang formal:

| Sumber | negative | neutral | positive |
|---|---|---|---|
| `rss_local` | 24 | 222 | 43 |
| `business_site_search` | 4 | 82 | 18 |
| `ojk_rss` | 0 | 87 | 3 |
| lainnya (gnews/newsapi/unknown) | 0 | 32 | 6 |

Kesimpulan: **layak dijalankan**, dengan catatan 28 contoh negative masih tipis untuk split train/val/test (varians tinggi diperkirakan), bukan pengganti test set resmi.

### Perubahan kode
- `app/Console/Commands/ExportR7dFulltextAblationCommand.php` — command ekspor baru (`sentiment:export-r7d-fulltext-ablation`), TERPISAH dari `ExportSentimentFinetuneDatasetCommand` (command produksi, sengaja tidak disentuh untuk eksperimen sekali-pakai ini). Membangun 2 varian teks dari baris & split stratified YANG SAMA: `title_summary` (formula produksi persis, `buildProductionInputText()` disalin identik) dan `title_summary_fulltext` (formula produksi + `full_text` ditambahkan, potong 4000 karakter).
- `quant/run_r7d_fulltext_ablation.py` — adaptasi `run_r7_ablation.py`, 2 varian, direktori kandidat/report terpisah (`storage/app/sentiment_model/_r7d_ablation/`, `output/prediction_research/sentiment_r7d_fulltext_ablation_report.*`), 4 epoch (bukan 6, pool lebih kecil).
- Test baru: `tests/Feature/ExportR7dFulltextAblationCommandTest.php` (2 test: kedua varian punya baris/split identik cuma teksnya beda, baris tanpa `full_text` dikecualikan).

### Data
Ekspor nyata: 521 baris → split stratified 365/78/78 (train/val/test), label distribution konsisten di kedua varian (negative 20/4/4, positive 49/11/10, neutral 296/63/64).

### Hasil training (4 epoch, CPU, dibungkus `caffeinate -i` — total ~1 jam 53 menit untuk 2 varian, TIDAK terganggu sleep laptop kali ini)

| Varian | test macro-F1 | akurasi | positive F1 | neutral F1 | negative F1 | support (pos/neu/neg) |
|---|---|---|---|---|---|---|
| `title_summary` (baseline, formula produksi) | 0,5803 | 85,90% | 0,3077 | 0,9333 | 0,5000 | 10/64/4 |
| `title_summary_fulltext` | **0,6499** | 84,62% | **0,5217** | 0,9280 | 0,5000 | 10/64/4 |

**Delta vs baseline: +0,0696** — satu-satunya hasil POSITIF dari seluruh eksperimen ablation Fase R7 (R7b title_only -0,0020, R7c entity_prefix -0,0355, sekarang R7d full_text +0,0696). Kenaikan didorong terutama oleh F1 kelas positive (0,308→0,522); neutral relatif stabil; negative tidak berubah (0,500) tapi support cuma 4 baris test — angka ini tidak bisa dipercaya sebagai estimasi stabil.

### Catatan kejujuran metodologis — WAJIB dibaca sebelum menyimpulkan apa pun
- **BUKAN pengukuran ulang baseline resmi 80,96%.** Pool 521-baris ini jauh lebih kecil dan disjoint dari `sentiment-test-v1` (283-baris terkunci, Fase R6) — beda populasi, beda ukuran, tidak bisa dibandingkan head-to-head dengan angka resmi.
- **Test set cuma 78 baris, 4 di antaranya negative.** Delta +0,0696 di kelas positive/overall bisa jadi sinyal nyata, tapi dengan sampel sekecil ini variansnya tinggi — satu-dua baris berbeda arah prediksi bisa menggeser macro-F1 signifikan. Ini temuan AWAL yang menjanjikan, bukan hasil final siap-promosi.
- Kedua kandidat model TIDAK menyentuh produksi (`indobert_finetuned_v1` tetap tidak berubah), tersimpan terpisah di `storage/app/sentiment_model/_r7d_ablation/`.

### Verifikasi
- `php artisan test --filter=ExportR7dFulltextAblationCommandTest` → 2 passed, 19 assertions.
- `php artisan test` → **465 passed** (463 + 2 baru), 1979 assertions.
- Training real (bukan simulasi): log lengkap ada, kedua varian dilatih end-to-end di data nyata, dievaluasi di test split yang sama persis.

### Status Fase R7d: SELESAI, TEMUAN POSITIF (dengan syarat). Full_text augmentation menaikkan macro-F1 +0,0696 di pool eksploratif 521-baris — arah pertama yang positif dari seluruh Fase R7. BELUM cukup bukti untuk promosi ke produksi (sampel kecil, bukan test set resmi) — kalau mau dikejar lebih jauh, langkah berikutnya adalah menambah lebih banyak label pada baris yang sudah punya `full_text`, atau ulang eksperimen ini di pool yang lebih besar begitu cakupan `full_text` naik lagi.

## Fase R7a (penutup kedua) — Rebalance limit fetch per-provider, menjauh dari google_news_rss

**Konteks:** user tanya kenapa cakupan `full_text` keseluruhan cuma 26% padahal 5 dari 6 sumber sudah 96-100% — jawabannya karena `google_news_rss` menampung 70% populasi artikel (1.349/1.976) dan kontribusinya 0% (jalan buntu terverifikasi, Fase R7a sebelumnya). User minta diperbaiki dari sisi berita.

### Keputusan desain
`google_news_rss` **tidak bisa diperbaiki** (URL redirect-nya terbukti tidak bisa diresolve lewat HTTP biasa, di luar kendali kode kita). Yang BISA dilakukan: kurangi porsi artikel baru yang datang dari sumber ini ke depannya, alihkan ke 5 sumber yang sudah terbukti scrape `full_text` dengan baik. Ini tidak memperbaiki 1.349 artikel yang sudah tersangkut, tapi menggeser komposisi pertumbuhan artikel baru secara bertahap.

### Perubahan kode
- `config/news.php` — `provider_limit_multiplier` baru: `google_news_rss` dipangkas ke **0.3x**, sedangkan `rss_local`/`business_site_search`/`newsapi`/`currents` dinaikkan ke **1.5x**, `ojk` ke **1.2x**.
- `app/Services/News/NewsAggregationService.php` — `refreshFromProvider()` menerapkan multiplier ini per-provider saat memanggil `$fetcher->fetchForStock($stock, $effectiveLimit)`, menggantikan `$limit` konstan yang dulu dibagi rata ke semua provider.
- Test baru: `tests/Unit/NewsAggregationServiceTest.php::test_provider_limit_multiplier_scales_the_per_provider_fetch_limit` — verifikasi limit 20 jadi 6 untuk provider bermultiplier 0.3, jadi 30 untuk yang 1.5.

### Verifikasi
- `php artisan test --filter=NewsAggregationServiceTest` → 13 passed (1 baru), 37 assertions.
- `php artisan test` → **466 passed** (465 + 1 baru), 1980 assertions.
- Smoke test config nyata: `google_news_rss` limit dasar 20 → efektif 6; `rss_local`/`business_site_search`/`newsapi`/`currents` → efektif 30; `ojk` → efektif 24. Sesuai rancangan.

### Status: SELESAI. Efeknya baru terlihat di siklus fetch berikutnya (artikel baru), bukan retroaktif ke 1.349 artikel `google_news_rss` yang sudah ada.

## Fase S — Menaikkan akurasi prediksi harga: multi-horizon, algoritma alternatif, dan sinyal buy/sell

**Konteks:** user menyoroti akurasi model prediksi harga yang rendah (V6A 40,2% arah / 37,0% macro-F1; V6B 40,5% / 34,6%) dan minta dicari segala cara menaikkannya, plus opsi horizon h+1/h+3/h+7/h+30. Tiga eksperimen dijalankan berurutan; hasil ketiganya negatif untuk tujuan "naikkan akurasi", tapi menghasilkan penjelasan mekanis yang jelas KENAPA.

### S1 — Perbaikan metodologi: purge gap (dikerjakan sebagai prasyarat, bukan hasil)
`build_folds()` yang dipakai V6A/V6B **tidak punya jeda antara akhir train dan awal test**. Untuk label forward-return N hari, baris training terakhir labelnya dihitung dari harga yang beririsan dengan awal window test — kebocoran nyata yang membesar seiring horizon (jauh lebih parah di h+30 daripada h+5). Semua eksperimen Fase S memakai `build_folds_with_purge()` dengan jeda = panjang horizon. **Catatan penting: produksi V6A/V6B saat ini masih memakai versi tanpa purge gap** — artinya angka produksi 40,2% kemungkinan sedikit optimistis. Belum diperbaiki di produksi (perlu retrain + re-gating, keputusan terpisah).

### S2 — Ablation multi-horizon (h+1/h+3/h+7/h+30) × 2 algoritma
`quant/run_multi_horizon_experiment.py`. Fitur teknikal saja (`V2_NO_SENTIMENT_FEATURE_COLUMNS`, identik V6A), ambang kelas diskalakan `0,015 × sqrt(h/5)`, label dihitung ulang dari `data/stocks/{TICKER}.csv` (bukan menyalin label 5-hari dari dataset).

| Horizon | RandomForest macro-F1 / akurasi | GradientBoosting macro-F1 / akurasi |
|---|---|---|
| h+1 | 0,3790 / 39,98% | 0,3676 / 38,79% |
| **h+3** | **0,3770 / 40,51%** | 0,3743 / 39,71% |
| h+7 | 0,3553 / 38,84% | 0,3502 / 37,69% |
| h+30 | 0,3516 / 38,21% | 0,3546 / 38,21% |

**Temuan 1 — berlawanan dengan ekspektasi literatur.** Literatur umum (dan rekomendasi awal sesi ini) menyebut horizon lebih panjang cenderung lebih mudah diprediksi. Di data ini **justru sebaliknya**: h+7 dan h+30 lebih buruk dari h+1/h+3. Konsisten dengan temuan lama proyek ini bahwa pola "korelasi menguat seiring horizon" adalah artefak smoothing, bukan sinyal.

**Temuan 2 — GradientBoosting tidak mengalahkan RandomForest** di 3 dari 4 horizon. Ganti algoritma bukan tuas perbaikan di sini.

**Temuan 3 — h+3 marginal lebih baik** (40,51% vs produksi 40,2%), tapi selisih 0,3pp dengan setup berbeda (ada purge gap) — **tidak cukup untuk klaim perbaikan**, dan belum diuji signifikansi statistiknya.

### S3 — Diagnosis: kenapa mentok ~40%?
`quant/diagnose_prediction_accuracy.py`, fold/purge-gap identik S2, dibandingkan dengan baseline naif.

| | macro-F1 | akurasi |
|---|---|---|
| Tebak kelas mayoritas | 0,163–0,170 | 32,5–34,3% |
| Tebak acak proporsional | 0,326–0,333 | 32,7–33,4% |
| **RandomForest** | **0,377–0,379** | **40,0–40,5%** |

**Model punya sinyal asli**, bukan kebetulan: +21pp macro-F1 di atas tebak-acak, +5,7 s/d +8,0pp akurasi di atas tebak-mayoritas, konsisten di 8 fold. Jadi 40% bukan berarti "model tidak belajar apa-apa".

**Penyebab plafon rendah — feature importance (h+3, deskriptif):**

| Fitur | Importance |
|---|---|
| `atr14_pct` | 0,1916 |
| `atr_ratio` | 0,1737 |
| `return_5d` | 0,0807 |
| `return_3d` | 0,0784 |
| ... | ... |
| `market_regime_bullish` | 0,0038 |
| `volume_spike_flag` | 0,0020 |

Dua fitur teratas (36% gabungan) adalah **ukuran volatilitas — besaran gerakan, bukan arahnya**. Model lebih banyak belajar "kapan harga bergejolak" daripada "ke mana arahnya". Dua fitur (`market_regime_bullish`, `volume_spike_flag`) praktis tidak terpakai (<0,5%).

### S4 — Sinyal buy/sell berbasis confidence threshold (permintaan eksplisit user)
`quant/run_confidence_signal_experiment.py`. Alih-alih argmax (yang dipakai serving produksi sekarang), sinyal BELI hanya keluar kalau `P(up) ≥ ambang`; SELL kalau `P(down) ≥ ambang`. Ambang disapu 0,40–0,60, dua horizon (h+3, h+5), probabilitas ketat out-of-sample per fold.

**Beda dari Fase L yang sudah gagal:** Fase L memakai sinyal komposit berbasis aturan (hitung konfirmasi/warning teknikal + gate R:R), bukan confidence model. Mekanismenya benar-benar berbeda, jadi layak diuji ulang — tapi diukur dengan bar yang sama: **return aktual, bukan akurasi/presisi.**

**Temuan utama — hubungan confidence vs return TERBALIK:**

| Ambang (buy) | h+3 edge vs baseline | h+5 edge vs baseline |
|---|---|---|
| 0,40 | +0,098% | +0,307% |
| 0,45 | +0,383% | +0,137% |
| 0,50 | **−0,413%** | **−1,103%** |
| 0,55 | **−0,398%** | **−7,487%** |
| 0,60 | **−9,309%** | **−13,440%** |

Sinyal berkeyakinan TINGGI justru **jauh lebih merugi** daripada yang berkeyakinan rendah — kebalikan dari yang seharusnya terjadi kalau confidence model melacak skill arah. Penjelasannya nyambung langsung dengan S3: karena fitur dominan adalah volatilitas, model paling "yakin" persis saat pasar sedang bergejolak — dan di kondisi itu gerakan besar terjadi ke **dua arah**, sehingga rata-rata returnnya hancur.

**Baris ber-edge positif tidak bertahan setelah biaya transaksi.** 9 dari 20 kombinasi mengalahkan baseline, tapi itu setara lemparan koin untuk 20 sapuan. Baris yang sample-nya memadai (n≥300) diuji terhadap biaya round-trip IDX (komisi beli+jual plus pajak final penjualan 0,1%; realistis ~0,4–0,5%):

| side | h | thr | n | gross edge | @0,2% | @0,4% | @0,6% |
|---|---|---|---|---|---|---|---|
| buy | 3 | 0,45 | 391 | +0,383% | +0,183% | −0,017% | −0,217% |
| buy | 5 | 0,40 | 1034 | +0,307% | +0,107% | −0,093% | −0,293% |
| buy | 5 | 0,45 | 338 | +0,137% | −0,063% | −0,263% | −0,463% |
| buy | 3 | 0,40 | 950 | +0,098% | −0,102% | −0,302% | −0,502% |
| sell | 3 | 0,40 | 1180 | +0,081% | −0,119% | −0,319% | −0,519% |

**Pada biaya IDX yang realistis, SEMUA baris jadi negatif.** Baris ber-edge besar lainnya semuanya bersampel mikro (n=7, n=8, n=15) dengan tanda yang bolak-balik antar-ambang — ciri khas noise, bukan sinyal.

### Kesimpulan Fase S
1. **Tidak ada perbaikan akurasi yang layak dipromosikan.** Multi-horizon, ganti algoritma, dan confidence thresholding semuanya gagal memberi perbaikan yang meyakinkan.
2. **Tapi sekarang ada penjelasan mekanis yang jujur**: model belajar besaran volatilitas, bukan arah. Itu menjelaskan plafon ~40% DAN kenapa confidence tinggi justru merugi.
3. **Sinyal buy/sell tetap tidak layak dibangun** — ini kali ketiga proyek ini sampai pada kesimpulan yang sama lewat tiga mekanisme berbeda (Fase L rule-based komposit, Fase A/C sentimen sebagai fitur, sekarang S4 confidence threshold). Konsistensi lintas metode ini justru temuan skripsi yang kuat, bukan kegagalan.
4. **Arah yang belum tertutup**: fitur yang benar-benar informatif dan bukan turunan harga historis (mis. aliran dana asing, order book, data fundamental frekuensi tinggi). Bukan sekadar ganti algoritma/horizon.

### Verifikasi
- `quant/run_multi_horizon_experiment.py` → 8 fold walk-forward × 4 horizon × 2 algoritma, purge gap aktif, dataset 50.766 baris.
- `quant/diagnose_prediction_accuracy.py` → fold identik, 3 model dibandingkan apple-to-apple.
- `quant/run_confidence_signal_experiment.py` → 10.009 (h+3) / 10.011 (h+5) baris prediksi out-of-sample, 20 kombinasi ambang×sisi, semua dilaporkan termasuk yang buruk.
- Model produksi TIDAK disentuh di seluruh Fase S. Semua murni laporan riset.

### S5 — Purge gap diterapkan ke pipeline produksi (menutup item terbuka S1)

**Perubahan kode:**
- `quant/train_prediction_models.py` — `build_folds()` dapat parameter baru `purge_days: int = 0`. **Default 0 dipilih sengaja**: ada 13 pemanggil lain, sebagian besar script riset yang hasilnya sudah jadi temuan beku skripsi. Backward-compatibility diverifikasi terprogram di 24 konfigurasi (6 panjang seri × 4 kombinasi `min_train_days`/`test_window_days`): output `purge_days=0` **identik persis** dengan implementasi lama. Jadi tidak ada satu pun hasil riset lama yang berubah.
- `quant/train_production_models.py` — `evaluate_walk_forward()` menerima `purge_days`, dipanggil dengan `spec["official_baseline"]["horizon_days"]` (= 5 untuk kedua varian). Nilainya ikut ditulis ke metadata `retrain_evaluation.purge_days` supaya perubahan metodologi terlacak.
- `app/Console/Commands/RetrainProductionPredictionModelsCommand.php` — **jebakan penting yang ditangani**: gate promosi membandingkan `new_macro_f1` vs `old_macro_f1` dengan ambang degradasi 0,05. Metadata lama tidak punya `purge_days` (dibaca sebagai 0), yang baru punya 5 — dua angka itu **mengukur hal yang berbeda**, jadi membandingkannya akan salah membaca koreksi pengukuran sebagai kemunduran model dan menolak model yang sebenarnya tidak memburuk. Ditambah cabang: kalau `purge_days` lama ≠ baru, promosikan tanpa gating dengan keputusan `promoted_eval_methodology_changed` + log warning, lalu re-baseline. Retrain berikutnya (saat kedua sisi sudah 5) kembali digating normal — escape hatch ini sekali pakai, bukan bypass permanen.

**Test baru** (`tests/Feature/RetrainProductionPredictionModelsCommandTest.php`):
- `test_purge_gap_methodology_change_promotes_instead_of_falsely_rejecting` — produksi lama (tanpa `purge_days`) vs kandidat macro-F1 jauh lebih rendah (0,20 vs 0,35, delta -0,15 → normalnya DITOLAK). Memverifikasi model tetap dipromosikan dan `purge_days` 0→5 terekam di history.
- `test_degradation_gate_still_applies_once_purge_days_match` — kedua sisi `purge_days=5`, kandidat benar-benar lebih buruk → tetap ditolak jadi `candidate_only`. Membuktikan escape hatch tidak melumpuhkan gate.

**Dampak nyata ke angka produksi** (diukur langsung di dataset produksi, `output/prediction_research/purge_gap_impact.json`):

| Varian | purge=0 (lama) | purge=5 (baru) | Selisih |
|---|---|---|---|
| V6A `technical` | macro-F1 0,3701 / akurasi 40,22% | macro-F1 0,3693 / akurasi 40,11% | **−0,0008 / −0,10pp** |
| V6B `technical_sentiment` | macro-F1 0,3484 / akurasi 39,82% | macro-F1 0,3481 / akurasi 39,77% | **−0,0003 / −0,05pp** |

**Catatan validasi:** hasil `purge=0` mereproduksi persis angka produksi yang tercatat di `retrain_history.jsonl` (0,3701 vs 0,370109) — konfirmasi bahwa setup pengukuran ini benar, bukan jalur kode berbeda.

**Kesimpulan jujur:** kebocoran labelnya **nyata tapi dampaknya dapat diabaikan** (−0,08pp macro-F1). Jadi angka 40,2% yang selama ini dilaporkan **tidak menyesatkan secara material** — sekarang menjadi 40,1%. Perbaikan ini tetap layak dilakukan karena benar secara metodologi dan penting kalau nanti horizon diperpanjang (di h+30 kebocorannya akan jauh lebih besar), bukan karena angkanya berubah signifikan.

**Belum dijalankan:** retrain produksi nyata belum dieksekusi — angka di atas dari pengukuran langsung, bukan dari `prediction:retrain-production`. Retrain terjadwal berikutnya (Senin 07:00 WIB) akan otomatis memakai purge gap dan memicu cabang `promoted_eval_methodology_changed` sekali, lalu kembali normal.

### Status Fase S: SELESAI. Tiga eksperimen perbaikan akurasi (multi-horizon, algoritma, sinyal confidence) semuanya bertemuan negatif tapi menghasilkan penjelasan mekanis yang jelas: model belajar besaran volatilitas, bukan arah. Purge gap sudah diterapkan ke produksi dengan gate yang aman terhadap perubahan metodologi (dampak −0,08pp, dapat diabaikan). Model produksi V6A/V6B tidak diganti.

## Fase T — Survei sistematis semua indikator teknikal (BUMI & DEWA)

**Konteks:** user mengirim link chart TradingView BUMI dan minta "coba semua indicator untuk bisa memprediksi, mana yang paling benar". Link chart tidak dipakai — data OHLCV harian BUMI (6.236 hari, 25,1 tahun) dan DEWA (4.613 hari) sudah tersedia lokal dan lebih lengkap daripada apa pun yang bisa dibaca dari gambar chart; membaca pola dari gambar justru menambah bias visual yang jadi inti masalah di sini.

**Yang membedakan ini dari backtest biasa:** menyapu banyak indikator itu sah — yang membatalkan hasilnya adalah memilih pemenang setelah melihat hasil, lalu mempercayainya. Jadi survei ini sekaligus **mengukur apakah hasil survei itu sendiri layak dipercaya**.

### Metodologi
- `quant/run_technical_indicator_survey.py` — 32 sinyal (RSI, MACD, Bollinger, Stochastic, Williams %R, CCI, OBV, ATR, golden/death cross, gap, volume spike, streak, new high/low) × 4 horizon (h+1/3/5/10) × 2 saham. Indikator diimplementasi manual (bukan TA-Lib) supaya tiap formula bisa diaudit.
- **Split kronologis 70/30**: 70% pertama = periode DISCOVERY, 30% terakhir = HOLDOUT yang tidak dipakai memilih apa pun.
- Eksekusi konservatif: sinyal terbentuk di close hari t → **masuk di close hari t+1** (tidak boleh trading di bar yang masih terbentuk).
- Edge = rata-rata return setelah sinyal − base rate periode itu sendiri. Net edge dikurangi biaya round-trip **0,80%** (asumsi MID yang sudah dipakai riset trading BUMI/DEWA proyek ini).
- Sinyal dengan n<30 tidak dinilai.
- **Metrik penentu: korelasi rank (Spearman) antara edge di discovery vs edge di holdout.** Kalau "bagus di backtest" memang membawa informasi tentang masa depan, korelasi ini harus positif kuat. Kalau nol atau negatif, seluruh premis "cari indikator terbaik" gugur — sebagus apa pun baris teratasnya.

### Hasil: korelasi rank discovery → holdout

| | h+1 | h+3 | h+5 | h+10 |
|---|---|---|---|---|
| BUMI | +0,407 | +0,263 | +0,419 | +0,494 |
| DEWA | −0,084 | **−0,618** | **−0,504** | **−0,760** |

**DEWA: korelasinya NEGATIF dan signifikan** (h+10: ρ=−0,760, p<0,001). Artinya indikator yang paling bagus di backtest justru **paling buruk** ke depannya — bukan acak, tapi terbalik secara sistematis.

### Demonstrasi paling telak — DEWA h+10, 5 sinyal terbaik di backtest

| Sinyal | Edge discovery | Edge holdout | Net setelah biaya |
|---|---|---|---|
| `rsi14_overbought_gt70` | **+8,199%** | −3,817% | −4,617% |
| `three_consecutive_up` | +5,831% | −3,791% | −4,591% |
| `cci_overbought_gt100` | +5,800% | −1,065% | −1,865% |
| `atr_expansion` | +4,949% | −1,887% | −2,687% |
| `volume_spike_down` | +4,884% | −0,254% | −1,054% |

Kelimanya berbalik negatif. Kalau seseorang melakukan persis yang diminta ("cari indikator paling benar"), dia akan memilih RSI>70 dengan edge +8,2% — terlihat seperti tambang emas — dan rugi 3,8% di periode berikutnya.

### BUMI: ada yang bertahan, tapi bukan sinyal timing

BUMI korelasinya positif dan beberapa sinyal lolos net-of-cost di holdout (h+10): `rsi14_cross_down_70` (+3,02% net, n=34), `rsi14_overbought_gt70` (+1,93%, n=132), `macd_above_zero` (+0,99%, n=609), `macd_bullish_cross` (+0,96%, n=62).

Tapi tiga catatan yang membatalkan pembacaan optimistis:
1. `macd_above_zero` menyala di **609 dari ~1.400 hari holdout (43%)** — itu bukan sinyal masuk, itu **filter tren**: "berada di pasar saat tren naik". Sama persis dengan temuan riset lama proyek ini bahwa sumber untung di data ini adalah regime bullish + memegang saham, bukan aturan trading.
2. **Indikator yang sama memberi hasil berlawanan di dua saham sejenis**: `rsi14_overbought_gt70` = +2,73% (BUMI) vs −3,82% (DEWA). Kalau sinyalnya asli, tidak akan berbalik arah antar-saham sebatubara.
3. Sampel kecil pada net-positive terkuat (n=34 dan n=62).

### Temuan sampingan: teori TA klasik justru terbalik di sini
"Overbought" (RSI>70) menurut buku teks adalah sinyal JUAL. Di BUMI holdout, RSI>70 justru diikuti kenaikan (+2,73%). Ini perilaku momentum, bukan mean-reversion — kebalikan dari yang diajarkan. Sekali lagi menandakan aturan TA generik tidak bisa dipakai apa adanya di saham ini.

### Kesimpulan Fase T
1. **Pertanyaan "indikator mana yang paling benar" tidak punya jawaban yang stabil.** Di DEWA, jawabannya berbalik arah secara sistematis; di BUMI, yang bertahan hanyalah indikator tren/regime, bukan sinyal timing.
2. **Ini bukti kuantitatif langsung** bahwa memilih indikator berdasarkan performa backtest tidak valid di data ini — ρ negatif di DEWA adalah bukti, bukan sekadar peringatan teoretis.
3. Konsisten dengan Fase S (model belajar volatilitas, bukan arah) dan dengan riset BUMI/DEWA terdahulu (960 hipotesis TP/SL scan → DEAD; kandidat OOS gagal, retired).
4. **Nilai untuk skripsi**: ini bab metodologi yang kuat — memperagakan overfitting/data snooping dengan data nyata dan angka sendiri, bukan mengutip teori.

### Status Fase T: SELESAI. Tidak ada indikator yang layak dipromosikan jadi sinyal trading. Artefak: `quant/run_technical_indicator_survey.py`, `output/prediction_research/technical_indicator_survey.{json,txt}`.

## Fase U — Ganti target: dari ARAH ke BESARAN. Hasil positif pertama untuk prediksi

**Konteks:** user bertanya apakah ada cara lain memprediksi — menyebut "belajar pola" dan "banyak yang jual beli" — lalu menurunkan bar sendiri: "kasih tanda-tanda saja setidaknya". Dua bagian, jawabannya berbeda.

### Bagian 1 — "banyak yang jual beli": SUDAH DIUJI, GAGAL (jangan diulang)
Proksi tekanan beli/jual dari harga+volume (`buying_pressure`) sudah divalidasi walk-forward di sesi lampau (`output/prediction_research/buying_pressure_walkforward_validation.txt`): sebagai aturan langsung dir_acc **33,06%** (kalah dari majority 38,80% DAN random 35,53%, kalah di 7/8 fold); sebagai fitur tambahan ke model justru **menurunkan** macro-F1 −0,0126 dan dir_acc −0,0136 (5-seed, di luar rentang std). Klaim "~59% vs ~50%" di komentar kode lama tidak bisa direproduksi.

**Order flow yang sebenarnya tidak tersedia**: skema `stock_prices` dan CSV harga hanya berisi OHLCV — tidak ada bid/ask, net beli asing, atau order book. Menguji ide ini dengan benar butuh sumber data baru (IDX Data Services berbayar / API broker), bukan turunan lain dari volume.

### Bagian 2 — "kasih tanda-tanda saja": DIUJI, HASILNYA POSITIF
Reframe ini mengikuti langsung dari diagnosis Fase S: kalau `atr14_pct`+`atr_ratio` (ukuran BESARAN gerakan) mendominasi 36% feature importance sementara akurasi ARAH cuma ~40%, maka fitur yang sama seharusnya jauh lebih baik pada target yang memang cocok. Diuji: `|return 5 hari| >= ambang` → "big_move" vs "quiet". Fitur, fold, dan purge gap identik dengan V6A — hanya targetnya yang diganti.

`quant/run_volatility_warning_experiment.py`. Ambang pre-specified 3%/5%/7%, semua dilaporkan.

| Ambang | Base rate | Presisi RF | Lift vs base | Recall | macro-F1 (vs majority) |
|---|---|---|---|---|---|
| 3% | 39,4% | 50,59% | **+11,18pp** | 55,29% | 0,5708 (vs 0,3764) |
| 5% | 19,5% | 32,98% | **+13,47pp** (1,7×) | 55,79% | 0,5817 (vs 0,4456) |
| 7% | 10,3% | 23,64% | **+13,30pp** (2,3×) | 58,01% | 0,5801 (vs 0,4726) |

**Konsistensi: lift positif di 8/8 fold pada KEDUA ambang 5% dan 7%** — tidak sekali pun berbalik. Ini kontras tajam dengan seluruh temuan lain sesi ini (survei indikator Fase T: tanda berbalik; autokorelasi: tanda berbalik antar-periode; kandidat DEWA: gagal OOS).

**Perbandingan konteks:** prediksi ARAH memberi 40% vs 33% peluang acak = 1,2×. Prediksi BESARAN memberi hingga 2,3× — jauh lebih kuat, dengan metodologi yang sama persis.

### Catatan jujur yang WAJIB dibaca bersama angka di atas
1. **Liftnya menyusut seiring waktu.** Ambang 5%: fold 2022–2024 memberi +11,9/+25,8/+26,1/+17,4pp, tapi fold 2024–2026 cuma +13,8/+4,4/+3,8/+4,7pp. Pola sama di ambang 7%. Periode terbaru — yang paling relevan untuk penggunaan ke depan — justru yang paling lemah. Penyebab yang paling mungkin: base rate ikut naik di fold belakangan (17,6% → 25,8%), dan saat semua saham sedang bergejolak, mengetahui sesuatu akan bergejolak jadi kurang informatif.
2. **Akurasi keseluruhan LEBIH RENDAH dari majority baseline** (67,4% vs 80,5% di ambang 5%). Itu memang konsekuensi yang benar untuk sistem peringatan — majority mendapat akurasi tinggi dengan tidak pernah membunyikan alarm sama sekali (presisi & recall kelas big_move = 0%) — tapi jangan dilaporkan sebagai "akurasi naik".
3. **Sebagian besar alarm tetap salah.** Presisi 23,6% di ambang 7% berarti ~3 dari 4 peringatan meleset. Berguna sebagai indikator risiko, bukan sebagai kepastian.
4. **Ini BUKAN sinyal beli/jual dan tidak boleh dijadikan sinyal.** Yang diprediksi adalah besaran, bukan arah — informasinya berguna untuk ukuran posisi dan lebar stop, bukan untuk memutuskan beli atau jual. Pertanyaan arah/entry sudah ditutup terpisah di Fase L, S4, dan T.

### Status Fase U: SELESAI, TEMUAN POSITIF PERTAMA UNTUK PREDIKSI (dengan syarat). Target besaran terbukti jauh lebih bisa diprediksi daripada arah, konsisten 8/8 fold. Belum diintegrasikan ke produksi/DSS — kalau mau dipakai, harus dilabeli tegas sebagai peringatan volatilitas/risiko, bukan rekomendasi transaksi, dan trend penyusutan lift-nya wajib dipantau.
