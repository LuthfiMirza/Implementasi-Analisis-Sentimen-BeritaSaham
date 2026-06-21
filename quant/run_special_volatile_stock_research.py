#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pandas as pd

from rebuild_prediction_research_dataset_v2 import (
    adjusted_stock_frame,
    build_ihsg_regime,
    calculate_rsi_series,
    label_direction,
)
from train_prediction_models import (
    CLASS_ORDER,
    build_folds,
    evaluate_predictions,
    infer_class_labels,
    mean_metrics,
    model_factories,
)

OUTPUT_DIR = Path("output/prediction_research")
IHSG_CSV = Path("data/IHSG.csv")
FEATURE_COLUMNS = [
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
SOURCE_PRIORITY = {
    "yahoo_history_incremental": 0,
    "yahoo_daily_rebuild_raw": 0,
    "": 1,
    None: 1,
    "command": 2,
    "seed": 3,
}
V6A_REFERENCE = {"macro_f1": 0.3673, "directional_accuracy": 0.4050}


def env_value(key: str, default: str = "") -> str:
    env_path = Path(".env")
    if not env_path.exists():
        return default
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"')
    return default


def load_raw_db_prices(ticker: str) -> pd.DataFrame:
    mysql_bin = "mysql"
    xampp_mysql = Path("/Applications/XAMPP/xamppfiles/bin/mysql")
    if xampp_mysql.exists():
        mysql_bin = str(xampp_mysql)
    database = env_value("DB_DATABASE", "sentimena_dashboard")
    user = env_value("DB_USERNAME", "root")
    password = env_value("DB_PASSWORD", "")
    host = env_value("DB_HOST", "127.0.0.1")
    port = env_value("DB_PORT", "3306")
    query = f"""
        SELECT sp.id, s.code AS ticker, DATE(sp.price_date) AS date, sp.open, sp.high, sp.low, sp.close,
               sp.volume, sp.source, sp.interval_type
        FROM stock_prices sp
        JOIN stocks s ON s.id = sp.stock_id
        WHERE s.code = '{ticker}' AND sp.interval_type = '1d'
        ORDER BY DATE(sp.price_date), sp.id
    """
    command = [mysql_bin, f"--host={host}", f"--port={port}", f"--user={user}", "--batch", "--raw", database, "-e", query]
    if password:
        command.insert(3, f"--password={password}")
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    with NamedTemporaryFile("w+", newline="", suffix=".tsv") as handle:
        handle.write(result.stdout)
        handle.flush()
        return pd.read_csv(handle.name, sep="\t")


def canonicalize_prices(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    frame["source"] = frame["source"].replace({np.nan: ""})
    if (frame["source"] != "seed").any():
        frame = frame[frame["source"] != "seed"].copy()
    frame["source_priority"] = frame["source"].map(lambda value: SOURCE_PRIORITY.get(value, 2))
    frame["volume_sort"] = frame["volume"].fillna(0).astype(float)
    frame = frame.sort_values(["date", "source_priority", "volume_sort", "id"], ascending=[True, True, False, False])
    canonical = frame.groupby("date", as_index=False).first()
    canonical = canonical.sort_values("date").reset_index(drop=True)
    canonical["date"] = pd.to_datetime(canonical["date"])
    for column in ["open", "high", "low", "close", "volume"]:
        canonical[column] = pd.to_numeric(canonical[column], errors="coerce")
    return canonical[["date", "open", "high", "low", "close", "volume", "source"]]


def add_technical_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy().sort_values("date").reset_index(drop=True)
    close = frame["close"].astype(float)
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            frame["high"].astype(float) - frame["low"].astype(float),
            (frame["high"].astype(float) - prev_close).abs(),
            (frame["low"].astype(float) - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    true_range.iloc[0] = np.nan
    frame["return_1d"] = close.div(close.shift(1)).sub(1)
    frame["return_3d"] = close.div(close.shift(3)).sub(1)
    frame["return_5d"] = close.div(close.shift(5)).sub(1)
    frame["return_20d"] = close.div(close.shift(20)).sub(1)
    frame["atr14"] = true_range.rolling(14, min_periods=14).mean()
    frame["atr_ratio"] = frame["atr14"].div(close)
    frame["atr14_pct"] = frame["atr_ratio"]
    frame["volume_ma5"] = frame["volume"].rolling(5, min_periods=5).mean()
    frame["volume_ma20"] = frame["volume"].rolling(20, min_periods=20).mean()
    frame["volume_ratio_5d"] = frame["volume_ma5"].div(frame["volume_ma20"])
    frame["volume_ratio_20d"] = frame["volume"].div(frame["volume_ma20"])
    frame["ema20"] = close.ewm(span=20, adjust=False).mean()
    frame["ema50"] = close.ewm(span=50, adjust=False).mean()
    frame["price_vs_ema20_pct"] = close.div(frame["ema20"]).sub(1)
    frame["price_vs_ema50"] = close.div(frame["ema50"]).sub(1)
    frame["rsi14"] = calculate_rsi_series(close, 14)
    frame["rsi_slope_5d"] = frame["rsi14"] - frame["rsi14"].shift(5)
    frame["volume_spike_flag"] = (frame["volume"] > (frame["volume_ma20"] * 2)).astype(float)
    frame.loc[frame.index < 19, "price_vs_ema20_pct"] = np.nan
    frame.loc[frame.index < 49, "price_vs_ema50"] = np.nan
    frame.loc[frame["volume_ma20"].isna(), "volume_spike_flag"] = np.nan
    frame["return_5d_cross_section_rank"] = 0.5
    frame["future_return_5d"] = close.shift(-5).div(close).sub(1)
    return frame


def label_counts(frame: pd.DataFrame, label_column: str) -> dict[str, object]:
    labels = CLASS_ORDER if set(frame[label_column].dropna().unique()).issubset(set(CLASS_ORDER)) else sorted(frame[label_column].dropna().unique())
    counts = frame[label_column].value_counts().reindex(labels, fill_value=0)
    total = int(counts.sum())
    return {
        "counts": {str(label): int(counts[label]) for label in labels},
        "shares": {str(label): round(float(counts[label] / total), 6) if total else 0.0 for label in labels},
    }


def build_dataset(ticker: str) -> pd.DataFrame:
    raw = load_raw_db_prices(ticker)
    canonical = canonicalize_prices(raw)
    dataset = add_technical_features(canonical)
    regime = build_ihsg_regime(IHSG_CSV).rename(columns={"reference_date": "date"})
    dataset = dataset.merge(regime, on="date", how="left")
    dataset["ticker"] = ticker
    dataset["reference_date"] = dataset["date"]
    dataset["prediction_feature_version"] = "volatile_stock_special_v1_canonical_db"
    return dataset


def evaluate(frame: pd.DataFrame, label_column: str, max_folds: int = 8) -> dict[str, object]:
    required = ["reference_date", label_column, *FEATURE_COLUMNS]
    eval_frame = frame[required].dropna().copy()
    eval_frame = eval_frame.sort_values("reference_date")
    class_labels = infer_class_labels(eval_frame[label_column])
    class_probabilities = eval_frame[label_column].value_counts(normalize=True).reindex(class_labels, fill_value=0).to_dict()
    unique_dates = sorted(eval_frame["reference_date"].drop_duplicates().tolist())
    folds = build_folds(unique_dates, min_train_days=252, test_window_days=126)[-max_folds:]
    factories = model_factories(class_probabilities, class_labels, "balanced", "balanced_subsample")
    models = []
    for model_name in ["logistic_regression", "random_forest", "random_baseline", "majority_class"]:
        fold_metrics = []
        fold_rows = []
        for fold in folds:
            train_df = eval_frame[eval_frame["reference_date"] <= fold.train_end]
            test_df = eval_frame[(eval_frame["reference_date"] >= fold.test_start) & (eval_frame["reference_date"] <= fold.test_end)]
            estimator = factories[model_name](FEATURE_COLUMNS)
            estimator.fit(train_df[FEATURE_COLUMNS], train_df[label_column])
            predictions = estimator.predict(test_df[FEATURE_COLUMNS])
            metrics = evaluate_predictions(test_df[label_column], predictions, class_labels)
            fold_metrics.append(metrics)
            fold_rows.append({"fold": asdict(fold), "train_rows": int(len(train_df)), "test_rows": int(len(test_df)), "metrics": metrics})
        models.append({"model_name": model_name, "mean_metrics": mean_metrics(fold_metrics), "fold_metrics": fold_rows})
    models.sort(key=lambda row: (row["mean_metrics"].get("f1_macro", 0), row["mean_metrics"].get("directional_accuracy", 0)), reverse=True)
    return {
        "label_column": label_column,
        "rows_after_dropna": int(len(eval_frame)),
        "date_start": str(eval_frame["reference_date"].min().date()),
        "date_end": str(eval_frame["reference_date"].max().date()),
        "fold_count": int(len(folds)),
        "class_labels": [str(label) for label in class_labels],
        "label_distribution": label_counts(eval_frame, label_column),
        "models": models,
        "best_model": models[0],
    }


def characterize_dewa_stale(frame: pd.DataFrame) -> dict[str, object]:
    work = frame[["reference_date", "close", "volume", "future_return_5d"]].dropna().copy()
    work["is_stale_5d"] = work["future_return_5d"].abs() < 1e-12
    runs = []
    current_state = None
    start = None
    rows = []
    for row in work.itertuples(index=False):
        state = bool(row.is_stale_5d)
        if current_state is None:
            current_state = state
            start = row.reference_date
            rows = [row]
        elif state == current_state:
            rows.append(row)
        else:
            runs.append({"is_stale_5d": current_state, "start": str(start.date()), "end": str(rows[-1].reference_date.date()), "length": len(rows)})
            current_state = state
            start = row.reference_date
            rows = [row]
    if rows:
        runs.append({"is_stale_5d": current_state, "start": str(start.date()), "end": str(rows[-1].reference_date.date()), "length": len(rows)})
    stale = work[work["is_stale_5d"]]
    moving = work[~work["is_stale_5d"]]
    return {
        "rows": int(len(work)),
        "stale_5d_rows": int(len(stale)),
        "stale_5d_share": round(float(len(stale) / len(work)), 6) if len(work) else 0.0,
        "avg_volume_stale": round(float(stale["volume"].mean()), 2) if len(stale) else None,
        "avg_volume_moving": round(float(moving["volume"].mean()), 2) if len(moving) else None,
        "longest_stale_runs": sorted([run for run in runs if run["is_stale_5d"]], key=lambda row: row["length"], reverse=True)[:10],
    }


def write_dataset(frame: pd.DataFrame, path: Path) -> None:
    columns = [
        "ticker", "reference_date", "open", "high", "low", "close", "volume", "source", "future_return_5d",
        *FEATURE_COLUMNS, "label_bumi_fixed_2_7pct", "label_dewa_move_0_5pct", "label_dewa_atr0_5_h5d", "label_dewa_atr0_75_h5d",
        "prediction_feature_version",
    ]
    available = [column for column in columns if column in frame.columns]
    output = frame[available].copy()
    output["reference_date"] = pd.to_datetime(output["reference_date"]).dt.strftime("%Y-%m-%d")
    for column in output.select_dtypes(include=["float", "float64"]).columns:
        output[column] = output[column].round(6)
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False)


def assessment(result: dict[str, object]) -> str:
    best = result["best_model"]
    majority = next(row for row in result["models"] if row["model_name"] == "majority_class")
    delta = best["mean_metrics"]["f1_macro"] - majority["mean_metrics"]["f1_macro"]
    if best["model_name"] in {"majority_class", "random_baseline"}:
        return f"no_clear_signal: best comparator is {best['model_name']} macro_f1={best['mean_metrics']['f1_macro']:.4f}, directional_accuracy={best['mean_metrics']['directional_accuracy']:.4f}; learned models did not beat trivial baseline cleanly."
    if delta >= 0.03:
        strength = "meaningful"
    elif delta > 0:
        strength = "marginal"
    else:
        strength = "no_clear_signal"
    return f"{strength}: best={best['model_name']} macro_f1={best['mean_metrics']['f1_macro']:.4f}, directional_accuracy={best['mean_metrics']['directional_accuracy']:.4f}, delta_macro_f1_vs_majority={delta:+.4f}."


def write_report(path: Path, title: str, summary: dict[str, object]) -> None:
    lines = [title, "=" * len(title), "", "Scope: prediction research only; no strategy, P&L, or trading recommendation.", "Data path: canonical DB price selection matching StockPrice canonical source priority.", ""]
    lines.extend([f"Dataset rows: {summary['dataset_rows']}", f"Date range: {summary['date_start']} -> {summary['date_end']}", ""])
    if "stale_characterization" in summary:
        stale = summary["stale_characterization"]
        lines.extend(["DEWA Stale 5D Characterization", "-----------------------------", f"Stale rows/share: {stale['stale_5d_rows']}/{stale['rows']} ({stale['stale_5d_share']:.4f})", f"Average volume stale vs moving: {stale['avg_volume_stale']} vs {stale['avg_volume_moving']}", "Longest stale runs:"])
        for run in stale["longest_stale_runs"][:5]:
            lines.append(f"- {run['start']} -> {run['end']}: {run['length']} rows")
        lines.append("")
    lines.extend(["Evaluation Results", "------------------", "experiment,label_distribution,best_model,macro_f1,directional_accuracy,majority_macro_f1,random_macro_f1,assessment"])
    for name, result in summary["evaluations"].items():
        majority = next(row for row in result["models"] if row["model_name"] == "majority_class")
        random = next(row for row in result["models"] if row["model_name"] == "random_baseline")
        best = result["best_model"]
        lines.append(
            f"{name},{json.dumps(result['label_distribution']['shares'], sort_keys=True)},{best['model_name']},{best['mean_metrics']['f1_macro']:.4f},{best['mean_metrics']['directional_accuracy']:.4f},{majority['mean_metrics']['f1_macro']:.4f},{random['mean_metrics']['f1_macro']:.4f},{assessment(result)}"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for ticker in ["BUMI", "DEWA"]:
        dataset = build_dataset(ticker)
        dataset["label_bumi_fixed_2_7pct"] = label_direction(dataset["future_return_5d"].astype(float), 0.027)
        dataset["label_dewa_move_0_5pct"] = np.where(dataset["future_return_5d"].abs() > 0.005, "move", "no_move")
        dataset["label_dewa_atr0_5_h5d"] = np.where(dataset["future_return_5d"] > dataset["atr14_pct"] * 0.5, "up", np.where(dataset["future_return_5d"] < -dataset["atr14_pct"] * 0.5, "down", "flat"))
        dataset["label_dewa_atr0_75_h5d"] = np.where(dataset["future_return_5d"] > dataset["atr14_pct"] * 0.75, "up", np.where(dataset["future_return_5d"] < -dataset["atr14_pct"] * 0.75, "down", "flat"))
        dataset_path = OUTPUT_DIR / f"dataset_{ticker.lower()}_special.csv"
        write_dataset(dataset, dataset_path)
        summary = {
            "ticker": ticker,
            "dataset_path": str(dataset_path),
            "dataset_rows": int(len(dataset)),
            "date_start": str(dataset["reference_date"].min().date()),
            "date_end": str(dataset["reference_date"].max().date()),
            "source_distribution": dataset["source"].fillna("").value_counts().to_dict(),
            "feature_columns": FEATURE_COLUMNS,
            "evaluations": {},
        }
        if ticker == "BUMI":
            summary["evaluations"]["bumi_fixed_2_7pct"] = evaluate(dataset, "label_bumi_fixed_2_7pct")
        else:
            summary["stale_characterization"] = characterize_dewa_stale(dataset)
            summary["evaluations"]["dewa_move_0_5pct"] = evaluate(dataset, "label_dewa_move_0_5pct")
            summary["evaluations"]["dewa_atr0_5_h5d"] = evaluate(dataset, "label_dewa_atr0_5_h5d")
            summary["evaluations"]["dewa_atr0_75_h5d"] = evaluate(dataset, "label_dewa_atr0_75_h5d")
        summaries[ticker] = summary
        json_path = OUTPUT_DIR / f"model_comparison_{ticker.lower()}_special.json"
        json_path.write_text(json.dumps(summary, indent=2, default=str) + "\n")
        write_report(OUTPUT_DIR / f"model_comparison_{ticker.lower()}_special.txt", f"{ticker} Special Volatile Stock Prediction Research", summary)

    comparison = {
        "v6a_official_10_ticker_blue_chip": V6A_REFERENCE,
        "bumi_special": {
            "best": summaries["BUMI"]["evaluations"]["bumi_fixed_2_7pct"]["best_model"],
            "assessment": assessment(summaries["BUMI"]["evaluations"]["bumi_fixed_2_7pct"]),
        },
        "dewa_special": {
            name: {"best": result["best_model"], "assessment": assessment(result)}
            for name, result in summaries["DEWA"]["evaluations"].items()
        },
    }
    (OUTPUT_DIR / "model_comparison_volatile_special_summary.json").write_text(json.dumps(comparison, indent=2, default=str) + "\n")

    lines = ["V6A vs Volatile Stock Special Research", "=======================================", "", "scope,experiment,best_model,macro_f1,directional_accuracy,assessment", f"V6A official,10ticker_technical,random_forest,{V6A_REFERENCE['macro_f1']:.4f},{V6A_REFERENCE['directional_accuracy']:.4f},official baseline from v6a_baseline_decision.md"]
    bumi = summaries["BUMI"]["evaluations"]["bumi_fixed_2_7pct"]
    lines.append(f"BUMI special,fixed_2_7pct,{bumi['best_model']['model_name']},{bumi['best_model']['mean_metrics']['f1_macro']:.4f},{bumi['best_model']['mean_metrics']['directional_accuracy']:.4f},{assessment(bumi)}")
    for name, result in summaries["DEWA"]["evaluations"].items():
        lines.append(f"DEWA special,{name},{result['best_model']['model_name']},{result['best_model']['mean_metrics']['f1_macro']:.4f},{result['best_model']['mean_metrics']['directional_accuracy']:.4f},{assessment(result)}")
    (OUTPUT_DIR / "model_comparison_volatile_special_summary.txt").write_text("\n".join(lines) + "\n")
    print("Wrote special volatile stock research outputs:")
    for path in [
        OUTPUT_DIR / "dataset_bumi_special.csv",
        OUTPUT_DIR / "dataset_dewa_special.csv",
        OUTPUT_DIR / "model_comparison_bumi_special.txt",
        OUTPUT_DIR / "model_comparison_bumi_special.json",
        OUTPUT_DIR / "model_comparison_dewa_special.txt",
        OUTPUT_DIR / "model_comparison_dewa_special.json",
        OUTPUT_DIR / "model_comparison_volatile_special_summary.txt",
        OUTPUT_DIR / "model_comparison_volatile_special_summary.json",
    ]:
        print(f"- {path}")


if __name__ == "__main__":
    main()
