# Laporan Riset Kuantitatif & Pasar: Breakout IHSG di Atas MA20 (5.344,41), Panen Profit Sistem 3-Lapis Proteksi (96,3% Win Rate), & Rumus Matematis Pola Rebound

- **Tanggal Riset**: Jumat, 13 November 2026 (Penutupan Sesi Perdagangan 16:00 WIB)
- **Status Rezim Pasar**: **BULLISH MARKUP / CONFIRMED UPTREND DI ATAS MA20 (IHSG +3,35% > MA20)**
- **Indeks Acuan**: IHSG (`^JKSE`) Ditutup di **5.344,41 (+1,78% / +93,51 poin)** | Range: Low **5.215,15** — High **5.361,94**
- **Market Breadth**: **78,5% Gainers** (102 saham naik vs 16 turun dari 130 saham aktif), **0 Saham Utama/LQ45 Terkunci ARB**
- **Performa Portofolio (6–13 Nov 2026)**: **27 Trade Closed (26 Win / 1 Loss = 96,3% Win Rate)**. Hari ini (`13 Nov`) 6 posisi mengunci profit otomatis via *Lapis 2 Trailing Stop* dengan realisasi **+Rp 5.460.758** (`PACK +12,16%`, `DEWA +14,75%`, `RAJA +10,25%`, `BRPT +7,80%`, `BRPT +5,69%`, `DEWA +4,08%`).

---

## 1. Ringkasan Eksekutif & Struktur Rezim Pasar

Pada penutupan perdagangan Jumat, 13 November 2026, Indeks Harga Saham Gabungan (`^JKSE`) resmi mengukuhkan **transisi rezim dari *Post-Crash Recovery* menjadi *Bullish Markup (Confirmed Uptrend di Atas MA20)***. Setelah pada Kamis (`12 Nov`) IHSG melonjak `+2,66%` ke `5.250,90` dan menembus garis `MA20` untuk pertama kalinya sejak *flash crash* Oktober 2026, hari ini IHSG melanjutkan reli **`+1,78%` (+93,51 poin)** ke level **5.344,41**.

### Tabel Evolusi Indikator Teknikal IHSG (`^JKSE`)

| Tanggal | Close | Perubahan 1H | Intraday Low – High | MA20 (Deviasi) | MA50 (Deviasi) | RSI(14) | MACD Hist | Status Rezim |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **03 Nov 2026** | 4.904,29 | -3,78% | 4.895,60 – 5.143,58 | 5.481,73 (-10,53%) | 6.036,66 (-18,76%) | 25,75 | -26,82 | Defensive / Re-test Low |
| **06 Nov 2026** | 5.050,43 | +0,40% | 4.925,10 – 5.050,43 | 5.318,16 (-5,03%) | 5.947,76 (-15,09%) | 33,51 | -1,76 | Transisi Awal Rebound |
| **09 Nov 2026** | 5.073,77 | +0,46% | 5.027,96 – 5.105,83 | 5.275,04 (-3,82%) | 5.918,73 (-14,28%) | 34,77 | **+9,77** | Bullish MACD Crossover |
| **10 Nov 2026** | 5.125,73 | +1,02% | 5.075,64 – 5.160,54 | 5.235,03 (-2,09%) | 5.889,24 (-12,96%) | 37,60 | +22,29 | Akumulasi Sektor Energi |
| **11 Nov 2026** | 5.115,04 | -0,21% | 5.086,02 – 5.144,79 | 5.193,63 (-1,51%) | 5.859,63 (-12,71%) | 37,24 | +30,72 | Higher Low Konsolidasi |
| **12 Nov 2026** | 5.250,90 | **+2,66%** | 5.114,80 – 5.250,90 | 5.162,99 (**+1,70%**) | 5.831,29 (-9,95%) | 44,48 | +45,43 | **Breakout Resmi > MA20** |
| **13 Nov 2026** | **5.344,41** | **+1,78%** | **5.215,15 – 5.361,94** | **5.170,95 (+3,35%)** | **5.805,44 (-7,94%)** | **48,86** | **+60,49** | **Bullish Markup (Hari ke-2 > MA20)** |

