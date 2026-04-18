"""Run Phase B item 8 adaptive backtests per ticker and optional group.

Example
-------
Preferred execution from project root:

    python3 -m quant.run_phase_b_item8_adaptive_backtest \
      --data-dir data \
      --output-dir output \
      --baseline-config output/phase_a_baseline_final.json \
      --metadata-file data/ticker_metadata.csv \
      --thresholds 1.5 2.0 2.5 \
      --strict-options false true \
      --min-trades 8
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

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

DEFAULT_THRESHOLDS = [1.5, 2.0, 2.5]
DEFAULT_STRICT_OPTIONS = [False, True]
GROUP_MIN_TICKERS = 2

RESULT_COLUMNS = [
    "ticker",
    "config_id",
    "volume_spike_threshold",
    "strict_mode",
    "rows",
    "date_start",
    "date_end",
    "baseline_threshold",
    "baseline_strict_mode",
    "baseline_total_trades",
    "total_trades",
    "delta_total_trades",
    "trade_retention_pct",
    "baseline_win_rate",
    "win_rate",
    "delta_win_rate",
    "baseline_average_return",
    "average_return",
    "delta_average_return",
    "baseline_max_drawdown",
    "max_drawdown",
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

BEST_TICKER_COLUMNS = [
    "ticker",
    "config_id",
    "best_threshold",
    "best_strict_mode",
    "decision_confidence",
    "decision_margin",
    "trade_floor_override",
    "usable_recommendation",
    "outcome",
    "baseline_threshold",
    "baseline_strict_mode",
    "baseline_total_trades",
    "total_trades",
    "delta_total_trades",
    "trade_retention_pct",
    "baseline_win_rate",
    "win_rate",
    "delta_win_rate",
    "baseline_average_return",
    "average_return",
    "delta_average_return",
    "baseline_max_drawdown",
    "max_drawdown",
    "delta_max_drawdown",
    "score",
    "selection_reason",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
]

GROUP_RECOMMENDATION_COLUMNS = [
    "group_field",
    "group_value",
    "config_id",
    "best_threshold",
    "best_strict_mode",
    "decision_confidence",
    "decision_margin",
    "ticker_count",
    "eligible_ticker_count",
    "improve_count",
    "neutral_count",
    "worsen_count",
    "trade_retention_mean_pct",
    "delta_win_rate_mean",
    "delta_average_return_mean",
    "delta_max_drawdown_mean",
    "mean_score",
    "median_score",
    "sample_status",
    "recommended_for_group",
    "selection_reason",
]


class Item8AdaptiveCliError(ValueError):
    """Friendly CLI error for Phase B item 8."""

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


def _normalize_thresholds(thresholds: Optional[Sequence[float]]) -> List[float]:
    requested = list(thresholds or DEFAULT_THRESHOLDS)
    if not requested:
        raise Item8AdaptiveCliError("Threshold list is empty. Provide at least one threshold.")

    normalized: List[float] = []
    for item in requested:
        try:
            threshold = float(item)
        except (TypeError, ValueError) as exc:
            raise Item8AdaptiveCliError(
                f"Invalid threshold value: {item}",
                suggestions=["Use numeric values only, for example: --thresholds 1.5 2.0 2.5"],
            ) from exc
        if not np.isfinite(threshold) or threshold <= 0:
            raise Item8AdaptiveCliError(
                f"Threshold must be a finite value greater than 0. Found: {item}",
            )
        rounded = round(threshold, 4)
        if rounded not in normalized:
            normalized.append(rounded)
    return sorted(normalized)


def _parse_bool_token(raw: object) -> bool:
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise Item8AdaptiveCliError(
        f"Invalid strict option: {raw}",
        suggestions=["Use boolean values only, for example: --strict-options false true"],
    )


def _normalize_strict_options(options: Optional[Sequence[object]]) -> List[bool]:
    requested = list(options or DEFAULT_STRICT_OPTIONS)
    if not requested:
        raise Item8AdaptiveCliError("Strict option list is empty. Provide at least one value.")

    normalized: List[bool] = []
    for item in requested:
        flag = _parse_bool_token(item)
        if flag not in normalized:
            normalized.append(flag)
    return normalized


def _config_id(threshold: float, strict_mode: bool) -> str:
    return f"threshold_{float(threshold):.1f}_strict_{str(bool(strict_mode)).lower()}"


def _evaluate_arm(
    frame: pd.DataFrame,
    threshold: float,
    strict_mode: bool,
    hold_period: int,
    allow_overlap: bool,
):
    signal_frame = generate_phase_a_signal(
        frame,
        strict=strict_mode,
        volume_spike_threshold=threshold,
        require_candle_volume_confirmation=False,
        require_weekly_trend_confirmation=False,
        require_sentiment_momentum=False,
    )
    signal_column = "phase_a_signal_strict" if strict_mode else "phase_a_signal"
    result = backtest_signal_frame(
        signal_frame,
        signal_column=signal_column,
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )
    return signal_frame, result


def _compute_score_components(
    candidate_metrics: pd.Series,
    baseline_metrics: pd.Series,
    min_trades: int,
) -> Dict[str, float]:
    candidate_trades = _safe_float(candidate_metrics.get("total_trades"))
    baseline_trades = _safe_float(baseline_metrics.get("baseline_total_trades"))
    win_delta = _safe_float(candidate_metrics.get("delta_win_rate"))
    avg_delta = _safe_float(candidate_metrics.get("delta_average_return"))
    drawdown_delta = _safe_float(candidate_metrics.get("delta_max_drawdown"))

    if baseline_trades > 0:
        trade_retention_pct = (candidate_trades / baseline_trades) * 100.0
    elif candidate_trades > 0:
        trade_retention_pct = 100.0
    else:
        trade_retention_pct = 0.0

    quality_reward = (win_delta * 1.0) + (avg_delta * 4.0)
    trade_penalty = max(0.0, 100.0 - trade_retention_pct) * 0.10
    drawdown_penalty = max(0.0, drawdown_delta) * 0.85
    low_trade_penalty = 0.0
    if candidate_trades < min_trades:
        low_trade_penalty = 30.0 + ((min_trades - candidate_trades) * 3.0)

    score = quality_reward - trade_penalty - drawdown_penalty - low_trade_penalty
    return {
        "trade_retention_pct": round(trade_retention_pct, 4),
        "score_quality_reward": round(quality_reward, 4),
        "score_trade_penalty": round(trade_penalty, 4),
        "score_drawdown_penalty": round(drawdown_penalty, 4),
        "score_low_trade_penalty": round(low_trade_penalty, 4),
        "score": round(score, 4),
    }


def _classify_outcome(
    score: float,
    delta_win_rate: float,
    delta_average_return: float,
    delta_max_drawdown: float,
    eligible_by_min_trades: bool,
) -> str:
    if (
        eligible_by_min_trades
        and score >= 1.0
        and delta_average_return >= 0
        and delta_win_rate >= 0
        and delta_max_drawdown <= 0.75
    ):
        return "improve"
    if score <= -1.0 or (delta_win_rate < 0 and delta_average_return < 0):
        return "worsen"
    return "neutral"


def run_item8_evaluations_for_ticker(
    path: Path,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    thresholds: Sequence[float],
    strict_options: Sequence[bool],
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

    baseline_signal_frame, baseline_result = _evaluate_arm(
        frame=frame,
        threshold=float(runtime["threshold"]),
        strict_mode=bool(runtime["strict_mode"]),
        hold_period=hold_period,
        allow_overlap=allow_overlap,
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
        for strict_mode in strict_options:
            candidate_signal_frame, candidate_result = _evaluate_arm(
                frame=frame,
                threshold=float(threshold),
                strict_mode=bool(strict_mode),
                hold_period=hold_period,
                allow_overlap=allow_overlap,
            )
            row = {
                "ticker": ticker,
                "config_id": _config_id(float(threshold), bool(strict_mode)),
                "volume_spike_threshold": float(threshold),
                "strict_mode": bool(strict_mode),
                "rows": int(len(candidate_signal_frame)),
                "date_start": candidate_signal_frame["date"].iloc[0],
                "date_end": candidate_signal_frame["date"].iloc[-1],
                "baseline_threshold": float(runtime["threshold"]),
                "baseline_strict_mode": bool(runtime["strict_mode"]),
                "baseline_total_trades": int(baseline_result.total_trades),
                "total_trades": int(candidate_result.total_trades),
                "delta_total_trades": int(candidate_result.total_trades - baseline_result.total_trades),
                "baseline_win_rate": float(baseline_result.win_rate),
                "win_rate": float(candidate_result.win_rate),
                "delta_win_rate": round(float(candidate_result.win_rate - baseline_result.win_rate), 4),
                "baseline_average_return": float(baseline_result.average_return),
                "average_return": float(candidate_result.average_return),
                "delta_average_return": round(
                    float(candidate_result.average_return - baseline_result.average_return),
                    4,
                ),
                "baseline_max_drawdown": float(baseline_result.max_drawdown),
                "max_drawdown": float(candidate_result.max_drawdown),
                "delta_max_drawdown": round(
                    float(candidate_result.max_drawdown - baseline_result.max_drawdown),
                    4,
                ),
                "eligible_by_min_trades": bool(candidate_result.total_trades >= min_trades),
                "data_warning_count": int(len(warnings)),
                "data_warnings": " | ".join(warnings),
            }
            breakdown = _compute_score_components(
                candidate_metrics=pd.Series(row),
                baseline_metrics=baseline_template,
                min_trades=min_trades,
            )
            row.update(breakdown)
            row["outcome"] = _classify_outcome(
                score=float(row["score"]),
                delta_win_rate=float(row["delta_win_rate"]),
                delta_average_return=float(row["delta_average_return"]),
                delta_max_drawdown=float(row["delta_max_drawdown"]),
                eligible_by_min_trades=bool(row["eligible_by_min_trades"]),
            )

            for column in ["category", "market_cap_group", "sector", "beta_group"]:
                row[column] = metadata_row.get(column)
            rows.append(row)

    return rows


def build_results_dataframe(rows: Sequence[Dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    results_df = pd.DataFrame(rows)
    results_df = results_df.reindex(columns=RESULT_COLUMNS)
    return results_df.sort_values(
        ["ticker", "eligible_by_min_trades", "score", "delta_average_return", "delta_win_rate", "config_id"],
        ascending=[True, False, False, False, False, True],
    ).reset_index(drop=True)


def _ticker_selection_reason(winner: pd.Series, trade_floor_override: bool, confidence: str) -> str:
    reason = (
        f"Config {winner['config_id']} dipilih karena memberi skor adaptive tertinggi "
        f"dengan threshold={float(winner['volume_spike_threshold']):.1f} "
        f"dan strict={str(bool(winner['strict_mode'])).lower()}."
    )
    reason += (
        f" total_trades={_safe_int(winner['total_trades'])}, "
        f"delta_win_rate={_safe_float(winner['delta_win_rate']):+.2f}, "
        f"delta_average_return={_safe_float(winner['delta_average_return']):+.4f}, "
        f"delta_max_drawdown={_safe_float(winner['delta_max_drawdown']):+.4f}."
    )
    if trade_floor_override:
        reason += " Tidak ada kandidat yang memenuhi min_trades sehingga rekomendasi tidak usable."
    elif confidence == "low":
        reason += " Margin keputusan tipis sehingga confidence tetap rendah."
    return reason


def select_best_config_per_ticker(
    results_df: pd.DataFrame,
    min_trades: int = 8,
) -> pd.DataFrame:
    if results_df.empty:
        return pd.DataFrame(columns=BEST_TICKER_COLUMNS)

    rows: List[Dict[str, object]] = []
    for ticker, group_df in results_df.groupby("ticker", sort=True):
        working = group_df.copy()
        eligible_df = working.loc[working["eligible_by_min_trades"]].copy()
        trade_floor_override = eligible_df.empty
        candidate_pool = eligible_df if not trade_floor_override else working

        candidate_pool["baseline_match"] = (
            np.isclose(candidate_pool["volume_spike_threshold"], candidate_pool["baseline_threshold"])
            & candidate_pool["strict_mode"].astype(bool).eq(candidate_pool["baseline_strict_mode"].astype(bool))
        ).astype(int)
        candidate_pool["threshold_distance"] = (
            candidate_pool["volume_spike_threshold"] - candidate_pool["baseline_threshold"]
        ).abs()
        ranked = candidate_pool.sort_values(
            [
                "score",
                "eligible_by_min_trades",
                "total_trades",
                "delta_average_return",
                "delta_win_rate",
                "baseline_match",
                "threshold_distance",
            ],
            ascending=[False, False, False, False, False, False, True],
        ).reset_index(drop=True)

        winner = ranked.iloc[0]
        runner_up = ranked.iloc[1] if len(ranked) > 1 else None
        decision_margin = float(winner["score"] - runner_up["score"]) if runner_up is not None else np.nan

        if trade_floor_override or _safe_int(winner["total_trades"]) < min_trades:
            confidence = "low"
        elif pd.isna(decision_margin) or decision_margin < 1.0:
            confidence = "low"
        elif decision_margin < 3.0:
            confidence = "moderate"
        else:
            confidence = "strong"

        usable_recommendation = bool(
            not trade_floor_override
            and bool(winner["eligible_by_min_trades"])
            and str(winner["outcome"]) == "improve"
            and _safe_float(winner["score"]) > 0
            and _safe_float(winner["delta_average_return"]) >= 0
            and _safe_float(winner["delta_win_rate"]) >= 0
        )

        row = {
            "ticker": ticker,
            "config_id": str(winner["config_id"]),
            "best_threshold": float(winner["volume_spike_threshold"]),
            "best_strict_mode": bool(winner["strict_mode"]),
            "decision_confidence": confidence,
            "decision_margin": decision_margin,
            "trade_floor_override": trade_floor_override,
            "usable_recommendation": usable_recommendation,
            "outcome": str(winner["outcome"]),
            "baseline_threshold": float(winner["baseline_threshold"]),
            "baseline_strict_mode": bool(winner["baseline_strict_mode"]),
            "baseline_total_trades": int(winner["baseline_total_trades"]),
            "total_trades": int(winner["total_trades"]),
            "delta_total_trades": int(winner["delta_total_trades"]),
            "trade_retention_pct": float(winner["trade_retention_pct"]),
            "baseline_win_rate": float(winner["baseline_win_rate"]),
            "win_rate": float(winner["win_rate"]),
            "delta_win_rate": float(winner["delta_win_rate"]),
            "baseline_average_return": float(winner["baseline_average_return"]),
            "average_return": float(winner["average_return"]),
            "delta_average_return": float(winner["delta_average_return"]),
            "baseline_max_drawdown": float(winner["baseline_max_drawdown"]),
            "max_drawdown": float(winner["max_drawdown"]),
            "delta_max_drawdown": float(winner["delta_max_drawdown"]),
            "score": float(winner["score"]),
            "selection_reason": _ticker_selection_reason(
                winner=winner,
                trade_floor_override=trade_floor_override,
                confidence=confidence,
            ),
            "category": winner.get("category"),
            "market_cap_group": winner.get("market_cap_group"),
            "sector": winner.get("sector"),
            "beta_group": winner.get("beta_group"),
        }
        rows.append(row)

    best_df = pd.DataFrame(rows)
    return best_df.reindex(columns=BEST_TICKER_COLUMNS).sort_values(
        ["usable_recommendation", "decision_confidence", "score", "ticker"],
        ascending=[False, True, False, True],
        key=lambda series: (
            series.map({"strong": 0, "moderate": 1, "low": 2})
            if series.name == "decision_confidence"
            else series
        ),
    ).reset_index(drop=True)


def _group_selection_reason(winner: pd.Series, confidence: str) -> str:
    reason = (
        f"Config {winner['config_id']} dipilih untuk group ini karena mean score adaptive paling baik."
    )
    reason += (
        f" ticker_count={_safe_int(winner['ticker_count'])}, "
        f"eligible_ticker_count={_safe_int(winner['eligible_ticker_count'])}, "
        f"delta_win_rate_mean={_safe_float(winner['delta_win_rate_mean']):+.2f}, "
        f"delta_average_return_mean={_safe_float(winner['delta_average_return_mean']):+.4f}."
    )
    if confidence == "low":
        reason += " Confidence group masih rendah karena margin tipis atau sample kecil."
    return reason


def summarize_group_recommendations(
    results_df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    if results_df.empty or metadata_df is None or metadata_df.empty:
        return pd.DataFrame(columns=GROUP_RECOMMENDATION_COLUMNS)

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
            working.groupby([field, "config_id", "volume_spike_threshold", "strict_mode"], dropna=False)
            .agg(
                ticker_count=("ticker", "nunique"),
                eligible_ticker_count=("eligible_by_min_trades", "sum"),
                improve_count=("outcome", lambda values: int((values == "improve").sum())),
                neutral_count=("outcome", lambda values: int((values == "neutral").sum())),
                worsen_count=("outcome", lambda values: int((values == "worsen").sum())),
                trade_retention_mean_pct=("trade_retention_pct", "mean"),
                delta_win_rate_mean=("delta_win_rate", "mean"),
                delta_average_return_mean=("delta_average_return", "mean"),
                delta_max_drawdown_mean=("delta_max_drawdown", "mean"),
                mean_score=("score", "mean"),
                median_score=("score", "median"),
            )
            .reset_index()
            .rename(columns={field: "group_value"})
        )
        grouped["group_field"] = field
        rows.extend(grouped.to_dict(orient="records"))

    if not rows:
        return pd.DataFrame(columns=GROUP_RECOMMENDATION_COLUMNS)

    summary_df = pd.DataFrame(rows)
    output_rows: List[Dict[str, object]] = []
    for (group_field, group_value), group_df in summary_df.groupby(["group_field", "group_value"], sort=True):
        working = group_df.copy()
        eligible = working.loc[working["eligible_ticker_count"] >= GROUP_MIN_TICKERS].copy()
        sample_override = eligible.empty
        candidate_pool = eligible if not sample_override else working
        ranked = candidate_pool.sort_values(
            [
                "mean_score",
                "eligible_ticker_count",
                "ticker_count",
                "delta_average_return_mean",
                "delta_win_rate_mean",
            ],
            ascending=[False, False, False, False, False],
        ).reset_index(drop=True)
        winner = ranked.iloc[0]
        runner_up = ranked.iloc[1] if len(ranked) > 1 else None
        decision_margin = float(winner["mean_score"] - runner_up["mean_score"]) if runner_up is not None else np.nan

        if sample_override or _safe_int(winner["eligible_ticker_count"]) < GROUP_MIN_TICKERS:
            confidence = "low"
        elif pd.isna(decision_margin) or decision_margin < 1.0:
            confidence = "low"
        elif decision_margin < 2.5:
            confidence = "moderate"
        else:
            confidence = "strong"

        recommended_for_group = bool(
            _safe_int(winner["eligible_ticker_count"]) >= GROUP_MIN_TICKERS
            and _safe_float(winner["mean_score"]) > 0
            and _safe_float(winner["delta_average_return_mean"]) >= 0
            and _safe_float(winner["delta_win_rate_mean"]) >= 0
            and _safe_int(winner["improve_count"]) >= _safe_int(winner["worsen_count"])
        )

        output_rows.append(
            {
                "group_field": group_field,
                "group_value": group_value,
                "config_id": str(winner["config_id"]),
                "best_threshold": float(winner["volume_spike_threshold"]),
                "best_strict_mode": bool(winner["strict_mode"]),
                "decision_confidence": confidence,
                "decision_margin": decision_margin,
                "ticker_count": int(winner["ticker_count"]),
                "eligible_ticker_count": int(winner["eligible_ticker_count"]),
                "improve_count": int(winner["improve_count"]),
                "neutral_count": int(winner["neutral_count"]),
                "worsen_count": int(winner["worsen_count"]),
                "trade_retention_mean_pct": float(winner["trade_retention_mean_pct"]),
                "delta_win_rate_mean": float(winner["delta_win_rate_mean"]),
                "delta_average_return_mean": float(winner["delta_average_return_mean"]),
                "delta_max_drawdown_mean": float(winner["delta_max_drawdown_mean"]),
                "mean_score": float(winner["mean_score"]),
                "median_score": float(winner["median_score"]),
                "sample_status": "enough_sample" if not sample_override else "insufficient_sample",
                "recommended_for_group": recommended_for_group,
                "selection_reason": _group_selection_reason(winner=winner, confidence=confidence),
            }
        )

    group_df = pd.DataFrame(output_rows)
    return group_df.reindex(columns=GROUP_RECOMMENDATION_COLUMNS).sort_values(
        ["recommended_for_group", "decision_confidence", "mean_score", "group_field", "group_value"],
        ascending=[False, True, False, True, True],
        key=lambda series: (
            series.map({"strong": 0, "moderate": 1, "low": 2})
            if series.name == "decision_confidence"
            else series
        ),
    ).reset_index(drop=True)


def determine_item8_go_no_go(
    best_by_ticker_df: pd.DataFrame,
    group_recommendations_df: Optional[pd.DataFrame] = None,
) -> Dict[str, object]:
    if best_by_ticker_df.empty:
        return {
            "decision": "no_go",
            "experiment_status": "completed",
            "adaptive_model_supported": False,
            "promote_ticker_specific": False,
            "promote_group_specific": False,
            "recommended_tickers": [],
            "recommended_groups": [],
            "blocked_from_broader_promotion": ["Adaptive sweep item 8 tidak menghasilkan evaluasi ticker."],
            "next_action": "stop",
            "item8_experiment_status": "failed",
            "item8_next_action": "stop",
        }

    recommended_tickers = (
        best_by_ticker_df.loc[
            best_by_ticker_df["usable_recommendation"] & best_by_ticker_df["decision_confidence"].ne("low"),
            "ticker",
        ]
        .astype(str)
        .tolist()
    )
    recommended_groups: List[str] = []
    if group_recommendations_df is not None and not group_recommendations_df.empty:
        recommended_groups = (
            group_recommendations_df.loc[group_recommendations_df["recommended_for_group"]]
            .apply(lambda row: f"{row['group_field']}={row['group_value']}", axis=1)
            .astype(str)
            .tolist()
        )

    positive_eligible_count = int(
        (
            best_by_ticker_df["usable_recommendation"]
            | (
                best_by_ticker_df["total_trades"].ge(1)
                & best_by_ticker_df["score"].gt(0)
                & best_by_ticker_df["decision_confidence"].ne("low")
            )
        ).sum()
    )
    ticker_count = int(len(best_by_ticker_df))
    blocked_from_broader_promotion: List[str] = []
    if len(recommended_tickers) < max(2, math.ceil(ticker_count * 0.4)):
        blocked_from_broader_promotion.append("Ticker yang benar-benar layak masih terlalu sedikit.")
    if not recommended_groups:
        blocked_from_broader_promotion.append("Belum ada group dengan sinyal adaptive yang cukup konsisten.")
    if int((best_by_ticker_df["trade_floor_override"]).sum()) > 0:
        blocked_from_broader_promotion.append("Sebagian ticker masih tidak punya kandidat yang lolos min_trades.")
    if int((best_by_ticker_df["outcome"] == "worsen").sum()) >= max(1, int((best_by_ticker_df["outcome"] == "improve").sum())):
        blocked_from_broader_promotion.append("Ticker yang memburuk masih terlalu banyak dibanding yang improve.")

    if recommended_groups and recommended_tickers:
        decision = "promote_for_subset"
        next_action = "promote_subset"
        experiment_status = "promising"
        adaptive_model_supported = True
    elif recommended_groups:
        decision = "promote_group_specific"
        next_action = "promote_group_specific"
        experiment_status = "promising"
        adaptive_model_supported = True
    elif recommended_tickers:
        decision = "promote_ticker_specific"
        next_action = "promote_ticker_specific"
        experiment_status = "promising"
        adaptive_model_supported = True
    elif positive_eligible_count > 0:
        decision = "keep_experimental"
        next_action = "continue_tuning"
        experiment_status = "mixed"
        adaptive_model_supported = True
    else:
        decision = "no_go"
        next_action = "stop"
        experiment_status = "failed"
        adaptive_model_supported = False

    return {
        "decision": decision,
        "experiment_status": "completed",
        "adaptive_model_supported": adaptive_model_supported,
        "promote_ticker_specific": decision in {"promote_ticker_specific", "promote_for_subset"},
        "promote_group_specific": decision in {"promote_group_specific", "promote_for_subset"},
        "recommended_tickers": recommended_tickers,
        "recommended_groups": recommended_groups,
        "blocked_from_broader_promotion": _dedupe(blocked_from_broader_promotion),
        "next_action": next_action,
        "item8_experiment_status": experiment_status,
        "item8_next_action": next_action,
    }


def build_global_summary_payload(
    data_dir: Path,
    output_dir: Path,
    baseline_path: Optional[Path],
    metadata_file: Optional[Path],
    thresholds: Sequence[float],
    strict_options: Sequence[bool],
    min_trades: int,
    results_df: pd.DataFrame,
    best_by_ticker_df: pd.DataFrame,
    group_recommendations_df: Optional[pd.DataFrame],
    go_no_go: Dict[str, object],
    notes: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    best_distribution: Dict[str, int] = {}
    if not best_by_ticker_df.empty:
        distribution = best_by_ticker_df["config_id"].value_counts().to_dict()
        best_distribution = {str(key): int(value) for key, value in distribution.items()}

    return {
        "generated_at": _now_iso(),
        "experiment_id": "phase_b_item8_adaptive_backtest",
        "data_dir": str(data_dir),
        "output_dir": str(output_dir),
        "baseline_config": str(baseline_path) if baseline_path else None,
        "metadata_file": str(metadata_file) if metadata_file else None,
        "thresholds_tested": [float(item) for item in thresholds],
        "strict_options_tested": [bool(item) for item in strict_options],
        "min_trades": int(min_trades),
        "ticker_count": int(results_df["ticker"].nunique()) if not results_df.empty else 0,
        "evaluated_config_count": int(len(results_df)),
        "eligible_best_ticker_count": int(best_by_ticker_df["usable_recommendation"].sum()) if not best_by_ticker_df.empty else 0,
        "recommended_ticker_count": int(len(go_no_go["recommended_tickers"])),
        "recommended_group_count": int(len(go_no_go["recommended_groups"])),
        "recommended_tickers": list(go_no_go["recommended_tickers"]),
        "recommended_groups": list(go_no_go["recommended_groups"]),
        "best_config_distribution": best_distribution,
        "ticker_outcome_counts": {
            "improve": int((best_by_ticker_df["outcome"] == "improve").sum()) if not best_by_ticker_df.empty else 0,
            "neutral": int((best_by_ticker_df["outcome"] == "neutral").sum()) if not best_by_ticker_df.empty else 0,
            "worsen": int((best_by_ticker_df["outcome"] == "worsen").sum()) if not best_by_ticker_df.empty else 0,
        },
        "adaptive_model_supported": bool(go_no_go["adaptive_model_supported"]),
        "decision": str(go_no_go["decision"]),
        "group_analysis_available": bool(group_recommendations_df is not None),
        "artifacts": {
            "adaptive_results_csv": str(output_dir / "phase_b_item8_adaptive_results.csv"),
            "best_config_per_ticker_csv": str(output_dir / "phase_b_item8_best_config_per_ticker.csv"),
            "group_recommendations_csv": str(output_dir / "phase_b_item8_group_recommendations.csv"),
            "global_summary_json": str(output_dir / "phase_b_item8_global_summary.json"),
            "recommendations_txt": str(output_dir / "phase_b_item8_recommendations.txt"),
            "go_no_go_json": str(output_dir / "phase_b_item8_go_no_go.json"),
        },
        "notes": list(notes or []),
    }


def build_recommendations_text(
    go_no_go: Dict[str, object],
    best_by_ticker_df: pd.DataFrame,
    group_recommendations_df: Optional[pd.DataFrame],
    notes: Optional[Sequence[str]] = None,
) -> str:
    lines = [
        "Phase B Item 8 Adaptive Recommendations",
        "=======================================",
        "",
        f"- Decision: {go_no_go['decision']}",
        f"- Adaptive model supported: {go_no_go['adaptive_model_supported']}",
        f"- Promote ticker specific: {go_no_go['promote_ticker_specific']}",
        f"- Promote group specific: {go_no_go['promote_group_specific']}",
        f"- Next action: {go_no_go['next_action']}",
        "",
        "Recommended tickers:",
    ]
    if go_no_go["recommended_tickers"]:
        for item in go_no_go["recommended_tickers"]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    lines.extend(["", "Recommended groups:"])
    if go_no_go["recommended_groups"]:
        for item in go_no_go["recommended_groups"]:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    lines.extend(["", "Blocked from broader promotion:"])
    blocked = list(go_no_go.get("blocked_from_broader_promotion") or [])
    if blocked:
        for item in blocked:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    if not best_by_ticker_df.empty:
        lines.extend(["", "Top ticker selections:"])
        for _, row in best_by_ticker_df.head(5).iterrows():
            lines.append(
                "- "
                f"{row['ticker']}: {row['config_id']} "
                f"(score={_safe_float(row['score']):+.3f}, "
                f"trades={_safe_int(row['total_trades'])}, "
                f"usable={bool(row['usable_recommendation'])})"
            )

    if group_recommendations_df is not None and not group_recommendations_df.empty:
        lines.extend(["", "Top group selections:"])
        for _, row in group_recommendations_df.head(5).iterrows():
            lines.append(
                "- "
                f"{row['group_field']}={row['group_value']}: {row['config_id']} "
                f"(mean_score={_safe_float(row['mean_score']):+.3f}, "
                f"recommended={bool(row['recommended_for_group'])})"
            )

    lines.extend(["", "Notes:"])
    if notes:
        for item in notes:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def run_phase_b_item8_adaptive_backtest(
    data_dir: Path,
    output_dir: Path,
    baseline_config: Path,
    metadata_file: Optional[Path] = None,
    thresholds: Optional[Sequence[float]] = None,
    strict_options: Optional[Sequence[object]] = None,
    min_trades: int = 8,
    hold_period: int = 5,
    allow_overlap: bool = False,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    baseline_config = Path(baseline_config)
    normalized_thresholds = _normalize_thresholds(thresholds)
    normalized_strict_options = _normalize_strict_options(strict_options)

    if min_trades < 1:
        raise Item8AdaptiveCliError("--min-trades must be >= 1.")
    if not baseline_config.exists():
        raise Item8AdaptiveCliError(
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

    notes = [*baseline_warnings, *metadata_warnings, *metadata_analysis_warnings]
    for warning in notes:
        print(f"warning: {warning}")

    rows: List[Dict[str, object]] = []
    for path in csv_files:
        rows.extend(
            run_item8_evaluations_for_ticker(
                path=path,
                baseline_payload=baseline_payload,
                metadata_lookup=metadata_lookup,
                thresholds=normalized_thresholds,
                strict_options=normalized_strict_options,
                hold_period=hold_period,
                allow_overlap=allow_overlap,
                min_trades=min_trades,
            )
        )

    results_df = build_results_dataframe(rows)
    best_by_ticker_df = select_best_config_per_ticker(results_df=results_df, min_trades=min_trades)
    group_recommendations_df = summarize_group_recommendations(results_df=results_df, metadata_df=metadata_df)
    if group_recommendations_df.empty:
        group_recommendations_df = None

    if not best_by_ticker_df.empty and int(best_by_ticker_df["usable_recommendation"].sum()) == 0:
        notes.append(
            f"Tidak ada konfigurasi adaptive yang lolos min_trades={int(min_trades)} sekaligus memperbaiki baseline secara konsisten."
        )

    go_no_go = determine_item8_go_no_go(
        best_by_ticker_df=best_by_ticker_df,
        group_recommendations_df=group_recommendations_df,
    )
    global_summary = build_global_summary_payload(
        data_dir=data_dir,
        output_dir=output_dir,
        baseline_path=resolved_baseline,
        metadata_file=metadata_file,
        thresholds=normalized_thresholds,
        strict_options=normalized_strict_options,
        min_trades=min_trades,
        results_df=results_df,
        best_by_ticker_df=best_by_ticker_df,
        group_recommendations_df=group_recommendations_df,
        go_no_go=go_no_go,
        notes=notes,
    )
    recommendations_text = build_recommendations_text(
        go_no_go=go_no_go,
        best_by_ticker_df=best_by_ticker_df,
        group_recommendations_df=group_recommendations_df,
        notes=notes,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "phase_b_item8_adaptive_results.csv"
    best_path = output_dir / "phase_b_item8_best_config_per_ticker.csv"
    group_path = output_dir / "phase_b_item8_group_recommendations.csv"
    summary_path = output_dir / "phase_b_item8_global_summary.json"
    recommendations_path = output_dir / "phase_b_item8_recommendations.txt"
    go_no_go_path = output_dir / "phase_b_item8_go_no_go.json"

    results_df.to_csv(results_path, index=False)
    best_by_ticker_df.to_csv(best_path, index=False)
    if metadata_df is not None:
        group_output_df = (
            group_recommendations_df
            if group_recommendations_df is not None
            else pd.DataFrame(columns=GROUP_RECOMMENDATION_COLUMNS)
        )
        group_output_df.to_csv(group_path, index=False)
    elif group_path.exists():
        group_path.unlink()
    summary_path.write_text(
        json.dumps(_sanitize_for_json(global_summary), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    recommendations_path.write_text(recommendations_text, encoding="utf-8")
    go_no_go_path.write_text(
        json.dumps(_sanitize_for_json(go_no_go), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    print(f"Saved item 8 adaptive results to {results_path}")
    print(f"Saved item 8 best-by-ticker summary to {best_path}")
    if metadata_df is not None:
        print(f"Saved item 8 group recommendations to {group_path}")
    print(f"Saved item 8 global summary JSON to {summary_path}")
    print(f"Saved item 8 recommendations to {recommendations_path}")
    print(f"Saved item 8 go/no-go JSON to {go_no_go_path}")

    return {
        "results_df": results_df,
        "best_by_ticker_df": best_by_ticker_df,
        "group_recommendations_df": group_recommendations_df,
        "global_summary": global_summary,
        "go_no_go": go_no_go,
        "artifacts": {
            "adaptive_results_csv": results_path,
            "best_config_per_ticker_csv": best_path,
            "group_recommendations_csv": group_path,
            "global_summary_json": summary_path,
            "recommendations_txt": recommendations_path,
            "go_no_go_json": go_no_go_path,
        },
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Phase B item 8 adaptive threshold/strict backtests per ticker."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing per-ticker OHLCV CSV files. Default: data",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory receiving the item-8 artifacts. Default: output",
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
        default=DEFAULT_THRESHOLDS,
        help="Requested adaptive volume spike thresholds. Default: 1.5 2.0 2.5",
    )
    parser.add_argument(
        "--strict-options",
        nargs="*",
        default=["false", "true"],
        help="Requested strict-mode options. Default: false true",
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
        help="Allow overlapping trades during backtest evaluation.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run_phase_b_item8_adaptive_backtest(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            baseline_config=Path(args.baseline_config),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            thresholds=args.thresholds,
            strict_options=args.strict_options,
            min_trades=args.min_trades,
            hold_period=args.hold_period,
            allow_overlap=args.allow_overlap,
        )
    except Item8AdaptiveCliError as exc:
        print(str(exc))
        for step in exc.suggestions:
            print(step)
        return 1
    except Exception as exc:
        print(f"Unexpected item 8 adaptive backtest failure: {exc}")
        return 1

    print(f"Item 8 decision: {result['go_no_go']['decision']}")
    print(f"Recommended tickers: {len(result['go_no_go']['recommended_tickers'])}")
    print(f"Recommended groups: {len(result['go_no_go']['recommended_groups'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
