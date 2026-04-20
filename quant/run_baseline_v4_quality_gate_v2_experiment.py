"""Run the second baseline v4 quality-gate iteration with slightly looser gates."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Optional, Sequence

import pandas as pd

from quant.run_baseline_v4_quality_gate_experiment import (
    BaselineV4QualityGateCliError,
    SCAFFOLD_COLUMNS,
    _load_v4_context,
    _now_iso,
    _safe_float,
    _safe_int,
    _safe_str,
    _write_json,
    _write_text,
    build_summary,
    build_summary_payload,
    determine_go_no_go,
    evaluate_v4_quality_gate_matrix,
)
from quant.phase_a_baseline import (
    load_optional_metadata_lookup,
    load_phase_a_baseline,
)
from quant.phase_a_transition_utils import dedupe


def _build_v2_scaffold_matrix(hold_period: int, min_trades: int) -> pd.DataFrame:
    rows = [
        {
            "candidate_id": "baseline_v4_quality_gate_v2_body_relaxed",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "body_strength_floor_relaxed",
            "gate_summary": "Relax body and close strength slightly while keeping a meaningful range floor.",
            "min_body_to_range_ratio": 0.50,
            "min_close_vs_open_pct": 0.25,
            "min_range_pct": 0.75,
            "min_close_vs_anchor_pct": 0.00,
            "hold_period": int(hold_period),
            "min_trades_threshold": int(min_trades),
            "status": "scaffold_only",
        },
        {
            "candidate_id": "baseline_v4_quality_gate_v2_anchor_micro_confirm",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "body_strength_relaxed_plus_micro_anchor_confirm",
            "gate_summary": "Allow a softer candle body but keep a small distance above EMA20 to avoid weak closes.",
            "min_body_to_range_ratio": 0.48,
            "min_close_vs_open_pct": 0.22,
            "min_range_pct": 0.70,
            "min_close_vs_anchor_pct": 0.02,
            "hold_period": int(hold_period),
            "min_trades_threshold": int(min_trades),
            "status": "scaffold_only",
        },
        {
            "candidate_id": "baseline_v4_quality_gate_v2_coverage_push",
            "entry_anchor_rule": "close_gt_ema20_and_bullish_candle",
            "quality_gate_id": "coverage_push_with_guardrails",
            "gate_summary": "Push for one more eligible ticker by relaxing body/range modestly without dropping the bullish-candle anchor.",
            "min_body_to_range_ratio": 0.47,
            "min_close_vs_open_pct": 0.18,
            "min_range_pct": 0.65,
            "min_close_vs_anchor_pct": 0.00,
            "hold_period": int(hold_period),
            "min_trades_threshold": int(min_trades),
            "status": "scaffold_only",
        },
    ]
    return pd.DataFrame(rows).reindex(columns=SCAFFOLD_COLUMNS)


def _load_v2_scaffold_matrix(output_dir: Path, hold_period: int, min_trades: int) -> pd.DataFrame:
    matrix_path = Path(output_dir) / "baseline_v4_quality_gate_v2_candidate_matrix.csv"
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
    return _build_v2_scaffold_matrix(hold_period=hold_period, min_trades=min_trades)


def _write_v2_scaffold_artifacts(
    output_dir: Path,
    matrix_df: pd.DataFrame,
    hold_period: int,
    min_trades: int,
    scaffold_only: bool,
) -> Dict[str, object]:
    payload = {
        "generated_at": _now_iso(),
        "experiment_id": "baseline_v4_quality_gate_guard_v2",
        "scaffold_only": bool(scaffold_only),
        "objective": (
            "Iterate the v4 quality-gate approach once more with only slightly looser post-entry filters "
            "to try lifting coverage from 2 to >=3 eligible tickers without collapsing quality."
        ),
        "candidate_matrix": matrix_df.to_dict(orient="records"),
        "execution_notes": [
            "Tetap gunakan fast anchor EMA20 + bullish candle.",
            "Jangan kembali ke entry relaxation only.",
            "Bandingkan terhadap baseline reference dan baseline_v3_ema20_trend_guard.",
        ],
    }

    matrix_path = output_dir / "baseline_v4_quality_gate_v2_candidate_matrix.csv"
    payload_path = output_dir / "baseline_v4_quality_gate_v2_experiment_scaffold.json"
    notes_path = output_dir / "baseline_v4_quality_gate_v2_experiment_scaffold.txt"

    matrix_df.to_csv(matrix_path, index=False)
    _write_json(payload_path, payload)
    _write_text(
        notes_path,
        [
            "Baseline v4 Quality Gate Experiment v2 Scaffold",
            "===============================================",
            "",
            "- experiment_id=baseline_v4_quality_gate_guard_v2",
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


def _build_v2_report_text(summary_payload: Dict[str, object]) -> str:
    reference = dict(summary_payload.get("reference_summary") or {})
    v3_control = dict(summary_payload.get("v3_control_summary") or {})
    best = dict(summary_payload.get("best_v4_candidate_summary") or {})
    go_no_go = dict(summary_payload.get("go_no_go") or {})

    lines = [
        "Baseline v4 Quality Gate Experiment v2",
        "======================================",
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
        "Best v4 v2 candidate:",
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


def run_baseline_v4_quality_gate_v2_experiment(
    output_dir: Path,
    hold_period: int,
    min_trades: int,
    scaffold_only: bool = False,
    data_dir: Optional[Path] = None,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
    profit_buffer_pct: float = 0.0,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    matrix_df = _load_v2_scaffold_matrix(output_dir=output_dir, hold_period=hold_period, min_trades=min_trades)
    scaffold_meta = _write_v2_scaffold_artifacts(
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
        raise BaselineV4QualityGateCliError("No v4 quality-gate v2 results were produced.")

    summary_df = build_summary(results_df=results_df)
    go_no_go = determine_go_no_go(summary_df=summary_df, context_payloads=context_payloads)
    go_no_go["experiment_id"] = "baseline_v4_quality_gate_guard_v2"
    summary_payload = build_summary_payload(summary_df=summary_df, go_no_go=go_no_go, context_payloads=context_payloads)
    report_text = _build_v2_report_text(summary_payload=summary_payload)

    results_path = output_dir / "baseline_v4_quality_gate_v2_results.csv"
    summary_path = output_dir / "baseline_v4_quality_gate_v2_summary.json"
    report_path = output_dir / "baseline_v4_quality_gate_v2_report.txt"
    go_no_go_path = output_dir / "baseline_v4_quality_gate_v2_go_no_go.json"

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
    parser = argparse.ArgumentParser(description="Run the second baseline v4 quality-gate iteration.")
    parser.add_argument("--output-dir", default="output", help="Directory for artifacts.")
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files for real evaluation.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Path to the frozen baseline JSON used for runtime settings.",
    )
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Optional ticker metadata CSV.")
    parser.add_argument("--hold-period", type=int, default=3, help="Hold period for the v4 v2 experiment.")
    parser.add_argument("--min-trades", type=int, default=5, help="Min trades threshold for v4 v2 eligibility.")
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
    result = run_baseline_v4_quality_gate_v2_experiment(
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
