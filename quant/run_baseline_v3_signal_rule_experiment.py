"""Run a controlled signal-rule experiment for baseline v3 entry candidates."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.evaluate_phase_a_real_data import load_price_csv  # noqa: E402
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.phase_a_transition_utils import dedupe, read_json_object  # noqa: E402
from quant.run_baseline_v2_candidate_validation import (  # noqa: E402
    _evaluate_one_variant,
    _feature_frame,
    _resolve_price_files,
    _safe_float,
    _safe_int,
    _sanitize_for_json,
    _write_json,
    _write_text,
)


RESULT_COLUMNS = [
    "ticker",
    "rule_id",
    "candidate_id",
    "entry_rule",
    "comparison_role",
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
    "rule_id",
    "candidate_id",
    "entry_rule",
    "comparison_role",
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
    "trade_retention_vs_baseline",
    "coverage_gain_vs_old_rule",
    "score_delta_vs_baseline",
    "average_return_delta_vs_baseline",
    "global_selection_score",
]

DECISION_VALUES = {
    "no_go",
    "keep_experimental",
    "promote_for_validation",
    "promote_as_new_candidate_default",
}

ENTRY_RULE_BY_CANDIDATE_ID = {
    "baseline_v2_hold3": "close_gt_ema50_and_volume_spike_threshold",
    "baseline_v2_hold3_with_min_return_buffer": "close_gt_ema50_and_volume_spike_threshold",
    "baseline_v2_hold3_with_simplified_entry": "close_gt_ema50",
    "baseline_v2_hold3_with_trend_guard": "close_gt_ema50_and_bullish_candle",
    "baseline_v3_ema20_trend": "close_gt_ema20",
    "baseline_v3_ema20_trend_guard": "close_gt_ema20_and_bullish_candle",
    "baseline_v3_ema20_volume_relaxed": "close_gt_ema20_and_volume_spike_relaxed",
}

V3_RULE_CONFIGS = [
    {
        "rule_id": "baseline_v3_ema20_trend",
        "candidate_id": "baseline_v3_ema20_trend",
        "entry_rule": "close_gt_ema20",
        "comparison_role": "v3_candidate",
    },
    {
        "rule_id": "baseline_v3_ema20_trend_guard",
        "candidate_id": "baseline_v3_ema20_trend_guard",
        "entry_rule": "close_gt_ema20_and_bullish_candle",
        "comparison_role": "v3_candidate",
    },
    {
        "rule_id": "baseline_v3_ema20_volume_relaxed",
        "candidate_id": "baseline_v3_ema20_volume_relaxed",
        "entry_rule": "close_gt_ema20_and_volume_spike_relaxed",
        "comparison_role": "v3_candidate",
    },
]


class BaselineV3SignalRuleExperimentCliError(ValueError):
    """Friendly CLI error for baseline v3 signal-rule experiment."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_ratio(numerator: float, denominator: float) -> float:
    if float(denominator) <= 0:
        return 1.0 if float(numerator) > 0 else 0.0
    return round(float(numerator) / float(denominator), 4)


def _default_reference_candidate() -> Dict[str, object]:
    return {
        "rule_id": "baseline_reference",
        "candidate_id": "baseline_v2_hold3_with_simplified_entry",
        "entry_rule": "close_gt_ema50",
        "comparison_role": "baseline_reference",
    }


def _load_reference_candidate(candidate_file: Optional[Path]) -> Dict[str, object]:
    reference = _default_reference_candidate()
    if candidate_file is None:
        return reference

    payload, _ = read_json_object(Path(candidate_file), "Baseline v2 best candidate JSON")
    selected = dict(payload.get("selected_candidate") or {}) if isinstance(payload, dict) else {}
    candidate_id = str(selected.get("candidate_id") or "").strip()
    entry_rule = str(selected.get("entry_rule") or "").strip()

    if not candidate_id and not entry_rule:
        return reference

    if not entry_rule:
        entry_rule = ENTRY_RULE_BY_CANDIDATE_ID.get(candidate_id, reference["entry_rule"])

    reference["rule_id"] = "baseline_reference"
    reference["candidate_id"] = candidate_id or str(reference["candidate_id"])
    reference["entry_rule"] = entry_rule or str(reference["entry_rule"])
    return reference


