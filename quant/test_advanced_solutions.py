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

high_low = df["high"] - df["low"]
high_close = (df["high"] - df["close"].shift(1)).abs()
low_close = (df["low"] - df["close"].shift(1)).abs()
tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
df["atr14"] = tr.rolling(14).mean()

df["bb_mid"] = df["close"].rolling(20).mean()
bb_std = df["close"].rolling(20).std()
df["bb_pct_b"] = (df["close"] - (df["bb_mid"] - 2 * bb_std)) / (4 * bb_std)

low14 = df["low"].rolling(14).min()
high14 = df["high"].rolling(14).max()
df["stoch_k"] = 100 * (df["close"] - low14) / (high14 - low14).replace(0, np.nan)
df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

start_date = pd.to_datetime("2025-12-01").date()
end_date = pd.to_datetime("2026-09-21").date()
df_test = df[(df["date"] >= start_date) & (df["date"] <= end_date)].copy().reset_index(drop=True)

# Evaluasi beberapa kombinasi solusi
def test_strategy(name, use_trend=True, sl_pct=0.035, use_be=True, be_trigger=0.03):
    capital = 10_000_000
    pos = 0
    entry_p = 0
    entry_d = None
    be_active = False
    trades = []
    
    for i, row in df_test.iterrows():
        if pos == 0:
            # Entry: Swing dip + rebound candle hijau
            cond_dip = (row["rsi14"] < 40 or row["stoch_k"] < 30 or row["bb_pct_b"] < 0.20)
            cond_green = row["close"] > row["open"]
            cond_trend = (row["close"] > row["ema50"] or row["ema20"] > row["ema50"]) if use_trend else True
            
            if cond_dip and cond_green and cond_trend:
                pos = 1
                entry_p = row["close"]
                entry_d = row["date"]
                be_active = False
        else:
            # Check BE trigger
            max_run = (row["high"] - entry_p) / entry_p
            if use_be and max_run >= be_trigger:
                be_active = True
                
            current_sl = entry_p if be_active else entry_p * (1.0 - sl_pct)
            
            # TP condition: RSI > 68 or Stoch > 80 or Gain >= 12%
            cond_tp = (row["rsi14"] > 68 or row["stoch_k"] > 80 or (row["high"] - entry_p)/entry_p >= 0.15)
            
            hit_sl = False
            exit_p = 0
            reason = ""
            
            if row["low"] <= current_sl:
                hit_sl = True
                exit_p = row["open"] if row["open"] < current_sl else current_sl
                reason = "Break-Even SL (0%)" if be_active else f"Stop Loss (-{sl_pct*100:.1f}%)"
                
            if hit_sl:
                net_ret = (exit_p / entry_p) - 1.0 - 0.008
                capital *= (1 + net_ret)
                trades.append({
                    "entry_d": entry_d,
                    "exit_d": row["date"],
                    "entry_p": entry_p,
                    "exit_p": exit_p,
                    "net_ret": net_ret,
                    "reason": reason,
                    "capital": capital
                })
                pos = 0
            elif cond_tp or i == len(df_test) - 1:
                exit_p = row["close"]
                net_ret = (exit_p / entry_p) - 1.0 - 0.008
                capital *= (1 + net_ret)
                trades.append({
                    "entry_d": entry_d,
                    "exit_d": row["date"],
                    "entry_p": entry_p,
                    "exit_p": exit_p,
                    "net_ret": net_ret,
                    "reason": "Take Profit" if cond_tp else "EOD",
                    "capital": capital
                })
                pos = 0
                
    wins = [t for t in trades if t["net_ret"] > 0]
    wr = len(wins)/len(trades)*100 if trades else 0
    losses = [t["net_ret"] for t in trades if t["net_ret"] <= 0]
    max_l = min(losses)*100 if losses else 0
    avg_l = (sum(losses)/len(losses))*100 if losses else 0
    return name, len(trades), wr, max_l, avg_l, capital, trades

strategies = [
    ("1. User: SL 2% Tanpa Filter (Intraday)", False, 0.02, False, 0),
    ("2. User: SL 2% + Break-Even 0%", False, 0.02, True, 0.03),
    ("3. Sweet Spot: SL 3.5% + Break-Even 0%", False, 0.035, True, 0.035),
    ("4. Trend Filter EMA50 + SL 3.5%", True, 0.035, False, 0),
    ("5. Solusi Juara (Trend + BE + SL 3.5%)", True, 0.035, True, 0.035),
    ("6. Solusi Konservatif (Trend + BE + SL 2.5%)", True, 0.025, True, 0.03),
]

print(f"{'Strategi':<45} | {'Trd':<4} | {'WinRate':<7} | {'MaxMinus':<9} | {'AvgMinus':<9} | {'Saldo Akhir':<14}")
print("=" * 105)
for s in strategies:
    n, trd, wr, ml, al, cap, tr_list = test_strategy(s[0], s[1], s[2], s[3], s[4])
    print(f"{n:<45} | {trd:<4} | {wr:6.1f}% | {ml:7.2f}%  | {al:7.2f}%  | Rp {cap:12,.0f}")
