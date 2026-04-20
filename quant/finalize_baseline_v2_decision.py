"""Finalize the strategic decision after Phase A runtime closeout and baseline v2 redesign."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object  # noqa: E402


DECISION_VALUES = {
    "phase_a_closed_and_baseline_v2_approved",
    "phase_a_closed_with_notes_and_baseline_v2_approved",
    "baseline_v2_keep_experimental",
    "baseline_v2_no_go_redesign_again",
    "cannot_decide_until_runtime_fixed",
}


class FinalizeBaselineV2DecisionCliError(ValueError):
    """Friendly CLI error for baseline v2 final strategic decision."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _sanitize_for_json(value: object) -> object:
    if isinstance(value, dict):
        return {key: _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    return value


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize_for_json(payload), indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_context(output_dir: Path) -> Dict[str, object]:
    artifact_map = {
        "phase_a_closeout": "phase_a_closeout_status.json",
        "phase_a_runtime": "phase_a_runtime_diagnostics.json",
        "baseline_redesign": "baseline_redesign_go_no_go.json",
        "baseline_best_candidate": "baseline_v2_best_candidate.json",
        "baseline_validation": "baseline_v2_validation.json",
        "baseline_validation_go_no_go": "baseline_v2_validation_go_no_go.json",
        "roadmap_status": "project_roadmap_status.json",
        "transition": "phase_a_to_phase_b_transition.json",
        "phase_b_next_phase": "phase_b_go_no_go_next_phase.json",
    }

    payloads: Dict[str, object] = {}
    warnings: List[str] = []
    for key, filename in artifact_map.items():
        payload, item_warnings = read_json_object(output_dir / filename, filename)
        payloads[key] = payload if isinstance(payload, dict) else {}
        warnings.extend(item_warnings)
    payloads["warnings"] = dedupe(warnings)
    return payloads


def build_final_decision_payload(output_dir: Path) -> Dict[str, object]:
    context = _load_context(output_dir=output_dir)
    closeout = dict(context.get("phase_a_closeout") or {})
    runtime = dict(context.get("phase_a_runtime") or {})
    redesign = dict(context.get("baseline_redesign") or {})
    best_candidate = dict(context.get("baseline_best_candidate") or {})
    validation = dict(context.get("baseline_validation") or {})
    validation_go_no_go = dict(context.get("baseline_validation_go_no_go") or {})
    roadmap = dict(context.get("roadmap_status") or {})
    transition = dict(context.get("transition") or {})
    phase_b_next_phase = dict(context.get("phase_b_next_phase") or {})

    runtime_status = _safe_str(runtime.get("runtime_status")) or _safe_str(closeout.get("runtime_status")) or "unknown"
    closeout_status = _safe_str(closeout.get("closeout_status")) or _safe_str(closeout.get("status")) or "unknown"
    redesign_decision = _safe_str(redesign.get("decision")) or "unknown"
    validation_status = _safe_str(validation.get("validation_status")) or _safe_str(validation_go_no_go.get("validation_status")) or "unknown"
    candidate_id = (
        _safe_str(best_candidate.get("candidate_id"))
        or _safe_str(dict(best_candidate.get("selected_candidate") or {}).get("candidate_id"))
        or _safe_str(validation.get("candidate_id"))
        or _safe_str(validation_go_no_go.get("candidate_id"))
        or "baseline_v2_hold3_with_trend_guard"
    )

    blockers_remaining = dedupe(
        [
            _safe_str(runtime.get("blocker_reason")),
            *[str(item).strip() for item in list(closeout.get("blocker_reasons") or []) if str(item).strip()],
            *[str(item).strip() for item in list(closeout.get("blocking_items") or []) if str(item).strip()],
        ]
    )

    if runtime_status != "runtime_ok":
        strategic_decision = "cannot_decide_until_runtime_fixed"
        baseline_v2_status = "decision_blocked_by_phase_a_runtime"
        current_project_mode = "phase_a_runtime_fix_required"
        can_continue_after_redesign = False
        recommended_next_action = (
            _safe_str(runtime.get("next_action"))
            or _safe_str(closeout.get("next_action"))
            or "fix_phase_a_runtime_then_rerun_closeout"
        )
    elif closeout_status == "closed" and validation_status == "promotable":
        strategic_decision = "phase_a_closed_and_baseline_v2_approved"
        baseline_v2_status = "approved_for_retry"
        current_project_mode = "baseline_v2_approved_for_limited_phase_b_retry"
        can_continue_after_redesign = True
        recommended_next_action = "run_limited_phase_b_retry_on_redesigned_baseline"
    elif closeout_status == "closed_with_notes" and validation_status == "promotable":
        strategic_decision = "phase_a_closed_with_notes_and_baseline_v2_approved"
        baseline_v2_status = "approved_with_notes_for_retry"
        current_project_mode = "baseline_v2_approved_with_closeout_notes"
        can_continue_after_redesign = True
        recommended_next_action = "run_limited_phase_b_retry_with_documented_closeout_notes"
    elif validation_status in {"usable", "weak"} and redesign_decision in {"improved_but_keep_experimental", "usable_for_retry", "promote_new_baseline_eval_design"}:
        strategic_decision = "baseline_v2_keep_experimental"
        baseline_v2_status = "keep_experimental"
        current_project_mode = "baseline_v2_experimental_hold"
        can_continue_after_redesign = False
        recommended_next_action = (
            _safe_str(validation.get("next_action"))
            or _safe_str(validation_go_no_go.get("recommended_next_action"))
            or "keep_baseline_v2_experimental_and_continue_validation"
        )
    else:
        strategic_decision = "baseline_v2_no_go_redesign_again"
        baseline_v2_status = "no_go_redesign_again"
        current_project_mode = "baseline_v2_redesign_required"
        can_continue_after_redesign = False
        recommended_next_action = (
            _safe_str(validation.get("next_action"))
            or _safe_str(redesign.get("next_action"))
            or "redesign_baseline_v2_again"
        )

    current_phase_b_status = (
        "limited_retry_ready" if can_continue_after_redesign else _safe_str(phase_b_next_phase.get("phase_b_status")) or _safe_str(dict(roadmap.get("latest_execution_status") or {}).get("phase_b_status")) or "phase_b_needs_redesign_before_continue"
    )

    payload = {
        "generated_at": _now_iso(),
        "decision": strategic_decision,
        "baseline_v2_candidate_selected": candidate_id,
        "candidate_id": candidate_id,
        "phase_a_runtime_status": runtime_status,
        "phase_a_closeout_status": closeout_status,
        "baseline_redesign_decision": redesign_decision,
        "baseline_v2_status": baseline_v2_status,
        "baseline_v2_validation_status": validation_status,
        "current_project_mode": current_project_mode,
        "current_phase_b_status": current_phase_b_status,
        "can_continue_after_redesign": can_continue_after_redesign,
        "recommended_next_action": recommended_next_action,
        "blockers_remaining": blockers_remaining,
        "roadmap_reference": {
            "phase_b_status": _safe_str(phase_b_next_phase.get("phase_b_status")) or _safe_str(dict(roadmap.get("latest_execution_status") or {}).get("phase_b_status")),
            "phase_c_decision": _safe_str(phase_b_next_phase.get("phase_c_decision")) or _safe_str(dict(roadmap.get("latest_execution_status") or {}).get("phase_c_decision")),
            "transition_retry_readiness": _safe_str(transition.get("phase_b_retry_readiness_after_candidate_validation")) or _safe_str(transition.get("phase_b_retry_readiness")),
        },
        "warnings": list(context.get("warnings") or []),
    }
    return payload


def build_project_current_state_payload(decision_payload: Dict[str, object]) -> Dict[str, object]:
    decision = _safe_str(decision_payload.get("decision"))
    can_continue = bool(decision_payload.get("can_continue_after_redesign"))
    return {
        "generated_at": decision_payload.get("generated_at"),
        "phase_a_runtime_status": decision_payload.get("phase_a_runtime_status"),
        "phase_a_closeout_status": decision_payload.get("phase_a_closeout_status"),
        "baseline_v2_status": decision_payload.get("baseline_v2_status"),
        "baseline_v2_validation_status": decision_payload.get("baseline_v2_validation_status"),
        "current_project_mode": decision_payload.get("current_project_mode"),
        "can_continue_after_redesign": can_continue,
        "recommended_next_action": decision_payload.get("recommended_next_action"),
        "blockers_remaining": list(decision_payload.get("blockers_remaining") or []),
        "final_decision": decision,
    }


def build_project_current_state_text(payload: Dict[str, object]) -> str:
    lines = [
        "Project Current State",
        "=====================",
        "",
        f"- phase_a_runtime_status={payload.get('phase_a_runtime_status')}",
        f"- phase_a_closeout_status={payload.get('phase_a_closeout_status')}",
        f"- baseline_v2_status={payload.get('baseline_v2_status')}",
        f"- baseline_v2_validation_status={payload.get('baseline_v2_validation_status')}",
        f"- current_project_mode={payload.get('current_project_mode')}",
        f"- can_continue_after_redesign={payload.get('can_continue_after_redesign')}",
        f"- recommended_next_action={payload.get('recommended_next_action')}",
        "",
        "Blockers remaining:",
    ]
    blockers = list(payload.get("blockers_remaining") or [])
    if blockers:
        lines.extend([f"- {item}" for item in blockers])
    else:
        lines.append("- none")
    lines.extend(["", f"- final_decision={payload.get('final_decision')}"])
    return "\n".join(lines) + "\n"


def finalize_baseline_v2_decision(output_dir: Path) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    decision_payload = build_final_decision_payload(output_dir=output_dir)
    current_state_payload = build_project_current_state_payload(decision_payload=decision_payload)
    current_state_text = build_project_current_state_text(current_state_payload)

    _write_json(output_dir / "baseline_v2_go_no_go.json", decision_payload)
    _write_json(output_dir / "project_current_state.json", current_state_payload)
    _write_text(output_dir / "project_current_state.txt", current_state_text)

    return {
        "decision_payload": decision_payload,
        "project_current_state": current_state_payload,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize the strategic project decision after Phase A runtime closeout and baseline v2 redesign."
    )
    parser.add_argument("--output-dir", default="output", help="Directory containing execution artifacts.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = finalize_baseline_v2_decision(output_dir=Path(args.output_dir))
    print(f"Decision: {result['decision_payload']['decision']}")
    print(f"Can continue after redesign: {result['decision_payload']['can_continue_after_redesign']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
