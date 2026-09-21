"""
Analisis Swing Low (Bottom) & Swing High (Peak) TINS (Des 2025 - Sep 2026)
Mencari karakteristik teknikal di titik-titik balik harga sebenarnya:
- RSI (14)
- ATR (14) & rasio ATR terhadap harga (Volatilitas Harian)
- Stochastic (14, 3, 3)
- MACD (12, 26, 9) & Histogram
- Bollinger Bands (20, 2)
- Moving Averages (EMA 20, EMA 50)
"""
from __future__ import annotations

import pathlib
import numpy as np
import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV_FILE = REPO_ROOT / "data" / "stocks" / "TINS.csv"

START_DATE = pd.to_datetime("2025-12-01").date()
END_DATE = pd.to_datetime("2026-09-21").date()

df = pd.read_csv(CSV_FILE)
df["date"] = pd.to_datetime(df["date"]).dt.date
df = df.sort_values("date").reset_index(drop=True)

# 1. RSI 14
delta = df["close"].diff()
gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
rs = gain / loss.replace(0, np.nan)
df["rsi14"] = 100 - (100 / (1 + rs))

# 2. ATR 14
high_low = df["high"] - df["low"]
high_close = (df["high"] - df["close"].shift(1)).abs()
low_close = (df["low"] - df["close"].shift(1)).abs()
tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
df["atr14"] = tr.rolling(14).mean()
df["atr_pct"] = (df["atr14"] / df["close"]) * 100

# 3. Bollinger Bands (20, 2)
df["bb_mid"] = df["close"].rolling(20).mean()
bb_std = df["close"].rolling(20).std()
df["bb_upper"] = df["bb_mid"] + 2 * bb_std
df["bb_lower"] = df["bb_mid"] - 2 * bb_std
df["bb_pct_b"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

# 4. MACD (12, 26, 9)
ema12 = df["close"].ewm(span=12, adjust=False).mean()
ema26 = df["close"].ewm(span=26, adjust=False).mean()
df["macd"] = ema12 - ema26
df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
df["macd_hist"] = df["macd"] - df["macd_signal"]

# 5. Stochastic (14, 3)
low14 = df["low"].rolling(14).min()
high14 = df["high"].rolling(14).max()
df["stoch_k"] = 100 * (df["close"] - low14) / (high14 - low14)
df["stoch_d"] = df["stoch_k"].rolling(3).mean()

# 6. EMA 20 & EMA 50
df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

# Filter window Des 2025 - Sep 2026
w_idx = df[(df["date"] >= START_DATE) & (df["date"] <= END_DATE)].index
df_sub = df.loc[max(0, w_idx[0]-10) : min(len(df)-1, w_idx[-1]+5)].reset_index(drop=True)

# Deteksi Swing Lows & Highs (window order = 4 hari kanan-kiri)
order = 4
lows = []
highs = []

for i in range(order, len(df_sub) - order):
    dt = df_sub.iloc[i]["date"]
    if not (START_DATE <= dt <= END_DATE):
        continue
    c = df_sub.iloc[i]["close"]
    # Check if local minimum
    window_c = df_sub.iloc[i - order : i + order + 1]["close"].values
    if c == np.min(window_c):
        lows.append(i)
    if c == np.max(window_c):
        highs.append(i)

# Eliminate adjacent duplicate indices
def deduplicate(indices, df_in, is_max=True):
    res = []
    for idx in indices:
        if not res:
            res.append(idx)
        else:
            if (df_in.iloc[idx]["date"] - df_in.iloc[res[-1]]["date"]).days <= 5:
                if is_max:
                    if df_in.iloc[idx]["close"] > df_in.iloc[res[-1]]["close"]:
                        res[-1] = idx
                else:
                    if df_in.iloc[idx]["close"] < df_in.iloc[res[-1]]["close"]:
                        res[-1] = idx
            else:
                res.append(idx)
    return res

lows = deduplicate(lows, df_sub, is_max=False)
highs = deduplicate(highs, df_sub, is_max=True)

print("=" * 85)
print(f"  ANALISIS STATISTIK TEKNIKAL TINS (1 Des 2025 - 21 Sep 2026)")
print("=" * 85)
cur_period = df_sub[(df_sub['date']>=START_DATE)&(df_sub['date']<=END_DATE)]
print(f"  Harga Terendah Periode : Rp {cur_period['low'].min():,.0f}")
print(f"  Harga Tertinggi Periode: Rp {cur_period['high'].max():,.0f}")
print(f"  Rata-rata ATR(14) TINS : {cur_period['atr_pct'].mean():.2f}% per hari")
print(f"  Rentang ATR(14)        : {cur_period['atr_pct'].min():.2f}% s/d {cur_period['atr_pct'].max():.2f}%")
print(f"\n  [!] KUNCI MASALAH TRAILING STOP 2%:")
print(f"      ATR harian TINS rata-rata {cur_period['atr_pct'].mean():.2f}%. Dalam SATU HARI BIASA saja,")
print(f"      fluktuasi wajar TINS adalah ±{cur_period['atr_pct'].mean():.1f}%.")
print(f"      Trailing stop 2% terlalu tipis, sehingga selalu terpotong oleh noise harian")
print(f"      tepat sebelum harga melanjutkan rally!")

print("\n" + "-" * 85)
print("  DAFTAR HARGA PALING BAWAH (LOCAL BOTTOMS / SWING LOWS) TINS")
print("-" * 85)
print(f"  {'Tanggal':<12} {'Harga':>8} {'RSI(14)':>8} {'Stoch %K':>9} {'%B Band':>8} {'MACD Hist':>10} {'vs EMA20':>9} {'ATR%':>6}")
print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*9} {'-'*8} {'-'*10} {'-'*9} {'-'*6}")

