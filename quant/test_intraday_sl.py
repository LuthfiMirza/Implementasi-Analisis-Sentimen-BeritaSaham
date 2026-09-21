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
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

start_date = pd.to_datetime("2025-12-01").date()
end_date = pd.to_datetime("2026-09-21").date()
df_test = df[(df["date"] >= start_date) & (df["date"] <= end_date)].copy().reset_index(drop=True)

def simulate(sl_pct=0.02, trigger_mode="intraday", filter_ema=False):
    # trigger_mode: 
    # 'intraday': order stop loss dipasang di sistem broker (trigger saat Low <= SL)
    # 'close': stop loss dievaluasi di penutupan market (trigger saat Close <= SL)
    capital = 10_000_000
    pos = 0
    entry_p = 0
    entry_d = None
    trades = []
    
    for i, row in df_test.iterrows():
        if pos == 0:
            cond_swing = (row["rsi14"] < 35 or row["stoch_k"] < 25 or row["bb_pct_b"] < 0.15)
            cond_rebound = (row["close"] > row["open"])
            cond_trend = (row["close"] > row["ema50"]) if filter_ema else True
            
            if cond_swing and cond_rebound and cond_trend:
                pos = 1
                entry_p = row["close"]
                entry_d = row["date"]
        else:
            sl_price = entry_p * (1.0 - sl_pct)
            cond_tp = (row["rsi14"] > 68 or row["stoch_k"] > 80 or row["bb_pct_b"] > 0.95)
            
            hit_sl = False
            exit_p = 0
            reason = ""
            
            if trigger_mode == "intraday":
                if row["low"] <= sl_price:
                    hit_sl = True
                    # Jika gap down open di bawah SL: kena di open
                    exit_p = row["open"] if row["open"] < sl_price else sl_price
                    reason = f"Intraday SL (-{sl_pct*100:.1f}%)"
            else:
                if row["close"] <= sl_price:
                    hit_sl = True
                    exit_p = row["close"]
                    reason = f"Close SL (-{sl_pct*100:.1f}%)"
                    
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
                    "reason": "TP Overbought" if cond_tp else "EOD",
                    "capital": capital
                })
                pos = 0
                
    wins = [t for t in trades if t["net_ret"] > 0]
    wr = len(wins)/len(trades)*100 if trades else 0
    losses = [t["net_ret"] for t in trades if t["net_ret"] <= 0]
    max_l = min(losses)*100 if losses else 0
    avg_l = (sum(losses)/len(losses))*100 if losses else 0
    return trades, capital, wr, max_l, avg_l

print(f"{'Skenario':<35} | {'Trade':<5} | {'Win Rate':<8} | {'Max Minus':<10} | {'Avg Minus':<10} | {'Saldo Akhir':<15}")
print("-" * 95)

scenarios = [
    ("Intraday SL 2% (Broker Auto Cut)", 0.02, "intraday", False),
    ("Intraday SL 3% (Broker Auto Cut)", 0.03, "intraday", False),
    ("Intraday SL 4% (Broker Auto Cut)", 0.04, "intraday", False),
    ("Intraday SL 5% (Broker Auto Cut)", 0.05, "intraday", False),
    ("Close SL 2% (Evaluasi Penutupan)", 0.02, "close", False),
    ("Close SL 3% (Evaluasi Penutupan)", 0.03, "close", False),
    ("Filter EMA50 + Intraday SL 2%", 0.02, "intraday", True),
    ("Filter EMA50 + Intraday SL 3%", 0.03, "intraday", True),
    ("Filter EMA50 + Intraday SL 4%", 0.04, "intraday", True),
]

for name, sl, mode, fema in scenarios:
    tr, cap, wr, ml, al = simulate(sl, mode, fema)
    print(f"{name:<35} | {len(tr):<5} | {wr:6.1f}%  | {ml:8.2f}%  | {al:8.2f}%  | Rp {cap:12,.0f}")

