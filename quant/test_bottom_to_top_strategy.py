"""
Simulasi Strategi 'Bottom-to-Top' (Ambil di Dasar, Jual di Pucuk) pada TINS
Periode: 1 Desember 2025 s/d 21 September 2026 | Modal Awal: Rp 10.000.000
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
df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

START_DATE = pd.to_datetime("2025-12-01").date()
END_DATE = pd.to_datetime("2026-09-21").date()
ROUND_TRIP_COST = 0.008

def run_bottom_to_top(use_trend_filter=True, hard_sl=0.04):
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
                
            # POLA AMBIL DI BAWAH (BOTTOM):
            # 1. Stochastic %K oversold / swing dip (< 30) ATAU BB %B dekat pita bawah (< 0.25) ATAU RSI < 45
            cond_dip = (row["stoch_k"] < 30 or row["bb_pct_b"] < 0.25 or row["rsi14"] < 45)
            # 2. Reversal Candle Hijau (Close > Open dan Close > Close Kemarin)
            cond_green = (row["close"] > row["open"] and row["close"] > df.iloc[i-1]["close"])
            # 3. Filter Tren Sehat (Close > EMA50) jika diaktifkan
            cond_trend = (row["close"] > row["ema50"]) if use_trend_filter else True
            
            if cond_dip and cond_green and cond_trend:
                pos = 1
                entry_p = row["close"]
                entry_d = curr_d
                peak_p = entry_p
        else:
            if row["high"] > peak_p:
                peak_p = row["high"]
                
            # POLA JUAL DI PUCUK (TOP):
            # 1. Stochastic Overbought (> 75) ATAU BB %B menembus pita atas (> 0.85) ATAU RSI > 65
            cond_overbought = (row["stoch_k"] > 75 or row["bb_pct_b"] > 0.85 or row["rsi14"] > 65)
            # 2. Tanda pelemahan di pucuk: Candle merah (Close < Open) ATAU harga mundur 3% dari puncak
            cond_top_reversal = (cond_overbought and row["close"] < row["open"])
            cond_pullback_from_peak = ((row["close"] - peak_p) / peak_p <= -0.035 and (peak_p - entry_p)/entry_p >= 0.05)
            
            # 3. Proteksi Cut Loss jika salah prediksi
            cond_sl = ((row["close"] - entry_p) / entry_p <= -hard_sl)
            
            exit_now = False
            reason = ""
            
            if cond_top_reversal:
                exit_now = True
                reason = "Jual di Pucuk (Overbought Reversal)"
            elif cond_pullback_from_peak:
                exit_now = True
                reason = "Jual Penguncian Puncak (Pullback 3.5%)"
            elif cond_sl:
                exit_now = True
                reason = f"Cut Loss (-{hard_sl*100:.1f}%)"
            elif i == len(df) - 1:
                exit_now = True
                reason = "EOD Terakhir"
                
            if exit_now:
                exit_p = row["close"]
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
                
    # Evaluasi modal
    cap = 10_000_000
    for t in trades:
        cap *= (1 + t["net_ret"])
    wins = [t for t in trades if t["net_ret"] > 0]
    wr = len(wins) / len(trades) * 100 if trades else 0
    return trades, cap, wr

# 1. Bottom-to-Top Dengan Filter Tren EMA50 (Sangat Disarankan)
tr_trend, cap_trend, wr_trend = run_bottom_to_top(use_trend_filter=True, hard_sl=0.04)

# 2. Bottom-to-Top Tanpa Filter Tren (Murni Osilator)
tr_pure, cap_pure, wr_pure = run_bottom_to_top(use_trend_filter=False, hard_sl=0.04)

print("=" * 90)
print(f"  STRATEGI 1: BOTTOM-TO-TOP DENGAN FILTER TREN EMA50")
print(f"  Total Trade: {len(tr_trend)} | Win Rate: {wr_trend:.1f}% | Modal Rp 10 Juta -> Rp {cap_trend:,.0f} ({((cap_trend/10_000_000)-1)*100:+.2f}%)")
print("=" * 90)
print(f"  {'#':<3} {'Tanggal Beli':<13} {'Harga Beli':>10} {'Tanggal Jual':<13} {'Harga Jual':>10} {'Net PnL%':>10} {'Saldo':>16} {'Alasan Exit'}")
print("  " + "-" * 88)
c = 10_000_000
for i, t in enumerate(tr_trend, 1):
    c *= (1 + t["net_ret"])
    print(f"  {i:<3} {str(t['entry_d']):<13} Rp {t['entry_p']:>7,.0f} {str(t['exit_d']):<13} Rp {t['exit_p']:>7,.0f} {t['net_ret']*100:>+9.2f}% Rp {c:>13,.0f}  {t['reason']}")

print("\n" + "=" * 90)
print(f"  STRATEGI 2: BOTTOM-TO-TOP TANPA FILTER TREN (MURNI OSILATOR)")
print(f"  Total Trade: {len(tr_pure)} | Win Rate: {wr_pure:.1f}% | Modal Rp 10 Juta -> Rp {cap_pure:,.0f} ({((cap_pure/10_000_000)-1)*100:+.2f}%)")
print("=" * 90)
print(f"  {'#':<3} {'Tanggal Beli':<13} {'Harga Beli':>10} {'Tanggal Jual':<13} {'Harga Jual':>10} {'Net PnL%':>10} {'Saldo':>16} {'Alasan Exit'}")
print("  " + "-" * 88)
c = 10_000_000
for i, t in enumerate(tr_pure, 1):
    c *= (1 + t["net_ret"])
    print(f"  {i:<3} {str(t['entry_d']):<13} Rp {t['entry_p']:>7,.0f} {str(t['exit_d']):<13} Rp {t['exit_p']:>7,.0f} {t['net_ret']*100:>+9.2f}% Rp {c:>13,.0f}  {t['reason']}")

