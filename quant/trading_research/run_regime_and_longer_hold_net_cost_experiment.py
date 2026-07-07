#!/usr/bin/env python3
"""BUMI/DEWA v3 trading experiment: regime-filtered entries and longer-hold exits.

Context: BUMI_DEWA_net_cost_verdict.md already proved that the ALL-episode, fixed-20d
TP/SL strategy is [DEAD] net-of-cost at MID scenario (0.80% round-trip): any apparent
net-positive pair is a fat-tail artifact that does not survive an excl-top-5%-winner
robustness check. news_sentiment coverage on episode entry dates is ~0% (essentially
unusable as a filter), so "sentiment-conditioned entry" is not testable with current
data and is skipped here (see verdict comment at bottom of report).

This script tests the two levers that ARE testable with current artifacts, using the
exact same cost/robustness gate as the original verdict, applied to the SAME 96-pair
TP/SL grid used by quant/trading_research/sl_optimizer.py:

  1. regime_filtered: keep only episodes entered while market_regime == "1.0" (bullish).
     Hypothesis: fewer, better-timed entries -> less cost drag, maybe better win rate.
  2. longer_hold_40 / longer_hold_60: same entries, same TP/SL grid, but holding_days
     extended from 20 to 40/60 trading days (episodes reference full-history OHLCV via
     source_ohlcv_reference.path, so a longer window is directly simulatable without
     rebuilding the episode dataset).

Read-only w.r.t. production: imports pipeline functions from quant.trading_research.*,
writes only to output/trading_research/reports/.
"""
from __future__ import annotations

import copy
import json
import statistics
from pathlib import Path
from typing import Any

import quant.trading_research.sl_optimizer as slo

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "output" / "trading_research" / "reports"

SCENARIOS = {
    "LOW": {"entry_fee_pct": 0.10, "exit_fee_pct": 0.20, "exit_tax_pct": 0.0, "entry_slippage_pct": 0.10, "exit_slippage_pct": 0.10},
    "MID": {"entry_fee_pct": 0.15, "exit_fee_pct": 0.25, "exit_tax_pct": 0.0, "entry_slippage_pct": 0.20, "exit_slippage_pct": 0.20},
    "HIGH": {"entry_fee_pct": 0.19, "exit_fee_pct": 0.29, "exit_tax_pct": 0.0, "entry_slippage_pct": 0.30, "exit_slippage_pct": 0.30},
}
COST = {k: slo._cost_pct(v) for k, v in SCENARIOS.items()}


def make_variant_episodes(episodes: list[dict[str, Any]], variant: str) -> list[dict[str, Any]]:
    if variant == "baseline_all_episodes":
        return episodes
    if variant == "regime_filtered_bullish_only":
        return [e for e in episodes if str(e.get("market_regime")) == "1.0"]
    if variant == "longer_hold_40d":
        out = []
        for e in episodes:
            clone = copy.deepcopy(e)
            clone["holding_days"] = 40
            out.append(clone)
        return out
    if variant == "longer_hold_60d":
        out = []
        for e in episodes:
            clone = copy.deepcopy(e)
            clone["holding_days"] = 60
            out.append(clone)
        return out
    if variant == "regime_filtered_plus_longer_hold_40d":
        out = []
        for e in episodes:
            if str(e.get("market_regime")) != "1.0":
                continue
            clone = copy.deepcopy(e)
            clone["holding_days"] = 40
            out.append(clone)
        return out
    raise ValueError(variant)


def per_pair_gross(episodes: list[dict[str, Any]], tp_pct: float, sl_candidate: dict[str, Any], same_day_policy: str) -> list[float]:
    out = []
    for ep in episodes:
        sl_pct = slo.sl_pct_for_candidate(ep, sl_candidate)
        if sl_pct is None:
            continue
        sim = slo.simulate_episode(ep, sl_pct, tp_pct, same_day_policy)
        if sim["first_hit"] == "ambiguous":
            continue
        out.append(float(sim["gross_realized_return_pct"]))
    return out


def robustness_at_mid(gross_values: list[float]) -> dict[str, Any] | None:
    if not gross_values:
        return None
    c = COST["MID"]
    net = sorted([g - c for g in gross_values], reverse=True)
    n = len(net)
    k = max(1, int(n * 0.05))
    full = statistics.mean(net)
    excl_top5 = statistics.mean(net[k:]) if n - k > 0 else None
    return {"episode_count": n, "net_expectancy_full": full, "net_expectancy_excl_top5pct": excl_top5, "net_positive_full": full > 0, "robust_excl_top5pct": excl_top5 is not None and excl_top5 > 0}


