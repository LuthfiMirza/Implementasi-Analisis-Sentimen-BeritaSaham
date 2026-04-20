"""Generate a focused baseline redesign v4 plan after v2/v3 failures."""

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


HYPOTHESIS_COLUMNS = [
    "hypothesis_id",
    "redesign_focus",
    "target_problem",
    "expected_benefit",
    "main_risk",
    "estimated_complexity",
    "recommended_priority",
    "should_test_next",
]

ARTIFACT_MAP = {
    "project_current_state": "project_current_state.json",
    "baseline_v2_go_no_go": "baseline_v2_go_no_go.json",
    "baseline_v2_validation": "baseline_v2_validation.json",
    "baseline_v2_best_candidate": "baseline_v2_best_candidate.json",
    "baseline_v3_signal_rule_go_no_go": "baseline_v3_signal_rule_go_no_go.json",
    "baseline_v3_signal_rule_summary": "baseline_v3_signal_rule_summary.json",
    "project_roadmap_status": "project_roadmap_status.json",
}


class BaselineV4RedesignPlanCliError(ValueError):
    """Friendly CLI error for baseline redesign v4 planning."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _sanitize_for_json(value: object) -> object:
    if isinstance(value, dict):
        return {key: _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize_for_json(payload), indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_context(output_dir: Path) -> Tuple[Dict[str, Dict[str, object]], List[str]]:
    payloads: Dict[str, Dict[str, object]] = {}
    warnings: List[str] = []
    for key, filename in ARTIFACT_MAP.items():
        payload, item_warnings = read_json_object(Path(output_dir) / filename, filename)
        payloads[key] = payload if isinstance(payload, dict) else {}
        warnings.extend(item_warnings)
    return payloads, dedupe(warnings)


def _extract_latest_roadmap(context: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    return safe_dict(safe_dict(context.get("project_roadmap_status")).get("latest_execution_status"))


def _build_hypothesis_matrix() -> pd.DataFrame:
    rows = [
        {
            "hypothesis_id": "candidate_a_fast_anchor_quality_gate",
            "redesign_focus": "Fast entry anchor + post-entry quality gate",
            "target_problem": (
                "EMA20 berhasil membuka coverage, tetapi quality trade runtuh karena anchor cepat "
                "memasukkan candle/trend lemah tanpa filter kualitas lanjutan."
            ),
            "expected_benefit": (
                "Menjaga coverage dari fast trend anchor sambil memangkas trade noise lewat gate kualitas "
                "seperti candle strength, body-to-range ratio, volatility floor, dan price confirmation."
            ),
            "main_risk": "Gate kualitas terlalu ketat dan coverage kembali collapse ke <3 ticker eligible.",
            "estimated_complexity": "medium",
            "recommended_priority": "high",
            "should_test_next": True,
        },
        {
            "hypothesis_id": "candidate_b_simple_entry_exit_hold_redesign",
            "redesign_focus": "Keep entry simple, redesign exit/hold",
            "target_problem": (
                "Trade tambahan dari anchor cepat mungkin tidak semuanya buruk; sebagian bisa rusak karena "
                "hold_period=3 terlalu kaku dan exit tidak menangkap follow-through yang benar."
            ),
            "expected_benefit": (
                "Meningkatkan average return tanpa mengorbankan coverage terlalu besar dengan menguji hold "
                "lebih adaptif, early exit, atau stop/target sederhana."
            ),
            "main_risk": "Jika kualitas entry memang buruk, perubahan exit hanya memindahkan noise tanpa memperbaiki edge.",
            "estimated_complexity": "medium",
            "recommended_priority": "medium_high",
            "should_test_next": False,
        },
        {
            "hypothesis_id": "candidate_c_hybrid_conservative_anchor",
            "redesign_focus": "Hybrid conservative anchor + light quality gate",
            "target_problem": (
                "EMA50 terlalu sempit, EMA20 terlalu longgar; dibutuhkan anchor tengah yang membuka coverage "
                "sedikit tanpa membiarkan semua trade lemah masuk."
            ),
            "expected_benefit": (
                "Coverage bisa naik moderat lewat trend proxy yang lebih konservatif daripada EMA20 murni, "
                "ditambah satu quality gate ringan agar noise tidak meledak."
            ),
            "main_risk": "Berakhir di middle ground yang tidak cukup menambah coverage dan tidak cukup menjaga quality.",
            "estimated_complexity": "medium",
            "recommended_priority": "medium",
            "should_test_next": False,
        },
    ]
    return pd.DataFrame(rows).reindex(columns=HYPOTHESIS_COLUMNS)


def _build_state_snapshot(context: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    project_state = safe_dict(context.get("project_current_state"))
    roadmap_latest = _extract_latest_roadmap(context)
    roadmap_payload = safe_dict(context.get("project_roadmap_status"))
    roadmap_phase_a = safe_dict(roadmap_payload.get("phase_a_final_status"))
    v2_go = safe_dict(context.get("baseline_v2_go_no_go"))
    v2_validation = safe_dict(context.get("baseline_v2_validation"))
    v2_candidate = safe_dict(context.get("baseline_v2_best_candidate"))
    v3_go = safe_dict(context.get("baseline_v3_signal_rule_go_no_go"))
    v3_summary = safe_dict(context.get("baseline_v3_signal_rule_summary"))
    v3_best = safe_dict(v3_summary.get("best_v3_rule"))
    baseline_reference = safe_dict(v3_go.get("baseline_reference_rule"))
    roadmap_current_track = _safe_str(roadmap_latest.get("current_track"))
    v3_decision = _safe_str(v3_go.get("decision"))

    redesign_mode_is_current = bool(
        roadmap_current_track == "redesign_baseline_v2_again"
        or v3_decision == "no_go"
        or _safe_str(roadmap_latest.get("baseline_v3_signal_rule_status")) == "no_go"
    )

    phase_a_closeout_status = (
        _safe_str(roadmap_phase_a.get("status"))
        or _safe_str(v2_go.get("phase_a_closeout_status"))
        or _safe_str(project_state.get("phase_a_closeout_status"))
        or "unknown"
    )
    phase_a_runtime_status = (
        _safe_str(v2_go.get("phase_a_runtime_status"))
        or _safe_str(project_state.get("phase_a_runtime_status"))
        or ("runtime_ok" if phase_a_closeout_status in {"closed", "closed_with_notes"} else "unknown")
    )
    if redesign_mode_is_current and phase_a_closeout_status in {"closed", "closed_with_notes"}:
        phase_a_runtime_status = "runtime_ok"
    current_project_mode = _safe_str(project_state.get("current_project_mode"))
    if (
        current_project_mode in {"", "unknown", "phase_a_runtime_fix_required"}
        and (
            _safe_str(v2_go.get("decision")) == "baseline_v2_no_go_redesign_again"
            or redesign_mode_is_current
        )
    ):
        current_project_mode = "baseline_v2_redesign_required"

    final_decision = _safe_str(project_state.get("final_decision"))
    if final_decision in {"", "unknown", "cannot_decide_until_runtime_fixed"} and redesign_mode_is_current:
        final_decision = "baseline_v2_no_go_redesign_again"
    elif final_decision in {"", "unknown", "cannot_decide_until_runtime_fixed"}:
        final_decision = _safe_str(v2_go.get("decision")) or "unknown"

    return {
        "phase_a_closeout_status": phase_a_closeout_status,
        "phase_a_runtime_status": phase_a_runtime_status,
        "current_project_mode": current_project_mode or "unknown",
        "final_decision": final_decision or "unknown",
        "phase_b_status": _safe_str(roadmap_latest.get("phase_b_status")) or "unknown",
        "phase_c_decision": _safe_str(roadmap_latest.get("phase_c_decision")) or "unknown",
        "baseline_v2_candidate_id": _safe_str(v2_candidate.get("candidate_id"))
        or _safe_str(safe_dict(v2_candidate.get("selected_candidate")).get("candidate_id")),
        "baseline_v2_validation_status": _safe_str(v2_validation.get("validation_status")) or "unknown",
        "baseline_v2_validation_next_action": _safe_str(v2_validation.get("next_action")) or "unknown",
        "baseline_v3_decision": _safe_str(v3_go.get("decision")) or "unknown",
        "baseline_v3_best_rule": _safe_str(v3_go.get("best_rule")) or "unknown",
        "v3_reference_eligible_ticker_count": _safe_int(baseline_reference.get("eligible_ticker_count")),
        "v3_reference_total_trades_sum": _safe_int(baseline_reference.get("total_trades_sum")),
        "v3_reference_mean_average_return": _safe_float(baseline_reference.get("mean_average_return")),
        "v3_best_eligible_ticker_count": _safe_int(v3_best.get("eligible_ticker_count") or v3_go.get("eligible_ticker_count")),
        "v3_best_total_trades_sum": _safe_int(v3_best.get("total_trades_sum")),
        "v3_best_mean_average_return": _safe_float(v3_best.get("mean_average_return")),
        "v3_best_trade_retention_vs_baseline": _safe_float(v3_best.get("trade_retention_vs_baseline")),
        "v3_best_coverage_gain_vs_old_rule": _safe_int(v3_best.get("coverage_gain_vs_old_rule")),
    }


def _why_v2_failed(context: Dict[str, Dict[str, object]]) -> str:
    v2_go = safe_dict(context.get("baseline_v2_go_no_go"))
    v2_validation = safe_dict(context.get("baseline_v2_validation"))
    eligible = _safe_int(v2_validation.get("eligible_ticker_count"))
    required_tickers = _safe_int(v2_validation.get("min_eligible_tickers_required"), 3)
    trades = _safe_int(v2_validation.get("total_trades_sum"))
    required_trades = _safe_int(v2_validation.get("minimum_trade_sample_required"), 15)
    validation_status = _safe_str(v2_validation.get("validation_status")) or "unknown"
    score = _safe_float(v2_validation.get("score"))

    if eligible or trades:
        return (
            f"Baseline v2 gagal karena coverage dan sample masih terlalu kecil: eligible_ticker_count={eligible} "
            f"dari minimum {required_tickers}, total_trades_sum={trades} dari minimum {required_trades}, "
            f"validation_status={validation_status}, score={score:+.4f}. Candidate belum promotable walau sempat "
            "lebih baik relatif terhadap baseline aktif pada subset sempit."
        )

    decision = _safe_str(v2_go.get("decision")) or "baseline_v2_no_go_redesign_again"
    return (
        f"Baseline v2 gagal mencapai gate promosi dan berakhir pada decision={decision}. "
        "Coverage terlalu sempit untuk membuka Phase B, jadi redesign berikutnya harus memperluas usability "
        "tanpa melepaskan kualitas trade."
    )


def _why_v3_failed(context: Dict[str, Dict[str, object]]) -> str:
    v3_go = safe_dict(context.get("baseline_v3_signal_rule_go_no_go"))
    v3_summary = safe_dict(context.get("baseline_v3_signal_rule_summary"))
    best = safe_dict(v3_summary.get("best_v3_rule"))
    reference = safe_dict(v3_go.get("baseline_reference_rule"))

    reference_eligible = _safe_int(reference.get("eligible_ticker_count"))
    reference_trades = _safe_int(reference.get("total_trades_sum"))
    reference_avg = _safe_float(reference.get("mean_average_return"))

    best_rule = _safe_str(v3_go.get("best_rule")) or _safe_str(best.get("candidate_id")) or "unknown_rule"
    best_eligible = _safe_int(best.get("eligible_ticker_count") or v3_go.get("eligible_ticker_count"))
    best_trades = _safe_int(best.get("total_trades_sum"))
    best_avg = _safe_float(best.get("mean_average_return"))
    retention = _safe_float(best.get("trade_retention_vs_baseline"))
    coverage_gain = _safe_int(best.get("coverage_gain_vs_old_rule"))
    quality_preserved = bool(v3_go.get("quality_preserved"))

    return (
        f"Baseline v3 gagal karena entry relaxation only membuka coverage tetapi merusak kualitas trade. "
        f"Rule terbaik {best_rule} menaikkan eligible_ticker_count dari {reference_eligible} ke {best_eligible}, "
        f"total_trades_sum dari {reference_trades} ke {best_trades}, trade_retention_vs_baseline={retention:.4f}, "
        f"coverage_gain_vs_old_rule={coverage_gain}, tetapi mean_average_return turun dari {reference_avg:+.5f} "
        f"menjadi {best_avg:+.5f}. quality_preserved={quality_preserved}, jadi arah ini tidak layak diteruskan."
    )


def _directions_to_avoid() -> List[str]:
    return [
        "Jangan lanjutkan redesign dengan entry relaxation only.",
        "Hindari volume-relaxed entry sebagai kandidat default.",
        "Jangan hidupkan ulang item 5-8 sebagai eksperimen aktif untuk menyelamatkan baseline.",
        "Jangan promosikan baseline v2 atau v3 sebelum ada validasi v4 yang lolos guardrail coverage dan quality.",
    ]


def _build_next_best_experiment() -> Dict[str, object]:
    return {
        "recommended_v4_direction": "candidate_a_fast_anchor_quality_gate",
        "experiment_id": "baseline_v4_quality_gate_guard",
        "experiment_goal": (
            "Uji apakah fast trend anchor tetap bisa menjaga coverage >=3 ticker eligible setelah ditambah "
            "quality gate ringan yang memangkas candle/trade lemah."
        ),
        "experiment_scope": (
            "Bandingkan anchor EMA20 trend guard dengan 3-4 variasi quality gate ringan pada hold_period=3 "
            "dan min_trades=5, tanpa mengubah scoring engine atau baseline aktif."
        ),
        "do_not_change": [
            "Jangan ubah baseline aktif.",
            "Jangan ubah scoring engine.",
            "Jangan hidupkan item Phase B 5-8 lagi.",
            "Jangan jadikan candidate v4 sebagai default sebelum validasi terpisah.",
        ],
        "expected_success_signal": (
            "eligible_ticker_count >= 3, total_trades_sum tetap jauh di atas baseline reference, "
            "dan mean_average_return membaik material versus baseline_v3_ema20_trend_guard tanpa quality collapse."
        ),
        "expected_failure_signal": (
            "coverage turun lagi ke <3 ticker atau mean_average_return tetap <= 0 sehingga quality tetap tidak preserved."
        ),
        "recommended_command_stub": (
            "python3 -m quant.run_baseline_v4_quality_gate_experiment "
            "--output-dir output --hold-period 3 --min-trades 5 --scaffold-only"
        ),
    }


def build_plan_payload(output_dir: Path) -> Dict[str, object]:
    context, warnings = _load_context(output_dir=output_dir)
    matrix_df = _build_hypothesis_matrix()
    state_snapshot = _build_state_snapshot(context=context)
    next_best_experiment = _build_next_best_experiment()

    recommended_v4_direction = "candidate_a_fast_anchor_quality_gate"
    payload = {
        "generated_at": _now_iso(),
        "state_snapshot": state_snapshot,
        "recommended_v4_direction": recommended_v4_direction,
        "directions_to_avoid": _directions_to_avoid(),
        "why_v2_failed": _why_v2_failed(context=context),
        "why_v3_failed": _why_v3_failed(context=context),
        "decision_summary": {
            "primary_conclusion": "Jangan lanjutkan redesign dengan entry relaxation only.",
            "secondary_conclusion": "Uji quality gate setelah fast trend anchor sebelum menambah pelonggaran entry baru.",
            "third_conclusion": "Uji exit/hold redesign sebagai prioritas kedua bila quality gate tidak cukup.",
            "default_rule_to_avoid": "volume_relaxed_entry_as_candidate_default",
        },
        "next_best_experiment": next_best_experiment,
        "hypotheses": [_sanitize_for_json(row) for row in matrix_df.to_dict(orient="records")],
        "warnings": warnings,
    }
    return payload


def build_plan_text(payload: Dict[str, object]) -> str:
    snapshot = safe_dict(payload.get("state_snapshot"))
    next_experiment = safe_dict(payload.get("next_best_experiment"))
    lines = [
        "Baseline v4 Redesign Plan",
        "=========================",
        "",
        f"- Recommended v4 direction: {payload.get('recommended_v4_direction')}",
        f"- Current project mode: {snapshot.get('current_project_mode')}",
        f"- Phase B status: {snapshot.get('phase_b_status')}",
        f"- Phase C decision: {snapshot.get('phase_c_decision')}",
        f"- Final decision so far: {snapshot.get('final_decision')}",
        "",
        "Conclusions:",
        f"- {safe_dict(payload.get('decision_summary')).get('primary_conclusion')}",
        f"- {safe_dict(payload.get('decision_summary')).get('secondary_conclusion')}",
        f"- {safe_dict(payload.get('decision_summary')).get('third_conclusion')}",
        "",
        "Why v2 failed:",
        f"- {payload.get('why_v2_failed')}",
        "",
        "Why v3 failed:",
        f"- {payload.get('why_v3_failed')}",
        "",
        "Directions to avoid:",
    ]
    for item in list(payload.get("directions_to_avoid") or []):
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "Hypothesis priorities:",
        ]
    )
    for item in list(payload.get("hypotheses") or []):
        lines.append(
            f"- {item.get('hypothesis_id')}: priority={item.get('recommended_priority')}, "
            f"should_test_next={item.get('should_test_next')}, focus={item.get('redesign_focus')}"
        )

    lines.extend(
        [
            "",
            "Next best experiment:",
            f"- experiment_id={next_experiment.get('experiment_id')}",
            f"- goal={next_experiment.get('experiment_goal')}",
            f"- scope={next_experiment.get('experiment_scope')}",
            f"- expected_success_signal={next_experiment.get('expected_success_signal')}",
            f"- expected_failure_signal={next_experiment.get('expected_failure_signal')}",
            f"- command={next_experiment.get('recommended_command_stub')}",
        ]
    )

    warnings = list(payload.get("warnings") or [])
    if warnings:
        lines.extend(["", "Warnings:"])
        for item in warnings:
            lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def generate_baseline_v4_redesign_plan(output_dir: Path) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = build_plan_payload(output_dir=output_dir)
    matrix_df = pd.DataFrame(list(payload.get("hypotheses") or [])).reindex(columns=HYPOTHESIS_COLUMNS)
    plan_text = build_plan_text(payload=payload)
    next_experiment = safe_dict(payload.get("next_best_experiment"))

    matrix_path = output_dir / "baseline_v4_hypothesis_matrix.csv"
    plan_json_path = output_dir / "baseline_v4_redesign_plan.json"
    plan_txt_path = output_dir / "baseline_v4_redesign_plan.txt"
    next_experiment_path = output_dir / "baseline_v4_next_experiment.json"

    matrix_df.to_csv(matrix_path, index=False)
    _write_json(plan_json_path, payload)
    _write_text(plan_txt_path, plan_text.rstrip("\n").splitlines())
    _write_json(next_experiment_path, next_experiment)

    return {
        "plan": payload,
        "matrix_df": matrix_df,
        "next_experiment": next_experiment,
        "artifacts": {
            "plan_json": str(plan_json_path),
            "plan_txt": str(plan_txt_path),
            "matrix_csv": str(matrix_path),
            "next_experiment_json": str(next_experiment_path),
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate baseline redesign v4 plan artifacts.")
    parser.add_argument("--output-dir", default="output", help="Directory containing prior artifacts and output files.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = generate_baseline_v4_redesign_plan(output_dir=Path(args.output_dir))
    print(f"Recommended v4 direction: {result['plan']['recommended_v4_direction']}")
    print(f"Next experiment: {result['next_experiment']['experiment_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
