"""
Test Formula Entry & Exit Adaptif TINS berdasarkan Karakteristik Swing Sebenarnya.
Entry:
  - Stochastic %K < 25 (Oversold)
  - Bollinger %B < 0.25 (Dekat/tembus Lower Band) atau RSI 35-50
  - Konfirmasi Rebound: Close > Close kemarin ATAU Stoch K cross D
Exit:
  - Trailing Stop Adaptif: 1.0 x ATR (bukan 2% kaku)
  - ATAU Target Overbought: RSI > 68 ATAU Stoch %K > 80 ATAU %B > 0.95
"""
from __future__ import annotations

import pathlib
import numpy as np
import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV_FILE = REPO_ROOT / "data" / "stocks" / "TINS.csv"

STARTING_CAPITAL = 10_000_000
ROUND_TRIP_COST = 0.008
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
df["atr_pct"] = (df["atr14"] / df["close"])

# 3. Bollinger Bands (20, 2)
df["bb_mid"] = df["close"].rolling(20).mean()
bb_std = df["close"].rolling(20).std()
df["bb_upper"] = df["bb_mid"] + 2 * bb_std
df["bb_lower"] = df["bb_mid"] - 2 * bb_std
df["bb_pct_b"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

# 4. Stochastic (14, 3)
low14 = df["low"].rolling(14).min()
high14 = df["high"].rolling(14).max()
df["stoch_k"] = 100 * (df["close"] - low14) / (high14 - low14)
df["stoch_d"] = df["stoch_k"].rolling(3).mean()

# 5. MACD
ema12 = df["close"].ewm(span=12, adjust=False).mean()
ema26 = df["close"].ewm(span=26, adjust=False).mean()
df["macd"] = ema12 - ema26
df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
df["macd_hist"] = df["macd"] - df["macd_signal"]

# Simulasi Strategi Adaptif
trades = []
in_position = False
entry_price = 0.0
entry_date = None
peak_price = 0.0
entry_atr = 0.0

for i in range(25, len(df)):
    row = df.iloc[i]
    prev = df.iloc[i-1]
    curr_date = row["date"]
    
    if curr_date < START_DATE:
        continue
    if curr_date > END_DATE:
        break
        
    if not in_position:
        # Syarat Entry:
        # 1. Stochastic oversold di bar sebelumnya atau sekarang (< 25)
        # 2. Bollinger %B < 0.30 (dekat lower band) ATAU RSI < 48
        # 3. Konfirmasi Reversal: Rebound Close > Open (candle hijau) ATAU Stoch K crossing up D
        cond_oversold = (prev["stoch_k"] < 25 or row["stoch_k"] < 25)
        cond_band = (prev["bb_pct_b"] < 0.30 or prev["rsi14"] < 48)
        cond_reversal = (row["close"] > row["open"] and row["close"] > prev["close"])
        
        if cond_oversold and cond_band and cond_reversal:
            in_position = True
            entry_price = row["close"]
            entry_date = curr_date
            peak_price = entry_price
            entry_atr = row["atr14"]
    else:
        # Sedang dalam posisi: cek Exit
        if row["high"] > peak_price:
            peak_price = row["high"]
            
        # Alasan Exit 1: Target Overbought (Take Profit)
        cond_tp = (row["rsi14"] > 68 or row["stoch_k"] > 80 or row["bb_pct_b"] > 0.95)
        
        # Alasan Exit 2: Trailing Stop adaptif = 1.2 x ATR dari peak (bukan 2% kaku)
        ts_threshold = max(0.05, (entry_atr / entry_price) * 1.0)
        pullback = (row["close"] - peak_price) / peak_price
        cond_sl = (pullback <= -ts_threshold)
        
        # Alasan Exit 3: Emergency Cut Loss jika close di bawah entry - (1.5 x ATR)
        cond_cutloss = (row["close"] < entry_price - (1.5 * entry_atr))
        
        if cond_tp or cond_sl or cond_cutloss or i == len(df) - 1:
            exit_price = row["close"]
            exit_date = curr_date
            reason = "TP (Overbought)" if cond_tp else ("Trailing Stop ATR" if cond_sl else "Cut Loss ATR")
            net_ret = (exit_price / entry_price) - 1.0 - ROUND_TRIP_COST
            
            trades.append({
                "entry_date": entry_date,
                "exit_date": exit_date,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "net_ret": net_ret,
                "reason": reason,
                "hold_days": (exit_date - entry_date).days,
            })
            in_position = False

print("=" * 80)
print("  HASIL SIMULASI FORMULA ENTRY & EXIT ADAPTIF TINS")
print(f"  Modal Awal : Rp {STARTING_CAPITAL:,}")
print(f"  Periode    : {START_DATE} s/d {END_DATE}")
print("=" * 80)

cap = STARTING_CAPITAL
print(f"\n  {'#':<3} {'Entry':<12} {'Exit':<12} {'Alasan Exit':<20} {'Beli':>8} {'Jual':>8} {'Net PnL%':>10} {'Saldo Akhir':>16}")
print(f"  {'-'*3} {'-'*12} {'-'*12} {'-'*20} {'-'*8} {'-'*8} {'-'*10} {'-'*16}")

for idx, t in enumerate(trades, start=1):
    ret = t["net_ret"]
    cap = cap * (1 + ret)
    print(f"  {idx:<3} {str(t['entry_date']):<12} {str(t['exit_date']):<12} {t['reason']:<20} {t['entry_price']:>8,.0f} {t['exit_price']:>8,.0f} {ret*100:>+9.2f}% Rp {cap:>13,.0f}")

win_rate = np.mean([t["net_ret"] > 0 for t in trades]) * 100
avg_ret = np.mean([t["net_ret"] for t in trades]) * 100

print("\n" + "-" * 80)
print(f"  Ringkasan Strategi Adaptif:")
print(f"  - Total Trade        : {len(trades)} trade")
print(f"  - Win Rate           : {win_rate:.1f}% ({(np.array([t['net_ret'] for t in trades]) > 0).sum()}/{len(trades)})")
print(f"  - Rata-rata per Trade: {avg_ret:+.2f}%")
print(f"  - Modal Rp 10 Juta   -> Rp {cap:,.0f} ({((cap/STARTING_CAPITAL)-1)*100:+.2f}%)")
print("=" * 80)
