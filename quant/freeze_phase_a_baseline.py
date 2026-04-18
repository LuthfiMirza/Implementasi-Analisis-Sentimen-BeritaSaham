"""Freeze the current Phase A baseline from threshold/tuning artifacts."""

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

from quant.phase_a_baseline import (  # noqa: E402
    DEFAULT_PHASE_A_BASELINE,
    merge_baseline_defaults,
)
from quant.phase_a_transition_utils import classify_closeout_artifact  # noqa: E402


class FreezeBaselineCliError(ValueError):
    """Friendly CLI error for the baseline freeze script."""


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_bool(value: object, default: bool) -> bool:
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


def _safe_dict(value: object) -> Dict[str, object]:
    return value if isinstance(value, dict) else {}


def _read_optional_json(path: Path, label: str) -> Tuple[Optional[Dict[str, object]], List[str]]:
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


def _read_optional_csv(path: Path, label: str) -> Tuple[Optional[pd.DataFrame], List[str]]:
    warnings: List[str] = []
    target = Path(path)
    if not target.exists():
        warnings.append(f"{label} not found: {target}.")
        return None, warnings
    if not target.is_file():
        warnings.append(f"{label} is not a file: {target}.")
        return None, warnings

    try:
        frame = pd.read_csv(target)
    except pd.errors.EmptyDataError:
        warnings.append(f"{label} is empty: {target}.")
        return None, warnings
    except pd.errors.ParserError as exc:
        warnings.append(f"{label} CSV parser error in {target}: {exc}.")
        return None, warnings
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"Failed to read {label} {target}: {exc}.")
        return None, warnings

    if frame.empty:
        warnings.append(f"{label} contains no rows: {target}.")
        return None, warnings

    return frame, warnings


def _strict_mode_from_tuning(tuning_payload: Optional[Dict[str, object]]) -> Tuple[bool, str, List[str]]:
    warnings: List[str] = []
    if not tuning_payload:
        warnings.append("Tuning decision not available. strict_mode_default falls back to false.")
        return False, "strict_default_not_available", warnings

    strict_decision = _safe_dict(tuning_payload.get("strict_mode_decision"))
    decision_code = str(strict_decision.get("decision_code", "")).strip()
    if decision_code == "strict_default_yes":
        return True, decision_code, warnings
    if decision_code == "strict_default_no":
        return False, decision_code, warnings
    if decision_code == "strict_only_for_subset":
        warnings.append(
            "Strict mode is only supported for a subset according to the tuning layer. "
            "Baseline strict_mode_default remains false."
        )
        return False, decision_code, warnings

    warnings.append("Strict mode decision is unavailable or ambiguous. strict_mode_default falls back to false.")
    return False, "strict_default_not_available", warnings


def _default_threshold_from_threshold_sweep(
    threshold_payload: Optional[Dict[str, object]],
) -> Tuple[float, Dict[str, object], List[str]]:
    warnings: List[str] = []
    default_decision = _safe_dict(
        _safe_dict(threshold_payload).get("default_threshold_decision")
    )
    selected = default_decision.get("selected_default_threshold")
    if selected is None:
        warnings.append("Threshold sweep decision not available. default_volume_spike_threshold falls back to 2.0.")
        return 2.0, default_decision, warnings
    return _safe_float(selected, 2.0), default_decision, warnings


def _group_overrides_from_best_by_group(
    best_by_group_df: Optional[pd.DataFrame],
    default_threshold: float,
) -> Tuple[List[Dict[str, object]], List[str]]:
    warnings: List[str] = []
    if best_by_group_df is None or best_by_group_df.empty:
        return [], warnings

    required = {"group_field", "group_value", "best_threshold"}
    if not required.issubset(best_by_group_df.columns):
        warnings.append(
            "Best-by-group CSV is present but missing required columns. Group overrides are skipped."
        )
        return [], warnings

    overrides: List[Dict[str, object]] = []
    for _, row in best_by_group_df.iterrows():
        sample_status = str(row.get("sample_status", "")).strip().lower()
        confidence = str(row.get("decision_confidence", "")).strip().lower()
        threshold = _safe_float(row.get("best_threshold"), default_threshold)

        if sample_status not in {"", "enough_sample"}:
            continue
        if confidence == "low":
            continue
        if abs(threshold - default_threshold) < 1e-9:
            continue

        overrides.append(
            {
                "group_field": str(row.get("group_field")),
                "group_value": str(row.get("group_value")),
                "threshold": threshold,
                "decision_confidence": confidence or "moderate",
                "sample_status": sample_status or "enough_sample",
                "source": "phase_a_threshold_best_by_group.csv",
            }
        )

    return overrides, warnings


