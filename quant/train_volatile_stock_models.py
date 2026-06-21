#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import pandas as pd

from train_prediction_models import (
    build_logistic_pipeline,
    build_random_forest_pipeline,
    extract_model_insights,
    infer_class_labels,
)
from run_special_volatile_stock_research import FEATURE_COLUMNS

JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
DEFAULT_OUTPUT_DIR = Path("storage/app/prediction")

MODEL_SPECS = {
    "bumi_technical": {
        "version": "bumi_special_random_forest_fixed_2_7pct_final",
        "artifact_name": "model_bumi_technical.joblib",
        "metadata_name": "model_bumi_technical_metadata.json",
        "dataset": Path("output/prediction_research/dataset_bumi_special.csv"),
        "ticker": "BUMI",
        "label_column": "label_bumi_fixed_2_7pct",
        "label_type": "directional_fixed_threshold",
        "label_threshold": 0.027,
        "algorithm": "random_forest",
        "scenario_name": "bumi_technical_fixed_2_7pct",
        "research_report_json": Path("output/prediction_research/model_comparison_bumi_special.json"),
        "research_report_txt": Path("output/prediction_research/model_comparison_bumi_special.txt"),
        "research_summary": {
            "macro_f1": 0.3742,
            "directional_accuracy": 0.4216,
            "majority_macro_f1": 0.1541,
            "majority_directional_accuracy": 0.3036,
            "baseline_comparison": "wins_both_metrics_vs_majority",
        },
    },
    "dewa_regime": {
        "version": "dewa_special_logistic_regression_move_no_move_0_5pct_final",
        "artifact_name": "model_dewa_regime.joblib",
        "metadata_name": "model_dewa_regime_metadata.json",
        "dataset": Path("output/prediction_research/dataset_dewa_special.csv"),
        "ticker": "DEWA",
        "label_column": "label_dewa_move_0_5pct",
        "label_type": "move_vs_no_move",
        "label_threshold": 0.005,
        "algorithm": "logistic_regression",
        "scenario_name": "dewa_regime_move_no_move_0_5pct",
        "research_report_json": Path("output/prediction_research/model_comparison_dewa_special.json"),
        "research_report_txt": Path("output/prediction_research/model_comparison_dewa_special.txt"),
        "research_summary": {
            "macro_f1": 0.5751,
            "directional_accuracy": 0.8532,
            "majority_macro_f1": 0.1544,
            "majority_directional_accuracy": 0.2183,
            "baseline_comparison": "wins_both_metrics_vs_majority",
            "important_note": "This is a regime model for move/no_move detection, not an up/down/flat directional model.",
        },
    },
    "dewa_technical": {
        "version": "dewa_special_logistic_regression_atr0_5_directional_final",
        "artifact_name": "model_dewa_technical.joblib",
        "metadata_name": "model_dewa_technical_metadata.json",
        "dataset": Path("output/prediction_research/dataset_dewa_special.csv"),
        "ticker": "DEWA",
        "label_column": "label_dewa_atr0_5_h5d",
        "label_type": "directional_atr_threshold",
        "atr_multiplier": 0.5,
        "algorithm": "logistic_regression",
        "scenario_name": "dewa_technical_atr0_5_directional",
        "research_report_json": Path("output/prediction_research/model_comparison_dewa_special.json"),
        "research_report_txt": Path("output/prediction_research/model_comparison_dewa_special.txt"),
        "research_summary": {
            "macro_f1": 0.3264,
            "directional_accuracy": 0.4067,
            "majority_macro_f1": 0.2188,
            "majority_directional_accuracy": 0.5000,
            "baseline_comparison": "partial_win_macro_f1_only",
            "important_note": "Directional signal is weak/moderate; directional accuracy is below the majority-class baseline in walk-forward evaluation.",
        },
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train final production artifacts for BUMI and DEWA special volatile-stock models.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--variant", choices=["all", *MODEL_SPECS.keys()], default="all")
    parser.add_argument("--sample-rows", type=int, default=None, help="Optional smoke-test row limit; do not use for production artifacts.")
    return parser.parse_args()


def build_estimator(algorithm: str, feature_columns: list[str]):
    if algorithm == "random_forest":
        return build_random_forest_pipeline(feature_columns, class_weight="balanced_subsample")
    if algorithm == "logistic_regression":
        return build_logistic_pipeline(feature_columns, class_weight="balanced")
    raise ValueError(f"Unsupported algorithm: {algorithm}")


def read_research_metrics(path: Path, scenario_name: str) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    evaluations = report.get("evaluations", {})
    scenario_map = {
        "bumi_technical_fixed_2_7pct": "bumi_fixed_2_7pct",
        "dewa_regime_move_no_move_0_5pct": "dewa_move_0_5pct",
        "dewa_technical_atr0_5_directional": "dewa_atr0_5_h5d",
    }
    key = scenario_map.get(scenario_name)
    value = evaluations.get(key) if key else None
    return value if isinstance(value, dict) else None


def train_variant(variant: str, output_dir: Path, sample_rows: int | None = None) -> dict[str, object]:
    spec = MODEL_SPECS[variant]
    dataset_path = Path(spec["dataset"])
    label_column = str(spec["label_column"])
    feature_columns = list(FEATURE_COLUMNS)
    required_columns = ["ticker", "reference_date", label_column, *feature_columns]

    if not dataset_path.is_file():
        raise SystemExit(f"Missing dataset for {variant}: {dataset_path}")

    frame = pd.read_csv(dataset_path, usecols=lambda column: column in required_columns)
    if sample_rows is not None:
        frame = frame.head(sample_rows).copy()

    missing_columns = [column for column in required_columns if column not in frame.columns]
    if missing_columns:
        raise SystemExit(f"Missing required columns for {variant}: {missing_columns}")

    frame = frame.dropna(subset=[label_column]).copy()
    if frame.empty:
        raise SystemExit(f"No training rows available for {variant}")

    class_labels = infer_class_labels(frame[label_column])
    estimator = build_estimator(str(spec["algorithm"]), feature_columns)
    estimator.fit(frame[feature_columns], frame[label_column])

    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / str(spec["artifact_name"])
    metadata_path = output_dir / str(spec["metadata_name"])
    joblib.dump(estimator, artifact_path)

    label_counts = frame[label_column].value_counts().reindex(class_labels, fill_value=0)
    total = int(label_counts.sum())
    metadata = {
        "model_variant": variant,
        "model_version": spec["version"],
        "artifact_path": str(artifact_path),
        "dataset_path": str(dataset_path),
        "dataset_rows": int(len(frame)),
        "ticker": spec["ticker"],
        "date_start": str(pd.to_datetime(frame["reference_date"]).min().date()),
        "date_end": str(pd.to_datetime(frame["reference_date"]).max().date()),
        "trained_at": datetime.now(JAKARTA_TZ).isoformat(),
        "production_training_scope": "all_available_rows" if sample_rows is None else f"sample_first_{sample_rows}_rows",
        "label_column": label_column,
        "label_type": spec["label_type"],
        "label_threshold": spec.get("label_threshold"),
        "atr_multiplier": spec.get("atr_multiplier"),
        "class_order": [str(label) for label in class_labels],
        "label_distribution": {
            "counts": {str(label): int(label_counts[label]) for label in class_labels},
            "shares": {str(label): round(float(label_counts[label] / total), 6) if total else 0.0 for label in class_labels},
        },
        "feature_columns": feature_columns,
        "selected_model": {
            "model_name": spec["algorithm"],
            "scenario_name": spec["scenario_name"],
            "feature_columns": feature_columns,
            "hyperparameters_source": "quant/train_prediction_models.py",
            "insights": extract_model_insights(estimator, feature_columns),
        },
        "research_metrics_reference": read_research_metrics(Path(spec["research_report_json"]), str(spec["scenario_name"])),
        "research_summary": spec["research_summary"],
        "research_report_json": str(spec["research_report_json"]),
        "research_report_txt": str(spec["research_report_txt"]),
        "governance_note": "Prediction research / decision support only; not a trading signal or investment recommendation.",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {
        "variant": variant,
        "artifact_path": str(artifact_path),
        "metadata_path": str(metadata_path),
        "rows": metadata["dataset_rows"],
        "date_start": metadata["date_start"],
        "date_end": metadata["date_end"],
        "sample_artifact": sample_rows is not None,
    }


def main() -> None:
    args = parse_args()
    variants = list(MODEL_SPECS.keys()) if args.variant == "all" else [args.variant]
    output_dir = Path(args.output_dir)
    results = [train_variant(variant, output_dir, args.sample_rows) for variant in variants]
    print(json.dumps({"trained_models": results}, indent=2))


if __name__ == "__main__":
    main()
