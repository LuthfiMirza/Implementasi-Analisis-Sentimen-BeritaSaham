# MOMENTUM Trailing Stop Compare

Generated: `2026-09-07`.

Entry window: `2025-12-01` sampai `2026-09-04`.
Rule entry: RSI14 `> 60`, entry close hari bursa berikutnya.
Exit: trailing stop atau target waktu `10` hari bursa.
Fee/slippage asumsi: `0.8%` round-trip.
Episode gap: `15` hari; angka episode pakai rata-rata trade dalam satu rally.

## Summary

| Trailing | Raw Trade | Raw WR | Raw Total | Raw Avg | Episode | Episode WR | Episode Total | Episode Avg | Episode Median |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `1.0%` | 121 | 77.7% | +376.8% | +3.11% | 8 | 100.0% | +20.5% | +2.56% | +2.56% |
| `1.5%` | 121 | 70.2% | +313.3% | +2.59% | 8 | 100.0% | +16.3% | +2.03% | +2.03% |
| `2.0%` | 121 | 64.5% | +257.4% | +2.13% | 8 | 87.5% | +12.5% | +1.57% | +1.74% |

## Per Ticker

| Trailing | Ticker | Raw Trade | Episode | Episode Win | Episode Total | Episode Avg |
|---:|---|---:|---:|---:|---:|---:|
| `1.0%` | `BUMI` | 46 | 2 | 100.0% | +6.1% | +3.06% |
| `1.0%` | `DEWA` | 48 | 3 | 100.0% | +7.6% | +2.55% |
| `1.0%` | `BRPT` | 16 | 2 | 100.0% | +3.7% | +1.85% |
| `1.0%` | `DSSA` | 11 | 1 | 100.0% | +3.0% | +2.97% |
| `1.5%` | `BUMI` | 46 | 2 | 100.0% | +5.1% | +2.54% |
| `1.5%` | `DEWA` | 48 | 3 | 100.0% | +6.1% | +2.03% |
| `1.5%` | `BRPT` | 16 | 2 | 100.0% | +2.7% | +1.34% |
| `1.5%` | `DSSA` | 11 | 1 | 100.0% | +2.4% | +2.45% |
| `2.0%` | `BUMI` | 46 | 2 | 100.0% | +4.5% | +2.24% |
| `2.0%` | `DEWA` | 48 | 3 | 100.0% | +4.5% | +1.50% |
| `2.0%` | `BRPT` | 16 | 2 | 50.0% | +1.6% | +0.82% |
| `2.0%` | `DSSA` | 11 | 1 | 100.0% | +1.9% | +1.92% |

## Kesimpulan

- `1.0%` paling tinggi profit di data ini, tapi paling cepat kena noise.
- `1.5%` kompromi: profit turun, noise buffer sedikit lebih longgar.
- `2.0%` paling longgar, profit paling rendah di simulasi ini.
- Sample episode kecil; gunakan paper/live kecil sebelum ubah rule produksi.