def _baseline_gate_assessment(
    threshold_payload: Optional[Dict[str, object]],
    tuning_payload: Optional[Dict[str, object]],
    default_decision: Dict[str, object],
) -> Dict[str, object]:
    threshold_readiness = _safe_dict(threshold_payload).get("readiness", {})
    threshold_status = str(_safe_dict(threshold_readiness).get("status", "")).strip().lower()
    tuning_readiness = _safe_dict(tuning_payload).get("ready_for_phase_b", {})
    tuning_status = str(_safe_dict(tuning_readiness).get("status", "")).strip().lower()

    strict_code = str(
        _safe_dict(_safe_dict(tuning_payload).get("strict_mode_decision")).get("decision_code", "")
    ).strip()
    threshold_confidence = str(default_decision.get("decision_confidence", "")).strip().lower()
    selected_threshold = default_decision.get("selected_default_threshold")

    provisional_requirements = [
        "Threshold decision memilih default threshold yang eksplisit.",
        "Threshold decision memiliki readiness.status.",
        "Tuning decision memiliki strict_mode_decision.decision_code.",
        "Tuning decision memiliki ready_for_phase_b.status.",
    ]
    provisional_missing: List[str] = []
    if selected_threshold is None:
        provisional_missing.append("Threshold decision belum memilih default threshold yang eksplisit.")
    if not threshold_status:
        provisional_missing.append("Threshold decision belum memiliki readiness.status.")
    if not strict_code:
        provisional_missing.append("Tuning decision belum memiliki strict_mode_decision.decision_code.")
    if not tuning_status:
        provisional_missing.append("Tuning decision belum memiliki ready_for_phase_b.status.")

    provisional_ready = not provisional_missing
    final_requirements = [
        "Baseline minimal sudah provisional.",
        "Threshold readiness sudah ready.",
        "Tuning readiness sudah ready.",
        "Strict mode decision sudah final (strict_default_yes / strict_default_no).",
        "Threshold confidence minimal moderate.",
        "Closeout artifact mendukung finalisasi baseline.",
    ]
    final_missing: List[str] = []
    if not provisional_ready:
        final_missing.append("Artifact keputusan belum cukup untuk menaikkan baseline ke provisional.")
    if threshold_status != "ready":
        final_missing.append("Threshold readiness belum ready.")
    if tuning_status != "ready":
        final_missing.append("Tuning readiness belum ready.")
    if strict_code not in {"strict_default_yes", "strict_default_no"}:
        final_missing.append("Strict mode decision belum final.")
    if threshold_confidence not in {"moderate", "strong"}:
        final_missing.append("Threshold confidence belum cukup kuat untuk final.")

    if provisional_ready:
        baseline_status = "provisional"
        baseline_status_reason = (
            "Threshold/tuning decision artifacts sudah usable, tetapi closeout/support final belum lengkap."
        )
    else:
        baseline_status = "draft"
        baseline_status_reason = (
            "Artifact keputusan belum cukup, jadi baseline masih draft."
        )

    return {
        "baseline_status": baseline_status,
        "baseline_status_reason": baseline_status_reason,
        "provisional_requirements": provisional_requirements,
        "provisional_missing": provisional_missing,
        "provisional_ready": provisional_ready,
        "final_requirements": final_requirements,
        "final_missing": final_missing,
        "threshold_status": threshold_status or None,
        "tuning_status": tuning_status or None,
        "strict_code": strict_code or None,
        "threshold_confidence": threshold_confidence or None,
    }


