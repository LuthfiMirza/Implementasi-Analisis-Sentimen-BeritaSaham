# Panduan Demo Cepat (untuk Dosen Penguji / Non-Developer)

Dokumen ini adalah versi ringkas dari `README.md` (yang isinya sangat teknis/panjang). Tujuannya: bisa menjalankan aplikasi dan menunjukkan hasil skripsi dalam < 10 menit tanpa perlu paham detail implementasi.

## 1. Menjalankan dari nol

Asumsi: PHP 8.3+, Composer, Node 18+, dan MySQL (mis. via XAMPP) sudah terpasang.

```bash
cd laravel-app
composer install
npm install && npm run build
cp .env.example .env        # kalau belum ada .env
php artisan key:generate
```

Pastikan MySQL aktif (kalau pakai XAMPP dan servicenya mati: `/Applications/XAMPP/xamppfiles/bin/mysql.server start`), lalu:

```bash
php artisan migrate --seed
php artisan serve
```

Buka `http://127.0.0.1:8000` di browser.

## 2. Login

| Role | Email | Password |
|---|---|---|
| Admin | `admin@sentimena.test` | `password` |
| User (demo) | `user@sentimena.test` | `password` |

## 3. Halaman kunci untuk ditunjukkan ke penguji

Urutan ini mengikuti alur skripsi: **berita → sentimen → fitur → prediksi → decision support**.

| # | Halaman | Apa yang ditunjukkan |
|---|---|---|
| 1 | **Berita Terkini** (`/news`) | Agregasi berita multi-sumber (16 feed RSS + API), filter sentimen/kualitas/tanggal, badge ML vs rule-based per artikel |
| 2 | **Prediksi** (`/analytics?code=BBCA`) | Chart harga+sentimen, decision support, kartu prediksi (Teknikal vs Teknikal+Sentimen) |
| 3 | **Prediksi BUMI/DEWA** (`/analytics?code=BUMI` atau `DEWA`) | Model khusus saham volatil + panel "Riset Trading" yang **jujur menampilkan keterbatasan** (strategi TP/SL terbukti tidak profitable net-of-cost) |
| 4 | **Evaluasi Model** (`/evaluasi`) | Ringkasan akurasi model prediksi 10 saham resmi |
| 5 | **Audit Sentimen** (`/evaluasi/sentimen`) | Perbandingan sentimen vs pergerakan harga |
| 6 | **Backtest DSS** (`/backtest`) | Hasil backtest sistem pendukung keputusan |
| 7 | **Validasi Sentimen Manual** (`/sentiment-validation`) | Tool riset: label manual ML vs rule-based, dengan ringkasan agreement rate (`/sentiment-validation/summary`) — bukti empiris kenapa rule-based dipilih sebagai tie-break |

## 4. Temuan riset yang layak disebut ke penguji (jujur, termasuk yang negatif)

Skripsi ini secara sengaja **tidak menyembunyikan hasil negatif** — itu bagian dari rigor ilmiahnya:

- **Coverage sentimen rendah** (0.22% dari total hari trading untuk 10 saham resmi) karena riwayat harga 25 tahun vs data berita baru ~1-1.5 tahun. Dicatat sebagai keterbatasan, bukan disembunyikan.
- **Strategi trading TP/SL BUMI/DEWA terbukti tidak profitable** net-of-cost (dianalisis sampai level fat-tail robustness, bukan cuma gross return).
- **Validasi manual 801 artikel** menunjukkan model ML (IndoBERT) cuma 35.6% akurat dibanding manusia — lebih buruk dari tebak acak — sementara rule-based 59.4%. Sistem sudah diperbaiki untuk pakai rule-based sebagai pemenang saat keduanya beda pendapat.
- Detail lengkap tiap temuan ada di `output/prediction_research/` dan `output/trading_research/reports/`. Lihat `output/RESEARCH_INDEX.md` untuk peta 700+ file artefak riset (final vs eksperimen).

## 5. Kalau ada yang error

```bash
php artisan test          # cek semua fitur backend masih jalan (target: semua passed)
php artisan migrate:status  # cek migrasi database
```

Kalau `php artisan test` gagal di `OjkRssFetcherTest`, itu bukan bug proyek — itu network-dependent test yang bisa gagal kalau layanan RSS eksternal sedang berubah struktur halaman.
