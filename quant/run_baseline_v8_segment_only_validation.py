"""Validate whether the v7 winning candidate is stable enough for segment-only validation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict
from quant.run_baseline_v6_guardrail_review import _write_json, _write_text


RESULT_OUTPUT = "baseline_v8_segment_only_validation_results.csv"
SUMMARY_OUTPUT = "baseline_v8_segment_only_validation_summary.json"
REPORT_OUTPUT = "baseline_v8_segment_only_validation_report.txt"
GO_NO_GO_OUTPUT = "baseline_v8_segment_only_validation_go_no_go.json"

DECISION_VALUES = {
    "stay_keep_experimental_for_segment_review",
    "promote_to_segment_only_validation",
    "no_go",
}
RESULT_COLUMNS = [
    "candidate_id",
    "primary_segment",
    "tested_segment",
    "segment_role",
    "segment_support_ok",
    "support_check_passed",
    "support_check_reason",
    "eligible_ticker_count",
    "total_trades_sum",
    "mean_average_return_all",
    "mean_average_return_eligible",
    "mean_score_all",
    "sample_skew_gap",
    "outlier_bias_risk",
    "decision_hint",
]


class BaselineV8SegmentOnlyValidationCliError(ValueError):
    """Friendly CLI error for v8 segment-only validation."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


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
        raise BaselineV8SegmentOnlyValidationCliError(f"Invalid segment spec: {spec}")
    field, value = token.split("=", 1)
    field = field.strip()
    value = value.strip()
    if not field or not value:
        raise BaselineV8SegmentOnlyValidationCliError(f"Invalid segment spec: {spec}")
    return field, value


def _load_governance(output_dir: Path) -> Dict[str, object]:
    payload, warnings = read_json_object(
        Path(output_dir) / "baseline_v6_next_experiment_governance.json",
        "baseline_v6_next_experiment_governance.json",
    )
    governance = payload if isinstance(payload, dict) else {}
    if not governance:
        raise BaselineV8SegmentOnlyValidationCliError("baseline_v6_next_experiment_governance.json is required before v8.")
    if warnings:
        governance["_warnings"] = warnings
    return governance


def _load_v7_results(output_dir: Path) -> pd.DataFrame:
    path = Path(output_dir) / "baseline_v7_segment_aware_results.csv"
    if not path.exists():
        raise BaselineV8SegmentOnlyValidationCliError(f"Required v7 results not found: {path}")
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        raise BaselineV8SegmentOnlyValidationCliError(f"Failed to read {path}: {exc}") from exc
    if frame.empty:
        raise BaselineV8SegmentOnlyValidationCliError(f"{path} is empty.")
    return frame


def _load_v7_go_no_go(output_dir: Path) -> Dict[str, object]:
    payload, _ = read_json_object(
        Path(output_dir) / "baseline_v7_segment_aware_go_no_go.json",
        "baseline_v7_segment_aware_go_no_go.json",
    )
    result = payload if isinstance(payload, dict) else {}
    if not result:
        raise BaselineV8SegmentOnlyValidationCliError("baseline_v7_segment_aware_go_no_go.json is required before v8.")
    return result


def _load_v7_summary(output_dir: Path) -> Dict[str, object]:
    payload, _ = read_json_object(
        Path(output_dir) / "baseline_v7_segment_aware_summary.json",
        "baseline_v7_segment_aware_summary.json",
    )
    return payload if isinstance(payload, dict) else {}


def _validate_v7_context(go_no_go: Dict[str, object]) -> None:
    if str(go_no_go.get("decision")) != "keep_experimental_for_segment_review":
        raise BaselineV8SegmentOnlyValidationCliError(
            "v8 requires v7 decision=keep_experimental_for_segment_review."
        )
    if bool(go_no_go.get("global_promotion_allowed")):
        raise BaselineV8SegmentOnlyValidationCliError(
            "v8 cannot run when v7 already allows global promotion."
        )


