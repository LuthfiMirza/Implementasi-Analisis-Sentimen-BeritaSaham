#!/usr/bin/env python3
from pathlib import Path

import pandas as pd
import yfinance as yf

PICKS_FILE = Path("research/strategy-notes/ptb-open-scalp-picks.csv")
OUT_FILE = Path("output/ptb_v6_trailing_start_compare.md")
DETAIL_FILE = Path("output/ptb_v6_trailing_start_trades.csv")
START = "2026-07-20"
END = "2026-09-02"
ROUND_TRIP_COST = 0.003
TRAILING_STOP = 0.01
TRAIL_START_HOUR = 9
TRAIL_START_MINUTE = 30


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


def clock(row) -> tuple[int, int]:
    dt = row["dt_jkt"]
    return dt.hour, dt.minute


def simulate_open(day: pd.DataFrame, ticker: str, trade_date, start_mode: str):
    if day.empty:
        return None
    day = day.reset_index(drop=True)
    entry_idx = 0
    entry_time = day.iloc[entry_idx]["dt_jkt"]
    entry_price = float(day.iloc[entry_idx]["Open"])
    open_time = entry_time
    open_price = entry_price
    return simulate_after_entry(day, ticker, trade_date, "buy_open_H", start_mode, entry_idx, entry_time, entry_price, open_time, open_price)


def simulate_prev_close(prev_day: pd.DataFrame, day: pd.DataFrame, ticker: str, trade_date, start_mode: str):
    if prev_day.empty or day.empty:
        return None
    prev_day = prev_day.reset_index(drop=True)
    day = day.reset_index(drop=True)
    entry_time = prev_day.iloc[-1]["dt_jkt"]
    entry_price = float(prev_day.iloc[-1]["Close"])
    open_time = day.iloc[0]["dt_jkt"]
    open_price = float(day.iloc[0]["Open"])
    return simulate_after_entry(day, ticker, trade_date, "buy_close_H_minus_1", start_mode, 0, entry_time, entry_price, open_time, open_price)


def simulate_after_entry(day: pd.DataFrame, ticker: str, trade_date, entry_mode: str, start_mode: str, entry_idx: int, entry_time, entry_price: float, open_time, open_price: float):
    if entry_price <= 0:
        return None
    if start_mode == "trail_from_entry":
        trail_idx = entry_idx
        peak = entry_price
    elif start_mode == "trail_from_0930":
        trail_idx = None
        peak = entry_price
        for idx, row in day.iterrows():
            peak = max(peak, float(row["High"]))
            hour, minute = clock(row)
            if (hour, minute) >= (TRAIL_START_HOUR, TRAIL_START_MINUTE):
                trail_idx = idx
                break
        if trail_idx is None:
            trail_idx = len(day) - 1
    else:
        raise ValueError(start_mode)

    trail_start_time = day.iloc[trail_idx]["dt_jkt"]
    exit_price = float(day.iloc[-1]["Close"])
    exit_time = day.iloc[-1]["dt_jkt"]
    exit_reason = "day_close"
    for _, row in day.iloc[trail_idx:].iterrows():
        peak = max(peak, float(row["High"]))
        stop = peak * (1 - TRAILING_STOP)
        if float(row["Low"]) <= stop:
            exit_price = stop
            exit_time = row["dt_jkt"]
            exit_reason = "trailing_stop"
            break
    return {
        "date": trade_date.date() if hasattr(trade_date, "date") else trade_date,
        "ticker": ticker,
        "scenario": f"{entry_mode}__{start_mode}",
        "entry_mode": entry_mode,
        "start_mode": start_mode,
        "open_time": str(open_time),
        "open_price": open_price,
        "entry_time": str(entry_time),
        "entry_price": entry_price,
        "trail_start_time": str(trail_start_time),
        "peak_price": peak,
        "exit_time": str(exit_time),
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "return_pct": (exit_price / entry_price - 1 - ROUND_TRIP_COST) * 100,
    }


def stats(rows: pd.DataFrame) -> dict:
    by_day = rows.groupby("date").return_pct.mean().sort_index()
    return {
        "raw_trade": len(rows),
        "days": len(by_day),
        "total_day": by_day.sum(),
        "avg_day": by_day.mean(),
        "median_day": by_day.median(),
        "win_day": (by_day > 0).mean() * 100,
        "avg_trade": rows.return_pct.mean(),
        "median_trade": rows.return_pct.median(),
        "win_trade": (rows.return_pct > 0).mean() * 100,
    }


def main() -> None:
    picks = pd.read_csv(PICKS_FILE, parse_dates=["date"]).sort_values("date")
    price = {}
    for ticker in sorted(picks.ticker.unique()):
        df = fetch_5m(ticker)
        if not df.empty:
            price[ticker] = {date: day.reset_index(drop=True) for date, day in df.groupby("date")}

    trades = []
    for _, pick in picks.iterrows():
        ticker = pick.ticker
        dates = sorted(price.get(ticker, {}))
        day = price.get(ticker, {}).get(pick.date)
        prev_dates = [date for date in dates if date < pick.date]
        prev_day = price.get(ticker, {}).get(prev_dates[-1]) if prev_dates else None
        if day is None:
            continue
        for start_mode in ["trail_from_entry", "trail_from_0930"]:
            trade = simulate_open(day, ticker, pick.date, start_mode)
            if trade:
                trades.append(trade)
            if prev_day is not None:
                trade = simulate_prev_close(prev_day, day, ticker, pick.date, start_mode)
                if trade:
                    trades.append(trade)

    result = pd.DataFrame(trades)
    result.to_csv(DETAIL_FILE, index=False)
    lines = [
        "# PTB V6 Trailing Start Compare",
        "",
        f"Periode: `{START}` sampai `2026-09-01`.",
        f"Ticker dipilih: semua ticker picks PTB manual yang punya data Yahoo 5m (`{result.ticker.nunique()}` ticker).",
        f"Trailing stop: `{TRAILING_STOP:.0%}`. Fee: `{ROUND_TRIP_COST * 100:.1f}%`.",
        "",
        "## Summary 4 Skenario",
        "",
        "| Rank | Skenario | Raw Trade | Hari | Total Return Harian | Avg Harian | Median Harian | Win Rate Harian | Avg Trade | Median Trade | Win Rate Trade |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    summary_rows = []
    for scenario, rows in result.groupby("scenario"):
        row = stats(rows)
        row["scenario"] = scenario
        summary_rows.append(row)
    summary_rows = sorted(summary_rows, key=lambda row: row["total_day"], reverse=True)
    for rank, row in enumerate(summary_rows, start=1):
        lines.append(f"| {rank} | {row['scenario']} | {row['raw_trade']} | {row['days']} | {row['total_day']:+.2f}% | {row['avg_day']:+.2f}% | {row['median_day']:+.2f}% | {row['win_day']:.1f}% | {row['avg_trade']:+.2f}% | {row['median_trade']:+.2f}% | {row['win_trade']:.1f}% |")

    top = result.sort_values("return_pct", ascending=False).head(20)
    lines += ["", "## Top 20 Trade", "", "```text", top[["date", "ticker", "scenario", "open_time", "open_price", "entry_time", "entry_price", "trail_start_time", "exit_time", "exit_price", "exit_reason", "return_pct"]].round(2).to_string(index=False), "```", "", "## Ticker Yang Dipakai", "", "```text", ", ".join(sorted(result.ticker.unique())), "```", "", f"Detail trade CSV: `{DETAIL_FILE}`", ""]
    OUT_FILE.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