### Keluasan Pasar (*Market Breadth* 130 Saham Aktif — 13 Nov 2026)
- **Saham Naik (*Gainers*)**: **102 saham (78,5%)** — jauh melampaui syarat minimal protokol `GEMINI.md` (`> 50%`).
- **Saham Turun (*Losers*)**: **16 saham (12,3%)**.
- **Saham Stagnan (*Flat*)**: **12 saham (9,2%)**.
- **Saham Terkunci ARB**: Hanya 1 saham mikro-cap tidak likuid (`AGAR`, nilai transaksi Rp 3,28 Miliar); **0 saham LQ45/IDX30/Utama terkunci ARB**.
- **Top Penggerak Reli & Likuiditas (13 Nov 2026)**:
  - `BRMS`: Rp 348 (**+16,00%**, Nilai Trx Rp 507,76 Miliar)
  - `BRPT`: Rp 805 (**+7,33%**, Nilai Trx Rp 474,26 Miliar)
  - `VKTR`: Rp 354 (**+10,62%**, Nilai Trx Rp 323,13 Miliar)
  - `SINI`: Rp 10.975 (**+19,95%**, Nilai Trx Rp 230,61 Miliar)
  - `WIFI`: Rp 885 (**+19,59%**, Nilai Trx Rp 154,64 Miliar)
  - `ESSA`: Rp 545 (**+11,68%**, Nilai Trx Rp 115,05 Miliar)
  - `BUMI`: Rp 136 (**+7,09%**, sempat menyentuh High Rp 138 / +15,0% dari entri 11 Nov)
  - `ENRG`: Rp 670 (**+6,35%**, sempat menyentuh High Rp 675 / +14,4% dari entri 11 Nov)

---

## 2. Evaluasi Hasil Radar & Eksekusi Portofolio Hari Ini (13 Nov 2026)

### A. 6 Posisi yang Panen Profit & Auto-Close Hari Ini (`13 Nov 2026`)
Berkat implementasi **Auto-Close 3-Lapis Proteksi** pada `check_trailing_stop.py` dan `CheckTrailingStopAlertCommand.php`, 6 posisi dari sinyal Rabu–Kamis (`11–12 Nov`) yang mencapai puncak intraday hari ini langsung dikunci keuntungannya secara otomatis saat harga menarik diri (*pullback*) melewati ambang batas Trailing Stop:

| ID Trade | Saham | Strategi / Radar | Tanggal & Harga Beli | Puncak Intraday (13 Nov) | Harga Eksekusi Auto-Close | Return Net | Realisasi PnL (Rp) | Alasan Keluar |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **#883** | **DEWA** | `GABUNGAN` | 11 Nov @ Rp 234 | Rp 274 (+17,09% @ 14:15) | **Rp 268,52** | **+14,75%** | **+Rp 1.474.004** | Lapis 2: TS 2,0% |
| **#879** | **PACK** | `BOTTOM_TO_TOP` | 11 Nov @ Rp 306 | Rp 352 (+15,03% @ 11:15) | **Rp 343,20** | **+12,16%** | **+Rp 1.212.720** | Lapis 2: Lock 2,5% |
| **#893** | **RAJA** | `GABUNGAN` | 11 Nov @ Rp 520 | Rp 585 (+12,50% @ 12 Nov) | **Rp 573,30** | **+10,25%** | **+Rp 1.023.360** | Lapis 2: TS 2,0% |
| **#886** | **BRPT** | `GABUNGAN` | 12 Nov @ Rp 750 | Rp 825 (+10,00% @ 14:45) | **Rp 808,50** | **+7,80%** | **+Rp 778.050** | Lapis 2: TS 2,0% |
| **#885** | **BRPT** | `GABUNGAN` | 11 Nov @ Rp 765 | Rp 825 (+7,84% @ 14:45) | **Rp 808,50** | **+5,69%** | **+Rp 565.500** | Lapis 2: TS 2,0% |
| **#884** | **DEWA** | `GABUNGAN` | 12 Nov @ Rp 258 | Rp 274 (+6,20% @ 14:15) | **Rp 268,52** | **+4,08%** | **+Rp 407.124** | Lapis 2: TS 2,0% |
| **TOTAL** | **6 Trade** | **100% Win Rate** | — | — | — | **+9,12% Avg** | **+Rp 5.460.758** | **Terkunci Otomatis** |

### B. 9 Posisi Terbuka (*Open Floating Profit*) yang Masih Hold (Pullback < 2,0%)
Seluruh posisi dari `10–12 Nov` yang belum menyentuh batas *pullback* 2,0% dari puncak tertingginya tetap dipertahankan (*let winners run*) dengan proteksi Trailing Stop ketat:

