# Laporan Riset Kuantitatif & Pasar: Evaluasi Koreksi IHSG, Diagnosa Rentetan Loss, & Roadmap Rebound

- **Tanggal Riset**: 15 Oktober 2026
- **Status Pasar**: Bearish Kuat (Distribusi & Likuidasi Sistemik)
- **Indeks Acuan**: IHSG (^JKSE) Ditutup di **5.844,43 (-1,83%)**

---

## 1. Eksekutif Ringkasan

Pada pertengahan Oktober 2026, IHSG mengalami tekanan jual agresif, menembus support psikologis 6.000 hingga menguji titik terendah harian di **5.804**. Mayoritas posisi trading berbasis strategi *mean reversion / drawdown bounce* mengalami rentetan *stop loss* (BUMI, INET, PTRO, BRPT, DEWA, DSSA, ENRG).

Riset ini mengidentifikasi akar penyebab kegagalan strategi (*regime mismatch*), mengevaluasi posisi terbuka saat ini, dan merumuskan **3 Syarat Wajib Konfirmasi Rebound** serta peta jalan waktu (*roadmap*) untuk entri kembali ke pasar pada rentang waktu **16 – 20 Oktober 2026**.

---

## 2. Diagnosa Data Kuantitatif Pasar (15 Oktober 2026)

### A. Metrik Teknikal IHSG

| Indikator | Nilai Terkini | Interpretasi Kuantitatif |
| :--- | :--- | :--- |
| **Harga Penutupan** | 5.844,43 | Anjlok -1,83% (-109 poin) dalam 1 sesi. |
| **Rentang Harian** | Open 5.917,13 \| High 5.917,70 \| Low 5.804,21 | Tanpa *upper shadow* (0,5%), body merah padat 64,1% dari range. |
| **MA20** | 6.131,93 | Deviasi: **-4,69%** (Downtrend pendek). |
| **MA50** | 6.346,16 | Deviasi: **-7,91%** (Downtrend menengah). |
| **MA200** | 7.050,54 | Deviasi: **-17,11%** (Siklus Bearish Besar). |
| **RSI(14)** | 28,2 | Masuk zona *oversold* (<30). Bukan sinyal beli sebelum ada konfirmasi pantulan. |
| **MACD (12,26,9)** | Line -127,41 \| Signal -104,51 \| Hist -22,90 | Histogram melebar negatif (momentum penurunan masih berakselerasi). |
| **Bollinger Bands** | Lower BB di 5.800,31 \| %B = 0,07 | Menempel batas bawah (*Band Walking Downward*). |

### B. Keluasan Pasar (*Market Breadth*)

Dari 128 saham aktif yang dipindai Sentimena pada 15 Oktober 2026:
- **Gainers (Naik)**: 7 saham (5,5%)
- **Unchanged (Stagnan)**: 5 saham (3,9%)
- **Losers (Turun)**: 116 saham (90,6%)
- **Rata-rata Return Seluruh Saham**: **-3,93%**

*Kesimpulan Breadth*: Terjadi likuidasi merata (panik massal), bukan sekadar rotasi sektoral biasa.

---

## 3. Akar Masalah Rentetan Loss (Diagnosa Strategi)

1. **Jebakan "Menangkap Pisau Jatuh" (*Catching a Falling Knife*)**:
   - Strategi *Drawdown Bounce / Gabungan* mengandalkan aturan: beli jika *ret_2d <= -5%* atau *drawdown_20d <= -20%*.
   - Dalam pasar *bullish* atau *sideways*, penurunan -5% adalah diskon sementara dengan peluang pantulan tinggi (win rate 75-80%).
   - Namun ketika **IHSG sendiri anjlok -1,8% per hari**, penurunan saham -5% adalah awal gelombang penurunan lanjutan. Begitu masuk di T+1, saham langsung anjlok lagi -4% hingga menabrak hard stop loss (-3,5%).
2. **Bahaya *Averaging Down* (Kasus ENRG)**:
   - Terjadi 4 kali entri pada ENRG (1.070, 1.060, 970, 950).
   - Penutupan hari ini di 895–905 mencatat kerugian floating -5,3% hingga -15,9%.
   - Menambah lot saat tren turun tanpa menunggu *base* justru melipatgandakan risiko portofolio.
