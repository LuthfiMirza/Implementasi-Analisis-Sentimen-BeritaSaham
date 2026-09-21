import pandas as pd
import numpy as np

df = pd.read_csv("data/stocks/TINS.csv")
df["date"] = pd.to_datetime(df["date"]).dt.date
df = df.sort_values("date").reset_index(drop=True)

# Indikator
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

print("=" * 85)
print("  DETAIL TRADE #9: PERIODE 18 MEI - 25 MEI 2026 (CUAN +16.19%)")
print("=" * 85)
sub9 = df[(df["date"] >= pd.to_datetime("2026-05-18").date()) & (df["date"] <= pd.to_datetime("2026-05-25").date())]
for _, r in sub9.iterrows():
    d, o, h, l, c, v = r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"]
    rsi, sk, sd, bbp = r["rsi14"], r["stoch_k"], r["stoch_d"], r["bb_pct_b"]
    print(f"Tanggal: {d} | O:{o:,.0f} H:{h:,.0f} L:{l:,.0f} C:{c:,.0f} | Vol:{v:,.0f}")
    print(f"         Indikator -> RSI:{rsi:.1f} | Stoch %K:{sk:.1f} | %D:{sd:.1f} | BB %B:{bbp:.2f}")
    is_green = c > o
    cond_dip = (sk < 30 or bbp < 0.25 or rsi < 45)
    print(f"         Kondisi Beli -> Dip:{cond_dip} | Hijau:{is_green}\n")

print("=" * 85)
print("  DETAIL TRADE #12: PERIODE 07 JULI - 16 JULI 2026 (CUAN +1.58%)")
print("=" * 85)
sub12 = df[(df["date"] >= pd.to_datetime("2026-07-07").date()) & (df["date"] <= pd.to_datetime("2026-07-16").date())]
for _, r in sub12.iterrows():
    d, o, h, l, c, v = r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"]
    rsi, sk, sd, bbp = r["rsi14"], r["stoch_k"], r["stoch_d"], r["bb_pct_b"]
    print(f"Tanggal: {d} | O:{o:,.0f} H:{h:,.0f} L:{l:,.0f} C:{c:,.0f} | Vol:{v:,.0f}")
    print(f"         Indikator -> RSI:{rsi:.1f} | Stoch %K:{sk:.1f} | %D:{sd:.1f} | BB %B:{bbp:.2f}")
    is_green = c > o
    cond_dip = (sk < 30 or bbp < 0.25 or rsi < 45)
    print(f"         Kondisi Beli -> Dip:{cond_dip} | Hijau:{is_green}\n")

