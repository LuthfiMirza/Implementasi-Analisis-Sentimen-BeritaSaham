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

Pastikan MySQL aktif (kalau pakai XAMPP dan servicenya mati: `/Applications/XAMPP/xamppfiles/bin/mysql.server start`), lalu isi database:

```bash
php artisan migrate --seed
```

### Menyalakan service

Proyek butuh **4 service**. Cara paling cepat — satu perintah:

```bash
./dev-start.sh      # cek MySQL, nyalakan 2 API Python di background, lalu jalankan web server
```

Buka `http://127.0.0.1:8000` di browser. Untuk mematikan API background nanti: `./dev-stop.sh`.

Kalau mau manual satu-satu (tiap baris di jendela terminal sendiri):

| Service | Perintah | Port | Perlu untuk |
|---|---|---|---|
| Web Laravel | `php artisan serve` | 8000 | **semua halaman** |
| Sentiment API | `./start_sentiment_api.sh` | 8002 | analisis sentimen IndoBERT (ada fallback rule-based kalau mati) |
| Prediction API | `./start_prediction_api.sh` | 8001 | halaman **Prediksi** & **Evaluasi Model** |
| MySQL | `/Applications/XAMPP/xamppfiles/bin/mysql.server start` | 3306 | **semua** (biasanya sudah auto-nyala saat login) |

Catatan:
- **Scheduler** (auto-fetch berita, update data Market Alerts tiap sore 18:35 WIB) sudah jalan
  lewat cron per-menit — tidak perlu dinyalakan. Kalau mau lihat lognya live: `php artisan schedule:work`.
- **`npm run dev`** cuma perlu kalau sedang mengubah tampilan (CSS/JS). Untuk demo biasa, hasil
  `npm run build` sudah cukup.
- Cek semua hidup:
  ```bash
  curl -s -o /dev/null -w "web %{http_code}\n"        http://127.0.0.1:8000/login
  curl -s -o /dev/null -w "sentiment %{http_code}\n"  http://127.0.0.1:8002/docs
  curl -s -o /dev/null -w "prediction %{http_code}\n" http://127.0.0.1:8001/docs
  ```

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
| 7 | **Validasi Sentimen Manual** (`/sentiment-validation`) | Tool riset: label manual ML vs rule-based, dengan ringkasan agreement rate (`/sentiment-validation/summary`) — dasar untuk memutuskan kebijakan tie-break saat ML dan rule-based beda pendapat |

## 4. Temuan riset yang layak disebut ke penguji (jujur, termasuk yang negatif)

Skripsi ini secara sengaja **tidak menyembunyikan hasil negatif** — itu bagian dari rigor ilmiahnya:

- **Coverage sentimen rendah** (1.37% dari total hari trading untuk 10 saham resmi di dataset full-history 25 tahun; naik ke 17-28% di subset periode terbaru 2024-08+) karena riwayat harga 25 tahun vs data berita baru ~1.5-2 tahun. Dicatat sebagai keterbatasan struktural, bukan disembunyikan.
- **Strategi trading TP/SL BUMI/DEWA terbukti tidak profitable** net-of-cost (dianalisis sampai level fat-tail robustness, bukan cuma gross return).
- **Model sentimen ML (IndoBERT) sudah di-fine-tune** dari 801 artikel yang dilabel manual (awalnya model mentah cuma 35.6% akurat dibanding manusia — lebih buruk dari tebak acak — vs rule-based 59.4%). Setelah fine-tuning, ML naik jadi 58.16% macro-F1, mengalahkan rule-based (54.82%) di test-set yang sama. Kebijakan tie-break (saat ML dan rule-based beda pendapat) sudah dibalik mengikuti bukti empiris ini: ML sekarang menang (55.8% akurat vs rule-based 32.7%, diukur khusus di kondisi disagreement), dan seluruh riwayat artikel sudah di-backfill mengikuti kebijakan baru.
- **Temuan jujur lanjutan**: meskipun kualitas sentimen terbukti membaik signifikan (dua kali diuji — model lebih akurat, DAN kebijakan tie-break diperbaiki), kontribusinya ke akurasi model prediksi harga **tetap tidak berubah** (diuji ulang dengan metodologi fair-comparison + multi-seed). Ini memperkuat kesimpulan bahwa akar masalahnya coverage berita yang struktural, bukan kualitas analisis sentimen — itu sebabnya bobot sentimen di skor Decision Support System sengaja dijaga moderat (0,20 dari total), bukan dominan.
- **Disiplin validasi juga diterapkan ke fitur non-sentimen**: eksperimen fitur "buying pressure" (rasio volume beli) yang sempat diklaim informal mencapai ~59% akurasi arah, setelah diuji ulang dengan walk-forward out-of-sample 8-fold justru terbukti **lebih buruk dari baseline** (33,06% vs majority-class 38,80%, kalah di 7 dari 8 fold) — sengaja **tidak digabungkan ke produksi** karena gagal validasi, contoh nyata bagaimana proyek ini menyaring klaim sebelum diterima. Laporan: `output/prediction_research/buying_pressure_walkforward_validation.txt`.
- Detail lengkap tiap temuan ada di `output/prediction_research/` dan `output/trading_research/reports/`. Lihat `output/RESEARCH_INDEX.md` untuk peta 700+ file artefak riset (final vs eksperimen), dan `plan.md` untuk log eksekusi fase perbaikan sentimen terbaru.

## 5. Kalau ada yang error

```bash
php artisan test          # cek semua fitur backend masih jalan (target: semua passed)
php artisan migrate:status  # cek migrasi database
```

Kalau `php artisan test` gagal di `OjkRssFetcherTest`, itu bukan bug proyek — itu network-dependent test yang bisa gagal kalau layanan RSS eksternal sedang berubah struktur halaman.
