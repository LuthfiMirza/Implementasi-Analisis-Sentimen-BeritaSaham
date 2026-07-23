# Sentimena — Super Plan & Codex CLI Handoff

> **Untuk agent yang membaca ini (Codex CLI):** kamu mulai dari nol. Baca dokumen ini
> **sampai habis** sebelum menyentuh kode. Ini adalah kontrak kerja proyek — bukan sekadar TODO.
> Sumber kebenaran metodologi ada di `plan.md` (log 15 fase, 0 s/d O). `CLAUDE.md` berisi
> konvensi repo. Dokumen ini menyatukan keduanya + antrian kerja ke depan.

Terakhir diperbarui: 2026-07-21. Ditulis oleh Claude (sesi audit) sebagai handoff ke Codex CLI.

---

## 0. Cara pakai dokumen ini

1. Baca §1–§2 (konteks + disiplin) — **wajib**, ini yang membedakan proyek skripsi ini dari demo biasa.
2. Cek §3 (state sekarang) untuk tahu apa yang sudah selesai & apa yang sedang berjalan.
3. Ambil item dari §4 (antrian kerja) **satu per satu, urut prioritas**. Jangan lompat.
4. Setiap selesai 1 item: jalankan protokol verifikasi §6, dokumentasikan sebagai fase baru di `plan.md`, commit selektif.
5. §5 = keputusan yang SUDAH FINAL — jangan dibuka ulang, jangan diusulkan lagi.

---

## 1. Konteks proyek (cold-start briefing)

**Sentimena** = aplikasi skripsi: analisis sentimen berita saham IDX + prediksi arah harga + Decision
Support System (DSS). Stack: **Laravel 13 / PHP 8.3 / MySQL** (`sentimena_dashboard`, sync, tanpa
queue/Redis) + **Python** (`quant/`) untuk ML training & serving (FastAPI).

**Pipeline 5 tahap** (kerangka berpikir untuk hampir semuanya):
```
Berita → Analisis Sentimen (IndoBERT fine-tuned + rule-based) →
Fitur Gabungan (teknikal + sentimen) → Model Prediksi (V6A/V6B) → DSS
```

**Model produksi:**
- **V6A** `storage/app/prediction/model_technical_v6a.joblib` — RandomForest, technical-only, 10 ticker resmi. **Ini acuan default sistem.**
- **V6B** `model_technical_sentiment_v6b.joblib` — LogisticRegression, teknikal+sentimen. Akurasi lebih rendah dari V6A (sentimen belum terbukti membantu prediksi harga).
- **BUMI/DEWA** — model khusus per-saham, TERPISAH, tidak digabung V6A/V6B.

**Serving lokal (LaunchAgent, auto-restart):** `quant/prediction_api.py` (port 8001),
`quant/sentiment_api.py` (port 8002, IndoBERT fine-tuned di `storage/app/sentiment_model/indobert_finetuned_v1/`).

**Command artisan penting:** `prediction:retrain-production` (V6A/V6B), `prediction:retrain-volatile`
(BUMI/DEWA), `prediction:refresh-price-history` (data harga), `stocks:sync-fundamentals`,
`prediction:export-research-dataset` (generator dataset), `news:auto-recover-gap`, `sentiment:reanalyze`.

**Scheduler (`routes/console.php`, satu-satunya source of truth, tidak ada cron config lain):**
Minggu 01:00 refresh harga → Minggu 02:00 retrain BUMI/DEWA → Senin 06:00 fundamental →
Senin 07:00 retrain V6A/V6B. Plus `news:auto-recover-gap` tiap 30 menit (self-heal outage MySQL).

**venv Python (terisolasi, gitignored):** `quant/.venv-sentiment/` (torch 2.2.2, transformers 4.57.6 —
untuk fine-tune sentimen, CPU-only karena GPU AMD OOM), `quant/.venv-fundamentals/` (yfinance).

**Sumber data training (PENTING, sering bikin bingung):** fitur teknikal dihitung dari **file statis
`data/stocks/{TICKER}.csv` + `data/IHSG.csv`** (via `ResearchPredictionFeatureService`), BUKAN dari
tabel DB `stock_prices` (DB lebih segar tapi training tidak baca langsung dari situ). File CSV ini
di-refresh mingguan oleh `prediction:refresh-price-history` sejak Fase O.

**Test:** `php artisan test` (saat ini **427 passed**). PHPUnit murni (BUKAN Pest). `vendor/bin/pint` untuk gaya PHP.

---

## 2. Disiplin kerja NON-NEGOTIABLE (baca ini dua kali)

Proyek ini sudah 15 fase audit yang menemukan pola berulang: fitur dibangun dari intuisi lalu
gagal saat divalidasi jujur. Jangan mengulang pola itu. Aturan:

1. **Tidak ada klaim metrik tanpa validasi out-of-sample yang benar.** Untuk model prediksi:
   walk-forward OOS pakai `build_folds`/`evaluate_predictions`/`mean_metrics` dari
   `quant/train_prediction_models.py` (setting resmi `min_train_days=252, test_window_days=126`).
   Untuk klasifikasi (sentimen): split train/val/test yang held-out, **seleksi di val, ukur di test SEKALI**.
