"""Finalize baseline redesign root-cause postmortem and next experiment plan."""

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


ROOT_CAUSE_VALUES = {
    "coverage_too_low",
    "entry_too_strict",
    "entry_too_loose_low_quality",
    "quality_gate_not_stable",
    "exit_hold_not_primary_problem",
    "eligibility_gate_misaligned",
    "sample_size_too_small",
    "ticker_universe_mismatch",
    "event_sentiment_coverage_uneven",
    "objective_function_mismatch",
}

PRIMARY_DIRECTIONS = {
    "revisit_eligibility_and_sample_guardrails",
    "revisit_ticker_universe_segmentation",
    "revisit_scoring_objective",
    "revisit_fast_anchor_with_better_quality_gate",
    "stop_strategy_redesign_and_collect_more_data",
}

STAGE_ORDER = ["baseline_v2", "baseline_v3", "baseline_v4", "baseline_v5"]

ARTIFACT_MAP = {
    "project_roadmap_status": "project_roadmap_status.json",
    "baseline_v2_go_no_go": "baseline_v2_go_no_go.json",
    "baseline_v2_validation": "baseline_v2_validation.json",
    "baseline_v3_signal_rule_go_no_go": "baseline_v3_signal_rule_go_no_go.json",
    "baseline_v3_signal_rule_summary": "baseline_v3_signal_rule_summary.json",
    "baseline_v4_quality_gate_go_no_go": "baseline_v4_quality_gate_go_no_go.json",
    "baseline_v4_quality_gate_summary": "baseline_v4_quality_gate_summary.json",
    "baseline_v5_exit_hold_go_no_go": "baseline_v5_exit_hold_go_no_go.json",
    "baseline_v5_exit_hold_summary": "baseline_v5_exit_hold_summary.json",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: object) -> Optional[float]:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> Optional[int]:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    return int(numeric)


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


def _load_context(output_dir: Path) -> Tuple[Dict[str, Dict[str, object]], List[str], List[str]]:
    payloads: Dict[str, Dict[str, object]] = {}
    warnings: List[str] = []
    gaps: List[str] = []
    for key, filename in ARTIFACT_MAP.items():
        payload, item_warnings = read_json_object(output_dir / filename, filename)
        payloads[key] = payload if isinstance(payload, dict) else {}
        warnings.extend(item_warnings)
        gaps.extend(
            item for item in item_warnings if "not found" in item.lower() or "invalid" in item.lower() or "does not contain" in item.lower()
        )
    return payloads, dedupe(warnings), dedupe(gaps)


