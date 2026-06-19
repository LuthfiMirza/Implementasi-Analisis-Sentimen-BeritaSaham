#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from statistics import pstdev

import numpy as np
import pandas as pd

from train_prediction_models import (
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    build_folds,
    evaluate_predictions,
    infer_class_labels,
    mean_metrics,
    model_factories,
)


OUTPUT_DIR = Path("output/prediction_research")
DATASET_PATH = OUTPUT_DIR / "dataset.csv"
V6A_DATASET_PATH = OUTPUT_DIR / "dataset_v6a.csv"
REPORT_TXT_PATH = OUTPUT_DIR / "model_comparison_v6a.txt"
REPORT_JSON_PATH = OUTPUT_DIR / "model_comparison_v6a.json"
STOCKS_DIR = Path("data/stocks")
CLASS_ORDER = ["down", "flat", "up"]
HORIZONS = [1, 3, 5, 10]
ATR_MULTIPLIERS = [0.5, 0.75]
BASELINE_V4A_DIRECTIONAL_ACCURACY = 0.4055


def adjusted_stock_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    factor = np.where(
        (frame["close"].astype(float) != 0.0) & frame["adj_close"].notna(),
        frame["adj_close"].astype(float) / frame["close"].astype(float),
        1.0,
    )
    frame["reference_date"] = pd.to_datetime(frame["date"])
    frame["close_adj"] = frame["adj_close"].fillna(frame["close"]).astype(float)
    frame["high_adj"] = frame["high"].astype(float) * factor
    frame["low_adj"] = frame["low"].astype(float) * factor
    return frame.sort_values("reference_date").reset_index(drop=True)


def label_direction(values: pd.Series, threshold: pd.Series | float) -> pd.Series:
    return pd.Series(
        np.where(values > threshold, "up", np.where(values < -threshold, "down", "flat")),
        index=values.index,
    )


