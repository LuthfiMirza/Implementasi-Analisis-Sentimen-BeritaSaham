#!/usr/bin/env python3
"""Confidence-thresholded buy/sell signal experiment.

The question this answers: instead of forcing the model to always pick a class (argmax, which is
how V6A/V6B serve predictions today), what if we only emit a BUY signal when the model's
P(up) clears a confidence threshold -- and a SELL when P(down) does? Rarer signals, but
hopefully higher quality.

Why this is NOT a repeat of Fase L (which failed):
  * Fase L's signal was a RULE-BASED composite (counting technical confirmations/warnings + R:R
    gate). It was never derived from model confidence. Result: avg return -0.25% vs +0.53%
    baseline over n=2400 windows -- actively harmful, and the VALID/WAIT claim was removed.
  * This tests a different mechanism: the trained model's own predicted probability. That has
    never been thresholded in this project -- serving always takes argmax.

Why accuracy is the wrong metric here, and what's measured instead:
  * A signal that fires on 3% of days with 45% precision can beat one that fires on 100% of days
    with 40% accuracy, if the winners are bigger than the losers. So the headline metric is
    AVERAGE FORWARD RETURN when the signal fires, compared against the average forward return of
    ALL days in the same test window (the "no signal, just be in the market" baseline).
  * If signalling does not beat that baseline, the signal has no value regardless of its
    precision. This is the same bar Fase L was held to.

Discipline (identical to run_multi_horizon_experiment.py):
  * Walk-forward with an explicit purge gap (= horizon trading days) between train and test.
  * Technical-only features (V2_NO_SENTIMENT_FEATURE_COLUMNS), matching V6A.
  * Probabilities come from models fitted ONLY on each fold's training window -- thresholds are
    applied to out-of-sample predictions, never in-sample.
  * Thresholds are swept and ALL results reported, including the bad ones. Picking the best
    threshold post-hoc and reporting only that would be data snooping -- the sweep is diagnostic,
    not a tuned result to promote.
  * No production model or serving path is touched. Research report only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from run_multi_horizon_experiment import (  # noqa: E402
    DATASET_PATH,
    MAX_FOLDS,
    MIN_TRAIN_DAYS,
    TEST_WINDOW_DAYS,
    build_folds_with_purge,
    build_horizon_dataset,
)
from train_prediction_models import (  # noqa: E402
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    build_random_forest_pipeline,
)

THRESHOLDS = [0.40, 0.45, 0.50, 0.55, 0.60]
REPORT_JSON = Path("output/prediction_research/confidence_signal_experiment.json")
REPORT_TXT = Path("output/prediction_research/confidence_signal_experiment.txt")


def collect_out_of_sample_predictions(frame: pd.DataFrame, feature_columns: list[str], horizon: int) -> pd.DataFrame:
    """Walk-forward: fit per fold, predict probabilities on that fold's test window only."""
    return_column = f"future_return_{horizon}d"
    frame = frame.dropna(subset=[*feature_columns, "label", return_column]).copy()
    frame["reference_date"] = pd.to_datetime(frame["reference_date"])
    unique_dates = sorted(frame["reference_date"].drop_duplicates().tolist())
    folds = build_folds_with_purge(unique_dates, MIN_TRAIN_DAYS, TEST_WINDOW_DAYS, horizon)[-MAX_FOLDS:]

    if not folds:
        return pd.DataFrame()

    collected = []
    for fold_index, fold in enumerate(folds):
        train_frame = frame[frame["reference_date"] <= fold["train_end"]]
        test_frame = frame[
            (frame["reference_date"] >= fold["test_start"]) & (frame["reference_date"] <= fold["test_end"])
        ]
        if train_frame.empty or test_frame.empty:
            continue

        model = build_random_forest_pipeline(feature_columns)
        model.fit(train_frame[feature_columns], train_frame["label"])
        probabilities = model.predict_proba(test_frame[feature_columns])
        classes = list(model.named_steps["model"].classes_)

        block = test_frame[["ticker", "reference_date", "label", return_column]].copy()
        block["fold"] = fold_index
        for class_index, class_name in enumerate(classes):
            block[f"proba_{class_name}"] = probabilities[:, class_index]
        collected.append(block)

    return pd.concat(collected, ignore_index=True) if collected else pd.DataFrame()


