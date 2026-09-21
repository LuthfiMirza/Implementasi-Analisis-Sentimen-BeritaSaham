# TINS Bottom-to-Top Strategy Notes

Dokumen ini adalah **Source of Truth (Buku Manual Resmi)** untuk strategi **Bottom-to-Top (Ambil di Dasar, Jual di Pucuk)** pada saham **TINS**.

---

## 1. Status & Ringkasan Performa

- **Status:** Validated Strategy (Kandidat Unggulan Khusus Saham Komoditas Volatile).
- **Periode Uji:** 1 Desember 2025 s/d 21 September 2026 (Data Riil Bursa).
- **Modal Awal:** Rp 10.000.000.
- **Hasil Akhir Modal:** **Rp 18.466.070 (+84.66% | Profit Bersih: Rp 8.466.070)**.
- **Total Trade:** 12 Trade (8 Menang, 4 Kalah).
- **Win Rate:** **66.7%**.
- **Kerugian Terburuk (Max Drawdown Trade):** **-3.80% net** (Rugi harga murni -3.00% + fee broker 0.80%).
- **Biaya Transaksi Diperhitungkan:** 0.80% round-trip (fee beli + fee jual + pajak).

---

## 2. Filosofi Strategi

TINS adalah saham komoditas tambang (*cyclical asset*) dengan Average True Range (ATR 14) tinggi sekitar **6.19%**. 
- Strategi *Drawdown-Bounce* kaku gagal di TINS (-12.84%) karena sering menangkap pisau jatuh saat fase downtrend.
- Strategi dengan patokan kaku *tahan 10 hari bursa* gagal karena membiarkan posisi yang tadinya sudah untung (+4% s/d +15%) melorot kembali menjadi rugi.
- **Strategi Bottom-to-Top** memecahkan masalah ini dengan dua prinsip:
  1. **Hanya beli jika dasar sudah terkonfirmasi memantul** (tidak beli saat candle masih merah).
  2. **Kunci untung dinamis begitu harga mencapai puncak lokal** (tidak menunggu 10 hari bursa).

---

## 3. Aturan Baku Eksekusi

### A. Syarat Beli (BUY Trigger)
Deteksi dilakukan pada penutupan sesi 2 (pukul 15:00–15:15 WIB). Posisi dibuka jika **KEDUA** syarat berikut terpenuhi:
1. **Osilator Diskon (Oversold):**
   - `Stochastic %K < 30` ATAU `Bollinger Band %B < 0.25` ATAU `RSI14 < 45`.
2. **Konfirmasi Lilin Rebound (Wajib):**
   - `Close > Open` (Lilin Hijau) **DAN** `Close > Close Kemarin` (Membuktikan pembeli mulai masuk membalikkan arah).

### B. Syarat Jual (SELL & Risk Management)
1. **Batas Risiko Keras (Hard Stop Loss 3.0%):**
   - Pasang order Stop Loss otomatis di aplikasi broker di level: `Harga Beli * 0.97` (-3.0%).
   - Jika pasar anjlok intraday, posisi terpotong otomatis di angka 3.0% (net fee -3.80%). **Sama sekali tidak ada trade yang rugi 5%**.
2. **Kunci Untung Dinamis (Trailing Profit Lock 2.5%):**
   - Begitu harga saham pernah mencatatkan kenaikan $\ge +3.0\%$ dari harga beli, level tertinggi dicatat sebagai *Peak Price*.
   - Jika harga kemudian mundur $\ge 2.5\%$ dari *Peak Price*, sistem **WAJIB JUAL** untuk mengamankan keuntungan.
3. **Puncak Jenuh Beli (Overbought Exit):**
   - Jika `Stochastic %K > 75` atau `Bollinger Band %B > 0.85` atau `RSI14 > 65` dan muncul tanda lilin pembalikan (`Close < Open`), posisi ditutup di penutupan.

---

## 4. Rincian 12 Trade Historis (1 Des 2025 – 21 Sep 2026)

| # | Tanggal Beli | Harga Beli | Tanggal Jual | Harga Jual | Net PnL (%) | Saldo Modal | Alasan Keluar |
| :-: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| 1 | 11 Des 2025 | Rp 3.060 | 15 Des 2025 | Rp 3.550 | **+15.21%** | Rp 11.521.307 | Kunci Profit (Mundur 2.5% dari Puncak 3.700) |
| 2 | 02 Jan 2026 | Rp 3.140 | 07 Jan 2026 | Rp 3.530 | **+11.62%** | Rp 12.860.127 | Kunci Profit (Mundur 2.5% dari Puncak 3.630) |
| 3 | 03 Feb 2026 | Rp 3.220 | 05 Feb 2026 | Rp 3.240 | -0.18% | Rp 12.837.123 | Kunci Profit (Keluar cepat di titik impas) |
| 4 | 09 Feb 2026 | Rp 3.160 | 12 Feb 2026 | Rp 4.190 | **+31.79%** | Rp 16.918.678 | **Mega Cuan**: Tangkap dasar 3.160, jual puncak 4.190 |
| 5 | 17 Mar 2026 | Rp 3.320 | 25 Mar 2026 | Rp 3.220 | **-3.80%** | Rp 16.275.768 | Stop Loss Auto 3.0% terpotong rapi |
| 6 | 27 Mar 2026 | Rp 3.170 | 30 Mar 2026 | Rp 3.075 | **-3.80%** | Rp 15.657.289 | Stop Loss Auto 3.0% terpotong rapi |
| 7 | 31 Mar 2026 | Rp 3.340 | 02 Apr 2026 | Rp 3.380 | **+0.40%** | Rp 15.719.543 | Kunci Profit cepat |
| 8 | 11 Mei 2026 | Rp 3.560 | 18 Mei 2026 | Rp 3.453 | **-3.80%** | Rp 15.122.200 | Stop Loss Auto 3.0% terpotong rapi |
| 9 | 20 Mei 2026 | Rp 3.060 | 22 Mei 2026 | Rp 3.580 | **+16.19%** | Rp 17.571.008 | Tangkap dasar 3.060, jual pucuk 3.580 |
| 10 | 04 Jun 2026 | Rp 3.060 | 05 Jun 2026 | Rp 3.150 | **+2.14%** | Rp 17.947.235 | Scalping cepat 1 hari |
| 11 | 02 Jul 2026 | Rp 3.350 | 06 Jul 2026 | Rp 3.420 | **+1.29%** | Rp 18.178.674 | Ambil untung cepat |
| 12 | 09 Jul 2026 | Rp 3.360 | 13 Jul 2026 | Rp 3.440 | **+1.58%** | **Rp 18.466.070** | Ambil untung cepat |

---

## 5. Cara Menjalankan Ulang Simulasi (Reproducibility)

Jalankan perintah ini di terminal untuk memverifikasi ulang hasil 12 trade di atas:
```bash
quant/.venv-fundamentals/bin/python quant/test_optimized_risk_be.py
```
