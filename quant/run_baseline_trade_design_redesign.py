"""Run a baseline-only trade-design redesign experiment."""

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
from quant.phase_a import backtest_signal_frame, generate_phase_a_signal  # noqa: E402
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.phase_a_transition_utils import dedupe, read_json_object  # noqa: E402


RESULT_COLUMNS = [
    "ticker",
    "config_id",
    "hold_period",
    "min_trades_threshold",
    "profit_buffer_pct",
    "applied_threshold",
    "applied_strict_mode",
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

BEST_CONFIG_COLUMNS = [
    "ticker",
    "config_id",
    "best_hold_period",
    "best_min_trades_threshold",
    "profit_buffer_pct",
    "decision_confidence",
    "decision_margin",
    "eligible_for_analysis",
    "total_trades",
    "win_rate",
    "buffered_win_rate",
    "average_return",
    "max_drawdown",
    "score",
    "selection_reason",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
]

GO_NO_GO_DECISIONS = {
    "no_improvement",
    "improved_but_keep_experimental",
    "usable_for_framework_redesign_only",
}

ENTRY_RULE_BY_CANDIDATE_ID = {
    "baseline_v2_hold3": "close_gt_ema50_and_volume_spike_threshold",
    "baseline_v2_hold3_with_min_return_buffer": "close_gt_ema50_and_volume_spike_threshold",
    "baseline_v2_hold3_with_simplified_entry": "close_gt_ema50",
    "baseline_v2_hold3_with_trend_guard": "close_gt_ema50_and_bullish_candle",
}


class BaselineRedesignCliError(ValueError):
    """Friendly CLI error for baseline redesign experiment."""


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


def _resolve_price_files(data_dir: Path) -> List[Path]:
    candidates = sorted(Path(data_dir).glob("*.csv"))
    valid_files: List[Path] = []
    for path in candidates:
        try:
            frame = pd.read_csv(path, nrows=2)
        except Exception:
            continue
        required = {"date", "open", "high", "low", "close", "volume"}
        if required.issubset({str(column) for column in frame.columns}):
            valid_files.append(path)
    return valid_files


def _buffered_win_rate(trades_df: pd.DataFrame, profit_buffer_pct: float) -> float:
    if trades_df.empty:
        return 0.0
    threshold = float(profit_buffer_pct)
    return round(float(trades_df["return_pct"].gt(threshold).mean() * 100.0), 4)


def _compute_score_components(
    total_trades: int,
    buffered_win_rate: float,
    average_return: float,
    max_drawdown: float,
    min_trades_threshold: int,
) -> Dict[str, float]:
    quality_reward = (buffered_win_rate * 0.30) + (average_return * 2.50)
    trade_support_reward = min(int(total_trades), int(min_trades_threshold)) * 4.00
    drawdown_penalty = max(0.0, float(max_drawdown)) * 0.50
    low_trade_penalty = 0.0
    if int(total_trades) < int(min_trades_threshold):
        low_trade_penalty = 18.0 + ((int(min_trades_threshold) - int(total_trades)) * 4.0)

    score = quality_reward + trade_support_reward - drawdown_penalty - low_trade_penalty
    return {
        "score_quality_reward": round(quality_reward, 4),
        "score_trade_support_reward": round(trade_support_reward, 4),
        "score_drawdown_penalty": round(drawdown_penalty, 4),
        "score_low_trade_penalty": round(low_trade_penalty, 4),
        "score": round(score, 4),
    }


def run_redesign_evaluations_for_ticker(
    path: Path,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    hold_period_options: Sequence[int],
    min_trades_options: Sequence[int],
    profit_buffer_pct: float,
    allow_overlap: bool,
) -> List[Dict[str, object]]:
    ticker = path.stem.upper()
    frame, _ = load_price_csv(path)
    runtime = resolve_phase_a_runtime_settings(
        ticker=ticker,
        baseline_config=baseline_payload,
        metadata_lookup=metadata_lookup,
    )
    metadata_row = dict(runtime.get("metadata_row") or {})

    signal_frame = generate_phase_a_signal(
        frame,
        strict=bool(runtime["strict_mode"]),
        volume_spike_threshold=float(runtime["threshold"]),
    )
    signal_column = "phase_a_signal_strict" if bool(runtime["strict_mode"]) else "phase_a_signal"

    rows: List[Dict[str, object]] = []
    for hold_period in hold_period_options:
        result = backtest_signal_frame(
            signal_frame,
            signal_column=signal_column,
            hold_period=int(hold_period),
            allow_overlap=allow_overlap,
        )
        buffered_win_rate = _buffered_win_rate(result.trades, profit_buffer_pct=profit_buffer_pct)
        for min_trades_threshold in min_trades_options:
            score_breakdown = _compute_score_components(
                total_trades=int(result.total_trades),
                buffered_win_rate=float(buffered_win_rate),
                average_return=float(result.average_return),
                max_drawdown=float(result.max_drawdown),
                min_trades_threshold=int(min_trades_threshold),
            )
            row = {
                "ticker": ticker,
                "config_id": f"hold_{int(hold_period)}_mintrades_{int(min_trades_threshold)}",
                "hold_period": int(hold_period),
                "min_trades_threshold": int(min_trades_threshold),
                "profit_buffer_pct": float(profit_buffer_pct),
                "applied_threshold": float(runtime["threshold"]),
                "applied_strict_mode": bool(runtime["strict_mode"]),
                "total_trades": int(result.total_trades),
                "win_rate": float(result.win_rate),
                "buffered_win_rate": float(buffered_win_rate),
                "average_return": float(result.average_return),
                "max_drawdown": float(result.max_drawdown),
                "eligible_for_analysis": bool(int(result.total_trades) >= int(min_trades_threshold)),
                "category": metadata_row.get("category"),
                "market_cap_group": metadata_row.get("market_cap_group"),
                "sector": metadata_row.get("sector"),
                "beta_group": metadata_row.get("beta_group"),
            }
            row.update(score_breakdown)
            rows.append(row)
    return rows


def build_results_dataframe(rows: Sequence[Dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    results_df = pd.DataFrame(rows)
    results_df = results_df.reindex(columns=RESULT_COLUMNS)
    return results_df.sort_values(
        ["ticker", "eligible_for_analysis", "score", "total_trades", "buffered_win_rate", "average_return", "hold_period"],
        ascending=[True, False, False, False, False, False, True],
    ).reset_index(drop=True)


def _selection_reason(winner: pd.Series, confidence: str) -> str:
    return (
        f"Config {winner['config_id']} dipilih karena score redesign baseline tertinggi "
        f"dengan hold_period={int(winner['hold_period'])}, min_trades={int(winner['min_trades_threshold'])}, "
        f"total_trades={int(winner['total_trades'])}, buffered_win_rate={_safe_float(winner['buffered_win_rate']):+.2f}, "
        f"average_return={_safe_float(winner['average_return']):+.4f}, max_drawdown={_safe_float(winner['max_drawdown']):+.4f}. "
        f"confidence={confidence}."
    )


def select_best_config_per_ticker(results_df: pd.DataFrame) -> pd.DataFrame:
    if results_df.empty:
        return pd.DataFrame(columns=BEST_CONFIG_COLUMNS)

    rows: List[Dict[str, object]] = []
    for ticker, group_df in results_df.groupby("ticker", sort=True):
        ranked = group_df.sort_values(
            [
                "eligible_for_analysis",
                "score",
                "total_trades",
                "buffered_win_rate",
                "average_return",
                "hold_period",
                "min_trades_threshold",
            ],
            ascending=[False, False, False, False, False, True, True],
        ).reset_index(drop=True)
        winner = ranked.iloc[0]
        runner_up = ranked.iloc[1] if len(ranked) > 1 else None
        decision_margin = float(winner["score"] - runner_up["score"]) if runner_up is not None else None

        if not bool(winner["eligible_for_analysis"]) or _safe_int(winner["total_trades"]) <= 0:
            confidence = "low"
        elif decision_margin is None or decision_margin < 1.0:
            confidence = "low"
        elif decision_margin < 3.0:
            confidence = "moderate"
        else:
            confidence = "strong"

        rows.append(
            {
                "ticker": ticker,
                "config_id": str(winner["config_id"]),
                "best_hold_period": int(winner["hold_period"]),
                "best_min_trades_threshold": int(winner["min_trades_threshold"]),
                "profit_buffer_pct": float(winner["profit_buffer_pct"]),
                "decision_confidence": confidence,
                "decision_margin": decision_margin,
                "eligible_for_analysis": bool(winner["eligible_for_analysis"]),
                "total_trades": int(winner["total_trades"]),
                "win_rate": float(winner["win_rate"]),
                "buffered_win_rate": float(winner["buffered_win_rate"]),
                "average_return": float(winner["average_return"]),
                "max_drawdown": float(winner["max_drawdown"]),
                "score": float(winner["score"]),
                "selection_reason": _selection_reason(winner=winner, confidence=confidence),
                "category": winner.get("category"),
                "market_cap_group": winner.get("market_cap_group"),
                "sector": winner.get("sector"),
                "beta_group": winner.get("beta_group"),
            }
        )

    best_df = pd.DataFrame(rows)
    return best_df.reindex(columns=BEST_CONFIG_COLUMNS).sort_values(
        ["eligible_for_analysis", "decision_confidence", "score", "ticker"],
        ascending=[False, True, False, True],
        key=lambda series: (
            series.map({"strong": 0, "moderate": 1, "low": 2})
            if series.name == "decision_confidence"
            else series
        ),
    ).reset_index(drop=True)


def build_global_summary(
    results_df: pd.DataFrame,
    baseline_floor: int,
) -> Dict[str, object]:
    if results_df.empty:
        return {
            "generated_at": _now_iso(),
            "config_summaries": [],
            "current_config": None,
            "best_global_config": None,
        }

    grouped = (
        results_df.groupby(["hold_period", "min_trades_threshold", "profit_buffer_pct"], dropna=False)
        .agg(
            ticker_count=("ticker", "nunique"),
            eligible_ticker_count=("eligible_for_analysis", "sum"),
            positive_score_ticker_count=("score", lambda values: int((values > 0).sum())),
            total_trades_sum=("total_trades", "sum"),
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
        + (grouped["eligible_ticker_count"] * 5.0)
        + (grouped["total_trades_sum"] * 0.10)
    )
    grouped = grouped.sort_values(
        ["global_selection_score", "eligible_ticker_count", "mean_score", "total_trades_sum", "hold_period"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)

    current_mask = (
        grouped["hold_period"].eq(5)
        & grouped["min_trades_threshold"].eq(int(baseline_floor))
    )
    current_row = grouped.loc[current_mask].iloc[0].to_dict() if current_mask.any() else grouped.iloc[0].to_dict()
    current_total_trades_sum = max(1.0, _safe_float(current_row.get("total_trades_sum"), 1.0))
    eligible_ticker_floor = max(3, math.ceil(_safe_int(grouped["ticker_count"].max()) * 0.4)) if not grouped.empty else 3
    grouped["trade_label"] = grouped["hold_period"].map(lambda value: f"t_plus_{_safe_int(value)}")
    grouped["trade_retention_vs_current_pct"] = grouped["total_trades_sum"].map(
        lambda value: round((_safe_float(value) / current_total_trades_sum) * 100.0, 4)
    )
    grouped["eligible_ticker_floor"] = eligible_ticker_floor
    grouped["trade_retention_floor_pct"] = 85.0
    grouped["meets_eligible_ticker_floor"] = grouped["eligible_ticker_count"].ge(eligible_ticker_floor)
    grouped["meets_trade_retention_floor"] = grouped["trade_retention_vs_current_pct"].ge(85.0)
    grouped["usable_for_framework_redesign"] = (
        grouped["meets_eligible_ticker_floor"] & grouped["meets_trade_retention_floor"]
    )
    best_row = grouped.iloc[0].to_dict()

    return {
        "generated_at": _now_iso(),
        "config_summaries": [_sanitize_for_json(row) for row in grouped.to_dict(orient="records")],
        "current_config": _sanitize_for_json(current_row),
        "best_global_config": _sanitize_for_json(best_row),
    }


def determine_baseline_redesign_go_no_go(
    global_summary: Dict[str, object],
) -> Dict[str, object]:
    best = dict(global_summary.get("best_global_config") or {})
    current = dict(global_summary.get("current_config") or {})
    if not best or not current:
        return {
            "decision": "no_improvement",
            "best_global_hold_period": None,
            "best_global_min_trades": None,
            "baseline_trade_design_improved": False,
            "can_retry_phase_b_after_this": False,
            "recommended_next_experiment": "no_retry_yet_until_baseline_revised",
            "next_action": "revise_baseline_further",
            "decision_notes": ["Global summary belum cukup untuk keputusan redesign baseline."],
        }

    improved = (
        _safe_float(best.get("global_selection_score")) > _safe_float(current.get("global_selection_score")) + 0.5
        or _safe_int(best.get("eligible_ticker_count")) > _safe_int(current.get("eligible_ticker_count"))
        or _safe_float(best.get("total_trades_sum")) > _safe_float(current.get("total_trades_sum")) + 1.0
    )

    ticker_count = _safe_int(best.get("ticker_count"), 0)
    eligible_ticker_floor = _safe_int(best.get("eligible_ticker_floor"), max(3, math.ceil(ticker_count * 0.4)) if ticker_count else 3)
    eligible_ticker_count = _safe_int(best.get("eligible_ticker_count"))
    positive_score_ticker_count = _safe_int(best.get("positive_score_ticker_count"))
    mean_score = _safe_float(best.get("mean_score"))
    trade_retention_vs_current_pct = _safe_float(best.get("trade_retention_vs_current_pct"))
    usable_for_framework_redesign = bool(best.get("usable_for_framework_redesign"))

    if not improved:
        decision = "no_improvement"
        recommended_next = "keep_data_extension_as_primary_track"
        next_action = "revise_baseline_further"
    elif usable_for_framework_redesign and mean_score > 0 and positive_score_ticker_count >= max(2, eligible_ticker_floor - 1):
        decision = "usable_for_framework_redesign_only"
        recommended_next = "refresh_framework_redesign_scope_after_data_extension"
        next_action = "hold_redesign_candidate_as_framework_input_only"
    else:
        decision = "improved_but_keep_experimental"
        recommended_next = "keep_data_extension_as_primary_track"
        next_action = "revise_baseline_further"

    return {
        "decision": decision,
        "best_global_hold_period": _safe_int(best.get("hold_period")),
        "best_global_min_trades": _safe_int(best.get("min_trades_threshold")),
        "best_trade_label": str(best.get("trade_label") or ""),
        "baseline_trade_design_improved": bool(improved),
        "can_retry_phase_b_after_this": False,
        "phase_b_retry_blocked_until_data_extension": True,
        "min_eligible_ticker_floor": eligible_ticker_floor,
        "trade_retention_vs_current_pct": trade_retention_vs_current_pct,
        "trade_retention_floor_pct": _safe_float(best.get("trade_retention_floor_pct"), 85.0),
        "usable_for_framework_redesign": usable_for_framework_redesign,
        "recommended_next_experiment": recommended_next,
        "next_action": next_action,
        "decision_notes": dedupe(
            [
                "Config terbaik global meningkatkan usability dibanding desain evaluasi baseline saat ini."
                if improved
                else "Tidak ada config redesign yang memperbaiki usability baseline secara berarti.",
                "Coverage ticker eligible masih terlalu kecil untuk dianggap usable."
                if eligible_ticker_count < eligible_ticker_floor
                else "",
                "Trade retention terhadap baseline evaluasi aktif masih terlalu tipis."
                if trade_retention_vs_current_pct < _safe_float(best.get("trade_retention_floor_pct"), 85.0)
                else "",
                "Score rata-rata config terbaik masih belum cukup kuat untuk dijadikan input redesign yang usable."
                if mean_score <= 0
                else "",
                "Hasil redesign ini hanya boleh dipakai sebagai input framework redesign; retry Phase B tetap diblokir sampai data extension selesai."
            ]
        ),
    }


def build_recommendations_text(
    global_summary: Dict[str, object],
    go_no_go: Dict[str, object],
) -> str:
    best = dict(global_summary.get("best_global_config") or {})
    current = dict(global_summary.get("current_config") or {})
    lines = [
        "Baseline Trade Design Redesign",
        "==============================",
        "",
        f"- Decision: {go_no_go['decision']}",
        f"- Baseline trade design improved: {go_no_go['baseline_trade_design_improved']}",
        f"- Can retry Phase B after this: {go_no_go['can_retry_phase_b_after_this']}",
        f"- Best global hold period: {go_no_go['best_global_hold_period']}",
        f"- Best global min trades: {go_no_go['best_global_min_trades']}",
        f"- Best trade label: {go_no_go.get('best_trade_label')}",
        f"- Min eligible ticker floor: {go_no_go.get('min_eligible_ticker_floor')}",
        f"- Trade retention vs current: {go_no_go.get('trade_retention_vs_current_pct')}",
        f"- Trade retention floor pct: {go_no_go.get('trade_retention_floor_pct')}",
        f"- Usable for framework redesign: {go_no_go.get('usable_for_framework_redesign')}",
        f"- Phase B retry blocked until data extension: {go_no_go.get('phase_b_retry_blocked_until_data_extension')}",
        f"- Recommended next experiment: {go_no_go['recommended_next_experiment']}",
        f"- Next action: {go_no_go['next_action']}",
        "",
        "Current baseline eval config:",
        f"- hold_period={_safe_int(current.get('hold_period'))}",
        f"- min_trades_threshold={_safe_int(current.get('min_trades_threshold'))}",
        f"- eligible_ticker_count={_safe_int(current.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_float(current.get('total_trades_sum'))}",
        f"- mean_score={_safe_float(current.get('mean_score')):+.4f}",
        "",
        "Best redesign config:",
        f"- hold_period={_safe_int(best.get('hold_period'))}",
        f"- min_trades_threshold={_safe_int(best.get('min_trades_threshold'))}",
        f"- eligible_ticker_count={_safe_int(best.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_float(best.get('total_trades_sum'))}",
        f"- mean_score={_safe_float(best.get('mean_score')):+.4f}",
    ]
    if go_no_go.get("decision_notes"):
        lines.extend(["", "Decision notes:"])
        for item in list(go_no_go.get("decision_notes") or []):
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _default_candidate_template() -> Dict[str, object]:
    return {
        "candidate_id": "baseline_v2_hold3_with_trend_guard",
        "entry_rule": "close_gt_ema50_and_bullish_candle",
        "profit_buffer_pct": 0.0,
    }


def _load_candidate_template(output_dir: Path) -> Dict[str, object]:
    candidate_path = Path(output_dir) / "baseline_v2_best_candidate.json"
    payload, _ = read_json_object(candidate_path, "Baseline v2 best candidate JSON")
    selected = dict(payload.get("selected_candidate") or {}) if isinstance(payload, dict) else {}
    template = {**_default_candidate_template(), **selected}

    candidate_id = str(template.get("candidate_id") or "").strip()
    if not str(template.get("entry_rule") or "").strip():
        template["entry_rule"] = ENTRY_RULE_BY_CANDIDATE_ID.get(candidate_id, "close_gt_ema50_and_bullish_candle")

    return template


def build_best_candidate_payload(
    output_dir: Path,
    global_summary: Dict[str, object],
    go_no_go: Dict[str, object],
) -> Dict[str, object]:
    best = dict(global_summary.get("best_global_config") or {})
    template = _load_candidate_template(output_dir)

    hold_period = _safe_int(best.get("hold_period"), _safe_int(template.get("hold_period"), 3))
    min_trades = _safe_int(best.get("min_trades_threshold"), 5)
    selection_score = _safe_float(best.get("global_selection_score"))
    why_selected = (
        f"Config redesign terbaik memakai hold_period={hold_period}, min_trades={min_trades}, "
        f"eligible_ticker_count={_safe_int(best.get('eligible_ticker_count'))}, total_trades_sum={_safe_int(best.get('total_trades_sum'))}, "
        f"mean_score={_safe_float(best.get('mean_score')):+.4f}, global_selection_score={selection_score:+.4f}."
    )
    weak_reason = None
    if str(go_no_go.get("decision")) in {"no_improvement", "improved_but_keep_experimental"}:
        weak_reason = " ".join(str(item) for item in list(go_no_go.get("decision_notes") or []) if str(item).strip()) or (
            "Coverage atau score kandidat redesign belum cukup kuat untuk promosi."
        )

    selected_candidate = {
        "candidate_id": str(template.get("candidate_id")),
        "entry_rule": str(template.get("entry_rule")),
        "hold_period": hold_period,
        "trade_label": str(best.get("trade_label") or f"t_plus_{hold_period}"),
        "min_trades_threshold": min_trades,
        "min_trades": min_trades,
        "profit_buffer_pct": _safe_float(best.get("profit_buffer_pct"), _safe_float(template.get("profit_buffer_pct"), 0.0)),
        "score": selection_score,
        "mean_score": _safe_float(best.get("mean_score")),
        "eligible_ticker_count": _safe_int(best.get("eligible_ticker_count")),
        "total_trades_sum": _safe_int(best.get("total_trades_sum")),
        "average_return": _safe_float(best.get("mean_average_return")),
        "win_rate": _safe_float(best.get("mean_win_rate")),
        "max_drawdown": _safe_float(best.get("mean_max_drawdown")),
        "why_selected": why_selected,
        "why_not_selected_if_weak": weak_reason,
    }

    return {
        "generated_at": _now_iso(),
        "candidate_id": selected_candidate["candidate_id"],
        "entry_rule": selected_candidate["entry_rule"],
        "hold_period": selected_candidate["hold_period"],
        "min_trades": selected_candidate["min_trades"],
        "score": selected_candidate["score"],
        "eligible_ticker_count": selected_candidate["eligible_ticker_count"],
        "average_return": selected_candidate["average_return"],
        "win_rate": selected_candidate["win_rate"],
        "max_drawdown": selected_candidate["max_drawdown"],
        "why_selected": selected_candidate["why_selected"],
        "why_not_selected_if_weak": selected_candidate["why_not_selected_if_weak"],
        "selected_candidate": _sanitize_for_json(selected_candidate),
        "redesign_summary": {
            "decision": go_no_go.get("decision"),
            "can_retry_phase_b_after_this": False,
            "phase_b_retry_blocked_until_data_extension": True,
            "usable_for_framework_redesign": bool(go_no_go.get("usable_for_framework_redesign")),
            "recommended_next_experiment": go_no_go.get("recommended_next_experiment"),
            "next_action": go_no_go.get("next_action"),
            "decision_notes": list(go_no_go.get("decision_notes") or []),
        },
    }


def build_baseline_v2_redesign_report(
    global_summary: Dict[str, object],
    go_no_go: Dict[str, object],
    best_candidate_payload: Dict[str, object],
) -> str:
    best = dict(global_summary.get("best_global_config") or {})
    candidate = dict(best_candidate_payload.get("selected_candidate") or {})
    lines = [
        "Baseline v2 Redesign Report",
        "===========================",
        "",
        f"- redesign_decision={go_no_go.get('decision')}",
        f"- can_retry_phase_b_after_this={go_no_go.get('can_retry_phase_b_after_this')}",
        f"- best_hold_period={_safe_int(best.get('hold_period'))}",
        f"- best_min_trades={_safe_int(best.get('min_trades_threshold'))}",
        f"- best_global_selection_score={_safe_float(best.get('global_selection_score')):+.4f}",
        "",
        "Selected candidate:",
        f"- candidate_id={candidate.get('candidate_id')}",
        f"- entry_rule={candidate.get('entry_rule')}",
        f"- hold_period={candidate.get('hold_period')}",
        f"- min_trades={candidate.get('min_trades')}",
        f"- score={_safe_float(candidate.get('score')):+.4f}",
        f"- eligible_ticker_count={_safe_int(candidate.get('eligible_ticker_count'))}",
        f"- average_return={_safe_float(candidate.get('average_return')):+.4f}",
        f"- win_rate={_safe_float(candidate.get('win_rate')):+.4f}",
        f"- max_drawdown={_safe_float(candidate.get('max_drawdown')):+.4f}",
        f"- why_selected={candidate.get('why_selected')}",
        f"- why_not_selected_if_weak={candidate.get('why_not_selected_if_weak') or 'none'}",
    ]

    if go_no_go.get("decision_notes"):
        lines.extend(["", "Decision notes:"])
        for item in list(go_no_go.get("decision_notes") or []):
            lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def update_transition_artifact(
    output_dir: Path,
    go_no_go: Dict[str, object],
) -> Dict[str, object]:
    transition_path = Path(output_dir) / "phase_a_to_phase_b_transition.json"
    payload, warnings = read_json_object(transition_path, "Phase A to Phase B transition JSON")
    if payload is None:
        return {"updated": False, "path": str(transition_path), "warnings": warnings}

    decision = str(go_no_go.get("decision"))
    can_retry = bool(go_no_go.get("can_retry_phase_b_after_this"))
    payload["baseline_redesign_status"] = decision
    payload["baseline_redesign_next_action"] = go_no_go.get("next_action")
    payload["phase_b_retry_readiness"] = "not_ready_yet"
    payload["baseline_redesign_trade_label"] = go_no_go.get("best_trade_label")
    transition_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    report_path = Path(output_dir) / "phase_a_to_phase_b_transition_report.txt"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    appendix = [
        "",
        "Baseline Redesign Update:",
        f"- baseline_redesign_status: {decision}",
        f"- baseline_redesign_next_action: {go_no_go.get('next_action')}",
        f"- baseline_redesign_trade_label: {go_no_go.get('best_trade_label')}",
        "- phase_b_retry_readiness: not_ready_yet",
    ]
    report_path.write_text(report_text.rstrip() + "\n" + "\n".join(appendix) + "\n", encoding="utf-8")
    return {"updated": True, "path": str(transition_path), "report_path": str(report_path), "warnings": warnings}


def run_baseline_trade_design_redesign(
    data_dir: Path,
    output_dir: Path,
    baseline_config: Optional[Path],
    metadata_file: Optional[Path],
    hold_period_options: Sequence[int],
    min_trades_options: Sequence[int],
    profit_buffer_pct: float = 0.0,
    allow_overlap: bool = False,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_payload, baseline_warnings, baseline_path = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    price_files = _resolve_price_files(data_dir)
    if not price_files:
        raise BaselineRedesignCliError(f"No usable price CSV files found in {data_dir}.")

    rows: List[Dict[str, object]] = []
    for path in price_files:
        rows.extend(
            run_redesign_evaluations_for_ticker(
                path=path,
                baseline_payload=baseline_payload,
                metadata_lookup=metadata_lookup,
                hold_period_options=hold_period_options,
                min_trades_options=min_trades_options,
                profit_buffer_pct=profit_buffer_pct,
                allow_overlap=allow_overlap,
            )
        )

    results_df = build_results_dataframe(rows)
    best_df = select_best_config_per_ticker(results_df)
    global_summary = build_global_summary(
        results_df=results_df,
        baseline_floor=_safe_int(baseline_payload.get("min_trades_floor"), 8),
    )
    global_summary["generated_at"] = _now_iso()
    global_summary["baseline_config_path"] = str(baseline_path) if baseline_path else None
    global_summary["metadata_file"] = str(metadata_file) if metadata_file else None
    global_summary["profit_buffer_pct"] = float(profit_buffer_pct)
    global_summary["warnings"] = dedupe([*baseline_warnings, *metadata_warnings])
    go_no_go = determine_baseline_redesign_go_no_go(global_summary)
    recommendations_text = build_recommendations_text(global_summary, go_no_go)
    best_candidate_payload = build_best_candidate_payload(output_dir=output_dir, global_summary=global_summary, go_no_go=go_no_go)
    redesign_report_text = build_baseline_v2_redesign_report(
        global_summary=global_summary,
        go_no_go=go_no_go,
        best_candidate_payload=best_candidate_payload,
    )
    redesign_results_df = pd.DataFrame(list(global_summary.get("config_summaries") or []))

    results_path = output_dir / "baseline_redesign_results.csv"
    best_path = output_dir / "baseline_redesign_best_config_per_ticker.csv"
    summary_path = output_dir / "baseline_redesign_global_summary.json"
    recommendations_path = output_dir / "baseline_redesign_recommendations.txt"
    go_no_go_path = output_dir / "baseline_redesign_go_no_go.json"
    baseline_v2_results_path = output_dir / "baseline_v2_redesign_results.csv"
    baseline_v2_best_candidate_path = output_dir / "baseline_v2_best_candidate.json"
    baseline_v2_report_path = output_dir / "baseline_v2_redesign_report.txt"

    results_df.to_csv(results_path, index=False)
    best_df.to_csv(best_path, index=False)
    summary_path.write_text(json.dumps(_sanitize_for_json(global_summary), indent=2, ensure_ascii=True), encoding="utf-8")
    recommendations_path.write_text(recommendations_text, encoding="utf-8")
    go_no_go_path.write_text(json.dumps(_sanitize_for_json(go_no_go), indent=2, ensure_ascii=True), encoding="utf-8")
    redesign_results_df.to_csv(baseline_v2_results_path, index=False)
    baseline_v2_best_candidate_path.write_text(
        json.dumps(_sanitize_for_json(best_candidate_payload), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    baseline_v2_report_path.write_text(redesign_report_text, encoding="utf-8")

    transition_update = update_transition_artifact(output_dir=output_dir, go_no_go=go_no_go)

    return {
        "results_df": results_df,
        "best_df": best_df,
        "redesign_results_df": redesign_results_df,
        "global_summary": global_summary,
        "go_no_go": go_no_go,
        "best_candidate_payload": best_candidate_payload,
        "paths": {
            "results_csv": results_path,
            "best_config_csv": best_path,
            "global_summary_json": summary_path,
            "recommendations_txt": recommendations_path,
            "go_no_go_json": go_no_go_path,
            "baseline_v2_results_csv": baseline_v2_results_path,
            "baseline_v2_best_candidate_json": baseline_v2_best_candidate_path,
            "baseline_v2_report_txt": baseline_v2_report_path,
        },
        "transition_update": transition_update,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run baseline trade-design redesign experiment without changing core entry logic."
    )
    parser.add_argument("--data-dir", default="data", help="Directory containing per-ticker OHLCV CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory for redesign artifacts.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Path to baseline config JSON.",
    )
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional metadata CSV path.",
    )
    parser.add_argument(
        "--hold-period-options",
        nargs="+",
        type=int,
        default=[3, 5, 7],
        help="Hold period values to evaluate. Default: 3 5 7",
    )
    parser.add_argument(
        "--min-trades-options",
        nargs="+",
        type=int,
        default=[5, 8, 10],
        help="Minimum trade thresholds to evaluate. Default: 5 8 10",
    )
    parser.add_argument(
        "--profit-buffer-pct",
        type=float,
        default=0.0,
        help="Optional profit buffer used when calculating buffered win rate. Default: 0.0",
    )
    parser.add_argument(
        "--allow-overlap",
        action="store_true",
        help="Allow overlapping trades during evaluation.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = run_baseline_trade_design_redesign(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        hold_period_options=args.hold_period_options,
        min_trades_options=args.min_trades_options,
        profit_buffer_pct=float(args.profit_buffer_pct),
        allow_overlap=bool(args.allow_overlap),
    )
    print(f"Decision: {result['go_no_go']['decision']}")
    print(f"Best global hold period: {result['go_no_go']['best_global_hold_period']}")
    print(f"Best global min trades: {result['go_no_go']['best_global_min_trades']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
