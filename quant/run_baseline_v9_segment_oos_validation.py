"""Run anchored out-of-sample walk-forward validation for the v8 segment-only candidate."""

from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.evaluate_phase_a_real_data import load_price_csv  # noqa: E402
from quant.phase_a import backtest_signal_frame  # noqa: E402
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402
from quant.run_baseline_v2_candidate_validation import (  # noqa: E402
    _candidate_signal,
    _compute_score_components,
    _feature_frame,
    _safe_float,
    _safe_int,
)
from quant.run_baseline_v6_guardrail_review import _write_json, _write_text  # noqa: E402


RESULT_OUTPUT = "baseline_v9_segment_oos_results.csv"
SUMMARY_OUTPUT = "baseline_v9_segment_oos_summary.json"
REPORT_OUTPUT = "baseline_v9_segment_oos_report.txt"
GO_NO_GO_OUTPUT = "baseline_v9_segment_oos_go_no_go.json"

DECISION_VALUES = {
    "stay_promote_to_segment_only_validation",
    "keep_experimental_for_segment_only_use",
    "no_go_even_for_segment",
}
RESULT_COLUMNS = [
    "row_type",
    "candidate_id",
    "segment_role",
    "tested_segment",
    "segment_field",
    "segment_value",
    "ticker",
    "fold_id",
    "fold_start",
    "fold_end",
    "warmup_bars",
    "fold_size_bars",
    "entry_rule",
    "hold_period",
    "min_trades_threshold",
    "applied_threshold",
    "candidate_signal_count",
    "candidate_total_trades",
    "win_rate",
    "average_return",
    "max_drawdown",
    "score",
    "trade_return_sum",
    "ticker_count",
    "active_ticker_count",
    "positive_ticker_count",
    "mean_average_return_all",
    "mean_average_return_active",
    "trade_weighted_average_return",
    "median_average_return_active",
    "active_fold_count",
    "positive_fold_count",
    "positive_fold_share",
    "top_abs_pnl_share",
    "top_positive_pnl_share",
    "outlier_bias_ok",
    "ticker_consistency_ok",
    "oos_stability_ok",
    "robustness_check_passed",
]