def _build_segment_validation_rows(
    *,
    candidate_id: str,
    primary_segment: str,
    supporting_segments: Sequence[str],
    v7_results: pd.DataFrame,
) -> pd.DataFrame:
    candidate_rows = v7_results.loc[v7_results["candidate_id"].astype(str).eq(str(candidate_id))].copy()
    if candidate_rows.empty:
        raise BaselineV8SegmentOnlyValidationCliError(f"Candidate {candidate_id} not found in v7 results.")

    rows: List[Dict[str, object]] = []
    ordered_segments = [primary_segment, *list(supporting_segments)]
    for segment in ordered_segments:
        scoped = candidate_rows.loc[candidate_rows["tested_segment"].astype(str).eq(str(segment))].copy()
        if scoped.empty:
            field, value = _parse_segment_spec(segment)
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "primary_segment": primary_segment,
                    "tested_segment": segment,
                    "segment_role": "primary" if segment == primary_segment else "supporting",
                    "segment_support_ok": False,
                    "support_check_passed": False,
                    "support_check_reason": f"missing_segment_result_for_{field}_{value}",
                    "eligible_ticker_count": 0,
                    "total_trades_sum": 0,
                    "mean_average_return_all": None,
                    "mean_average_return_eligible": None,
                    "mean_score_all": None,
                    "sample_skew_gap": None,
                    "outlier_bias_risk": None,
                    "decision_hint": "missing_segment_result",
                }
            )
            continue

        row = dict(scoped.iloc[0].to_dict())
        segment_support_ok = _safe_bool(row.get("segment_support_ok"))
        outlier_bias_risk = _safe_bool(row.get("outlier_bias_risk"))
        eligible_mean = row.get("mean_average_return_eligible")
        support_check_passed = bool(
            segment_support_ok
            and not outlier_bias_risk
            and eligible_mean is not None
            and _safe_float(eligible_mean, -999.0) > 0.0
        )

        if not segment_support_ok:
            reason = "segment_support_failed"
            decision_hint = "segment_failed"
        elif outlier_bias_risk:
            reason = "segment_support_has_outlier_bias_risk"
            decision_hint = "support_needs_more_review"
        elif eligible_mean is None or _safe_float(eligible_mean, -999.0) <= 0.0:
            reason = "eligible_return_not_positive"
            decision_hint = "support_needs_more_review"
        else:
            reason = "segment_support_confirmed"
            decision_hint = "segment_validated"

        rows.append(
            {
                "candidate_id": candidate_id,
                "primary_segment": primary_segment,
                "tested_segment": segment,
                "segment_role": "primary" if segment == primary_segment else "supporting",
                "segment_support_ok": segment_support_ok,
                "support_check_passed": support_check_passed,
                "support_check_reason": reason,
                "eligible_ticker_count": row.get("eligible_ticker_count"),
                "total_trades_sum": row.get("total_trades_sum"),
                "mean_average_return_all": row.get("mean_average_return_all"),
                "mean_average_return_eligible": row.get("mean_average_return_eligible"),
                "mean_score_all": row.get("mean_score_all"),
                "sample_skew_gap": row.get("sample_skew_gap"),
                "outlier_bias_risk": row.get("outlier_bias_risk"),
                "decision_hint": decision_hint,
            }
        )

    results_df = pd.DataFrame(rows)
    return results_df.reindex(columns=RESULT_COLUMNS)


