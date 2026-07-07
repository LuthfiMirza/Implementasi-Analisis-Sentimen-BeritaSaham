#!/usr/bin/env python3
"""Out-of-sample walk-forward validation of the surviving BUMI/DEWA trading candidate.

Context: run_regime_and_longer_hold_net_cost_experiment.py found exactly one variant/pair that
passed both the excl-top-5% robustness gate and the beats-naive-buy-hold gate: DEWA
regime_filtered_plus_longer_hold_40d with tp=30/sl=3 (fixed). It was flagged
candidate_experimental because it emerged from scanning 960 hypotheses on ONE full sample with
no train/test split -- textbook data-snooping risk. This script runs the pre-registered
graduation test that the project's research notes require before that candidate may be trusted:

  1. Sort regime-filtered 40d-hold episodes chronologically, split train/test (primary 70/30,
     sensitivity 60/40). The test window is never used for selection.
  2. Selection replay: on TRAIN episodes only, evaluate the same 96-pair TP/SL grid net of MID
     costs (0.80% round trip) and select the best pair by full net expectancy -- mirroring how
     the original candidate was discovered, but honestly (selection cannot see the test data).
  3. Evaluate the selected pair on the untouched TEST episodes: net expectancy, excl-top-5%
     robustness, win rate, bootstrap 95% CI of mean net return, and naive buy-and-hold over the
     same horizon on the same test episodes.
  4. The frozen original candidate (tp=30/sl=3) is also evaluated on the test window, clearly
     labeled as WEAKER evidence: that pair was chosen using the full sample, so its OOS numbers
     are upward-biased by construction.

PRE-REGISTERED pass criteria (fixed before looking at any result; primary split only):
  P1. selected-pair OOS net expectancy > 0
  P2. selected-pair OOS net expectancy > naive buy-hold net expectancy on the same test episodes
  P3. selected-pair OOS excl-top-5% net expectancy > 0
  P4. bootstrap 95% CI lower bound of the OOS mean net return > 0
Overall verdict PASS requires all four. Anything else = candidate stays experimental (or is
retired if P1/P2 fail outright).

Read-only w.r.t. production storage/; writes only to output/trading_research/reports/.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

import numpy as np

import quant.trading_research.sl_optimizer as slo
from quant.trading_research.run_regime_and_longer_hold_net_cost_experiment import (
    COST,
    make_variant_episodes,
    naive_buy_hold_net_mid,
    per_pair_gross,
)

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "output" / "trading_research" / "reports"

VARIANT = "regime_filtered_plus_longer_hold_40d"
HOLDING_DAYS = 40
FROZEN_CANDIDATE = {"tp_pct": 30.0, "sl_candidate": {"type": "fixed_pct", "value": 3.0}}
BOOTSTRAP_ITERATIONS = 5000
BOOTSTRAP_SEED = 42


def pair_net_returns(episodes: list[dict[str, Any]], pair: dict[str, Any], same_day_policy: str) -> list[float]:
    gross = per_pair_gross(episodes, pair["tp_pct"], pair["sl_candidate"], same_day_policy)
    cost = COST["MID"]
    return [g - cost for g in gross]


def bootstrap_ci(values: list[float]) -> tuple[float, float]:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    data = np.array(values)
    means = [float(rng.choice(data, size=len(data), replace=True).mean()) for _ in range(BOOTSTRAP_ITERATIONS)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summarize_net(net: list[float]) -> dict[str, Any] | None:
    if not net:
        return None
    ordered = sorted(net, reverse=True)
    k = max(1, int(len(ordered) * 0.05))
    ci_low, ci_high = bootstrap_ci(net)
    return {
        "episode_count": len(net),
        "net_expectancy": statistics.mean(net),
        "net_expectancy_excl_top5pct": statistics.mean(ordered[k:]) if len(ordered) > k else None,
        "win_rate": sum(1 for value in net if value > 0) / len(net),
        "bootstrap_ci95_low": ci_low,
        "bootstrap_ci95_high": ci_high,
    }


def select_best_pair_on_train(train_episodes: list[dict[str, Any]], matrix: list[dict[str, Any]], same_day_policy: str) -> tuple[dict[str, Any], float]:
    best_pair = None
    best_expectancy = None
    for pair in matrix:
        net = pair_net_returns(train_episodes, pair, same_day_policy)
        if not net:
            continue
        expectancy = statistics.mean(net)
        if best_expectancy is None or expectancy > best_expectancy:
            best_expectancy = expectancy
            best_pair = pair
    return best_pair, best_expectancy


def evaluate_split(episodes_sorted: list[dict[str, Any]], split_fraction: float, matrix: list[dict[str, Any]], same_day_policy: str) -> dict[str, Any]:
    cut = int(len(episodes_sorted) * split_fraction)
    train = episodes_sorted[:cut]
    test = episodes_sorted[cut:]

    selected_pair, train_expectancy = select_best_pair_on_train(train, matrix, same_day_policy)
    oos_selected = summarize_net(pair_net_returns(test, selected_pair, same_day_policy))
    oos_frozen = summarize_net(pair_net_returns(test, FROZEN_CANDIDATE, same_day_policy))
    naive = naive_buy_hold_net_mid(test, HOLDING_DAYS)

    criteria = None
    if oos_selected is not None and naive["expectancy_pct"] is not None:
        criteria = {
            "P1_oos_net_expectancy_positive": oos_selected["net_expectancy"] > 0,
            "P2_beats_naive_buy_hold": oos_selected["net_expectancy"] > naive["expectancy_pct"],
            "P3_excl_top5pct_positive": (oos_selected["net_expectancy_excl_top5pct"] or 0) > 0,
            "P4_bootstrap_ci_lower_positive": oos_selected["bootstrap_ci95_low"] > 0,
        }

    return {
        "split_fraction": split_fraction,
        "train_episode_count": len(train),
        "test_episode_count": len(test),
        "train_window": [train[0]["entry_date"], train[-1]["entry_date"]] if train else None,
        "test_window": [test[0]["entry_date"], test[-1]["entry_date"]] if test else None,
        "selected_pair_on_train": {"tp_pct": selected_pair["tp_pct"], "sl_candidate": selected_pair["sl_candidate"]},
        "selected_pair_train_net_expectancy": train_expectancy,
        "selected_pair_matches_frozen_candidate": (
            selected_pair["tp_pct"] == FROZEN_CANDIDATE["tp_pct"]
            and selected_pair["sl_candidate"] == FROZEN_CANDIDATE["sl_candidate"]
        ),
        "oos_selected_pair": oos_selected,
        "oos_frozen_candidate_tp30_sl3_biased_view": oos_frozen,
        "oos_naive_buy_hold_same_horizon": naive,
        "pre_registered_criteria": criteria,
        "all_criteria_pass": bool(criteria) and all(criteria.values()),
    }


def main() -> None:
    report: dict[str, Any] = {
        "scope": "trading research only; graduation test for the candidate_experimental strategy, not a trading recommendation",
        "governance": "read-only w.r.t. production storage/; selection never sees the test window",
        "variant": VARIANT,
        "cost_scenario": "MID (0.80% round-trip)",
        "pre_registered_pass_criteria": [
            "P1: selected-pair OOS net expectancy > 0",
            "P2: selected-pair OOS net expectancy > naive buy-hold on same test episodes",
            "P3: selected-pair OOS excl-top-5% net expectancy > 0",
            "P4: bootstrap 95% CI lower bound of OOS mean net return > 0",
            "Overall PASS requires all four on the primary 70/30 split.",
        ],
        "tickers": {},
    }

    for ticker in ["DEWA", "BUMI"]:
        episodes_path = ROOT / f"storage/app/trading_research/episodes/{ticker}_trade_episodes_v1.json"
        sl_artifact = json.loads((ROOT / f"storage/app/trading_research/sl_optimizer/{ticker}_sl_optimizer_v1_1.json").read_text())
        matrix = sl_artifact["joint_tp_sl_matrix"]
        same_day_policy = sl_artifact["config"]["same_day_policy"]

        slo.SIM_CACHE.clear()
        episodes = slo.load_episode_artifact(episodes_path, ticker)["episodes"]
        variant_episodes = sorted(make_variant_episodes(episodes, VARIANT), key=lambda e: e["entry_date"])

        report["tickers"][ticker] = {
            "primary_split_70_30": evaluate_split(variant_episodes, 0.7, matrix, same_day_policy),
            "sensitivity_split_60_40": evaluate_split(variant_episodes, 0.6, matrix, same_day_policy),
        }
        slo.SIM_CACHE.clear()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "BUMI_DEWA_candidate_oos_walkforward_validation.json"
    md_path = REPORT_DIR / "BUMI_DEWA_candidate_oos_walkforward_validation.md"
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n")

    lines = [
        "# OOS Walk-Forward Validation: kandidat regime-filter + hold 40d (BUMI & DEWA)",
        "",
        f"Scope: {report['scope']}",
        "",
        "Kriteria lolos (pre-registered, ditetapkan SEBELUM melihat hasil):",
    ]
    lines += [f"- {c}" for c in report["pre_registered_pass_criteria"]]
    lines.append("")

    for ticker, splits in report["tickers"].items():
        lines.append(f"## {ticker}")
        for split_name, result in splits.items():
            selected = result["selected_pair_on_train"]
            oos = result["oos_selected_pair"]
            frozen = result["oos_frozen_candidate_tp30_sl3_biased_view"]
            naive = result["oos_naive_buy_hold_same_horizon"]
            lines.append("")
            lines.append(f"### {split_name} (train n={result['train_episode_count']}, test n={result['test_episode_count']}, test window {result['test_window'][0]} -> {result['test_window'][1]})")
            lines.append(f"- Pair terpilih di TRAIN saja: tp={selected['tp_pct']} / sl={selected['sl_candidate']} (train net exp {result['selected_pair_train_net_expectancy']:+.4f}%)")
            lines.append(f"- Sama dengan kandidat asli tp30/sl3? {'YA' if result['selected_pair_matches_frozen_candidate'] else 'TIDAK'}")
            if oos:
                lines.append(
                    f"- OOS pair terpilih: net exp {oos['net_expectancy']:+.4f}% | excl-top5% {oos['net_expectancy_excl_top5pct']:+.4f}% | "
                    f"win rate {oos['win_rate']:.1%} | CI95 [{oos['bootstrap_ci95_low']:+.4f}%, {oos['bootstrap_ci95_high']:+.4f}%]"
                )
            if frozen:
                lines.append(
                    f"- OOS kandidat beku tp30/sl3 (bias ke atas, dipilih pakai full sample): net exp {frozen['net_expectancy']:+.4f}% | "
                    f"excl-top5% {frozen['net_expectancy_excl_top5pct']:+.4f}% | CI95 [{frozen['bootstrap_ci95_low']:+.4f}%, {frozen['bootstrap_ci95_high']:+.4f}%]"
                )
            lines.append(f"- Naive buy-hold {HOLDING_DAYS}d di test episodes yang sama: {naive['expectancy_pct']:+.4f}%")
            if result["pre_registered_criteria"]:
                for name, passed in result["pre_registered_criteria"].items():
                    lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
            lines.append(f"- **Verdict split ini: {'PASS' if result['all_criteria_pass'] else 'FAIL'}**")
        lines.append("")

    md_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
