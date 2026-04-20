"""Finalize the formal Phase B strategy closeout after v9 segment OOS validation."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402


PHASE_B_FINAL_STATUS_VALUES = {
    "phase_b_closed_failed_strategy",
    "phase_b_closed_failed_due_to_data",
    "phase_b_closed_with_learnings_no_candidate",
    "phase_b_keep_one_candidate_experimental",
}
PRIMARY_NEXT_STEP_VALUES = {
    "stop_and_collect_more_data",
    "redesign_evaluation_framework",
    "stop_and_collect_more_data_then_redesign_framework",
}
PARKED_ITEMS = [
    "item5",
    "item6",
    "item7",
    "item8",
    "entry_relaxation_only",
    "volume_relaxed_entry",
    "exit_hold_only_redesign",
    "segment-only promotion for current candidate",
]
STILL_POSSIBLE_LATER = [
    "framework_redesign",
    "wider_data_collection",
    "re_labeled_evaluation_horizon",
    "universe_reconstruction",
]
TRACKED_JSON_ARTIFACTS = [
    ("project_roadmap_status", "project_roadmap_status.json"),
    ("baseline_root_cause_postmortem", "baseline_root_cause_postmortem.json"),
    ("baseline_next_experiment_plan", "baseline_next_experiment_plan.json"),
    ("baseline_v2_go_no_go", "baseline_v2_go_no_go.json"),
    ("baseline_v3_signal_rule_go_no_go", "baseline_v3_signal_rule_go_no_go.json"),
    ("baseline_v4_quality_gate_go_no_go", "baseline_v4_quality_gate_go_no_go.json"),
    ("baseline_v4_quality_gate_v2_go_no_go", "baseline_v4_quality_gate_v2_go_no_go.json"),
    ("baseline_v5_exit_hold_go_no_go", "baseline_v5_exit_hold_go_no_go.json"),
    ("baseline_v6_next_experiment_governance", "baseline_v6_next_experiment_governance.json"),
    ("baseline_v7_segment_aware_go_no_go", "baseline_v7_segment_aware_go_no_go.json"),
    ("baseline_v8_segment_only_validation_go_no_go", "baseline_v8_segment_only_validation_go_no_go.json"),
    ("baseline_v9_segment_oos_go_no_go", "baseline_v9_segment_oos_go_no_go.json"),
]
OPTIONAL_ITEM_ARTIFACTS = [
    ("phase_b_item5_go_no_go", "phase_b_item5_go_no_go.json"),
    ("phase_b_item6_go_no_go", "phase_b_item6_go_no_go.json"),
    ("phase_b_item7_go_no_go", "phase_b_item7_go_no_go.json"),
    ("phase_b_item8_go_no_go", "phase_b_item8_go_no_go.json"),
]
MATRIX_COLUMNS = [
    "artifact_id",
    "artifact_file",
    "artifact_available",
    "decision",
    "candidate_id",
    "recommended_next_action",
    "global_promotion_allowed",
    "survivor_signal",
    "final_survivor_after_v9",
    "summary_note",
]


class PhaseBStrategyCloseoutCliError(ValueError):
    """Friendly CLI error for Phase B strategy closeout."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: object) -> str:
    return str(value or "").strip()


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


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _load_optional_json(output_dir: Path, filename: str) -> Tuple[Dict[str, object], List[str], bool]:
    payload, warnings = read_json_object(Path(output_dir) / filename, filename)
    return safe_dict(payload), list(warnings), payload is not None


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _artifact_decision(payload: Dict[str, object]) -> str:
    for key in [
        "decision",
        "phase_b_status",
        "phase_b_final_status",
        "recommended_primary_direction",
        "recommended_guardrail_mode",
    ]:
        value = _safe_str(payload.get(key))
        if value:
            return value
    return "missing"


