# Perbandingan Strategi

| Strategi | Filosofi | Entry | Cocok Saat | Risiko Utama |
|---|---|---|---|---|
| GABUNGAN | Mean-reversion | `ret_2d <= -5% OR drawdown_20d <= -20%` | Panic sell, oversold | Catching falling knife |
| MOMENTUM | Trend-following | `RSI14 > 60` | Uptrend kuat | Beli terlalu mahal, sinyal berulang |
| BOTTOM_REBOUND | Rebound confirmation | cross pertama `close > bottom_10d * 1.05` | Reversal mulai terbentuk | False breakout |

## Cara Baca

- `GABUNGAN` masuk saat harga masih jatuh.
- `MOMENTUM` masuk saat harga sudah kuat naik.
- `BOTTOM_REBOUND` menunggu pantulan dari bottom 10 hari.

## Status

Semua strategi di file ini masih eksplorasi. Perlu backtest, episode independence, dan OOS sebelum layak live.
