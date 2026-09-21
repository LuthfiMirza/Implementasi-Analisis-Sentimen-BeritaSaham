"""
Simulasi Pengurangan Risiko pada Bottom-to-Top Strategy:
Membatasi risiko maksimal di angka 2% - 3%, mencegah minus 5%,
dan melihat apakah modal akhir bisa melampaui Rp 18.850.659!
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

def test_risk_variations():
    configs = [
        ("A. Baseline Kemarin (Hard SL 4% Close)", 0.04, False, 0.0, 0.035, "close"),
        ("B. Hard SL 3.0% Intraday", 0.03, False, 0.0, 0.035, "intraday"),
        ("C. Hard SL 2.5% Intraday", 0.025, False, 0.0, 0.035, "intraday"),
        ("D. Hard SL 2.0% Intraday", 0.02, False, 0.0, 0.035, "intraday"),
        ("E. Solusi Juara: SL 3.0% + Break-Even 0% (Trigger +3%)", 0.03, True, 0.03, 0.035, "intraday"),
        ("F. Solusi Juara: SL 2.5% + Break-Even 0% (Trigger +2.5%)", 0.025, True, 0.025, 0.03, "intraday"),
        ("G. Super Protektif: SL 3.0% + BE 0% + Trailing Profit 2.5%", 0.03, True, 0.03, 0.025, "intraday"),
    ]
    
    for cfg_name, sl_pct, use_be, be_trig, peak_pullback, trigger_type in configs:
        trades = []
        pos = 0
        entry_p = 0
        entry_d = None
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
                # Pola Ambil di Bawah (Bottom Rebound)
                cond_dip = (row["stoch_k"] < 30 or row["bb_pct_b"] < 0.25 or row["rsi14"] < 45)
                cond_green = (row["close"] > row["open"] and row["close"] > df.iloc[i-1]["close"])
                
                if cond_dip and cond_green:
                    pos = 1
                    entry_p = row["close"]
                    entry_d = curr_d
                    peak_p = entry_p
                    be_active = False
            else:
                if row["high"] > peak_p:
                    peak_p = row["high"]
                    
                # Cek apakah Break-Even aktif
                gain_high = (row["high"] - entry_p) / entry_p
                if use_be and gain_high >= be_trig:
                    be_active = True
                    
                # Tentukan level Stop Loss hari ini
                # Jika BE aktif: stop loss = entry_p
                # Jika belum BE: stop loss = entry_p * (1 - sl_pct)
                current_sl = entry_p if be_active else entry_p * (1.0 - sl_pct)
                
                # Cek Kondisi Exit:
                # 1. Stop Loss Hit (Intraday vs Close)
                hit_sl = False
                sl_exit_price = 0
                sl_reason = ""
                
                if trigger_type == "intraday":
                    if row["low"] <= current_sl:
                        hit_sl = True
                        sl_exit_price = row["open"] if row["open"] < current_sl else current_sl
                        sl_reason = "Break-Even (0% Impas)" if be_active else f"Stop Loss (-{sl_pct*100:.1f}%)"
                else: # close
                    if row["close"] <= current_sl:
                        hit_sl = True
                        sl_exit_price = row["close"]
                        sl_reason = f"Cut Loss Close (-{sl_pct*100:.1f}%)"
                        
                # 2. Pola Jual di Pucuk (Overbought Reversal)
                cond_overbought = (row["stoch_k"] > 75 or row["bb_pct_b"] > 0.85 or row["rsi14"] > 65)
                cond_top_reversal = (cond_overbought and row["close"] < row["open"])
                
                # 3. Pullback dari Puncak (Penguncian Untung)
                cond_pullback = ((row["close"] - peak_p) / peak_p <= -peak_pullback and (peak_p - entry_p)/entry_p >= 0.04)
                
                exit_now = False
                exit_p = 0
                reason = ""
                
                if hit_sl:
                    exit_now = True
                    exit_p = sl_exit_price
                    reason = sl_reason
                elif cond_top_reversal:
                    exit_now = True
                    exit_p = row["close"]
                    reason = "Jual Pucuk (Overbought)"
                elif cond_pullback:
                    exit_now = True
                    exit_p = row["close"]
                    reason = f"Kunci Untung (Pullback {peak_pullback*100:.1f}%)"
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
        wr = len(wins) / len(trades) * 100 if trades else 0
        losses = [t["net_ret"] for t in trades if t["net_ret"] <= 0]
        max_l = min(losses)*100 if losses else 0
        
        print(f"{cfg_name:<60} | Trd: {len(trades):<2} | WR: {wr:5.1f}% | Max Minus: {max_l:6.2f}% | Modal: Rp {cap:12,.0f}")
        
        # Simpan trade list untuk skenario E (Juara)
        if cfg_name.startswith("E."):
            global best_trades
            best_trades = trades

test_risk_variations()
