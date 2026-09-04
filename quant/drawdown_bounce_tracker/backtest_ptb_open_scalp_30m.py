#!/usr/bin/env python3
from pathlib import Path

import pandas as pd
import yfinance as yf

PICKS_FILE = Path("research/strategy-notes/ptb-open-scalp-picks.csv")
OUT_FILE = Path("output/ptb_open_scalp_30m_backtest.md")
START = "2026-07-20"
END = "2026-09-02"
CAPITAL = 10_000_000
ROUND_TRIP_COST = 0.003


def fetch_first_30m(ticker: str) -> pd.DataFrame:
    df = yf.download(
        f"{ticker}.JK",
        start=START,
        end=END,
        interval="30m",
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
    first = df.sort_values("dt_jkt").groupby("date").first().reset_index()
    first["ticker"] = ticker
    first["ret_30m"] = first["Close"] / first["Open"] - 1 - ROUND_TRIP_COST
    return first[["date", "ticker", "Open", "Close", "ret_30m"]]


def main() -> None:
    picks = pd.read_csv(PICKS_FILE, parse_dates=["date"])
    intraday = pd.concat([fetch_first_30m(ticker) for ticker in sorted(picks.ticker.unique())], ignore_index=True)
    merged = picks.merge(intraday, on=["date", "ticker"], how="left")
    valid = merged.dropna(subset=["ret_30m"])
    by_day = valid.groupby("date").ret_30m.mean().sort_index()
    capital = CAPITAL
    for ret in by_day:
        capital *= 1 + ret
    labels = picks.label.value_counts().to_dict()
    text = f"""# PTB Open Scalp 30m Backtest

Periode: `{START}` sampai `2026-09-01`.
Modal awal: `Rp{CAPITAL:,.0f}`.
Entry: first 30m bar open Yahoo.
Exit: first 30m bar close Yahoo.
Biaya asumsi: `{ROUND_TRIP_COST * 100:.1f}%` round-trip.

## Label Dari Chat

- Total picks manual: `{len(picks)}`
- Win: `{labels.get('win', 0)}`
- Loss: `{labels.get('loss', 0)}`
- Draw: `{labels.get('draw', 0)}`

## Backtest Harga 30m

- Picks punya data intraday: `{len(valid)}`
- Hari trading valid: `{len(by_day)}`
- Rata-rata return harian basket: `{by_day.mean() * 100:+.2f}%`
- Total compound return: `{(capital / CAPITAL - 1) * 100:+.2f}%`
- Modal akhir: `Rp{capital:,.0f}`

## Catatan

Ini proxy `open -> close bar 30m pertama`, bukan harga jual tepat jam `09:30` dari broker.
"""
    OUT_FILE.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
