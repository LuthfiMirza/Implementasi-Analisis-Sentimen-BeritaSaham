#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

V1_ALL_FEATURE_COLUMNS = [
    "return_5d",
    "return_20d",
    "atr14_pct",
    "volume_ratio_20d",
    "price_vs_ema50",
    "market_regime_bullish",
    "has_sentiment_data",
    "sentiment_average_5d",
    "weighted_sentiment_5d",
    "news_volume_5d",
    "sentiment_average_5d_x_regime",
    "weighted_sentiment_5d_x_regime",
]

V1_NO_SENTIMENT_FEATURE_COLUMNS = [
    "return_5d",
    "return_20d",
    "atr14_pct",
    "volume_ratio_20d",
    "price_vs_ema50",
    "market_regime_bullish",
]

V2_ALL_FEATURE_COLUMNS = [
    "return_1d",
    "return_3d",
    "return_5d",
    "return_20d",
    "atr14_pct",
    "atr_ratio",
    "volume_ratio_5d",
    "volume_ratio_20d",
    "price_vs_ema20_pct",
    "price_vs_ema50",
    "rsi_slope_5d",
    "return_5d_cross_section_rank",
    "volume_spike_flag",
    "market_regime_bullish",
    "regime_duration",
    "has_sentiment_data",
    "sentiment_average_5d",
    "weighted_sentiment_5d",
    "news_volume_5d",
    "sentiment_average_5d_x_regime",
    "weighted_sentiment_5d_x_regime",
]

V2_NO_SENTIMENT_FEATURE_COLUMNS = [
    "return_1d",
    "return_3d",
    "return_5d",
    "return_20d",
    "atr14_pct",
    "atr_ratio",
    "volume_ratio_5d",
    "volume_ratio_20d",
    "price_vs_ema20_pct",
    "price_vs_ema50",
    "rsi_slope_5d",
    "return_5d_cross_section_rank",
    "volume_spike_flag",
    "market_regime_bullish",
    "regime_duration",
]

CLASS_ORDER = ["down", "flat", "up"]


@dataclass
class FoldWindow:
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


class MajorityClassModel:
    def __init__(self) -> None:
        self.majority_class_: object | None = None
        self.classes_ = np.array([])

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "MajorityClassModel":
        self.majority_class_ = y.mode().iloc[0]
        self.classes_ = np.array(pd.Series(y).drop_duplicates().tolist())
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        if self.majority_class_ is None:
            raise RuntimeError("Model is not fitted.")
        return np.repeat(self.majority_class_, len(x))

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        if self.majority_class_ is None:
            raise RuntimeError("Model is not fitted.")
        classes = self.classes_.tolist()
        probs = np.zeros((len(x), len(classes)), dtype=float)
        probs[:, classes.index(self.majority_class_)] = 1.0
        return probs


class RandomBaselineModel:
    def __init__(self, class_probabilities: dict[object, float], class_labels: list[object], random_state: int = 42) -> None:
        self.class_probabilities = class_probabilities
        self.class_labels = class_labels
        self.random_state = random_state
        self.classes_ = np.array(class_labels)

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "RandomBaselineModel":
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        probs = [self.class_probabilities[label] for label in self.class_labels]
        rng = np.random.default_rng(self.random_state)
        return rng.choice(self.class_labels, size=len(x), p=probs)

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        probs = np.array([self.class_probabilities[label] for label in self.class_labels], dtype=float)
        return np.tile(probs, (len(x), 1))


def parse_class_weight(value: str) -> str | None:
    return None if value == "none" else value


def build_logistic_pipeline(feature_columns: list[str], class_weight: str | None = "balanced") -> Pipeline:
    return Pipeline(
        steps=[
            (
                "preprocess",
                ColumnTransformer(
                    transformers=[
                        (
                            "num",
                            Pipeline(
                                steps=[
                                    ("imputer", SimpleImputer(strategy="median")),
                                    ("scaler", StandardScaler()),
                                ]
                            ),
                            feature_columns,
                        )
                    ]
                ),
            ),
            (
                "model",
                LogisticRegression(
                    max_iter=2000,
                    class_weight=class_weight,
                    random_state=42,
                ),
            ),
        ]
    )


