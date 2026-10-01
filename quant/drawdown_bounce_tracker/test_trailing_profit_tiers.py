#!/usr/bin/env python3
"""Simulasi dan Uji Coba Multi-Tier Trailing Stop & Profit Protection
Menguji hipotesis:
1. Saham naik +3% -> Stop Loss digeser ke Breakeven (+0.8% cover fee).
2. Saham naik +5% -> Trailing Stop 1.5% dari puncak (kunci min +3.5%).
3. Saham naik +7% -> Trailing Stop 1.0% dari puncak (kunci super ketat di pucuk).
"""

from pathlib import Path
import numpy as np
import pandas as pd

STOCKS = ["DEWA", "BUMI", "BRPT", "ESSA", "TINS", "ENRG"]
COST = 0.008  # 0.80% round-trip broker fee


def load_stock_df(ticker: str) -> pd.DataFrame:
    csv_path = Path(f"data/stocks/{ticker}.csv")
    if not csv_path.is_file():
        return pd.DataFrame()
    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)
    df["ret_2d"] = (df["close"] - df["close"].shift(2)) / df["close"].shift(2)
    rolling_max_20 = df["close"].rolling(20).max()
    df["dd_20d"] = (df["close"] - rolling_max_20) / rolling_max_20
    df = df[df["date"] >= pd.to_datetime("2024-01-01").date()].reset_index(drop=True)
    return df


def get_signals(df: pd.DataFrame):
    signals = []
    for i in range(20, len(df) - 1):
        if (df.loc[i, "ret_2d"] <= -0.05) or (df.loc[i, "dd_20d"] <= -0.20):
            entry_idx = i + 1
            signals.append((df.loc[entry_idx, "date"], entry_idx, df.loc[entry_idx, "close"]))

    non_overlapping = []
    last_idx = -999
    for s in signals:
        if s[1] > last_idx:
            non_overlapping.append(s)
            last_idx = s[1] + 10
    return non_overlapping


def simulate(df: pd.DataFrame, signals: list, mode: str):
    results = []
    reasons = []

    for dt, entry_idx, entry_p in signals:
        peak_p = entry_p
        exit_p = entry_p
        exit_r = "10d"

        for d in range(1, 11):
            curr_idx = entry_idx + d
            if curr_idx >= len(df):
                break
            high = df.loc[curr_idx, "high"]
            low = df.loc[curr_idx, "low"]
            close = df.loc[curr_idx, "close"]

            if high > peak_p:
                peak_p = high

            gain_from_entry = (peak_p - entry_p) / entry_p

            if mode == "1_baseline_bh10d":
                if d == 10:
                    exit_p = close
                    exit_r = "10d"
                    break

            elif mode == "2_fixed_sl3_tp5":
                if low <= entry_p * 0.97:
                    exit_p = entry_p * 0.97
                    exit_r = "SL_3%"
                    break
                elif high >= entry_p * 1.05:
                    exit_p = entry_p * 1.05
                    exit_r = "TP_5%"
                    break
                elif d == 10:
                    exit_p = close
                    exit_r = "10d"
                    break

            elif mode == "3_ts2_classic":
                if (peak_p - low) / peak_p >= 0.02 and d > 1:
                    exit_p = peak_p * 0.98
                    exit_r = "TS_2%"
                    break
                elif d == 10:
                    exit_p = close
                    exit_r = "10d"
                    break

            elif mode == "4_multitier_protection":
                # Tier 3: Jika pernah untung >= +7%, trailing stop super ketat 1.0% dari puncak
                if gain_from_entry >= 0.07:
                    if (peak_p - low) / peak_p >= 0.01:
                        exit_p = peak_p * 0.99
                        exit_r = "Lock_TS_1%_at_Pucuk_7%+"
                        break
                # Tier 2: Jika pernah untung >= +5%, trailing stop 1.5% dari puncak
                elif gain_from_entry >= 0.05:
                    if (peak_p - low) / peak_p >= 0.015:
                        exit_p = peak_p * 0.985
                        exit_r = "Lock_TS_1.5%_at_5%+"
                        break
                # Tier 1: Jika pernah untung >= +3%, kunci di Break-Even (+0.8% cover fee)
                elif gain_from_entry >= 0.03:
                    if low <= entry_p * 1.008:
                        exit_p = entry_p * 1.008
                        exit_r = "BEP_Protection"
                        break
                # Belum pernah untung +3%: Hard Stop Loss 3%
                else:
                    if low <= entry_p * 0.97:
                        exit_p = entry_p * 0.97
                        exit_r = "Hard_SL_3%"
                        break

                if d == 10:
                    exit_p = close
                    exit_r = "10d"
                    break

        net_ret = (exit_p / entry_p) - 1.0 - COST
        results.append(net_ret)
        reasons.append(exit_r)

    arr = np.array(results)
    if len(arr) == 0:
        return 0, 0, 0, 0, 0
    win_rate = (arr > 0).mean() * 100
    avg_ret = arr.mean() * 100
    total_ret = ((1 + arr).prod() - 1) * 100
    worst_trade = arr.min() * 100
    return len(arr), win_rate, avg_ret, total_ret, worst_trade


def main():
    print("=" * 80)
    print("HASIL UJI COBA ATURAN TRAILING STOP & PROTEKSI PROFIT (2024 - 2026)")
    print("=" * 80)
    modes = [
        ("1_baseline_bh10d", "Baseline Kaku: Tahan 10 Hari (Tanpa SL/TS)"),
        ("2_fixed_sl3_tp5", "Kaku Tradisional: SL 3% / TP 5%"),
        ("3_ts2_classic", "Trailing Stop Klasik 2% dari Puncak"),
        ("4_multitier_protection", "Multi-Tier: BEP @+3%, TS 1.5% @+5%, TS 1.0% @+7% (Hard SL 3%)"),
    ]

    for ticker in STOCKS:
        df = load_stock_df(ticker)
        if df.empty:
            continue
        signals = get_signals(df)
        print(f"\nSaham: {ticker} (Total Sinyal Independen: {len(signals)})")
        print("-" * 80)
        for m_id, m_label in modes:
            n, wr, avg, tot, worst = simulate(df, signals, m_id)
            print(f"  {m_label:<62s} | WR: {wr:5.1f}% | Avg: {avg:+5.2f}% | Total: {tot:+7.1f}% | Worst: {worst:+5.2f}%")


if __name__ == "__main__":
    main()
