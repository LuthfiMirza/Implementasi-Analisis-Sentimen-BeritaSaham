"""Run the next experiment as a segment-aware fairness review on safe universe subsets."""

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

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402
from quant.run_baseline_v6_guardrail_review import (  # noqa: E402
    _evaluate_status,
    _load_candidate_frames,
    _resolve_current_guardrails,
    _sanitize_for_json,
    _segment_guardrails,
    _summarize_scope,
    _write_json,
    _write_text,
)


RESULT_OUTPUT = "baseline_v7_segment_aware_results.csv"
SUMMARY_OUTPUT = "baseline_v7_segment_aware_summary.json"
REPORT_OUTPUT = "baseline_v7_segment_aware_report.txt"
GO_NO_GO_OUTPUT = "baseline_v7_segment_aware_go_no_go.json"

RESULT_COLUMNS = [
    "experiment_stage",
    "candidate_id",
    "tested_segment",
    "segment_field",
    "segment_value",
    "segment_tickers",
    "segment_ticker_count",
    "source_results_file",
    "eligible_trade_floor",
    "min_eligible_tickers_required",
    "minimum_trade_sample_required",
    "ticker_count",
    "eligible_ticker_count",
    "total_trades_sum",
    "positive_score_ticker_count",
    "mean_average_return_all",
    "mean_average_return_eligible",
    "mean_score_all",
    "supportive_but_ineligible_ticker_count",
    "positive_return_but_ineligible_ticker_count",
    "sample_skew_gap",
    "outlier_bias_risk",
    "segment_support_ok",
    "decision",
    "global_promotion_allowed",
    "recommended_next_action",
]

DECISION_VALUES = {
    "keep_experimental_for_segment_review",
    "no_go",
}


class BaselineV7SegmentAwareCliError(ValueError):
    """Friendly CLI error for the v7 segment-aware experiment."""


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


def _load_governance(output_dir: Path) -> Tuple[Dict[str, object], List[str]]:
    payload, warnings = read_json_object(
        Path(output_dir) / "baseline_v6_next_experiment_governance.json",
        "baseline_v6_next_experiment_governance.json",
    )
    governance = payload if isinstance(payload, dict) else {}
    if not governance:
        raise BaselineV7SegmentAwareCliError("baseline_v6_next_experiment_governance.json is required before running v7.")

    if str(governance.get("recommended_guardrail_mode")) != "move_to_segment_aware_guardrail":
        raise BaselineV7SegmentAwareCliError("v7 requires recommended_guardrail_mode=move_to_segment_aware_guardrail.")
    if str(governance.get("recommended_universe_mode")) != "split_universe_before_next_experiment":
        raise BaselineV7SegmentAwareCliError("v7 requires recommended_universe_mode=split_universe_before_next_experiment.")
    if not bool(governance.get("segment_aware_evaluation_recommended")):
        raise BaselineV7SegmentAwareCliError("v7 requires segment_aware_evaluation_recommended=true.")
    return governance, warnings


def _load_universe_segmentation(output_dir: Path) -> pd.DataFrame:
    path = Path(output_dir) / "baseline_v6_universe_segmentation.csv"
    if not path.exists():
        raise BaselineV7SegmentAwareCliError(f"Required segmentation file not found: {path}")

    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise BaselineV7SegmentAwareCliError(f"Failed to read {path}: {exc}") from exc

    if frame.empty or "ticker" not in frame.columns:
        raise BaselineV7SegmentAwareCliError(f"{path} does not contain usable universe segmentation rows.")
    frame = frame.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    return frame


def _parse_segment_spec(spec: str) -> Tuple[str, str]:
    token = str(spec or "").strip()
    if "=" not in token:
        raise BaselineV7SegmentAwareCliError(f"Invalid segment spec: {spec}")
    field, value = token.split("=", 1)
    field = field.strip()
    value = value.strip()
    if not field or not value:
        raise BaselineV7SegmentAwareCliError(f"Invalid segment spec: {spec}")
    return field, value


def _safe_segment_list(governance: Dict[str, object], key: str) -> List[str]:
    values = []
    for item in list(governance.get(key) or []):
        text = str(item).strip()
        if text:
            values.append(text)
    return dedupe(values)


def _candidate_results_frame(item: Dict[str, object]) -> pd.DataFrame:
    frame = item["frame"].copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    return frame


