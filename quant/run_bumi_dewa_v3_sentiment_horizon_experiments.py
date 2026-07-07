#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from run_volatile_v2_experiments import (
    EXTENDED_FEATURES,
    OLD_BASELINES,
    add_new_features,
    add_horizon_labels,
    baseline_models,
    build_fast_random_forest_pipeline,
    label_distribution,
    row_for_table,
    SoftVotingEnsemble,
    status_vs_majority,
)
from train_prediction_models import (
    RandomBaselineModel,
    MajorityClassModel,
    build_folds,
    build_logistic_pipeline,
    evaluate_predictions,
    infer_class_labels,
    mean_metrics,
)

OUTPUT_DIR = Path("output/prediction_research")

SENTIMENT_FEATURES = [
    "has_sentiment_data",
    "sentiment_average_5d",
    "weighted_sentiment_5d",
    "news_volume_5d",
    "sentiment_average_5d_x_regime",
    "weighted_sentiment_5d_x_regime",
    "sentiment_available_count_5d",
    "sentiment_unavailable_count_5d",
]
FULL_FEATURES = EXTENDED_FEATURES + SENTIMENT_FEATURES

GB_CONFIGS = {
    "gradient_boosting_default": {"max_iter": 60, "learning_rate": 0.08},
    "gradient_boosting_deeper_slower": {"max_iter": 120, "learning_rate": 0.05, "max_depth": 6},
    "gradient_boosting_shallow_fast": {"max_iter": 40, "learning_rate": 0.12, "max_depth": 3},
}

GOVERNANCE_NOTE = (
    "prediction research only; no strategy/P&L/trading recommendation; "
    "does not replace production artifacts trained by quant/train_volatile_stock_models.py"
)


def build_gb_pipeline(feature_columns: list[str], config_name: str) -> Pipeline:
    params = GB_CONFIGS[config_name]
    return Pipeline(
        steps=[
            ("preprocess", ColumnTransformer(transformers=[("num", SimpleImputer(strategy="median"), feature_columns)])),
            ("model", HistGradientBoostingClassifier(random_state=42, **params)),
        ]
    )


def make_model(name: str, feature_columns: list[str], class_probabilities: dict[object, float], class_labels: list[object]):
    if name in GB_CONFIGS:
        return build_gb_pipeline(feature_columns, name)
    if name == "logistic_regression":
        return build_logistic_pipeline(feature_columns, class_weight="balanced")
    if name == "random_forest":
        return build_fast_random_forest_pipeline(feature_columns)
    if name == "soft_voting_ensemble":
        return SoftVotingEnsemble(feature_columns, class_labels)
    if name == "random_baseline":
        return RandomBaselineModel(class_probabilities, class_labels)
    if name == "majority_class":
        return MajorityClassModel()
    raise ValueError(name)


def evaluate(frame: pd.DataFrame, label_column: str, feature_columns: list[str], algorithms: list[str]) -> dict[str, object]:
    required = ["reference_date", label_column, *feature_columns]
    eval_frame = frame[required].dropna().copy().sort_values("reference_date")
    class_labels = infer_class_labels(eval_frame[label_column])
    class_probabilities = eval_frame[label_column].value_counts(normalize=True).reindex(class_labels, fill_value=0).to_dict()
    unique_dates = sorted(eval_frame["reference_date"].drop_duplicates().tolist())
    folds = build_folds(unique_dates, min_train_days=252, test_window_days=126)[-8:]
    models = []
    for algorithm in algorithms:
        fold_metrics = []
        fold_rows = []
        for fold in folds:
            train_df = eval_frame[eval_frame["reference_date"] <= fold.train_end]
            test_df = eval_frame[(eval_frame["reference_date"] >= fold.test_start) & (eval_frame["reference_date"] <= fold.test_end)]
            estimator = make_model(algorithm, feature_columns, class_probabilities, class_labels)
            estimator.fit(train_df[feature_columns], train_df[label_column])
            predictions = estimator.predict(test_df[feature_columns])
            metrics = evaluate_predictions(test_df[label_column], predictions, class_labels)
            fold_metrics.append(metrics)
            fold_rows.append({"fold": asdict(fold), "train_rows": int(len(train_df)), "test_rows": int(len(test_df)), "metrics": metrics})
        models.append({"model_name": algorithm, "mean_metrics": mean_metrics(fold_metrics), "fold_metrics": fold_rows})
    models.sort(key=lambda row: (row["mean_metrics"].get("f1_macro", 0), row["mean_metrics"].get("directional_accuracy", 0)), reverse=True)
    return {
        "label_column": label_column,
        "feature_columns": feature_columns,
        "rows_after_dropna": int(len(eval_frame)),
        "fold_count": int(len(folds)),
        "label_distribution": label_distribution(eval_frame, label_column),
        "models": models,
        "best_model": models[0],
    }


