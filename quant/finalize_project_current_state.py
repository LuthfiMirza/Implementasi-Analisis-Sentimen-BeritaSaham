"""Freeze the current project state from roadmap and execution artifacts."""

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


class ProjectCurrentStateCliError(ValueError):
    """Friendly CLI error for current-state finalization."""


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


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_context(output_dir: Path) -> Dict[str, object]:
    artifact_map = {
        "roadmap_status": "project_roadmap_status.json",
        "phase_b_next_phase": "phase_b_go_no_go_next_phase.json",
        "phase_b_final_closeout": "phase_b_final_closeout.json",
        "project_after_phase_b_decision": "project_after_phase_b_decision.json",
        "phase_b_retest_readiness_gate": "phase_b_retest_readiness_gate.json",
        "baseline_file": "phase_a_baseline_final.json",
        "transition": "phase_a_to_phase_b_transition.json",
        "baseline_revision": "baseline_v2_go_no_go.json",
        "baseline_v2_validation": "baseline_v2_validation_go_no_go.json",
        "baseline_v2_subset": "baseline_v2_subset_go_no_go.json",
        "baseline_v2_watchlist": "baseline_v2_watchlist_go_no_go.json",
        "baseline_v2_watchlist_monitoring": "baseline_v2_watchlist_monitoring_decision.json",
    }

    payloads: Dict[str, object] = {}
    warnings: List[str] = []
    for key, filename in artifact_map.items():
        payload, item_warnings = read_json_object(Path(output_dir) / filename, filename)
        payloads[key] = payload if isinstance(payload, dict) else {}
        warnings.extend(item_warnings)
    payloads["warnings"] = dedupe(warnings)
    return payloads


