"""Evaluate the second entry simplification cycle against the current control stack."""

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


SUMMARY_OUTPUT = "entry_simplification_cycle_2_summary.json"
REPORT_OUTPUT = "entry_simplification_cycle_2_report.txt"
CLOSEOUT_JSON_OUTPUT = "entry_simplification_cycle_2_closeout.json"
CLOSEOUT_TXT_OUTPUT = "entry_simplification_cycle_2_closeout.txt"


@dataclass(frozen=True)
class EvaluationWindow:
    window_id: str
    label: str
    start_date: str
    end_date: str
    role: str


@dataclass(frozen=True)
class EntryVariant:
    variant_id: str
    label: str
    entry_policy: str
    layer_3_active: bool
    position_sizing_active: bool
    risk_per_trade_pct: float
    max_position_pct: float
    initial_capital: float


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


def _build_variant_registry() -> List[EntryVariant]:
    return [
        EntryVariant(
            variant_id="control_phase1_layer1_plus_return20d_positive",
            label="Control: Phase 1 base signal generation + Layer 1 + return_20d > 0 + ATR trailing stop + sizing",
            entry_policy="control_return20d_positive",
            layer_3_active=False,
            position_sizing_active=True,
            risk_per_trade_pct=2.0,
            max_position_pct=10.0,
            initial_capital=100_000_000.0,
        ),
        EntryVariant(
            variant_id="candidate_phase1_plus_layer1_only",
            label="Candidate: Phase 1 base signal generation + Layer 1 only + ATR trailing stop + sizing",
            entry_policy="phase1_plus_layer1_only",
            layer_3_active=False,
            position_sizing_active=True,
            risk_per_trade_pct=2.0,
            max_position_pct=10.0,
            initial_capital=100_000_000.0,
        ),
    ]


def _apply_entry_policy(frame: pd.DataFrame, variant: EntryVariant) -> pd.DataFrame:
    working = frame.sort_values(["date", "ticker"]).reset_index(drop=True).copy()
    if variant.entry_policy == "control_return20d_positive":
        working["active_selected"] = (
            working["market_regime_bullish"].astype(bool)
            & working["alt_data_ready"].astype(bool)
            & working["alt_momentum_positive"].astype(bool)
        )
        working["entry_signal"] = (
            working["phase_1_signal_layer1"].astype(bool)
            & working["alt_data_ready"].astype(bool)
            & working["alt_momentum_positive"].astype(bool)
        )
    elif variant.entry_policy == "phase1_plus_layer1_only":
        working["active_selected"] = working["market_regime_bullish"].astype(bool)
        working["entry_signal"] = working["phase_1_signal_layer1"].astype(bool)
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported entry policy: {variant.entry_policy}")
    working["target_selected_count"] = (
        working.groupby("date")["active_selected"].transform("sum").fillna(0).astype(int)
    )
    return working


