#!/usr/bin/env python3
"""Fair same-sample re-check of v3 BUMI candidates vs official RF160 (BASE_FEATURES).

Context: run_bumi_dewa_v3_sentiment_horizon_experiments.py compares its candidates'
macro_f1 directly against OLD_BASELINES, which was computed on a different (larger)
row set because EXTENDED_FEATURES/FULL_FEATURES need extra rolling-window warm-up
rows that BASE_FEATURES does not. This script repeats the "fair subset" check that
model_comparison_volatile_v2_verification.txt already established as required
before claiming any improvement: re-evaluate the official RF160/BASE_FEATURES model
on the exact same eval rows as the new candidate, then compare on identical folds.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from run_bumi_dewa_v3_sentiment_horizon_experiments import (
    FULL_FEATURES,
    load_sentiment_augmented_dataset,
)
from run_volatile_v2_experiments import BASE_FEATURES, EXTENDED_FEATURES
from train_prediction_models import (
    build_folds,
    build_random_forest_pipeline,
    evaluate_predictions,
    infer_class_labels,
    mean_metrics,
)

OUTPUT_DIR = Path("output/prediction_research")


def fair_subset_rf160(frame, label_column: str, candidate_feature_columns: list[str]) -> dict[str, object]:
    candidate_required = ["reference_date", label_column, *candidate_feature_columns]
    candidate_eval_frame = frame[candidate_required].dropna().copy().sort_values("reference_date")
    same_dates = set(candidate_eval_frame["reference_date"].tolist())

    official_required = ["reference_date", label_column, *BASE_FEATURES]
    official_frame = frame[official_required].dropna().copy()
    official_frame = official_frame[official_frame["reference_date"].isin(same_dates)].sort_values("reference_date")

    class_labels = infer_class_labels(official_frame[label_column])
    unique_dates = sorted(official_frame["reference_date"].drop_duplicates().tolist())
    folds = build_folds(unique_dates, min_train_days=252, test_window_days=126)[-8:]

    fold_metrics = []
    for fold in folds:
        train_df = official_frame[official_frame["reference_date"] <= fold.train_end]
        test_df = official_frame[(official_frame["reference_date"] >= fold.test_start) & (official_frame["reference_date"] <= fold.test_end)]
        estimator = build_random_forest_pipeline(BASE_FEATURES, class_weight="balanced_subsample")
        estimator.fit(train_df[BASE_FEATURES], train_df[label_column])
        predictions = estimator.predict(test_df[BASE_FEATURES])
        metrics = evaluate_predictions(test_df[label_column], predictions, class_labels)
        fold_metrics.append(metrics)

    return {
        "rows_official_rf160_same_subset": int(len(official_frame)),
        "rows_candidate_subset": int(len(candidate_eval_frame)),
        "fold_count": int(len(folds)),
        "official_rf160_same_subset_metrics": mean_metrics(fold_metrics),
    }


def main() -> None:
    frame = load_sentiment_augmented_dataset("BUMI")
    label_column = "label_bumi_fixed_2_7pct"

    v3_json = json.loads((OUTPUT_DIR / "model_comparison_volatile_v3_sentiment_horizon.json").read_text())
    candidates = {
        "v3_technical_only_gb_tuning": {"features": EXTENDED_FEATURES, "candidate_macro_f1": None, "candidate_dir_acc": None},
        "v3_technical_plus_sentiment": {"features": FULL_FEATURES, "candidate_macro_f1": None, "candidate_dir_acc": None},
    }
    for exp in v3_json["experiments"]:
        if exp["ticker"] == "BUMI" and exp["experiment"] == "bumi_fixed_2_7pct" and exp["scope"] in candidates:
            best = exp["result"]["best_model"]
            candidates[exp["scope"]]["candidate_macro_f1"] = best["mean_metrics"]["f1_macro"]
            candidates[exp["scope"]]["candidate_dir_acc"] = best["mean_metrics"]["directional_accuracy"]
            candidates[exp["scope"]]["candidate_model_name"] = best["model_name"]

    lines = [
        "BUMI v3 Fair-Subset Verification (vs official RF160 on identical rows)",
        "========================================================================",
        "",
        "Scope: verification only; does not replace production artifacts.",
        "",
    ]
    report: dict[str, object] = {"scope": "verification_only", "ticker": "BUMI", "label_column": label_column, "checks": {}}
    for scope, info in candidates.items():
        result = fair_subset_rf160(frame, label_column, info["features"])
        official = result["official_rf160_same_subset_metrics"]
        macro_delta = info["candidate_macro_f1"] - official["f1_macro"]
        acc_delta = info["candidate_dir_acc"] - official["directional_accuracy"]
        fair_clear = macro_delta > 0.02 or acc_delta > 0.02
        report["checks"][scope] = {
            "candidate_model": info["candidate_model_name"],
            "candidate_macro_f1": info["candidate_macro_f1"],
            "candidate_directional_accuracy": info["candidate_dir_acc"],
            "official_rf160_same_subset_macro_f1": official["f1_macro"],
            "official_rf160_same_subset_directional_accuracy": official["directional_accuracy"],
            "rows_used": result["rows_official_rf160_same_subset"],
            "fair_delta_macro_f1": macro_delta,
            "fair_delta_directional_accuracy": acc_delta,
            "fair_verdict": "clear_improvement_fair_subset" if fair_clear else "no_clear_improvement_fair_subset",
        }
        lines.append(f"## {scope}")
        lines.append(f"- candidate: {info['candidate_model_name']}, macro_f1={info['candidate_macro_f1']:.4f}, dir_acc={info['candidate_dir_acc']:.4f}")
        lines.append(f"- official RF160 (BASE_FEATURES) on identical {result['rows_official_rf160_same_subset']} rows: macro_f1={official['f1_macro']:.4f}, dir_acc={official['directional_accuracy']:.4f}")
        lines.append(f"- fair delta: macro_f1={macro_delta:+.4f}, directional_accuracy={acc_delta:+.4f}")
        lines.append(f"- verdict: {'CLEAR (fair, >0.02)' if fair_clear else 'NOT CLEAR (fair, <=0.02 threshold)'}")
        lines.append("")

    (OUTPUT_DIR / "bumi_v3_fair_subset_verification.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    (OUTPUT_DIR / "bumi_v3_fair_subset_verification.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