def build_current_state_payload(output_dir: Path) -> Dict[str, object]:
    context = _load_context(output_dir=output_dir)
    roadmap = dict(context.get("roadmap_status") or {})
    roadmap_latest = dict(roadmap.get("latest_execution_status") or {})
    phase_b_next = dict(context.get("phase_b_next_phase") or {})
    phase_b_closeout = dict(context.get("phase_b_final_closeout") or {})
    project_after_phase_b = dict(context.get("project_after_phase_b_decision") or {})
    readiness_gate = dict(context.get("phase_b_retest_readiness_gate") or {})
    transition = dict(context.get("transition") or {})
    baseline_revision = dict(context.get("baseline_revision") or {})
    validation = dict(context.get("baseline_v2_validation") or {})
    subset = dict(context.get("baseline_v2_subset") or {})
    watchlist = dict(context.get("baseline_v2_watchlist") or {})
    monitoring = dict(context.get("baseline_v2_watchlist_monitoring") or {})

    candidate_id = (
        _safe_str(monitoring.get("candidate_id"))
        or _safe_str(watchlist.get("candidate_id"))
        or _safe_str(subset.get("candidate_id"))
        or _safe_str(validation.get("candidate_id"))
        or _safe_str(baseline_revision.get("baseline_v2_candidate_selected"))
        or _safe_str(baseline_revision.get("candidate_id"))
    )
    if not candidate_id:
        candidate_id = "baseline_v2_hold3_with_trend_guard"

    active_baseline_status = "phase_a_active_baseline"
    project_closeout_status = _safe_str(dict(roadmap.get("phase_a_final_status") or {}).get("status")) or "unknown"
    phase_b_status = (
        _safe_str(phase_b_closeout.get("phase_b_final_status"))
        or _safe_str(project_after_phase_b.get("phase_b_final_status"))
        or _safe_str(phase_b_next.get("phase_b_status"))
        or _safe_str(roadmap_latest.get("phase_b_status"))
    )
    phase_c_decision = (
        _safe_str(project_after_phase_b.get("phase_c_decision"))
        or _safe_str(phase_b_next.get("phase_c_decision"))
        or _safe_str(roadmap_latest.get("phase_c_decision"))
    )
    recommended_next_action = (
        _safe_str(phase_b_closeout.get("recommended_primary_next_step"))
        or _safe_str(project_after_phase_b.get("recommended_primary_next_step"))
        or _safe_str(project_after_phase_b.get("recommended_next_action"))
        or _safe_str(phase_b_next.get("recommended_next_action"))
        or "stop_and_collect_more_data_then_redesign_framework"
    )
    readiness_status = _safe_str(readiness_gate.get("final_decision")) or "belum_boleh_retest"

    redesign_only_candidate = _safe_str(validation.get("decision")) == "candidate_usable_for_framework_redesign_only"
    recommended_tickers = (
        dedupe(
            [
                *_list_strings(monitoring.get("recommended_tickers")),
                *_list_strings(watchlist.get("recommended_tickers")),
                *_list_strings(subset.get("recommended_tickers")),
            ]
        )
        if redesign_only_candidate
        else []
    )
    recommended_groups = (
        dedupe(
            [
                *_list_strings(monitoring.get("recommended_groups")),
                *_list_strings(watchlist.get("recommended_groups")),
                *_list_strings(subset.get("recommended_groups")),
            ]
        )
        if redesign_only_candidate
        else []
    )

    payload = {
        "generated_at": _now_iso(),
        "project_state": "frozen_waiting_data_extension_and_framework_redesign",
        "roadmap_alignment_status": "aligned_to_project_roadmap_status",
        "active_operational_baseline": {
            "baseline_id": active_baseline_status,
            "source": str(Path(output_dir) / "phase_a_baseline_final.json"),
            "use_for_operations": True,
            "status_note": "Gunakan baseline aktif Phase A untuk operasional sampai ada bukti yang cukup untuk menggantinya.",
        },
        "experimental_baseline_candidate": {
            "candidate_id": candidate_id,
            "status": _safe_str(validation.get("decision")) or _safe_str(monitoring.get("decision")) or _safe_str(watchlist.get("decision")) or "keep_candidate_experimental",
            "scope": "framework_redesign_input_only",
            "promote_globally": False,
            "recommended_tickers": recommended_tickers,
            "recommended_groups": recommended_groups,
        },
        "phase_b": {
            "status": phase_b_status or "phase_b_closed_with_learnings_no_candidate",
            "retry_ready": False,
            "retry_scope_allowed": "none",
            "readiness_gate_status": readiness_status,
            "next_action": recommended_next_action,
            "reason": "Phase B retry tetap ditutup sampai data extension selesai, framework evaluasi diredesign, dan keputusan resmi baru diterbitkan.",
        },
        "phase_c": {
            "decision": phase_c_decision or "phase_c_no_go_yet",
            "can_start": False,
            "reason": "Phase C tetap no-go karena Phase B sudah ditutup tanpa kandidat strategi yang usable.",
        },
        "framework_redesign_status": {
            "baseline_redesign_status": _safe_str(baseline_revision.get("decision")),
            "candidate_validation_status": _safe_str(validation.get("decision")),
            "baseline_candidate_usable_for_redesign_only": bool(
                validation.get("decision") == "candidate_usable_for_framework_redesign_only"
                or validation.get("usable_for_framework_redesign_only")
            ),
            "data_extension_required_before_any_retry": True,
            "next_action": recommended_next_action,
        },
        "project_closeout_status": {
            "formal_closeout_status": project_closeout_status,
            "operational_freeze_allowed": True,
            "note": "Project dibekukan pada state operasional saat ini, walaupun closeout formal masih punya blocker runtime yang terpisah.",
        },
        "allowed_actions": [
            "Gunakan baseline aktif Phase A untuk operasional.",
            "Lanjutkan data extension dan refresh audit coverage/OOS secara berkala.",
            "Gunakan hasil redesign baseline hanya sebagai input redesign framework evaluasi.",
            "Refresh current-state summary setelah closeout/readiness artifacts diperbarui.",
        ],
        "forbidden_actions": [
            "Jangan retry item 5-8 secara global.",
            "Jangan promote baseline v2 menjadi baseline operasional global.",
            "Jangan promote candidate watchlist-only menjadi baseline operasional.",
            "Jangan mulai Phase C.",
            "Jangan hidupkan adaptive search space lagi.",
        ],
        "next_decision_gate": {
            "gate_id": "data_extension_and_framework_redesign_completion",
            "promote_condition": "Coverage data, OOS window, overlap audit, signal sparsity audit, dan baseline redesign usability sudah ditutup secara resmi.",
            "reject_condition": "Framework redesign membuktikan candidate redesign tetap tidak usable setelah data extension material.",
            "default_until_then": "keep_phase_b_closed_and_continue_data_extension",
        },
        "warnings": list(context.get("warnings") or []),
    }
    return payload


