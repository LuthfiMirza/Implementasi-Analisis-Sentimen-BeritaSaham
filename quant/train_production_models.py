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
    V2_ALL_FEATURE_COLUMNS,
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    build_logistic_pipeline,
    build_random_forest_pipeline,
    extract_model_insights,
    infer_class_labels,
)


JAKARTA_TZ = ZoneInfo("Asia/Jakarta")
DEFAULT_OUTPUT_DIR = Path("storage/app/prediction")

MODEL_SPECS = {
    "technical": {
        "version": "v6a_technical_random_forest_final",
        "artifact_name": "model_technical_v6a.joblib",
        "metadata_name": "model_technical_v6a_metadata.json",
        "dataset": Path("output/prediction_research/dataset_v6a.csv"),
        "label_column": "label_v2_h5d",
        "feature_columns": V2_NO_SENTIMENT_FEATURE_COLUMNS,
        "algorithm": "random_forest",
        "scenario_name": "technical_only",
        "research_report_json": Path("output/prediction_research/model_comparison_v6a.json"),
        "research_report_txt": Path("output/prediction_research/model_comparison_v6a.txt"),
        "official_baseline": {
            "horizon_days": 5,
            "label_threshold": 0.015,
            "macro_f1": 0.3673,
            "directional_accuracy": 0.4050,
        },
    },
    "technical_sentiment": {
        "version": "v6b_technical_sentiment_logistic_regression_final",
        "artifact_name": "model_technical_sentiment_v6b.joblib",
        "metadata_name": "model_technical_sentiment_v6b_metadata.json",
        "dataset": Path("output/prediction_research/dataset_v6b_10ticker.csv"),
        "label_column": "label_v2",
        "feature_columns": V2_ALL_FEATURE_COLUMNS,
        "algorithm": "logistic_regression",
        "scenario_name": "technical_plus_sentiment",
        "research_report_json": Path("output/prediction_research/model_comparison_v6b.json"),
        "research_report_txt": Path("output/prediction_research/model_comparison_v6b.txt"),
        "official_baseline": {
            "horizon_days": 5,
            "label_threshold": 0.015,
            "sentiment_contribution_basis": "V6B logistic_regression wins 3/3 walk-forward settings with sentiment features.",
        },
    },
}

KNOWN_LIVE_LIMITATIONS = [
    {
        "feature": "return_5d_cross_section_rank",
        "status": "known_limited_live_serving",
        "detail": "Live ResearchPredictionFeatureService currently emits this key as null; training and serving rely on the same SimpleImputer(strategy='median') behavior used in V6 walk-forward research.",
    }
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train final production V6A/V6B prediction artifacts.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--variant", choices=["all", *MODEL_SPECS.keys()], default="all")
    parser.add_argument("--sample-rows", type=int, default=None, help="Optional smoke-test row limit; do not use for production artifacts.")
    return parser.parse_args()


def read_research_metrics(path: Path, variant: str) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    if variant == "technical":
        best = report.get("best_result", {}).get("best_model")
        if isinstance(best, dict):
            return best
    if variant == "technical_sentiment":
        rows = report.get("results", [])
        matches = [
            row for row in rows
            if row.get("scenario") == "technical_plus_sentiment"
            and row.get("algorithm") == "logistic_regression"
        ]
        return {"walk_forward_settings": matches} if matches else None
    return None


def build_estimator(algorithm: str, feature_columns: list[str]):
    if algorithm == "random_forest":
        return build_random_forest_pipeline(feature_columns, class_weight="balanced_subsample")
    if algorithm == "logistic_regression":
        return build_logistic_pipeline(feature_columns, class_weight="balanced")
    raise ValueError(f"Unsupported algorithm: {algorithm}")


def train_variant(variant: str, output_dir: Path, sample_rows: int | None = None) -> dict[str, object]:
    spec = MODEL_SPECS[variant]
    dataset_path = Path(spec["dataset"])
    label_column = str(spec["label_column"])
    feature_columns = list(spec["feature_columns"])
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
        "ticker_count": int(frame["ticker"].nunique()) if "ticker" in frame.columns else None,
        "date_start": str(pd.to_datetime(frame["reference_date"]).min().date()) if "reference_date" in frame.columns else None,
        "date_end": str(pd.to_datetime(frame["reference_date"]).max().date()) if "reference_date" in frame.columns else None,
        "trained_at": datetime.now(JAKARTA_TZ).isoformat(),
        "production_training_scope": "all_available_rows" if sample_rows is None else f"sample_first_{sample_rows}_rows",
        "label_column": label_column,
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
        "official_baseline": spec["official_baseline"],
        "research_metrics_reference": read_research_metrics(Path(spec["research_report_json"]), variant),
        "research_report_json": str(spec["research_report_json"]),
        "research_report_txt": str(spec["research_report_txt"]),
        "known_live_limitations": KNOWN_LIVE_LIMITATIONS,
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
