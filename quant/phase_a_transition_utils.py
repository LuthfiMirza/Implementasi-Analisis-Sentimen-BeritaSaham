"""Shared helpers for Phase A decision artifacts, closeout, and transition gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


VALID_CLOSEOUT_STATUSES = {"closed", "closed_with_notes", "partially_ready", "blocked"}
VALID_BASELINE_STATUSES = {"draft", "provisional", "final"}
FULL_START_TEST_STATUSES = {"passed"}
ENVIRONMENT_ERROR_KEYWORDS = [
    "sqlstate",
    "operation not permitted",
    "connection refused",
    "refused",
    "timed out",
    "timeout",
    "access denied",
    "mysql",
    "database",
    "could not connect",
    "host:",
    "port:",
]


def safe_dict(value: object) -> Dict[str, object]:
    """Return a dict or an empty dict."""

    return value if isinstance(value, dict) else {}


def dedupe(items: Sequence[str]) -> List[str]:
    """Deduplicate ordered strings."""

    seen = set()
    ordered: List[str] = []
    for item in items:
        token = str(item).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def read_json_object(path: Path, label: str) -> Tuple[Optional[Dict[str, object]], List[str]]:
    """Load one JSON object with warnings instead of raising."""

    warnings: List[str] = []
    target = Path(path)
    if not target.exists():
        warnings.append(f"{label} not found: {target}.")
        return None, warnings
    if not target.is_file():
        warnings.append(f"{label} is not a file: {target}.")
        return None, warnings

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        warnings.append(f"{label} contains invalid JSON ({target}: {exc}).")
        return None, warnings
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"Failed to read {label} {target}: {exc}.")
        return None, warnings

    if not isinstance(payload, dict):
        warnings.append(f"{label} {target} does not contain a JSON object.")
        return None, warnings

    return payload, warnings


def validate_threshold_artifact(output_dir: Path) -> Dict[str, object]:
    """Validate the threshold sweep decision artifact."""

    path = Path(output_dir) / "phase_a_threshold_decision.json"
    payload, warnings = read_json_object(path, "Threshold decision JSON")
    if payload is None:
        return {
            "path": str(path),
            "artifact_status": "missing" if not path.exists() else "invalid",
            "available": False,
            "valid": False,
            "readiness_status": None,
            "selected_default_threshold": None,
            "decision_confidence": None,
            "sufficient_for_minimum_gate": False,
            "sufficient_for_full_start": False,
            "warnings": warnings,
            "blocking_reasons": ["Threshold sweep real artifact belum tersedia atau tidak valid."],
            "payload": None,
        }

    default_decision = safe_dict(payload.get("default_threshold_decision"))
    readiness = safe_dict(payload.get("readiness"))
    selected_default_threshold = default_decision.get("selected_default_threshold")
    readiness_status = str(readiness.get("status", "")).strip().lower() or None
    decision_confidence = str(default_decision.get("decision_confidence", "")).strip().lower() or None

    blocking_reasons: List[str] = []
    if selected_default_threshold is None:
        blocking_reasons.append("Threshold decision belum memilih default threshold yang eksplisit.")
    if readiness_status is None:
        blocking_reasons.append("Threshold decision belum memiliki readiness.status.")

    return {
        "path": str(path),
        "artifact_status": "valid" if not blocking_reasons else "not_ready",
        "available": True,
        "valid": not blocking_reasons,
        "readiness_status": readiness_status,
        "selected_default_threshold": selected_default_threshold,
        "decision_confidence": decision_confidence,
        "sufficient_for_minimum_gate": selected_default_threshold is not None and readiness_status is not None,
        "sufficient_for_full_start": readiness_status == "ready",
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
        "payload": payload,
    }


def validate_tuning_artifact(output_dir: Path) -> Dict[str, object]:
    """Validate the tuning decision artifact."""

    path = Path(output_dir) / "phase_a_tuning_decision.json"
    payload, warnings = read_json_object(path, "Tuning decision JSON")
    if payload is None:
        return {
            "path": str(path),
            "artifact_status": "missing" if not path.exists() else "invalid",
            "available": False,
            "valid": False,
            "readiness_status": None,
            "strict_mode_decision_code": None,
            "strict_mode_final": False,
            "sufficient_for_minimum_gate": False,
            "sufficient_for_full_start": False,
            "warnings": warnings,
            "blocking_reasons": ["Tuning decision real belum tersedia atau tidak valid."],
            "payload": None,
        }

    strict_mode_decision = safe_dict(payload.get("strict_mode_decision"))
    readiness = safe_dict(payload.get("ready_for_phase_b"))
    strict_mode_decision_code = str(strict_mode_decision.get("decision_code", "")).strip() or None
    readiness_status = str(readiness.get("status", "")).strip().lower() or None
    strict_mode_final = strict_mode_decision_code in {"strict_default_yes", "strict_default_no"}

    blocking_reasons: List[str] = []
    if strict_mode_decision_code is None:
        blocking_reasons.append("Tuning decision belum memiliki strict_mode_decision.decision_code.")
    if readiness_status is None:
        blocking_reasons.append("Tuning decision belum memiliki ready_for_phase_b.status.")

    return {
        "path": str(path),
        "artifact_status": "valid" if not blocking_reasons else "not_ready",
        "available": True,
        "valid": not blocking_reasons,
        "readiness_status": readiness_status,
        "strict_mode_decision_code": strict_mode_decision_code,
        "strict_mode_final": strict_mode_final,
        "sufficient_for_minimum_gate": strict_mode_decision_code is not None and readiness_status is not None,
        "sufficient_for_full_start": readiness_status == "ready" and strict_mode_final,
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
        "payload": payload,
    }


def _is_environment_message(message: object) -> bool:
    """Return True when a closeout message points to infra/runtime issues."""

    text = str(message).strip().lower()
    if not text:
        return False
    return any(keyword in text for keyword in ENVIRONMENT_ERROR_KEYWORDS)


def classify_closeout_artifact(output_dir: Path, closeout_status_file: Optional[Path] = None) -> Dict[str, object]:
    """Classify closeout output into environment/artifact/finalization buckets."""

    path = Path(closeout_status_file or Path(output_dir) / "phase_a_closeout_status.json")
    payload, warnings = read_json_object(path, "Phase A closeout status JSON")
    if payload is None:
        return {
            "path": str(path),
            "artifact_status": "missing" if not path.exists() else "invalid",
            "available": False,
            "valid": False,
            "closeout_status": None,
            "raw_status": None,
            "interpreted_status": "blocked_artifact",
            "readable": False,
            "ojk_runtime_validated": False,
            "macro_runtime_validated": False,
            "runtime_validated": False,
            "tests_clean": False,
            "tests": {"python_status": None, "php_status": None},
            "environment_blockers": [],
            "artifact_blockers": ["Closeout artifact belum tersedia atau tidak valid."],
            "remaining_blockers": ["Closeout artifact belum tersedia atau tidak valid."],
            "notes": [],
            "warnings": warnings,
            "supports_limited_experiment": False,
            "supports_final": False,
            "payload": None,
        }

    raw_status = str(payload.get("status", "")).strip().lower() or None
    ojk_backfill = safe_dict(payload.get("ojk_backfill"))
    macro_signal = safe_dict(payload.get("macro_regulatory_signal"))
    tests = safe_dict(payload.get("tests"))
    python_tests = safe_dict(tests.get("python"))
    php_tests = safe_dict(tests.get("php"))
    python_status = str(python_tests.get("status", "")).strip().lower() or None
    php_status = str(php_tests.get("status", "")).strip().lower() or None
    tests_clean = python_status in FULL_START_TEST_STATUSES and php_status in FULL_START_TEST_STATUSES

    blocking_items = [str(item) for item in list(payload.get("blocking_items") or [])]
    environment_blockers: List[str] = []
    artifact_blockers: List[str] = []

    if ojk_backfill.get("error"):
        environment_blockers.append(f"OJK runtime error: {ojk_backfill['error']}")
    if macro_signal.get("error"):
        environment_blockers.append(f"Macro runtime error: {macro_signal['error']}")

    for item in blocking_items:
        if _is_environment_message(item):
            environment_blockers.append(item)
        else:
            artifact_blockers.append(item)

    environment_blockers = dedupe(environment_blockers)
    artifact_blockers = dedupe(artifact_blockers)

    if raw_status not in VALID_CLOSEOUT_STATUSES:
        interpreted_status = "blocked_artifact"
        artifact_blockers = dedupe(
            [*artifact_blockers, f"Closeout status tidak dikenali: {raw_status or 'missing'}."]
        )
    elif environment_blockers:
        interpreted_status = "blocked_environment"
    elif raw_status == "blocked":
        interpreted_status = "blocked_artifact"
        if not artifact_blockers:
            artifact_blockers = ["Closeout masih blocked karena blocker non-environment."]
    else:
        interpreted_status = raw_status

    readable = raw_status in VALID_CLOSEOUT_STATUSES
    supports_limited_experiment = readable and not environment_blockers
    supports_final = readable and raw_status in {"closed", "closed_with_notes"} and not environment_blockers

    return {
        "path": str(path),
        "artifact_status": "valid" if raw_status in VALID_CLOSEOUT_STATUSES else "invalid",
        "available": True,
        "valid": raw_status in VALID_CLOSEOUT_STATUSES,
        "closeout_status": raw_status,
        "raw_status": raw_status,
        "interpreted_status": interpreted_status,
        "readable": readable,
        "ojk_runtime_validated": bool(ojk_backfill.get("ready")),
        "macro_runtime_validated": bool(macro_signal.get("ready")),
        "runtime_validated": bool(ojk_backfill.get("ready")) and bool(macro_signal.get("ready")),
        "tests_clean": tests_clean,
        "tests": {"python_status": python_status, "php_status": php_status},
        "environment_blockers": environment_blockers,
        "artifact_blockers": artifact_blockers,
        "remaining_blockers": dedupe([*environment_blockers, *artifact_blockers]),
        "notes": list(payload.get("notes") or []),
        "warnings": warnings,
        "supports_limited_experiment": supports_limited_experiment,
        "supports_final": supports_final,
        "payload": payload,
    }