bottom_data = []
for i in lows:
    r = df_sub.iloc[i]
    ema_diff = (r['close'] - r['ema20']) / r['ema20'] * 100
    bottom_data.append(r)
    print(f"  {str(r['date']):<12} {r['close']:>8,.0f} {r['rsi14']:>8.1f} {r['stoch_k']:>9.1f} {r['bb_pct_b']:>8.2f} {r['macd_hist']:>10.1f} {ema_diff:>+8.1f}% {r['atr_pct']:>5.1f}%")

df_bottoms = pd.DataFrame(bottom_data)

print("\n" + "-" * 85)
print("  DAFTAR HARGA PALING ATAS (LOCAL PEAKS / SWING HIGHS) TINS")
print("-" * 85)
print(f"  {'Tanggal':<12} {'Harga':>8} {'RSI(14)':>8} {'Stoch %K':>9} {'%B Band':>8} {'MACD Hist':>10} {'vs EMA20':>9} {'ATR%':>6}")
print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*9} {'-'*8} {'-'*10} {'-'*9} {'-'*6}")

peak_data = []
for i in highs:
    r = df_sub.iloc[i]
    ema_diff = (r['close'] - r['ema20']) / r['ema20'] * 100
    peak_data.append(r)
    print(f"  {str(r['date']):<12} {r['close']:>8,.0f} {r['rsi14']:>8.1f} {r['stoch_k']:>9.1f} {r['bb_pct_b']:>8.2f} {r['macd_hist']:>10.1f} {ema_diff:>+8.1f}% {r['atr_pct']:>5.1f}%")

df_peaks = pd.DataFrame(peak_data)

print("\n" + "=" * 85)
print("  KESIMPULAN POLA INDIKATOR UNTUK FORMULA MASUK (IN) & KELUAR (OUT)")
print("=" * 85)
print(f"  1. POLA DI TITIK PALING BAWAH (BOTTOM):")
print(f"     - RSI(14)        : Rata-rata {df_bottoms['rsi14'].mean():.1f} (Median {df_bottoms['rsi14'].median():.1f}) -> Berada di rentang 40 - 48 (bukan oversold ekstrem <30 karena TINS bullish)")
print(f"     - Stochastic %K  : Rata-rata {df_bottoms['stoch_k'].mean():.1f} -> Oversold (< 20)")
print(f"     - Bollinger %B   : Rata-rata {df_bottoms['bb_pct_b'].mean():.2f} -> Menembus / mendekati Lower Band (< 0.15)")
print(f"     - MACD Histogram : Rata-rata {df_bottoms['macd_hist'].mean():.1f} -> Palung lembah negatif (momentum jual habis)")
print(f"     - Posisi vs EMA20: Rata-rata diskon {((df_bottoms['close']-df_bottoms['ema20'])/df_bottoms['ema20']*100).mean():.1f}% di bawah EMA20")

print(f"\n  2. POLA DI TITIK PALING ATAS (PEAK):")
print(f"     - RSI(14)        : Rata-rata {df_peaks['rsi14'].mean():.1f} (Median {df_peaks['rsi14'].median():.1f}) -> Overbought (> 68 - 82)")
print(f"     - Stochastic %K  : Rata-rata {df_peaks['stoch_k'].mean():.1f} -> Overbought (> 80)")
print(f"     - Bollinger %B   : Rata-rata {df_peaks['bb_pct_b'].mean():.2f} -> Menembus Upper Band (> 0.90)")
print(f"     - Posisi vs EMA20: Rata-rata premi {((df_peaks['close']-df_peaks['ema20'])/df_peaks['ema20']*100).mean():+.1f}% di atas EMA20")
