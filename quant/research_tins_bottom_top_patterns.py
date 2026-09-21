"""
Riset Komprehensif TINS:
Bagian 1: Eksperimen Exit MOMENTUM Tanpa Batas 10 Hari Bursa
Bagian 2: Deteksi Pola Matematis Titik Terbawah (Bottom) dan Titik Teratas (Peak)
"""
import pandas as pd
import numpy as np

df = pd.read_csv("data/stocks/TINS.csv")
df["date"] = pd.to_datetime(df["date"]).dt.date
df = df.sort_values("date").reset_index(drop=True)

# Indikator Teknikal
delta = df["close"].diff()
gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
rs = gain / loss.replace(0, np.nan)
df["rsi14"] = 100 - (100 / (1 + rs))

# Stochastic Oscillator
low14 = df["low"].rolling(14).min()
high14 = df["high"].rolling(14).max()
df["stoch_k"] = 100 * (df["close"] - low14) / (high14 - low14).replace(0, np.nan)
df["stoch_d"] = df["stoch_k"].rolling(3).mean()

# Moving Averages & Bands
df["sma20"] = df["close"].rolling(20).mean()
df["std20"] = df["close"].rolling(20).std()
df["bb_upper"] = df["sma20"] + 2 * df["std20"]
df["bb_lower"] = df["sma20"] - 2 * df["std20"]
df["bb_pct_b"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)

df["ema10"] = df["close"].ewm(span=10, adjust=False).mean()
df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

# Volume MA
df["vol_ma20"] = df["volume"].rolling(20).mean()
df["vol_ratio"] = df["volume"] / df["vol_ma20"].replace(0, np.nan)

# MACD
ema12 = df["close"].ewm(span=12, adjust=False).mean()
ema26 = df["close"].ewm(span=26, adjust=False).mean()
df["macd"] = ema12 - ema26
df["macd_sig"] = df["macd"].ewm(span=9, adjust=False).mean()
df["macd_hist"] = df["macd"] - df["macd_sig"]

# Candlestick characteristics
df["candle_body"] = (df["close"] - df["open"]).abs()
df["candle_range"] = df["high"] - df["low"]
df["is_green"] = df["close"] > df["open"]
df["lower_wick"] = np.minimum(df["open"], df["close"]) - df["low"]
df["upper_wick"] = df["high"] - np.maximum(df["open"], df["close"])
df["is_hammer"] = (df["lower_wick"] > 2 * df["candle_body"]) & (df["upper_wick"] < 0.2 * df["candle_range"])
df["is_bullish_engulfing"] = (df["is_green"]) & (df["close"].shift(1) < df["open"].shift(1)) & (df["close"] > df["open"].shift(1)) & (df["open"] < df["close"].shift(1))

# ==============================================================================
# BAGIAN 1: SIMULASI MOMENTUM TANPA PATOKAN KAKU 10 HARI BURSA
# ==============================================================================
START_DATE = pd.to_datetime("2025-12-01").date()
END_DATE = pd.to_datetime("2026-09-21").date()
ROUND_TRIP_COST = 0.008

print("=" * 80)
print("  BAGIAN 1: HASIL STRATEGI MOMENTUM TANPA PATOKAN 10 HARI BURSA")
print("  Periode: 1 Des 2025 s/d 21 Sep 2026 | Modal Awal: Rp 10.000.000")
print("=" * 80)

