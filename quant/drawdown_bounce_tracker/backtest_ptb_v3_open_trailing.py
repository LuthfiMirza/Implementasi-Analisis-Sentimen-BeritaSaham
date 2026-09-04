#!/usr/bin/env python3
from pathlib import Path

import pandas as pd
import yfinance as yf

PICKS_FILE = Path("research/strategy-notes/ptb-open-scalp-picks.csv")
OUT_FILE = Path("output/ptb_v3_open_trailing_backtest.md")
START = "2026-07-20"
END = "2026-09-02"
ROUND_TRIP_COST = 0.003


def fetch_5m(ticker: str) -> pd.DataFrame:
    df = yf.download(
        f"{ticker}.JK",
        start=START,
        end=END,
        interval="5m",
        progress=False,
        auto_adjust=False,
        threads=False,
    )
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    df = df.reset_index()
    df["dt_jkt"] = pd.to_datetime(df[df.columns[0]], utc=True).dt.tz_convert("Asia/Jakarta")
    df["date"] = df["dt_jkt"].dt.normalize().dt.tz_localize(None)
    return df[["date", "dt_jkt", "Open", "High", "Low", "Close"]].dropna()


def simulate_day(day: pd.DataFrame, stop_pct: float):
    day = day.sort_values("dt_jkt")
    if day.empty:
        return None
    entry = float(day.iloc[0]["Open"])
    if entry <= 0:
        return None
    peak = entry
    exit_price = float(day.iloc[-1]["Close"])
    for _, row in day.iterrows():
        peak = max(peak, float(row["High"]))
        stop = peak * (1 - stop_pct)
        if float(row["Low"]) <= stop:
            exit_price = stop
            break
    return exit_price / entry - 1 - ROUND_TRIP_COST


def main() -> None:
    picks = pd.read_csv(PICKS_FILE, parse_dates=["date"])
    all_results = []
    for ticker in sorted(picks.ticker.unique()):
        df = fetch_5m(ticker)
        if df.empty:
            continue
        by_date = {date: day for date, day in df.groupby("date")}
        ticker_picks = picks[picks.ticker == ticker]
        for _, pick in ticker_picks.iterrows():
            day = by_date.get(pick.date)
            if day is None:
                continue
            for stop_pct in (0.01, 0.02):
                ret = simulate_day(day, stop_pct)
                if ret is not None:
                    all_results.append({"date": pick.date, "ticker": ticker, "stop_pct": stop_pct, "ret": ret})
    results = pd.DataFrame(all_results)
    rows = []
    for stop_pct, group in results.groupby("stop_pct"):
        by_day = group.groupby("date").ret.mean().sort_index()
        rows.append({
            "stop": f"{stop_pct * 100:.0f}%",
            "raw_trade": len(group),
            "days": len(by_day),
            "total_day": by_day.sum() * 100,
            "avg_day": by_day.mean() * 100,
            "median_day": by_day.median() * 100,
            "win_day": (by_day > 0).mean() * 100,
            "avg_trade": group.ret.mean() * 100,
            "win_trade": (group.ret > 0).mean() * 100,
        })
    table = pd.DataFrame(rows).sort_values("total_day", ascending=False)
    lines = [
        "# PTB V3 Open Trailing Backtest",
        "",
        f"Periode: `{START}` sampai `2026-09-01`.",
        "Entry: first 5m open pada hari picks PTB.",
        "Exit: trailing stop intraday, atau close terakhir hari itu jika stop tidak kena.",
        f"Biaya asumsi: `{ROUND_TRIP_COST * 100:.1f}%` round-trip.",
        "",
        "| Rank | Trailing Stop | Raw Trade | Hari | Total Return Harian | Avg Harian | Median Harian | Win Rate Harian | Avg Trade | Win Rate Trade |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(table.to_dict("records"), start=1):
        lines.append(f"| {rank} | {row['stop']} | {row['raw_trade']} | {row['days']} | {row['total_day']:+.2f}% | {row['avg_day']:+.2f}% | {row['median_day']:+.2f}% | {row['win_day']:.1f}% | {row['avg_trade']:+.2f}% | {row['win_trade']:.1f}% |")
    winner = table.iloc[0]["stop"] if not table.empty else "-"
    lines += ["", f"Kesimpulan: trailing stop `{winner}` paling untung pada total return harian.", "", "Catatan: simulasi pakai OHLC 5m Yahoo, jadi urutan high/low dalam satu candle tidak diketahui persis.", ""]
    OUT_FILE.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
