"""
Simulasi Lengkap 4 Strategi Berjalan pada Saham TINS
Periode: 1 Desember 2025 s/d 21 September 2026
Modal Awal: Rp 10.000.000 (All-in compounded per episode independen)
Biaya Transaksi: 0.8% round-trip (fee broker beli + jual + pajak)
"""
from __future__ import annotations
import pathlib
import numpy as np
import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV_FILE = REPO_ROOT / "data" / "stocks" / "TINS.csv"

STARTING_CAPITAL = 10_000_000
ROUND_TRIP_COST = 0.008
EPISODE_GAP_DAYS = 15
START_DATE = pd.to_datetime("2025-12-01").date()
END_DATE = pd.to_datetime("2026-09-21").date()

df = pd.read_csv(CSV_FILE)
df["date"] = pd.to_datetime(df["date"]).dt.date
df = df.sort_values("date").reset_index(drop=True)

# Indikator teknikal dasar
delta = df["close"].diff()
gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
rs = gain / loss.replace(0, np.nan)
df["rsi14"] = 100 - (100 / (1 + rs))

df["ret_2d"] = df["close"].pct_change(2, fill_method=None)
df["ret_5d"] = df["close"].pct_change(5, fill_method=None)
df["dd_20d"] = df["close"] / df["close"].rolling(20).max() - 1
df["bottom_10d_prev"] = df["close"].shift(1).rolling(10).min()

def group_episodes(raw_trades):
    if not raw_trades:
        return []
    sorted_trades = sorted(raw_trades, key=lambda t: t["entry_date"])
    episodes = []
    for t in sorted_trades:
        if not episodes or (t["entry_date"] - episodes[-1][-1]["entry_date"]).days > EPISODE_GAP_DAYS:
            episodes.append([t])
        else:
            episodes[-1].append(t)
    # Ambil trade pertama per episode independen (aturan produksi anti-stacking)
    return [ep[0] for ep in episodes]

