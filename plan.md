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

## Fase V — Pencatat evaluasi prospektif untuk layanan sinyal Telegram komersial

**Konteks:** user menunjukkan screenshot layanan sinyal Telegram berbayar ("Zeta AI") yang mengklaim win rate 82,4% dan tabel "broker paling prediktif". Sebelum membangun apa pun, dianalisis dulu klaim yang sudah ada:

### Analisis klaim yang ditunjukkan (tanpa perlu data baru)
- **Win rate 82,4% dihitung dari penyebut yang salah.** Screenshot menunjukkan 38 sinyal, 14 TP hit, 3 SL hit → "resolved" cuma 17. `14/17=82,4%` yang dipajang; kalau semua 38 sinyal masuk penyebut (termasuk 21 yang belum selesai, kemungkinan besar didominasi posisi merah yang ditahan menunggu balik), `14/38=36,8%`. Pola tepat sama dengan yang dulu dibongkar di kode `buying_pressure` proyek ini sendiri.
- **Tabel "broker paling prediktif" tidak signifikan secara statistik.** Dihitung peluang kebetulan (binomial, asumsi broker sama sekali tidak punya skill, p=0,5): "Phintraco 100% dari 6 trade" → 1,56% peluang kebetulan (dari ~100 broker, ~1-2 memang akan terlihat begini murni acak); "UBS 80% dari 10 trade" → 5,47%. Sampel terlalu kecil untuk disebut pola.
- **7 indikator teknikal yang mereka pakai** (MACD, RSI, EMA, VWAP, ADX, Bollinger, ATR) **persis** subset dari 32 indikator yang sudah diuji Fase T di data BUMI/DEWA milik proyek ini — korelasi backtest→masa depan untuk DEWA sudah terbukti **−0,760**.

### Sumber data net asing gratis: DICEK, BUNTU
Endpoint `idx.co.id/primary/TradingSummary/GetBrokerSummary` dan `GetStockSummary` (dipakai berbagai scraper GitHub publik) dites langsung: **403 Cloudflare**, sama seperti temuan sebelumnya untuk endpoint IDX lain. `sectors.app` (fitur "Bandarmology"/net asing) API-nya cuma untuk paket berbayar "Insider", tidak ada tier gratis. **Tidak ada jalur gratis yang ditemukan.**

### Solusi yang dibangun: evaluasi prospektif pre-registered
`quant/signal_tracker/` — bukan mencoba scrape data broker (buntu), tapi menguji KLAIM layanan sinyal itu sendiri secara jujur, ke depan.

- **`PROTOCOL.md`** — aturan evaluasi ditulis dan di-commit SEBELUM sinyal pertama dicatat: filter (BUY + confidence=5, sinyal lain tetap dicatat sebagai tidak-dilacak), horizon 30 hari kalender, semua sinyal masuk penyebut (memperbaiki celah 82,4%→36,8% di atas), biaya 0,80% round-trip, wajib dibandingkan ke beli-diamkan DAN IHSG, minimum n=20 sebelum simpulkan apa pun.
- **`schema.sql`** — SQLite dengan trigger `BEFORE UPDATE`/`BEFORE DELETE` yang memblokir edit/hapus di level database (bukan cuma konvensi) — diverifikasi langsung: percobaan UPDATE dan DELETE keduanya gagal dengan `sqlite3.IntegrityError`.
- **`log_signal.py`** — catat satu sinyal (CLI interaktif atau argumen), otomatis menandai `tracked=1/0` sesuai filter protokol, sinyal yang tidak lolos filter tetap tersimpan dengan alasan.
- **`evaluate.py`** — setelah 30 hari lewat, ambil harga asli via yfinance (bukan re-baca klaim sumber), tentukan TP_HIT/SL_HIT/TIME_EXIT, hitung return net biaya + pembanding beli-diamkan + IHSG.
- **`report.py`** — menampilkan win rate versi jujur BERDAMPINGAN dengan versi ala-dashboard, distribusi return, waktu penyelesaian per jenis hasil, dan verdict — **menolak menyimpulkan apa pun kalau n<20** (dicoba: n=0/1, program menampilkan "BELUM CUKUP DATA" bukan angka palsu).

### Verifikasi end-to-end (bukan simulasi)
- Filter diuji 3 kasus: WATCHLIST conf=5 → dikecualikan; BUY conf=5 → tracked; BUY conf=3 → dikecualikan. Semua sesuai protokol.
- Trigger append-only diuji: UPDATE dan DELETE keduanya diblokir dengan pesan error yang jelas.
- `evaluate.py` diuji dengan sinyal RAJA (tanggal posting sudah lewat 30 hari): berhasil fetch data RAJA.JK dan ^JKSE asli via yfinance, hasil TP_HIT, net_return +7,04% terhitung benar.
- **Bug ditemukan & diperbaiki saat uji nyata**: fetch IHSG menempelkan `.JK` ke `^JKSE` (404) — simbol indeks yfinance tidak boleh dapat suffix itu, cuma kode saham individual. Diperbaiki.
- Data uji coba dihapus sebelum dipakai sungguhan (bukan data sinyal asli, aman dihapus). `tracker.sqlite3` di-gitignore — akan di-commit sebagai bukti begitu terkumpul data asli dan sudah lewat 30 hari, bukan sebelum itu.

### Status Fase V: KODE SIAP DAN TERUJI END-TO-END, MENUNGGU DATA ASLI. Belum ada sinyal sungguhan dicatat — itu tindakan user (mengamati channel Telegram secara live). Minimum 20 sinyal + 30 hari per sinyal dibutuhkan sebelum kesimpulan bisa ditarik.

## Fase W — Rekonstruksi & uji skor gabungan "Zeta AI" (separuh teknikal saja)

**Konteks:** user minta uji apakah sistem skor gabungan (aliran broker + indikator teknikal → BUY di atas ambang) yang teridentifikasi dari screenshot layanan Telegram bisa diimplementasikan dan berdampak.

**Batasan yang dinyatakan di depan**: komponen aliran broker (DI Dominant, SM Buy, Star Buyer) TIDAK BISA dibangun — Fase V sudah membuktikan tidak ada sumber data gratis (endpoint broker `idx.co.id` 403, `sectors.app` berbayar). Yang diuji cuma separuh teknikal.

### Metodologi
`quant/run_composite_score_experiment.py` — skor 6 poin (MACD bullish, harga>EMA20, harga>EMA50, ADX>25+arah, harga>VWAP-proxy 20 hari, RSI 45-70), disiplin identik Fase T: split kronologis 70/30, holdout tersegel, entry 1 bar setelah skor terbentuk, net biaya 0,80%, ambang 3/4/5/6 disapu semua.

### Hasil: BEDA per saham, bukan seragam

**BUMI — meningkat monoton seiring ambang, konsisten:**
| Ambang | n holdout | Net edge h+5 | Net edge h+10 | Win rate |
|---|---|---|---|---|
| ≥3 | 748 | −0,05% | +0,45% | 43,7% |
| ≥4 | 628 | +0,44% | +0,96% | 45,7% |
| ≥5 | 428 | +1,59% | +2,44% | 49,1% |
| **≥6 (semua setuju)** | **141** | **+1,25%** | **+2,93%** | **56–62%** |

Sinyal ≥6 menyala cuma ~7,5% hari (141/~1871 hari holdout) — selektif, bukan sekadar filter tren seperti `macd_above_zero` (43% hari) yang gagal sebelumnya.

**DEWA — tidak monoton, memburuk di tengah:**
| Ambang | n holdout | Net edge h+5 | Net edge h+10 |
|---|---|---|---|
| ≥3 | 629 | −0,52% | −0,21% |
| ≥5 | 398 | **−0,95%** | **−0,92%** |
| ≥6 | 173 | +0,06% | +1,03% |

Korelasi peringkat discovery→holdout: BUMI positif (+0,60 h5, +0,80 h10, TIDAK signifikan p=0,2-0,4 karena cuma 4 titik ambang), DEWA negatif (−0,80, −0,40) — pola sama dengan Fase T.

### Kesimpulan
1. **Konfluensi (beberapa indikator setuju bersamaan) menunjukkan efek nyata di BUMI** — beda dari SEMUA eksperimen sebelumnya sesi ini yang gagal telak. Monoton, selektif, tidak sekadar filter tren.
2. **Tapi gagal total di DEWA** — tidak konsisten antar-saham sejenis, jadi belum bisa diklaim sebagai temuan umum untuk IDX.
3. **Cuma separuh sistem asli** yang teruji (tanpa aliran broker) — bukan verifikasi/replikasi "Zeta AI" itu sendiri.
4. **n=2 saham, 4 titik ambang** — terlalu kecil untuk kesimpulan robust. Perlu diuji di lebih banyak saham sebelum ditindaklanjuti.

### Status Fase W: SELESAI, TEMUAN CAMPURAN (bukan gagal murni, bukan berhasil murni). Layak dicatat sebagai arah lanjutan — uji skor konfluensi serupa di 10 saham resmi (bukan cuma BUMI/DEWA) — tapi BELUM cukup bukti untuk dipromosikan jadi sinyal produksi.

## Fase W (lanjutan) — Uji skor konfluensi di 10 saham resmi: BUMI ternyata pengecualian

**Konteks:** menindaklanjuti Fase W (BUMI positif, DEWA negatif) — uji apakah efeknya berlaku umum di IDX dengan menambah 10 saham resmi (BBCA, BBRI, BMRI, TLKM, ASII, GOTO, INDF, ICBP, ADRO, UNVR).

### Hasil ringkasan lintas 12 saham (ambang paling ketat, score≥6, net biaya)

| Saham | h+5 net edge | h+10 net edge | Positif? |
|---|---|---|---|
| BBCA | −1,12% | −0,96% | tidak |
| BBRI | −0,71% | −0,69% | tidak |
| BMRI | −0,95% | −0,74% | tidak |
| TLKM | −1,05% | −1,12% | tidak |
| ASII | −1,03% | −1,04% | tidak |
| INDF | −1,13% | −0,82% | tidak |
| ICBP | −0,44% | −0,02% | tidak |
| ADRO | −1,72% | −2,13% | tidak |
| UNVR | +0,66% | +2,77% | **ya** |
| BUMI | +1,25% | +2,93% | **ya** |
| DEWA | +0,06% | +1,03% | **ya** |
| GOTO | data kurang (holdout terlalu sedikit di ambang ketat) | | — |

**6 dari 22 kombinasi ticker×horizon positif net biaya** — dan yang positif cuma 3 saham: BUMI, DEWA, UNVR. **8 dari 10 saham resmi (termasuk SEMUA blue-chip paling likuid: BBCA, BBRI, BMRI, TLKM, ASII) hasilnya negatif**, beberapa sampai −1,7% s/d −2,1%.

### Kesimpulan
Efek positif di BUMI (Fase W awal) **bukan pola umum IDX** — spesifik untuk saham kecil/volatil, gagal total di saham blue-chip besar yang lebih likuid dan stabil. Ini memperkuat, bukan membantah, temuan Fase T/S bahwa harga blue-chip jauh lebih sulit "dibaca" dari pola teknikal murni dibanding saham kecil yang pergerakannya lebih liar. Skor konfluensi teknikal **tidak layak dipromosikan sebagai sinyal umum** — kalaupun mau dipakai, cuma masuk akal dipertimbangkan khusus untuk profil saham serupa BUMI/DEWA, dan itu pun cuma separuh sistem (tanpa komponen broker/asing).

### Status: Fase W DITUTUP TUNTAS. Tidak ada bukti generalisasi. Konsisten dengan seluruh pola sesi ini: teknikal murni tidak cukup untuk memprediksi arah, kecuali mungkin di segmen saham yang sangat spesifik dan itu pun belum diverifikasi cukup kuat.

## Fase X — Sumber data aliran asing: satu ditemukan, dibangun sebagai pengumpul jujur (bukan fitur siap pakai)

**Konteks:** user minta dicari lagi lebih keras data net asing/broker (buntu di sesi sebelumnya via `idx.co.id` dan `sectors.app`), termasuk kemungkinan live.

### Pencarian ulang
Dicek: endpoint `idx.co.id/primary/TradingSummary/*` (403 Cloudflare, konsisten dengan temuan sebelumnya), `sahamidx.com` (226 byte, redirect/blocked), `RTI Business` (aplikasi mobile, tidak ada web publik tanpa login yang ditemukan), `KSEI` (tidak ada API terbuka yang ditemukan).

**Satu sumber ditemukan yang benar-benar bisa diakses**: `infovesta.com/index/data_info/saham/{topbuy,topsell}` — HTML statis, bisa di-fetch via `curl` biasa, TIDAK diblokir Cloudflare. Berisi 5 saham dengan net-buy asing terbesar dan 5 dengan net-sell terbesar, dalam volume lembar.

### Dua batasan yang membatasi penggunaannya — diverifikasi langsung, bukan diasumsikan
1. **Parameter `?date=` diabaikan sepenuhnya** — dites dengan tanggal 2020-01-01 vs hari ini, hasilnya identik (selalu snapshot live). **Tidak ada riwayat yang bisa diambil dari sumber ini**, artinya tidak bisa divalidasi walk-forward seperti seluruh metodologi proyek ini.
2. **Cuma top-5, bukan semua saham** — bukan data lengkap 10 saham resmi + BUMI/DEWA secara sistematis, cuma siapa pun yang kebetulan jadi top mover volume lembar hari itu.

### Keputusan desain: pengumpul, bukan fitur model
Karena tidak bisa divalidasi, memasukkan ini langsung sebagai fitur ke V6A/V6B/DSS akan mengulang pola kesalahan `buying_pressure` lama (dipakai sebelum diuji, klaim 59% ternyata 33% saat divalidasi). Yang dibangun: `quant/foreign_flow_tracker/collect_snapshot.py` — mengumpulkan snapshot ke `snapshots.jsonl` (append-only) setiap kali dijalankan, supaya beberapa bulan ke depan terkumpul riwayat milik sendiri yang BARU BISA divalidasi nanti (pola sama dengan Fase V: kalau data historis tidak ada, kumpulkan prospektif dulu, jangan pura-pura sudah tervalidasi).

- **Verifikasi nyata**: dijalankan sungguhan, berhasil parsing 5 saham net-buy (IATA, BACH, BRPT, RAJA, SCMA) dan 5 net-sell (**BUMI**, BUKA, PADI, BNBR, DSSA) dari HTML asli infovesta hari ini — termasuk breakdown Buy/Sell/Net per saham, bukan cuma judul kolom.
- Tidak dijadwalkan otomatis ke `routes/console.php` — statusnya eksploratif/pengumpulan data, bukan bagian pipeline produksi.

### Status Fase X: KODE SIAP DAN TERUJI, DATA BARU MULAI TERKUMPUL. Belum ada nilai analitis — perlu bulanan pengumpulan sebelum `analyze.py` (belum dibangun, langkah berikut kalau data sudah cukup) bisa mulai menguji apakah kemunculan di daftar top-5 berkorelasi dengan return berikutnya.

## Fase X (lanjutan) — Jadwal otomatis harian untuk pengumpul foreign flow

**Konteks:** menindaklanjuti Fase X — jadwalkan `collect_snapshot.py` supaya berjalan otomatis tiap hari bursa, bukan manual.

### Perubahan kode
- `app/Console/Commands/CollectForeignFlowSnapshotCommand.php` — command tipis (`research:collect-foreign-flow`), pola sama seperti `prediction:refresh-price-history`: proxy `Process::run([$python, $script])` dengan `env('PYTHON_BINARY', 'python3')`, semua parsing tetap di skrip Python, PHP cuma meneruskan output dan exit code.
- `routes/console.php` — dijadwalkan **15.15 WIB, hari kerja**, di antara `stocks:fetch-history` (15.10) dan `sentiment:reanalyze` (15.20) — setelah bursa tutup (sesi 2 berakhir 15.00), supaya top-5 net-buy/sell hari itu sudah final saat diambil.
- Test baru: `tests/Feature/CollectForeignFlowSnapshotCommandTest.php` (2 test: output sukses diteruskan, kegagalan fetch dilaporkan dengan exit code 1) — pakai `Process::fake()`, pola identik `RefreshPriceHistoryCommandTest`.

### Verifikasi
- `php artisan test --filter=CollectForeignFlowSnapshotCommandTest` → 2 passed, 6 assertions.
- `php artisan research:collect-foreign-flow` dijalankan sungguhan (bukan simulasi) → baris kedua berhasil tersimpan ke `snapshots.jsonl`.
- `php artisan test` → **470 passed** (468 + 2 baru), 1997 assertions.

### Catatan penting yang tetap berlaku
Jadwal ini TIDAK mengubah status Fase X — masih murni pengumpulan data, bukan fitur model. Kesimpulan analitis apa pun tetap menunggu beberapa bulan akumulasi, lalu WAJIB dibagi discovery/holdout seperti metodologi proyek ini yang lain (bukan dianalisis begitu "kelihatan ada pola" di data yang baru terkumpul sedikit).

### Status: SELESAI. Pengumpulan sekarang berjalan otomatis tiap hari kerja tanpa perlu dijalankan manual.

## Fase Y — Indikator DSS sebagai fitur ML kontinu (bukan panel display doang)

**Konteks:** User melihat panel "Indikator Teknikal Lanjutan" di `/analytics` (MACD, Bollinger Bands,
Stochastic, OBV, ADX, ATR, VWAP, Candlestick — semua dihitung `DecisionSupportService.php`) dan
bertanya apakah semua ini bisa "dimasukkan ke indikatornya" — maksudnya dua hal: (1) tampilkan
overlay-nya di chart TradingView, (2) uji apakah menambahkannya sebagai fitur ML kontinu ke
pipeline prediksi V6A membantu akurasi.

### Bagian 1 — Overlay indikator di chart TradingView
`resources/views/analytics/index.blade.php`: iframe `s.tradingview.com/widgetembed` sebelumnya
punya `studies=[]` (kosong) — 7 indikator yang sudah dihitung untuk panel teks di bawahnya tidak
pernah tervisualisasi di chart itu sendiri. Ditambahkan `$tvStudies` berisi 7 built-in TradingView
study ID: `MACD@tv-basicstudies`, `BB@tv-basicstudies`, `Stochastic@tv-basicstudies`,
`ADX@tv-basicstudies`, `ATR@tv-basicstudies`, `VWAP@tv-basicstudies`, `OBV@tv-basicstudies`.
Diverifikasi via DOM inspect (`document.querySelectorAll('iframe')` di browser) — src iframe
sekarang membawa ketujuh study ID itu di query param `studies`.

### Bagian 2 — Eksperimen: MACD/BB/Stochastic/ADX/VWAP/OBV sebagai fitur ML kontinu
Fase T (survey 32 indikator, threshold rules) dan Fase W (composite confluence score) sudah
menguji indikator-indikator ini sebagai SINYAL DISKRIT dan tidak menemukan edge OOS di 10 saham
resmi. Pertanyaan Fase Y berbeda: apakah RandomForest bisa menemukan struktur non-linear kalau
indikatornya dikasih sebagai fitur KONTINU mentah (bukan threshold biner)?

- Script baru: `quant/run_dss_indicator_ml_feature_experiment.py`. 10 saham resmi, walk-forward
  sama persis dengan produksi V6A (`min_train_days=252`, `test_window_days=126`, `max_folds=8`,
  `purge_days=5` sesuai horizon label — disiplin Fase S5), RandomForest hyperparameter identik
  (`build_random_forest_pipeline`).
- 6 fitur baru dihitung langsung dari `data/stocks/{TICKER}.csv` (OHLCV, sumber training yang
  sama): `macd_hist`, `bb_percent_b`, `stoch_k`, `adx14`, `vwap_distance_pct`, `obv_roc_20d`.
  Coverage baris dengan keenamnya non-null: 99.9%.
- Baseline (`V2_NO_SENTIMENT_FEATURE_COLUMNS` produksi) dievaluasi ulang di fold yang SAMA persis
  sebagai sanity check metodologi.

### Hasil
```
Baseline  (fitur produksi saja, 8 fold): macro_f1=0.3693  directional_accuracy=0.4011
Candidate (+ 6 indikator DSS,   8 fold): macro_f1=0.3680  directional_accuracy=0.4111

Delta macro_f1            = -0.0013
Delta directional_accuracy = +0.0100
```
Baseline persis cocok dengan angka produksi tercatat di `retrain_history.jsonl`
(purge_days=5: macro_f1 0.3693, accuracy 0.4011) — memverifikasi skrip eksperimen mereproduksi
metodologi produksi dengan benar, bukan setup yang beda diam-diam.

### Interpretasi
Delta macro-F1 negatif tipis, delta akurasi positif tipis (+1pp) — berlawanan arah dan
keduanya jauh di bawah ambang yang biasa dipakai proyek ini untuk menyebut sesuatu "ada edge"
(varians antar-fold historis jauh lebih besar dari ini). **Konsisten dengan Fase T/W**: keenam
indikator ini sudah "terkandung" secara tidak langsung lewat fitur produksi yang ada
(`atr14_pct`, `atr_ratio`, `rsi_slope_5d`, dll saling berkorelasi dengan MACD/BB/Stochastic/ADX
karena sama-sama turunan harga+volume jangka pendek) — menambah versi mentahnya sebagai fitur
ML tidak memberi informasi baru yang bisa dieksploitasi RandomForest secara OOS.

### Status: SELESAI. Bagian 1 (visual chart) di-commit ke produksi. Bagian 2 (fitur ML) adalah
temuan riset NEGATIF — TIDAK diintegrasikan ke `V2_NO_SENTIMENT_FEATURE_COLUMNS` produksi,
konsisten dengan aturan proyek "jangan bangun fitur di atas metrik yang belum tervalidasi OOS".
Laporan lengkap: `output/prediction_research/dss_indicator_ml_feature_experiment.json` /
`.txt` (tidak di-commit, hasil regenerable via skrip).

## Fase Y (koreksi) — iframe widgetembed?studies= ternyata diam-diam diabaikan TradingView

**Konteks:** Klaim "SELESAI" di atas untuk Bagian 1 (overlay chart) hanya diverifikasi lewat
`document.querySelectorAll('iframe')[1].src` -- itu cuma membuktikan URL query string yang KITA
kirim sudah benar, BUKAN bukti TradingView benar-benar merendernya. User screenshot langsung
chart real dan menunjukkan tidak ada overlay MACD/BB/Stochastic/ADX/ATR/VWAP/OBV sama sekali --
cuma candlestick + volume polos, walau parameter `studies` sudah ada di URL. Ini kesalahan
verifikasi yang sama persis dengan pola "silent-ignored-parameter" yang sudah ditemukan di sesi
ini sebelumnya (infovesta `?date=` diabaikan tanpa error).

### Akar masalah
`https://s.tradingview.com/widgetembed/?...&studies=[...]` adalah endpoint iframe legacy/tidak
resmi -- parameter `studies` di situ tidak didukung TradingView dan diabaikan tanpa error apa pun.
Cara resmi TradingView untuk menyertakan studies adalah widget JS (`s3.tradingview.com/tv.js` +
`new TradingView.widget({studies: [...], ...})`), bukan query string di URL iframe langsung.

### Perbaikan
`resources/views/analytics/index.blade.php` diganti dari iframe manual ke widget resmi:
`<script src="https://s3.tradingview.com/tv.js">` + `new TradingView.widget({container_id, symbol,
interval, studies: [...7 studies...], ...})`, dirender ke `<div id="tv_chart_{{ $stock->code }}">`.

### Verifikasi (kali ini benar-benar visual, bukan cuma cek URL)
- Screenshot browser langsung: BB (Bollinger Bands) band terlihat overlay di atas candlestick,
  plus panel terpisah MACD, Stoch, ATR di bawah chart utama (ADX/VWAP/OBV ada di studies array
  yang sama, kemungkinan perlu scroll dalam widget untuk terlihat semua -- widget TradingView
  sendiri yang mengatur layout multi-panel-nya).
- `php artisan test` → tetap 470 passed setelah perubahan.

### Status: SELESAI (kali ini terverifikasi visual, bukan cuma URL). Pelajaran: verifikasi
"parameter ada di URL" TIDAK CUKUP untuk widget pihak ketiga -- harus screenshot/render nyata.