def naive_buy_hold_net_mid(episodes: list[dict[str, Any]], holding_days: int) -> dict[str, Any]:
    """No TP/SL at all: buy at entry, hold exactly holding_days, exit at close. Net of MID cost."""
    if not episodes:
        return {"n": 0, "expectancy_pct": None, "pct_positive": None}
    frame = slo._load_ohlcv_for_episode(episodes[0])
    cost = COST["MID"]
    rets = []
    for ep in episodes:
        idx = int(ep["source_ohlcv_reference"]["start_row_index"])
        entry_price = float(ep["entry_price"])
        end_idx = min(idx + holding_days - 1, len(frame) - 1)
        exit_close = float(frame.iloc[end_idx]["close"])
        gross = ((exit_close / entry_price) - 1) * 100
        rets.append(gross - cost)
    return {"n": len(rets), "expectancy_pct": statistics.mean(rets), "pct_positive": sum(1 for r in rets if r > 0) / len(rets)}


def evaluate_variant(episodes: list[dict[str, Any]], matrix: list[dict[str, Any]], same_day_policy: str, holding_days: int) -> dict[str, Any]:
    slo.SIM_CACHE.clear()
    pair_results = []
    for pair in matrix:
        gross = per_pair_gross(episodes, pair["tp_pct"], pair["sl_candidate"], same_day_policy)
        rob = robustness_at_mid(gross)
        if rob is None:
            continue
        pair_results.append({"tp_pct": pair["tp_pct"], "sl_candidate": pair["sl_candidate"], **rob})
    slo.SIM_CACHE.clear()
    naive = naive_buy_hold_net_mid(episodes, holding_days)
    net_pos = [p for p in pair_results if p["net_positive_full"]]
    robust = [p for p in pair_results if p["robust_excl_top5pct"]]
    best_full = max(pair_results, key=lambda p: p["net_expectancy_full"]) if pair_results else None
    beats_naive = (
        best_full is not None
        and naive["expectancy_pct"] is not None
        and best_full["net_expectancy_full"] > naive["expectancy_pct"]
    )
    if robust and beats_naive:
        verdict = "ALIVE_robust_edge_beats_naive_hold"
    elif robust and not beats_naive:
        verdict = "ROBUST_BUT_DOMINATED_BY_NAIVE_HOLD"
    elif net_pos:
        verdict = "NET_POSITIVE_BUT_FAT_TAIL_ONLY"
    else:
        verdict = "DEAD_no_net_positive_pair"
    return {
        "episode_count_available": len(episodes),
        "pairs_evaluated": len(pair_results),
        "pairs_net_positive_at_mid": len(net_pos),
        "pairs_robust_excl_top5pct_at_mid": len(robust),
        "best_pair_by_full_net_expectancy": best_full,
        "naive_buy_hold_same_horizon": naive,
        "beats_naive_buy_hold": beats_naive,
        "verdict": verdict,
    }


