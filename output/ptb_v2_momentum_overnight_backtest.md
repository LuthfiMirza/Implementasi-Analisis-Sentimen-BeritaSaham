# PTB V2 Momentum Overnight Backtest

Modal awal: `Rp10,000,000`.
Periode signal: `2026-07-20` sampai `2026-09-01`.
Entry: daily close saat `RSI14 > 60`.
Exit: close bar 30m pertama hari bursa berikutnya.
Biaya asumsi: `0.3%` round-trip.

## Hasil

- Trade mentah: `109`
- Episode: `14`
- Win rate episode: `64.3%`
- Modal akhir: `Rp10,065,597`
- Return compound: `+0.66%`

## Catatan

Ini `overnight momentum`, bukan PTB label-picks. Data exit pakai proxy first 30m Yahoo.
