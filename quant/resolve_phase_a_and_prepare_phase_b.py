"""Resolve Phase A gates and decide whether Phase B may start officially."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.audit_project_roadmap import (  # noqa: E402
    RepoInspector,
    build_phase_a_blockers,
    build_phase_a_final_status,
    build_roadmap_items,
)
from quant.ensure_phase_a_decision_artifacts import (  # noqa: E402
    ensure_phase_a_decision_artifacts,
)
from quant.evaluate_phase_a_real_data import (  # noqa: E402
    EvaluationCliError,
    evaluate_folder,
)
from quant.freeze_phase_a_baseline import freeze_phase_a_baseline  # noqa: E402
from quant.phase_a_transition_utils import (  # noqa: E402
    classify_closeout_artifact,
    dedupe,
    read_json_object,
)


class PhaseTransitionCliError(ValueError):
    """Friendly CLI error for the Phase A transition resolver."""


def load_item5_post_transition_status(output_dir: Path) -> Dict[str, object]:
    """Load optional post-limited-experiment item-5 decision artifacts."""

    path = Path(output_dir) / "phase_b_item5_go_no_go.json"
    payload, warnings = read_json_object(path, "Phase B item 5 go/no-go JSON")
    if payload is None:
        return {
            "available": False,
            "path": str(path),
            "item5_experiment_status": None,
            "item5_next_action": None,
            "decision": None,
            "warnings": warnings,
            "payload": None,
        }

    decision = str(payload.get("decision", "")).strip() or None
    status_map = {
        "no_go": ("failed", "stop"),
        "keep_experimental": ("mixed", "continue_tuning"),
        "promote_for_subset": ("promising", "promote_subset"),
        "promote_global": ("promising", "promote_global"),
    }
    experiment_status, next_action = status_map.get(decision, (None, None))
    return {
        "available": True,
        "path": str(path),
        "item5_experiment_status": experiment_status,
        "item5_next_action": next_action,
        "decision": decision,
        "warnings": warnings,
        "payload": payload,
    }


def load_item6_post_transition_status(output_dir: Path) -> Dict[str, object]:
    """Load optional post-limited-experiment item-6 artifacts."""

    go_no_go_path = Path(output_dir) / "phase_b_item6_go_no_go.json"
    summary_path = Path(output_dir) / "phase_b_item6_multitimeframe_summary.json"
    per_ticker_path = Path(output_dir) / "phase_b_item6_multitimeframe_per_ticker.csv"
    report_path = Path(output_dir) / "phase_b_item6_multitimeframe_report.txt"

    payload, warnings = read_json_object(go_no_go_path, "Phase B item 6 go/no-go JSON")
    if payload is not None:
        decision = str(payload.get("decision", "")).strip() or None
        status_map = {
            "no_go": ("failed", "stop"),
            "keep_experimental": ("mixed", "continue_tuning"),
            "promote_for_subset": ("promising", "promote_subset"),
            "promote_global": ("promising", "promote_global"),
        }
        experiment_status, next_action = status_map.get(
            decision,
            (None, str(payload.get("next_action", "")).strip() or None),
        )
        return {
            "available": True,
            "path": str(go_no_go_path),
            "item6_experiment_status": experiment_status,
            "item6_next_action": next_action,
            "decision": decision,
            "warnings": warnings,
            "payload": payload,
        }

    partial_artifacts_exist = any(path.exists() for path in [summary_path, per_ticker_path, report_path])
    return {
        "available": partial_artifacts_exist,
        "path": str(go_no_go_path),
        "item6_experiment_status": "running" if partial_artifacts_exist else "pending",
        "item6_next_action": "run_experiment" if not partial_artifacts_exist else "await_decision",
        "decision": None,
        "warnings": warnings,
        "payload": None,
    }


def load_item7_post_transition_status(output_dir: Path) -> Dict[str, object]:
    """Load optional post-limited-experiment item-7 artifacts."""

    go_no_go_path = Path(output_dir) / "phase_b_item7_go_no_go.json"
    summary_path = Path(output_dir) / "phase_b_item7_sentiment_momentum_summary.json"
    per_ticker_path = Path(output_dir) / "phase_b_item7_sentiment_momentum_per_ticker.csv"
    report_path = Path(output_dir) / "phase_b_item7_sentiment_momentum_report.txt"

    payload, warnings = read_json_object(go_no_go_path, "Phase B item 7 go/no-go JSON")
    if payload is not None:
        decision = str(payload.get("decision", "")).strip() or None
        raw_status = str(payload.get("experiment_status", "")).strip() or "completed"
        status_map = {
            "no_go": ("failed", "stop"),
            "keep_experimental": ("mixed", "continue_tuning"),
            "promote_for_subset": ("promising", "promote_subset"),
            "promote_global": ("promising", "promote_global"),
        }
        experiment_status, next_action = status_map.get(
            decision,
            (raw_status, str(payload.get("next_action", "")).strip() or None),
        )
        if raw_status in {"pending", "running"}:
            experiment_status = raw_status
            next_action = str(payload.get("next_action", "")).strip() or None
        return {
            "available": True,
            "path": str(go_no_go_path),
            "item7_experiment_status": experiment_status,
            "item7_next_action": next_action,
            "decision": decision,
            "warnings": warnings,
            "payload": payload,
        }

    partial_artifacts_exist = any(path.exists() for path in [summary_path, per_ticker_path, report_path])
    return {
        "available": partial_artifacts_exist,
        "path": str(go_no_go_path),
        "item7_experiment_status": "running" if partial_artifacts_exist else "pending",
        "item7_next_action": "run_experiment" if not partial_artifacts_exist else "await_decision",
        "decision": None,
        "warnings": warnings,
        "payload": None,
    }


def load_item8_post_transition_status(output_dir: Path) -> Dict[str, object]:
    """Load optional post-limited-experiment item-8 artifacts."""

    go_no_go_path = Path(output_dir) / "phase_b_item8_go_no_go.json"
    summary_path = Path(output_dir) / "phase_b_item8_global_summary.json"
    results_path = Path(output_dir) / "phase_b_item8_adaptive_results.csv"
    best_ticker_path = Path(output_dir) / "phase_b_item8_best_config_per_ticker.csv"
    report_path = Path(output_dir) / "phase_b_item8_recommendations.txt"

    payload, warnings = read_json_object(go_no_go_path, "Phase B item 8 go/no-go JSON")
    if payload is not None:
        decision = str(payload.get("decision", "")).strip() or None
        status_map = {
            "no_go": ("failed", "stop"),
            "keep_experimental": ("mixed", "continue_tuning"),
            "promote_for_subset": ("promising", "promote_subset"),
            "promote_ticker_specific": ("promising", "promote_ticker_specific"),
            "promote_group_specific": ("promising", "promote_group_specific"),
        }
        experiment_status, next_action = status_map.get(
            decision,
            (
                str(payload.get("item8_experiment_status", "")).strip()
                or str(payload.get("experiment_status", "")).strip()
                or None,
                str(payload.get("item8_next_action", "")).strip()
                or str(payload.get("next_action", "")).strip()
                or None,
            ),
        )
        return {
            "available": True,
            "path": str(go_no_go_path),
            "item8_experiment_status": experiment_status,
            "item8_next_action": next_action,
            "decision": decision,
            "warnings": warnings,
            "payload": payload,
        }

    partial_artifacts_exist = any(path.exists() for path in [summary_path, results_path, best_ticker_path, report_path])
    return {
        "available": partial_artifacts_exist,
        "path": str(go_no_go_path),
        "item8_experiment_status": "running" if partial_artifacts_exist else "pending",
        "item8_next_action": "run_experiment" if not partial_artifacts_exist else "await_decision",
        "decision": None,
        "warnings": warnings,
        "payload": None,
    }


def _now_iso() -> str:
    """Return a stable UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def refresh_baseline_artifact(
    output_dir: Path,
    closeout_status_file: Optional[Path] = None,
) -> Dict[str, object]:
    """Refresh the baseline freeze and summarize the result."""

    try:
        artifacts = freeze_phase_a_baseline(
            output_dir=Path(output_dir),
            closeout_status_file=closeout_status_file,
        )
    except Exception as exc:  # pragma: no cover - defensive
        path = Path(output_dir) / "phase_a_baseline_final.json"
        return {
            "path": str(path),
            "artifact_status": "invalid",
            "refresh_status": "failed",
            "available": path.exists(),
            "valid": False,
            "baseline_status": "draft",
            "readiness_status": "partially_ready",
            "usable_for_limited_experiment": False,
            "final_for_full_start": False,
            "strict_mode_final": False,
            "warnings": [f"Baseline freeze failed: {exc}"],
            "payload": None,
        }

    payload = dict(artifacts.get("baseline_payload") or {})
    baseline_status = str(payload.get("baseline_status", "draft")).strip().lower() or "draft"
    readiness_status = str(payload.get("readiness_status", "partially_ready")).strip().lower() or "partially_ready"
    strict_code = str(payload.get("strict_mode_decision_code", "")).strip()

    return {
        "path": str(artifacts["baseline_json"]),
        "artifact_status": "valid",
        "refresh_status": "passed",
        "available": True,
        "valid": True,
        "baseline_status": baseline_status,
        "readiness_status": readiness_status,
        "usable_for_limited_experiment": baseline_status in {"provisional", "final"},
        "final_for_full_start": baseline_status == "final",
        "strict_mode_final": strict_code in {"strict_default_yes", "strict_default_no"},
        "warnings": list(payload.get("warnings") or []),
        "payload": payload,
        "gate_report_path": str(artifacts.get("gate_report_path")) if artifacts.get("gate_report_path") else None,
    }


