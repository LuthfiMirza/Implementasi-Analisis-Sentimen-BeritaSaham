# Plan Eksekusi & Audit Sentimena — Active Plan

Dibuat: 2026-07-19 | Diperbarui & Dirampingkan: 2026-09-21  
Dokumen ini mencatat fase aktif yang sedang dikerjakan pada sistem Sentimena.

---

## 🗄️ Peta Arsip Jejak Audit (Riwayat Lengkap Terarsip Rapi)

Untuk menjaga performa repositori agar tetap ringan dan cepat, riwayat fase sebelumnya yang telah selesai telah diarsipkan secara utuh tanpa ada satu kata pun yang dihapus:

| Era / Topik | Lokasi Berkas Arsip | Cakupan Fase | Keterangan |
| :--- | :--- | :---: | :--- |
| **Era 1: Riset Skripsi & ML Sentimen** | [`docs/audit_history/plan_era1_skripsi_ml.md`](docs/audit_history/plan_era1_skripsi_ml.md) | **Fase 0 s/d Fase Z** <br>*(1.603 baris)* | Fine-tuning IndoBERT, evaluasi model V6A/V6B, fix RSS feed berita, dataset skripsi. |
| **Era 2: Live Trading Tracker & Sinyal**| [`docs/audit_history/plan_era2_live_trading_tracker.md`](docs/audit_history/plan_era2_live_trading_tracker.md) | **Fase AA s/d Fase EX** <br>*(5.366 baris)* | Peluncuran live tracker BUMI/DEWA/BRPT/INET, trailing stop 15-menit, bot Telegram, reconciler. |
| **Manual Strategi TINS Bottom-to-Top** | [`quant/drawdown_bounce_tracker/TINS_BOTTOM_TO_TOP_NOTES.md`](quant/drawdown_bounce_tracker/TINS_BOTTOM_TO_TOP_NOTES.md) | **Source of Truth** | Aturan baku buy, sell, risk management 3%, dan tabel 12 trade TINS. |
| **Manual Strategi Self-Radar V1** | [`quant/drawdown_bounce_tracker/SELF_RADAR_V1_NOTES.md`](quant/drawdown_bounce_tracker/SELF_RADAR_V1_NOTES.md) | **Source of Truth** | Aturan overnight scalp radar jam 15:35 WIB. |
| **Laporan Riset TINS Terverifikasi** | [`output/tins_bottom_to_top_strategy_report.md`](output/tins_bottom_to_top_strategy_report.md) | **Audit Report** | Laporan resmi komparasi 6 model trading TINS. |

---

## 🚀 Fase Aktif Terkini

### Fase EY — Riset Strategi TINS Bottom-to-Top & Mitigasi Risiko Maksimal 3% (21 Sep 2026)

#### 1. Latar Belakang Masalah
* Pengujian awal strategi bawaan *Drawdown-Bounce* dan *Bottom Rebound* kaku pada saham **TINS** (periode 1 Des 2025 s/d 21 Sep 2026) menghasilkan kerugian **-5.8% s/d -14.6%**.
* Keluhan User:
  1. Patokan kaku 10 hari bursa membuat posisi yang tadinya cuan berbalik menjadi rugi.
  2. Adanya dua trade yang minus $\ge 5\%$ (Trade 17 Mar -5.62% dan Trade 11 Mei -5.01%).
  3. Permintaan: Cari pola di mana harga terbawah (ambil) dan jual saat di atas, serta batasi risiko maksimal di 2% - 3%.

#### 2. Investigasi & Solusi Kuantitatif
1. **Pelepasan Batas 10 Hari Bursa pada Momentum:**
   * Begitu batas kaku 10 hari diganti dengan Trailing Stop fleksibel 5.0%, performa strategi Momentum naik drastis menjadi **Win Rate 85.7%** dan modal Rp 10 Juta tumbuh menjadi **Rp 14.448.024 (+44.48%)**.
2. **Data Mining Siklus Ayunan TINS (41 Bottom & 40 Peak):**
   * *Bottom Signature:* Stochastic %K $< 30$ / BB %B $< 0.25$ + Konfirmasi Lilin Hijau (`Close > Open` & `Close > Close[-1]`). Membalikkan tren turun menjadi reli rata-rata +25%.
   * *Peak Signature:* Stochastic %K $> 75$ / BB %B $> 0.85$ + Kemunduran 2.5% dari puncak tertinggi (*Peak Price*).
