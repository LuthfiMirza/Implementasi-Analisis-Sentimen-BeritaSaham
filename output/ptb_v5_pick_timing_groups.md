# PTB V5 Pick Timing Groups

Periode: `2026-07-20` sampai `2026-09-01`.
Exit: trailing stop `1%`. Fee: `0.3%`.
Timing dibandingkan: beli `open hari H` vs beli `close H-1` lalu jual trailing hari H.

## Basket Semua Picks

| Timing | Raw Trade | Hari | Total Return Harian | Avg Harian | Avg Trade | Win Rate Harian | Win Rate Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| buy_open_H | 376 | 30 | +27.97% | +0.93% | +0.95% | 80.0% | 53.7% |
| buy_close_H_minus_1 | 358 | 29 | +65.55% | +2.26% | +2.13% | 96.6% | 77.9% |

## Top Ticker Buy Open H

```text
        trades  total_ret  avg_ret  median_ret  win_rate
ticker                                                  
MDIA         4      23.25     5.81        3.59     75.00
KOTA         4      17.65     4.41        4.59    100.00
PACK         5      21.44     4.29        4.66    100.00
COIN         5      19.67     3.93        4.02     80.00
JGLE         3       8.03     2.68        2.66    100.00
INET         5      12.96     2.59        2.80     60.00
BACH         7      15.38     2.20        2.86     85.71
JELI         4       7.36     1.84        1.59     75.00
BIPI         7       7.81     1.12       -0.01     42.86
PTBA         3       2.93     0.98        2.04     66.67
PADI         3       2.69     0.90        0.11    100.00
ADMR         3       2.02     0.67        0.76    100.00
PSAB         5       3.34     0.67        0.09     80.00
ISAT         3       1.89     0.63        0.49     66.67
INCO         3       1.69     0.56        0.04     66.67
ARCI         3       1.55     0.52        0.91     66.67
GGRM         3       1.40     0.47        0.58     66.67
ESSA         5       1.74     0.35        0.82     80.00
BRMS         8       2.68     0.34        0.33     50.00
AMMN        12       3.80     0.32       -0.12     41.67
```

## Top Ticker Buy Close H-1

```text
        trades  total_ret  avg_ret  median_ret  win_rate
ticker                                                  
COIN         5      48.03     9.61        8.39     80.00
MDIA         4      28.54     7.13        4.40    100.00
KOTA         4      28.51     7.13        5.68    100.00
PACK         5      28.69     5.74        6.73    100.00
JELI         3      11.85     3.95        4.38    100.00
INET         5      19.13     3.83        3.51    100.00
BACH         7      26.14     3.73        4.52    100.00
ARCI         3      10.08     3.36        3.70    100.00
PTBA         3       9.78     3.26        4.24     66.67
JGLE         3       9.07     3.02        2.66    100.00
BRMS         7      18.15     2.59        1.97    100.00
PSAB         5      12.51     2.50        0.57    100.00
BIPI         6      14.26     2.38        1.42     83.33
HRTA         5      10.17     2.03        1.50    100.00
ENRG         9      17.42     1.94        1.53     88.89
PADI         3       5.46     1.82        1.57    100.00
ISAT         3       4.96     1.65        1.49    100.00
EMAS         6       9.22     1.54        1.67     83.33
ADMR         3       4.46     1.49        1.36    100.00
INDY         8      11.79     1.47        1.98     75.00
```

## Basket Top 10 Ticker Per Timing

| Group | Raw Trade | Hari | Total Return Harian | Avg Harian | Avg Trade | Win Rate Harian | Win Rate Trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| top10_close_H_minus_1 | 42 | 22 | +125.31% | +5.70% | +5.23% | 100.0% | 95.2% |
| top10_open_H | 47 | 22 | +62.14% | +2.82% | +2.90% | 90.9% | 76.6% |

## Interpretasi

- Ini mencari pola profit aktual dari picks PTB, bukan memakai label win/loss saja.
- Top ticker bisa overfit karena periode pendek; validasi perlu data minggu berikutnya.
- Kalau `buy_close_H_minus_1` menang, sinyal cocok overnight. Kalau `buy_open_H` menang, sinyal cocok scalp pagi.
