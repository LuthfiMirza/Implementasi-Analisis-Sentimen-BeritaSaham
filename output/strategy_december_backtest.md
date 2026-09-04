# Backtest Strategi Desember

Periode entry: `2025-12-01` sampai `2026-09-01`.
Universe: `BUMI, DEWA, BRPT, ESSA, UNVR, SMGR, TINS, PTRO, ENRG, RAJA, INET, DSSA`.
Exit: hold `10` hari bursa, biaya round-trip `0.8%`.

| Rank | Strategi | Trade | Episode | Win Rate | Total Episode PnL | Avg Episode | Median Episode |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | GABUNGAN | 754 | 48 | 58.3% | +238.1% | +4.96% | +2.16% |
| 2 | BOTTOM_REBOUND | 176 | 86 | 54.7% | +196.0% | +2.28% | +2.12% |
| 3 | MOMENTUM | 338 | 38 | 26.3% | -259.4% | -6.83% | -6.17% |

Kesimpulan sementara: `GABUNGAN` paling profit pada total PnL level episode.

Catatan: hasil eksplorasi, bukan validasi OOS final. MOMENTUM raw trade mudah menggelembung karena sinyal bisa muncul berhari-hari.
