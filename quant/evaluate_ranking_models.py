#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from quant.train_prediction_models import (
    V2_NO_SENTIMENT_FEATURE_COLUMNS,
    build_folds,
    build_logistic_pipeline,
    build_random_forest_pipeline,
    parse_class_weight,
)

RANKING_UNIVERSE = ["ADRO", "ASII", "BBCA", "BBRI", "BMRI", "GOTO", "ICBP", "INDF", "TLKM", "UNVR"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate cross-sectional ranking quality from binary up-probability models.")
    parser.add_argument("--dataset", default="output/prediction_research/dataset.csv")
    parser.add_argument("--dataset-ranking", default="output/prediction_research/dataset_ranking.csv")
    parser.add_argument("--metrics-json", default="output/prediction_research/model_ranking_v5.json")
    parser.add_argument("--metrics-txt", default="output/prediction_research/model_ranking_v5.txt")
    parser.add_argument("--test-window-days", type=int, default=126)
    parser.add_argument("--max-folds", type=int, default=8)
    parser.add_argument("--min-train-days", type=int, default=252)
    parser.add_argument("--top-k", type=int, default=3)
    return parser.parse_args()


def build_binary_dataset(df: pd.DataFrame) -> pd.DataFrame:
    ranking_df = df.copy()
    ranking_df["date"] = ranking_df["reference_date"]
    ranking_df["label_binary"] = (ranking_df["label_v2"] == "up").astype(int)
    ranking_df["cross_sectional_rank_actual"] = (
        ranking_df.groupby("reference_date")["future_return_5d"].rank(method="first", ascending=False).astype(int)
    )
    ranking_df["actual_top_half"] = (
        ranking_df.groupby("reference_date")["cross_sectional_rank_actual"].transform(lambda ranks: ranks <= int(np.ceil(len(ranks) / 2)))
    ).astype(int)
    return ranking_df


def build_estimators() -> dict[str, object]:
    return {
        "logistic_regression": build_logistic_pipeline(V2_NO_SENTIMENT_FEATURE_COLUMNS, class_weight="balanced"),
        "random_forest": build_random_forest_pipeline(V2_NO_SENTIMENT_FEATURE_COLUMNS, class_weight="balanced"),
    }


def score_with_estimator(estimator: object, test_df: pd.DataFrame) -> np.ndarray:
    probabilities = estimator.predict_proba(test_df[V2_NO_SENTIMENT_FEATURE_COLUMNS])
    classes = getattr(estimator, "classes_", None)
    if classes is None and hasattr(estimator, "named_steps"):
        classes = estimator.named_steps["model"].classes_
    class_list = list(classes)
    return probabilities[:, class_list.index(1)]


def spearman_rank_correlation(scores: pd.Series, actual_returns: pd.Series) -> float:
    if scores.nunique() <= 1 or actual_returns.nunique() <= 1:
        return 0.0
    return float(scores.rank(method="average", ascending=False).corr(actual_returns.rank(method="average", ascending=False), method="pearson"))


def evaluate_daily_ranking(day_df: pd.DataFrame, score_column: str, top_k: int) -> dict[str, float]:
    sorted_df = day_df.sort_values([score_column, "ticker"], ascending=[False, True]).reset_index(drop=True)
    n = len(sorted_df)
    if n < top_k:
        raise ValueError("Not enough rows to compute top-k metrics.")

    actual_top_half_threshold = int(np.ceil(n / 2))
    top_metrics: dict[str, float] = {}
    for k in range(1, top_k + 1):
        selected = sorted_df.head(k)
        top_metrics[f"top_{k}_precision"] = float((selected["cross_sectional_rank_actual"] <= actual_top_half_threshold).mean())

    long_short_block = sorted_df if n >= top_k * 2 else None
    long_short_spread = None
    if long_short_block is not None:
        top_return = float(long_short_block.head(top_k)["future_return_5d"].mean())
        bottom_return = float(long_short_block.tail(top_k)["future_return_5d"].mean())
        long_short_spread = top_return - bottom_return

    return {
        **top_metrics,
        "spearman": spearman_rank_correlation(sorted_df[score_column], sorted_df["future_return_5d"]),
        "top_1_hit_rate_positive": float(sorted_df.iloc[0]["future_return_5d"] > 0),
        "top_1_return": float(sorted_df.iloc[0]["future_return_5d"]),
        "long_short_spread": float(long_short_spread) if long_short_spread is not None else 0.0,
    }


def aggregate_metrics(rows: list[dict[str, float]]) -> dict[str, float]:
    frame = pd.DataFrame(rows)
    return {column: round(float(frame[column].mean()), 6) for column in frame.columns}


def format_metrics_text(summary: dict[str, object]) -> str:
    lines = [
        "Ranking Model Evaluation",
        "========================",
        "",
        f"Dataset rows: {summary['dataset_rows']}",
        f"Universe: {', '.join(summary['universe'])}",
        f"Date range: {summary['date_start']} -> {summary['date_end']}",
        f"Walk-forward folds: {summary['fold_count']}",
        f"Top-k: {summary['top_k']}",
        "",
        "Model metrics:",
    ]
    for model in summary["models"]:
        metrics = model["overall_metrics"]
        lines.append(
            "- {name}: spearman={spearman:.4f}, long_short={spread:.4f}, top3_precision={top3:.4f}, top1_hit={hit:.4f}".format(
                name=model["model_name"],
                spearman=metrics["spearman"],
                spread=metrics["long_short_spread"],
                top3=metrics["top_3_precision"],
                hit=metrics["top_1_hit_rate_positive"],
            )
        )
    lines.append("")
    lines.append(f"Best ranking model: {summary['selected_model']['model_name']}")
    lines.append(f"Conclusion: {summary['conclusion']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    dataset_path = Path(args.dataset)
    dataset_ranking_path = Path(args.dataset_ranking)
    metrics_json_path = Path(args.metrics_json)
    metrics_txt_path = Path(args.metrics_txt)

    df = pd.read_csv(dataset_path)
    df = df[df["ticker"].isin(RANKING_UNIVERSE)].copy()
    df["reference_date"] = pd.to_datetime(df["reference_date"])
    df = df.sort_values(["reference_date", "ticker"]).reset_index(drop=True)

    ranking_df = build_binary_dataset(df)
    dataset_ranking_path.parent.mkdir(parents=True, exist_ok=True)
    ranking_df.to_csv(dataset_ranking_path, index=False)

    unique_dates = sorted(ranking_df["reference_date"].drop_duplicates().tolist())
    folds = build_folds(unique_dates, args.min_train_days, args.test_window_days)
    if args.max_folds > 0 and len(folds) > args.max_folds:
        folds = folds[-args.max_folds :]
    if not folds:
        raise SystemExit("Not enough history to build ranking folds.")

    model_results: list[dict[str, object]] = []
    random_seed = 42

    for model_name, estimator_template in build_estimators().items():
        fold_summaries: list[dict[str, object]] = []
        all_daily_metrics: list[dict[str, float]] = []
        all_random_daily_metrics: list[dict[str, float]] = []
        all_momentum_daily_metrics: list[dict[str, float]] = []

        for fold in folds:
            train_df = ranking_df[ranking_df["reference_date"] <= fold.train_end].copy()
            test_df = ranking_df[(ranking_df["reference_date"] >= fold.test_start) & (ranking_df["reference_date"] <= fold.test_end)].copy()
            estimator = estimator_template
            estimator.fit(train_df[V2_NO_SENTIMENT_FEATURE_COLUMNS], train_df["label_binary"])
            test_df["model_score"] = score_with_estimator(estimator, test_df)

            rng = np.random.default_rng(random_seed)
            test_df["random_score"] = rng.random(len(test_df))
            test_df["momentum_score"] = test_df["return_5d"]

            model_daily_metrics: list[dict[str, float]] = []
            random_daily_metrics: list[dict[str, float]] = []
            momentum_daily_metrics: list[dict[str, float]] = []

            for _, day_df in test_df.groupby("reference_date", sort=True):
                if len(day_df) < args.top_k * 2:
                    continue
                model_daily_metrics.append(evaluate_daily_ranking(day_df, "model_score", args.top_k))
                random_daily_metrics.append(evaluate_daily_ranking(day_df, "random_score", args.top_k))
                momentum_daily_metrics.append(evaluate_daily_ranking(day_df, "momentum_score", args.top_k))

            if not model_daily_metrics:
                continue

            fold_summary = {
                "fold_start": str(fold.test_start.date()),
                "fold_end": str(fold.test_end.date()),
                "model_metrics": aggregate_metrics(model_daily_metrics),
                "random_metrics": aggregate_metrics(random_daily_metrics),
                "momentum_metrics": aggregate_metrics(momentum_daily_metrics),
            }
            fold_summaries.append(fold_summary)
            all_daily_metrics.extend(model_daily_metrics)
            all_random_daily_metrics.extend(random_daily_metrics)
            all_momentum_daily_metrics.extend(momentum_daily_metrics)

        if not fold_summaries:
            continue

        model_results.append(
            {
                "model_name": model_name,
                "overall_metrics": aggregate_metrics(all_daily_metrics),
                "folds": fold_summaries,
                "comparators": {
                    "random_ranking": aggregate_metrics(all_random_daily_metrics),
                    "momentum_naive": aggregate_metrics(all_momentum_daily_metrics),
                },
            }
        )

    if not model_results:
        raise SystemExit("No ranking models could be evaluated.")

    selected_model = sorted(
        model_results,
        key=lambda row: (
            row["overall_metrics"]["long_short_spread"],
            row["overall_metrics"]["spearman"],
            row["overall_metrics"]["top_3_precision"],
        ),
        reverse=True,
    )[0]

    momentum_better_folds = []
    for fold in selected_model["folds"]:
        if fold["model_metrics"]["long_short_spread"] > fold["momentum_metrics"]["long_short_spread"]:
            momentum_better_folds.append(
                {
                    "fold_start": fold["fold_start"],
                    "fold_end": fold["fold_end"],
                    "model_long_short_spread": fold["model_metrics"]["long_short_spread"],
                    "momentum_long_short_spread": fold["momentum_metrics"]["long_short_spread"],
                }
            )

    momentum_baseline = selected_model["comparators"]["momentum_naive"]
    adds_edge = (
        selected_model["overall_metrics"]["long_short_spread"] > momentum_baseline["long_short_spread"]
        and selected_model["overall_metrics"]["spearman"] > momentum_baseline["spearman"]
    )

    summary = {
        "freeze_date": pd.Timestamp.now(tz="Asia/Jakarta").date().isoformat(),
        "dataset_rows": int(len(ranking_df)),
        "universe": RANKING_UNIVERSE,
        "date_start": str(ranking_df["reference_date"].min().date()),
        "date_end": str(ranking_df["reference_date"].max().date()),
        "top_k": args.top_k,
        "fold_count": len(folds),
        "evaluation_periods": [{"test_start": str(fold.test_start.date()), "test_end": str(fold.test_end.date())} for fold in folds],
        "models": model_results,
        "selected_model": selected_model,
        "momentum_outperformed_folds": momentum_better_folds,
        "conclusion": (
            "ranking model adds edge over momentum naive"
            if adds_edge
            else "ranking model does not add clear edge over momentum naive"
        ),
    }

    metrics_json_path.parent.mkdir(parents=True, exist_ok=True)
    with metrics_json_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    metrics_txt_path.write_text(format_metrics_text(summary), encoding="utf-8")

    print(json.dumps(
        {
            "selected_model": selected_model["model_name"],
            "long_short_spread": selected_model["overall_metrics"]["long_short_spread"],
            "spearman": selected_model["overall_metrics"]["spearman"],
            "top_3_precision": selected_model["overall_metrics"]["top_3_precision"],
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