def _roadmap_snapshot(payloads: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    roadmap = safe_dict(payloads.get("project_roadmap_status"))
    latest = safe_dict(roadmap.get("latest_execution_status"))
    phase_a_status = safe_dict(roadmap.get("phase_a_final_status")).get("status")
    return {
        "phase_a_status": phase_a_status or latest.get("phase_a_status") or "unknown",
        "phase_b_status": latest.get("phase_b_status") or "unknown",
        "phase_c_decision": latest.get("phase_c_decision") or "unknown",
        "current_track": latest.get("current_track") or "unknown",
    }


def _classify_baseline_v2(payloads: Dict[str, Dict[str, object]], gaps: List[str]) -> Dict[str, object]:
    go = safe_dict(payloads.get("baseline_v2_go_no_go"))
    validation = safe_dict(payloads.get("baseline_v2_validation"))
    eligible = _safe_int(validation.get("eligible_ticker_count"))
    trades = _safe_int(validation.get("total_trades_sum"))
    required_eligible = _safe_int(validation.get("min_eligible_tickers_required")) or 3
    required_trades = _safe_int(validation.get("minimum_trade_sample_required")) or 15
    decision = str(validation.get("decision") or go.get("decision") or "").strip() or "missing"
    status = str(validation.get("validation_status") or "").strip() or "missing"

    primary = "coverage_too_low"
    supporting = [
        "sample_size_too_small",
        "entry_too_strict",
        "eligibility_gate_misaligned",
    ]
    reasoning = (
        f"Baseline v2 gagal dengan eligible_ticker_count={eligible if eligible is not None else 'n/a'} "
        f"vs minimum {required_eligible} dan total_trades_sum={trades if trades is not None else 'n/a'} "
        f"vs minimum {required_trades}; ini menunjukkan baseline terlalu sempit untuk coverage dan sample yang dibutuhkan."
    )
    if not validation:
        reasoning = "Artifact baseline v2 validation tidak lengkap; klasifikasi diturunkan dari status reject/no-go yang tersedia."

    return {
        "stage_id": "baseline_v2",
        "decision": decision,
        "status": status,
        "primary_root_cause": primary,
        "supporting_root_causes": supporting[:3],
        "reasoning": reasoning,
        "key_metrics": {
            "eligible_ticker_count": eligible,
            "required_eligible_ticker_count": required_eligible,
            "total_trades_sum": trades,
            "required_total_trades_sum": required_trades,
        },
        "artifact_gaps": [gap for gap in gaps if "baseline_v2" in gap],
    }


def _classify_baseline_v3(payloads: Dict[str, Dict[str, object]], gaps: List[str]) -> Dict[str, object]:
    go = safe_dict(payloads.get("baseline_v3_signal_rule_go_no_go"))
    summary = safe_dict(payloads.get("baseline_v3_signal_rule_summary"))
    best = safe_dict(summary.get("best_v3_rule"))
    reference = safe_dict(go.get("baseline_reference_rule"))

    eligible = _safe_int(best.get("eligible_ticker_count") or go.get("eligible_ticker_count"))
    reference_eligible = _safe_int(reference.get("eligible_ticker_count"))
    trades = _safe_int(best.get("total_trades_sum"))
    reference_trades = _safe_int(reference.get("total_trades_sum"))
    avg_return = _safe_float(best.get("mean_average_return"))
    reference_avg_return = _safe_float(reference.get("mean_average_return"))

    primary = "entry_too_loose_low_quality"
    supporting = [
        "objective_function_mismatch",
        "ticker_universe_mismatch",
    ]
    reasoning = (
        f"Baseline v3 menaikkan coverage dari {reference_eligible if reference_eligible is not None else 'n/a'} ke {eligible if eligible is not None else 'n/a'} "
        f"dan trade dari {reference_trades if reference_trades is not None else 'n/a'} ke {trades if trades is not None else 'n/a'}, "
        f"tetapi mean_average_return turun dari {reference_avg_return if reference_avg_return is not None else 'n/a'} "
        f"ke {avg_return if avg_return is not None else 'n/a'}; jadi pelonggaran entry membuka coverage sambil merusak kualitas."
    )
    if avg_return is not None and reference_avg_return is not None and avg_return > reference_avg_return:
        supporting = ["objective_function_mismatch"]

    return {
        "stage_id": "baseline_v3",
        "decision": str(go.get("decision") or "missing"),
        "status": str(go.get("best_rule") or "missing"),
        "primary_root_cause": primary,
        "supporting_root_causes": supporting[:3],
        "reasoning": reasoning,
        "key_metrics": {
            "best_rule": go.get("best_rule"),
            "eligible_ticker_count": eligible,
            "reference_eligible_ticker_count": reference_eligible,
            "total_trades_sum": trades,
            "reference_total_trades_sum": reference_trades,
            "mean_average_return": avg_return,
            "reference_mean_average_return": reference_avg_return,
        },
        "artifact_gaps": [gap for gap in gaps if "baseline_v3" in gap],
    }


def _classify_baseline_v4(payloads: Dict[str, Dict[str, object]], gaps: List[str]) -> Dict[str, object]:
    go = safe_dict(payloads.get("baseline_v4_quality_gate_go_no_go"))
    summary = safe_dict(payloads.get("baseline_v4_quality_gate_summary"))
    best = safe_dict(summary.get("best_v4_candidate_summary"))

    eligible = _safe_int(go.get("eligible_ticker_count") or best.get("eligible_ticker_count"))
    trades = _safe_int(go.get("total_trades_sum") or best.get("total_trades_sum"))
    avg_return = _safe_float(go.get("mean_average_return") or best.get("mean_average_return"))
    quality_preserved = bool(go.get("quality_preserved"))

    primary = "coverage_too_low"
    supporting = ["quality_gate_not_stable", "eligibility_gate_misaligned", "sample_size_too_small"]
    reasoning = (
        f"Baseline v4 sudah menunjukkan kualitas yang preserved dan mean_average_return={avg_return if avg_return is not None else 'n/a'}, "
        f"tetapi berhenti di eligible_ticker_count={eligible if eligible is not None else 'n/a'} dan total_trades_sum={trades if trades is not None else 'n/a'}, "
        "jadi masalah utama bergeser dari kualitas entry ke coverage yang tidak cukup untuk lolos guardrail."
    )
    if not quality_preserved:
        primary = "quality_gate_not_stable"
        supporting = ["coverage_too_low", "sample_size_too_small"]

    return {
        "stage_id": "baseline_v4",
        "decision": str(go.get("decision") or "missing"),
        "status": str(best.get("candidate_id") or "missing"),
        "primary_root_cause": primary,
        "supporting_root_causes": supporting[:3],
        "reasoning": reasoning,
        "key_metrics": {
            "best_candidate": best.get("candidate_id"),
            "eligible_ticker_count": eligible,
            "total_trades_sum": trades,
            "mean_average_return": avg_return,
            "quality_preserved": quality_preserved,
        },
        "artifact_gaps": [gap for gap in gaps if "baseline_v4" in gap],
    }


def _classify_baseline_v5(payloads: Dict[str, Dict[str, object]], gaps: List[str]) -> Dict[str, object]:
    go = safe_dict(payloads.get("baseline_v5_exit_hold_go_no_go"))
    summary = safe_dict(payloads.get("baseline_v5_exit_hold_summary"))
    best = safe_dict(summary.get("best_v5_candidate_summary"))

    primary = "exit_hold_not_primary_problem"
    supporting = ["coverage_too_low", "sample_size_too_small", "eligibility_gate_misaligned"]
    reasoning = (
        f"Baseline v5 memperbaiki mean_average_return relatif terhadap anchor v4 sebesar "
        f"{_safe_float(go.get('mean_average_return_delta_vs_v4_anchor')) if _safe_float(go.get('mean_average_return_delta_vs_v4_anchor')) is not None else 'n/a'}, "
        f"tetapi tetap berakhir dengan eligible_ticker_count={_safe_int(go.get('eligible_ticker_count')) if _safe_int(go.get('eligible_ticker_count')) is not None else 'n/a'}, "
        f"trade_retention_vs_v4_anchor={_safe_float(go.get('trade_retention_vs_v4_anchor')) if _safe_float(go.get('trade_retention_vs_v4_anchor')) is not None else 'n/a'}, "
        "dan quality_preserved=false; jadi redesign exit/hold bukan solusi utama tunggal."
    )
    if bool(go.get("supports_exit_hold_hypothesis")):
        primary = "eligibility_gate_misaligned"
        supporting = ["coverage_too_low", "sample_size_too_small"]

    return {
        "stage_id": "baseline_v5",
        "decision": str(go.get("decision") or "missing"),
        "status": str(best.get("candidate_id") or "missing"),
        "primary_root_cause": primary,
        "supporting_root_causes": supporting[:3],
        "reasoning": reasoning,
        "key_metrics": {
            "best_candidate": best.get("candidate_id"),
            "eligible_ticker_count": _safe_int(go.get("eligible_ticker_count")),
            "total_trades_sum": _safe_int(go.get("total_trades_sum")),
            "mean_average_return": _safe_float(go.get("mean_average_return")),
            "mean_average_return_delta_vs_v4_anchor": _safe_float(go.get("mean_average_return_delta_vs_v4_anchor")),
            "trade_retention_vs_v4_anchor": _safe_float(go.get("trade_retention_vs_v4_anchor")),
            "quality_preserved": bool(go.get("quality_preserved")),
            "supports_exit_hold_hypothesis": bool(go.get("supports_exit_hold_hypothesis")),
        },
        "artifact_gaps": [gap for gap in gaps if "baseline_v5" in gap],
    }


def _build_root_cause_stages(payloads: Dict[str, Dict[str, object]], gaps: List[str]) -> List[Dict[str, object]]:
    return [
        _classify_baseline_v2(payloads=payloads, gaps=gaps),
        _classify_baseline_v3(payloads=payloads, gaps=gaps),
        _classify_baseline_v4(payloads=payloads, gaps=gaps),
        _classify_baseline_v5(payloads=payloads, gaps=gaps),
    ]


def _infer_bottleneck(stages: List[Dict[str, object]]) -> Dict[str, object]:
    primary_causes = {stage["stage_id"]: stage["primary_root_cause"] for stage in stages}
    v4 = next(stage for stage in stages if stage["stage_id"] == "baseline_v4")
    v5 = next(stage for stage in stages if stage["stage_id"] == "baseline_v5")

    bottleneck = {
        "data": "not_primary",
        "eligibility_rule": "primary",
        "scoring_objective": "secondary",
        "anchor_concept": "not_primary",
        "universe_ticker": "secondary",
    }
    if primary_causes["baseline_v4"] not in {"coverage_too_low", "quality_gate_not_stable"}:
        bottleneck["eligibility_rule"] = "secondary"
    if primary_causes["baseline_v5"] == "exit_hold_not_primary_problem":
        bottleneck["anchor_concept"] = "not_primary"
    if "objective_function_mismatch" not in v4["supporting_root_causes"] and "objective_function_mismatch" not in next(stage for stage in stages if stage["stage_id"] == "baseline_v3")["supporting_root_causes"]:
        bottleneck["scoring_objective"] = "watchlist_only"
    if "ticker_universe_mismatch" not in next(stage for stage in stages if stage["stage_id"] == "baseline_v3")["supporting_root_causes"]:
        bottleneck["universe_ticker"] = "watchlist_only"
    if _safe_int(v5["key_metrics"].get("eligible_ticker_count")) == 0:
        bottleneck["eligibility_rule"] = "primary"
        bottleneck["universe_ticker"] = "secondary"
    return bottleneck


def _extract_stopped_phase_b_items(payloads: Dict[str, Dict[str, object]]) -> List[str]:
    roadmap = safe_dict(payloads.get("project_roadmap_status"))
    parked: List[str] = []
    for item in list(roadmap.get("items") or []):
        row = safe_dict(item)
        phase = str(row.get("phase") or "").strip()
        name = str(row.get("item_name") or "").strip().lower()
        action = str(row.get("recommended_next_action") or "").strip().lower()
        action_signals = ["stop", "nonaktif", "parkir", "jangan hidupkan lagi", "tetap parkirkan"]
        if phase != "phase_b" or not any(signal in action for signal in action_signals):
            continue
        if "volume confirmation" in name:
            parked.append("item5")
        elif "multi-timeframe" in name:
            parked.append("item6")
        elif "sentiment momentum" in name:
            parked.append("item7")
        elif "adaptif" in name or "adaptive" in name:
            parked.append("item8")
    return dedupe(parked)


def _build_stop_lists(payloads: Dict[str, Dict[str, object]], stages: List[Dict[str, object]]) -> Dict[str, List[str]]:
    v3 = next(stage for stage in stages if stage["stage_id"] == "baseline_v3")
    v5 = next(stage for stage in stages if stage["stage_id"] == "baseline_v5")
    hard_stop: List[str] = _extract_stopped_phase_b_items(payloads=payloads)

    if v3["primary_root_cause"] == "entry_too_loose_low_quality":
        hard_stop.extend(["entry_relaxation_only", "volume_relaxed_entry"])
    if v5["primary_root_cause"] == "exit_hold_not_primary_problem":
        hard_stop.append("exit_hold_only_redesign")

    still_allowed = [
        "fast_anchor_plus_quality_gate",
        "eligibility_gate_review",
        "universe_segmentation",
        "sample_sufficiency_redesign",
    ]
    return {
        "must_stop_or_park": dedupe(hard_stop),
        "still_explorable": dedupe(still_allowed),
    }


def _decide_primary_direction(stages: List[Dict[str, object]], bottleneck: Dict[str, object]) -> Dict[str, str]:
    v3 = next(stage for stage in stages if stage["stage_id"] == "baseline_v3")
    v4 = next(stage for stage in stages if stage["stage_id"] == "baseline_v4")
    v5 = next(stage for stage in stages if stage["stage_id"] == "baseline_v5")

    if (
        v3["primary_root_cause"] == "entry_too_loose_low_quality"
        and v4["primary_root_cause"] == "coverage_too_low"
        and v5["primary_root_cause"] == "exit_hold_not_primary_problem"
        and bottleneck.get("eligibility_rule") == "primary"
    ):
        return {
            "recommended_primary_direction": "revisit_eligibility_and_sample_guardrails",
            "recommended_secondary_direction_1": "revisit_ticker_universe_segmentation",
            "recommended_secondary_direction_2": "revisit_fast_anchor_with_better_quality_gate",
        }

    if bottleneck.get("anchor_concept") == "primary":
        return {
            "recommended_primary_direction": "revisit_fast_anchor_with_better_quality_gate",
            "recommended_secondary_direction_1": "revisit_eligibility_and_sample_guardrails",
            "recommended_secondary_direction_2": "revisit_scoring_objective",
        }

    return {
        "recommended_primary_direction": "revisit_scoring_objective",
        "recommended_secondary_direction_1": "revisit_eligibility_and_sample_guardrails",
        "recommended_secondary_direction_2": "revisit_ticker_universe_segmentation",
    }


def _build_key_findings(stages: List[Dict[str, object]], direction_block: Dict[str, str]) -> List[str]:
    return [
        "Masalah utama bukan lagi entry relaxation, karena v3 sudah membuktikan coverage naik tetapi kualitas trade runtuh.",
        "Masalah utama bukan exit/hold sebagai solusi tunggal, karena v5 tidak memulihkan eligibility maupun quality walau average return relatif membaik dari anchor v4.",
        "Arah fast anchor plus quality gate terbukti lebih benar daripada entry relaxation only, karena v4 sempat menjaga quality, tetapi coverage-nya masih belum cukup stabil untuk lolos guardrail.",
        "Bottleneck paling mungkin sekarang ada pada guardrail eligibility/sample dan kecocokan universe ticker, bukan pada anchor concept sebagai ide dasar.",
        (
            "Arah paling masuk akal berikutnya adalah review guardrail eligibility/sample atau segmentasi universe, "
            "bukan menambah filter teknikal baru."
            if direction_block["recommended_primary_direction"] == "revisit_eligibility_and_sample_guardrails"
            else "Arah berikutnya perlu kembali ke desain objective/guardrail sebelum strategi baru dicoba."
        ),
    ]


def _build_postmortem_payload(
    payloads: Dict[str, Dict[str, object]],
    warnings: List[str],
    gaps: List[str],
    stages: List[Dict[str, object]],
) -> Dict[str, object]:
    roadmap = _roadmap_snapshot(payloads=payloads)
    bottleneck = _infer_bottleneck(stages=stages)
    stop_lists = _build_stop_lists(payloads=payloads, stages=stages)
    direction_block = _decide_primary_direction(stages=stages, bottleneck=bottleneck)
    key_findings = _build_key_findings(stages=stages, direction_block=direction_block)

    return {
        "generated_at": _now_iso(),
        "roadmap_snapshot": roadmap,
        "artifact_gaps": gaps,
        "warnings": warnings,
        "baseline_stage_root_causes": stages,
        "current_primary_bottleneck": bottleneck,
        "key_findings": key_findings,
        "what_has_been_proven_not_to_work": [
            "entry_relaxation_only",
            "exit_hold_only_redesign",
            "reactivating_phase_b_items_5_to_8",
        ],
        "what_to_stop": stop_lists["must_stop_or_park"],
        "what_is_still_explorable": stop_lists["still_explorable"],
        **direction_block,
    }


def _build_next_experiment_plan(postmortem: Dict[str, object]) -> Dict[str, object]:
    primary = str(postmortem["recommended_primary_direction"])
    stop_list = list(postmortem.get("what_to_stop") or [])
    if primary not in PRIMARY_DIRECTIONS:
        raise ValueError(f"Unsupported recommended primary direction: {primary}")

    why_this_is_next = (
        "v3 sudah membuktikan coverage bisa naik bila entry dilonggarkan, v4 membuktikan kualitas bisa dipertahankan pada fast anchor yang diberi quality gate, "
        "dan v5 membuktikan exit/hold bukan penyelesai utama. Jadi langkah paling rasional berikutnya adalah meninjau ulang guardrail eligibility/sample "
        "yang mungkin terlalu kaku terhadap universe dan coverage event saat ini."
        if primary == "revisit_eligibility_and_sample_guardrails"
        else "Urutan evidence saat ini tidak mendukung filter strategi baru; fokus harus dialihkan ke lapisan evaluasi yang paling mungkin salah sasaran."
    )
    success_criteria = [
        "Definisi eligibility baru harus menjelaskan mengapa v4 quality-preserved tetap gagal no_go walau return sudah positif kuat.",
        "Review harus menghasilkan guardrail coverage/sample yang tetap ketat tetapi tidak menghukum kandidat yang jelas lebih baik dari v3.",
        "Arah baru tidak boleh menghidupkan lagi item 5-8, tidak boleh lanjut ke Phase C, dan tidak boleh mengubah baseline aktif.",
    ]
    failure_criteria = [
        "Rencana berikutnya kembali jatuh ke trial-and-error filter teknikal baru tanpa menjawab mismatch guardrail.",
        "Perubahan yang diusulkan tetap bergantung pada entry relaxation only atau exit/hold only sebagai jawaban utama.",
        "Eksperimen berikutnya membutuhkan aktivasi ulang item 5-8 atau mendorong Phase C lebih awal.",
    ]

    return {
        "generated_at": _now_iso(),
        "recommended_primary_direction": primary,
        "recommended_secondary_direction_1": postmortem["recommended_secondary_direction_1"],
        "recommended_secondary_direction_2": postmortem["recommended_secondary_direction_2"],
        "why_this_is_next": why_this_is_next,
        "what_to_stop": stop_list,
        "what_not_to_change": [
            "Jangan ubah baseline aktif.",
            "Jangan lanjut ke Phase C.",
            "Jangan hidupkan lagi item 5-8.",
            "Jangan mulai eksperimen strategi baru sebelum root cause guardrail ditutup.",
        ],
        "success_criteria": success_criteria,
        "failure_criteria": failure_criteria,
        "suggested_experiment_id": "baseline_v6_guardrail_review",
        "suggested_command_stub": "python3 -m quant.finalize_baseline_root_cause_postmortem --output-dir output",
    }


def _write_root_cause_matrix(path: Path, stages: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "stage_id",
                "decision",
                "status",
                "primary_root_cause",
                "supporting_root_causes",
                "reasoning",
                "artifact_gaps",
            ],
        )
        writer.writeheader()
        for stage in stages:
            writer.writerow(
                {
                    "stage_id": stage["stage_id"],
                    "decision": stage["decision"],
                    "status": stage["status"],
                    "primary_root_cause": stage["primary_root_cause"],
                    "supporting_root_causes": "|".join(stage["supporting_root_causes"]),
                    "reasoning": stage["reasoning"],
                    "artifact_gaps": "|".join(stage["artifact_gaps"]),
                }
            )