def improvement_assessment(experiment: str, result: dict[str, object]) -> str:
    old = OLD_BASELINES.get(experiment)
    if not old:
        return "horizon alternative; no direct 5D baseline"
    best = result["best_model"]
    macro_delta = best["mean_metrics"]["f1_macro"] - old["macro_f1"]
    acc_delta = best["mean_metrics"]["directional_accuracy"] - old["directional_accuracy"]
    status = status_vs_majority(result)
    clear = (macro_delta > 0.02 or acc_delta > 0.02) and status.startswith("menang kedua")
    return f"{'clear_improvement' if clear else 'no_clear_improvement'}: delta_macro_f1={macro_delta:+.4f}, delta_directional_accuracy={acc_delta:+.4f}, {status}"


def sentiment_coverage_note(frame: pd.DataFrame) -> dict[str, object]:
    total = int(len(frame))
    covered = int(frame["has_sentiment_data"].fillna(0).astype(float).eq(1.0).sum())
    return {
        "total_rows": total,
        "rows_with_real_sentiment": covered,
        "coverage_pct": round(covered / total, 6) if total else 0.0,
    }


def load_sentiment_augmented_dataset(ticker: str) -> pd.DataFrame:
    special_path = OUTPUT_DIR / f"dataset_{ticker.lower()}_special.csv"
    sentiment_path = OUTPUT_DIR / f"dataset_{ticker.lower()}_with_sentiment.csv"
    frame = pd.read_csv(special_path, parse_dates=["reference_date"])
    sentiment = pd.read_csv(sentiment_path, parse_dates=["reference_date"])
    frame = frame.merge(sentiment[["reference_date", *SENTIMENT_FEATURES]], on="reference_date", how="left")
    frame[SENTIMENT_FEATURES] = frame[SENTIMENT_FEATURES].fillna(0.0)
    frame = add_new_features(frame)
    frame = add_horizon_labels(frame, ticker)
    return frame


