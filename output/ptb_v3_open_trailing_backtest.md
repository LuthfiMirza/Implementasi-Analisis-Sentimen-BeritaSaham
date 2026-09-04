# PTB V3 Open Trailing Backtest

Periode: `2026-07-20` sampai `2026-09-01`.
Entry: first 5m open pada hari picks PTB.
Exit: trailing stop intraday, atau close terakhir hari itu jika stop tidak kena.
Biaya asumsi: `0.3%` round-trip.

| Rank | Trailing Stop | Raw Trade | Hari | Total Return Harian | Avg Harian | Median Harian | Win Rate Harian | Avg Trade | Win Rate Trade |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1% | 457 | 30 | +26.84% | +0.89% | +0.51% | 83.3% | +0.90% | 53.2% |
| 2 | 2% | 457 | 30 | +13.29% | +0.44% | +0.31% | 66.7% | +0.53% | 48.6% |

Kesimpulan: trailing stop `1%` paling untung pada total return harian.

Catatan: simulasi pakai OHLC 5m Yahoo, jadi urutan high/low dalam satu candle tidak diketahui persis.