def freeze_phase_a_baseline(
    output_dir: Path,
    threshold_decision_file: Optional[Path] = None,
    tuning_decision_file: Optional[Path] = None,
    best_by_group_file: Optional[Path] = None,
    best_by_ticker_file: Optional[Path] = None,
    closeout_status_file: Optional[Path] = None,
) -> Dict[str, object]:
    """Freeze the current Phase A baseline into one JSON payload and report."""

    output_dir = Path(output_dir)
    threshold_decision_path = Path(
        threshold_decision_file or output_dir / "phase_a_threshold_decision.json"
    )
    tuning_decision_path = Path(
        tuning_decision_file or output_dir / "phase_a_tuning_decision.json"
    )
    best_by_group_path = Path(
        best_by_group_file or output_dir / "phase_a_threshold_best_by_group.csv"
    )
    best_by_ticker_path = Path(
        best_by_ticker_file or output_dir / "phase_a_threshold_best_by_ticker.csv"
    )
    closeout_status_path = Path(
        closeout_status_file or output_dir / "phase_a_closeout_status.json"
    )

    warnings: List[str] = []
    decision_sources: List[str] = []

    threshold_payload, threshold_warnings = _read_optional_json(
        threshold_decision_path,
        "Threshold decision JSON",
    )
    warnings.extend(threshold_warnings)
    if threshold_payload:
        decision_sources.append(str(threshold_decision_path))

    tuning_payload, tuning_warnings = _read_optional_json(
        tuning_decision_path,
        "Tuning decision JSON",
    )
    warnings.extend(tuning_warnings)
    if tuning_payload:
        decision_sources.append(str(tuning_decision_path))

    best_by_group_df, group_warnings = _read_optional_csv(
        best_by_group_path,
        "Threshold best-by-group CSV",
    )
    warnings.extend(group_warnings)
    if best_by_group_df is not None:
        decision_sources.append(str(best_by_group_path))

    best_by_ticker_df, ticker_warnings = _read_optional_csv(
        best_by_ticker_path,
        "Threshold best-by-ticker CSV",
    )
    warnings.extend(ticker_warnings)
    if best_by_ticker_df is not None:
        decision_sources.append(str(best_by_ticker_path))

    default_threshold, default_decision, threshold_default_warnings = _default_threshold_from_threshold_sweep(
        threshold_payload
    )
    warnings.extend(threshold_default_warnings)
    strict_mode_default, strict_decision_code, strict_warnings = _strict_mode_from_tuning(
        tuning_payload
    )
    warnings.extend(strict_warnings)

    adaptive_payload = _safe_dict(_safe_dict(threshold_payload).get("adaptive_threshold_by_group"))
    adaptive_enabled = _safe_bool(adaptive_payload.get("supported"), False) or (
        str(
            _safe_dict(_safe_dict(tuning_payload).get("default_threshold_decision")).get(
                "decision_code", ""
            )
        ).strip()
        == "adaptive_threshold_by_group"
    )

    group_overrides, override_warnings = _group_overrides_from_best_by_group(
        best_by_group_df,
        default_threshold,
    )
    warnings.extend(override_warnings)
    if adaptive_enabled and not group_overrides:
        warnings.append(
            "Adaptive threshold is indicated by artifacts, but no confident group override could be frozen yet."
        )

    min_trades_floor = _safe_float(
        _safe_dict(_safe_dict(threshold_payload).get("config")).get("min_trades"),
        DEFAULT_PHASE_A_BASELINE["min_trades_floor"],
    )

    threshold_readiness = str(
        _safe_dict(_safe_dict(threshold_payload).get("readiness")).get("status", "")
    ).strip()
    tuning_readiness = str(
        _safe_dict(_safe_dict(tuning_payload).get("ready_for_phase_b")).get("status", "")
    ).strip()
    readiness_status = threshold_readiness or tuning_readiness or "partially_ready"

    baseline_gate = _baseline_gate_assessment(
        threshold_payload=threshold_payload,
        tuning_payload=tuning_payload,
        default_decision=default_decision,
    )
    closeout_support = classify_closeout_artifact(
        output_dir=output_dir,
        closeout_status_file=closeout_status_path,
    )
    warnings.extend(list(closeout_support.get("warnings") or []))
    closeout_support_status = str(closeout_support["interpreted_status"])
    closeout_support_reason = (
        "Closeout artifact mendukung finalisasi baseline."
        if closeout_support["supports_final"]
        else (
            "Closeout artifact terbaca tetapi belum cukup untuk finalisasi baseline."
            if closeout_support["readable"]
            else "Closeout artifact belum tersedia atau belum bisa dibaca."
        )
    )

    final_missing = list(baseline_gate["final_missing"])
    if not closeout_support["supports_final"]:
        if closeout_support["interpreted_status"] == "blocked_environment":
            final_missing.append("Closeout runtime masih blocked_environment, jadi baseline belum bisa final.")
        elif closeout_support["readable"]:
            final_missing.append("Closeout artifact belum mendukung kenaikan baseline ke final.")
        else:
            final_missing.append("Closeout artifact belum bisa dibaca untuk mendukung finalisasi baseline.")

    if baseline_gate["provisional_ready"] and not final_missing:
        baseline_status = "final"
        baseline_status_reason = "Decision artifacts lengkap dan closeout mendukung, jadi baseline final."
    else:
        baseline_status = str(baseline_gate["baseline_status"])
        baseline_status_reason = str(baseline_gate["baseline_status_reason"])

    remaining_gate_blockers = (
        list(baseline_gate["provisional_missing"])
        if baseline_status == "draft"
        else final_missing
    )

    best_threshold_counts: Dict[str, int] = {}
    if best_by_ticker_df is not None and not best_by_ticker_df.empty and "best_threshold" in best_by_ticker_df.columns:
        counts = (
            best_by_ticker_df["best_threshold"]
            .map(lambda value: f"{_safe_float(value, default_threshold):.1f}")
            .value_counts()
            .sort_index()
        )
        best_threshold_counts = {key: int(value) for key, value in counts.items()}

    baseline_payload = merge_baseline_defaults(
        {
            "default_volume_spike_threshold": default_threshold,
            "strict_mode_default": strict_mode_default,
            "adaptive_threshold_enabled": adaptive_enabled and bool(group_overrides),
            "group_threshold_overrides": group_overrides,
            "min_trades_floor": int(min_trades_floor),
            "readiness_status": readiness_status or "partially_ready",
            "baseline_status": baseline_status,
            "decision_source": decision_sources,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "strict_mode_decision_code": strict_decision_code,
            "baseline_status_reason": baseline_status_reason,
            "threshold_decision_confidence": default_decision.get("decision_confidence"),
            "threshold_decision_margin": default_decision.get("decision_margin"),
            "selected_threshold_mode": default_decision.get("mode"),
            "best_threshold_counts": best_threshold_counts,
            "closeout_support_status": closeout_support_status,
            "closeout_support_reason": closeout_support_reason,
            "provisional_requirements": list(baseline_gate["provisional_requirements"]),
            "provisional_requirements_met": bool(baseline_gate["provisional_ready"]),
            "provisional_missing_requirements": list(baseline_gate["provisional_missing"]),
            "final_requirements": list(baseline_gate["final_requirements"]),
            "final_requirements_met": bool(baseline_status == "final"),
            "final_missing_requirements": final_missing,
            "remaining_gate_blockers": remaining_gate_blockers,
            "warnings": warnings,
        }
    )

    lines = [
        "Phase A Baseline Freeze",
        "=======================",
        "",
        f"- Baseline status: {baseline_payload['baseline_status']}",
        f"- Readiness status: {baseline_payload['readiness_status']}",
        f"- Default threshold: {baseline_payload['default_volume_spike_threshold']}",
        f"- Strict mode default: {baseline_payload['strict_mode_default']}",
        f"- Adaptive threshold enabled: {baseline_payload['adaptive_threshold_enabled']}",
        f"- Min trades floor: {baseline_payload['min_trades_floor']}",
        f"- Decision sources used: {', '.join(decision_sources) if decision_sources else 'none'}",
        "",
        "Reasoning:",
        f"- {baseline_status_reason}",
        f"- Closeout support: {closeout_support_status} | {closeout_support_reason}",
    ]

    if group_overrides:
        lines.extend(["", "Frozen group overrides:"])
        for item in group_overrides:
            lines.append(
                f"- {item['group_field']}={item['group_value']} -> threshold {item['threshold']} "
                f"({item['decision_confidence']})"
            )
    else:
        lines.extend(["", "Frozen group overrides:", "- none"])

    if best_threshold_counts:
        lines.extend(["", "Best-by-ticker threshold counts:"])
        for key, value in best_threshold_counts.items():
            lines.append(f"- threshold {key}: {value} ticker")

    if warnings:
        lines.extend(["", "Warnings:"])
        for item in warnings:
            lines.append(f"- {item}")

    report_text = "\n".join(lines) + "\n"
    gate_lines = [
        "Phase A Baseline Gate",
        "=====================",
        "",
        f"- Current baseline status: {baseline_payload['baseline_status']}",
        f"- Reason: {baseline_payload['baseline_status_reason']}",
        f"- Closeout support status: {closeout_support_status}",
        f"- Closeout support reason: {closeout_support_reason}",
        "",
        "Minimum requirements to reach provisional:",
    ]
    for item in baseline_payload["provisional_requirements"]:
        gate_lines.append(f"- {item}")
    if baseline_payload["provisional_missing_requirements"]:
        gate_lines.append("- Missing now:")
        for item in baseline_payload["provisional_missing_requirements"]:
            gate_lines.append(f"  - {item}")
    else:
        gate_lines.append("- Missing now: none")

    gate_lines.extend(["", "Minimum requirements to reach final:"])
    for item in baseline_payload["final_requirements"]:
        gate_lines.append(f"- {item}")
    if baseline_payload["final_missing_requirements"]:
        gate_lines.append("- Missing now:")
        for item in baseline_payload["final_missing_requirements"]:
            gate_lines.append(f"  - {item}")
    else:
        gate_lines.append("- Missing now: none")

    if baseline_payload["remaining_gate_blockers"]:
        gate_lines.extend(["", "Remaining gate blockers:"])
        for item in baseline_payload["remaining_gate_blockers"]:
            gate_lines.append(f"- {item}")
    else:
        gate_lines.extend(["", "Remaining gate blockers:", "- none"])

    gate_report_text = "\n".join(gate_lines) + "\n"

    output_dir.mkdir(parents=True, exist_ok=True)
    baseline_json = output_dir / "phase_a_baseline_final.json"
    baseline_json.write_text(
        json.dumps(baseline_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    report_path = output_dir / "phase_a_baseline_report.txt"
    report_path.write_text(report_text, encoding="utf-8")
    gate_report_path = output_dir / "phase_a_baseline_gate_report.txt"
    gate_report_path.write_text(gate_report_text, encoding="utf-8")

    print(f"Saved frozen baseline JSON to {baseline_json}")
    print(f"Saved baseline report to {report_path}")
    print(f"Saved baseline gate report to {gate_report_path}")

    return {
        "baseline_payload": baseline_payload,
        "report_text": report_text,
        "gate_report_text": gate_report_text,
        "warnings": warnings,
        "baseline_json": baseline_json,
        "report_path": report_path,
        "gate_report_path": gate_report_path,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Freeze the current Phase A baseline from threshold and tuning artifacts."
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory containing and receiving Phase A artifacts. Default: output",
    )
    parser.add_argument(
        "--threshold-decision-file",
        default=None,
        help="Optional threshold decision JSON path. Default: output/phase_a_threshold_decision.json",
    )
    parser.add_argument(
        "--tuning-decision-file",
        default=None,
        help="Optional tuning decision JSON path. Default: output/phase_a_tuning_decision.json",
    )
    parser.add_argument(
        "--best-by-group-file",
        default=None,
        help="Optional threshold best-by-group CSV path. Default: output/phase_a_threshold_best_by_group.csv",
    )
    parser.add_argument(
        "--best-by-ticker-file",
        default=None,
        help="Optional threshold best-by-ticker CSV path. Default: output/phase_a_threshold_best_by_ticker.csv",
    )
    parser.add_argument(
        "--closeout-status-file",
        default=None,
        help="Optional closeout status JSON path. Default: output/phase_a_closeout_status.json",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)
    try:
        freeze_phase_a_baseline(
            output_dir=Path(args.output_dir),
            threshold_decision_file=Path(args.threshold_decision_file)
            if args.threshold_decision_file
            else None,
            tuning_decision_file=Path(args.tuning_decision_file)
            if args.tuning_decision_file
            else None,
            best_by_group_file=Path(args.best_by_group_file) if args.best_by_group_file else None,
            best_by_ticker_file=Path(args.best_by_ticker_file)
            if args.best_by_ticker_file
            else None,
            closeout_status_file=Path(args.closeout_status_file)
            if args.closeout_status_file
            else None,
        )
    except FreezeBaselineCliError as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        print(f"Unexpected baseline freeze failure: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