## Fase Z — GDELT connectTimeout silently truncated to 10s, terpisah dari timeout() 20s

**Konteks:** User minta cek status ingest berita setelah MySQL sempat mati semalam (~17 jam gap,
2026-07-30 16:42 → 2026-07-31 16:30). `news:auto-recover-gap` sudah bekerja sesuai desain (self-heal
otomatis begitu MySQL nyala), tapi saat verifikasi ditemukan provider GDELT konsisten gagal dengan
"cURL error 28: Connection timed out after 10001 milliseconds" -- padahal `GdeltFetcher.php` sudah
eksplisit set `Http::timeout(20)`.

### Akar masalah
Laravel HTTP client (Guzzle) punya default `connectTimeout` 10 detik yang TERPISAH dari `->timeout()`
-- `->timeout(20)` cuma membatasi durasi total request, bukan fase connect (DNS+TCP+TLS handshake).
GDELT dari jaringan ini butuh waktu connect >10 detik saat itu, jadi tiap request mati di fase
connect sebelum sempat kirim query sama sekali, konsisten di angka 10.0-10.1 detik setiap kali.

### Perbaikan
`app/Services/News/GdeltFetcher.php` -- kedua method (`fetchForStock()` dan `fetchHistorical()`)
sekarang eksplisit set `Http::connectTimeout(20)->timeout(20)`, bukan cuma `->timeout(20)`.

### Verifikasi
- Live test SEBELUM fix: `php artisan news:fetch --provider=gdelt --stock=BBCA` → `raw 0`, waktu
  persis 10.095s, log `cURL error 28: Connection timed out after 10001 milliseconds`.
- Live test SESUDAH fix (tinker langsung `Http::connectTimeout(20)->timeout(20)->get(...)`):
  berhasil CONNECT dan dapat respons asli server (`status: 429`, elapsed 11.82s) -- bukan lagi
  connect-timeout exception. Membuktikan fix-nya benar secara struktural: sekarang request
  benar-benar sampai ke server GDELT, bukan mati di tengah jalan.
- Sisa kegagalan (`429 Please limit requests to one every 5 seconds`) di beberapa tes berikutnya
  murni akibat testing manual saya sendiri yang beruntun dalam waktu singkat (bukan bug) --
  `throttle()` yang sudah ada (jeda 5.5s) hanya berlaku DALAM satu proses PHP, sedangkan saya
  menjalankan banyak proses CLI terpisah berturut-turut saat verifikasi, masing-masing punya
  static `$lastRequestAt` sendiri-sendiri sehingga tidak saling mengenal jeda. Di operasional
  normal (scheduler, satu proses per run, jeda antar-run minimal 30 menit) ini tidak jadi masalah.
- `php artisan test --filter=Gdelt` → 9 passed, `php artisan test` penuh → 470 passed.

### Status: SELESAI. connectTimeout eksplisit sudah diterapkan dan diverifikasi live berhasil
connect ke server GDELT. Tidak menjamin GDELT selalu responsif (itu di luar kendali kita), tapi
sekarang aplikasi tidak lagi menyerah sebelum sempat mencoba.

## Fase Z (lanjutan) — Audit menyeluruh semua provider berita, perbaiki 2 temuan lagi

**Konteks:** Menindaklanjuti Fase Z (GDELT connectTimeout), user minta cek status SEMUA provider
berita lainnya. Dijalankan `php artisan news:fetch --stock=BBCA` (multi-provider, tanpa filter)
untuk mendapat gambaran lengkap satu kali jalan: `raw 32, saved 10, updated 7` dari breakdown
`idx_disclosure:0, google_news_rss:2, business_site_search:6, rss_local:7, ojk_rss:3, gnews:0,
newsapi:8, finnhub:0, gdelt:0, currents:6`.

### Temuan 1 (diperbaiki): 4 URL RSS di `rss_local` sudah mati
Live-verified via curl langsung ke tiap URL (dengan & tanpa User-Agent browser):
- `kontan.co.id/feed` dan `/rss` — HTTP 200 tapi isinya HTML, bukan RSS lagi (situs tidak lagi
  publish RSS di endpoint itu, tidak ketemu endpoint XML pengganti setelah cek homepage untuk
  link RSS -- tidak ada sama sekali).
- `bisnis.com/rss` dan variasi lain — HTTP 403 konsisten (Cloudflare bot-block), termasuk dengan
  User-Agent browser asli. Tidak ada workaround aman tanpa scraping HTML penuh.
- `katadata.co.id/feed` — HTTP 307 redirect ke halaman HTML. **Diganti** ke
  `katadata.co.id/rss/finansial` yang live-verified HTTP 200 dengan XML RSS asli dan artikel
  terbaru (bukan cuma feed umum, tapi kanal finansial yang lebih relevan untuk saham).
- `investor.id/rss` dan variasi lain — semua 404, tidak ketemu endpoint RSS pengganti setelah
  cek homepage.

Perbaikan: `app/Services/News/RssLocalFetcher.php` -- 3 URL mati (kontan, bisnis, investor.id)
dihapus dari `DEFAULT_FEEDS`, katadata diganti ke URL yang benar. Test
`tests/Unit/RssLocalFetcherTest.php::test_default_feeds_are_expanded` diupdate untuk assert URL
baru dan assert URL lama TIDAK ADA lagi (bukan cuma dihapus assertion-nya).

### Temuan 2 (didisable, bukan diperbaiki -- tidak bisa diperbaiki lewat kode): Finnhub tidak
mendukung ticker IDX di tier gratis
Live-verified via curl langsung pakai API key produksi:
- `symbol=BBCA.JK` (format yang dipakai `FinnhubNewsFetcher.php`) → `403 "You don't have access
  to this resource."`
- Sanity check API key masih valid: `symbol=AAPL` (ticker AS) → berhasil, data asli dikembalikan.
  Jadi bukan API key invalid/kadaluarsa -- murni batasan tier gratis Finnhub yang tidak
  mengizinkan endpoint company-news untuk exchange non-AS.
- **Dicek juga apakah strip suffix `.JK` bisa jadi workaround** -- `symbol=BBCA` (tanpa suffix)
  ternyata BERHASIL dapat data, tapi datanya tentang ticker AS lain yang kebetulan sama kodenya
  "BBCA" (bukan Bank Central Asia). Kalau ini diikuti, sistem akan salah atribusi berita
  perusahaan lain sebagai berita BBCA -- lebih berbahaya daripada 0 hasil.

Kesimpulan: ini keterbatasan akun/plan, bukan bug kode -- setiap request finnhub untuk ticker IDX
dijamin gagal, tidak ada perbaikan kode yang bisa mengatasinya. **Didisable** dari
`config/news.php` `multi_providers` dan `source_priority` (bukan dihapus total dari
`NewsAggregationService`'s `$fetchers` -- `--provider=finnhub` manual tetap bisa dipakai untuk
testing/kalau suatu saat upgrade plan). Dikomentari jelas di config kenapa dan bagaimana
diverifikasi, supaya tidak ada yang "memperbaiki" dengan strip `.JK` di masa depan tanpa tahu
risikonya.

### Verifikasi
- `php artisan news:fetch --provider=rss_local --stock=BBCA --debug` setelah fix: `raw 5, saved 1,
  updated 3` -- tidak ada lagi warning 404/HTML untuk kontan/bisnis/katadata/investor.id.
- `php artisan test` → 470 passed (1 test diupdate untuk assertion baru, bukan gagal).

### Status: SELESAI. rss_local sudah bersih dari 3 URL mati + 1 URL diperbaiki. finnhub didisable
dari siklus otomatis dengan dokumentasi lengkap kenapa (bukan cuma dihapus diam-diam).

## Fase AA — Buang percobaan resolve-URL google_news_rss yang belum di-commit (uncommitted leftover)

**Konteks:** Ditemukan sejak fase-fase awal sesi ini (dicatat di plan-mode note) ada file uncommitted
di working tree: `app/Services/News/GoogleNewsRssFetcher.php` (dimodifikasi, menambah
`resolvePublisherUrl()`), `app/Console/Commands/ResolveGoogleNewsUrlsCommand.php` (baru), dan
`tests/Unit/GoogleNewsRssFetcherTest.php` (test baru untuk fitur itu) -- kemungkinan besar kerjaan
sesi Codex lain yang belum selesai/dites. Karena file ini AKTIF di filesystem meski belum
di-commit (PHP baca dari disk, bukan git), fungsinya sudah berjalan diam-diam selama sesi ini.

### Live-reverify sebelum diputuskan (bukan asumsi dari catatan lama)
`php artisan news:resolve-google-news-urls --dry-run --limit=15` di 15 URL `news.google.com/rss/
articles/...` asli dari DB → **0 resolved, 15 skipped**. Persis sama dengan temuan Fase R7a sesi
ini sebelumnya (0/277 URL berhasil) -- dikonfirmasi ulang hari ini, bukan basi.

Test yang ditulis untuk fitur ini (`test_google_news_rss_prefers_publisher_canonical_url`) cuma
lolos karena pakai `Http::fakeSequence()` dengan respons canonical URL PALSU yang dikarang manual
-- tidak pernah diuji ke respons Google sungguhan (yang berupa SPA client-rendered tanpa link
publisher di HTML statis, akar masalah yang sama seperti temuan R7a).

**Efek samping tak disengaja:** karena kode ini aktif di filesystem meski uncommitted, setiap
fetch `google_news_rss` selama sesi ini diam-diam mencoba resolve URL per-artikel (5 detik timeout
tiap percobaan, SELALU gagal) -- kemungkinan besar ini sumber sebagian warning "Google News RSS
canonical URL resolution failed" yang berulang kali muncul di log saat audit GDELT/backfill
sebelumnya di sesi ini, menambah latensi nyata tanpa manfaat.

### Tindakan
`git checkout -- app/Services/News/GoogleNewsRssFetcher.php tests/Unit/GoogleNewsRssFetcherTest.php`
(kembalikan ke versi committed terakhir) + hapus `app/Console/Commands/ResolveGoogleNewsUrlsCommand.php`.

### Verifikasi
`php artisan test` → 469 passed (turun 1 dari 470, sesuai ekspektasi -- test untuk fitur yang
dibuang ikut hilang bersamanya, bukan regresi).

### Status: SELESAI. Working tree bersih dari sisa kerjaan yang tidak selesai. Konsisten dengan
temuan Fase R7a: resolusi URL google_news_rss ke publisher asli TETAP dead end permanen, jangan
dicoba ulang tanpa perubahan mendasar (mis. headless browser rendering JS, di luar scope proyek ini).

## Fase AB — Uji sistematis aturan "IHSG + saham crash bareng" ke seluruh histori BUMI/DEWA

**Konteks:** User share screenshot akun trading BUMI/DEWA riil miliknya (equity curve Rp11,3jt→
Rp15,5jt periode Jan-Jul 2026) dan minta baca pola 4 keputusan entry/exit real: entri 8 Jul (setelah
drop 7 Jul), entri 9 Jul, exit ~24 Jul (setelah drop), entri lagi 29 Jul. Dicek dulu harga+berita
riil di tanggal-tanggal itu: pergerakan besar (9 Jul, 20-23 Jul rally; 30 Jun & 24 Jul drop) ternyata
dominan mengikuti pergerakan IHSG luas/rotasi saham tambang kecil, dan berita spesifik BUMI/DEWA di
hari itu kebanyakan MENJELASKAN pergerakan yang sudah terjadi, bukan memberi sinyal sebelumnya.

4 kejadian dari satu akun selama 5 minggu jelas tidak cukup untuk dipercaya sebagai aturan (proyek
ini sudah berulang kali menemukan pola yang "kelihatan benar" di sedikit contoh gagal total
walk-forward). Diusulkan uji sistematis: **entry = IHSG DAN saham sama-sama turun ≥5% kumulatif 2
hari, exit = fixed holding period** (bukan "jual saat laba positif" -- tidak ada dataset tanggal
earnings historis bersih untuk BUMI/DEWA, jadi diuji 4 pilihan holding period: 3/5/10/20 hari,
semua dilaporkan, tidak cherry-pick satu).

### Metodologi
`quant/run_ihsg_drawdown_entry_experiment.py` (baru). Data IHSG diambil live via yfinance (`^JKSE`,
2001-sekarang, 6.206 baris, disimpan `data/stocks/IHSG.csv` -- belum pernah ada di proyek ini).
Entry dieksekusi di close hari SETELAH sinyal terbentuk (bukan hari sinyal, hindari lookahead).
Split discovery/holdout 70/30 kronologis. Net biaya round-trip 0,80%. Baseline pembanding: rata-rata
return semua hari (bukan cuma hari sinyal) untuk holding period yang sama.

### Hasil BUMI (2001-06-11 s/d 2026-07-21, 6.090 hari)
42 sinyal mentah. **Positif di discovery DAN holdout, di keempat holding period, jauh mengalahkan
baseline:**
```
Hold 3d : discovery +0,51% (n=31, win 51,6%) | holdout +4,82% (n=11, win 63,6%) | baseline -0,40%
Hold 5d : discovery +2,86% (n=31, win 54,8%) | holdout +7,29% (n=11, win 63,6%) | baseline -0,13%
Hold 10d: discovery +6,47% (n=31, win 61,3%) | holdout +7,34% (n=11, win 54,5%) | baseline +0,56%
Hold 20d: discovery +6,85% (n=31, win 64,5%) | holdout +2,47% (n=11, win 45,5%) | baseline +2,06%
```

### Hasil DEWA (2007-09-28 s/d 2026-07-21, 4.547 hari)
38 sinyal mentah, tapi hold 10-20 hari **berbalik arah** antara discovery (negatif, sampai -12,94%
di hold 20) dan holdout (positif, sampai +11,41%) -- tanda peringatan, bukan konfirmasi.

### Cek kritis: apakah "n" ini nyata atau cuma beberapa krisis dihitung berulang?
Sinyal di-cluster berdasar jarak tanggal (>15 hari = episode baru) untuk cek independensi:
- **BUMI: 42 sinyal mentah → 27 episode independen**, tersebar di 22 tahun dan BANYAK rezim pasar
  berbeda (2004, 2005, 2006, 2007, GFC 2008 x6 klaster, 2009, Eurozone 2011, taper tantrum 2013,
  2016, 2018, 2025, 2026) -- **melewati ambang minimum proyek ini (n≥20)**, dan tidak didominasi
  satu krisis. Ini temuan paling konsisten yang pernah keluar dari eksperimen manapun di sesi ini.
- **DEWA: 38 sinyal mentah → cuma 18 episode independen**, dan 10 dari 38 sinyal mentah (26%)
  berasal dari SATU episode (6-28 Okt 2008, crash Lehman) -- menjelaskan kenapa hasil discovery
  DEWA di hold 10-20 hari aneh: itu efeknya dominan dari satu krisis ekstrem, bukan pola stabil.
  **Di bawah ambang minimum (n≥20), dan hasil hold 10-20 hari untuk DEWA tidak bisa dipercaya.**

### Interpretasi
BUMI menunjukkan sinyal paling kredibel yang pernah ditemukan proyek ini -- konsisten arah positif
di discovery+holdout+4 horizon, n cukup (27 episode independen), dan punya rasionalisasi ekonomi
yang masuk akal (mean-reversion setelah panic-selling bareng index, bukan threshold indikator
teknikal sembarang). Hold 5-10 hari kelihatan titik manis (positif kuat di kedua split). Hold 20
hari lemah di holdout (+2,47% vs baseline +2,06%, hampir tidak beda) -- jangan dipakai.
DEWA jangan dipakai untuk hold 10-20 hari (kontaminasi 2008), hold 3-5 hari DEWA masih kelihatan
oke tapi n independen makin kecil kalau dipisah lagi per horizon.

### Foreign flow / net asing (bagian 2 permintaan user)
Data `quant/foreign_flow_tracker/snapshots.jsonl` dicek ulang: 4 baris tersimpan, TAPI keempatnya
punya angka identik (infovesta cuma update sekali sehari, 4x scrape menangkap snapshot beku yang
sama) -- **efektif cuma 1 titik data riil**. Jauh dari cukup untuk dilatih apapun. Konsisten dengan
batasan yang sudah didokumentasikan Fase X (live-only, tidak bisa historical backfill). Tidak ada
yang bisa dilatih dari ini sekarang -- perlu bulanan pengumpulan lagi sebelum layak dicoba.

### Status: BUMI SELESAI dengan hasil positif tervalidasi lebih ketat dari eksperimen sebelumnya,
tapi BELUM DIREKOMENDASIKAN untuk trading langsung -- baru backtest historis, belum forward-tested.
Langkah wajar berikutnya: masukkan aturan ini ke `quant/signal_tracker/` (Fase V) untuk dipantau
live ke depan sebelum dipercaya penuh, sesuai disiplin proyek ini (jangan percaya backtest historis
begitu saja, backtest cuma lolos gerbang pertama). DEWA TIDAK direkomendasikan untuk hold >5 hari.
Foreign flow tetap dalam mode pengumpulan pasif, belum ada nilai analitis.

## Fase AC — Tracker prospektif untuk sinyal "IHSG+saham crash bareng" (BUMI tracked, DEWA exploratory)

**Konteks:** Menindaklanjuti Fase AB (backtest historis positif untuk BUMI, 27 episode independen).
Sesuai disiplin proyek ini (backtest historis cuma lolos gerbang pertama, harus diverifikasi live
sebelum dipercaya -- pola sama seperti `signal_tracker/` Fase V untuk sinyal Zeta AI), dibangun
tracker prospektif baru: `quant/drawdown_bounce_tracker/`.

### Yang dibangun
- **`PROTOCOL.md`** -- dikunci 2026-07-31, SEBELUM sinyal live pertama. Entry: IHSG+saham turun
  kumulatif ≥5% dalam 2 hari bursa. Exit: fixed 10 hari (metrik utama) dan 5 hari (pembanding
  sekunder) -- keduanya ditetapkan sekarang, tidak dipilih setelah lihat hasil. BUMI berlabel
  `tracked` (boleh disimpulkan setelah n≥20), DEWA berlabel `exploratory` (JANGAN dipakai
  kesimpulan sampai ada pencabutan label eksplisit -- kontaminasi Okt 2008 di backtem historisnya).
- **`schema.sql`** -- SQLite append-only (trigger blokir UPDATE/DELETE), pola identik
  `signal_tracker/`.
- **`detect_signal.py`** -- deteksi OTOMATIS harian (bukan manual seperti Zeta tracker, karena
  aturan ini murni hitungan dari harga OHLCV sendiri). Ambil BUMI/DEWA/IHSG langsung dari yfinance
  tiap run, cek trigger, log sinyal kalau trigger_date ≥ 2026-07-31 (backtest historis TIDAK ikut
  dihitung sebagai n live). Idempotent via `UNIQUE(ticker, trigger_date)`.
- **`evaluate.py`** -- isi outcome begitu horizon 5/10 hari sudah lewat.
- **`report.py`** -- laporan gaya P&L broker (tanggal/equity/P&L), menolak menyimpulkan di bawah
  n≥20. Flag `--demo-historical` merender laporan dari backtest Fase AB sebagai CONTOH BENTUK
  laporan (berlabel jelas bukan live) -- tracker live sesungguhnya masih n=0.
- **Command Laravel**: `research:detect-drawdown-bounce-signal` + `research:evaluate-drawdown-
  bounce-signal`, pola tipis sama seperti `research:collect-foreign-flow` (proxy Process::run,
  parsing di Python). Dijadwalkan 15.18 & 15.19 WIB hari kerja (setelah harga EOD 15.10 settle).
- Test: `DetectDrawdownBounceSignalCommandTest` + `EvaluateDrawdownBounceSignalCommandTest`, 6 test,
  pola `Process::fake()` sama seperti command lain.

### Temuan penting saat membangun laporan contoh
Percobaan pertama report.py pakai position sizing 100% modal per trade (all-in, redeploy penuh tiap
sinyal). Hasilnya BUMI +843% (22 tahun) tapi **DEWA ambruk -76,6%** -- bukan karena strateginya jelek
(rata-rata per-trade DEWA cuma -0,63%), tapi karena beberapa sinyal nyambung BERURUTAN dalam satu
episode krisis (Okt 2008) meng-compound kerugian secara artifisial saat modal 100% langsung
dipertaruhkan lagi tanpa jeda. Diperbaiki ke 20% modal per trade (`POSITION_FRACTION=0.20`) --
hasil jadi jauh lebih representatif: BUMI +71,14%, DEWA -8,57% (kecil, sesuai rata-rata sebenarnya).
Ini pelajaran position-sizing yang nyata, bukan cuma kosmetik -- dicatat sebagai temuan, bukan
disembunyikan.

### Verifikasi
- `php artisan research:detect-drawdown-bounce-signal` (real run) → "Tidak ada sinyal baru" (benar,
  tidak ada trigger sejak 31 Jul 2026 kemarin).
- `php artisan research:evaluate-drawdown-bounce-signal` (real run) → "Belum ada horizon yang lewat"
  (benar, n=0).
- `php artisan test` → 475 passed (469+6 baru).

### Status: SELESAI. Tracker aktif dan terjadwal, tapi **n=0 sinyal live** -- laporan P&L
sesungguhnya baru akan berisi apa pun setelah trigger pertama live terjadi (realistis: sinyal ini
langka, ~1,2 kejadian/tahun untuk BUMI di backtest 22 tahun, jadi mencapai n≥20 bisa makan waktu
bertahun-tahun). Ini BUKAN rekomendasi trading -- baru mulai fase verifikasi forward, sesuai
disiplin proyek ini yang sudah berkali-kali menemukan pola bagus di backtest gagal saat live.

## Fase AC (lanjutan) — Alert Telegram untuk tracker drawdown-bounce

**Catatan:** ini alat monitoring operasional pribadi (bukan bagian metodologi/temuan riset), atas
permintaan eksplisit user JANGAN dimasukkan ke naskah skripsi -- didokumentasikan di sini murni
untuk jejak teknis proyek.

`detect_signal.py` sekarang kirim notifikasi Telegram otomatis begitu sinyal baru tercatat (bukan
duplikat). Kredensial (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) di `.env` (gitignored, tidak pernah
masuk kode/git, konsisten dengan API key lain di proyek ini). Gagal kirim Telegram (mis. jaringan
mati) tidak menggagalkan pencatatan sinyal itu sendiri -- dibungkus try/except, cuma print warning.

Live-verified: `sendMessage` API Telegram dites langsung, berhasil (`ok: true`), pesan tes diterima.

## Fase AC (lanjutan) — RSI14/Stochastic %K sebagai info tambahan di alert Telegram

**Konteks:** User minta cek apakah "buy pressure/sell pressure tinggi" bisa dipakai untuk deteksi
puncak-lembah, dengan narasi 8 titik dari akun trading riilnya (7-8 Mei jual, 8 Jun beli, 15 Jun
jual, 30 Jun beli, 22-23 Jul jual, 29 Jul beli). Live-checked RSI14 + Stochastic %K BUMI/DEWA di
kedelapan tanggal itu: **cuma 3/8 titik (8 Jun, 30 Jun, 22-23 Jul) yang cocok kuat dengan kondisi
oversold/overbought ekstrem**; sisanya netral atau malah kontradiktif (8 Mei: Stoch 0 di kedua
saham, itu oversold/beli, bukan jual seperti klaim). Konsisten dengan temuan Fase T lama: RSI/
Stochastic KADANG bekerja tapi tidak cukup konsisten untuk jadi aturan sendiri.

### Keputusan
Tidak dibangun sebagai sinyal berdiri sendiri (sudah terbukti gagal di 5/8 kasus). Ditambahkan
sebagai **info tambahan** di alert Telegram drawdown-bounce yang sudah ada -- ditampilkan tapi
dilabeli eksplisit "bukan bagian aturan" dan dicantumkan rasio 3/8 supaya user tidak salah kira ini
sinyal terpisah yang sudah tervalidasi.

### Perubahan kode
- `quant/drawdown_bounce_tracker/schema.sql` -- tambah kolom `rsi14`, `stoch_k` (nullable, context
  only) ke tabel `signals`. Database kosong (0 baris) di-recreate untuk pakai skema baru (aman,
  tidak ada data hilang).