2. **Anti data-snooping.** JANGAN tuning hyperparameter/threshold dengan mengintip test set. JANGAN
   "coba banyak config lalu pilih yang terbaik di test". Kalau butuh pilih config → pilih di val.
3. **Temuan negatif WAJIB dicatat apa adanya di `plan.md`.** Ini bukti skripsi, bukan aib. Kalau
   sebuah perbaikan ternyata tidak membantu / tidak konklusif, tulis itu — jangan disembunyikan atau dipoles.
4. **Gating & jangan timpa produksi.** Semua retrain punya gerbang: model baru hanya menggantikan
   yang lama kalau TIDAK memburuk (ambang degradasi macro-F1 0.05). Kalau memburuk → simpan sebagai
   `*_candidate`, jangan promosikan. Model/artefak produksi tidak boleh ditimpa sebelum lolos gate.
5. **Git selektif.** JANGAN `git add -A`. Repo ini campur CSV besar hasil regenerasi, log, dan
   source asli. Stage file per nama, cek `git diff` sebelum commit. Commit message akhiri dengan
   `Co-Authored-By: Codex <noreply@openai.com>` (atau identitas agent-mu). **Jangan push kecuali user minta.**
6. **`source='seed'` di `stock_prices` = data sintetis sisa** — filter (`WHERE source <> 'seed'`) di query yang harus reflect data pasar nyata.
7. **Dua klaim yang HARUS dipisah:** (a) "kualitas analisis sentimen" (boleh dikejar naik) vs
   (b) "kontribusi sentimen ke prediksi harga" (sudah terbukti NOL 2×, batasan struktural coverage
   berita — JANGAN diklaim membaik tanpa bukti baru). Menaikkan (a) tidak otomatis menaikkan (b).

---

## 3. State sekarang (per 2026-07-22 malam — Fase 0-Q5 tuntas, R1-R5b tuntas, R6-R7 DIRENCANAKAN)

**Fase 0–P, Q1–Q5 SEMUA SELESAI dan di-push.** 436 test hijau per commit terakhir yang diverifikasi
(`6689596`). Ringkas: sentimen ML 35.6%→58.16% (B, **tapi baca peringatan di bawah soal angka ini**),
tie-break 32.69%→55.77% (C), engine prediksi 33.3%→39.6% (G), DSS berbasis model tervalidasi (F→I),
fundamental live mingguan (K), Trading Signal "VALID" dibuang (L), retrain V6A/V6B otomatis (N),
staleness data harga ditutup (O), dataset BUMI/DEWA diregenerasi tiap retrain (Q1), class-weighted
sentimen NO IMPROVEMENT (P), active-learning Q2 kalah dari produksi (Q2), cross-section-rank
diperbaiki (Q3), file data regeneratif di-untrack git (Q4), log MySQL dibersihkan (Q5).

**Fase R1-R5b SUDAH SELESAI DAN DI-COMMIT** (bukan lagi rencana — sudah dieksekusi oleh Codex sesi
sebelumnya, commit `00956ae`, `bc4b0a8`, `eb30232`, `6689596`):
- R1: kolom `sample_method` di `sentiment_manual_labels`, backfill 988 baris jadi `legacy_hard_case`.
- R2: `sentiment:audit-manual-labels` — 91/988 label di-flag mismatch tinggi vs model produksi.
- R3: `NewsArticleTypeClassifier` (macro/emiten_spesifik/multi_emiten_recommendation).
- R4: `docs/sentiment_labeling_guideline.md`.
- R5a: UI `/sentiment-validation/representative` — user sudah label **865 baris representative_random**
  (jauh di atas target awal 150-200).
- R5b: retrain candidate + evaluasi ganda. **Gate awalnya PASSED secara SALAH** (bandingkan ke
  konstanta lama 0.5816 dari file yang sudah tidak ada, bukan ke produksi di file yang sama) — **sudah
  DIKOREKSI** di commit `6689596`: gate yang benar (`candidate >= production, SAMA file`) menghasilkan
  **FAILED** (0.7141 vs 0.8768, delta -0.1627). Candidate R5b **TIDAK dipromosikan**. Test set terkunci
  dengan SHA256 di `output/prediction_research/sentiment_r5b_locked_tests/` (di-commit ke git, TIDAK
  digitignore — pelajaran dari insiden ini).

**⚠️ TEMUAN BARU KRITIS (ditemukan investigasi 2026-07-22 malam, BELUM ditindaklanjuti)**: ada
**audit evaluasi independen lain** yang sudah jalan paralel (kemungkinan sesi Codex/tool lain),
hasilnya di working tree TAPI **masih uncommitted**: `docs/sentiment_evaluation_contract.md`,
`docs/sentiment_project_context.md`, `config/sentiment_evaluation.php`, `scripts/*.py`,
`data/evaluation/`, `reports/*.json`. Temuan utamanya: **file test aktif (`storage/app/
sentiment_finetune/test.jsonl`, 148 baris) berstatus "likely_contaminated"** — ada 14 overlap exact +
13 near-duplicate + 2 label conflict dengan train/validation aktif (`reports/evaluation_contract_audit.json`).
Angka `0.5816` cuma "historical_reference", tidak bisa direproduksi di file manapun yang ada sekarang.
**Rencana detail penanganan ini ada di §4c "Fase R6-R7" di bawah — baca SEBELUM kerja apa pun
terkait sentimen lagi, termasuk sebelum melanjutkan ke ablation input konteks.** Fase R6-R7 murni
rencana, belum ada implementasi baru.

