# Sentimena Trading & Risk Management Protocol (Agent Memory)

File ini adalah memori permanen dan aturan disiplin trading untuk proyek **Sentimena**. Aturan ini wajib dibaca dan diacu pada setiap analisis pasar, scanner, evaluasi sinyal, dan rekomendasi trading.

---

## 1. Aturan Rezim Pasar (Market Regime Filter)

1. **Crash / Downtrend Guard**:
   - Jika IHSG turun `>= 1,0%` dalam 1 hari atau berada di bawah MA20 & MA50 dengan MACD histogram melebar negatif:
     - **STATUS: CASH IS KING / DEFENSIVE**.
     - **DILARANG** merekomendasikan entri baru pada strategi *Drawdown Bounce* atau *Bottom Rebound*.
     - Penurunan harga saham pada kondisi ini adalah *falling knife*, bukan pantulan diskon normal (*regime mismatch*).
2. **Kriteria Wajib Konfirmasi Rebound Pasar**:
   Pasar HANYA boleh dinyatakan mulai aman untuk dientri jika memenuhi 3 syarat konfirmasi:
   - **Candle Reversal IHSG**: Terbentuk *hammer*, *pin bar*, atau *bullish engulfing* ditutup hijau tebal dengan volume di atas rata-rata 20 hari.
   - **Market Breadth**: Jumlah saham naik (*gainers*) minimal `> 50%` dari total bursa aktif (bukan minoritas < 20%).
   - **Support Defense**: Support kunci (misal 5.800) terbukti bertahan minimal `2 hari bursa berturut-turut` tanpa mencetak titik terendah baru (*no new low*).

---

## 2. Aturan Disiplin Eksekusi Portofolio

1. **Larangan Keras Averaging Down (Martingale)**:
   - **DILARANG MENAMBAH LOT** pada posisi yang sedang mengalami *floating loss* ketika tren pasar masih turun.
   - Kasus nyata: Penambahan lot 4x pada ENRG (1.070, 1.060, 970, 950) menyebabkan akumulasi kerugian besar. Maksimal 1 posisi per setup.
2. **Disiplin Stop Loss**:
   - Setiap posisi yang menyentuh batas Cut Loss `-3,5%` (atau trailing stop yang terpicu) **WAJIB DIEKSEKUSI**.
   - Jangan pernah membiarkan kerugian kecil berubah menjadi kerugian fatal.
3. **Disiplin Target Waktu**:
   - Posisi strategi *Gabungan / Drawdown Bounce* memiliki batas waktu maksimal **10 hari bursa**.
   - Jika sudah mencapai hari ke-10 dan membukukan profit (seperti kasus SMGR @ 1.505 ➔ 1.590, profit +5,6%), **WAJIB TAKE PROFIT** untuk mengamankan kas.
4. **Metode Entri Rebound (Pyramiding)**:
   - Saat sinyal rebound terkonfirmasi valid:
     * Alokasikan maksimal `25% - 30%` kas untuk entri awal.
     * Tambahkan posisi hanya jika harga terbukti naik dan menembus *resistance* pertama.

---

## 3. Rumus Kuantitatif & Pola Rebound Tervalidasi (2022–2026 OOS + 15m Intraday)

1. **Sistem 3-Lapis Proteksi (*Auto-Close Exit Engine*)**:
   - **Lapis 1 (Hard Stop Loss)**: $\text{SL} = \text{Entry} \times (1 - s)$ dengan $s = 3,5\%$ untuk `GABUNGAN`/`MOMENTUM`/`BOTTOM_REBOUND` dan $s = 3,0\%$ untuk `BOTTOM_TO_TOP`. Wajib auto-close tanpa kompromi saat tersentuh.
   - **Lapis 2 (Trailing Stop dari Puncak Intraday 15m)**: $\text{Peak} = \max(\text{Entry}, \text{High}_{\text{intraday setelah hari beli}})$.
     * Strategi `GABUNGAN`/`MOMENTUM`/`BOTTOM_REBOUND`: aktif saat $\text{Peak} > \text{Entry}$, trigger auto-close saat $\text{Pullback} = (\text{Peak} - \text{Price}) / \text{Peak} \ge 2,0\%$ pada harga $\text{Peak} \times 0,98$.
     * Strategi `BOTTOM_TO_TOP`: aktif setelah profit puncak $\ge +3,0\%$, trigger auto-close saat $\text{Pullback} \ge 2,5\%$ pada harga $\text{Peak} \times 0,975$.
   - **Lapis 3 (Target Waktu)**: Maksimal `10 hari bursa` untuk `GABUNGAN` dan `MOMENTUM`.
