# Panduan & Template Master Prompt Riset Harian Sentimena AI

Dokumen ini berisi template **Master Prompt Riset Kuantitatif & Pasar Harian** yang siap Anda salin (*copy-paste*) ke dalam percakapan Antigravity IDE setiap hari bursa.

---

## 🕒 Waktu Terbaik Menjalankan Prompt Ini

1. **Penutupan Sesi Bursa (Rekomendasi Utama: 15:45 – 16:30 WIB)**:
   - Data candle harian, volume bursa, dan penutupan IHSG sudah final.
   - Sisa antrian ARB/ARA dan sentimen berita sore hari sudah terbit lengkap.
   - Memberikan waktu yang cukup untuk merencanakan strategi eksekusi untuk hari berikutnya.
2. **Pra-Pembukaan Bursa (08:15 – 08:45 WIB)**:
   - Untuk memverifikasi apakah ada katalis berita global overnight (Wall Street, Dow Jones, indeks regional Asia, kurs Rupiah pagi).

---

## 📋 Teks Master Prompt (Tingkat Mendalam & Komprehensif)

Salin teks berikut secara utuh ke input chat Antigravity IDE:

```text
Halo Antigravity, tolong jalankan analisis dan riset mendalam Market Intelligence untuk kondisi pasar bursa hari ini:

1. DIAGNOSA KUANTITATIF PASAR HARI INI:
   - Ambil data penutupan IHSG (^JKSE) hari ini: Open, High, Low, Close, Volume, dan % perubahan.
   - Hitung deviasi harga terhadap MA20, MA50, dan MA200.
   - Evaluasi nilai RSI(14) dan akselerasi MACD Histogram.
   - Uji Market Breadth pada 48 saham acuan (LQ45/IDX30): jumlah gainers, losers, unchanged, dan saham yang membentur batas ARB (7%).
   - Cek kurs penutupan USD/IDR dan dampaknya terhadap capital flow.

2. EVALUASI ATURAN DISIPLIN GEMINI.md (3 KUNCI REBOUND):
   - Kunci 1 (Candle Reversal): Apakah terbentuk hammer/pin bar/bullish engulfing hijau tebal dengan volume di atas MA20?
   - Kunci 2 (Market Breadth): Apakah jumlah gainers sudah melampaui > 50% bursa aktif?
   - Kunci 3 (Support Defense): Apakah support kunci bertahan minimal 2 hari bursa berturut-turut tanpa new low?
   - Tentukan STATUS REZIM PASAR saat ini (CASH IS KING / DEFENSIVE / REBOUND SPECULATIVE / REBOUND CONFIRMED).

3. INTELIJEN SENTIMEN BERITA & KATALIS:
   - Telusuri perkembangan berita sentimen terkini (kebijakan BEI/OJK, respon resmi MSCI, pergerakan dana asing, dan sentimen sektoral/komoditas).
   - Identifikasi apakah ada katalis yang meredakan atau memperparah kepanikan likuiditas.

4. AUDIT PORTOFOLIO & SINKRONISASI SISTEM:
   - Cek posisi terbuka di database MySQL / open_positions.json.
   - Pastikan kepatuhan Stop Loss (-3,5%), larangan averaging down (martingale), dan aturan batas waktu 10 hari.

5. PENCATATAN & GIT COMMIT ATOMIK:
   - Buat laporan riset baru di: reports/market_regime_research_YYYYMMDD.md
   - Perbarui log kronologis di: docs/trading-log.md
   - Perbarui memori permanen di: GEMINI.md
   - Lakukan commit dan push secara atomik ke origin/main dengan pesan commit terstandar.
   - Tampilkan ringkasan eksekutif beserta rekomendasi aksi konkret untuk sesi besok.
```

---

## ⚡ Versi Prompt Cepat (Untuk Update Singkat)

Jika Anda sedang terburu-buru dan ingin update cepat dalam 1 menit:

```text
Tolong lakukan audit harian Market Intelligence untuk penutupan pasar hari ini: cek metrik IHSG, market breadth, verifikasi 3 kunci rebound sesuai GEMINI.md, perbarui laporan riset dan docs/trading-log.md, lalu push atomik ke GitHub.
```

---

## 🛠️ Apa Saja yang Otomatis Dikerjakan AI?

Setelah Anda mengirimkan prompt di atas, sistem Antigravity IDE akan otomatis:
1. Mengambil data pasar real-time lewat skrip Python/yfinance.
2. Melakukan audit komputasi teknikal dan keluasan bursa (*market breadth*).
3. Mengecek RSS feed Google News terkini untuk berita bursa dan kurs.
4. Memverifikasi portofolio terhadap protokol disiplin `GEMINI.md`.
5. Menghasilkan laporan markdown lengkap di `reports/market_regime_research_YYYYMMDD.md`.
6. Otomatis muncul di web portal **`/market-intelligence`** tanpa perlu konfigurasi tambahan.
7. Meng-commit dan mem-push perubahan ke GitHub secara atomik.
