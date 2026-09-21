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

START_DATE = pd.to_datetime("2025-12-01").date()
END_DATE = pd.to_datetime("2026-09-21").date()
ROUND_TRIP_COST = 0.008

def run_test(tp_quick=0.035, sl_pct=0.03):
    trades = []
    pos = 0
    entry_p = 0
    entry_d = None
    peak_p = 0
    
    for i in range(20, len(df)):
        row = df.iloc[i]
        curr_d = row["date"]
        if curr_d > END_DATE:
            break
            
        if pos == 0:
            if curr_d < START_DATE:
                continue
            cond_dip = (row["stoch_k"] < 30 or row["bb_pct_b"] < 0.25 or row["rsi14"] < 45)
            cond_green = (row["close"] > row["open"] and row["close"] > df.iloc[i-1]["close"])
            if cond_dip and cond_green:
                pos = 1
                entry_p = row["close"]
                entry_d = curr_d
                peak_p = entry_p
        else:
            if row["high"] > peak_p:
                peak_p = row["high"]
                
            # Cek Trailing Stop dari Puncak jika sudah pernah cuan >= 3%
            gain_peak = (peak_p - entry_p) / entry_p
            
            # SL price
            sl_price = entry_p * (1.0 - sl_pct)
            
            # Cek apakah kena SL intraday
            hit_sl = (row["low"] <= sl_price)
            
            # Cek apakah pernah untung >= 3% dan mundur 2.5% dari puncak (Penguncian Untung)
            hit_trailing_profit = (gain_peak >= 0.03 and row["close"] <= peak_p * (1.0 - 0.025))
            
            # Pola Jual di Pucuk
            cond_overbought = (row["stoch_k"] > 75 or row["bb_pct_b"] > 0.85 or row["rsi14"] > 65)
            cond_top_reversal = (cond_overbought and row["close"] < row["open"])
            
            exit_now = False
            exit_p = 0
            reason = ""
            
            if hit_sl:
                exit_now = True
                exit_p = row["open"] if row["open"] < sl_price else sl_price
                reason = f"Stop Loss (-{sl_pct*100:.1f}%)"
            elif hit_trailing_profit:
                exit_now = True
                exit_p = row["close"]
                reason = "Kunci Profit (Mundur 2.5% dari Puncak)"
            elif cond_top_reversal:
                exit_now = True
                exit_p = row["close"]
                reason = "Jual Pucuk (Overbought)"
            elif i == len(df) - 1:
                exit_now = True
                exit_p = row["close"]
                reason = "EOD"
                
            if exit_now:
                net_ret = (exit_p / entry_p) - 1.0 - ROUND_TRIP_COST
                trades.append({
                    "entry_d": entry_d,
                    "exit_d": curr_d,
                    "entry_p": entry_p,
                    "exit_p": exit_p,
                    "net_ret": net_ret,
                    "reason": reason
                })
                pos = 0
                
    cap = 10_000_000
    for t in trades:
        cap *= (1 + t["net_ret"])
    wins = [t for t in trades if t["net_ret"] > 0]
    wr = len(wins) / len(trades) * 100
    losses = [t["net_ret"] for t in trades if t["net_ret"] <= 0]
    max_l = min(losses)*100
    return trades, cap, wr, max_l

tr, cap, wr, ml = run_test(tp_quick=0.035, sl_pct=0.03)
print(f"Hasil: Trade={len(tr)} | WR={wr:.1f}% | Max Minus={ml:.2f}% | Saldo Akhir=Rp {cap:,.0f}\n")
c = 10_000_000
for i, t in enumerate(tr, 1):
    c *= (1 + t["net_ret"])
    ed, xd, ep, xp, nr, r = t["entry_d"], t["exit_d"], t["entry_p"], t["exit_p"], t["net_ret"]*100, t["reason"]
    print(f"  {i:<2} {ed} @ {ep:>5,.0f} -> {xd} @ {xp:>5,.0f} | Ret: {nr:+6.2f}% | Saldo: Rp {c:>12,.0f} ({r})")