2. **Hukum Pantulan Diskon $\ge 5\%$ (`DIP5_WICK`: Skenario A vs Skenario B)**:
   - Saat saham turun intraday $\text{Low}_t \le \text{Close}_{t-1} \times 0,95$:
     * **Skenario A ($\text{Lower Wick} = (\text{Close}_t - \text{Low}_t)/\text{Low}_t \ge 1,0\%$ — Ada Serapan Bid Sore)**: Win Rate pantulan esok hari ($\text{High}_{t+1} \ge +2\%$) mencapai **87,5% pada `BUMI`** (avg `+4,98%`, 3H `+8,50%`) dan **79,3% pada `DEWA`** (avg `+5,23%`, 3H `+8,77%`). Valid untuk *buy pre-closing* Hari ke-1.
     * **Skenario B ($\text{Lower Wick} < 0,8\%$ atau $\text{Close}_t = \text{Low}_t$ — Dead Low / ARB Lock)**: **84,6% (`BUMI`)** dan **74,2% (`DEWA`)** lanjut *flush* `-4,0% s/d -4,4%` pagi esoknya (rawan kena SL `-3,5%` jika beli di Hari ke-1). **DILARANG beli di Hari ke-1**; tunggu tangkapan *flush* pagi Hari ke-2 (Win Rate pantulan $\ge +3\%$ dari Low Hari ke-2 = **100%**).
3. **Matriks Spesifisitas Strategi per Emiten (*Strategy-Ticker Fit*)**:
   - `BUMI` & `DEWA`: `GABUNGAN` + Regime Filter (`PF 2,29` & `1,80`), `BOTTOM_REBOUND` (`CI95 Low +0,54%`), & `DIP5_WICK` Skenario A.
   - `PACK` & `TINS`: `BOTTOM_TO_TOP` (`PACK` 4Y `PF 3,32`, 60d-15m `100% WR`; `TINS` `+84,66%`).
   - `ENRG`, `PTRO`, `RAJA`: `GABUNGAN` (`ENRG` 4Y `PF 1,82`; hindari `BOTTOM_TO_TOP` pada `ENRG` karena `PF 0,76`).
   - `DMAS`: `BOTTOM_REBOUND_CROSS` (`PF 4,24`) & `GABUNGAN` (`PF 6,35`, MaxDD `-3,9%`).
   - `NSSS`, `ESSA`, `SINI`: `SELF_RADAR_V1` ($\text{RSI}_{14} \ge 60, \text{ret}_{5d} \ge +5\%, \text{dd}_{20d} \ge -5\%$) & `BSJP` ($\text{Vol Spike} \ge 2,5\times$).

---

## 4. Arsip Riset & Catatan Harian

- Laporan riset mendalam crash Oktober 2026 (Tahap 1 - Breakdown 5.800): `laravel-app/reports/market_regime_research_20261015.md`
- Laporan riset investigasi crash IHSG (-8,01%) & audit portofolio (Tahap 2): `laravel-app/reports/market_regime_research_20261016.md`
- Laporan riset kapitualasi & penembusan level psikologis 5.000 (Tahap 3): `laravel-app/reports/market_regime_research_20261019.md`
- Laporan proyeksi tanggal & skenario rebound IHSG pasca isu MSCI & ARB 7%: `laravel-app/reports/rebound_prediction_scenarios_20261020.md`
- Laporan riset rebound IHSG (+3,61%) & backtest entri Sesi 1 vs Sesi 2: `laravel-app/reports/market_regime_research_20261020.md`
- Laporan konfirmasi rebound IHSG (Support 5.000 teruji 2 hari) & eksekusi Tier 2: `laravel-app/reports/market_regime_research_20261021.md`
- Laporan breakout IHSG > MA20 (5.344,41), panen Auto-Close 3-Lapis (96,3% WR), & kodifikasi rumus kuantitatif: `laravel-app/reports/market_regime_research_20261113.md`
- Catatan histori trading dan evaluasi berkala: `laravel-app/docs/trading-log.md`


