"""Diagnose core baseline weaknesses and propose simple baseline v2 candidates."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.evaluate_phase_a_real_data import load_price_csv  # noqa: E402
from quant.phase_a import (  # noqa: E402
    add_trend_features,
    add_volume_features,
    backtest_signal_frame,
)
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.phase_a_transition_utils import dedupe, read_json_object  # noqa: E402


CANDIDATE_RESULTS_COLUMNS = [
    "candidate_id",
    "entry_rule",
    "hold_period",
    "min_trades_threshold",
    "profit_buffer_pct",
    "ticker",
    "applied_threshold",
    "applied_strict_mode",
    "signal_count",
    "total_trades",
    "win_rate",
    "buffered_win_rate",
    "average_return",
    "max_drawdown",
    "eligible_for_analysis",
    "score_quality_reward",
    "score_trade_support_reward",
    "score_drawdown_penalty",
    "score_low_trade_penalty",
    "score",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
]

DECISION_VALUES = {
    "no_revision_helpful",
    "keep_experimental",
    "baseline_v2_candidate_ready",
    "baseline_v2_ready_for_phase_b_retry",
}


class BaselineRevisionCliError(ValueError):
    """Friendly CLI error for baseline revision diagnostics."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


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
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize_for_json(payload), indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_price_files(data_dir: Path) -> List[Path]:
    candidates = sorted(Path(data_dir).glob("*.csv"))
    valid_paths: List[Path] = []
    required = {"date", "open", "high", "low", "close", "volume"}
    for path in candidates:
        try:
            preview = pd.read_csv(path, nrows=2)
        except Exception:
            continue
        if required.issubset({str(column) for column in preview.columns}):
            valid_paths.append(path)
    return valid_paths


def _load_context_artifacts(output_dir: Path) -> Dict[str, object]:
    mapping = {
        "phase_b_postmortem": "phase_b_postmortem.json",
        "phase_b_redesign_decision": "phase_b_v2_redesign_decision.json",
        "baseline_redesign_go_no_go": "baseline_redesign_go_no_go.json",
        "baseline_redesign_global_summary": "baseline_redesign_global_summary.json",
    }
    context: Dict[str, object] = {"warnings": []}
    warnings: List[str] = []
    for key, filename in mapping.items():
        payload, item_warnings = read_json_object(Path(output_dir) / filename, filename)
        context[key] = payload
        warnings.extend(item_warnings)
    context["warnings"] = dedupe(warnings)
    return context


def _buffered_win_rate(trades_df: pd.DataFrame, profit_buffer_pct: float) -> float:
    if trades_df.empty:
        return 0.0
    return round(float(trades_df["return_pct"].gt(float(profit_buffer_pct)).mean() * 100.0), 4)


def _compute_score_components(
    total_trades: int,
    buffered_win_rate: float,
    average_return: float,
    max_drawdown: float,
    min_trades_threshold: int,
) -> Dict[str, float]:
    quality_reward = (float(buffered_win_rate) * 0.25) + (float(average_return) * 2.50)
    trade_support_reward = min(int(total_trades), int(min_trades_threshold)) * 3.50
    drawdown_penalty = max(0.0, float(max_drawdown)) * 0.45
    low_trade_penalty = 0.0
    if int(total_trades) < int(min_trades_threshold):
        low_trade_penalty = 14.0 + ((int(min_trades_threshold) - int(total_trades)) * 4.0)

    score = quality_reward + trade_support_reward - drawdown_penalty - low_trade_penalty
    return {
        "score_quality_reward": round(quality_reward, 4),
        "score_trade_support_reward": round(trade_support_reward, 4),
        "score_drawdown_penalty": round(drawdown_penalty, 4),
        "score_low_trade_penalty": round(low_trade_penalty, 4),
        "score": round(score, 4),
    }


