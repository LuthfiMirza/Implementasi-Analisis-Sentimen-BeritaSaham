"""
Simulasi riil trading TINS dari 1 Desember 2025 sampai 21 September 2026.
Modal awal: Rp 10.000.000.
Mengevaluasi:
1. Strategi Drawdown Bounce (GABUNGAN: ret_2d <= -5% atau dd_20d <= -20%)
   - Varian A: Exit Trailing Stop 2% / 10 Hari (Produksi Fase BP)
   - Varian B: Fixed Hold 10 Hari (Fase AB/AC murni)
2. Strategi Momentum (RSI14 > 60)
3. Buy & Hold (Beli 1 Des 2025, hold sampai sekarang)

Menghitung:
- 100% modal per episode (compounding)
- 20% modal per trade (standard position sizing repo)
- Daftar trade lengkap (Tanggal Entry, Harga Beli, Tanggal Exit, Harga Jual, PnL %, Nominal PnL, Saldo)
"""
from __future__ import annotations

import pathlib
import numpy as np
import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CSV_FILE = REPO_ROOT / "data" / "stocks" / "TINS.csv"

STARTING_CAPITAL = 10_000_000
ROUND_TRIP_COST = 0.008
TARGET_HOLD_DAYS = 10
PULLBACK_THRESHOLD = 0.02
EPISODE_GAP_DAYS = 15
START_DATE = pd.to_datetime("2025-12-01").date()
END_DATE = pd.to_datetime("2026-09-21").date()

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

df = pd.read_csv(CSV_FILE)
df["date"] = pd.to_datetime(df["date"]).dt.date
df = df.sort_values("date").reset_index(drop=True)
df["Close"] = df["close"]
df["ret_2d"] = df["Close"].pct_change(2, fill_method=None)
df["dd_20d"] = df["Close"] / df["Close"].rolling(20).max() - 1
df["rsi14"] = rsi(df["Close"])

# Filter window
df_window = df[(df["date"] >= START_DATE) & (df["date"] <= END_DATE)].reset_index(drop=True)

# 1. BUY & HOLD
p_start = float(df_window.iloc[0]["Close"])
d_start = df_window.iloc[0]["date"]
p_end = float(df_window.iloc[-1]["Close"])
d_end = df_window.iloc[-1]["date"]
bnh_gross = (p_end / p_start) - 1.0
bnh_net = bnh_gross - ROUND_TRIP_COST
bnh_final_cap = STARTING_CAPITAL * (1 + bnh_net)

print("=" * 75)
print("  SIMULASI TRADING TINS — MODAL RP 10.000.000")
print(f"  Periode: {d_start} s/d {d_end}")
print(f"  Harga TINS Awal (1 Des 2025): Rp {p_start:,.0f}")
print(f"  Harga TINS Akhir (21 Sep 2026): Rp {p_end:,.0f}")
print(f"  Return Buy & Hold (Net): {bnh_net*100:+.2f}%")
print(f"  Modal Rp 10 Juta via Buy & Hold menjadi: Rp {bnh_final_cap:,.0f}")
print("=" * 75)