def determine_transition_decision(
    phase_a_final_status: Dict[str, object],
    decision_status: Dict[str, object],
    baseline_artifact: Dict[str, object],
    closeout_artifact: Dict[str, object],
) -> Dict[str, object]:
    """Determine whether the repo is blocked by environment, artifact, or ready to start."""

    environment_blockers = list(closeout_artifact.get("environment_blockers") or [])
    artifact_blockers: List[str] = []
    remaining_notes: List[str] = []
    artifact_gate_ready = (
        decision_status["threshold_decision_valid"]
        and decision_status["tuning_decision_valid"]
        and baseline_artifact["usable_for_limited_experiment"]
        and closeout_artifact["readable"]
    )

    if not decision_status["threshold_decision_valid"]:
        artifact_blockers.append("Threshold decision artifact belum valid.")
    if not decision_status["tuning_decision_valid"]:
        artifact_blockers.append("Tuning decision artifact belum valid.")
    if baseline_artifact["baseline_status"] == "draft":
        artifact_blockers.append("Baseline freeze masih draft.")
    if not closeout_artifact["readable"]:
        artifact_blockers.append("Closeout artifact belum cukup untuk dibaca.")

    for item in list(closeout_artifact.get("artifact_blockers") or []):
        normalized = str(item).lower()
        if "baseline" in normalized and baseline_artifact["baseline_status"] in {"provisional", "final"}:
            continue
        if "strict mode" in normalized and baseline_artifact["strict_mode_final"]:
            continue
        if "threshold decision" in normalized and decision_status["threshold_decision_valid"]:
            continue
        if "tuning decision" in normalized and decision_status["tuning_decision_valid"]:
            continue
        remaining_notes.append(item)
    if environment_blockers:
        remaining_notes.extend(
            f"Runtime closeout masih pending untuk full_start: {item}" for item in environment_blockers
        )
    if not closeout_artifact["tests_clean"]:
        remaining_notes.append("Test suite inti belum clean untuk full_start.")
    if baseline_artifact["baseline_status"] != "final":
        remaining_notes.append("Baseline belum final, jadi transisi maksimal hanya limited_experiment.")

    if environment_blockers and not artifact_gate_ready:
        remaining_blockers = dedupe([*environment_blockers, *artifact_blockers])
        return {
            "transition_status": "blocked",
            "transition_reason": "Transisi diblokir oleh masalah environment/runtime yang membuat closeout tidak bisa divalidasi penuh.",
            "blocked_type": "blocked_environment",
            "phase_b_entry_allowed": False,
            "phase_b_entry_mode": "blocked",
            "remaining_blockers": remaining_blockers,
            "remaining_notes": dedupe(remaining_notes),
        }

    if artifact_blockers:
        return {
            "transition_status": "blocked",
            "transition_reason": "Transisi diblokir karena artifact/gate Fase A belum cukup kuat.",
            "blocked_type": "blocked_artifact",
            "phase_b_entry_allowed": False,
            "phase_b_entry_mode": "blocked",
            "remaining_blockers": dedupe(artifact_blockers),
            "remaining_notes": dedupe(remaining_notes),
        }

    if (
        baseline_artifact["final_for_full_start"]
        and closeout_artifact["supports_final"]
        and closeout_artifact["tests_clean"]
        and phase_a_final_status["status"] in {"closed", "closed_with_notes"}
        and decision_status["threshold_artifact"]["sufficient_for_full_start"]
        and decision_status["tuning_artifact"]["sufficient_for_full_start"]
    ):
        return {
            "transition_status": "full_start",
            "transition_reason": "Fase A sudah closed/closed_with_notes dengan baseline final dan closeout clean.",
            "blocked_type": None,
            "phase_b_entry_allowed": True,
            "phase_b_entry_mode": "full_start",
            "remaining_blockers": [],
            "remaining_notes": dedupe(remaining_notes),
        }

    if artifact_gate_ready:
        return {
            "transition_status": "limited_experiment",
            "transition_reason": (
                "Decision artifact lengkap dan baseline minimal provisional, sehingga item 5 boleh masuk mode "
                "limited_experiment walau closeout runtime penuh belum final."
            ),
            "blocked_type": None,
            "phase_b_entry_allowed": True,
            "phase_b_entry_mode": "limited_experiment",
            "remaining_blockers": [],
            "remaining_notes": dedupe(remaining_notes),
        }

    return {
        "transition_status": "blocked",
        "transition_reason": "Transisi belum memenuhi syarat eksplisit untuk limited_experiment maupun full_start.",
        "blocked_type": "blocked_artifact",
        "phase_b_entry_allowed": False,
        "phase_b_entry_mode": "blocked",
        "remaining_blockers": ["Status transisi belum bisa diklasifikasikan sebagai limited_experiment atau full_start."],
        "remaining_notes": dedupe(remaining_notes),
    }


