#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quant"))

from train_prediction_models import (  # noqa: E402
    MajorityClassModel,
    build_folds,
    build_logistic_pipeline,
    build_random_forest_pipeline,
    evaluate_predictions,
    infer_class_labels,
    mean_metrics,
    model_factories,
)

START_DATE = "2025-10-01"
END_DATE = "2026-04-15"
MIN_TRAIN_DAYS = 40
TEST_WINDOW_DAYS = 10
PROMOTION_MARGIN = 0.02

REPORT_JSON = ROOT / "output/prediction_research/model_comparison_bumi_dewa_sentiment.json"
REPORT_TXT = ROOT / "output/prediction_research/model_comparison_bumi_dewa_sentiment.txt"

TECHNICAL_FEATURES = [
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

SENTIMENT_FEATURES = [
    "has_sentiment_data",
    "sentiment_average_5d",
    "weighted_sentiment_5d",
    "news_volume_5d",
    "sentiment_average_5d_x_regime",
    "weighted_sentiment_5d_x_regime",
]

PRODUCTION_BASELINES = {
    "BUMI_directional_fixed_2_7pct": {"macro_f1": 0.3742, "directional_accuracy": 0.4216, "algorithm": "random_forest"},
    "DEWA_directional_atr0_5": {"macro_f1": 0.4102, "directional_accuracy": 0.5050, "algorithm": "gradient_boosting"},
    "DEWA_regime_move_0_5pct": {"macro_f1": 0.5751, "directional_accuracy": 0.8532, "algorithm": "logistic_regression"},
}


def build_gradient_boosting_pipeline(feature_columns: list[str]) -> Pipeline:
    return Pipeline(
        steps=[
            (
                "preprocess",
                ColumnTransformer(
                    transformers=[
                        (
                            "num",
                            Pipeline(steps=[("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]),
                            feature_columns,
                        )
                    ]
                ),
            ),
            ("model", HistGradientBoostingClassifier(max_iter=60, learning_rate=0.08, random_state=42)),
        ]
    )


def label_direction(return_series: pd.Series, threshold: float) -> np.ndarray:
    return np.where(return_series > threshold, "up", np.where(return_series < -threshold, "down", "flat"))


def add_labels(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["label_directional_fixed_2_7pct"] = label_direction(frame["future_return_5d"].astype(float), 0.027)
    frame["label_regime_move_0_5pct"] = np.where(frame["future_return_5d"].abs() > 0.005, "move", "no_move")
    frame["label_directional_atr0_5"] = np.where(
        frame["future_return_5d"] > frame["atr14_pct"] * 0.5,
        "up",
        np.where(frame["future_return_5d"] < -frame["atr14_pct"] * 0.5, "down", "flat"),
    )
    return frame


def load_subset(path: Path, ticker: str) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["reference_date"])
    frame = frame[(frame["reference_date"] >= START_DATE) & (frame["reference_date"] <= END_DATE)].copy()
    frame = frame.sort_values("reference_date").reset_index(drop=True)
    return add_labels(frame, ticker)


def factories(class_probabilities: dict[Any, float], class_labels: list[Any]) -> dict[str, Any]:
    base = model_factories(class_probabilities, class_labels, "balanced", "balanced_subsample")
    base["gradient_boosting"] = build_gradient_boosting_pipeline
    return base


def label_distribution(frame: pd.DataFrame, label_column: str) -> dict[str, Any]:
    labels = infer_class_labels(frame[label_column])
    counts = frame[label_column].value_counts().reindex(labels, fill_value=0)
    total = int(counts.sum())
    return {
        "counts": {str(label): int(counts[label]) for label in labels},
        "shares": {str(label): round(float(counts[label] / total), 6) if total else 0.0 for label in labels},
    }


def run_evaluation(
    frame: pd.DataFrame,
    experiment_id: str,
    label_column: str,
    feature_columns: list[str],
    model_names: list[str],
) -> dict[str, Any]:
    required = ["reference_date", label_column, *feature_columns]
    sentiment_index = frame.index[frame["has_sentiment_data"].fillna(0).astype(int) == 1]
    eval_frame = frame.loc[sentiment_index, required].dropna().sort_values("reference_date").copy()
    class_labels = infer_class_labels(eval_frame[label_column])
    class_probabilities = eval_frame[label_column].value_counts(normalize=True).reindex(class_labels, fill_value=0).to_dict()
    unique_dates = sorted(eval_frame["reference_date"].drop_duplicates().tolist())
    folds = build_folds(unique_dates, MIN_TRAIN_DAYS, TEST_WINDOW_DAYS)
    all_factories = factories(class_probabilities, class_labels)
    models: list[dict[str, Any]] = []
    for model_name in [*model_names, "majority_class", "random_baseline"]:
        fold_metrics = []
        fold_rows = []
        for fold_index, fold in enumerate(folds, start=1):
            train_df = eval_frame[eval_frame["reference_date"] <= fold.train_end]
            test_df = eval_frame[(eval_frame["reference_date"] >= fold.test_start) & (eval_frame["reference_date"] <= fold.test_end)]
            single_class_train = train_df[label_column].nunique(dropna=True) < 2
            estimator = MajorityClassModel() if single_class_train and model_name not in {"majority_class", "random_baseline"} else all_factories[model_name](feature_columns)
            estimator.fit(train_df[feature_columns], train_df[label_column])
            predictions = estimator.predict(test_df[feature_columns])
            metrics = evaluate_predictions(test_df[label_column], predictions, class_labels)
            fold_metrics.append(metrics)
            fold_rows.append({"fold_index": fold_index, "fold": asdict(fold), "train_rows": int(len(train_df)), "test_rows": int(len(test_df)), "single_class_train_fallback": bool(single_class_train and model_name not in {"majority_class", "random_baseline"}), "metrics": metrics})
        models.append({"model_name": model_name, "mean_metrics": mean_metrics(fold_metrics) if fold_metrics else {}, "fold_metrics": fold_rows})
    return {
        "experiment_id": experiment_id,
        "label_column": label_column,
        "feature_columns": feature_columns,
        "rows_after_dropna": int(len(eval_frame)),
        "sentiment_rows": int(frame.loc[eval_frame.index, "has_sentiment_data"].sum()) if "has_sentiment_data" in frame else None,
        "date_start": str(eval_frame["reference_date"].min().date()) if len(eval_frame) else None,
        "date_end": str(eval_frame["reference_date"].max().date()) if len(eval_frame) else None,
        "fold_count": int(len(folds)),
        "class_labels": [str(label) for label in class_labels],
        "label_distribution": label_distribution(eval_frame, label_column) if len(eval_frame) else {"counts": {}, "shares": {}},
        "models": models,
    }


def model_lookup(result: dict[str, Any], model_name: str) -> dict[str, Any]:
    return next(row for row in result["models"] if row["model_name"] == model_name)


def fold_win_share(sentiment_model: dict[str, Any], technical_model: dict[str, Any]) -> dict[str, Any]:
    sentiment_folds = sentiment_model["fold_metrics"]
    technical_folds = technical_model["fold_metrics"]
    f1_wins = 0
    acc_wins = 0
    both_wins = 0
    for sentiment_fold, technical_fold in zip(sentiment_folds, technical_folds):
        f1_win = sentiment_fold["metrics"]["f1_macro"] > technical_fold["metrics"]["f1_macro"]
        acc_win = sentiment_fold["metrics"]["directional_accuracy"] > technical_fold["metrics"]["directional_accuracy"]
        f1_wins += int(f1_win)
        acc_wins += int(acc_win)
        both_wins += int(f1_win and acc_win)
    total = len(sentiment_folds)
    return {"folds": total, "f1_wins": f1_wins, "accuracy_wins": acc_wins, "both_metric_wins": both_wins, "both_metric_win_share": round(both_wins / total, 6) if total else 0.0}


def status_for(delta_f1: float, delta_acc: float, fold_wins: dict[str, Any]) -> str:
    majority_needed = fold_wins["both_metric_wins"] > fold_wins["folds"] / 2 if fold_wins["folds"] else False
    if delta_f1 > PROMOTION_MARGIN and delta_acc > PROMOTION_MARGIN and majority_needed:
        return "menang"
    if delta_f1 > 0 and delta_acc > 0:
        return "sebagian"
    return "tidak_menang"


def summarize_pair(ticker: str, task: str, algorithm: str, technical_result: dict[str, Any], sentiment_result: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    technical_model = model_lookup(technical_result, algorithm)
    sentiment_model = model_lookup(sentiment_result, algorithm)
    majority = model_lookup(technical_result, "majority_class")
    random = model_lookup(technical_result, "random_baseline")
    for variant, model, reference in [("technical_only", technical_model, None), ("technical_plus_sentiment", sentiment_model, technical_model)]:
        metrics = model["mean_metrics"]
        if not metrics:
            rows.append(
                {
                    "ticker": ticker,
                    "task": task,
                    "variant": variant,
                    "algorithm": algorithm,
                    "macro_f1": None,
                    "directional_accuracy": None,
                    "majority_class_macro_f1": None,
                    "majority_class_directional_accuracy": None,
                    "random_baseline_macro_f1": None,
                    "random_baseline_directional_accuracy": None,
                    "delta_macro_f1_vs_internal_technical": None,
                    "delta_directional_accuracy_vs_internal_technical": None,
                    "fold_win_summary": {"folds": technical_result["fold_count"], "f1_wins": 0, "accuracy_wins": 0, "both_metric_wins": 0, "both_metric_win_share": 0.0},
                    "status": "insufficient_data",
                }
            )
            continue
        delta_f1 = metrics["f1_macro"] - reference["mean_metrics"]["f1_macro"] if reference and reference["mean_metrics"] else 0.0
        delta_acc = metrics["directional_accuracy"] - reference["mean_metrics"]["directional_accuracy"] if reference and reference["mean_metrics"] else 0.0
        wins = fold_win_share(model, reference) if reference else {"folds": technical_result["fold_count"], "f1_wins": 0, "accuracy_wins": 0, "both_metric_wins": 0, "both_metric_win_share": 0.0}
        rows.append(
            {
                "ticker": ticker,
                "task": task,
                "variant": variant,
                "algorithm": algorithm,
                "macro_f1": metrics["f1_macro"],
                "directional_accuracy": metrics["directional_accuracy"],
                "majority_class_macro_f1": majority["mean_metrics"]["f1_macro"],
                "majority_class_directional_accuracy": majority["mean_metrics"]["directional_accuracy"],
                "random_baseline_macro_f1": random["mean_metrics"]["f1_macro"],
                "random_baseline_directional_accuracy": random["mean_metrics"]["directional_accuracy"],
                "delta_macro_f1_vs_internal_technical": round(float(delta_f1), 6),
                "delta_directional_accuracy_vs_internal_technical": round(float(delta_acc), 6),
                "fold_win_summary": wins,
                "status": "internal_baseline" if reference is None else status_for(delta_f1, delta_acc, wins),
            }
        )
    return rows


def representativeness_rows(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping = {
        ("BUMI", "directional_fixed_2_7pct", "random_forest"): "BUMI_directional_fixed_2_7pct",
        ("DEWA", "directional_atr0_5", "gradient_boosting"): "DEWA_directional_atr0_5",
        ("DEWA", "regime_move_0_5pct", "logistic_regression"): "DEWA_regime_move_0_5pct",
    }
    rows = []
    for row in summary_rows:
        if row["variant"] != "technical_only":
            continue
        key = mapping.get((row["ticker"], row["task"], row["algorithm"]))
        if not key:
            continue
        if row["macro_f1"] is None or row["directional_accuracy"] is None:
            continue
        prod = PRODUCTION_BASELINES[key]
        rows.append(
            {
                "ticker": row["ticker"],
                "task": row["task"],
                "algorithm": row["algorithm"],
                "subset_macro_f1": row["macro_f1"],
                "production_macro_f1": prod["macro_f1"],
                "delta_macro_f1_subset_minus_production": round(row["macro_f1"] - prod["macro_f1"], 6),
                "subset_directional_accuracy": row["directional_accuracy"],
                "production_directional_accuracy": prod["directional_accuracy"],
                "delta_directional_accuracy_subset_minus_production": round(row["directional_accuracy"] - prod["directional_accuracy"], 6),
            }
        )
    return rows


def assessment(summary_rows: list[dict[str, Any]], bumi_fold_count: int) -> dict[str, str]:
    sentiment_rows = [row for row in summary_rows if row["variant"] == "technical_plus_sentiment"]
    dewa_wins = [row for row in sentiment_rows if row["ticker"] == "DEWA" and row["status"] == "menang"]
    bumi_wins = [row for row in sentiment_rows if row["ticker"] == "BUMI" and row["status"] == "menang"]
    return {
        "DEWA": "Sentiment layak dipromosikan hanya jika ada status menang pada task production dengan margin >0.02 dan mayoritas fold; hasil eksperimen ini menunjukkan " + ("ada kandidat menang." if dewa_wins else "belum ada bukti konsisten yang cukup kuat."),
        "BUMI": ("Preliminary only, insufficient folds; jangan jadikan dasar keputusan promosi model. " if bumi_fold_count < 3 else "") + ("Ada indikasi awal positif." if bumi_wins else "Tidak ada bukti kuat yang cukup untuk promosi sentiment."),
    }


def format_report(payload: dict[str, Any]) -> str:
    def fmt(value: Any, signed: bool = False) -> str:
        if value is None:
            return "NA"
        return f"{float(value):+0.4f}" if signed else f"{float(value):0.4f}"

    lines = [
        "BUMI & DEWA Sentiment Walk-Forward Experiment",
        "==============================================",
        "",
        f"Periode subset: {START_DATE} s.d. {END_DATE}",
        f"Walk-forward: min_train_days={MIN_TRAIN_DAYS}, test_window_days={TEST_WINDOW_DAYS}",
        "Metric policy: macro F1 utama + directional accuracy sekunder.",
        "Evaluasi memakai rows ber-sentimen untuk menjaga apples-to-apples technical-only vs +sentiment pada sample yang sama.",
        "BUMI disclaimer: hasil bersifat preliminary karena keterbatasan sample; jika fold < 3 maka insufficient data for robust walk-forward.",
        "",
        "Coverage",
        "--------",
    ]
    for ticker, meta in payload["dataset_summary"].items():
        lines.append(f"- {ticker}: rows={meta['rows']}, sentiment_rows/evaluation_rows={meta['sentiment_rows']} ({meta['sentiment_coverage_pct']:.2f}%), fold_count={meta['fold_count']}")
    lines.extend(["", "Comparison Table", "----------------", "ticker,task,variant,algorithm,macro_f1,directional_accuracy,majority_f1,majority_acc,random_f1,random_acc,delta_f1,delta_acc,fold_both_wins,status"])
    for row in payload["comparison_table"]:
        lines.append(
            f"{row['ticker']},{row['task']},{row['variant']},{row['algorithm']},{fmt(row['macro_f1'])},{fmt(row['directional_accuracy'])},"
            f"{fmt(row['majority_class_macro_f1'])},{fmt(row['majority_class_directional_accuracy'])},{fmt(row['random_baseline_macro_f1'])},{fmt(row['random_baseline_directional_accuracy'])},"
            f"{fmt(row['delta_macro_f1_vs_internal_technical'], signed=True)},{fmt(row['delta_directional_accuracy_vs_internal_technical'], signed=True)},"
            f"{row['fold_win_summary']['both_metric_wins']}/{row['fold_win_summary']['folds']},{row['status']}"
        )
    lines.extend(["", "Production Baseline Representativeness", "--------------------------------------", "ticker,task,algorithm,subset_f1,production_f1,delta_f1,subset_acc,production_acc,delta_acc"])
    for row in payload["production_representativeness"]:
        lines.append(
            f"{row['ticker']},{row['task']},{row['algorithm']},{row['subset_macro_f1']:.4f},{row['production_macro_f1']:.4f},{row['delta_macro_f1_subset_minus_production']:+.4f},"
            f"{row['subset_directional_accuracy']:.4f},{row['production_directional_accuracy']:.4f},{row['delta_directional_accuracy_subset_minus_production']:+.4f}"
        )
    lines.extend(["", "Assessment", "----------"])
    for ticker, text in payload["assessment"].items():
        lines.append(f"- {ticker}: {text}")
    lines.extend(["", "Recommendation", "--------------", payload["recommendation"]])
    return "\n".join(lines) + "\n"


def main() -> None:
    datasets = {
        "BUMI": load_subset(ROOT / "output/prediction_research/dataset_bumi_with_sentiment.csv", "BUMI"),
        "DEWA": load_subset(ROOT / "output/prediction_research/dataset_dewa_with_sentiment.csv", "DEWA"),
    }
    features = {"technical_only": TECHNICAL_FEATURES, "technical_plus_sentiment": [*TECHNICAL_FEATURES, *SENTIMENT_FEATURES]}
    experiments: dict[str, Any] = {}

    specs = [
        ("DEWA", "directional_atr0_5", "label_directional_atr0_5", ["gradient_boosting", "logistic_regression"]),
        ("DEWA", "regime_move_0_5pct", "label_regime_move_0_5pct", ["gradient_boosting", "logistic_regression"]),
        ("BUMI", "directional_fixed_2_7pct", "label_directional_fixed_2_7pct", ["random_forest", "logistic_regression"]),
    ]
    for ticker, task, label_column, model_names in specs:
        for variant, feature_columns in features.items():
            experiment_id = f"{ticker.lower()}_{task}_{variant}"
            experiments[experiment_id] = run_evaluation(datasets[ticker], experiment_id, label_column, feature_columns, model_names)

    comparison_rows: list[dict[str, Any]] = []
    comparison_plan = [
        ("DEWA", "directional_atr0_5", "gradient_boosting"),
        ("DEWA", "directional_atr0_5", "logistic_regression"),
        ("DEWA", "regime_move_0_5pct", "gradient_boosting"),
        ("DEWA", "regime_move_0_5pct", "logistic_regression"),
        ("BUMI", "directional_fixed_2_7pct", "random_forest"),
        ("BUMI", "directional_fixed_2_7pct", "logistic_regression"),
    ]
    for ticker, task, algorithm in comparison_plan:
        technical = experiments[f"{ticker.lower()}_{task}_technical_only"]
        sentiment = experiments[f"{ticker.lower()}_{task}_technical_plus_sentiment"]
        comparison_rows.extend(summarize_pair(ticker, task, algorithm, technical, sentiment))

    dataset_summary = {}
    for ticker, frame in datasets.items():
        sentiment_frame = frame[frame["has_sentiment_data"].fillna(0).astype(int) == 1]
        fold_count = len(build_folds(sorted(sentiment_frame["reference_date"].drop_duplicates().tolist()), MIN_TRAIN_DAYS, TEST_WINDOW_DAYS))
        dataset_summary[ticker] = {
            "rows": int(len(frame)),
            "sentiment_rows": int(frame["has_sentiment_data"].sum()),
            "sentiment_coverage_pct": round(float(frame["has_sentiment_data"].sum() / len(frame) * 100), 2),
            "evaluation_rows": int(len(sentiment_frame)),
            "fold_count": int(fold_count),
            "date_start": str(frame["reference_date"].min().date()),
            "date_end": str(frame["reference_date"].max().date()),
        }

    payload = {
        "metadata": {
            "scope": "prediction research only; no production dataset/model overwrite",
            "period_start": START_DATE,
            "period_end": END_DATE,
            "min_train_days": MIN_TRAIN_DAYS,
            "test_window_days": TEST_WINDOW_DAYS,
            "promotion_criteria": "wins both macro_f1 and directional_accuracy by >0.02 and wins both metrics in majority of folds",
        },
        "dataset_summary": dataset_summary,
        "experiments": experiments,
        "comparison_table": comparison_rows,
        "production_representativeness": representativeness_rows(comparison_rows),
        "assessment": assessment(comparison_rows, dataset_summary["BUMI"]["fold_count"]),
    }
    winning_sentiment = [row for row in comparison_rows if row["variant"] == "technical_plus_sentiment" and row["status"] == "menang"]
    payload["recommendation"] = (
        "Tidak promosikan model sentiment dulu; tunggu review dan/atau validasi tambahan."
        if not winning_sentiment
        else "Ada kandidat sentiment yang memenuhi gate numerik; tetap jangan training full-data sampai hasil ini direview manual."
    )

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    REPORT_TXT.write_text(format_report(payload), encoding="utf-8")
    print(json.dumps({"json": str(REPORT_JSON), "txt": str(REPORT_TXT), "recommendation": payload["recommendation"]}, indent=2))


if __name__ == "__main__":
    main()
