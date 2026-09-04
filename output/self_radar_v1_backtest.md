# Self Radar V1 Backtest

Sinyal tidak pakai PTB radar. Universe dari `ptb_backtest_prices_5y.json`, fitur D-1, entry close D-1, exit trailing stop 1% mulai 09:30 hari H.

Dataset: `3105` ticker-day outcome dari `106` ticker.

## Rule Terbaik

```text
{'rsi_min': 60, 'ret1_min': None, 'ret5_min': 0.05, 'ret5_max': None, 'above_ma20': False, 'dd_min': -0.05}
```

## Hasil Rule Terbaik

- Trade: `149`
- Hari aktif: `30`
- Total return harian: `+144.06%`
- Avg return harian: `+4.80%`
- Avg trade: `+4.79%`
- Win rate harian: `96.7%`
- Win rate trade: `75.8%`

## Top 10 Rule Kandidat

```text
1. avg_day=+4.80% avg_trade=+4.79% days=30 trades=149 win_day=96.7% rule={'rsi_min': 60, 'ret1_min': None, 'ret5_min': 0.05, 'ret5_max': None, 'above_ma20': False, 'dd_min': -0.05}
2. avg_day=+4.80% avg_trade=+4.79% days=30 trades=149 win_day=96.7% rule={'rsi_min': 60, 'ret1_min': None, 'ret5_min': 0.05, 'ret5_max': None, 'above_ma20': True, 'dd_min': -0.05}
3. avg_day=+4.75% avg_trade=+4.75% days=30 trades=150 win_day=96.7% rule={'rsi_min': 60, 'ret1_min': None, 'ret5_min': None, 'ret5_max': None, 'above_ma20': False, 'dd_min': -0.05}
4. avg_day=+4.75% avg_trade=+4.75% days=30 trades=150 win_day=96.7% rule={'rsi_min': 60, 'ret1_min': None, 'ret5_min': None, 'ret5_max': None, 'above_ma20': True, 'dd_min': -0.05}
5. avg_day=+4.75% avg_trade=+4.75% days=30 trades=150 win_day=96.7% rule={'rsi_min': 60, 'ret1_min': None, 'ret5_min': 0, 'ret5_max': None, 'above_ma20': False, 'dd_min': -0.05}
6. avg_day=+4.75% avg_trade=+4.75% days=30 trades=150 win_day=96.7% rule={'rsi_min': 60, 'ret1_min': None, 'ret5_min': 0, 'ret5_max': None, 'above_ma20': True, 'dd_min': -0.05}
7. avg_day=+4.75% avg_trade=+4.75% days=30 trades=150 win_day=96.7% rule={'rsi_min': 60, 'ret1_min': None, 'ret5_min': 0.03, 'ret5_max': None, 'above_ma20': False, 'dd_min': -0.05}
8. avg_day=+4.75% avg_trade=+4.75% days=30 trades=150 win_day=96.7% rule={'rsi_min': 60, 'ret1_min': None, 'ret5_min': 0.03, 'ret5_max': None, 'above_ma20': True, 'dd_min': -0.05}
9. avg_day=+4.74% avg_trade=+4.74% days=30 trades=150 win_day=100.0% rule={'rsi_min': 55, 'ret1_min': None, 'ret5_min': None, 'ret5_max': None, 'above_ma20': False, 'dd_min': None}
10. avg_day=+4.74% avg_trade=+4.74% days=30 trades=150 win_day=100.0% rule={'rsi_min': 55, 'ret1_min': None, 'ret5_min': 0, 'ret5_max': None, 'above_ma20': False, 'dd_min': None}
```

## Ticker Yang Sering Menang Di Rule Terbaik

