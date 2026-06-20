#!/usr/bin/env python3
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from train_prediction_models import (
    V2_ALL_FEATURE_COLUMNS,
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    build_folds,
    evaluate_predictions,
    infer_class_labels,
    mean_metrics,
)

OUTPUT_DIR = Path("output/prediction_research")
DATASET_PATH = OUTPUT_DIR / "dataset_v6b_10ticker.csv"
REPORT_TXT_PATH = OUTPUT_DIR / "model_comparison_v6b_rf_tuning.txt"
REPORT_JSON_PATH = OUTPUT_DIR / "model_comparison_v6b_rf_tuning.json"

START_DATE = "2025-10-01"
END_DATE = "2026-04-15"
LABEL_COLUMN = "label_v2"
WALK_FORWARD_SETTINGS = [
    {"min_train_days": 40, "test_window_days": 10},
    {"min_train_days": 60, "test_window_days": 10},
    {"min_train_days": 60, "test_window_days": 20},
]
SCENARIOS = [
    {"scenario_name": "technical_only", "feature_columns": V2_NO_SENTIMENT_FEATURE_COLUMNS},
    {"scenario_name": "technical_plus_sentiment", "feature_columns": V2_ALL_FEATURE_COLUMNS},
]
RF_VARIANTS = [
    {"variant": "original_depth8_leaf20_trees160", "n_estimators": 160, "max_depth": 8, "min_samples_leaf": 20},
    {"variant": "simple_depth4_leaf40_trees160", "n_estimators": 160, "max_depth": 4, "min_samples_leaf": 40},
    {"variant": "simple_depth5_leaf30_trees160", "n_estimators": 160, "max_depth": 5, "min_samples_leaf": 30},
    {"variant": "simple_depth5_leaf30_trees50", "n_estimators": 50, "max_depth": 5, "min_samples_leaf": 30},
]


