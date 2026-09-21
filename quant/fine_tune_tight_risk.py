"""
Penyempurnaan Risk Management Bottom-to-Top TINS:
Tujuan: Membatasi minus maksimal di angka 2% - 3% (menghindari -5%),
sambil menjaga modal akhir tetap tinggi (mendekati atau melampaui Rp 18.8M).
"""
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

def run_simulation(name, sl_pct=0.03, sl_mode="close", use_be=False, be_trigger=0.03, time_stop_days=None):
    trades = []
    pos = 0
    entry_p = 0
    entry_d = None
    entry_idx = 0
    peak_p = 0
    be_active = False
    
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
                entry_idx = i
                peak_p = entry_p
                be_active = False
        else:
            if row["high"] > peak_p:
                peak_p = row["high"]
                
            gain_high = (row["high"] - entry_p) / entry_p
            if use_be and gain_high >= be_trigger:
                be_active = True
                
            current_sl = entry_p if be_active else entry_p * (1.0 - sl_pct)
            
            days_in_trade = i - entry_idx
            
            # Cek Exit:
            # 1. SL Hit
            hit_sl = False
            sl_price = 0
            sl_reason = ""
            
            if sl_mode == "intraday":
                if row["low"] <= current_sl:
                    hit_sl = True
                    sl_price = row["open"] if row["open"] < current_sl else current_sl
                    sl_reason = "Break-Even (0% Impas)" if be_active else f"Stop Loss (-{sl_pct*100:.1f}%)"
            else: # close
                if row["close"] <= current_sl:
                    hit_sl = True
                    sl_price = row["close"]
                    sl_reason = "Break-Even Close (0% Impas)" if be_active else f"Cut Loss Close (-{sl_pct*100:.1f}%)"
                    
            # 2. Pola Jual di Pucuk
            cond_overbought = (row["stoch_k"] > 75 or row["bb_pct_b"] > 0.85 or row["rsi14"] > 65)
            cond_top_reversal = (cond_overbought and row["close"] < row["open"])
            cond_pullback = ((row["close"] - peak_p) / peak_p <= -0.035 and (peak_p - entry_p)/entry_p >= 0.04)
            
            # 3. Time Stop jika macet
            cond_time_stop = (time_stop_days is not None and days_in_trade >= time_stop_days and (row["close"] <= entry_p * 1.01))
            
            exit_now = False
            exit_p = 0
            reason = ""
            
            if hit_sl:
                exit_now = True
                exit_p = sl_price
                reason = sl_reason
            elif cond_top_reversal:
                exit_now = True
                exit_p = row["close"]
                reason = "Jual Pucuk (Overbought)"
            elif cond_pullback:
                exit_now = True
                exit_p = row["close"]
                reason = "Kunci Untung (Pullback 3.5%)"
            elif cond_time_stop:
                exit_now = True
                exit_p = row["close"]
                reason = f"Time Stop ({time_stop_days} Hari Macet)"
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
                    "days": days_in_trade,
                    "reason": reason
                })
                pos = 0
                
    cap = 10_000_000
    for t in trades:
        cap *= (1 + t["net_ret"])
    wins = [t for t in trades if t["net_ret"] > 0]
    wr = len(wins) / len(trades) * 100 if trades else 0
    losses = [t["net_ret"] for t in trades if t["net_ret"] <= 0]
    max_l = min(losses)*100 if losses else 0
    avg_l = (sum(losses)/len(losses))*100 if losses else 0
    return name, trades, cap, wr, max_l, avg_l

scenarios = [
    ("1. Baseline Kemarin (SL 4% Close)", 0.04, "close", False, 0.0, None),
    ("2. SL 3.0% Close (Ketat di Sore)", 0.03, "close", False, 0.0, None),
    ("3. SL 2.5% Close (Ketat di Sore)", 0.025, "close", False, 0.0, None),
    ("4. SL 3.0% Close + Break-Even (+3%)", 0.03, "close", True, 0.03, None),
    ("5. SL 2.5% Close + Break-Even (+2.5%)", 0.025, "close", True, 0.025, None),
    ("6. SL 3.0% Intraday (Auto Broker)", 0.03, "intraday", False, 0.0, None),
    ("7. SL 3.0% Close + Time Stop 3 Hari", 0.03, "close", False, 0.0, 3),
]

print(f"{'Skenario':<42} | {'Trd':<4} | {'WinRate':<7} | {'MaxMinus':<9} | {'AvgMinus':<9} | {'Saldo Akhir':<15}")
print("=" * 100)

for s in scenarios:
    name, tr, cap, wr, ml, al = run_simulation(s[0], s[1], s[2], s[3], s[4], s[5])
    print(f"{name:<42} | {len(tr):<4} | {wr:6.1f}% | {ml:7.2f}%  | {al:7.2f}%  | Rp {cap:12,.0f}")

