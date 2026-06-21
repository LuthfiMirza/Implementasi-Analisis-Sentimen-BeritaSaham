#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from rebuild_prediction_research_dataset_v2 import label_direction
from train_prediction_models import (
    CLASS_ORDER,
    RandomBaselineModel,
    MajorityClassModel,
    build_folds,
    build_logistic_pipeline,
    evaluate_predictions,
    infer_class_labels,
    mean_metrics,
)

OUTPUT_DIR = Path("output/prediction_research")
BASE_FEATURES = [
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
NEW_FEATURES = [
    "volume_spike_ratio",
    "overnight_gap_pct",
    "rolling_volatility_5d_vs_20d",
    "consecutive_move_days",
]
EXTENDED_FEATURES = BASE_FEATURES + NEW_FEATURES
OLD_BASELINES = {
    "bumi_fixed_2_7pct": {"macro_f1": 0.3742, "directional_accuracy": 0.4216, "model": "random_forest"},
    "dewa_move_0_5pct": {"macro_f1": 0.5751, "directional_accuracy": 0.8532, "model": "logistic_regression"},
    "dewa_atr0_5_h5d": {"macro_f1": 0.3264, "directional_accuracy": 0.4067, "model": "logistic_regression"},
    "dewa_atr0_75_h5d": {"macro_f1": 0.2877, "directional_accuracy": 0.5466, "model": "random_baseline"},
}


def build_gradient_boosting_pipeline(feature_columns: list[str]) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocess", ColumnTransformer(transformers=[("num", SimpleImputer(strategy="median"), feature_columns)])),
            ("model", HistGradientBoostingClassifier(max_iter=60, learning_rate=0.08, random_state=42)),
        ]
    )