def _determine_decision(
    *,
    candidate_id: str,
    primary_segment: str,
    results_df: pd.DataFrame,
) -> Dict[str, object]:
    primary_rows = results_df.loc[results_df["segment_role"].astype(str).eq("primary")].copy()
    if primary_rows.empty:
        raise BaselineV8SegmentOnlyValidationCliError("Primary segment row is missing in v8 results.")
    primary_row = dict(primary_rows.iloc[0].to_dict())
    supporting_rows = results_df.loc[results_df["segment_role"].astype(str).eq("supporting")].copy()

    primary_support_ok = _safe_bool(primary_row.get("support_check_passed"))
    supporting_segments = supporting_rows["tested_segment"].astype(str).tolist()
    supporting_segments_passed = supporting_rows.loc[
        supporting_rows["support_check_passed"].fillna(False), "tested_segment"
    ].astype(str).tolist()
    supporting_segments_failed = supporting_rows.loc[
        ~supporting_rows["support_check_passed"].fillna(False), "tested_segment"
    ].astype(str).tolist()

    if not primary_support_ok:
        decision = "no_go"
        segment_stability_ok = False
        next_action = "drop_candidate_from_segment_only_validation_shortlist"
        notes = [
            "Primary segment tidak cukup stabil untuk mempertahankan kandidat sebagai strategi subset.",
            "Kandidat harus tetap no_go sampai primary segment menunjukkan support yang valid.",
        ]
    else:
        segment_stability_ok = len(supporting_segments) > 0 and len(supporting_segments_failed) == 0
        if segment_stability_ok:
            decision = "promote_to_segment_only_validation"
            next_action = "promote_candidate_to_segment_only_validation_on_primary_segment_without_global_promotion"
            notes = [
                "Primary segment lolos dan seluruh supporting safe segments konsisten.",
                "Kandidat layak naik ke validasi khusus subset, tetapi tetap dilarang untuk promosi global.",
            ]
        else:
            decision = "stay_keep_experimental_for_segment_review"
            next_action = "keep_candidate_experimental_on_primary_segment_and_collect_more_supporting_segment_evidence"
            notes = [
                "Primary segment lolos, tetapi supporting safe segments belum cukup konsisten untuk naik ke tahap validasi subset.",
                "Kandidat tetap boleh dipertahankan hanya sebagai experimental subset.",
            ]

    payload = {
        "candidate_id": candidate_id,
        "primary_segment": primary_segment,
        "supporting_segments": supporting_segments_passed,
        "decision": decision,
        "segment_stability_ok": bool(segment_stability_ok),
        "global_promotion_allowed": False,
        "recommended_next_action": next_action,
        "supporting_segments_checked": supporting_segments,
        "supporting_segments_failed": supporting_segments_failed,
        "primary_segment_support_ok": primary_support_ok,
        "decision_notes": dedupe(notes),
    }
    if decision not in DECISION_VALUES:
        raise BaselineV8SegmentOnlyValidationCliError("v8 decision must be explicit and valid.")
    return payload


def _build_summary_payload(
    *,
    governance: Dict[str, object],
    v7_go_no_go: Dict[str, object],
    v7_summary: Dict[str, object],
    results_df: pd.DataFrame,
    go_no_go: Dict[str, object],
) -> Dict[str, object]:
    supporting_checked = list(go_no_go.get("supporting_segments_checked") or [])
    supporting_passed = list(go_no_go.get("supporting_segments") or [])
    supporting_failed = list(go_no_go.get("supporting_segments_failed") or [])
    return {
        "generated_at": _now_iso(),
        "input_context": {
            "v7_best_candidate_id": v7_go_no_go.get("best_candidate_id"),
            "v7_tested_segment": v7_go_no_go.get("tested_segment"),
            "v7_decision": v7_go_no_go.get("decision"),
            "global_promotion_allowed": False,
        },
        "safe_segments_from_governance": list(governance.get("segments_safe_to_test_next") or []),
        "segments_to_avoid": list(governance.get("segments_to_avoid") or []),
        "candidate_id": go_no_go.get("candidate_id"),
        "primary_segment": go_no_go.get("primary_segment"),
        "supporting_segments_checked": supporting_checked,
        "supporting_segments_passed": supporting_passed,
        "supporting_segments_failed": supporting_failed,
        "primary_segment_row": (
            results_df.loc[results_df["segment_role"].astype(str).eq("primary")].head(1).to_dict(orient="records") or [{}]
        )[0],
        "supporting_segment_rows": results_df.loc[
            results_df["segment_role"].astype(str).eq("supporting")
        ].to_dict(orient="records"),
        "segment_stability_ok": go_no_go.get("segment_stability_ok"),
        "decision": _sanitize_for_summary(go_no_go),
        "prior_segment_context": {
            "v7_supported_result_count": v7_summary.get("supported_result_count"),
            "v7_tested_safe_segments": v7_summary.get("tested_safe_segments"),
        },
    }