def build_random_forest_pipeline(feature_columns: list[str], class_weight: str | None = "balanced_subsample") -> Pipeline:
    return Pipeline(
        steps=[
            (
                "preprocess",
                ColumnTransformer(
                    transformers=[
                        ("num", SimpleImputer(strategy="median"), feature_columns),
                    ]
                ),
            ),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=160,
                    max_depth=8,
                    min_samples_leaf=20,
                    class_weight=class_weight,
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train walk-forward prediction models for the Laravel research pipeline.")
    parser.add_argument("--dataset", default="output/prediction_research/dataset.csv")
    parser.add_argument("--model-dir", default="storage/app/prediction")
    parser.add_argument("--metrics-json", default="output/prediction_research/model_comparison.json")
    parser.add_argument("--metrics-txt", default="output/prediction_research/model_comparison.txt")
    parser.add_argument("--label-column", default="target_direction_5d")
    parser.add_argument("--feature-set", choices=["v1", "v2"], default="v1")
    parser.add_argument("--scenario-filter", choices=["all", "with_sentiment", "without_sentiment"], default="all")
    parser.add_argument("--logistic-class-weight", choices=["none", "balanced"], default="balanced")
    parser.add_argument("--random-forest-class-weight", choices=["none", "balanced", "balanced_subsample"], default="balanced_subsample")
    parser.add_argument("--positive-label")
    parser.add_argument("--selection-metric", default="directional_accuracy")
    parser.add_argument("--sentiment-start-date")
    parser.add_argument("--min-train-days", type=int, default=252)
    parser.add_argument("--test-window-days", type=int, default=126)
    parser.add_argument("--max-folds", type=int, default=8)
    return parser.parse_args()


def build_folds(unique_dates: list[pd.Timestamp], min_train_days: int, test_window_days: int) -> list[FoldWindow]:
    folds: list[FoldWindow] = []
    train_end_idx = min_train_days - 1
    while train_end_idx + test_window_days < len(unique_dates):
        train_end = unique_dates[train_end_idx]
        test_dates = unique_dates[train_end_idx + 1 : train_end_idx + 1 + test_window_days]
        if not test_dates:
            break
        folds.append(FoldWindow(train_end=train_end, test_start=test_dates[0], test_end=test_dates[-1]))
        train_end_idx += test_window_days
    return folds


def metric_key(label: object) -> str:
    return str(label).strip().lower().replace(" ", "_")


def infer_class_labels(values: pd.Series) -> list[object]:
    unique_values = values.dropna().drop_duplicates().tolist()
    if not unique_values:
        return []

    if all(isinstance(value, str) for value in unique_values):
        ordered = [label for label in CLASS_ORDER if label in unique_values]
        remaining = sorted([label for label in unique_values if label not in ordered], key=lambda value: str(value))
        return ordered + remaining

    return sorted(unique_values)


def metric_value(row: dict[str, object], selection_metric: str) -> float:
    return float(row["mean_metrics"].get(selection_metric, float("-inf")))


def evaluate_predictions(
    y_true: pd.Series,
    y_pred: np.ndarray,
    class_labels: list[object],
    positive_label: object | None = None,
) -> dict[str, float]:
    metrics: dict[str, float] = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "directional_accuracy": float(accuracy_score(y_true, y_pred)),
    }
    precision, recall, f1_values, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=class_labels,
        zero_division=0,
    )
    for index, label in enumerate(class_labels):
        key = metric_key(label)
        metrics[f"precision_{key}"] = float(precision[index])
        metrics[f"recall_{key}"] = float(recall[index])
        metrics[f"f1_{key}"] = float(f1_values[index])

    metrics["f1_macro"] = float(f1_score(y_true, y_pred, labels=class_labels, average="macro", zero_division=0))

    if positive_label is not None:
        positive_key = metric_key(positive_label)
        metrics["precision_positive"] = metrics.get(f"precision_{positive_key}", 0.0)
        metrics["recall_positive"] = metrics.get(f"recall_{positive_key}", 0.0)
        metrics["f1_positive"] = metrics.get(f"f1_{positive_key}", 0.0)

    return metrics


