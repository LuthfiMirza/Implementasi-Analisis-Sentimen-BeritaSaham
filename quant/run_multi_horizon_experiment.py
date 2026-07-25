#!/usr/bin/env python3
"""Multi-horizon prediction experiment: does accuracy improve at longer horizons (h+1/h+3/h+7/h+30)
compared to the production 5-day horizon, and does gradient boosting beat RandomForest (V6A's
current algorithm)?

Discipline:
  * Reuses build_folds/evaluate_predictions/mean_metrics from quant/train_prediction_models.py
    (the same walk-forward primitives already used for V6A/V6B) -- not reinvented.
  * Technical-only features (V2_NO_SENTIMENT_FEATURE_COLUMNS), matching V6A exactly -- sentiment
    has never been shown to help price prediction in this project (Fase A/C), so it's excluded
    here to isolate the two variables actually being tested: horizon length and algorithm.
  * CRITICAL METHODOLOGY FIX vs the existing 5-day setup: build_folds() has no purge gap between
    train and test. For a forward-looking label of N days, the last ~N training rows' labels
    depend on price data that overlaps the first N days of the test window -- a real leakage risk
    that grows with horizon (bigger at h+30 than h+5). This script adds an explicit purge gap
    (= horizon trading days) between train_end and test_start, per the "Leakage-Controlled
    Horizon-Specific Model Selection" methodology (Forecasting, 2026).
  * Labels are NOT copied from dataset_v6a.csv (which only has the 5-day label). Forward returns
    are computed fresh per horizon from data/stocks/{TICKER}.csv's adj_close (back-adjusted,
    matching ResearchPredictionFeatureService's basis) and joined to the already-computed
    technical features by ticker+reference_date.
  * Class threshold scales by sqrt(horizon/5) from the production 5-day threshold (0.015) --
    same scaling already used for BUMI/DEWA horizon experiments (run_volatile_v2_experiments.py),
    reflecting that cumulative volatility grows with the sqrt of time.
  * No production model is touched. This is a research report only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).parent))
from train_prediction_models import (  # noqa: E402
    CLASS_ORDER,
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    build_random_forest_pipeline,
    evaluate_predictions,
    mean_metrics,
)

HORIZONS = [1, 3, 7, 30]
BASE_THRESHOLD = 0.015  # matches production V6A 5-day threshold
BASE_HORIZON = 5
STOCKS_DIR = Path("data/stocks")
DATASET_PATH = Path("output/prediction_research/dataset_v6a.csv")
REPORT_JSON = Path("output/prediction_research/multi_horizon_experiment_report.json")
REPORT_TXT = Path("output/prediction_research/multi_horizon_experiment_report.txt")
MIN_TRAIN_DAYS = 252
TEST_WINDOW_DAYS = 126
MAX_FOLDS = 8


def build_gradient_boosting_pipeline(feature_columns: list[str]) -> Pipeline:
    return Pipeline(steps=[
        ("preprocess", ColumnTransformer(transformers=[("num", SimpleImputer(strategy="median"), feature_columns)])),
        ("model", HistGradientBoostingClassifier(max_iter=100, learning_rate=0.08, max_depth=6, random_state=42)),
    ])


def label_direction(returns: pd.Series, threshold: float) -> pd.Series:
    return pd.Series(
        np.where(returns >= threshold, "up", np.where(returns <= -threshold, "down", "flat")),
        index=returns.index,
    )


def load_price_series(ticker: str) -> pd.DataFrame:
    path = STOCKS_DIR / f"{ticker}.csv"
    frame = pd.read_csv(path)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values("date").reset_index(drop=True)
    return frame[["date", "adj_close"]]


def build_horizon_dataset(features: pd.DataFrame, horizon: int) -> pd.DataFrame:
    threshold = BASE_THRESHOLD * np.sqrt(horizon / BASE_HORIZON)
    frames = []
    for ticker, group in features.groupby("ticker"):
        prices = load_price_series(ticker)
        prices[f"future_return_{horizon}d"] = prices["adj_close"].shift(-horizon).div(prices["adj_close"]).sub(1)
        merged = group.merge(prices[["date", f"future_return_{horizon}d"]], left_on="reference_date", right_on="date", how="inner")
        merged = merged.drop(columns=["date"])
        merged["label"] = label_direction(merged[f"future_return_{horizon}d"], threshold)
        merged = merged.dropna(subset=[f"future_return_{horizon}d"])
        frames.append(merged)

    result = pd.concat(frames, ignore_index=True)
    return result, threshold


def build_folds_with_purge(unique_dates: list[pd.Timestamp], min_train_days: int, test_window_days: int, purge_days: int) -> list[dict]:
    folds = []
    train_end_idx = min_train_days - 1
    while True:
        test_start_idx = train_end_idx + 1 + purge_days
        if test_start_idx + test_window_days > len(unique_dates):
            break
        test_dates = unique_dates[test_start_idx: test_start_idx + test_window_days]
        if not test_dates:
            break
        folds.append({
            "train_end": unique_dates[train_end_idx],
            "test_start": test_dates[0],
            "test_end": test_dates[-1],
        })
        train_end_idx += test_window_days
    return folds


def run_walk_forward(frame: pd.DataFrame, feature_columns: list[str], model_factory, purge_days: int) -> dict:
    frame = frame.dropna(subset=[*feature_columns, "label"]).copy()
    frame["reference_date"] = pd.to_datetime(frame["reference_date"])
    unique_dates = sorted(frame["reference_date"].drop_duplicates().tolist())
    folds = build_folds_with_purge(unique_dates, MIN_TRAIN_DAYS, TEST_WINDOW_DAYS, purge_days)
    folds = folds[-MAX_FOLDS:]

    if not folds:
        return {"error": f"no folds fit (n_dates={len(unique_dates)}, purge_days={purge_days})"}

    fold_metrics = []
    for fold in folds:
        train_mask = frame["reference_date"] <= fold["train_end"]
        test_mask = (frame["reference_date"] >= fold["test_start"]) & (frame["reference_date"] <= fold["test_end"])
        train_frame = frame[train_mask]
        test_frame = frame[test_mask]
        if train_frame.empty or test_frame.empty:
            continue

        model = model_factory(feature_columns)
        model.fit(train_frame[feature_columns], train_frame["label"])
        preds = model.predict(test_frame[feature_columns])
        fold_metrics.append(evaluate_predictions(test_frame["label"], preds, CLASS_ORDER))

    if not fold_metrics:
        return {"error": "no non-empty folds"}

    return {"fold_count": len(fold_metrics), "mean_metrics": mean_metrics(fold_metrics)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizons", type=int, nargs="*", default=HORIZONS)
    args = parser.parse_args()

    dataset = pd.read_csv(DATASET_PATH)
    dataset["reference_date"] = pd.to_datetime(dataset["reference_date"])
    features = dataset[["ticker", "reference_date", *V2_NO_SENTIMENT_FEATURE_COLUMNS]].copy()

    results = []
    for horizon in args.horizons:
        print(f"\n=== horizon={horizon}d ===", flush=True)
        horizon_frame, threshold = build_horizon_dataset(features, horizon)
        label_counts = horizon_frame["label"].value_counts().to_dict()
        print(f"  rows={len(horizon_frame)} threshold={threshold:.4f} label_counts={label_counts}", flush=True)

        for algo_name, factory in [
            ("random_forest", build_random_forest_pipeline),
            ("gradient_boosting", build_gradient_boosting_pipeline),
        ]:
            result = run_walk_forward(horizon_frame, V2_NO_SENTIMENT_FEATURE_COLUMNS, factory, purge_days=horizon)
            if "error" in result:
                print(f"  {algo_name}: SKIPPED ({result['error']})", flush=True)
                results.append({"horizon": horizon, "algorithm": algo_name, "threshold": threshold, "label_counts": label_counts, "error": result["error"]})
                continue

            print(f"  {algo_name}: macro_f1={result['mean_metrics']['f1_macro']:.4f} "
                  f"directional_accuracy={result['mean_metrics']['directional_accuracy']:.4f} "
                  f"folds={result['fold_count']}", flush=True)
            results.append({
                "horizon": horizon, "algorithm": algo_name, "threshold": round(threshold, 4),
                "label_counts": label_counts, "fold_count": result["fold_count"],
                "mean_metrics": result["mean_metrics"],
            })

    lines = [
        "Multi-Horizon Prediction Experiment (h+1 / h+3 / h+7 / h+30)",
        "===============================================================",
        "",
        "Technical-only features (matches V6A exactly), RandomForest vs GradientBoosting, walk-forward",
        f"with an explicit purge gap (= horizon trading days) between train and test to prevent label",
        f"leakage from overlapping forward-return windows. min_train_days={MIN_TRAIN_DAYS}, "
        f"test_window_days={TEST_WINDOW_DAYS}, max_folds={MAX_FOLDS}.",
        "Reference: production V6A (5-day horizon, no purge gap, RandomForest) = 37.0% macro-F1, "
        "40.2% directional accuracy on the full 10-ticker walk-forward set (different setup, not "
        "directly comparable -- shown for orientation only).",
        "",
    ]
    for r in results:
        if "error" in r:
            lines.append(f"h+{r['horizon']:<3d} {r['algorithm']:20s} SKIPPED: {r['error']}")
            continue
        m = r["mean_metrics"]
        lines.append(
            f"h+{r['horizon']:<3d} {r['algorithm']:20s} macro_f1={m['f1_macro']:.4f}  "
            f"directional_accuracy={m['directional_accuracy']:.4f}  "
            f"f1_up={m.get('f1_up', 0):.4f}  f1_down={m.get('f1_down', 0):.4f}  f1_flat={m.get('f1_flat', 0):.4f}  "
            f"folds={r['fold_count']}  threshold={r['threshold']}  labels={r['label_counts']}"
        )

    REPORT_TXT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    print("\n" + "\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