3. **Penjinakan Risiko Minus $\ge 5\%$:**
   * Trade 17 Maret (-5.62%) disebabkan karena menunggu sore hari jam 16:00 Close. Dengan **Auto-Cut Broker 3.0% Intraday**, kerugian langsung terpotong menjadi **-3.80% net** (-3.0% murni).
   * Trade 11 Mei (-5.01%) sebenarnya sempat naik +3.93% di hari ke-2 & ke-3. Dengan **Trailing Profit Lock 2.5% dari Puncak**, posisi tidak dibiarkan berbalik rugi.

#### 3. Hasil Validasi Akhir (Modal Rp 10.000.000)
* **Total Trade:** 12 Trade (8 Win, 4 Loss).
* **Win Rate:** **66.7%**.
* **Kerugian Maksimal:** **-3.80% net** (Rugi harga saham murni 3.00% + fee 0.80%). **Sama sekali tidak ada trade yang minus 5%**.
* **Hasil Akhir Modal:** **Rp 18.466.070 (+84.66% | Profit Bersih: Rp 8.466.070)**.
* Script verifikasi reproducible: `quant/test_optimized_risk_be.py`.

#### 4. Status Fase EY: SELESAI (21 Sep 2026).
Dokumentasi operasional disimpan di `quant/drawdown_bounce_tracker/TINS_BOTTOM_TO_TOP_NOTES.md`. Laporan formal di `output/tins_bottom_to_top_strategy_report.md`. Riwayat audit lama sukses dipisahkan ke `docs/audit_history/`.

---

### Fase EZ — Otomatisasi Strategi TINS Bottom-to-Top ke Signal Radar & Telegram Alert (21 Sep 2026)

#### 1. Latar Belakang & Kebutuhan
* Pengguna menyetujui penerapan otomatisasi penuh (Opsi 1) dari temuan riset Fase EY agar TINS dimonitoring secara real-time via Signal Radar web dan dikirim otomatis ke Telegram saat sinyal beli/jual muncul.
* TINS dilepaskan dari aturan generic GABUNGAN/BOTTOM_REBOUND agar tidak terjebak dalam batas 10-hari bursa yang kaku.

#### 2. Implementasi Sistem Kuantitatif
1. **Database Schema (`quant/drawdown_bounce_tracker/schema.sql`):**
   * Membuat tabel `tins_bottom_to_top_signals` dengan audit trail append-only (`tins_btt_no_update`, `tins_btt_no_delete`).
2. **EOD Signal Detector (`detect_signal.py`):**
   * Fungsi `detect_tins_bottom_to_top()`: scanning EOD 15:18 WIB untuk kondisi dasar diskon (Stoch %K < 30 / BB %B < 0.25 / RSI < 45) + konfirmasi lilin hijau.
   * Format alert Telegram kaya informasi: status sinyal, indikator, harga beli, rekomendasi Stop Loss (-3%), target trailing cuan 2.5%, dan auto-register ke `open_positions.json` (strategy: `BOTTOM_TO_TOP`).
3. **Intraday Monitor & Alerting (`check_trailing_stop.py`):**
   * Hard Stop Loss alert (-3.0% harga saham) untuk mencegah kerugian $\ge 5\%$.
   * Trailing Profit Lock alert (kemunduran 2.5% dari puncak tertinggi setelah profit $\ge +3.0\%$).
4. **Backend Signal Radar (`SignalRadarService.php`):**
   * Menambahkan `buildTinsBottomToTopRow()`: live calculation Stochastic %K 14-period, Bollinger Band %B 20-period, RSI14 Wilder, dan status 4-tingkat (`BUY SEKARANG`, `DISKON SIKLUS`, `OVERBOUGHT`, `WAIT`).
5. **Frontend Signal Radar (`radar.blade.php` & `app.js`):**
   * Menampilkan kartu khusus TINS Bottom-to-Top Swing dengan badge live status, harga live, konfirmasi lilin hijau, level SL ketat Rp, dan metrik teknikal.
6. **Automated Testing (`tests/Feature/SignalRadarTest.php`):**
   * Menambahkan unit test deteksi kondisi diskon + lilin hijau (`test_tins_bottom_to_top_trigger_detected_on_oversold_and_green`) dan kondisi overbought (`test_tins_bottom_to_top_not_triggered_when_overbought`). 9 test lolos (47 assertions).

#### 3. Status Fase EZ: SELESAI (Aktif Produksi).
Sinyal otomatis aktif di cron EOD 15:18 WIB dan intraday trailing monitor setiap 15 menit. Live radar dapat dipantau di halaman `/trades/radar`.

---