```text
        trades  avg_ret  win_rate
ticker                           
BAJA         6    14.92    100.00
MCAS         4    11.32     50.00
GDST         2    10.70    100.00
MDIA        13     8.74     84.62
BYAN         2     8.58     50.00
PACK         5     8.25    100.00
KOTA         7     6.58     85.71
MGLV         3     6.50    100.00
SLIS         5     6.09     80.00
FAST         5     5.51     60.00
TEBE         3     5.51     33.33
IATA         9     5.25     77.78
JGLE         5     5.11     80.00
KIJA         5     4.84    100.00
SINI         3     4.49     66.67
GULA         3     4.45    100.00
JKON         4     4.00     50.00
JARR         6     3.79     83.33
INET         4     3.58    100.00
RGAS         1     3.13    100.00
NSSS         5     3.03    100.00
DEWA         3     2.60     66.67
ISAT         3     2.50    100.00
CUAN         2     2.21    100.00
PADA         6     1.81     83.33
WIFI         2     1.80    100.00
SSIA         3     1.61     66.67
HATM         2     1.58     50.00
ESSA         1     1.55    100.00
FPNI         6     1.53     50.00
```

## Top Trade Rule Terbaik

```text
trade_date ticker   close  rsi14  ret_1d  ret_5d  drawdown_20d  target_ret
2026-07-27   MCAS   214.0  68.03   34.59   38.96          0.00       24.00
2026-08-06   MDIA   216.0  92.17    0.00   66.15          0.00       23.45
2026-07-28   MCAS   266.0  78.53   24.30   79.73          0.00       23.26
2026-07-28   BAJA   222.0  83.56   34.55   33.73          0.00       22.78
2026-07-23   MDIA   104.0  73.81   26.83   50.72          0.00       22.50
2026-08-05   BAJA   304.0  81.39    0.00   35.71          0.00       22.15
2026-08-18   TEBE  1375.0  82.92   25.00   23.87          0.00       18.86
2026-08-18   BYAN 14400.0  85.74   20.00   19.01          0.00       18.47
2026-08-14   SLIS    88.0  73.52   12.82   18.92          0.00       17.83
2026-08-10   GDST   126.0  75.50    8.62   29.90          0.00       17.56
2026-08-03   MDIA   191.0  90.29    9.14   50.39          0.00       16.84
2026-08-03   BAJA   244.0  73.29    6.09   47.88          0.00       16.55
2026-08-18   FAST   478.0  77.58    6.70   30.60          0.00       15.68
2026-08-03   IATA    76.0  72.21   33.33   31.03          0.00       15.63
2026-09-01   KOTA   216.0  68.41   34.16   29.34          0.00       15.20
2026-08-12   MDIA   246.0  83.54    0.82   13.89         -1.60       14.80
2026-07-31   BAJA   230.0  70.52   20.42   39.39          0.00       13.33
2026-08-10   IATA   115.0  84.91   -1.71   51.32         -1.71       13.33
2026-08-04   JKON    89.0  80.74   34.85   34.85          0.00       13.16
2026-08-03   KOTA   147.0  71.99   -2.65   28.95         -2.65       12.17
2026-07-22   JGLE    67.0  76.27   34.00   34.00          0.00       12.00
2026-07-30   MDIA   130.0  80.83   -0.76   25.00         -0.76       11.65
2026-08-04   MDIA   202.0  91.18    5.76   59.06          0.00       10.46
2026-08-06   BAJA   338.0  84.48   11.18   76.96          0.00        9.83
2026-08-20   FPNI   540.0  80.75   24.42   29.81          0.00        9.70
2026-08-24   KIJA   200.0  78.90   -2.91   61.29         -2.91        9.59
2026-08-31   PACK   510.0  89.43    9.44   44.89          0.00        9.50
2026-07-29   KOTA   128.0  68.50    4.92   24.27          0.00        8.75
2026-08-12   FAST   418.0  71.75   14.84   25.15          0.00        8.65
2026-07-23   DEWA   440.0  70.33    0.00   21.55          0.00        8.60
```

## Interpretasi

- Pola terbaik dari grid ini mencari saham yang sudah momentum, bukan oversold.
- Rule masih discovery di periode sama; perlu walk-forward sebelum dipakai live.
- Data paling kurang: volume intraday, orderbook pre-open, dan universe semua saham IDX harian.
