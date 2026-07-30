#!/usr/bin/env python3
"""Fase Y: does adding MACD/Bollinger/Stochastic/ADX/VWAP/OBV as CONTINUOUS ML features help V6A?

Context: DecisionSupportService.php already computes these 6 indicators, but only for the
"Indikator Teknikal Lanjutan" DISPLAY panel and the DSS composite score -- they were never fed
into the actual V6A/V6B walk-forward prediction pipeline (V2_NO_SENTIMENT_FEATURE_COLUMNS in
train_prediction_models.py has none of them). Fase T (technical indicator survey, threshold rules)
and Fase W (composite confluence score) already tested these indicators as discrete signals/scores
and found no OOS edge on the 10 official tickers. This experiment is a different question: does
adding them as raw CONTINUOUS features let RandomForest itself find nonlinear structure the
threshold-rule versions missed?

Method:
  - Same 10 official tickers, same walk-forward settings as production V6A
    (min_train_days=252, test_window_days=126, max_folds=8), same purge_days=5 (label horizon)
    discipline introduced in Fase S5 to avoid forward-label leakage.
  - Baseline = V2_NO_SENTIMENT_FEATURE_COLUMNS (current production feature set).
  - Candidate = baseline + 6 new continuous indicator features (macd_hist, bb_percent_b,
    stoch_k, adx14, vwap_distance_pct, obv_roc_20d), computed from data/stocks/{TICKER}.csv
    (the same OHLCV source of truth used by ResearchPredictionFeatureService for training).
  - Both evaluated on the IDENTICAL folds (same dates), same RandomForest hyperparameters as
    build_random_forest_pipeline(), so the only difference is feature columns.
  - Reported as delta macro-F1 / delta directional-accuracy, mean across folds -- not cherry-picked
    from a single fold.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from train_prediction_models import (
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    build_folds,
    build_random_forest_pipeline,
    evaluate_predictions,
    infer_class_labels,
    mean_metrics,
)

OFFICIAL_TICKERS = ["BBCA", "BBRI", "BMRI", "TLKM", "ASII", "GOTO", "INDF", "ICBP", "ADRO", "UNVR"]
DATASET_PATH = Path("output/prediction_research/dataset_v6a.csv")
STOCK_DIR = Path("data/stocks")
LABEL_COLUMN = "label_v2"
PURGE_DAYS = 5  # matches label_v2's 5-day-ahead horizon (Fase S5 discipline)
MIN_TRAIN_DAYS = 252
TEST_WINDOW_DAYS = 126
MAX_FOLDS = 8

NEW_INDICATOR_COLUMNS = [
    "macd_hist",
    "bb_percent_b",
    "stoch_k",
    "adx14",
    "vwap_distance_pct",
    "obv_roc_20d",
]

REPORT_JSON = Path("output/prediction_research/dss_indicator_ml_feature_experiment.json")
REPORT_TXT = Path("output/prediction_research/dss_indicator_ml_feature_experiment.txt")


def macd_hist(close: pd.Series) -> pd.Series:
    line = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    signal = line.ewm(span=9, adjust=False).mean()
    return line - signal


def bollinger_percent_b(close: pd.Series, period: int = 20, mult: float = 2.0) -> pd.Series:
    mid = close.rolling(period).mean()
    sd = close.rolling(period).std()
    upper, lower = mid + mult * sd, mid - mult * sd
    return (close - lower) / (upper - lower).replace(0, np.nan)


def stochastic_k(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    lowest = low.rolling(period).min()
    highest = high.rolling(period).max()
    return 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def vwap_distance_pct(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 20) -> pd.Series:
    typical = (high + low + close) / 3
    vwap = (typical * volume).rolling(period).sum() / volume.rolling(period).sum().replace(0, np.nan)
    return 100 * (close - vwap) / vwap.replace(0, np.nan)


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    return (np.sign(close.diff()).fillna(0) * volume).cumsum()


def obv_roc_20d(close: pd.Series, volume: pd.Series, period: int = 20) -> pd.Series:
    o = obv(close, volume)
    return o.pct_change(period).replace([np.inf, -np.inf], np.nan)


def build_indicator_frame(ticker: str) -> pd.DataFrame:
    path = STOCK_DIR / f"{ticker}.csv"
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    c, h, l, v = df["adj_close"], df["high"], df["low"], df["volume"]

    out = pd.DataFrame({
        "ticker": ticker,
        "reference_date": df["date"],
        "macd_hist": macd_hist(c),
        "bb_percent_b": bollinger_percent_b(c),
        "stoch_k": stochastic_k(h, l, c),
        "adx14": adx(h, l, c),
        "vwap_distance_pct": vwap_distance_pct(h, l, c, v),
        "obv_roc_20d": obv_roc_20d(c, v),
    })
    return out


def run_walk_forward(frame: pd.DataFrame, feature_columns: list[str]) -> dict[str, object]:
    frame = frame.dropna(subset=[LABEL_COLUMN]).copy()
    frame["reference_date"] = pd.to_datetime(frame["reference_date"])
    unique_dates = sorted(frame["reference_date"].drop_duplicates().tolist())
    folds = build_folds(unique_dates, MIN_TRAIN_DAYS, TEST_WINDOW_DAYS, purge_days=PURGE_DAYS)
    folds = folds[-MAX_FOLDS:] if len(folds) > MAX_FOLDS else folds

    class_labels = infer_class_labels(frame[LABEL_COLUMN])
    fold_metrics = []
    for fold in folds:
        train = frame[frame["reference_date"] <= fold.train_end]
        test = frame[(frame["reference_date"] >= fold.test_start) & (frame["reference_date"] <= fold.test_end)]
        if train.empty or test.empty:
            continue
        model = build_random_forest_pipeline(feature_columns, class_weight="balanced_subsample")
        model.fit(train[feature_columns], train[LABEL_COLUMN])
        preds = model.predict(test[feature_columns])
        metrics = evaluate_predictions(test[LABEL_COLUMN], preds, class_labels)
        fold_metrics.append({
            **metrics,
            "fold_train_end": str(fold.train_end.date()),
            "fold_test_start": str(fold.test_start.date()),
            "fold_test_end": str(fold.test_end.date()),
            "n_test_rows": int(len(test)),
        })

    numeric_only = [
        {k: v for k, v in row.items() if k not in ("fold_train_end", "fold_test_start", "fold_test_end")}
        for row in fold_metrics
    ]
    return {
        "n_folds": len(fold_metrics),
        "fold_metrics": fold_metrics,
        "mean_metrics": mean_metrics(numeric_only) if numeric_only else {},
    }


def main() -> None:
    base = pd.read_csv(DATASET_PATH, parse_dates=["reference_date"])
    base = base[base["ticker"].isin(OFFICIAL_TICKERS)].copy()

    indicator_frames = [build_indicator_frame(ticker) for ticker in OFFICIAL_TICKERS]
    indicators = pd.concat(indicator_frames, ignore_index=True)
    indicators["reference_date"] = pd.to_datetime(indicators["reference_date"])

    merged = base.merge(indicators, on=["ticker", "reference_date"], how="left")
    coverage = merged[NEW_INDICATOR_COLUMNS].notna().all(axis=1).mean()

    baseline_result = run_walk_forward(merged, V2_NO_SENTIMENT_FEATURE_COLUMNS)
    candidate_columns = V2_NO_SENTIMENT_FEATURE_COLUMNS + NEW_INDICATOR_COLUMNS
    candidate_result = run_walk_forward(merged, candidate_columns)

    baseline_mean = baseline_result["mean_metrics"]
    candidate_mean = candidate_result["mean_metrics"]
    delta_macro_f1 = candidate_mean.get("f1_macro", float("nan")) - baseline_mean.get("f1_macro", float("nan"))
    delta_accuracy = candidate_mean.get("directional_accuracy", float("nan")) - baseline_mean.get("directional_accuracy", float("nan"))

    report = {
        "experiment": "dss_indicator_ml_feature_experiment",
        "official_tickers": OFFICIAL_TICKERS,
        "new_indicator_columns": NEW_INDICATOR_COLUMNS,
        "row_coverage_with_all_new_indicators": float(coverage),
        "purge_days": PURGE_DAYS,
        "min_train_days": MIN_TRAIN_DAYS,
        "test_window_days": TEST_WINDOW_DAYS,
        "max_folds": MAX_FOLDS,
        "baseline": {
            "feature_columns": V2_NO_SENTIMENT_FEATURE_COLUMNS,
            "n_folds": baseline_result["n_folds"],
            "mean_metrics": baseline_mean,
        },
        "candidate": {
            "feature_columns": candidate_columns,
            "n_folds": candidate_result["n_folds"],
            "mean_metrics": candidate_mean,
        },
        "delta_macro_f1": delta_macro_f1,
        "delta_directional_accuracy": delta_accuracy,
    }

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    lines = [
        "DSS Indicator ML Feature Experiment (Fase Y)",
        "=============================================",
        "",
        f"10 official tickers: {', '.join(OFFICIAL_TICKERS)}",
        f"Row coverage with all 6 new indicators non-null: {coverage:.1%}",
        f"purge_days={PURGE_DAYS}, min_train_days={MIN_TRAIN_DAYS}, test_window_days={TEST_WINDOW_DAYS}, max_folds={MAX_FOLDS}",
        "",
        f"Baseline (V2_NO_SENTIMENT_FEATURE_COLUMNS, {baseline_result['n_folds']} folds):",
        f"  macro_f1            = {baseline_mean.get('f1_macro', float('nan')):.4f}",
        f"  directional_accuracy = {baseline_mean.get('directional_accuracy', float('nan')):.4f}",
        "",
        f"Candidate (baseline + MACD/BB/Stochastic/ADX/VWAP/OBV, {candidate_result['n_folds']} folds):",
        f"  macro_f1            = {candidate_mean.get('f1_macro', float('nan')):.4f}",
        f"  directional_accuracy = {candidate_mean.get('directional_accuracy', float('nan')):.4f}",
        "",
        f"Delta macro_f1            = {delta_macro_f1:+.4f}",
        f"Delta directional_accuracy = {delta_accuracy:+.4f}",
    ]
    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
