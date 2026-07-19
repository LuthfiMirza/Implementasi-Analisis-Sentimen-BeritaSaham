#!/usr/bin/env python3
"""Fair-comparison multi-seed test: does widening the sentiment aggregation
window (5d -> 10d/20d) let sentiment features contribute to prediction
accuracy? Reuses the same narrowed subset (2024-08-01..2026-04-15, 10 official
tickers) and methodology established in the Gap 1 fair-comparison test:
- with/without sentiment cut to the identical row set (apples-to-apples)
- 5 random seeds for RandomForest to guard against single-seed noise
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from train_prediction_models import (
    CLASS_ORDER,
    V2_ALL_FEATURE_COLUMNS,
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    build_folds,
    evaluate_predictions,
    infer_class_labels,
    mean_metrics,
)

OUTPUT_DIR = Path("output/prediction_research/window_experiment")
DATASET_TEMPLATE = OUTPUT_DIR / "narrowed" / "dataset_narrowed_w{window}.csv"
REPORT_TXT_PATH = OUTPUT_DIR / "sentiment_window_experiment.txt"
REPORT_JSON_PATH = OUTPUT_DIR / "sentiment_window_experiment.json"

LABEL_COLUMN = "target_direction_5d"
WINDOWS = [5, 10, 20]
SEEDS = [42, 7, 123, 2024, 99]
MIN_TRAIN_DAYS = 252
TEST_WINDOW_DAYS = 126

SCENARIOS = [
    {"scenario_name": "without_sentiment", "feature_columns": V2_NO_SENTIMENT_FEATURE_COLUMNS},
    {"scenario_name": "with_sentiment", "feature_columns": V2_ALL_FEATURE_COLUMNS},
]


def build_logistic_pipeline(feature_columns: list[str], seed: int) -> Pipeline:
    return Pipeline(steps=[
        ("preprocess", ColumnTransformer(transformers=[
            ("num", Pipeline(steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ]), feature_columns),
        ])),
        ("model", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)),
    ])


def build_random_forest_pipeline(feature_columns: list[str], seed: int) -> Pipeline:
    return Pipeline(steps=[
        ("preprocess", ColumnTransformer(transformers=[
            ("num", SimpleImputer(strategy="median"), feature_columns),
        ])),
        ("model", RandomForestClassifier(
            n_estimators=160, max_depth=8, min_samples_leaf=20,
            class_weight="balanced_subsample", random_state=seed, n_jobs=-1,
        )),
    ])


def run_seed(frame: pd.DataFrame, feature_columns: list[str], seed: int, algorithm: str) -> dict[str, object] | None:
    unique_dates = sorted(frame["reference_date"].drop_duplicates().tolist())
    folds = build_folds(unique_dates, MIN_TRAIN_DAYS, TEST_WINDOW_DAYS)
    class_labels = infer_class_labels(frame[LABEL_COLUMN])
    fold_metrics: list[dict[str, float]] = []

    builder = build_random_forest_pipeline if algorithm == "random_forest" else build_logistic_pipeline
    for fold in folds:
        train_df = frame[frame["reference_date"] <= fold.train_end].copy()
        test_df = frame[(frame["reference_date"] >= fold.test_start) & (frame["reference_date"] <= fold.test_end)].copy()
        if train_df.empty or test_df.empty:
            continue
        estimator = deepcopy(builder(feature_columns, seed))
        estimator.fit(train_df[feature_columns], train_df[LABEL_COLUMN])
        predictions = estimator.predict(test_df[feature_columns])
        fold_metrics.append(evaluate_predictions(test_df[LABEL_COLUMN], predictions, class_labels))

    if not fold_metrics:
        return None
    return {"fold_count": len(fold_metrics), **mean_metrics(fold_metrics)}


def main() -> None:
    all_results = []
    for window in WINDOWS:
        dataset_path = Path(str(DATASET_TEMPLATE).format(window=window))
        frame = pd.read_csv(dataset_path)
        frame["reference_date"] = pd.to_datetime(frame["reference_date"])

        for scenario in SCENARIOS:
            for algorithm in ["logistic_regression", "random_forest"]:
                seeds_to_run = SEEDS if algorithm == "random_forest" else SEEDS[:1]
                seed_runs = []
                for seed in seeds_to_run:
                    result = run_seed(frame, scenario["feature_columns"], seed, algorithm)
                    if result is not None:
                        seed_runs.append(result)

                if not seed_runs:
                    continue

                f1_values = [r["f1_macro"] for r in seed_runs]
                acc_values = [r["directional_accuracy"] for r in seed_runs]
                all_results.append({
                    "window_days": window,
                    "scenario": scenario["scenario_name"],
                    "algorithm": algorithm,
                    "seeds_run": len(seed_runs),
                    "fold_count": seed_runs[0]["fold_count"],
                    "f1_macro_mean": round(float(np.mean(f1_values)), 4),
                    "f1_macro_std": round(float(np.std(f1_values)), 4),
                    "directional_accuracy_mean": round(float(np.mean(acc_values)), 4),
                    "directional_accuracy_std": round(float(np.std(acc_values)), 4),
                })

    comparisons = []
    for window in WINDOWS:
        for algorithm in ["logistic_regression", "random_forest"]:
            without = next((r for r in all_results if r["window_days"] == window and r["algorithm"] == algorithm and r["scenario"] == "without_sentiment"), None)
            with_ = next((r for r in all_results if r["window_days"] == window and r["algorithm"] == algorithm and r["scenario"] == "with_sentiment"), None)
            if without is None or with_ is None:
                continue
            comparisons.append({
                "window_days": window,
                "algorithm": algorithm,
                "delta_f1_macro": round(with_["f1_macro_mean"] - without["f1_macro_mean"], 4),
                "delta_directional_accuracy": round(with_["directional_accuracy_mean"] - without["directional_accuracy_mean"], 4),
                "with_sentiment_f1_macro": with_["f1_macro_mean"],
                "without_sentiment_f1_macro": without["f1_macro_mean"],
                "with_sentiment_dir_acc": with_["directional_accuracy_mean"],
                "without_sentiment_dir_acc": without["directional_accuracy_mean"],
            })

    summary = {
        "label_column": LABEL_COLUMN,
        "windows_tested": WINDOWS,
        "seeds": SEEDS,
        "min_train_days": MIN_TRAIN_DAYS,
        "test_window_days": TEST_WINDOW_DAYS,
        "results": all_results,
        "comparisons": comparisons,
    }
    REPORT_JSON_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = ["Sentiment Window Experiment (5d vs 10d vs 20d)", "=" * 48, ""]
    lines.append("window_days,scenario,algorithm,seeds_run,fold_count,f1_macro_mean,f1_macro_std,dir_acc_mean,dir_acc_std")
    for row in all_results:
        lines.append(f"{row['window_days']},{row['scenario']},{row['algorithm']},{row['seeds_run']},{row['fold_count']},{row['f1_macro_mean']:.4f},{row['f1_macro_std']:.4f},{row['directional_accuracy_mean']:.4f},{row['directional_accuracy_std']:.4f}")
    lines.append("")
    lines.append("With vs Without Sentiment (delta, positive = sentiment helps)")
    lines.append("window_days,algorithm,delta_f1_macro,delta_directional_accuracy,with_f1,without_f1,with_dir_acc,without_dir_acc")
    for row in comparisons:
        lines.append(f"{row['window_days']},{row['algorithm']},{row['delta_f1_macro']:+.4f},{row['delta_directional_accuracy']:+.4f},{row['with_sentiment_f1_macro']:.4f},{row['without_sentiment_f1_macro']:.4f},{row['with_sentiment_dir_acc']:.4f},{row['without_sentiment_dir_acc']:.4f}")
    REPORT_TXT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