def _artifact_candidate(payload: Dict[str, object]) -> str:
    for key in [
        "candidate_id",
        "best_candidate_id",
        "best_rule",
        "baseline_v2_candidate_selected",
        "best_candidate",
    ]:
        value = _safe_str(payload.get(key))
        if value:
            return value
    return ""


def _artifact_next_action(payload: Dict[str, object]) -> str:
    for key in [
        "recommended_next_action",
        "next_action",
        "recommended_primary_direction",
        "suggested_experiment_id",
    ]:
        value = _safe_str(payload.get(key))
        if value:
            return value
    return ""


def _artifact_survivor_signal(artifact_id: str, payload: Dict[str, object]) -> bool:
    decision = _artifact_decision(payload)
    if artifact_id == "baseline_v7_segment_aware_go_no_go":
        return decision == "keep_experimental_for_segment_review"
    if artifact_id == "baseline_v8_segment_only_validation_go_no_go":
        return decision == "promote_to_segment_only_validation"
    if artifact_id == "baseline_v9_segment_oos_go_no_go":
        return decision in {
            "stay_promote_to_segment_only_validation",
            "keep_experimental_for_segment_only_use",
        }
    return decision in {
        "keep_experimental",
        "promote_global",
        "promote_for_subset",
        "promote_group_specific",
        "promote_ticker_specific",
    }


def _artifact_note(artifact_id: str, payload: Dict[str, object]) -> str:
    if artifact_id == "baseline_v9_segment_oos_go_no_go":
        return _safe_str(payload.get("recommended_next_action")) or "final_candidate_check"
    if artifact_id == "baseline_v8_segment_only_validation_go_no_go":
        return _safe_str(payload.get("primary_segment")) or "segment_only_validation"
    if artifact_id == "baseline_v7_segment_aware_go_no_go":
        return _safe_str(payload.get("tested_segment")) or "segment_review"
    notes = list(payload.get("decision_notes") or [])
    if notes:
        return _safe_str(notes[0])
    return _artifact_next_action(payload)


def _candidate_survivors(artifacts: Dict[str, Dict[str, object]]) -> List[str]:
    v9 = artifacts.get("baseline_v9_segment_oos_go_no_go", {})
    v8 = artifacts.get("baseline_v8_segment_only_validation_go_no_go", {})
    v7 = artifacts.get("baseline_v7_segment_aware_go_no_go", {})

    if v9:
        if _artifact_survivor_signal("baseline_v9_segment_oos_go_no_go", v9):
            candidate = _artifact_candidate(v9)
            return [candidate] if candidate else []
        return []
    if _artifact_survivor_signal("baseline_v8_segment_only_validation_go_no_go", v8):
        candidate = _artifact_candidate(v8)
        return [candidate] if candidate else []
    if _artifact_survivor_signal("baseline_v7_segment_aware_go_no_go", v7):
        candidate = _safe_str(v7.get("best_candidate_id"))
        return [candidate] if candidate else []
    return []


def _has_learnings(root_cause: Dict[str, object], next_plan: Dict[str, object]) -> bool:
    if list(root_cause.get("key_findings") or []):
        return True
    if list(root_cause.get("what_has_been_proven_not_to_work") or []):
        return True
    if list(next_plan.get("success_criteria") or []):
        return True
    return False


def _data_issue_dominant(
    *,
    root_cause: Dict[str, object],
    v9: Dict[str, object],
    warnings: Sequence[str],
) -> bool:
    bottleneck = safe_dict(root_cause.get("current_primary_bottleneck"))
    if _safe_str(bottleneck.get("data")) == "primary":
        return True
    if _safe_int(v9.get("primary_total_trades_sum"), 0) <= 3:
        return True
    warning_hits = sum(1 for item in warnings if "not found" in item.lower())
    return warning_hits >= 6 and not v9


