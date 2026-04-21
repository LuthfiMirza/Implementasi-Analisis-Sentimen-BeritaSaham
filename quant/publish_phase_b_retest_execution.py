"""Publish roadmap and concise retest artifacts after a formal retest run."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import read_json_object, safe_dict  # noqa: E402


class PublishPhaseBRetestExecutionCliError(ValueError):
    """Friendly CLI error for retest execution publishing."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _load_required(output_dir: Path, filename: str) -> Dict[str, object]:
    payload, warnings = read_json_object(output_dir / filename, filename)
    result = safe_dict(payload)
    if result:
        return result
    detail = "; ".join(warnings) if warnings else f"{filename} not found or invalid"
    raise PublishPhaseBRetestExecutionCliError(detail)


def _load_optional(output_dir: Path, filename: str) -> Dict[str, object]:
    payload, _ = read_json_object(output_dir / filename, filename)
    return safe_dict(payload)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _primary_segment_tickers(summary: Dict[str, object]) -> List[str]:
    tested_segments = list(summary.get("tested_segments") or [])
    if not tested_segments:
        return []
    first = safe_dict(tested_segments[0])
    return [str(item).strip() for item in list(first.get("tickers") or []) if str(item).strip()]


def build_retest_execution_summary(output_dir: Path) -> Dict[str, object]:
    readiness = _load_required(output_dir, "phase_b_retest_readiness_gate.json")
    blockers = _load_required(output_dir, "phase_b_readiness_blocker_audit.json")
    summary = _load_required(output_dir, "baseline_v9_segment_oos_summary.json")
    go_no_go = _load_required(output_dir, "baseline_v9_segment_oos_go_no_go.json")
    closeout = _load_required(output_dir, "phase_b_final_closeout.json")
    project_decision = _load_required(output_dir, "project_after_phase_b_decision.json")
    roadmap = _load_optional(output_dir, "project_roadmap_status.json")

    primary_summary = safe_dict(safe_dict(list(summary.get("tested_segments") or [{}])[0]).get("summary"))
    official_primary_segment_tickers = _primary_segment_tickers(summary)

    payload = {
        "generated_at": _now_iso(),
        "source_of_truth_artifacts": {
            "readiness_gate": "output/phase_b_retest_readiness_gate.json",
            "readiness_blockers": "output/phase_b_readiness_blocker_audit.json",
            "oos_summary": "output/baseline_v9_segment_oos_summary.json",
            "oos_go_no_go": "output/baseline_v9_segment_oos_go_no_go.json",
            "phase_b_closeout": "output/phase_b_final_closeout.json",
            "project_after_phase_b_decision": "output/project_after_phase_b_decision.json",
        },
        "retest_readiness_status": readiness.get("final_decision"),
        "readiness_gate_all_pass": readiness.get("final_decision") == "boleh_retest",
        "active_blockers": list(blockers.get("active_blockers") or []),
        "strategy_retest_status": "executed",
        "candidate_id": go_no_go.get("candidate_id"),
        "primary_segment": go_no_go.get("primary_segment"),
        "official_primary_segment_tickers": official_primary_segment_tickers,
        "retest_result": go_no_go.get("decision"),
        "recommended_retest_next_action": go_no_go.get("recommended_next_action"),
        "phase_b_final_status": closeout.get("phase_b_final_status"),
        "project_phase_c_status": project_decision.get("phase_c_status")
        or closeout.get("phase_c_status")
        or safe_dict(roadmap.get("latest_execution_status")).get("phase_c_decision"),
        "can_continue_strategy_experiments_now": project_decision.get("can_continue_strategy_experiments_now"),
        "can_continue_to_phase_c": project_decision.get("can_continue_to_phase_c"),
        "primary_segment_metrics": {
            "ticker_count": primary_summary.get("ticker_count"),
            "active_ticker_count": primary_summary.get("active_ticker_count"),
            "candidate_total_trades": primary_summary.get("candidate_total_trades"),
            "trade_weighted_average_return": primary_summary.get("trade_weighted_average_return"),
            "mean_average_return_active": primary_summary.get("mean_average_return_active"),
            "positive_fold_share": primary_summary.get("positive_fold_share"),
            "oos_stability_ok": primary_summary.get("oos_stability_ok"),
            "ticker_consistency_ok": primary_summary.get("ticker_consistency_ok"),
            "outlier_bias_ok": primary_summary.get("outlier_bias_ok"),
        },
        "decisive_statement": project_decision.get("decisive_statement")
        or closeout.get("decisive_statement")
        or "Retest resmi sudah dijalankan; lihat keputusan go/no-go untuk langkah berikutnya.",
    }
    return payload