def build_rf_pipeline(feature_columns: list[str], params: dict[str, object]) -> Pipeline:
    return Pipeline(
        steps=[
            (
                "preprocess",
                ColumnTransformer(transformers=[("num", SimpleImputer(strategy="median"), feature_columns)]),
            ),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=int(params["n_estimators"]),
                    max_depth=int(params["max_depth"]),
                    min_samples_leaf=int(params["min_samples_leaf"]),
                    class_weight="balanced_subsample",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def evaluate_variant(frame: pd.DataFrame, variant: dict[str, object], setting: dict[str, int], scenario: dict[str, object]) -> dict[str, object]:
    feature_columns = list(scenario["feature_columns"])
    required_columns = ["reference_date", LABEL_COLUMN, *feature_columns]
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise SystemExit(f"Missing required columns for {scenario['scenario_name']}: {missing}")

    folds = build_folds(sorted(frame["reference_date"].drop_duplicates().tolist()), setting["min_train_days"], setting["test_window_days"])
    class_labels = infer_class_labels(frame[LABEL_COLUMN])
    estimator_template = build_rf_pipeline(feature_columns, variant)
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

    aggregate = mean_metrics(fold_metrics) if fold_metrics else {"f1_macro": 0.0, "directional_accuracy": 0.0}
    return {
        "variant": variant["variant"],
        "n_estimators": variant["n_estimators"],
        "max_depth": variant["max_depth"],
        "min_samples_leaf": variant["min_samples_leaf"],
        "min_train_days": setting["min_train_days"],
        "test_window_days": setting["test_window_days"],
        "scenario": scenario["scenario_name"],
        "algorithm": "random_forest",
        "f1_macro": aggregate.get("f1_macro", 0.0),
        "directional_accuracy": aggregate.get("directional_accuracy", 0.0),
        "fold_count": len(fold_details),
        "avg_train_rows": round(float(np.mean([fold["train_rows"] for fold in fold_details])), 2) if fold_details else 0.0,
        "avg_test_rows": round(float(np.mean([fold["test_rows"] for fold in fold_details])), 2) if fold_details else 0.0,
        "limit_warning": "fold_count_below_3" if len(fold_details) < 3 else None,
        "folds": fold_details,
    }


def build_lift_table(results: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for variant in RF_VARIANTS:
        for setting in WALK_FORWARD_SETTINGS:
            tech = next(
                row for row in results
                if row["variant"] == variant["variant"]
                and row["min_train_days"] == setting["min_train_days"]
                and row["test_window_days"] == setting["test_window_days"]
                and row["scenario"] == "technical_only"
            )
            sent = next(
                row for row in results
                if row["variant"] == variant["variant"]
                and row["min_train_days"] == setting["min_train_days"]
                and row["test_window_days"] == setting["test_window_days"]
                and row["scenario"] == "technical_plus_sentiment"
            )
            rows.append(
                {
                    "variant": variant["variant"],
                    "min_train_days": setting["min_train_days"],
                    "test_window_days": setting["test_window_days"],
                    "delta_f1_macro": round(float(sent["f1_macro"] - tech["f1_macro"]), 6),
                    "delta_directional_accuracy": round(float(sent["directional_accuracy"] - tech["directional_accuracy"]), 6),
                    "sentiment_wins_both_metrics": bool(sent["f1_macro"] > tech["f1_macro"] and sent["directional_accuracy"] > tech["directional_accuracy"]),
                }
            )
    return rows


def summarize_variants(results: list[dict[str, object]], lift_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    original_results = [row for row in results if row["variant"] == "original_depth8_leaf20_trees160"]
    original_mean_f1 = float(np.mean([row["f1_macro"] for row in original_results]))
    original_mean_acc = float(np.mean([row["directional_accuracy"] for row in original_results]))
    for variant in RF_VARIANTS:
        variant_results = [row for row in results if row["variant"] == variant["variant"]]
        variant_lifts = [row for row in lift_rows if row["variant"] == variant["variant"]]
        summaries.append(
            {
                "variant": variant["variant"],
                "sentiment_wins_both_count": sum(1 for row in variant_lifts if row["sentiment_wins_both_metrics"]),
                "sentiment_f1_win_count": sum(1 for row in variant_lifts if row["delta_f1_macro"] > 0),
                "sentiment_accuracy_win_count": sum(1 for row in variant_lifts if row["delta_directional_accuracy"] > 0),
                "mean_f1_macro_all_rows": round(float(np.mean([row["f1_macro"] for row in variant_results])), 6),
                "mean_directional_accuracy_all_rows": round(float(np.mean([row["directional_accuracy"] for row in variant_results])), 6),
                "delta_mean_f1_vs_original": round(float(np.mean([row["f1_macro"] for row in variant_results]) - original_mean_f1), 6),
                "delta_mean_accuracy_vs_original": round(float(np.mean([row["directional_accuracy"] for row in variant_results]) - original_mean_acc), 6),
            }
        )
    return summaries


def assess(summaries: list[dict[str, object]]) -> str:
    simple = [row for row in summaries if row["variant"] != "original_depth8_leaf20_trees160"]
    candidates = [
        row for row in simple
        if row["sentiment_wins_both_count"] >= 2
        and row["delta_mean_f1_vs_original"] >= -0.02
        and row["delta_mean_accuracy_vs_original"] >= -0.02
    ]
    if candidates:
        best = sorted(candidates, key=lambda row: (row["sentiment_wins_both_count"], row["mean_f1_macro_all_rows"], row["mean_directional_accuracy_all_rows"]), reverse=True)[0]
        return (
            "Overfitting hypothesis is partially supported: at least one simpler RF variant makes sentiment lift more consistent "
            f"without a large aggregate metric penalty. Best candidate: {best['variant']}."
        )
    if any(row["sentiment_wins_both_count"] >= 2 for row in simple):
        return "Results are mixed: some simpler variants improve sentiment-lift consistency, but with enough metric trade-off that replacement is not clearly justified."
    return "Overfitting hypothesis is not supported by this tuning pass: simpler RF variants do not make sentiment lift consistently stronger."


def write_reports(summary: dict[str, object]) -> None:
    REPORT_JSON_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "V6B Random Forest Complexity Follow-up",
        "=======================================",
        "",
        f"Dataset: {DATASET_PATH}",
        f"Subset: {START_DATE} to {END_DATE}",
        "Label: label_v2 (5D fixed threshold 1.5%)",
        "Scope: random_forest parameter comparison only; V6B main report is unchanged.",
        "",
        "Variant Summary",
        "---------------",
        "variant,sentiment_wins_both_count,sentiment_f1_win_count,sentiment_accuracy_win_count,mean_macro_f1,mean_directional_accuracy,delta_mean_f1_vs_original,delta_mean_accuracy_vs_original",
    ]
    for row in summary["variant_summaries"]:
        lines.append(
            f"{row['variant']},{row['sentiment_wins_both_count']},{row['sentiment_f1_win_count']},{row['sentiment_accuracy_win_count']},{row['mean_f1_macro_all_rows']:.4f},{row['mean_directional_accuracy_all_rows']:.4f},{row['delta_mean_f1_vs_original']:+.4f},{row['delta_mean_accuracy_vs_original']:+.4f}"
        )

    lines.extend([
        "",
        "Complete Results",
        "----------------",
        "variant,min_train_days,test_window_days,scenario,macro_f1,directional_accuracy,fold_count,avg_train_rows,avg_test_rows,params",
    ])
    for row in summary["results"]:
        params = f"trees={row['n_estimators']};depth={row['max_depth']};leaf={row['min_samples_leaf']}"
        lines.append(
            f"{row['variant']},{row['min_train_days']},{row['test_window_days']},{row['scenario']},{row['f1_macro']:.4f},{row['directional_accuracy']:.4f},{row['fold_count']},{row['avg_train_rows']:.2f},{row['avg_test_rows']:.2f},{params}"
        )

    lines.extend([
        "",
        "Sentiment Lift",
        "--------------",
        "variant,min_train_days,test_window_days,delta_macro_f1,delta_directional_accuracy,sentiment_wins_both_metrics",
    ])
    for row in summary["sentiment_lift"]:
        lines.append(
            f"{row['variant']},{row['min_train_days']},{row['test_window_days']},{row['delta_f1_macro']:+.4f},{row['delta_directional_accuracy']:+.4f},{row['sentiment_wins_both_metrics']}"
        )

    lines.extend([
        "",
        "Assessment",
        "----------",
        str(summary["assessment"]),
        "",
        "Recommendation",
        "--------------",
        str(summary["recommendation"]),
        "",
    ])
    REPORT_TXT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    dataset = pd.read_csv(DATASET_PATH)
    dataset["reference_date"] = pd.to_datetime(dataset["reference_date"])
    subset = dataset[(dataset["reference_date"] >= START_DATE) & (dataset["reference_date"] <= END_DATE)].copy()
    results: list[dict[str, object]] = []
    for variant in RF_VARIANTS:
        for setting in WALK_FORWARD_SETTINGS:
            for scenario in SCENARIOS:
                results.append(evaluate_variant(subset, variant, setting, scenario))

    lift_rows = build_lift_table(results)
    variant_summaries = summarize_variants(results, lift_rows)
    assessment = assess(variant_summaries)
    best_candidates = [
        row for row in variant_summaries
        if row["variant"] != "original_depth8_leaf20_trees160"
        and row["sentiment_wins_both_count"] >= 2
        and row["delta_mean_f1_vs_original"] >= -0.02
        and row["delta_mean_accuracy_vs_original"] >= -0.02
    ]
    if best_candidates:
        best = sorted(best_candidates, key=lambda row: (row["sentiment_wins_both_count"], row["mean_f1_macro_all_rows"], row["mean_directional_accuracy_all_rows"]), reverse=True)[0]
        recommendation = f"Use {best['variant']} as the RF candidate for any V6B robustness follow-up; keep original V6B report unchanged."
    else:
        recommendation = "Do not replace the original RF setting based on this small tuning pass; report logistic regression as the more stable sentiment-contribution evidence."

    summary = {
        "dataset": str(DATASET_PATH),
        "subset_start_date": START_DATE,
        "subset_end_date": END_DATE,
        "row_count": int(len(subset)),
        "ticker_count": int(subset["ticker"].nunique()),
        "unique_trading_dates": int(subset["reference_date"].nunique()),
        "variants": RF_VARIANTS,
        "walk_forward_settings": WALK_FORWARD_SETTINGS,
        "results": results,
        "sentiment_lift": lift_rows,
        "variant_summaries": variant_summaries,
        "assessment": assessment,
        "recommendation": recommendation,
    }
    write_reports(summary)
    print(json.dumps({"txt": str(REPORT_TXT_PATH), "json": str(REPORT_JSON_PATH), "rows": len(results)}, indent=2))


if __name__ == "__main__":
    main()
