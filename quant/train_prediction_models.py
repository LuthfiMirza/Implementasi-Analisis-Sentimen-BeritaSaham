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
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ALL_FEATURE_COLUMNS = [
    "return_5d",
    "return_20d",
    "atr14_pct",
    "volume_ratio_20d",
    "price_vs_ema50",
    "market_regime_bullish",
    "sentiment_average_5d",
    "weighted_sentiment_5d",
    "news_volume_5d",
    "sentiment_average_5d_x_regime",
    "weighted_sentiment_5d_x_regime",
]

NO_SENTIMENT_FEATURE_COLUMNS = [
    "return_5d",
    "return_20d",
    "atr14_pct",
    "volume_ratio_20d",
    "price_vs_ema50",
    "market_regime_bullish",
]

CLASS_ORDER = ["down", "flat", "up"]


@dataclass
class FoldWindow:
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


class MajorityClassModel:
    def __init__(self) -> None:
        self.majority_class_: str | None = None
        self.classes_ = np.array(CLASS_ORDER)

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "MajorityClassModel":
        self.majority_class_ = y.mode().iloc[0]
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        if self.majority_class_ is None:
            raise RuntimeError("Model is not fitted.")
        return np.repeat(self.majority_class_, len(x))

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        if self.majority_class_ is None:
            raise RuntimeError("Model is not fitted.")
        probs = np.zeros((len(x), len(CLASS_ORDER)), dtype=float)
        probs[:, CLASS_ORDER.index(self.majority_class_)] = 1.0
        return probs


def build_logistic_pipeline(feature_columns: list[str]) -> Pipeline:
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
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )


def build_random_forest_pipeline(feature_columns: list[str]) -> Pipeline:
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
                    class_weight="balanced_subsample",
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


def evaluate_predictions(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "directional_accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_down": float(f1_score(y_true, y_pred, labels=CLASS_ORDER, average=None, zero_division=0)[0]),
        "f1_flat": float(f1_score(y_true, y_pred, labels=CLASS_ORDER, average=None, zero_division=0)[1]),
        "f1_up": float(f1_score(y_true, y_pred, labels=CLASS_ORDER, average=None, zero_division=0)[2]),
        "f1_macro": float(f1_score(y_true, y_pred, labels=CLASS_ORDER, average="macro", zero_division=0)),
    }


def mean_metrics(metrics: list[dict[str, float]]) -> dict[str, float]:
    keys = metrics[0].keys()
    return {key: round(float(np.mean([row[key] for row in metrics])), 6) for key in keys}


def model_factories() -> dict[str, Callable[[list[str]], object]]:
    return {
        "majority_class": lambda _feature_columns: MajorityClassModel(),
        "logistic_regression": build_logistic_pipeline,
        "random_forest": build_random_forest_pipeline,
    }


def extract_model_insights(fitted_model: object, feature_columns: list[str]) -> dict[str, object]:
    model = fitted_model
    if isinstance(fitted_model, Pipeline):
        model = fitted_model.named_steps["model"]

    if hasattr(model, "coef_"):
        coef = np.abs(np.asarray(model.coef_)).mean(axis=0)
        ranking = sorted(zip(feature_columns, coef.tolist()), key=lambda item: item[1], reverse=True)
        return {"type": "coefficients", "top_features": ranking[:5]}

    if hasattr(model, "feature_importances_"):
        importance = np.asarray(model.feature_importances_)
        ranking = sorted(zip(feature_columns, importance.tolist()), key=lambda item: item[1], reverse=True)
        return {"type": "feature_importances", "top_features": ranking[:5]}

    return {"type": "none", "top_features": []}


