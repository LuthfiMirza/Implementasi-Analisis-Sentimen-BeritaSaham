# Analisis Pola Sinyal PTB Manual

Data picks: `460` rows, `150` ticker unik.
Fitur teknikal dihitung dari data harian D-1 karena sinyal scalp terjadi besok pagi.

## Temuan Utama

- Sampel fitur valid: `319` picks.
- `RSI14 > 60`: `39.2%` picks.
- Hari sebelumnya hijau `ret_1d > 0`: `56.4%` picks.
- Momentum 5 hari hijau `ret_5d > 0`: `67.7%` picks.
- Harga di atas MA20: `79.0%` picks.
- Drawdown besar `<= -20%`: `3.1%` picks.
- Median `RSI14`: `57.2`.
- Median volume ratio 20d: `1.20x`.

## Berdasarkan Label

         n      rsi14  ret_1d_pct  ret_5d_pct  vol_ratio20  above_ma20_pct
label                                                                     
draw    33  53.086739        0.00        0.79         0.97           69.70
loss    68  59.316264        2.90        5.60         1.31           80.88
win    218  56.741947        0.62        3.67         1.20           79.82

## Ticker Paling Sering Dipilih

label   draw  loss  win  total win_rate_ex_draw
ticker                                         
BUMI       1     2   10     13        83.333333
AMMN       0     4    8     12        66.666667
TINS       1     4    7     12        63.636364
TPIA       1     2    8     11             80.0
VKTR       2     3    6     11        66.666667
CUAN       0     2    8     10             80.0
BULL       0     3    7     10             70.0
DSSA       0     3    7     10             70.0
BNBR       1     3    6     10        66.666667
DEWA       0     1    8      9        88.888889
BMRI       2     2    5      9        71.428571
ENRG       1     4    4      9             50.0
BRMS       0     0    8      8            100.0
BRPT       2     0    6      8            100.0
INDY       0     1    7      8             87.5
BUVA       1     1    6      8        85.714286
PTRO       1     2    5      8        71.428571
BACH       1     0    6      7            100.0
BIPI       0     2    5      7        71.428571
BREN       0     2    5      7        71.428571

## Interpretasi

- Pola paling terlihat: PTB condong ke saham momentum pendek, bukan mean-reversion murni.
- Mayoritas picks punya `ret_5d > 0`, banyak yang di atas `MA20`, dan median `RSI14` cenderung kuat.
- `RSI14 > 60` sendiri tidak cukup jadi formula PTB; PTB V2 RSI-only hampir flat.
- Kemungkinan formula asli perlu unsur volume/orderflow/news, bukan cuma harga daily.

## Data Yang Masih Dibutuhkan

- Intraday 5m/1m OHLCV sejak pre-open sampai 09:30.
- Order book bid/offer dan antrean pre-open.
- Running trade/value/frequency menit awal.
- Full watchlist sebelum market open, bukan cuma hasil sore.
- News/sentimen/ticker trending sebelum open.
- Universe pembanding harian: saham yang tidak dipilih pada hari yang sama.