def _build_feature_frame(frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    return add_trend_features(add_volume_features(frame, volume_spike_threshold=float(threshold)))


def _apply_candidate_signal(
    feature_frame: pd.DataFrame,
    candidate_id: str,
    threshold: float,
) -> Tuple[pd.DataFrame, str]:
    working = feature_frame.copy()

    if candidate_id in {"current_entry_hold3", "current_entry_hold3_with_min_return_buffer"}:
        signal_column = f"signal_{candidate_id}"
        working[signal_column] = (
            working["close"].gt(working["ema50"]) & working["volume_ratio"].ge(float(threshold))
        ).fillna(False)
        return working, signal_column

    if candidate_id == "baseline_v2_hold3_with_simplified_entry":
        signal_column = "signal_simplified_entry"
        working[signal_column] = working["close"].gt(working["ema50"]).fillna(False)
        return working, signal_column

    if candidate_id == "baseline_v2_hold3_with_trend_guard":
        signal_column = "signal_trend_guard"
        working[signal_column] = (
            working["close"].gt(working["ema50"]) & working["close"].gt(working["open"])
        ).fillna(False)
        return working, signal_column

    raise BaselineRevisionCliError(f"Unsupported baseline v2 candidate: {candidate_id}")


def _candidate_specs(min_trades_threshold: int) -> List[Dict[str, object]]:
    return [
        {
            "candidate_id": "baseline_v2_hold3",
            "internal_candidate_id": "current_entry_hold3",
            "entry_rule": "close_gt_ema50_and_volume_spike_threshold",
            "hold_period": 3,
            "min_trades_threshold": int(min_trades_threshold),
            "profit_buffer_pct": 0.0,
        },
        {
            "candidate_id": "baseline_v2_hold3_with_min_return_buffer",
            "internal_candidate_id": "current_entry_hold3_with_min_return_buffer",
            "entry_rule": "close_gt_ema50_and_volume_spike_threshold",
            "hold_period": 3,
            "min_trades_threshold": int(min_trades_threshold),
            "profit_buffer_pct": 0.25,
        },
        {
            "candidate_id": "baseline_v2_hold3_with_simplified_entry",
            "internal_candidate_id": "baseline_v2_hold3_with_simplified_entry",
            "entry_rule": "close_gt_ema50",
            "hold_period": 3,
            "min_trades_threshold": int(min_trades_threshold),
            "profit_buffer_pct": 0.0,
        },
        {
            "candidate_id": "baseline_v2_hold3_with_trend_guard",
            "internal_candidate_id": "baseline_v2_hold3_with_trend_guard",
            "entry_rule": "close_gt_ema50_and_bullish_candle",
            "hold_period": 3,
            "min_trades_threshold": int(min_trades_threshold),
            "profit_buffer_pct": 0.0,
        },
    ]


def evaluate_candidates_for_ticker(
    path: Path,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    min_trades_threshold: int,
) -> List[Dict[str, object]]:
    ticker = path.stem.upper()
    frame, _ = load_price_csv(path)
    runtime = resolve_phase_a_runtime_settings(
        ticker=ticker,
        baseline_config=baseline_payload,
        metadata_lookup=metadata_lookup,
    )
    metadata_row = dict(runtime.get("metadata_row") or {})
    feature_frame = _build_feature_frame(frame, threshold=float(runtime["threshold"]))

    rows: List[Dict[str, object]] = []
    for spec in _candidate_specs(min_trades_threshold=min_trades_threshold):
        candidate_frame, signal_column = _apply_candidate_signal(
            feature_frame=feature_frame,
            candidate_id=str(spec["internal_candidate_id"]),
            threshold=float(runtime["threshold"]),
        )
        signal_count = int(candidate_frame[signal_column].fillna(False).astype(bool).sum())
        result = backtest_signal_frame(
            candidate_frame,
            signal_column=signal_column,
            hold_period=int(spec["hold_period"]),
            allow_overlap=False,
        )
        buffered_win_rate = _buffered_win_rate(
            result.trades,
            profit_buffer_pct=float(spec["profit_buffer_pct"]),
        )
        score_components = _compute_score_components(
            total_trades=int(result.total_trades),
            buffered_win_rate=float(buffered_win_rate),
            average_return=float(result.average_return),
            max_drawdown=float(result.max_drawdown),
            min_trades_threshold=int(spec["min_trades_threshold"]),
        )
        row = {
            "candidate_id": str(spec["candidate_id"]),
            "entry_rule": str(spec["entry_rule"]),
            "hold_period": int(spec["hold_period"]),
            "min_trades_threshold": int(spec["min_trades_threshold"]),
            "profit_buffer_pct": float(spec["profit_buffer_pct"]),
            "ticker": ticker,
            "applied_threshold": float(runtime["threshold"]),
            "applied_strict_mode": bool(runtime["strict_mode"]),
            "signal_count": signal_count,
            "total_trades": int(result.total_trades),
            "win_rate": float(result.win_rate),
            "buffered_win_rate": float(buffered_win_rate),
            "average_return": float(result.average_return),
            "max_drawdown": float(result.max_drawdown),
            "eligible_for_analysis": bool(int(result.total_trades) >= int(spec["min_trades_threshold"])),
            "category": metadata_row.get("category"),
            "market_cap_group": metadata_row.get("market_cap_group"),
            "sector": metadata_row.get("sector"),
            "beta_group": metadata_row.get("beta_group"),
        }
        row.update(score_components)
        rows.append(row)
    return rows


def build_candidate_results(rows: Sequence[Dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=CANDIDATE_RESULTS_COLUMNS)
    results_df = pd.DataFrame(rows)
    results_df = results_df.reindex(columns=CANDIDATE_RESULTS_COLUMNS)
    return results_df.sort_values(
        ["candidate_id", "eligible_for_analysis", "score", "total_trades", "buffered_win_rate", "ticker"],
        ascending=[True, False, False, False, False, True],
    ).reset_index(drop=True)


def summarize_candidates(results_df: pd.DataFrame) -> pd.DataFrame:
    if results_df.empty:
        return pd.DataFrame(
            columns=[
                "candidate_id",
                "entry_rule",
                "hold_period",
                "min_trades_threshold",
                "profit_buffer_pct",
                "ticker_count",
                "eligible_ticker_count",
                "positive_score_ticker_count",
                "total_trades_sum",
                "signal_count_sum",
                "mean_score",
                "mean_win_rate",
                "mean_buffered_win_rate",
                "mean_average_return",
                "mean_max_drawdown",
                "global_selection_score",
            ]
        )

    grouped = (
        results_df.groupby(
            ["candidate_id", "entry_rule", "hold_period", "min_trades_threshold", "profit_buffer_pct"],
            dropna=False,
        )
        .agg(
            ticker_count=("ticker", "nunique"),
            eligible_ticker_count=("eligible_for_analysis", "sum"),
            positive_score_ticker_count=("score", lambda values: int((values > 0).sum())),
            total_trades_sum=("total_trades", "sum"),
            signal_count_sum=("signal_count", "sum"),
            mean_score=("score", "mean"),
            mean_win_rate=("win_rate", "mean"),
            mean_buffered_win_rate=("buffered_win_rate", "mean"),
            mean_average_return=("average_return", "mean"),
            mean_max_drawdown=("max_drawdown", "mean"),
        )
        .reset_index()
    )
    grouped["global_selection_score"] = (
        grouped["mean_score"]
        + (grouped["eligible_ticker_count"] * 6.0)
        + (grouped["positive_score_ticker_count"] * 3.0)
        + (grouped["total_trades_sum"] * 0.10)
    )
    return grouped.sort_values(
        ["global_selection_score", "eligible_ticker_count", "mean_score", "total_trades_sum"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)


def build_diagnostics_payload(
    baseline_payload: Dict[str, object],
    candidate_summaries: pd.DataFrame,
    results_df: pd.DataFrame,
    context_artifacts: Dict[str, object],
    generated_at: str,
) -> Dict[str, object]:
    current_candidate = (
        candidate_summaries.loc[candidate_summaries["candidate_id"] == "baseline_v2_hold3"].iloc[0].to_dict()
        if not candidate_summaries.empty and (candidate_summaries["candidate_id"] == "baseline_v2_hold3").any()
        else {}
    )
    simplified_candidate = (
        candidate_summaries.loc[
            candidate_summaries["candidate_id"] == "baseline_v2_hold3_with_simplified_entry"
        ].iloc[0].to_dict()
        if not candidate_summaries.empty
        and (candidate_summaries["candidate_id"] == "baseline_v2_hold3_with_simplified_entry").any()
        else {}
    )
    trend_guard_candidate = (
        candidate_summaries.loc[
            candidate_summaries["candidate_id"] == "baseline_v2_hold3_with_trend_guard"
        ].iloc[0].to_dict()
        if not candidate_summaries.empty
        and (candidate_summaries["candidate_id"] == "baseline_v2_hold3_with_trend_guard").any()
        else {}
    )
    buffer_candidate = (
        candidate_summaries.loc[
            candidate_summaries["candidate_id"] == "baseline_v2_hold3_with_min_return_buffer"
        ].iloc[0].to_dict()
        if not candidate_summaries.empty
        and (candidate_summaries["candidate_id"] == "baseline_v2_hold3_with_min_return_buffer").any()
        else {}
    )

    current_rows = results_df.loc[results_df["candidate_id"] == "baseline_v2_hold3"].copy()
    current_zero_trade_tickers = int(current_rows["total_trades"].le(0).sum()) if not current_rows.empty else 0
    current_weak_trade_tickers = int(current_rows["total_trades"].lt(5).sum()) if not current_rows.empty else 0

    raw_win_rate = _safe_float(current_candidate.get("mean_win_rate"))
    buffered_win_rate = _safe_float(buffer_candidate.get("mean_buffered_win_rate"))
    labeling_gap = raw_win_rate - buffered_win_rate

    entry_diagnosis = (
        "current_entry_too_tight"
        if _safe_float(simplified_candidate.get("total_trades_sum")) > _safe_float(current_candidate.get("total_trades_sum")) + 1.0
        and _safe_float(simplified_candidate.get("mean_average_return")) >= _safe_float(current_candidate.get("mean_average_return"))
        else "current_entry_not_clearly_better_than_simplified_alternatives"
    )
    exit_diagnosis = (
        "hold_period_3_is_preferred"
        if str(safe_dict(context_artifacts.get("baseline_redesign_go_no_go")).get("best_global_hold_period")) == "3"
        or _safe_int(safe_dict(context_artifacts.get("baseline_redesign_go_no_go")).get("best_global_hold_period")) == 3
        else "hold_period_unclear"
    )
    labeling_diagnosis = (
        "success_label_too_coarse"
        if labeling_gap >= 1.0
        else "success_label_not_main_blocker"
    )
    coverage_diagnosis = (
        "baseline_coverage_insufficient"
        if _safe_int(current_candidate.get("eligible_ticker_count")) < max(2, math.ceil(_safe_int(current_candidate.get("ticker_count"), 0) * 0.3))
        else "baseline_coverage_usable"
    )

    return {
        "generated_at": generated_at,
        "current_baseline_context": {
            "default_volume_spike_threshold": baseline_payload.get("default_volume_spike_threshold"),
            "strict_mode_default": baseline_payload.get("strict_mode_default"),
            "adaptive_threshold_enabled": baseline_payload.get("adaptive_threshold_enabled"),
            "min_trades_floor": baseline_payload.get("min_trades_floor"),
            "baseline_status": baseline_payload.get("baseline_status"),
        },
        "audit": {
            "entry_rule": {
                "current_rule": "close_gt_ema50_and_volume_spike_threshold",
                "overlap_with_volume_spike_ema50": "high",
                "current_total_trades_sum": _safe_float(current_candidate.get("total_trades_sum")),
                "simplified_entry_total_trades_sum": _safe_float(simplified_candidate.get("total_trades_sum")),
                "current_mean_average_return": _safe_float(current_candidate.get("mean_average_return")),
                "simplified_entry_mean_average_return": _safe_float(simplified_candidate.get("mean_average_return")),
                "diagnosis": entry_diagnosis,
            },
            "exit_hold_logic": {
                "current_hold_period": 5,
                "redesign_best_hold_period": safe_dict(context_artifacts.get("baseline_redesign_go_no_go")).get(
                    "best_global_hold_period"
                ),
                "diagnosis": exit_diagnosis,
            },
            "labeling_success_criteria": {
                "current_profit_buffer_pct": 0.0,
                "buffer_candidate_profit_buffer_pct": buffer_candidate.get("profit_buffer_pct"),
                "raw_win_rate_mean": raw_win_rate,
                "buffered_win_rate_mean": buffered_win_rate,
                "raw_vs_buffered_gap": round(labeling_gap, 6),
                "diagnosis": labeling_diagnosis,
            },
            "coverage_usability": {
                "current_zero_trade_ticker_count": current_zero_trade_tickers,
                "current_weak_trade_ticker_count": current_weak_trade_tickers,
                "current_eligible_ticker_count": _safe_int(current_candidate.get("eligible_ticker_count")),
                "trend_guard_eligible_ticker_count": _safe_int(trend_guard_candidate.get("eligible_ticker_count")),
                "simplified_entry_eligible_ticker_count": _safe_int(simplified_candidate.get("eligible_ticker_count")),
                "diagnosis": coverage_diagnosis,
            },
        },
        "recommended_revision_axes": dedupe(
            [
                "Kurangi ketergantungan entry pada volume spike sebagai syarat wajib."
                if entry_diagnosis == "current_entry_too_tight"
                else "",
                "Tetapkan hold period default 3 sebagai kandidat baseline v2 utama."
                if exit_diagnosis == "hold_period_3_is_preferred"
                else "",
                "Tambahkan label evaluasi berbasis buffered return untuk mengurangi noise win-rate mentah."
                if labeling_diagnosis == "success_label_too_coarse"
                else "",
                "Pilih entry yang lebih sederhana tetapi tetap menjaga trend sebagai syarat esensial."
                if coverage_diagnosis == "baseline_coverage_insufficient"
                else "",
            ]
        ),
        "context_artifacts_available": {
            "phase_b_postmortem": context_artifacts.get("phase_b_postmortem") is not None,
            "phase_b_redesign_decision": context_artifacts.get("phase_b_redesign_decision") is not None,
            "baseline_redesign_go_no_go": context_artifacts.get("baseline_redesign_go_no_go") is not None,
        },
        "warnings": list(context_artifacts.get("warnings") or []),
    }


def determine_go_no_go(
    candidate_summaries: pd.DataFrame,
) -> Tuple[Dict[str, object], Dict[str, object]]:
    if candidate_summaries.empty:
        selected = {}
        go_no_go = {
            "decision": "no_revision_helpful",
            "baseline_v2_candidate_selected": None,
            "baseline_revision_supported": False,
            "can_retry_phase_b_after_baseline_v2": False,
            "recommended_retry_target": "none",
            "next_action": "revise_baseline_further",
        }
        return selected, go_no_go

    current = (
        candidate_summaries.loc[candidate_summaries["candidate_id"] == "baseline_v2_hold3"].iloc[0].to_dict()
        if (candidate_summaries["candidate_id"] == "baseline_v2_hold3").any()
        else candidate_summaries.iloc[0].to_dict()
    )
    selected = candidate_summaries.iloc[0].to_dict()
    selected_id = str(selected.get("candidate_id"))
    baseline_revision_supported = (
        selected_id != "baseline_v2_hold3"
        and _safe_float(selected.get("global_selection_score")) > _safe_float(current.get("global_selection_score")) + 2.0
    ) or (
        selected_id == "baseline_v2_hold3"
        and _safe_float(selected.get("mean_score")) > 0
    )

    ticker_count = _safe_int(selected.get("ticker_count"))
    retry_gate = max(2, math.ceil(ticker_count * 0.3)) if ticker_count else 2
    can_retry = bool(
        _safe_int(selected.get("eligible_ticker_count")) >= retry_gate
        and _safe_int(selected.get("positive_score_ticker_count")) >= 2
        and _safe_float(selected.get("mean_score")) > 0
        and _safe_float(selected.get("mean_average_return")) >= 0
    )

    if not baseline_revision_supported:
        decision = "no_revision_helpful"
        recommended_retry_target = "none"
        next_action = "revise_baseline_further"
    elif can_retry:
        decision = "baseline_v2_ready_for_phase_b_retry"
        recommended_retry_target = "phase_b_retry_gate_reassessment"
        next_action = "validate_baseline_v2_and_prepare_phase_b_retry"
    elif _safe_int(selected.get("eligible_ticker_count")) >= 1 and _safe_float(selected.get("mean_average_return")) >= 0:
        decision = "baseline_v2_candidate_ready"
        recommended_retry_target = "none_yet_until_baseline_v2_validated"
        next_action = "validate_baseline_v2_candidate"
    else:
        decision = "keep_experimental"
        recommended_retry_target = "none"
        next_action = "revise_baseline_further"

    go_no_go = {
        "decision": decision,
        "baseline_v2_candidate_selected": selected_id,
        "baseline_revision_supported": bool(baseline_revision_supported),
        "can_retry_phase_b_after_baseline_v2": bool(can_retry),
        "recommended_retry_target": recommended_retry_target,
        "next_action": next_action,
        "decision_notes": dedupe(
            [
                "Candidate terpilih memperbaiki score global terhadap baseline redesign saat ini."
                if baseline_revision_supported
                else "Tidak ada kandidat baseline v2 yang cukup membantu dibanding baseline redesign saat ini.",
                "Coverage ticker eligible masih terlalu kecil untuk membuka retry Phase B."
                if not can_retry
                else "",
                "Candidate terpilih layak divalidasi dulu sebagai baseline v2 sebelum Phase B diulang."
                if decision == "baseline_v2_candidate_ready"
                else "",
            ]
        ),
    }
    return selected, go_no_go


def build_best_candidate_payload(
    selected_candidate: Dict[str, object],
    candidate_summaries: pd.DataFrame,
    generated_at: str,
) -> Dict[str, object]:
    return {
        "generated_at": generated_at,
        "selected_candidate": _sanitize_for_json(selected_candidate),
        "candidate_summaries": _sanitize_for_json(candidate_summaries.to_dict(orient="records")),
    }


def build_recommendations_text(
    diagnostics: Dict[str, object],
    selected_candidate: Dict[str, object],
    go_no_go: Dict[str, object],
) -> str:
    lines = [
        "Baseline v2 Recommendations",
        "===========================",
        "",
        f"- Decision: {go_no_go['decision']}",
        f"- Baseline v2 candidate selected: {go_no_go['baseline_v2_candidate_selected']}",
        f"- Baseline revision supported: {go_no_go['baseline_revision_supported']}",
        f"- Can retry Phase B after baseline v2: {go_no_go['can_retry_phase_b_after_baseline_v2']}",
        f"- Recommended retry target: {go_no_go['recommended_retry_target']}",
        f"- Next action: {go_no_go['next_action']}",
        "",
        "Selected candidate snapshot:",
        f"- candidate_id={selected_candidate.get('candidate_id')}",
        f"- entry_rule={selected_candidate.get('entry_rule')}",
        f"- hold_period={_safe_int(selected_candidate.get('hold_period'))}",
        f"- min_trades_threshold={_safe_int(selected_candidate.get('min_trades_threshold'))}",
        f"- eligible_ticker_count={_safe_int(selected_candidate.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_float(selected_candidate.get('total_trades_sum'))}",
        f"- mean_score={_safe_float(selected_candidate.get('mean_score')):+.4f}",
        f"- mean_average_return={_safe_float(selected_candidate.get('mean_average_return')):+.4f}",
        "",
        "Recommended revision axes:",
    ]
    for item in list(diagnostics.get("recommended_revision_axes") or []):
        lines.append(f"- {item}")
    if go_no_go.get("decision_notes"):
        lines.extend(["", "Decision notes:"])
        for item in list(go_no_go.get("decision_notes") or []):
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def update_transition_artifact(output_dir: Path, go_no_go: Dict[str, object]) -> Dict[str, object]:
    transition_path = Path(output_dir) / "phase_a_to_phase_b_transition.json"
    payload, warnings = read_json_object(transition_path, "Phase A to Phase B transition JSON")
    if payload is None:
        return {"updated": False, "path": str(transition_path), "warnings": warnings}

    payload["baseline_revision_status"] = go_no_go.get("decision")
    payload["baseline_revision_next_action"] = go_no_go.get("next_action")
    payload["phase_b_retry_readiness_after_baseline_v2"] = (
        "ready_for_retry_gate" if bool(go_no_go.get("can_retry_phase_b_after_baseline_v2")) else "not_ready_yet"
    )
    transition_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    report_path = Path(output_dir) / "phase_a_to_phase_b_transition_report.txt"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    appendix = [
        "",
        "Baseline Revision Update:",
        f"- baseline_revision_status: {go_no_go.get('decision')}",
        f"- baseline_revision_next_action: {go_no_go.get('next_action')}",
        f"- phase_b_retry_readiness_after_baseline_v2: {'ready_for_retry_gate' if bool(go_no_go.get('can_retry_phase_b_after_baseline_v2')) else 'not_ready_yet'}",
    ]
    report_path.write_text(report_text.rstrip() + "\n" + "\n".join(appendix) + "\n", encoding="utf-8")
    return {"updated": True, "path": str(transition_path), "report_path": str(report_path), "warnings": warnings}


def run_baseline_revision_diagnostics(
    data_dir: Path,
    output_dir: Path,
    baseline_config: Optional[Path],
    metadata_file: Optional[Path],
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = _now_iso()

    baseline_payload, baseline_warnings, _ = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    context_artifacts = _load_context_artifacts(output_dir)
    price_files = _resolve_price_files(data_dir)
    if not price_files:
        raise BaselineRevisionCliError(f"No usable price CSV files found in {data_dir}.")

    min_trades_threshold = int(
        safe_dict(context_artifacts.get("phase_b_redesign_decision")).get("supporting_signals", {}).get(
            "recommended_realistic_min_trades",
            5,
        )
        if isinstance(safe_dict(context_artifacts.get("phase_b_redesign_decision")).get("supporting_signals"), dict)
        else 5
    )
    if min_trades_threshold < 1:
        min_trades_threshold = 5

    rows: List[Dict[str, object]] = []
    for path in price_files:
        rows.extend(
            evaluate_candidates_for_ticker(
                path=path,
                baseline_payload=baseline_payload,
                metadata_lookup=metadata_lookup,
                min_trades_threshold=min_trades_threshold,
            )
        )

    results_df = build_candidate_results(rows)
    candidate_summaries = summarize_candidates(results_df)
    diagnostics = build_diagnostics_payload(
        baseline_payload=baseline_payload,
        candidate_summaries=candidate_summaries,
        results_df=results_df,
        context_artifacts=context_artifacts,
        generated_at=generated_at,
    )
    diagnostics["warnings"] = dedupe(
        [*list(diagnostics.get("warnings") or []), *baseline_warnings, *metadata_warnings]
    )

    selected_candidate, go_no_go = determine_go_no_go(candidate_summaries)
    best_candidate_payload = build_best_candidate_payload(
        selected_candidate=selected_candidate,
        candidate_summaries=candidate_summaries,
        generated_at=generated_at,
    )
    recommendations_text = build_recommendations_text(
        diagnostics=diagnostics,
        selected_candidate=selected_candidate,
        go_no_go=go_no_go,
    )

    diagnostics_path = output_dir / "baseline_revision_diagnostics.json"
    diagnostics_txt_path = output_dir / "baseline_revision_diagnostics.txt"
    candidate_results_path = output_dir / "baseline_v2_candidate_results.csv"
    best_candidate_path = output_dir / "baseline_v2_best_candidate.json"
    recommendations_path = output_dir / "baseline_v2_recommendations.txt"
    go_no_go_path = output_dir / "baseline_v2_go_no_go.json"

    _write_json(diagnostics_path, diagnostics)
    _write_text(
        diagnostics_txt_path,
        [
            "Baseline Revision Diagnostics",
            "=============================",
            "",
            f"- Generated at: {generated_at}",
            f"- Entry diagnosis: {diagnostics['audit']['entry_rule']['diagnosis']}",
            f"- Exit diagnosis: {diagnostics['audit']['exit_hold_logic']['diagnosis']}",
            f"- Labeling diagnosis: {diagnostics['audit']['labeling_success_criteria']['diagnosis']}",
            f"- Coverage diagnosis: {diagnostics['audit']['coverage_usability']['diagnosis']}",
            "",
            "Recommended revision axes:",
            *[f"- {item}" for item in list(diagnostics.get("recommended_revision_axes") or [])],
        ],
    )
    results_df.to_csv(candidate_results_path, index=False)
    _write_json(best_candidate_path, best_candidate_payload)
    _write_text(recommendations_path, recommendations_text.splitlines())
    _write_json(go_no_go_path, go_no_go)

    transition_update = update_transition_artifact(output_dir=output_dir, go_no_go=go_no_go)

    return {
        "diagnostics": diagnostics,
        "candidate_results_df": results_df,
        "candidate_summaries_df": candidate_summaries,
        "best_candidate_payload": best_candidate_payload,
        "go_no_go": go_no_go,
        "transition_update": transition_update,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose baseline core weaknesses and propose simple baseline v2 candidates."
    )
    parser.add_argument("--data-dir", default="data", help="Directory containing per-ticker OHLCV CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory for baseline revision artifacts.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Path to current baseline config JSON.",
    )
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional metadata CSV path.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = run_baseline_revision_diagnostics(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    print(f"Decision: {result['go_no_go']['decision']}")
    print(f"Selected candidate: {result['go_no_go']['baseline_v2_candidate_selected']}")
    return 0


def safe_dict(value: object) -> Dict[str, object]:
    return value if isinstance(value, dict) else {}


if __name__ == "__main__":
    raise SystemExit(main())
