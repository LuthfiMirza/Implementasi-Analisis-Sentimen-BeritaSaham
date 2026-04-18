"""Run a measured threshold sweep for Phase B item 5 candle confirmation.

Example
-------
Preferred execution from project root:

    python3 -m quant.run_phase_b_item5_threshold_sweep \
      --data-dir data \
      --output-dir output \
      --baseline-config output/phase_a_baseline_final.json \
      --metadata-file data/ticker_metadata.csv \
      --thresholds 0.8 1.0 1.2 1.5
"""

from __future__ import annotations

import argparse
import json
import math
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.evaluate_phase_a_real_data import extract_ticker_from_filename, load_price_csv  # noqa: E402
from quant.phase_a import backtest_signal_frame, generate_phase_a_signal  # noqa: E402
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.run_phase_a_threshold_sweep import GROUP_FIELDS, load_metadata, resolve_csv_files  # noqa: E402

DEFAULT_THRESHOLDS = [0.8, 1.0, 1.2, 1.5]
DEFAULT_REFERENCE_THRESHOLD = 1.0
SUPPORTED_METADATA_COLUMNS = ["ticker", "category", "market_cap_group", "sector", "beta_group"]
GROUP_MIN_TICKERS = 2

RESULT_COLUMNS = [
    "ticker",
    "threshold",
    "effective_confirmation_threshold",
    "rows",
    "date_start",
    "date_end",
    "phase_a_applied_threshold",
    "phase_a_applied_strict_mode",
    "baseline_total_trades",
    "candidate_total_trades",
    "delta_total_trades",
    "trade_retention_pct",
    "baseline_win_rate",
    "candidate_win_rate",
    "delta_win_rate",
    "baseline_average_return",
    "candidate_average_return",
    "delta_average_return",
    "baseline_max_drawdown",
    "candidate_max_drawdown",
    "delta_max_drawdown",
    "eligible_by_min_trades",
    "score_quality_reward",
    "score_trade_penalty",
    "score_drawdown_penalty",
    "score_low_trade_penalty",
    "score",
    "outcome",
    "data_warning_count",
    "data_warnings",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
]

BEST_BY_TICKER_COLUMNS = [
    "ticker",
    "best_threshold",
    "effective_confirmation_threshold",
    "decision_confidence",
    "decision_margin",
    "trade_floor_override",
    "outcome",
    "baseline_total_trades",
    "candidate_total_trades",
    "delta_total_trades",
    "trade_retention_pct",
    "baseline_win_rate",
    "candidate_win_rate",
    "delta_win_rate",
    "baseline_average_return",
    "candidate_average_return",
    "delta_average_return",
    "baseline_max_drawdown",
    "candidate_max_drawdown",
    "delta_max_drawdown",
    "score",
    "selection_reason",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
]

GLOBAL_SUMMARY_COLUMNS = [
    "threshold",
    "effective_confirmation_threshold",
    "ticker_count",
    "eligible_ticker_count",
    "low_trade_ticker_count",
    "improve_count",
    "neutral_count",
    "worsen_count",
    "baseline_total_trades_sum",
    "candidate_total_trades_sum",
    "delta_total_trades_sum",
    "trade_retention_mean_pct",
    "baseline_win_rate_mean",
    "candidate_win_rate_mean",
    "delta_win_rate_mean",
    "baseline_average_return_mean",
    "candidate_average_return_mean",
    "delta_average_return_mean",
    "baseline_max_drawdown_mean",
    "candidate_max_drawdown_mean",
    "delta_max_drawdown_mean",
    "mean_score",
    "median_score",
    "threshold_profile",
    "selected_as_global_best",
]

GROUP_SUMMARY_COLUMNS = [
    "group_field",
    "group_value",
    "threshold",
    "effective_confirmation_threshold",
    "ticker_count",
    "eligible_ticker_count",
    "improve_count",
    "neutral_count",
    "worsen_count",
    "baseline_total_trades_sum",
    "candidate_total_trades_sum",
    "delta_total_trades_sum",
    "trade_retention_mean_pct",
    "delta_win_rate_mean",
    "delta_average_return_mean",
    "delta_max_drawdown_mean",
    "mean_score",
    "median_score",
    "sample_status",
    "threshold_profile",
]

BEST_BY_GROUP_COLUMNS = [
    "group_field",
    "group_value",
    "best_threshold",
    "effective_confirmation_threshold",
    "decision_confidence",
    "decision_margin",
    "ticker_count",
    "eligible_ticker_count",
    "improve_count",
    "neutral_count",
    "worsen_count",
    "sample_status",
    "recommended_for_subset",
    "selection_reason",
    "winning_mean_score",
    "winning_trade_retention_pct",
    "winning_delta_win_rate_mean",
    "winning_delta_average_return_mean",
    "winning_delta_max_drawdown_mean",
]


class Item5ThresholdSweepCliError(ValueError):
    """Friendly CLI error for the measured item-5 sweep."""

    def __init__(self, message: str, suggestions: Optional[Sequence[str]] = None) -> None:
        super().__init__(message)
        self.suggestions = list(suggestions or [])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(numeric):
        return float(default)
    return float(numeric)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _json_metric(value: object) -> Optional[float]:
    numeric = _safe_float(value, default=np.nan)
    if pd.isna(numeric):
        return None
    return float(numeric)


