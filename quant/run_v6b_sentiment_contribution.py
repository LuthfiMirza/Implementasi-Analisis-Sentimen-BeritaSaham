#!/usr/bin/env python3
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd

from train_prediction_models import (
    CLASS_ORDER,
    V2_ALL_FEATURE_COLUMNS,
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    build_folds,
    build_logistic_pipeline,
    build_random_forest_pipeline,
    evaluate_predictions,
    infer_class_labels,
    mean_metrics,
)

OUTPUT_DIR = Path("output/prediction_research")
DATASET_PATH = OUTPUT_DIR / "dataset_v6b_10ticker.csv"
REPORT_TXT_PATH = OUTPUT_DIR / "model_comparison_v6b.txt"
REPORT_JSON_PATH = OUTPUT_DIR / "model_comparison_v6b.json"

START_DATE = "2025-10-01"
END_DATE = "2026-04-15"
LABEL_COLUMN = "label_v2"
V6A_OFFICIAL_BASELINE = {"macro_f1": 0.3673, "directional_accuracy": 0.4050}
FULL_DATASET_LABEL_DISTRIBUTION = {"down": 0.356, "flat": 0.338, "up": 0.306}
WALK_FORWARD_SETTINGS = [
    {"min_train_days": 40, "test_window_days": 10},
    {"min_train_days": 60, "test_window_days": 10},
    {"min_train_days": 60, "test_window_days": 20},
]
SCENARIOS = [
    {"scenario_name": "technical_only", "feature_columns": V2_NO_SENTIMENT_FEATURE_COLUMNS},
    {"scenario_name": "technical_plus_sentiment", "feature_columns": V2_ALL_FEATURE_COLUMNS},
]


def build_estimators(feature_columns: list[str]) -> dict[str, object]:
    return {
        "logistic_regression": build_logistic_pipeline(feature_columns, class_weight="balanced"),
        "random_forest": build_random_forest_pipeline(feature_columns, class_weight="balanced_subsample"),
    }


def label_distribution(frame: pd.DataFrame) -> dict[str, object]:
    counts = frame[LABEL_COLUMN].value_counts().reindex(CLASS_ORDER, fill_value=0)
    total = int(counts.sum())
    return {
        "counts": {label: int(counts[label]) for label in CLASS_ORDER},
        "shares": {label: round(float(counts[label] / total), 6) if total else 0.0 for label in CLASS_ORDER},
        "total": total,
    }


def evaluate_setting(frame: pd.DataFrame, setting: dict[str, int], scenario: dict[str, object]) -> list[dict[str, object]]:
    feature_columns = list(scenario["feature_columns"])
    required_columns = ["reference_date", LABEL_COLUMN, *feature_columns]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise SystemExit(f"Missing required columns for {scenario['scenario_name']}: {missing}")

    unique_dates = sorted(frame["reference_date"].drop_duplicates().tolist())
    folds = build_folds(unique_dates, setting["min_train_days"], setting["test_window_days"])
    class_labels = infer_class_labels(frame[LABEL_COLUMN])
    rows: list[dict[str, object]] = []

    for algorithm, estimator_template in build_estimators(feature_columns).items():
        fold_metrics: list[dict[str, float]] = []
        fold_details: list[dict[str, object]] = []
        for fold_index, fold in enumerate(folds, start=1):
            train_df = frame[frame["reference_date"] <= fold.train_end].copy()
            test_df = frame[(frame["reference_date"] >= fold.test_start) & (frame["reference_date"] <= fold.test_end)].copy()
            if train_df.empty or test_df.empty:
                continue
            estimator = deepcopy(estimator_template)
            estimator.fit(train_df[feature_columns], train_df[LABEL_COLUMN])
            predictions = estimator.predict(test_df[feature_columns])
            metrics = evaluate_predictions(test_df[LABEL_COLUMN], predictions, class_labels)
            fold_metrics.append(metrics)
            fold_details.append(
                {
                    "fold_index": fold_index,
                    "train_end": str(fold.train_end.date()),
                    "test_start": str(fold.test_start.date()),
                    "test_end": str(fold.test_end.date()),
                    "train_rows": int(len(train_df)),
                    "test_rows": int(len(test_df)),
                    "metrics": metrics,
                }
            )

        if fold_metrics:
            aggregate = mean_metrics(fold_metrics)
            avg_train_rows = round(float(np.mean([fold["train_rows"] for fold in fold_details])), 2)
            avg_test_rows = round(float(np.mean([fold["test_rows"] for fold in fold_details])), 2)
        else:
            aggregate = {"f1_macro": 0.0, "directional_accuracy": 0.0, "accuracy": 0.0}
            avg_train_rows = 0.0
            avg_test_rows = 0.0

        rows.append(
            {
                "min_train_days": setting["min_train_days"],
                "test_window_days": setting["test_window_days"],
                "scenario": scenario["scenario_name"],
                "algorithm": algorithm,
                "f1_macro": aggregate.get("f1_macro", 0.0),
                "directional_accuracy": aggregate.get("directional_accuracy", 0.0),
                "fold_count": len(fold_details),
                "avg_train_rows": avg_train_rows,
                "avg_test_rows": avg_test_rows,
                "folds": fold_details,
                "limit_warning": "fold_count_below_3" if len(fold_details) < 3 else None,
            }
        )
    return rows