| ID Trade | Saham | Strategi / Radar | Entry Date & Price | Puncak Intraday | Harga Close (13 Nov) | Floating Return | Pullback dari Peak | Level Trailing Stop Aktif |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **#880** | **ENRG** | `GABUNGAN` | 11 Nov @ Rp 590 | Rp 675 (+14,41%) | **Rp 670** | **+13,56%** | 0,74% (< 2,0%) | **Rp 661,50** |
| **#881** | **BUMI** | `GABUNGAN` | 11 Nov @ Rp 120 | Rp 138 (+15,00%) | **Rp 136** | **+13,33%** | 1,45% (< 2,0%) | **Rp 135,24** |
| **#888** | **PTRO** | `GABUNGAN` | 11 Nov @ Rp 2.250 | Rp 2.550 (+13,33%) | **Rp 2.540** | **+12,89%** | 0,39% (< 2,0%) | **Rp 2.499,00** |
| **#878** | **BUMI** | `BOTTOM_REBOUND` | 11 Nov @ Rp 123 | Rp 138 (+12,20%) | **Rp 136** | **+10,57%** | 1,45% (< 2,0%) | **Rp 135,24** |
| **#882** | **BUMI** | `GABUNGAN` | 12 Nov @ Rp 127 | Rp 138 (+8,66%) | **Rp 136** | **+7,09%** | 1,45% (< 2,0%) | **Rp 135,24** |
| **#891** | **ENRG** | `GABUNGAN` | 12 Nov @ Rp 630 | Rp 675 (+7,14%) | **Rp 670** | **+6,35%** | 0,74% (< 2,0%) | **Rp 661,50** |
| **#889** | **PTRO** | `GABUNGAN` | 12 Nov @ Rp 2.430 | Rp 2.550 (+4,94%) | **Rp 2.540** | **+4,53%** | 0,39% (< 2,0%) | **Rp 2.499,00** |
| **#877** | **TINS** | `BOTTOM_TO_TOP` | 10 Nov @ Rp 3.550 | Rp 3.690 (+3,94%) | **Rp 3.650** | **+2,82%** | 1,08% (< 2,5%) | **Rp 3.597,75** |
| **#895** | **TINS** | `BOTTOM_TO_TOP` | 11 Nov @ Rp 3.600 | Rp 3.690 (+2,50%) | **Rp 3.650** | **+1,39%** | 1,08% (SL Rp 3.492) | Aktif setelah +3,0% |

---

## 3. Radar yang Berhasil Kita Pick Sore Hari Ini (Jumat, 13 Nov 2026)

Berikut adalah jabaran lengkap sinyal yang berhasil ditangkap oleh **5 Mesin Radar Sentimena** pada penutupan Jumat, `13 November 2026` (untuk posisi berjalan & peluang Senin, `16 November 2026`):

### 1. Radar `BOTTOM-REBOUND` (Konfirmasi Pantul $\ge +5\%$ dari Dasar 10 Hari)
- **Pick Resmi Hari Ini (`#894 BUMI`)**:
  - **Trigger**: Kamis, `12 Nov 2026` (Titik bawah 10 hari = `Rp 115`, batas konfirmasi `+5%` = `Rp 120,75`, ditembus kuat).
  - **Eksekusi Entry**: Jumat, `13 Nov 2026` @ **`Rp 136`** (`SL Rp 131,24`, Trailing Stop `2,0%` dari puncak).

### 2. Radar `GABUNGAN` (Drawdown Bounce `dd_20d <= -20%` & `ret_2d <= -5%` dalam Rezim Uptrend)
- **3 Pick Resmi Masuk Trade Journal Sore Ini (`13 Nov 2026`)**:
  1. **`#892 ENRG` (`GABUNGAN - drawdown`)**: Entry **`Rp 670`** | `SL Rp 646,55` (`-3,5%`). Didukung katalis positif temuan minyak *Malacca Strait* dan tren *higher high* harian (`590 ➔ 630 ➔ 670`). Juga mencetak **Peringatan Dini H-1 (`heads_up_alerts #106`)** untuk Senin (`dd_20d = -23,86%`).
  2. **`#890 PTRO` (`GABUNGAN - drawdown`)**: Entry **`Rp 2.540`** | `SL Rp 2.451,10` (`-3,5%`). Reli akumulasi pasca pembalikan dari dasar `Rp 2.010`.
  3. **`#887 BRPT` (`GABUNGAN - ganda`)**: Entry **`Rp 805`** | `SL Rp 776,82` (`-3,5%`). Rebound teknikal `+7,33%` hari ini dengan nilai transaksi Rp 474,26 Miliar; mencetak **Peringatan Dini H-1 (`heads_up_alerts #105`)** (`dd_20d = -45,79%`).

