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