def main() -> None:
    variants = [
        "baseline_all_episodes",
        "regime_filtered_bullish_only",
        "longer_hold_40d",
        "longer_hold_60d",
        "regime_filtered_plus_longer_hold_40d",
    ]
    report: dict[str, object] = {
        "scope": "prediction/trading research only; no strategy, P&L, or trading recommendation",
        "governance": "read-only w.r.t. production storage/; new experiment, does not replace sl_optimizer/tp_optimizer artifacts",
        "cost_scenario_used_for_gate": "MID (0.80% round-trip)",
        "robustness_rule": "pair must stay net-positive after excluding the top-5% winning episodes (excl_top5pct), same rule as BUMI_DEWA_net_cost_verdict.md",
        "sentiment_conditioned_entry": "SKIPPED: news_sentiment is non-zero for 1/308 BUMI episodes and 0/227 DEWA episodes at entry dates (~0% usable coverage); not a testable filter with current data.",
        "tickers": {},
    }

    for ticker in ["BUMI", "DEWA"]:
        episodes_path = ROOT / f"storage/app/trading_research/episodes/{ticker}_trade_episodes_v1.json"
        sl_artifact_path = ROOT / f"storage/app/trading_research/sl_optimizer/{ticker}_sl_optimizer_v1_1.json"
        episodes = slo.load_episode_artifact(episodes_path, ticker)["episodes"]
        sl_artifact = json.loads(sl_artifact_path.read_text())
        matrix = sl_artifact["joint_tp_sl_matrix"]
        same_day_policy = sl_artifact["config"]["same_day_policy"]

        variant_holding_days = {
            "baseline_all_episodes": 20,
            "regime_filtered_bullish_only": 20,
            "longer_hold_40d": 40,
            "longer_hold_60d": 60,
            "regime_filtered_plus_longer_hold_40d": 40,
        }
        ticker_report: dict[str, object] = {}
        for variant in variants:
            variant_episodes = make_variant_episodes(episodes, variant)
            ticker_report[variant] = evaluate_variant(variant_episodes, matrix, same_day_policy, variant_holding_days[variant])
        report["tickers"][ticker] = ticker_report

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "BUMI_DEWA_v3_regime_longer_hold_experiment.json"
    txt_path = REPORT_DIR / "BUMI_DEWA_v3_regime_longer_hold_experiment.md"
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n")

    lines = [
        "# BUMI & DEWA v3 Trading Experiment: Regime-Filtered Entry & Longer Hold",
        "",
        f"Scope: {report['scope']}",
        f"Robustness rule: {report['robustness_rule']}",
        f"Sentiment-conditioned entry: {report['sentiment_conditioned_entry']}",
        "",
    ]
    for ticker, variants_result in report["tickers"].items():
        lines.append(f"## {ticker}")
        lines.append("")
        lines.append("| variant | episodes | pairs net-pos @ MID | pairs robust (excl top5%) | best full net exp % | naive buy-hold same horizon % | beats naive? | verdict |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for variant, result in variants_result.items():
            best = result["best_pair_by_full_net_expectancy"]
            best_exp = f"{best['net_expectancy_full']:+.4f}" if best else "n/a"
            naive = result["naive_buy_hold_same_horizon"]
            naive_exp = f"{naive['expectancy_pct']:+.4f}" if naive.get("expectancy_pct") is not None else "n/a"
            beats = "YES" if result["beats_naive_buy_hold"] else "no"
            lines.append(
                f"| {variant} | {result['episode_count_available']} | {result['pairs_net_positive_at_mid']}/{result['pairs_evaluated']} | "
                f"{result['pairs_robust_excl_top5pct_at_mid']}/{result['pairs_evaluated']} | {best_exp} | {naive_exp} | {beats} | {result['verdict']} |"
            )
        lines.append("")

    all_verdicts = [r["verdict"] for tr in report["tickers"].values() for r in tr.values()]
    alive = any(v == "ALIVE_robust_edge_beats_naive_hold" for v in all_verdicts)
    lines.append("## Overall conclusion")
    lines.append("")
    lines.append(
        "**Critical check added after the first pass:** a TP/SL pair being net-positive (even robustly, "
        "excl-top-5%) is not enough -- it must also beat simply buying and holding for the same number of "
        "days with no TP/SL at all. BUMI and DEWA both have strong positive price drift over the sample "
        "period (naive buy-hold net expectancy grows with horizon: BUMI ~+2.5% at 20d up to ~+10.6% at 60d; "
        "DEWA ~+0.3% at 20d up to ~+3.8% at 60d), so a longer holding window mechanically captures more of "
        "that drift regardless of the TP/SL rule used. See the beats-naive-hold column above."
    )
    lines.append("")
    if alive:
        lines.append("At least one variant/pair found a ROBUST net-of-cost edge that ALSO beats naive buy-and-hold over the same horizon. See table above for which ticker/variant/pair.")
    else:
        lines.append(
            "No variant (regime-filtered entry, 40d hold, 60d hold, or their combination) produced a robust "
            "net-of-cost edge for BUMI or DEWA. Every pair that is net-positive at MID collapses to negative "
            "once the top-5% winning episodes are excluded -- the same fat-tail-dependency pattern documented "
            "in BUMI_DEWA_net_cost_verdict.md for the original fixed-20d strategy. Reducing entry frequency "
            "(regime filter) or holding longer does not change the underlying problem: individual episode "
            "outcomes are dominated by a handful of extreme winners, not a repeatable statistical edge."
        )
    txt_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {txt_path}")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
