"""Run the locked single-variable Layer 2 confirmation-days experiment across all approved values."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

if __package__ is None or __package__ == "":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.run_walk_forward_validation import run_walk_forward_validation  # noqa: E402


SUMMARY_OUTPUT = "single_variable_experiment_results_v2.json"
REPORT_OUTPUT = "single_variable_experiment_results_v2.txt"

LOCKED_CONFIRMATION_DAYS = [0, 1, 2, 3]
PREFERRED_STACK_ID = "rebuild_core_without_layer3"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_stack(summary: Dict[str, object], stack_id: str) -> Dict[str, object]:
    for item in list(summary.get("stack_results") or []):
        if str(item.get("stack_id")) == stack_id:
            return item
    raise ValueError(f"Stack {stack_id} not found in summary.")


def _passes_minimum_criteria(
    result_row: Dict[str, object],
    criteria: Dict[str, object],
    baseline_holdout_avg_return: float,
) -> bool:
    return bool(
        float(result_row["oos_avg_return_per_trade"]) > float(criteria["oos_avg_return_per_trade_gt"])
        and float(result_row["oos_max_drawdown_pct"]) < float(criteria["oos_max_drawdown_pct_lt"])
        and float(result_row["holdout_avg_return_per_trade"]) >= float(criteria["holdout_avg_return_per_trade_floor"])
        and int(result_row["trade_count"]) >= int(criteria["trade_count_floor"])
        and (
            not bool(criteria["no_worse_than_current_holdout"])
            or float(result_row["holdout_avg_return_per_trade"]) >= float(baseline_holdout_avg_return)
        )
    )


def _winner_sort_key(result_row: Dict[str, object]) -> tuple[float, float, float]:
    return (
        float(result_row["oos_avg_return_per_trade"]),
        -float(result_row["oos_max_drawdown_pct"]),
        float(result_row["holdout_avg_return_per_trade"]),
    )


def run_single_variable_confirmation_days_experiment(
    *,
    output_dir: Path,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    baseline_config: Optional[Path],
    metadata_file: Optional[Path],
    broker_fee_bps: float,
    slippage_bps: float,
    baseline_reference: Path,
    hypothesis_reference: Path,
    spec_reference: Path,
) -> Dict[str, object]:
    baseline_summary = _read_json(baseline_reference)
    hypothesis_payload = _read_json(hypothesis_reference)
    spec_payload = _read_json(spec_reference)
    minimum_pass_criteria = dict(hypothesis_payload["minimum_pass_criteria"])
    baseline_windows = dict(baseline_summary["before_vs_after_by_window"])
    baseline_holdout_avg_return = float(baseline_windows["final_holdout"]["average_return_per_trade_after_costs"])

    experiment_run_root = output_dir / "single_variable_experiment_runs_v2"
    experiment_run_root.mkdir(parents=True, exist_ok=True)

    results_by_variant: List[Dict[str, object]] = []
    for confirmation_days in LOCKED_CONFIRMATION_DAYS:
        variant_dir = experiment_run_root / f"confirmation_days_{int(confirmation_days)}"
        run_result = run_walk_forward_validation(
            stock_indicator_master_file=stock_indicator_master_file,
            ihsg_indicator_master_file=ihsg_indicator_master_file,
            output_dir=variant_dir,
            baseline_config=baseline_config,
            metadata_file=metadata_file,
            broker_fee_bps=float(broker_fee_bps),
            slippage_bps=float(slippage_bps),
            layer2_momentum_floor_on_return_20d=0.0,
            layer2_confirmation_days=int(confirmation_days),
        )
        stack_result = _find_stack(run_result["summary"], PREFERRED_STACK_ID)
        windows = dict(stack_result["window_lookup"])
        result_row = {
            "confirmation_days": int(confirmation_days),
            "in_sample_avg_return_per_trade": float(windows["in_sample"]["average_return_per_trade"]),
            "oos_avg_return_per_trade": float(windows["out_of_sample"]["average_return_per_trade"]),
            "holdout_avg_return_per_trade": float(windows["final_holdout"]["average_return_per_trade"]),
            "oos_max_drawdown_pct": float(windows["out_of_sample"]["max_drawdown_pct"]),
            "holdout_max_drawdown_pct": float(windows["final_holdout"]["max_drawdown_pct"]),
            "trade_count": int(windows["final_holdout"]["total_trades"]),
        }
        result_row["passes_minimum_criteria"] = _passes_minimum_criteria(
            result_row,
            minimum_pass_criteria,
            baseline_holdout_avg_return,
        )
        result_row["assessment_note"] = (
            "Passes all locked minimum criteria against the current frozen-stack baseline."
            if result_row["passes_minimum_criteria"]
            else "Fails at least one locked minimum criterion; no escape clause, range expansion, or second variable allowed."
        )
        result_row["baseline_comparison"] = {
            "oos_avg_return_per_trade_before": float(baseline_windows["out_of_sample"]["average_return_per_trade_after_costs"]),
            "oos_avg_return_per_trade_after": float(result_row["oos_avg_return_per_trade"]),
            "holdout_avg_return_per_trade_before": float(baseline_windows["final_holdout"]["average_return_per_trade_after_costs"]),
            "holdout_avg_return_per_trade_after": float(result_row["holdout_avg_return_per_trade"]),
            "oos_max_drawdown_pct_before": float(baseline_windows["out_of_sample"]["max_drawdown_pct_after_costs"]),
            "oos_max_drawdown_pct_after": float(result_row["oos_max_drawdown_pct"]),
            "holdout_max_drawdown_pct_before": float(baseline_windows["final_holdout"]["max_drawdown_pct_after_costs"]),
            "holdout_max_drawdown_pct_after": float(result_row["holdout_max_drawdown_pct"]),
            "trade_count_before": int(baseline_windows["final_holdout"]["trade_count_after_costs"]),
            "trade_count_after": int(result_row["trade_count"]),
        }
        results_by_variant.append(result_row)

    passing_variants = [item for item in results_by_variant if bool(item["passes_minimum_criteria"])]
    if passing_variants:
        winner = max(passing_variants, key=_winner_sort_key)
        winner_variant: Optional[int] = int(winner["confirmation_days"])
        winner_selection_basis = (
            "passed_locked_minimum_criteria_then_ranked_by_higher_oos_avg_return_per_trade_"
            "with_no_unnecessary_drawdown_penalty_and_no_worse_than_current_holdout"
        )
        hypothesis_result = "hypothesis_supported"
        hypothesis_result_reason = (
            f"At least one approved confirmation-days setting passed the locked criteria; confirmation_days="
            f"{winner_variant} is the most defensible passing variant after comparing all four approved values."
        )
    else:
        winner_variant = None
        winner_selection_basis = "no_variant_passed_locked_minimum_criteria"
        hypothesis_result = "hypothesis_rejected"
        hypothesis_result_reason = (
            "None of the four approved confirmation-days values passed the locked minimum criteria, so the hypothesis "
            "is rejected without expanding the range, loosening pass criteria, or adding a second variable."
        )

    summary_payload = {
        "artifact": "single_variable_experiment_results_v2",
        "generated_at": _now_iso(),
        "experiment_scope": str(spec_payload["experiment_scope"]),
        "single_variable_name": str(spec_payload["single_variable_name"]),
        "baseline_reference": str(baseline_reference),
        "tested_variants": [int(value) for value in LOCKED_CONFIRMATION_DAYS],
        "results_by_variant": results_by_variant,
        "minimum_pass_criteria": minimum_pass_criteria,
        "winner_variant": winner_variant,
        "winner_selection_basis": winner_selection_basis,
        "hypothesis_result": hypothesis_result,
        "hypothesis_result_reason": hypothesis_result_reason,
        "no_range_expansion_performed": True,
        "stack_changed": False,
        "retest_status": "blocked",
        "paper_trading_status": "blocked",
        "next_action": "review_single_variable_experiment_result_v2_against_locked_criteria_before_any_further_strategy_change",
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_OUTPUT
    report_path = output_dir / REPORT_OUTPUT
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Single Variable Layer 2 Confirmation-Days Experiment Results",
        "============================================================",
        "",
        f"- experiment_scope = {summary_payload['experiment_scope']}",
        f"- single_variable_name = {summary_payload['single_variable_name']}",
        f"- baseline_reference = {summary_payload['baseline_reference']}",
        f"- tested_variants = {summary_payload['tested_variants']}",
        "",
        "Locked minimum pass criteria:",
        f"- oos_avg_return_per_trade_gt = {minimum_pass_criteria['oos_avg_return_per_trade_gt']}",
        f"- oos_max_drawdown_pct_lt = {minimum_pass_criteria['oos_max_drawdown_pct_lt']}",
        f"- holdout_avg_return_per_trade_floor = {minimum_pass_criteria['holdout_avg_return_per_trade_floor']}",
        f"- trade_count_floor = {minimum_pass_criteria['trade_count_floor']}",
        f"- no_worse_than_current_holdout = {minimum_pass_criteria['no_worse_than_current_holdout']}",
        "",
    ]
    for row in results_by_variant:
        report_lines.extend(
            [
                f"Variant confirmation_days {int(row['confirmation_days'])}",
                f"- passes_minimum_criteria = {row['passes_minimum_criteria']}",
                f"- in_sample_avg_return_per_trade = {row['in_sample_avg_return_per_trade']}",
                f"- oos_avg_return_per_trade = {row['oos_avg_return_per_trade']} "
                f"(baseline {row['baseline_comparison']['oos_avg_return_per_trade_before']})",
                f"- holdout_avg_return_per_trade = {row['holdout_avg_return_per_trade']} "
                f"(baseline {row['baseline_comparison']['holdout_avg_return_per_trade_before']})",
                f"- oos_max_drawdown_pct = {row['oos_max_drawdown_pct']} "
                f"(baseline {row['baseline_comparison']['oos_max_drawdown_pct_before']})",
                f"- holdout_max_drawdown_pct = {row['holdout_max_drawdown_pct']} "
                f"(baseline {row['baseline_comparison']['holdout_max_drawdown_pct_before']})",
                f"- trade_count = {row['trade_count']} "
                f"(baseline {row['baseline_comparison']['trade_count_before']})",
                f"- assessment_note = {row['assessment_note']}",
                "",
            ]
        )
    report_lines.extend(
        [
            f"- winner_variant = {summary_payload['winner_variant']}",
            f"- winner_selection_basis = {summary_payload['winner_selection_basis']}",
            f"- hypothesis_result = {summary_payload['hypothesis_result']}",
            f"- hypothesis_result_reason = {summary_payload['hypothesis_result_reason']}",
            f"- no_range_expansion_performed = {summary_payload['no_range_expansion_performed']}",
            f"- stack_changed = {summary_payload['stack_changed']}",
            f"- retest_status = {summary_payload['retest_status']}",
            f"- paper_trading_status = {summary_payload['paper_trading_status']}",
            f"- next_action = {summary_payload['next_action']}",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "summary_path": summary_path,
        "report_path": report_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the locked single-variable Layer 2 confirmation-days experiment.")
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
    parser.add_argument(
        "--broker-fee-bps",
        type=float,
        default=10.0,
        help="Per-side broker fee in basis points applied to each realized trade.",
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=5.0,
        help="Per-side slippage in basis points applied to each realized trade.",
    )
    parser.add_argument(
        "--baseline-reference",
        default="output/walk_forward_with_costs_summary.json",
        help="Baseline reference artifact for the current frozen stack after costs.",
    )
    parser.add_argument(
        "--hypothesis-reference",
        default="output/one_small_controlled_strategy_hypothesis_v2.json",
        help="Locked hypothesis v2 artifact path.",
    )
    parser.add_argument(
        "--spec-reference",
        default="output/single_variable_experiment_spec_v2.json",
        help="Locked experiment v2 spec artifact path.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    run_single_variable_confirmation_days_experiment(
        output_dir=Path(args.output_dir),
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        broker_fee_bps=float(args.broker_fee_bps),
        slippage_bps=float(args.slippage_bps),
        baseline_reference=Path(args.baseline_reference),
        hypothesis_reference=Path(args.hypothesis_reference),
        spec_reference=Path(args.spec_reference),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
