"""
Data Mining: Karakteristik Matematis & Indikator Titik Terbawah (Bottom) 
dan Titik Teratas (Peak) pada Saham TINS.
"""
import pandas as pd
import numpy as np

df = pd.read_csv("data/stocks/TINS.csv")
df["date"] = pd.to_datetime(df["date"]).dt.date
df = df.sort_values("date").reset_index(drop=True)

# Indikator Lengkap
delta = df["close"].diff()
gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
rs = gain / loss.replace(0, np.nan)
df["rsi14"] = 100 - (100 / (1 + rs))

low14 = df["low"].rolling(14).min()
high14 = df["high"].rolling(14).max()
df["stoch_k"] = 100 * (df["close"] - low14) / (high14 - low14).replace(0, np.nan)
df["stoch_d"] = df["stoch_k"].rolling(3).mean()

df["sma20"] = df["close"].rolling(20).mean()
df["std20"] = df["close"].rolling(20).std()
df["bb_upper"] = df["sma20"] + 2 * df["std20"]
df["bb_lower"] = df["sma20"] - 2 * df["std20"]
df["bb_pct_b"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)

df["ema10"] = df["close"].ewm(span=10, adjust=False).mean()
df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

df["vol_ma20"] = df["volume"].rolling(20).mean()
df["vol_ratio"] = df["volume"] / df["vol_ma20"].replace(0, np.nan)

ema12 = df["close"].ewm(span=12, adjust=False).mean()
ema26 = df["close"].ewm(span=26, adjust=False).mean()
df["macd"] = ema12 - ema26
df["macd_sig"] = df["macd"].ewm(span=9, adjust=False).mean()
df["macd_hist"] = df["macd"] - df["macd_sig"]

# Candlestick metrics
df["candle_body"] = (df["close"] - df["open"]).abs()
df["candle_range"] = df["high"] - df["low"]
df["is_green"] = df["close"] > df["open"]
df["lower_wick"] = np.minimum(df["open"], df["close"]) - df["low"]
df["upper_wick"] = df["high"] - np.maximum(df["open"], df["close"])
df["lower_wick_ratio"] = df["lower_wick"] / df["candle_range"].replace(0, np.nan)
df["upper_wick_ratio"] = df["upper_wick"] / df["candle_range"].replace(0, np.nan)

# Deteksi Swing Bottom: titik terendah dalam rentang 5 hari sebelum & 5 hari sesudah, lalu rally >= 10%
# Deteksi Swing Peak: titik tertinggi dalam rentang 5 hari sebelum & 5 hari sesudah, lalu drop >= 10%

df_recent = df[df["date"] >= pd.to_datetime("2024-01-01").date()].copy().reset_index(drop=True)

bottoms = []
peaks = []

N = len(df_recent)
for i in range(5, N - 15):
    # Cek Bottom
    is_local_min = df_recent.iloc[i]["low"] == df_recent.iloc[i-5:i+6]["low"].min()
    future_max = df_recent.iloc[i+1:i+15]["high"].max()
    gain_ahead = (future_max - df_recent.iloc[i]["low"]) / df_recent.iloc[i]["low"]
    
    if is_local_min and gain_ahead >= 0.10:
        row = df_recent.iloc[i]
        # Next day candle
        next_row = df_recent.iloc[i+1]
        bottoms.append({
            "date": row["date"],
            "price": row["low"],
            "close": row["close"],
            "gain_ahead": gain_ahead * 100,
            "rsi14": row["rsi14"],
            "stoch_k": row["stoch_k"],
            "stoch_d": row["stoch_d"],
            "bb_pct_b": row["bb_pct_b"],
            "vol_ratio": row["vol_ratio"],
            "lower_wick_ratio": row["lower_wick_ratio"],
            "macd_hist": row["macd_hist"],
            "next_green": next_row["is_green"],
            "next_close_above": next_row["close"] > row["close"]
        })
        
    # Cek Peak
    is_local_max = df_recent.iloc[i]["high"] == df_recent.iloc[i-5:i+6]["high"].max()
    future_min = df_recent.iloc[i+1:i+15]["low"].min()
    drop_ahead = (future_min - df_recent.iloc[i]["high"]) / df_recent.iloc[i]["high"]
    
    if is_local_max and drop_ahead <= -0.10:
        row = df_recent.iloc[i]
        peaks.append({
            "date": row["date"],
            "price": row["high"],
            "close": row["close"],
            "drop_ahead": drop_ahead * 100,
            "rsi14": row["rsi14"],
            "stoch_k": row["stoch_k"],
            "bb_pct_b": row["bb_pct_b"],
            "vol_ratio": row["vol_ratio"],
            "upper_wick_ratio": row["upper_wick_ratio"],
            "macd_hist": row["macd_hist"],
        })

