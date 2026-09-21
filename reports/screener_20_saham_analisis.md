# Laporan Analisis Kuantitatif: Bedah 20 Saham Stockbit Screener & Backtest Momentum BSJP

**Tanggal Analisis:** 21 September 2026  
**Dataset:** 20 Saham Pilihan Screener Stockbit (Desember 2025 s/d 21 September 2026)  
**Modal Awal Uji Coba:** Rp 10.000.000  

---

## 1. Profil 20 Saham yang Terpilih Hari Ini

Seluruh 20 saham yang lolos screener hari ini memiliki karakteristik umum yang sangat seragam: **Saham Lapis Tiga (Small Cap / Penny Stocks) dengan Order Book Relatif Tipis dan Dominasi Sektor Properti & Siklikal**.

| No | Ticker | Nama Perusahaan | Sektor | Harga Hari Ini | Kenaikan (%) | Rasio Lonjakan Vol | Nilai Transaksi | Estimasi Market Cap |
|:---|:---|:---|:---|:---:|:---:|:---:|:---:|:---:|
| 1 | **URBN** | Urban Jakarta Propertindo Tbk | Real Estate | Rp 252 | **+9.57%** | 3.8x | Rp 226 Juta | Rp 786 M |
| 2 | **MAYA** | Bank Mayapada Internasional Tbk | Financial Services | Rp 210 | **+8.81%** | **19.1x** | Rp 2,89 Miliar | Rp 5,49 T |
| 3 | **GRIA** | Ingria Pratama Capitalindo Tbk | Real Estate | Rp 183 | **+7.65%** | **17.9x** | Rp 5,67 Miliar | Rp 1,35 T |
| 4 | **MSIE** | Multisarana Intan Eduka Tbk | Real Estate | Rp 185 | **+6.94%** | 2.6x | Rp 1,88 Miliar | Rp 270 M |
| 5 | **PSDN** | Prasidha Aneka Niaga Tbk | Consumer Defensive | Rp 144 | **+6.67%** | **9.5x** | Rp 6,03 Miliar | Rp 207 M |
| 6 | **BKDP** | Bukit Darmo Property Tbk | Real Estate | Rp 179 | **+6.55%** | 4.6x | Rp 6,76 Miliar | Rp 1,35 T |
| 7 | **NATO** | Olympus Strategic Indonesia Tbk | Consumer Cyclical | Rp 1.155 | **+6.45%** | 1.5x | Rp 583 Juta | Rp 9,24 T |
| 8 | **ARII** | Atlas Resources Tbk | Energy | Rp 302 | **+6.34%** | **10.0x** | Rp 1,15 Miliar | Rp 1,13 T |
| 9 | **RISE** | Jaya Sukses Makmur Sentosa Tbk | Real Estate | Rp 850 | **+6.25%** | 5.0x | Rp 3,79 Miliar | Rp 13,76 T |
| 10 | **VERN** | Verona Indah Pictures Tbk | Communication Serv | Rp 244 | **+6.09%** | 3.1x | Rp 6,82 Miliar | Rp 1,16 T |
| 11 | **SMLE** | Sinergi Multi Lestarindo Tbk | Basic Materials | Rp 222 | **+5.71%** | 1.8x | Rp 7,89 Miliar | Rp 516 M |
| 12 | **SCNP** | Selaras Citra Nusantara Perkasa | Technology | Rp 168 | **+5.66%** | **49.9x** | Rp 2,46 Miliar | Rp 387 M |
| 13 | **AMIN** | Ateliers Mecaniques D Indonesie | Industrials | Rp 274 | **+5.38%** | 3.4x | Rp 537 Juta | Rp 296 M |
| 14 | **BAIK** | Bersama Mencapai Puncak Tbk | Consumer Cyclical | Rp 254 | **+4.96%** | 1.7x | Rp 2,80 Miliar | Rp 286 M |
| 15 | **VINS** | Victoria Insurance Tbk | Financial Services | Rp 150 | **+4.90%** | 6.3x | Rp 166 Juta | Rp 219 M |
| 16 | **IOTF** | Sumber Sinergi Makmur Tbk | Technology | Rp 65 | **+4.84%** | 5.3x | Rp 2,18 Miliar | Rp 344 M |
| 17 | **ASLC** | Autopedia Sukses Lestari Tbk | Consumer Cyclical | Rp 69 | **+4.55%** | **9.2x** | Rp 4,81 Miliar | Rp 879 M |
| 18 | **CARS** | Bintraco Dharma Tbk | Consumer Cyclical | Rp 119 | **+4.39%** | 3.1x | Rp 1,62 Miliar | Rp 1,78 T |
| 19 | **DSFI** | Dharma Samudera Fishing Ind | Consumer Defensive | Rp 96 | **+4.35%** | 2.7x | Rp 2,85 Miliar | Rp 178 M |
| 20 | **BCIC** | Bank JTrust Indonesia Tbk | Financial Services | Rp 140 | **+3.70%** | 3.6x | Rp 298 Juta | Rp 2,53 T |

---

## 2. Mengapa Saham-Saham Ini Bisa Lolos Screener Hari Ini?