def _sanitize_for_summary(value: object) -> object:
    if isinstance(value, dict):
        return {key: _sanitize_for_summary(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_summary(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def _build_report_text(summary_payload: Dict[str, object], go_no_go: Dict[str, object]) -> List[str]:
    lines = [
        "Baseline v8 Segment-Only Validation",
        "===================================",
        "",
        f"- Candidate: {go_no_go.get('candidate_id')}",
        f"- Primary segment: {go_no_go.get('primary_segment')}",
        f"- Supporting segments: {', '.join(go_no_go.get('supporting_segments_checked') or []) or '-'}",
        f"- Decision: {go_no_go.get('decision')}",
        f"- Segment stability ok: {go_no_go.get('segment_stability_ok')}",
        f"- Global promotion allowed: {go_no_go.get('global_promotion_allowed')}",
        f"- Recommended next action: {go_no_go.get('recommended_next_action')}",
        "",
        "Supporting check summary:",
        f"- passed={', '.join(go_no_go.get('supporting_segments') or []) or '-'}",
        f"- failed={', '.join(go_no_go.get('supporting_segments_failed') or []) or '-'}",
    ]
    notes = list(go_no_go.get("decision_notes") or [])
    if notes:
        lines.extend(["", "Decision notes:"])
        for item in notes:
            lines.append(f"- {item}")
    return lines


def run_baseline_v8_segment_only_validation(output_dir: Path) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    governance = _load_governance(output_dir=output_dir)
    v7_results = _load_v7_results(output_dir=output_dir)
    v7_go_no_go = _load_v7_go_no_go(output_dir=output_dir)
    v7_summary = _load_v7_summary(output_dir=output_dir)
    _validate_v7_context(go_no_go=v7_go_no_go)

    candidate_id = str(v7_go_no_go.get("best_candidate_id") or "").strip()
    primary_segment = str(v7_go_no_go.get("tested_segment") or "").strip()
    if not candidate_id or not primary_segment:
        raise BaselineV8SegmentOnlyValidationCliError("v7 go/no-go must contain best_candidate_id and tested_segment.")

    safe_segments = [str(item).strip() for item in list(governance.get("segments_safe_to_test_next") or []) if str(item).strip()]
    supporting_segments = [item for item in dedupe(safe_segments) if item != primary_segment]
    if primary_segment not in safe_segments:
        safe_segments = dedupe([primary_segment, *safe_segments])
        supporting_segments = [item for item in safe_segments if item != primary_segment]

    results_df = _build_segment_validation_rows(
        candidate_id=candidate_id,
        primary_segment=primary_segment,
        supporting_segments=supporting_segments,
        v7_results=v7_results,
    )
    go_no_go = _determine_decision(
        candidate_id=candidate_id,
        primary_segment=primary_segment,
        results_df=results_df,
    )
    summary_payload = _build_summary_payload(
        governance=governance,
        v7_go_no_go=v7_go_no_go,
        v7_summary=v7_summary,
        results_df=results_df,
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
        description="Validate the v7 winner as a subset-only experimental candidate without global promotion."
    )
    parser.add_argument("--output-dir", default="output", help="Artifact directory. Default: output")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = run_baseline_v8_segment_only_validation(output_dir=Path(args.output_dir))
    except BaselineV8SegmentOnlyValidationCliError as exc:
        print(f"Segment-only validation failed: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during segment-only validation: {exc}")
        return 1

    go_no_go = result["go_no_go"]
    print("Baseline v8 segment-only validation complete.")
    print(f"candidate_id={go_no_go['candidate_id']}")
    print(f"primary_segment={go_no_go['primary_segment']}")
    print(f"decision={go_no_go['decision']}")
    print(f"recommended_next_action={go_no_go['recommended_next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