def simulate_strategy(strategy_name: str, use_trailing: bool = True):
    trades = []
    # Loop over original df to avoid edge issues
    for idx in range(20, len(df) - TARGET_HOLD_DAYS - 1):
        row = df.iloc[idx]
        entry_idx = idx + 1
        entry_date = df.iloc[entry_idx]["date"]
        if not (START_DATE <= entry_date <= END_DATE):
            continue

        if strategy_name == "DRAWDOWN_BOUNCE":
            ret2d_hit = bool(row["ret_2d"] <= -0.05)
            dd_hit = bool(row["dd_20d"] <= -0.20)
            if not (ret2d_hit or dd_hit):
                continue
            sig_type = "ganda" if (ret2d_hit and dd_hit) else ("ret2d" if ret2d_hit else "drawdown")
        elif strategy_name == "MOMENTUM":
            if pd.isna(row["rsi14"]) or row["rsi14"] <= 60:
                continue
            sig_type = "momentum"
        else:
            continue

        entry_price = float(df.iloc[entry_idx]["Close"])
        exit_price = None
        exit_day = TARGET_HOLD_DAYS
        exit_reason = "10_hari"
        peak = entry_price

        for d in range(1, TARGET_HOLD_DAYS + 1):
            curr = float(df.iloc[entry_idx + d]["Close"])
            if curr > peak:
                peak = curr
            if use_trailing and sig_type != "ganda":
                pullback = (curr - peak) / peak
                if pullback <= -PULLBACK_THRESHOLD:
                    exit_price = curr
                    exit_day = d
                    exit_reason = f"TS_2%_hari_{d}"
                    break
        if exit_price is None:
            exit_price = float(df.iloc[entry_idx + TARGET_HOLD_DAYS]["Close"])

        net_ret = (exit_price / entry_price) - 1.0 - ROUND_TRIP_COST
        trades.append({
            "trigger_date": row["date"],
            "entry_date": entry_date,
            "exit_date": df.iloc[entry_idx + exit_day]["date"],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "net_ret": net_ret,
            "exit_reason": exit_reason,
            "hold_days": exit_day,
            "sig_type": sig_type,
        })

    # Group into episodes (gap > 15 days)
    if not trades:
        print(f"\n[!] Tidak ada trade untuk {strategy_name}")
        return

    episodes = []
    sorted_trades = sorted(trades, key=lambda t: t["entry_date"])
    for t in sorted_trades:
        if not episodes or (t["entry_date"] - episodes[-1][-1]["entry_date"]).days > EPISODE_GAP_DAYS:
            episodes.append([t])
        else:
            episodes[-1].append(t)

    # Ambil trade pertama per episode (aturan produksi tidak stacking trade dalam 1 episode)
    first_trades = [ep[0] for ep in episodes]

    print(f"\n>>> STRATEGI: {strategy_name} (Trailing Stop: {use_trailing})")
    print(f"    Total Trigger Mentah: {len(trades)} | Episode Independen: {len(first_trades)}")
    
    # 1. 100% Capital Reinvested (Compounding All-In per episode)
    cap_allin = STARTING_CAPITAL
    # 2. 20% Position Fraction per trade (Fixed-fraction risk)
    cap_fractional = STARTING_CAPITAL

    print(f"\n    {'#':<3} {'Entry':<12} {'Exit':<12} {'Alasan':<14} {'Beli':>8} {'Jual':>8} {'Net PnL%':>10} {'Saldo (All-in)':>18} {'Saldo (20% Size)':>18}")
    print(f"    {'-'*3} {'-'*12} {'-'*12} {'-'*14} {'-'*8} {'-'*8} {'-'*10} {'-'*18} {'-'*18}")

    for i, t in enumerate(first_trades, start=1):
        ret = t["net_ret"]
        pnl_allin = cap_allin * ret
        cap_allin += pnl_allin

        pnl_frac = (cap_fractional * 0.20) * ret
        cap_fractional += pnl_frac

        print(f"    {i:<3} {str(t['entry_date']):<12} {str(t['exit_date']):<12} {t['exit_reason']:<14} {t['entry_price']:>8,.0f} {t['exit_price']:>8,.0f} {ret*100:>+9.2f}% {cap_allin:>18,.0f} {cap_fractional:>18,.0f}")

    win_rate = np.mean([t["net_ret"] > 0 for t in first_trades]) * 100
    avg_ret = np.mean([t["net_ret"] for t in first_trades]) * 100
    
    print(f"\n    Ringkasan {strategy_name}:")
    print(f"    - Win Rate             : {win_rate:.1f}% ({(np.array([t['net_ret'] for t in first_trades]) > 0).sum()}/{len(first_trades)})")
    print(f"    - Rata-rata per Trade  : {avg_ret:+.2f}%")
    print(f"    - Modal Rp 10 Juta (All-In Compounded)   -> Rp {cap_allin:,.0f} ({((cap_allin/STARTING_CAPITAL)-1)*100:+.2f}%)")
    print(f"    - Modal Rp 10 Juta (20% Risk-Fractional) -> Rp {cap_fractional:,.0f} ({((cap_fractional/STARTING_CAPITAL)-1)*100:+.2f}%)")

simulate_strategy("DRAWDOWN_BOUNCE", use_trailing=True)
simulate_strategy("DRAWDOWN_BOUNCE", use_trailing=False)
simulate_strategy("MOMENTUM", use_trailing=True)