def format_metrics_text(summary: dict[str, object]) -> str:
    lines = [
        "Prediction Model Comparison",
        "===========================",
        "",
        f"Dataset rows: {summary['dataset_rows']}",
        f"Tickers: {summary['ticker_count']}",
        f"Date range: {summary['date_start']} -> {summary['date_end']}",
        f"Walk-forward folds: {summary['fold_count']}",
        "",
        "Scenario results:",
    ]

    for scenario in summary["scenarios"]:
        lines.append(f"- {scenario['scenario_name']}")
        for model in scenario["models"]:
            metrics = model["mean_metrics"]
            lines.append(
                "  - {name}: acc={acc:.4f}, f1_macro={f1:.4f}, dir_acc={dir_acc:.4f}".format(
                    name=model["model_name"],
                    acc=metrics["accuracy"],
                    f1=metrics["f1_macro"],
                    dir_acc=metrics["directional_accuracy"],
                )
            )

    lines.extend(
        [
            "",
            f"Selected deployment model: {summary['selected_model']['model_name']} ({summary['selected_model']['scenario_name']})",
            f"Sentiment contribution delta vs best no-sentiment: {summary['sentiment_contribution']['directional_accuracy_delta']:.4f}",
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

    df = pd.read_csv(dataset_path)
    if df.empty:
        raise SystemExit("Dataset is empty.")

    df["reference_date"] = pd.to_datetime(df["reference_date"])
    df = df.sort_values(["reference_date", "ticker"]).reset_index(drop=True)
    df = df[df["target_direction_5d"].isin(CLASS_ORDER)].copy()
    if df.empty:
        raise SystemExit("Dataset contains no valid labels.")

    unique_dates = sorted(df["reference_date"].drop_duplicates().tolist())
    folds = build_folds(unique_dates, args.min_train_days, args.test_window_days)
    if args.max_folds > 0 and len(folds) > args.max_folds:
        folds = folds[-args.max_folds :]
    if not folds:
        raise SystemExit("Not enough history to build walk-forward folds. Lower --min-train-days or increase dataset span.")

    scenarios = [
        {"scenario_name": "with_sentiment", "feature_columns": ALL_FEATURE_COLUMNS},
        {"scenario_name": "without_sentiment", "feature_columns": NO_SENTIMENT_FEATURE_COLUMNS},
    ]

    scenario_results: list[dict[str, object]] = []
    best_sentiment_candidate: dict[str, object] | None = None
    best_no_sentiment_candidate: dict[str, object] | None = None

    for scenario in scenarios:
        models_summary: list[dict[str, object]] = []
        for model_name, factory in model_factories().items():
            fold_metrics: list[dict[str, float]] = []
            for fold in folds:
                train_df = df[df["reference_date"] <= fold.train_end]
                test_df = df[(df["reference_date"] >= fold.test_start) & (df["reference_date"] <= fold.test_end)]
                if train_df.empty or test_df.empty:
                    continue

                x_train = train_df[scenario["feature_columns"]]
                y_train = train_df["target_direction_5d"]
                x_test = test_df[scenario["feature_columns"]]
                y_test = test_df["target_direction_5d"]

                estimator = factory(scenario["feature_columns"])
                estimator.fit(x_train, y_train)
                predictions = estimator.predict(x_test)
                fold_metrics.append(evaluate_predictions(y_test, predictions))

            if not fold_metrics:
                continue

            mean_result = mean_metrics(fold_metrics)
            summary_row = {
                "model_name": model_name,
                "scenario_name": scenario["scenario_name"],
                "feature_columns": scenario["feature_columns"],
                "fold_metrics": fold_metrics,
                "mean_metrics": mean_result,
            }
            models_summary.append(summary_row)

        models_summary.sort(key=lambda row: (row["mean_metrics"]["directional_accuracy"], row["mean_metrics"]["f1_macro"]), reverse=True)
        scenario_block = {
            "scenario_name": scenario["scenario_name"],
            "feature_columns": scenario["feature_columns"],
            "models": models_summary,
        }
        scenario_results.append(scenario_block)

        if models_summary:
            top_model = models_summary[0]
            if scenario["scenario_name"] == "with_sentiment":
                best_sentiment_candidate = top_model
            else:
                best_no_sentiment_candidate = top_model

    if best_sentiment_candidate is None:
        raise SystemExit("No sentiment-enabled model could be evaluated.")

    selected_model_info = best_sentiment_candidate
    full_x = df[selected_model_info["feature_columns"]]
    full_y = df["target_direction_5d"]
    final_estimator = model_factories()[selected_model_info["model_name"]](selected_model_info["feature_columns"])
    final_estimator.fit(full_x, full_y)

    selected_model = {
        "model_name": selected_model_info["model_name"],
        "scenario_name": selected_model_info["scenario_name"],
        "feature_columns": selected_model_info["feature_columns"],
        "mean_metrics": selected_model_info["mean_metrics"],
        "insights": extract_model_insights(final_estimator, selected_model_info["feature_columns"]),
    }

    contribution_delta = 0.0
    if best_no_sentiment_candidate is not None:
        contribution_delta = (
            best_sentiment_candidate["mean_metrics"]["directional_accuracy"]
            - best_no_sentiment_candidate["mean_metrics"]["directional_accuracy"]
        )

    summary = {
        "dataset_rows": int(len(df)),
        "ticker_count": int(df["ticker"].nunique()),
        "date_start": str(df["reference_date"].min().date()),
        "date_end": str(df["reference_date"].max().date()),
        "fold_count": len(folds),
        "folds": [
            {
                "train_end": str(fold.train_end.date()),
                "test_start": str(fold.test_start.date()),
                "test_end": str(fold.test_end.date()),
            }
            for fold in folds
        ],
        "scenarios": scenario_results,
        "selected_model": selected_model,
        "sentiment_contribution": {
            "directional_accuracy_delta": round(float(contribution_delta), 6),
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
                "class_order": CLASS_ORDER,
                "selected_model": selected_model,
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
            "directional_accuracy": selected_model["mean_metrics"]["directional_accuracy"],
            "model_dir": str(model_dir),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
