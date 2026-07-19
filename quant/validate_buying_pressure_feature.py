#!/usr/bin/env python3
"""Walk-forward validation of the uncommitted 'buying_pressure' feature
(app/Services/Prediction/FeatureBuilderService.php + BaselinePredictionService.php).

The code comments there claim: "buying_pressure >= 0.55 -> up, <= 0.45 -> down
achieves ~59% directional accuracy vs ~50% baseline on held-out validation of
10 research tickers" -- but no supporting artifact exists anywhere in the repo.
This script reproduces that claim properly using this project's established
methodology (walk-forward OOS folds, RandomForest 5-seed, majority-class and
random baselines as comparators -- same pattern as train_prediction_models.py
and the Gap 1 sentiment experiments).

Two tests:
  (a) ML value-add: does adding buying_pressure to the existing technical
      feature set improve RandomForest accuracy on target_direction_5d?
  (b) Literal rule test: does the EXACT rule from the code (>=0.55 up,
      <=0.45 down, else flat) beat majority-class / random baselines
      out-of-sample?
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

from train_prediction_models import (
    CLASS_ORDER,
    MajorityClassModel,
    RandomBaselineModel,
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    build_folds,
    build_random_forest_pipeline,
    evaluate_predictions,
    infer_class_labels,
    mean_metrics,
)

DATASET_PATH = Path("output/prediction_research/window_experiment/dataset_full_w5.csv")
PRICE_DIR = Path("data/stocks")
OFFICIAL_TICKERS = ["BBCA", "BBRI", "BMRI", "TLKM", "ASII", "GOTO", "INDF", "ICBP", "ADRO", "UNVR"]
LABEL_COLUMN = "target_direction_5d"
SEEDS = [42, 7, 123, 2024, 99]
MIN_TRAIN_DAYS = 252
TEST_WINDOW_DAYS = 126
MAX_FOLDS = 8


def compute_buying_pressure(ticker: str) -> pd.DataFrame:
    """Replicates FeatureBuilderService::buyingPressure() exactly: trailing
    20-day ratio of up-day volume (raw close, not adjusted) to total volume."""
    path = PRICE_DIR / f"{ticker}.csv"
    prices = pd.read_csv(path)
    prices["date"] = pd.to_datetime(prices["date"])
    prices = prices.sort_values("date").reset_index(drop=True)

    close = prices["close"].astype(float).to_numpy()
    volume = prices["volume"].astype(float).to_numpy()
    n = len(prices)
    buying_pressure = np.full(n, np.nan)

    for i in range(1, n):
        window = min(20, i)
        start = i - window + 1
        up_volume = 0.0
        total_volume = 0.0
        for j in range(max(start, 1), i + 1):
            total_volume += volume[j]
            if close[j] > close[j - 1]:
                up_volume += volume[j]
        if total_volume > 0:
            buying_pressure[i] = round(up_volume / total_volume, 4)

    return pd.DataFrame({
        "ticker": ticker,
        "reference_date": prices["date"].dt.strftime("%Y-%m-%d"),
        "buying_pressure": buying_pressure,
    })


class BuyingPressureRuleModel:
    """Literal reproduction of the rule hardcoded in BaselinePredictionService."""

    def __init__(self) -> None:
        self.classes_ = np.array(CLASS_ORDER)

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "BuyingPressureRuleModel":
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        bp = x["buying_pressure"].to_numpy()
        predictions = np.full(len(bp), "flat", dtype=object)
        predictions[bp >= 0.55] = "up"
        predictions[bp <= 0.45] = "down"
        return predictions


def main() -> None:
    dataset = pd.read_csv(DATASET_PATH)
    dataset = dataset[dataset["ticker"].isin(OFFICIAL_TICKERS)].copy()
    dataset["reference_date"] = pd.to_datetime(dataset["reference_date"])

    bp_frames = [compute_buying_pressure(ticker) for ticker in OFFICIAL_TICKERS]
    bp_df = pd.concat(bp_frames, ignore_index=True)
    bp_df["reference_date"] = pd.to_datetime(bp_df["reference_date"])

    merged = dataset.merge(bp_df, on=["ticker", "reference_date"], how="left")
    merged = merged.dropna(subset=["buying_pressure", LABEL_COLUMN]).copy()
    print(f"Rows with buying_pressure available: {len(merged)}/{len(dataset)}")

    unique_dates = sorted(merged["reference_date"].drop_duplicates().tolist())
    folds = build_folds(unique_dates, MIN_TRAIN_DAYS, TEST_WINDOW_DAYS)[:MAX_FOLDS]
    class_labels = infer_class_labels(merged[LABEL_COLUMN])
    print(f"Walk-forward folds: {len(folds)}")

    # --- Test (a): ML value-add ---
    technical_only = list(V2_NO_SENTIMENT_FEATURE_COLUMNS)
    technical_plus_bp = technical_only + ["buying_pressure"]

    def run_rf_scenario(feature_columns: list[str]) -> dict[str, object]:
        seed_fold_metrics = []
        for seed in SEEDS:
            fold_metrics = []
            for fold in folds:
                train_df = merged[merged["reference_date"] <= fold.train_end]
                test_df = merged[(merged["reference_date"] >= fold.test_start) & (merged["reference_date"] <= fold.test_end)]
                if train_df.empty or test_df.empty:
                    continue
                estimator = deepcopy(build_random_forest_pipeline(feature_columns, class_weight="balanced_subsample"))
                estimator.set_params(model__random_state=seed)
                estimator.fit(train_df[feature_columns], train_df[LABEL_COLUMN])
                predictions = estimator.predict(test_df[feature_columns])
                fold_metrics.append(evaluate_predictions(test_df[LABEL_COLUMN], predictions, class_labels))
            if fold_metrics:
                seed_fold_metrics.append(mean_metrics(fold_metrics))
        f1_values = [m["f1_macro"] for m in seed_fold_metrics]
        acc_values = [m["directional_accuracy"] for m in seed_fold_metrics]
        return {
            "f1_macro_mean": round(float(np.mean(f1_values)), 4),
            "f1_macro_std": round(float(np.std(f1_values)), 4),
            "dir_acc_mean": round(float(np.mean(acc_values)), 4),
            "dir_acc_std": round(float(np.std(acc_values)), 4),
        }

    ml_technical_only = run_rf_scenario(technical_only)
    ml_with_bp = run_rf_scenario(technical_plus_bp)

    # --- Test (b): literal rule vs majority-class / random baselines, per fold OOS ---
    class_counts = merged[LABEL_COLUMN].value_counts(normalize=True).to_dict()
    rule_fold_metrics = []
    majority_fold_metrics = []
    random_fold_metrics = []
    per_fold_detail = []
    for fold_index, fold in enumerate(folds, start=1):
        train_df = merged[merged["reference_date"] <= fold.train_end]
        test_df = merged[(merged["reference_date"] >= fold.test_start) & (merged["reference_date"] <= fold.test_end)]
        if train_df.empty or test_df.empty:
            continue

        rule_model = BuyingPressureRuleModel()
        rule_pred = rule_model.predict(test_df)
        rule_metrics = evaluate_predictions(test_df[LABEL_COLUMN], rule_pred, class_labels)
        rule_fold_metrics.append(rule_metrics)

        majority_model = MajorityClassModel().fit(train_df, train_df[LABEL_COLUMN])
        majority_pred = majority_model.predict(test_df)
        majority_metrics = evaluate_predictions(test_df[LABEL_COLUMN], majority_pred, class_labels)
        majority_fold_metrics.append(majority_metrics)

        random_model = RandomBaselineModel(class_counts, class_labels, random_state=42)
        random_pred = random_model.predict(test_df)
        random_metrics = evaluate_predictions(test_df[LABEL_COLUMN], random_pred, class_labels)
        random_fold_metrics.append(random_metrics)

        per_fold_detail.append({
            "fold_index": fold_index,
            "test_start": str(fold.test_start.date()),
            "test_end": str(fold.test_end.date()),
            "test_rows": int(len(test_df)),
            "rule_dir_acc": round(rule_metrics["directional_accuracy"], 4),
            "majority_dir_acc": round(majority_metrics["directional_accuracy"], 4),
            "random_dir_acc": round(random_metrics["directional_accuracy"], 4),
            "rule_beats_majority": bool(rule_metrics["directional_accuracy"] > majority_metrics["directional_accuracy"]),
        })

    rule_agg = mean_metrics(rule_fold_metrics)
    majority_agg = mean_metrics(majority_fold_metrics)
    random_agg = mean_metrics(random_fold_metrics)
    folds_where_rule_wins = sum(1 for row in per_fold_detail if row["rule_beats_majority"])

    summary = {
        "official_tickers": OFFICIAL_TICKERS,
        "rows_with_buying_pressure": int(len(merged)),
        "fold_count": len(per_fold_detail),
        "test_a_ml_value_add_5seed_walkforward": {
            "technical_only": ml_technical_only,
            "technical_plus_buying_pressure": ml_with_bp,
            "delta_f1_macro": round(ml_with_bp["f1_macro_mean"] - ml_technical_only["f1_macro_mean"], 4),
            "delta_dir_acc": round(ml_with_bp["dir_acc_mean"] - ml_technical_only["dir_acc_mean"], 4),
        },
        "test_b_literal_rule_vs_baselines_walkforward_oos": {
            "rule_directional_accuracy": round(rule_agg["directional_accuracy"], 4),
            "majority_class_directional_accuracy": round(majority_agg["directional_accuracy"], 4),
            "random_baseline_directional_accuracy": round(random_agg["directional_accuracy"], 4),
            "claimed_in_code_comments": {"rule": 0.59, "baseline": 0.50},
            "folds_where_rule_beats_majority": f"{folds_where_rule_wins}/{len(per_fold_detail)}",
            "per_fold_detail": per_fold_detail,
        },
    }

    OUTPUT_DIR = Path("output/prediction_research")
    (OUTPUT_DIR / "buying_pressure_walkforward_validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