def add_future_returns(dataset: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for ticker in sorted(dataset["ticker"].dropna().unique()):
        stock_path = STOCKS_DIR / f"{ticker}.csv"
        if not stock_path.is_file():
            raise SystemExit(f"Missing stock CSV for {ticker}: {stock_path}")
        stock = adjusted_stock_frame(stock_path)
        close = stock["close_adj"]
        for horizon in HORIZONS:
            stock[f"future_return_{horizon}d"] = close.shift(-horizon).div(close).sub(1)
        columns = ["reference_date", *[f"future_return_{horizon}d" for horizon in HORIZONS]]
        frames.append(stock[columns].assign(ticker=ticker))

    future_returns = pd.concat(frames, ignore_index=True)
    rebuilt = dataset.drop(columns=[f"future_return_{horizon}d" for horizon in HORIZONS if horizon != 5], errors="ignore")
    rebuilt = rebuilt.merge(future_returns, on=["ticker", "reference_date"], how="left", suffixes=("", "_recalc"))
    if "future_return_5d_recalc" in rebuilt.columns:
        rebuilt["future_return_5d"] = rebuilt["future_return_5d_recalc"]
        rebuilt = rebuilt.drop(columns=["future_return_5d_recalc"])
    return rebuilt


def add_labels(dataset: pd.DataFrame) -> pd.DataFrame:
    dataset = dataset.copy()
    for horizon in HORIZONS:
        return_column = f"future_return_{horizon}d"
        dataset[f"label_v2_h{horizon}d"] = label_direction(dataset[return_column].astype(float), 0.015)
        for multiplier in ATR_MULTIPLIERS:
            label_column = f"label_v6_atr{str(multiplier).replace('.', '_')}_h{horizon}d"
            threshold = dataset["atr14_pct"].astype(float) * multiplier
            dataset[label_column] = label_direction(dataset[return_column].astype(float), threshold)
    dataset["label_v6"] = dataset["label_v6_atr0_5_h5d"]
    return dataset


def label_distribution(dataset: pd.DataFrame, label_column: str) -> dict[str, object]:
    counts = dataset[label_column].value_counts().reindex(CLASS_ORDER, fill_value=0)
    shares = counts / counts.sum()
    return {
        "counts": {label: int(counts[label]) for label in CLASS_ORDER},
        "shares": {label: float(shares[label]) for label in CLASS_ORDER},
    }


def evaluate_label(dataset: pd.DataFrame, label_column: str) -> dict[str, object]:
    required_columns = ["reference_date", label_column, *V2_NO_SENTIMENT_FEATURE_COLUMNS]
    frame = dataset[required_columns].dropna().copy()
    class_labels = infer_class_labels(frame[label_column])
    class_probabilities = frame[label_column].value_counts(normalize=True).reindex(class_labels, fill_value=0).to_dict()
    factories = model_factories(class_probabilities, class_labels, "balanced", "balanced_subsample")
    unique_dates = sorted(frame["reference_date"].drop_duplicates().tolist())
    folds = build_folds(unique_dates, min_train_days=252, test_window_days=126)[-8:]
    models = []
    for model_name in ["logistic_regression", "random_forest", "random_baseline", "majority_class"]:
        fold_metrics = []
        for fold in folds:
            train_df = frame[frame["reference_date"] <= fold.train_end]
            test_df = frame[(frame["reference_date"] >= fold.test_start) & (frame["reference_date"] <= fold.test_end)]
            estimator = factories[model_name](V2_NO_SENTIMENT_FEATURE_COLUMNS)
            estimator.fit(train_df[V2_NO_SENTIMENT_FEATURE_COLUMNS], train_df[label_column])
            predictions = estimator.predict(test_df[V2_NO_SENTIMENT_FEATURE_COLUMNS])
            fold_metrics.append(evaluate_predictions(test_df[label_column], predictions, class_labels))
        models.append(
            {
                "model_name": model_name,
                "mean_metrics": mean_metrics(fold_metrics),
                "fold_metrics": fold_metrics,
            }
        )
    models.sort(key=lambda row: (row["mean_metrics"]["f1_macro"], row["mean_metrics"]["directional_accuracy"]), reverse=True)
    return {
        "label_column": label_column,
        "rows": int(len(frame)),
        "fold_count": len(folds),
        "distribution": label_distribution(frame, label_column),
        "models": models,
        "best_model": models[0],
    }


def ticker_volatility_table(dataset: pd.DataFrame) -> list[dict[str, object]]:
    rows = []
    for ticker, group in dataset.groupby("ticker"):
        rows.append(
            {
                "ticker": ticker,
                "median_atr14_pct": round(float(group["atr14_pct"].median()), 6),
                "label_v2_h5d_flat_share": round(float((group["label_v2_h5d"] == "flat").mean()), 6),
                "label_v6_atr0_5_h5d_flat_share": round(float((group["label_v6_atr0_5_h5d"] == "flat").mean()), 6),
                "label_v6_atr0_75_h5d_flat_share": round(float((group["label_v6_atr0_75_h5d"] == "flat").mean()), 6),
            }
        )
    return sorted(rows, key=lambda row: row["median_atr14_pct"])


def format_pct(value: float) -> str:
    return f"{value:.4f}"


def write_report(summary: dict[str, object]) -> None:
    lines = [
        "V6A Technical Direction Prediction Model",
        "========================================",
        "",
        "Scope: offline prediction research only; no P&L, backtest, entry/exit, stop-loss, or strategy promotion logic.",
        "Primary selection metric: macro F1. Secondary metric: directional_accuracy.",
        "Feature set: v2 without sentiment. Models: logistic_regression, random_forest plus random/majority baselines.",
        "Walk-forward policy: min_train_days=252, test_window_days=126, latest 8 folds; scaling remains inside model pipeline.",
        "",
        f"Dataset rows: {summary['dataset_rows']}",
        f"Tickers: {summary['ticker_count']}",
        f"Date range: {summary['date_start']} -> {summary['date_end']}",
        f"Baseline comparator: model_comparison_v4a logistic_regression directional_accuracy={BASELINE_V4A_DIRECTIONAL_ACCURACY:.4f}",
        "",
        "Label/Horizon Comparison",
        "------------------------",
        "label,horizon,down_share,flat_share,up_share,best_model,macro_f1,directional_accuracy,majority_macro_f1,majority_directional_accuracy,fold_macro_f1_std",
    ]
    for row in summary["comparison_rows"]:
        lines.append(
            ",".join(
                [
                    row["label_family"],
                    str(row["horizon"]),
                    format_pct(row["down_share"]),
                    format_pct(row["flat_share"]),
                    format_pct(row["up_share"]),
                    row["best_model"],
                    format_pct(row["macro_f1"]),
                    format_pct(row["directional_accuracy"]),
                    format_pct(row["majority_macro_f1"]),
                    format_pct(row["majority_directional_accuracy"]),
                    format_pct(row["fold_macro_f1_std"]),
                ]
            )
        )

    best = summary["best_result"]
    lines.extend(
        [
            "",
            "Best V6A Candidate",
            "-------------------",
            f"Label column: {best['label_column']}",
            f"Model: {best['best_model']['model_name']}",
            f"Macro F1: {best['best_model']['mean_metrics']['f1_macro']:.4f}",
            f"Directional accuracy: {best['best_model']['mean_metrics']['directional_accuracy']:.4f}",
            f"Delta vs v4a directional_accuracy: {best['best_model']['mean_metrics']['directional_accuracy'] - BASELINE_V4A_DIRECTIONAL_ACCURACY:+.4f}",
            f"Delta vs majority macro F1: {summary['best_majority_delta_macro_f1']:+.4f}",
            f"Delta vs majority directional_accuracy: {summary['best_majority_delta_directional_accuracy']:+.4f}",
            "",
            "Ticker Volatility Consistency Snapshot",
            "--------------------------------------",
            "ticker,median_atr14_pct,label_v2_h5d_flat_share,label_v6_atr0_5_h5d_flat_share,label_v6_atr0_75_h5d_flat_share",
        ]
    )
    for row in summary["ticker_volatility"]:
        lines.append(
            f"{row['ticker']},{row['median_atr14_pct']:.4f},{row['label_v2_h5d_flat_share']:.4f},{row['label_v6_atr0_5_h5d_flat_share']:.4f},{row['label_v6_atr0_75_h5d_flat_share']:.4f}"
        )

    lines.extend(
        [
            "",
            "Assessment",
            "----------",
            summary["assessment"],
            "",
            "Recommendation",
            "--------------",
            summary["recommendation"],
            "",
        ]
    )
    REPORT_TXT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    dataset = pd.read_csv(DATASET_PATH)
    dataset["reference_date"] = pd.to_datetime(dataset["reference_date"])
    dataset = add_labels(add_future_returns(dataset))
    dataset.to_csv(V6A_DATASET_PATH, index=False)

    results = []
    comparison_rows = []
    for horizon in HORIZONS:
        label_specs = [("v2_fixed_1_5pct", f"label_v2_h{horizon}d")]
        label_specs.extend((f"v6_atr_k_{multiplier}", f"label_v6_atr{str(multiplier).replace('.', '_')}_h{horizon}d") for multiplier in ATR_MULTIPLIERS)
        for label_family, label_column in label_specs:
            print(f"Evaluating {label_column}...", flush=True)
            result = evaluate_label(dataset, label_column)
            result["label_family"] = label_family
            result["horizon"] = horizon
            results.append(result)
            distribution = result["distribution"]["shares"]
            majority = next(model for model in result["models"] if model["model_name"] == "majority_class")
            fold_macro_f1_values = [row["f1_macro"] for row in result["best_model"]["fold_metrics"]]
            comparison_rows.append(
                {
                    "label_family": label_family,
                    "horizon": horizon,
                    "down_share": distribution["down"],
                    "flat_share": distribution["flat"],
                    "up_share": distribution["up"],
                    "best_model": result["best_model"]["model_name"],
                    "macro_f1": result["best_model"]["mean_metrics"]["f1_macro"],
                    "directional_accuracy": result["best_model"]["mean_metrics"]["directional_accuracy"],
                    "majority_macro_f1": majority["mean_metrics"]["f1_macro"],
                    "majority_directional_accuracy": majority["mean_metrics"]["directional_accuracy"],
                    "fold_macro_f1_std": float(pstdev(fold_macro_f1_values)) if len(fold_macro_f1_values) > 1 else 0.0,
                }
            )

    best_result = sorted(results, key=lambda row: (row["best_model"]["mean_metrics"]["f1_macro"], row["best_model"]["mean_metrics"]["directional_accuracy"]), reverse=True)[0]
    best_majority = next(model for model in best_result["models"] if model["model_name"] == "majority_class")
    delta = best_result["best_model"]["mean_metrics"]["directional_accuracy"] - BASELINE_V4A_DIRECTIONAL_ACCURACY
    majority_delta_macro_f1 = best_result["best_model"]["mean_metrics"]["f1_macro"] - best_majority["mean_metrics"]["f1_macro"]
    majority_delta_directional = best_result["best_model"]["mean_metrics"]["directional_accuracy"] - best_majority["mean_metrics"]["directional_accuracy"]
    if delta >= 0.05 and majority_delta_macro_f1 >= 0.05 and majority_delta_directional >= 0:
        assessment = "V6A shows a substantial improvement over v4a and the majority baseline on the fixed metric, with no directional-accuracy penalty versus majority."
    elif delta >= 0.02 and majority_delta_macro_f1 >= 0.02:
        assessment = "V6A improves macro F1 versus trivial majority and improves directional accuracy versus v4a, but the best fixed-metric candidate can still trail majority-class directional accuracy on imbalanced horizons; treat this as a classification research baseline, not strategy evidence."
    else:
        assessment = "V6A improvement is marginal or absent versus v4a; this is likely close to the realistic limit of the current technical feature set."

    recommendation = (
        "Use the best V6A technical-only configuration as the official comparison baseline for V6B only if V6B reports the same fixed metrics "
        "and remains in the offline prediction lane. Do not promote either V6A or V6B into trading/backtest scope without new governance approval."
    )
    summary = {
        "dataset_rows": int(len(dataset)),
        "ticker_count": int(dataset["ticker"].nunique()),
        "date_start": str(dataset["reference_date"].min().date()),
        "date_end": str(dataset["reference_date"].max().date()),
        "feature_set": "v2_without_sentiment",
        "selection_metric": "f1_macro",
        "secondary_metric": "directional_accuracy",
        "horizons": HORIZONS,
        "atr_multipliers": ATR_MULTIPLIERS,
        "comparison_rows": comparison_rows,
        "results": results,
        "best_result": best_result,
        "best_majority_delta_macro_f1": round(float(majority_delta_macro_f1), 6),
        "best_majority_delta_directional_accuracy": round(float(majority_delta_directional), 6),
        "ticker_volatility": ticker_volatility_table(dataset),
        "assessment": assessment,
        "recommendation": recommendation,
    }
    REPORT_JSON_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(summary)
    print({"report": str(REPORT_TXT_PATH), "json": str(REPORT_JSON_PATH), "dataset": str(V6A_DATASET_PATH)})


if __name__ == "__main__":
    main()