def _evaluate_full_period(
    prepared_frame: pd.DataFrame,
    variant: EntryVariant,
    *,
    allow_overlap: bool,
) -> Dict[str, object]:
    variant_frame = _apply_entry_policy(prepared_frame, variant)
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
        "entry_policy": variant.entry_policy,
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
    variant: EntryVariant,
    window: EvaluationWindow,
    *,
    allow_overlap: bool,
) -> Dict[str, object]:
    variant_frame = _apply_entry_policy(prepared_frame, variant)
    window_frame = _slice_window_frame(variant_frame, window)
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
    variant: EntryVariant,
    windows: List[EvaluationWindow],
    *,
    allow_overlap: bool,
) -> Dict[str, object]:
    window_results = [
        _evaluate_window(
            prepared_frame,
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


def _compare_candidate_vs_control(
    full_period_results: Dict[str, Dict[str, object]],
    walk_forward_results: Dict[str, Dict[str, object]],
) -> Dict[str, object]:
    control_full = full_period_results["control_phase1_layer1_plus_return20d_positive"]
    candidate_full = full_period_results["candidate_phase1_plus_layer1_only"]
    control_wf = walk_forward_results["control_phase1_layer1_plus_return20d_positive"]
    candidate_wf = walk_forward_results["candidate_phase1_plus_layer1_only"]

    control_oos = control_wf["window_lookup"]["out_of_sample"]
    candidate_oos = candidate_wf["window_lookup"]["out_of_sample"]
    control_holdout = control_wf["window_lookup"]["final_holdout"]
    candidate_holdout = candidate_wf["window_lookup"]["final_holdout"]

    candidate_wins = {
        "oos_average_return_better": float(candidate_oos["average_return_per_trade"])
        > float(control_oos["average_return_per_trade"]),
        "holdout_average_return_better": float(candidate_holdout["average_return_per_trade"])
        > float(control_holdout["average_return_per_trade"]),
        "oos_profit_factor_better": float(candidate_oos["profit_factor"] or 0.0) > float(control_oos["profit_factor"] or 0.0),
        "holdout_profit_factor_better": float(candidate_holdout["profit_factor"] or 0.0)
        > float(control_holdout["profit_factor"] or 0.0),
        "oos_degradation_lower": float(candidate_wf["oos_degradation_vs_in_sample_pct"] or 1e12)
        < float(control_wf["oos_degradation_vs_in_sample_pct"] or 1e12),
    }
    candidate_win_count = int(sum(bool(value) for value in candidate_wins.values()))
    candidate_better_in_oos = bool(
        candidate_win_count >= 3
        and str(candidate_oos["sample_adequacy"]["risk"]) != "high"
        and str(candidate_holdout["sample_adequacy"]["risk"]) != "high"
    )

    drop_return20d = bool(
        candidate_better_in_oos
        and float(candidate_full["average_return_per_trade"]) >= float(control_full["average_return_per_trade"]) - 0.35
    )
    drop_decision = (
        "provisionally_drop_from_core_stack"
        if drop_return20d
        else "not_yet_keep_under_review"
    )
    reason = (
        "Candidate baru menunjukkan ketahanan OOS/holdout yang lebih baik secara mayoritas metrik utama, sehingga `return_20d > 0` layak dibuang dari stack inti secara provisional."
        if drop_return20d
        else "Candidate baru belum cukup tegas mengalahkan control di OOS/holdout, sehingga `return_20d > 0` belum resmi dibuang dari stack inti."
    )
    return {
        "candidate_more_oos_resilient_than_control": candidate_better_in_oos,
        "candidate_win_count_across_key_oos_metrics": candidate_win_count,
        "candidate_wins": candidate_wins,
        "return20d_positive_drop_decision": drop_decision,
        "reason": reason,
    }


def run_entry_simplification_cycle_2_validation(
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
    variants = _build_variant_registry()
    windows = _build_window_registry()

    full_period_results: Dict[str, Dict[str, object]] = {}
    walk_forward_results: Dict[str, Dict[str, object]] = {}
    for variant in variants:
        full_period_results[variant.variant_id] = _evaluate_full_period(
            prepared_frame,
            variant,
            allow_overlap=allow_overlap,
        )
        walk_forward_results[variant.variant_id] = _build_walk_forward_summary(
            prepared_frame,
            variant,
            windows,
            allow_overlap=allow_overlap,
        )

    comparison_decision = _compare_candidate_vs_control(full_period_results, walk_forward_results)
    summary_payload = {
        "phase": "entry_simplification_cycle_2_validation",
        "status": "completed",
        "generated_at": _now_iso(),
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
            "effective_constraint_audit": "output/entry_effective_constraint_audit.json",
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

    control_full = full_period_results["control_phase1_layer1_plus_return20d_positive"]
    candidate_full = full_period_results["candidate_phase1_plus_layer1_only"]
    control_wf = walk_forward_results["control_phase1_layer1_plus_return20d_positive"]
    candidate_wf = walk_forward_results["candidate_phase1_plus_layer1_only"]
    control_oos = control_wf["window_lookup"]["out_of_sample"]
    candidate_oos = candidate_wf["window_lookup"]["out_of_sample"]
    control_holdout = control_wf["window_lookup"]["final_holdout"]
    candidate_holdout = candidate_wf["window_lookup"]["final_holdout"]

    report_lines = [
        "Entry Simplification Cycle 2 Validation",
        "=======================================",
        "",
        "Full-period integration comparison:",
        f"- control: trades={control_full['total_trades']}, win_rate={control_full['win_rate']}, avg_return={control_full['average_return_per_trade']}, max_drawdown={control_full['max_drawdown_pct']}, profit_factor={control_full['profit_factor']}, sample={control_full['sample_adequacy']['risk']}",
        f"- candidate: trades={candidate_full['total_trades']}, win_rate={candidate_full['win_rate']}, avg_return={candidate_full['average_return_per_trade']}, max_drawdown={candidate_full['max_drawdown_pct']}, profit_factor={candidate_full['profit_factor']}, sample={candidate_full['sample_adequacy']['risk']}",
        "",
        "Walk-forward comparison:",
        f"- control OOS: trades={control_oos['total_trades']}, win_rate={control_oos['win_rate']}, avg_return={control_oos['average_return_per_trade']}, max_drawdown={control_oos['max_drawdown_pct']}, profit_factor={control_oos['profit_factor']}, sample={control_oos['sample_adequacy']['risk']}",
        f"- candidate OOS: trades={candidate_oos['total_trades']}, win_rate={candidate_oos['win_rate']}, avg_return={candidate_oos['average_return_per_trade']}, max_drawdown={candidate_oos['max_drawdown_pct']}, profit_factor={candidate_oos['profit_factor']}, sample={candidate_oos['sample_adequacy']['risk']}",
        f"- control holdout: trades={control_holdout['total_trades']}, win_rate={control_holdout['win_rate']}, avg_return={control_holdout['average_return_per_trade']}, max_drawdown={control_holdout['max_drawdown_pct']}, profit_factor={control_holdout['profit_factor']}, sample={control_holdout['sample_adequacy']['risk']}",
        f"- candidate holdout: trades={candidate_holdout['total_trades']}, win_rate={candidate_holdout['win_rate']}, avg_return={candidate_holdout['average_return_per_trade']}, max_drawdown={candidate_holdout['max_drawdown_pct']}, profit_factor={candidate_holdout['profit_factor']}, sample={candidate_holdout['sample_adequacy']['risk']}",
        f"- control oos_degradation = {control_wf['oos_degradation_vs_in_sample_pct']}",
        f"- candidate oos_degradation = {candidate_wf['oos_degradation_vs_in_sample_pct']}",
        "",
        "Decision:",
        f"- candidate_more_oos_resilient_than_control = {comparison_decision['candidate_more_oos_resilient_than_control']}",
        f"- return20d_positive_drop_decision = {comparison_decision['return20d_positive_drop_decision']}",
        f"- reason = {comparison_decision['reason']}",
    ]
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    closeout_payload = {
        "artifact": "entry_simplification_cycle_2_closeout",
        "generated_at": datetime.now(timezone.utc).date().isoformat(),
        "source_of_truth": {
            "cycle_2_summary": str(summary_path.relative_to(output_dir.parent)),
            "cycle_2_report": str(report_path.relative_to(output_dir.parent)),
            "effective_constraint_audit": "output/entry_effective_constraint_audit.json",
            "project_roadmap_status": "output/project_roadmap_status.txt",
        },
        "current_official_decision": {
            "candidate_validation_status": "completed",
            "candidate_more_oos_resilient_than_control": comparison_decision["candidate_more_oos_resilient_than_control"],
            "return20d_positive_removed_from_core_stack": comparison_decision["return20d_positive_drop_decision"]
            == "provisionally_drop_from_core_stack",
            "drop_decision": comparison_decision["return20d_positive_drop_decision"],
            "paper_trading_allowed": False,
            "retest_allowed": False,
            "note": comparison_decision["reason"],
        },
        "comparison_snapshot": {
            "control_full_period": control_full,
            "candidate_full_period": candidate_full,
            "control_out_of_sample": control_oos,
            "candidate_out_of_sample": candidate_oos,
            "control_holdout": control_holdout,
            "candidate_holdout": candidate_holdout,
            "control_oos_degradation_vs_in_sample_pct": control_wf["oos_degradation_vs_in_sample_pct"],
            "candidate_oos_degradation_vs_in_sample_pct": candidate_wf["oos_degradation_vs_in_sample_pct"],
        },
        "official_next_action": {
            "action": (
                "prepare_core_stack_update_without_return20d_positive"
                if comparison_decision["return20d_positive_drop_decision"] == "provisionally_drop_from_core_stack"
                else "open_more_fundamental_entry_redesign_planning"
            ),
            "note": (
                "Candidate cycle 2 beat control enough to justify provisional removal of `return_20d > 0`."
                if comparison_decision["return20d_positive_drop_decision"] == "provisionally_drop_from_core_stack"
                else "Cycle 2 did not justify dropping `return_20d > 0`; entry redesign now needs a more fundamental planning pass."
            ),
        },
    }
    closeout_json_path.write_text(json.dumps(_sanitize_for_json(closeout_payload), indent=2), encoding="utf-8")

    closeout_lines = [
        "Entry Simplification Cycle 2 Closeout",
        "=====================================",
        "",
        "Current official decision:",
        f"- candidate_more_oos_resilient_than_control = {comparison_decision['candidate_more_oos_resilient_than_control']}",
        f"- return20d_positive_drop_decision = {comparison_decision['return20d_positive_drop_decision']}",
        f"- note = {comparison_decision['reason']}",
        "- paper trading tetap tertutup",
        "- retest tetap tertutup",
        "",
        "Official next action:",
        f"- {closeout_payload['official_next_action']['action']}",
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
    parser = argparse.ArgumentParser(description="Validate the second entry simplification cycle versus the current control.")
    parser.add_argument(
        "--stock-indicator-master-file",
        default="data/indicator_master/stock_indicator_master.csv",
        help="Stock indicator master CSV for the rebuild universe.",
    )
    parser.add_argument(
        "--ihsg-indicator-master-file",
        default="data/indicator_master/IHSG_indicator_master.csv",
        help="IHSG indicator master CSV for Layer 1 regime alignment.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for output artifacts.")
    parser.add_argument("--allow-overlap", action="store_true", help="Allow overlapping trades.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Frozen Phase A baseline config path.",
    )
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional metadata file for baseline runtime overrides.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    run_entry_simplification_cycle_2_validation(
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        output_dir=Path(args.output_dir),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