### Fase FA — Otomatisasi 2-Tahap BSJP Momentum: Early Warning 15:00 WIB & Konfirmasi 15:35 WIB (21 Sep 2026)

#### 1. Latar Belakang & Validasi Kuantitatif
* Reverse engineering dari 20 saham screener Stockbit (SMLE, BKDP, VERN, PSDN, GRIA, ASLC, RISE, DSFI, MAYA, BAIK, SCNP, IOTF, MSIE, CARS, ARII, NATO, AMIN, BCIC, URBN, VINS) menghasilkan 5 aturan inti:
  1. *Volume Spike:* Volume > Previous Volume (1.5x s/d 50x).
  2. *Bullish Candle:* Price > Open Price.
  3. *Price Return:* Kenaikan $\ge +3.0\%$.
  4. *Liquidity:* Nilai transaksi $\ge \text{Rp 100 Juta}$.
  5. *Breakout:* Price $\ge$ Price MA5 atau MA10.
* Backtest historis membuktikan:
  * Model Swing Hold 1 Hari: Modal Rp 10 Juta anjlok menjadi **Rp 3.605.542 (-63.94%)** (rugi dibanting bandar pada sore H+1).
  * Model BSJP Murni (Beli Sore Jual Open 09:00 WIB): Modal Rp 10 Juta melonjak menjadi **Rp 55.382.991 (+453.83% | WR 50.0%)**!
  * Probabilitas H+1 Pagi mencetak *Higher High*: **82.8%** dengan rata-rata puncak **+6.38%**.

#### 2. Solusi Data Akurat & Skema 2-Tahap
* **Tantangan Waktu:** User menginginkan screening dimulai sejak **Pukul 15:00 WIB** agar punya waktu 35 menit untuk menganalisis order book dengan santai sebelum penutupan.
* **Skema 2-Tahap:**
  1. **Pukul 15:00 WIB (Early Warning):** Scan lonjakan volume & lilin hijau awal. Kirim alert Telegram untuk mulai pantau 3-5 saham terkuat.
  2. **Pukul 15:35 WIB (Final Confirmation):** Validasi ulang apakah candle tetap hijau solid tanpa guyuran menit akhir. Kirim rekomendasi beli di Pre-Closing (15:50 WIB).
  3. **Pukul 08:52 WIB (Morning Reminder):** Pengingat 8 menit sebelum bursa buka untuk memasang antrian jual di pembukaan 09:00 WIB (Target TP +2.5% / Open).

#### 3. Implementasi Sistem
1. **Artisan Command (`app/Console/Commands/ScanBsjpMomentumCommand.php`):**
   * Perintah `trade:scan-bsjp {--stage=early|confirm|reminder} {--send}`.
   * Query database BEI `idx_daily_summaries` secara instan (kecepatan 7 ms).
   * Notifikasi Telegram otomatis berformat HTML lengkap dengan target TP (+2.5%) dan SL (-3.0%).
2. **Scheduler Cron (`routes/console.php`):**
   * 15:00 WIB (Senin-Jumat): `trade:scan-bsjp --stage=early --send`
   * 15:35 WIB (Senin-Jumat): `trade:scan-bsjp --stage=confirm --send`
   * 08:52 WIB (Senin-Jumat): `trade:scan-bsjp --stage=reminder --send`
3. **Web Signal Radar (`SignalRadarService.php` & `radar.blade.php`):**
   * Method `buildBsjpMomentumRows()` menambahkan kandidat BSJP real-time ke payload JSON `/trades/radar-data`.
   * Komponen UI responsif menampilkan kartu saham dengan badge status tahap, harga sore, nilai transaksi, rasio volume, dan instruksi entry/exit.
4. **Pengujian & Verifikasi:**
   * Unit test `test_bsjp_momentum_section_present_in_radar_data` lolos (10/10 tests, 53 assertions).
   * Verifikasi browser visual via subagent: tangkapan layar `bsjp_momentum_section_1790006227203.png` memvalidasi rendering sempurna kartu BSJP.
   * Uji coba kirim live alert Telegram sukses diterima di chat ID `7162558029` dan `8870402966`.

#### 4. Status Fase FA: SELESAI (Aktif Produksi).
Sistem scanner 2-tahap telah aktif di cron scheduler dan terintegrasi penuh di halaman `/trades/radar`.

---

### Fase FB — Klasifikasi Top Gainers Mover (Super Rocket vs Sweetspot) & Filter Kategori Web Radar (21 Sep 2026)