def main() -> None:
    datasets = {"BUMI": load_sentiment_augmented_dataset("BUMI"), "DEWA": load_sentiment_augmented_dataset("DEWA")}
    coverage = {ticker: sentiment_coverage_note(frame) for ticker, frame in datasets.items()}

    algorithms_full = [
        "logistic_regression", "random_forest",
        "gradient_boosting_default", "gradient_boosting_deeper_slower", "gradient_boosting_shallow_fast",
        "soft_voting_ensemble", "random_baseline", "majority_class",
    ]
    algorithms_horizon = [
        "logistic_regression", "random_forest",
        "gradient_boosting_default", "gradient_boosting_deeper_slower", "gradient_boosting_shallow_fast",
        "random_baseline", "majority_class",
    ]

    results: dict[str, object] = {
        "methodology": {
            "walk_forward": "min_train_days=252, test_window_days=126, latest 8 folds (identical to run_volatile_v2_experiments.py)",
            "metrics": "macro F1 primary, directional_accuracy secondary",
            "sentiment_features": SENTIMENT_FEATURES,
            "gb_configs": GB_CONFIGS,
            "improvement_rule": "clear_improvement only if delta >0.02 macro F1 OR >0.02 directional accuracy vs official OLD_BASELINES AND learned model wins both metrics vs majority (same rule as v2)",
            "governance": GOVERNANCE_NOTE,
        },
        "sentiment_coverage": coverage,
        "experiments": [],
        "table": [],
    }

    five_day_specs = [
        ("BUMI", "bumi_fixed_2_7pct", "label_bumi_fixed_2_7pct"),
        ("DEWA", "dewa_atr0_5_h5d", "label_dewa_atr0_5_h5d"),
    ]
    for ticker, experiment, label_column in five_day_specs:
        frame = datasets[ticker]
        for scope, feature_columns in [
            ("v3_technical_only_gb_tuning", EXTENDED_FEATURES),
            ("v3_technical_plus_sentiment", FULL_FEATURES),
        ]:
            result = evaluate(frame, label_column, feature_columns, algorithms_full)
            results["experiments"].append({"scope": scope, "ticker": ticker, "experiment": experiment, "result": result})
            row = row_for_table(scope, ticker, experiment, result)
            row["assessment"] = improvement_assessment(experiment, result)
            results["table"].append(row)

    horizon_specs = [
        ("BUMI", "bumi_h3_fixed_scaled", "label_bumi_fixed_scaled_h3d"),
        ("BUMI", "bumi_h10_fixed_scaled", "label_bumi_fixed_scaled_h10d"),
        ("DEWA", "dewa_atr0_5_h3d", "label_dewa_atr0_5_h3d"),
        ("DEWA", "dewa_atr0_5_h10d", "label_dewa_atr0_5_h10d"),
    ]
    for ticker, experiment, label_column in horizon_specs:
        frame = datasets[ticker]
        result = evaluate(frame, label_column, FULL_FEATURES, algorithms_horizon)
        results["experiments"].append({"scope": "v3_horizon_technical_plus_sentiment", "ticker": ticker, "experiment": experiment, "result": result})
        row = row_for_table("v3_horizon_technical_plus_sentiment", ticker, experiment, result)
        row["assessment"] = improvement_assessment(experiment, result)
        results["table"].append(row)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "model_comparison_volatile_v3_sentiment_horizon.json"
    txt_path = OUTPUT_DIR / "model_comparison_volatile_v3_sentiment_horizon.txt"
    json_path.write_text(json.dumps(results, indent=2, default=str) + "\n")

    lines = [
        "Volatile Stock V3: GB Tuning + Sentiment + Horizon Experiments (BUMI/DEWA)",
        "==========================================================================",
        "",
        f"Scope: {GOVERNANCE_NOTE}",
        "Baseline comparator: OLD_BASELINES from run_volatile_v2_experiments.py (official model_comparison_*_special results).",
        "",
        "Sentiment coverage (rows where has_sentiment_data==1, i.e. real news that day):",
    ]
    for ticker, cov in coverage.items():
        lines.append(f"- {ticker}: {cov['rows_with_real_sentiment']}/{cov['total_rows']} rows ({cov['coverage_pct']:.2%}) have real sentiment; rest are no-news days (sentiment features = 0).")
    lines.extend([
        "",
        "scope,ticker,experiment,best_model,macro_f1,directional_accuracy,majority_macro_f1,majority_directional_accuracy,random_macro_f1,random_directional_accuracy,status_vs_majority,assessment",
    ])
    for row in results["table"]:
        lines.append(
            ",".join([
                row["scope"], row["ticker"], row["experiment"], row["best_model"],
                f"{row['macro_f1']:.4f}", f"{row['directional_accuracy']:.4f}",
                f"{row['majority_macro_f1']:.4f}", f"{row['majority_directional_accuracy']:.4f}",
                f"{row['random_macro_f1']:.4f}", f"{row['random_directional_accuracy']:.4f}",
                row["status_vs_majority"], row["assessment"],
            ])
        )

    clear = [row for row in results["table"] if str(row["assessment"]).startswith("clear_improvement")]
    lines.extend(["", "Assessment Summary", "------------------"])
    if clear:
        for row in clear:
            lines.append(f"- CLEAR: {row['scope']} {row['ticker']} {row['experiment']} -> {row['best_model']} macro_f1={row['macro_f1']:.4f}, directional_accuracy={row['directional_accuracy']:.4f}; {row['assessment']}")
    else:
        lines.append("- No v3 GB-tuning/sentiment experiment produced a clear improvement over official baselines under the predefined >0.02 rule.")
    lines.append("- Horizon (h3d/h10d) variants remain exploratory; no official 5D baseline to compare against.")
    txt_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {txt_path}")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
