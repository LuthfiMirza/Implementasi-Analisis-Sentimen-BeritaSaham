"""
Backtest komprehensif drawdown-bounce vs momentum untuk kandidat eksploratif: TINS & PSAB.
Memakai data riwayat historis penuh dari data/stocks/TINS.csv dan data/stocks/PSAB.csv.
"""
from __future__ import annotations

import pathlib
import sys
import numpy as np
import pandas as pd

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
STOCKS_DIR = REPO_ROOT / "data" / "stocks"

DROP_THRESHOLD = -0.05
DRAWDOWN_THRESHOLD = -0.20
PULLBACK_THRESHOLD = 0.02
TARGET_HOLD_DAYS = 10
ROUND_TRIP_COST = 0.008
EPISODE_GAP_DAYS = 15
BOOTSTRAP_N = 10_000
MOMENTUM_RSI_THRESHOLD = 60

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def load_data(ticker: str) -> pd.DataFrame:
    csv_file = STOCKS_DIR / f"{ticker}.csv"
    if not csv_file.exists():
        raise FileNotFoundError(f"{csv_file} tidak ditemukan")
    df = pd.read_csv(csv_file)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)
    df["Close"] = df["close"]
    df["ret_2d"] = df["Close"].pct_change(2, fill_method=None)
    df["dd_20d"] = df["Close"] / df["Close"].rolling(20).max() - 1
    df["rsi14"] = rsi(df["Close"])
    return df

def simulate_trade(df: pd.DataFrame, trigger_idx: int, signal_type: str) -> dict | None:
    entry_idx = trigger_idx + 1
    if entry_idx >= len(df):
        return None
    entry_price = float(df.iloc[entry_idx]["Close"])
    if pd.isna(entry_price) or entry_price <= 0:
        return None

    use_trailing = (signal_type != "ganda")
    peak = entry_price
    exit_price = None
    exit_day = TARGET_HOLD_DAYS
    exit_reason = "time_10d"

    for d in range(1, TARGET_HOLD_DAYS + 1):
        day_idx = entry_idx + d
        if day_idx >= len(df):
            return None
        curr_price = float(df.iloc[day_idx]["Close"])
        if pd.isna(curr_price) or curr_price <= 0:
            return None
        
        if curr_price > peak:
            peak = curr_price
        
        if use_trailing:
            pullback = (curr_price - peak) / peak
            if pullback <= -PULLBACK_THRESHOLD:
                exit_price = curr_price
                exit_day = d
                exit_reason = f"trailing_stop_day_{d}"
                break
    
    if exit_price is None:
        exit_price = float(df.iloc[entry_idx + TARGET_HOLD_DAYS]["Close"])
    
    gross_return = (exit_price / entry_price) - 1.0
    net_return = gross_return - ROUND_TRIP_COST

    return {
        "trigger_date": df.iloc[trigger_idx]["date"],
        "entry_date": df.iloc[entry_idx]["date"],
        "exit_date": df.iloc[entry_idx + exit_day]["date"],
        "entry_price": entry_price,
        "exit_price": exit_price,
        "signal_type": signal_type,
        "gross_return": gross_return,
        "net_return": net_return,
        "hold_days": exit_day,
        "exit_reason": exit_reason,
    }

def to_episodes(trades: list[dict]) -> list[list[dict]]:
    if not trades:
        return []
    sorted_trades = sorted(trades, key=lambda t: t["trigger_date"])
    episodes = [[sorted_trades[0]]]
    for t in sorted_trades[1:]:
        gap = (t["trigger_date"] - episodes[-1][-1]["trigger_date"]).days
        if gap > EPISODE_GAP_DAYS:
            episodes.append([t])
        else:
            episodes[-1].append(t)
    return episodes