def summarize_signal(predictions: pd.DataFrame, horizon: int, side: str, threshold: float) -> dict:
    """side='buy' -> long when P(up) >= threshold. side='sell' -> short when P(down) >= threshold."""
    return_column = f"future_return_{horizon}d"
    proba_column = "proba_up" if side == "buy" else "proba_down"
    target_label = "up" if side == "buy" else "down"

    fired = predictions[predictions[proba_column] >= threshold]
    total = len(predictions)
    baseline_return = float(predictions[return_column].mean())

    if fired.empty:
        return {
            "side": side, "threshold": threshold, "signal_count": 0, "signal_rate": 0.0,
            "precision": None, "avg_return": None, "median_return": None,
            "baseline_avg_return": round(baseline_return, 6), "edge_vs_baseline": None,
            "win_rate": None, "folds_with_signal": 0,
        }

    # For a short, the trade profits when price falls -- flip the sign so avg_return is P&L, not
    # raw price change, making buy and sell directly comparable.
    signed_returns = fired[return_column] if side == "buy" else -fired[return_column]
    signed_baseline = baseline_return if side == "buy" else -baseline_return

    return {
        "side": side,
        "threshold": threshold,
        "signal_count": int(len(fired)),
        "signal_rate": round(len(fired) / total, 6),
        "precision": round(float((fired["label"] == target_label).mean()), 6),
        "avg_return": round(float(signed_returns.mean()), 6),
        "median_return": round(float(signed_returns.median()), 6),
        "baseline_avg_return": round(signed_baseline, 6),
        "edge_vs_baseline": round(float(signed_returns.mean()) - signed_baseline, 6),
        "win_rate": round(float((signed_returns > 0).mean()), 6),
        "folds_with_signal": int(fired["fold"].nunique()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizons", type=int, nargs="*", default=[3, 5])
    args = parser.parse_args()

    dataset = pd.read_csv(DATASET_PATH)
    dataset["reference_date"] = pd.to_datetime(dataset["reference_date"])
    features = dataset[["ticker", "reference_date", *V2_NO_SENTIMENT_FEATURE_COLUMNS]].copy()

    lines = [
        "Confidence-Thresholded Buy/Sell Signal Experiment",
        "=" * 55,
        "",
        "Only signal when the model's own probability clears a threshold, instead of always taking",
        "argmax (which is what production serving does today). Walk-forward with purge gap,",
        "technical-only features, probabilities strictly out-of-sample.",
        "",
        "THE BAR: avg_return when the signal fires must beat baseline_avg_return (the average",
        "forward return of ALL days in the same test windows). Beating precision alone is not",
        "enough -- Fase L's rule-based signal had signals too, and still lost money (-0.25% vs",
        "+0.53% baseline). edge_vs_baseline <= 0 means the signal is worthless or harmful.",
        "",
        "All thresholds are reported, including bad ones. Do NOT cherry-pick the best row -- that",
        "would be data snooping. Read this as a diagnostic of whether ANY threshold shows an edge.",
        "",
    ]
    results = []

    for horizon in args.horizons:
        print(f"\n=== horizon={horizon}d ===", flush=True)
        horizon_frame, class_threshold = build_horizon_dataset(features, horizon)
        predictions = collect_out_of_sample_predictions(horizon_frame, V2_NO_SENTIMENT_FEATURE_COLUMNS, horizon)

        if predictions.empty:
            print("  no folds -- skipped", flush=True)
            lines.append(f"h+{horizon}: SKIPPED (no folds fit)")
            continue

        return_column = f"future_return_{horizon}d"
        baseline = float(predictions[return_column].mean())
        print(f"  out-of-sample rows={len(predictions)} baseline_avg_return={baseline:.4%}", flush=True)

        lines.append(f"--- h+{horizon} (class threshold={class_threshold:.4f}, "
                     f"out-of-sample rows={len(predictions)}) ---")
        lines.append(f"baseline avg forward return (all days, long) = {baseline:+.4%}")
        lines.append("")
        lines.append(f"{'side':5s} {'thr':>5s} {'signals':>8s} {'rate':>7s} {'precision':>10s} "
                     f"{'avg_ret':>9s} {'baseline':>9s} {'EDGE':>9s} {'win_rate':>9s} {'folds':>6s}")

        for side in ["buy", "sell"]:
            for threshold in THRESHOLDS:
                summary = summarize_signal(predictions, horizon, side, threshold)
                summary["horizon"] = horizon
                results.append(summary)

                if summary["signal_count"] == 0:
                    lines.append(f"{side:5s} {threshold:5.2f} {0:8d} {'-':>7s} {'-':>10s} "
                                 f"{'-':>9s} {'-':>9s} {'-':>9s} {'-':>9s} {0:6d}")
                    continue

                lines.append(
                    f"{side:5s} {threshold:5.2f} {summary['signal_count']:8d} "
                    f"{summary['signal_rate']:6.2%} {summary['precision']:9.2%} "
                    f"{summary['avg_return']:+8.3%} {summary['baseline_avg_return']:+8.3%} "
                    f"{summary['edge_vs_baseline']:+8.3%} {summary['win_rate']:8.2%} "
                    f"{summary['folds_with_signal']:6d}"
                )
                print(f"  {side} thr={threshold:.2f}: n={summary['signal_count']} "
                      f"precision={summary['precision']:.2%} avg_ret={summary['avg_return']:+.3%} "
                      f"edge={summary['edge_vs_baseline']:+.3%}", flush=True)

        lines.append("")

    positive_edges = [r for r in results if r.get("edge_vs_baseline") is not None and r["edge_vs_baseline"] > 0]
    lines.append("--- verdict ---")
    if not positive_edges:
        lines.append("NO threshold on either side beat the baseline. Confidence thresholding does not")
        lines.append("produce a tradeable signal on this data -- same conclusion as Fase L, different")
        lines.append("mechanism. Do not ship a buy/sell signal on this basis.")
    else:
        lines.append(f"{len(positive_edges)} of {len(results)} threshold/side combinations beat baseline.")
        lines.append("CAUTION: with 20 combinations swept, some positive edges are expected by chance")
        lines.append("alone. Treat any positive row as a HYPOTHESIS to re-test on held-out data, not a")
        lines.append("validated signal. Check whether the edge holds across most folds (folds column)")
        lines.append("and whether signal_count is large enough to be meaningful.")

    REPORT_TXT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    print("\n" + "\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
