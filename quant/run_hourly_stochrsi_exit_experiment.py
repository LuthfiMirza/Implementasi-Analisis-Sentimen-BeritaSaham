#!/usr/bin/env python3
"""Fase AE: does an HOURLY Stoch RSI overbought exit beat the daily fixed-10-day hold?

Why this exists (and why it is different from Fase AD, which already failed):

The user pointed out two real errors in Fase AD. First, they use **Stoch RSI** (a stochastic
computed over RSI values), not the classic price stochastic Fase AD tested -- on 23 Jul 2026 the
two disagreed sharply (Stoch RSI 100.0 vs classic 78.3). Second, they trade off the **1-hour**
chart, while every backtest in this project so far used daily closes. Live-checked: on hourly
bars, Stoch RSI %K hit exactly 100.0 at 23 Jul 11:00 WIB with price at 194 -- the top of the
move, the same bar their real trailing stop fired. That single observation is real but proves
nothing on its own (the same indicator screamed oversold all through 22 Jul while price sat flat,
and again all through 24 Jul while price kept falling), so this tests it properly.

Design, kept comparable to Fase AB/AD:
  - Entry: unchanged, the validated daily rule (IHSG and stock both <= -5% over 2 days), entered
    at the next daily close. Only the EXIT differs between variants.
  - Exit variants (all reported, no cherry-picking):
      daily_fixed_10d   -- current production baseline
      hourly_k_gt80     -- first hourly bar where Stoch RSI %K > 80
      hourly_k_gt90     -- stricter threshold
      hourly_kd_cross   -- %K crosses back DOWN through %D while above 80 (classic exit trigger)
  - Hourly exits are capped at the same 20 trading days as Fase AD so a position cannot be held
    open-ended when the condition never fires -- otherwise the comparison would be rigged.
  - Exit fills at the CLOSE of the triggering hourly bar, never its high (no lookahead, no
    assuming a perfect fill at the peak).
  - 0.80% round-trip cost, chronological 70/30 discovery/holdout split.

Data: data/intraday/{TICKER}_1h.csv (yfinance, ~3 years -- the maximum hourly history available).
Because hourly history starts 2023-07-18, this covers far fewer entry signals than Fase AB's
22-year daily test. Sample size is reported prominently and the minimum-n rule still applies.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

TICKERS = ["BUMI", "DEWA"]
DROP_THRESHOLD = -0.05
ROUND_TRIP_COST = 0.008
DISCOVERY_FRACTION = 0.70
FIXED_HOLD_DAYS = 10
MAX_HOLD_DAYS = 20
MIN_SIGNALS_TO_CONCLUDE = 20

REPORT_JSON = Path("output/prediction_research/hourly_stochrsi_exit_experiment.json")
REPORT_TXT = Path("output/prediction_research/hourly_stochrsi_exit_experiment.txt")


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def stoch_rsi(close: pd.Series, rsi_len: int = 14, stoch_len: int = 14, k: int = 3, d: int = 3):
    """Matches the TradingView Stoch RSI defaults the user has configured (K=3, D=3, RSI 14,
    Stochastic 14, source=close)."""
    r = rsi_wilder(close, rsi_len)
    lo = r.rolling(stoch_len).min()
    hi = r.rolling(stoch_len).max()
    raw = 100 * (r - lo) / (hi - lo).replace(0, np.nan)
    k_line = raw.rolling(k).mean()
    return k_line, k_line.rolling(d).mean()


def load_daily(ticker: str) -> pd.DataFrame:
    path = "data/stocks/IHSG.csv" if ticker == "IHSG" else f"data/stocks/{ticker}.csv"
    df = pd.read_csv(path)
    date_col = "Date" if "Date" in df.columns else "date"
    close_col = "Adj Close" if "Adj Close" in df.columns else "adj_close"
    df = df.rename(columns={date_col: "date", close_col: "adj_close"})
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df = df.sort_values("date").reset_index(drop=True)
    df["ret_2d"] = df["adj_close"].pct_change(2)
    return df[["date", "adj_close", "ret_2d"]]


def load_hourly(ticker: str) -> pd.DataFrame:
    df = pd.read_csv(f"data/intraday/{ticker}_1h.csv")
    ts_col = df.columns[0]
    df = df.rename(columns={ts_col: "ts"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert("Asia/Jakarta")
    df = df.sort_values("ts").reset_index(drop=True)
    k, d = stoch_rsi(df["Close"])
    df["k"] = k
    df["d"] = d
    df["date"] = df["ts"].dt.tz_localize(None).dt.normalize()
    return df[["ts", "date", "Close", "k", "d"]]


def hourly_exit(hourly: pd.DataFrame, entry_date: pd.Timestamp, cap_date: pd.Timestamp, variant: str):
    """First hourly bar strictly AFTER the entry day's close that satisfies the variant. Returns
    (exit_price, exit_timestamp) or None if it never fires before cap_date."""
    window = hourly[(hourly["date"] > entry_date) & (hourly["date"] <= cap_date)]
    prev_k = prev_d = None
    for _, row in window.iterrows():
        k, d = row["k"], row["d"]
        if pd.isna(k) or pd.isna(d):
            continue
        fired = False
        if variant == "hourly_k_gt80":
            fired = k > 80
        elif variant == "hourly_k_gt90":
            fired = k > 90
        elif variant == "hourly_kd_cross":
            fired = prev_k is not None and prev_k >= prev_d and k < d and prev_k > 80
        if fired:
            return float(row["Close"]), row["ts"]
        prev_k, prev_d = k, d
    return None


def evaluate(daily: pd.DataFrame, hourly: pd.DataFrame, entries: list[int], variant: str) -> dict:
    returns, holds, never_fired = [], [], 0
    hourly_start = hourly["date"].min()

    for sig_idx in entries:
        entry_idx = sig_idx + 1
        if entry_idx >= len(daily):
            continue
        entry_date = daily["date"].iloc[entry_idx]
        if entry_date < hourly_start:
            continue  # no hourly coverage for this signal -- excluded from ALL variants alike
        entry_price = float(daily["adj_close"].iloc[entry_idx])

        cap_idx = min(entry_idx + MAX_HOLD_DAYS, len(daily) - 1)
        cap_date = daily["date"].iloc[cap_idx]

        if variant == "daily_fixed_10d":
            exit_idx = min(entry_idx + FIXED_HOLD_DAYS, len(daily) - 1)
            if exit_idx <= entry_idx:
                continue
            exit_price = float(daily["adj_close"].iloc[exit_idx])
            hold = exit_idx - entry_idx
        else:
            hit = hourly_exit(hourly, entry_date, cap_date, variant)
            if hit is None:
                never_fired += 1
                exit_price = float(daily["adj_close"].iloc[cap_idx])
                hold = cap_idx - entry_idx
            else:
                exit_price, exit_ts = hit
                hold = (exit_ts.tz_localize(None).normalize() - entry_date).days

        returns.append((exit_price / entry_price) - 1 - ROUND_TRIP_COST)
        holds.append(hold)

    if not returns:
        return {"n": 0}
    arr = np.array(returns)
    return {
        "n": len(arr),
        "mean_net_return": float(arr.mean()),
        "median_net_return": float(np.median(arr)),
        "win_rate": float((arr > 0).mean()),
        "mean_hold_days": float(np.mean(holds)),
        "never_fired": never_fired,
    }


def run_ticker(ticker: str, ihsg: pd.DataFrame) -> dict:
    daily = load_daily(ticker)
    hourly = load_hourly(ticker)
    merged = daily.merge(ihsg, on="date", suffixes=("_stock", "_ihsg")).dropna().reset_index(drop=True)
    merged = merged.rename(columns={"adj_close_stock": "adj_close"})

    hourly_start = hourly["date"].min()
    signal_idx = merged.index[
        (merged["ret_2d_stock"] <= DROP_THRESHOLD) & (merged["ret_2d_ihsg"] <= DROP_THRESHOLD)
    ].tolist()
    covered = [i for i in signal_idx if i + 1 < len(merged) and merged["date"].iloc[i + 1] >= hourly_start]

    split_point = int(len(covered) * DISCOVERY_FRACTION)
    discovery, holdout = covered[:split_point], covered[split_point:]

    result = {
        "ticker": ticker,
        "hourly_coverage_start": str(hourly_start.date()),
        "signals_total_daily_history": len(signal_idx),
        "signals_with_hourly_coverage": len(covered),
        "discovery_signals": len(discovery),
        "holdout_signals": len(holdout),
        "signal_dates": [str(merged["date"].iloc[i].date()) for i in covered],
        "variants": {},
    }
    for variant in ["daily_fixed_10d", "hourly_k_gt80", "hourly_k_gt90", "hourly_kd_cross"]:
        result["variants"][variant] = {
            "discovery": evaluate(merged, hourly, discovery, variant),
            "holdout": evaluate(merged, hourly, holdout, variant),
            "full_sample": evaluate(merged, hourly, covered, variant),
        }
    return result


def main() -> None:
    ihsg = load_daily("IHSG")
    results = [run_ticker(t, ihsg) for t in TICKERS]

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    lines = [
        "Fase AE: Exit Stoch RSI 1-JAM vs fixed 10-hari harian -- BUMI/DEWA",
        "=" * 84,
        "",
        "Stoch RSI (14,14,3,3) sesuai setting TradingView user, dihitung di bar 1 jam.",
        "Entry SAMA untuk semua varian (aturan harian Fase AB). Yang beda cuma cara KELUAR.",
        f"Exit di CLOSE bar pemicu (bukan high -- tanpa lookahead). Biaya {ROUND_TRIP_COST:.2%}, cap {MAX_HOLD_DAYS} hari.",
        "",
        "PENTING: data 1 jam cuma tersedia ~3 tahun (mulai 2023-07-18), jadi jumlah sinyal jauh",
        f"lebih sedikit dari uji harian 22 tahun di Fase AB. Ambang minimum {MIN_SIGNALS_TO_CONCLUDE} sinyal tetap berlaku.",
        "",
    ]
    for r in results:
        lines.append(f"### {r['ticker']}")
        lines.append(
            f"Sinyal dengan data 1 jam: {r['signals_with_hourly_coverage']} "
            f"(dari {r['signals_total_daily_history']} sinyal di histori harian penuh) "
            f"| discovery {r['discovery_signals']}, holdout {r['holdout_signals']}"
        )
        lines.append(f"Tanggal sinyal: {', '.join(r['signal_dates']) or '(tidak ada)'}")
        if r["signals_with_hourly_coverage"] < MIN_SIGNALS_TO_CONCLUDE:
            lines.append(
                f"  -> !!! DI BAWAH AMBANG MINIMUM ({MIN_SIGNALS_TO_CONCLUDE}). Hasil di bawah TIDAK BOLEH "
                "dijadikan dasar keputusan trading -- indikatif saja."
            )
        lines.append("")
        lines.append(f"{'varian':<18}{'discovery':>24}{'holdout':>24}{'hari':>8}{'tdk kena':>10}")
        for variant, m in r["variants"].items():
            d, o, f = m["discovery"], m["holdout"], m["full_sample"]
            d_txt = f"{d.get('mean_net_return', float('nan')):+.2%} (w{d.get('win_rate', float('nan')):.0%}, n={d.get('n', 0)})"
            o_txt = f"{o.get('mean_net_return', float('nan')):+.2%} (w{o.get('win_rate', float('nan')):.0%}, n={o.get('n', 0)})"
            lines.append(
                f"{variant:<18}{d_txt:>24}{o_txt:>24}"
                f"{f.get('mean_hold_days', float('nan')):>8.1f}{f.get('never_fired', 0):>10}"
            )
        lines.append("")

        base = r["variants"]["daily_fixed_10d"]
        lines.append("Selisih vs baseline daily_fixed_10d (positif = exit Stoch RSI 1 jam lebih baik):")
        for variant, m in r["variants"].items():
            if variant == "daily_fixed_10d":
                continue
            dd = m["discovery"].get("mean_net_return", float("nan")) - base["discovery"].get("mean_net_return", float("nan"))
            do = m["holdout"].get("mean_net_return", float("nan")) - base["holdout"].get("mean_net_return", float("nan"))
            verdict = "LEBIH BAIK di dua-duanya" if dd > 0 and do > 0 else "tidak konsisten / lebih buruk"
            lines.append(f"  {variant:<18} discovery {dd:+.2%} | holdout {do:+.2%}  -> {verdict}")
        lines.append("")

    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