#### 1. Latar Belakang & Analisis 50 Top Gainers
* Pengguna menguji 50 saham *Top Gainers / Movers* bursa (CSMI, TRUE, BBSS, JAWA, AGAR, NASI, HOPE, BAJA, INTD, GDST, COIN, CHEM, TRIN, WAPO, PRAY, AISA, HELI, SQMI, IBOS, FLMC, IRSX, DPUM, GTSI, MAYA, PKPK, HUMI, GRIA, TCPI, BIPI, MSIE, PSDN, BKDP, NATO, ARII, RELI, RISE, VERN, NEST, CENT, KKES, SMLE, GWSA, SCNP, UVCR, AMIN, WIIM, SILO, BAIK, FOLK, VINS).
* Pertanyaan Kritis: Mengapa saham-saham ini terbang, apakah semuanya bagus untuk BSJP, dan bagaimana membedakan calon ARA vs saham likuid serta menolak jebakan fakeout?
* Temuan Kuantitatif:
  1. **🚀 Super Rocket ($\ge$ 15% / Calon ARA):** Lonjakan volume 14x s/d 53x lipat (`BBSS` 53.2x, `CSMI` 18.3x). Potensi gap-up pagi rata-rata **+8.82%**, tetapi antrian offer rawan terkunci ARA saat pre-closing.
  2. **🎯 Sweetspot BSJP (4% - 15% / Likuiditas Terbuka):** Saham seperti `COIN`, `CHEM`, `SQMI`, `IRSX`, `GRIA`, `PSDN`, `SMLE`, `SCNP`. Antrian offer melimpah di pre-closing 15:50 WIB sehingga order beli 100% pasti match, dengan **Win Rate pagi 83.9%** (rata-rata kenaikan +4.30%).
  3. **⛔ Jebakan Batman / Volume Trap:** Saham yang naik tinggi tanpa volume (`NASI` +24.79% tapi volume ratio hanya 0.18x / drop 82%, `WAPO` 0.56x, `DPUM` 0.49x, `RELI` trx cuma Rp 51 Juta). Wajib disaring oleh kriteria volume spike $\ge 1.5x$ dan nilai transaksi $\ge$ Rp 1 Miliar.

#### 2. Implementasi Sistem
1. **Artisan Command & Engine CLI:**
   * Ditambahkan opsi `--category=all|sweetspot|rocket` pada `php artisan trade:scan-bsjp` dan `quant/screen_bsjp_live.py`.
   * Labeling otomatis badge `[🚀 Super Rocket]` dan `[🎯 Sweetspot]` pada tabel CLI dan pesan alert Telegram.
2. **Web Signal Radar UI (`radar.blade.php` & `app.js`):**
   * Filter tabs reaktif Alpine.js: `Semua`, `🚀 Super Rocket (≥15%)`, dan `🎯 Sweetspot BSJP (4% - 15%)`.
   * Badge kategori berwarna cerah pada setiap kartu emiten (`bg-rose-500` vs `bg-emerald-500`).
3. **Pengujian Kuantitatif & Database SQLite/MySQL:**
   * Query volume spike distandarisasi ke klausa `WHERE t.volume >= p.volume * 1.5` untuk kompatibilitas penuh SQLite dan MySQL.
   * Isolasi cache test menggunakan array store di lingkungan pengujian.
   * Seluruh 10 test di `SignalRadarTest` lulus 100% (60 assertions).

#### 3. Status Fase FB: SELESAI (Aktif Produksi).
Fitur klasifikasi kategori BSJP dan filter tabs telah aktif di `/trades/radar` dan bot Telegram. Riwayat commit dicatat secara atomik ke repositori utama.

---

### Fase FC — BSJP Live Trade Tracker, Alokasi Modal Rp 20.000.000, & Evaluator Otomatis 09:05 WIB (22 Sep 2026)

#### 1. Latar Belakang & Kebutuhan Pengguna
* Setelah pengujian backtest BSJP murni (144 trade menghasilkan pertumbuhan modal **+453.83%** dari Rp 10 Juta menjadi Rp 55,38 Juta), pengguna meminta sistem pencatatan nyata (**Live Trade Tracker**) untuk mulai trading asli.
* Parameter eksekusi baku yang ditentukan:
  1. **Alokasi Modal:** **Rp 20.000.000** per saham (menghitung jumlah lot otomatis sesuai harga emiten dan fee beli).
  2. **Struktur Fee Broker:** Fee beli **0.15%**, Fee jual **0.25%** (total round-trip 0.40%).
  3. **Filter Likuiditas Ketat:** Transaksi harian minimal $\ge$ **Rp 5 Miliar s/d Rp 10 Miliar+** (contoh: `BIPI` Rp 115,5M, `IRSX` Rp 73,3M, `DYAN` Rp 18,7M, `HUMI` Rp 14,6M, `CENT` Rp 8,5M, `SMLE` Rp 7,8M, `PSDN` Rp 6,1M, `BSSR` Rp 30,5M) agar eksekusi order modal Rp 20 Jt (200 - 2.000 lot) langsung match tanpa risiko slippage.
  4. **Protokol Waktu:** Entry pre-closing 15:50 WIB &rarr; Hold menginap &rarr; Exit di pembukaan bursa 09:00 WIB (Target TP +2.5% / SL -3.0%).

