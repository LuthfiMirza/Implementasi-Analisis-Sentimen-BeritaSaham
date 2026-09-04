#!/usr/bin/env python3
from pathlib import Path
import json
import itertools

import pandas as pd
import yfinance as yf

PRICE_FILE = Path("quant/drawdown_bounce_tracker/ptb_backtest_prices_5y.json")
OUT_FILE = Path("output/self_radar_v1_backtest.md")
START = pd.Timestamp("2026-07-20")
END = pd.Timestamp("2026-09-01")
YF_END = "2026-09-02"
ROUND_TRIP_COST = 0.003
TRAILING_STOP = 0.01
MAX_PER_DAY = 5


def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    return 100 - (100 / (1 + gain / loss.replace(0, pd.NA)))


def daily_features(ticker, rows):
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna().sort_values("date")
    df["ticker"] = ticker
    df["ret_1d"] = df.close.pct_change()
    df["ret_2d"] = df.close.pct_change(2)
    df["ret_5d"] = df.close.pct_change(5)
    df["ret_10d"] = df.close.pct_change(10)
    df["rsi14"] = rsi(df.close)
    df["ma20"] = df.close.rolling(20).mean()
    df["above_ma20"] = df.close > df.ma20
    df["drawdown_20d"] = df.close / df.close.rolling(20).max() - 1
    df["volatility_10d"] = df.ret_1d.rolling(10).std()
    return df


