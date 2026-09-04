# PTB V4 Filtered Backtest

Periode: `2026-07-20` sampai `2026-09-01`.
Filter: historical `win_rate >= 70%`, `bad_rate <= 35%`, sample minimal `3`, max `5` ticker per hari.
Entry: first 5m open. Exit: trailing stop `1%` intraday, atau close terakhir hari itu.
Biaya asumsi: `0.3%` round-trip.

## Hasil

- Raw trade terpilih: `79`
- Hari aktif: `25`
- Hari tanpa kandidat karena belum cukup histori/filter: `5`
- Label win/loss/draw terpilih: `51/21/7`
- Total return harian: `+15.82%`
- Avg return harian: `+0.63%`
- Median return harian: `+0.06%`
- Win rate harian: `52.0%`
- Avg trade: `+0.30%`
- Win rate trade: `41.8%`

## Ticker Terpilih

```text
        trade  avg_ret  win_rate
ticker                          
BUMI        9    -0.33     22.22
CUAN        7    -0.04     42.86
TPIA        7    -0.38     28.57
DEWA        6    -0.03     33.33
BRMS        5     0.49     60.00
INDY        5     0.44     60.00
BRPT        5    -0.32     40.00
BACH        4     1.75     75.00
BUVA        3     0.94    100.00
BNBR        3    -0.02     66.67
BREN        3    -0.24      0.00
TINS        3    -0.33      0.00
AMMN        3    -0.33      0.00
WIFI        2     1.15    100.00
BULL        2     0.46     50.00
PTRO        2    -0.31      0.00
KOTA        1     8.17    100.00
PACK        1     7.57    100.00
MDIA        1     5.45    100.00
ADRO        1     1.25    100.00
MEDC        1     0.11    100.00
GULA        1    -0.67      0.00
ANTM        1    -0.96      0.00
BIPI        1    -1.30      0.00
PSAB        1    -1.30      0.00
VKTR        1    -1.30      0.00
```

## Interpretasi

- Filter ini mengurangi trade dari PTB V3, tapi juga telat aktif karena butuh histori label dulu.
- Ini bukan oracle: filter hanya boleh memakai label sebelum tanggal trade, supaya tidak bocor masa depan.
- Kalau hasil kalah dari V3, berarti filter histori pendek membuang terlalu banyak peluang bagus.