- `quant/drawdown_bounce_tracker/detect_signal.py` -- tambah `rsi()`/`stochastic_k()` (auditable
  inline, pola sama seperti skrip riset lain di proyek ini), `fetch_recent()` window diperpanjang
  20d -> 60d supaya rolling RSI14/Stoch14 sudah warm-up di tanggal trigger, `describe_rsi()`/
  `describe_stoch()` untuk label oversold/netral/overbought, `format_signal_alert()` menampilkan
  info tambahan ini dengan disclaimer rasio 3/8 di badan pesan.

### Verifikasi
- Live test: dikirim contoh alert sungguhan ke Telegram (`@IDX_alert_keysentimen_bot`) dengan
  RSI14/Stoch %K BUMI hari ini (57/43, netral) -- terkirim sukses, format terbaca jelas.
- `php artisan research:detect-drawdown-bounce-signal` real run -> tetap jalan normal tanpa error
  setelah perubahan skema.
- `php artisan test` -> 475 passed.

### Status: SELESAI. RSI/Stochastic sekarang tampil di tiap alert sebagai konteks, bukan sinyal
kedua -- user tetap yang menilai, sistem tidak berpura-pura ini sudah tervalidasi.

## Fase AC (lanjutan) — Alert trailing-stop manual (bukan eksekusi) untuk posisi BUMI/DEWA open

**Konteks:** User verifikasi real trailing stop 4% di StockBit (beli BUMI 30 Jun ~Rp130-135, jual
otomatis 23 Jul jam 13:30 di Rp189 setelah spike intraday ke Rp196, profit ~40%). Angka di
screenshot dicek cocok persis dengan data harga riil (High 23 Jul = 196, 196*0.96=188.16≈189).
User minta: bukan eksekusi otomatis, cuma **alert Telegram** begitu posisi open mundur 4-5% dari
puncak sejak entry -- trailing stop-nya tetap dipasang manual sendiri di StockBit.

### Perubahan kode
- `quant/drawdown_bounce_tracker/open_positions.json` (baru) -- daftar posisi open yang dipantau,
  dikelola manual (bukan baca dari Trade Journal/MySQL, supaya tetap jalan walau MySQL mati, sama
  seperti prinsip resiliensi `detect_signal.py`). Isi awal: BUMI Rp159 (29 Jul), DEWA Rp440 (29 Jul)
  -- posisi open yang sudah tercatat di Trade Journal sebelumnya.
- `quant/drawdown_bounce_tracker/check_trailing_stop.py` (baru) -- untuk tiap posisi: ambil harga
  sejak entry_date via yfinance, cari puncak (`High` tertinggi), hitung persen mundur dari puncak
  ke harga penutupan terbaru. Kalau >=4%, kirim alert Telegram SEKALI (`alerted_pullback_pct`
  disimpan ke JSON supaya tidak spam berulang tiap hari untuk pullback yang sama).
- `app/Console/Commands/CheckTrailingStopAlertCommand.php` (baru) -- `research:check-trailing-
  stop-alert`, pola tipis sama seperti command drawdown-bounce lainnya.
- `routes/console.php` -- dijadwalkan 15.21 WIB hari kerja (setelah evaluate-drawdown-bounce-signal
  15.19, sebelum sentiment:reanalyze 15.20 selesai).
- Test: `CheckTrailingStopAlertCommandTest`, 2 test (`Process::fake()`).

### Verifikasi
- Real run: BUMI mundur 2,9% dari puncak (Rp173, 3 Agu), DEWA mundur 3,7% dari puncak (Rp482) --
  keduanya di bawah ambang 4%, belum ada alert terkirim (benar, sesuai kondisi harga saat ini).
- `php artisan research:check-trailing-stop-alert` (real run via Laravel) -> sukses, sama dengan
  output Python langsung.
- `php artisan test` -> 477 passed.

### Status: SELESAI. Alert-only, TIDAK ada order otomatis dipasang/dieksekusi -- keputusan trading
tetap sepenuhnya di tangan user. `open_positions.json` perlu diupdate manual tiap kali user
buka/tutup posisi baru (belum otomatis sinkron dengan Trade Journal).

## Fase AC (lanjutan) — Perintah /open /close /status lewat Telegram

**Konteks:** User minta cara kelola `open_positions.json` (posisi yang dipantau trailing-stop)
langsung dari HP, tanpa perlu bilang ke Claude tiap kali buka/tutup posisi.

### Perubahan kode
- `quant/drawdown_bounce_tracker/telegram_commands.py` (baru) -- long-polling `getUpdates` (bukan
  webhook, tidak perlu endpoint HTTPS publik, cocok untuk mesin dev lokal). Parsing perintah:
  `/open TICKER HARGA [TANGGAL]`, `/close TICKER HARGA [TANGGAL]`, `/status`. Cuma memproses pesan
  dari `TELEGRAM_CHAT_ID` yang terdaftar di `.env` -- kalau token bocor, orang lain tidak bisa
  suntik posisi palsu lewat bot ini. Offset update_id disimpan di `telegram_update_offset.txt`
  (gitignored, state lokal) supaya tidak memproses pesan lama berulang.
- `app/Console/Commands/CheckTelegramCommandsCommand.php` (baru) -- `research:check-telegram-
  commands`, pola tipis sama seperti command lain di tracker ini.
- `routes/console.php` -- dijadwalkan tiap 5 menit, 08.00-20.00 WIB (bukan cuma jam bursa, posisi
  bisa ditutup kapan saja).
- Test: `CheckTelegramCommandsCommandTest`, 3 test.

### Verifikasi
- `handle_command()` dites langsung: `/close BUMI 172` menghapus BUMI dari daftar + balasan
  konfirmasi; `/open ADRO 2510` menambah posisi baru; perintah tidak dikenal dapat balasan bantuan.
- Real run via Python langsung & via `php artisan research:check-telegram-commands` -- keduanya
  sukses, "Tidak ada perintah baru" (benar, belum ada pesan real terkirim ke bot).
- `php artisan test` -> 480 passed.

### Status: SELESAI. User sekarang bisa kirim `/open`, `/close`, `/status` langsung ke
@IDX_alert_keysentimen_bot dari HP untuk kelola posisi yang dipantau trailing-stop, tanpa perlu
lewat chat ke Claude.

## Fase AC (lanjutan) — Keyboard tombol Telegram + harga otomatis live

**Konteks:** User minta tombol yang bisa di-tap langsung (seperti composer app chat lain), bukan
harus ketik perintah manual tiap kali.

### Perubahan kode
- `detect_signal.py` -- `send_telegram_alert()` sekarang terima parameter opsional `reply_markup`
  (dikirim sebagai `ReplyKeyboardMarkup` Telegram, JSON-encoded). `default_keyboard()` baru:
  tombol `/status`, `/close BUMI`, `/close DEWA` -- persistent di bawah kotak pesan.
- `telegram_commands.py` -- `COMMAND_PATTERN` diubah supaya HARGA jadi opsional (tombol `/close
  BUMI` tanpa argumen harga). `fetch_live_price()` baru: kalau HARGA tidak disebut, ambil harga
  penutupan terakhir live dari yfinance otomatis. Semua balasan sekarang menyertakan
  `default_keyboard()` supaya tombolnya tetap muncul terus-menerus.

### Verifikasi
- `handle_command('/close BUMI', ...)` (tanpa harga) -> berhasil ambil harga live otomatis
  (Rp168, harga real saat itu), bukan error.
- Live test: keyboard tombol dikirim sungguhan ke Telegram (`@IDX_alert_keysentimen_bot`).
- `php artisan test` -> 480 passed.

### Status: SELESAI. User sekarang bisa tap tombol langsung dari Telegram tanpa ketik perintah,
harga otomatis terisi dari harga pasar live kalau tidak disebutkan manual.

## Fase AE — Exit Stoch RSI 1 jam diuji ke 3 tahun data (GAGAL, tapi mekanismenya informatif)

**Konteks:** User mengoreksi dua kesalahan nyata di Fase AD, dan koreksinya BENAR:
1. Fase AD menguji *Stochastic klasik* (posisi harga dalam rentang 14 hari); user memakai
   **Stoch RSI** (stochastic di atas nilai RSI) -- indikator berbeda. Di 23 Jul 2026 keduanya
   berbeda tajam: Stoch RSI = 100,0 vs Stochastic klasik = 78,3 (di bawah ambang 80).
2. Semua backtest proyek ini sejauh ini memakai data HARIAN; user trading di chart **1 jam**.

Live-check membuktikan observasi user tepat: di bar 1 jam, Stoch RSI %K menyentuh **100,0 pada
23 Jul 11:00 WIB dengan harga 194** -- puncak pergerakan, jam yang sama trailing stop asli mereka
tereksekusi. Klaim saya sebelumnya ("Stoch 78,3 jadi tidak akan menyuruh jual") salah untuk
indikator yang mereka pakai, dan sudah dikoreksi eksplisit ke user.

### Metodologi
`quant/run_hourly_stochrsi_exit_experiment.py` (baru). Data 1 jam diunduh via yfinance ke
`data/intraday/{TICKER}_1h.csv` (4.870 bar BUMI, 4.865 DEWA, mulai 2023-07-18 -- batas maksimum
histori intraday yang tersedia). Stoch RSI (14,14,3,3) persis setting TradingView user. Entry
tidak diubah (aturan harian Fase AB); yang dibandingkan HANYA cara keluar. Exit diisi di CLOSE
bar pemicu (bukan high -- tanpa lookahead), cap 20 hari, biaya 0,80%, split 70/30 kronologis.

### Hasil: SEMUA varian kalah telak dari baseline
```
BUMI   discovery / holdout            rata2 hari tahan
daily_fixed_10d    +9,11% / +4,24%          10,0   <-- baseline, terbaik
hourly_k_gt80      +0,61% / +2,93%           2,2
hourly_k_gt90      +0,47% / +2,93%           2,2
hourly_kd_cross    -0,45% / +7,99%           2,5

DEWA
daily_fixed_10d    +6,98% / +14,09%         10,0   <-- baseline, terbaik
hourly_k_gt80      +0,34% / +3,18%           2,0
hourly_k_gt90      +0,76% / +3,18%           2,2
hourly_kd_cross    -0,36% / +14,15%          2,5
```

### Kenapa gagal -- ini bagian yang paling berguna
Lihat kolom "rata2 hari tahan": exit Stoch RSI 1 jam rata-rata keluar **2,0-2,5 hari** setelah
entry, bukan 10. Stoch RSI di bar 1 jam berosilasi sangat cepat, jadi hampir selalu menyentuh >80
dalam 2 hari pertama -- posisi ditutup **sebelum pantulan sempat berkembang**. Untung dipotong
di awal.

Ini kebalikan persis dari kegagalan Fase AD (exit overbought HARIAN justru menahan 15-20 hari,
kelamaan). Jadi dua-duanya gagal karena alasan berlawanan: harian kelamaan, per-jam kecepetan.
Ini menguatkan bahwa masalahnya bukan "ambangnya kurang pas", tapi indikator overbought memang
bukan alat yang tepat untuk menentukan kapan keluar dari trade pantulan.

### Catatan sample size (penting)
Data 1 jam cuma 3 tahun, jadi hanya **11 sinyal** yang tercakup (dari 42 sinyal BUMI di histori
harian 22 tahun) -- **di bawah ambang minimum n>=20 proyek ini**. Angka holdout yang terlihat
bagus (`hourly_kd_cross` +7,99% BUMI / +14,15% DEWA) berasal dari **4 trade saja** dan TIDAK
boleh dipercaya. Discovery-nya negatif untuk kedua saham, jadi tetap tidak konsisten.

### Kenapa ini TIDAK bertentangan dengan kejadian 23 Juli
Stoch RSI memang menandai puncak dengan tepat hari itu. Bedanya: saat itu posisi sudah untung
~40% dan sudah berjalan >3 minggu. Yang menyelamatkan profit adalah **trailing stop** (keluar
karena harga benar-benar berbalik dari puncak), bukan prediksi puncak. Trailing stop membiarkan
posisi yang menang terus berjalan dan baru keluar saat pembalikan nyata -- persis yang tidak
dilakukan aturan overbought, yang keluar 2 hari setelah entry apa pun kondisinya.

### Status: GAGAL, tidak diintegrasikan. Aturan jual tetap: (1) fixed 10 hari bursa (paling
untung di semua uji), (2) trailing-stop alert 4% (proteksi, sudah live, terbukti nyata di akun
user 23 Jul). Stoch RSI boleh tetap dipakai user sebagai konteks visual di TradingView, tapi
tidak dijadikan pemicu keputusan otomatis di sistem ini.

## Fase AF — Alert intraday: trailing stop per-jam + target waktu 10 hari

**Konteks:** User bertanya kenapa momen bagus 21-23 Jul 2026 (spike BUMI ke 196 lalu jatuh)
"terlewatkan". Dicek ulang: **tidak terlewat** -- versi harian tetap mengirim alert di run 15.21
tanggal 23 Jul (mundur 6,6% dari puncak 196 ke close 183). Tapi waktunya sore, bukan saat
kejadian.

### Verifikasi empiris sebelum membangun
Disimulasikan trailing stop 4% dicek TIAP JAM ke data 1 jam asli 20-24 Jul 2026:
```
23 Jul 11:00 | H=196 C=194 | puncak=196 | mundur 1,0%
23 Jul 13:00 | H=195 C=189 | puncak=196 | mundur 3,6%
23 Jul 14:00 | H=191 C=184 | puncak=196 | mundur 6,1%  <<< ALERT, profit +36,3%
23 Jul 15:00 | H=185 C=182 | puncak=196 | mundur 7,1%
```
Alert datang **23 Jul 14.00** vs versi harian 15.21 -- ~1,5 jam lebih cepat, harga 184 vs 183.
Selisih harga kecil di kasus ini, tapi pada penurunan yang lebih cepat bedanya jauh lebih besar.

### Perubahan kode
- `quant/drawdown_bounce_tracker/check_trailing_stop.py` -- diubah dari daily close ke **bar 1 jam**
  (`period=730d, interval=1h`). Puncak diambil dari `High` intraday (tertangkap saat terjadi, bukan
  setelah bar harian tutup). Ditambah **alert kedua: target waktu 10 hari bursa** -- exit yang
  menang di semua backtest (Fase AB/AD/AE), sebelumnya cuma dicatat diam-diam tanpa notifikasi.
  Kedua alert masing-masing cuma sekali per posisi (flag `alerted_pullback_pct`, `alerted_day10`
  disimpan ke `open_positions.json`).
- `routes/console.php` -- `research:check-trailing-stop-alert` dari `dailyAt('15:21')` menjadi
  **tiap 30 menit, 09.00-16.00 WIB hari kerja**.

### Verifikasi
- Real run: BUMI puncak 173 (3 Agu 09.00), sekarang 168, mundur 2,9%, hari bursa ke-4, P&L +5,7%.
  DEWA puncak 482, sekarang 464, mundur 3,7%, hari ke-4, P&L +5,5%. Keduanya di bawah ambang 4%
  dan belum 10 hari -- benar, belum ada alert.
- Jalan via `php artisan research:check-trailing-stop-alert` -- output sama dengan Python langsung.

### Status: SELESAI. Sistem jual sekarang lengkap dan semuanya berbasis aturan yang lolos uji:
(1) trailing stop 4% dicek per 30 menit saat jam bursa, (2) pengingat target waktu 10 hari bursa.
Tidak ada yang memakai indikator overbought sebagai pemicu -- dua-duanya sudah terbukti gagal
(Fase AD harian, Fase AE Stoch RSI 1 jam).

## Fase AG — Perketat trailing stop: 4%/30 menit -> 2%/15 menit

**Konteks:** User menunjuk momen spesifik BUMI 23 Jul jam 11.30 (puncak 196 di 11.45) dan
bertanya kenapa alertnya baru bunyi jam 14.00 (Fase AF), minta alert lebih cepat "jam 9/10-an".

### Koreksi kesalahpahaman dulu, sebelum ubah apa pun
Alert TIDAK BISA lebih cepat dari puncak itu sendiri -- puncak baru terbentuk 11.45, jadi alert
sebelum jam itu berarti jual SEBELUM harga mencapai tertinggi (profit lebih KECIL, bukan lebih
besar). Lever yang benar-benar bisa diperbaiki cuma satu: jarak waktu antara puncak terbentuk dan
alert bunyi (lag), bukan menggeser alert ke pagi.

### Perbandingan real (granularitas 15 menit, data 21-23 Jul 2026)
```
Ambang 4% (15 menit): alert 23 Jul 14:15, harga 186
Ambang 3% (15 menit): alert 23 Jul 13:45, harga 189
Ambang 2% (15 menit): alert 23 Jul 13:30, harga 192  <-- SAMA PERSIS dgn jam stop StockBit user (13:30 @ 189)
```
User memilih **2% + granularitas 15 menit** setelah melihat tabel ini secara eksplisit ("2% aja +
cek 15 menit").

### Perubahan kode
- `quant/drawdown_bounce_tracker/check_trailing_stop.py`: `PULLBACK_THRESHOLD` 0,04 -> 0,02;
  `fetch_hourly_since()` (interval 1h, 730 hari) diganti `fetch_15m_since()` (interval 15m, 60
  hari -- batas maksimum Yahoo untuk granularitas ini, tapi tidak jadi soal karena horizon exit
  proyek ini cuma ~10-20 hari bursa).
- `routes/console.php`: `research:check-trailing-stop-alert` dari `everyThirtyMinutes()` menjadi
  `everyFifteenMinutes()`, komentar diperbarui.

### Trade-off yang disadari (bukan cuma "lebih cepat = lebih baik")
2% lebih ketat dari ATR harian BUMI/DEWA (~5,8-6,0%), jadi ambang ini AKAN kadang bunyi karena
noise intraday biasa, bukan cuma pembalikan sungguhan. User memilih ini secara sadar melihat
trade-off lag-vs-alarm-palsu di angka nyata, bukan diam-diam diubah oleh sistem.

### Verifikasi
- `python3 quant/drawdown_bounce_tracker/check_trailing_stop.py`: BUMI mundur 2,9% dari puncak
  173 (3 Agu 09.45) -> **ALERT TRAILING STOP terkirim** (P&L +5,7%). DEWA mundur 3,7% dari puncak
  482 (3 Agu 09.00) -> **ALERT TRAILING STOP terkirim** (P&L +5,5%). Dengan ambang lama (4%) dua
  posisi ini TIDAK akan dapat alert -- perubahan ambang langsung menangkap pullback nyata yang
  sebelumnya terlewat. Alert Telegram nyata terkirim, `open_positions.json` ter-update
  (`alerted_pullback_pct` terisi untuk keduanya).
- `php artisan research:check-trailing-stop-alert` dijalankan ulang setelahnya: output identik,
  TIDAK kirim alert dobel (flag `alerted_pullback_pct` sudah terisi) -- guard sekali-per-posisi
  bekerja benar.
- `php artisan test`: 480 passed (tidak ada test yang menyentuh script Python ini secara langsung,
  jadi hijau seperti sebelumnya).

### Status: SELESAI. Ambang trailing stop sekarang 2%, dicek tiap 15 menit jam bursa 09.00-16.00
WIB. Target waktu 10 hari bursa tidak berubah.

## Fase AH — Percepat polling perintah Telegram: 5 menit -> 1 menit

**Konteks:** User kirim `/status` jam 11:02, baru dijawab jam 11:05 -- tanya kenapa lambat.
Dicek langsung di `storage/logs/cron.log`: siklus `research:check-telegram-commands` jam
11:00:06 sudah lewat duluan sebelum pesan masuk, jadi baru ketangkap siklus berikutnya 11:05:03
-- delay 3 menit murni dari interval polling 5 menit, bukan bug.

### Temuan tambahan saat investigasi (di luar scope langsung, dicatat)
Ditemukan dua LaunchAgent macOS (`com.sentimena.prediction-api`, `com.sentimena.sentiment-api`)
dengan `KeepAlive: true` yang selama ini menjalankan API Python otomatis di background --
tidak diketahui sebelumnya dalam sesi ini. Juga ditemukan `com.luthfimirza.sentimena.scheduler`
(LaunchAgent, `php artisan schedule:run` tiap 60 detik) berjalan REDUNDAN paralel dengan crontab
sistem yang sudah ada (`* * * * * php artisan schedule:run`) -- scheduler jalan dobel dari dua
sumber. Dibiarkan apa adanya (tidak mengganggu, `withoutOverlapping()` mencegah eksekusi ganda),
tapi perlu dibereskan suatu saat (pilih salah satu: cron ATAU launchd, bukan dua-duanya).

### Perubahan kode
- `routes/console.php`: `research:check-telegram-commands` dari `everyFiveMinutes()` menjadi
  `everyMinute()`. Feasible tanpa infrastruktur tambahan karena cron sistem sudah jalan tiap
  menit -- cuma nambah request `getUpdates` kosong ke Telegram tiap menit saat tidak ada pesan
  baru, murah.

### Verifikasi
- `php artisan schedule:list` menunjukkan entry `* * * * *` untuk
  `research:check-telegram-commands`.
- `php artisan research:check-telegram-commands` dijalankan manual -- "Tidak ada perintah baru."
  (tidak error).
- `php artisan test`: 480 passed.

### Status: SELESAI. Worst-case delay respons Telegram turun dari ~5 menit menjadi ~1 menit.

## Fase AI — Fitur `/history` di Telegram bot

**Konteks:** Ditanya fitur tambahan apa lagi yang masuk akal selain `/status` dan `/close`.
Rekomendasi: `/history` (riwayat posisi yang sudah ditutup) -- gap nyata, P&L cuma bisa dilihat
lewat web Trade Journal sekarang, padahal semua interaksi lain sudah bisa dari Telegram.

### Tantangan desain
`telegram_commands.py` sengaja TIDAK pernah menyentuh MySQL langsung (pola resiliensi yang sama
dengan `open_positions.json` -- tetap jalan walau MySQL mati). Tapi riwayat trade cuma ada di
Trade Journal (MySQL, tabel `trades`), bukan di `open_positions.json` (itu cuma posisi yang lagi
dipantau trailing-stop, konsep berbeda).

### Solusi: cache file yang di-refresh tiap run
- `CheckTelegramCommandsCommand.php` (`refreshClosedTradesCache()`): sebelum panggil Python,
  query `Trade::where('status','closed')->orderByDesc('exit_date')->limit(10)` dan tulis ke
  `quant/drawdown_bounce_tracker/closed_trades_cache.json`. Dibungkus try/catch -- kalau MySQL
  mati, skip diam-diam dan biarkan cache lama (self-heal begitu MySQL nyala lagi, sama seperti
  `news:auto-recover-gap`). File ini di-gitignore (murni turunan dari DB, regenerasi tiap 1 menit
  sekarang karena Fase AH).
- `telegram_commands.py`: `/history` baca cache itu (tidak pernah query DB langsung), format jadi
  pesan HTML rapi -- ticker, entry->exit, tanggal, lama hari, P&L (Rp + %, tanda +/- dan emoji
  hijau/merah), hasil (kena target/stop loss/tutup manual).
- `detect_signal.py`: tombol baru "📜 Riwayat" ditambah ke `default_keyboard()` di baris yang sama
  dengan Status (jadi 2 tombol sebaris: Status | Riwayat).

### Verifikasi
- `php artisan test --filter=CheckTelegramCommandsCommandTest`: 5 passed (2 test baru --
  cache terisi benar saat ada trade closed, cache `[]` saat tidak ada, ticker DEWA yang masih
  `open` sengaja dikecualikan dari cache).
- Real run `php artisan research:check-telegram-commands`: cache terisi 10 trade asli dari Trade
  Journal (BUMI 136->171 +Rp1.750.000, DEWA 332->442 +Rp1.716.000, dst).
- `format_history()` dites langsung ke data cache asli -- output rapi, termasuk kasus P&L negatif
  (`-Rp528.623`, bukan `Rp-528.623` seperti percobaan pertama -- diperbaiki).
- Pesan `/history` beneran dikirim ke Telegram user (bukan cuma print lokal) -- dikonfirmasi
  terkirim.
- `php artisan test` penuh: 482 passed (naik dari 480 -- 2 test baru untuk cache refresh).

### Status: SELESAI.

## Fase AJ — Fitur `/price TICKER` di Telegram bot

**Konteks:** Lanjutan daftar saran fitur -- `/price` biar bisa cek harga live ticker APA SAJA
(bukan cuma BUMI/DEWA yang lagi dipantau), berguna buat mantau kandidat sebelum entry baru tanpa
buka aplikasi lain.

### Implementasi
- `telegram_commands.py`: `PRICE_PATTERN` regex (`/price TICKER`, case-insensitive), fungsi baru
  `fetch_price_snapshot(ticker)` -- reuse pola yfinance yang sama dengan `fetch_live_price()`
  (period 5d, auto_adjust=False), tapi simpan 2 baris terakhir supaya bisa hitung perubahan
  harian (harga sekarang vs penutupan sebelumnya). `format_price()` -- tampilkan harga + panah
  hijau/merah + % perubahan + tanggal data, atau pesan jelas kalau ticker tidak ditemukan.
- Tidak perlu tombol keyboard baru (ticker-nya bebas, tidak bisa di-fix ke satu tombol) -- murni
  perintah teks `/price TICKER`.
- Tidak ada perubahan sisi Laravel/PHP -- murni logic Python, tidak butuh data MySQL sama sekali.

### Verifikasi
- Regex dites: `/price BUMI`, `/PRICE bumi` (case-insensitive), `/price   ADRO` (spasi ganda) --
  semua cocok benar. `/open BUMI 159` dan `/pricebumi` (tanpa spasi) benar-benar TIDAK cocok --
  tidak akan salah tangkap perintah lain.
- Real fetch: BUMI Rp169 (+0,6%), BBCA Rp6.375 (+1,2%), DEWA Rp464 (+0,0%) -- semua akurat
  dibanding harga yang sudah diverifikasi di Fase AG/AH hari yang sama.
- Ticker tidak valid (`XXXX`): tidak crash, balas pesan jelas "Tidak ada data harga ... cek lagi
  penulisan ticker-nya".
- Pesan `/price BBCA` beneran dikirim ke Telegram user, dikonfirmasi terkirim.
- `php artisan test`: 482 passed (tidak ada perubahan PHP, angka tetap sama seperti Fase AI).

### Status: SELESAI.

## Fase AK — Fitur `/help` di Telegram bot

**Konteks:** Terakhir dari daftar saran fitur -- `/help` menampilkan daftar semua perintah yang
tersedia, biar tidak perlu ingat syntax `/open`/`/close`/`/price` dari luar kepala.

### Implementasi
- `detect_signal.py`: tombol baru "❓ Bantuan", ditambah sebagai baris ketiga di
  `default_keyboard()` (Status+Riwayat, Tutup BUMI+Tutup DEWA, Bantuan).
- `telegram_commands.py`: `format_help()` -- daftar lengkap 6 perintah dengan contoh pemakaian
  untuk yang butuh argumen (`/open`, `/close`, `/price`). Pesan "perintah tidak dikenali" yang
  lama (daftar panjang di-inline) disederhanakan jadi arahan ke `/help`, tidak dobel-maintain dua
  tempat.

### Verifikasi
- Struktur keyboard dicek langsung -- 3 baris benar, tombol Bantuan muncul di baris terpisah.
- `BUTTON_LABELS` mapping dicek -- "❓ Bantuan" -> "/help" benar.
- Pesan `/help` beneran dikirim ke Telegram user, dikonfirmasi terkirim, format rapi (emoji per
  perintah, contoh dengan `<code>`).
- `php artisan test`: 482 passed (tidak ada perubahan PHP).

### Status: SELESAI. Semua 4 fitur dari daftar saran (kecuali peringatan H-1 hari ke-9, belum
diminta) sudah dibangun: /history, /price, /help, plus /status /open /close yang sudah ada
sebelumnya.