**Item P & Q1 di §4 di bawah sudah SELESAI — jangan dikerjakan ulang.** Antrian berikutnya: Q2–Q5,
semua butuh keputusan/konfirmasi user dulu sebelum dieksekusi (lihat catatan di masing-masing item).

---

## 4. Antrian kerja (urut prioritas — ambil satu per satu)

### P. ✅ SELESAI (2026-07-21) — Evaluasi eksperimen sentimen berbobot
**JANGAN DIKERJAKAN ULANG / JANGAN DIRETRAIN LAGI.** Eksperimen dituntaskan (resume dari 3 model
sweep yang sudah tersimpan, evaluasi ulang, konfirmasi 3-seed pemenang). **Verdict: NO IMPROVEMENT**
— skema `sqrt_inverse` menang di val (0.7564) tapi mean test macro-F1 3-seed **0.5552** < produksi
**0.5816** (margin -0.0264, dalam std 0.0262 → gagal gate). Class weighting menaikkan positive F1
(0.377→0.386) tapi menjatuhkan negative F1 (0.621→0.545) — memindahkan masalah, bukan menyelesaikan.
**Model produksi `indobert_finetuned_v1` TIDAK diganti, TIDAK ada promosi.** Kandidat tersimpan di
`storage/app/sentiment_model/indobert_finetuned_v2_weighted/` sebagai referensi riset, bukan dipakai
serving. Dokumentasi lengkap: `plan.md` Fase P. Report mentah: `output/prediction_research/
sentiment_weighted_experiment_report.{json,txt}`. Commit: `2edd8a3`. **Kalau mau kejar sentimen lebih
akurat lagi, jalur class-weighting sudah terbukti buntu di dataset ini — lihat Q2 untuk jalur yang
lebih mungkin berhasil (butuh label baru, bukan reweight data lama).**

### Q1. ✅ SELESAI (2026-07-21) — Tutup gap dataset statis BUMI/DEWA
**JANGAN DIKERJAKAN ULANG.** Sudah diselesaikan (kemungkinan oleh instance Codex sebelumnya, terdeteksi
lewat `git diff` — kualitasnya sudah dicek & konsisten dengan konvensi proyek):
`RetrainVolatilePredictionModelsCommand.php` sekarang memanggil `quant/run_special_volatile_stock_research.py`
(via `runDatasetRefreshProcess()`, env-overridable `PREDICTION_VOLATILE_DATASET_SCRIPT`) sebelum training
kalau ada varian yang akan retrain — gagal refresh = batal sebelum sentuh artefak produksi. Test baru di
`RetrainVolatilePredictionModelsCommandTest.php` (6 test dataset-refresh). Real run terverifikasi: BUMI
2744 rows s/d 2026-07-21, DEWA 2669 rows s/d 2026-07-21, 3 model dipromosikan gating. **Full suite 428
passed.** Detail lengkap di `plan.md` Fase Q1. **File ini masih UNCOMMITTED di working tree per 2026-07-21
malam** — cek `git status` dulu, kalau masih ada, commit selektif (jangan `git add -A`) sebelum lanjut
item lain, supaya tidak tertimpa/hilang.

### Q2. ✅ SELESAI DENGAN TEMUAN NEGATIF (2026-07-22) — Perluas label manual kelas positif
**JANGAN DIKERJAKAN ULANG.** Infrastruktur active-learning dibangun (UI klik cepat di
`/sentiment-validation/active-learning`, bukan CSV manual — lihat Fase Q2-prep/Q2-ui di `plan.md`).
Label manual naik 801→988 (positive 207→307). Retrain dari checkpoint mentah dengan label baru
**KALAH JAUH** dari produksi v1 di test split baru (candidate macro-F1 0.674 vs v1 0.893). Candidate
**tidak dipromosikan**. Kemungkinan besar: banyak label baru adalah kasus yang v1 sudah benar,
sehingga retrain ulang tidak memberi bukti perbaikan OOS. Detail: `plan.md` Fase Q2. Kalau mau lanjut
jalur ini lagi, perlu strategi retrain berbeda (fine-tune dari checkpoint v1, bukan dari nol) —
diskusikan dengan user dulu, jangan asumsikan otomatis worth mencoba lagi.

### Q3. ✅ SELESAI (2026-07-22) — `return_5d_cross_section_rank` diperbaiki di live inference
**JANGAN DIKERJAKAN ULANG.** `ResearchPredictionFeatureService` sekarang menghitung rank asli
(bukan null lagi), cache sekali per instance dari `return_5d` saja (hindari OOM). Verifikasi real:
BBCA 2026-07-21 `return_5d_cross_section_rank=0.545455`. Test baru
`tests/Feature/ResearchPredictionFeatureServiceTest.php`. Detail: `plan.md` Fase Q3.