df_b = pd.DataFrame(bottoms)
df_p = pd.DataFrame(peaks)

print("=" * 80)
print(f"  ANALISIS STATISTIK TITIK TERBAWAH (BOTTOM SWING) TINS (Total: {len(df_b)} Titik)")
print("=" * 80)
print(f"  Rata-rata Kenaikan Setelah Bottom : +{df_b['gain_ahead'].mean():.1f}% (Rentang: +{df_b['gain_ahead'].min():.1f}% s/d +{df_b['gain_ahead'].max():.1f}%)")
print(f"  Rata-rata RSI14 di Titik Terbawah : {df_b['rsi14'].mean():.1f} (Median: {df_b['rsi14'].median():.1f}, 80% di bawah {df_b['rsi14'].quantile(0.8):.1f})")
print(f"  Rata-rata Stoch %K di Bottom      : {df_b['stoch_k'].mean():.1f} (Median: {df_b['stoch_k'].median():.1f})")
print(f"  Rata-rata Bollinger %B di Bottom  : {df_b['bb_pct_b'].mean():.2f} (Median: {df_b['bb_pct_b'].median():.2f})")
print(f"  Ekor Bawah Panjang (Rejection)    : {(df_b['lower_wick_ratio'] > 0.35).mean()*100:.1f}% kasus")
print(f"  Konfirmasi Hari Berikutnya Hijau  : {df_b['next_green'].mean()*100:.1f}% kasus")
print(f"  Konfirmasi Close > Close Kemarin  : {df_b['next_close_above'].mean()*100:.1f}% kasus")

print("\n  Sample 6 Titik Terbawah TINS Terbaru:")
for _, r in df_b.tail(6).iterrows():
    print(f"    {r['date']} @ Rp {r['price']:,.0f} | RSI: {r['rsi14']:.1f} | Stoch: {r['stoch_k']:.1f} | BB%B: {r['bb_pct_b']:.2f} | Naik Lanjutan: +{r['gain_ahead']:.1f}%")

print("\n" + "=" * 80)
print(f"  ANALISIS STATISTIK TITIK TERATAS (PEAK SWING) TINS (Total: {len(df_p)} Titik)")
print("=" * 80)
print(f"  Rata-rata Penurunan Setelah Peak  : {df_p['drop_ahead'].mean():.1f}% (Rentang: {df_p['drop_ahead'].max():.1f}% s/d {df_p['drop_ahead'].min():.1f}%)")
print(f"  Rata-rata RSI14 di Titik Teratas  : {df_p['rsi14'].mean():.1f} (Median: {df_p['rsi14'].median():.1f}, 80% di atas {df_p['rsi14'].quantile(0.2):.1f})")
print(f"  Rata-rata Stoch %K di Peak        : {df_p['stoch_k'].mean():.1f} (Median: {df_p['stoch_k'].median():.1f})")
print(f"  Rata-rata Bollinger %B di Peak    : {df_p['bb_pct_b'].mean():.2f} (Median: {df_p['bb_pct_b'].median():.2f})")
print(f"  Ekor Atas Panjang (Selling Press) : {(df_p['upper_wick_ratio'] > 0.35).mean()*100:.1f}% kasus")

print("\n  Sample 6 Titik Puncak TINS Terbaru:")
for _, r in df_p.tail(6).iterrows():
    print(f"    {r['date']} @ Rp {r['price']:,.0f} | RSI: {r['rsi14']:.1f} | Stoch: {r['stoch_k']:.1f} | BB%B: {r['bb_pct_b']:.2f} | Drop Lanjutan: {r['drop_ahead']:.1f}%")