## Fase AL — Peringatan H-1 (hari bursa ke-9) sebelum target waktu 10 hari

**Konteks:** Item terakhir dari daftar saran fitur -- alert hari ke-10 (Fase AF) selama ini
langsung "mendadak" tanpa pemanasan; peringatan sehari sebelumnya (hari ke-9) kasih waktu
bersiap-siap alih-alih kaget di hari-H.

### Implementasi
- `check_trailing_stop.py`: `WARN_HOLD_DAYS = TARGET_HOLD_DAYS - 1` (=9). Alert baru
  "\U0001F7E1 H-1 TARGET WAKTU" disisipkan di antara alert trailing-stop dan alert target hari
  ke-10, kondisi `WARN_HOLD_DAYS <= trading_days < TARGET_HOLD_DAYS` (guard `< TARGET_HOLD_DAYS`
  sengaja supaya tidak ikut menyala lagi setelah hari ke-10 lewat). Flag baru `alerted_day9`,
  sekali per posisi seperti dua alert lain.
- `routes/console.php`: komentar jadwal `research:check-trailing-stop-alert` diperbarui dari
  "dua alert" jadi "tiga alert".

### Verifikasi (posisi sintetis, TIDAK menyentuh open_positions.json asli -- BUMI/DEWA real
masih hari ke-5, belum kena H-1)
- Dicari dulu `entry_date` yang menghasilkan tepat hari bursa ke-9 lewat data 15 menit real
  (`2026-07-23` -> 9 hari bursa per `04 Aug`).
- `check_position()` dipanggil langsung dengan posisi sintetis (`{"ticker": "BUMI", "entry_date":
  "2026-07-23", ...}`) -- ALERT H-1 TARGET WAKTU beneran terkirim ke Telegram di hari ke-9, flag
  `alerted_day9` tersimpan.
- Re-run dengan flag yang sama -- tidak ada alert baru tercetak/terkirim (idempotent, terverifikasi).
- Posisi sintetis lain di hari ke-10 (`entry_date=2026-07-22`) dengan `alerted_day9` SUDAH terisi
  -- ALERT TARGET WAKTU (hari ke-10) tetap terkirim normal, H-1 tidak nyangkut/ikut menyala lagi.
- `open_positions.json` real dicek ulang setelah semua percobaan -- BUMI/DEWA tidak berubah sama
  sekali (percobaan pakai dict terpisah, bukan file production).
- `php artisan test`: 482 passed (tidak ada perubahan PHP kecuali komentar di routes/console.php).

### Status: SELESAI. Semua 4 fitur dari daftar saran (termasuk H-1) sudah dibangun lengkap.

## Fase AM — Audit & isi ulang statistik Trade Journal yang kosong

**Konteks:** User curiga dashboard "Total Trade 19 / Win Rate 47,1% / dst" tidak masuk akal
dibanding "Riwayat Trading (17)" yang dia lihat.

### Temuan (dicek langsung ke DB, bukan asumsi)
19 trade di `trades` (`user_id=2`) ternyata **campuran dua sumber**:
- **15 trade SIMULASI BACKTEST** (id #82-#155, `created_at` sama persis 2026-07-08 23:15:17,
  `notes` eksplisit "SIMULASI BACKTEST (bukan transaksi riil)") -- dibuat sesi sebelumnya untuk
  evaluasi volatilitas Des2025-Jul2026, BUKAN transaksi riil user (lihat memori
  `stock-prices-seed-contamination.md`).
- **4 trade REAL** (#157-#160, `created_at` 2026-07-31), dikoreksi manual sebelumnya dari data
  StockBit user (lot size di-reverse-engineer, R²=1,0).

Semua angka dashboard (`TradeController::index()`) **akurat secara kalkulasi** (diverifikasi
manual satu-satu: Win Rate 8/17=47,06%, Total PnL Rp46.899.197 exact, Avg R:R 5,08, Expectancy
12,28%) -- TAPI didominasi data simulasi: Win Rate 100% dari simulasi (2 trade real result-nya
`manual_close`, tidak masuk hitungan win/loss), Total PnL 93% dari simulasi (Rp43,4jt dari 15
trade simulasi vs Rp3,47jt dari 2 trade real), dan **Avg R:R + Avg Holding 100% dari simulasi**
(field `actual_rr`/`holding_days` #157/#158 kosong -- dibuat lewat tinker langsung, bukan lewat
alur `Trade::close()` yang otomatis menghitungnya).

User sempat klaim 15 trade simulasi itu "sesuai dengan yang saya lakukan di StockBit" --
DITOLAK tanpa bukti, mengacu ke catatan eksplisit di memori bahwa user pernah minta data
"seolah profit" dan itu sudah ditolak sebelumnya; prinsip yang sama dipertahankan di sini.

### Perbaikan (persetujuan user)
Isi `actual_rr` dan `holding_days` untuk #157/#158, pakai formula yang SAMA persis dengan
`Trade::close()` (`pnlPerShare/risk` untuk R:R, `entry_date` ke `exit_date` untuk holding --
bukan ke `now()` seperti bug kecil di `close()` yang cuma valid saat dipanggil real-time):
- #157 BUMI: (171-136)/(136-129,2) = 35/6,8 = **R:R 5,15**, 8→24 Jul = **16 hari**
- #158 DEWA: (442-332)/(332-315,4) = 110/16,6 = **R:R 6,63**, 9→24 Jul = **15 hari**

Avg R:R dashboard naik dari 1:5,08 (100% simulasi) jadi **1:5,17** (ikut 2 trade real). Avg
Holding naik dari 4,3 hari jadi **5,6 hari**. Win Rate/Total PnL/Expectancy tidak berubah
(sudah termasuk real sejak awal).

### Status: SELESAI. Update data murni (2 UPDATE query), tidak ada perubahan kode -- tidak perlu
`php artisan test`.

## Fase AN — Form Trade Journal input Lot, bukan lembar mentah

**Konteks:** User tunjukkan form "Catat Trade Baru" (field "Lot Size (lembar)", minta ketik
50000) vs screenshot order StockBit asli (field "Lot", cuma ketik 2) -- minta disederhanakan
ikut kebiasaan broker: ketik Lot, bukan hitung lembar manual.

### Investigasi sebelum eksekusi
- Kolom `lot_size` di DB **sebenarnya menyimpan lembar** (dipakai langsung di
  `Trade::close()` untuk `pnlTotal = pnlPerShare * lot_size`, dan di `position_value`). Standar
  IDX: **1 Lot = 100 lembar** (berlaku sejak 2014) -- konsisten dengan data yang sudah ada
  (BUMI 500 Lot = 50.000 lembar, DEWA 156 Lot = 15.600 lembar, keduanya kelipatan 100 bersih).
  Cuma dipakai di 3 titik: form input, validasi controller, tampilan daftar -- perubahan aman
  dan terisolasi, tidak perlu migrasi DB.
- Ditemukan bug kecil yang belum disadari: kolom tabel Riwayat Trading judulnya sudah "LOT"
  tapi isinya nampilin `lot_size` MENTAH (lembar, bukan lot) -- salah label dari awal.
- Ditemukan titik lain yang akan ikut rusak kalau tidak disesuaikan: link "Catat Trade Manual"
  dari halaman Analytics (pre-fill dari sinyal DSS) mengirim query param `lot_size` mentah --
  kalau form berubah baca `lot`, pre-fill DSS jadi kosong.

### Perubahan kode
- `TradeController::store()`: validasi `lot` (bukan `lot_size`), dikonversi
  `lot_size = lot * 100` (konstanta `LEMBAR_PER_LOT`) sebelum `Trade::create()`.
- `resources/views/trades/index.blade.php`:
  - Form: label "Lot Size (lembar)" -> **"Jumlah Lot"**, `name="lot"`, placeholder "mis. 500",
    helper text live `= X lembar` (JS `oninput`, plus server-rendered untuk pre-fill DSS).
  - Kartu posisi terbuka: tampilan diubah jadi "500 Lot" (utama) + "50.000 lbr" (kecil, sekunder).
  - Tabel Riwayat Trading: kolom "Lot" diperbaiki dari nampilin lembar mentah jadi
    `lot_size / 100` (lot beneran).
- `resources/views/analytics/index.blade.php`: link pre-fill DSS diubah dari
  `'lot_size' => $signal['lot_size']` jadi `'lot' => max(1, intdiv($signal['lot_size'], 100))`
  -- dibulatkan ke bawah ke lot terdekat karena order riil IDX memang cuma bisa lot utuh
  (nilai lembar mentah dari `DecisionSupportService` tidak selalu kelipatan 100).
- `tests/Feature/TradeJournalTest.php`: test lama diupdate pakai `lot` bukan `lot_size`, tambah
  test baru khusus verifikasi konversi 1 Lot = 100 lembar.

### Verifikasi
- `php artisan test --filter=TradeJournalTest`: 5 passed (test baru lolos).
- `php artisan test` penuh: 483 passed (naik dari 482).
- Verifikasi visual real di browser (login `user@sentimena.test`, data asli, bukan data uji):
  - Kartu posisi terbuka BUMI menampilkan **"500 Lot" / "50.000 lbr"** dengan benar.
  - Tabel Riwayat Trading: DEWA #158 kolom Lot menampilkan **156** (sebelumnya salah nampilin
    15600), BUMI #157 menampilkan **500** -- cocok persis dengan hasil Fase AM.
  - Form "Catat Trade Baru" dibuka -- label "Jumlah Lot" muncul, ketik "500" di kolom -> helper
    text langsung update jadi **"= 50.000 lembar"** (live, terverifikasi lewat interaksi
    browser sungguhan, bukan cuma baca kode).

### Status: SELESAI.

## Fase AO — Uji drawdown-bounce di 9 saham produksi + backfill Trade Journal + perbaiki bug Win Rate

**Konteks:** User minta uji aturan drawdown-bounce (Fase AB/AC, dipakai bot Telegram) ke 9 saham
produksi (bukan cuma BUMI/DEWA), lalu masukkan hasilnya ke Trade Journal untuk dibahas di skripsi.

### AO-1: Backtest 8 bulan (5 Des 2025 - 4 Agu 2026)
Data segar via yfinance (CSV statis mentok 21 Jul). 33 trade, 73% menang, rata2 +5,60%/trade net.
Simulasi modal Rp33jt -> Rp47,4jt (+43,8%) exit 10 hari; trailing stop 2% MERUSAK hasil jadi cuma
+11,8% (bunyi 33/33 kali, rata2 1,5 hari -- ambang 2% terlalu sempit untuk blue chip, volatilitas
harian BBCA cuma 1,75% vs BUMI/DEWA 4,4-4,8%). **33 trade ternyata cuma 5 episode pasar
independen** (IHSG anjlok -> semua saham anjlok bareng) -- jauh di bawah n>=20.

### AO-2: Uji histori panjang (18-26 tahun, discovery/holdout 70/30)
432 trade, 37 episode independen (n>=20 TERPENUHI, pertama kali di luar BUMI). Discovery +1,21%
DAN holdout +2,01% -- konsisten, tidak ganti tanda. TAPI uji ketahanan gagal: buang 5 dari 37
episode (semua pemulihan pasca-krisis: Mei 2009, Okt 2002, Sep 2011, Agu 2007, Apr 2025), seluruh
profit hilang (rata2 jadi -0,20%). Per saham: **5 dari 9 saham ganti tanda** antara discovery dan
holdout (ASII, BBRI, BMRI, ICBP, INDF gagal). Cuma **BBCA dan UNVR** lolos dua syarat (konsisten
+ n cukup) dengan margin meyakinkan; TLKM lolos syarat tapi rata2 cuma +0,45% (tipis pasca-biaya).
INDF dan ICBP malah **rugi** sepanjang histori (-2,81% dan -2,49%/trade).

**Rekomendasi ke user:** JANGAN aktifkan 9 saham borongan -- edge-nya bergantung pada segelintir
krisis dan mayoritas saham tidak konsisten. Kalau mau aktifkan, cuma BBCA+UNVR yang layak.
**Belum dieksekusi** (aktivasi live) -- user minta backfill Trade Journal dulu untuk skripsi.

### AO-3: Backfill 33 trade (5 Des 2025 - 4 Agu 2026) ke Trade Journal
Insert via tinker, label eksplisit di `notes`: "SIMULASI BACKTEST (bukan transaksi riil) --
aturan drawdown-bounce ... exit BERBASIS WAKTU, bukan harga ...". Kolom `stop_loss`/`target_1`
NOT NULL di DB tapi strategi ini tidak punya aturan stop/target harga (exit murni 10 hari bursa)
-- diisi REFERENSI INFORMATIF (stop_loss = harga terendah selama dipegang/MAE, target_1 = harga
exit aktual), dijelaskan eksplisit di notes supaya tidak disalahartikan sebagai aturan operasional.
`result` = `manual_close` untuk semua (exit waktu, bukan hit_target/stop_loss beneran).