### Q4. ✅ SELESAI (2026-07-22) — Keputusan git untuk file data yang diregenerasi mingguan
**JANGAN DIKERJAKAN ULANG.** Keputusan: `git rm --cached` untuk `data/stocks/*.csv`, `data/IHSG.csv`,
`output/prediction_research/dataset_v6a.csv`/`dataset_v6b_10ticker.csv`/`dataset_bumi_special.csv`/
`dataset_dewa_special.csv` + entri `.gitignore` baru. File LOKAL tidak dihapus, cuma berhenti
ter-track — jadi refresh mingguan tidak lagi bikin diff besar di git. Clone baru harus jalankan
`prediction:refresh-price-history` + `prediction:export-research-dataset` dulu sebelum retrain
penuh. Detail: `plan.md` Fase Q4.

### Q5. ✅ SELESAI (2026-07-22) — Bersihkan log MySQL 1.3GB
**JANGAN DIKERJAKAN ULANG.** User menjalankan command truncate manual di Terminal lokal. Verifikasi:
semua file `.err` sekarang 0B (kecuali log aktif, 712B — wajar, baru mulai lagi), turun dari ~1.4GB.
Tidak ada file DB/data yang tersentuh. Detail: `plan.md` Fase Q5.

---

## 4b. Fase R1-R5b — ✅ SEMUA SELESAI (lihat §3 untuk ringkasan hasil final, JANGAN kerjakan ulang)

Konten di bawah ini adalah rencana ASLI (ditulis sebelum eksekusi) — dipertahankan sebagai referensi
konteks/rasional keputusan, BUKAN instruksi aktif lagi. Hasil aktual (termasuk koreksi gate R5b) ada
di §3 dan `plan.md` Fase R1-R5b. Untuk kerja SELANJUTNYA terkait sentimen, baca **§4c "Fase R6-R7"**
di bawah, bukan bagian ini.

Setelah Fase P (class-weighted retrain) dan
Q2 (active-learning label) sama-sama GAGAL menaikkan performa produksi, investigasi lanjutan
menemukan akar masalah: seluruh 988 label manual yang ada (801 asli + 207 Q2) **bukan sampel acak**
— semuanya berasal dari kasus disagreement/ambigu, bukan representasi populasi berita asli.

Perbandingan (sudah diverifikasi langsung ke DB, bukan asumsi):

| | Populasi asli (1.884 artikel) | Label training (988) |
|---|---|---|
| Neutral | 77.3% | 62.4% |
| Positive | 15.6% | 25.8% |
| Negative | 7.1% | 11.8% |

Model dilatih & diuji HANYA di dunia "sulit", bukan populasi nyata — kemungkinan besar ini penjelasan
kenapa P dan Q2 gagal (keduanya cuma memutar ulang data yang sama, bukan menyerang bias sampling-nya).

**Jebakan metodologis WAJIB dihindari**: test set representatif baru akan MENGHASILKAN macro-F1 lebih
tinggi dari test set hard-case lama (0.5816) — BUKAN karena model membaik, tapi karena populasinya
lebih mudah. Bukti: model v1 (tidak berubah) dapat macro-F1 0.8929 di test set Q2 vs 0.5816 di test
lama — populasi beda, bukan model beda. **Test set hard-case lama (120 baris) HARUS tetap jadi
benchmark utama untuk semua percobaan masa depan** — test set representatif baru adalah ANGKA KEDUA
yang terpisah, tidak pernah digabung/diklaim sebagai "kenaikan" dari 0.5816.

**Ekspektasi jujur**: kalau dikerjakan penuh dengan disiplin, realistis macro-F1 di test hard-case
lama naik ke ~0.62–0.68 (bukan 80%) — perbaikan bertahap dari mengurangi noise label + eksposur ke
pola representatif, bukan lompatan besar.

### File & pola yang WAJIB direuse (jangan tulis ulang)
- `app/Http/Controllers/SentimentValidationController.php` — sudah ada 2 mode (`index`/`next` untuk
  disagreement, `activeLearning`/`activeLearningNext` untuk Q2), keduanya reuse view yang sama
  `resources/views/sentiment-validation/index.blade.php`. Mode baru (R5a) ikuti pola persis ini.
- `app/Console/Commands/ExportSentimentFinetuneDatasetCommand.php` — sudah ada `stratifiedSplit()`
  dan `buildProductionInputText()`. Export test set baru (R5b) reuse fungsi ini, jangan tulis ulang.
- `quant/finetune_sentiment_model.py` — sudah ada opsi `--model-out-dir`/`--report-json`/
  `--report-txt` (dari Q2) untuk retrain candidate tanpa menyentuh produksi. Reuse di R5b.
- `app/Models/SentimentManualLabel.php` + migrasi `2026_07_07_000001_create_sentiment_manual_labels_table.php`
  — skema SAAT INI cuma `news_article_id`, `user_id`, `label`. TIDAK ADA kolom untuk membedakan
  sumber sampling — ini yang diperbaiki di R1.