### 3. Radar `SELF_RADAR_V1` (Momentum Breakout Kuat: `RSI14 >= 60`, `ret_5d >= +5%`, `dd_20d >= -5%`)
- **Juara #1 Sore Ini (`SelfRadarSignalLog #78`)**:
  - **`NSSS` (Nusantara Sawit Sejahtera Tbk.) @ `Rp 665`** (`+10,83%` hari ini):
    - `RSI(14)`: **62,24** ($\ge 60$)
    - `Return 5 Hari`: **+30,39%** ($\ge +5\%$)
    - `Drawdown 20 Hari`: **0,00%** (*Breakout 20-Day High* baru!)
    - `Composite Score`: **30,62** | Aturan Exit: *Trailing Stop 1,0% aktif Senin, 16 Nov pukul 09:30 WIB*.

### 4. Radar `BSJP` (Beli Sore Jual Pagi — Ledakan Volume $\ge 1,5\times$ & Bullish Candle)
Dari 10 saham yang terdeteksi scanner `trade:scan-bsjp` pada `2026-11-13`, berikut adalah **4 Pick Terbaik** setelah disaring dengan **Filter Likuiditas Transaksi**:
1. **`ESSA` (Surya Esa Perkasa Tbk.) — 🎯 `Sweetspot Institusi Terbaik`**:
   - Harga Close: **`Rp 545 (+11,68%)`** | Open: `Rp 494` | High: `Rp 550` (tutup sangat dekat *high*).
   - **Volume Spike**: **`2,94x`** lipat rata-rata kemarin | **Nilai Transaksi**: **`Rp 115,05 Miliar`** (likuiditas institusi sangat tebal).
2. **`SINI` (Singaraja Putra Tbk.) — 🚀 `Super Rocket Marubozu`**:
   - Harga Close: **`Rp 10.975 (+19,95%)`** | Open: `Rp 9.450` | High: `Rp 10.975` (*Close == High*, tanpa ekor atas).
   - **Volume Spike**: **`2,91x`** | **Nilai Transaksi**: **`Rp 230,61 Miliar`**.