def mean_metrics(metrics: list[dict[str, float]]) -> dict[str, float]:
    keys = metrics[0].keys()
    return {key: round(float(np.mean([row[key] for row in metrics])), 6) for key in keys}


def model_factories(
    class_probabilities: dict[object, float],
    class_labels: list[object],
    logistic_class_weight: str | None,
    random_forest_class_weight: str | None,
) -> dict[str, Callable[[list[str]], object]]:
    return {
        "majority_class": lambda _feature_columns: MajorityClassModel(),
        "random_baseline": lambda _feature_columns: RandomBaselineModel(
            class_probabilities=class_probabilities,
            class_labels=class_labels,
        ),
        "logistic_regression": lambda feature_columns: build_logistic_pipeline(
            feature_columns,
            class_weight=logistic_class_weight,
        ),
        "random_forest": lambda feature_columns: build_random_forest_pipeline(
            feature_columns,
            class_weight=random_forest_class_weight,
        ),
    }


def build_scenarios(feature_set: str, scenario_filter: str) -> list[dict[str, object]]:
    if feature_set == "v2":
        scenarios = [
            {"scenario_name": "with_sentiment", "feature_columns": V2_ALL_FEATURE_COLUMNS},
            {"scenario_name": "without_sentiment", "feature_columns": V2_NO_SENTIMENT_FEATURE_COLUMNS},
        ]
    else:
        scenarios = [
            {"scenario_name": "with_sentiment", "feature_columns": V1_ALL_FEATURE_COLUMNS},
            {"scenario_name": "without_sentiment", "feature_columns": V1_NO_SENTIMENT_FEATURE_COLUMNS},
        ]

    if scenario_filter == "all":
        return scenarios

    return [scenario for scenario in scenarios if scenario["scenario_name"] == scenario_filter]


def extract_model_insights(fitted_model: object, feature_columns: list[str], top_n: int = 10) -> dict[str, object]:
    model = fitted_model
    if isinstance(fitted_model, Pipeline):
        model = fitted_model.named_steps["model"]

    if hasattr(model, "coef_"):
        coef = np.abs(np.asarray(model.coef_)).mean(axis=0)
        ranking = sorted(zip(feature_columns, coef.tolist()), key=lambda item: item[1], reverse=True)
        return {"type": "coefficients", "top_features": ranking[:top_n]}

    if hasattr(model, "feature_importances_"):
        importance = np.asarray(model.feature_importances_)
        ranking = sorted(zip(feature_columns, importance.tolist()), key=lambda item: item[1], reverse=True)
        return {"type": "feature_importances", "top_features": ranking[:top_n]}

    return {"type": "none", "top_features": []}


def summarize_confusion_matrix(y_true: list[object], y_pred: list[object], class_labels: list[object]) -> dict[str, object]:
    matrix = confusion_matrix(y_true, y_pred, labels=class_labels)
    row_percent = []
    for row in matrix:
        total = int(np.sum(row))
        if total == 0:
            row_percent.append([0.0 for _ in class_labels])
            continue
        row_percent.append([round(float(value / total), 6) for value in row])

    return {
        "labels": [str(label) for label in class_labels],
        "counts": matrix.tolist(),
        "row_percent": row_percent,
    }


