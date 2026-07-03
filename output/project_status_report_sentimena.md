# Laporan Status Proyek Sentimena — Fokus Analisis BUMI & DEWA

Tanggal penyusunan: 22 Juni 2026. Laporan ini disusun dari metadata model, output riset, source code serving/retrain, dan retrain history yang sudah ada. Tidak ada training, backtest, atau API eksternal yang dijalankan untuk menyusun laporan ini.

## 1. Ringkasan Eksekutif

- Sistem prediksi Sentimena saat ini memiliki lima model production di FastAPI: V6A technical, V6B technical+sentiment, BUMI technical, DEWA regime, dan DEWA technical.
- BUMI dan DEWA dipisahkan dari model 10 ticker resmi karena karakter volatilitasnya berbeda tajam. Audit sebelumnya mencatat DEWA memiliki volatilitas harian sekitar 8,3x BBCA dan 5,08x rata-rata 10 ticker resmi; BUMI sekitar 3,2x BBCA dan 1,96x rata-rata 10 ticker resmi.
- Model V6A/V6B general untuk 10 ticker blue-chip tidak cocok untuk BUMI/DEWA. Backtest awal menunjukkan performa sangat buruk, awalnya sampai 0/10 benar dengan korelasi negatif; setelah canonical price layer memperbaiki duplikasi harga, hasil masih lemah sekitar 1/10 benar dengan korelasi negatif untuk DEWA dan BUMI.
- Hasil production saat ini: BUMI memakai random forest threshold 2,7%; DEWA memiliki dua output terpisah, yaitu deteksi rezim move/no_move dan prediksi arah ATR 0,5 berbasis gradient boosting.
- Sistem sudah memiliki retrain otomatis mingguan dan history JSONL sebagai bukti operasional. Mekanisme retrain memakai candidate gating agar model baru yang turun macro F1 lebih dari 0,05 tidak langsung mengganti model production.

## 2. Inventaris Model Production Saat Ini

| Model | Algoritma | Cakupan | Training terakhir | Metrik performa | Fitur utama | Limitasi/catatan |
|---|---|---|---|---|---|---|
| V6A Technical | random_forest | 10 ticker resmi | 2026-06-21T10:01:30.826837+07:00 | macro F1 0.3673, directional accuracy 0.4050 | return_1d, return_3d, return_5d, return_20d, atr14_pct, atr_ratio, volume_ratio_5d, volume_ratio_20d, ... (15 fitur total) | return_5d_cross_section_rank: known_limited_live_serving — Live ResearchPredictionFeatureService currently emits this key as null; training and serving rely on the same SimpleImputer(strategy='median') behavior used in V6 walk-forward research. |
| V6B Technical + Sentiment | logistic_regression | 10 ticker resmi | 2026-06-21T10:01:31.942866+07:00 | V6B contribution study; metrics referenced in model_comparison_v6b, not claimed as final full-data production metric | return_1d, return_3d, return_5d, return_20d, atr14_pct, atr_ratio, volume_ratio_5d, volume_ratio_20d, ... (21 fitur total) | return_5d_cross_section_rank: known_limited_live_serving — Live ResearchPredictionFeatureService currently emits this key as null; training and serving rely on the same SimpleImputer(strategy='median') behavior used in V6 walk-forward research. |
| BUMI Technical | random_forest | BUMI | 2026-06-22T10:01:49.427077+07:00 | macro F1 0.3742, directional accuracy 0.4216 | return_1d, return_3d, return_5d, return_20d, atr14_pct, atr_ratio, volume_ratio_5d, volume_ratio_20d, ... (15 fitur total) | - |
| DEWA Regime | logistic_regression | DEWA | 2026-06-22T10:01:53.149823+07:00 | macro F1 0.5751, directional accuracy 0.8532 | return_1d, return_3d, return_5d, return_20d, atr14_pct, atr_ratio, volume_ratio_5d, volume_ratio_20d, ... (15 fitur total) | Model mendeteksi rezim move/no_move, bukan arah up/down/flat. |
| DEWA Technical | gradient_boosting | DEWA | 2026-06-22T10:01:58.037255+07:00 | macro F1 0.4102, directional accuracy 0.5050 | return_1d, return_3d, return_5d, return_20d, atr14_pct, atr_ratio, volume_ratio_5d, volume_ratio_20d, ... (15 fitur total) | Upgrade reason: GB menang vs LR production dan RF160 pada sample identik; macro F1 +0.0838, dir acc +0.0983 |

