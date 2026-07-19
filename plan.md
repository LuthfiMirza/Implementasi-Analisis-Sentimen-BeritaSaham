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