3. **`NSSS` (Nusantara Sawit Sejahtera Tbk.) — 🎯 `Dual-Radar Confirmation`**:
   - Harga Close: **`Rp 665 (+10,83%)`** | **Volume Spike**: **`2,75x`** | Terkonfirmasi ganda oleh `SELF_RADAR_V1` (#1) dan `BSJP Sweetspot`.
4. **`HRUM` (Harum Energy Tbk.) — 🎯 `Sweetspot Komoditas`**:
   - Harga Close: **`Rp 720 (+4,35%)`** | Open: `Rp 695` | **Volume Spike**: **`2,75x`** | **Nilai Transaksi**: **`Rp 13,75 Miliar`**.

### 5. Radar `DIP5_WICK` (Pantulan Ekor Bawah $\ge 1\%$ untuk Senin, 16 Nov 2026)
Hasil pemindaian rumus `DIP5_WICK` pada penutupan Jumat (`13 Nov 2026`) memisahkan saham yang terkoreksi intraday menjadi 2 skenario:
- **Skenario A (`Intraday Low <= -4,5%` DAN `Lower Wick >= 1,0%` ➔ Peluang Rebound Senin)**:
  1. **`RAJA`**: Sempat dibanting ke Intraday Low `Rp 510 (-4,67% vs Prev Rp 535)`, namun diserap masif hingga tutup di **`Rp 530 (-0,93%)`** dengan **`Lower Wick = +3,92%`** dan nilai transaksi **`Rp 81,35 Miliar`**.
  2. **`BREN`**: Intraday Low `Rp 2.120 (-5,78% vs Prev Rp 2.250)`, memantul ke **`Rp 2.160 (-4,00%)`** dengan **`Lower Wick = +1,89%`** dan nilai transaksi **`Rp 80,58 Miliar`**.
  3. **`TEBE`**: Intraday Low `Rp 1.590 (-4,50%)`, ditarik kembali ke **`Rp 1.660 (-0,30%)`** dengan **`Lower Wick = +4,40%`** (Nilai Trx `Rp 20,54 Miliar`).
  4. **`IRSX`** (`Low -4,90%`, `Wick +6,19%`, tutup hijau `+0,98%` @ `Rp 206`) & **`ASLI`** (`Low -4,67%`, `Wick +6,86%`, tutup hijau `+1,87%` @ `Rp 218`).
- **Skenario B (`Close == Low`, `Lower Wick = 0,00%` ➔ WAJIB HINDARI / TUNGGU FLUSH HARI KE-2)**:
  - **`AGAR`** (`-6,84%`, `Close = Low = Rp 1.635`, `Wick 0%`) dan **`CSMI`** (`-6,59%`, `Close = Low = Rp 340`, `Wick 0%`). Sesuai hukum Skenario B, saham yang terkunci tanpa ekor bawah memiliki probabilitas 74%–85% lanjut *flush* `-4%` di pagi hari berikutnya.

---

## 4. Kodifikasi Rumus Matematis & Pola Kuantitatif Sentimena

Agar seluruh temuan riset ini menjadi standar permanen yang mudah direproduksi, berikut adalah **4 Rumus Utama** yang telah teruji secara statistik (*Out-of-Sample 4 Tahun* + *Intraday 15-Menit*):

### Rumus 1: Sistem 3-Lapis Proteksi (*Auto-Close Exit Engine*)
Setiap posisi terbuka dievaluasi terhadap bar intraday 15-menit setelah tanggal beli (`date > entry_date`):

1. **Lapis 1 — Hard Stop Loss (`-3,5%` Umum / `-3,0%` Bottom-to-Top)**:
   $$\text{Stop Loss Price} = \text{Entry Price} \times (1 - s), \quad s \in \{0,035,\; 0,030\}$$
   Jika $\text{Price}_{\text{now}} \le \text{Stop Loss Price}$, sistem otomatis mengeksekusi `stop_loss` tanpa kompromi (mencegah *averaging down*).

2. **Lapis 2 — Trailing Stop dari Puncak Intraday (`2,0%` Umum / `2,5%` Bottom-to-Top)**:
   $$\text{Peak}_t = \max\left(\text{Entry Price},\; \max_{\tau \in (t_{\text{entry}}, t]} \text{High}_{\tau, 15\text{m}}\right)$$
   $$\text{Pullback}_t = \frac{\text{Peak}_t - \text{Price}_{\text{now}}}{\text{Peak}_t}$$
   - Untuk strategi `GABUNGAN`, `MOMENTUM`, dan `BOTTOM_REBOUND`: aktif begitu $\text{Peak}_t > \text{Entry Price}$, trigger `trailing_stop` saat $\text{Pullback}_t \ge 2,0\%$ pada harga $\text{Exit Price} = \text{Peak}_t \times 0,98$.
   - Untuk strategi `BOTTOM_TO_TOP`: aktif setelah profit puncak mencapai $\ge +3,0\%$ ($\text{Peak}_t \ge \text{Entry Price} \times 1,03$), trigger `trailing_stop` saat $\text{Pullback}_t \ge 2,5\%$ pada harga $\text{Exit Price} = \text{Peak}_t \times 0,975$.

3. **Lapis 3 — Target Waktu Maksimal (`10 Hari Bursa`)**:
   Untuk strategi `GABUNGAN` dan `MOMENTUM`, jika $\text{Holding Days (BDay)} \ge 10$, posisi wajib dievaluasi/ditutup untuk mengamankan perputaran kas.

### Rumus 2: Hukum Pantulan Diskon Intraday (`DIP5_WICK` — Skenario A vs Skenario B)
Saat saham mengalami bantingan intraday $\ge 5\%$ dari penutupan sebelumnya:
$$\text{Intraday Drop} = \frac{\text{Low}_t - \text{Close}_{t-1}}{\text{Close}_{t-1}} \le -0,05, \qquad \text{Lower Wick} = \frac{\text{Close}_t - \text{Low}_t}{\text{Low}_t}$$

- **Skenario A ($\text{Lower Wick} \ge 1,0\%$ — Ada Serapan Bid Sore)**:
  - **Win Rate Pantulan Esok Hari ($\text{High}_{t+1} \ge \text{Close}_t \times 1,02$)**: **87,5% pada `BUMI`** ($n=48$, rata-rata max gain T+1 `+4,98%`, 3H `+8,50%`) dan **79,3% pada `DEWA`** ($n=58$, rata-rata max gain T+1 `+5,23%`, 3H `+8,77%`).
  - **Aturan Eksekusi**: Boleh *buy on pre-closing* (15:45–15:50 WIB) pada Hari ke-1.
- **Skenario B ($\text{Lower Wick} < 0,8\%$ atau $\text{Close}_t = \text{Low}_t$ — Dead Low / ARB Lock)**:
  - **Probabilitas Guyuran Lanjutan Pagi Esok (T+1 Flush)**: **84,6% pada `BUMI`** (rata-rata *flush* pagi `-4,38%`) dan **74,2% pada `DEWA`** (rata-rata *flush* pagi `-4,01%`). Membeli pada sore Hari ke-1 hampir pasti terkena Stop Loss `-3,5%` esok pagi.
  - **Aturan Eksekusi**: **DILARANG beli di Hari ke-1**. Tunggu guyuran panik pagi Hari ke-2 (`09:00–10:30 WIB`) di area `-3,5% s/d -5,0%` di bawah $\text{Close}_t$; setelah memantul dari $\text{Low}_{t+1}$, **Win Rate pantulan $\ge +3\%$ mencapai 100%** (`BUMI` avg `+10,38%`, `DEWA` avg `+12,91%`).

### Rumus 3: Filter Rezim Pasar (`Market Regime Master Switch`)
Setiap sinyal *mean-reversion* (`GABUNGAN`, `BOTTOM_REBOUND`, `BOTTOM_TO_TOP`) **HANYA** boleh dieksekusi jika:
$$\text{Regime\_OK}_t = \mathbb{I}\Big(\text{IHSG\_Ret}_{1d,t} > -1,0\%\Big) \;\land\; \neg\Big(\text{IHSG}_t < \text{MA20}_t \;\land\; \text{IHSG}_t < \text{MA50}_t \;\land\; \Delta\text{MACD\_Hist}_t < 0\Big)$$
Filter ini mengubah performa *Out-of-Sample (Holdout 30%)* `BUMI [GABUNGAN]` dari `-0,38%` (tanpa filter) menjadi **`+1,11%` per episode** (`PF 2,29`, Bootstrap CI95 Lower `+0,58%`) dan `DEWA [GABUNGAN]` menjadi **`+1,49%` di Holdout** (`PF 1,80`).

### Rumus 4: Matriks Spesifisitas Strategi per Karakter Emiten (*Strategy-Ticker Fit*)
Tidak semua saham cocok dengan strategi yang sama. Berdasarkan *backtest* 4 tahun (2022–2026) & stres-tes 15-menit:
- **`BUMI` & `DEWA`**: Unggul pada **`GABUNGAN` + Regime Filter** (`PF 2,29` & `1,80`), **`BOTTOM_REBOUND`** (`CI95 Lower +0,54%`), dan **`DIP5_WICK` Skenario A** (`WR 87,5%` & `79,3%`).
- **`PACK` & `TINS`**: Unggul pada **`BOTTOM_TO_TOP`** (`PACK` 4Y `PF 3,32`, Mean `+4,44%`, 60d-15m `100% WR`; `TINS` `+84,66%` kumulatif).
- **`ENRG`, `PTRO`, `RAJA`**: Unggul pada **`GABUNGAN`** (`ret_2d <= -5%` atau `dd_20d <= -20%` saat rezim pasar aman), namun `ENRG` tidak cocok menggunakan `BOTTOM_TO_TOP` (`PF 0,76`).
- **`DMAS`**: Unggul pada **`BOTTOM_REBOUND_CROSS`** (`PF 4,24`, Mean `+2,99%`) & **`GABUNGAN`** (`PF 6,35`, MaxDD `-3,9%`).
- **`NSSS`, `ESSA`, `SINI`**: Unggul pada **`SELF_RADAR_V1` & `BSJP`** saat terjadi ledakan volume $\ge 2,5\times$ dan $\text{RSI}_{14} \ge 60$ di atas `MA20`.