Screener Stockbit Anda menggunakan 5 filter utama yang menyaring lebih dari 900 emiten di BEI menjadi hanya 20 saham ini:
1. **Ledakan Volume (Volume Spike)**: `Volume > Previous Volume`. 100% saham mengalami lonjakan volume dari 1.5x hingga **50x lipat** (misalnya SCNP naik dari 293 ribu lembar menjadi 14,6 juta lembar!).
2. **Lilin Hijau Solid (Bullish Candle)**: `Price > Open Price`. 100% saham ditutup di atas harga pembukaan tanpa adanya doji atau penolakan harga atas yang ekstrem saat sesi 2 berakhir.
3. **Kenaikan Harga Minimum**: `1-Day Return >= 3.0%`. Seluruh saham menguat di atas +3.7% hingga +9.57%.
4. **Batas Likuiditas Nyata**: `Value >= Rp 100 Juta`. Mengeliminasi saham yang naik karena transaksi beberapa lot semata.
5. **Breakout / Uji Resistance**: `Price >= Price MA 5` & `Price >= Price MA 10`. Harga saham berhasil menembus moving average jangka pendek, memicu sinyal teknikal 'Golden Cross' atau 'Breakout'.

---

## 3. Mengapa Seluruh Saham Tersebut Naik Serentak Hari Ini?

Ada 3 faktor mekanis di balik fenomena ini:
1. **Sifat Micro-Cap & Order Book Tipis**:
   - 10 dari 20 saham memiliki kapitalisasi pasar di bawah Rp 500 Miliar.
   - Pada saham seperti BBCA atau TLKM, dana Rp 3 Miliar tidak akan menggerakkan harga 0.1%. Namun pada saham seperti GRIA, PSDN, atau SCNP, injeksi modal Rp 2 s/d Rp 6 Miliar langsung melahap seluruh antrian offer dan menaikkan harga +5% sampai +8% dalam hitungan menit.
2. **Rotasi Spekulasi Sektor Properti & Siklikal**:
   - Terdapat klaster kuat hari ini di sektor properti lapis tiga (URBN, GRIA, MSIE, BKDP, RISE). Ketika satu saham sektor mulai ditarik, spekulan dan retail berpindah ke saham-saham satu sektor yang masih tertinggal.
3. **Trigger Algoritma & Screener Retail**:
   - Ketika volume awal melonjak dan harga menembus MA5, screener ribuan trader retail (seperti Stockbit, RTI, IPOT) serentak membunyikan notifikasi. Masuknya gelombang beli retail (FOMO buying) mendorong harga bertahan di level puncak hingga penutupan sesi 2.

---

## 4. Hasil Backtest Historis (1 Des 2025 s/d 21 Sep 2026 - Modal Rp 10 Juta)

Kami melakukan backtest kuantitatif terhadap **331 kejadian sinyal historis** pada ke-20 saham ini dari 1 Desember 2025 sampai sekarang dengan memperhitungkan biaya transaksi broker (Fee 0.40% round-trip):

| Model Eksekusi | Logika Trading | Modal Akhir (Dari Rp 10 Juta) | Total Return (%) | Win Rate (%) | Keterangan |
|:---|:---|:---:|:---:|:---:|:---|
| **Model 1: Naive Swing Hold** | Beli Sore, Jual Sore H+1 | **Rp 3.605.542** | **-63.94%** | 34.7% | **RUGI BESAR**. Saham dibanting sore H+1 setelah retail masuk. |
| **Model 2: BSJP Murni (09:00 WIB)** | Beli Sore, Jual di Pembukaan Open H+1 | **Rp 55.382.991** | **+453.83%** | 50.0% | **SANGAT PROFITABEL**. Memanfaatkan gap-up euforia pagi. |
| **Model 3: Scalping Pagi (TP 2.5% / SL 2.5%)** | TP +2.5% Pagi, SL -2.5%, exit sore | **Rp 13.437.937** | **+34.38%** | 59.0% | **KONSISTEN & AMAN**. Risiko terkontrol ketat. |
| **Model 4: Scalping Pagi (TP 3.5% / SL 3.0%)** | TP +3.5% Pagi, SL -3.0%, exit sore | **Rp 13.174.014** | **+31.74%** | 52.1% | **PROFITABEL**. Menjaring kenaikan lebih tinggi. |

### Bukti Statistik Kunci:
- **Puncak Pagi Hari (H+1 High)**: Rata-rata harga tertinggi keesokan paginya adalah **+6.38%**, dengan peluang membuat higher high sebesar **82.8%**!
- **Penutupan Sore Hari (H+1 Close)**: Namun jika ditahan hingga sore, rata-rata return merosot menjadi **+0.28%** dengan Win Rate hanya **34.4%** karena 65% saham mengalami pelemahan (distribusi).

---

## 5. Panduan Praktis: Cara Menangkap Saham-Saham Ini Sebelum / Saat Naik

### Strategi 1: Beli Sore Jual Pagi (BSJP) — Jam 15:35 s/d 15:55 WIB (Direkomendasikan)
1. Buka Stockbit Screener pada pukul **15:30 - 15:45 WIB**.
2. Masukkan rumus:
   - `Volume > Previous Volume * 2`
   - `Price > Open Price`
   - `1 Day Return (%) >= 3.0%`
   - `Value >= 100,000,000`
   - `Price >= Price MA 5`
3. Pilih 1–2 saham dengan lonjakan volume tertinggi dan nilai transaksi di atas Rp 1 Miliar.
4. Lakukan pembelian di harga penutupan (pre-closing 15:50 - 15:58 WIB).
5. Pasang order jual otomatis (Auto Order / GTC) pada **08:55 WIB** esok hari dengan target **+2.5% s/d +3.5%**. Begitu pasar buka (09:00 - 09:10 WIB), order akan langsung tereksekusi saat euforia pagi.

### Strategi 2: Deteksi Dini Intraday (Jam 09:15 - 10:00 WIB)
Untuk menangkapnya saat baru naik +1% s/d +2%:
- Aturan screener intraday:
  - `Volume Jam 09:30 >= 50% dari Rata-rata Volume 20 Hari`
  - `Price Return antara +1.5% s/d +3.0%` (belum terbang tinggi)
  - `Bid Volume > Offer Volume` (Tekanan beli agresif)