def _evaluate_candidate_segment(
    *,
    experiment_stage: str,
    candidate_id: str,
    source_results_file: str,
    segment_field: str,
    segment_value: str,
    segment_tickers: Sequence[str],
    candidate_frame: pd.DataFrame,
    current_guardrails: Dict[str, object],
) -> Dict[str, object]:
    scoped = candidate_frame.loc[candidate_frame["ticker"].isin(list(segment_tickers))].copy()
    if scoped.empty:
        raise BaselineV7SegmentAwareCliError(
            f"Candidate {candidate_id} has no rows inside tested segment {segment_field}={segment_value}."
        )

    segment_guardrails = _segment_guardrails(
        segment_ticker_count=int(scoped["ticker"].nunique()),
        current_guardrails=current_guardrails,
    )
    if segment_guardrails is None:
        raise BaselineV7SegmentAwareCliError(
            f"Safe segment {segment_field}={segment_value} is too small for segment-aware evaluation."
        )

    summary = _summarize_scope(
        scoped,
        eligible_trade_floor=_safe_int(current_guardrails.get("min_trades_threshold"), 5),
    )
    decision = _evaluate_status(
        summary=summary,
        min_eligible_tickers=_safe_int(segment_guardrails.get("min_eligible_tickers"), 2),
        minimum_trade_sample=_safe_int(segment_guardrails.get("minimum_trade_sample_required"), 10),
        min_segment_tickers=3,
    )
    segment_support_ok = str(decision.get("status")) == "keep_experimental"
    final_decision = "keep_experimental_for_segment_review" if segment_support_ok else "no_go"
    tested_segment = f"{segment_field}={segment_value}"

    if segment_support_ok:
        next_action = f"keep_candidate_for_segment_review_only_on_{segment_field}_{segment_value}"
    else:
        next_action = f"no_go_keep_candidate_out_of_{segment_field}_{segment_value}_segment_shortlist"

    return {
        "experiment_stage": experiment_stage,
        "candidate_id": candidate_id,
        "tested_segment": tested_segment,
        "segment_field": segment_field,
        "segment_value": segment_value,
        "segment_tickers": "|".join(sorted(set(segment_tickers))),
        "segment_ticker_count": int(len(set(segment_tickers))),
        "source_results_file": source_results_file,
        "eligible_trade_floor": _safe_int(current_guardrails.get("min_trades_threshold"), 5),
        "min_eligible_tickers_required": _safe_int(segment_guardrails.get("min_eligible_tickers"), 2),
        "minimum_trade_sample_required": _safe_int(segment_guardrails.get("minimum_trade_sample_required"), 10),
        **summary,
        "segment_support_ok": bool(segment_support_ok),
        "decision": final_decision,
        "global_promotion_allowed": False,
        "recommended_next_action": next_action,
    }


def _rank_results(results_df: pd.DataFrame) -> pd.DataFrame:
    if results_df.empty:
        return results_df
    decision_rank = results_df["decision"].map(
        {"keep_experimental_for_segment_review": 1, "no_go": 0}
    ).fillna(0)
    support_rank = results_df["segment_support_ok"].fillna(False).astype(int)
    ranked = results_df.assign(_decision_rank=decision_rank, _support_rank=support_rank)
    ranked = ranked.sort_values(
        by=[
            "_decision_rank",
            "_support_rank",
            "mean_average_return_eligible",
            "eligible_ticker_count",
            "total_trades_sum",
            "mean_score_all",
        ],
        ascending=[False, False, False, False, False, False],
    ).reset_index(drop=True)
    return ranked.drop(columns=["_decision_rank", "_support_rank"])


def _build_summary_payload(
    *,
    governance: Dict[str, object],
    current_guardrails: Dict[str, object],
    safe_segments: Sequence[str],
    tested_segments: Sequence[Dict[str, object]],
    results_df: pd.DataFrame,
    warnings: Sequence[str],
    go_no_go: Dict[str, object],
) -> Dict[str, object]:
    candidate_summaries: List[Dict[str, object]] = []
    for candidate_id, frame in results_df.groupby("candidate_id", dropna=False):
        ranked = _rank_results(frame.copy())
        best = dict(ranked.iloc[0].to_dict())
        candidate_summaries.append(
            {
                "candidate_id": str(candidate_id),
                "experiment_stages": dedupe(frame["experiment_stage"].astype(str).tolist()),
                "tested_segment_count": int(len(frame)),
                "supported_segment_count": int(frame["segment_support_ok"].fillna(False).sum()),
                "best_segment_result": _sanitize_for_json(best),
            }
        )

    return {
        "generated_at": _now_iso(),
        "input_context": {
            "recommended_guardrail_mode": governance.get("recommended_guardrail_mode"),
            "recommended_universe_mode": governance.get("recommended_universe_mode"),
            "global_guardrail_still_valid": governance.get("global_guardrail_still_valid"),
            "segment_aware_evaluation_recommended": governance.get("segment_aware_evaluation_recommended"),
        },
        "guardrails_kept_fixed": {
            "global_min_trades_threshold": _safe_int(current_guardrails.get("min_trades_threshold"), 5),
            "global_min_eligible_tickers": _safe_int(current_guardrails.get("min_eligible_tickers"), 3),
            "global_minimum_trade_sample_required": _safe_int(current_guardrails.get("minimum_trade_sample_required"), 15),
            "global_promotion_allowed": False,
        },
        "tested_safe_segments": list(safe_segments),
        "tested_segment_details": _sanitize_for_json(list(tested_segments)),
        "tested_candidate_count": int(results_df["candidate_id"].nunique()) if not results_df.empty else 0,
        "supported_result_count": int(results_df["segment_support_ok"].fillna(False).sum()) if not results_df.empty else 0,
        "candidate_summaries": candidate_summaries,
        "go_no_go": _sanitize_for_json(go_no_go),
        "warnings": dedupe([str(item) for item in list(warnings)]),
    }


