#!/usr/bin/env python3
from pathlib import Path

import pandas as pd
import yfinance as yf

PICKS_FILE = Path("research/strategy-notes/ptb-open-scalp-picks.csv")
OUT_FILE = Path("output/ptb_v4_filtered_backtest.md")
START = "2026-07-20"
END = "2026-09-02"
ROUND_TRIP_COST = 0.003
TRAILING_STOP = 0.01
MIN_SAMPLE = 3
MIN_WIN_RATE = 0.70
MAX_BAD_RATE = 0.35
MAX_PICKS_PER_DAY = 5


def fetch_5m(ticker: str) -> pd.DataFrame:
    df = yf.download(f"{ticker}.JK", start=START, end=END, interval="5m", progress=False, auto_adjust=False, threads=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    df = df.reset_index()
    df["dt_jkt"] = pd.to_datetime(df[df.columns[0]], utc=True).dt.tz_convert("Asia/Jakarta")
    df["date"] = df["dt_jkt"].dt.normalize().dt.tz_localize(None)
    return df[["date", "dt_jkt", "Open", "High", "Low", "Close"]].dropna()


def simulate_day(day: pd.DataFrame):
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
        stop = peak * (1 - TRAILING_STOP)
        if float(row["Low"]) <= stop:
            exit_price = stop
            break
    return exit_price / entry - 1 - ROUND_TRIP_COST


def score_history(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=["ticker", "win", "loss", "draw", "total", "win_rate", "bad_rate"])
    stats = history.pivot_table(index="ticker", columns="label", aggfunc="size", fill_value=0)
    for col in ["win", "loss", "draw"]:
        if col not in stats:
            stats[col] = 0
    stats = stats[["win", "loss", "draw"]]
    stats["total"] = stats.sum(axis=1)
    stats["win_rate"] = stats["win"] / (stats["win"] + stats["loss"]).replace(0, pd.NA)
    stats["bad_rate"] = (stats["loss"] + stats["draw"]) / stats["total"]
    return stats.reset_index()


def main() -> None:
    picks = pd.read_csv(PICKS_FILE, parse_dates=["date"]).sort_values("date")
    price_by_ticker = {}
    for ticker in sorted(picks.ticker.unique()):
        df = fetch_5m(ticker)
        if not df.empty:
            price_by_ticker[ticker] = {date: day for date, day in df.groupby("date")}

    selected_rows = []
    skipped_days = []
    for pick_date, day_picks in picks.groupby("date"):
        history = picks[picks.date < pick_date]
        scores = score_history(history)
        candidates = day_picks.merge(scores, on="ticker", how="left")
        candidates = candidates[
            (candidates.total >= MIN_SAMPLE)
            & (candidates.win_rate >= MIN_WIN_RATE)
            & (candidates.bad_rate <= MAX_BAD_RATE)
        ].sort_values(["win_rate", "total", "bad_rate"], ascending=[False, False, True]).head(MAX_PICKS_PER_DAY)
        if candidates.empty:
            skipped_days.append(pick_date.date())
            continue
        for _, pick in candidates.iterrows():
            day = price_by_ticker.get(pick.ticker, {}).get(pick.date)
            if day is None:
                continue
            ret = simulate_day(day)
            if ret is None:
                continue
            selected_rows.append({
                "date": pick.date,
                "ticker": pick.ticker,
                "label": pick.label,
                "win_rate": pick.win_rate,
                "bad_rate": pick.bad_rate,
                "hist_total": pick.total,
                "ret": ret,
            })

    selected = pd.DataFrame(selected_rows)
    by_day = selected.groupby("date").ret.mean().sort_index() if not selected.empty else pd.Series(dtype=float)
    labels = selected.label.value_counts().to_dict() if not selected.empty else {}
    lines = [
        "# PTB V4 Filtered Backtest",
        "",
        f"Periode: `{START}` sampai `2026-09-01`.",
        f"Filter: historical `win_rate >= {MIN_WIN_RATE:.0%}`, `bad_rate <= {MAX_BAD_RATE:.0%}`, sample minimal `{MIN_SAMPLE}`, max `{MAX_PICKS_PER_DAY}` ticker per hari.",
        f"Entry: first 5m open. Exit: trailing stop `{TRAILING_STOP:.0%}` intraday, atau close terakhir hari itu.",
        f"Biaya asumsi: `{ROUND_TRIP_COST * 100:.1f}%` round-trip.",
        "",
        "## Hasil",
        "",
        f"- Raw trade terpilih: `{len(selected)}`",
        f"- Hari aktif: `{len(by_day)}`",
        f"- Hari tanpa kandidat karena belum cukup histori/filter: `{len(skipped_days)}`",
        f"- Label win/loss/draw terpilih: `{labels.get('win', 0)}/{labels.get('loss', 0)}/{labels.get('draw', 0)}`",
        f"- Total return harian: `{by_day.sum() * 100:+.2f}%`",
        f"- Avg return harian: `{by_day.mean() * 100:+.2f}%`",
        f"- Median return harian: `{by_day.median() * 100:+.2f}%`",
        f"- Win rate harian: `{(by_day > 0).mean() * 100:.1f}%`",
        f"- Avg trade: `{selected.ret.mean() * 100:+.2f}%`",
        f"- Win rate trade: `{(selected.ret > 0).mean() * 100:.1f}%`",
        "",
        "## Ticker Terpilih",
        "",
    ]
    if not selected.empty:
        by_ticker = selected.groupby("ticker").agg(trade=("ret", "size"), avg_ret=("ret", lambda s: s.mean() * 100), win_rate=("ret", lambda s: (s > 0).mean() * 100)).sort_values(["trade", "avg_ret"], ascending=False)
        lines += ["```text", by_ticker.round(2).to_string(), "```", ""]
    lines += [
        "## Interpretasi",
        "",
        "- Filter ini mengurangi trade dari PTB V3, tapi juga telat aktif karena butuh histori label dulu.",
        "- Ini bukan oracle: filter hanya boleh memakai label sebelum tanggal trade, supaya tidak bocor masa depan.",
        "- Kalau hasil kalah dari V3, berarti filter histori pendek membuang terlalu banyak peluang bagus.",
        "",
    ]
    OUT_FILE.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
