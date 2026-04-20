"""Run the first baseline v4 quality-gate experiment or prepare its scaffold."""

from __future__ import annotations

import argparse
import json
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
    _resolve_price_files,
    _safe_float,
    _safe_int,
)


SCAFFOLD_COLUMNS = [
    "candidate_id",
    "entry_anchor_rule",
    "quality_gate_id",
    "gate_summary",
    "min_body_to_range_ratio",
    "min_close_vs_open_pct",
    "min_range_pct",
    "min_close_vs_anchor_pct",
    "hold_period",
    "min_trades_threshold",
    "status",
]

RESULT_COLUMNS = [
    "ticker",
    "variant_id",
    "candidate_id",
    "comparison_role",
    "entry_rule",
    "entry_anchor_rule",
    "quality_gate_id",
    "hold_period",
    "min_trades_threshold",
    "profit_buffer_pct",
    "applied_threshold",
    "candidate_signal_count",
    "candidate_total_trades",
    "candidate_eligible_for_analysis",
    "win_rate",
    "buffered_win_rate",
    "average_return",
    "max_drawdown",
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

SUMMARY_COLUMNS = [
    "variant_id",
    "candidate_id",
    "comparison_role",
    "entry_rule",
    "entry_anchor_rule",
    "quality_gate_id",
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
    "trade_retention_vs_reference",
    "coverage_gain_vs_reference",
    "mean_average_return_delta_vs_v3",
    "global_selection_score",
]

GO_NO_GO_DECISIONS = {
    "no_go",
    "keep_experimental",
    "promote_for_validation",
}


class BaselineV4QualityGateCliError(ValueError):
    """Friendly CLI error for baseline v4 quality-gate experiment."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _safe_str(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize_for_json(payload), indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _buffered_win_rate(trades_df: pd.DataFrame, profit_buffer_pct: float) -> float:
    if trades_df.empty:
        return 0.0
    return round(float(trades_df["return_pct"].gt(float(profit_buffer_pct)).mean() * 100.0), 4)


def _safe_ratio(numerator: float, denominator: float) -> float:
    if float(denominator) <= 0:
        return 1.0 if float(numerator) > 0 else 0.0
    return round(float(numerator) / float(denominator), 4)


def _build_scaffold_matrix(hold_period: int, min_trades: int) -> pd.DataFrame:
    rows = [
        {
            "candidate_id": "baseline_v4_quality_gate_guard",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "body_strength_floor",
            "gate_summary": "Require stronger bullish body before accepting fast anchor signal.",
            "min_body_to_range_ratio": 0.55,
            "min_close_vs_open_pct": 0.35,
            "min_range_pct": 0.80,
            "min_close_vs_anchor_pct": 0.00,
            "hold_period": int(hold_period),
            "min_trades_threshold": int(min_trades),
            "status": "scaffold_only",
        },
        {
            "candidate_id": "baseline_v4_quality_gate_guard_confirmed",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "body_strength_plus_anchor_confirmation",
            "gate_summary": "Add minimum close distance above fast anchor to reject weak closes.",
            "min_body_to_range_ratio": 0.50,
            "min_close_vs_open_pct": 0.30,
            "min_range_pct": 0.80,
            "min_close_vs_anchor_pct": 0.20,
            "hold_period": int(hold_period),
            "min_trades_threshold": int(min_trades),
            "status": "scaffold_only",
        },
        {
            "candidate_id": "baseline_v4_quality_gate_guard_volatility_floor",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "body_strength_plus_volatility_floor",
            "gate_summary": "Reject quiet candles that sit above anchor without meaningful range expansion.",
            "min_body_to_range_ratio": 0.45,
            "min_close_vs_open_pct": 0.25,
            "min_range_pct": 1.10,
            "min_close_vs_anchor_pct": 0.10,
            "hold_period": int(hold_period),
            "min_trades_threshold": int(min_trades),
            "status": "scaffold_only",
        },
    ]
    return pd.DataFrame(rows).reindex(columns=SCAFFOLD_COLUMNS)


def _load_scaffold_matrix(output_dir: Path, hold_period: int, min_trades: int) -> pd.DataFrame:
    matrix_path = Path(output_dir) / "baseline_v4_quality_gate_candidate_matrix.csv"
    if matrix_path.exists():
        try:
            frame = pd.read_csv(matrix_path)
            if not frame.empty:
                for column in SCAFFOLD_COLUMNS:
                    if column not in frame.columns:
                        frame[column] = None
                frame["hold_period"] = frame["hold_period"].fillna(int(hold_period)).astype(int)
                frame["min_trades_threshold"] = frame["min_trades_threshold"].fillna(int(min_trades)).astype(int)
                return frame.reindex(columns=SCAFFOLD_COLUMNS)
        except Exception:
            pass
    return _build_scaffold_matrix(hold_period=hold_period, min_trades=min_trades)


def _base_control_configs() -> List[Dict[str, object]]:
    return [
        {
            "variant_id": "baseline_reference",
            "candidate_id": "baseline_v2_hold3_with_trend_guard",
            "comparison_role": "reference",
            "entry_rule": "close_gt_ema50_and_bullish_candle",
            "entry_anchor_rule": "close_gt_ema50_and_bullish_candle",
            "quality_gate_id": "none",
        },
        {
            "variant_id": "baseline_v3_ema20_trend_guard",
            "candidate_id": "baseline_v3_ema20_trend_guard",
            "comparison_role": "v3_control",
            "entry_rule": "close_gt_ema20_and_bullish_candle",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "none",
        },
    ]


def _build_variant_configs(matrix_df: pd.DataFrame) -> List[Dict[str, object]]:
    configs = _base_control_configs()
    for row in matrix_df.to_dict(orient="records"):
        config = dict(row)
        config["variant_id"] = str(config.get("candidate_id") or "")
        config["comparison_role"] = "v4_candidate"
        config["entry_rule"] = "v4_quality_gate_guard"
        configs.append(config)
    return configs


def _load_v4_context(output_dir: Path) -> Dict[str, object]:
    artifact_map = {
        "next_experiment": "baseline_v4_next_experiment.json",
        "plan": "baseline_v4_redesign_plan.json",
        "v3_go_no_go": "baseline_v3_signal_rule_go_no_go.json",
        "v3_summary": "baseline_v3_signal_rule_summary.json",
    }
    payloads: Dict[str, object] = {}
    warnings: List[str] = []
    for key, filename in artifact_map.items():
        payload, item_warnings = read_json_object(Path(output_dir) / filename, filename)
        payloads[key] = payload if isinstance(payload, dict) else {}
        warnings.extend(item_warnings)
    payloads["warnings"] = dedupe(warnings)
    return payloads


def _prepare_quality_features(feature_frame: pd.DataFrame) -> pd.DataFrame:
    working = feature_frame.copy()
    if "ema20" not in working.columns:
        working["ema20"] = working["close"].ewm(span=20, adjust=False, min_periods=20).mean()

    working["candle_range"] = (working["high"] - working["low"]).clip(lower=0.0)
    working["candle_body"] = (working["close"] - working["open"]).abs()
    working["body_to_range_ratio"] = (
        working["candle_body"].div(working["candle_range"].where(working["candle_range"].gt(0.0)))
    ).fillna(0.0)
    working["close_vs_open_pct"] = (
        working["close"].sub(working["open"]).div(working["open"].where(working["open"].gt(0.0))).mul(100.0)
    ).fillna(0.0)
    working["range_pct"] = (
        working["candle_range"].div(working["close"].where(working["close"].gt(0.0))).mul(100.0)
    ).fillna(0.0)
    working["close_vs_anchor_pct"] = (
        working["close"].sub(working["ema20"]).div(working["ema20"].where(working["ema20"].gt(0.0))).mul(100.0)
    ).fillna(0.0)
    return working


def _evaluate_signal_variant(
    feature_frame: pd.DataFrame,
    config: Dict[str, object],
    threshold: float,
    hold_period: int,
    min_trades: int,
    profit_buffer_pct: float,
) -> Dict[str, object]:
    working = _prepare_quality_features(feature_frame=feature_frame)
    comparison_role = str(config.get("comparison_role") or "")
    candidate_id = str(config.get("candidate_id") or "")
    entry_rule = str(config.get("entry_rule") or "")

    if comparison_role in {"reference", "v3_control"}:
        candidate_frame, signal_column, resolved_entry_rule = _candidate_signal(
            feature_frame=working,
            candidate_id=candidate_id,
            threshold=float(threshold),
            entry_rule=entry_rule,
        )
    else:
        signal_column = f"signal_{candidate_id}"
        base_anchor = (
            working["close"].gt(working["ema20"])
            & working["ema20"].notna()
            & working["close"].gt(working["open"])
        )
        quality_gate = (
            working["body_to_range_ratio"].ge(float(config.get("min_body_to_range_ratio") or 0.0))
            & working["close_vs_open_pct"].ge(float(config.get("min_close_vs_open_pct") or 0.0))
            & working["range_pct"].ge(float(config.get("min_range_pct") or 0.0))
            & working["close_vs_anchor_pct"].ge(float(config.get("min_close_vs_anchor_pct") or 0.0))
        )
        candidate_frame = working.copy()
        candidate_frame[signal_column] = (base_anchor & quality_gate).fillna(False)
        resolved_entry_rule = str(config.get("entry_anchor_rule") or "close_gt_ema20_and_bullish_candle")

    signal_count = int(candidate_frame[signal_column].fillna(False).astype(bool).sum())
    result = backtest_signal_frame(
        candidate_frame,
        signal_column=signal_column,
        hold_period=int(hold_period),
        allow_overlap=False,
    )
    buffered_win_rate = _buffered_win_rate(result.trades, profit_buffer_pct=profit_buffer_pct)
    score_components = _compute_score_components(
        total_trades=int(result.total_trades),
        buffered_win_rate=float(buffered_win_rate),
        average_return=float(result.average_return),
        max_drawdown=float(result.max_drawdown),
        min_trades_threshold=int(min_trades),
    )
    return {
        "entry_rule": resolved_entry_rule,
        "signal_count": signal_count,
        "total_trades": int(result.total_trades),
        "win_rate": float(result.win_rate),
        "buffered_win_rate": float(buffered_win_rate),
        "average_return": float(result.average_return),
        "max_drawdown": float(result.max_drawdown),
        "eligible_for_analysis": bool(int(result.total_trades) >= int(min_trades)),
        **score_components,
    }


def evaluate_v4_quality_gate_matrix(
    data_dir: Path,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    matrix_df: pd.DataFrame,
    hold_period: int,
    min_trades: int,
    profit_buffer_pct: float,
) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    variant_configs = _build_variant_configs(matrix_df=matrix_df)

    for path in _resolve_price_files(data_dir):
        ticker = path.stem.upper()
        frame, _ = load_price_csv(path)
        runtime = resolve_phase_a_runtime_settings(
            ticker=ticker,
            baseline_config=baseline_payload,
            metadata_lookup=metadata_lookup,
        )
        metadata_row = dict(runtime.get("metadata_row") or {})
        feature_frame = _feature_frame(frame=frame, threshold=float(runtime["threshold"]))

        for config in variant_configs:
            metrics = _evaluate_signal_variant(
                feature_frame=feature_frame,
                config=config,
                threshold=float(runtime["threshold"]),
                hold_period=int(hold_period),
                min_trades=int(min_trades),
                profit_buffer_pct=float(profit_buffer_pct),
            )
            rows.append(
                {
                    "ticker": ticker,
                    "variant_id": str(config.get("variant_id") or ""),
                    "candidate_id": str(config.get("candidate_id") or ""),
                    "comparison_role": str(config.get("comparison_role") or ""),
                    "entry_rule": str(metrics.get("entry_rule") or ""),
                    "entry_anchor_rule": str(config.get("entry_anchor_rule") or ""),
                    "quality_gate_id": str(config.get("quality_gate_id") or ""),
                    "hold_period": int(hold_period),
                    "min_trades_threshold": int(min_trades),
                    "profit_buffer_pct": float(profit_buffer_pct),
                    "applied_threshold": float(runtime["threshold"]),
                    "candidate_signal_count": int(metrics["signal_count"]),
                    "candidate_total_trades": int(metrics["total_trades"]),
                    "candidate_eligible_for_analysis": bool(metrics["eligible_for_analysis"]),
                    "win_rate": float(metrics["win_rate"]),
                    "buffered_win_rate": float(metrics["buffered_win_rate"]),
                    "average_return": float(metrics["average_return"]),
                    "max_drawdown": float(metrics["max_drawdown"]),
                    "score_quality_reward": float(metrics["score_quality_reward"]),
                    "score_trade_support_reward": float(metrics["score_trade_support_reward"]),
                    "score_drawdown_penalty": float(metrics["score_drawdown_penalty"]),
                    "score_low_trade_penalty": float(metrics["score_low_trade_penalty"]),
                    "score": float(metrics["score"]),
                    "category": metadata_row.get("category"),
                    "market_cap_group": metadata_row.get("market_cap_group"),
                    "sector": metadata_row.get("sector"),
                    "beta_group": metadata_row.get("beta_group"),
                }
            )

    results_df = pd.DataFrame(rows)
    if results_df.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)
    return results_df.reindex(columns=RESULT_COLUMNS).sort_values(
        ["ticker", "comparison_role", "score", "candidate_total_trades", "candidate_signal_count"],
        ascending=[True, True, False, False, False],
    ).reset_index(drop=True)


def build_summary(results_df: pd.DataFrame) -> pd.DataFrame:
    if results_df.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    grouped = (
        results_df.groupby(
            [
                "variant_id",
                "candidate_id",
                "comparison_role",
                "entry_rule",
                "entry_anchor_rule",
                "quality_gate_id",
                "hold_period",
                "min_trades_threshold",
                "profit_buffer_pct",
            ],
            dropna=False,
        )
        .agg(
            ticker_count=("ticker", "nunique"),
            eligible_ticker_count=("candidate_eligible_for_analysis", "sum"),
            positive_score_ticker_count=("score", lambda values: int((values > 0).sum())),
            total_trades_sum=("candidate_total_trades", "sum"),
            signal_count_sum=("candidate_signal_count", "sum"),
            mean_score=("score", "mean"),
            mean_win_rate=("win_rate", "mean"),
            mean_buffered_win_rate=("buffered_win_rate", "mean"),
            mean_average_return=("average_return", "mean"),
            mean_max_drawdown=("max_drawdown", "mean"),
        )
        .reset_index()
    )

    reference_row = dict(grouped.loc[grouped["variant_id"].eq("baseline_reference")].iloc[0].to_dict())
    v3_row = dict(grouped.loc[grouped["variant_id"].eq("baseline_v3_ema20_trend_guard")].iloc[0].to_dict())

    grouped["trade_retention_vs_reference"] = grouped["total_trades_sum"].map(
        lambda value: _safe_ratio(value, _safe_float(reference_row.get("total_trades_sum")))
    )
    grouped["coverage_gain_vs_reference"] = (
        grouped["eligible_ticker_count"] - _safe_int(reference_row.get("eligible_ticker_count"))
    )
    grouped["mean_average_return_delta_vs_v3"] = (
        grouped["mean_average_return"] - _safe_float(v3_row.get("mean_average_return"))
    )
    grouped["global_selection_score"] = (
        grouped["mean_average_return"] * 5.0
        + grouped["eligible_ticker_count"] * 6.0
        + grouped["positive_score_ticker_count"] * 2.0
        + grouped["total_trades_sum"] * 0.10
    )
    return grouped.reindex(columns=SUMMARY_COLUMNS).sort_values(
        ["comparison_role", "global_selection_score", "eligible_ticker_count", "mean_average_return"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)


def determine_go_no_go(
    summary_df: pd.DataFrame,
    context_payloads: Dict[str, object],
) -> Dict[str, object]:
    reference = dict(summary_df.loc[summary_df["variant_id"].eq("baseline_reference")].iloc[0].to_dict())
    v3_control = dict(summary_df.loc[summary_df["variant_id"].eq("baseline_v3_ema20_trend_guard")].iloc[0].to_dict())
    v4_candidates = summary_df.loc[summary_df["comparison_role"].eq("v4_candidate")].copy()
    if v4_candidates.empty:
        raise BaselineV4QualityGateCliError("No v4 candidates found in summary.")

    next_experiment = safe_dict(context_payloads.get("next_experiment"))
    success_text = _safe_str(next_experiment.get("expected_success_signal"))
    failure_text = _safe_str(next_experiment.get("expected_failure_signal"))

    def _decision_rank(row: pd.Series) -> Tuple[int, float, int, float, float]:
        coverage_ok = _safe_int(row.get("eligible_ticker_count")) >= 3
        far_above_reference = _safe_int(row.get("total_trades_sum")) >= max(20, _safe_int(reference.get("total_trades_sum")) * 2)
        quality_positive = _safe_float(row.get("mean_average_return")) > 0
        quality_improved_vs_v3 = _safe_float(row.get("mean_average_return_delta_vs_v3")) >= 0.25
        decision_rank = 2 if (coverage_ok and far_above_reference and quality_positive and quality_improved_vs_v3) else 1 if coverage_ok and quality_improved_vs_v3 else 0
        return (
            decision_rank,
            _safe_float(row.get("mean_average_return")),
            _safe_int(row.get("eligible_ticker_count")),
            _safe_float(row.get("mean_score")),
            _safe_float(row.get("total_trades_sum")),
        )

    ranked = v4_candidates.sort_values(
        ["mean_average_return", "eligible_ticker_count", "mean_score", "total_trades_sum"],
        ascending=[False, False, False, False],
    ).copy()
    ranked["_rank"] = ranked.apply(_decision_rank, axis=1)
    ranked = ranked.sort_values("_rank", ascending=False, key=lambda col: col).reset_index(drop=True)
    best = dict(ranked.iloc[0].to_dict())

    coverage_ok = _safe_int(best.get("eligible_ticker_count")) >= 3
    far_above_reference = _safe_int(best.get("total_trades_sum")) >= max(20, _safe_int(reference.get("total_trades_sum")) * 2)
    quality_positive = _safe_float(best.get("mean_average_return")) > 0
    quality_improved_vs_v3 = _safe_float(best.get("mean_average_return_delta_vs_v3")) >= 0.25
    quality_preserved = bool(quality_positive and quality_improved_vs_v3)

    if coverage_ok and far_above_reference and quality_preserved:
        decision = "promote_for_validation"
        recommended_next_action = "run_baseline_v4_candidate_validation"
    elif coverage_ok and _safe_float(best.get("mean_average_return_delta_vs_v3")) > 0 and _safe_float(best.get("mean_average_return")) > -0.25:
        decision = "keep_experimental"
        recommended_next_action = "tighten_quality_gate_then_rerun_v4"
    else:
        decision = "no_go"
        recommended_next_action = "redesign_quality_gate_or_shift_to_exit_hold_hypothesis"

    return {
        "best_candidate_id": str(best.get("candidate_id") or ""),
        "best_variant_id": str(best.get("variant_id") or ""),
        "decision": decision,
        "coverage_ok": bool(coverage_ok),
        "trade_support_ok": bool(far_above_reference),
        "quality_preserved": bool(quality_preserved),
        "eligible_ticker_count": _safe_int(best.get("eligible_ticker_count")),
        "total_trades_sum": _safe_int(best.get("total_trades_sum")),
        "mean_average_return": _safe_float(best.get("mean_average_return")),
        "mean_average_return_delta_vs_v3": _safe_float(best.get("mean_average_return_delta_vs_v3")),
        "trade_retention_vs_reference": _safe_float(best.get("trade_retention_vs_reference")),
        "coverage_gain_vs_reference": _safe_int(best.get("coverage_gain_vs_reference")),
        "reference_variant_id": str(reference.get("variant_id") or ""),
        "v3_control_variant_id": str(v3_control.get("variant_id") or ""),
        "recommended_next_action": recommended_next_action,
        "expected_success_signal": success_text,
        "expected_failure_signal": failure_text,
        "decision_notes": dedupe(
            [
                "Coverage target tercapai (>=3 ticker eligible)." if coverage_ok else "Coverage masih di bawah target minimum 3 ticker eligible.",
                "Trade support jauh di atas baseline reference." if far_above_reference else "Trade support belum cukup jauh di atas baseline reference.",
                "Quality preserved vs baseline_v3_ema20_trend_guard." if quality_preserved else "Quality belum preserved versus baseline_v3_ema20_trend_guard.",
                "Jangan lanjutkan entry relaxation only." if decision == "no_go" else "",
            ]
        ),
    }


def build_summary_payload(
    summary_df: pd.DataFrame,
    go_no_go: Dict[str, object],
    context_payloads: Dict[str, object],
) -> Dict[str, object]:
    reference = dict(summary_df.loc[summary_df["variant_id"].eq("baseline_reference")].iloc[0].to_dict())
    v3_control = dict(summary_df.loc[summary_df["variant_id"].eq("baseline_v3_ema20_trend_guard")].iloc[0].to_dict())
    best_variant = dict(summary_df.loc[summary_df["variant_id"].eq(go_no_go["best_variant_id"])].iloc[0].to_dict())
    return {
        "generated_at": _now_iso(),
        "reference_summary": _sanitize_for_json(reference),
        "v3_control_summary": _sanitize_for_json(v3_control),
        "best_v4_candidate_summary": _sanitize_for_json(best_variant),
        "go_no_go": _sanitize_for_json(go_no_go),
        "next_experiment_context": _sanitize_for_json(safe_dict(context_payloads.get("next_experiment"))),
        "warnings": list(context_payloads.get("warnings") or []),
    }


def build_report_text(summary_payload: Dict[str, object]) -> str:
    reference = safe_dict(summary_payload.get("reference_summary"))
    v3_control = safe_dict(summary_payload.get("v3_control_summary"))
    best = safe_dict(summary_payload.get("best_v4_candidate_summary"))
    go_no_go = safe_dict(summary_payload.get("go_no_go"))

    lines = [
        "Baseline v4 Quality Gate Experiment",
        "===================================",
        "",
        f"- Decision: {go_no_go.get('decision')}",
        f"- Best candidate: {go_no_go.get('best_candidate_id')}",
        f"- Coverage ok: {go_no_go.get('coverage_ok')}",
        f"- Trade support ok: {go_no_go.get('trade_support_ok')}",
        f"- Quality preserved: {go_no_go.get('quality_preserved')}",
        f"- Recommended next action: {go_no_go.get('recommended_next_action')}",
        "",
        "Reference baseline:",
        f"- eligible_ticker_count={_safe_int(reference.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_int(reference.get('total_trades_sum'))}",
        f"- mean_average_return={_safe_float(reference.get('mean_average_return')):+.5f}",
        "",
        "V3 control:",
        f"- eligible_ticker_count={_safe_int(v3_control.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_int(v3_control.get('total_trades_sum'))}",
        f"- mean_average_return={_safe_float(v3_control.get('mean_average_return')):+.5f}",
        "",
        "Best v4 candidate:",
        f"- candidate_id={best.get('candidate_id')}",
        f"- quality_gate_id={best.get('quality_gate_id')}",
        f"- eligible_ticker_count={_safe_int(best.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_int(best.get('total_trades_sum'))}",
        f"- mean_average_return={_safe_float(best.get('mean_average_return')):+.5f}",
        f"- trade_retention_vs_reference={_safe_float(best.get('trade_retention_vs_reference')):.4f}",
        f"- coverage_gain_vs_reference={_safe_int(best.get('coverage_gain_vs_reference'))}",
        f"- mean_average_return_delta_vs_v3={_safe_float(best.get('mean_average_return_delta_vs_v3')):+.5f}",
    ]
    if go_no_go.get("decision_notes"):
        lines.extend(["", "Decision notes:"])
        for item in list(go_no_go.get("decision_notes") or []):
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _write_scaffold_artifacts(output_dir: Path, matrix_df: pd.DataFrame, hold_period: int, min_trades: int, scaffold_only: bool) -> Dict[str, object]:
    payload = {
        "generated_at": _now_iso(),
        "experiment_id": "baseline_v4_quality_gate_guard",
        "scaffold_only": bool(scaffold_only),
        "objective": (
            "Prepare the first v4 experiment around fast anchor + quality gate without changing "
            "baseline defaults or running a full experiment matrix."
        ),
        "candidate_matrix": matrix_df.to_dict(orient="records"),
        "execution_notes": [
            "Gunakan anchor cepat yang sudah terbukti membuka coverage, tetapi tambahkan quality gate ringan.",
            "Jangan ubah baseline aktif atau scoring engine.",
            "Bandingkan hanya terhadap reference rule dan fast-anchor v3 sebagai control.",
        ],
    }

    matrix_path = output_dir / "baseline_v4_quality_gate_candidate_matrix.csv"
    payload_path = output_dir / "baseline_v4_quality_gate_experiment_scaffold.json"
    notes_path = output_dir / "baseline_v4_quality_gate_experiment_scaffold.txt"

    matrix_df.to_csv(matrix_path, index=False)
    _write_json(payload_path, payload)
    _write_text(
        notes_path,
        [
            "Baseline v4 Quality Gate Experiment Scaffold",
            "============================================",
            "",
            "- experiment_id=baseline_v4_quality_gate_guard",
            f"- scaffold_only={bool(scaffold_only)}",
            f"- hold_period={int(hold_period)}",
            f"- min_trades_threshold={int(min_trades)}",
            "",
            "Candidate matrix prepared. No full evaluation has been executed." if bool(scaffold_only) else "Candidate matrix prepared for real-data experiment execution.",
        ],
    )
    return {
        "payload": payload,
        "artifacts": {
            "matrix_csv": str(matrix_path),
            "scaffold_json": str(payload_path),
            "scaffold_txt": str(notes_path),
        },
    }


def run_baseline_v4_quality_gate_experiment(
    output_dir: Path,
    hold_period: int,
    min_trades: int,
    scaffold_only: bool = True,
    data_dir: Optional[Path] = None,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
    profit_buffer_pct: float = 0.0,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix_df = _load_scaffold_matrix(output_dir=output_dir, hold_period=hold_period, min_trades=min_trades)
    scaffold_meta = _write_scaffold_artifacts(
        output_dir=output_dir,
        matrix_df=matrix_df,
        hold_period=hold_period,
        min_trades=min_trades,
        scaffold_only=scaffold_only,
    )

    if bool(scaffold_only):
        return {
            "payload": scaffold_meta["payload"],
            "matrix_df": matrix_df,
            "artifacts": scaffold_meta["artifacts"],
        }

    resolved_data_dir = Path(data_dir or "data")
    baseline_payload, baseline_warnings, _ = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    context_payloads = _load_v4_context(output_dir=output_dir)
    context_payloads["warnings"] = dedupe([*list(context_payloads.get("warnings") or []), *baseline_warnings, *metadata_warnings])

    results_df = evaluate_v4_quality_gate_matrix(
        data_dir=resolved_data_dir,
        baseline_payload=baseline_payload,
        metadata_lookup=metadata_lookup,
        matrix_df=matrix_df,
        hold_period=int(hold_period),
        min_trades=int(min_trades),
        profit_buffer_pct=float(profit_buffer_pct),
    )
    if results_df.empty:
        raise BaselineV4QualityGateCliError("No v4 quality-gate results were produced.")

    summary_df = build_summary(results_df=results_df)
    go_no_go = determine_go_no_go(summary_df=summary_df, context_payloads=context_payloads)
    summary_payload = build_summary_payload(summary_df=summary_df, go_no_go=go_no_go, context_payloads=context_payloads)
    report_text = build_report_text(summary_payload=summary_payload)

    results_path = output_dir / "baseline_v4_quality_gate_results.csv"
    summary_path = output_dir / "baseline_v4_quality_gate_summary.json"
    report_path = output_dir / "baseline_v4_quality_gate_report.txt"
    go_no_go_path = output_dir / "baseline_v4_quality_gate_go_no_go.json"

    results_df.to_csv(results_path, index=False)
    _write_json(summary_path, summary_payload)
    _write_text(report_path, report_text.rstrip("\n").splitlines())
    _write_json(go_no_go_path, go_no_go)

    return {
        "results_df": results_df,
        "summary_df": summary_df,
        "summary_payload": summary_payload,
        "go_no_go": go_no_go,
        "artifacts": {
            **scaffold_meta["artifacts"],
            "results_csv": str(results_path),
            "summary_json": str(summary_path),
            "report_txt": str(report_path),
            "go_no_go_json": str(go_no_go_path),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare or run the first baseline v4 quality-gate experiment.")
    parser.add_argument("--output-dir", default="output", help="Directory for artifacts.")
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files for real evaluation.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Path to the frozen baseline JSON used for runtime settings.",
    )
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Optional ticker metadata CSV.")
    parser.add_argument("--hold-period", type=int, default=3, help="Hold period for the v4 experiment.")
    parser.add_argument("--min-trades", type=int, default=5, help="Min trades threshold for v4 eligibility.")
    parser.add_argument("--profit-buffer-pct", type=float, default=0.0, help="Optional profit buffer for buffered win rate.")
    parser.add_argument(
        "--scaffold-only",
        action="store_true",
        help="Only prepare scaffold artifacts and candidate matrix. Skip real-data experiment execution.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = run_baseline_v4_quality_gate_experiment(
        output_dir=Path(args.output_dir),
        data_dir=Path(args.data_dir),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        hold_period=int(args.hold_period),
        min_trades=int(args.min_trades),
        profit_buffer_pct=float(args.profit_buffer_pct),
        scaffold_only=bool(args.scaffold_only),
    )
    if bool(args.scaffold_only):
        print(f"Prepared scaffold: {result['payload']['experiment_id']}")
        print(f"Candidates: {len(result['matrix_df'])}")
    else:
        print(f"Decision: {result['go_no_go']['decision']}")
        print(f"Best candidate: {result['go_no_go']['best_candidate_id']}")
        print(f"Next action: {result['go_no_go']['recommended_next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
