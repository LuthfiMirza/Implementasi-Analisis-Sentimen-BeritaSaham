# PTB Open Scalp 30m Backtest

Periode: `2026-07-20` sampai `2026-09-01`.
Modal awal: `Rp10.000.000`.
Entry: first 30m bar open Yahoo.
Exit: first 30m bar close Yahoo.
Biaya asumsi: `0.3%` round-trip.

## Label Dari Chat

- Total picks manual: `460`
- Win: `317`
- Loss: `105`
- Draw: `38`

## Backtest Harga 30m

- Picks punya data intraday: `457`
- Hari trading valid: `30`
- Rata-rata return harian basket: `+0.79%`
- Total compound return: `+26.09%`
- Modal akhir: `Rp12,609,060`

## Catatan

Ini memakai picks manual dari chat `2026-07-20` sampai `2026-09-01`; data `2026-09-02/2026-09-03` belum masuk compare karena batas data intraday lokal/Yahoo saat run.

## Compare Modal 10 Juta Periode Sama

| Strategi | Modal Akhir | Return | Episode/Hari |
|---|---:|---:|---:|
| PTB_OPEN_SCALP_30M | Rp12,609,060 | +26.09% | 30 hari |
| GABUNGAN | Rp16,388,613 | +63.89% | 10 episode |
| BOTTOM_REBOUND | Rp13,351,861 | +33.52% | 10 episode |
| MOMENTUM | Rp7,919,073 | -20.81% | 13 episode |

Kesimpulan periode ini: `GABUNGAN` masih paling besar, `BOTTOM_REBOUND` kedua, `PTB_OPEN_SCALP_30M` ketiga, `MOMENTUM` kalah.