def test_momentum_exits():
    # Skenario Exit yang diuji:
    # 1. Baseline Lama: Trailing Stop 2% / Maksimal 10 Hari (Pembanding)
    # 2. Pure Trailing Stop 2% (TANPA batas hari bursa)
    # 3. Pure Trailing Stop 3.5% (Memberi ruang nafas)
    # 4. Pure Trailing Stop 5.0% (Trend rider lebar)
    # 5. Exit saat RSI Menembus Balik Turun di Bawah 60 (Momentum Hilang)
    # 6. Exit saat Close Tembus Turun di Bawah EMA10 (Trend Follower)
    # 7. Kombinasi Cerdas: Trailing Stop 3.5% ATAU Exit saat RSI Menembus < 55
    
    scenarios = [
        ("1. Patokan Lama (TS 2% + Max 10 Hari)", "ts_days", 0.02, 10),
        ("2. Pure Trailing Stop 2% (No Time Limit)", "pure_ts", 0.02, None),
        ("3. Pure Trailing Stop 3.5% (No Time Limit)", "pure_ts", 0.035, None),
        ("4. Pure Trailing Stop 5.0% (No Time Limit)", "pure_ts", 0.05, None),
        ("5. Exit Momentum Mati (RSI14 < 60)", "rsi_exit", 60, None),
        ("6. Exit Trend Melemah (Close < EMA10)", "ema_exit", 10, None),
        ("7. Kombinasi: TS 3.5% + RSI Cross < 55", "combo", 0.035, 55),
    ]
    
    results = []
    
    for s_name, s_type, param1, param2 in scenarios:
        trades = []
        pos = 0
        entry_p = 0
        entry_d = None
        entry_idx = 0
        peak_p = 0
        
        for i in range(20, len(df)):
            row = df.iloc[i]
            curr_d = row["date"]
            if curr_d > END_DATE:
                break
                
            if pos == 0:
                if curr_d < START_DATE:
                    continue
                # Trigger Momentum: RSI14 > 60 kemarin, entry hari ini
                prev_row = df.iloc[i - 1]
                if prev_row["rsi14"] > 60:
                    pos = 1
                    entry_p = row["close"]
                    entry_d = curr_d
                    entry_idx = i
                    peak_p = entry_p
            else:
                # Update peak
                if row["high"] > peak_p:
                    peak_p = row["high"]
                    
                days_held = i - entry_idx
                exit_now = False
                reason = ""
                
                if s_type == "ts_days":
                    pullback = (row["close"] - peak_p) / peak_p
                    if pullback <= -param1:
                        exit_now = True
                        reason = f"TS {param1*100:.0f}%"
                    elif days_held >= param2:
                        exit_now = True
                        reason = f"{param2} Hari"
                elif s_type == "pure_ts":
                    pullback = (row["close"] - peak_p) / peak_p
                    if pullback <= -param1:
                        exit_now = True
                        reason = f"TS {param1*100:.1f}%"
                elif s_type == "rsi_exit":
                    if row["rsi14"] < param1:
                        exit_now = True
                        reason = f"RSI < {param1}"
                elif s_type == "ema_exit":
                    if row["close"] < row["ema10"]:
                        exit_now = True
                        reason = "Close < EMA10"
                elif s_type == "combo":
                    pullback = (row["close"] - peak_p) / peak_p
                    if pullback <= -param1:
                        exit_now = True
                        reason = f"TS {param1*100:.1f}%"
                    elif row["rsi14"] < param2:
                        exit_now = True
                        reason = f"RSI < {param2}"
                        
                # End of data exit
                if not exit_now and i == len(df) - 1:
                    exit_now = True
                    reason = "EOD"
                    
                if exit_now:
                    exit_p = row["close"]
                    net_ret = (exit_p / entry_p) - 1.0 - ROUND_TRIP_COST
                    trades.append({
                        "entry_d": entry_d,
                        "exit_d": curr_d,
                        "entry_p": entry_p,
                        "exit_p": exit_p,
                        "net_ret": net_ret,
                        "days": days_held,
                        "reason": reason
                    })
                    pos = 0
                    
        # Filter episode independen
        episodes = []
        for t in sorted(trades, key=lambda x: x["entry_d"]):
            if not episodes or (t["entry_d"] - episodes[-1][-1]["entry_d"]).days > 15:
                episodes.append([t])
            else:
                episodes[-1].append(t)
        first_trades = [ep[0] for ep in episodes]
        
        cap = 10_000_000
        for t in first_trades:
            cap *= (1 + t["net_ret"])
            
        wins = [t for t in first_trades if t["net_ret"] > 0]
        wr = len(wins) / len(first_trades) * 100 if first_trades else 0
        avg_days = np.mean([t["days"] for t in first_trades]) if first_trades else 0
        results.append({
            "name": s_name,
            "trades": len(first_trades),
            "win_rate": wr,
            "avg_days": avg_days,
            "capital": cap,
            "trades_list": first_trades
        })
        
    for r in results:
        print(f"  {r['name']:<42} | Trade: {r['trades']:<2} | WinRate: {r['win_rate']:5.1f}% | Avg Hold: {r['avg_days']:4.1f} hari | Saldo: Rp {r['capital']:12,.0f}")
        
    return results

res = test_momentum_exits()

# Detail per trade untuk pemenang
print("\n" + "=" * 80)
print("  DETAIL TRADE PEMENANG MOMENTUM (TANPA PATOKAN 10 HARI)")
print("=" * 80)
# Tampilkan detail trade untuk Skenario 3 (Pure TS 3.5%) dan Skenario 7 (Combo)
best = res[2] # Pure TS 3.5%
print(f"\n>>> {best['name']} (Saldo Akhir: Rp {best['capital']:,.0f}):")
cap = 10_000_000
for i, t in enumerate(best["trades_list"], 1):
    cap *= (1 + t["net_ret"])
    print(f"    Trade {i}: Beli {t['entry_d']} @ {t['entry_p']:,.0f} -> Jual {t['exit_d']} @ {t['exit_p']:,.0f} | Hold {t['days']} hr | Ret: {t['net_ret']*100:+6.2f}% | Saldo: Rp {cap:,.0f} ({t['reason']})")

combo = res[6] # Combo
print(f"\n>>> {combo['name']} (Saldo Akhir: Rp {combo['capital']:,.0f}):")
cap = 10_000_000
for i, t in enumerate(combo["trades_list"], 1):
    cap *= (1 + t["net_ret"])
    print(f"    Trade {i}: Beli {t['entry_d']} @ {t['entry_p']:,.0f} -> Jual {t['exit_d']} @ {t['exit_p']:,.0f} | Hold {t['days']} hr | Ret: {t['net_ret']*100:+6.2f}% | Saldo: Rp {cap:,.0f} ({t['reason']})")