Catatan penting: metric pada metadata adalah referensi performa walk-forward riset, bukan klaim bahwa artifact final yang dilatih ulang pada seluruh data memiliki performa identik. Metadata V6B secara khusus mencatat basis kontribusi sentimen, bukan klaim metrik full-data production.

## 3. Perjalanan Riset BUMI & DEWA

### 3.1 Alasan BUMI dan DEWA Dipilih

BUMI dan DEWA dipilih sebagai objek khusus karena keduanya mewakili saham berkarakter volatil dan volume trading besar. Secara kuantitatif, DEWA tercatat jauh lebih ekstrem: volatilitas harian sekitar 8,3x BBCA dan 5,08x rata-rata 10 ticker resmi. Selain itu, sekitar 57% future return 5D DEWA bernilai tepat nol, menunjukkan pola stale price/tidak bergerak yang panjang, diselingi lonjakan besar. BUMI juga lebih volatil dari blue-chip, sekitar 3,2x BBCA dan 1,96x rata-rata 10 ticker resmi, tetapi distribusinya lebih konvensional dibanding DEWA.

### 3.2 Mengapa V6A/V6B Tidak Cocok

V6A/V6B dikembangkan untuk 10 ticker resmi yang lebih blue-chip dan stabil. V6A baseline resmi memakai horizon 5D, threshold 1,5%, random forest, macro F1 0,3673 dan directional accuracy 0,4050. Ketika diterapkan ke BUMI/DEWA, model general tidak menangani karakter return ekstrem/stale dengan baik. Audit/backtest awal menunjukkan akurasi sangat buruk, termasuk 0/10 pada pengujian awal dan korelasi score-vs-return negatif. Setelah canonical price layer memperbaiki duplikasi dan scale mismatch harga di `stock_prices`, return palsu ekstrem hilang, tetapi model general tetap tidak cocok: DEWA sekitar 1/10 benar dengan korelasi -0,435 dan BUMI sekitar 1/10 benar dengan korelasi -0,275 pada uji awal pasca-mitigasi.

### 3.3 Pendekatan BUMI

- Threshold label disesuaikan dari 1,5% menjadi 2,7% agar distribusi down/flat/up lebih seimbang.
- Model special awal BUMI: random forest dengan macro F1 0,3742 dan directional accuracy 0,4216; menang kedua metrik terhadap majority class (macro F1 0,1541; directional accuracy 0,3036).
- Eksperimen v2 menambahkan fitur volatilitas dan ensemble. Soft voting ensemble mencapai macro F1 0,4040 dan directional accuracy 0,4395. Namun verifikasi subset fair menunjukkan margin terhadap RF160 production hanya +0,0062 macro F1 dan +0,0069 directional accuracy, di bawah threshold material 0,02. Karena itu BUMI tidak dipromosikan ke ensemble; production tetap random forest.

### 3.4 Pendekatan DEWA

- DEWA diperlakukan berbeda karena pola stale price sangat dominan. Eksperimen move/no_move 0,5% menjawab pertanyaan apakah harga akan bergerak signifikan, bukan arah pergerakan.
- DEWA regime move/no_move dengan logistic regression mencapai macro F1 0,5751 dan directional/regime accuracy 0,8532; menang kedua metrik dibanding majority dan random baseline. Model ini dipilih production sebagai deteksi rezim, bukan prediksi arah.
- DEWA directional ATR 0,5 awal memakai logistic regression, macro F1 0,3264 dan directional accuracy 0,4067. Ini hanya menang sebagian karena directional accuracy kalah dari majority class 0,5000.
- Eksperimen ATR 0,75 tidak dipilih. Pada baseline special, model terbaik justru random baseline dengan macro F1 0,2877 dan directional accuracy 0,5466; learned model tidak menang bersih.
- Eksperimen v2 menemukan bahwa gradient boosting pada fitur lama untuk DEWA ATR 0,5 mencapai macro F1 0,4102 dan directional accuracy 0,5050. Verifikasi menunjukkan GB mengalahkan LR production (0,3264/0,4067), RF160 (0,3212/0,3859), random baseline (0,2887/0,4415), dan majority class (0,2188/0,5000). Karena itu DEWA technical dipromosikan ke gradient boosting.