def _framework_redesign_needed(
    root_cause: Dict[str, object],
    next_plan: Dict[str, object],
    governance: Dict[str, object],
) -> bool:
    primary_direction = _safe_str(root_cause.get("recommended_primary_direction"))
    if primary_direction in {
        "revisit_eligibility_and_sample_guardrails",
        "revisit_ticker_universe_segmentation",
    }:
        return True
    if _safe_str(governance.get("recommended_guardrail_mode")) == "move_to_segment_aware_guardrail":
        return True
    if list(next_plan.get("what_not_to_change") or []):
        return True
    return False


def _data_collection_needed(root_cause: Dict[str, object], v9: Dict[str, object]) -> bool:
    primary_trades = _safe_int(v9.get("primary_total_trades_sum"), 0)
    active_tickers = _safe_int(v9.get("primary_active_ticker_count"), 0)
    explorable = {str(item).strip() for item in list(root_cause.get("what_is_still_explorable") or [])}
    if primary_trades < 15:
        return True
    if active_tickers < 6:
        return True
    return "sample_sufficiency_redesign" in explorable or "universe_segmentation" in explorable


def _determine_phase_b_final_status(
    *,
    survivors: Sequence[str],
    root_cause: Dict[str, object],
    next_plan: Dict[str, object],
    v9: Dict[str, object],
    warnings: Sequence[str],
) -> str:
    if list(survivors):
        return "phase_b_keep_one_candidate_experimental"
    if _data_issue_dominant(root_cause=root_cause, v9=v9, warnings=warnings):
        return "phase_b_closed_failed_due_to_data"
    if _safe_str(v9.get("decision")) == "no_go_even_for_segment":
        if _has_learnings(root_cause=root_cause, next_plan=next_plan):
            return "phase_b_closed_with_learnings_no_candidate"
        return "phase_b_closed_failed_strategy"
    if _has_learnings(root_cause=root_cause, next_plan=next_plan):
        return "phase_b_closed_with_learnings_no_candidate"
    return "phase_b_closed_failed_strategy"


def _determine_primary_next_step(
    *,
    final_status: str,
    root_cause: Dict[str, object],
    next_plan: Dict[str, object],
    governance: Dict[str, object],
    v9: Dict[str, object],
) -> str:
    if final_status == "phase_b_closed_failed_due_to_data":
        return "stop_and_collect_more_data"

    need_data = _data_collection_needed(root_cause=root_cause, v9=v9)
    need_framework = _framework_redesign_needed(
        root_cause=root_cause,
        next_plan=next_plan,
        governance=governance,
    )

    if need_data and need_framework:
        return "stop_and_collect_more_data_then_redesign_framework"
    if need_framework:
        return "redesign_evaluation_framework"
    return "stop_and_collect_more_data"


def _determine_secondary_steps(primary_next_step: str) -> Tuple[str, str]:
    if primary_next_step == "stop_and_collect_more_data_then_redesign_framework":
        return (
            "freeze_strategy_experiment_track_and_keep_phase_c_closed",
            "prepare_framework_redesign_scope_after_data_extension",
        )
    if primary_next_step == "redesign_evaluation_framework":
        return (
            "freeze_strategy_experiment_track_and_keep_phase_c_closed",
            "prepare_universe_and_horizon_reconstruction_brief",
        )
    return (
        "freeze_strategy_experiment_track_and_keep_phase_c_closed",
        "prepare_data_extension_scope_without_new_strategy_tests",
    )


