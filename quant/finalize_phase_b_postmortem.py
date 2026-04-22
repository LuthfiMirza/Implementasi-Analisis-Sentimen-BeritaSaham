"""Finalize Phase B postmortem artifacts and next-phase decisions."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402


FINAL_DECISIONS = {
    "no_go",
    "promote_global",
    "promote_for_subset",
    "promote_group_specific",
    "promote_ticker_specific",
    "keep_experimental",
}
FOUNDATIONAL_CAUSES = {
    "baseline_mismatch",
    "trade_retention_too_low",
    "signal_collapse",
    "sentiment_data_weak_or_non_informative",
    "adaptive_config_not_usable",
    "insufficient_trade_sample",
}

ITEM_SPECS: Dict[str, Dict[str, object]] = {
    "item5": {
        "label": "Phase B item 5",
        "go_no_go_json": "phase_b_item5_go_no_go.json",
        "report_txt": "phase_b_item5_recommendations.txt",
        "optional_json": [
            "phase_b_item5_decision.json",
            "phase_b_item5_candle_confirmation_summary.json",
        ],
    },
    "item6": {
        "label": "Phase B item 6",
        "go_no_go_json": "phase_b_item6_go_no_go.json",
        "report_txt": "phase_b_item6_multitimeframe_report.txt",
        "optional_json": ["phase_b_item6_multitimeframe_summary.json"],
    },
    "item7": {
        "label": "Phase B item 7",
        "go_no_go_json": "phase_b_item7_go_no_go.json",
        "report_txt": "phase_b_item7_sentiment_momentum_report.txt",
        "optional_json": [
            "phase_b_item7_sentiment_momentum_summary.json",
            "phase_b_item7_data_readiness.json",
        ],
    },
    "item8": {
        "label": "Phase B item 8",
        "go_no_go_json": "phase_b_item8_go_no_go.json",
        "report_txt": "phase_b_item8_recommendations.txt",
        "optional_json": ["phase_b_item8_global_summary.json"],
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text(path: Path, label: str) -> Tuple[Optional[str], List[str]]:
    warnings: List[str] = []
    target = Path(path)
    if not target.exists():
        warnings.append(f"{label} not found: {target}.")
        return None, warnings
    if not target.is_file():
        warnings.append(f"{label} is not a file: {target}.")
        return None, warnings

    try:
        return target.read_text(encoding="utf-8"), warnings
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"Failed to read {label} {target}: {exc}.")
        return None, warnings


def _safe_float(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: object) -> Optional[int]:
    number = _safe_float(value)
    if number is None:
        return None
    return int(number)


def _normalize_key(text: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return normalized


def _parse_scalar(raw: str) -> object:
    value = raw.strip()
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"none", "null", "n_a", "na"}:
        return None
    try:
        if "." not in value and "e" not in lowered:
            return int(value)
        return float(value)
    except ValueError:
        return value


def _parse_report_metrics(text: Optional[str]) -> Dict[str, object]:
    if not text:
        return {}

    metrics: Dict[str, object] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        payload = line[2:].strip()
        if ":" in payload:
            key, value = payload.split(":", 1)
        elif "=" in payload:
            key, value = payload.split("=", 1)
        else:
            continue
        metrics[_normalize_key(key)] = _parse_scalar(value)
    return metrics


def _extract_item_status(item_id: str, go_no_go: Dict[str, object]) -> str:
    raw_status = (
        str(go_no_go.get(f"{item_id}_experiment_status", "")).strip()
        or str(go_no_go.get("experiment_status", "")).strip()
    )
    decision = str(go_no_go.get("decision", "")).strip()
    if raw_status:
        return raw_status
    if decision == "no_go":
        return "failed"
    if decision in {"promote_global", "promote_for_subset", "promote_group_specific", "promote_ticker_specific"}:
        return "promising"
    if decision == "keep_experimental":
        return "mixed"
    return "unknown"


def _extract_next_action(item_id: str, go_no_go: Dict[str, object]) -> Optional[str]:
    value = (
        str(go_no_go.get(f"{item_id}_next_action", "")).strip()
        or str(go_no_go.get("next_action", "")).strip()
    )
    return value or None


def _extract_blocked_reasons(go_no_go: Dict[str, object]) -> List[str]:
    blocked: List[str] = []
    for key in ["blocked_from_default", "blocked_from_broader_promotion"]:
        blocked.extend(str(item).strip() for item in list(go_no_go.get(key) or []))
    return dedupe(blocked)


def _build_item_metrics(
    item_id: str,
    go_no_go: Dict[str, object],
    report_metrics: Dict[str, object],
    optional_json_payloads: Dict[str, Dict[str, object]],
) -> Dict[str, object]:
    metrics: Dict[str, object] = {}
    if item_id == "item5":
        decision_payload = safe_dict(optional_json_payloads.get("phase_b_item5_decision.json"))
        global_row = safe_dict(decision_payload.get("global_best_row"))
        metrics.update(global_row)
        metrics["best_global_threshold"] = go_no_go.get("best_global_threshold")
        metrics["mean_score"] = metrics.get("mean_score", report_metrics.get("mean_score"))
        metrics["delta_win_rate_mean"] = metrics.get(
            "delta_win_rate_mean",
            report_metrics.get("delta_win_rate_mean"),
        )
        metrics["delta_average_return_mean"] = metrics.get(
            "delta_average_return_mean",
            report_metrics.get("delta_average_return_mean"),
        )
        metrics["trade_retention_mean_pct"] = metrics.get(
            "trade_retention_mean_pct",
            report_metrics.get("trade_retention_mean_pct"),
        )
        metrics["threshold_profile"] = metrics.get(
            "threshold_profile",
            report_metrics.get("threshold_profile"),
        )
    elif item_id == "item6":
        summary = safe_dict(optional_json_payloads.get("phase_b_item6_multitimeframe_summary.json"))
        metrics.update(safe_dict(summary.get("aggregate")))
        metrics["comparison_status"] = summary.get("comparison_status") or report_metrics.get("comparison_status")
        metrics["weekly_trend_method"] = safe_dict(summary.get("experiment_arm")).get(
            "weekly_trend_method",
            report_metrics.get("weekly_trend_method"),
        )
    elif item_id == "item7":
        summary = safe_dict(optional_json_payloads.get("phase_b_item7_sentiment_momentum_summary.json"))
        readiness = safe_dict(optional_json_payloads.get("phase_b_item7_data_readiness.json"))
        metrics.update(safe_dict(summary.get("aggregate")))
        metrics["comparison_status"] = summary.get("comparison_status") or report_metrics.get("comparison_status")
        metrics["sentiment_momentum_mode"] = safe_dict(summary.get("experiment_arm")).get(
            "sentiment_momentum_mode",
            report_metrics.get("sentiment_momentum_mode"),
        )
        metrics["dataset_is_item7_ready"] = readiness.get("dataset_is_item7_ready")
        metrics["experiment_can_run"] = readiness.get("experiment_can_run")
        metrics["valid_ticker_count"] = readiness.get("valid_ticker_count")
        metrics["unusable_ticker_count"] = readiness.get("unusable_ticker_count")
        metrics["selected_ticker_count"] = readiness.get("selected_ticker_count")
    elif item_id == "item8":
        summary = safe_dict(optional_json_payloads.get("phase_b_item8_global_summary.json"))
        metrics.update(summary)
        metrics["adaptive_model_supported"] = go_no_go.get(
            "adaptive_model_supported",
            summary.get("adaptive_model_supported"),
        )
        metrics["recommended_ticker_count"] = summary.get(
            "recommended_ticker_count",
            len(list(go_no_go.get("recommended_tickers") or [])),
        )
        metrics["recommended_group_count"] = summary.get(
            "recommended_group_count",
            len(list(go_no_go.get("recommended_groups") or [])),
        )
    return metrics


def _make_reasoning(item_id: str, metrics: Dict[str, object], blocked: List[str]) -> str:
    if item_id == "item5":
        return (
            "Item 5 menambah filter konfirmasi tetapi kualitas agregat tetap negatif, "
            "sementara threshold efektif bertabrakan dengan baseline dan dukungan trade tetap tipis."
        )
    if item_id == "item6":
        retention = _safe_float(metrics.get("trade_retention_mean_pct"))
        return (
            "Item 6 tidak menjaga retensi trade yang cukup."
            if retention is None
            else f"Item 6 hanya mempertahankan sekitar {retention:.2f}% trade rata-rata, terlalu rendah untuk promosi."
        )
    if item_id == "item7":
        candidate_trades = _safe_float(metrics.get("candidate_total_trades_sum"))
        if candidate_trades == 0:
            return "Item 7 membuat trade candidate kolaps ke 0 pada ticker comparable walau readiness runnable."
        return "Item 7 menambah momentum sentiment tetapi trade candidate dan kualitas sinyal tetap kolaps."
    if item_id == "item8":
        eligible_count = _safe_int(metrics.get("eligible_best_ticker_count"))
        if eligible_count == 0:
            return "Item 8 menguji adaptive search space, tetapi tidak menghasilkan satu pun konfigurasi ticker yang usable."
        return "Item 8 menghasilkan kandidat adaptive, tetapi belum ada yang cukup usable untuk direkomendasikan."
    return blocked[0] if blocked else "Tidak ada reasoning tambahan."


def _classify_item_root_causes(
    item_id: str,
    go_no_go: Dict[str, object],
    metrics: Dict[str, object],
    blocked_reasons: List[str],
) -> Dict[str, object]:
    blocked_text = " ".join(blocked_reasons).lower()
    decision = str(go_no_go.get("decision", "")).strip()

    primary = "feature_not_additive"
    supporting: List[str] = []

    if item_id == "item5":
        primary = "over_filtering"
        if "collapse ke effective confirmation threshold" in blocked_text or "baseline phase a aktif" in blocked_text:
            supporting.append("baseline_mismatch")
        if "min_trades" in blocked_text or "dukungan sampelnya belum cukup" in blocked_text:
            supporting.append("insufficient_trade_sample")
        if _safe_float(metrics.get("mean_score")) is not None and _safe_float(metrics.get("mean_score")) <= 0:
            supporting.append("feature_not_additive")
        elif decision == "no_go":
            supporting.append("feature_not_additive")
    elif item_id == "item6":
        primary = "trade_retention_too_low"
        if _safe_int(metrics.get("comparable_ticker_count")) is not None and _safe_int(metrics.get("comparable_ticker_count")) < 5:
            supporting.append("insufficient_trade_sample")
        if decision == "no_go":
            supporting.append("feature_not_additive")
        if (
            _safe_float(metrics.get("candidate_total_trades_sum")) is not None
            and _safe_float(metrics.get("baseline_total_trades_sum")) is not None
            and _safe_float(metrics.get("candidate_total_trades_sum")) < _safe_float(metrics.get("baseline_total_trades_sum"))
        ):
            supporting.append("over_filtering")
    elif item_id == "item7":
        candidate_trades = _safe_float(metrics.get("candidate_total_trades_sum"))
        primary = "signal_collapse" if candidate_trades == 0 else "trade_retention_too_low"
        ready_count = _safe_int(metrics.get("valid_ticker_count"))
        selected_count = _safe_int(metrics.get("selected_ticker_count"))
        unusable_count = _safe_int(metrics.get("unusable_ticker_count"))
        if (
            unusable_count and unusable_count > 0
        ) or (
            ready_count is not None and selected_count is not None and ready_count < selected_count
        ):
            supporting.append("sentiment_data_weak_or_non_informative")
        supporting.append("trade_retention_too_low")
        if decision == "no_go":
            supporting.append("feature_not_additive")
    elif item_id == "item8":
        adaptive_supported = bool(metrics.get("adaptive_model_supported"))
        eligible_count = _safe_int(metrics.get("eligible_best_ticker_count"))
        primary = (
            "adaptive_config_not_usable"
            if (eligible_count is None or eligible_count <= 0 or not adaptive_supported)
            else "feature_not_additive"
        )
        if "min_trades" in blocked_text or "lolos min_trades" in blocked_text or (eligible_count is not None and eligible_count <= 0):
            supporting.append("insufficient_trade_sample")
        outcome_counts = safe_dict(metrics.get("ticker_outcome_counts"))
        worsen_count = _safe_int(outcome_counts.get("worsen"))
        improve_count = _safe_int(outcome_counts.get("improve"))
        if (
            worsen_count is not None
            and improve_count is not None
            and worsen_count >= max(1, improve_count)
        ):
            supporting.append("feature_not_additive")
        if not adaptive_supported or (eligible_count is not None and eligible_count <= 0):
            supporting.append("signal_collapse")

    supporting = [cause for cause in dedupe(supporting) if cause != primary][:3]
    if not supporting:
        supporting = ["feature_not_additive"] if primary != "feature_not_additive" else ["insufficient_trade_sample"]

    return {
        "primary_root_cause": primary,
        "supporting_root_causes": supporting[:3],
        "reasoning": _make_reasoning(item_id=item_id, metrics=metrics, blocked=blocked_reasons),
    }


def _load_item_artifact(output_dir: Path, item_id: str) -> Dict[str, object]:
    spec = ITEM_SPECS[item_id]
    go_path = output_dir / str(spec["go_no_go_json"])
    report_path = output_dir / str(spec["report_txt"])

    go_no_go, go_warnings = read_json_object(go_path, f"{spec['label']} go/no-go JSON")
    report_text, report_warnings = _read_text(report_path, f"{spec['label']} report TXT")

    optional_payloads: Dict[str, Dict[str, object]] = {}
    optional_warnings: List[str] = []
    for filename in list(spec.get("optional_json") or []):
        payload, warnings = read_json_object(output_dir / filename, f"{spec['label']} optional JSON")
        optional_warnings.extend(warnings)
        if payload is not None:
            optional_payloads[filename] = payload

    warnings = dedupe([*go_warnings, *report_warnings, *optional_warnings])
    gaps = [item for item in warnings if "not found" in item.lower() or "invalid" in item.lower()]

    if go_no_go is None:
        return {
            "item_id": item_id,
            "label": spec["label"],
            "available": False,
            "decision": None,
            "experiment_status": "missing",
            "next_action": None,
            "is_final": False,
            "blocked_reasons": [],
            "metrics": {},
            "root_causes": {
                "primary_root_cause": "insufficient_trade_sample",
                "supporting_root_causes": ["feature_not_additive"],
                "reasoning": "Artifact keputusan final tidak tersedia sehingga postmortem item ini belum final.",
            },
            "warnings": warnings,
            "gaps": gaps,
            "artifact_paths": {
                "go_no_go_json": str(go_path),
                "report_txt": str(report_path),
            },
        }

    report_metrics = _parse_report_metrics(report_text)
    metrics = _build_item_metrics(
        item_id=item_id,
        go_no_go=go_no_go,
        report_metrics=report_metrics,
        optional_json_payloads=optional_payloads,
    )
    root_causes = _classify_item_root_causes(
        item_id=item_id,
        go_no_go=go_no_go,
        metrics=metrics,
        blocked_reasons=_extract_blocked_reasons(go_no_go),
    )
    decision = str(go_no_go.get("decision", "")).strip() or None
    experiment_status = _extract_item_status(item_id=item_id, go_no_go=go_no_go)
    next_action = _extract_next_action(item_id=item_id, go_no_go=go_no_go)
    is_final = bool(decision in FINAL_DECISIONS and experiment_status not in {"pending", "running", "missing"})

    return {
        "item_id": item_id,
        "label": spec["label"],
        "available": True,
        "decision": decision,
        "experiment_status": experiment_status,
        "next_action": next_action,
        "is_final": is_final,
        "blocked_reasons": _extract_blocked_reasons(go_no_go),
        "metrics": metrics,
        "root_causes": root_causes,
        "warnings": warnings,
        "gaps": gaps,
        "artifact_paths": {
            "go_no_go_json": str(go_path),
            "report_txt": str(report_path),
        },
    }


def _summarize_root_problem_class(items: List[Dict[str, object]]) -> str:
    items_with_foundation = 0
    items_with_feature = 0
    for item in items:
        causes = [
            str(safe_dict(item.get("root_causes")).get("primary_root_cause", "")).strip(),
            *[str(value).strip() for value in list(safe_dict(item.get("root_causes")).get("supporting_root_causes") or [])],
        ]
        causes = [cause for cause in causes if cause]
        if any(cause in FOUNDATIONAL_CAUSES for cause in causes):
            items_with_foundation += 1
        if any(cause in {"over_filtering", "feature_not_additive"} for cause in causes):
            items_with_feature += 1

    if items_with_foundation >= 3:
        return "foundation_and_signal_usability"
    if items_with_feature >= 3 and items_with_foundation <= 1:
        return "non_additive_feature_filters"
    return "mixed_phase_b_failure"


def _build_must_fix_before_phase_c(items: List[Dict[str, object]]) -> List[str]:
    all_causes: List[str] = []
    for item in items:
        root_causes = safe_dict(item.get("root_causes"))
        primary = str(root_causes.get("primary_root_cause", "")).strip()
        supporting = [str(value).strip() for value in list(root_causes.get("supporting_root_causes") or [])]
        all_causes.extend([cause for cause in [primary, *supporting] if cause])

    ordered: List[str] = []
    if "baseline_mismatch" in all_causes or "over_filtering" in all_causes:
        ordered.append(
            "Audit overlap baseline versus filter tambahan agar eksperimen baru tidak collapse ke aturan yang sudah aktif."
        )
    if "trade_retention_too_low" in all_causes or "signal_collapse" in all_causes:
        ordered.append(
            "Review entry/exit baseline, hold period, dan trade labeling karena filter tambahan menurunkan retensi trade terlalu agresif."
        )
    if "insufficient_trade_sample" in all_causes:
        ordered.append(
            "Audit sample size per ticker dan definisikan ulang coverage minimum yang realistis sebelum eksperimen berikutnya."
        )
    if "sentiment_data_weak_or_non_informative" in all_causes:
        ordered.append(
            "Audit distribusi sentiment series, article count, dan relevansi timing sentiment terhadap entry trade."
        )
    if "adaptive_config_not_usable" in all_causes:
        ordered.append(
            "Sederhanakan search space adaptive dan pastikan success criteria usable sebelum adaptive diuji lagi."
        )
    return ordered[:5]


def _decide_phase_b_status(
    items: List[Dict[str, object]],
    root_problem_class: str,
) -> Dict[str, object]:
    final_items = [item for item in items if bool(item.get("is_final"))]
    decisions = [str(item.get("decision", "")).strip() for item in final_items if item.get("decision")]
    all_items_final = len(final_items) == len(items)
    all_no_go = len(decisions) == len(items) and all(decision == "no_go" for decision in decisions)
    any_promoted = any(
        decision in {"promote_global", "promote_for_subset", "promote_group_specific", "promote_ticker_specific"}
        for decision in decisions
    )
    any_keep_experimental = any(decision == "keep_experimental" for decision in decisions)
    gap_count = sum(len(list(item.get("gaps") or [])) for item in items)

    if not all_items_final or any_keep_experimental:
        status = "phase_b_keep_experimental"
        reason = "Masih ada item Fase B yang belum final atau masih berstatus keep_experimental."
    elif all_no_go and gap_count >= 4:
        status = "phase_b_closed_failed"
        reason = "Semua item gagal tetapi artifact final terlalu banyak gap untuk menarik learning yang cukup kuat."
    elif all_no_go and root_problem_class == "foundation_and_signal_usability":
        status = "phase_b_closed_with_learnings_no_candidate"
        reason = "Semua item final no_go dan akar masalah dominan menyentuh usability sinyal, retensi trade, dan sample coverage."
    elif all_no_go or any_promoted:
        status = "phase_b_closed_with_learnings"
        reason = "Fase B sudah menghasilkan keputusan final dan learning yang cukup jelas untuk langkah berikutnya."
    else:
        status = "phase_b_closed_failed"
        reason = "Fase B ditutup tanpa jalur promosi yang layak."

    return {
        "phase_b_status": status,
        "all_items_final": all_items_final,
        "all_items_no_go": all_no_go,
        "any_item_promoted": any_promoted,
        "any_item_keep_experimental": any_keep_experimental,
        "reason": reason,
    }


def _decide_phase_c(
    phase_b_status: str,
    root_problem_class: str,
    transition_payload: Optional[Dict[str, object]],
    items: List[Dict[str, object]],
) -> Dict[str, object]:
    must_fix = _build_must_fix_before_phase_c(items)
    _ = phase_b_status
    _ = root_problem_class
    _ = transition_payload
    decision = "phase_c_no_go_yet"
    recommended_next_action = "stop_and_collect_more_data_then_redesign_framework"
    can_continue = False

    return {
        "phase_c_decision": decision,
        "recommended_next_action": recommended_next_action,
        "can_continue_to_phase_c": can_continue,
        "must_fix_before_phase_c": must_fix,
    }


def _build_phase_b_summary(
    phase_b_status: str,
    items: List[Dict[str, object]],
    root_problem_class: str,
) -> str:
    decisions = []
    for item in items:
        decisions.append(f"{item['item_id']}={item.get('decision') or 'missing'}")
    summary = ", ".join(decisions)
    if phase_b_status == "phase_b_needs_redesign_before_continue":
        return (
            f"Fase B ditutup tanpa promosi baseline ({summary}); pola gagal didominasi {root_problem_class}, "
            "sehingga redesign minimum dibutuhkan sebelum lanjut."
        )
    if phase_b_status == "phase_b_closed_with_learnings_no_candidate":
        return (
            f"Fase B ditutup tanpa promosi baseline ({summary}); pola gagal didominasi {root_problem_class}, "
            "dan langkah resmi berikutnya adalah collect more data plus redesign framework evaluasi."
        )
    if phase_b_status == "phase_b_closed_with_learnings":
        return (
            f"Fase B ditutup dengan learning yang cukup jelas ({summary}); eksperimen tambahan sebaiknya tidak diteruskan dalam bentuk sekarang."
        )
    if phase_b_status == "phase_b_keep_experimental":
        return f"Fase B belum final ({summary}) karena sebagian artifact/keputusan belum lengkap."
    return f"Fase B ditutup gagal ({summary})."


def _write_root_cause_matrix(path: Path, items: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "item_id",
                "decision",
                "experiment_status",
                "primary_root_cause",
                "supporting_root_causes",
                "reasoning",
                "artifact_gaps",
            ],
        )
        writer.writeheader()
        for item in items:
            root_causes = safe_dict(item.get("root_causes"))
            writer.writerow(
                {
                    "item_id": item["item_id"],
                    "decision": item.get("decision") or "missing",
                    "experiment_status": item.get("experiment_status") or "unknown",
                    "primary_root_cause": root_causes.get("primary_root_cause") or "",
                    "supporting_root_causes": "|".join(
                        str(value)
                        for value in list(root_causes.get("supporting_root_causes") or [])
                    ),
                    "reasoning": root_causes.get("reasoning") or "",
                    "artifact_gaps": "|".join(str(value) for value in list(item.get("gaps") or [])),
                }
            )


def _build_redesign_plan(
    generated_at: str,
    output_dir: Path,
    items: List[Dict[str, object]],
) -> Dict[str, object]:
    experiments = [
        {
            "experiment_id": "phase_b_v2_exp1_baseline_trade_shape_audit",
            "priority": 1,
            "focus": "Audit entry/exit baseline, hold period, dan labeling untuk melihat mengapa semua filter tambahan menurunkan retensi trade.",
            "success_criteria": "Ada hipotesis konkret tentang sumber collapse trade dan perubahan minimal yang bisa diuji.",
        },
        {
            "experiment_id": "phase_b_v2_exp2_filter_overlap_audit",
            "priority": 2,
            "focus": "Audit overlap baseline versus filter item 5/6/7 agar eksperimen tidak hanya menduplikasi constraint yang sudah aktif.",
            "success_criteria": "Ditemukan filter mana yang redundant dan mana yang benar-benar orthogonal terhadap baseline.",
        },
        {
            "experiment_id": "phase_b_v2_exp3_sample_size_coverage_audit",
            "priority": 3,
            "focus": "Audit sample size per ticker, comparable coverage, dan kecukupan min_trades terhadap horizon data yang ada.",
            "success_criteria": "Ada aturan coverage minimum yang realistis dan konsisten untuk evaluasi berikutnya.",
        },
        {
            "experiment_id": "phase_b_v2_exp4_sentiment_series_relevance_audit",
            "priority": 4,
            "focus": "Audit distribusi sentiment series, article count, dan timing relevansi sentiment terhadap trigger entry.",
            "success_criteria": "Jelas apakah sentiment layak dipakai sebagai gate timing atau hanya cocok sebagai konteks, bukan filter entry.",
        },
        {
            "experiment_id": "phase_b_v2_exp5_single_change_rerun",
            "priority": 5,
            "focus": "Rerun satu eksperimen paling kecil dengan satu perubahan saja setelah audit di atas, bukan sweep besar.",
            "success_criteria": "Ada bukti apakah redesign minimum memperbaiki retention dan usability tanpa menambah kompleksitas besar.",
        },
    ]
    return {
        "generated_at": generated_at,
        "phase_b_v2_needed": True,
        "scope": "minimum_redesign_only",
        "reason": "Phase B belum layak lanjut ke Phase C; redesign difokuskan pada baseline, data, dan evaluasi.",
        "experiments": experiments[:5],
        "source_items": [item["item_id"] for item in items],
        "artifacts": {
            "json": str(output_dir / "phase_b_v2_redesign_plan.json"),
            "txt": str(output_dir / "phase_b_v2_redesign_plan.txt"),
        },
    }


def _write_redesign_plan(output_dir: Path, redesign: Dict[str, object]) -> Dict[str, Path]:
    json_path = output_dir / "phase_b_v2_redesign_plan.json"
    txt_path = output_dir / "phase_b_v2_redesign_plan.txt"
    lines = [
        "Phase B v2 Minimum Redesign Plan",
        "================================",
        "",
        f"- Generated at: {redesign['generated_at']}",
        f"- Scope: {redesign['scope']}",
        f"- Reason: {redesign['reason']}",
        "",
        "Minimum experiments:",
    ]
    for experiment in list(redesign.get("experiments") or []):
        lines.append(
            f"- P{experiment['priority']}: {experiment['experiment_id']} | {experiment['focus']}"
        )
        lines.append(f"  success_criteria={experiment['success_criteria']}")

    json_path.write_text(json.dumps(redesign, indent=2, ensure_ascii=True), encoding="utf-8")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json_path": json_path, "txt_path": txt_path}


def _update_transition_layer(
    output_dir: Path,
    generated_at: str,
    phase_b_status: str,
    phase_b_summary: str,
    phase_c_decision: str,
    recommended_next_action: str,
) -> Dict[str, object]:
    transition_path = output_dir / "phase_a_to_phase_b_transition.json"
    payload, warnings = read_json_object(transition_path, "Phase A to Phase B transition JSON")
    if payload is None:
        return {
            "updated": False,
            "path": str(transition_path),
            "warnings": warnings,
        }

    payload["phase_b_status"] = phase_b_status
    payload["phase_b_summary"] = phase_b_summary
    payload["next_phase_recommendation"] = recommended_next_action
    payload["phase_c_decision"] = phase_c_decision
    payload["phase_b_postmortem_generated_at"] = generated_at
    transition_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    report_path = output_dir / "phase_a_to_phase_b_transition_report.txt"
    report_text, _ = _read_text(report_path, "Phase A to Phase B transition report TXT")
    appendix = [
        "",
        "Phase B Postmortem Update:",
        f"- Phase B status: {phase_b_status}",
        f"- Phase B summary: {phase_b_summary}",
        f"- Phase C decision: {phase_c_decision}",
        f"- Next phase recommendation: {recommended_next_action}",
        f"- Updated at: {generated_at}",
    ]
    merged = (report_text.rstrip() if report_text else "").rstrip()
    report_path.write_text((merged + "\n" + "\n".join(appendix)).lstrip("\n") + "\n", encoding="utf-8")

    return {
        "updated": True,
        "path": str(transition_path),
        "report_path": str(report_path),
        "warnings": warnings,
    }


def finalize_phase_b_postmortem(output_dir: Path) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = _now_iso()

    transition_payload, transition_warnings = read_json_object(
        output_dir / "phase_a_to_phase_b_transition.json",
        "Phase A to Phase B transition JSON",
    )
    items = [_load_item_artifact(output_dir=output_dir, item_id=item_id) for item_id in ITEM_SPECS]
    all_gaps = dedupe(
        [*transition_warnings, *[gap for item in items for gap in list(item.get("gaps") or [])]]
    )
    root_problem_class = _summarize_root_problem_class(items)
    phase_b_status_payload = _decide_phase_b_status(items=items, root_problem_class=root_problem_class)
    phase_c_payload = _decide_phase_c(
        phase_b_status=str(phase_b_status_payload["phase_b_status"]),
        root_problem_class=root_problem_class,
        transition_payload=transition_payload,
        items=items,
    )
    phase_b_summary = _build_phase_b_summary(
        phase_b_status=str(phase_b_status_payload["phase_b_status"]),
        items=items,
        root_problem_class=root_problem_class,
    )

    postmortem_payload = {
        "generated_at": generated_at,
        "phase_b_status": phase_b_status_payload["phase_b_status"],
        "phase_b_status_reason": phase_b_status_payload["reason"],
        "phase_b_summary": phase_b_summary,
        "phase_c_decision": phase_c_payload["phase_c_decision"],
        "recommended_next_action": phase_c_payload["recommended_next_action"],
        "root_problem_class": root_problem_class,
        "can_continue_to_phase_c": phase_c_payload["can_continue_to_phase_c"],
        "must_fix_before_phase_c": phase_c_payload["must_fix_before_phase_c"],
        "items": items,
        "artifact_gaps": all_gaps,
        "transition_context": {
            "available": transition_payload is not None,
            "phase_b_entry_mode": safe_dict(transition_payload).get("phase_b_entry_mode"),
            "phase_b_entry_allowed": safe_dict(transition_payload).get("phase_b_entry_allowed"),
            "transition_status": safe_dict(transition_payload).get("transition_status"),
        },
        "rule_evaluation": {
            **phase_b_status_payload,
            **phase_c_payload,
        },
    }

    root_cause_csv_path = output_dir / "phase_b_root_cause_matrix.csv"
    _write_root_cause_matrix(path=root_cause_csv_path, items=items)

    postmortem_json_path = output_dir / "phase_b_postmortem.json"
    postmortem_txt_path = output_dir / "phase_b_postmortem.txt"
    final_status_path = output_dir / "phase_b_final_status.json"
    next_phase_path = output_dir / "phase_b_go_no_go_next_phase.json"

    postmortem_json_path.write_text(
        json.dumps(postmortem_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    report_lines = [
        "Phase B Official Postmortem",
        "===========================",
        "",
        f"- Generated at: {generated_at}",
        f"- Phase B status: {phase_b_status_payload['phase_b_status']}",
        f"- Phase B status reason: {phase_b_status_payload['reason']}",
        f"- Phase C decision: {phase_c_payload['phase_c_decision']}",
        f"- Root problem class: {root_problem_class}",
        f"- Recommended next action: {phase_c_payload['recommended_next_action']}",
        "",
        "Strategic summary:",
        f"- {phase_b_summary}",
        "",
        "Per-item conclusions:",
    ]
    for item in items:
        root_causes = safe_dict(item.get("root_causes"))
        report_lines.append(
            f"- {item['item_id']}: decision={item.get('decision') or 'missing'} | "
            f"primary_root_cause={root_causes.get('primary_root_cause')} | "
            f"supporting={','.join(str(value) for value in list(root_causes.get('supporting_root_causes') or [])) or 'none'}"
        )
        report_lines.append(f"  reasoning={root_causes.get('reasoning')}")
    if all_gaps:
        report_lines.extend(["", "Artifact gaps:"])
        for gap in all_gaps:
            report_lines.append(f"- {gap}")
    if phase_c_payload["must_fix_before_phase_c"]:
        report_lines.extend(["", "Must fix before Phase C:"])
        for item in phase_c_payload["must_fix_before_phase_c"]:
            report_lines.append(f"- {item}")

    postmortem_txt_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    final_status_payload = {
        "generated_at": generated_at,
        "phase_b_status": phase_b_status_payload["phase_b_status"],
        "reason": phase_b_status_payload["reason"],
        "root_problem_class": root_problem_class,
        "all_items_final": phase_b_status_payload["all_items_final"],
        "all_items_no_go": phase_b_status_payload["all_items_no_go"],
        "any_item_promoted": phase_b_status_payload["any_item_promoted"],
        "any_item_keep_experimental": phase_b_status_payload["any_item_keep_experimental"],
    }
    final_status_path.write_text(
        json.dumps(final_status_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    next_phase_payload = {
        "phase_b_status": phase_b_status_payload["phase_b_status"],
        "phase_c_decision": phase_c_payload["phase_c_decision"],
        "root_problem_class": root_problem_class,
        "recommended_next_action": phase_c_payload["recommended_next_action"],
        "can_continue_to_phase_c": phase_c_payload["can_continue_to_phase_c"],
        "must_fix_before_phase_c": phase_c_payload["must_fix_before_phase_c"],
        "generated_at": generated_at,
    }
    next_phase_path.write_text(
        json.dumps(next_phase_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    redesign_result: Optional[Dict[str, Path]] = None
    redesign_payload: Optional[Dict[str, object]] = None
    if phase_c_payload["phase_c_decision"] == "phase_c_no_go_yet":
        redesign_payload = _build_redesign_plan(
            generated_at=generated_at,
            output_dir=output_dir,
            items=items,
        )
        redesign_result = _write_redesign_plan(output_dir=output_dir, redesign=redesign_payload)

    transition_update = _update_transition_layer(
        output_dir=output_dir,
        generated_at=generated_at,
        phase_b_status=str(phase_b_status_payload["phase_b_status"]),
        phase_b_summary=phase_b_summary,
        phase_c_decision=str(phase_c_payload["phase_c_decision"]),
        recommended_next_action=str(phase_c_payload["recommended_next_action"]),
    )

    return {
        "postmortem_payload": postmortem_payload,
        "final_status_payload": final_status_payload,
        "next_phase_payload": next_phase_payload,
        "postmortem_json_path": postmortem_json_path,
        "postmortem_txt_path": postmortem_txt_path,
        "root_cause_csv_path": root_cause_csv_path,
        "final_status_path": final_status_path,
        "next_phase_path": next_phase_path,
        "redesign_payload": redesign_payload,
        "redesign_paths": redesign_result,
        "transition_update": transition_update,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize Phase B postmortem and next-phase strategic decision."
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory containing and receiving Phase B artifacts. Default: output",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = finalize_phase_b_postmortem(output_dir=Path(args.output_dir))
    payload = result["postmortem_payload"]
    print(f"Phase B status: {payload['phase_b_status']}")
    print(f"Phase C decision: {payload['phase_c_decision']}")
    print(f"Postmortem JSON: {result['postmortem_json_path']}")
    print(f"Next-phase JSON: {result['next_phase_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