def run_backtest_for_ticker(ticker: str, strategy: str = "drawdown", start_date=None) -> dict:
    df = load_data(ticker)
    if start_date:
        start_dt = pd.to_datetime(start_date).date()
        df = df[df["date"] >= start_dt].reset_index(drop=True)
    
    raw_trades = []
    for idx in range(20, len(df) - TARGET_HOLD_DAYS - 1):
        row = df.iloc[idx]
        if strategy == "drawdown":
            ret2d_hit = bool(row["ret_2d"] <= DROP_THRESHOLD)
            dd_hit = bool(row["dd_20d"] <= DRAWDOWN_THRESHOLD)
            if not (ret2d_hit or dd_hit):
                continue
            signal_type = "ganda" if (ret2d_hit and dd_hit) else ("ret2d" if ret2d_hit else "drawdown")
        elif strategy == "momentum":
            if pd.isna(row["rsi14"]) or row["rsi14"] <= MOMENTUM_RSI_THRESHOLD:
                continue
            signal_type = "momentum"
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        trade = simulate_trade(df, idx, signal_type)
        if trade:
            raw_trades.append(trade)

    episodes = to_episodes(raw_trades)
    first_trades = [ep[0] for ep in episodes]

    if not first_trades:
        return {"ticker": ticker, "strategy": strategy, "n_episodes": 0}

    rets = [t["net_return"] for t in first_trades]
    win_rate = np.mean([r > 0 for r in rets]) * 100
    avg_ret = np.mean(rets) * 100
    med_ret = np.median(rets) * 100
    total_compounded = (np.prod([1 + r for r in rets]) - 1) * 100
    
    # B&H comparison over the same overall period
    bnh_ret = (df["Close"].iloc[-1] / df["Close"].iloc[0] - 1) * 100

    # Gates P1-P4
    n_ep = len(first_trades)
    p1_pass = False
    p2_pass = False
    p3_pass = False
    p4_pass = False

    if n_ep >= 6:
        # P1: 70/30 split
        split_70 = int(n_ep * 0.70)
        holdout_rets_70 = rets[split_70:]
        # P1: 60/40 split
        split_60 = int(n_ep * 0.60)
        holdout_rets_60 = rets[split_60:]
        p1_pass = bool(np.mean(holdout_rets_70) > 0 and np.mean(holdout_rets_60) > 0)
        
        # P2: beats buy & hold annualized or total
        p2_pass = bool(total_compounded > bnh_ret)

        # P3: drop top 5% winners
        n_drop = max(1, int(round(n_ep * 0.05)))
        sorted_rets = sorted(rets)
        trimmed_rets = sorted_rets[:-n_drop]
        p3_pass = bool(np.mean(trimmed_rets) > 0)

        # P4: bootstrap CI95
        rng = np.random.default_rng(42)
        boots = [np.mean(rng.choice(rets, size=n_ep, replace=True)) for _ in range(BOOTSTRAP_N)]
        ci_lower = np.percentile(boots, 2.5) * 100
        p4_pass = bool(ci_lower > 0)
    else:
        ci_lower = 0.0

    return {
        "ticker": ticker,
        "strategy": strategy,
        "period": f"{df['date'].iloc[0]} -> {df['date'].iloc[-1]}",
        "n_episodes": n_ep,
        "n_raw_trades": len(raw_trades),
        "win_rate": win_rate,
        "avg_return_pct": avg_ret,
        "median_return_pct": med_ret,
        "total_compounded_pct": total_compounded,
        "bnh_return_pct": bnh_ret,
        "p1_holdout": p1_pass,
        "p2_beat_bnh": p2_pass,
        "p3_no_top5pct": p3_pass,
        "p4_bootstrap": p4_pass,
        "ci_lower_pct": ci_lower,
    }

def print_report(title: str, res: dict):
    strat_name = "DRAWDOWN BOUNCE" if res["strategy"] == "drawdown" else "MOMENTUM (RSI > 60)"
    print(f"\n{'='*70}")
    print(f"  {title}: {res['ticker']} [{strat_name}]")
    print(f"{'='*70}")
    if res.get("n_episodes", 0) == 0:
        print("  Tidak ada episode sinyal yang ditemukan.")
        return
    print(f"  Rentang Data       : {res['period']}")
    print(f"  Jumlah Episode     : {res['n_episodes']} episode (dari {res['n_raw_trades']} trigger mentah)")
    print(f"  Win Rate           : {res['win_rate']:.1f}%")
    print(f"  Rata-rata Return   : {res['avg_return_pct']:+.2f}% net")
    print(f"  Median Return      : {res['median_return_pct']:+.2f}% net")
    print(f"  Total Compounded   : {res['total_compounded_pct']:+.1f}%")
    print(f"  Buy & Hold Saham   : {res['bnh_return_pct']:+.1f}%")
    print(f"\n  [Evaluasi Gate Statistik P1-P4]:")
    print(f"    P1 (Holdout > 0)          : {'✅ LULUS' if res['p1_holdout'] else '❌ GAGAL'}")
    print(f"    P2 (Kalahkan Buy & Hold)  : {'✅ LULUS' if res['p2_beat_bnh'] else '❌ GAGAL'}")
    print(f"    P3 (Tanpa Top 5% Winner)  : {'✅ LULUS' if res['p3_no_top5pct'] else '❌ GAGAL'}")
    print(f"    P4 (Bootstrap CI95 > 0)   : {'✅ LULUS' if res['p4_bootstrap'] else '❌ GAGAL'} (CI95 lower: {res['ci_lower_pct']:+.2f}%)")

if __name__ == "__main__":
    for ticker in ["TINS", "PSAB"]:
        for strat in ["drawdown", "momentum"]:
            res = run_backtest_for_ticker(ticker, strategy=strat, start_date="2024-01-01")
            print_report(f"REZIM MODERN (2024 - 2026)", res)