- `app/Models/NewsArticle.php` — TIDAK punya kolom "jenis berita". `stock_id` nullable (null = artikel
  makro/global). Klasifikasi jenis berita (R3) harus jadi classifier ringan berbasis aturan, BUKAN
  kolom skema baru atau model ML baru.

### R1. Migrasi: tag sumber sampling label
Tambah kolom `sample_method` (string, nullable) ke `sentiment_manual_labels`. Backfill SEMUA 988
baris existing jadi `sample_method='legacy_hard_case'` (801 asli + 207 Q2 digabung, sama-sama
hard-case-biased, tidak perlu dibedakan lagi). `SentimentValidationController::store()` set
`sample_method` sesuai mode aktif untuk label baru ke depan. **Tidak ada retrain, tidak sentuh
produksi** — murni infrastruktur data. Test: migration up/down, backfill benar.

### R2. Audit label yang berpotensi salah/ambigu
Command baru `sentiment:audit-manual-labels` — bandingkan label manusia existing vs prediksi model
produksi v1 SAAT INI. Flag baris di mana v1 sangat yakin tapi beda dari label manusia (kandidat
re-review — entah label manusia salah, atau model punya blind spot sistematis, dua-duanya bernilai).
Output: report ke `output/prediction_research/sentiment_label_audit_report.{csv,txt}`, TIDAK
auto-koreksi apa pun (keputusan re-label tetap manusia). **Tidak retrain.**

### R3. Klasifikasi jenis berita (diagnostik, BUKAN fitur live/model prediksi harga)
Service ringan (mis. `App\Services\Sentiment\NewsArticleTypeClassifier`) — aturan: `stock_id` null →
`macro`; title/summary match keyword rekomendasi ("rekomendasi", "top pick", multi-ticker) →
`multi_emiten_recommendation`; selain itu → `emiten_spesifik`. SEKADAR lensa analisis untuk R2/R4,
TIDAK masuk `ResearchPredictionFeatureService` atau fitur training model prediksi harga (beda
concern total — jangan campur). **Tidak retrain, tidak ubah pipeline prediksi.**

### R4. Guideline labeling
Dokumen `docs/sentiment_labeling_guideline.md` (bukan kode) — definisi jelas per kelas, aturan batas
ambigu, contoh NYATA per jenis berita (dari R3) diambil dari kasus yang di-flag R2 (bukan karangan).
Termasuk aturan untuk pola yang sudah diketahui menyesatkan (listicle rekomendasi saham, PR/CSR,
berita institusional — didokumentasikan Fase B). **Tidak ada kode/retrain.**

### R5a. UI labeling sampel representatif (mirror pola Q2-ui, butuh keputusan user kapan mulai)
`SentimentValidationController::representativeSample()` + `representativeSampleNext()` — query
artikel belum dilabel, **random murni tanpa filter bias** (beda dari `activeLearningQuery()` yang
sengaja condong positif). Route baru `/sentiment-validation/representative` (+`/next`), reuse view
yang sama. `store()` set `sample_method='representative_random'`. Target: tidak wajib, sarankan
~150-200 label untuk test set kedua yang bermakna statistik, dikerjakan bertahap. **Tanya user dulu
kapan siap mulai — jangan asumsikan otomatis mulai setelah R1-R4 selesai.**

### R5b. Export test set terkunci + retrain & evaluasi ganda (JEDA MANUSIA — jangan lanjut otomatis dari R5a)
**JANGAN MULAI sampai user eksplisit konfirmasi label representatif sudah terkumpul cukup** — ini
judgment call manusia, bukan sesuatu yang bisa dicek otomatis. Kalau sudah dikonfirmasi: tambah
filter `--sample-method=` ke `sentiment:export-finetune-dataset` untuk export test set representatif
terkunci. Retrain gabung SEMUA label untuk TRAIN, tapi **evaluasi terpisah di 2 test set** (hard-case
lama 120 baris + representatif baru), laporkan KEDUA angka terpisah dengan jelas artinya apa. Gate:
**harus TIDAK memburuk di test hard-case lama** (vs 0.5816, ambang sama seperti Fase P). Simpan
candidate terpisah, JANGAN timpa produksi sebelum lolos gate. Dokumentasikan Fase R5 di `plan.md`
apa pun hasilnya — kalau gagal lagi, itu tetap temuan sah untuk skripsi.

### Verifikasi Fase R
`php artisan test` tetap hijau (baseline 431) di tiap R1-R4. R1: cek 988 baris existing punya
`sample_method='legacy_hard_case'`. R2: spot check manual beberapa baris hasil flag. R3: unit test
classifier dengan judul artikel real dari DB. R5a: buka `/sentiment-validation/representative` di
browser, cek artikel random (bukan condong satu label), cek `sample_method` tersimpan benar. R5b:
2 angka macro-F1 terpisah jelas, gate ketat terhadap 0.5816, produksi v1 tidak tersentuh sebelum lolos.

---

## 4c. Fase R6-R7 — RENCANA (belum dieksekusi), benahi fondasi evaluasi lalu ablation input konteks

