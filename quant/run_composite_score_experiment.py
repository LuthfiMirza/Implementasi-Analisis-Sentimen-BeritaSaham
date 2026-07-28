#!/usr/bin/env python3
"""Reconstruct and test the TECHNICAL HALF of the "Zeta AI" composite scoring system the user
showed screenshots of (Fase V discussion).

CRITICAL SCOPE LIMIT, stated up front: that service's score combines broker-flow signals
("DI Dominant", "SM Buy", "Star Buyer" -- net foreign/broker order flow) with technical
confirmation (MACD, RSI, EMA, VWAP, ADX, Bollinger). The broker-flow half CANNOT be built --
Fase V confirmed no accessible free source exists (idx.co.id broker-summary endpoints return 403
Cloudflare; sectors.app's Bandarmology API is paid-only). This script tests ONLY a technical
composite score. Any result here describes a technical-confluence system, not the full thing the
screenshots showed -- reported explicitly as a partial reconstruction, not a replication.

The question worth asking regardless: Fase T found individual indicators mostly fail out of
sample (DEWA backtest-to-holdout rank correlation -0.760). Does REQUIRING SEVERAL to agree
simultaneously (a composite score crossing a threshold) do any better, or does it just combine
several weak/unstable signals into an equally weak one?

Method identical to Fase T for direct comparability:
  * Same two tickers (BUMI, DEWA), same chronological 70/30 discovery/holdout split.
  * Composite score = count of bullish conditions among: MACD bullish (line > signal), price
    above EMA20, price above EMA50, ADX > 25 (trending, a proxy for "confirmed direction" since
    plain ADX doesn't carry direction on its own -- gated on price > EMA50 for direction), price
    above VWAP-proxy (20-day volume-weighted average price, since intraday VWAP isn't available
    in daily OHLCV), RSI in the 45-70 "bullish momentum, not yet overbought" zone. 6 possible
    points.
  * Entry deferred one bar after the score is observed (same execution discipline as Fase T).
  * Thresholds 3/4/5/6 (out of 6) swept, ALL reported -- no cherry-picking the best one.
  * Net of the same 0.80% round-trip cost.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

TICKERS = ["BBCA", "BBRI", "BMRI", "TLKM", "ASII", "GOTO", "INDF", "ICBP", "ADRO", "UNVR", "BUMI", "DEWA"]
HORIZONS = [5, 10]
ROUND_TRIP_COST = 0.008
DISCOVERY_FRACTION = 0.70
SCORE_THRESHOLDS = [3, 4, 5, 6]
REPORT_JSON = Path("output/prediction_research/composite_score_experiment.json")
REPORT_TXT = Path("output/prediction_research/composite_score_experiment.txt")


def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close):
    line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    return line, line.ewm(span=9, adjust=False).mean()


def adx(high, low, close, period=14):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1 / period, adjust=False).mean() / atr_
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1 / period, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def build_composite_score(d: pd.DataFrame) -> pd.DataFrame:
    c, h, l, v = d["adj_close"], d["high"], d["low"], d["volume"]
    r = rsi(c)
    macd_line, macd_sig = macd(c)
    ema20, ema50 = c.ewm(span=20, adjust=False).mean(), c.ewm(span=50, adjust=False).mean()
    a = adx(h, l, c)
    # Daily-bar proxy for VWAP: 20-day volume-weighted average price (true intraday VWAP needs
    # tick data we don't have -- stated explicitly as an approximation, not the real thing).
    vwap_proxy = (c * v).rolling(20).sum() / v.rolling(20).sum()

    conditions = pd.DataFrame({
        "macd_bullish": macd_line > macd_sig,
        "above_ema20": c > ema20,
        "above_ema50": c > ema50,
        "adx_trending_up": (a > 25) & (c > ema50),
        "above_vwap_proxy": c > vwap_proxy,
        "rsi_bullish_zone": (r >= 45) & (r <= 70),
    })
    score = conditions.sum(axis=1)
    return score, conditions


def measure(fired: pd.Series, fwd: pd.Series, base_rate: float) -> dict:
    mask = fired.fillna(False) & fwd.notna()
    n = int(mask.sum())
    if n < 30:
        return {"n": n, "edge": None, "net_edge": None, "win_rate": None}
    returns = fwd[mask]
    edge = float(returns.mean() - base_rate)
    return {
        "n": n, "edge": round(edge, 6), "net_edge": round(edge - ROUND_TRIP_COST, 6),
        "win_rate": round(float((returns > 0).mean()), 4),
    }


def main() -> None:
    lines = [
        "Composite Technical Score Experiment (TECHNICAL HALF ONLY -- see scope limit)",
        "=" * 78,
        "",
        "SCOPE LIMIT: the source's real score combines broker-flow signals (net foreign/broker",
        "buying) with technical confirmation. The broker-flow half could not be built -- no",
        "accessible free data source (Fase V: idx.co.id broker endpoints 403, sectors.app paid-",
        "only). This tests ONLY a technical composite (6-point score: MACD, EMA20, EMA50, ADX+",
        "trend direction, VWAP-proxy, RSI zone). This is a partial reconstruction, not the actual",
        "system -- treat results as informative about technical confluence generally, not as a",
        "verdict on the real service.",
        "",
        "Same discipline as Fase T: chronological 70/30 split, holdout never used to pick",
        "anything, entry one bar after the score is observed, net of 0.80% round-trip cost.",
        "",
    ]
    results = []

    for ticker in TICKERS:
        d = pd.read_csv(f"data/stocks/{ticker}.csv", parse_dates=["date"]).sort_values("date").reset_index(drop=True)
        score, conditions = build_composite_score(d)
        c = d["adj_close"]
        split = int(len(d) * DISCOVERY_FRACTION)

        lines.append(f"\n{'='*78}\n{ticker}  (discovery {d.date[0].date()}..{d.date[split-1].date()}, "
                     f"holdout {d.date[split].date()}..{d.date.iloc[-1].date()})\n{'='*78}")

        for horizon in HORIZONS:
            fwd = (c.shift(-(horizon + 1)) / c.shift(-1) - 1)
            disc_slice, hold_slice = slice(0, split), slice(split, len(d))
            base_disc, base_hold = float(fwd[disc_slice].mean()), float(fwd[hold_slice].mean())

            rows = []
            for threshold in SCORE_THRESHOLDS:
                fired = score >= threshold
                dm = measure(fired[disc_slice], fwd[disc_slice], base_disc)
                hm = measure(fired[hold_slice], fwd[hold_slice], base_hold)
                rows.append({"ticker": ticker, "horizon": horizon, "score_threshold": threshold,
                             "discovery": dm, "holdout": hm})
            results.extend(rows)

            usable = [r for r in rows if r["discovery"]["edge"] is not None and r["holdout"]["edge"] is not None]
            lines.append(f"\n-- h+{horizon} (base rate: discovery {base_disc:+.3%}, holdout {base_hold:+.3%}) --")
            lines.append(f"{'score >=':>9s} {'disc n':>7s} {'disc edge':>10s} {'hold n':>7s} {'hold edge':>10s} {'hold NET':>10s} {'hold win%':>10s}")
            for r in rows:
                dn = r["discovery"]["n"] or 0
                hn = r["holdout"]["n"] or 0
                de = f"{r['discovery']['edge']:+9.3%}" if r["discovery"]["edge"] is not None else "     n/a"
                he = f"{r['holdout']['edge']:+9.3%}" if r["holdout"]["edge"] is not None else "     n/a"
                hne = f"{r['holdout']['net_edge']:+9.3%}" if r["holdout"]["net_edge"] is not None else "     n/a"
                hw = f"{r['holdout']['win_rate']:9.2%}" if r["holdout"]["win_rate"] is not None else "      n/a"
                lines.append(f"{r['score_threshold']:9d} {dn:7d} {de} {hn:7d} {he} {hne} {hw}")

            if len(usable) >= 4:
                d_edges = [r["discovery"]["edge"] for r in usable]
                h_edges = [r["holdout"]["edge"] for r in usable]
                rho, pval = stats.spearmanr(d_edges, h_edges)
                lines.append(f"  rank correlation discovery vs holdout across thresholds: rho={rho:+.3f} (p={pval:.3f})")

    # Cross-ticker summary at the highest threshold (score>=6, all conditions agree) -- the
    # single number decision-relevant to "does this generalize beyond BUMI": count of tickers
    # where the strictest confluence signal beats holdout base rate net of cost.
    lines.append(f"\n\n{'='*78}\nRINGKASAN LINTAS SAHAM (score >= {max(SCORE_THRESHOLDS)}, ambang paling ketat)\n{'='*78}")
    lines.append(f"{'ticker':8s} {'horizon':>8s} {'n hold':>7s} {'net edge':>10s} {'win rate':>10s} {'positif net?':>13s}")
    top = [r for r in results if r["score_threshold"] == max(SCORE_THRESHOLDS)]
    positive_count, total_count = 0, 0
    for r in top:
        hm = r["holdout"]
        if hm["net_edge"] is None:
            lines.append(f"{r['ticker']:8s} {r['horizon']:8d} {'n/a':>7s} {'n/a':>10s} {'n/a':>10s} {'data kurang':>13s}")
            continue
        total_count += 1
        is_pos = hm["net_edge"] > 0
        positive_count += int(is_pos)
        lines.append(f"{r['ticker']:8s} {r['horizon']:8d} {hm['n']:7d} {hm['net_edge']:+9.3%} "
                     f"{hm['win_rate']:9.2%} {'YA' if is_pos else 'tidak':>13s}")
    lines.append(f"\n-> net edge positif di {positive_count}/{total_count} kombinasi ticker x horizon "
                 f"(ambang paling ketat, di luar biaya transaksi)")

    REPORT_TXT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({"results": results, "scope_limit": "technical_half_only_no_broker_flow_data"}, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