def compare_scenarios(results: list[dict[str, object]]) -> list[dict[str, object]]:
    comparisons: list[dict[str, object]] = []
    for setting in WALK_FORWARD_SETTINGS:
        for algorithm in ["logistic_regression", "random_forest"]:
            tech = next(
                row for row in results
                if row["min_train_days"] == setting["min_train_days"]
                and row["test_window_days"] == setting["test_window_days"]
                and row["algorithm"] == algorithm
                and row["scenario"] == "technical_only"
            )
            sent = next(
                row for row in results
                if row["min_train_days"] == setting["min_train_days"]
                and row["test_window_days"] == setting["test_window_days"]
                and row["algorithm"] == algorithm
                and row["scenario"] == "technical_plus_sentiment"
            )
            comparisons.append(
                {
                    "min_train_days": setting["min_train_days"],
                    "test_window_days": setting["test_window_days"],
                    "algorithm": algorithm,
                    "delta_f1_macro": round(float(sent["f1_macro"] - tech["f1_macro"]), 6),
                    "delta_directional_accuracy": round(float(sent["directional_accuracy"] - tech["directional_accuracy"]), 6),
                    "sentiment_wins_both_metrics": bool(sent["f1_macro"] > tech["f1_macro"] and sent["directional_accuracy"] > tech["directional_accuracy"]),
                }
            )
    return comparisons


def assessment(comparisons: list[dict[str, object]]) -> str:
    wins_both = sum(1 for row in comparisons if row["sentiment_wins_both_metrics"])
    f1_wins = sum(1 for row in comparisons if row["delta_f1_macro"] > 0)
    acc_wins = sum(1 for row in comparisons if row["delta_directional_accuracy"] > 0)
    if wins_both == len(comparisons):
        return "Sentiment improves both macro F1 and directional accuracy consistently across all settings and algorithms in this subset."
    if wins_both >= 4 and f1_wins >= 4 and acc_wins >= 4:
        return "Sentiment contribution is mostly positive, but not fully consistent across all settings and algorithms. Treat as promising but not definitive."
    if f1_wins >= 4 or acc_wins >= 4:
        return "Sentiment contribution is mixed: it helps one metric or some settings, but the evidence is not consistent enough to claim robust predictive lift."
    return "No consistent evidence that sentiment adds predictive signal in this subset under the fixed metric policy."


def format_pct(value: float) -> str:
    return f"{value:.4f}"