def _list_strings(value: object) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def build_current_state_text(payload: Dict[str, object]) -> str:
    active = dict(payload.get("active_operational_baseline") or {})
    candidate = dict(payload.get("experimental_baseline_candidate") or {})
    phase_b = dict(payload.get("phase_b") or {})
    phase_c = dict(payload.get("phase_c") or {})
    redesign = dict(payload.get("framework_redesign_status") or {})
    closeout = dict(payload.get("project_closeout_status") or {})

    lines = [
        "Project Current State Summary",
        "=============================",
        "",
        f"- Project state: {payload['project_state']}",
        f"- Roadmap alignment: {payload['roadmap_alignment_status']}",
        "",
        "Operational baseline:",
        f"- baseline_id={active.get('baseline_id')}",
        f"- use_for_operations={active.get('use_for_operations')}",
        f"- note={active.get('status_note')}",
        "",
        "Experimental candidate:",
        f"- candidate_id={candidate.get('candidate_id')}",
        f"- status={candidate.get('status')}",
        f"- scope={candidate.get('scope')}",
        f"- recommended_tickers={', '.join(list(candidate.get('recommended_tickers') or [])) or '-'}",
        f"- recommended_groups={', '.join(list(candidate.get('recommended_groups') or [])) or '-'}",
        "",
        "Phase gates:",
        f"- phase_b_status={phase_b.get('status')}",
        f"- phase_b_retry_ready={phase_b.get('retry_ready')}",
        f"- phase_b_readiness_gate_status={phase_b.get('readiness_gate_status')}",
        f"- phase_b_next_action={phase_b.get('next_action')}",
        f"- phase_c_decision={phase_c.get('decision')}",
        f"- phase_c_can_start={phase_c.get('can_start')}",
        "",
        "Framework redesign status:",
        f"- baseline_redesign_status={redesign.get('baseline_redesign_status')}",
        f"- candidate_validation_status={redesign.get('candidate_validation_status')}",
        f"- baseline_candidate_usable_for_redesign_only={redesign.get('baseline_candidate_usable_for_redesign_only')}",
        f"- data_extension_required_before_any_retry={redesign.get('data_extension_required_before_any_retry')}",
        f"- next_action={redesign.get('next_action')}",
        "",
        "Project closeout status:",
        f"- formal_closeout_status={closeout.get('formal_closeout_status')}",
        f"- operational_freeze_allowed={closeout.get('operational_freeze_allowed')}",
        f"- note={closeout.get('note')}",
        "",
        "Allowed actions:",
    ]
    for item in list(payload.get("allowed_actions") or []):
        lines.append(f"- {item}")
    lines.extend(["", "Forbidden actions:"])
    for item in list(payload.get("forbidden_actions") or []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "Next decision gate:",
            f"- gate_id={dict(payload.get('next_decision_gate') or {}).get('gate_id')}",
            f"- promote_condition={dict(payload.get('next_decision_gate') or {}).get('promote_condition')}",
            f"- reject_condition={dict(payload.get('next_decision_gate') or {}).get('reject_condition')}",
            f"- default_until_then={dict(payload.get('next_decision_gate') or {}).get('default_until_then')}",
        ]
    )
    return "\n".join(lines) + "\n"