def build_phase_b_item5_entry_gate(
    output_dir: Path,
    transition_decision: Dict[str, object],
    decision_status: Dict[str, object],
    baseline_artifact: Dict[str, object],
    closeout_artifact: Dict[str, object],
) -> Dict[str, object]:
    """Build and persist the dedicated item-5 gate artifact."""

    prerequisites_satisfied: List[str] = []
    remaining_notes: List[str] = list(transition_decision.get("remaining_notes") or [])

    if decision_status["threshold_decision_valid"]:
        prerequisites_satisfied.append("Threshold decision artifact valid.")
    if decision_status["tuning_decision_valid"]:
        prerequisites_satisfied.append("Tuning decision artifact valid.")
    if baseline_artifact["baseline_status"] in {"provisional", "final"}:
        prerequisites_satisfied.append(
            f"Baseline sudah {baseline_artifact['baseline_status']}."
        )
    if closeout_artifact["readable"]:
        prerequisites_satisfied.append("Closeout artifact dapat dibaca.")
    if not closeout_artifact["environment_blockers"]:
        prerequisites_satisfied.append("Tidak ada blocker environment keras dari closeout.")

    allowed = transition_decision["phase_b_entry_mode"] in {"limited_experiment", "full_start"}
    gate_payload = {
        "generated_at": _now_iso(),
        "allowed": allowed,
        "mode": transition_decision["phase_b_entry_mode"] if allowed else "blocked",
        "reason": (
            "Item 5 boleh dijalankan sebagai eksperimen resmi default-off."
            if allowed
            else transition_decision["transition_reason"]
        ),
        "prerequisites_satisfied": prerequisites_satisfied,
        "remaining_notes": dedupe(remaining_notes),
        "remaining_blockers": list(transition_decision.get("remaining_blockers") or []),
    }

    path = Path(output_dir) / "phase_b_item5_entry_gate.json"
    path.write_text(json.dumps(gate_payload, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"Saved item 5 entry gate JSON to {path}")
    return {
        "path": str(path),
        "payload": gate_payload,
    }


def maybe_run_phase_b_item5_experiment(
    output_dir: Path,
    data_dir: Path,
    baseline_config: Path,
    metadata_file: Optional[Path],
    item5_gate: Dict[str, object],
    candle_volume_confirmation_threshold: float,
    hold_period: int,
    allow_overlap: bool,
) -> Dict[str, object]:
    """Run the official measured experiment for Phase B item 5 when the gate allows it."""

    command = (
        "python3 -m quant.evaluate_phase_a_real_data "
        f"--data-dir {shlex.quote(str(data_dir))} "
        f"--output-dir {shlex.quote(str(output_dir))} "
        f"--baseline-config {shlex.quote(str(baseline_config))} "
        "--require-candle-volume-confirmation "
        f"--candle-volume-confirmation-threshold {float(candle_volume_confirmation_threshold):.2f}"
    )
    if metadata_file is not None:
        command = f"{command} --metadata-file {shlex.quote(str(metadata_file))}"
    if hold_period != 5:
        command = f"{command} --hold-period {hold_period}"
    if allow_overlap:
        command = f"{command} --allow-overlap"

    result = {
        "eligible_to_run": bool(item5_gate["payload"]["allowed"]),
        "execution_status": "skipped",
        "reason": "",
        "command": command,
        "artifacts": {
            "per_ticker_csv": str(output_dir / "phase_b_item5_candle_confirmation_per_ticker.csv"),
            "summary_json": str(output_dir / "phase_b_item5_candle_confirmation_summary.json"),
            "report_txt": str(output_dir / "phase_b_item5_candle_confirmation_report.txt"),
        },
    }

    if not item5_gate["payload"]["allowed"]:
        result["reason"] = "Gate item 5 belum terbuka."
        return result

    if not Path(data_dir).exists():
        result["reason"] = f"Data directory tidak ditemukan: {data_dir}."
        return result

    if not Path(baseline_config).exists():
        result["reason"] = f"Baseline config tidak ditemukan: {baseline_config}."
        return result

    try:
        evaluate_folder(
            folder_path=data_dir,
            output_dir=output_dir,
            baseline_config=baseline_config,
            metadata_file=metadata_file,
            hold_period=hold_period,
            allow_overlap=allow_overlap,
            require_candle_volume_confirmation=True,
            candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
        )
    except EvaluationCliError as exc:
        result["execution_status"] = "failed"
        result["reason"] = str(exc)
        return result
    except Exception as exc:  # pragma: no cover - defensive
        result["execution_status"] = "failed"
        result["reason"] = f"Unexpected experiment failure: {exc}"
        return result

    result["execution_status"] = "executed"
    result["reason"] = "Eksperimen item 5 berhasil dijalankan dan artifact terukur sudah ditulis."
    return result


def resolve_phase_a_and_prepare_phase_b(
    output_dir: Path,
    data_dir: Path,
    metadata_file: Optional[Path] = None,
    candle_volume_confirmation_threshold: float = 1.0,
    hold_period: int = 5,
    allow_overlap: bool = False,
) -> Dict[str, object]:
    """Run the full Phase A -> Phase B transition workflow."""

    project_root = Path(__file__).resolve().parent.parent
    output_dir = Path(output_dir)
    data_dir = Path(data_dir)

    decision_result = ensure_phase_a_decision_artifacts(
        output_dir=output_dir,
        data_dir=data_dir,
        metadata_file=metadata_file,
        hold_period=hold_period,
        allow_overlap=allow_overlap,
        build_missing=True,
    )
    decision_status = decision_result["status_payload"]

    closeout_artifact = classify_closeout_artifact(output_dir=output_dir)
    baseline_artifact = refresh_baseline_artifact(
        output_dir=output_dir,
        closeout_status_file=Path(closeout_artifact["path"]),
    )

    inspector = RepoInspector(root=project_root)
    roadmap_items = build_roadmap_items(
        inspector=inspector,
        output_dir=output_dir,
        baseline_payload=baseline_artifact.get("payload"),
        closeout_payload=closeout_artifact.get("payload"),
    )
    phase_a_final_status = build_phase_a_final_status(
        roadmap_items=roadmap_items,
        baseline_payload=baseline_artifact.get("payload"),
        closeout_payload=closeout_artifact.get("payload"),
        inspector=inspector,
    )
    blockers_df, next_steps = build_phase_a_blockers(
        final_status=phase_a_final_status,
        baseline_payload=baseline_artifact.get("payload"),
        closeout_payload=closeout_artifact.get("payload"),
    )

    transition_decision = determine_transition_decision(
        phase_a_final_status=phase_a_final_status,
        decision_status=decision_status,
        baseline_artifact=baseline_artifact,
        closeout_artifact=closeout_artifact,
    )
    required_minimum_actions = dedupe(
        list(decision_status.get("next_action") or [])
        + list(next_steps)
    )

    item5_gate = build_phase_b_item5_entry_gate(
        output_dir=output_dir,
        transition_decision=transition_decision,
        decision_status=decision_status,
        baseline_artifact=baseline_artifact,
        closeout_artifact=closeout_artifact,
    )
    baseline_config = Path(baseline_artifact["path"])
    item5_result = maybe_run_phase_b_item5_experiment(
        output_dir=output_dir,
        data_dir=data_dir,
        baseline_config=baseline_config,
        metadata_file=metadata_file,
        item5_gate=item5_gate,
        candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )
    item5_post_status = load_item5_post_transition_status(output_dir=output_dir)
    item6_post_status = load_item6_post_transition_status(output_dir=output_dir)
    item7_post_status = load_item7_post_transition_status(output_dir=output_dir)
    item8_post_status = load_item8_post_transition_status(output_dir=output_dir)

    transition_payload = {
        "generated_at": _now_iso(),
        "phase_a_status": phase_a_final_status["status"],
        "transition_status": transition_decision["transition_status"],
        "transition_reason": transition_decision["transition_reason"],
        "blocked_type": transition_decision["blocked_type"],
        "phase_b_entry_allowed": transition_decision["phase_b_entry_allowed"],
        "phase_b_entry_mode": transition_decision["phase_b_entry_mode"],
        "remaining_blockers": transition_decision["remaining_blockers"],
        "required_minimum_actions": required_minimum_actions,
        "item5_gate": item5_gate["payload"],
        "item5_experiment_status": item5_post_status["item5_experiment_status"],
        "item5_next_action": item5_post_status["item5_next_action"],
        "item6_experiment_status": item6_post_status["item6_experiment_status"],
        "item6_next_action": item6_post_status["item6_next_action"],
        "item7_experiment_status": item7_post_status["item7_experiment_status"],
        "item7_next_action": item7_post_status["item7_next_action"],
        "item8_experiment_status": item8_post_status["item8_experiment_status"],
        "item8_next_action": item8_post_status["item8_next_action"],
        "phase_a_resolution": {
            "decision_artifacts": {
                "status_file": str(decision_result["status_path"]),
                "report_file": str(decision_result["report_path"]),
                "threshold_artifact": decision_status["threshold_artifact"],
                "tuning_artifact": decision_status["tuning_artifact"],
            },
            "baseline_artifact": baseline_artifact,
            "closeout_artifact": closeout_artifact,
        },
        "phase_a_final_status": phase_a_final_status,
        "transition_decision": transition_decision,
        "minimum_blockers": blockers_df.to_dict(orient="records"),
        "next_steps": next_steps,
        "phase_b_item5_entry_gate": item5_gate["payload"],
        "phase_b_item5_official_experiment": item5_result,
        "phase_b_item5_post_transition_status": item5_post_status,
        "phase_b_item6_post_transition_status": item6_post_status,
        "phase_b_item7_post_transition_status": item7_post_status,
        "phase_b_item8_post_transition_status": item8_post_status,
    }

    report_lines = [
        "Phase A To Phase B Transition",
        "=============================",
        "",
        f"- Generated at: {transition_payload['generated_at']}",
        f"- Phase A status: {transition_payload['phase_a_status']}",
        f"- Transition status: {transition_payload['transition_status']}",
        f"- Transition reason: {transition_payload['transition_reason']}",
        f"- Blocked type: {transition_payload['blocked_type'] or 'none'}",
        f"- Phase B entry allowed: {transition_payload['phase_b_entry_allowed']}",
        f"- Phase B entry mode: {transition_payload['phase_b_entry_mode']}",
        "",
        "Artifact checks:",
        f"- Threshold decision valid: {decision_status['threshold_decision_valid']}",
        f"- Tuning decision valid: {decision_status['tuning_decision_valid']}",
        f"- Baseline status: {baseline_artifact['baseline_status']}",
        f"- Closeout interpreted status: {closeout_artifact['interpreted_status']}",
        f"- Closeout readable: {closeout_artifact['readable']}",
        f"- Closeout tests clean: {closeout_artifact['tests_clean']}",
    ]

    if transition_payload["remaining_blockers"]:
        report_lines.extend(["", "Remaining blockers:"])
        for item in transition_payload["remaining_blockers"]:
            report_lines.append(f"- {item}")

    if required_minimum_actions:
        report_lines.extend(["", "Required minimum actions:"])
        for item in required_minimum_actions:
            report_lines.append(f"- {item}")

    item5_payload = item5_gate["payload"]
    report_lines.extend(
        [
            "",
            "Phase B Item 5 Entry Gate:",
            f"- Allowed: {item5_payload['allowed']}",
            f"- Mode: {item5_payload['mode']}",
            f"- Reason: {item5_payload['reason']}",
            f"- Experiment status: {item5_post_status['item5_experiment_status'] or 'not_available'}",
            f"- Next action: {item5_post_status['item5_next_action'] or 'not_available'}",
            f"- Item 6 experiment status: {item6_post_status['item6_experiment_status'] or 'pending'}",
            f"- Item 6 next action: {item6_post_status['item6_next_action'] or 'run_experiment'}",
            f"- Item 7 experiment status: {item7_post_status['item7_experiment_status'] or 'pending'}",
            f"- Item 7 next action: {item7_post_status['item7_next_action'] or 'run_experiment'}",
            f"- Item 8 experiment status: {item8_post_status['item8_experiment_status'] or 'pending'}",
            f"- Item 8 next action: {item8_post_status['item8_next_action'] or 'run_experiment'}",
        ]
    )
    if item5_payload["remaining_notes"]:
        report_lines.append("- Remaining notes:")
        for item in item5_payload["remaining_notes"]:
            report_lines.append(f"  - {item}")

    report_lines.extend(
        [
            "",
            "Phase B Item 5 Execution:",
            f"- Execution status: {item5_result['execution_status']}",
            f"- Reason: {item5_result['reason']}",
            f"- Command: {item5_result['command']}",
        ]
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "phase_a_to_phase_b_transition.json"
    report_path = output_dir / "phase_a_to_phase_b_transition_report.txt"
    json_path.write_text(json.dumps(transition_payload, indent=2, ensure_ascii=True), encoding="utf-8")
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"Saved transition decision JSON to {json_path}")
    print(f"Saved transition decision report to {report_path}")

    return {
        "transition_payload": transition_payload,
        "json_path": json_path,
        "report_path": report_path,
        "item5_gate_path": item5_gate["path"],
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Resolve official Phase A -> Phase B transition status."
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory containing and receiving Phase A artifacts. Default: output",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing per-ticker OHLCV CSV files for the optional item-5 run. Default: data",
    )
    parser.add_argument(
        "--metadata-file",
        default=None,
        help="Optional ticker metadata CSV used by baseline overrides and evaluator output.",
    )
    parser.add_argument(
        "--candle-volume-confirmation-threshold",
        type=float,
        default=1.0,
        help="Minimum volume_ratio used if the official item-5 experiment is executed. Default: 1.0",
    )
    parser.add_argument(
        "--hold-period",
        type=int,
        default=5,
        help="Holding period used by the official item-5 experiment. Default: 5",
    )
    parser.add_argument(
        "--allow-overlap",
        action="store_true",
        help="Allow overlapping trades if the official item-5 experiment is executed.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)

    try:
        result = resolve_phase_a_and_prepare_phase_b(
            output_dir=Path(args.output_dir),
            data_dir=Path(args.data_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            candle_volume_confirmation_threshold=args.candle_volume_confirmation_threshold,
            hold_period=args.hold_period,
            allow_overlap=args.allow_overlap,
        )
    except PhaseTransitionCliError as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        print(f"Unexpected transition resolution failure: {exc}")
        return 1

    payload = result["transition_payload"]
    print(f"Phase A status: {payload['phase_a_status']}")
    print(f"Transition status: {payload['transition_status']}")
    print(f"Phase B entry mode: {payload['phase_b_entry_mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