def build_retest_execution_text(payload: Dict[str, object]) -> str:
    metrics = safe_dict(payload.get("primary_segment_metrics"))
    lines = [
        "Phase B Retest Execution Summary",
        "================================",
        "",
        f"- generated_at={payload.get('generated_at')}",
        f"- retest_readiness_status={payload.get('retest_readiness_status')}",
        f"- strategy_retest_status={payload.get('strategy_retest_status')}",
        f"- candidate_id={payload.get('candidate_id')}",
        f"- primary_segment={payload.get('primary_segment')}",
        f"- official_primary_segment_tickers={', '.join(list(payload.get('official_primary_segment_tickers') or [])) or '-'}",
        f"- retest_result={payload.get('retest_result')}",
        f"- recommended_retest_next_action={payload.get('recommended_retest_next_action')}",
        f"- phase_b_final_status={payload.get('phase_b_final_status')}",
        f"- project_phase_c_status={payload.get('project_phase_c_status')}",
        f"- can_continue_strategy_experiments_now={payload.get('can_continue_strategy_experiments_now')}",
        f"- can_continue_to_phase_c={payload.get('can_continue_to_phase_c')}",
        "",
        "Primary segment metrics:",
        f"- ticker_count={metrics.get('ticker_count')}",
        f"- active_ticker_count={metrics.get('active_ticker_count')}",
        f"- candidate_total_trades={metrics.get('candidate_total_trades')}",
        f"- trade_weighted_average_return={metrics.get('trade_weighted_average_return')}",
        f"- mean_average_return_active={metrics.get('mean_average_return_active')}",
        f"- positive_fold_share={metrics.get('positive_fold_share')}",
        f"- oos_stability_ok={metrics.get('oos_stability_ok')}",
        f"- ticker_consistency_ok={metrics.get('ticker_consistency_ok')}",
        f"- outlier_bias_ok={metrics.get('outlier_bias_ok')}",
        "",
        f"- decisive_statement={payload.get('decisive_statement')}",
    ]
    return "\n".join(lines) + "\n"


def build_updated_roadmap(output_dir: Path, retest_summary: Dict[str, object]) -> Dict[str, object]:
    roadmap = _load_optional(output_dir, "project_roadmap_status.json")
    readiness = _load_required(output_dir, "phase_b_retest_readiness_gate.json")
    project_decision = _load_required(output_dir, "project_after_phase_b_decision.json")

    latest = dict(roadmap.get("latest_execution_status") or {})
    latest.update(
        {
            "phase_b_status": project_decision.get("phase_b_final_status")
            or latest.get("phase_b_status")
            or "phase_b_closed_with_learnings_no_candidate",
            "phase_c_decision": project_decision.get("phase_c_status")
            or retest_summary.get("project_phase_c_status")
            or latest.get("phase_c_decision")
            or "phase_c_no_go_yet",
            "current_track": "phase_b_retest_executed_formal_closeout_published",
            "recommended_next_action": project_decision.get("recommended_primary_next_step")
            or retest_summary.get("recommended_retest_next_action")
            or latest.get("recommended_next_action"),
            "retest_readiness_status": readiness.get("final_decision"),
            "retest_readiness_snapshot_published": readiness.get("final_decision") == "boleh_retest",
            "strategy_retest_status": "executed",
            "strategy_retest_result": retest_summary.get("retest_result"),
            "strategy_retest_candidate": retest_summary.get("candidate_id"),
            "strategy_retest_primary_segment": retest_summary.get("primary_segment"),
            "official_primary_segment_tickers": retest_summary.get("official_primary_segment_tickers"),
            "can_continue_strategy_experiments_now": project_decision.get("can_continue_strategy_experiments_now"),
        }
    )

    payload = dict(roadmap)
    payload.update(
        {
            "generated_at": _now_iso(),
            "current_focus": "phase_b_retest_closeout",
            "latest_execution_status": latest,
            "retest_execution": {
                "status": "executed",
                "readiness_gate_decision": readiness.get("final_decision"),
                "roadmap_ready_for_retest_snapshot_published": readiness.get("final_decision") == "boleh_retest",
                "official_result": retest_summary.get("retest_result"),
                "candidate_id": retest_summary.get("candidate_id"),
                "primary_segment": retest_summary.get("primary_segment"),
                "official_primary_segment_tickers": retest_summary.get("official_primary_segment_tickers"),
                "phase_b_final_status": project_decision.get("phase_b_final_status"),
                "phase_c_decision": project_decision.get("phase_c_status")
                or retest_summary.get("project_phase_c_status"),
                "recommended_next_action": project_decision.get("recommended_primary_next_step")
                or retest_summary.get("recommended_retest_next_action"),
                "source_artifacts": retest_summary.get("source_of_truth_artifacts"),
            },
        }
    )
    return payload


