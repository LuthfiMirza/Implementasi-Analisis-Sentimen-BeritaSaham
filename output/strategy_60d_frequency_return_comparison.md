# Compare Strategi 60 Hari Tanpa Compound Modal

Periode efektif: `2026-07-20` sampai `2026-09-01`.
Tujuan: bandingkan frekuensi dan return rata-rata, karena `PTB_OPEN_SCALP_30M` keluar harian sedangkan strategi lain bisa tahan beberapa hari.

| Strategi | Trade Raw | Unit Fair | Total Return Unit Fair | Avg Return Unit Fair | Median Unit Fair | Win Rate Unit Fair |
|---|---:|---:|---:|---:|---:|---:|
| GABUNGAN | 22 | 10 episode | +53.31% | +5.33% | +6.69% | 70.0% |
| BOTTOM_REBOUND | 18 | 10 episode | +36.03% | +3.60% | -0.82% | 40.0% |
| PTB_OPEN_SCALP_30M | 457 | 30 hari | +23.71% | +0.79% | +0.78% | 80.0% |
| PTB_V2_MOMENTUM_OVERNIGHT | 109 | 14 episode | +0.76% | +0.05% | +0.23% | 64.3% |
| MOMENTUM | 73 | 13 episode | -20.35% | -1.57% | -1.83% | 38.5% |

## Cara Baca Fair

- `PTB_OPEN_SCALP_30M` dihitung per hari basket: semua picks hari itu dibeli rata, lalu selesai hari itu juga.
- Strategi selain PTB dihitung per episode, karena satu sinyal bisa overlap dan tahan beberapa hari.
- `Total Return Unit Fair` bukan modal akhir; ini jumlah return unit fair supaya frekuensi terlihat.

## Kesimpulan

- `GABUNGAN` paling kuat per kesempatan: avg episode `+5.33%`.
- `PTB_OPEN_SCALP_30M` paling sering: 457 raw trade dalam 30 hari, avg harian `+0.79%`, win-rate harian `80.0%`.
- Kalau butuh strategi cash cepat harian, PTB menarik; kalau cari return per kesempatan, `GABUNGAN` masih lebih kuat.