def _build_report_text(summary_payload: Dict[str, object], go_no_go: Dict[str, object]) -> List[str]:
    safe_segments = list(summary_payload.get("tested_safe_segments") or [])
    candidate_summaries = list(summary_payload.get("candidate_summaries") or [])
    lines = [
        "Baseline v7 Segment-Aware Experiment",
        "====================================",
        "",
        f"- Decision: {go_no_go.get('decision')}",
        f"- Best candidate: {go_no_go.get('best_candidate_id')}",
        f"- Tested segment: {go_no_go.get('tested_segment')}",
        f"- Segment support ok: {go_no_go.get('segment_support_ok')}",
        f"- Global promotion allowed: {go_no_go.get('global_promotion_allowed')}",
        f"- Recommended next action: {go_no_go.get('recommended_next_action')}",
        "",
        "Safe segments tested:",
    ]
    for item in safe_segments:
        lines.append(f"- {item}")

    lines.extend(["", "Candidate outcomes:"])
    for item in candidate_summaries:
        best = safe_dict(item.get("best_segment_result"))
        lines.append(
            f"- {item.get('candidate_id')}: supported_segment_count={item.get('supported_segment_count')}, "
            f"best_segment={best.get('tested_segment')}, best_decision={best.get('decision')}"
        )

    notes = list(go_no_go.get("decision_notes") or [])
    if notes:
        lines.extend(["", "Decision notes:"])
        for item in notes:
            lines.append(f"- {item}")
    return lines


def _determine_go_no_go(results_df: pd.DataFrame) -> Dict[str, object]:
    ranked = _rank_results(results_df.copy())
    if ranked.empty:
        return {
            "best_candidate_id": None,
            "tested_segment": None,
            "decision": "no_go",
            "segment_support_ok": False,
            "global_promotion_allowed": False,
            "recommended_next_action": "no_safe_segment_support_found_keep_global_guardrail_only",
            "decision_notes": ["Tidak ada hasil segment-aware yang bisa dievaluasi."],
        }

    best = dict(ranked.iloc[0].to_dict())
    supported = ranked.loc[ranked["segment_support_ok"].fillna(False)].copy()

    if not supported.empty:
        decision = "keep_experimental_for_segment_review"
        next_action = f"keep_candidate_for_segment_review_only_on_{best['segment_field']}_{best['segment_value']}"
        notes = [
            "Kandidat hanya didukung pada subset aman tertentu dan tetap tidak boleh dipromosikan global.",
            "Guardrail global tetap berlaku sebagai gate promosi akhir.",
        ]
    else:
        decision = "no_go"
        next_action = "no_candidate_has_fair_segment_support_keep_current_global_guardrail"
        notes = [
            "Tidak ada kandidat existing yang menunjukkan dukungan segment yang cukup kuat.",
            "Eksperimen global tetap tidak boleh dilanjutkan dari hasil subset ini.",
        ]

    payload = {
        "best_candidate_id": best.get("candidate_id"),
        "tested_segment": best.get("tested_segment"),
        "decision": decision,
        "segment_support_ok": bool(best.get("segment_support_ok")),
        "global_promotion_allowed": False,
        "recommended_next_action": next_action,
        "experiment_stage": best.get("experiment_stage"),
        "decision_notes": dedupe(notes),
    }
    if payload["decision"] not in DECISION_VALUES:
        raise BaselineV7SegmentAwareCliError("Decision must be explicit and non-ambiguous.")
    return payload