### 3.5 Model Production yang Dipilih

- BUMI: `model_bumi_technical`, random forest, label fixed threshold 2,7%. Dipilih karena menang kedua metrik terhadap baseline trivial, dan ensemble v2 tidak memberi margin fair yang cukup besar untuk mengganti production.
- DEWA Regime: `model_dewa_regime`, logistic regression, label move_vs_no_move 0,5%. Dipilih karena paling kuat untuk menjelaskan karakter stale/lonjakan DEWA.
- DEWA Technical: `model_dewa_technical`, gradient boosting, label ATR 0,5. Dipilih setelah verifikasi v2 karena menang vs LR production, RF160, majority, dan random baseline pada sample identik.

## 4. Tabel Perbandingan Komprehensif BUMI & DEWA

| Eksperimen | Pendekatan | Macro F1 | Directional Accuracy | vs Majority Class | Status akhir |
|---|---|---:|---:|---|---|
| bumi_fixed_2_7pct | BUMI fixed threshold 2.7%, random_forest | 0.3742 | 0.4216 | Menang kedua metrik | Production |
| dewa_move_0_5pct | DEWA move/no_move 0.5% | 0.5751 | 0.8532 | Menang kedua metrik | Production |
| dewa_atr0_5_h5d | DEWA ATR threshold, logistic_regression | 0.3264 | 0.4067 | Menang sebagian | Digantikan oleh GB production |
| dewa_atr0_75_h5d | DEWA ATR threshold, random_baseline | 0.2877 | 0.5466 | Menang sebagian | Ditolak |
| old_features_all_models / bumi_fixed_2_7pct | BUMI random_forest | 0.3758 | 0.4236 | Menang kedua metrik | Eksplorasi/ditolak |
| new_features_all_models / bumi_fixed_2_7pct | BUMI gradient_boosting | 0.4020 | 0.4325 | Menang kedua metrik | Eksplorasi/ditolak |
| new_features_with_ensemble / bumi_fixed_2_7pct | BUMI soft_voting_ensemble | 0.4040 | 0.4395 | Menang kedua metrik | Candidate; tidak dipromosikan |
| old_features_all_models / dewa_move_0_5pct | DEWA logistic_regression | 0.5751 | 0.8532 | Menang kedua metrik | Eksplorasi/ditolak |
| new_features_all_models / dewa_move_0_5pct | DEWA random_forest | 0.5613 | 0.8163 | Menang sebagian | Eksplorasi/ditolak |
| new_features_with_ensemble / dewa_move_0_5pct | DEWA soft_voting_ensemble | 0.5694 | 0.8322 | Menang kedua metrik | Eksplorasi/ditolak |
| old_features_all_models / dewa_atr0_5_h5d | DEWA gradient_boosting | 0.4102 | 0.5050 | Menang kedua metrik | Production |
| new_features_all_models / dewa_atr0_5_h5d | DEWA gradient_boosting | 0.3913 | 0.4807 | Menang kedua metrik | Eksplorasi/ditolak |
| new_features_with_ensemble / dewa_atr0_5_h5d | DEWA soft_voting_ensemble | 0.3978 | 0.4785 | Menang sebagian | Eksplorasi/ditolak |
| old_features_all_models / dewa_atr0_75_h5d | DEWA gradient_boosting | 0.3666 | 0.5655 | Menang sebagian | Eksplorasi/ditolak |
| new_features_all_models / dewa_atr0_75_h5d | DEWA gradient_boosting | 0.3941 | 0.5658 | Menang sebagian | Eksplorasi/ditolak |
| new_features_with_ensemble / dewa_atr0_75_h5d | DEWA gradient_boosting | 0.3941 | 0.5658 | Menang sebagian | Eksplorasi/ditolak |
| horizon_alternative_new_features_ensemble / bumi_h10_fixed_scaled | BUMI random_forest | 0.4195 | 0.4782 | Menang kedua metrik | Eksplorasi/ditolak |
| horizon_alternative_new_features_ensemble / dewa_atr0_5_h10d | DEWA logistic_regression | 0.4166 | 0.4660 | Menang kedua metrik | Eksplorasi/ditolak |

## 5. Status Sistem Live Saat Ini

### 5.1 FastAPI Serving

`quant/prediction_api.py` memuat lima model production aktif di `production_stores`:

1. `technical` — V6A technical random forest untuk 10 ticker resmi.
2. `technical_sentiment` — V6B technical+sentiment logistic regression untuk 10 ticker resmi.
3. `bumi_technical` — model directional khusus BUMI.
4. `dewa_regime` — model rezim move/no_move khusus DEWA.
5. `dewa_technical` — model directional ATR 0,5 khusus DEWA.

FastAPI juga memiliki validasi ticker-specific: `bumi_technical` hanya untuk BUMI, sedangkan `dewa_regime` dan `dewa_technical` hanya untuk DEWA. Respons `dewa_regime` memakai field `predicted_regime`, bukan `predicted_direction`, agar tidak menyesatkan sebagai prediksi arah.

### 5.2 Halaman/Endpoint yang Menampilkan Prediksi

- `/predictions`: halaman prediksi saham. Untuk 10 ticker resmi menampilkan V6A/V6B; untuk BUMI menampilkan BUMI technical; untuk DEWA menampilkan DEWA regime dan DEWA technical.
- `/api/predict`: endpoint API prediksi. Secara default masih pola V6A/V6B, dan dapat menerima `model_variant` spesifik.
- `/backtest`: halaman backtest DSS. Untuk BUMI/DEWA, service memakai model khusus per-saham dan threshold riset yang divalidasi. Untuk DEWA, halaman juga menampilkan section terpisah untuk regime move/no_move.
- `/backtest/all`: agregasi backtest semua saham, dengan canonical price layer di service backtest.

### 5.3 Retrain Otomatis

Command retrain: `php artisan prediction:retrain-volatile {--dry-run} {--force} {--model=...}`. Scheduler di `routes/console.php` menjalankan command ini setiap Minggu pukul 02:00 WIB, `withoutOverlapping`, `runInBackground`, dan log output ke `storage/logs/retrain-volatile.log`.

Mekanisme pengaman:

- Mengecek `trained_at` metadata model terhadap data harga canonical dan artikel terbaru.
- Skip bila tidak ada data baru dan tidak memakai `--force`.
- Training dilakukan ke folder candidate terlebih dahulu.
- Jika macro F1 turun lebih dari 0,05, candidate disimpan sebagai `_candidate` dan production tidak ditimpa.
- Jika sebanding/lebih baik, model lama dibackup ke `storage/app/prediction/archive/` dan production diganti.
- History dicatat di `storage/app/prediction/retrain_history.jsonl`.

### 5.4 Riwayat Retrain

Jumlah entry retrain history saat laporan dibuat: 9 baris JSONL.

Distribusi keputusan: skip=3, replace=3, promoted=3.

| Model | Timestamp terakhir | Decision terakhir | Trigger | Rows baru | Old F1 | New F1 |
|---|---|---|---|---:|---:|---:|
| bumi_technical | 2026-06-22T03:01:49+00:00 | promoted | forced | 1 | 0.3742 | 0.3742 |
| dewa_regime | 2026-06-22T03:01:53+00:00 | promoted | forced | 1 | 0.5751 | 0.5751 |
| dewa_technical | 2026-06-22T03:01:58+00:00 | promoted | forced | 0 | 0.4102 | 0.4102 |

## 6. Keterbatasan yang Harus Disebutkan Jujur

- Coverage sentimen BUMI/DEWA masih terbatas dan tidak setara dengan 10 ticker resmi yang mendapat backfill sentimen lebih sistematis. Karena itu model BUMI/DEWA production saat ini technical-only/regime technical, bukan sentiment-enhanced.
- DEWA directional tetap menantang. Walaupun gradient boosting ATR 0,5 sudah memperbaiki metrik, karakter DEWA masih didominasi stale price dan lonjakan ekstrem. Hasil live/backtest window terbaru dapat berfluktuasi dan tidak boleh diklaim sebagai sinyal trading pasti.
- `return_5d_cross_section_rank` masih known-limited di live serving: metadata V6A/V6B mencatat fitur ini dapat null di live dan ditangani oleh imputer median. Untuk BUMI/DEWA satu ticker, fitur cross-sectional juga secara konsep kurang kuat.
- Canonical price layer adalah mitigasi query agar duplicate/scale mismatch tidak merusak fitur live. Ini belum sama dengan cleanup permanen database; data duplikat lama masih perlu rencana cleanup terpisah bila ingin menegakkan unique constraint.
- Artifact model masih snapshot yang diretrain berkala, bukan truly real-time learning. Retrain mingguan membantu operasional, tetapi model tidak otomatis belajar setiap tick/hari secara instan.
- File artifact `.joblib` di `storage/app/prediction/` tidak masuk Git. Untuk pindah mesin/demo di laptop lain, artifact harus dicopy atau digenerate ulang.
- Hasil metrik adalah hasil walk-forward research. Artifact final dilatih pada seluruh data yang tersedia untuk production, sehingga metadata harus dibaca sebagai referensi penelitian, bukan jaminan performa masa depan.
- BUMI ensemble v2 tidak dipromosikan walaupun angka absolut lebih tinggi, karena setelah kontrol sample yang identik margin fair terhadap RF160 production hanya +0,0062 macro F1 dan +0,0069 directional accuracy.