**Baca dulu sebelum kerja sentimen apa pun berikutnya, termasuk sebelum melanjutkan ke pertanyaan
"kenapa akurasi cuma 58%".** Investigasi 2026-07-22 malam menemukan audit evaluasi independen lain
yang SUDAH BERJALAN paralel (kemungkinan sesi Codex/tool lain), semua uncommitted di working tree:
`docs/sentiment_evaluation_contract.md`, `docs/sentiment_project_context.md`,
`config/sentiment_evaluation.php`, `scripts/*.py` (5 script), `data/evaluation/`, `reports/*.json`
(~25 file). **Cek `git status` dulu — kalau file-file ini masih ada, itu bukan sampah, itu kerjaan
orang lain yang belum di-commit. Jangan hapus/timpa tanpa baca isinya dulu.**

### Temuan kunci dari audit yang sudah ada (dibaca langsung isinya, bukan asumsi)
1. `reports/evaluation_contract_audit.json` → **`"status": "likely_contaminated"`**. File test aktif
   (`storage/app/sentiment_finetune/test.jsonl`, 148 baris, dipakai berulang di Q2/R5b) punya **14
   overlap exact + 13 near-duplicate + 2 label conflict** dengan train/validation aktif — sebagian isi
   test SUDAH BOCOR ke train. Beda dari bug R5b yang sudah diperbaiki (file tertimpa) — ini kontaminasi
   silang DI DALAM file yang sama saat ini.
2. Angka **`0.5816` cuma "historical_reference"** — dihitung di split 120-baris yang sudah tidak ada
   lagi fisiknya. Konsisten dengan temuan kita sendiri di insiden R5b, sekarang dikonfirmasi independen.