def fetch_5m(ticker):
    df = yf.download(f"{ticker}.JK", start=str(START.date()), end=YF_END, interval="5m", progress=False, auto_adjust=False, threads=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    df = df.reset_index()
    df["dt_jkt"] = pd.to_datetime(df[df.columns[0]], utc=True).dt.tz_convert("Asia/Jakarta")
    df["date"] = df.dt_jkt.dt.normalize().dt.tz_localize(None)
    return df[["date", "dt_jkt", "Open", "High", "Low", "Close"]].dropna().sort_values("dt_jkt")


def outcome_for_day(prev_close, day):
    if day.empty or prev_close <= 0:
        return None
    day = day.reset_index(drop=True)
    peak = prev_close
    trail_idx = None
    for idx, row in day.iterrows():
        peak = max(peak, float(row.High))
        dt = row.dt_jkt
        if (dt.hour, dt.minute) >= (9, 30):
            trail_idx = idx
            break
    if trail_idx is None:
        return None
    exit_price = float(day.iloc[-1].Close)
    for _, row in day.iloc[trail_idx:].iterrows():
        peak = max(peak, float(row.High))
        stop = peak * (1 - TRAILING_STOP)
        if float(row.Low) <= stop:
            exit_price = stop
            break
    return exit_price / prev_close - 1 - ROUND_TRIP_COST


def build_dataset():
    prices = json.loads(PRICE_FILE.read_text())
    tickers = sorted(prices)
    daily = pd.concat([daily_features(t, prices[t]) for t in tickers if prices[t]], ignore_index=True)
    rows = []
    for ticker in tickers:
        intra = fetch_5m(ticker)
        if intra.empty:
            continue
        by_day = {date: day for date, day in intra.groupby("date")}
        d = daily[daily.ticker == ticker].reset_index(drop=True)
        for idx in range(1, len(d) - 1):
            feature_day = d.iloc[idx]
            trade_day = d.iloc[idx + 1].date
            if not (START <= trade_day <= END):
                continue
            day = by_day.get(trade_day)
            if day is None:
                continue
            ret = outcome_for_day(float(feature_day.close), day)
            if ret is None:
                continue
            row = feature_day.to_dict()
            row["trade_date"] = trade_day
            row["target_ret"] = ret
            rows.append(row)
    return pd.DataFrame(rows)


def apply_rule(df, rule):
    out = df.copy()
    if rule["rsi_min"] is not None:
        out = out[out.rsi14 >= rule["rsi_min"]]
    if rule["ret1_min"] is not None:
        out = out[out.ret_1d >= rule["ret1_min"]]
    if rule["ret5_min"] is not None:
        out = out[out.ret_5d >= rule["ret5_min"]]
    if rule["ret5_max"] is not None:
        out = out[out.ret_5d <= rule["ret5_max"]]
    if rule["above_ma20"]:
        out = out[out.above_ma20]
    if rule["dd_min"] is not None:
        out = out[out.drawdown_20d >= rule["dd_min"]]
    out = out.sort_values(["trade_date", "ret_5d", "rsi14"], ascending=[True, False, False])
    return out.groupby("trade_date").head(MAX_PER_DAY)


def stats(sel):
    by_day = sel.groupby("trade_date").target_ret.mean().sort_index()
    return {
        "trades": len(sel), "days": len(by_day), "total": by_day.sum() * 100,
        "avg_day": by_day.mean() * 100, "avg_trade": sel.target_ret.mean() * 100,
        "win_day": (by_day > 0).mean() * 100, "win_trade": (sel.target_ret > 0).mean() * 100,
    }


def main():
    df = build_dataset().dropna(subset=["rsi14", "ret_1d", "ret_5d", "drawdown_20d", "volatility_10d"])
    rules = []
    for rsi_min, ret1_min, ret5_min, ret5_max, above_ma20, dd_min in itertools.product(
        [None, 50, 55, 60], [None, 0, 0.01], [None, 0, 0.03, 0.05], [None, 0.20, 0.35], [False, True], [None, -0.15, -0.05]
    ):
        rule = {"rsi_min": rsi_min, "ret1_min": ret1_min, "ret5_min": ret5_min, "ret5_max": ret5_max, "above_ma20": above_ma20, "dd_min": dd_min}
        sel = apply_rule(df, rule)
        if len(sel) < 40 or sel.trade_date.nunique() < 15:
            continue
        s = stats(sel)
        s["rule"] = rule
        rules.append(s)
    ranked = sorted(rules, key=lambda x: (x["avg_day"], x["win_day"], x["days"]), reverse=True)[:10]
    best = ranked[0]
    best_sel = apply_rule(df, best["rule"])
    by_ticker = best_sel.groupby("ticker").agg(trades=("target_ret", "size"), avg_ret=("target_ret", lambda s: s.mean() * 100), win_rate=("target_ret", lambda s: (s > 0).mean() * 100)).sort_values(["avg_ret", "trades"], ascending=False).head(30)
    top_trades = best_sel.sort_values("target_ret", ascending=False).head(30)[["trade_date", "ticker", "close", "rsi14", "ret_1d", "ret_5d", "drawdown_20d", "target_ret"]]
    lines = ["# Self Radar V1 Backtest", "", "Sinyal tidak pakai PTB radar. Universe dari `ptb_backtest_prices_5y.json`, fitur D-1, entry close D-1, exit trailing stop 1% mulai 09:30 hari H.", "", f"Dataset: `{len(df)}` ticker-day outcome dari `{df.ticker.nunique()}` ticker.", "", "## Rule Terbaik", "", f"```text\n{best['rule']}\n```", "", "## Hasil Rule Terbaik", "", f"- Trade: `{best['trades']}`", f"- Hari aktif: `{best['days']}`", f"- Total return harian: `{best['total']:+.2f}%`", f"- Avg return harian: `{best['avg_day']:+.2f}%`", f"- Avg trade: `{best['avg_trade']:+.2f}%`", f"- Win rate harian: `{best['win_day']:.1f}%`", f"- Win rate trade: `{best['win_trade']:.1f}%`", "", "## Top 10 Rule Kandidat", "", "```text"]
    for i, r in enumerate(ranked, 1):
        lines.append(f"{i}. avg_day={r['avg_day']:+.2f}% avg_trade={r['avg_trade']:+.2f}% days={r['days']} trades={r['trades']} win_day={r['win_day']:.1f}% rule={r['rule']}")
    lines += ["```", "", "## Ticker Yang Sering Menang Di Rule Terbaik", "", "```text", by_ticker.round(2).to_string(), "```", "", "## Top Trade Rule Terbaik", "", "```text", top_trades.assign(ret_1d=lambda x:x.ret_1d*100, ret_5d=lambda x:x.ret_5d*100, drawdown_20d=lambda x:x.drawdown_20d*100, target_ret=lambda x:x.target_ret*100).round(2).to_string(index=False), "```", "", "## Interpretasi", "", "- Pola terbaik dari grid ini mencari saham yang sudah momentum, bukan oversold.", "- Rule masih discovery di periode sama; perlu walk-forward sebelum dipakai live.", "- Data paling kurang: volume intraday, orderbook pre-open, dan universe semua saham IDX harian.", ""]
    OUT_FILE.write_text("\n".join(lines))
    print("\n".join(lines[:45]))
    print("report", OUT_FILE)

if __name__ == "__main__":
    main()