def build_updated_roadmap_text(payload: Dict[str, object]) -> str:
    latest = safe_dict(payload.get("latest_execution_status"))
    retest = safe_dict(payload.get("retest_execution"))
    phase_summary = safe_dict(payload.get("phase_summary"))

    def _fmt_phase(name: str) -> str:
        section = safe_dict(phase_summary.get(name))
        if not section:
            return f"- {name}: -"
        return (
            f"- {name}: done={section.get('done')}, partial={section.get('partial')}, "
            f"not_started={section.get('not_started')}, total={section.get('total')}"
        )

    lines = [
        "Project Roadmap Status",
        "======================",
        "",
        f"- generated_at={payload.get('generated_at')}",
        f"- current_focus={payload.get('current_focus')}",
        "",
        "Phase summary:",
        _fmt_phase("phase_a"),
        _fmt_phase("phase_b"),
        _fmt_phase("phase_c"),
        "",
        "Latest execution status:",
        f"- phase_b_status={latest.get('phase_b_status')}",
        f"- phase_c_decision={latest.get('phase_c_decision')}",
        f"- current_track={latest.get('current_track')}",
        f"- recommended_next_action={latest.get('recommended_next_action')}",
        f"- retest_readiness_status={latest.get('retest_readiness_status')}",
        f"- retest_readiness_snapshot_published={latest.get('retest_readiness_snapshot_published')}",
        f"- strategy_retest_status={latest.get('strategy_retest_status')}",
        f"- strategy_retest_result={latest.get('strategy_retest_result')}",
        f"- strategy_retest_candidate={latest.get('strategy_retest_candidate')}",
        f"- strategy_retest_primary_segment={latest.get('strategy_retest_primary_segment')}",
        f"- official_primary_segment_tickers={', '.join(list(latest.get('official_primary_segment_tickers') or [])) or '-'}",
        f"- can_continue_strategy_experiments_now={latest.get('can_continue_strategy_experiments_now')}",
        "",
        "Retest execution summary:",
        f"- status={retest.get('status')}",
        f"- readiness_gate_decision={retest.get('readiness_gate_decision')}",
        f"- official_result={retest.get('official_result')}",
        f"- phase_b_final_status={retest.get('phase_b_final_status')}",
        f"- phase_c_decision={retest.get('phase_c_decision')}",
        f"- recommended_next_action={retest.get('recommended_next_action')}",
    ]
    return "\n".join(lines) + "\n"


def publish_phase_b_retest_execution(output_dir: Path) -> Dict[str, object]:
    output_dir = Path(output_dir)
    retest_summary = build_retest_execution_summary(output_dir)
    roadmap_payload = build_updated_roadmap(output_dir, retest_summary)

    retest_json = output_dir / "phase_b_retest_execution_summary.json"
    retest_txt = output_dir / "phase_b_retest_execution_summary.txt"
    roadmap_json = output_dir / "project_roadmap_status.json"
    roadmap_txt = output_dir / "project_roadmap_status.txt"

    _write_json(retest_json, retest_summary)
    _write_text(retest_txt, build_retest_execution_text(retest_summary))
    _write_json(roadmap_json, roadmap_payload)
    _write_text(roadmap_txt, build_updated_roadmap_text(roadmap_payload))

    return {
        "phase_b_retest_execution_summary": retest_summary,
        "project_roadmap_status": roadmap_payload,
        "artifacts": {
            "phase_b_retest_execution_summary_json": str(retest_json),
            "phase_b_retest_execution_summary_txt": str(retest_txt),
            "project_roadmap_status_json": str(roadmap_json),
            "project_roadmap_status_txt": str(roadmap_txt),
        },
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish roadmap and retest summary after formal retest execution.")
    parser.add_argument("--output-dir", default="output", help="Artifact directory. Default: output")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = publish_phase_b_retest_execution(output_dir=Path(args.output_dir))
    except PublishPhaseBRetestExecutionCliError as exc:
        print(f"Phase B retest publish failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during Phase B retest publish: {exc}", file=sys.stderr)
        return 1

    payload = result["phase_b_retest_execution_summary"]
    print("Phase B retest publish complete.")
    print(f"retest_readiness_status={payload['retest_readiness_status']}")
    print(f"retest_result={payload['retest_result']}")
    print(f"phase_b_final_status={payload['phase_b_final_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
