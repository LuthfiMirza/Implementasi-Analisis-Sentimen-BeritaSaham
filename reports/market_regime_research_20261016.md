# Laporan Riset Kuantitatif & Pasar: Investigasi Crash IHSG (-8,01%), Kegagalan Rezim Strategi & Evaluasi Portofolio

- **Tanggal Riset**: 16 Oktober 2026 (09:35 WIB)
- **Status Rezim Pasar**: **CRASH SISTEMIK / PANIC LIQUIDATION (DEFENSIVE / CASH IS KING)**
- **Indeks Acuan**: IHSG (^JKSE) Dibuka Anjlok ke **5.393,92 (-8,01% / -469,85 poin)**
- **Status Portofolio**: 24/24 Posisi Terbuka (100%) Mengalami Floating Loss & Menembus Batas Stop Loss

---

## 1. Eksekutif Ringkasan

Pada pembukaan perdagangan Jumat, 16 Oktober 2026 pukul 09:00 WIB, pasar saham Indonesia mengalami peristiwa *flash crash / systemic sell-off*. IHSG langsung dibuka *gap down* menembus seluruh level support teknikal hingga ke level **5.393,92 (-8,01%)**. 

Tekanan jual ini menyeret seluruh saham aktif, termasuk saham penopang indeks (BBRI -14,56%, BMRI -14,39%, TLKM -15,56%) hingga membentur batas Auto Rejection Bawah (ARB). Akibatnya, seluruh 24 posisi terbuka berbasis strategi *Drawdown Bounce* Sentimena ambruk serentak dengan kerugian floating berkisar antara **-6,3% hingga -26,2%**.

Laporan ini mendokumentasikan akar penyebab kejatuhan pasar, mengidentifikasi kelemahan kritis pada algoritma skrining dan eksekusi portofolio, serta menetapkan protokol disiplin manajemen risiko darurat.

---

## 2. Diagnosa Kuantitatif Pasar (16 Oktober 2026)

### A. Metrik Teknikal IHSG

| Indikator | 15 Okt 2026 | 16 Okt 2026 (Live 09:30 WIB) | Interpretasi Kuantitatif |
| :--- | :--- | :--- | :--- |
| **Harga Indeks** | 5.863,78 | **5.393,92** | Anjlok -8,01% (-469,85 poin) di pembukaan. |
| **Support 5.800** | Teruji di 5.804 | **Jebol Telak** | Support kunci runtuh tanpa perlawanan antrian beli. |
| **Deviasi vs MA20** | -4,39% | **-12,05%** | Deviasi ekstrem jangka pendek (*free fall*). |
| **Deviasi vs MA50** | -7,61% | **-14,99%** | Patah tren menengah (*Bearish capitulation*). |
| **Deviasi vs MA200**| -16,83% | **-23,49%** | Krisis likuidasi siklus besar. |
| **RSI(14)** | 29,09 | **< 18,5** | Ekstrem *oversold*, namun pantulan dilarang dientri tanpa konfirmasi. |
| **MACD Histogram**| -21,66 | **Melebar Drastis Negatif** | Momentum akselerasi penurunan makin dalam. |

### B. Keluasan Pasar (*Market Breadth*) & Likuiditas

- Saham-saham berkapitalisasi pasar terbesar (*Big Caps*) langsung dihantam *net sell* asing masif:
  - **BBRI**: Rp 2.640 (-14,56%) ➔ Menempel ARB
  - **BMRI**: Rp 3.390 (-14,39%) ➔ Menempel ARB
  - **TLKM**: Rp 1.900 (-15,56%) ➔ Terjun bebas
- Likuiditas pada sisi antrian beli (*Bid Volume*) lenyap, menyebabkan *bid-ask spread* melebar dan *order book* membeku di batas bawah.

---

## 3. Evaluasi Real-Time 4 Posisi Terbuka Portofolio (Hasil Rekonsiliasi)

Setelah dilakukan audit dan rekonsiliasi antara Database MySQL (`trades` table - Trade Journal) dan file tracker Python (`open_positions.json`), dipastikan bahwa **hanya ada 4 posisi terbuka yang sah dan riil dipegang oleh trader**:

| No | Ticker | Trade ID | Tanggal Beli | Harga Beli | Harga 15-Okt | Harga 16-Okt (Live) | Floating PnL | Diagnosa Status Rule |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 1 | **SMGR** | #732 | 02 Okt 2026 | Rp 1.505 | Rp 1.635 | **Rp 1.395** | **-7,31%** | **Hari ke-11**. Profit +8% kemarin tergerus gap down. Wajib antrikan likuidasi. |
| 2 | **PTRO** | #748 | 12 Okt 2026 | Rp 4.190 | Rp 4.120 | **Rp 3.340** | **-20,29%** | Katalis Rights Issue 170 jt lbr + Jebol Hard SL (-3,5%). |
| 3 | **ENRG** | #749 | 12 Okt 2026 | Rp 950 | Rp 935 | **Rp 790** | **-16,84%** | Posisi riil ke-4. Menembus batas Stop Loss (-3,5%). |
| 4 | **ESSA** | #752 | 14 Okt 2026 | Rp 585 | Rp 580 | **Rp 480** | **-17,95%** | Menembus batas Stop Loss (-3,5%). |

> **Catatan Rekonsiliasi Data (Koreksi Desinkronisasi)**:  
> Laporan sebelumnya sempat memuat 24 baris karena `detect_signal.py` secara otomatis mendaftarkan setiap sinyal baru ke `open_positions.json` saat IHSG drop (12–15 Okt), termasuk 20 sinyal yang tidak pernah dieksekusi oleh user di Trade Journal (BUMI, DEWA, RAJA, TINS, BRPT, INET, PSAB, serta variasi tanggal ENRG & PTRO). File `open_positions.json` kini telah direkonsiliasi dan dibersihkan sehingga tepat 100% sinkron dengan 4 posisi riil di database.

---

## 4. Analisis Akar Masalah: Mengapa Tiba-Tiba Jebol Semua?

### 1. Faktor Eksternal (Makro & Likuiditas Bursa)
- **Pelanggaran Batas Support Psikologis**: Jebolnya level 6.000 dan 5.800 mengaktifkan perintah *stop loss order* otomatis dari institusi besar, memicu efek domino (*cascade liquidation*).
- **Outflow Asing Agresif**: Likuidasi global pada aset *emerging markets* membuat investor asing membuang saham likuid perbankan (BBRI, BMRI, TLKM).
- **Forced Liquidation & Margin Call**: Nasabah margin yang tertekan sejak penurunan beberapa hari sebelumnya dipaksa melikuidasi portofolio di pembukaan pasar.

### 2. Faktor Internal Algoritma Sentimena
- **Regime Mismatch (Menangkap Pisau Jatuh)**: Strategi *Drawdown Bounce* mengandalkan asumsi *mean reversion* (pantulan harga setelah diskon). Di pasar *bearish crash*, penurunan harga saham bukan diskon melainkan kelanjutan tren turun (*falling knife*).
- **Regresi Engine `detect_signal.py` (Fase AW)**: Penghapusan filter tren IHSG membuat sistem terus menerbitkan sinyal beli saat pasar sedang ambruk.
- **Jebakan Averaging Down (Martingale)**: Akumulasi lot hingga 7x di ENRG, 4x di PTRO, dan 3x di RAJA melipatgandakan kerugian portofolio.
- **Keterlambatan Eksekusi Cut Loss**: Sinyal Stop Loss -3,5% yang terpicu sejak 14-15 Oktober tidak segera dieksekusi, sehingga terakumulasi menjadi kerugian belasan hingga puluhan persen.
- **Gagal Eksekusi Target Waktu SMGR**: SMGR yang sudah mencetak profit +5,6% s/d +8,6% dan genap mencapai hari ke-10 tidak langsung dieksekusi Take Profit di pembukaan 09:00 WIB, sehingga tergerus oleh gap down pasar.

---

## 5. Protokol Tindakan Wajib Sesuai GEMINI.md

1. **STATUS: CASH IS KING / DEFENSIVE**:
   - **DILARANG KERAS** melakukan pembelian baru atau belanja saham murah hari ini.
2. **STOP AVERAGING DOWN**:
   - Tutup opsi penambahan posisi pada saham yang sedang floating loss.
3. **Eksekusi Likuidasi & Cut Loss Disiplin**:
   - Mengantrikan penjualan secara bertahap begitu likuiditas pada bid menyerap antrian ARB.
4. **Tiga Syarat Konfirmasi Rebound Sebelum Masuk Kembali**:
   - Terbentuk candle pembalikan (*hammer/bullish engulfing*) ditutup hijau tebal + volume tinggi.
   - Market breadth membaik (*gainers* > 50% bursa aktif).
   - Support baru terbukti bertahan minimal **2 hari bursa berturut-turut** tanpa mencetak titik terendah baru (*no new low*).