class BaselineV9SegmentOosCliError(ValueError):
    """Friendly CLI error for baseline v9 segment OOS validation."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _parse_segment_spec(spec: str) -> Tuple[str, str]:
    token = str(spec or "").strip()
    if "=" not in token:
        raise BaselineV9SegmentOosCliError(f"Invalid segment spec: {spec}")
    field, value = token.split("=", 1)
    field = field.strip()
    value = value.strip()
    if not field or not value:
        raise BaselineV9SegmentOosCliError(f"Invalid segment spec: {spec}")
    return field, value


def _sanitize_for_json(value: object) -> object:
    if isinstance(value, dict):
        return {key: _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def _load_required_object(output_dir: Path, filename: str) -> Dict[str, object]:
    payload, _ = read_json_object(Path(output_dir) / filename, filename)
    result = payload if isinstance(payload, dict) else {}
    if not result:
        raise BaselineV9SegmentOosCliError(f"{filename} is required before running v9.")
    return result


def _validate_roadmap_constraints(output_dir: Path) -> Dict[str, object]:
    phase_a = _load_required_object(output_dir, "phase_a_final_status.json")
    phase_b = _load_required_object(output_dir, "phase_b_final_status.json")
    project_status = _load_required_object(output_dir, "project_roadmap_status.json")
    latest = safe_dict(project_status.get("latest_execution_status"))

    if str(phase_a.get("status")) != "closed_with_notes":
        raise BaselineV9SegmentOosCliError("v9 requires Phase A status=closed_with_notes.")
    if str(phase_b.get("phase_b_status")) != "phase_b_needs_redesign_before_continue":
        raise BaselineV9SegmentOosCliError(
            "v9 requires phase_b_status=phase_b_needs_redesign_before_continue."
        )
    if str(latest.get("phase_c_decision")) != "phase_c_no_go_yet":
        raise BaselineV9SegmentOosCliError("v9 cannot continue when Phase C is no longer blocked.")

    return {
        "phase_a_status": phase_a.get("status"),
        "phase_b_status": phase_b.get("phase_b_status"),
        "phase_c_decision": latest.get("phase_c_decision"),
    }


def _load_v8_context(output_dir: Path) -> Dict[str, object]:
    go_no_go = _load_required_object(output_dir, "baseline_v8_segment_only_validation_go_no_go.json")
    if str(go_no_go.get("decision")) != "promote_to_segment_only_validation":
        raise BaselineV9SegmentOosCliError(
            "v9 requires baseline_v8 decision=promote_to_segment_only_validation."
        )
    if _safe_bool(go_no_go.get("global_promotion_allowed")):
        raise BaselineV9SegmentOosCliError("v9 cannot run when global promotion is already allowed.")
    return go_no_go


def _load_segmentation(output_dir: Path) -> pd.DataFrame:
    path = Path(output_dir) / "baseline_v6_universe_segmentation.csv"
    if not path.exists():
        raise BaselineV9SegmentOosCliError(f"Required segmentation file not found: {path}")
    frame = pd.read_csv(path)
    if frame.empty or "ticker" not in frame.columns:
        raise BaselineV9SegmentOosCliError(f"{path} does not contain usable segmentation rows.")
    result = frame.copy()
    result["ticker"] = result["ticker"].astype(str).str.upper().str.strip()
    return result


def _resolve_candidate_config(output_dir: Path, candidate_id: str) -> Dict[str, object]:
    path = Path(output_dir) / "baseline_v3_signal_rule_results.csv"
    if not path.exists():
        raise BaselineV9SegmentOosCliError(f"Required v3 results not found: {path}")
    frame = pd.read_csv(path)
    subset = frame.loc[frame["rule_id"].astype(str).eq(str(candidate_id))].copy()
    if subset.empty:
        raise BaselineV9SegmentOosCliError(f"Candidate {candidate_id} not found in {path.name}.")

    row = dict(subset.iloc[0].to_dict())
    return {
        "candidate_id": candidate_id,
        "entry_rule": str(row.get("entry_rule") or "").strip() or "close_gt_ema20_and_bullish_candle",
        "hold_period": _safe_int(row.get("hold_period"), 3),
        "min_trades_threshold": _safe_int(row.get("min_trades_threshold"), 5),
        "profit_buffer_pct": _safe_float(row.get("profit_buffer_pct"), 0.0),
    }


def _resolve_tested_segments(
    *,
    governance: Dict[str, object],
    v8_go_no_go: Dict[str, object],
) -> List[Dict[str, str]]:
    primary_segment = str(v8_go_no_go.get("primary_segment") or "").strip()
    if not primary_segment:
        raise BaselineV9SegmentOosCliError("v8 go/no-go does not contain primary_segment.")

    supporting_segments = [
        str(item).strip()
        for item in list(
            v8_go_no_go.get("supporting_segments_checked")
            or v8_go_no_go.get("supporting_segments")
            or []
        )
        if str(item).strip()
    ]
    safe_segments = [
        str(item).strip()
        for item in list(governance.get("segments_safe_to_test_next") or [])
        if str(item).strip()
    ]

    ordered = dedupe([primary_segment, *supporting_segments, *safe_segments])
    tested: List[Dict[str, str]] = []
    for item in ordered:
        field, value = _parse_segment_spec(item)
        tested.append(
            {
                "tested_segment": item,
                "segment_field": field,
                "segment_value": value,
                "segment_role": "primary" if item == primary_segment else "supporting",
            }
        )
    return tested


def _resolve_segment_tickers(segmentation_df: pd.DataFrame, segment_field: str, segment_value: str) -> List[str]:
    if segment_field not in segmentation_df.columns:
        raise BaselineV9SegmentOosCliError(
            f"Segment field {segment_field} is missing from baseline_v6_universe_segmentation.csv."
        )
    return (
        segmentation_df.loc[
            segmentation_df[segment_field].astype(str).eq(str(segment_value)),
            "ticker",
        ]
        .astype(str)
        .str.upper()
        .tolist()
    )


def _resolve_walk_forward_spec(
    *,
    data_dir: Path,
    tested_segments: Sequence[Dict[str, str]],
    segmentation_df: pd.DataFrame,
    hold_period: int,
) -> Dict[str, object]:
    union_tickers: List[str] = []
    for segment in tested_segments:
        union_tickers.extend(
            _resolve_segment_tickers(
                segmentation_df,
                segment_field=str(segment["segment_field"]),
                segment_value=str(segment["segment_value"]),
            )
        )
    tickers = dedupe(union_tickers)
    if not tickers:
        raise BaselineV9SegmentOosCliError("No tickers resolved for v9 OOS validation.")

    row_counts: List[int] = []
    for ticker in tickers:
        path = Path(data_dir) / f"{ticker}.csv"
        if not path.exists():
            continue
        frame, _ = load_price_csv(path)
        row_counts.append(len(frame))
    if not row_counts:
        raise BaselineV9SegmentOosCliError("No usable price files were found for tested segments.")

    min_rows = min(row_counts)
    warmup_bars = max(21, int(hold_period) + 2)
    if min_rows <= warmup_bars:
        raise BaselineV9SegmentOosCliError(
            "Not enough rows to run OOS validation after EMA20 warmup."
        )

    available_oos_bars = min_rows - warmup_bars
    if available_oos_bars >= 18:
        fold_count = 3
    elif available_oos_bars >= 8:
        fold_count = 2
    else:
        fold_count = 1
    fold_size = int(math.ceil(available_oos_bars / float(fold_count)))

    fold_index_ranges: List[Tuple[int, int, int]] = []
    start_index = warmup_bars
    for fold_id in range(1, fold_count + 1):
        if start_index >= min_rows:
            break
        end_index = min(start_index + fold_size - 1, min_rows - 1)
        fold_index_ranges.append((fold_id, start_index, end_index))
        start_index = end_index + 1

    return {
        "warmup_bars": warmup_bars,
        "available_oos_bars": available_oos_bars,
        "fold_count": len(fold_index_ranges),
        "fold_size_bars": fold_size,
        "fold_index_ranges": fold_index_ranges,
        "min_rows_across_tested_tickers": min_rows,
        "tested_ticker_union": tickers,
    }


def _trade_metrics(trades_df: pd.DataFrame) -> Dict[str, float]:
    if trades_df.empty:
        return {
            "candidate_total_trades": 0,
            "win_rate": 0.0,
            "average_return": 0.0,
            "max_drawdown": 0.0,
            "trade_return_sum": 0.0,
        }

    ordered = trades_df.copy()
    ordered["return"] = pd.to_numeric(ordered["return"], errors="coerce").fillna(0.0)
    ordered["return_pct"] = pd.to_numeric(ordered["return_pct"], errors="coerce").fillna(0.0)
    equity = (1.0 + ordered["return"]).cumprod()
    running_peak = equity.cummax()
    drawdown = (equity / running_peak) - 1.0
    return {
        "candidate_total_trades": int(len(ordered)),
        "win_rate": round(float(ordered["return_pct"].gt(0.0).mean() * 100.0), 2),
        "average_return": round(float(ordered["return_pct"].mean()), 4),
        "max_drawdown": round(float(abs(drawdown.min()) * 100.0), 4),
        "trade_return_sum": round(float(ordered["return_pct"].sum()), 4),
    }


def _score_from_metrics(metrics: Dict[str, object], min_trades_threshold: int) -> float:
    components = _compute_score_components(
        total_trades=_safe_int(metrics.get("candidate_total_trades"), 0),
        buffered_win_rate=_safe_float(metrics.get("win_rate"), 0.0),
        average_return=_safe_float(metrics.get("average_return"), 0.0),
        max_drawdown=_safe_float(metrics.get("max_drawdown"), 0.0),
        min_trades_threshold=int(min_trades_threshold),
    )
    return float(components["score"])


def _evaluate_ticker_oos(
    *,
    ticker: str,
    data_dir: Path,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    candidate_config: Dict[str, object],
    walk_forward_spec: Dict[str, object],
) -> Dict[str, object]:
    path = Path(data_dir) / f"{ticker}.csv"
    if not path.exists():
        raise BaselineV9SegmentOosCliError(f"Ticker file not found for OOS validation: {path}")

    frame, _ = load_price_csv(path)
    runtime = resolve_phase_a_runtime_settings(
        ticker=ticker,
        baseline_config=baseline_payload,
        metadata_lookup=metadata_lookup,
    )
    feature_frame = _feature_frame(frame=frame, threshold=float(runtime["threshold"]))
    feature_frame, signal_column, resolved_entry_rule = _candidate_signal(
        feature_frame=feature_frame,
        candidate_id=str(candidate_config["candidate_id"]),
        threshold=float(runtime["threshold"]),
        entry_rule=str(candidate_config["entry_rule"]),
    )

    dates = pd.to_datetime(feature_frame["date"], errors="coerce")
    fold_ranges: List[Dict[str, object]] = []
    for fold_id, start_index, end_index in list(walk_forward_spec.get("fold_index_ranges") or []):
        fold_ranges.append(
            {
                "fold_id": int(fold_id),
                "start_date": dates.iloc[start_index],
                "end_date": dates.iloc[end_index],
            }
        )
    if not fold_ranges:
        raise BaselineV9SegmentOosCliError("Walk-forward fold ranges could not be resolved.")

    masked = feature_frame.copy()
    oos_start_date = fold_ranges[0]["start_date"]
    masked[signal_column] = masked[signal_column].fillna(False) & dates.ge(oos_start_date)
    result = backtest_signal_frame(
        masked,
        signal_column=signal_column,
        hold_period=_safe_int(candidate_config.get("hold_period"), 3),
        allow_overlap=False,
    )

    trades_df = result.trades.copy()
    if not trades_df.empty:
        trades_df["signal_date"] = pd.to_datetime(trades_df["signal_date"], errors="coerce")
        trades_df["return"] = pd.to_numeric(trades_df["return"], errors="coerce").fillna(0.0)
        trades_df["return_pct"] = pd.to_numeric(trades_df["return_pct"], errors="coerce").fillna(0.0)
        trades_df["ticker"] = ticker

    fold_rows: List[Dict[str, object]] = []
    for fold in fold_ranges:
        start_date = pd.Timestamp(fold["start_date"])
        end_date = pd.Timestamp(fold["end_date"])
        signal_mask = dates.ge(start_date) & dates.le(end_date)
        signal_count = int(masked.loc[signal_mask, signal_column].fillna(False).astype(bool).sum())
        fold_trades = (
            trades_df.loc[
                trades_df["signal_date"].ge(start_date) & trades_df["signal_date"].le(end_date)
            ].copy()
            if not trades_df.empty
            else pd.DataFrame(columns=["return", "return_pct"])
        )
        metrics = _trade_metrics(fold_trades)
        fold_rows.append(
            {
                "fold_id": int(fold["fold_id"]),
                "fold_start": str(start_date.date()),
                "fold_end": str(end_date.date()),
                "candidate_signal_count": signal_count,
                **metrics,
                "score": round(
                    _score_from_metrics(
                        metrics=metrics,
                        min_trades_threshold=_safe_int(candidate_config.get("min_trades_threshold"), 5),
                    ),
                    4,
                ),
            }
        )

    overall_metrics = _trade_metrics(trades_df)
    overall_row = {
        "candidate_signal_count": int(masked[signal_column].fillna(False).astype(bool).sum()),
        **overall_metrics,
        "score": round(
            _score_from_metrics(
                metrics=overall_metrics,
                min_trades_threshold=_safe_int(candidate_config.get("min_trades_threshold"), 5),
            ),
            4,
        ),
    }

    return {
        "ticker": ticker,
        "entry_rule": resolved_entry_rule,
        "applied_threshold": float(runtime["threshold"]),
        "fold_rows": fold_rows,
        "overall_row": overall_row,
        "trades_df": trades_df,
    }


def _segment_summary(
    *,
    segment_info: Dict[str, str],
    segment_tickers: Sequence[str],
    ticker_results: Dict[str, Dict[str, object]],
    min_trades_threshold: int,
) -> Dict[str, object]:
    overall_rows: List[Dict[str, object]] = []
    fold_bucket: Dict[int, List[Dict[str, object]]] = {}
    trade_frames: List[pd.DataFrame] = []

    for ticker in segment_tickers:
        result = ticker_results.get(ticker)
        if result is None:
            continue
        overall = dict(result["overall_row"])
        overall["ticker"] = ticker
        overall_rows.append(overall)

        for fold in list(result["fold_rows"]):
            fold_bucket.setdefault(int(fold["fold_id"]), []).append({"ticker": ticker, **fold})

        trade_df = result["trades_df"]
        if not trade_df.empty:
            trade_frames.append(trade_df.copy())

    if not overall_rows:
        raise BaselineV9SegmentOosCliError(
            f"Segment {segment_info['tested_segment']} has no ticker OOS results."
        )

    overall_df = pd.DataFrame(overall_rows)
    active_df = overall_df.loc[overall_df["candidate_total_trades"].fillna(0).astype(int).gt(0)].copy()
    positive_active_df = active_df.loc[active_df["average_return"].fillna(0.0).gt(0.0)].copy()

    fold_summaries: List[Dict[str, object]] = []
    active_fold_count = 0
    positive_fold_count = 0
    for fold_id in sorted(fold_bucket):
        fold_df = pd.DataFrame(fold_bucket[fold_id])
        active_fold_df = fold_df.loc[fold_df["candidate_total_trades"].fillna(0).astype(int).gt(0)].copy()
        if not active_fold_df.empty:
            active_fold_count += 1

        trade_weighted_average_return = (
            round(
                float(active_fold_df["trade_return_sum"].sum() / active_fold_df["candidate_total_trades"].sum()),
                4,
            )
            if not active_fold_df.empty and float(active_fold_df["candidate_total_trades"].sum()) > 0.0
            else 0.0
        )
        if trade_weighted_average_return > 0.0:
            positive_fold_count += 1

        fold_summaries.append(
            {
                "fold_id": int(fold_id),
                "fold_start": fold_df["fold_start"].astype(str).iloc[0],
                "fold_end": fold_df["fold_end"].astype(str).iloc[0],
                "ticker_count": int(len(fold_df)),
                "active_ticker_count": int(len(active_fold_df)),
                "candidate_signal_count": int(fold_df["candidate_signal_count"].fillna(0).sum()),
                "candidate_total_trades": int(fold_df["candidate_total_trades"].fillna(0).sum()),
                "mean_average_return_all": round(float(fold_df["average_return"].fillna(0.0).mean()), 4),
                "mean_average_return_active": round(float(active_fold_df["average_return"].mean()), 4)
                if not active_fold_df.empty
                else 0.0,
                "trade_weighted_average_return": trade_weighted_average_return,
            }
        )

    combined_trades = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    ticker_pnl = (
        combined_trades.groupby("ticker")["return_pct"].sum().sort_values(ascending=False)
        if not combined_trades.empty
        else pd.Series(dtype=float)
    )
    total_abs_pnl = float(ticker_pnl.abs().sum()) if not ticker_pnl.empty else 0.0
    positive_pnl = ticker_pnl.loc[ticker_pnl.gt(0.0)] if not ticker_pnl.empty else pd.Series(dtype=float)

    total_trades_sum = int(overall_df["candidate_total_trades"].fillna(0).sum())
    active_ticker_count = int(len(active_df))
    positive_ticker_count = int(len(positive_active_df))
    positive_ticker_share = (
        float(positive_ticker_count) / float(active_ticker_count) if active_ticker_count > 0 else 0.0
    )
    mean_average_return_all = round(float(overall_df["average_return"].fillna(0.0).mean()), 4)
    mean_average_return_active = round(float(active_df["average_return"].mean()), 4) if not active_df.empty else 0.0
    median_average_return_active = round(float(active_df["average_return"].median()), 4) if not active_df.empty else 0.0
    trade_weighted_average_return = round(float(combined_trades["return_pct"].mean()), 4) if not combined_trades.empty else 0.0
    positive_fold_share = (
        round(float(positive_fold_count) / float(active_fold_count), 4) if active_fold_count > 0 else 0.0
    )
    top_abs_pnl_share = (
        round(float(ticker_pnl.abs().max() / total_abs_pnl), 4) if total_abs_pnl > 0.0 else 0.0
    )
    top_positive_pnl_share = (
        round(float(positive_pnl.max() / positive_pnl.sum()), 4)
        if not positive_pnl.empty and float(positive_pnl.sum()) > 0.0
        else 0.0
    )

    outlier_bias_ok = not (
        top_abs_pnl_share > 0.65
        or (top_positive_pnl_share > 0.80 and positive_ticker_count < 2 and trade_weighted_average_return > 0.0)
    )
    ticker_consistency_ok = bool(
        active_ticker_count >= 3 and positive_ticker_share >= 0.5 and median_average_return_active > 0.0
    )
    oos_stability_ok = bool(
        total_trades_sum >= max(10, int(min_trades_threshold) * 2)
        and active_fold_count >= 2
        and positive_fold_share >= 0.5
        and trade_weighted_average_return > 0.0
        and mean_average_return_active > 0.0
    )
    primary_viable = bool(
        total_trades_sum >= max(8, int(min_trades_threshold) + 3)
        and active_ticker_count >= 2
        and trade_weighted_average_return > 0.0
        and mean_average_return_active > 0.0
    )
    robustness_check_passed = bool(primary_viable and outlier_bias_ok)

    return {
        **segment_info,
        "tickers": list(segment_tickers),
        "ticker_count": int(len(overall_df)),
        "active_ticker_count": active_ticker_count,
        "positive_ticker_count": positive_ticker_count,
        "candidate_signal_count": int(overall_df["candidate_signal_count"].fillna(0).sum()),
        "candidate_total_trades": total_trades_sum,
        "mean_average_return_all": mean_average_return_all,
        "mean_average_return_active": mean_average_return_active,
        "trade_weighted_average_return": trade_weighted_average_return,
        "median_average_return_active": median_average_return_active,
        "mean_score_all": round(float(overall_df["score"].fillna(0.0).mean()), 4),
        "mean_score_active": round(float(active_df["score"].mean()), 4) if not active_df.empty else 0.0,
        "active_fold_count": active_fold_count,
        "positive_fold_count": positive_fold_count,
        "positive_fold_share": positive_fold_share,
        "top_abs_pnl_share": top_abs_pnl_share,
        "top_positive_pnl_share": top_positive_pnl_share,
        "outlier_bias_ok": bool(outlier_bias_ok),
        "ticker_consistency_ok": bool(ticker_consistency_ok),
        "oos_stability_ok": bool(oos_stability_ok),
        "primary_viable": bool(primary_viable),
        "robustness_check_passed": bool(robustness_check_passed),
        "fold_summaries": fold_summaries,
    }


def _build_results_frame(
    *,
    candidate_config: Dict[str, object],
    walk_forward_spec: Dict[str, object],
    tested_segments: Sequence[Dict[str, str]],
    segment_ticker_map: Dict[str, List[str]],
    ticker_results: Dict[str, Dict[str, object]],
    segment_summaries: Dict[str, Dict[str, object]],
) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for segment in tested_segments:
        tested_segment = str(segment["tested_segment"])
        summary = segment_summaries[tested_segment]

        for fold in list(summary["fold_summaries"]):
            rows.append(
                {
                    "row_type": "segment_fold",
                    "candidate_id": candidate_config["candidate_id"],
                    "segment_role": segment["segment_role"],
                    "tested_segment": tested_segment,
                    "segment_field": segment["segment_field"],
                    "segment_value": segment["segment_value"],
                    "ticker": "__segment__",
                    "fold_id": fold["fold_id"],
                    "fold_start": fold["fold_start"],
                    "fold_end": fold["fold_end"],
                    "warmup_bars": walk_forward_spec["warmup_bars"],
                    "fold_size_bars": walk_forward_spec["fold_size_bars"],
                    "entry_rule": candidate_config["entry_rule"],
                    "hold_period": candidate_config["hold_period"],
                    "min_trades_threshold": candidate_config["min_trades_threshold"],
                    "applied_threshold": None,
                    "candidate_signal_count": fold["candidate_signal_count"],
                    "candidate_total_trades": fold["candidate_total_trades"],
                    "win_rate": None,
                    "average_return": None,
                    "max_drawdown": None,
                    "score": None,
                    "trade_return_sum": None,
                    "ticker_count": fold["ticker_count"],
                    "active_ticker_count": fold["active_ticker_count"],
                    "positive_ticker_count": None,
                    "mean_average_return_all": fold["mean_average_return_all"],
                    "mean_average_return_active": fold["mean_average_return_active"],
                    "trade_weighted_average_return": fold["trade_weighted_average_return"],
                    "median_average_return_active": None,
                    "active_fold_count": None,
                    "positive_fold_count": None,
                    "positive_fold_share": None,
                    "top_abs_pnl_share": None,
                    "top_positive_pnl_share": None,
                    "outlier_bias_ok": None,
                    "ticker_consistency_ok": None,
                    "oos_stability_ok": None,
                    "robustness_check_passed": None,
                }
            )

        for ticker in segment_ticker_map[tested_segment]:
            ticker_result = ticker_results.get(ticker)
            if ticker_result is None:
                continue
            overall = dict(ticker_result["overall_row"])
            rows.append(
                {
                    "row_type": "ticker_oos_summary",
                    "candidate_id": candidate_config["candidate_id"],
                    "segment_role": segment["segment_role"],
                    "tested_segment": tested_segment,
                    "segment_field": segment["segment_field"],
                    "segment_value": segment["segment_value"],
                    "ticker": ticker,
                    "fold_id": None,
                    "fold_start": None,
                    "fold_end": None,
                    "warmup_bars": walk_forward_spec["warmup_bars"],
                    "fold_size_bars": walk_forward_spec["fold_size_bars"],
                    "entry_rule": ticker_result["entry_rule"],
                    "hold_period": candidate_config["hold_period"],
                    "min_trades_threshold": candidate_config["min_trades_threshold"],
                    "applied_threshold": ticker_result["applied_threshold"],
                    "candidate_signal_count": overall["candidate_signal_count"],
                    "candidate_total_trades": overall["candidate_total_trades"],
                    "win_rate": overall["win_rate"],
                    "average_return": overall["average_return"],
                    "max_drawdown": overall["max_drawdown"],
                    "score": overall["score"],
                    "trade_return_sum": overall["trade_return_sum"],
                    "ticker_count": None,
                    "active_ticker_count": None,
                    "positive_ticker_count": None,
                    "mean_average_return_all": None,
                    "mean_average_return_active": None,
                    "trade_weighted_average_return": None,
                    "median_average_return_active": None,
                    "active_fold_count": None,
                    "positive_fold_count": None,
                    "positive_fold_share": None,
                    "top_abs_pnl_share": None,
                    "top_positive_pnl_share": None,
                    "outlier_bias_ok": None,
                    "ticker_consistency_ok": None,
                    "oos_stability_ok": None,
                    "robustness_check_passed": None,
                }
            )

        rows.append(
            {
                "row_type": "segment_oos_summary",
                "candidate_id": candidate_config["candidate_id"],
                "segment_role": segment["segment_role"],
                "tested_segment": tested_segment,
                "segment_field": segment["segment_field"],
                "segment_value": segment["segment_value"],
                "ticker": "__segment__",
                "fold_id": None,
                "fold_start": None,
                "fold_end": None,
                "warmup_bars": walk_forward_spec["warmup_bars"],
                "fold_size_bars": walk_forward_spec["fold_size_bars"],
                "entry_rule": candidate_config["entry_rule"],
                "hold_period": candidate_config["hold_period"],
                "min_trades_threshold": candidate_config["min_trades_threshold"],
                "applied_threshold": None,
                "candidate_signal_count": summary["candidate_signal_count"],
                "candidate_total_trades": summary["candidate_total_trades"],
                "win_rate": None,
                "average_return": None,
                "max_drawdown": None,
                "score": summary["mean_score_all"],
                "trade_return_sum": None,
                "ticker_count": summary["ticker_count"],
                "active_ticker_count": summary["active_ticker_count"],
                "positive_ticker_count": summary["positive_ticker_count"],
                "mean_average_return_all": summary["mean_average_return_all"],
                "mean_average_return_active": summary["mean_average_return_active"],
                "trade_weighted_average_return": summary["trade_weighted_average_return"],
                "median_average_return_active": summary["median_average_return_active"],
                "active_fold_count": summary["active_fold_count"],
                "positive_fold_count": summary["positive_fold_count"],
                "positive_fold_share": summary["positive_fold_share"],
                "top_abs_pnl_share": summary["top_abs_pnl_share"],
                "top_positive_pnl_share": summary["top_positive_pnl_share"],
                "outlier_bias_ok": summary["outlier_bias_ok"],
                "ticker_consistency_ok": summary["ticker_consistency_ok"],
                "oos_stability_ok": summary["oos_stability_ok"],
                "robustness_check_passed": summary["robustness_check_passed"],
            }
        )

    results_df = pd.DataFrame(rows)
    if results_df.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    return results_df.reindex(columns=RESULT_COLUMNS)


def _determine_go_no_go(
    *,
    candidate_id: str,
    primary_summary: Dict[str, object],
    supporting_summaries: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    supporting_passed = [
        str(item["tested_segment"])
        for item in supporting_summaries
        if _safe_bool(item.get("robustness_check_passed"))
    ]
    supporting_failed = [
        str(item["tested_segment"])
        for item in supporting_summaries
        if not _safe_bool(item.get("robustness_check_passed"))
    ]

    primary_viable = _safe_bool(primary_summary.get("primary_viable"))
    oos_stability_ok = _safe_bool(primary_summary.get("oos_stability_ok"))
    ticker_consistency_ok = _safe_bool(primary_summary.get("ticker_consistency_ok"))
    outlier_bias_ok = _safe_bool(primary_summary.get("outlier_bias_ok"), True)
    supporting_all_ok = len(supporting_failed) == 0

    if not primary_viable:
        decision = "no_go_even_for_segment"
        next_action = "drop_candidate_from_primary_segment_even_for_experimental_use"
        notes = [
            "Primary segment gagal mempertahankan kualitas OOS minimum.",
            "Kandidat tidak stabil bahkan sebagai strategi subset eksperimental.",
        ]
    elif oos_stability_ok and ticker_consistency_ok and outlier_bias_ok and supporting_all_ok:
        decision = "stay_promote_to_segment_only_validation"
        next_action = "keep_candidate_in_segment_only_validation_primary_only_without_global_promotion"
        notes = [
            "Primary segment tetap layak setelah walk-forward OOS.",
            "Supporting safe segments tidak menunjukkan kontradiksi material.",
        ]
    else:
        decision = "keep_experimental_for_segment_only_use"
        next_action = "keep_candidate_as_experimental_primary_segment_only_and_monitor_more_oos"
        notes = [
            "Primary segment masih punya sinyal hidup, tetapi stabilitas OOS belum cukup bersih.",
            "Kandidat harus dibatasi hanya untuk pemakaian eksperimental subset tanpa promosi lebih lanjut.",
        ]

    payload = {
        "candidate_id": candidate_id,
        "primary_segment": primary_summary.get("tested_segment"),
        "decision": decision,
        "oos_stability_ok": bool(oos_stability_ok),
        "ticker_consistency_ok": bool(ticker_consistency_ok),
        "outlier_bias_ok": bool(outlier_bias_ok),
        "global_promotion_allowed": False,
        "recommended_next_action": next_action,
        "supporting_segments_checked": [str(item.get("tested_segment")) for item in supporting_summaries],
        "supporting_segments_passed": supporting_passed,
        "supporting_segments_failed": supporting_failed,
        "primary_total_trades_sum": primary_summary.get("candidate_total_trades"),
        "primary_active_ticker_count": primary_summary.get("active_ticker_count"),
        "primary_trade_weighted_average_return": primary_summary.get("trade_weighted_average_return"),
        "primary_mean_average_return_active": primary_summary.get("mean_average_return_active"),
        "decision_notes": dedupe(notes),
    }
    if payload["decision"] not in DECISION_VALUES:
        raise BaselineV9SegmentOosCliError("v9 decision must be explicit and valid.")
    return payload


def _build_summary_payload(
    *,
    roadmap_constraints: Dict[str, object],
    governance: Dict[str, object],
    v8_go_no_go: Dict[str, object],
    candidate_config: Dict[str, object],
    walk_forward_spec: Dict[str, object],
    tested_segments: Sequence[Dict[str, str]],
    segment_ticker_map: Dict[str, List[str]],
    segment_summaries: Dict[str, Dict[str, object]],
    go_no_go: Dict[str, object],
) -> Dict[str, object]:
    return {
        "generated_at": _now_iso(),
        "roadmap_constraints": roadmap_constraints,
        "input_context": {
            "baseline_v8_decision": v8_go_no_go.get("decision"),
            "candidate_id": candidate_config.get("candidate_id"),
            "primary_segment": v8_go_no_go.get("primary_segment"),
            "supporting_segments": list(
                v8_go_no_go.get("supporting_segments_checked")
                or v8_go_no_go.get("supporting_segments")
                or []
            ),
            "global_promotion_allowed": False,
        },
        "methodology": {
            "validation_mode": "anchored_walk_forward_oos",
            "candidate_frozen": True,
            "entry_exit_logic_changed": False,
            "global_guardrail_changed": False,
            "global_promotion_allowed": False,
            "warmup_bars": walk_forward_spec.get("warmup_bars"),
            "fold_count": walk_forward_spec.get("fold_count"),
            "fold_size_bars": walk_forward_spec.get("fold_size_bars"),
            "min_rows_across_tested_tickers": walk_forward_spec.get("min_rows_across_tested_tickers"),
            "hold_period": candidate_config.get("hold_period"),
            "entry_rule": candidate_config.get("entry_rule"),
            "min_trades_threshold": candidate_config.get("min_trades_threshold"),
        },
        "governance_snapshot": {
            "segments_safe_to_test_next": list(governance.get("segments_safe_to_test_next") or []),
            "what_to_keep_fixed": list(governance.get("what_to_keep_fixed") or []),
            "what_not_to_do": list(governance.get("what_not_to_do") or []),
        },
        "tested_segments": [
            {
                **segment,
                "tickers": list(segment_ticker_map[str(segment["tested_segment"])]),
                "summary": _sanitize_for_json(segment_summaries[str(segment["tested_segment"])]),
            }
            for segment in tested_segments
        ],
        "decision": _sanitize_for_json(go_no_go),
    }


def _build_report_text(
    *,
    candidate_config: Dict[str, object],
    walk_forward_spec: Dict[str, object],
    primary_summary: Dict[str, object],
    supporting_summaries: Sequence[Dict[str, object]],
    go_no_go: Dict[str, object],
) -> List[str]:
    lines = [
        "Baseline v9 Segment OOS Validation",
        "==================================",
        "",
        f"- Candidate: {candidate_config.get('candidate_id')}",
        f"- Primary segment: {primary_summary.get('tested_segment')}",
        f"- Entry rule: {candidate_config.get('entry_rule')}",
        f"- Hold period: {candidate_config.get('hold_period')}",
        f"- Walk-forward folds: {walk_forward_spec.get('fold_count')} x {walk_forward_spec.get('fold_size_bars')} bars",
        f"- Warmup bars: {walk_forward_spec.get('warmup_bars')}",
        f"- Decision: {go_no_go.get('decision')}",
        f"- OOS stability ok: {go_no_go.get('oos_stability_ok')}",
        f"- Ticker consistency ok: {go_no_go.get('ticker_consistency_ok')}",
        f"- Outlier bias ok: {go_no_go.get('outlier_bias_ok')}",
        f"- Global promotion allowed: {go_no_go.get('global_promotion_allowed')}",
        f"- Recommended next action: {go_no_go.get('recommended_next_action')}",
        "",
        "Primary segment OOS snapshot:",
        f"- ticker_count={primary_summary.get('ticker_count')} | active_ticker_count={primary_summary.get('active_ticker_count')} | total_trades={primary_summary.get('candidate_total_trades')}",
        f"- mean_average_return_all={primary_summary.get('mean_average_return_all')} | mean_average_return_active={primary_summary.get('mean_average_return_active')}",
        f"- trade_weighted_average_return={primary_summary.get('trade_weighted_average_return')} | positive_fold_share={primary_summary.get('positive_fold_share')}",
        f"- top_abs_pnl_share={primary_summary.get('top_abs_pnl_share')} | top_positive_pnl_share={primary_summary.get('top_positive_pnl_share')}",
        "",
        "Supporting robustness checks:",
    ]
    for item in supporting_summaries:
        lines.append(
            f"- {item.get('tested_segment')}: robustness_check_passed={item.get('robustness_check_passed')}, "
            f"total_trades={item.get('candidate_total_trades')}, trade_weighted_average_return={item.get('trade_weighted_average_return')}"
        )
    notes = list(go_no_go.get("decision_notes") or [])
    if notes:
        lines.extend(["", "Decision notes:"])
        for item in notes:
            lines.append(f"- {item}")
    return lines


def run_baseline_v9_segment_oos_validation(
    *,
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
    baseline_config: Optional[Path] = None,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not data_dir.exists() or not data_dir.is_dir():
        raise BaselineV9SegmentOosCliError(f"Data directory not found: {data_dir}")

    roadmap_constraints = _validate_roadmap_constraints(output_dir=output_dir)
    governance = _load_required_object(output_dir, "baseline_v6_next_experiment_governance.json")
    v8_go_no_go = _load_v8_context(output_dir=output_dir)
    segmentation_df = _load_segmentation(output_dir=output_dir)
    candidate_config = _resolve_candidate_config(
        output_dir=output_dir,
        candidate_id=str(v8_go_no_go.get("candidate_id") or "").strip(),
    )
    tested_segments = _resolve_tested_segments(governance=governance, v8_go_no_go=v8_go_no_go)

    baseline_payload, _, _ = load_phase_a_baseline(baseline_config)
    metadata_lookup, _ = load_optional_metadata_lookup(metadata_file)
    walk_forward_spec = _resolve_walk_forward_spec(
        data_dir=data_dir,
        tested_segments=tested_segments,
        segmentation_df=segmentation_df,
        hold_period=_safe_int(candidate_config.get("hold_period"), 3),
    )

    segment_ticker_map: Dict[str, List[str]] = {}
    for segment in tested_segments:
        tested_segment = str(segment["tested_segment"])
        segment_ticker_map[tested_segment] = _resolve_segment_tickers(
            segmentation_df,
            segment_field=str(segment["segment_field"]),
            segment_value=str(segment["segment_value"]),
        )

    ticker_results: Dict[str, Dict[str, object]] = {}
    for ticker in list(walk_forward_spec.get("tested_ticker_union") or []):
        ticker_results[ticker] = _evaluate_ticker_oos(
            ticker=ticker,
            data_dir=data_dir,
            baseline_payload=baseline_payload,
            metadata_lookup=metadata_lookup,
            candidate_config=candidate_config,
            walk_forward_spec=walk_forward_spec,
        )

    segment_summaries: Dict[str, Dict[str, object]] = {}
    for segment in tested_segments:
        tested_segment = str(segment["tested_segment"])
        segment_summaries[tested_segment] = _segment_summary(
            segment_info=segment,
            segment_tickers=segment_ticker_map[tested_segment],
            ticker_results=ticker_results,
            min_trades_threshold=_safe_int(candidate_config.get("min_trades_threshold"), 5),
        )

    primary_summary = next(
        segment_summaries[str(segment["tested_segment"])]
        for segment in tested_segments
        if str(segment["segment_role"]) == "primary"
    )
    supporting_summaries = [
        segment_summaries[str(segment["tested_segment"])]
        for segment in tested_segments
        if str(segment["segment_role"]) == "supporting"
    ]

    go_no_go = _determine_go_no_go(
        candidate_id=str(candidate_config["candidate_id"]),
        primary_summary=primary_summary,
        supporting_summaries=supporting_summaries,
    )
    results_df = _build_results_frame(
        candidate_config=candidate_config,
        walk_forward_spec=walk_forward_spec,
        tested_segments=tested_segments,
        segment_ticker_map=segment_ticker_map,
        ticker_results=ticker_results,
        segment_summaries=segment_summaries,
    )
    summary_payload = _build_summary_payload(
        roadmap_constraints=roadmap_constraints,
        governance=governance,
        v8_go_no_go=v8_go_no_go,
        candidate_config=candidate_config,
        walk_forward_spec=walk_forward_spec,
        tested_segments=tested_segments,
        segment_ticker_map=segment_ticker_map,
        segment_summaries=segment_summaries,
        go_no_go=go_no_go,
    )
    report_lines = _build_report_text(
        candidate_config=candidate_config,
        walk_forward_spec=walk_forward_spec,
        primary_summary=primary_summary,
        supporting_summaries=supporting_summaries,
        go_no_go=go_no_go,
    )

    results_path = output_dir / RESULT_OUTPUT
    summary_path = output_dir / SUMMARY_OUTPUT
    report_path = output_dir / REPORT_OUTPUT
    go_no_go_path = output_dir / GO_NO_GO_OUTPUT

    results_df.to_csv(results_path, index=False)
    _write_json(summary_path, summary_payload)
    _write_text(report_path, report_lines)
    _write_json(go_no_go_path, go_no_go)

    return {
        "results_df": results_df,
        "summary_payload": summary_payload,
        "go_no_go": go_no_go,
        "artifacts": {
            "results_csv": str(results_path),
            "summary_json": str(summary_path),
            "report_txt": str(report_path),
            "go_no_go_json": str(go_no_go_path),
        },
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run anchored walk-forward OOS validation for the v8-promoted segment-only candidate."
    )
    parser.add_argument("--data-dir", default="data", help="Price CSV directory. Default: data")
    parser.add_argument("--output-dir", default="output", help="Artifact directory. Default: output")
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional metadata CSV. Default: data/ticker_metadata.csv",
    )
    parser.add_argument(
        "--baseline-config",
        default="config/phase_a_baseline.json",
        help="Phase A baseline config. Default: config/phase_a_baseline.json",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run_baseline_v9_segment_oos_validation(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        )
    except BaselineV9SegmentOosCliError as exc:
        print(f"Segment OOS validation failed: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during segment OOS validation: {exc}")
        return 1

    go_no_go = result["go_no_go"]
    print("Baseline v9 segment OOS validation complete.")
    print(f"candidate_id={go_no_go['candidate_id']}")
    print(f"primary_segment={go_no_go['primary_segment']}")
    print(f"decision={go_no_go['decision']}")
    print(f"recommended_next_action={go_no_go['recommended_next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