3. **Sudah ada 3 kandidat official test set dibangun** (`scripts/build_official_evaluation_split.py`)
   tapi **SEMUA gagal gate** (`exact_leak==0 and crossing==0 and unresolved==0 and min_support>=5 and
   prev==0`) karena script itu jalan **tanpa akses DB penuh** ("DB unavailable during generation...
   fallback inventory") — field source/entity/date tidak lengkap, deteksi duplikat kemungkinan tidak
   akurat.
4. **Ground truth belum "attested"** — audit bilang struktur data membuktikan label dari
   `sentiment_manual_labels` (bukan turunan ML/rule), tapi butuh pernyataan eksplisit pemilik data
   bahwa labeling-nya independen. User SUDAH konfirmasi ini verbal di sesi Claude — tinggal diformalkan
   tertulis (R6b).
5. Tooling untuk beresin semua ini **sudah ada, tinggal dijalankan ulang dengan benar**:
   `scripts/audit_evaluation_contract.py`, `build_official_evaluation_split.py`,
   `verify_evaluation_contract.py`, `build_sentiment_groups.py`, `build_sentiment_source_inventory.py`.

### Kenapa urutan diubah dari rencana ablation awal
Menjalankan ablation input-konteks (title/summary/full_text/entity) di atas test set yang berstatus
"likely_contaminated" menghasilkan angka yang tidak bisa dipercaya — persis kesalahan yang sama seperti
insiden R5b yang baru diperbaiki. **R6 WAJIB selesai dengan official test yang lolos gate dulu, baru
R7 (ablation) boleh jalan.**

### R6a. Jalankan ulang audit & pembangunan official test set DENGAN akses DB penuh
Jalankan ulang `scripts/build_sentiment_source_inventory.py`, `build_sentiment_groups.py`, lalu
`build_official_evaluation_split.py` dengan koneksi DB live (bukan fallback inventory) — cek apakah
kandidat sekarang lolos gate. Kalau masih ada duplikat/konflik nyata: lihat
`reports/evaluation_near_duplicates.csv`, `evaluation_label_conflicts.csv`,
`mixed_label_group_root_cause.csv` untuk detail. **Tidak boleh mengubah label siapa pun otomatis** —
konflik di-exclude dari kandidat, dicatat, keputusan re-label tetap ke user.

### R6b. Formalkan ground-truth attestation
Tambahkan bagian di `docs/sentiment_evaluation_contract.md` (dokumen yang sudah ada) mengutip
konfirmasi user: label manual independen lewat `SentimentValidationController::store()`, skor ML/rule
cuma info sampling. Bukan klaim baru, cuma formalisasi.

### R6c. Kunci official test set yang lolos gate
Kalau R6a berhasil: kunci dengan pola SAMA seperti R5b (checksum SHA256, direktori terpisah, **commit
ke git, JANGAN gitignore**). Evaluasi ulang produksi `indobert_finetuned_v1` di official test baru ini
— angka INI jadi acuan resmi baru menggantikan `0.5816`. Update status kontrak di
`docs/sentiment_evaluation_contract.md` dari `draft` → `locked`/`official`.
**Kalau R6a TIDAK menghasilkan kandidat yang lolos gate walau dengan DB penuh — STOP, laporkan ke
user akar masalahnya, JANGAN paksa lanjut ke R7 di atas fondasi rapuh.**

### R7. Ablation input konteks (baru mulai setelah R6c selesai dengan official test lolos gate)
Base checkpoint tetap `w11wo/indonesian-roberta-base-sentiment-classifier` (bukan variabel di sini).
- **R7a** — investigasi kenapa `full_text` kosong di 94.6% artikel (dicek: cuma `ojk_rss`/`unknown`
  terisi; `google_news_rss`, sumber terbesar 1.316/1.888 artikel, 0% terisi). Cek
  `app/Console/Commands/ResolveGoogleNewsUrlsCommand.php` (**sudah ada, uncommitted** — resolve URL
  redirect Google News ke publisher asli, prasyarat scraping). **Diskusikan kelayakan dengan user
  dulu sebelum bangun scraper baru** — effort besar, bukan quick win.
- **R7b** — ablation title-only vs title+summary (pakai seluruh pool label, tidak perlu full_text).
  Retrain 2 varian candidate terpisah, evaluasi KEDUANYA di official test dari R6c.
- **R7c** — ablation entity injection (prefix teks dengan nama emiten/ticker) — murah dicoba, relevan
  untuk artikel `multi_emiten_recommendation` (`NewsArticleTypeClassifier`, R3).
- **R7d** — ablation full_text (HANYA kalau R7a simpulkan layak & datanya sudah bertambah) — sampel
  kecil (~102 awal), catat keterbatasan ukuran sampel.
- Semua hasil R7: delta macro-F1 vs produksi, **diukur di official test yang SAMA (R6c)** — cek SHA256
  sama di semua laporan perbandingan, jangan ulangi kesalahan file-berbeda seperti insiden R5b.

### Aturan khusus R6-R7
- R6a aman dikerjakan langsung (audit ulang, tidak ada retrain/perubahan produksi).
- R6c aman otomatis KALAU gate lolos — kalau gate gagal, WAJIB berhenti & lapor, jangan improvisasi
  kriteria gate sendiri.
- R7a WAJIB didiskusikan dengan user dulu (keputusan effort besar).
- R7b/R7c boleh otomatis setelah R6c selesai (retrain candidate + evaluasi, tidak timpa produksi).
- File uncommitted yang sudah ada (`ResolveGoogleNewsUrlsCommand.php`,
  `GoogleNewsRssFetcher.php` yang modified) — cek isinya dulu, kemungkinan kerjaan Codex sesi lain
  yang belum selesai/dites, jangan ditimpa/dihapus tanpa tanya user.

### Verifikasi R6-R7
`php artisan test` tetap hijau (baseline 436). R6a: laporan gate baru menunjukkan minimal 1 kandidat
`quality_gate_pass=true`, atau alasan jelas kenapa masih gagal. R6c: checksum SHA256 tervalidasi, file
ter-commit (bukan gitignored), evaluasi produksi di official test baru menghasilkan angka acuan baru.
R7b/c/d: delta macro-F1 vs produksi, file test SAMA (cek SHA256) di semua laporan. Semua fase
didokumentasikan terpisah di `plan.md` (format: Konteks → Perubahan → Verifikasi → Status).

---

## 5. SUDAH FINAL — jangan dibuka ulang / diusulkan lagi

- **LaunchDaemon auto-start MySQL: DITOLAK** (Fase E). MySQL tetap manual. Auto-recovery gap berita
  sudah menutup celahnya. Jangan usulkan lagi kecuali user yang mengangkat.
- **Redesign bobot komposit DSS (Opsi A): DITOLAK** (Fase I). Risiko data-snooping tinggi. Status DSS
  sekarang berbasis model ML tervalidasi — itu keputusan final.
- **Kontribusi sentimen → akurasi harga = NOL** (Fase A & C, diuji 2×). Batasan struktural coverage
  berita (berita ~2024+, harga 2001+). Bukan target perbaikan model lagi. Untuk skripsi: framing yang
  benar = "kualitas sentimen berhasil ditingkatkan independen, tapi kontribusi prediktifnya dibatasi coverage".
- **MySQL keputusan FINAL tetap manual.**

---

## 6. Protokol verifikasi & commit (jalankan tiap selesai 1 item)

1. `php artisan test` — HARUS tetap hijau (baseline 427). Kalau turun, ada regresi — perbaiki dulu.
2. Untuk perubahan Python: syntax check + smoke test kecil sebelum full run mahal.
3. Untuk perubahan yang observable di UI: verifikasi via browser (`/analytics?code=BBCA`) kalau relevan.
4. Untuk retrain: 1× real run manual (`--force`), cek metadata (`date_end`, `retrain_evaluation`,
   decision) masuk akal, cek `retrain_history.jsonl` + tabel "Status Retrain Model" di `/analytics`.
5. Dokumentasikan sebagai fase baru di `plan.md` (ikuti format fase sebelumnya: Konteks → Perubahan
   kode → Verifikasi → Status). Sertakan temuan negatif kalau ada.
6. Commit selektif (per nama file, cek `git diff`). Jangan push kecuali user minta.

---

## 7. Menjaga laporan "Status Sentimena" tetap update (DIVISION OF LABOR)

- **Laporan artifact "Status Sentimena"** (di claude.ai) hanya bisa diupdate oleh **Claude** (fitur
  Claude Code), BUKAN Codex. URL: `https://claude.ai/code/artifact/79ad68ac-a4c5-4376-9231-30077cdbc01d`.
- **Alur:** Codex kerjakan item + update `plan.md` + kabari user angka final. User bawa hasil itu balik
  ke sesi Claude → Claude update artifact. Jadi tugas Codex soal pelaporan = **update `plan.md` dengan
  angka final yang jelas & jujur**, itu yang jadi sumber untuk artifact.
- Metrik yang perlu diupdate ke artifact kalau berubah: baris sentimen ML (kalau Fase P promote),
  status BUMI/DEWA retrain (kalau Q1 selesai), plus fase baru di log.

---

## LAMPIRAN: Prompt siap-tempel untuk Codex CLI

```
Kamu bekerja di repo Laravel+Python "Sentimena" (skripsi analisis sentimen & prediksi saham IDX)
di /Applications/XAMPP/xamppfiles/htdocs/Implementasi AnalisisSentimenBerita/laravel-app.

WAJIB PERTAMA: baca CODEX_HANDOFF.md sampai habis, lalu CLAUDE.md, lalu plan.md (log fase). Itu
kontrak kerja & metodologi proyek — bukan opsional.

Aturan mutlak (ada detail di CODEX_HANDOFF.md §2):
- Tidak ada klaim metrik tanpa validasi OOS yang benar (walk-forward untuk model, held-out val/test
  untuk klasifikasi; seleksi di val, ukur test sekali). Anti data-snooping.
- Temuan negatif WAJIB dicatat jujur di plan.md.
- Jangan timpa model/artefak produksi sebelum lolos gate (degradasi macro-F1 0.05 → simpan candidate).
- Git selektif per-file, cek diff, JANGAN `git add -A`, JANGAN push kecuali aku minta.
- Jangan buka ulang keputusan final di §5 (LaunchDaemon MySQL, redesign bobot DSS, MySQL manual).

SEMUA item Fase 0-P, Q1-Q5, R1-R5b SUDAH SELESAI per 2026-07-22 malam -- JANGAN DIKERJAKAN ULANG,
JANGAN retrain/regenerasi apa pun dari fase-fase itu. (R5b sempat punya bug gate yang sudah
DIKOREKSI -- lihat §3, hasil final gate R5b = FAILED, candidate tidak dipromosikan.)

LANGKAH PERTAMA sebelum kerja apa pun: jalankan `git status -sb`. Kalau ada commit yang belum
di-push, JANGAN push tanpa diminta eksplisit. Kalau ada perubahan uncommitted -- **khususnya
`docs/sentiment_evaluation_contract.md`, `docs/sentiment_project_context.md`,
`config/sentiment_evaluation.php`, `scripts/*.py`, `data/evaluation/`, `reports/*.json`, atau
`app/Console/Commands/ResolveGoogleNewsUrlsCommand.php`** -- itu BUKAN sampah, itu hasil audit
independen lain yang belum di-commit. Baca isinya (ringkasan ada di §4c), jangan hapus/timpa.

Tugas berikutnya: **Fase R6-R7** (baca CODEX_HANDOFF.md §4c LENGKAP sebelum mulai -- rencana detail,
BELUM ada implementasi baru). Ringkas: audit independen menemukan file test aktif yang dipakai
berulang (Q2, R5b) berstatus **"likely_contaminated"** (14 overlap exact + 13 near-duplicate + 2
label conflict dengan train/validation). Angka 0.5816 cuma referensi historis, tidak bisa
direproduksi di file manapun yang ada sekarang. **R6 (benahi fondasi evaluasi -- bangun official
test set yang benar-benar bersih & terkunci) WAJIB selesai dulu sebelum R7 (ablation cari tahu
kenapa akurasi mentok di 58%, title/summary/full-text/entity) boleh mulai.**

ATURAN KHUSUS R6-R7 (selain aturan umum §2):
- R6a (audit ulang dengan DB penuh) aman dikerjakan langsung, tidak ada retrain.
- R6c (kunci official test) aman otomatis KALAU gate lolos (`exact_leak==0 and crossing==0 and
  unresolved==0 and min_support>=5 and prev==0`) -- kalau gate GAGAL walau dengan DB penuh, WAJIB
  STOP dan lapor ke user, JANGAN improvisasi kriteria gate sendiri atau paksa lanjut ke R7.
- R7a (scraping full_text) WAJIB didiskusikan dengan user dulu -- effort besar, bukan quick win.
- R7b/R7c boleh otomatis setelah R6c selesai, tapi WAJIB evaluasi di official test yang SAMA (cek
  SHA256 sama di semua laporan) -- jangan ulangi kesalahan file-berbeda seperti insiden R5b.

Kerjakan satu sub-fase per giliran: investigasi dulu (baca file terkait) → konfirmasi rencana kalau
ada keputusan besar → eksekusi → verifikasi (`php artisan test` tetap ≥436 hijau) → dokumentasikan
sebagai fase terpisah di plan.md (format: Konteks → Perubahan kode → Verifikasi → Status, termasuk
temuan negatif kalau ada) → commit selektif per file, JANGAN `git add -A`, JANGAN push kecuali
diminta. Jangan buka ulang keputusan final di §5.
```