def _decisive_statement(
    *,
    final_status: str,
    primary_next_step: str,
) -> str:
    if final_status == "phase_b_keep_one_candidate_experimental":
        return (
            "Masih ada satu kandidat yang bisa dipertahankan secara eksperimental, tetapi Phase C tetap tidak boleh dibuka "
            "dan eksperimen strategi baru tetap tidak boleh dimulai sekarang."
        )
    if primary_next_step == "redesign_evaluation_framework":
        return (
            "Tidak ada kandidat yang stabil bahkan pada subset-aware OOS validation. Phase B ditutup sebagai gagal secara strategi, "
            "bukan karena coding belum selesai. Langkah berikutnya bukan eksperimen strategi baru, melainkan redesign framework evaluasi. "
            "Phase C tetap tidak boleh dibuka."
        )
    if primary_next_step == "stop_and_collect_more_data":
        return (
            "Tidak ada kandidat yang stabil bahkan pada subset-aware OOS validation. Phase B ditutup sebagai gagal secara strategi, "
            "bukan karena coding belum selesai. Langkah berikutnya bukan eksperimen strategi baru, melainkan pengumpulan data tambahan. "
            "Phase C tetap tidak boleh dibuka."
        )
    return (
        "Tidak ada kandidat yang stabil bahkan pada subset-aware OOS validation. Phase B ditutup sebagai gagal secara strategi, "
        "bukan karena coding belum selesai. Langkah berikutnya bukan eksperimen strategi baru, melainkan pengumpulan data tambahan "
        "dan redesign framework evaluasi. Phase C tetap tidak boleh dibuka."
    )


def _strategy_failed(final_status: str) -> bool:
    return final_status in {
        "phase_b_closed_failed_strategy",
        "phase_b_closed_with_learnings_no_candidate",
    }