def _sanitize_for_json(value: object) -> object:
    if isinstance(value, dict):
        return {key: _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if pd.isna(value) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def _dedupe(items: Sequence[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        token = str(item).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _print_next_steps(steps: Sequence[str]) -> None:
    cleaned_steps = [step for step in steps if step]
    if not cleaned_steps:
        return

    print("\nNext step suggestions:")
    for step in cleaned_steps:
        print(f"  {step}")


def _normalize_thresholds(thresholds: Optional[Sequence[float]]) -> List[float]:
    requested = list(thresholds or DEFAULT_THRESHOLDS)
    if not requested:
        raise Item5ThresholdSweepCliError("Threshold list is empty. Provide at least one threshold.")

    normalized: List[float] = []
    for item in requested:
        try:
            threshold = float(item)
        except (TypeError, ValueError) as exc:
            raise Item5ThresholdSweepCliError(
                f"Invalid threshold value: {item}",
                suggestions=[
                    "Use numeric values only, for example: --thresholds 0.8 1.0 1.2 1.5",
                ],
            ) from exc
        if not np.isfinite(threshold) or threshold <= 0:
            raise Item5ThresholdSweepCliError(
                f"Threshold must be a finite value greater than 0. Found: {item}",
            )
        rounded = round(threshold, 4)
        if rounded not in normalized:
            normalized.append(rounded)

    return sorted(normalized)


def _evaluate_phase_a_arm(
    frame: pd.DataFrame,
    phase_a_threshold: float,
    strict_mode: bool,
    hold_period: int,
    allow_overlap: bool,
    require_candle_volume_confirmation: bool,
    candle_volume_confirmation_threshold: float,
):
    signal_frame = generate_phase_a_signal(
        frame,
        strict=strict_mode,
        volume_spike_threshold=phase_a_threshold,
        require_candle_volume_confirmation=require_candle_volume_confirmation,
        candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
    )
    signal_column = "phase_a_signal_strict" if strict_mode else "phase_a_signal"
    result = backtest_signal_frame(
        signal_frame,
        signal_column=signal_column,
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )
    return signal_frame, result


def _compute_item5_score_components(
    candidate_row: pd.Series,
    baseline_row: pd.Series,
    min_trades: int,
) -> Dict[str, float]:
    candidate_trades = _safe_float(candidate_row.get("candidate_total_trades"))
    baseline_trades = _safe_float(baseline_row.get("baseline_total_trades"))
    win_delta = _safe_float(candidate_row.get("delta_win_rate"))
    avg_delta = _safe_float(candidate_row.get("delta_average_return"))
    drawdown_delta = _safe_float(candidate_row.get("delta_max_drawdown"))

    if baseline_trades > 0:
        trade_retention_pct = (candidate_trades / baseline_trades) * 100.0
    elif candidate_trades > 0:
        trade_retention_pct = 100.0
    else:
        trade_retention_pct = 0.0

    quality_reward = (win_delta * 1.0) + (avg_delta * 3.0)
    trade_penalty = max(0.0, 100.0 - trade_retention_pct) * 0.12
    drawdown_penalty = max(0.0, drawdown_delta) * 0.75
    low_trade_penalty = 0.0
    if candidate_trades < min_trades:
        low_trade_penalty = 25.0 + ((min_trades - candidate_trades) * 2.0)

    score = quality_reward - trade_penalty - drawdown_penalty - low_trade_penalty
    return {
        "trade_retention_pct": round(trade_retention_pct, 4),
        "score_quality_reward": round(quality_reward, 4),
        "score_trade_penalty": round(trade_penalty, 4),
        "score_drawdown_penalty": round(drawdown_penalty, 4),
        "score_low_trade_penalty": round(low_trade_penalty, 4),
        "score": round(score, 4),
    }


def compute_item5_score(
    candidate_row: pd.Series,
    baseline_row: pd.Series,
    min_trades: int = 8,
) -> float:
    return float(
        _compute_item5_score_components(
            candidate_row=candidate_row,
            baseline_row=baseline_row,
            min_trades=min_trades,
        )["score"]
    )


def _classify_item5_outcome(
    score: float,
    delta_win_rate: float,
    delta_average_return: float,
    delta_max_drawdown: float,
    trade_retention_pct: float,
    eligible_by_min_trades: bool,
) -> str:
    if (
        eligible_by_min_trades
        and score >= 1.0
        and delta_average_return >= 0
        and delta_win_rate >= 0
        and delta_max_drawdown <= 0.5
    ):
        return "improve"
    if (
        score <= -1.0
        or (delta_win_rate < 0 and delta_average_return < 0)
        or (trade_retention_pct < 60.0 and not eligible_by_min_trades)
    ):
        return "worsen"
    return "neutral"


def run_item5_threshold_evaluations_for_ticker(
    path: Path,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    thresholds: Sequence[float],
    hold_period: int,
    allow_overlap: bool,
    min_trades: int,
) -> List[Dict[str, object]]:
    ticker = extract_ticker_from_filename(path)
    frame, warnings = load_price_csv(path)
    runtime = resolve_phase_a_runtime_settings(
        ticker=ticker,
        baseline_config=baseline_payload,
        metadata_lookup=metadata_lookup,
    )
    metadata_row = dict(runtime.get("metadata_row") or {})

    baseline_signal_frame, baseline_result = _evaluate_phase_a_arm(
        frame=frame,
        phase_a_threshold=float(runtime["threshold"]),
        strict_mode=bool(runtime["strict_mode"]),
        hold_period=hold_period,
        allow_overlap=allow_overlap,
        require_candle_volume_confirmation=False,
        candle_volume_confirmation_threshold=DEFAULT_REFERENCE_THRESHOLD,
    )

    baseline_template = pd.Series(
        {
            "baseline_total_trades": baseline_result.total_trades,
            "baseline_win_rate": baseline_result.win_rate,
            "baseline_average_return": baseline_result.average_return,
            "baseline_max_drawdown": baseline_result.max_drawdown,
        }
    )

    rows: List[Dict[str, object]] = []
    for threshold in thresholds:
        candidate_signal_frame, candidate_result = _evaluate_phase_a_arm(
            frame=frame,
            phase_a_threshold=float(runtime["threshold"]),
            strict_mode=bool(runtime["strict_mode"]),
            hold_period=hold_period,
            allow_overlap=allow_overlap,
            require_candle_volume_confirmation=True,
            candle_volume_confirmation_threshold=float(threshold),
        )

        row = {
            "ticker": ticker,
            "threshold": float(threshold),
            "effective_confirmation_threshold": float(max(float(threshold), float(runtime["threshold"]))),
            "rows": int(len(candidate_signal_frame)),
            "date_start": candidate_signal_frame["date"].iloc[0],
            "date_end": candidate_signal_frame["date"].iloc[-1],
            "phase_a_applied_threshold": float(runtime["threshold"]),
            "phase_a_applied_strict_mode": bool(runtime["strict_mode"]),
            "baseline_total_trades": int(baseline_result.total_trades),
            "candidate_total_trades": int(candidate_result.total_trades),
            "delta_total_trades": int(candidate_result.total_trades - baseline_result.total_trades),
            "baseline_win_rate": float(baseline_result.win_rate),
            "candidate_win_rate": float(candidate_result.win_rate),
            "delta_win_rate": round(float(candidate_result.win_rate - baseline_result.win_rate), 4),
            "baseline_average_return": float(baseline_result.average_return),
            "candidate_average_return": float(candidate_result.average_return),
            "delta_average_return": round(
                float(candidate_result.average_return - baseline_result.average_return), 4
            ),
            "baseline_max_drawdown": float(baseline_result.max_drawdown),
            "candidate_max_drawdown": float(candidate_result.max_drawdown),
            "delta_max_drawdown": round(
                float(candidate_result.max_drawdown - baseline_result.max_drawdown), 4
            ),
            "eligible_by_min_trades": bool(candidate_result.total_trades >= min_trades),
            "data_warning_count": int(len(warnings)),
            "data_warnings": " | ".join(warnings),
        }

        breakdown = _compute_item5_score_components(
            candidate_row=pd.Series(row),
            baseline_row=baseline_template,
            min_trades=min_trades,
        )
        row.update(breakdown)
        row["outcome"] = _classify_item5_outcome(
            score=float(row["score"]),
            delta_win_rate=float(row["delta_win_rate"]),
            delta_average_return=float(row["delta_average_return"]),
            delta_max_drawdown=float(row["delta_max_drawdown"]),
            trade_retention_pct=float(row["trade_retention_pct"]),
            eligible_by_min_trades=bool(row["eligible_by_min_trades"]),
        )

        for column in SUPPORTED_METADATA_COLUMNS:
            if column == "ticker":
                continue
            row[column] = metadata_row.get(column)

        rows.append(row)

    return rows


def build_results_dataframe(rows: Sequence[Dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    results_df = pd.DataFrame(rows)
    results_df = results_df.reindex(columns=RESULT_COLUMNS)
    results_df = results_df.sort_values(
        ["ticker", "score", "delta_average_return", "delta_win_rate", "threshold"],
        ascending=[True, False, False, False, True],
    ).reset_index(drop=True)
    return results_df


def _build_ticker_selection_reason(
    winner: pd.Series,
    confidence: str,
    trade_floor_override: bool,
) -> str:
    threshold = float(winner["threshold"])
    trade_retention = _safe_float(winner.get("trade_retention_pct"), default=0.0)
    delta_win_rate = _safe_float(winner.get("delta_win_rate"))
    delta_average_return = _safe_float(winner.get("delta_average_return"))
    delta_drawdown = _safe_float(winner.get("delta_max_drawdown"))

    reason = (
        f"Threshold {threshold:.1f} dipilih karena memberi skor item 5 tertinggi "
        f"untuk ticker ini."
    )
    details = (
        f" trade_retention={trade_retention:.1f}%, delta_win_rate={delta_win_rate:+.2f}, "
        f"delta_average_return={delta_average_return:+.4f}, delta_max_drawdown={delta_drawdown:+.4f}."
    )
    if trade_floor_override:
        details += " Semua kandidat berada di bawah min_trades sehingga confidence rendah."
    elif confidence == "low":
        details += " Margin keputusan tipis sehingga hasil ini masih rapuh."
    return reason + details


def select_best_threshold_per_ticker(
    results_df: pd.DataFrame,
    min_trades: int = 8,
    reference_threshold: float = DEFAULT_REFERENCE_THRESHOLD,
) -> pd.DataFrame:
    if results_df.empty:
        return pd.DataFrame(columns=BEST_BY_TICKER_COLUMNS)

    rows: List[Dict[str, object]] = []
    for ticker, group_df in results_df.groupby("ticker", sort=True):
        group_df = group_df.copy()
        eligible_df = group_df.loc[group_df["eligible_by_min_trades"]].copy()
        trade_floor_override = eligible_df.empty
        if trade_floor_override:
            eligible_df = group_df.copy()

        eligible_df["reference_preference"] = np.isclose(
            eligible_df["threshold"], reference_threshold
        ).astype(int)
        eligible_df["threshold_distance"] = (
            eligible_df["threshold"] - reference_threshold
        ).abs()
        ranked = eligible_df.sort_values(
            [
                "score",
                "reference_preference",
                "candidate_total_trades",
                "delta_average_return",
                "delta_win_rate",
                "threshold_distance",
            ],
            ascending=[False, False, False, False, False, True],
        ).reset_index(drop=True)

        winner = ranked.iloc[0]
        runner_up = ranked.iloc[1] if len(ranked) > 1 else None
        decision_margin = float(winner["score"] - runner_up["score"]) if runner_up is not None else np.nan

        if trade_floor_override or _safe_int(winner["candidate_total_trades"]) < min_trades:
            confidence = "low"
        elif pd.isna(decision_margin) or decision_margin < 0.75:
            confidence = "low"
        elif decision_margin < 2.0:
            confidence = "moderate"
        else:
            confidence = "strong"

        row = {
            "ticker": ticker,
            "best_threshold": float(winner["threshold"]),
            "effective_confirmation_threshold": float(winner["effective_confirmation_threshold"]),
            "decision_confidence": confidence,
            "decision_margin": decision_margin,
            "trade_floor_override": trade_floor_override,
            "outcome": str(winner["outcome"]),
            "baseline_total_trades": int(winner["baseline_total_trades"]),
            "candidate_total_trades": int(winner["candidate_total_trades"]),
            "delta_total_trades": int(winner["delta_total_trades"]),
            "trade_retention_pct": float(winner["trade_retention_pct"]),
            "baseline_win_rate": float(winner["baseline_win_rate"]),
            "candidate_win_rate": float(winner["candidate_win_rate"]),
            "delta_win_rate": float(winner["delta_win_rate"]),
            "baseline_average_return": float(winner["baseline_average_return"]),
            "candidate_average_return": float(winner["candidate_average_return"]),
            "delta_average_return": float(winner["delta_average_return"]),
            "baseline_max_drawdown": float(winner["baseline_max_drawdown"]),
            "candidate_max_drawdown": float(winner["candidate_max_drawdown"]),
            "delta_max_drawdown": float(winner["delta_max_drawdown"]),
            "score": float(winner["score"]),
            "selection_reason": _build_ticker_selection_reason(
                winner=winner,
                confidence=confidence,
                trade_floor_override=trade_floor_override,
            ),
        }
        for column in GROUP_FIELDS:
            row[column] = winner.get(column)
        rows.append(row)

    best_df = pd.DataFrame(rows)
    best_df = best_df.sort_values(
        ["decision_confidence", "score", "delta_average_return", "delta_win_rate"],
        ascending=[True, False, False, False],
        key=lambda series: (
            series.map({"strong": 0, "moderate": 1, "low": 2})
            if series.name == "decision_confidence"
            else series
        ),
    ).reset_index(drop=True)
    return best_df.reindex(columns=BEST_BY_TICKER_COLUMNS)


def _profile_item5_threshold_row(row: pd.Series) -> str:
    mean_score = _safe_float(row.get("mean_score"))
    delta_avg = _safe_float(row.get("delta_average_return_mean"))
    delta_win = _safe_float(row.get("delta_win_rate_mean"))
    worsen_count = _safe_int(row.get("worsen_count"))
    improve_count = _safe_int(row.get("improve_count"))

    if mean_score > 0 and delta_avg >= 0 and delta_win >= 0 and improve_count > worsen_count:
        return "promising"
    if mean_score < 0 and worsen_count >= improve_count:
        return "negative"
    return "mixed"


def summarize_global_thresholds(
    results_df: pd.DataFrame,
    reference_threshold: float = DEFAULT_REFERENCE_THRESHOLD,
) -> pd.DataFrame:
    if results_df.empty:
        return pd.DataFrame(columns=GLOBAL_SUMMARY_COLUMNS)

    summary = (
        results_df.groupby(["threshold", "effective_confirmation_threshold"], dropna=False)
        .agg(
            ticker_count=("ticker", "nunique"),
            eligible_ticker_count=("eligible_by_min_trades", "sum"),
            low_trade_ticker_count=("eligible_by_min_trades", lambda values: int((~values.astype(bool)).sum())),
            improve_count=("outcome", lambda values: int((values == "improve").sum())),
            neutral_count=("outcome", lambda values: int((values == "neutral").sum())),
            worsen_count=("outcome", lambda values: int((values == "worsen").sum())),
            baseline_total_trades_sum=("baseline_total_trades", "sum"),
            candidate_total_trades_sum=("candidate_total_trades", "sum"),
            delta_total_trades_sum=("delta_total_trades", "sum"),
            trade_retention_mean_pct=("trade_retention_pct", "mean"),
            baseline_win_rate_mean=("baseline_win_rate", "mean"),
            candidate_win_rate_mean=("candidate_win_rate", "mean"),
            delta_win_rate_mean=("delta_win_rate", "mean"),
            baseline_average_return_mean=("baseline_average_return", "mean"),
            candidate_average_return_mean=("candidate_average_return", "mean"),
            delta_average_return_mean=("delta_average_return", "mean"),
            baseline_max_drawdown_mean=("baseline_max_drawdown", "mean"),
            candidate_max_drawdown_mean=("candidate_max_drawdown", "mean"),
            delta_max_drawdown_mean=("delta_max_drawdown", "mean"),
            mean_score=("score", "mean"),
            median_score=("score", "median"),
        )
        .reset_index()
    )
    summary["threshold_profile"] = summary.apply(_profile_item5_threshold_row, axis=1)
    summary["selected_as_global_best"] = False

    ranked = summary.copy()
    ranked["reference_preference"] = np.isclose(ranked["threshold"], reference_threshold).astype(int)
    ranked["threshold_distance"] = (ranked["threshold"] - reference_threshold).abs()
    ranked = ranked.sort_values(
        [
            "mean_score",
            "improve_count",
            "eligible_ticker_count",
            "delta_average_return_mean",
            "delta_win_rate_mean",
            "reference_preference",
            "threshold_distance",
        ],
        ascending=[False, False, False, False, False, False, True],
    ).reset_index(drop=True)
    if not ranked.empty:
        selected_threshold = float(ranked.iloc[0]["threshold"])
        summary.loc[np.isclose(summary["threshold"], selected_threshold), "selected_as_global_best"] = True

    return summary.reindex(columns=GLOBAL_SUMMARY_COLUMNS)


def summarize_group_thresholds(results_df: pd.DataFrame) -> pd.DataFrame:
    if results_df.empty:
        return pd.DataFrame(columns=GROUP_SUMMARY_COLUMNS)

    rows: List[Dict[str, object]] = []
    for field in GROUP_FIELDS:
        if field not in results_df.columns:
            continue
        working = results_df.loc[
            results_df[field].notna() & results_df[field].astype(str).str.strip().ne("")
        ].copy()
        if working.empty:
            continue

        grouped = (
            working.groupby([field, "threshold", "effective_confirmation_threshold"], dropna=False)
            .agg(
                ticker_count=("ticker", "nunique"),
                eligible_ticker_count=("eligible_by_min_trades", "sum"),
                improve_count=("outcome", lambda values: int((values == "improve").sum())),
                neutral_count=("outcome", lambda values: int((values == "neutral").sum())),
                worsen_count=("outcome", lambda values: int((values == "worsen").sum())),
                baseline_total_trades_sum=("baseline_total_trades", "sum"),
                candidate_total_trades_sum=("candidate_total_trades", "sum"),
                delta_total_trades_sum=("delta_total_trades", "sum"),
                trade_retention_mean_pct=("trade_retention_pct", "mean"),
                delta_win_rate_mean=("delta_win_rate", "mean"),
                delta_average_return_mean=("delta_average_return", "mean"),
                delta_max_drawdown_mean=("delta_max_drawdown", "mean"),
                mean_score=("score", "mean"),
                median_score=("score", "median"),
            )
            .reset_index()
        )
        grouped = grouped.rename(columns={field: "group_value"})
        grouped["group_field"] = field
        grouped["sample_status"] = np.where(
            grouped["ticker_count"] >= GROUP_MIN_TICKERS,
            "enough_sample",
            "insufficient_sample",
        )
        grouped["threshold_profile"] = grouped.apply(_profile_item5_threshold_row, axis=1)
        rows.extend(grouped.to_dict(orient="records"))

    if not rows:
        return pd.DataFrame(columns=GROUP_SUMMARY_COLUMNS)

    group_summary_df = pd.DataFrame(rows)
    group_summary_df = group_summary_df.reindex(columns=GROUP_SUMMARY_COLUMNS)
    group_summary_df = group_summary_df.sort_values(
        ["group_field", "group_value", "mean_score", "threshold"],
        ascending=[True, True, False, True],
    ).reset_index(drop=True)
    return group_summary_df


def _build_group_selection_reason(winner: pd.Series, confidence: str) -> str:
    reason = (
        f"Threshold {float(winner['threshold']):.1f} dipilih untuk group ini "
        f"karena mean score item 5 paling baik."
    )
    details = (
        f" delta_average_return_mean={_safe_float(winner.get('delta_average_return_mean')):+.4f}, "
        f"delta_win_rate_mean={_safe_float(winner.get('delta_win_rate_mean')):+.2f}, "
        f"trade_retention_mean={_safe_float(winner.get('trade_retention_mean_pct'), default=0.0):.1f}%."
    )
    if confidence == "low":
        details += " Confidence rendah karena sampel kecil atau margin tipis."
    return reason + details


def select_best_threshold_per_group(
    group_summary_df: pd.DataFrame,
    reference_threshold: float = DEFAULT_REFERENCE_THRESHOLD,
) -> pd.DataFrame:
    if group_summary_df.empty:
        return pd.DataFrame(columns=BEST_BY_GROUP_COLUMNS)

    rows: List[Dict[str, object]] = []
    for (group_field, group_value), group_df in group_summary_df.groupby(
        ["group_field", "group_value"],
        sort=True,
    ):
        ranked = group_df.copy()
        ranked["reference_preference"] = np.isclose(ranked["threshold"], reference_threshold).astype(int)
        ranked["threshold_distance"] = (ranked["threshold"] - reference_threshold).abs()
        ranked = ranked.sort_values(
            [
                "mean_score",
                "improve_count",
                "eligible_ticker_count",
                "delta_average_return_mean",
                "delta_win_rate_mean",
                "reference_preference",
                "threshold_distance",
            ],
            ascending=[False, False, False, False, False, False, True],
        ).reset_index(drop=True)

        winner = ranked.iloc[0]
        runner_up = ranked.iloc[1] if len(ranked) > 1 else None
        decision_margin = float(winner["mean_score"] - runner_up["mean_score"]) if runner_up is not None else np.nan
        if str(winner["sample_status"]) != "enough_sample":
            confidence = "low"
        elif pd.isna(decision_margin) or decision_margin < 0.5:
            confidence = "low"
        elif decision_margin < 1.5:
            confidence = "moderate"
        else:
            confidence = "strong"

        recommended_for_subset = bool(
            str(winner["sample_status"]) == "enough_sample"
            and float(winner["mean_score"]) > 0
            and int(winner["improve_count"]) > int(winner["worsen_count"])
            and confidence != "low"
        )

        rows.append(
            {
                "group_field": group_field,
                "group_value": group_value,
                "best_threshold": float(winner["threshold"]),
                "effective_confirmation_threshold": float(winner["effective_confirmation_threshold"]),
                "decision_confidence": confidence,
                "decision_margin": decision_margin,
                "ticker_count": int(winner["ticker_count"]),
                "eligible_ticker_count": int(winner["eligible_ticker_count"]),
                "improve_count": int(winner["improve_count"]),
                "neutral_count": int(winner["neutral_count"]),
                "worsen_count": int(winner["worsen_count"]),
                "sample_status": str(winner["sample_status"]),
                "recommended_for_subset": recommended_for_subset,
                "selection_reason": _build_group_selection_reason(
                    winner=winner,
                    confidence=confidence,
                ),
                "winning_mean_score": float(winner["mean_score"]),
                "winning_trade_retention_pct": float(winner["trade_retention_mean_pct"]),
                "winning_delta_win_rate_mean": float(winner["delta_win_rate_mean"]),
                "winning_delta_average_return_mean": float(winner["delta_average_return_mean"]),
                "winning_delta_max_drawdown_mean": float(winner["delta_max_drawdown_mean"]),
            }
        )

    best_group_df = pd.DataFrame(rows)
    best_group_df = best_group_df.sort_values(
        ["recommended_for_subset", "decision_confidence", "winning_mean_score"],
        ascending=[False, True, False],
        key=lambda series: (
            series.map({"strong": 0, "moderate": 1, "low": 2})
            if series.name == "decision_confidence"
            else series
        ),
    ).reset_index(drop=True)
    return best_group_df.reindex(columns=BEST_BY_GROUP_COLUMNS)


def determine_item5_go_no_go(
    best_by_ticker_df: pd.DataFrame,
    global_summary_df: pd.DataFrame,
    best_by_group_df: Optional[pd.DataFrame] = None,
) -> Dict[str, object]:
    if best_by_ticker_df.empty or global_summary_df.empty:
        return {
            "decision": "keep_experimental",
            "best_global_threshold": None,
            "promote_default": False,
            "promote_subset_only": False,
            "recommended_groups": [],
            "recommended_tickers": [],
            "blocked_from_default": [
                "Sweep item 5 tidak menghasilkan data cukup untuk keputusan tegas.",
            ],
            "next_action": "continue_tuning",
            "item5_experiment_status": "failed",
            "item5_next_action": "continue_tuning",
        }

    selected_global = global_summary_df.loc[global_summary_df["selected_as_global_best"]]
    if selected_global.empty:
        selected_global = global_summary_df.sort_values(
            ["mean_score", "delta_average_return_mean", "delta_win_rate_mean"],
            ascending=[False, False, False],
        ).head(1)
    global_row = selected_global.iloc[0]

    improve_count = int((best_by_ticker_df["outcome"] == "improve").sum())
    neutral_count = int((best_by_ticker_df["outcome"] == "neutral").sum())
    worsen_count = int((best_by_ticker_df["outcome"] == "worsen").sum())
    ticker_count = int(len(best_by_ticker_df))
    improve_share = (improve_count / ticker_count) if ticker_count else 0.0
    worsen_share = (worsen_count / ticker_count) if ticker_count else 0.0

    recommended_tickers = (
        best_by_ticker_df.loc[
            (best_by_ticker_df["outcome"] == "improve")
            & (best_by_ticker_df["decision_confidence"] != "low"),
            "ticker",
        ]
        .astype(str)
        .tolist()
    )

    recommended_groups: List[str] = []
    if best_by_group_df is not None and not best_by_group_df.empty:
        recommended_groups = (
            best_by_group_df.loc[best_by_group_df["recommended_for_subset"]]
            .apply(lambda row: f"{row['group_field']}={row['group_value']}", axis=1)
            .astype(str)
            .tolist()
        )

    blocked_from_default: List[str] = []
    if _safe_float(global_row["mean_score"]) <= 0:
        blocked_from_default.append("Skor global item 5 tidak positif.")
    if _safe_float(global_row["delta_average_return_mean"]) <= 0:
        blocked_from_default.append("Average return global tidak membaik.")
    if _safe_float(global_row["delta_win_rate_mean"]) < 0:
        blocked_from_default.append("Win rate global tidak membaik.")
    if worsen_count >= improve_count:
        blocked_from_default.append("Ticker yang memburuk minimal sama banyak dengan yang improve.")
    if _safe_float(global_row["trade_retention_mean_pct"], default=0.0) < 75.0:
        blocked_from_default.append("Trade retention global terlalu rendah untuk default.")

    if (
        improve_share >= 0.6
        and worsen_share <= 0.2
        and _safe_float(global_row["mean_score"]) > 0.75
        and _safe_float(global_row["delta_average_return_mean"]) > 0
        and _safe_float(global_row["delta_win_rate_mean"]) >= 0
        and _safe_float(global_row["trade_retention_mean_pct"], default=0.0) >= 75.0
        and len(recommended_tickers) >= max(3, math.ceil(ticker_count * 0.5))
    ):
        decision = "promote_global"
        next_action = "promote_global"
        item5_experiment_status = "promising"
        item5_next_action = "promote_global"
    elif recommended_groups or (
        len(recommended_tickers) >= 2
        and improve_count > worsen_count
        and _safe_float(global_row["mean_score"]) > -0.25
    ):
        decision = "promote_for_subset"
        next_action = "promote_subset"
        item5_experiment_status = "promising"
        item5_next_action = "promote_subset"
    elif (
        _safe_float(global_row["mean_score"]) > -0.5
        and (improve_count > 0 or neutral_count >= worsen_count)
    ):
        decision = "keep_experimental"
        next_action = "continue_tuning"
        item5_experiment_status = "mixed"
        item5_next_action = "continue_tuning"
    else:
        decision = "no_go"
        next_action = "stop"
        item5_experiment_status = "failed"
        item5_next_action = "stop"

    return {
        "decision": decision,
        "best_global_threshold": float(global_row["threshold"]),
        "promote_default": decision == "promote_global",
        "promote_subset_only": decision == "promote_for_subset",
        "recommended_groups": recommended_groups,
        "recommended_tickers": recommended_tickers,
        "blocked_from_default": _dedupe(blocked_from_default),
        "next_action": next_action,
        "item5_experiment_status": item5_experiment_status,
        "item5_next_action": item5_next_action,
    }


def build_item5_decision_payload(
    output_dir: Path,
    data_dir: Path,
    baseline_config_path: Optional[Path],
    metadata_file: Optional[Path],
    thresholds: Sequence[float],
    min_trades: int,
    results_df: pd.DataFrame,
    best_by_ticker_df: pd.DataFrame,
    global_summary_df: pd.DataFrame,
    best_by_group_df: Optional[pd.DataFrame],
    go_no_go: Dict[str, object],
    notes: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    selected_global = global_summary_df.loc[global_summary_df["selected_as_global_best"]]
    selected_global_row = (
        selected_global.iloc[0].to_dict() if not selected_global.empty else {}
    )

    return {
        "generated_at": _now_iso(),
        "experiment_id": "phase_b_item5_threshold_sweep",
        "output_dir": str(output_dir),
        "data_dir": str(data_dir),
        "baseline_config": str(baseline_config_path) if baseline_config_path else None,
        "metadata_file": str(metadata_file) if metadata_file else None,
        "thresholds_tested": [float(item) for item in thresholds],
        "min_trades": int(min_trades),
        "ticker_count": int(results_df["ticker"].nunique()) if not results_df.empty else 0,
        "best_global_threshold": go_no_go["best_global_threshold"],
        "global_best_row": _sanitize_for_json(selected_global_row),
        "ticker_outcome_counts": {
            "improve": int((best_by_ticker_df["outcome"] == "improve").sum()) if not best_by_ticker_df.empty else 0,
            "neutral": int((best_by_ticker_df["outcome"] == "neutral").sum()) if not best_by_ticker_df.empty else 0,
            "worsen": int((best_by_ticker_df["outcome"] == "worsen").sum()) if not best_by_ticker_df.empty else 0,
        },
        "recommended_groups": list(go_no_go["recommended_groups"]),
        "recommended_tickers": list(go_no_go["recommended_tickers"]),
        "go_no_go": _sanitize_for_json(go_no_go),
        "artifacts": {
            "results_csv": str(output_dir / "phase_b_item5_threshold_sweep_results.csv"),
            "best_by_ticker_csv": str(output_dir / "phase_b_item5_best_by_ticker.csv"),
            "global_summary_csv": str(output_dir / "phase_b_item5_global_summary.csv"),
            "group_summary_csv": str(output_dir / "phase_b_item5_group_summary.csv"),
            "best_by_group_csv": str(output_dir / "phase_b_item5_best_by_group.csv"),
            "go_no_go_json": str(output_dir / "phase_b_item5_go_no_go.json"),
            "decision_json": str(output_dir / "phase_b_item5_decision.json"),
            "recommendations_txt": str(output_dir / "phase_b_item5_recommendations.txt"),
        },
        "subset_analysis_available": bool(best_by_group_df is not None and not best_by_group_df.empty),
        "notes": list(notes or []),
    }


def build_item5_recommendations_text(
    decision_payload: Dict[str, object],
    go_no_go: Dict[str, object],
    global_summary_df: pd.DataFrame,
) -> str:
    best_threshold = go_no_go.get("best_global_threshold")
    recommended_groups = list(go_no_go.get("recommended_groups") or [])
    recommended_tickers = list(go_no_go.get("recommended_tickers") or [])
    blocked_from_default = list(go_no_go.get("blocked_from_default") or [])
    decision = str(go_no_go.get("decision"))

    if decision == "promote_global":
        item5_viable = "Ya, item 5 konsisten cukup kuat untuk dipromosikan global."
        item6_guidance = "Item 6 boleh mulai, sambil siapkan promosi global item 5 secara terpisah."
    elif decision == "promote_for_subset":
        item5_viable = "Ya, tetapi hanya layak dipromosikan untuk subset tertentu."
        item6_guidance = "Item 6 boleh mulai setelah subset item 5 yang direkomendasikan didokumentasikan tegas."
    elif decision == "keep_experimental":
        item5_viable = "Belum cukup kuat untuk promosi; tetap experimental sambil tuning lanjut."
        item6_guidance = "Item 6 sebaiknya ditunda dulu sampai item 5 tidak lagi ambigu."
    else:
        item5_viable = "Tidak layak dipromosikan; item 5 sebaiknya dihentikan sebagai kandidat default."
        item6_guidance = "Item 6 boleh mulai sekarang karena keputusan item 5 sudah cukup tegas."

    lines = [
        "Phase B Item 5 Recommendations",
        "================================",
        "",
        f"- Decision: {decision}",
        f"- Apakah item 5 layak lanjut: {item5_viable}",
        f"- Threshold terbaik global: {best_threshold if best_threshold is not None else 'none'}",
        f"- Apakah cocok global: {'ya' if decision == 'promote_global' else 'tidak'}",
        f"- Apakah hanya cocok subset: {'ya' if decision == 'promote_for_subset' else 'tidak'}",
        f"- Apakah tetap experimental: {'ya' if decision == 'keep_experimental' else 'tidak'}",
        f"- Apakah item 6 boleh mulai sekarang: {item6_guidance}",
        "",
        "Recommended groups:",
    ]
    if recommended_groups:
        for item in recommended_groups:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    lines.extend(["", "Recommended tickers:"])
    if recommended_tickers:
        for item in recommended_tickers:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    lines.extend(["", "Blocked from default:"])
    if blocked_from_default:
        for item in blocked_from_default:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    decision_notes = list(decision_payload.get("notes") or [])
    lines.extend(["", "Decision notes:"])
    if decision_notes:
        for item in decision_notes:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    if not global_summary_df.empty:
        selected = global_summary_df.loc[global_summary_df["selected_as_global_best"]]
        if not selected.empty:
            row = selected.iloc[0]
            lines.extend(
                [
                    "",
                    "Global best threshold snapshot:",
                    f"- mean_score={_safe_float(row['mean_score']):+.4f}",
                    f"- delta_win_rate_mean={_safe_float(row['delta_win_rate_mean']):+.4f}",
                    f"- delta_average_return_mean={_safe_float(row['delta_average_return_mean']):+.4f}",
                    f"- trade_retention_mean_pct={_safe_float(row['trade_retention_mean_pct']):.2f}",
                    f"- threshold_profile={row['threshold_profile']}",
                ]
            )

    return "\n".join(lines) + "\n"


def run_phase_b_item5_threshold_sweep(
    data_dir: Path,
    output_dir: Path,
    baseline_config: Path,
    metadata_file: Optional[Path] = None,
    thresholds: Optional[Sequence[float]] = None,
    min_trades: int = 8,
    hold_period: int = 5,
    allow_overlap: bool = False,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    baseline_config = Path(baseline_config)
    normalized_thresholds = _normalize_thresholds(thresholds)

    if not baseline_config.exists():
        raise Item5ThresholdSweepCliError(
            f"Baseline config not found: {baseline_config}",
            suggestions=[
                "Refresh the active Phase A baseline first with: python3 -m quant.freeze_phase_a_baseline --output-dir output",
            ],
        )

    baseline_payload, baseline_warnings, resolved_baseline = load_phase_a_baseline(
        baseline_config=baseline_config
    )
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    metadata_df, metadata_analysis_warnings = load_metadata(metadata_file)
    csv_files = resolve_csv_files(data_dir=data_dir, metadata_file=metadata_file)

    for warning in [*baseline_warnings, *metadata_warnings, *metadata_analysis_warnings]:
        print(f"warning: {warning}")

    rows: List[Dict[str, object]] = []
    for path in csv_files:
        ticker_rows = run_item5_threshold_evaluations_for_ticker(
            path=path,
            baseline_payload=baseline_payload,
            metadata_lookup=metadata_lookup,
            thresholds=normalized_thresholds,
            hold_period=hold_period,
            allow_overlap=allow_overlap,
            min_trades=min_trades,
        )
        rows.extend(ticker_rows)

    results_df = build_results_dataframe(rows)
    best_by_ticker_df = select_best_threshold_per_ticker(
        results_df=results_df,
        min_trades=min_trades,
    )
    global_summary_df = summarize_global_thresholds(results_df=results_df)
    group_summary_df = summarize_group_thresholds(results_df=results_df)
    best_by_group_df = select_best_threshold_per_group(group_summary_df=group_summary_df)
    if best_by_group_df.empty:
        best_by_group_df = None

    decision_notes: List[str] = []
    if (
        not results_df.empty
        and int(results_df["threshold"].nunique()) > 1
        and int(results_df["effective_confirmation_threshold"].nunique()) == 1
    ):
        effective_threshold = float(results_df["effective_confirmation_threshold"].iloc[0])
        decision_notes.append(
            "Semua threshold yang diuji collapse ke effective confirmation threshold "
            f"{effective_threshold:.1f} karena baseline Phase A aktif sudah menuntut volume_ratio minimal itu."
        )
    if not global_summary_df.empty and int(global_summary_df["eligible_ticker_count"].max()) == 0:
        decision_notes.append(
            f"Tidak ada threshold item 5 yang memenuhi min_trades={int(min_trades)}, jadi dukungan sampelnya belum cukup untuk promosi."
        )

    go_no_go = determine_item5_go_no_go(
        best_by_ticker_df=best_by_ticker_df,
        global_summary_df=global_summary_df,
        best_by_group_df=best_by_group_df,
    )
    go_no_go["blocked_from_default"] = _dedupe(
        list(go_no_go.get("blocked_from_default") or []) + decision_notes
    )
    decision_payload = build_item5_decision_payload(
        output_dir=output_dir,
        data_dir=data_dir,
        baseline_config_path=resolved_baseline,
        metadata_file=metadata_file,
        thresholds=normalized_thresholds,
        min_trades=min_trades,
        results_df=results_df,
        best_by_ticker_df=best_by_ticker_df,
        global_summary_df=global_summary_df,
        best_by_group_df=best_by_group_df,
        go_no_go=go_no_go,
        notes=decision_notes,
    )
    recommendations_text = build_item5_recommendations_text(
        decision_payload=decision_payload,
        go_no_go=go_no_go,
        global_summary_df=global_summary_df,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "phase_b_item5_threshold_sweep_results.csv"
    best_by_ticker_path = output_dir / "phase_b_item5_best_by_ticker.csv"
    global_summary_path = output_dir / "phase_b_item5_global_summary.csv"
    group_summary_path = output_dir / "phase_b_item5_group_summary.csv"
    best_by_group_path = output_dir / "phase_b_item5_best_by_group.csv"
    decision_path = output_dir / "phase_b_item5_decision.json"
    recommendations_path = output_dir / "phase_b_item5_recommendations.txt"
    go_no_go_path = output_dir / "phase_b_item5_go_no_go.json"

    results_df.to_csv(results_path, index=False)
    best_by_ticker_df.to_csv(best_by_ticker_path, index=False)
    global_summary_df.to_csv(global_summary_path, index=False)
    print(f"Saved item 5 sweep results to {results_path}")
    print(f"Saved item 5 best-by-ticker summary to {best_by_ticker_path}")
    print(f"Saved item 5 global summary to {global_summary_path}")

    if group_summary_df.empty:
        if group_summary_path.exists():
            group_summary_path.unlink()
        if best_by_group_path.exists():
            best_by_group_path.unlink()
    else:
        group_summary_df.to_csv(group_summary_path, index=False)
        print(f"Saved item 5 group summary to {group_summary_path}")
        if best_by_group_df is not None:
            best_by_group_df.to_csv(best_by_group_path, index=False)
            print(f"Saved item 5 best-by-group summary to {best_by_group_path}")

    decision_path.write_text(
        json.dumps(_sanitize_for_json(decision_payload), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    go_no_go_path.write_text(
        json.dumps(_sanitize_for_json(go_no_go), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    recommendations_path.write_text(recommendations_text, encoding="utf-8")
    print(f"Saved item 5 decision JSON to {decision_path}")
    print(f"Saved item 5 go/no-go JSON to {go_no_go_path}")
    print(f"Saved item 5 recommendations to {recommendations_path}")

    return {
        "results_df": results_df,
        "best_by_ticker_df": best_by_ticker_df,
        "global_summary_df": global_summary_df,
        "group_summary_df": group_summary_df,
        "best_by_group_df": best_by_group_df,
        "decision_payload": decision_payload,
        "go_no_go": go_no_go,
        "artifacts": {
            "results_csv": results_path,
            "best_by_ticker_csv": best_by_ticker_path,
            "global_summary_csv": global_summary_path,
            "group_summary_csv": group_summary_path,
            "best_by_group_csv": best_by_group_path,
            "decision_json": decision_path,
            "go_no_go_json": go_no_go_path,
            "recommendations_txt": recommendations_path,
        },
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the official measured threshold sweep for Phase B item 5 candle confirmation."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing per-ticker OHLCV CSV files. Default: data",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory receiving the item-5 sweep artifacts. Default: output",
    )
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Frozen baseline JSON used as the control arm. Default: output/phase_a_baseline_final.json",
    )
    parser.add_argument(
        "--metadata-file",
        default=None,
        help="Optional ticker metadata CSV used for group analysis.",
    )
    parser.add_argument(
        "--thresholds",
        nargs="*",
        type=float,
        default=DEFAULT_THRESHOLDS,
        help="Requested candle confirmation thresholds. Default: 0.8 1.0 1.2 1.5",
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=8,
        help="Minimum trade floor used when scoring candidates. Default: 8",
    )
    parser.add_argument(
        "--hold-period",
        type=int,
        default=5,
        help="Holding period in bars for each backtest trade. Default: 5",
    )
    parser.add_argument(
        "--allow-overlap",
        action="store_true",
        help="Allow overlapping trades during backtest.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run_phase_b_item5_threshold_sweep(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            baseline_config=Path(args.baseline_config),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            thresholds=args.thresholds,
            min_trades=args.min_trades,
            hold_period=args.hold_period,
            allow_overlap=args.allow_overlap,
        )
    except Item5ThresholdSweepCliError as exc:
        print(str(exc))
        _print_next_steps(exc.suggestions)
        return 1
    except Exception as exc:
        print(f"Unexpected item 5 sweep failure: {exc}")
        _print_next_steps(
            [
                "Pastikan baseline Phase A aktif dan data/*.csv sudah tersedia sebelum rerun item 5 sweep.",
                (
                    "Contoh command: python3 -m quant.run_phase_b_item5_threshold_sweep "
                    "--data-dir data --output-dir output --baseline-config output/phase_a_baseline_final.json"
                ),
            ]
        )
        return 1

    go_no_go = result["go_no_go"]
    print(f"Decision: {go_no_go['decision']}")
    print(f"Best global threshold: {go_no_go['best_global_threshold']}")
    print(f"Next action: {go_no_go['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
