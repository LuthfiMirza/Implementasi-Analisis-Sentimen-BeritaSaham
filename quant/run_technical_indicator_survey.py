#!/usr/bin/env python3
"""Systematic survey of classical technical indicators on BUMI/DEWA: which one actually predicts?

The user's question is "try every indicator and find which predicts best". Scanning many
indicators is fine -- what invalidates the usual version of this exercise is picking the
best-performing one afterwards and believing it. With ~27 signals x 4 horizons x 2 tickers,
several will look excellent on any dataset purely by chance.

So this does the scan AND measures whether the scan's answer is trustworthy:

  1. Chronological split (no shuffling): the first 70% of history is the DISCOVERY set, the last
     30% is a HOLDOUT never used to choose anything.
  2. Every signal's edge is measured on both, independently.
  3. The headline diagnostic is the Spearman rank correlation between discovery-set edge and
     holdout edge across signals. If "looked best historically" carried real information about
     future performance, that correlation would be strongly positive. If it is near zero, then
     ranking indicators by backtest performance tells you nothing about what happens next -- which
     invalidates the whole "find the best indicator" premise, no matter how good the top row looks.
  4. Edges are reported net of a 0.80% round-trip cost, the MID assumption already used by this
     project's BUMI/DEWA trading research (output/trading_research/reports/).
  5. Every signal is reported, winners and losers. No cherry-picking.

Entry timing is deliberately conservative: a signal observed at the close of day t is entered at
the close of day t+1 (you cannot trade on the bar you are still forming), and held h days from
there. Indicators are implemented inline rather than via TA-Lib so every formula is auditable.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

TICKERS = ["BUMI", "DEWA"]
HORIZONS = [1, 3, 5, 10]
ROUND_TRIP_COST = 0.008  # 0.80% MID, matches this project's existing net-of-cost verdicts
DISCOVERY_FRACTION = 0.70
REPORT_JSON = Path("output/prediction_research/technical_indicator_survey.json")
REPORT_TXT = Path("output/prediction_research/technical_indicator_survey.txt")


# ---------- indicators (implemented inline so every formula is auditable) ----------

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series) -> tuple[pd.Series, pd.Series]:
    line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    return line, line.ewm(span=9, adjust=False).mean()


def bollinger(close: pd.Series, period: int = 20, mult: float = 2.0):
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std()
    return mid - mult * sd, mid, mid + mult * sd


def stochastic(high, low, close, period: int = 14):
    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    k = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    return k, k.rolling(3).mean()


def atr(high, low, close, period: int = 14) -> pd.Series:
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def williams_r(high, low, close, period: int = 14) -> pd.Series:
    highest = high.rolling(period).max()
    lowest = low.rolling(period).min()
    return -100 * (highest - close) / (highest - lowest).replace(0, np.nan)


def cci(high, low, close, period: int = 20) -> pd.Series:
    tp = (high + low + close) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma) / (0.015 * mad.replace(0, np.nan))


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    return (np.sign(close.diff()).fillna(0) * volume).cumsum()


def build_signals(d: pd.DataFrame) -> dict[str, pd.Series]:
    c, h, l, v = d["adj_close"], d["high"], d["low"], d["volume"]
    ret = c.pct_change()

    r = rsi(c)
    macd_line, macd_sig = macd(c)
    bb_low, bb_mid, bb_up = bollinger(c)
    k, dline = stochastic(h, l, c)
    a = atr(h, l, c)
    wr = williams_r(h, l, c)
    cc = cci(h, l, c)
    o = obv(c, v)
    sma20, sma50, sma200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    vol_avg20 = v.rolling(20).mean()
    up, down = ret > 0, ret < 0

    return {
        "rsi14_oversold_lt30": r < 30,
        "rsi14_cross_up_30": (r > 30) & (r.shift() <= 30),
        "rsi14_overbought_gt70": r > 70,
        "rsi14_cross_down_70": (r < 70) & (r.shift() >= 70),
        "macd_bullish_cross": (macd_line > macd_sig) & (macd_line.shift() <= macd_sig.shift()),
        "macd_bearish_cross": (macd_line < macd_sig) & (macd_line.shift() >= macd_sig.shift()),
        "macd_above_zero": macd_line > 0,
        "golden_cross_50_200": (sma50 > sma200) & (sma50.shift() <= sma200.shift()),
        "death_cross_50_200": (sma50 < sma200) & (sma50.shift() >= sma200.shift()),
        "price_cross_above_sma20": (c > sma20) & (c.shift() <= sma20.shift()),
        "price_cross_below_sma20": (c < sma20) & (c.shift() >= sma20.shift()),
        "price_above_sma200": c > sma200,
        "bb_touch_lower": c <= bb_low,
        "bb_touch_upper": c >= bb_up,
        "bb_squeeze": ((bb_up - bb_low) / bb_mid) < ((bb_up - bb_low) / bb_mid).rolling(100).quantile(0.20),
        "stoch_oversold_lt20": k < 20,
        "stoch_overbought_gt80": k > 80,
        "stoch_bullish_cross": (k > dline) & (k.shift() <= dline.shift()) & (k < 30),
        "williams_oversold": wr < -80,
        "williams_overbought": wr > -20,
        "cci_oversold_lt_m100": cc < -100,
        "cci_overbought_gt100": cc > 100,
        "volume_spike_up": (v > 2 * vol_avg20) & up,
        "volume_spike_down": (v > 2 * vol_avg20) & down,
        "three_consecutive_down": down & down.shift(1) & down.shift(2),
        "three_consecutive_up": up & up.shift(1) & up.shift(2),
        "gap_up": d["open"] > h.shift(),
        "gap_down": d["open"] < l.shift(),
        "atr_expansion": a > 1.5 * a.rolling(50).mean(),
        "obv_above_ma20": o > o.rolling(20).mean(),
        "new_high_20d": c >= c.rolling(20).max(),
        "new_low_20d": c <= c.rolling(20).min(),
    }


def measure(signal: pd.Series, fwd: pd.Series, base_rate: float) -> dict:
    """Edge = mean forward return when the signal fires, minus the period's own base rate."""
    fired = signal.fillna(False) & fwd.notna()
    n = int(fired.sum())
    if n < 30:  # too few observations to say anything
        return {"n": n, "edge": None, "net_edge": None, "t_stat": None, "win_rate": None}

    returns = fwd[fired]
    edge = float(returns.mean() - base_rate)
    t_stat = float(returns.mean() / (returns.std(ddof=1) / np.sqrt(n))) if returns.std(ddof=1) > 0 else 0.0
    return {
        "n": n,
        "edge": round(edge, 6),
        "net_edge": round(edge - ROUND_TRIP_COST, 6),
        "t_stat": round(t_stat, 3),
        "win_rate": round(float((returns > 0).mean()), 4),
    }