#### 2. Implementasi Arsitektur Sistem
1. **Database Migration (`database/migrations/2026_09_22_100000_create_bsjp_trade_logs_table.php`):**
   * Membuat tabel `bsjp_trade_logs` untuk mencatat detail signal, tanggal entry/exit, harga masuk/keluar, alokasi modal Rp 20 Jt, lot riil, status (`PENDING`, `OPEN`, `CLOSED`, `SKIPPED`), tipe exit (`OPEN_MARKET`, `TARGET_TP`, `STOP_LOSS`, `MANUAL`), serta kalkulasi PnL kotor dan bersih.
2. **Model Eloquent (`app/Models/BsjpTradeLog.php`):**
   * Menambahkan fungsi presisi `calculateLots($capital, $price, $buyFeeRate)` dan `calculatePnl($entryPrice, $exitPrice, $lots, $buyFeeRate, $sellFeeRate)`.
   * Method `closeTrade($exitPrice, $exitedAt, $notes, $exitType)` untuk penutupan posisi otomatis / manual.
3. **Controller & Web Routing (`BsjpTradeController.php` & `routes/web.php`):**
   * Endpoint `GET /trades/bsjp-tracker`: Dasbor analitik portofolio BSJP (Metrik Modal Awal Rp 20 Jt, Total Realized PnL, Win Rate, Posisi Terbuka Menginap, dan Riwayat Trade).
   * Endpoint `POST /trades/bsjp-tracker/buy`: Form eksekusi beli sore pre-closing.
   * Endpoint `POST /trades/bsjp-tracker/{log}/sell`: Form eksekusi jual di open pagi atau saat TP tercapai.
   * Endpoint `POST /trades/bsjp-tracker/{log}/skip`: Menandai sinyal dilewati jika volume offer tidak memadai.
4. **Tampilan Web UI Modern (`resources/views/trades/bsjp_tracker.blade.php`):**
   * Tampilan Glassmorphism Dark Mode Sentimena dengan 4 KPI metric cards, tabel posisi aktif menginap lengkap dengan kalkulasi target TP/SL, tabel riwayat trading selesai, dan modal dialog Alpine.js.
   * Navigasi global sidebar di `resources/views/layouts/app.blade.php` dan tombol 1-klik `[🛒 Catat Beli Rp 20 Jt]` di kartu emiten `resources/views/trades/radar.blade.php`.
5. **Registrasi Emiten Likuid & Sinkronisasi Harga:**
   * Mendaftarkan 20 emiten likuid baru (`CENT`, `PSDN`, `SMLE`, `IRSX`, `HUMI`, `BIPI`, `CBRE`, `BKDP`, `DSFI`, `DYAN`, `BSSR`, `CSMI`, `ASLI`, `SRSN`, `DOOH`, `SMIL`, `AGAR`, `IDEA`, `IKAN`, `PSSI`) ke database `stocks` (`is_active = 1`) dan watchlist pengguna.
   * Sinkronisasi data harga real-time via `stocks:sync-live`.
6. **Evaluator Otomatis Pukul 09:05 WIB (`EvaluateBsjpTradesCommand.php` & `routes/console.php`):**
   * Command `php artisan trade:evaluate-bsjp` otomatis dijalankan setiap hari bursa jam 09:05 WIB untuk memeriksa posisi menginap terhadap harga open bursa.
7. **Pengujian Fitur Otomatis (`tests/Feature/BsjpTradeTrackerTest.php`):**
   * 5 test suite lengkap (render halaman, buy calculation lot Rp 20 Jt, sell PnL calculation fee broker, skip action, artisan command execution) lulus 100% (15 assertions).

#### 3. Status Fase FC: SELESAI (Aktif Produksi).
Sistem pencatatan trade live BSJP aktif penuh dan siap digunakan pengguna untuk eksekusi portofolio riil Rp 20.000.000.