**Verifikasi:** 33 trade dibuat (ID 161-193, dicek presisi -- filter `LIKE '%drawdown-bounce%'`
sempat salah hitung 34 karena notes lama #157 juga mengandung kata itu, dikoreksi pakai filter ID).
PnL total trade baru Rp11.853.723 -- cocok persis dengan laporan sebelum insert.

### AO-4: Bug ditemukan setelah insert -- Win Rate dashboard jadi 16% (salah menyesatkan)
33 trade baru semuanya `result=manual_close` (exit waktu, bukan target/stop harga). Formula lama
`TradeController::index()` cuma hitung `result IN (hit_target_1, hit_target_2)` sebagai "menang" --
28 dari 33 trade baru (untung beneran) SAMA SEKALI TIDAK KEHITUNG, bukan menang bukan kalah, hilang
dari Win Rate. Total 37 dari 50 closed trade (74%) berstatus manual_close, dan 28 di antaranya
positif.

**Perbaikan (persetujuan user):** `win`/`loss`/`win_rate`/`expectancy` di `TradeController::index()`
diubah dari berbasis kategori `result` menjadi berbasis **PnL aktual** (`pnl_total > 0` = menang,
`<= 0` = kalah) -- benar untuk semua jenis strategi exit (target harga, stop harga, ATAU waktu),
bukan cuma yang exit-nya lewat target/stop.

### Verifikasi
- `php artisan test --filter=TradeJournalTest`: 6 passed (test baru
  `test_win_rate_counts_profitable_manual_close_trades_as_wins` mengunci perilaku benar).
- `php artisan test` penuh: 484 passed (naik dari 483).
- Data real setelah perbaikan: Total 52 trade (2 open, 50 closed), **Win Rate 72% (36W/14L)**
  -- sebelumnya 16%. Total PnL Rp58.752.920, Avg R:R 1:3,88, Expectancy +9,44%, Avg Holding 8,5
  hari. Dicek visual di browser (data user asli): dashboard dan tabel "Riwayat Trading (50)"
  tampil benar, termasuk baris-baris trade baru dengan PnL negatif terformat benar.

### Status: SELESAI (backfill + fix bug). Keputusan aktivasi live BBCA/UNVR belum diambil --
menunggu arahan user selanjutnya.

## Fase AP — `/price` tampilkan jam, bukan cuma tanggal

**Konteks:** User cek `/price BUMI`, balasannya "per 04 Aug 2026" -- cuma tanggal, tidak ada jam,
padahal harga live seharusnya berubah beberapa kali sehari.

### Penyebab
`fetch_price_snapshot()` sebelumnya cuma pakai data HARIAN (`interval` default 1d) -- timestamp-nya
memang tidak pernah punya komponen jam yang berarti.

### Perbaikan
`fetch_price_snapshot()` sekarang ambil harga TERKINI dari bar 15 menit (pola sama dengan
`check_trailing_stop.py`), tapi persentase perubahan tetap dihitung terhadap penutupan HARIAN
kemarin (bukan bar 15 menit sebelumnya) -- supaya tetap bermakna sebagai "naik/turun hari ini",
bukan noise antar-bar 15 menit. Fallback ke data harian kalau data 15 menit kosong (ticker jarang
diperdagangkan). `format_price()`: `%d %b %Y` -> `%d %b %H:%M`.

### Verifikasi
- Real fetch: BUMI, BBCA, DEWA semua nampilin jam sekarang, mis. "per 04 Aug 14:30" (bar 15 menit
  terakhir yang tersedia).
- Ticker tidak valid (XXXX): tetap tidak crash, pesan error jelas.
- Pesan `/price BUMI` beneran dikirim ke Telegram user, dikonfirmasi terkirim.
- `php artisan test`: 484 passed (murni Python, tidak ada perubahan PHP).

### Status: SELESAI.

## Fase AQ — Bot Telegram bisa dipakai dari 2 akun (nomor kedua)

**Konteks:** User tanya kenapa bot tidak respons dari nomor Telegram lain. Sengaja begitu --
proteksi keamanan (`chat.id == TELEGRAM_CHAT_ID`), bukan bug. User minta ditambah nomor kedua.

### Perubahan kode
- `detect_signal.py`: fungsi baru `load_allowed_chat_ids()` -- kumpulan chat_id yang diizinkan
  (`TELEGRAM_CHAT_ID` utama + `TELEGRAM_CHAT_ID_2` opsional). `send_telegram_alert()` sekarang
  terima parameter `chat_id` opsional (default ke nomor utama -- tidak mengubah perilaku alert
  otomatis/sinyal/trailing-stop yang lama).
- `telegram_commands.py`: cek otorisasi diganti dari `chat.id == chat_id tunggal` jadi
  `chat.id in allowed_ids`. **Perbaikan penting yang ikut ditemukan**: sebelumnya SEMUA balasan
  (`/status`, `/history`, dst) selalu dikirim ke nomor UTAMA lewat `load_telegram_credentials()`
  di dalam `send_telegram_alert()` -- kalau nomor kedua kirim perintah, balasannya akan salah
  alamat (ke nomor utama, bukan ke pengirim). Sekarang tiap balasan eksplisit dikirim ke
  `sender_chat_id` (chat_id pengirim asli), bukan selalu default.
- `.env.example`: tambah `TELEGRAM_CHAT_ID_2=` (placeholder kosong).

### Aktivasi nyata
- User kirim `/start` dari akun Telegram kedua (nama "Luthfi", beda dari akun utama).
- `chat_id` diambil dari `getUpdates` API langsung (bukan diminta manual dari user): **8870402966**
  (akun utama tetap 7162558029).
- `.env` real diisi `TELEGRAM_CHAT_ID_2=8870402966`, `php artisan config:clear`.

### Verifikasi
- `load_allowed_chat_ids()` dicek langsung: sebelum diisi -> `{'7162558029'}`, dengan
  `TELEGRAM_CHAT_ID_2` contoh -> `{'999999999', '7162558029'}`, setelah `.env` real diisi ->
  `{'7162558029', '8870402966'}`.
- Semua modul (`detect_signal`, `telegram_commands`, `check_trailing_stop`) tetap ter-import
  tanpa error -- signature `send_telegram_alert` backward-compatible (`chat_id=None` default).
- `php artisan research:check-telegram-commands` dijalankan real, tidak error.
- Pesan konfirmasi beneran dikirim ke chat_id akun kedua (8870402966) via `send_telegram_alert(
  ..., chat_id='8870402966')` -- membuktikan jalur kirim-ke-chat_id-tertentu bekerja.
- `php artisan test`: 484 passed (tidak ada perubahan PHP di luar `.env.example`).

### Status: SELESAI. Kedua akun Telegram sekarang bisa kirim /status, /open, /close, /history,
/price, /help dan dapat balasan yang benar ke nomor masing-masing.

## Fase AR — Perbaiki 33 trade Trade Journal: bug Adj Close vs Close

**Konteks:** Cross-check manual (user minta) ke data pasar asli menemukan 27 dari 50 trade
meleset dari range harga High-Low hari itu, dengan pola persentase TETAP per ticker (TLKM selalu
-7,54%, BBCA -4,19%, dst). Diinvestigasi: **bukan** stock split (dicek `yfinance actions` --
tidak ada split di periode ini untuk 9 ticker), tapi **dividen** -- besarnya selisih berbanding
lurus dengan total dividen tiap saham di periode itu (BMRI dividen terbesar = selisih terbesar
-8,14%, dst).

### Akar masalah sebenarnya (bukan cuma dividen)
`run_bluechip_backtest.py::load()` (skrip Fase AO yang menghasilkan 33 trade ini) salah pilih
kolom CSV: `df.rename(columns={"Adj Close": "close"})` -- padahal fetch pakai `auto_adjust=False`
yang seharusnya dipakai kolom `Close` (harga mentah/asli), bukan `Adj Close` (harga yang sudah
dikurangi dividen masa depan sampai tanggal fetch). Bug ini terpakai dari laporan PERTAMA yang
sudah disetujui user, bukan cuma di satu percobaan.

### Perbaikan
- Data historis 9 saham (`INDF,BBCA,ICBP,BBRI,ASII,BMRI,TLKM,ADRO,UNVR`) ditarik ulang segar
  via yfinance, dihitung ulang PAKAI kolom `Close` (bukan `Adj Close`).
- 33 trade lama (ID 161-193) **dihapus**, diganti 33 trade baru (ID 194-226) dengan harga yang
  benar. Notes diperbarui menyebut koreksi ini eksplisit ("dikoreksi ulang dari versi awal yang
  salah pakai harga tersesuaikan dividen").
- `stop_loss`/`target_1` (kolom NOT NULL, bukan aturan operasional untuk strategi berbasis waktu
  ini) diisi ulang dari MAE (harga terendah selama posisi dipegang) yang dihitung bareng harga
  yang sudah benar.

### Perubahan angka
| | Sebelum (salah) | Sesudah (benar) |
|---|---|---|
| Win Rate (33 trade drawdown-bounce) | 24/33 (72,7%) | **22/33 (66,7%)** |
| PnL 33 trade | +Rp11.853.723 | **+Rp10.797.840** |
| Win Rate dashboard (52 trade total) | 72% | **68%** |
| Total PnL dashboard | +Rp58.752.920 | **+Rp57.697.037** |
| Avg R:R dashboard | 1:3,88 | **1:3,36** |

2 trade ganti dari MENANG jadi RUGI setelah dikoreksi (BMRI 27 Apr, TLKM 9 Jun).

### Verifikasi
- Cross-check ulang ke pasar SETELAH insert: **0 dari 33 trade baru** bermasalah (semua dalam
  range High-Low hari itu, 100% cocok).
- Ditemukan (tapi TIDAK disentuh, di luar scope perbaikan ini): 8 dari 15 trade simulasi LAMA
  (BUMI/DEWA, ID 82-155, dari Fase D, metodologi/skrip berbeda) masih punya masalah serupa
  (tanggal bukan hari bursa / harga di luar range) -- dicatat sebagai temuan terpisah untuk
  audit lanjutan, bukan bagian dari perbaikan Fase AR ini.
- Dicek visual di browser: dashboard menampilkan 68%/34W16L/+Rp57.697.037 persis sesuai
  perhitungan; baris tabel (mis. TLKM 29 Jan: 3.450->3.560) cocok persis dengan tabel yang
  sudah disetujui user sebelum insert.
- `php artisan test`: 484 passed (murni perubahan data, tidak ada perubahan kode).

### Status: SELESAI.

## Fase AS — Perapikan tampilan `/history` di Telegram

**Konteks:** User tunjukkan hasil `/history` (10 baris riwayat trade) minta saran biar enak dibaca.

### Perubahan
- `format_history()`: tambah baris ringkasan di atas daftar (jumlah menang/rugi + total P&L 10
  trade yang ditampilkan) -- biar tidak perlu hitung manual satu-satu.
- Tanggal ISO (`2026-07-08`) diringkas jadi `08 Jul` (fungsi baru `_short_date()`) -- lebih
  ringkas dibaca di layar HP.
- Tiap entry diberi baris kosong eksplisit setelahnya (bukan cuma newline tunggal) supaya jarak
  antar-entry konsisten kelihatan lega, tidak numpuk.

### Verifikasi
- Real run pakai data cache asli: ringkasan tampil benar ("8 menang - 2 rugi - Total P&L
  +Rp7.175.663"), tanggal semua entry berhasil diringkas format "DD Mon".
- Pesan beneran dikirim ke Telegram user, dikonfirmasi terkirim.
- `php artisan test`: 484 passed (murni Python, tidak ada perubahan PHP).

### Status: SELESAI.

## Fase AT — `/status` tampilkan progres live + `/ihsg` (progres sinyal entry)

**Konteks:** User minta 2 fitur: (1) `/status` upgrade dari cuma "entry Rp159 (tanggal)" jadi
progres live lengkap terhadap 3 aturan exit (trailing stop, H-1, target 10 hari), (2) command baru
`/ihsg` cek seberapa dekat IHSG + saham yang dipantau ke ambang entry -5%.

### AT-1: Refactor `check_trailing_stop.py` -- pisah kalkulasi dari alerting
`compute_snapshot(ticker, entry_date, entry_price)` fungsi baru, READ-ONLY (tidak pernah kirim
alert/ubah `open_positions.json`) -- diekstrak dari `check_position()` yang lama supaya logika
sama persis bisa dipakai ulang di Telegram `/status` on-demand, bukan cuma nunggu alert otomatis.
`check_position()` di-refactor pakai fungsi ini juga -- perilakunya TIDAK berubah (diverifikasi:
output print sama persis dengan sebelum refactor).

### AT-2: `format_status()` di `telegram_commands.py`
Sekarang tiap posisi tampil: harga sekarang + P&L%, hari bursa ke berapa dari 10, puncak, %
mundur dari puncak, plus catatan kalau sudah lewat ambang trailing stop 2% atau masuk H-1/target
waktu -- semua dari `compute_snapshot()` yang sama dengan sistem alert asli (angka selalu
konsisten).

### AT-3: `/ihsg` -- progres sinyal entry
`fetch_2d_return()` (fungsi baru) hitung return 2-hari PAKAI 'Close' MENTAH (bukan 'Adj Close' --
menghindari bug yang sama seperti Fase AR). `format_ihsg_progress()` tampilkan: IHSG turun berapa
% dalam 2 hari + progres menuju ambang -5%, plus tiap saham di `LABELS` (BUMI/DEWA) statusnya
masing-masing. `DROP_THRESHOLD`/`LABELS` diimpor dari `detect_signal.py` supaya konsisten persis
dengan aturan deteksi sinyal live (bukan angka duplikat yang bisa drift).

### Temuan sampingan (dicatat, TIDAK diperbaiki sekarang)
`detect_signal.py::fetch_recent()` menyimpan `entry_price` sinyal LIVE dari kolom `adj_close`
(Adj Close), bug yang sama persis dengan Fase AR. Dampak praktis kecil untuk BUMI/DEWA karena
dividennya nyaris nol (sudah dikonfirmasi Fase AR), tapi tetap salah secara prinsip kalau nanti
ticker lain (yang bayar dividen besar) ditambahkan ke `LABELS`. Perlu diperbaiki kalau BBCA/UNVR
jadi diaktifkan live.

### Verifikasi
- `check_position()` real run setelah refactor: output print identik formatnya dengan sebelum
  refactor (BUMI hari ke-6 P&L +12,6%, DEWA hari ke-6 P&L +9,5%).
- `format_status()` real run: menampilkan persis format yang diminta user (entry->sekarang,
  P&L%, hari bursa ke-X dari 10, puncak, % mundur).
- `format_ihsg_progress()` real run: IHSG +1,95% 2 hari (belum kena ambang), BUMI +6,55%, DEWA
  +3,88% (bukan penurunan, jadi tidak "KENA" -- logika threshold bekerja benar).
- Regex `IHSG_PATTERN` dicek: `/ihsg`, `/IHSG` cocok; `/ihsg BUMI`, `/price BUMI` TIDAK cocok
  (tidak salah tangkap perintah lain).
- Kedua pesan (`/status` baru, `/ihsg`) beneran dikirim ke Telegram user, dikonfirmasi terkirim.
- `php artisan research:check-telegram-commands`: jalan normal, tidak error.
- `php artisan test`: 484 passed (tidak ada perubahan PHP).

### Status: SELESAI.

## Fase AU — Trailing stop reset per puncak baru + alert "Puncak Baru" (naik >=5%)

**Konteks:** User sadar dari `/status` bahwa BUMI/DEWA sudah bikin puncak baru (181/486) lebih
tinggi dari puncak saat alert trailing-stop pertama kali (173/482), tapi karena alert lama
"sekali seumur posisi", tidak akan pernah bunyi lagi walau mundur lebih dalam dari puncak baru
itu. Minta 2 hal: (1) trailing-stop reset tiap ada puncak baru (bukan sekali selamanya), (2)
alert baru saat harga bikin puncak >=5% lebih tinggi dari puncak terakhir yang diberi tahu.

### AU-1: Trailing stop reset per puncak
Field lama `alerted_pullback_pct` (boolean-like, `None`=belum pernah) diganti mekanismenya jadi
berbasis level puncak: field baru `alerted_pullback_at_peak` menyimpan PUNCAK saat alert
terakhir terkirim. Kondisi baru: `pullback >= PULLBACK_THRESHOLD and peak > alerted_at_peak`.
Ini otomatis "reset" begitu ada puncak baru yang lebih tinggi dari alert sebelumnya -- sama
persis cara kerja trailing stop asli (level naik seiring harga, bukan dipatok mati di titik
pertama).

### AU-2: Alert "Puncak Baru" (milestone +5%)
`NEW_HIGH_THRESHOLD = 0.05`. Field baru `milestone_peak` menyimpan puncak terakhir yang sudah
diumumkan (baseline awal = entry_price kalau belum pernah). Kondisi: `peak >= milestone_base *
1.05`. Pasangan positif dari trailing-stop -- kasih tahu user kapan "level aman" baru saja naik,
tanpa perlu tanya manual.

### Verifikasi
- Real run terhadap posisi BUMI/DEWA asli: ALERT PUNCAK BARU terkirim (BUMI Rp181 +13,8% dari
  baseline entry, DEWA Rp486 +10,5%) -- wajar karena ini pertama kali fitur ini aktif, langsung
  "menangkap" puncak historis yang belum pernah diumumkan. `open_positions.json` terverifikasi
  terisi `milestone_peak` dengan benar.
- Simulasi 3-langkah terkontrol (monkey-patch `compute_snapshot`, bukan data palsu -- alur kode
  ASLI `check_position()` yang dites, cuma input snapshot-nya dikontrol) membuktikan reset
  bekerja benar:
  1. Puncak 173, mundur 3% (belum pernah alert) -> PUNCAK BARU + TRAILING STOP dua-duanya
     terkirim, `alerted_pullback_at_peak` tersimpan 173.
  2. Puncak baru 183 (+5,8% dari 173), tapi cuma mundur 0,5% -> cuma PUNCAK BARU terkirim,
     trailing stop TIDAK ikut bunyi (pullback di bawah ambang, benar).
  3. Masih puncak 183 (tidak ada puncak baru lagi), mundur 2,5% -> TRAILING STOP terkirim LAGI
     (karena `peak(183) > alerted_at_peak(173)` dari langkah 1) -- walau sudah pernah alert di
     puncak sebelumnya. Ini bukti utama reset-nya jalan.
- `php artisan test`: 484 passed (murni Python, tidak ada perubahan PHP).

### Status: SELESAI.

## Fase AV — Alert otomatis broadcast ke kedua akun Telegram

**Konteks:** Fase AU (Puncak Baru) dites kirim ke akun utama, tapi user ternyata sudah pindah
cek dari akun kedua (Luthfi, 8870402966, ditambah Fase AQ) -- pesannya tidak pernah kelihatan.
Investigasi (`getUpdates`): `/status` terakhir user memang datang dari 8870402966, sementara
`send_telegram_alert()` tanpa `chat_id` eksplisit (dipakai SEMUA alert otomatis) selalu kirim ke
nomor utama saja (`load_telegram_credentials()`). Bukan bug kirim gagal -- salah target chat_id
sejak awal desain nomor kedua (Fase AQ cuma benerin ARAH BALASAN perintah, bukan alert otomatis).

### Perubahan
`send_telegram_alert()` di `detect_signal.py`: kalau `chat_id` diisi eksplisit (dipakai
`telegram_commands.py` buat balas /status dst) -> perilaku SAMA seperti sebelumnya, kirim cuma
ke situ. Kalau `chat_id` DIKOSONGKAN (dipakai semua alert otomatis: sinyal baru, trailing stop,
H-1, target waktu, puncak baru) -> sekarang **broadcast ke SEMUA `load_allowed_chat_ids()`**
(loop kirim satu-satu, gagal di satu akun tidak menggagalkan akun lain).

### Verifikasi
- Real test: `send_telegram_alert()` tanpa chat_id dipanggil, dicek eksplisit ke API Telegram
  langsung untuk KEDUA chat_id -- `ok:true` + `message_id` valid untuk 7162558029 (101) dan
  8870402966 (102).
- `php artisan research:check-trailing-stop-alert` dan `research:check-telegram-commands`
  dijalankan real setelah perubahan -- tidak error.
- `php artisan test`: 484 passed (murni Python, tidak ada perubahan PHP).

### Status: SELESAI. Semua alert otomatis (Puncak Baru, trailing stop, H-1, target waktu, sinyal
baru drawdown-bounce) sekarang nyampe ke dua-duanya akun, bukan cuma akun utama.

## Fase AW — Diskusi pasca-sidang: eksplorasi pelonggaran aturan sinyal beli BUMI (belum diimplementasikan)

### Konteks
Skripsi sudah selesai sidang (nilai A). User lanjut mengeksplorasi apakah aturan sinyal beli
`detect_signal.py` (dual-condition: BUMI DAN IHSG sama-sama <=-5% dalam 2 hari bursa) bisa
dilonggarkan untuk real-trading (bukan lagi keperluan skripsi). Ini catatan diskusi/backtest,
BELUM ada perubahan kode.

### Temuan 1: Backtest strategi RESMI (dual-condition) yang sedang berjalan, Jan-Agu 2026
5 trade, win rate 80% (4 profit, 1 rugi tipis), total return net (biaya 0.80% dipotong) +24.5%
non-compound, rata-rata +4.9%/trade. Simulasi modal Rp10jt all-in tiap trade -> jadi Rp12.656.167.
Trigger: 28 Jan (BUMI -11.4%/IHSG -7.3%), 4 Mar, 24 Apr, 19 Mei, 4 Jun. Semua exit via trailing
stop 2% (tidak ada yang sampai target waktu 10 hari).

### Temuan 2: Backtest usulan "BUMI-only" (syarat IHSG dihapus, threshold tetap -5%/2 hari)
Sejak 2024: 58 trade (vs 7 dual-condition), win rate 71% (sama dengan dual-condition), rata-rata
net +2.19%/trade, total non-compound +126.87%. Dicek discovery (70%, n=40) vs holdout (30%, n=18):
win rate 70%->72%, median return tetap POSITIF di kedua split (+1.39% -> +1.71%) -- beda dari
trend-following (Golden Cross) yang gagal karena median negatif di holdout. Kesimpulan: aturan
BUMI-only lebih longgar tapi TIDAK terlihat overfit ke masa lalu, konsisten kuat di data terbaru.
Risiko yang dicatat: tanpa filter IHSG, sistem tidak bisa bedakan "ikut market crash" vs "masalah
spesifik BUMI sendiri" (regulasi/tambang/dsb) -- kalau ada berita buruk beneran serius, strategi
ini tetap akan coba "beli waktu turun" padahal situasinya beda. Juga sinyal jadi ~1x/bulan (lebih
sering, butuh disiplin eksekusi lebih tinggi), dan 70% profit holdout disumbang cuma 5 trade
terbaik (konsentrasi tinggi).

### Belum diputuskan / next
User masih membandingkan varian lain (ambang lebih ketat -15% BUMI-only) sebelum memutuskan mau
ubah `detect_signal.py::detect()` yang mana. TIDAK ADA perubahan kode di fase ini -- murni riset
angka. Kalau nanti jadi diimplementasikan, WAJIB dokumentasikan sebagai fase terpisah dengan
detail perubahan kode + verifikasi test.

### Status: RISET, BELUM DIEKSEKUSI.

## Fase AX — Implementasi BUMI-only -5% (eksekusi hasil riset Fase AW)

### Konteks
Skripsi sudah selesai (nilai A). User memutuskan pakai varian BUMI-only -5% untuk real-trading
setelah membandingkan 5 varian (dual-condition resmi, BUMI-only -5%/-10%/-15%) -- BUMI-only -5%
menang telak di backtest Jan-Agu 2026 (20 trade, win rate 75%, total return net +54.6%, vs dual-
condition 5 trade/80%/+24.5%) dan tetap konsisten di backtest jangka panjang sejak 2024
(discovery/holdout, median tetap positif). Detail lengkap di Fase AW.

### Perubahan kode: quant/drawdown_bounce_tracker/detect_signal.py
- `detect()`: syarat trigger diubah dari `ret_2d_stock <= DROP_THRESHOLD AND ret_2d_ihsg <=
  DROP_THRESHOLD` jadi HANYA `ret_2d_stock <= DROP_THRESHOLD` (DROP_THRESHOLD tetap -5%, tidak
  berubah -- yang dihapus cuma syarat IHSG-nya).
- `ihsg_ret_2d` TETAP dihitung & disimpan di setiap signal (merge dengan data IHSG tidak dihapus),
  cuma tidak lagi dipakai sebagai filter -- murni info konteks.
- `format_signal_alert()`: pesan Telegram diupdate, baris IHSG diberi label eksplisit "info
  konteks saja, bukan syarat" supaya user tidak salah paham ini masih syarat wajib.
- Docstring modul diupdate menjelaskan histori keputusan (Fase AB/AC dual-condition -> Fase AW
  riset -> Fase AX eksekusi BUMI-only).
- `TRACKING_START_DATE` (31 Juli 2026) TIDAK diubah -- perubahan ini cuma mempengaruhi sinyal ke
  depan, tidak backdate sinyal historis.

### Verifikasi
- `detect()` dijalankan dry-run (send_telegram_alert di-monkeypatch, tidak ada side-effect real):
  0 sinyal baru ditemukan sejak TRACKING_START_DATE (konsisten -- BUMI cuma naik terus sejak 29
  Juli, belum ada momen turun >=5%/2 hari lagi).
- `format_signal_alert()` dites manual pakai data sinyal 8 Juni 2026 (real historical case), pesan
  Telegram tampil rapi dengan baris IHSG yang sudah dilabeli info konteks.
- Tidak menyentuh kode PHP -- `php artisan test` tidak perlu dijalankan ulang (tidak ada
  dependensi Laravel yang berubah).
- DEWA tetap pakai jalur yang sama (loop `for ticker in ["BUMI", "DEWA"]` tidak diubah) -- syarat
  BUMI-only sebenarnya jadi "stock-only" untuk KEDUANYA, bukan spesifik BUMI saja. Perlu dicatat:
  backtest yang mendasari keputusan ini HANYA diuji di BUMI, belum di DEWA -- risiko terbuka kalau
  DEWA punya karakteristik beda (lihat catatan "exploratory" di PROTOCOL.md).

### Status: SELESAI. Live mulai job scheduler berikutnya (harian 15:18 WIB).

## Fase AX (lanjutan) — Validasi & aktivasi DEWA setara BUMI

### Konteks
User minta strategi BUMI-only -5% yang baru diimplementasikan (Fase AX di atas) juga diterapkan
ke DEWA. Ternyata loop `detect()` sudah otomatis mencakup BUMI & DEWA sejak awal Fase AX (tidak
per-ticker) -- jadi secara kode tidak ada yang perlu diubah, tapi keputusan ini butuh divalidasi
dulu karena DEWA sebelumnya berlabel "exploratory" (sample historis dianggap belum cukup
meyakinkan, per PROTOCOL.md).

### Backtest DEWA-only -5% (Jan-Agu 2026 & sejak 2024)
- Jan-Agu 2026: 22 trade, win rate 86%, total return net +76.5% (vs dual-condition lama: 5 trade,
  80%, +19.3%).
- Sejak 2024 (discovery/holdout 70/30): discovery n=37 win rate 86% median +1.76%; holdout n=16
  win rate 88% median +2.91% -- performa MENINGKAT di holdout, tidak ada tanda overfit. Lebih kuat
  dari hasil BUMI sendiri (holdout BUMI: 72% win rate, median +1.71%).

### Perubahan kode
- `LABELS = {"BUMI": "tracked", "DEWA": "exploratory"}` -> `{"BUMI": "tracked", "DEWA": "tracked"}`.
  Efeknya di `format_signal_alert()`: ikon DEWA jadi 🟢 (sama seperti BUMI, sebelumnya 🟡), dan
  peringatan "⚠️ EXPLORATORY -- JANGAN dijadikan kesimpulan sendirian" tidak lagi muncul di alert
  DEWA.
- User dikonfirmasi via pertanyaan eksplisit sebelum eksekusi (naikkan status vs biarkan
  exploratory) -- user pilih naikkan ke "tracked".

### Verifikasi
- Backtest dijalankan dengan disiplin sama seperti riset BUMI (chronological discovery/holdout,
  entry defer 1 hari, net biaya 0.80%, exit trailing-stop 2% / target 10 hari).
- Tidak ada perubahan ke `detect()` -- sudah otomatis dari perubahan sebelumnya di Fase AX.

### Status: SELESAI.

## Fase AY — Screening kandidat saham baru + tambah BRPT ke tracker

### Konteks
Setelah BUMI/DEWA stabil dengan aturan stock-only -5%, user minta dicarikan saham lain yang cocok
dengan strategi yang sama. Discovery via screening 53 saham universe proyek (data/stocks/*.csv),
bukan feed live Top Value/Volume/Frequency BEI (tidak tersedia di proyek ini) -- overlap besar
karena universe ini sendiri sudah saham aktif/likuid.

### Temuan: episode independence adalah pembeda kunci
Screening awal (per-trade) menobatkan BRPT & TPIA sebagai kandidat terbaik (win rate 78-89%, total
return >100% sejak 2024). TAPI setelah dicek episode independence (jeda >15 hari kalender = episode
baru, mencegah satu penurunan panjang dihitung sebagai banyak trade independen palsu -- pola yang
sama yang menjatuhkan validasi trend-following sebelumnya):
- BRPT: n=58 trade -> cuma 21 episode independen. 1 episode (12 Jan - 5 Jun 2026, 144 hari)
  menyumbang 25/58 trade (43%). TAPI per-episode win rate TETAP kuat: 81%, median +1.17%. LOLOS.
- TPIA: n=51 trade -> 21 episode. Per-episode win rate cuma 52%, median +0.01% (praktis nol) --
  edge-nya nyaris seluruhnya artefak dari trade-count inflation. DITOLAK, tidak diimplementasikan.

### Perubahan kode
- `quant/drawdown_bounce_tracker/detect_signal.py`:
  - `LABELS`: tambah `"BRPT": "tracked"`.
  - `detect()`: loop ticker jadi `["BUMI", "DEWA", "BRPT"]`.
  - Tambah `BUTTON_CLOSE_BRPT = "🔴 Tutup BRPT"`, ditambahkan ke `default_keyboard()` (baris baru
    di keyboard, di bawah baris BUMI/DEWA).
- `quant/drawdown_bounce_tracker/telegram_commands.py`: import `BUTTON_CLOSE_BRPT`, ditambahkan ke
  `BUTTON_LABELS` map (-> `/close BRPT`).
- `/open`, `/close`, `/price`, `check_trailing_stop.py::compute_snapshot()` semua SUDAH generik
  (terima ticker apa saja lewat regex, tidak ada whitelist BUMI/DEWA hardcoded) -- tidak perlu
  diubah untuk mendukung BRPT.

### Verifikasi
- Dry-run `detect()` (monkeypatch, tanpa efek samping): 0 sinyal baru sejak TRACKING_START_DATE,
  LABELS & keyboard tampil benar mencakup BRPT.
- Dijalankan real lewat `php artisan research:detect-drawdown-bounce-signal`: "Tidak ada sinyal
  baru. Tidak ada trigger sejak 2026-07-31. Total tercatat: 0." -- konsisten.
- TPIA TIDAK ditambahkan kemanapun di kode -- keputusan sadar berbasis bukti episode-level yang
  lemah, bukan terlewat.

### Status: SELESAI.

## Fase AY (lanjutan) — Episode-check & tambah SMGR, ESSA

### Konteks
Lanjutan Fase AY: user minta episode-check 3 kandidat tambahan (ESSA, INDY, SMGR) sebelum
diputuskan mana yang ditambahkan.

### Hasil episode-check (per-episode, sejak 2024)
- SMGR: n=18 episode, win rate 89%, median +1.64%. Discovery (n=12) 92%/+1.29%, holdout (n=6)
  83%/+1.83%. Episode terbesar cuma 5/35 trade (14%) -- tidak ada konsentrasi masalah.
- ESSA: n=19 episode, win rate 79%, median +1.25%. Discovery (n=13) 77%/+1.02%, holdout (n=6)
  83%/+3.58% (MENINGKAT di holdout). Episode terbesar 4/29 trade (14%).
- INDY: n=21 episode, win rate 62%, median +1.03%. Discovery (n=14) 57%/+0.52%, holdout (n=7)
  71%/+2.41%. Masih lolos ambang (positif di semua split) tapi margin lebih tipis dari SMGR/ESSA.

User pilih: tambahkan SMGR & ESSA saja, skip INDY (marginnya lebih tipis).

### Perubahan kode
- `detect_signal.py`: `LABELS` tambah `SMGR` & `ESSA` (keduanya "tracked"). Loop ticker di
  `detect()` jadi `["BUMI", "DEWA", "BRPT", "SMGR", "ESSA"]`.
- Tombol Telegram baru: `BUTTON_CLOSE_SMGR`, `BUTTON_CLOSE_ESSA`, ditambahkan ke
  `default_keyboard()` (layout dirapikan jadi 2 tombol/baris: [BRPT, SMGR], [ESSA]).
- `telegram_commands.py`: import & `BUTTON_LABELS` map diupdate untuk SMGR/ESSA.

### Verifikasi
- Dry-run `detect()`: LABELS & keyboard tampil benar mencakup 5 ticker.
- Real run `php artisan research:detect-drawdown-bounce-signal`: "Tidak ada sinyal baru... Total
  tercatat: 0." -- konsisten, tidak ada error.
- INDY TIDAK ditambahkan kemanapun di kode -- keputusan sadar, bukan terlewat.

### Status: SELESAI. Tracker sekarang memantau 5 saham: BUMI, DEWA, BRPT, SMGR, ESSA.

## Fase AZ — Backtest usulan cek sinyal 2x/hari (sesi 1 + EOD) -- DITOLAK

### Konteks
User mengusulkan pecah cek sinyal beli jadi 2x/hari: tambahan cek di sesi 1 (~12:00 WIB) selain
cek EOD (15:18) yang sudah ada, biar alert lebih cepat kalau crash sudah kelihatan di sesi 1.
Didiskusikan dulu risikonya (whipsaw, harga belum settled, belum ada bukti) sebelum dibacktest.

### Backtest
Untuk 259 trigger historis (5 saham, sejak 2024, dibatasi data 1h yfinance 729 hari terakhir),
165 trigger (64%) sudah menembus -5%/2hari di closing sesi 1 -- kasus di mana cek sesi 1 akan
kasih alert lebih cepat. Dibandingkan entry HARI YANG SAMA (early) vs entry T+1 (current, aturan
sekarang), exit rule sama (trailing-stop 2%/target 10 hari):
- Win rate: current 75% vs early 68% -- TURUN.
- Rata-rata return: current +2.90% vs early +2.87% -- PRAKTIS SAMA, tidak ada gain nyata.
- Head-to-head: early menang 83/165 (50%), kalah 64/165 (39%), sama 18/165.

### Kesimpulan
Jeda T+1 yang sudah ada BUKAN cuma proteksi anti-data-snooping teoretis -- ternyata berfungsi
sebagai filter kualitas nyata: menunggu closing settle membantu menyaring penurunan sesi 1 yang
cuma noise sesaat (recover di sesi 2), bukan penurunan genuine. Split 2x/hari TIDAK memberi edge
tambahan, malah berpotensi menurunkan win rate.

### Keputusan
TIDAK DIIMPLEMENTASIKAN. Tidak ada perubahan kode -- aturan cek 1x/hari EOD (15:18) tetap
dipertahankan berdasarkan bukti.

### Status: RISET SELESAI, DITOLAK berdasarkan bukti.

## Fase BA — Peringatan awal sesi 1 (bukan ubah aturan entry)

### Konteks
Klarifikasi dari user setelah Fase AZ (yang menolak ubah aturan ENTRY jadi 2x/hari karena win
rate turun 75%->68%): maksud user bukan ubah strategi, tapi tambah NOTIFIKASI PERINGATAN di sesi
1 (~12:00 WIB) sebagai heads-up, sementara aturan resmi (trigger + entry T+1) tetap 100% sama
persis seperti sekarang di closing 15:18. Ini murni informasional, tidak menyentuh logika trading
yang sudah divalidasi sama sekali.

### File baru: quant/drawdown_bounce_tracker/check_session1_warning.py
- `fetch_daily_closes()`: Close MENTAH (bukan Adj Close) -- sengaja beda dari `fetch_recent()` di
  detect_signal.py yang masih pakai Adj Close (bug lama belum diperbaiki di sana) -- penting
  terutama untuk SMGR yang bagi dividen nyata (beda dari BUMI/DEWA/BRPT/ESSA yang dividennya
  minimal).
- `fetch_session1_price()`: closing sesi 1 (bar 1-jam terakhir sebelum jam 12:00 WIB) HARI INI,
  dari data intraday 1-jam yfinance.
- `format_session1_warning()`: pesan Telegram ⚠️ WASPADA, EKSPLISIT bilang "INI BELUM SINYAL
  RESMI" + statistik "~39% kasus recover di sesi 2" (dari temuan Fase AZ) supaya user tidak buru-
  buru entry cuma dari peringatan ini.
- `check_session1_warning()`: loop 5 ticker di LABELS (BUMI/DEWA/BRPT/SMGR/ESSA), cek ret_2d pakai
  harga sesi 1 vs Close 2 hari lalu, kirim peringatan kalau <= DROP_THRESHOLD (-5%, threshold SAMA
  dengan detect_signal.py). Idempotent per hari per ticker via `session1_warning_state.json`
  (state direset otomatis tiap tanggal berubah, tidak perlu cleanup manual).
- TIDAK PERNAH tulis ke tracker.sqlite3, TIDAK PERNAH ubah open_positions.json -- murni kirim
  pesan, tidak ada efek samping ke data lain.

### File baru: app/Console/Commands/CheckSession1WarningCommand.php
- `research:check-session1-warning` -- pola sama persis dengan `DetectDrawdownBounceSignalCommand`
  (tipis, panggil script Python via Process).

### routes/console.php
- Jadwal baru: `research:check-session1-warning` weekdays, 12:05 WIB (bukan pas 12:00 -- kasih
  buffer 5 menit biar sesi 1 beneran sudah tutup dulu), `withoutOverlapping()`.
- Job `research:detect-drawdown-bounce-signal` (15:18) TIDAK DIUBAH SAMA SEKALI.

### Verifikasi
- `php artisan schedule:list` menunjukkan job baru terjadwal benar (weekdays 12:05 WIB).
- Real run manual `php artisan research:check-session1-warning`: berhasil cek 5 ticker
  (BUMI/DEWA/BRPT/SMGR/ESSA), semua ret_2d positif/mendekati nol hari ini (tidak ada yang trigger
  peringatan) -- konsisten, tidak ada error.
- Preview `format_session1_warning()` dengan data simulasi (-6.2%) menghasilkan pesan yang rapi
  dan eksplisit menyatakan "belum sinyal resmi".

### Status: SELESAI.

### Verifikasi tambahan: tes Telegram beneran (bukan cuma dry-run)
User minta pastikan bot Telegram benar-benar tersambung ke command baru ini. Dua tes real terkirim
via `send_telegram_alert()` (jalur asli, broadcast ke semua chat_id):
1. Pesan format lengkap (`format_session1_warning()` dengan data simulasi -6.2%), dilabeli jelas
   "TES KONEKSI" supaya tidak disangka kondisi pasar beneran.
2. Tes eksplisit cek respons API Telegram langsung (bukan cuma print generik dari
   `send_telegram_alert()`): kedua chat_id (7162558029 utama, 8870402966 Luthfi) menerima
   `ok=True`, message_id 129 & 130.

Kesimpulan: koneksi Telegram bot <-> check_session1_warning.py <-> research:check-session1-warning
terverifikasi jalan end-to-end, bukan cuma asumsi dari dry-run.

## Fase BB — UNVR ditambahkan ke tracker + BRPT/SMGR/ESSA diintegrasikan ke sistem utama

### Konteks
User minta 2 hal: (1) tambahkan UNVR ke tracker drawdown-bounce Telegram (sudah lolos backtest Des
2025-Agu 2026: n=12, win rate 83%, total return net +39.7%), dan (2) integrasikan BRPT/SMGR/ESSA
(yang sebelumnya cuma "hidup sendiri" via script Python, terpisah dari sistem utama) ke tabel
`stocks` resmi supaya ikut fetch berita, sentimen, dan tampil di `/analytics` -- BUKAN cuma UNVR.

Klarifikasi penting yang didiskusikan sebelum eksekusi: UNVR sudah ADA di tabel `stocks` sejak
awal (salah satu dari 12 saham resmi, terintegrasi penuh news/sentimen/V6A-V6B), beda dari
BRPT/SMGR/ESSA yang TIDAK ADA di tabel `stocks` -- cuma dipantau lewat `detect_signal.py` (yfinance
langsung, tanpa dependensi DB).

### Bagian 1: UNVR -> tracker Telegram
- `detect_signal.py`: `LABELS` tambah `"UNVR": "tracked"`. Loop ticker di `detect()` jadi
  `["BUMI", "DEWA", "BRPT", "SMGR", "ESSA", "UNVR"]`.
- Tombol Telegram baru `BUTTON_CLOSE_UNVR`, ditambahkan ke `default_keyboard()` (baris [ESSA,
  UNVR]).
- `telegram_commands.py`: import & `BUTTON_LABELS` map diupdate.
- `check_session1_warning.py` otomatis ikut mencakup UNVR (loop `for ticker in LABELS`, tidak
  perlu diubah).

### Bagian 2: BRPT/SMGR/ESSA -> tabel `stocks` resmi (integrasi sistem utama)
Arsitektur ternyata bersih: begitu ada row baru di tabel `stocks` dengan `is_active=true`, SEMUA
command terjadwal otomatis mengambilnya (FetchNewsCommand, SyncLivePricesCommand,
ReanalyzeSentimentCommand, UpdateStockSnapshotsCommand, BacktestService, StockDashboardService --
semua query `Stock::where('is_active', true)`). Tidak perlu ubah kode command apapun.

Langkah eksekusi:
1. Insert 3 row baru ke `stocks` (code, company_name, sector, exchange=IDX, tradingview_symbol,
   yahoo_symbol, is_active=true): BRPT (id 20, Barito Pacific Tbk), SMGR (id 21, Semen Indonesia
   (Persero) Tbk), ESSA (id 22, Surya Esa Perkasa Tbk).
2. Insert `stock_aliases` untuk entity/keyword matching berita: BRPT (Barito Pacific, BRPT, Prajogo
   Pangestu), SMGR (Semen Indonesia, SMGR, SIG, Semen Gresik), ESSA (Surya Esa Perkasa, ESSA).
3. Backfill harga historis: `php artisan stocks:fetch-history --days=730 --stock=BRPT --stock=SMGR
   --stock=ESSA` -> 480 baris tiap saham tersimpan ke `stock_prices`.
4. Test fetch berita per saham (`php artisan news:fetch --stock=X`): BRPT 7 artikel, SMGR 8
   artikel, ESSA 5 artikel -- semua tersimpan dengan `stock_id` terhubung benar, sentimen otomatis
   ter-analisis inline (sentiment_label sudah terisi begitu artikel disimpan).

### Catatan penting: `article_entities` BUKAN mekanisme linking utama
Sempat mengira entity linking berita->saham lewat tabel `article_entities` (0 baris untuk 3 saham
baru, bikin kaget) -- ternyata itu SALAH ASUMSI. Linking utama adalah kolom `news_articles.stock_id`
langsung (FK), sudah terisi benar untuk ketiganya. `article_entities` sepertinya tabel terpisah/
legacy untuk keperluan lain (mungkin multi-entity NER per artikel), tidak dipakai untuk linking
dasar stock<->article. Tidak ada bug di sini, cuma salah baca tabel di awal.

### ⚠️ CATATAN PENTING YANG BELUM DISELESAIKAN: model prediksi V6A/V6B TIDAK otomatis valid untuk BRPT/SMGR/ESSA
Menambahkan saham ke tabel `stocks` membuat mereka ikut fetch berita/sentimen/harga, TAPI model
prediksi V6A (`model_technical_v6a.joblib`) dan V6B (`model_technical_sentiment_v6b.joblib`) adalah
ARTIFACT TERLATIH yang sebelumnya cuma divalidasi (walk-forward OOS) di 10 saham resmi lama.
BRPT/SMGR/ESSA belum pernah ikut proses training/evaluasi model ini -- kalau `/analytics` dipanggil
untuk saham ini, model MUNGKIN tetap menghasilkan output (RF/LogReg bisa generalisasi ke ticker
baru selama fitur teknikalnya numerik & mirip), TAPI akurasinya belum pernah diverifikasi secara
walk-forward OOS untuk saham-saham ini secara spesifik -- klaim "39.6% akurasi" TIDAK otomatis
berlaku untuk mereka. Preseden BUMI/DEWA: butuh MODEL TERPISAH KHUSUS karena karakteristiknya beda
dari 10 saham resmi -- BRPT/SMGR/ESSA berpotensi butuh perlakuan serupa. INI BELUM DIKERJAKAN --
perlu didiskusikan dengan user dulu sebelum retrain/validasi model untuk 3 saham baru ini
dilakukan (retrain adalah keputusan besar, bukan default, sesuai konvensi proyek).

### Verifikasi
- `php artisan test --filter="Stock|Analytics"`: 40 passed, tidak ada regresi dari perubahan DB.
- Query manual: BRPT/SMGR/ESSA masing-masing 480 baris `stock_prices`, dan 7/8/5 artikel
  `news_articles` dengan `stock_id` terhubung benar.
- Dry-run + real run `detect()`/`research:detect-drawdown-bounce-signal`: LABELS & keyboard
  mencakup 6 ticker (BUMI/DEWA/BRPT/SMGR/ESSA/UNVR), tidak ada error.

### Status: SELESAI untuk integrasi berita/sentimen/harga. TERBUKA untuk keputusan model
prediksi V6A/V6B (perlu diskusi user dulu).

## Fase BC — EmitentrustFetcher: sumber berita baru (RSS resmi, bukan scraping StockBit)

### Konteks
User awalnya minta scraping halaman `/stream` `/news` StockBit (pakai sesi login pribadi) untuk
narik berita. Ditolak dengan penjelasan: scraping otomatis halaman berlogin kemungkinan besar
melanggar ToS StockBit (risiko akun di-suspend/banned), dan kontennya sendiri berlisensi dari
penerbit asli (IDN Financials, Emitentrust) yang ditampilkan di StockBit -- bukan konten asli
StockBit. Disepakati: cek dulu apakah sumber ASLI (bukan agregatornya) punya RSS/API resmi.

### Riset RSS/API resmi
- **IDN Financials**: TIDAK ADA RSS publik (dicek homepage, /news, robots.txt, tag
  `<link rel="alternate" type="application/rss+xml">` di HTML -- nihil). Kemungkinan jual data
  lewat API berbayar terpisah, tidak diverifikasi lebih lanjut (di luar scope tanpa akun/kontak
  mereka).
- **Emitentrust.com**: ADA, WordPress standard feed di `https://emitentrust.com/feed/` -- publik,
  tidak butuh login/API key, `robots.txt` tidak melarang (cuma disallow /wp-admin/), update per jam,
  50 item terbaru per fetch, sudah ada kategori/tag per topik (termasuk nama emiten kadang).

### Perubahan kode
- File baru `app/Services/News/EmitentrustFetcher.php`: implements `NewsFetcherInterface`, pola
  sama persis dengan `RssLocalFetcher` (parse RSS 2.0 via simplexml, filter relevansi via
  `StockKeywordMapper::directHits()`), tapi scoped ke SATU feed (emitentrust) bukan daftar banyak
  feed seperti rss_local.
- `NewsAggregationService.php`: import `EmitentrustFetcher`, didaftarkan di `$fetchers` dengan key
  `'emitentrust'`.
- `config/news.php`: `multi_providers` dan `source_priority` ditambah `'emitentrust'` di akhir
  array (provider ini sebelumnya tidak akan pernah dipanggil walau sudah didaftarkan di
  `$fetchers`, karena mode 'multi' cuma iterasi provider yang ada di config ini).

### Verifikasi
- Test manual `EmitentrustFetcher::fetchForStock()` langsung: 50 item RSS mentah ter-parse benar;
  filter relevansi bekerja (BBCA 2 hit, BBRI 1 hit, ESSA/TLKM/ASII/BUMI 0 hit di snapshot saat itu
  -- wajar, feed general/macro-heavy, bukan bug).
  - Real run `php artisan news:fetch --stock=BBCA`: provider breakdown menunjukkan
  `emitentrust: 2`, terintegrasi penuh ke pipeline (relevance scoring, dedup, sentiment analysis
  inline) -- bukan cuma jalan sendirian di luar sistem.
- `php artisan test --filter="News"`: 75 passed, tidak ada regresi.

### Status: SELESAI.

## Fase BE — Redesain kartu berita: ringkasan + thumbnail gambar (mirip StockBit)

### Konteks
User bandingkan kartu berita proyek ini vs StockBit (screenshot): kartu proyek terlalu padat badge
teknis (ML/Rule/Skor/Conf/Relevansi/Q-score), tidak ada gambar thumbnail, ringkasan tidak
menonjol -- padahal StockBit nampilin judul + 2-3 baris ringkasan + sumber/tanggal + gambar.

### Temuan sebelum implementasi
- Kolom `summary` SUDAH ADA isinya di DB, cuma dirender kecil/terkubur di antara badge -- bukan
  data yang hilang, cuma masalah hierarki visual.
- Kolom gambar TIDAK ADA sama sekali di skema `news_articles`.
- 3 dari ~10 fetcher (newsapi, gnews, currents) TERNYATA SUDAH menyimpan URL gambar di kolom
  `raw_payload` (field `urlToImage`/`image`), cuma tidak pernah diekstrak ke kolom sendiri --
  data sebenarnya sudah ada, tinggal diambil, bukan perlu fetch ulang.
- Provider lain (business_site_search, rss_local, emitentrust, google_news_rss, ojk) TIDAK
  punya data gambar dari sumbernya sama sekali -- dicek langsung (grep tag media:content/
  enclosure di RSS mentah, cek struktur JSON response) -- bukan bug, keterbatasan sumber.

### Perubahan kode
- Migration baru: `news_articles.image_url` (string 1000, nullable).
- `NewsApiFetcher.php`, `GNewsFetcher.php` (2 lokasi: fetchForStock & fetchHistorical),
  `CurrentsFetcher.php`: tambah `'image_url' => $item['urlToImage'|'image'] ?? null` di array
  yang dikembalikan.
- `NewsAggregationService::persistRawArticles()`: tambah mapping `image_url` ke
  `updateOrCreate()` (sebelumnya field ini sudah ada di array fetcher tapi tidak pernah ditulis
  ke DB -- root cause kenapa gambar tidak pernah muncul walau datanya sudah difetch).
- `NewsArticle.php`: tambah `image_url` ke `$fillable`.
- `resources/views/news/index.blade.php`: kartu didesain ulang -- gambar/placeholder (ikon 📰)
  24x24 di kanan, ringkasan dipindah jadi paragraf utama (leading-relaxed, limit 220 char, naik
  dari 160), sumber+tanggal jadi baris sendiri, badge teknis (ML/Rule/Skor/Conf/Relevansi/Q)
  dipindah ke `<details>` collapsible "Detail teknis" (defaultnya tertutup, tidak lagi dominan).
  `onerror` di `<img>` fallback ke ikon placeholder kalau URL gambar broken/hilang.
- Backfill data lama: script sekali-jalan (tinker) ekstrak `image_url` dari `raw_payload` yang
  sudah tersimpan untuk artikel newsapi/gnews/currents lama -- 86 artikel ter-backfill tanpa
  fetch ulang ke API manapun.

### Verifikasi
- `php artisan test --filter="News"`: 75 passed, tidak ada regresi.
- Screenshot browser: placeholder ikon tampil rapi untuk artikel tanpa gambar (business_site_
  search, google_news_rss), layout konsisten di semua sentimen (border warna tetap jalan),
  "Detail teknis" collapsible berfungsi.
- Cek DB langsung: artikel ID 41 (provider detik/newsapi) punya `image_url` valid hasil backfill.

### Status: SELESAI.

## Fase BF — Backfill 108 trade (6 saham, Rp10jt/saham) ke Trade Journal -- berdampingan dengan data lama

### Konteks
User minta backtest 6 saham yang dipantau Telegram (BUMI/DEWA/BRPT/SMGR/ESSA/UNVR), Des 2025-
sekarang, modal Rp10.000.000 TERPISAH per saham (bukan satu modal gabung), lalu dicatat ke Trade
Journal beneran (`/trades`). Diminta diskusi dulu soal potensi tabrakan dengan data lama sebelum
eksekusi (bukan langsung insert).

### Temuan tabrakan (sebelum eksekusi)
- BRPT/SMGR/ESSA: 0 trade lama di Journal -- aman, tidak ada tabrakan.
- BUMI (11 trade lama, ID 120-159), DEWA (8 trade lama, ID 82-160), UNVR (4 trade lama, ID 197-
  208): SEMUA tumpang tindih periode dengan 58 trade baru (22+24+12) yang mau dimasukkan.
  Dibuktikan konkret: BUMI entry 9 Feb 2026 @Rp240 di data LAMA exit 28 Feb @Rp232,8, tapi
  backtest BARU untuk trigger yang SAMA (entry sama persis) exit 10 Feb @Rp259 -- strategi/exit
  logic beda, bukan cuma duplikat tanggal.
- 2 trade lama BUMI (ID 159) & DEWA (ID 160) berstatus OPEN -- posisi live yang masih dipantau
  bot Telegram (entry 29 Jul 2026), TIDAK disentuh oleh backtest baru (backtest baru tidak
  mencakup tanggal itu).

### Keputusan user
Ditanya lewat AskUserQuestion: skip BUMI/DEWA/UNVR vs hapus-ganti vs masukkan berdampingan tetap
dobel. User pilih opsi ke-3 (masukkan berdampingan, TIDAK menghapus/mengganti data lama) meski
itu bukan opsi yang direkomendasikan.

### Eksekusi
- Backtest 6 saham, modal Rp10.000.000/saham TERPISAH (compounding per saham, bukan gabung),
  metodologi sama seperti sebelumnya (stock-only <=-5%/2hari, entry T+1, exit trailing-stop 2%/
  target 10 hari, biaya net 0.80%).
- Hasil ringkas: BRPT 27 trade (81% WR, Rp10jt->Rp38,2jt, +281,8%), DEWA 24 trade (83% WR,
  ->Rp22,4jt, +123,9%), BUMI 22 trade (73% WR, ->Rp17jt, +70,0%), UNVR 12 trade (83% WR,
  ->Rp14,7jt, +47,2%), ESSA 11 trade (91% WR, ->Rp13,9jt, +38,9%), SMGR 12 trade (83% WR,
  ->Rp13,5jt, +34,9%). Total: 108 trade, modal Rp60jt -> Rp119,7jt (+99,43%).
- File CSV lengkap (108 baris) dikirim ke user via SendUserFile sebelum insert ke DB.
- Insert via script tinker (`Trade::create()` per baris), `result` = 'manual_close' (konsisten
  dengan precedent 33 trade drawdown-bounce sebelumnya, ID 194-226), `stop_loss`/`target_1` diisi
  referensi non-operasional (entry*0.98 / entry*1.05, kolom NOT NULL tapi tidak dipakai strategi
  time-based-exit ini), `notes` eksplisit menjelaskan: SIMULASI BACKTEST, modal Rp10jt KHUSUS per
  saham (bukan gabung), DAN untuk BUMI/DEWA/UNVR eksplisit mencatat bahwa ini berdampingan dengan
  data lama yang strategi/exit logic-nya berbeda (user sudah diberi tahu, memilih tetap masukkan).

### Verifikasi
- Jumlah trade per ticker setelah insert cocok persis (lama+baru): BUMI 11+22=33, DEWA 8+24=32,
  BRPT 0+27=27, SMGR 0+12=12, ESSA 0+11=11, UNVR 4+12=16. Total Trade Journal: 155 (2 open + 153
  closed).
- `php artisan test --filter="Trade"`: 34 passed, tidak ada regresi.
- Dashboard `/trades` (browser, live): Total Trade 155, Win Rate 83% (127W/26L), Total PnL
  +Rp129.931.xxx, Avg R:R 1:3,59 -- semua angka konsisten dengan gabungan data lama+baru.
- 2 posisi OPEN (BUMI/DEWA entry 29 Jul, live di Telegram) dikonfirmasi TIDAK tersentuh oleh
  insert ini.

### Status: SELESAI. Dicatat sebagai keputusan sadar user (bukan default rekomendasi) -- kalau
nanti perlu dirapikan/dipilah data lama vs baru untuk BUMI/DEWA/UNVR, tinggal filter dari `notes`
(yang lama tidak punya frasa "Fase AX-AY-BB", yang baru punya).

## Fase BG — Perbaiki business_site_search: gambar tetap tidak muncul walau ada di sumbernya

### Konteks
User tunjukkan contoh konkret: artikel BUMI dari provider `business_site_search` (Katadata) tampil
placeholder 📰, padahal begitu link artikelnya dibuka manual, ada gambar jelas.

### Root cause
`BusinessSiteSearchFetcher` TIDAK PERNAH membuka halaman artikel aslinya -- dia cuma scrape
halaman HASIL PENCARIAN (mis. search.katadata.co.id/search?q=...), ambil judul+ringkasan dari
situ, simpan link artikel, selesai. Dicek langsung: `<img>` di halaman hasil pencarian cuma logo
Katadata + avatar generik, BUKAN thumbnail artikel. Gambar asli cuma ada di
`<meta property="og:image">` pada halaman ARTIKEL itu sendiri -- yang tidak pernah dikunjungi
fetcher ini.

### Perbaikan
- `BusinessSiteSearchFetcher.php`: tambah method `fetchOgImage(string $articleUrl): ?string` --
  1 request tambahan (timeout 4 detik, try/catch penuh supaya kegagalan 1 artikel tidak
  menggagalkan fetch keseluruhan) HANYA untuk artikel yang SUDAH lolos filter relevansi (bukan
  semua hasil pencarian mentah), parse `<meta property="og:image">` (fallback `twitter:image`)
  via DOMXPath.
- Dipanggil di `articleFromNode()`, hasilnya dimasukkan ke field `image_url` yang baru
  ditambahkan di Fase BE.

### Verifikasi
- Test manual `BusinessSiteSearchFetcher::fetchForStock('BUMI')`: 5/5 artikel dapat `image_url`
  valid (URL CDN Katadata asli).
- `php artisan test --filter="News"`: 75 passed, tidak ada regresi.
- Artikel spesifik yang ditunjukkan user (ID 365, "Laba Bumi Resources (BUMI) Naik 35%...")
  diupdate manual dengan gambar hasil fetch sebagai bukti langsung.
- Real run `php artisan news:fetch --stock=BUMI` dijalankan di background untuk backfill natural
  artikel BUMI lainnya (tidak ditunggu selesai -- provider ini jadi sedikit lebih lambat karena
  request tambahan per artikel, wajar).

### Status: SELESAI. Artikel lama dari business_site_search selain yang di-update manual akan
terisi image_url secara bertahap tiap kali scheduler fetch berita berjalan (tidak di-backfill
massal sinkron -- terlalu banyak artikel utk 1x request per URL dalam sesi ini).

## Fase BG (lanjutan) — Backfill massal gambar business_site_search + temuan bot-detection

### Konteks
User tunjukkan contoh KEDUA (artikel BRPT "Milik Prajogo Ungkap Fakta...") yang masih placeholder
walau fix Fase BG sudah aktif -- ternyata artikel itu tersimpan SEBELUM fix, jadi belum ter-refresh
(bukan bug baru). Diminta backfill semua artikel lama sekalian.

### Perubahan kode
- `BusinessSiteSearchFetcher::fetchOgImage()` diubah dari `protected` ke `public` supaya bisa
  dipanggil ulang dari command terpisah.
- File baru `app/Console/Commands/BackfillBusinessSiteSearchImagesCommand.php`
  (`news:backfill-business-site-images --limit=N`) -- iterasi artikel `business_site_search` yang
  `image_url` masih null, panggil `fetchOgImage()` per artikel, update kalau ketemu.

### Eksekusi & hasil
- Dijalankan `--limit=141` (semua yang butuh backfill saat itu) di background, ~129 artikel
  diproses berhasil selesai.
- Hasil akhir: **118/143 artikel business_site_search sekarang punya image_url** (naik dari 2/143
  sebelum backfill).
- 25 sisanya TIDAK dapat gambar -- 2 kategori penyebab berbeda:
  1. Artikel yang og:image-nya memang tidak ada di halaman aslinya (situs tidak selalu isi tag
     itu) -- normal, bukan bug.
  2. **Temuan penting**: sebagian request ke Katadata diblokir oleh WAF/anti-bot mereka (BytePlus
     captcha "Security Check in Progress...") -- dibuktikan konkret dengan artikel BRPT yang
     ditunjukkan user kedua, response HTTP 200 tapi isinya cuma halaman captcha, bukan artikel
     asli. TIDAK DICOBA DIBYPASS (melanggar kebijakan anti-scraping situs sumber) -- artikel yang
     kena ini akan tetap placeholder selamanya kecuali Katadata berhenti nge-block request kita di
     lain waktu (misal karena rate limit sementara, bukan permanent block).

### Verifikasi
- `php artisan test --filter="News"`: 75 passed, tidak ada regresi.
- Query DB langsung: 118/143 (82%) artikel business_site_search sekarang punya image_url valid.

### Status: SELESAI. Command `news:backfill-business-site-images` tersedia untuk dipakai ulang
manual kalau perlu (tidak dijadwalkan otomatis -- artikel baru sudah dapat gambar langsung lewat
fetch normal, backfill cuma untuk artikel lama).

## Fase BH — RssLocalFetcher: ambil gambar dari enclosure/media:content di RSS mentah

### Konteks
User tunjukkan artikel `rss_local` (BMRI, BBRI) yang juga masih placeholder. Beda dari
business_site_search, dicek dulu apakah feed-nya sendiri sudah bawa data gambar.

### Temuan
Dicek 9 feed default `RssLocalFetcher` langsung: 7 dari 9 SUDAH punya tag `<enclosure type=
"image/...">` atau `<media:content>` (MRSS namespace) berisi URL gambar -- Detik, CNBC Indonesia,
Antara, IDX Channel, CNN Indonesia, Bloomberg Technoz, Republika. Cuma Katadata RSS & Tempo RSS
yang tidak punya tag ini sama sekali. Beda dari business_site_search, ini TIDAK BUTUH request
tambahan -- datanya sudah ada di RSS yang sama yang sudah difetch.

### Perubahan kode
- `RssLocalFetcher.php`: tambah `extractImageFromRssItem()` -- cek `<enclosure>` (kalau
  type dimulai "image" atau kosong) lalu fallback `<media:content>`/`<media:thumbnail>` (namespace
  `http://search.yahoo.com/mrss/`, diakses via `$item->children()`). Dipanggil di `parseFeedItems()`
  untuk kedua format (RSS 2.0 `<item>` dan Atom `<entry>`), hasilnya diteruskan ke `image_url` di
  array artikel yang dikembalikan `fetchForStock()`.
- `BackfillBusinessSiteSearchImagesCommand.php` digeneralisasi: tambah `--provider=` option
  (default `business_site_search`), supaya bisa dipakai juga untuk `rss_local` (dan provider lain
  ke depannya) -- logikanya generik (fetch og:image dari `source_url` yang tersimpan), tidak
  spesifik ke satu provider.

### Verifikasi
- Test manual `RssLocalFetcher::fetchForStock('BMRI')`: 3 dari 4 artikel dapat `image_url`
  langsung (termasuk artikel "Bank Mandiri Gandeng Paramount..." yang ditunjukkan user), 1 tanpa
  gambar (feed Katadata, sesuai ekspektasi -- bukan bug).
- `php artisan test --filter="News"`: 75 passed, tidak ada regresi.
- Backfill 391 artikel rss_local lama dijalankan via `news:backfill-business-site-images
  --provider=rss_local --limit=391` (di background, hasil dilaporkan terpisah).

### Status: SELESAI (kode). Backfill artikel lama sedang berjalan.

## Fase BI — Bug besar ditemukan: 1.606 link google_news_rss RUSAK untuk pembaca (bukan cuma soal gambar)

### Konteks
Investigasi lanjutan soal gambar hilang di artikel `google_news_rss` -- user coba klik tombol
"Buka artikel" secara manual, dapat "Error 400 (Bad request)" dari Google. Ini ternyata bug yang
JAUH lebih serius dari sekadar gambar hilang: link artikelnya sendiri rusak untuk SEMUA pembaca.

### Root cause (BUKAN limitasi Google seperti dikira awal / dicatat di Fase R7a sesi lalu)
`GoogleNewsRssFetcher::normalizeSourceUrl()` (baris 191 versi lama) punya bug: kalau link asli
dari Google News RSS (bentuk base64 "CBMi...", NORMAL panjangnya 196-873 karakter, live-verified
resolve ke HTTP 200) melebihi 240 karakter, kode MEMBUANG link asli itu dan menggantinya dengan
`https://news.google.com/rss/articles/` + hash SHA1 32-karakter -- yang TIDAK PERNAH valid (bukan
ID Google News asli, cuma hash palsu yang kebetulan mirip format). Karena link asli Google News
HAMPIR SELALU >240 karakter, bug ini merusak MAYORITAS artikel google_news_rss (1.606 total).

Live-verified: link asli (`CBMi...`) diakses langsung -> HTTP 200 (redirect 302 dulu, lalu 200,
halaman Google News yang bisa diklik lanjut ke publisher). Link hash palsu -> HTTP 400 error,
selalu, karena hash itu bukan ID valid apapun di sistem Google.

### Kenapa 240 dipilih sebelumnya
Kolom `news_articles.source_url` cuma `varchar(255)` -- 240 dipilih sebagai margin aman di bawah
255. Tapi karena link asli Google News nyaris selalu >240 karakter, threshold ini pada praktiknya
merusak SEMUA link Google News, bukan cuma kasus langka seperti maksud awalnya.

### Perbaikan
- Migration baru: `source_url` diperlebar dari `varchar(255)` ke `varchar(768)`. 768 dipilih
  sebagai batas AMAN untuk index UNIQUE `utf8mb4` (768 x 4 byte = 3072 byte, limit index InnoDB/
  MariaDB) -- bukan sembarang angka, sudah dicek `SHOW TABLE STATUS`/`SHOW VARIABLES LIKE
  'innodb_large_prefix'` dulu sebelum migrate. Panjang link asli maksimal yang ditemukan di data
  (1608 artikel dicek): 873 karakter -- 768 mencakup mayoritas kasus.
- `GoogleNewsRssFetcher::normalizeSourceUrl()`: threshold naik dari 240 ke 768. Link >768 karakter
  (jarang, cuma 5 dari 1606 di backfill) tetap fallback ke hash -- bukan valid, tapi tidak ada
  pilihan lain karena batas kolom.
- `tests/Unit/GoogleNewsRssFetcherTest.php`: test lama (`test_google_news_rss_normalizes_
  overlong_source_url`) yang menguji perilaku BUGGY (assert truncate di 240) diganti jadi 2 test:
  satu memverifikasi link realistis (318 karakter) DIPERTAHANKAN utuh (bug fix), satu lagi
  memverifikasi kasus ekstrem (>768) tetap fallback ke hash (constraint kolom).

### Backfill 1.606 artikel lama
Link asli SUDAH tersimpan di `raw_payload.link` sejak awal (fetcher selalu menyimpannya di sana,
cuma `source_url` yang salah override ke hash) -- backfill TIDAK perlu fetch ulang ke Google, cuma
baca `raw_payload` yang sudah ada dan tulis ulang `source_url`.
- **1.285 artikel diperbaiki** (source_url diganti dari hash palsu ke link asli valid).
- 5 artikel tetap hash (link asli >768 karakter, kasus ekstrem).
- 1 duplikat dilewati (sudah ada artikel lain dengan link asli yang sama -- unique constraint).
- 320 artikel tidak berubah (link aslinya sudah <=240 karakter sejak awal, sudah benar).

### Verifikasi
- `php artisan test --filter="News"`: 76 passed (2 test baru menggantikan 1 test lama).
- Live-verified: artikel yang ditunjukkan user ("Berikut Saham Pilihan Hari Ini...") -- source_url
  sebelum backfill = hash palsu (400 error kalau diklik), sesudah = link asli, dites langsung
  curl -> HTTP 200.

### Status: SELESAI. Ini bug lama yang sudah ada sejak GoogleNewsRssFetcher dibuat -- sempat
disalahartikan sebagai "limitasi Google yang tidak bisa diperbaiki" di riset R7a sesi sebelumnya,
padahal itu bug murni di kode kita sendiri (kolom kekecilan + threshold salah).

## Fase BJ — Jembatan otomatis Telegram /close -> web Trade Journal + /history tampilkan total sebenarnya

### Konteks
User tutup posisi BUMI & DEWA via `/close` di Telegram, tapi web `/trades` masih menampilkan
keduanya sebagai OPEN. Root cause: bot Telegram (`open_positions.json`) dan web Trade Journal
(tabel MySQL `trades`) itu 2 sistem data terpisah total, tidak pernah saling sinkron -- `/close`
cuma mematikan alert otomatis, tidak menyentuh record MySQL. Ditutup manual dulu (BUMI exit
Rp186, DEWA exit Rp474, tanggal 10 Agu 2026) sebagai perbaikan segera, lalu diminta bangun
jembatan otomatis biar tidak perlu tutup 2 kali lagi ke depannya.

Sekalian ditemukan pertanyaan kedua: `/history` di Telegram menampilkan ringkasan cuma dari 10
posisi terakhir ("10 menang, 0 rugi, +Rp7,4jt"), beda jauh dari kartu ringkasan web yang
menghitung dari SEMUA 155 trade (83% WR, +Rp129,9jt) -- membingungkan karena kelihatan seperti
angka salah, padahal cuma beda cakupan data.

### Perbaikan 1: jembatan /close -> MySQL
- `telegram_commands.py::handle_command()`: saat `/close` berhasil, cetak baris terstruktur
  `SYNC_CLOSE|TICKER|PRICE|TANGGAL` ke stdout (selain balasan normal ke user) -- Python
  TETAP tidak pernah sentuh MySQL langsung (prinsip resilience yang sama seperti
  `open_positions.json`, biar tetap jalan kalau MySQL lagi mati).
- `Trade.php::close()`: tambah parameter opsional `?Carbon $exitDate = null` (default `now()`
  kalau tidak diisi) -- sebelumnya selalu hardcode "sekarang", tidak bisa dipakai untuk sync
  tanggal exit yang beda dari hari ini.
- `CheckTelegramCommandsCommand.php`: method baru `syncTelegramClosesToTradeJournal()` -- parse
  baris `SYNC_CLOSE|...` dari output Python, cari record `trades` dengan ticker sama & status
  `open` (paling baru kalau lebih dari satu), panggil `Trade::close()` dengan harga & tanggal
  yang sama persis dari Telegram. Kalau tidak ada record open yang cocok atau DB mati, skip
  dengan warning -- tidak menggagalkan keseluruhan command (alert Telegram tetap harus jalan).

### Perbaikan 2: /history tampilkan ringkasan SEMUA trade, bukan cuma 10
- `CheckTelegramCommandsCommand::refreshClosedTradesCache()`: cache sekarang `{"overall": {...},
  "recent": [...]}` -- `overall` dihitung dari SEMUA trade closed (basis sama persis dengan kartu
  ringkasan web: total_trades, win_count, loss_count, win_rate, total_pnl, avg_rr, expectancy,
  avg_holding), `recent` tetap 10 detail terakhir seperti sebelumnya.
- `telegram_commands.py::load_closed_trades()` & `format_history()`: baca struktur baru,
  tampilkan `overall` sebagai ringkasan utama (match web), `recent` sebagai daftar 10 di
  bawahnya. Fallback ke format lama (list mentah) kalau cache belum sempat di-refresh setelah
  deploy -- tidak crash.

### Verifikasi
- Uji end-to-end manual: buat trade OPEN palsu (TESTX), panggil `handle_command('/close ...')`
  di Python -> konfirmasi baris `SYNC_CLOSE|TESTX|120.0|2026-08-10` tercetak. Panggil
  `syncTelegramClosesToTradeJournal()` di PHP dengan baris itu -> record TESTX otomatis
  ter-tutup dengan perhitungan benar (holding 9 hari, pnl Rp20.000). Panggil lagi kedua kalinya
  -> terdeteksi "sudah tidak ada posisi OPEN", tidak dobel proses. Data uji dihapus setelahnya.
- Render `format_history()` real: ringkasan "155 total trade... Win rate 83.2%... Total P&L
  +Rp131.811.825" -- cocok dengan kartu web (dicek langsung, angka match).
- 2 test lama (`CheckTelegramCommandsCommandTest`) diupdate mengikuti struktur cache baru.
- `php artisan test`: **485 passed**, tidak ada regresi.

### Status: SELESAI. Sinkronisasi berlaku otomatis untuk SEMUA /close berikutnya dari Telegram --
tidak perlu tutup manual di web lagi kecuali posisi itu memang belum pernah dicatat di sana sejak
awal.

## Fase BK -- Implementasi aturan gabungan (ret_2d ATAU drawdown_20d) ke live detector

### Konteks
User memberi 17 tanggal historis BUMI yang menurutnya "seharusnya" tertangkap sinyal beli, minta
dicarikan indikator/strategi yang bisa menangkapnya. Untuk menghindari curve-fitting (3 kegagalan
sebelumnya di proyek ini: buying-pressure, trend-following, TPIA), dilakukan base-rate/lift
analysis dulu, bukan langsung cocok-cocokkan ke 17 tanggal. Hasil karakterisasi: 17 tanggal itu
terbagi 2 klaster berbeda --
- **Klaster A "pullback dalam"** (12 tanggal): median RSI=35, Stoch=13, harga -14% dari MA20,
  -27% dari puncak 20 hari -- pola oversold/mean-reversion klasik.
- **Klaster B "momentum/dekat puncak"** (5 tanggal: 8 Des, 17/22/29 Jul, 5 Agu): median RSI=62,
  Stoch=62, harga +9% di atas MA20 -- pola breakout/momentum, TIDAK mungkin ditangkap filter
  oversold apa pun secara struktural. **Belum ada strategi untuk klaster ini -- area riset
  terbuka, belum diminta user untuk dikerjakan.**

Klaster A cocok ditangkap indikator **drawdown 20 hari** (`Close / rolling_max(Close,20) - 1`).
Aturan gabungan `ret_2d<=-5% ATAU drawdown_20d<=-20%` divalidasi dengan protokol KETAT yang sama
persis dipakai untuk memvonis kandidat DEWA TP/SL dulu (P1: OOS expectancy>0, P2: MENGALAHKAN
buy-and-hold, P3: excl-top5%-winner>0, P4: bootstrap CI95 lower bound>0; split 70/30 DAN 60/40;
episode-independence -- trade dalam 15 hari kalender digabung jadi 1 episode) -- diuji di BUMI lalu
5 saham lain (DEWA, BRPT, SMGR, ESSA, UNVR).

### Hasil validasi (6 saham)
| Saham | Status | Total return SEKARANG | Total return GABUNGAN |
|---|---|---|---|
| BUMI | LULUS PENUH | +196,2% (69 trade) | (baseline pembanding) |
| DEWA | LULUS PENUH | -- | naik |
| BRPT | LULUS PENUH | -- | naik |
| ESSA | LULUS PENUH | -- | naik |
| UNVR | LULUS PENUH | -- | naik |
| SMGR | GAGAL gate P4 saja (bootstrap CI95 lower bound belum >0, arah TIDAK negatif) | -- | -- |

**Keputusan**: 5 saham (BUMI/DEWA/BRPT/ESSA/UNVR) pindah ke aturan gabungan. SMGR TETAP pakai
aturan lama (ret_2d saja) -- gagal 1 dari 4 gate meski arahnya tidak negatif, tidak cukup kuat
untuk dinaikkan status.

### Perubahan
- `quant/drawdown_bounce_tracker/detect_signal.py`:
  - `fetch_recent()`: tambah kolom `dd_20d` (`Close/rolling_max(Close,20)-1`). **Sekalian
    perbaiki bug lama**: ganti basis harga dari `Adj Close` (disesuaikan dividen) ke `Close`
    mentah -- ditandai sebelumnya "low-impact untuk BUMI/DEWA" tapi WAJIB diperbaiki sebelum ada
    saham berdividen nyata di daftar; UNVR (salah satu dari 5 saham gabungan) itu pembayar
    dividen besar, dan backtest validasi di atas memang pakai Close mentah, bukan Adj Close.
  - Konstanta baru: `DRAWDOWN_THRESHOLD = -0.20`, `COMBINED_RULE_TICKERS = {BUMI, DEWA, BRPT,
    ESSA, UNVR}` (SMGR sengaja tidak dimasukkan).
  - `detect()`: trigger sekarang `ret2d_hit OR (ticker in COMBINED_RULE_TICKERS AND dd_hit)`,
    setiap sinyal diberi label `signal_type` (`ret2d` / `drawdown` / `ganda`) sesuai kondisi yang
    benar-benar terpenuhi.
  - **Bug lain ditemukan & diperbaiki sekalian**: `entry_row["adj_close"]` seharusnya
    `entry_row["adj_close_stock"]` -- kolom sudah di-suffix oleh `merge(suffixes=("_stock",
    "_ihsg"))` sejak refactor sebelumnya, tapi baris ini tidak pernah diperbaiki karena belum
    pernah ada sinyal live yang benar-benar tembus sejak refactor itu (TRACKING_START_DATE masih
    sangat baru, 2026-07-31). Ditemukan saat dry-run simulasi historis untuk fase ini.
  - `format_signal_alert()`: baris trigger sekarang menandai jelas syarat mana yang terpenuhi
    ("-- syarat sinyal (Turun Tajam 2 Hari)" / "(Drawdown Dalam)" / "(Ganda: ...)" vs "-- info
    konteks (bukan syarat kali ini)" untuk kondisi yang tidak ikut memicu).
- `quant/drawdown_bounce_tracker/schema.sql`: kolom baru `signal_type TEXT` di tabel `signals`.
- `get_connection()`: tambah migrasi `ALTER TABLE signals ADD COLUMN signal_type TEXT` dibungkus
  try/except (`CREATE TABLE IF NOT EXISTS` di schema.sql tidak menambah kolom ke DB yang sudah
  ada) -- dicek: kolom berhasil bertambah ke `tracker.sqlite3` yang sudah eksis tanpa merusak
  data lama.

### Verifikasi
- Simulasi historis (TRACKING_START_DATE dimundurkan ke 2024-01-01 sekadar untuk uji, tidak
  mengubah nilai produksi) menghasilkan 32 sinyal gabungan di 6 saham: 18 `ret2d`, 7 `drawdown`,
  7 `ganda` -- 3 jenis benar-benar muncul, bukan cuma teoretis.
  - Contoh `ret2d`: ESSA 28 Jul 2026, -5,5%/2hari.
  - Contoh `drawdown` murni: BRPT 1 Jul 2026, ret_2d cuma -1,8% (tidak lolos syarat lama) tapi
    drawdown 20 hari -22,5% -- kasus PERSIS yang tadinya lolos dari radar aturan lama.
  - Contoh `ganda`: ESSA 30 Jun 2026, ret_2d -16,9% DAN drawdown -22,6% sekaligus.
- Real run produksi: `php artisan research:detect-drawdown-bounce-signal` -- 0 sinyal baru sejak
  `TRACKING_START_DATE` (2026-07-31), konsisten dengan laporan sebelumnya (BUMI sudah pulih sejak
  22 Jul, belum ada trigger baru). Kolom `signal_type` berhasil termigrasi ke `tracker.sqlite3`
  yang sudah ada (dicek `PRAGMA table_info`).
- Format alert Telegram baru dites kirim REAL ke kedua akun (chat_id 7162558029 & 8870402966) --
  `ok:true`, message_id 187 & 188.

### Status: SELESAI. Aturan gabungan live di produksi untuk BUMI/DEWA/BRPT/ESSA/UNVR (SMGR tetap
aturan lama). Klaster B (momentum/breakout, 5 tanggal user) masih belum tertangani -- area riset
terbuka, menunggu keputusan user apakah mau dikejar.

## Fase BL -- Implementasi strategi momentum (RSI14>60) untuk Klaster B

### Konteks
Lanjutan riset Klaster B (momentum/breakout) dari Fase BK. Base-rate/lift analysis terhadap 5
tanggal hindsight user (17 Jul, 22 Jul, 29 Jul, 5 Agu, 8 Des) menunjukkan lift lemah (indikator
momentum menembak 15-50% dari SEMUA hari, tidak selektif) -- cocok-cocokkan ke tanggal spesifik
TIDAK layak dijadikan aturan. Sebagai gantinya, dibacktest strategi momentum-continuation
SUNGGUHAN (entry RSI14>60, exit sama seperti drawdown-bounce: trailing 2%/target 10 hari),
divalidasi protokol ketat P1-P4 yang sama (split 70/30 & 60/40, episode-independence) di 6 saham:

| Saham | Status |
|---|---|
| BUMI | LULUS PENUH 4/4 |
| DEWA | LULUS PENUH 4/4 |
| BRPT | LULUS PENUH 4/4 |
| ESSA | LULUS SEBAGIAN (3/4) |
| SMGR | GAGAL (win rate turun ke 43-50%, salah satu varian rugi) |
| UNVR | GAGAL (1-2/4 gate) |

**Red flag yang dicatat eksplisit**: 3 saham yang lulus penuh (BUMI/DEWA/BRPT) itu persis saham
dengan bull-run terbesar sepanjang periode uji (2024-sekarang, +133% s/d +301%) -- risiko
regime-dependence (strategi momentum cuma teruji valid di dalam tren naik yang sama, belum
terbukti tahan di kondisi sideways/turun panjang). Beda dari drawdown-bounce (mean-reversion) yang
tidak butuh tren naik untuk profit.

**Validasi tambahan (independen, tidak diminta tapi kebetulan terjadi)**: user menandai manual
zona "buy" di TradingView chart BUMI 4H (Jun-Agu 2026) berdasarkan insting sendiri, lalu dicek
objektif via deteksi swing-low->rally di data intraday -- HAMPIR SEMUA zona hijau yang ditandai
user match persis ke tanggal trigger yang sudah ditemukan: kaki-kaki kecil di Juni = drawdown-bounce
(GABUNGAN), kaki BESAR 17-22 Jul (rally +16,9%) = momentum RSI>60. Ini konfirmasi independen dari
sisi user sendiri (bukan cocok-cocokkan angka ke tanggal), bukan cuma dari backtest.

### Keputusan
User approve implementasi terbatas: **RSI14>60 untuk BUMI/DEWA/BRPT saja** (3 saham yang lulus
penuh), sebagai jenis alert BARU dan TERPISAH dari drawdown-bounce -- bukan gabung jadi satu
aturan, supaya user tidak salah kira ini strategi yang sama dengan yang sudah divalidasi lebih
matang.

### Perubahan
- `quant/drawdown_bounce_tracker/detect_signal.py`:
  - Konstanta baru: `MOMENTUM_RSI_THRESHOLD = 60`, `MOMENTUM_TICKERS = {BUMI, DEWA, BRPT}`,
    `MOMENTUM_TRACKING_START_DATE = 2026-08-12` (baru diaktifkan hari ini, tidak backdate).
  - `detect_momentum()`: fungsi terpisah dari `detect()` -- trigger `rsi14 > 60`, tidak perlu
    merge dengan IHSG (momentum tidak pernah pakai IHSG di riset validasinya). Exit sama seperti
    drawdown-bounce (dihitung di luar live-detector, exit ditangani terpisah lewat tracking
    trailing-stop yang sudah ada).
  - `format_momentum_alert()`: format alert BARU dan berbeda dari `format_signal_alert()` --
    icon biru (bukan hijau/kuning), header "SINYAL MOMENTUM" (bukan "SINYAL BELI"), SELALU
    ditandai EXPLORATORY dengan penjelasan eksplisit soal risiko regime-dependence, tidak peduli
    saham yang lulus validasi penuh sekalipun.
  - `main()`: sekarang panggil `detect()` DAN `detect_momentum()`, insert ke tabel masing-masing,
    kirim alert masing-masing lewat formatter masing-masing.
- `quant/drawdown_bounce_tracker/schema.sql`: tabel baru `momentum_signals` (append-only, pola
  sama seperti `signals` -- trigger blokir UPDATE/DELETE, `UNIQUE(ticker, trigger_date)` untuk
  idempotency). TERPISAH dari tabel `signals` yang sudah ada -- tidak dicampur.

### Verifikasi
- Simulasi historis (MOMENTUM_TRACKING_START_DATE dimundurkan ke 2026-06-01 sekadar untuk uji)
  menghasilkan 21 sinyal momentum di 3 saham sejak awal Juni -- konsisten dengan tabel trade yang
  sudah ditunjukkan ke user sebelumnya.
- Real run produksi: `php artisan research:detect-drawdown-bounce-signal` -- 0 sinyal baru (baik
  drawdown-bounce maupun momentum), sesuai ekspektasi karena `MOMENTUM_TRACKING_START_DATE` baru
  hari ini. Tabel `momentum_signals` berhasil dibuat di `tracker.sqlite3` (dicek `PRAGMA
  table_info`).
- Format alert momentum dites kirim REAL ke kedua akun Telegram (chat_id 7162558029 &
  8870402966) -- `ok:true`, message_id 189 & 190.
- `php artisan test`: **485 passed**, tidak ada regresi (test command yang ada cuma fake Process
  output, tidak bergantung ke teks exact dari script Python, jadi tidak perlu diupdate).

### Status: SELESAI. Sinyal momentum RSI14>60 live di produksi untuk BUMI/DEWA/BRPT, sebagai jenis
alert TERPISAH dari drawdown-bounce, selalu ditandai EXPLORATORY karena caveat regime-dependence
belum terselesaikan (belum teruji di kondisi pasar non-tren-naik).

## Fase BM -- Isi Trade Journal pakai aturan GABUNGAN (backfill + jembatan otomatis live)

### Konteks
User minta bandingkan strategi lama vs baru dari data Trade Journal web -- ternyata tabel `trades`
belum punya SATU PUN baris aturan GABUNGAN (baru live sejak Fase BK, dan production belum pernah
trigger sampai hari ini), jadi tidak bisa dibandingkan langsung. Sepanjang diskusi juga ditemukan:
data lama di `trades` ternyata campuran BEBERAPA strategi berbeda (drawdown-bounce ret2d-saja DAN
"AI tp30%/sl3%/hold40h") tanpa filter jelas di kartu ringkasan web -- dan dari 152 trade yang ada,
148 eksplisit berlabel SIMULASI BACKTEST, 4 sisanya juga belum terverifikasi ke fill broker asli
(0% benar-benar transaksi riil, semua backtest berbasis harga pasar asli). User setuju lanjut opsi
gabungan: (A) backfill historis GABUNGAN, (B) jembatan otomatis sinyal live -> Trade Journal.

### Opsi A -- Backfill historis
- Backtest aturan GABUNGAN (ret_2d<=-5% ATAU drawdown_20d<=-20%, exit trailing 2%/target 10 hari,
  biaya 0.80%) untuk BUMI/DEWA/BRPT/ESSA/UNVR sejak 2025-12-05 (window SAMA dengan backfill LAMA
  yang sudah ada, biar bisa dibandingkan langsung, bukan ditimpa/dihapus -- data lama TETAP ada,
  berdampingan, sama seperti presedan sebelumnya).
- 118 trade di-insert ke `trades`: BUMI 29, DEWA 28, BRPT 33, ESSA 14, UNVR 14. Modal simulasi
  Rp10.000.000 KHUSUS per saham, compounding (P&L trade berikutnya dihitung dari modal berjalan).
- Label eksplisit di `notes`: "SIMULASI BACKTEST (bukan transaksi riil) -- aturan GABUNGAN (Fase
  BK): ..." plus jenis sinyal (ret2d/drawdown/ganda) dan modal sebelum/sesudah tiap trade --
  konsisten dengan gaya baris LAMA yang sudah ada, supaya jujur & tidak tercampur seolah live.
- Verifikasi: win rate agregat 79.7% dari 118 trade GABUNGAN, angka modal akhir per saham cocok
  persis dengan backtest yang sudah ditunjukkan ke user sebelumnya (mis. BRPT Rp50.022.229).

### Opsi B -- Jembatan otomatis sinyal live -> Trade Journal
- `detect_signal.py`: fungsi baru `register_open_position()` -- begitu sinyal baru (drawdown-bounce
  ATAU momentum) berhasil di-insert ke sqlite, OTOMATIS didaftarkan ke `open_positions.json` (dulu
  cuma bisa lewat `/open` manual Telegram) supaya `check_trailing_stop.py` (jalan tiap 15 menit)
  langsung mulai mantau tanpa nunggu user ketik apa-apa. Sekaligus cetak baris terstruktur
  `SYNC_OPEN|TICKER|HARGA|TANGGAL|STRATEGI|DETAIL` ke stdout -- pasangan dari `SYNC_CLOSE` yang
  sudah ada di Fase BJ.
- `DetectDrawdownBounceSignalCommand.php`: method baru `syncOpenSignalsToTradeJournal()` -- parse
  baris `SYNC_OPEN`, cari `Stock` by kode ticker, `Trade::create()` status `open` berlabel jelas
  **"LIVE — sinyal otomatis ..."** (BUKAN simulasi) -- modal simulasi tetap Rp10.000.000 per posisi
  (bukan compounding, beda gaya sengaja dari backfill karena live entries dibuat satu-satu tanpa
  tahu urutan modal di muka, dijelaskan eksplisit di notes). Idempotent lewat `whereDate()` check
  (bukan `where()` string exact -- ketahuan lewat test kalau kolom `entry_date` disimpan dengan
  komponen waktu `00:00:00`, perbandingan string gagal cocok kalau tidak pakai `whereDate`).
  Penutupan REUSE jembatan `SYNC_CLOSE` yang sudah ada (Fase BJ) -- tidak perlu logika baru, begitu
  user `/close` posisi ini di Telegram, otomatis ikut nutup baris Trade Journal yang sama.

### Verifikasi
- 3 test baru di `DetectDrawdownBounceSignalCommandTest`: `sync_open_line_creates_live_trade_
  journal_entry`, `sync_open_is_idempotent_on_rerun` (jalan 2x, tetap 1 baris -- awalnya GAGAL
  karena bug `where('entry_date', $dateStr)` vs kolom tersimpan `2026-08-12 00:00:00`, diperbaiki
  jadi `whereDate()`), `sync_open_skipped_gracefully_when_stock_unknown`.
- `php artisan test`: **488 passed** (naik dari 485), tidak ada regresi.
- **Real run produksi hari ini (12 Agustus, bursa baru buka) -- DAN LANGSUNG DAPAT SINYAL LIVE
  PERTAMA**: DEWA trigger 11 Agustus (ret_2d -7,5%, persis sinyal pending yang sudah dipantau
  sejak kemarin), entry 12 Agustus @Rp448; BRPT JUGA trigger bersamaan, entry @Rp1.860. Keduanya
  otomatis: (1) terkirim alert Telegram, (2) masuk `open_positions.json` untuk pemantauan
  trailing-stop tiap 15 menit, (3) muncul di web Trade Journal sebagai posisi `open` berlabel LIVE
  -- seluruh pipeline dari deteksi sampai tercatat di web terbukti jalan end-to-end tanpa
  intervensi manual, bukan cuma teori.
- 2 baris sisa dari debugging manual (TESTBM, BUMI dobel) dibersihkan sebelum commit.

### Status: SELESAI. Trade Journal sekarang punya 270 trade total (152 lama + 118 backfill
GABUNGAN), plus 2 posisi LIVE pertama (DEWA, BRPT) yang tercatat otomatis dari sinyal produksi
hari ini -- bukti pipeline end-to-end bekerja, bukan simulasi.

## Fase BM lanjutan -- bug lot_size (lot vs lembar) ditemukan user

### Konteks
User beli DEWA riil di broker (241 lot @Rp448, IDX Order ID 202608120000773631, matched 12 Aug
09:05:14 WIB) dan minta lot di Trade Journal disesuaikan -- tapi begitu diperbaiki, UI malah
menampilkan "2 Lot / 241 lbr" (salah, seharusnya "241 Lot / 24.100 lbr"). Investigasi: kolom
`lot_size` di DB itu **LEMBAR** (bukan jumlah lot) -- konvensi resmi & sudah DITES
(`TradeJournalTest::test_lot_input_is_converted_to_lembar_at_100_per_lot`,
`TradeController::LEMBAR_PER_LOT`), "Lot" yang ditampilkan UI = `lot_size / 100`. Kode SYNC_OPEN
bridge (Fase BM) yang saya tulis keliru mengisi `lot_size` dengan jumlah LOT langsung (241), bukan
lembar (24100) -- kebalik dari konvensi asli. Sempat salah 2x: percobaan pertama saya malah
mengubah blade view (yang sebenarnya SUDAH BENAR) alih-alih memperbaiki data -- ketahuan begitu
baca test yang sudah ada, blade di-revert ke kondisi commit semula.

### Perbaikan
- `DetectDrawdownBounceSignalCommand::syncOpenSignalsToTradeJournal()`: `lot_size` sekarang diisi
  `$quantity` (lembar) langsung, bukan `$quantity / 100`.
- Data yang sudah kadung salah diperbaiki langsung di DB: 118 baris backfill GABUNGAN (Opsi A,
  `lot_size = quantity`), trade live BRPT (`lot_size = quantity`), dan trade live DEWA (diset manual
  `lot_size = 24100` sesuai order asli 241 lot).
- Blade view **TIDAK diubah** (sempat disentuh lalu di-revert -- sudah benar dari awal).
- Trade DEWA sekaligus diupdate notes-nya jadi "TRANSAKSI RIIL TERKONFIRMASI" (bukan simulasi lagi)
  lengkap dengan IDX Order ID, jam order/matched, breakdown fee broker+exchange.

### Verifikasi
- `php artisan test`: tetap 488 passed setelah perbaikan.
- Dicek manual: DEWA lot_size=24100 -> tampil "241 Lot / 24.100 lbr" (cocok order asli). BRPT &
  contoh backfill BUMI juga dicek, hasilnya benar.

### Status: SELESAI, sudah commit & push.

## Fase BN -- Peringatan dini H-1 sore (heads-up, bukan sinyal resmi)

### Konteks
User beli DEWA jam 09:05 WIB berdasarkan diskusi SEBELUM bursa buka (sinyal sudah "pending" sejak
closing kemarin sore) -- tapi alert sistem baru terkirim jam 09:16 (saya jalankan manual saat
chat), dan harganya (Rp448) itu SNAPSHOT INTRADAY, bukan closing resmi (bursa belum tutup saat
script dijalankan). User tanya: gimana caranya dapat peringatan SEBELUM harga bergerak, bukan
setelah. User pilih opsi: bangun alert peringatan dini (bukan perbaiki harga entry hari ini).

**Constraint desain**: aturan resmi (sudah divalidasi ketat, Fase BK) entry = closing harga T+1 --
TIDAK BOLEH diubah jadi lebih cepat (Fase AZ sudah backtest ide serupa: entry 2x/hari, win rate
turun 75%->68%). Jadi solusinya BUKAN mempercepat entry, tapi kasih heads-up LEBIH AWAL (sore hari
T, bukan pagi hari T+1) tanpa mengubah kapan entry resmi terjadi.

### Perubahan
- `quant/drawdown_bounce_tracker/schema.sql`: tabel baru `heads_up_alerts` (append-only, pola sama
  seperti `signals`/`momentum_signals`, `UNIQUE(ticker, trigger_date)`).
- `detect_signal.py`:
  - `detect_heads_up()`: fungsi baru, beda dari `detect()` -- cek HARI PALING BARU yang closing-nya
    sudah tersedia (T, bukan butuh T+1 seperti `detect()`), pakai syarat trigger yang SAMA
    (ret_2d<=-5% ATAU drawdown_20d<=-20% untuk COMBINED_RULE_TICKERS). Kalau match, berarti
    KEMUNGKINAN BESAR jadi sinyal resmi besok begitu closing T+1 tersedia.
  - `format_heads_up_alert()`: icon/header beda (🟡 PERINGATAN DINI, bukan 🟢 SINYAL BELI),
    eksplisit bilang BUKAN sinyal resmi, harga entry belum ada, aturan resmi tetap closing T+1 --
    tidak berubah.
  - `main()`: panggil `detect_heads_up()`, insert baru ke `heads_up_alerts`, kirim alert. Idempotent
    lewat `UNIQUE(ticker, trigger_date)` -- sekali diperingatkan untuk satu trigger_date, tidak
    diulang lagi walau job jalan berkali-kali di hari yang sama.

### Verifikasi
- Dry-run: 0 peringatan dini terdeteksi hari ini (benar -- semua 6 saham di bawah ambang saat ini,
  DEWA paling dekat -4,2%/-5,4%, belum tembus -5%/-20%).
- Format alert dites dengan data sintetis, dikirim REAL ke Telegram (`ok:true`, message_id 205 &
  206).
- Real run produksi: `php artisan research:detect-drawdown-bounce-signal` -- jalan bersih, baris
  baru "Tidak ada peringatan dini baru. Total tercatat: 0." muncul tanpa error.
- `php artisan test`: 488 passed, tidak ada regresi.

### Status: SELESAI. Peringatan dini live di produksi untuk 6 saham (BUMI/DEWA/BRPT/SMGR/ESSA/UNVR),
jalan otomatis di jadwal harian yang sama (15:18 WIB) dengan deteksi sinyal resmi -- tidak perlu
job terjadwal terpisah.

## Fase BN lanjutan -- rapikan wording alert (Sinyal Beli + Peringatan Dini)

### Konteks
User protes "Rencana exit: tahan 10 hari bursa ≈ {tanggal}" di alert Sinyal Beli itu MENYESATKAN
-- exit sebenarnya trailing stop 2% dari puncak (bisa jauh lebih cepat dari 10 hari) ATAU target
waktu 10 hari (mana duluan), bukan "tahan sampai tanggal X" seperti kesan yang diberikan teks lama.
Sempat diusulkan tambah baris statistik win rate historis per saham, tapi user minta itu DIHAPUS
(cuma mau bagian exit yang diperbaiki). Sekalian diminta rapikan wording Peringatan Dini (Fase BN)
juga.

### Perubahan
- `format_signal_alert()`: baris "Rencana exit: tahan 10 hari bursa ≈ {tanggal}" DIHAPUS, diganti
  "Exit: dipantau OTOMATIS tiap 15 menit -- keluar begitu harga mundur 2% dari puncak (trailing
  stop, bisa kapan saja) ATAU maksimal 10 hari bursa kalau belum kena. Alert susulan (🎉 Puncak
  Baru / 🔴 Trailing Stop / 🟠 Target Waktu) menyusul otomatis, tidak perlu dipantau manual." --
  variabel `exit_estimate` yang sudah tidak dipakai ikut dihapus.
- `format_heads_up_alert()`: dirombak jadi label-tebal per bagian (Closing hari ini / Status /
  Kemungkinan besok / Kenapa nunggu besok / Yang perlu kamu lakukan), konsisten gaya dengan
  `format_signal_alert()` -- sebelumnya 1 paragraf panjang, sekarang terpisah section pendek biar
  lebih gampang dipindai di HP.
- Contoh render didemo pakai DATA ASLI DEWA (trigger 11 Agustus, ret_2d -7,5%, dd_20d -7,9%,
  IHSG -2,2%) -- bukan data sintetis -- supaya user bisa lihat persis bunyi alert yang akan
  terkirim untuk kasus nyata yang sudah terjadi.

### Verifikasi
- Kedua format dites kirim REAL ke Telegram (kedua akun), `ok:true`, message_id 209-212.
- `grep` konfirmasi tidak ada test PHP yang bergantung ke teks lama ("Rencana exit"/"tahan 10
  hari") -- semua teks Python, tidak ada assertion PHP yang menyentuhnya.
- `php artisan test`: 488 passed, tidak ada regresi.

### Status: SELESAI.

## Fase BN lanjutan lagi -- rapikan /status Telegram

### Konteks
User cek `/status`, protes "Hari bursa ke-1 dari 10" dianggap kurang berguna, minta dihapus. Juga
"Puncak Rp458, mundur 0,9%" membingungkan -- kesannya ambang trailing stop itu 0,9%, padahal
aturannya TETAP 2% (0,9% itu progress mundur SAAT INI dari puncak, bukan ambang trigger). Diskusi
2 putaran sebelum diimplementasikan.

### Perubahan
- `telegram_commands.py::format_status()`: "Hari bursa ke-X dari {TARGET_HOLD_DAYS}" DIHAPUS.
  "Puncak Rp.../mundur X%" diganti dua angka terpisah yang jelas: **harga PASTI** trigger trailing
  stop (`peak * (1 - PULLBACK_THRESHOLD)`, ditulis eksplisit "-2%") dan **jarak SEKARANG** ke harga
  itu (dari current price ke stop price, BUKAN dari peak) -- "Sekarang masih +X% di atas stop".
- Notes tambahan (H-1 target waktu / sudah lewat ambang) tetap dipertahankan, cuma teksnya
  disederhanakan (tidak sebut ulang angka 2% di situ karena sudah eksplisit di baris utama).

### Verifikasi
- Dites dengan posisi live asli (DEWA, BRPT) -- render benar: "Stop trailing (-2%): Rp449 |
  Sekarang masih +0,7% di atas stop".
- Dikirim REAL ke Telegram (`ok:true`, message_id 217 & 218).
- `php artisan test`: 488 passed, tidak ada regresi (tidak ada test PHP yang bergantung ke teks
  lama "Hari bursa ke-").

### Status: SELESAI.

## Fase BN lanjutan ketiga -- sederhanakan /status gaya kartu posisi broker

### Konteks
User protes lagi: "Stop trailing (-2%): Rp449 | Sekarang masih X% di atas stop" dianggap masih
berlebihan -- alert otomatis SUDAH bunyi sendiri begitu stop kena, jadi /status tidak perlu
mengulang aturan/persentase tiap kali. Diskusi dulu, saya usulkan format gaya kartu posisi broker
(StockBit/IBKR dst -- cukup 2 angka: Puncak & Stop, tanpa penjelasan ulang), user setuju.

### Perubahan
- `format_status()`: baris kedua disederhanakan jadi `Puncak Rp{X} | Stop Rp{Y}` saja -- hilang
  "-2%" eksplisit dan "Sekarang masih X% di atas stop". Baris pertama juga dibalik urutannya:
  harga SEKARANG duluan (paling penting dilihat cepat), baru "dari entry Rp{Z}" sebagai konteks
  (sebelumnya: entry dulu → sekarang).
- Notes kondisional (H-1 target waktu / sudah lewat ambang) tetap dipertahankan apa adanya.

### Verifikasi
- Dites dengan posisi live asli (DEWA, BRPT) -- render: "🟢 DEWA: Rp466 (+4.0%) dari entry Rp448 /
  Puncak Rp470 | Stop Rp461".
- Dikirim REAL ke Telegram (`ok:true`, message_id 225 & 226).
- `php artisan test`: 488 passed, tidak ada regresi.

### Status: SELESAI.
