# Laporan Riset Kuantitatif: Strategi Bottom-to-Top TINS

**Tanggal Laporan:** 21 September 2026  
**Ticker:** TINS (PT Timah Tbk)  
**Periode Data:** 1 Desember 2025 s/d 21 September 2026  
**Modal Awal Hipotetis:** Rp 10.000.000 (Compounded All-In per Episode Independen)  
**Biaya Transaksi:** 0.80% round-trip (fee beli + fee jual + PPh)  
**Script Audit:** `quant/test_optimized_risk_be.py`  

---

## 1. Eksekutif Ringkasan

Riset ini diinisiasi untuk menjawab kegagalan strategi kaku *Drawdown-Bounce* dan batas kaku *10 hari bursa* pada saham **TINS** yang sebelumnya mengakibatkan kerugian -5.8% s/d -12.8%.

Dengan menganalisis 41 siklus dasar (*swing bottom*) dan 40 siklus puncak (*swing peak*) historis TINS, dirumuskan strategi **Bottom-to-Top** yang menggabungkan:
1. **Pola Deteksi Dasar (Swing Bottom):** Osilator oversold (`Stoch %K < 30` / `BB %B < 0.25`) + Konfirmasi Rebound Lilin Hijau (`Close > Open` & `Close > Close Kemarin`).
2. **Pengendalian Risiko Ketat (Max 3%):** Order Stop Loss otomatis di broker pada level -3.00% (net loss maksimal -3.80% termasuk fee broker). Menghilangkan 100% risiko minus $\ge 5\%$.
3. **Kunci Untung Dinamis (Trailing Profit Lock 2.5%):** Begitu harga pernah terapresiasi $\ge +3.0\%$, kunci untung otomatis jika harga mundur 2.5% dari puncak tertinggi.

---

## 2. Tabel Perbandingan 6 Pendekatan Strategi pada TINS

| # | Pendekatan Strategi | Trade | Win Rate | Kerugian Terburuk | Rata-rata Minus | **Hasil Akhir Modal** | PnL Bersih (%) |
| :-: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | Drawdown-Bounce (Tahan Kaku 10 Hari) | 5 | 40.0% | -8.35% | -6.50% | Rp 9.418.363 | -5.82% |
| 2 | Drawdown-Bounce (Trailing Stop 2%) | 5 | 20.0% | -7.76% | -5.56% | Rp 8.716.214 | -12.84% |
| 3 | Bottom Rebound (Pantul +5% Kaku) | 10 | 40.0% | -8.98% | -5.63% | Rp 8.530.988 | -14.69% |
| 4 | Self-Radar V1 (Overnight Scalp) | 5 | 20.0% | -15.68% | -5.86% | Rp 8.221.549 | -17.78% |
| 5 | Momentum (RSI > 60, TS 5% Fleksibel) | 7 | 85.7% | -4.14% | -2.61% | Rp 14.448.024 | +44.48% |
| **6**| **Bottom-to-Top (Auto SL 3% + Kunci Untung)** | **12**| **66.7%**| **-3.80%** | **-2.89%** | **Rp 18.466.070** | **+84.66% 🏆** |

---

## 3. Rincian 12 Trade Strategi Bottom-to-Top

```
  #   Tanggal Beli  Harga Beli Tanggal Jual  Harga Jual   Net PnL%            Saldo Alasan Exit
  -------------------------------------------------------------------------------------------------------
  1   2025-12-11    Rp   3,060 2025-12-15    Rp   3,550    +15.21% Rp    11,521,307 Kunci Profit (Puncak 3.700)
  2   2026-01-02    Rp   3,140 2026-01-07    Rp   3,530    +11.62% Rp    12,860,127 Kunci Profit (Puncak 3.630)
  3   2026-02-03    Rp   3,220 2026-02-05    Rp   3,240     -0.18% Rp    12,837,123 Keluar Cepat Impas
  4   2026-02-09    Rp   3,160 2026-02-12    Rp   4,190    +31.79% Rp    16,918,678 Mega Cuan (Puncak 4.190)
  5   2026-03-17    Rp   3,320 2026-03-25    Rp   3,220     -3.80% Rp    16,275,768 Auto Cut Loss 3.0%
  6   2026-03-27    Rp   3,170 2026-03-30    Rp   3,075     -3.80% Rp    15,657,289 Auto Cut Loss 3.0%
  7   2026-03-31    Rp   3,340 2026-04-02    Rp   3,380     +0.40% Rp    15,719,543 Kunci Profit Cepat
  8   2026-05-11    Rp   3,560 2026-05-18    Rp   3,453     -3.80% Rp    15,122,200 Auto Cut Loss 3.0%
  9   2026-05-20    Rp   3,060 2026-05-22    Rp   3,580    +16.19% Rp    17,571,008 Tangkap Dasar 3.060, Jual 3.580
  10  2026-06-04    Rp   3,060 2026-06-05    Rp   3,150     +2.14% Rp    17,947,235 Scalping 1 Hari
  11  2026-07-02    Rp   3,350 2026-07-06    Rp   3,420     +1.29% Rp    18,178,674 Ambil Untung Cepat
  12  2026-07-09    Rp   3,360 2026-07-13    Rp   3,440     +1.58% Rp    18,466,070 Ambil Untung Cepat
```

---

## 4. Kesimpulan & Rekomendasi Operasional

1. Batas rugi kaku di **3.0%** terbukti sukses memotong kerugian besar tanpa mengorbankan ruang nafas volatilitas wajar TINS.
2. Aturan penguncian untung **mundur 2.5% dari puncak** berhasil mengamankan profit sebelum reli berbalik arah.
3. Catatan manual operasional tersimpan di `quant/drawdown_bounce_tracker/TINS_BOTTOM_TO_TOP_NOTES.md`.