3. **Katalis Berita Spesifik Emiten**:
   - **PTRO**: Pengumuman resmi rencana *Rights Issue 170 Juta Saham* (15 Okt, 15:29 WIB) memicu kekhawatiran dilusi, memicu aksi jual dengan volume tinggi (harga turun ke 3.880).
   - **BUMI & DEWA**: Tekanan net sell asing berkelanjutan (outflow ratusan juta lembar saham) dan volume guyuran 1,2x–1,4x MA20.

---

## 4. Evaluasi Posisi Berjalan (15 Oktober 2026)

| Ticker | Entry Price & Date | Harga Hari Ini | Floating PnL | Tindakan Wajib |
| :--- | :--- | :--- | :--- | :--- |
| **SMGR** | Rp1.505 (02 Okt 2026) | **Rp1.590** | **+5,65%** | **TAKE PROFIT** di pembukaan 16 Okt 09:00 WIB. Hari bursa ke-10 (Target Waktu tercapai). Kunci kas segar. |
| **PTRO** | Rp4.190 (12 Okt 2026) | **Rp3.880** | **-7,40%** | **CUT LOSS DISIPLIN**. Batas SL (-3,5% @ 4.043) sudah jebol + sentimen Rights Issue. |
| **ESSA** | Rp585 (14 Okt 2026) | **Rp555** | **-5,13%** | **CUT LOSS DISIPLIN**. Batas SL (-3,5% @ 565) sudah jebol. |
| **ENRG** | Rp1.070 s/d Rp950 | **Rp895 - Rp905**| **-5,3% s/d -15,9%** | **STOP AVERAGING DOWN**. Batasi eksposur risiko dan tunggu terbentuknya struktur dasar. |

---

## 5. Tiga Syarat Mutlak Konfirmasi Rebound

Pasar **DILARANG DIENTRI** sampai ketiga syarat berikut terpenuhi:

1. **Konfirmasi Candlestick IHSG**: Terbentuk pola pembalikan arah yang jelas (*hammer*, *pin bar* berekor bawah panjang, atau *bullish engulfing*) dengan penutupan hijau padat dan volume di atas rata-rata 20 hari.
2. **Keluasan Pasar Membaik**: Jumlah saham yang naik (*gainers*) minimal mencapai **> 50%** dari total bursa.
3. **Pertahanan Support**: IHSG mampu bertahan di atas level psikologis **5.800** tanpa mencetak *new low* selama minimal **2 sesi perdagangan berturut-turut**.

---

## 6. Peta Jalan Waktu Masuk Kembali (*Roadmap 16 – 20 Oktober 2026*)

```
[Kamis, 15 Okt] ─────────> [Jumat, 16 Okt] ─────────> [Senin, 19 Okt] ─────────> [Selasa, 20 Okt]
  IHSG 5.844                 Uji Support 5.800          Observasi Base            Konfirmasi Rebound
 (Panic Sell-off)            & Weekend Risk            (Volume Mereda)           (Jendela Entri Valid)
  STATUS: CASH               STATUS: NO ENTRY          STATUS: WAIT & SEE        STATUS: ENTRY 25-30%
```

- **Jumat, 16 Oktober 2026**:
  - Pasar rawan *weekend risk aversion* dan aksi likuidasi lanjutan.
  - Sesi 1: Potensi pengujian 5.800 - 5.810. **Dilarang belanja saham di pagi hari**.
  - Sesi 2 (15:30 - 16:00 WIB): Amati apakah terbentuk penolakan (*rejection*) di atas 5.800.
- **Senin, 19 Oktober 2026**:
  - Konfirmasi *selling exhaustion* (apakah volume jual mulai kering dan pergerakan mendatar / *sideways*).
- **Selasa, 20 Oktober 2026**:
  - Jendela waktu terawal yang aman jika terjadi *breakout* di atas 5.880 - 5.900 dengan konfirmasi *market breadth* positif.
  - Terapkan strategi *pyramiding*: Masuk 25% modal terlebih dahulu, tambah hanya jika harga naik menembus resistance berikutnya.