def _rule_configs(reference_candidate: Dict[str, object]) -> List[Dict[str, object]]:
    return [dict(reference_candidate), *[dict(item) for item in V3_RULE_CONFIGS]]


def evaluate_rule_results(
    data_dir: Path,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    rule_configs: Sequence[Dict[str, object]],
    hold_period: int,
    min_trades: int,
    profit_buffer_pct: float,
) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []

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

        for config in rule_configs:
            metrics = _evaluate_one_variant(
                feature_frame=feature_frame,
                candidate_id=str(config["candidate_id"]),
                threshold=float(runtime["threshold"]),
                hold_period=int(hold_period),
                min_trades=int(min_trades),
                profit_buffer_pct=float(profit_buffer_pct),
                entry_rule=str(config["entry_rule"]),
            )
            rows.append(
                {
                    "ticker": ticker,
                    "rule_id": str(config["rule_id"]),
                    "candidate_id": str(config["candidate_id"]),
                    "entry_rule": str(metrics["entry_rule"]),
                    "comparison_role": str(config["comparison_role"]),
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


def build_rule_summary(results_df: pd.DataFrame, reference_rule_id: str) -> pd.DataFrame:
    if results_df.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    grouped = (
        results_df.groupby(
            [
                "rule_id",
                "candidate_id",
                "entry_rule",
                "comparison_role",
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

    reference_rows = grouped.loc[grouped["rule_id"].eq(reference_rule_id)]
    if reference_rows.empty:
        raise BaselineV3SignalRuleExperimentCliError("Reference rule summary is missing.")
    reference = dict(reference_rows.iloc[0].to_dict())

    grouped["trade_retention_vs_baseline"] = grouped["total_trades_sum"].map(
        lambda value: _safe_ratio(value, _safe_float(reference.get("total_trades_sum")))
    )
    grouped["coverage_gain_vs_old_rule"] = (
        grouped["eligible_ticker_count"] - _safe_int(reference.get("eligible_ticker_count"))
    )
    grouped["score_delta_vs_baseline"] = grouped["mean_score"] - _safe_float(reference.get("mean_score"))
    grouped["average_return_delta_vs_baseline"] = (
        grouped["mean_average_return"] - _safe_float(reference.get("mean_average_return"))
    )
    grouped["global_selection_score"] = (
        grouped["mean_score"]
        + (grouped["eligible_ticker_count"] * 6.0)
        + (grouped["positive_score_ticker_count"] * 3.0)
        + (grouped["total_trades_sum"] * 0.10)
    )
    grouped = grouped.reindex(columns=SUMMARY_COLUMNS)
    return grouped.sort_values(
        ["comparison_role", "global_selection_score", "eligible_ticker_count", "mean_score", "total_trades_sum"],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)


def determine_rule_decision(
    rule_summary: Dict[str, object],
    reference_summary: Dict[str, object],
    min_eligible_tickers: int,
) -> Dict[str, object]:
    coverage_gain = _safe_int(rule_summary.get("coverage_gain_vs_old_rule"))
    eligible_ticker_count = _safe_int(rule_summary.get("eligible_ticker_count"))
    mean_score = _safe_float(rule_summary.get("mean_score"))
    score_delta = _safe_float(rule_summary.get("score_delta_vs_baseline"))
    average_return_delta = _safe_float(rule_summary.get("average_return_delta_vs_baseline"))
    mean_max_drawdown = _safe_float(rule_summary.get("mean_max_drawdown"))
    reference_mean_score = _safe_float(reference_summary.get("mean_score"))
    reference_average_return = _safe_float(reference_summary.get("mean_average_return"))
    reference_max_drawdown = _safe_float(reference_summary.get("mean_max_drawdown"))
    trade_retention = _safe_float(rule_summary.get("trade_retention_vs_baseline"))
    positive_score_ticker_count = _safe_int(rule_summary.get("positive_score_ticker_count"))

    quality_preserved = bool(
        mean_score >= max(reference_mean_score - 1.5, -2.0)
        and _safe_float(rule_summary.get("mean_average_return")) >= reference_average_return - 0.35
        and mean_max_drawdown <= reference_max_drawdown + 2.5
    )
    quality_collapse = bool(
        mean_score < max(reference_mean_score - 4.0, -5.0)
        or _safe_float(rule_summary.get("mean_average_return")) < reference_average_return - 0.6
        or mean_max_drawdown > reference_max_drawdown + 5.0
    )

    notes = [
        "Coverage ticker eligible naik dibanding rule referensi." if coverage_gain > 0 else "",
        "Kualitas rata-rata masih terjaga terhadap rule referensi." if quality_preserved else "",
        "Kualitas runtuh walaupun coverage naik." if coverage_gain > 0 and quality_collapse else "",
        "Rule masih terlalu sempit karena baru usable di kurang dari 2 ticker." if eligible_ticker_count < 2 else "",
    ]

    if quality_collapse or (coverage_gain > 0 and not quality_preserved and mean_score < -2.0):
        decision = "no_go"
        next_action = "drop_rule_from_redesign_shortlist"
    elif eligible_ticker_count >= int(min_eligible_tickers) and coverage_gain >= 2 and quality_preserved and (
        mean_score > 0 or (score_delta >= 2.0 and average_return_delta >= 0.0)
    ) and positive_score_ticker_count >= max(2, int(min_eligible_tickers) - 1):
        decision = "promote_as_new_candidate_default"
        next_action = "treat_rule_as_top_redesign_candidate_but_require_full_candidate_validation"
    elif eligible_ticker_count >= 2 and coverage_gain >= 1 and (
        quality_preserved or (score_delta >= 2.0 and average_return_delta >= 0.0)
    ) and trade_retention >= 0.6:
        decision = "promote_for_validation"
        next_action = "include_rule_in_next_baseline_v3_candidate_validation_sweep"
    elif eligible_ticker_count >= 2 and (coverage_gain > 0 or score_delta > 1.0 or trade_retention >= 0.85):
        decision = "keep_experimental"
        next_action = "keep_rule_in_redesign_backlog_without_promoting_default"
    else:
        decision = "no_go"
        next_action = "drop_rule_from_redesign_shortlist"

    return {
        "rule_id": str(rule_summary.get("rule_id") or ""),
        "candidate_id": str(rule_summary.get("candidate_id") or ""),
        "entry_rule": str(rule_summary.get("entry_rule") or ""),
        "decision": decision,
        "coverage_improved": bool(coverage_gain > 0),
        "quality_preserved": bool(quality_preserved),
        "eligible_ticker_count": eligible_ticker_count,
        "trade_retention_vs_baseline": trade_retention,
        "score_delta_vs_baseline": score_delta,
        "average_return_delta_vs_baseline": average_return_delta,
        "recommended_next_action": next_action,
        "decision_notes": dedupe(notes),
    }


def build_summary_payload(
    summary_df: pd.DataFrame,
    reference_rule_id: str,
    min_trades: int,
    min_eligible_tickers: int,
    warnings: Sequence[str],
) -> Dict[str, object]:
    reference_row = dict(summary_df.loc[summary_df["rule_id"].eq(reference_rule_id)].iloc[0].to_dict())
    decisions: List[Dict[str, object]] = []
    candidate_rows: List[Dict[str, object]] = []

    for row in summary_df.to_dict(orient="records"):
        if str(row.get("rule_id")) == str(reference_rule_id):
            continue
        decision = determine_rule_decision(
            rule_summary=row,
            reference_summary=reference_row,
            min_eligible_tickers=min_eligible_tickers,
        )
        decisions.append(decision)
        enriched = {**row, **decision}
        candidate_rows.append(_sanitize_for_json(enriched))

    rank_map = {
        "promote_as_new_candidate_default": 3,
        "promote_for_validation": 2,
        "keep_experimental": 1,
        "no_go": 0,
    }
    ranked = sorted(
        candidate_rows,
        key=lambda item: (
            rank_map.get(str(item.get("decision")), -1),
            _safe_float(item.get("global_selection_score")),
            _safe_int(item.get("eligible_ticker_count")),
            _safe_float(item.get("mean_score")),
            _safe_float(item.get("total_trades_sum")),
        ),
        reverse=True,
    )
    best_rule = dict(ranked[0]) if ranked else {}
    recommended_redesign_candidates = [
        {
            "candidate_id": str(item.get("candidate_id") or ""),
            "entry_rule": str(item.get("entry_rule") or ""),
            "hold_period": _safe_int(item.get("hold_period"), 3),
            "min_trades_threshold": _safe_int(item.get("min_trades_threshold"), min_trades),
            "decision": str(item.get("decision") or ""),
        }
        for item in ranked
        if str(item.get("decision")) in {"keep_experimental", "promote_for_validation", "promote_as_new_candidate_default"}
    ]

    if not best_rule:
        go_no_go = {
            "best_rule": None,
            "decision": "no_go",
            "coverage_improved": False,
            "quality_preserved": False,
            "eligible_ticker_count": 0,
            "recommended_next_action": "rerun_redesign_with_different_entry_logic",
            "recommended_redesign_candidates": [],
        }
    else:
        go_no_go = {
            "best_rule": str(best_rule.get("candidate_id") or best_rule.get("rule_id") or ""),
            "decision": str(best_rule.get("decision") or "no_go"),
            "coverage_improved": bool(best_rule.get("coverage_improved")),
            "quality_preserved": bool(best_rule.get("quality_preserved")),
            "eligible_ticker_count": _safe_int(best_rule.get("eligible_ticker_count")),
            "recommended_next_action": str(best_rule.get("recommended_next_action") or ""),
            "recommended_redesign_candidates": recommended_redesign_candidates,
        }

    go_no_go["baseline_reference_rule"] = {
        "candidate_id": str(reference_row.get("candidate_id") or ""),
        "entry_rule": str(reference_row.get("entry_rule") or ""),
        "eligible_ticker_count": _safe_int(reference_row.get("eligible_ticker_count")),
        "total_trades_sum": _safe_int(reference_row.get("total_trades_sum")),
        "mean_score": _safe_float(reference_row.get("mean_score")),
        "mean_average_return": _safe_float(reference_row.get("mean_average_return")),
    }

    return {
        "generated_at": _now_iso(),
        "guardrails": {
            "min_trades": int(min_trades),
            "min_eligible_tickers": int(min_eligible_tickers),
        },
        "reference_rule": _sanitize_for_json(reference_row),
        "rule_summaries": [_sanitize_for_json(row) for row in summary_df.to_dict(orient="records")],
        "rule_decisions": [_sanitize_for_json(item) for item in decisions],
        "recommended_redesign_candidates": recommended_redesign_candidates,
        "best_v3_rule": _sanitize_for_json(best_rule),
        "go_no_go": _sanitize_for_json(go_no_go),
        "warnings": dedupe([str(item) for item in list(warnings)]),
    }


def build_report_text(summary_payload: Dict[str, object]) -> str:
    reference = dict(summary_payload.get("reference_rule") or {})
    go_no_go = dict(summary_payload.get("go_no_go") or {})
    lines = [
        "Baseline v3 Signal Rule Experiment",
        "==================================",
        "",
        f"- Decision: {go_no_go.get('decision')}",
        f"- Best rule: {go_no_go.get('best_rule')}",
        f"- Coverage improved: {go_no_go.get('coverage_improved')}",
        f"- Quality preserved: {go_no_go.get('quality_preserved')}",
        f"- Eligible ticker count: {_safe_int(go_no_go.get('eligible_ticker_count'))}",
        f"- Recommended next action: {go_no_go.get('recommended_next_action')}",
        "",
        "Reference rule:",
        f"- candidate_id={reference.get('candidate_id')}",
        f"- entry_rule={reference.get('entry_rule')}",
        f"- eligible_ticker_count={_safe_int(reference.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_int(reference.get('total_trades_sum'))}",
        f"- mean_score={_safe_float(reference.get('mean_score')):+.4f}",
        f"- mean_average_return={_safe_float(reference.get('mean_average_return')):+.4f}",
        "",
        "Candidate rules:",
    ]

    for item in list(summary_payload.get("rule_decisions") or []):
        lines.extend(
            [
                f"- {item.get('candidate_id')}: decision={item.get('decision')}, "
                f"coverage_improved={item.get('coverage_improved')}, "
                f"quality_preserved={item.get('quality_preserved')}, "
                f"eligible_ticker_count={_safe_int(item.get('eligible_ticker_count'))}, "
                f"trade_retention_vs_baseline={_safe_float(item.get('trade_retention_vs_baseline')):.4f}, "
                f"score_delta_vs_baseline={_safe_float(item.get('score_delta_vs_baseline')):+.4f}",
            ]
        )

    candidates = list(summary_payload.get("recommended_redesign_candidates") or [])
    if candidates:
        lines.extend(["", "Recommended redesign candidates:"])
        for item in candidates:
            lines.append(
                f"- {item.get('candidate_id')} ({item.get('entry_rule')}), "
                f"hold_period={_safe_int(item.get('hold_period'))}, "
                f"min_trades_threshold={_safe_int(item.get('min_trades_threshold'))}, "
                f"decision={item.get('decision')}"
            )

    warnings = list(summary_payload.get("warnings") or [])
    if warnings:
        lines.extend(["", "Warnings:"])
        for item in warnings:
            lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def run_baseline_v3_signal_rule_experiment(
    data_dir: Path,
    output_dir: Path,
    baseline_config: Optional[Path],
    metadata_file: Optional[Path],
    min_trades: int,
    min_eligible_tickers: int,
    hold_period: int,
    profit_buffer_pct: float,
    candidate_file: Optional[Path] = None,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_payload, baseline_warnings, _ = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    reference_candidate = _load_reference_candidate(candidate_file=candidate_file)
    rule_configs = _rule_configs(reference_candidate=reference_candidate)

    results_df = evaluate_rule_results(
        data_dir=data_dir,
        baseline_payload=baseline_payload,
        metadata_lookup=metadata_lookup,
        rule_configs=rule_configs,
        hold_period=hold_period,
        min_trades=min_trades,
        profit_buffer_pct=profit_buffer_pct,
    )
    if results_df.empty:
        raise BaselineV3SignalRuleExperimentCliError("No rule experiment rows were produced.")

    summary_df = build_rule_summary(results_df=results_df, reference_rule_id=str(reference_candidate["rule_id"]))
    summary_payload = build_summary_payload(
        summary_df=summary_df,
        reference_rule_id=str(reference_candidate["rule_id"]),
        min_trades=min_trades,
        min_eligible_tickers=min_eligible_tickers,
        warnings=[*baseline_warnings, *metadata_warnings],
    )
    report_text = build_report_text(summary_payload=summary_payload)

    results_path = output_dir / "baseline_v3_signal_rule_results.csv"
    summary_path = output_dir / "baseline_v3_signal_rule_summary.json"
    report_path = output_dir / "baseline_v3_signal_rule_report.txt"
    go_no_go_path = output_dir / "baseline_v3_signal_rule_go_no_go.json"

    results_df.to_csv(results_path, index=False)
    _write_json(summary_path, summary_payload)
    _write_text(report_path, report_text.rstrip("\n").splitlines())
    _write_json(go_no_go_path, dict(summary_payload.get("go_no_go") or {}))

    return {
        "results_df": results_df,
        "summary_df": summary_df,
        "summary": summary_payload,
        "go_no_go": dict(summary_payload.get("go_no_go") or {}),
        "artifacts": {
            "results_csv": str(results_path),
            "summary_json": str(summary_path),
            "report_txt": str(report_path),
            "go_no_go_json": str(go_no_go_path),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run baseline v3 signal-rule experiment.")
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory for experiment artifacts.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Path to frozen Phase A baseline JSON.",
    )
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional ticker metadata CSV.",
    )
    parser.add_argument(
        "--candidate-file",
        default="output/baseline_v2_best_candidate.json",
        help="Optional baseline v2 candidate JSON used as reference rule if available.",
    )
    parser.add_argument("--min-trades", type=int, default=5, help="Min trades threshold for eligibility.")
    parser.add_argument(
        "--min-eligible-tickers",
        type=int,
        default=3,
        help="Guardrail for broad enough candidate coverage.",
    )
    parser.add_argument("--hold-period", type=int, default=3, help="Hold period used across all tested rules.")
    parser.add_argument(
        "--profit-buffer-pct",
        type=float,
        default=0.0,
        help="Optional profit buffer used for buffered win rate scoring.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    result = run_baseline_v3_signal_rule_experiment(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        min_trades=int(args.min_trades),
        min_eligible_tickers=int(args.min_eligible_tickers),
        hold_period=int(args.hold_period),
        profit_buffer_pct=float(args.profit_buffer_pct),
        candidate_file=Path(args.candidate_file) if args.candidate_file else None,
    )
    print(f"Decision: {result['go_no_go']['decision']}")
    print(f"Best rule: {result['go_no_go']['best_rule']}")
    print(f"Next action: {result['go_no_go']['recommended_next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