def main() -> None:
    results = []
    lines = [
        "Technical Indicator Survey -- BUMI & DEWA",
        "=" * 70,
        "",
        f"{len(TICKERS)} tickers x {HORIZONS} day horizons x ~32 signals, entry at the close AFTER",
        f"the signal bar. Edge = mean forward return when fired, minus that period's own base rate.",
        f"Net edge subtracts a {ROUND_TRIP_COST:.2%} round-trip cost (this project's MID assumption).",
        "",
        f"Split: first {DISCOVERY_FRACTION:.0%} of history = DISCOVERY, last {1-DISCOVERY_FRACTION:.0%} = HOLDOUT",
        "(never used to pick anything). The decisive number is the rank correlation between the two:",
        "it says whether 'best in backtest' predicts 'best going forward' at all.",
        "",
    ]

    for ticker in TICKERS:
        d = pd.read_csv(f"data/stocks/{ticker}.csv", parse_dates=["date"]).sort_values("date").reset_index(drop=True)
        signals = build_signals(d)
        c = d["adj_close"]
        split = int(len(d) * DISCOVERY_FRACTION)

        lines.append(f"\n{'='*70}\n{ticker}  (n={len(d)}, discovery {d.date[0].date()}..{d.date[split-1].date()}, "
                     f"holdout {d.date[split].date()}..{d.date.iloc[-1].date()})\n{'='*70}")

        for horizon in HORIZONS:
            # Signal at t -> enter at close of t+1 -> exit h days later. Shift(-1) implements the
            # one-bar execution delay so no signal is traded on the bar that formed it.
            fwd = (c.shift(-(horizon + 1)) / c.shift(-1) - 1)

            disc_slice = slice(0, split)
            hold_slice = slice(split, len(d))
            base_disc = float(fwd[disc_slice].mean())
            base_hold = float(fwd[hold_slice].mean())

            rows = []
            for name, sig in signals.items():
                dm = measure(sig[disc_slice], fwd[disc_slice], base_disc)
                hm = measure(sig[hold_slice], fwd[hold_slice], base_hold)
                rows.append({"ticker": ticker, "horizon": horizon, "signal": name,
                             "discovery": dm, "holdout": hm})
            results.extend(rows)

            usable = [r for r in rows if r["discovery"]["edge"] is not None and r["holdout"]["edge"] is not None]
            if len(usable) < 5:
                lines.append(f"\n-- h+{horizon}: too few signals with enough observations --")
                continue

            d_edges = [r["discovery"]["edge"] for r in usable]
            h_edges = [r["holdout"]["edge"] for r in usable]
            rho, pval = stats.spearmanr(d_edges, h_edges)

            usable.sort(key=lambda r: -r["discovery"]["edge"])
            lines.append(f"\n-- h+{horizon} (base rate: discovery {base_disc:+.3%}, holdout {base_hold:+.3%}) --")
            lines.append(f"{'signal':28s} {'disc n':>7s} {'disc edge':>10s} {'hold n':>7s} {'hold edge':>10s} {'hold NET':>10s}")
            for r in usable:
                lines.append(f"{r['signal']:28s} {r['discovery']['n']:7d} {r['discovery']['edge']:+9.3%} "
                             f"{r['holdout']['n']:7d} {r['holdout']['edge']:+9.3%} {r['holdout']['net_edge']:+9.3%}")

            top5 = usable[:5]
            top5_survived = sum(1 for r in top5 if r["holdout"]["edge"] > 0)
            top5_net_pos = sum(1 for r in top5 if r["holdout"]["net_edge"] > 0)
            any_net_pos = sum(1 for r in usable if r["holdout"]["net_edge"] > 0)

            lines.append(f"  rank correlation discovery vs holdout: rho={rho:+.3f} (p={pval:.3f})")
            lines.append(f"  of the top-5 discovery signals: {top5_survived}/5 still positive in holdout, "
                         f"{top5_net_pos}/5 positive after cost")
            lines.append(f"  signals with positive NET edge in holdout: {any_net_pos}/{len(usable)}")

    REPORT_TXT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({"round_trip_cost": ROUND_TRIP_COST, "results": results}, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
