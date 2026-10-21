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

## 3. Arsip Riset & Catatan Harian

- Laporan riset mendalam crash Oktober 2026 (Tahap 1 - Breakdown 5.800): `laravel-app/reports/market_regime_research_20261015.md`
- Laporan riset investigasi crash IHSG (-8,01%) & audit portofolio (Tahap 2): `laravel-app/reports/market_regime_research_20261016.md`
- Laporan riset kapitualasi & penembusan level psikologis 5.000 (Tahap 3): `laravel-app/reports/market_regime_research_20261019.md`
- Laporan proyeksi tanggal & skenario rebound IHSG pasca isu MSCI & ARB 7%: `laravel-app/reports/rebound_prediction_scenarios_20261020.md`
- Laporan riset rebound IHSG (+3,61%) & backtest entri Sesi 1 vs Sesi 2: `laravel-app/reports/market_regime_research_20261020.md`
- Laporan konfirmasi rebound IHSG (Support 5.000 teruji 2 hari) & eksekusi Tier 2: `laravel-app/reports/market_regime_research_20261021.md`
- Catatan histori trading dan evaluasi berkala: `laravel-app/docs/trading-log.md`