def write_reports(summary: dict[str, object]) -> None:
    REPORT_JSON_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "V6B Sentiment Contribution Study",
        "=================================",
        "",
        f"Dataset: {DATASET_PATH}",
        f"Subset: {START_DATE} to {END_DATE}",
        "Label: label_v2 (5D fixed threshold 1.5%)",
        "Models: logistic_regression, random_forest",
        "Metric policy: macro F1 primary, directional_accuracy secondary",
        "Governance: classification research only; no strategy/backtest/P&L metrics.",
        "",
        "Subset Label Distribution",
        "-------------------------",
        "label,count,share,full_dataset_reference_share",
    ]
    label_dist = summary["label_distribution"]
    for label in CLASS_ORDER:
        lines.append(
            f"{label},{label_dist['counts'][label]},{label_dist['shares'][label]:.4f},{FULL_DATASET_LABEL_DISTRIBUTION[label]:.4f}"
        )

    lines.extend([
        "",
        "Complete Results",
        "----------------",
        "min_train_days,test_window_days,scenario,algorithm,macro_f1,directional_accuracy,fold_count,avg_train_rows,avg_test_rows,limit_warning",
    ])
    for row in summary["results"]:
        lines.append(
            ",".join(
                [
                    str(row["min_train_days"]),
                    str(row["test_window_days"]),
                    str(row["scenario"]),
                    str(row["algorithm"]),
                    format_pct(float(row["f1_macro"])),
                    format_pct(float(row["directional_accuracy"])),
                    str(row["fold_count"]),
                    f"{float(row['avg_train_rows']):.2f}",
                    f"{float(row['avg_test_rows']):.2f}",
                    str(row["limit_warning"] or ""),
                ]
            )
        )

    lines.extend([
        "",
        "Technical + Sentiment vs Technical Only",
        "----------------------------------------",
        "min_train_days,test_window_days,algorithm,delta_macro_f1,delta_directional_accuracy,sentiment_wins_both_metrics",
    ])
    for row in summary["scenario_comparisons"]:
        lines.append(
            f"{row['min_train_days']},{row['test_window_days']},{row['algorithm']},{row['delta_f1_macro']:+.4f},{row['delta_directional_accuracy']:+.4f},{row['sentiment_wins_both_metrics']}"
        )

    lines.extend([
        "",
        "Subset Technical-Only vs V6A Official Baseline",
        "-----------------------------------------------",
        "V6A official baseline is full-period 25-year context and is not an apples-to-apples V6B comparator.",
        "It is included only to assess whether this 6-month subset behaves like a special market regime.",
        "scenario,algorithm,min_train_days,test_window_days,subset_macro_f1,subset_directional_accuracy,delta_macro_f1_vs_v6a,delta_directional_accuracy_vs_v6a",
    ])
    for row in summary["technical_vs_v6a"]:
        lines.append(
            f"technical_only,{row['algorithm']},{row['min_train_days']},{row['test_window_days']},{row['f1_macro']:.4f},{row['directional_accuracy']:.4f},{row['delta_f1_macro_vs_v6a']:+.4f},{row['delta_directional_accuracy_vs_v6a']:+.4f}"
        )

    lines.extend([
        "",
        "Assessment",
        "----------",
        str(summary["assessment"]),
        "",
    ])
    REPORT_TXT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    dataset = pd.read_csv(DATASET_PATH)
    dataset["reference_date"] = pd.to_datetime(dataset["reference_date"])
    subset = dataset[(dataset["reference_date"] >= START_DATE) & (dataset["reference_date"] <= END_DATE)].copy()
    if subset.empty:
        raise SystemExit("V6B subset is empty.")

    results: list[dict[str, object]] = []
    for setting in WALK_FORWARD_SETTINGS:
        for scenario in SCENARIOS:
            results.extend(evaluate_setting(subset, setting, scenario))

    comparisons = compare_scenarios(results)
    technical_vs_v6a = []
    for row in results:
        if row["scenario"] != "technical_only":
            continue
        technical_vs_v6a.append(
            {
                "algorithm": row["algorithm"],
                "min_train_days": row["min_train_days"],
                "test_window_days": row["test_window_days"],
                "f1_macro": row["f1_macro"],
                "directional_accuracy": row["directional_accuracy"],
                "delta_f1_macro_vs_v6a": round(float(row["f1_macro"] - V6A_OFFICIAL_BASELINE["macro_f1"]), 6),
                "delta_directional_accuracy_vs_v6a": round(float(row["directional_accuracy"] - V6A_OFFICIAL_BASELINE["directional_accuracy"]), 6),
            }
        )

    summary = {
        "dataset": str(DATASET_PATH),
        "subset_start_date": START_DATE,
        "subset_end_date": END_DATE,
        "row_count": int(len(subset)),
        "ticker_count": int(subset["ticker"].nunique()),
        "unique_trading_dates": int(subset["reference_date"].nunique()),
        "label_column": LABEL_COLUMN,
        "label_distribution": label_distribution(subset),
        "full_dataset_reference_label_distribution": FULL_DATASET_LABEL_DISTRIBUTION,
        "v6a_official_baseline": V6A_OFFICIAL_BASELINE,
        "walk_forward_settings": WALK_FORWARD_SETTINGS,
        "results": results,
        "scenario_comparisons": comparisons,
        "technical_vs_v6a": technical_vs_v6a,
        "assessment": assessment(comparisons),
    }
    write_reports(summary)
    print(json.dumps({"txt": str(REPORT_TXT_PATH), "json": str(REPORT_JSON_PATH), "rows": len(results)}, indent=2))


if __name__ == "__main__":
    main()
