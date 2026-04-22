"""Validate narrow Layer 1 regime refinements for holdout resilience on the updated core stack."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

if __package__ is None or __package__ == "":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
)
from quant.run_phase_1_1_market_regime_filter_refinement import (  # noqa: E402
    _load_ihsg_indicator_master,
)
from quant.run_phase_1_2_market_regime_alignment_confirmation import (  # noqa: E402
    AlignmentPolicy,
    _apply_alignment_policy,
    _build_policy_registry,
)
from quant.run_phase_4_position_sizing import (  # noqa: E402
    _apply_position_sizing,
    _attach_entry_context,
    _build_entry_exit_frame,
    _evaluate_variant_ticker,
)
from quant.run_walk_forward_validation import (  # noqa: E402
    _mask_non_tradable_tail_signals,
    _pct_degradation,
    _profit_factor_from_trades,
    _sanitize_for_json,
    _slice_window_frame,
    _summarize_sample_adequacy,
)


SUMMARY_OUTPUT = "layer1_holdout_regime_sensitivity_summary.json"
REPORT_OUTPUT = "layer1_holdout_regime_sensitivity_report.txt"
CLOSEOUT_JSON_OUTPUT = "layer1_holdout_regime_sensitivity_closeout.json"
CLOSEOUT_TXT_OUTPUT = "layer1_holdout_regime_sensitivity_closeout.txt"


@dataclass(frozen=True)
class EvaluationWindow:
    window_id: str
    label: str
    start_date: str
    end_date: str
    role: str


@dataclass(frozen=True)
class Layer1Variant:
    variant_id: str
    label: str
    definition: str
    initial_capital: float
    risk_per_trade_pct: float
    max_position_pct: float
    layer_3_active: bool = False
    position_sizing_active: bool = True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_window_registry() -> List[EvaluationWindow]:
    return [
        EvaluationWindow(
            window_id="in_sample",
            label="In-sample 2019-2021",
            start_date="2019-01-01",
            end_date="2021-12-31",
            role="in_sample",
        ),
        EvaluationWindow(
            window_id="out_of_sample",
            label="Out-of-sample 2022-2023",
            start_date="2022-01-01",
            end_date="2023-12-31",
            role="out_of_sample",
        ),
        EvaluationWindow(
            window_id="final_holdout",
            label="Final holdout 2024-2025",
            start_date="2024-01-01",
            end_date="2025-12-31",
            role="final_holdout",
        ),
    ]


def _build_variant_registry() -> List[Layer1Variant]:
    return [
        Layer1Variant(
            variant_id="current_ema50_above_ema200",
            label="Current regime: IHSG EMA50 > EMA200",
            definition="ihsg_ema50 > ihsg_ema200",
            initial_capital=100_000_000.0,
            risk_per_trade_pct=2.0,
            max_position_pct=10.0,
        ),
        Layer1Variant(
            variant_id="ema50_above_ema200_and_ema50_slope_up",
            label="Current regime + EMA50 slope up",
            definition="ihsg_ema50 > ihsg_ema200 AND ihsg_ema50 > prev_ihsg_ema50",
            initial_capital=100_000_000.0,
            risk_per_trade_pct=2.0,
            max_position_pct=10.0,
        ),
        Layer1Variant(
            variant_id="ema50_above_ema200_buffer_0p5pct",
            label="Current regime + 0.5% buffer",
            definition="ihsg_ema50 > ihsg_ema200 * 1.005",
            initial_capital=100_000_000.0,
            risk_per_trade_pct=2.0,
            max_position_pct=10.0,
        ),
        Layer1Variant(
            variant_id="ema50_above_ema200_and_ema200_slope_up",
            label="Current regime + EMA200 slope up",
            definition="ihsg_ema50 > ihsg_ema200 AND ihsg_ema200 > prev_ihsg_ema200",
            initial_capital=100_000_000.0,
            risk_per_trade_pct=2.0,
            max_position_pct=10.0,
        ),
    ]


def _official_alignment_policy() -> AlignmentPolicy:
    return next(
        policy
        for policy in _build_policy_registry()
        if policy.policy_id == "explicit_previous_trading_day_alignment"
    )


def _build_variant_alignment(
    stock_dates: pd.Series,
    ihsg_indicator_master_file: Path,
    variant: Layer1Variant,
) -> pd.DataFrame:
    ihsg_frame = _load_ihsg_indicator_master(ihsg_indicator_master_file).sort_values("date").reset_index(drop=True)
    ihsg_frame["ihsg_ema50_slope_up"] = (
        ihsg_frame["ihsg_ema50"].gt(ihsg_frame["ihsg_ema50"].shift(1))
        & ihsg_frame["ihsg_ema50"].notna()
        & ihsg_frame["ihsg_ema50"].shift(1).notna()
    ).fillna(False)

    if variant.variant_id == "current_ema50_above_ema200":
        regime = ihsg_frame["ihsg_ema50"].gt(ihsg_frame["ihsg_ema200"])
    elif variant.variant_id == "ema50_above_ema200_and_ema50_slope_up":
        regime = ihsg_frame["ihsg_ema50"].gt(ihsg_frame["ihsg_ema200"]) & ihsg_frame["ihsg_ema50_slope_up"]
    elif variant.variant_id == "ema50_above_ema200_buffer_0p5pct":
        regime = ihsg_frame["ihsg_ema50"].gt(ihsg_frame["ihsg_ema200"] * 1.005)
    elif variant.variant_id == "ema50_above_ema200_and_ema200_slope_up":
        regime = ihsg_frame["ihsg_ema50"].gt(ihsg_frame["ihsg_ema200"]) & ihsg_frame["ihsg_ema200_slope_up"]
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported Layer 1 variant: {variant.variant_id}")

    aligned_source = ihsg_frame.copy()
    aligned_source["candidate_regime_bullish"] = regime.fillna(False).astype(bool)
    aligned = _apply_alignment_policy(stock_dates, aligned_source, _official_alignment_policy())
    return aligned.sort_values("date").reset_index(drop=True)


def _apply_variant(frame: pd.DataFrame, aligned_regime: pd.DataFrame, variant: Layer1Variant) -> pd.DataFrame:
    working = frame.sort_values(["date", "ticker"]).reset_index(drop=True).copy()
    regime_lookup = aligned_regime.set_index("date")["market_regime_bullish"]
    aligned_date_lookup = aligned_regime.set_index("date")["aligned_ihsg_date"]
    working["aligned_ihsg_date"] = working["date"].map(aligned_date_lookup)
    working["market_regime_bullish"] = working["date"].map(regime_lookup).fillna(False).astype(bool)
    working["active_selected"] = working["market_regime_bullish"].astype(bool)
    working["phase_1_signal_layer1"] = (
        working["phase_1_signal_base"].fillna(False).astype(bool)
        & working["market_regime_bullish"].astype(bool)
    )
    working["entry_signal"] = working["phase_1_signal_layer1"].astype(bool)
    working["target_selected_count"] = (
        working.groupby("date")["active_selected"].transform("sum").fillna(0).astype(int)
    )
    working["layer1_variant_id"] = variant.variant_id
    return working


def _evaluate_full_period(
    prepared_frame: pd.DataFrame,
    aligned_regime: pd.DataFrame,
    variant: Layer1Variant,
    *,
    allow_overlap: bool,
) -> Dict[str, object]:
    variant_frame = _apply_variant(prepared_frame, aligned_regime, variant)
    ticker_rows: List[Dict[str, object]] = []
    trade_frames: List[pd.DataFrame] = []

    for ticker, group in variant_frame.groupby("ticker"):
        ticker_row, ticker_trades = _evaluate_variant_ticker(
            ticker,
            group.copy(),
            layer_3_active=variant.layer_3_active,
            allow_overlap=allow_overlap,
        )
        ticker_rows.append(ticker_row)
        if not ticker_trades.empty:
            trade_frames.append(ticker_trades)

    per_ticker_df = pd.DataFrame(ticker_rows)
    trades_df = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    trades_df = _attach_entry_context(variant_frame, trades_df)
    sized_trades_df, sizing_metrics = _apply_position_sizing(trades_df, variant)
    sample_risk, sample_reason, sample_detail = _summarize_sample_adequacy(variant_frame, per_ticker_df)

    return {
        "variant_id": variant.variant_id,
        "variant_label": variant.label,
        "definition": variant.definition,
        "alignment_policy": "explicit_previous_trading_day_alignment",
        "bullish_day_pct": round(float(aligned_regime["market_regime_bullish"].mean() * 100.0), 4)
        if not aligned_regime.empty
        else 0.0,
        "total_signals": int(variant_frame["entry_signal"].fillna(False).astype(bool).sum()),
        "total_trades": int(len(sized_trades_df)),
        "win_rate": round(float(sized_trades_df["is_win"].mean() * 100.0), 4) if not sized_trades_df.empty else 0.0,
        "average_return_per_trade": round(float(sized_trades_df["return_pct"].mean()), 4)
        if not sized_trades_df.empty
        else 0.0,
        "max_drawdown_pct": sizing_metrics["portfolio_max_drawdown_pct"],
        "profit_factor": _profit_factor_from_trades(sized_trades_df),
        "portfolio_return_pct": sizing_metrics["portfolio_return_pct"],
        "portfolio_ending_value": sizing_metrics["portfolio_ending_value"],
        "sample_adequacy": {
            "risk": sample_risk,
            "reason": sample_reason,
            **sample_detail,
        },
    }


def _evaluate_window(
    prepared_frame: pd.DataFrame,
    aligned_regime: pd.DataFrame,
    variant: Layer1Variant,
    window: EvaluationWindow,
    *,
    allow_overlap: bool,
) -> Dict[str, object]:
    variant_frame = _apply_variant(prepared_frame, aligned_regime, variant)
    window_frame = _slice_window_frame(variant_frame, window)
    window_alignment = aligned_regime.loc[
        (aligned_regime["date"] >= pd.Timestamp(window.start_date))
        & (aligned_regime["date"] <= pd.Timestamp(window.end_date))
    ].sort_values("date")
    ticker_rows: List[Dict[str, object]] = []
    trade_frames: List[pd.DataFrame] = []

    for ticker, group in window_frame.groupby("ticker"):
        tradable_group = _mask_non_tradable_tail_signals(group.copy())
        ticker_row, ticker_trades = _evaluate_variant_ticker(
            ticker,
            tradable_group,
            layer_3_active=variant.layer_3_active,
            allow_overlap=allow_overlap,
        )
        ticker_rows.append(ticker_row)
        if not ticker_trades.empty:
            trade_frames.append(ticker_trades)

    per_ticker_df = pd.DataFrame(ticker_rows)
    trades_df = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    trades_df = _attach_entry_context(window_frame, trades_df)
    sized_trades_df, sizing_metrics = _apply_position_sizing(trades_df, variant)
    sample_risk, sample_reason, sample_detail = _summarize_sample_adequacy(window_frame, per_ticker_df)
    requested_start = pd.Timestamp(window.start_date)
    requested_end = pd.Timestamp(window.end_date)
    effective_start = window_frame["date"].min() if not window_frame.empty else None
    effective_end = window_frame["date"].max() if not window_frame.empty else None
    first_trade_date = sized_trades_df["entry_date"].min() if not sized_trades_df.empty else None
    last_trade_date = sized_trades_df["exit_date"].max() if not sized_trades_df.empty else None

    return {
        "window_id": window.window_id,
        "window_label": window.label,
        "window_role": window.role,
        "requested_start_date": requested_start.date().isoformat(),
        "requested_end_date": requested_end.date().isoformat(),
        "effective_data_start_date": effective_start.date().isoformat() if effective_start is not None else None,
        "effective_data_end_date": effective_end.date().isoformat() if effective_end is not None else None,
        "first_trade_date": first_trade_date.date().isoformat() if first_trade_date is not None else None,
        "last_trade_date": last_trade_date.date().isoformat() if last_trade_date is not None else None,
        "bullish_day_pct": round(float(window_alignment["market_regime_bullish"].mean() * 100.0), 4)
        if not window_alignment.empty
        else 0.0,
        "total_signals": int(window_frame["entry_signal"].fillna(False).astype(bool).sum()) if not window_frame.empty else 0,
        "total_trades": int(len(sized_trades_df)),
        "win_rate": round(float(sized_trades_df["is_win"].mean() * 100.0), 4) if not sized_trades_df.empty else 0.0,
        "average_return_per_trade": round(float(sized_trades_df["return_pct"].mean()), 4)
        if not sized_trades_df.empty
        else 0.0,
        "max_drawdown_pct": sizing_metrics["portfolio_max_drawdown_pct"],
        "profit_factor": _profit_factor_from_trades(sized_trades_df),
        "portfolio_return_pct": sizing_metrics["portfolio_return_pct"],
        "sample_adequacy": {
            "risk": sample_risk,
            "reason": sample_reason,
            **sample_detail,
        },
    }


def _build_walk_forward_summary(
    prepared_frame: pd.DataFrame,
    aligned_regime: pd.DataFrame,
    variant: Layer1Variant,
    windows: List[EvaluationWindow],
    *,
    allow_overlap: bool,
) -> Dict[str, object]:
    window_results = [
        _evaluate_window(
            prepared_frame,
            aligned_regime,
            variant,
            window,
            allow_overlap=allow_overlap,
        )
        for window in windows
    ]
    lookup = {item["window_id"]: item for item in window_results}
    in_sample = lookup["in_sample"]
    out_of_sample = lookup["out_of_sample"]
    final_holdout = lookup["final_holdout"]
    return {
        "variant_id": variant.variant_id,
        "variant_label": variant.label,
        "definition": variant.definition,
        "window_results": window_results,
        "window_lookup": lookup,
        "oos_degradation_vs_in_sample_pct": _pct_degradation(
            float(in_sample["average_return_per_trade"]),
            float(out_of_sample["average_return_per_trade"]),
        ),
        "holdout_degradation_vs_in_sample_pct": _pct_degradation(
            float(in_sample["average_return_per_trade"]),
            float(final_holdout["average_return_per_trade"]),
        ),
    }


def _variant_sort_key(candidate_wf: Dict[str, object]) -> tuple[float, float, float, float, float]:
    holdout = candidate_wf["window_lookup"]["final_holdout"]
    oos = candidate_wf["window_lookup"]["out_of_sample"]
    return (
        float(holdout["average_return_per_trade"]),
        float(holdout["profit_factor"] or 0.0),
        -float(holdout["max_drawdown_pct"]),
        float(oos["average_return_per_trade"]),
        -float(candidate_wf["oos_degradation_vs_in_sample_pct"] or 1e12),
    )


def _compare_vs_current(
    full_period_results: Dict[str, Dict[str, object]],
    walk_forward_results: Dict[str, Dict[str, object]],
) -> Dict[str, object]:
    control_id = "current_ema50_above_ema200"
    control_wf = walk_forward_results[control_id]
    control_holdout = control_wf["window_lookup"]["final_holdout"]
    control_oos = control_wf["window_lookup"]["out_of_sample"]

    candidate_ids = [variant_id for variant_id in walk_forward_results if variant_id != control_id]
    best_candidate_id = max(candidate_ids, key=lambda variant_id: _variant_sort_key(walk_forward_results[variant_id]))
    best_candidate_wf = walk_forward_results[best_candidate_id]
    best_candidate_full = full_period_results[best_candidate_id]
    best_candidate_holdout = best_candidate_wf["window_lookup"]["final_holdout"]
    best_candidate_oos = best_candidate_wf["window_lookup"]["out_of_sample"]

    candidate_wins = {
        "holdout_average_return_better": float(best_candidate_holdout["average_return_per_trade"])
        > float(control_holdout["average_return_per_trade"]),
        "holdout_profit_factor_better": float(best_candidate_holdout["profit_factor"] or 0.0)
        > float(control_holdout["profit_factor"] or 0.0),
        "holdout_drawdown_lower": float(best_candidate_holdout["max_drawdown_pct"])
        < float(control_holdout["max_drawdown_pct"]),
        "oos_average_return_not_materially_worse": float(best_candidate_oos["average_return_per_trade"])
        >= float(control_oos["average_return_per_trade"]) - 0.15,
        "oos_degradation_lower": float(best_candidate_wf["oos_degradation_vs_in_sample_pct"] or 1e12)
        < float(control_wf["oos_degradation_vs_in_sample_pct"] or 1e12),
    }
    candidate_win_count = int(sum(bool(value) for value in candidate_wins.values()))
    candidate_sample_usable = (
        str(best_candidate_oos["sample_adequacy"]["risk"]) != "high"
        and str(best_candidate_holdout["sample_adequacy"]["risk"]) != "high"
    )
    provisional_revision = bool(
        candidate_wins["holdout_average_return_better"]
        and candidate_wins["holdout_profit_factor_better"]
        and candidate_win_count >= 3
        and candidate_sample_usable
    )

    if provisional_revision:
        revision_decision = "provisionally_revise_layer1_regime"
        reason = (
            "Varian Layer 1 terbaik mengalahkan current regime pada average return dan profit factor holdout tanpa merusak OOS secara material, sehingga revisi Layer 1 layak dibuka secara provisional."
        )
        next_action = "prepare_provisional_layer1_regime_update"
        next_note = "Sinkronkan core stack provisional dengan varian Layer 1 baru lalu tutup pass regime sensitivity ini secara formal."
    else:
        revision_decision = "keep_current_layer1_regime"
        reason = (
            "Tidak ada varian Layer 1 yang cukup tegas memperbaiki holdout resilience versus current regime, sehingga Layer 1 tetap dipertahankan dan residual weakness bergeser ke exit/drawdown behaviour."
        )
        next_action = "open_layer5_drawdown_control_planning"
        next_note = "Karena refinement Layer 1 tidak memberi perbaikan holdout yang cukup tegas, scope berikutnya dibatasi ke Layer 5/drawdown control planning."

    return {
        "best_holdout_variant_id": best_candidate_id,
        "best_holdout_variant_label": best_candidate_full["variant_label"],
        "best_holdout_variant_definition": best_candidate_full["definition"],
        "candidate_more_holdout_resilient_than_current": provisional_revision,
        "candidate_win_count_across_holdout_metrics": candidate_win_count,
        "candidate_wins": candidate_wins,
        "layer1_revision_decision": revision_decision,
        "reason": reason,
        "official_next_action": {
            "action": next_action,
            "note": next_note,
        },
    }


def run_layer1_holdout_regime_sensitivity_validation(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    output_dir: Path,
    allow_overlap: bool = False,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    baseline_payload, baseline_warnings, baseline_source = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    prepared_frame = _build_entry_exit_frame(
        stock_indicator_master_file,
        ihsg_indicator_master_file,
        baseline_payload=baseline_payload,
        metadata_lookup=metadata_lookup,
    )
    prepared_frame["date"] = pd.to_datetime(prepared_frame["date"])
    stock_dates = prepared_frame["date"].drop_duplicates().sort_values().reset_index(drop=True)
    variants = _build_variant_registry()
    windows = _build_window_registry()

    full_period_results: Dict[str, Dict[str, object]] = {}
    walk_forward_results: Dict[str, Dict[str, object]] = {}
    for variant in variants:
        aligned_regime = _build_variant_alignment(stock_dates, ihsg_indicator_master_file, variant)
        full_period_results[variant.variant_id] = _evaluate_full_period(
            prepared_frame,
            aligned_regime,
            variant,
            allow_overlap=allow_overlap,
        )
        walk_forward_results[variant.variant_id] = _build_walk_forward_summary(
            prepared_frame,
            aligned_regime,
            variant,
            windows,
            allow_overlap=allow_overlap,
        )

    comparison_decision = _compare_vs_current(full_period_results, walk_forward_results)
    summary_payload = {
        "phase": "layer1_holdout_regime_sensitivity_validation",
        "status": "completed",
        "generated_at": _now_iso(),
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
            "holdout_resilience_plan": "output/holdout_resilience_plan.json",
            "core_stack_update_closeout": "output/core_stack_update_closeout.json",
            "project_roadmap_status": "output/project_roadmap_status.txt",
        },
        "variants_compared": list(full_period_results.values()),
        "walk_forward_results": list(walk_forward_results.values()),
        "decision": comparison_decision,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_OUTPUT
    report_path = output_dir / REPORT_OUTPUT
    closeout_json_path = output_dir / CLOSEOUT_JSON_OUTPUT
    closeout_txt_path = output_dir / CLOSEOUT_TXT_OUTPUT
    summary_path.write_text(json.dumps(_sanitize_for_json(summary_payload), indent=2), encoding="utf-8")

    report_lines = [
        "Layer 1 Holdout Regime Sensitivity Validation",
        "=============================================",
        "",
        "Variants tested:",
    ]
    for variant in variants:
        full_result = full_period_results[variant.variant_id]
        wf_result = walk_forward_results[variant.variant_id]
        is_window = wf_result["window_lookup"]["in_sample"]
        oos_window = wf_result["window_lookup"]["out_of_sample"]
        holdout_window = wf_result["window_lookup"]["final_holdout"]
        report_lines.extend(
            [
                f"- {variant.variant_id}: {variant.definition}",
                f"  full: trades={full_result['total_trades']}, win_rate={full_result['win_rate']}, avg_return={full_result['average_return_per_trade']}, max_drawdown={full_result['max_drawdown_pct']}, profit_factor={full_result['profit_factor']}, sample={full_result['sample_adequacy']['risk']}",
                f"  in-sample: trades={is_window['total_trades']}, win_rate={is_window['win_rate']}, avg_return={is_window['average_return_per_trade']}, max_drawdown={is_window['max_drawdown_pct']}, profit_factor={is_window['profit_factor']}, sample={is_window['sample_adequacy']['risk']}",
                f"  oos: trades={oos_window['total_trades']}, win_rate={oos_window['win_rate']}, avg_return={oos_window['average_return_per_trade']}, max_drawdown={oos_window['max_drawdown_pct']}, profit_factor={oos_window['profit_factor']}, sample={oos_window['sample_adequacy']['risk']}",
                f"  holdout: trades={holdout_window['total_trades']}, win_rate={holdout_window['win_rate']}, avg_return={holdout_window['average_return_per_trade']}, max_drawdown={holdout_window['max_drawdown_pct']}, profit_factor={holdout_window['profit_factor']}, sample={holdout_window['sample_adequacy']['risk']}",
                f"  oos_degradation={wf_result['oos_degradation_vs_in_sample_pct']}, holdout_degradation={wf_result['holdout_degradation_vs_in_sample_pct']}",
            ]
        )
    report_lines.extend(
        [
            "",
            "Decision:",
            f"- best_holdout_variant = {comparison_decision['best_holdout_variant_id']}",
            f"- candidate_more_holdout_resilient_than_current = {comparison_decision['candidate_more_holdout_resilient_than_current']}",
            f"- layer1_revision_decision = {comparison_decision['layer1_revision_decision']}",
            f"- reason = {comparison_decision['reason']}",
            f"- official_next_action = {comparison_decision['official_next_action']['action']}",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    best_variant_id = comparison_decision["best_holdout_variant_id"]
    closeout_payload = {
        "artifact": "layer1_holdout_regime_sensitivity_closeout",
        "generated_at": datetime.now(timezone.utc).date().isoformat(),
        "source_of_truth": {
            "validation_summary": str(summary_path.relative_to(output_dir.parent)),
            "validation_report": str(report_path.relative_to(output_dir.parent)),
            "holdout_resilience_plan": "output/holdout_resilience_plan.json",
            "core_stack_update_closeout": "output/core_stack_update_closeout.json",
            "project_roadmap_status": "output/project_roadmap_status.txt",
        },
        "current_official_decision": {
            "validation_status": "completed",
            "best_holdout_variant_id": best_variant_id,
            "candidate_more_holdout_resilient_than_current": comparison_decision[
                "candidate_more_holdout_resilient_than_current"
            ],
            "layer1_revision_decision": comparison_decision["layer1_revision_decision"],
            "paper_trading_allowed": False,
            "retest_allowed": False,
            "note": comparison_decision["reason"],
        },
        "comparison_snapshot": {
            "control_full_period": full_period_results["current_ema50_above_ema200"],
            "control_walk_forward": walk_forward_results["current_ema50_above_ema200"],
            "best_variant_full_period": full_period_results[best_variant_id],
            "best_variant_walk_forward": walk_forward_results[best_variant_id],
        },
        "official_next_action": comparison_decision["official_next_action"],
    }
    closeout_json_path.write_text(json.dumps(_sanitize_for_json(closeout_payload), indent=2), encoding="utf-8")

    closeout_lines = [
        "Layer 1 Holdout Regime Sensitivity Closeout",
        "===========================================",
        "",
        "Current official decision:",
        f"- best_holdout_variant = {comparison_decision['best_holdout_variant_id']}",
        f"- candidate_more_holdout_resilient_than_current = {comparison_decision['candidate_more_holdout_resilient_than_current']}",
        f"- layer1_revision_decision = {comparison_decision['layer1_revision_decision']}",
        f"- note = {comparison_decision['reason']}",
        "- paper trading tetap tertutup",
        "- retest tetap tertutup",
        "",
        "Official next action:",
        f"- {comparison_decision['official_next_action']['action']}",
    ]
    closeout_txt_path.write_text("\n".join(closeout_lines) + "\n", encoding="utf-8")

    return {
        "summary_path": summary_path,
        "report_path": report_path,
        "closeout_json_path": closeout_json_path,
        "closeout_txt_path": closeout_txt_path,
        "summary": summary_payload,
        "closeout": closeout_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate narrow Layer 1 market regime refinements for holdout resilience."
    )
    parser.add_argument(
        "--stock-indicator-master-file",
        default="data/indicator_master/stock_indicator_master.csv",
        help="Stock indicator master CSV for the rebuild universe.",
    )
    parser.add_argument(
        "--ihsg-indicator-master-file",
        default="data/indicator_master/IHSG_indicator_master.csv",
        help="IHSG indicator master CSV for Layer 1 regime evaluation.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory for summary, report, and closeout artifacts.",
    )
    parser.add_argument(
        "--allow-overlap",
        action="store_true",
        help="Allow overlapping ATR-trailing-stop trades.",
    )
    parser.add_argument(
        "--baseline-config",
        default=None,
        help="Optional Phase A baseline JSON override.",
    )
    parser.add_argument(
        "--metadata-file",
        default=None,
        help="Optional ticker metadata CSV override.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    result = run_layer1_holdout_regime_sensitivity_validation(
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        output_dir=Path(args.output_dir),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    print(f"Summary written to {result['summary_path']}")
    print(f"Report written to {result['report_path']}")
    print(f"Closeout JSON written to {result['closeout_json_path']}")
    print(f"Closeout TXT written to {result['closeout_txt_path']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
