#!/usr/bin/env python3
from pathlib import Path

import pandas as pd
import yfinance as yf

PICKS_FILE = Path("research/strategy-notes/ptb-open-scalp-picks.csv")
OUT_FILE = Path("output/ptb_v5_pick_timing_groups.md")
START = "2026-07-20"
END = "2026-09-02"
ROUND_TRIP_COST = 0.003
TRAILING_STOP = 0.01
MIN_TRADES = 3
TOP_N = 20


def fetch_5m(ticker: str) -> pd.DataFrame:
    df = yf.download(f"{ticker}.JK", start=START, end=END, interval="5m", progress=False, auto_adjust=False, threads=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    df = df.reset_index()
    df["dt_jkt"] = pd.to_datetime(df[df.columns[0]], utc=True).dt.tz_convert("Asia/Jakarta")
    df["date"] = df["dt_jkt"].dt.normalize().dt.tz_localize(None)
    return df[["date", "dt_jkt", "Open", "High", "Low", "Close"]].dropna().sort_values("dt_jkt")


def trailing_exit(day: pd.DataFrame, entry_idx: int, entry_price: float):
    peak = entry_price
    exit_price = float(day.iloc[-1]["Close"])
    for _, row in day.iloc[entry_idx:].iterrows():
        peak = max(peak, float(row["High"]))
        stop = peak * (1 - TRAILING_STOP)
        if float(row["Low"]) <= stop:
            exit_price = stop
            break
    return exit_price / entry_price - 1 - ROUND_TRIP_COST


def simulate_open(day: pd.DataFrame):
    if day.empty:
        return None
    entry = float(day.iloc[0]["Open"])
    if entry <= 0:
        return None
    return trailing_exit(day, 0, entry)


def simulate_prev_close(prev_day: pd.DataFrame, day: pd.DataFrame):
    if prev_day.empty or day.empty:
        return None
    entry = float(prev_day.iloc[-1]["Close"])
    if entry <= 0:
        return None
    # ponytail: overnight risk approximated with first next-day 5m onward; add pre-open/orderbook when available.
    return trailing_exit(day, 0, entry)


def summarize(rows: pd.DataFrame) -> pd.DataFrame:
    return rows.groupby("ticker").agg(
        trades=("ret", "size"),
        total_ret=("ret", lambda s: s.sum() * 100),
        avg_ret=("ret", lambda s: s.mean() * 100),
        median_ret=("ret", lambda s: s.median() * 100),
        win_rate=("ret", lambda s: (s > 0).mean() * 100),
    ).query("trades >= @MIN_TRADES").sort_values(["avg_ret", "win_rate"], ascending=False)


def basket_stats(rows: pd.DataFrame) -> dict:
    by_day = rows.groupby("date").ret.mean().sort_index()
    return {
        "raw": len(rows),
        "days": len(by_day),
        "total_day": by_day.sum() * 100,
        "avg_day": by_day.mean() * 100,
        "avg_trade": rows.ret.mean() * 100,
        "win_day": (by_day > 0).mean() * 100,
        "win_trade": (rows.ret > 0).mean() * 100,
    }


def main() -> None:
    picks = pd.read_csv(PICKS_FILE, parse_dates=["date"]).sort_values("date")
    price = {}
    for ticker in sorted(picks.ticker.unique()):
        df = fetch_5m(ticker)
        if not df.empty:
            price[ticker] = {date: day.reset_index(drop=True) for date, day in df.groupby("date")}

    out = []
    for _, pick in picks.iterrows():
        dates = sorted(price.get(pick.ticker, {}))
        day = price.get(pick.ticker, {}).get(pick.date)
        prev_dates = [d for d in dates if d < pick.date]
        prev_day = price.get(pick.ticker, {}).get(prev_dates[-1]) if prev_dates else None
        ret_open = simulate_open(day) if day is not None else None
        ret_prev = simulate_prev_close(prev_day, day) if prev_day is not None and day is not None else None
        if ret_open is not None:
            out.append({"date": pick.date, "ticker": pick.ticker, "timing": "buy_open_H", "label": pick.label, "ret": ret_open})
        if ret_prev is not None:
            out.append({"date": pick.date, "ticker": pick.ticker, "timing": "buy_close_H_minus_1", "label": pick.label, "ret": ret_prev})

    results = pd.DataFrame(out)
    open_rows = results[results.timing == "buy_open_H"]
    prev_rows = results[results.timing == "buy_close_H_minus_1"]
    open_top = summarize(open_rows).head(TOP_N)
    prev_top = summarize(prev_rows).head(TOP_N)
    open_symbols = set(open_top.head(10).index)
    prev_symbols = set(prev_top.head(10).index)
    filtered = pd.concat([
        open_rows[open_rows.ticker.isin(open_symbols)].assign(group="top10_open_H"),
        prev_rows[prev_rows.ticker.isin(prev_symbols)].assign(group="top10_close_H_minus_1"),
    ])
    lines = [
        "# PTB V5 Pick Timing Groups",
        "",
        f"Periode: `{START}` sampai `2026-09-01`.",
        f"Exit: trailing stop `{TRAILING_STOP:.0%}`. Fee: `{ROUND_TRIP_COST * 100:.1f}%`.",
        "Timing dibandingkan: beli `open hari H` vs beli `close H-1` lalu jual trailing hari H.",
        "",
        "## Basket Semua Picks",
        "",
        "| Timing | Raw Trade | Hari | Total Return Harian | Avg Harian | Avg Trade | Win Rate Harian | Win Rate Trade |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, rows in [("buy_open_H", open_rows), ("buy_close_H_minus_1", prev_rows)]:
        stats = basket_stats(rows)
        lines.append(f"| {name} | {stats['raw']} | {stats['days']} | {stats['total_day']:+.2f}% | {stats['avg_day']:+.2f}% | {stats['avg_trade']:+.2f}% | {stats['win_day']:.1f}% | {stats['win_trade']:.1f}% |")
    lines += ["", "## Top Ticker Buy Open H", "", "```text", open_top.round(2).to_string(), "```", "", "## Top Ticker Buy Close H-1", "", "```text", prev_top.round(2).to_string(), "```", "", "## Basket Top 10 Ticker Per Timing", "", "| Group | Raw Trade | Hari | Total Return Harian | Avg Harian | Avg Trade | Win Rate Harian | Win Rate Trade |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for group, rows in filtered.groupby("group"):
        stats = basket_stats(rows)
        lines.append(f"| {group} | {stats['raw']} | {stats['days']} | {stats['total_day']:+.2f}% | {stats['avg_day']:+.2f}% | {stats['avg_trade']:+.2f}% | {stats['win_day']:.1f}% | {stats['win_trade']:.1f}% |")
    lines += ["", "## Interpretasi", "", "- Ini mencari pola profit aktual dari picks PTB, bukan memakai label win/loss saja.", "- Top ticker bisa overfit karena periode pendek; validasi perlu data minggu berikutnya.", "- Kalau `buy_close_H_minus_1` menang, sinyal cocok overnight. Kalau `buy_open_H` menang, sinyal cocok scalp pagi.", ""]
    OUT_FILE.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