def run_baseline_v7_segment_aware_experiment(
    output_dir: Path,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    governance, governance_warnings = _load_governance(output_dir=output_dir)
    segmentation_df = _load_universe_segmentation(output_dir=output_dir)
    context_payloads = {
        "baseline_v2_validation": safe_dict(read_json_object(Path(output_dir) / "baseline_v2_validation.json", "baseline_v2_validation.json")[0]),
        "baseline_v3_summary": safe_dict(read_json_object(Path(output_dir) / "baseline_v3_signal_rule_summary.json", "baseline_v3_signal_rule_summary.json")[0]),
        "baseline_v4_summary": safe_dict(read_json_object(Path(output_dir) / "baseline_v4_quality_gate_summary.json", "baseline_v4_quality_gate_summary.json")[0]),
        "baseline_v5_summary": safe_dict(read_json_object(Path(output_dir) / "baseline_v5_exit_hold_summary.json", "baseline_v5_exit_hold_summary.json")[0]),
    }
    current_guardrails = _resolve_current_guardrails(context_payloads=context_payloads)
    candidate_frames, candidate_warnings = _load_candidate_frames(output_dir=output_dir, context_payloads=context_payloads)
    if not candidate_frames:
        raise BaselineV7SegmentAwareCliError("No candidate result frames available for v7 segment-aware evaluation.")

    safe_segments = _safe_segment_list(governance, "segments_safe_to_test_next")
    if not safe_segments:
        raise BaselineV7SegmentAwareCliError("No safe segments are defined in baseline_v6_next_experiment_governance.json.")

    tested_segments: List[Dict[str, object]] = []
    result_rows: List[Dict[str, object]] = []
    for segment_spec in safe_segments:
        segment_field, segment_value = _parse_segment_spec(segment_spec)
        if segment_field not in segmentation_df.columns:
            raise BaselineV7SegmentAwareCliError(
                f"Safe segment field {segment_field} is missing from baseline_v6_universe_segmentation.csv."
            )

        segment_tickers = (
            segmentation_df.loc[
                segmentation_df[segment_field].astype(str).eq(str(segment_value)),
                "ticker",
            ]
            .astype(str)
            .str.upper()
            .tolist()
        )
        if len(segment_tickers) < 3:
            raise BaselineV7SegmentAwareCliError(
                f"Safe segment {segment_spec} resolves to fewer than 3 tickers and cannot be evaluated fairly."
            )

        tested_segments.append(
            {
                "tested_segment": segment_spec,
                "segment_field": segment_field,
                "segment_value": segment_value,
                "tickers": segment_tickers,
                "ticker_count": len(segment_tickers),
            }
        )

        for item in candidate_frames:
            result_rows.append(
                _evaluate_candidate_segment(
                    experiment_stage=str(item["experiment_stage"]),
                    candidate_id=str(item["candidate_id"]),
                    source_results_file=str(item["frame"]["source_results_file"].iloc[0]),
                    segment_field=segment_field,
                    segment_value=segment_value,
                    segment_tickers=segment_tickers,
                    candidate_frame=_candidate_results_frame(item),
                    current_guardrails=current_guardrails,
                )
            )

    results_df = pd.DataFrame(result_rows)
    if results_df.empty:
        raise BaselineV7SegmentAwareCliError("No v7 segment-aware rows were produced.")
    results_df = _rank_results(results_df.reindex(columns=RESULT_COLUMNS))
    go_no_go = _determine_go_no_go(results_df=results_df)
    summary_payload = _build_summary_payload(
        governance=governance,
        current_guardrails=current_guardrails,
        safe_segments=safe_segments,
        tested_segments=tested_segments,
        results_df=results_df,
        warnings=[*governance_warnings, *candidate_warnings],
        go_no_go=go_no_go,
    )
    report_lines = _build_report_text(summary_payload=summary_payload, go_no_go=go_no_go)

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
        description="Evaluate existing candidates fairly on safe universe segments without changing the active baseline."
    )
    parser.add_argument("--output-dir", default="output", help="Artifact directory. Default: output")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run_baseline_v7_segment_aware_experiment(output_dir=Path(args.output_dir))
    except BaselineV7SegmentAwareCliError as exc:
        print(f"Segment-aware experiment failed: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during segment-aware experiment: {exc}")
        return 1

    go_no_go = result["go_no_go"]
    print("Baseline v7 segment-aware experiment complete.")
    print(f"best_candidate_id={go_no_go['best_candidate_id']}")
    print(f"tested_segment={go_no_go['tested_segment']}")
    print(f"decision={go_no_go['decision']}")
    print(f"recommended_next_action={go_no_go['recommended_next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