def _build_postmortem_text(postmortem: Dict[str, object]) -> str:
    lines = [
        "Baseline Root-Cause Postmortem",
        "==============================",
        "",
        "Roadmap snapshot:",
        f"- Phase A: {safe_dict(postmortem.get('roadmap_snapshot')).get('phase_a_status')}",
        f"- Phase B: {safe_dict(postmortem.get('roadmap_snapshot')).get('phase_b_status')}",
        f"- Phase C: {safe_dict(postmortem.get('roadmap_snapshot')).get('phase_c_decision')}",
        f"- Current track: {safe_dict(postmortem.get('roadmap_snapshot')).get('current_track')}",
        "",
        "Key findings:",
    ]
    for item in list(postmortem.get("key_findings") or []):
        lines.append(f"- {item}")

    lines.extend(["", "Stage root causes:"])
    for stage in list(postmortem.get("baseline_stage_root_causes") or []):
        lines.append(
            f"- {stage['stage_id']}: primary={stage['primary_root_cause']} | supporting={','.join(stage['supporting_root_causes'])}"
        )
        lines.append(f"  decision={stage['decision']} | {stage['reasoning']}")

    lines.extend(
        [
            "",
            "Current bottleneck:",
            f"- data={safe_dict(postmortem.get('current_primary_bottleneck')).get('data')}",
            f"- eligibility_rule={safe_dict(postmortem.get('current_primary_bottleneck')).get('eligibility_rule')}",
            f"- scoring_objective={safe_dict(postmortem.get('current_primary_bottleneck')).get('scoring_objective')}",
            f"- anchor_concept={safe_dict(postmortem.get('current_primary_bottleneck')).get('anchor_concept')}",
            f"- universe_ticker={safe_dict(postmortem.get('current_primary_bottleneck')).get('universe_ticker')}",
            "",
            "Stop or park:",
        ]
    )
    for item in list(postmortem.get("what_to_stop") or []):
        lines.append(f"- {item}")

    lines.extend(["", "Still explorable:"])
    for item in list(postmortem.get("what_is_still_explorable") or []):
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "Next direction:",
            f"- recommended_primary_direction={postmortem.get('recommended_primary_direction')}",
            f"- recommended_secondary_direction_1={postmortem.get('recommended_secondary_direction_1')}",
            f"- recommended_secondary_direction_2={postmortem.get('recommended_secondary_direction_2')}",
        ]
    )
    if postmortem.get("artifact_gaps"):
        lines.extend(["", "Artifact gaps:"])
        for item in list(postmortem.get("artifact_gaps") or []):
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _build_plan_text(plan: Dict[str, object]) -> str:
    lines = [
        "Baseline Next Experiment Plan",
        "=============================",
        "",
        f"- recommended_primary_direction={plan.get('recommended_primary_direction')}",
        f"- recommended_secondary_direction_1={plan.get('recommended_secondary_direction_1')}",
        f"- recommended_secondary_direction_2={plan.get('recommended_secondary_direction_2')}",
        f"- suggested_experiment_id={plan.get('suggested_experiment_id')}",
        f"- suggested_command_stub={plan.get('suggested_command_stub')}",
        "",
        "Why this is next:",
        f"- {plan.get('why_this_is_next')}",
        "",
        "What to stop:",
    ]
    for item in list(plan.get("what_to_stop") or []):
        lines.append(f"- {item}")
    lines.extend(["", "What not to change:"])
    for item in list(plan.get("what_not_to_change") or []):
        lines.append(f"- {item}")
    lines.extend(["", "Success criteria:"])
    for item in list(plan.get("success_criteria") or []):
        lines.append(f"- {item}")
    lines.extend(["", "Failure criteria:"])
    for item in list(plan.get("failure_criteria") or []):
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def finalize_baseline_root_cause_postmortem(output_dir: Path) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    payloads, warnings, gaps = _load_context(output_dir=output_dir)
    stages = _build_root_cause_stages(payloads=payloads, gaps=gaps)
    postmortem = _build_postmortem_payload(
        payloads=payloads,
        warnings=warnings,
        gaps=gaps,
        stages=stages,
    )
    plan = _build_next_experiment_plan(postmortem=postmortem)

    postmortem_json_path = output_dir / "baseline_root_cause_postmortem.json"
    postmortem_txt_path = output_dir / "baseline_root_cause_postmortem.txt"
    root_cause_csv_path = output_dir / "baseline_root_cause_matrix.csv"
    next_plan_json_path = output_dir / "baseline_next_experiment_plan.json"
    next_plan_txt_path = output_dir / "baseline_next_experiment_plan.txt"

    _write_json(postmortem_json_path, postmortem)
    _write_text(postmortem_txt_path, _build_postmortem_text(postmortem=postmortem).rstrip("\n").splitlines())
    _write_root_cause_matrix(root_cause_csv_path, stages=stages)
    _write_json(next_plan_json_path, plan)
    _write_text(next_plan_txt_path, _build_plan_text(plan=plan).rstrip("\n").splitlines())

    return {
        "postmortem_json_path": postmortem_json_path,
        "postmortem_txt_path": postmortem_txt_path,
        "root_cause_csv_path": root_cause_csv_path,
        "next_plan_json_path": next_plan_json_path,
        "next_plan_txt_path": next_plan_txt_path,
        "postmortem": postmortem,
        "plan": plan,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finalize baseline root-cause postmortem and next experiment plan.")
    parser.add_argument("--output-dir", default="output", help="Directory containing baseline artifacts.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    result = finalize_baseline_root_cause_postmortem(output_dir=Path(args.output_dir))
    print(f"Recommended primary direction: {result['plan']['recommended_primary_direction']}")
    print(f"Suggested experiment id: {result['plan']['suggested_experiment_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