def format_metrics_text(summary: dict[str, object]) -> str:
    label_distribution_lines = []
    for label in summary["class_labels"]:
        label_distribution_lines.append(
            "  - {label}: {count} ({share:.2%})".format(
                label=label,
                count=summary["label_distribution"]["counts"][str(label)],
                share=summary["label_distribution"]["shares"][str(label)],
            )
        )

    lines = [
        "Prediction Model Comparison",
        "===========================",
        "",
        f"Dataset rows: {summary['dataset_rows']}",
        f"Tickers: {summary['ticker_count']}",
        f"Date range: {summary['date_start']} -> {summary['date_end']}",
        f"Label column: {summary['label_column']}",
        f"Class labels: {', '.join(summary['class_labels'])}",
        f"Feature set: {summary['feature_set']}",
        f"Scenario filter: {summary['scenario_filter']}",
        f"Selection metric: {summary['selection_metric']}",
        f"Positive label: {summary['positive_label'] if summary['positive_label'] is not None else 'none'}",
        f"Sentiment start date: {summary['sentiment_start_date'] or 'none'}",
        f"Walk-forward folds: {summary['fold_count']}",
        "",
        "Label distribution:",
        *label_distribution_lines,
        "",
        "Scenario results:",
    ]

    for scenario in summary["scenarios"]:
        lines.append(f"- {scenario['scenario_name']}")
        for model in scenario["models"]:
            metrics = model["mean_metrics"]
            metric_parts = [
                f"acc={metrics['accuracy']:.4f}",
                f"f1_macro={metrics['f1_macro']:.4f}",
                f"dir_acc={metrics['directional_accuracy']:.4f}",
            ]
            if "precision_positive" in metrics:
                metric_parts.extend(
                    [
                        f"precision_pos={metrics['precision_positive']:.4f}",
                        f"recall_pos={metrics['recall_positive']:.4f}",
                        f"f1_pos={metrics['f1_positive']:.4f}",
                    ]
                )
            lines.append(f"  - {model['model_name']}: " + ", ".join(metric_parts))

    lines.extend(
        [
            "",
            "Selected deployment model: {name} ({scenario}) on {metric}={value:.4f}".format(
                name=summary["selected_model"]["model_name"],
                scenario=summary["selected_model"]["scenario_name"],
                metric=summary["selection_metric"],
                value=summary["selected_model"]["mean_metrics"][summary["selection_metric"]],
            ),
            "Sentiment contribution delta vs best no-sentiment: {value}".format(
                value=(
                    f"{summary['sentiment_contribution']['directional_accuracy_delta']:.4f}"
                    if summary["sentiment_contribution"]["directional_accuracy_delta"] is not None
                    else "n/a"
                )
            ),
        ]
    )

    top_features = summary["selected_model"].get("insights", {}).get("top_features", [])
    if top_features:
        lines.append("Top model features:")
        for feature, score in top_features:
            lines.append(f"  - {feature}: {score:.6f}")

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset)
    model_dir = Path(args.model_dir)
    metrics_json_path = Path(args.metrics_json)
    metrics_txt_path = Path(args.metrics_txt)
    label_column = args.label_column
    feature_set = args.feature_set
    scenario_filter = args.scenario_filter
    sentiment_start_date = pd.to_datetime(args.sentiment_start_date) if args.sentiment_start_date else None
    logistic_class_weight = parse_class_weight(args.logistic_class_weight)
    random_forest_class_weight = parse_class_weight(args.random_forest_class_weight)

    df = pd.read_csv(dataset_path)
    if df.empty:
        raise SystemExit("Dataset is empty.")

    if label_column not in df.columns:
        raise SystemExit(f"Label column '{label_column}' is missing from dataset.")

    df["reference_date"] = pd.to_datetime(df["reference_date"])
    df = df.sort_values(["reference_date", "ticker"]).reset_index(drop=True)
    df = df[df[label_column].notna()].copy()
    if df.empty:
        raise SystemExit("Dataset contains no valid labels.")

    class_labels = infer_class_labels(df[label_column])
    if not class_labels:
        raise SystemExit("Unable to infer class labels from dataset.")

    if np.issubdtype(df[label_column].dtype, np.number):
        if args.positive_label is not None:
            try:
                positive_label: object | None = int(args.positive_label)
            except ValueError:
                positive_label = float(args.positive_label)
        else:
            positive_label = None
    else:
        positive_label = args.positive_label

    label_counts = df[label_column].value_counts().reindex(class_labels, fill_value=0)
    label_shares = (label_counts / label_counts.sum()).to_dict()
    scenarios = build_scenarios(feature_set, scenario_filter)
    factories = model_factories(
        {label: float(label_shares[label]) for label in class_labels},
        class_labels,
        logistic_class_weight,
        random_forest_class_weight,
    )
    required_columns = {label_column}
    for scenario in scenarios:
        required_columns.update(scenario["feature_columns"])

    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise SystemExit(f"Dataset is missing required columns: {', '.join(sorted(missing_columns))}")

    scenario_results: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []
    best_sentiment_candidate: dict[str, object] | None = None
    best_no_sentiment_candidate: dict[str, object] | None = None
    scenario_fold_counts: list[int] = []

    for scenario in scenarios:
        scenario_df = df
        if scenario["scenario_name"] == "with_sentiment" and sentiment_start_date is not None:
            scenario_df = df[df["reference_date"] >= sentiment_start_date].copy()

        unique_dates = sorted(scenario_df["reference_date"].drop_duplicates().tolist())
        folds = build_folds(unique_dates, args.min_train_days, args.test_window_days)
        if args.max_folds > 0 and len(folds) > args.max_folds:
            folds = folds[-args.max_folds :]
        if not folds:
            raise SystemExit(
                f"Not enough history to build walk-forward folds for scenario '{scenario['scenario_name']}'. "
                "Lower --min-train-days or increase dataset span."
            )

        scenario_fold_counts.append(len(folds))
        models_summary: list[dict[str, object]] = []
        for model_name, factory in factories.items():
            fold_metrics: list[dict[str, float]] = []
            oos_y_true: list[str] = []
            oos_y_pred: list[str] = []
            for fold in folds:
                train_df = scenario_df[scenario_df["reference_date"] <= fold.train_end]
                test_df = scenario_df[(scenario_df["reference_date"] >= fold.test_start) & (scenario_df["reference_date"] <= fold.test_end)]
                if train_df.empty or test_df.empty:
                    continue

                x_train = train_df[scenario["feature_columns"]]
                y_train = train_df[label_column]
                x_test = test_df[scenario["feature_columns"]]
                y_test = test_df[label_column]

                estimator = factory(scenario["feature_columns"])
                estimator.fit(x_train, y_train)
                predictions = estimator.predict(x_test)
                fold_metrics.append(
                    evaluate_predictions(
                        y_test,
                        predictions,
                        class_labels=class_labels,
                        positive_label=positive_label,
                    )
                )
                oos_y_true.extend(y_test.tolist())
                oos_y_pred.extend(predictions.tolist())

            if not fold_metrics:
                continue

            mean_result = mean_metrics(fold_metrics)
            full_estimator = factory(scenario["feature_columns"])
            full_estimator.fit(scenario_df[scenario["feature_columns"]], scenario_df[label_column])
            summary_row = {
                "model_name": model_name,
                "scenario_name": scenario["scenario_name"],
                "feature_columns": scenario["feature_columns"],
                "dataset_rows": int(len(scenario_df)),
                "fold_metrics": fold_metrics,
                "mean_metrics": mean_result,
                "confusion_matrix": summarize_confusion_matrix(oos_y_true, oos_y_pred, class_labels),
                "insights": extract_model_insights(full_estimator, scenario["feature_columns"]),
            }
            models_summary.append(summary_row)
            candidate_rows.append(summary_row)

        models_summary.sort(
            key=lambda row: (
                metric_value(row, args.selection_metric),
                row["mean_metrics"]["directional_accuracy"],
                row["mean_metrics"]["f1_macro"],
            ),
            reverse=True,
        )
        scenario_block = {
            "scenario_name": scenario["scenario_name"],
            "feature_columns": scenario["feature_columns"],
            "dataset_rows": int(len(scenario_df)),
            "fold_count": len(folds),
            "models": models_summary,
        }
        scenario_results.append(scenario_block)

        if models_summary:
            top_model = models_summary[0]
            if scenario["scenario_name"] == "with_sentiment":
                best_sentiment_candidate = top_model
            else:
                best_no_sentiment_candidate = top_model

    if not candidate_rows:
        raise SystemExit("No model could be evaluated for the requested scenario filter.")

    selected_model_info = sorted(
        candidate_rows,
        key=lambda row: (
            metric_value(row, args.selection_metric),
            row["mean_metrics"]["directional_accuracy"],
            row["mean_metrics"]["f1_macro"],
        ),
        reverse=True,
    )[0]
    selected_model_df = df
    if selected_model_info["scenario_name"] == "with_sentiment" and sentiment_start_date is not None:
        selected_model_df = df[df["reference_date"] >= sentiment_start_date].copy()

    full_x = selected_model_df[selected_model_info["feature_columns"]]
    full_y = selected_model_df[label_column]
    final_estimator = factories[selected_model_info["model_name"]](selected_model_info["feature_columns"])
    final_estimator.fit(full_x, full_y)

    selected_model = {
        "model_name": selected_model_info["model_name"],
        "scenario_name": selected_model_info["scenario_name"],
        "feature_columns": selected_model_info["feature_columns"],
        "mean_metrics": selected_model_info["mean_metrics"],
        "confusion_matrix": selected_model_info["confusion_matrix"],
        "insights": extract_model_insights(final_estimator, selected_model_info["feature_columns"]),
    }

    contribution_delta: float | None = None
    if best_sentiment_candidate is not None and best_no_sentiment_candidate is not None:
        contribution_delta = (
            best_sentiment_candidate["mean_metrics"]["directional_accuracy"]
            - best_no_sentiment_candidate["mean_metrics"]["directional_accuracy"]
        )

    summary = {
        "dataset_rows": int(len(df)),
        "ticker_count": int(df["ticker"].nunique()),
        "date_start": str(df["reference_date"].min().date()),
        "date_end": str(df["reference_date"].max().date()),
        "label_column": label_column,
        "class_labels": [str(label) for label in class_labels],
        "feature_set": feature_set,
        "scenario_filter": scenario_filter,
        "selection_metric": args.selection_metric,
        "positive_label": str(positive_label) if positive_label is not None else None,
        "sentiment_start_date": str(sentiment_start_date.date()) if sentiment_start_date is not None else None,
        "label_distribution": {
            "counts": {str(label): int(label_counts[label]) for label in class_labels},
            "shares": {str(label): round(float(label_shares[label]), 6) for label in class_labels},
        },
        "fold_count": max(scenario_fold_counts) if scenario_fold_counts else 0,
        "scenarios": scenario_results,
        "selected_model": selected_model,
        "sentiment_contribution": {
            "directional_accuracy_delta": round(float(contribution_delta), 6) if contribution_delta is not None else None,
            "best_no_sentiment_model": best_no_sentiment_candidate,
        },
    }

    model_dir.mkdir(parents=True, exist_ok=True)
    metrics_json_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_txt_path.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(final_estimator, model_dir / "prediction_model.joblib")
    with (model_dir / "prediction_model_metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "feature_columns": selected_model["feature_columns"],
                "class_order": [str(label) for label in class_labels],
                "selected_model": selected_model,
                "label_column": label_column,
                "feature_set": feature_set,
                "dataset_rows": summary["dataset_rows"],
                "date_start": summary["date_start"],
                "date_end": summary["date_end"],
            },
            handle,
            indent=2,
        )

    with metrics_json_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    metrics_txt_path.write_text(format_metrics_text(summary), encoding="utf-8")

    print(json.dumps(
        {
            "selected_model": selected_model["model_name"],
            "scenario": selected_model["scenario_name"],
            "selection_metric": args.selection_metric,
            "selection_metric_value": selected_model["mean_metrics"][args.selection_metric],
            "directional_accuracy": selected_model["mean_metrics"]["directional_accuracy"],
            "model_dir": str(model_dir),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
