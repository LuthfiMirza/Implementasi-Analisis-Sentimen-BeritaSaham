"""Audit policy alignment for the Phase B news distribution gate."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import read_json_object, safe_dict  # noqa: E402


AUDIT_OUTPUT = "phase_b_news_distribution_policy_alignment_audit.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


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


def _read_json(path: Path, label: str) -> Dict[str, object]:
    payload, _ = read_json_object(path, label)
    return safe_dict(payload)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _threshold_lookup(rows: object) -> Dict[str, Dict[str, object]]:
    lookup: Dict[str, Dict[str, object]] = {}
    for row in list(rows or []):
        item = safe_dict(row)
        name = _safe_str(item.get("blocker_name"))
        if name:
            lookup[name] = item
    return lookup


def run_phase_b_news_distribution_policy_alignment_audit(*, output_dir: Path) -> Dict[str, object]:
    output_dir = Path(output_dir)

    readiness = _read_json(output_dir / "phase_b_retest_readiness_gate.json", "phase_b_retest_readiness_gate")
    blocker_audit = _read_json(output_dir / "phase_b_readiness_blocker_audit.json", "phase_b_readiness_blocker_audit")
    threshold_audit = _read_json(
        output_dir / "phase_b_news_distribution_threshold_audit.json",
        "phase_b_news_distribution_threshold_audit",
    )

    threshold_rows = _threshold_lookup(blocker_audit.get("all_threshold_checks"))
    density_row = safe_dict(threshold_rows.get("news_distribution_gate::median_news_density_pct"))
    share_row = safe_dict(threshold_rows.get("news_distribution_gate::no_single_ticker_article_share"))
    total_articles_row = safe_dict(threshold_rows.get("news_distribution_gate::primary_segment_total_articles"))
    median_days_row = safe_dict(threshold_rows.get("news_distribution_gate::primary_segment_article_days_median"))
    primary_ticker_count_row = safe_dict(threshold_rows.get("universe_coverage_gate::primary_segment_ticker_count"))

    official_universe = safe_dict(threshold_audit.get("official_distribution_universe"))
    distribution_stats = safe_dict(threshold_audit.get("distribution_statistics"))
    realism = safe_dict(threshold_audit.get("threshold_realism_assessment"))
    feasibility = safe_dict(threshold_audit.get("operational_feasibility_assessment"))
    density_breakdown = [safe_dict(row) for row in list(threshold_audit.get("per_ticker_density_breakdown") or [])]
    primary_breakdown = [
        row for row in density_breakdown
        if bool(row.get("included_in_primary_distribution_pool"))
    ]

    primary_density_values = [_safe_float(row.get("news_density_pct_current")) for row in primary_breakdown]
    primary_median_density = (
        round(float(statistics.median(primary_density_values)), 4) if primary_density_values else 0.0
    )
    primary_tickers_at_or_above_threshold = [
        _safe_str(row.get("ticker"))
        for row in primary_breakdown
        if _safe_float(row.get("news_density_pct_current")) >= _safe_float(density_row.get("target_value"))
    ]

    current_definition = {
        "gate_name": "news_distribution_gate",
        "status": _safe_str(readiness.get("news_distribution_gate")),
        "subchecks": [
            {
                "threshold_name": "median_news_density_pct",
                "operator": _safe_str(density_row.get("operator")),
                "target_value": _safe_float(density_row.get("target_value")),
                "actual_value": _safe_float(density_row.get("actual_value")),
                "scope": "current ticker universe from data/ticker_metadata.csv",
                "scope_tickers": list(official_universe.get("density_gate_tickers") or []),
                "scope_ticker_count": _safe_int(official_universe.get("density_gate_ticker_count")),
                "source_of_truth_artifact": _safe_str(density_row.get("source_of_truth_artifact")),
                "source_field": _safe_str(density_row.get("source_field")),
            },
            {
                "threshold_name": "primary_segment_total_articles",
                "operator": _safe_str(total_articles_row.get("operator")),
                "target_value": _safe_float(total_articles_row.get("target_value")),
                "actual_value": _safe_float(total_articles_row.get("actual_value")),
                "scope": _safe_str(official_universe.get("primary_distribution_pool_scope")),
                "scope_tickers": list(official_universe.get("primary_distribution_pool_tickers") or []),
                "scope_ticker_count": _safe_int(official_universe.get("primary_distribution_pool_ticker_count")),
                "source_of_truth_artifact": _safe_str(total_articles_row.get("source_of_truth_artifact")),
                "source_field": _safe_str(total_articles_row.get("source_field")),
            },
            {
                "threshold_name": "primary_segment_article_days_median",
                "operator": _safe_str(median_days_row.get("operator")),
                "target_value": _safe_float(median_days_row.get("target_value")),
                "actual_value": _safe_float(median_days_row.get("actual_value")),
                "scope": _safe_str(official_universe.get("primary_distribution_pool_scope")),
                "scope_tickers": list(official_universe.get("primary_distribution_pool_tickers") or []),
                "scope_ticker_count": _safe_int(official_universe.get("primary_distribution_pool_ticker_count")),
                "source_of_truth_artifact": _safe_str(median_days_row.get("source_of_truth_artifact")),
                "source_field": _safe_str(median_days_row.get("source_field")),
            },
            {
                "threshold_name": "no_single_ticker_article_share",
                "operator": _safe_str(share_row.get("operator")),
                "target_value": _safe_float(share_row.get("target_value")),
                "actual_value": _safe_float(share_row.get("actual_value")),
                "scope": _safe_str(official_universe.get("primary_distribution_pool_scope")),
                "scope_tickers": list(official_universe.get("primary_distribution_pool_tickers") or []),
                "scope_ticker_count": _safe_int(official_universe.get("primary_distribution_pool_ticker_count")),
                "source_of_truth_artifact": _safe_str(share_row.get("source_of_truth_artifact")),
                "source_field": _safe_str(share_row.get("source_field")),
            },
        ],
    }

    compatibility_assessment = {
        "status": "incompatible",
        "reason": (
            f"Subcheck median_news_density_pct memakai threshold {_safe_float(density_row.get('target_value'))} "
            f"pada universe resmi { _safe_int(official_universe.get('density_gate_ticker_count')) } ticker, tetapi "
            f"aktual median hanya {_safe_float(density_row.get('actual_value'))}. Tidak ada ticker yang mencapai target."
        ),
        "main_problem_location": "threshold_with_secondary_metric_scope_tension",
    }

    structural_gap_assessment = {
        "actual_median_density": _safe_float(threshold_audit.get("actual_median_density")),
        "threshold_density": _safe_float(threshold_audit.get("threshold_density")),
        "gap_to_threshold": _safe_float(threshold_audit.get("gap_to_threshold")),
        "actual_mean_density": _safe_float(distribution_stats.get("actual_mean_density")),
        "actual_min_density": _safe_float(distribution_stats.get("actual_min_density")),
        "actual_max_density": _safe_float(distribution_stats.get("actual_max_density")),
        "actual_density_range": _safe_float(distribution_stats.get("actual_density_range")),
        "current_tickers_at_or_above_threshold": _safe_int(feasibility.get("current_ticker_count_at_or_above_threshold")),
        "minimum_tickers_needed_at_or_above_threshold_for_median_pass": _safe_int(
            feasibility.get("minimum_tickers_needed_at_or_above_threshold_for_median_pass")
        ),
        "minimum_additional_article_days_total_for_cheapest_path": _safe_int(
            feasibility.get("minimum_additional_article_days_total_for_cheapest_path")
        ),
        "threshold_article_days_required_for_typical_ticker": _safe_int(
            feasibility.get("threshold_article_days_required_for_typical_ticker")
        ),
        "actual_median_article_days": _safe_float(distribution_stats.get("actual_median_article_days")),
        "primary_pool_counterfactual_median_density_if_option_B_uses_primary_only": primary_median_density,
        "primary_pool_counterfactual_tickers_at_or_above_threshold": primary_tickers_at_or_above_threshold,
    }

    policy_options = [
        {
            "option_id": "A",
            "policy_path": "keep_official_distribution_universe_realign_density_threshold",
            "summary": "Pertahankan definisi universe resmi saat ini, tetapi realign threshold median density ke level yang data-aligned.",
            "pro": [
                "Perubahan paling kecil di layer policy.",
                "Tetap memakai source-of-truth universe yang sekarang dipakai gate.",
                "Mudah diaudit karena hanya threshold density yang dibahas ulang.",
            ],
            "contra": [
                "Risiko dibaca sebagai pelonggaran threshold semata.",
                "Tidak menyelesaikan fakta bahwa gate mencampur scope universe-wide density dengan primary-pool concentration.",
            ],
            "methodological_risk": "low_to_medium",
            "comparability_risk": "medium_on_gate_history_but_low_on_strategy_and_oos_artifacts",
            "implementation_effort": "low",
            "alignment_with_real_data": "better_than_current_but_still_imperfect_due_to_scope_mix",
        },
        {
            "option_id": "B",
            "policy_path": "keep_density_threshold_5_redefine_distribution_universe",
            "summary": "Pertahankan threshold 5.0, tetapi ubah universe/pool yang dihitung gate.",
            "pro": [
                "Threshold 5.0 tetap dipertahankan tanpa penurunan eksplisit.",
                "Bisa membuat seluruh subcheck news distribution memakai scope yang seragam.",
            ],
            "contra": [
                "Counterfactual primary-pool median density tetap hanya "
                f"{primary_median_density}, jadi mengganti universe saja tidak menyelesaikan mismatch.",
                "Mengubah universe berisiko terlihat arbitrer jika tidak ditopang alasan governance yang kuat.",
            ],
            "methodological_risk": "medium",
            "comparability_risk": "medium_to_high_because_gate_scope_changes",
            "implementation_effort": "medium",
            "alignment_with_real_data": "poor_if_threshold_5_is_retained",
        },
        {
            "option_id": "C",
            "policy_path": "keep_distribution_intent_replace_density_metric_with_sparse_coverage_robust_metric",
            "summary": "Pertahankan intent distribution gate, tetapi ganti metric density median ke metric yang lebih robust terhadap long-tail sparse coverage.",
            "pro": [
                "Lebih selaras dengan data harian yang sangat panjang tetapi news-event driven.",
                "Bisa memakai metric yang lebih interpretable seperti median article_days atau share tickers above minimum article-days.",
                "Memisahkan fairness distribusi dari penalti historis yang berlebihan pada universe panjang.",
            ],
            "contra": [
                "Perubahan metric lebih besar daripada sekadar realign threshold.",
                "Perlu justifikasi policy yang lebih lengkap agar tidak dianggap moving the goalposts.",
            ],
            "methodological_risk": "medium",
            "comparability_risk": "high_on_gate_metric_history",
            "implementation_effort": "medium",
            "alignment_with_real_data": "high",
        },
        {
            "option_id": "D",
            "policy_path": "hybrid_keep_share_controls_realign_density_component_with_sparse_coverage_metric_or_threshold",
            "summary": "Pertahankan kontrol concentration/primary-pool yang ada, tetapi realign khusus density component dengan threshold atau metric yang sparse-coverage aware.",
            "pro": [
                "Menjaga blocker concentration yang masih relevan seperti no_single_ticker_article_share.",
                "Mengoreksi mismatch utama di density component tanpa menghapus intent distribution gate.",
                "Paling mudah dipertahankan secara governance karena masalah utama memang ada di subcheck density, bukan seluruh gate.",
            ],
            "contra": [
                "Gate akan tetap terdiri dari subcheck dengan scope berbeda, sehingga dokumentasi harus sangat jelas.",
                "Comparability historis di subcheck density tetap berubah.",
            ],
            "methodological_risk": "low_to_medium",
            "comparability_risk": "medium_on_density_subcheck_only",
            "implementation_effort": "medium",
            "alignment_with_real_data": "highest",
        },
    ]

    recommended_policy_path = {
        "option_id": "D",
        "policy_path": "hybrid_keep_share_controls_realign_density_component_with_sparse_coverage_metric_or_threshold",
        "decision": "escalate_gate_policy_discussion_for_density_component_only",
        "rationale": [
            "Masalah eksplisit ada pada density subcheck: threshold 5.0 tidak reachable secara wajar di universe resmi saat ini.",
            "Mengganti universe saja tidak menyelesaikan mismatch; primary-pool counterfactual median pun tetap jauh di bawah 5.0.",
            "Share/concentration control masih relevan dan hampir tertutup, jadi tidak perlu dibuang bersama subcheck density.",
            "Hybrid path menjaga intent distribution governance sambil membatasi perubahan hanya pada bagian policy yang terbukti structurally misaligned.",
        ],
        "requires_gate_policy_change": True,
        "requires_strategy_or_oos_change": False,
    }

    payload = {
        "generated_at": _now_iso(),
        "source_of_truth_artifacts": {
            "readiness_gate": "output/phase_b_retest_readiness_gate.json",
            "readiness_blocker_audit": "output/phase_b_readiness_blocker_audit.json",
            "news_distribution_threshold_audit": "output/phase_b_news_distribution_threshold_audit.json",
        },
        "current_news_distribution_gate_definition": current_definition,
        "official_distribution_universe": official_universe,
        "actual_distribution_summary": {
            "actual_median_density": _safe_float(threshold_audit.get("actual_median_density")),
            "actual_mean_density": _safe_float(distribution_stats.get("actual_mean_density")),
            "dominant_ticker": _safe_str(threshold_audit.get("dominant_ticker")),
            "current_primary_pool_share": _safe_float(share_row.get("actual_value")),
            "current_primary_pool_total_articles": _safe_float(total_articles_row.get("actual_value")),
            "current_primary_pool_article_days_median": _safe_float(median_days_row.get("actual_value")),
        },
        "threshold_density": _safe_float(density_row.get("target_value")),
        "threshold_share": _safe_float(share_row.get("target_value")),
        "compatibility_assessment": compatibility_assessment,
        "structural_gap_assessment": structural_gap_assessment,
        "policy_options": policy_options,
        "recommended_policy_path": recommended_policy_path,
        "remaining_active_blockers_even_if_news_density_policy_is_realigned": [
            {
                "blocker_name": "universe_coverage_gate::primary_segment_ticker_count",
                "actual_value": _safe_float(primary_ticker_count_row.get("actual_value")),
                "target_value": _safe_float(primary_ticker_count_row.get("target_value")),
                "operator": _safe_str(primary_ticker_count_row.get("operator")),
            },
            {
                "blocker_name": "news_distribution_gate::no_single_ticker_article_share",
                "actual_value": _safe_float(share_row.get("actual_value")),
                "target_value": _safe_float(share_row.get("target_value")),
                "operator": _safe_str(share_row.get("operator")),
            },
        ],
        "readiness_status_final": _safe_str(readiness.get("final_decision")),
        "roadmap_update_assessment": {
            "allowed": False,
            "reason": "News distribution policy audit ini tidak menutup blocker lain yang masih aktif.",
        },
    }
    _write_json(output_dir / AUDIT_OUTPUT, payload)
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit policy alignment for the Phase B news distribution gate.")
    parser.add_argument("--output-dir", default="output", help="Directory containing readiness artifacts.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    payload = run_phase_b_news_distribution_policy_alignment_audit(output_dir=Path(args.output_dir))
    print("Phase B news distribution policy alignment audit complete.")
    print(f"compatibility_assessment={safe_dict(payload.get('compatibility_assessment')).get('status')}")
    print(f"recommended_policy_path={safe_dict(payload.get('recommended_policy_path')).get('policy_path')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
