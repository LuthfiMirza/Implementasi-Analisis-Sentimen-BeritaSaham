#!/usr/bin/env python3
"""Diagnose why walk-forward accuracy sits around 38-40%: how much real edge does the model have
over naive baselines (majority-class / random), and which features actually carry signal?

Reuses build_horizon_dataset/run_walk_forward from run_multi_horizon_experiment.py so the exact
same rows/folds/purge-gap are used -- baselines and models are compared apples-to-apples.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from run_multi_horizon_experiment import build_horizon_dataset, run_walk_forward, DATASET_PATH  # noqa: E402
from train_prediction_models import (  # noqa: E402
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    MajorityClassModel,
    RandomBaselineModel,
    build_random_forest_pipeline,
)

REPORT_JSON = Path("output/prediction_research/prediction_accuracy_diagnosis.json")
REPORT_TXT = Path("output/prediction_research/prediction_accuracy_diagnosis.txt")


def majority_factory(_feature_columns):
    return MajorityClassModel()


def make_random_factory(class_probabilities, class_labels):
    def factory(_feature_columns):
        return RandomBaselineModel(class_probabilities, class_labels)
    return factory


def main() -> None:
    dataset = pd.read_csv(DATASET_PATH)
    dataset["reference_date"] = pd.to_datetime(dataset["reference_date"])
    features = dataset[["ticker", "reference_date", *V2_NO_SENTIMENT_FEATURE_COLUMNS]].copy()

    lines = ["Diagnosis: why is walk-forward accuracy ~38-40%?", "=" * 55, ""]
    results = {}

    for horizon in [1, 3]:
        horizon_frame, threshold = build_horizon_dataset(features, horizon)
        label_probs = horizon_frame["label"].value_counts(normalize=True).to_dict()
        class_labels = sorted(label_probs.keys())

        lines.append(f"--- horizon={horizon}d (threshold={threshold:.4f}) ---")
        lines.append(f"label shares: {label_probs}")

        horizon_results = {}
        for name, factory in [
            ("majority_class", majority_factory),
            ("random_baseline", make_random_factory(label_probs, class_labels)),
            ("random_forest", build_random_forest_pipeline),
        ]:
            result = run_walk_forward(horizon_frame, V2_NO_SENTIMENT_FEATURE_COLUMNS, factory, purge_days=horizon)
            if "error" in result:
                lines.append(f"  {name}: SKIPPED ({result['error']})")
                continue
            m = result["mean_metrics"]
            lines.append(f"  {name:18s} macro_f1={m['f1_macro']:.4f}  directional_accuracy={m['directional_accuracy']:.4f}")
            horizon_results[name] = {"macro_f1": m["f1_macro"], "directional_accuracy": m["directional_accuracy"]}

        if "random_forest" in horizon_results and "majority_class" in horizon_results:
            edge_acc = horizon_results["random_forest"]["directional_accuracy"] - horizon_results["majority_class"]["directional_accuracy"]
            edge_f1 = horizon_results["random_forest"]["macro_f1"] - horizon_results["majority_class"]["macro_f1"]
            lines.append(f"  => edge of random_forest over majority_class: accuracy {edge_acc:+.4f}, macro_f1 {edge_f1:+.4f}")
            horizon_results["rf_edge_over_majority"] = {"accuracy": edge_acc, "macro_f1": edge_f1}

        lines.append("")
        results[f"h{horizon}d"] = horizon_results

    # Feature importance: fit RF on the FULL h+3 dataset (not walk-forward -- purely descriptive,
    # to see which features the model actually leans on).
    horizon_frame, _ = build_horizon_dataset(features, 3)
    horizon_frame = horizon_frame.dropna(subset=[*V2_NO_SENTIMENT_FEATURE_COLUMNS, "label"])
    model = build_random_forest_pipeline(V2_NO_SENTIMENT_FEATURE_COLUMNS)
    model.fit(horizon_frame[V2_NO_SENTIMENT_FEATURE_COLUMNS], horizon_frame["label"])
    importances = model.named_steps["model"].feature_importances_
    ranked = sorted(zip(V2_NO_SENTIMENT_FEATURE_COLUMNS, importances.tolist()), key=lambda x: x[1], reverse=True)

    lines.append("--- feature importance (RandomForest, full h+3 dataset, descriptive only) ---")
    for name, importance in ranked:
        lines.append(f"  {name:35s} {importance:.4f}")
    results["feature_importance_h3d"] = ranked

    REPORT_TXT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