def _build_status_matrix(
    *,
    artifacts: Dict[str, Dict[str, object]],
    availability: Dict[str, bool],
    filenames: Dict[str, str],
    survivors: Sequence[str],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    survivor_set = {str(item).strip() for item in list(survivors)}
    for artifact_id, filename in list(filenames.items()):
        payload = safe_dict(artifacts.get(artifact_id))
        candidate = _artifact_candidate(payload)
        rows.append(
            {
                "artifact_id": artifact_id,
                "artifact_file": filename,
                "artifact_available": bool(availability.get(artifact_id)),
                "decision": _artifact_decision(payload),
                "candidate_id": candidate,
                "recommended_next_action": _artifact_next_action(payload),
                "global_promotion_allowed": _safe_bool(payload.get("global_promotion_allowed")),
                "survivor_signal": _artifact_survivor_signal(artifact_id, payload),
                "final_survivor_after_v9": bool(candidate and candidate in survivor_set),
                "summary_note": _artifact_note(artifact_id, payload),
            }
        )
    return rows


def _write_status_matrix(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATRIX_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_closeout_payload(
    *,
    artifacts: Dict[str, Dict[str, object]],
    warnings: Sequence[str],
    final_status: str,
    primary_next_step: str,
    secondary_step_1: str,
    secondary_step_2: str,
    survivors: Sequence[str],
) -> Dict[str, object]:
    root_cause = safe_dict(artifacts.get("baseline_root_cause_postmortem"))
    next_plan = safe_dict(artifacts.get("baseline_next_experiment_plan"))
    v9 = safe_dict(artifacts.get("baseline_v9_segment_oos_go_no_go"))
    roadmap = safe_dict(artifacts.get("project_roadmap_status"))
    latest = safe_dict(roadmap.get("latest_execution_status"))
    decisive_statement = _decisive_statement(
        final_status=final_status,
        primary_next_step=primary_next_step,
    )

    return {
        "generated_at": _now_iso(),
        "phase_b_final_status": final_status,
        "phase_b_failed_as_strategy": _strategy_failed(final_status),
        "has_candidate_survivors": bool(list(survivors)),
        "candidate_survivors": list(survivors),
        "recommended_primary_next_step": primary_next_step,
        "recommended_secondary_step_1": secondary_step_1,
        "recommended_secondary_step_2": secondary_step_2,
        "parked_items": list(PARKED_ITEMS),
        "still_theoretically_possible_later_but_not_now": list(STILL_POSSIBLE_LATER),
        "can_continue_to_phase_c": False,
        "can_continue_strategy_experiments_now": False,
        "phase_c_status": _safe_str(latest.get("phase_c_decision")) or "phase_c_no_go_yet",
        "latest_candidate_terminal_status": _safe_str(v9.get("decision")) or "unknown",
        "current_candidate_terminal_action": _safe_str(v9.get("recommended_next_action")),
        "phase_b_strategy_summary": {
            "v2_decision": _artifact_decision(safe_dict(artifacts.get("baseline_v2_go_no_go"))),
            "v3_decision": _artifact_decision(safe_dict(artifacts.get("baseline_v3_signal_rule_go_no_go"))),
            "v4_decision": _artifact_decision(safe_dict(artifacts.get("baseline_v4_quality_gate_go_no_go"))),
            "v4_v2_decision": _artifact_decision(safe_dict(artifacts.get("baseline_v4_quality_gate_v2_go_no_go"))),
            "v5_decision": _artifact_decision(safe_dict(artifacts.get("baseline_v5_exit_hold_go_no_go"))),
            "v7_decision": _artifact_decision(safe_dict(artifacts.get("baseline_v7_segment_aware_go_no_go"))),
            "v8_decision": _artifact_decision(safe_dict(artifacts.get("baseline_v8_segment_only_validation_go_no_go"))),
            "v9_decision": _artifact_decision(v9),
        },
        "root_cause_snapshot": {
            "recommended_primary_direction": _safe_str(root_cause.get("recommended_primary_direction")),
            "recommended_secondary_direction_1": _safe_str(root_cause.get("recommended_secondary_direction_1")),
            "recommended_secondary_direction_2": _safe_str(root_cause.get("recommended_secondary_direction_2")),
            "what_to_stop": list(root_cause.get("what_to_stop") or []),
            "what_is_still_explorable": list(root_cause.get("what_is_still_explorable") or []),
        },
        "next_plan_snapshot": {
            "recommended_primary_direction": _safe_str(next_plan.get("recommended_primary_direction")),
            "suggested_experiment_id": _safe_str(next_plan.get("suggested_experiment_id")),
            "what_to_stop": list(next_plan.get("what_to_stop") or []),
            "what_not_to_change": list(next_plan.get("what_not_to_change") or []),
        },
        "final_candidate_assessment": {
            "candidate_id": _safe_str(v9.get("candidate_id")),
            "primary_segment": _safe_str(v9.get("primary_segment")),
            "decision": _safe_str(v9.get("decision")),
            "oos_stability_ok": _safe_bool(v9.get("oos_stability_ok")),
            "ticker_consistency_ok": _safe_bool(v9.get("ticker_consistency_ok")),
            "outlier_bias_ok": _safe_bool(v9.get("outlier_bias_ok"), True),
            "global_promotion_allowed": False,
            "primary_total_trades_sum": _safe_int(v9.get("primary_total_trades_sum")),
            "primary_active_ticker_count": _safe_int(v9.get("primary_active_ticker_count")),
            "primary_trade_weighted_average_return": v9.get("primary_trade_weighted_average_return"),
            "primary_mean_average_return_active": v9.get("primary_mean_average_return_active"),
            "supporting_segments_failed": list(v9.get("supporting_segments_failed") or []),
        },
        "decisive_statement": decisive_statement,
        "warnings": dedupe([str(item).strip() for item in list(warnings) if str(item).strip()]),
    }


def _build_closeout_text(payload: Dict[str, object]) -> List[str]:
    return [
        "Phase B Final Closeout",
        "=======================",
        "",
        f"- phase_b_final_status={payload.get('phase_b_final_status')}",
        f"- phase_b_failed_as_strategy={payload.get('phase_b_failed_as_strategy')}",
        f"- candidate_survivors={', '.join(payload.get('candidate_survivors') or []) or 'none'}",
        f"- recommended_primary_next_step={payload.get('recommended_primary_next_step')}",
        f"- recommended_secondary_step_1={payload.get('recommended_secondary_step_1')}",
        f"- recommended_secondary_step_2={payload.get('recommended_secondary_step_2')}",
        f"- can_continue_to_phase_c={payload.get('can_continue_to_phase_c')}",
        f"- can_continue_strategy_experiments_now={payload.get('can_continue_strategy_experiments_now')}",
        "",
        "Final candidate assessment:",
        f"- candidate_id={safe_dict(payload.get('final_candidate_assessment')).get('candidate_id')}",
        f"- primary_segment={safe_dict(payload.get('final_candidate_assessment')).get('primary_segment')}",
        f"- decision={safe_dict(payload.get('final_candidate_assessment')).get('decision')}",
        f"- primary_total_trades_sum={safe_dict(payload.get('final_candidate_assessment')).get('primary_total_trades_sum')}",
        f"- primary_active_ticker_count={safe_dict(payload.get('final_candidate_assessment')).get('primary_active_ticker_count')}",
        f"- primary_trade_weighted_average_return={safe_dict(payload.get('final_candidate_assessment')).get('primary_trade_weighted_average_return')}",
        f"- primary_mean_average_return_active={safe_dict(payload.get('final_candidate_assessment')).get('primary_mean_average_return_active')}",
        "",
        "Park permanently for now:",
        *[f"- {item}" for item in list(payload.get("parked_items") or [])],
        "",
        "Still theoretically possible later, but not now:",
        *[f"- {item}" for item in list(payload.get("still_theoretically_possible_later_but_not_now") or [])],
        "",
        "Decisive statement:",
        f"- {payload.get('decisive_statement')}",
    ]


def _build_project_decision_payload(closeout_payload: Dict[str, object]) -> Dict[str, object]:
    return {
        "generated_at": _now_iso(),
        "phase_b_final_status": closeout_payload.get("phase_b_final_status"),
        "recommended_primary_next_step": closeout_payload.get("recommended_primary_next_step"),
        "recommended_secondary_step_1": closeout_payload.get("recommended_secondary_step_1"),
        "recommended_secondary_step_2": closeout_payload.get("recommended_secondary_step_2"),
        "candidate_survivors": list(closeout_payload.get("candidate_survivors") or []),
        "parked_items": list(closeout_payload.get("parked_items") or []),
        "can_continue_to_phase_c": False,
        "can_continue_strategy_experiments_now": False,
        "decisive_statement": closeout_payload.get("decisive_statement"),
    }


def _build_project_decision_text(payload: Dict[str, object]) -> List[str]:
    return [
        "Project After Phase B Decision",
        "==============================",
        "",
        f"- phase_b_final_status={payload.get('phase_b_final_status')}",
        f"- recommended_primary_next_step={payload.get('recommended_primary_next_step')}",
        f"- recommended_secondary_step_1={payload.get('recommended_secondary_step_1')}",
        f"- recommended_secondary_step_2={payload.get('recommended_secondary_step_2')}",
        f"- candidate_survivors={', '.join(payload.get('candidate_survivors') or []) or 'none'}",
        f"- can_continue_to_phase_c={payload.get('can_continue_to_phase_c')}",
        f"- can_continue_strategy_experiments_now={payload.get('can_continue_strategy_experiments_now')}",
        "",
        "Parked items:",
        *[f"- {item}" for item in list(payload.get("parked_items") or [])],
        "",
        "Decisive statement:",
        f"- {payload.get('decisive_statement')}",
    ]


def finalize_phase_b_strategy_closeout(output_dir: Path) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    artifacts: Dict[str, Dict[str, object]] = {}
    availability: Dict[str, bool] = {}
    filenames: Dict[str, str] = {}
    warnings: List[str] = []

    for artifact_id, filename in [*TRACKED_JSON_ARTIFACTS, *OPTIONAL_ITEM_ARTIFACTS]:
        payload, item_warnings, available = _load_optional_json(output_dir=output_dir, filename=filename)
        artifacts[artifact_id] = payload
        availability[artifact_id] = available
        filenames[artifact_id] = filename
        warnings.extend(item_warnings)

    survivors = _candidate_survivors(artifacts=artifacts)
    root_cause = safe_dict(artifacts.get("baseline_root_cause_postmortem"))
    next_plan = safe_dict(artifacts.get("baseline_next_experiment_plan"))
    governance = safe_dict(artifacts.get("baseline_v6_next_experiment_governance"))
    v9 = safe_dict(artifacts.get("baseline_v9_segment_oos_go_no_go"))

    final_status = _determine_phase_b_final_status(
        survivors=survivors,
        root_cause=root_cause,
        next_plan=next_plan,
        v9=v9,
        warnings=warnings,
    )
    if final_status not in PHASE_B_FINAL_STATUS_VALUES:
        raise PhaseBStrategyCloseoutCliError("Invalid Phase B final status.")

    primary_next_step = _determine_primary_next_step(
        final_status=final_status,
        root_cause=root_cause,
        next_plan=next_plan,
        governance=governance,
        v9=v9,
    )
    if primary_next_step not in PRIMARY_NEXT_STEP_VALUES:
        raise PhaseBStrategyCloseoutCliError("Invalid recommended primary next step.")
    secondary_step_1, secondary_step_2 = _determine_secondary_steps(primary_next_step)

    matrix_rows = _build_status_matrix(
        artifacts=artifacts,
        availability=availability,
        filenames=filenames,
        survivors=survivors,
    )
    closeout_payload = _build_closeout_payload(
        artifacts=artifacts,
        warnings=warnings,
        final_status=final_status,
        primary_next_step=primary_next_step,
        secondary_step_1=secondary_step_1,
        secondary_step_2=secondary_step_2,
        survivors=survivors,
    )
    project_decision_payload = _build_project_decision_payload(closeout_payload=closeout_payload)

    closeout_json_path = output_dir / "phase_b_final_closeout.json"
    closeout_txt_path = output_dir / "phase_b_final_closeout.txt"
    matrix_csv_path = output_dir / "phase_b_strategy_status_matrix.csv"
    project_json_path = output_dir / "project_after_phase_b_decision.json"
    project_txt_path = output_dir / "project_after_phase_b_decision.txt"

    _write_json(closeout_json_path, closeout_payload)
    _write_text(closeout_txt_path, _build_closeout_text(closeout_payload))
    _write_status_matrix(matrix_csv_path, matrix_rows)
    _write_json(project_json_path, project_decision_payload)
    _write_text(project_txt_path, _build_project_decision_text(project_decision_payload))

    return {
        "phase_b_final_closeout": closeout_payload,
        "project_after_phase_b_decision": project_decision_payload,
        "status_matrix_rows": matrix_rows,
        "artifacts": {
            "phase_b_final_closeout_json": str(closeout_json_path),
            "phase_b_final_closeout_txt": str(closeout_txt_path),
            "phase_b_strategy_status_matrix_csv": str(matrix_csv_path),
            "project_after_phase_b_decision_json": str(project_json_path),
            "project_after_phase_b_decision_txt": str(project_txt_path),
        },
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize the formal Phase B strategy closeout without starting new experiments."
    )
    parser.add_argument("--output-dir", default="output", help="Artifact directory. Default: output")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = finalize_phase_b_strategy_closeout(output_dir=Path(args.output_dir))
    except PhaseBStrategyCloseoutCliError as exc:
        print(f"Phase B strategy closeout failed: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during Phase B strategy closeout: {exc}")
        return 1

    payload = result["project_after_phase_b_decision"]
    print("Phase B strategy closeout complete.")
    print(f"phase_b_final_status={payload['phase_b_final_status']}")
    print(f"recommended_primary_next_step={payload['recommended_primary_next_step']}")
    print(f"can_continue_to_phase_c={payload['can_continue_to_phase_c']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
