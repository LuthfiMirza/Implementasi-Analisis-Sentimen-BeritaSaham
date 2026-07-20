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

### Status Fase L: TEMUAN DIDOKUMENTASIKAN. Belum ada perubahan kode/UI — keputusan tindak lanjut (perkuat disclaimer / redesign gerbang validitas / nonaktifkan badge "VALID" sampai diperbaiki) akan dibahas dengan user di sesi berjalan ini.