def build_fast_random_forest_pipeline(feature_columns: list[str]) -> Pipeline:
    return Pipeline(
        steps=[
            ("preprocess", ColumnTransformer(transformers=[("num", SimpleImputer(strategy="median"), feature_columns)])),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=30,
                    max_depth=8,
                    min_samples_leaf=20,
                    class_weight="balanced_subsample",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )


class SoftVotingEnsemble:
    def __init__(self, feature_columns: list[str], class_labels: list[object]) -> None:
        self.feature_columns = feature_columns
        self.class_labels = class_labels
        self.models = [
            build_logistic_pipeline(feature_columns, class_weight="balanced"),
            build_fast_random_forest_pipeline(feature_columns),
            build_gradient_boosting_pipeline(feature_columns),
        ]
        self.classes_ = np.array(class_labels)

    def fit(self, x: pd.DataFrame, y: pd.Series) -> "SoftVotingEnsemble":
        fitted = []
        for model in self.models:
            model.fit(x, y)
            fitted.append(model)
        self.models = fitted
        return self

    def predict_proba(self, x: pd.DataFrame) -> np.ndarray:
        aligned = []
        for model in self.models:
            probs = model.predict_proba(x)
            model_classes = list(model.classes_)
            matrix = np.zeros((len(x), len(self.class_labels)), dtype=float)
            for idx, label in enumerate(self.class_labels):
                if label in model_classes:
                    matrix[:, idx] = probs[:, model_classes.index(label)]
            aligned.append(matrix)
        return np.mean(aligned, axis=0)

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        probs = self.predict_proba(x)
        return np.array([self.class_labels[int(np.argmax(row))] for row in probs])


def add_new_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy().sort_values("reference_date").reset_index(drop=True)
    close = frame["close"].astype(float)
    open_ = frame["open"].astype(float)
    volume = frame["volume"].astype(float)
    returns = close.div(close.shift(1)).sub(1)
    frame["volume_spike_ratio"] = volume.div(volume.rolling(20, min_periods=20).mean())
    frame["overnight_gap_pct"] = open_.div(close.shift(1)).sub(1)
    vol5 = returns.rolling(5, min_periods=5).std()
    vol20 = returns.rolling(20, min_periods=20).std()
    frame["rolling_volatility_5d_vs_20d"] = vol5.div(vol20)
    signs = np.sign(returns.fillna(0.0).to_numpy())
    runs: list[float] = []
    current = 0
    previous = 0
    for sign in signs:
        if sign == 0:
            current = 0
        elif sign == previous:
            current += 1
        else:
            current = 1
        runs.append(float(current if sign != 0 else 0))
        previous = sign
    frame["consecutive_move_days"] = runs
    return frame


def add_horizon_labels(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    frame = frame.copy().sort_values("reference_date").reset_index(drop=True)
    close = frame["close"].astype(float)
    for horizon in [3, 10]:
        frame[f"future_return_{horizon}d"] = close.shift(-horizon).div(close).sub(1)
        if ticker == "BUMI":
            threshold = 0.027 * np.sqrt(horizon / 5)
            frame[f"label_bumi_fixed_scaled_h{horizon}d"] = label_direction(frame[f"future_return_{horizon}d"], threshold)
        else:
            scale = np.sqrt(horizon / 5)
            for multiplier in [0.5, 0.75]:
                col = f"label_dewa_atr{str(multiplier).replace('.', '_')}_h{horizon}d"
                threshold = frame["atr14_pct"].astype(float) * multiplier * scale
                frame[col] = np.where(frame[f"future_return_{horizon}d"] > threshold, "up", np.where(frame[f"future_return_{horizon}d"] < -threshold, "down", "flat"))
    return frame


def label_distribution(frame: pd.DataFrame, label_column: str) -> dict[str, object]:
    values = frame[label_column].dropna()
    labels = infer_class_labels(values)
    counts = values.value_counts().reindex(labels, fill_value=0)
    total = int(counts.sum())
    return {
        "counts": {str(label): int(counts[label]) for label in labels},
        "shares": {str(label): round(float(counts[label] / total), 6) if total else 0.0 for label in labels},
    }


def make_model(name: str, feature_columns: list[str], class_probabilities: dict[object, float], class_labels: list[object]):
    if name == "logistic_regression":
        return build_logistic_pipeline(feature_columns, class_weight="balanced")
    if name == "random_forest":
        return build_fast_random_forest_pipeline(feature_columns)
    if name == "gradient_boosting":
        return build_gradient_boosting_pipeline(feature_columns)
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


def baseline_models(result: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    by_name = {row["model_name"]: row for row in result["models"]}
    return by_name["majority_class"], by_name["random_baseline"]


def status_vs_majority(result: dict[str, object]) -> str:
    best = result["best_model"]
    majority, _ = baseline_models(result)
    bm = best["mean_metrics"]
    mm = majority["mean_metrics"]
    if best["model_name"] in {"majority_class", "random_baseline"}:
        return "tidak menang: best model adalah baseline trivial"
    f1 = bm["f1_macro"] > mm["f1_macro"]
    acc = bm["directional_accuracy"] > mm["directional_accuracy"]
    if f1 and acc:
        return "menang kedua metrik vs majority"
    if f1 or acc:
        return "menang sebagian vs majority"
    return "tidak menang vs majority"


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


def row_for_table(scope: str, ticker: str, experiment: str, result: dict[str, object]) -> dict[str, object]:
    best = result["best_model"]
    majority, random = baseline_models(result)
    bm = best["mean_metrics"]
    mm = majority["mean_metrics"]
    rm = random["mean_metrics"]
    return {
        "scope": scope,
        "ticker": ticker,
        "experiment": experiment,
        "label_column": result["label_column"],
        "best_model": best["model_name"],
        "macro_f1": bm["f1_macro"],
        "directional_accuracy": bm["directional_accuracy"],
        "majority_macro_f1": mm["f1_macro"],
        "majority_directional_accuracy": mm["directional_accuracy"],
        "random_macro_f1": rm["f1_macro"],
        "random_directional_accuracy": rm["directional_accuracy"],
        "status_vs_majority": status_vs_majority(result),
        "assessment": improvement_assessment(experiment, result),
        "label_distribution": result["label_distribution"],
    }


def load_dataset(ticker: str) -> pd.DataFrame:
    path = OUTPUT_DIR / f"dataset_{ticker.lower()}_special.csv"
    frame = pd.read_csv(path, parse_dates=["reference_date"])
    frame = add_new_features(frame)
    frame = add_horizon_labels(frame, ticker)
    return frame


def main() -> None:
    datasets = {"BUMI": load_dataset("BUMI"), "DEWA": load_dataset("DEWA")}
    algorithms_all = ["logistic_regression", "random_forest", "gradient_boosting", "soft_voting_ensemble", "random_baseline", "majority_class"]
    algorithms_single = ["logistic_regression", "random_forest", "gradient_boosting", "random_baseline", "majority_class"]
    algorithms_horizon = ["logistic_regression", "random_forest", "random_baseline", "majority_class"]
    results: dict[str, object] = {"methodology": {
        "walk_forward": "min_train_days=252, test_window_days=126, latest 8 folds",
        "metrics": "macro F1 primary, directional_accuracy secondary",
        "new_features": NEW_FEATURES,
        "horizon_threshold_policy": "BUMI fixed threshold scaled by sqrt(horizon/5); DEWA ATR thresholds scaled by sqrt(horizon/5).",
        "estimator_note": "Exploratory RF uses same V6A shape but n_estimators=30 for runtime; no production artifact is replaced. Ensemble is tested on 5D experiments; horizon alternatives use LR/RF plus trivial baselines.",
        "governance": "prediction research only; no strategy/P&L/trading recommendation",
    }, "experiments": [], "table": []}

    experiment_specs = [
        ("BUMI", "bumi_fixed_2_7pct", "label_bumi_fixed_2_7pct"),
        ("DEWA", "dewa_move_0_5pct", "label_dewa_move_0_5pct"),
        ("DEWA", "dewa_atr0_5_h5d", "label_dewa_atr0_5_h5d"),
        ("DEWA", "dewa_atr0_75_h5d", "label_dewa_atr0_75_h5d"),
    ]

    for ticker, experiment, label_column in experiment_specs:
        frame = datasets[ticker]
        for scope, feature_columns, algorithms in [
            ("old_features_all_models", BASE_FEATURES, algorithms_single),
            ("new_features_all_models", EXTENDED_FEATURES, algorithms_single),
            ("new_features_with_ensemble", EXTENDED_FEATURES, algorithms_all),
        ]:
            result = evaluate(frame, label_column, feature_columns, algorithms)
            record = {"scope": scope, "ticker": ticker, "experiment": experiment, "result": result}
            results["experiments"].append(record)
            results["table"].append(row_for_table(scope, ticker, experiment, result))

    horizon_specs = [
        ("BUMI", "bumi_h3_fixed_scaled", "label_bumi_fixed_scaled_h3d"),
        ("BUMI", "bumi_h10_fixed_scaled", "label_bumi_fixed_scaled_h10d"),
        ("DEWA", "dewa_atr0_5_h3d", "label_dewa_atr0_5_h3d"),
        ("DEWA", "dewa_atr0_5_h10d", "label_dewa_atr0_5_h10d"),
        ("DEWA", "dewa_atr0_75_h3d", "label_dewa_atr0_75_h3d"),
        ("DEWA", "dewa_atr0_75_h10d", "label_dewa_atr0_75_h10d"),
    ]
    for ticker, experiment, label_column in horizon_specs:
        result = evaluate(datasets[ticker], label_column, EXTENDED_FEATURES, algorithms_horizon)
        results["experiments"].append({"scope": "horizon_alternative_new_features_ensemble", "ticker": ticker, "experiment": experiment, "result": result})
        results["table"].append(row_for_table("horizon_alternative_new_features_ensemble", ticker, experiment, result))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "model_comparison_volatile_v2.json"
    txt_path = OUTPUT_DIR / "model_comparison_volatile_v2.txt"
    json_path.write_text(json.dumps(results, indent=2, default=str) + "\n")

    lines = [
        "Volatile Stock V2 Feature/Ensemble/Horizon Experiments",
        "======================================================",
        "",
        "Scope: prediction research only; no strategy, P&L, trading signal, or production replacement.",
        "Baseline comparator: model_comparison_bumi_special + model_comparison_dewa_special remain unchanged.",
        "Walk-forward: min_train_days=252, test_window_days=126, latest 8 folds.",
        "Horizon threshold policy: BUMI fixed threshold scaled by sqrt(horizon/5); DEWA ATR thresholds scaled by sqrt(horizon/5).",
        "Improvement rule: claim only if delta >0.02 macro F1 OR >0.02 directional accuracy AND learned model wins both metrics vs majority.",
        "",
        "scope,ticker,experiment,best_model,macro_f1,directional_accuracy,majority_macro_f1,majority_directional_accuracy,random_macro_f1,random_directional_accuracy,status_vs_majority,assessment,label_distribution",
    ]
    for row in results["table"]:
        lines.append(
            ",".join([
                row["scope"], row["ticker"], row["experiment"], row["best_model"],
                f"{row['macro_f1']:.4f}", f"{row['directional_accuracy']:.4f}",
                f"{row['majority_macro_f1']:.4f}", f"{row['majority_directional_accuracy']:.4f}",
                f"{row['random_macro_f1']:.4f}", f"{row['random_directional_accuracy']:.4f}",
                row["status_vs_majority"], row["assessment"], json.dumps(row["label_distribution"]["shares"], sort_keys=True),
            ])
        )

    clear = [row for row in results["table"] if str(row["assessment"]).startswith("clear_improvement")]
    lines.extend(["", "Assessment Summary", "------------------"])
    if clear:
        for row in clear:
            lines.append(f"- CLEAR: {row['scope']} {row['ticker']} {row['experiment']} -> {row['best_model']} macro_f1={row['macro_f1']:.4f}, directional_accuracy={row['directional_accuracy']:.4f}; {row['assessment']}")
    else:
        lines.append("- No new 5D feature/ensemble experiment produced a clear improvement under the predefined rule.")
    lines.append("- Horizon alternatives are exploratory and require separate review before any production artifact replacement.")
    txt_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {txt_path}")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
