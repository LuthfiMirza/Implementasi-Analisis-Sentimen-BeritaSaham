# Guideline Labeling Sentimen Berita Saham

Tujuan dokumen ini: membuat label manusia konsisten untuk retrain/evaluasi sentimen. Label harus menilai dampak berita ke emiten/saham target, bukan nada bahasa umum.

## Label

### `positive`
Pakai saat berita cenderung menguntungkan emiten/saham target.

Contoh sinyal:
- laba, pendapatan, margin, ROE/ROA, atau kualitas aset membaik;
- dividen/buyback besar;
- kontrak baru, ekspansi sehat, target harga naik, rekomendasi beli;
- investor asing net buy/akumulasi pada saham target;
- regulasi/kebijakan jelas menguntungkan emiten target.

Contoh nyata dari audit R2:
- `Laba BCA tumbuh dobel digit, perbankan tetap defensif` → `positive` untuk BBCA bila isi mendukung laba/ketahanan bank.
- `Dividen Interim ADRO Jumbo Awal 2026, Yield Tembus 6%...` → `positive` untuk ADRO bila fokusnya dividen besar/yield menarik.
- `Di Tengah Badai Ekonomi, Indofood Tancap Gas! Laba Melonjak 24%...` → `positive` untuk INDF.

### `neutral`
Pakai saat dampak ke saham/emiten tidak jelas, campur, atau hanya informatif.

Contoh sinyal:
- agenda RUPS/perubahan manajemen tanpa dampak finansial jelas;
- artikel makro umum tanpa emiten target spesifik;
- rekomendasi/listicle banyak saham tanpa argumen jelas untuk target;
- berita campur: ada kekuatan fundamental, tapi ada tekanan laba/margin/risiko;
- aksi korporasi kecil yang belum jelas dampak untung/ruginya.

Contoh nyata dari audit R2:
- `Siaran Pers: OJK Sambut Positif Klasifikasi FTSE Russell...` → biasanya `neutral` untuk saham tertentu karena makro/regulator, bukan dampak emiten langsung.
- `Saham BBRI 2026: Potensi Cuan 40%, Dividen, dan Panduan Lengkap` → `neutral` bila berupa panduan/listicle umum tanpa sinyal berita baru yang spesifik.

### `negative`
Pakai saat berita cenderung merugikan emiten/saham target.

Contoh sinyal:
- laba turun/rugi, NPL naik, margin tertekan, biaya kredit naik;
- asing net sell besar pada saham target;
- harga saham turun tajam/terburuk relatif indeks;
- sanksi, gugatan, gagal bayar, suspensi, downgrade;
- target harga turun atau rekomendasi jual.

Contoh nyata dari sesi labeling Q2:
- `Investor Asing Lepas Saham BBRI Senilai Rp 198 Miliar...` → `negative` untuk BBRI.
- `Saham BUMI Kembali ke Titik Awal` → `negative` untuk BUMI karena pelemahan dan net sell asing.
- `IHSG Rebound, Tapi UNVR-AMRT Terburuk di LQ45` → `negative` untuk UNVR/AMRT, walaupun IHSG rebound.

## Jenis Berita

### `macro`
Artikel pasar/regulator/makro tanpa `stock_id`. Label berdasarkan dampak pasar umum. Jika tidak jelas ke emiten tertentu, pilih `neutral`.

### `emiten_spesifik`
Artikel fokus satu emiten. Label berdasarkan dampak ke emiten itu.

### `multi_emiten_recommendation`
Artikel rekomendasi/listicle banyak saham. Label target hanya jika sinyal untuk emiten target jelas. Kalau target hanya disebut dalam daftar tanpa argumen kuat, pilih `neutral`.

## Aturan Ambigu

- Kalau ragu lebih dari ±30 detik, pilih `neutral`.
- Jangan menyalin `ML`/`Rule` sebagai jawaban; itu hanya referensi.
- Berita harga saham teknikal pendek boleh `positive`/`negative` jika arah jelas, tapi pilih `neutral` bila ada sinyal berlawanan besar.
- PR/CSR/institusional biasanya `neutral` kecuali dampak finansial atau regulasi ke emiten jelas.
- Berita makro positif tidak otomatis `positive` untuk semua saham.
- Artikel berbahasa Inggris tetap dinilai dari dampak finansial ke emiten.

## Review Ulang

Report `output/prediction_research/sentiment_label_audit_report.csv` berisi kandidat re-review: label manusia berbeda dari prediksi model produksi yang sangat yakin. Report ini tidak otomatis menyatakan label manusia salah. Gunakan kolom `review_decision` untuk catatan manual seperti `keep_manual`, `fix_label`, atau `ambiguous_neutral`.