## 7. Rekomendasi Pekerjaan Tersisa

### 7.1 Sudah Selesai dan Siap Dilaporkan

- Baseline resmi V6A untuk 10 ticker: horizon 5D, threshold 1,5%, random forest, macro F1 0,3673, directional accuracy 0,4050.
- V6B sentiment contribution sudah tersedia sebagai model pembanding technical+sentiment untuk 10 ticker resmi.
- BUMI/DEWA sudah dipisahkan sebagai riset saham volatil, dengan dataset dan laporan terpisah.
- BUMI production model: random forest threshold 2,7%.
- DEWA production model: regime move/no_move logistic regression dan directional ATR 0,5 gradient boosting.
- FastAPI dual/special serving sudah mendukung semua variant production.
- UI `/predictions` dan `/backtest` sudah membedakan model BUMI/DEWA dari model 10 ticker resmi.
- Retrain otomatis mingguan dan JSONL history sudah tersedia sebagai bukti sistem operasional.

### 7.2 Prioritas Tinggi Sebelum Sidang

- Jalankan smoke test end-to-end dengan MySQL dan FastAPI aktif tepat sebelum demo: `/predictions`, `/backtest?code=BUMI`, dan `/backtest?code=DEWA`.
- Pastikan artifact `.joblib` dan metadata ada di mesin demo; jika tidak, jalankan training script production ulang.
- Rapikan narasi BAB IV agar jelas membedakan prediksi arah, deteksi rezim, dan backtest DSS; jangan mencampur dengan klaim strategi trading/P&L.
- Siapkan screenshot/tabel dari `model_comparison_volatile_v2_verification.txt` untuk membuktikan alasan promosi DEWA gradient boosting.
- Pertimbangkan cleanup database `stock_prices` setelah approval, agar canonical layer tidak menjadi satu-satunya mitigasi jangka panjang.

### 7.3 Saran Penelitian Lanjutan BAB V

- Backfill sentimen khusus BUMI/DEWA agar dapat diuji apakah sentiment-enhanced model juga membantu saham volatil.
- Riset label khusus untuk saham tidak likuid/stale, misalnya model dua tahap: prediksi move/no_move terlebih dahulu, lalu prediksi arah hanya saat regime move.
- Pengembangan fitur microstructure sederhana: volume abnormal, bid-ask proxy, frekuensi transaksi, atau liquidity regime bila data tersedia.
- Eksperimen horizon lebih lanjut: BUMI 10D dan DEWA ATR 0,5 10D menunjukkan sinyal eksploratif yang menarik, tetapi belum dipromosikan.
- Cleanup data permanen dan unique constraint `(stock_id, trade_date, interval_type)` setelah seluruh duplikasi lama diselesaikan.

## 8. Kesimpulan

Proyek Sentimena sudah bergerak dari sistem prediksi berbasis heuristic manual menuju pipeline research-to-production yang lebih konsisten. Untuk 10 ticker resmi, V6A/V6B tetap menjadi baseline utama. Untuk BUMI dan DEWA, sistem kini memiliki model khusus yang disesuaikan dengan karakter saham volatil. Temuan terpenting secara akademik adalah bahwa satu model general tidak cukup untuk seluruh tipe saham: BUMI masih dapat dimodelkan dengan threshold directional yang disesuaikan, sedangkan DEWA lebih tepat dijelaskan melalui kombinasi deteksi rezim move/no_move dan model arah ATR-based yang lebih hati-hati. Seluruh hasil tetap dibingkai sebagai decision support, bukan rekomendasi investasi final.