# ==========================================
# 1. STRATEGI GABUNGAN (DRAWDOWN-BOUNCE)
# ==========================================
def sim_gabungan():
    raw = []
    for idx in range(20, len(df) - 11):
        row = df.iloc[idx]
        entry_idx = idx + 1
        entry_date = df.iloc[entry_idx]["date"]
        if not (START_DATE <= entry_date <= END_DATE):
            continue
            
        hit = (row["ret_2d"] <= -0.05 or row["dd_20d"] <= -0.20)
        if not hit:
            continue
            
        entry_price = float(df.iloc[entry_idx]["close"])
        peak = entry_price
        exit_price = None
        exit_day = 10
        exit_reason = "10 Hari Bursa"
        
        for d in range(1, 11):
            curr = float(df.iloc[entry_idx + d]["close"])
            if curr > peak:
                peak = curr
            # Trailing stop 2% dari puncak
            pullback = (curr - peak) / peak
            if pullback <= -0.02:
                exit_price = curr
                exit_day = d
                exit_reason = f"Trailing Stop 2% (Hari ke-{d})"
                break
        if exit_price is None:
            exit_price = float(df.iloc[entry_idx + 10]["close"])
            
        net_ret = (exit_price / entry_price) - 1.0 - ROUND_TRIP_COST
        raw.append({
            "trigger_date": row["date"],
            "entry_date": entry_date,
            "exit_date": df.iloc[entry_idx + exit_day]["date"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "net_ret": net_ret,
            "exit_reason": exit_reason,
            "hold_days": exit_day,
        })
    return group_episodes(raw)

# ==========================================
# 2. STRATEGI MOMENTUM (RSI > 60)
# ==========================================
def sim_momentum():
    raw = []
    for idx in range(20, len(df) - 11):
        row = df.iloc[idx]
        entry_idx = idx + 1
        entry_date = df.iloc[entry_idx]["date"]
        if not (START_DATE <= entry_date <= END_DATE):
            continue
            
        if pd.isna(row["rsi14"]) or row["rsi14"] <= 60:
            continue
            
        entry_price = float(df.iloc[entry_idx]["close"])
        peak = entry_price
        exit_price = None
        exit_day = 10
        exit_reason = "10 Hari Bursa"
        
        for d in range(1, 11):
            curr = float(df.iloc[entry_idx + d]["close"])
            if curr > peak:
                peak = curr
            pullback = (curr - peak) / peak
            if pullback <= -0.02:
                exit_price = curr
                exit_day = d
                exit_reason = f"Trailing Stop 2% (Hari ke-{d})"
                break
        if exit_price is None:
            exit_price = float(df.iloc[entry_idx + 10]["close"])
            
        net_ret = (exit_price / entry_price) - 1.0 - ROUND_TRIP_COST
        raw.append({
            "trigger_date": row["date"],
            "entry_date": entry_date,
            "exit_date": df.iloc[entry_idx + exit_day]["date"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "net_ret": net_ret,
            "exit_reason": exit_reason,
            "hold_days": exit_day,
        })
    return group_episodes(raw)

# ==========================================
# 3. STRATEGI BOTTOM REBOUND
# ==========================================
def sim_bottom_rebound():
    raw = []
    for idx in range(20, len(df) - 11):
        row = df.iloc[idx]
        prev = df.iloc[idx - 1]
        entry_idx = idx + 1
        entry_date = df.iloc[entry_idx]["date"]
        if not (START_DATE <= entry_date <= END_DATE):
            continue
            
        # Trigger: Close tembus naik >= 5% dari min 10d
        level = row["bottom_10d_prev"] * 1.05
        prev_level = prev["bottom_10d_prev"] * 1.05
        hit = (row["close"] >= level and prev["close"] < prev_level)
        if not hit:
            continue
            
        entry_price = float(df.iloc[entry_idx]["close"])
        peak = entry_price
        exit_price = None
        exit_day = 10
        exit_reason = "10 Hari Bursa"
        
        for d in range(1, 11):
            curr = float(df.iloc[entry_idx + d]["close"])
            if curr > peak:
                peak = curr
            pullback = (curr - peak) / peak
            if pullback <= -0.02:
                exit_price = curr
                exit_day = d
                exit_reason = f"Trailing Stop 2% (Hari ke-{d})"
                break
        if exit_price is None:
            exit_price = float(df.iloc[entry_idx + 10]["close"])
            
        net_ret = (exit_price / entry_price) - 1.0 - ROUND_TRIP_COST
        raw.append({
            "trigger_date": row["date"],
            "entry_date": entry_date,
            "exit_date": df.iloc[entry_idx + exit_day]["date"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "net_ret": net_ret,
            "exit_reason": exit_reason,
            "hold_days": exit_day,
        })
    return group_episodes(raw)

# ==========================================
# 4. STRATEGI SELF-RADAR V1 (Overnight Scalp)
# ==========================================
def sim_self_radar():
    raw = []
    # Self radar: entry beli sore jam closing (hari yang sama dengan trigger)
    # Risk: trailing stop 1% di hari-hari berikutnya
    for idx in range(20, len(df) - 6):
        row = df.iloc[idx]
        entry_date = row["date"]
        if not (START_DATE <= entry_date <= END_DATE):
            continue
            
        hit = (row["rsi14"] >= 60 and row["ret_5d"] >= 0.05 and row["dd_20d"] >= -0.05)
        if not hit:
            continue
            
        entry_price = float(row["close"])
        peak = entry_price
        exit_price = None
        exit_day = 5
        exit_reason = "5 Hari Hold"
        
        for d in range(1, 6):
            curr = float(df.iloc[idx + d]["close"])
            if curr > peak:
                peak = curr
            pullback = (curr - peak) / peak
            # Trailing stop 1%
            if pullback <= -0.01:
                exit_price = curr
                exit_day = d
                exit_reason = f"Trailing Stop 1% (Hari ke-{d})"
                break
        if exit_price is None:
            exit_price = float(df.iloc[idx + 5]["close"])
            
        net_ret = (exit_price / entry_price) - 1.0 - ROUND_TRIP_COST
        raw.append({
            "trigger_date": row["date"],
            "entry_date": entry_date,
            "exit_date": df.iloc[idx + exit_day]["date"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "net_ret": net_ret,
            "exit_reason": exit_reason,
            "hold_days": exit_day,
        })
    return group_episodes(raw)

strategies = [
    ("1. GABUNGAN (Drawdown-Bounce)", sim_gabungan()),
    ("2. MOMENTUM (RSI > 60)", sim_momentum()),
    ("3. BOTTOM REBOUND (Pantul +5%)", sim_bottom_rebound()),
    ("4. SELF-RADAR V1 (Overnight Scalp)", sim_self_radar()),
]

for name, trades in strategies:
    print("\n" + "=" * 95)
    print(f"  STRATEGI: {name}")
    print("=" * 95)
    if not trades:
        print("  [!] Tidak ada sinyal yang terpicu dalam periode ini.")
        continue
        
    cap = STARTING_CAPITAL
    wins = [t for t in trades if t["net_ret"] > 0]
    wr = len(wins) / len(trades) * 100
    
    print(f"  {'#':<3} {'Tanggal Beli':<13} {'Harga Beli':>10} {'Tanggal Jual':<13} {'Harga Jual':>10} {'Net PnL%':>10} {'Saldo Akhir':>16} {'Alasan Exit'}")
    print("  " + "-" * 92)
    
    for i, t in enumerate(trades, 1):
        cap *= (1 + t["net_ret"])
        print(f"  {i:<3} {str(t['entry_date']):<13} Rp {t['entry_price']:>7,.0f} {str(t['exit_date']):<13} Rp {t['exit_price']:>7,.0f} {t['net_ret']*100:>+9.2f}% Rp {cap:>13,.0f}  {t['exit_reason']}")
        
    pnl_nominal = cap - STARTING_CAPITAL
    pnl_pct = (cap / STARTING_CAPITAL - 1) * 100
    print("  " + "-" * 92)
    print(f"  TOTAL TRADE: {len(trades)} | WIN: {len(wins)} | LOSS: {len(trades)-len(wins)} | WIN RATE: {wr:.1f}%")
    print(f"  MODAL AWAL : Rp {STARTING_CAPITAL:,.0f}")
    print(f"  MODAL AKHIR: Rp {cap:,.0f} ({pnl_pct:+.2f}% | PnL: Rp {pnl_nominal:+,.0f})")