def update_transition_artifact(output_dir: Path, payload: Dict[str, object]) -> Dict[str, object]:
    transition_path = Path(output_dir) / "phase_a_to_phase_b_transition.json"
    transition_payload, warnings = read_json_object(transition_path, "Phase A to Phase B transition JSON")
    if transition_payload is None:
        return {"updated": False, "path": str(transition_path), "warnings": warnings}

    phase_b = dict(payload.get("phase_b") or {})
    transition_payload["project_current_state_status"] = payload.get("project_state")
    transition_payload["project_current_state_next_action"] = phase_b.get("next_action")
    transition_payload["project_operational_baseline"] = dict(payload.get("active_operational_baseline") or {}).get("baseline_id")
    transition_payload["project_experimental_candidate"] = dict(payload.get("experimental_baseline_candidate") or {}).get("candidate_id")
    transition_payload["project_phase_b_retry_status"] = "not_ready"
    transition_payload["project_phase_c_status"] = dict(payload.get("phase_c") or {}).get("decision")
    transition_path.write_text(json.dumps(transition_payload, indent=2, ensure_ascii=True), encoding="utf-8")

    report_path = Path(output_dir) / "phase_a_to_phase_b_transition_report.txt"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    appendix = [
        "",
        "Project Current State Update:",
        f"- project_current_state_status: {payload.get('project_state')}",
        f"- project_current_state_next_action: {phase_b.get('next_action')}",
        f"- project_operational_baseline: {dict(payload.get('active_operational_baseline') or {}).get('baseline_id')}",
        f"- project_experimental_candidate: {dict(payload.get('experimental_baseline_candidate') or {}).get('candidate_id')}",
        "- project_phase_b_retry_status: not_ready",
        f"- project_phase_c_status: {dict(payload.get('phase_c') or {}).get('decision')}",
    ]
    report_path.write_text(report_text.rstrip() + "\n" + "\n".join(appendix) + "\n", encoding="utf-8")
    return {"updated": True, "path": str(transition_path), "report_path": str(report_path), "warnings": warnings}


def finalize_project_current_state(output_dir: Path) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_current_state_payload(output_dir=output_dir)
    summary_text = build_current_state_text(payload=payload)

    summary_json_path = output_dir / "project_current_state_summary.json"
    summary_txt_path = output_dir / "project_current_state_summary.txt"
    current_state_json_path = output_dir / "project_current_state.json"
    current_state_txt_path = output_dir / "project_current_state.txt"
    freeze_json_path = output_dir / "project_freeze_status.json"

    _write_json(summary_json_path, payload)
    _write_text(summary_txt_path, summary_text.splitlines())
    _write_json(current_state_json_path, payload)
    _write_text(current_state_txt_path, summary_text.splitlines())
    _write_json(
        freeze_json_path,
        {
            "generated_at": payload["generated_at"],
            "project_state": payload["project_state"],
            "active_operational_baseline": dict(payload.get("active_operational_baseline") or {}).get("baseline_id"),
            "experimental_candidate": dict(payload.get("experimental_baseline_candidate") or {}).get("candidate_id"),
            "phase_b_retry_ready": False,
            "phase_c_can_start": False,
            "next_action": dict(payload.get("phase_b") or {}).get("next_action"),
        },
    )
    transition_update = update_transition_artifact(output_dir=output_dir, payload=payload)

    return {
        "payload": payload,
        "summary_text": summary_text,
        "transition_update": transition_update,
        "artifacts": {
            "project_current_state_summary_json": str(summary_json_path),
            "project_current_state_summary_txt": str(summary_txt_path),
            "project_current_state_json": str(current_state_json_path),
            "project_current_state_txt": str(current_state_txt_path),
            "project_freeze_status_json": str(freeze_json_path),
        },
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze the current project state from roadmap and execution artifacts.")
    parser.add_argument("--output-dir", default="output", help="Directory containing project artifacts. Default: output")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = finalize_project_current_state(output_dir=Path(args.output_dir))
    payload = result["payload"]
    print(f"Project state: {payload['project_state']}")
    print(f"Next action: {dict(payload.get('phase_b') or {}).get('next_action')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
