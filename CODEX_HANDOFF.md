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

## 3. State sekarang (per 2026-07-22, seluruh antrian Q1–Q5 tuntas)

**SEMUA ITEM DI §4 SUDAH SELESAI** kecuali eksekusi manual `sudo` di Q5 (butuh user, agent tidak
punya password). Kalau ada pekerjaan baru, itu akan jadi Fase R+ — jangan asumsikan ada kerja lanjutan
tersirat dari dokumen ini, tanya user dulu apa yang mereka mau berikutnya.

**Selesai:** Fase 0, A–P, Q1–Q5 (lihat `plan.md` untuk detail tiap fase). Ringkas metrik kunci:
sentimen ML 35.6%→58.16% (B), tie-break 32.69%→55.77% (C), engine prediksi 33.3%→39.6% (G),
status DSS pindah ke model tervalidasi (F→I), fundamental live mingguan (K), Trading Signal "VALID"
dibuang (L), retrain V6A/V6B otomatis (N), staleness data harga + IHSG ditutup (O), dataset khusus
BUMI/DEWA diregenerasi tiap retrain (Q1), eksperimen class-weighted sentimen dievaluasi tuntas — NO
IMPROVEMENT (P), active-learning label positif 801→988 tapi candidate kalah dari produksi — TIDAK
dipromosikan (Q2), `return_5d_cross_section_rank` diperbaiki nyata di live inference (Q3), file data
regeneratif besar di-untrack dari git (`git rm --cached`, bukan dihapus) (Q4), log MySQL 1.3GB
**menunggu user jalankan command sudo manual** (Q5, lihat item Q5 di §4). **431 test hijau.**
Commit terakhir `c22dd20`, **6 commit ahead dari origin/main, belum di-push** per 2026-07-22 — cek
`git status -sb` dan tanya user sebelum push.

**Fase P — hasil final (NO IMPROVEMENT, model produksi TIDAK diganti):** skema `sqrt_inverse` menang
di validation (val macro-F1 0.7564) tapi mean test macro-F1 3-seed = **0.5552** vs produksi **0.5816**
(margin -0.0264, di dalam std 0.0262 → gagal gate). Detail: class weighting menaikkan F1 positive
sedikit (0.377→0.386) TAPI menjatuhkan F1 negative jauh lebih besar (0.621→0.545) — memindahkan
masalah, bukan menyelesaikannya. Produksi `indobert_finetuned_v1` tidak disentuh. Kandidat tersimpan
di `storage/app/sentiment_model/indobert_finetuned_v2_weighted/` sebagai referensi, tidak dipakai
serving. **Ini temuan negatif yang valid untuk skripsi** — bukan kegagalan eksekusi.

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

### Q5. ⏳ TERTUNDA MANUAL (perlu USER, bukan agent) — Bersihkan log MySQL 1.3GB
Agent TIDAK bisa menyelesaikan ini — file `.err` dimiliki `_mysql`, butuh `sudo` dengan password
interaktif yang agent tidak punya. **User perlu jalankan sendiri di Terminal lokal:**
```bash
sudo sh -c 'for f in /Applications/XAMPP/xamppfiles/var/mysql/*.err; do : > "$f"; done'
```
Verifikasi: `ls -lh /Applications/XAMPP/xamppfiles/var/mysql/*.err` (harus mengecil ke ~0). Aman —
cuma mengosongkan log error, bukan data DB, tidak menyentuh MySQL yang sedang jalan. Detail:
`plan.md` Fase Q5.

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

SEMUA item di CODEX_HANDOFF.md §4 (P, Q1-Q4) SUDAH SELESAI per 2026-07-22 -- JANGAN DIKERJAKAN
ULANG, JANGAN retrain/regenerasi apa pun dari item-item itu. Q5 (bersihkan log MySQL) TERTUNDA
tapi butuh sudo password interaktif yang cuma user punya -- kalau user belum konfirmasi sudah
dijalankan, cukup ingatkan command-nya (ada di §4 item Q5), jangan coba jalankan sendiri.

LANGKAH PERTAMA sebelum kerja apa pun: jalankan `git status -sb`. Kalau ada commit yang belum
di-push, JANGAN push tanpa diminta eksplisit. Kalau ada perubahan uncommitted, tanya user dulu
apa itu sebelum menimpa/menghapus apa pun.

Tugas berikutnya BELUM ditentukan -- dokumen ini adalah log kerja yang sudah selesai, bukan antrian
aktif. TANYA USER apa yang mereka mau kerjakan selanjutnya sebelum memulai investigasi/kode apa pun.
Kalau user memberi task baru, ikuti pola yang sama seperti fase-fase sebelumnya di plan.md:
investigasi dulu (baca file terkait) → konfirmasi rencana kalau ada keputusan besar (promosi model,
hapus data, sudo, effort besar) → eksekusi → verifikasi (`php artisan test` harus tetap ≥431 hijau)
→ dokumentasikan sebagai fase baru di plan.md (§Fase R+, ikuti format: Konteks → Perubahan kode →
Verifikasi → Status, termasuk temuan negatif kalau ada) → commit selektif per file, JANGAN
`git add -A`, JANGAN push kecuali diminta. Jangan buka ulang keputusan final di §5.
```
