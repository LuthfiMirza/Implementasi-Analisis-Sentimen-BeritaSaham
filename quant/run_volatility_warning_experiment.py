#!/usr/bin/env python3
"""Can the model warn that a stock is about to MOVE, even if it can't say which way?

Fase S found that atr14_pct and atr_ratio -- both magnitude-of-movement measures -- dominate
feature importance (36% combined), while the model only reaches ~40% on 3-class direction. That
diagnosis implies a specific, testable prediction: the same features should do considerably better
on a target they actually match, namely magnitude rather than direction.

So this swaps the target and changes nothing else:
    direction  : up / flat / down          -> ~40% (already measured, barely above chance)
    magnitude  : "big move" / "quiet"      -> tested here

This is not a trading signal and is not intended to become one. A magnitude warning says "position
sizing and stop distance should account for a wider range in the coming days"; it says nothing
about whether to buy or sell. Fase L, S4 and T all closed the direction/entry-signal question.

Method is identical to the rest of the project so results are comparable:
  * Same features as V6A (V2_NO_SENTIMENT_FEATURE_COLUMNS), same dataset, same 10 tickers.
  * Walk-forward with a purge gap = label horizon, so training rows whose labels overlap the test
    window are excluded (Fase S5).
  * Compared against majority-class and random baselines on the identical folds -- an 80% accuracy
    means nothing if 80% of days are "quiet" and the majority baseline gets it for free.
  * Thresholds are pre-specified (3%, 5%, 7%) and ALL are reported, winners and losers.

For a warning system the headline number is not overall accuracy but the "big move" class:
precision (when we raise the flag, how often is it right?) and recall (of all big moves, how many
did we catch?). Both are reported alongside their base rates.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support

sys.path.insert(0, str(Path(__file__).parent))
from run_multi_horizon_experiment import build_folds_with_purge  # noqa: E402
from train_prediction_models import (  # noqa: E402
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    MajorityClassModel,
    RandomBaselineModel,
    build_random_forest_pipeline,
)

DATASET = Path("output/prediction_research/dataset_v6a.csv")
STOCKS_DIR = Path("data/stocks")
HORIZON = 5
THRESHOLDS = [0.03, 0.05, 0.07]
MIN_TRAIN_DAYS, TEST_WINDOW_DAYS, MAX_FOLDS = 252, 126, 8
CLASSES = ["quiet", "big_move"]
REPORT_JSON = Path("output/prediction_research/volatility_warning_experiment.json")
REPORT_TXT = Path("output/prediction_research/volatility_warning_experiment.txt")


def build_dataset(features: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for ticker, group in features.groupby("ticker"):
        prices = pd.read_csv(STOCKS_DIR / f"{ticker}.csv", parse_dates=["date"]).sort_values("date")
        prices["fwd"] = prices["adj_close"].shift(-HORIZON) / prices["adj_close"] - 1
        merged = group.merge(prices[["date", "fwd"]], left_on="reference_date", right_on="date", how="inner")
        frames.append(merged.drop(columns=["date"]))
    out = pd.concat(frames, ignore_index=True)
    return out.dropna(subset=["fwd"])


def run(frame: pd.DataFrame, threshold: float) -> dict:
    frame = frame.copy()
    frame["label"] = np.where(frame["fwd"].abs() >= threshold, "big_move", "quiet")
    frame = frame.dropna(subset=[*V2_NO_SENTIMENT_FEATURE_COLUMNS, "label"])
    frame["reference_date"] = pd.to_datetime(frame["reference_date"])

    unique_dates = sorted(frame["reference_date"].drop_duplicates().tolist())
    folds = build_folds_with_purge(unique_dates, MIN_TRAIN_DAYS, TEST_WINDOW_DAYS, HORIZON)[-MAX_FOLDS:]
    if not folds:
        return {"error": "no folds"}

    class_probs = frame["label"].value_counts(normalize=True).to_dict()
    models = {
        "random_forest": lambda: build_random_forest_pipeline(V2_NO_SENTIMENT_FEATURE_COLUMNS),
        "majority_class": lambda: MajorityClassModel(),
        "random_baseline": lambda: RandomBaselineModel(class_probs, CLASSES),
    }

    per_model = {name: [] for name in models}
    base_rates = []
    # Per-fold detail matters more than the average here: an average lift can be carried by a
    # couple of favourable periods. Recording each fold makes both consistency AND any drift
    # over time visible instead of hidden behind a single mean.
    fold_detail = []

    for fold in folds:
        train = frame[frame["reference_date"] <= fold["train_end"]]
        test = frame[(frame["reference_date"] >= fold["test_start"]) & (frame["reference_date"] <= fold["test_end"])]
        if train.empty or test.empty:
            continue
        fold_base = float((test["label"] == "big_move").mean())
        base_rates.append(fold_base)

        for name, factory in models.items():
            model = factory()
            model.fit(train[V2_NO_SENTIMENT_FEATURE_COLUMNS], train["label"])
            pred = model.predict(test[V2_NO_SENTIMENT_FEATURE_COLUMNS])
            prec, rec, _, _ = precision_recall_fscore_support(
                test["label"], pred, labels=CLASSES, zero_division=0
            )
            metrics = {
                "accuracy": float(accuracy_score(test["label"], pred)),
                "f1_macro": float(f1_score(test["label"], pred, labels=CLASSES, average="macro", zero_division=0)),
                "precision_big_move": float(prec[CLASSES.index("big_move")]),
                "recall_big_move": float(rec[CLASSES.index("big_move")]),
            }
            per_model[name].append(metrics)
            if name == "random_forest":
                fold_detail.append({
                    "test_start": str(fold["test_start"])[:10],
                    "test_end": str(fold["test_end"])[:10],
                    "base_rate": round(fold_base, 4),
                    "precision_big_move": round(metrics["precision_big_move"], 4),
                    "lift": round(metrics["precision_big_move"] - fold_base, 4),
                })

    summary = {
        "threshold": threshold,
        "base_rate_big_move": round(float(np.mean(base_rates)), 4),
        "fold_count": len(base_rates),
        "folds_with_positive_lift": sum(1 for f in fold_detail if f["lift"] > 0),
        "fold_detail": fold_detail,
    }
    for name, rows in per_model.items():
        summary[name] = {k: round(float(np.mean([r[k] for r in rows])), 4) for k in rows[0]} if rows else None
    return summary


def main() -> None:
    df = pd.read_csv(DATASET)
    df["reference_date"] = pd.to_datetime(df["reference_date"])
    data = build_dataset(df[["ticker", "reference_date", *V2_NO_SENTIMENT_FEATURE_COLUMNS]])

    lines = [
        "Volatility Warning Experiment -- predicting MAGNITUDE instead of DIRECTION",
        "=" * 78,
        "",
        f"Same features as V6A, same walk-forward folds, purge gap = {HORIZON} days.",
        f"Target: |{HORIZON}-day forward return| >= threshold -> 'big_move', else 'quiet'.",
        "Reference: the same features on 3-class DIRECTION reach ~40% accuracy / 0.37 macro-F1.",
        "",
        "Read the 'big_move' precision/recall, not overall accuracy -- accuracy is inflated whenever",
        "one class dominates, which is exactly what the majority_class row exists to expose.",
        "",
    ]
    results = []

    for threshold in THRESHOLDS:
        r = run(data, threshold)
        results.append(r)
        if "error" in r:
            lines.append(f"threshold {threshold:.0%}: SKIPPED ({r['error']})")
            continue

        lines.append(f"--- ambang {threshold:.0%} (base rate 'big_move' = {r['base_rate_big_move']:.1%}, "
                     f"{r['fold_count']} fold) ---")
        lines.append(f"{'model':18s} {'accuracy':>9s} {'macro-F1':>9s} {'precision':>10s} {'recall':>8s}")
        for name in ["random_forest", "majority_class", "random_baseline"]:
            m = r[name]
            lines.append(f"{name:18s} {m['accuracy']:9.2%} {m['f1_macro']:9.4f} "
                         f"{m['precision_big_move']:10.2%} {m['recall_big_move']:8.2%}")

        rf, maj = r["random_forest"], r["majority_class"]
        lines.append(f"  -> vs majority: accuracy {rf['accuracy']-maj['accuracy']:+.2%}, "
                     f"macro-F1 {rf['f1_macro']-maj['f1_macro']:+.4f}")
        lines.append(f"  -> lift precision vs base rate: "
                     f"{rf['precision_big_move']-r['base_rate_big_move']:+.2%}")
        lines.append(f"  -> lift positif di {r['folds_with_positive_lift']}/{r['fold_count']} fold")
        lines.append("     per fold (cek konsistensi DAN pergeseran seiring waktu):")
        for f in r["fold_detail"]:
            lines.append(f"       {f['test_start']}..{f['test_end']}  presisi {f['precision_big_move']:6.2%} "
                         f"vs base {f['base_rate']:6.2%}  lift {f['lift']:+6.2%}")
        lines.append("")

    REPORT_TXT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({"horizon": HORIZON, "results": results}, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
