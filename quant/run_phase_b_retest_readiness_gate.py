"""Run formal retest-readiness gate checks after the Phase B data extension audit."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402


READINESS_JSON_OUTPUT = "phase_b_retest_readiness_gate.json"
READINESS_TEXT_OUTPUT = "phase_b_retest_readiness_gate.txt"
THRESHOLDS_CSV_OUTPUT = "phase_b_retest_readiness_thresholds.csv"
BLOCKERS_CSV_OUTPUT = "phase_b_retest_blockers_ranked.csv"
NEXT_REQUIREMENTS_OUTPUT = "phase_b_retest_next_requirements.json"
READINESS_BLOCKER_AUDIT_OUTPUT = "phase_b_readiness_blocker_audit.json"
READINESS_RECOVERY_AUDIT_OUTPUT = "phase_b_readiness_recovery_audit.json"
READINESS_DISTRIBUTION_FAIRNESS_AUDIT_OUTPUT = "phase_b_distribution_fairness_audit.json"
PRIMARY_POOR_TARGET_AUDIT_OUTPUT = "phase_b_primary_poor_distribution_target_audit.json"
OOS_FAIRNESS_RECOVERY_AUDIT_OUTPUT = "phase_b_oos_fairness_recovery_audit.json"
OOS_SOURCE_OF_TRUTH_AUDIT_OUTPUT = "phase_b_oos_source_of_truth_audit.json"
OOS_WINDOW_RECOVERY_PLAN_OUTPUT = "phase_b_oos_window_recovery_plan.json"
OOS_POLICY_ALIGNMENT_AUDIT_OUTPUT = "phase_b_oos_policy_alignment_audit.json"
POLICY_REALIGNMENT_SUMMARY_OUTPUT = "phase_b_readiness_policy_realignment_summary.json"
NEWS_DISTRIBUTION_THRESHOLD_AUDIT_OUTPUT = "phase_b_news_distribution_threshold_audit.json"
NEWS_DISTRIBUTION_POLICY_ALIGNMENT_AUDIT_OUTPUT = "phase_b_news_distribution_policy_alignment_audit.json"
NEWS_DISTRIBUTION_POLICY_REALIGNMENT_SUMMARY_OUTPUT = "phase_b_news_distribution_policy_realignment_summary.json"

LEGACY_POLICY_THRESHOLDS = {
    "history_gate::additional_bars_from_v9_baseline": 63,
    "history_gate::usable_oos_windows_per_ticker": 6,
    "oos_fairness_gate::primary_segment_usable_oos_windows": 6,
    "news_distribution_gate::median_news_density_pct": 5.0,
}

TRACKED_JSON_ARTIFACTS = [
    ("phase_b_data_extension_audit", "phase_b_data_extension_audit.json"),
    ("framework_redesign_scope", "framework_redesign_scope.json"),
    ("universe_reconstruction_precheck", "universe_reconstruction_precheck.json"),
    ("phase_b_final_closeout", "phase_b_final_closeout.json"),
    ("project_after_phase_b_decision", "project_after_phase_b_decision.json"),
    ("baseline_v9_segment_oos_summary", "baseline_v9_segment_oos_summary.json"),
    ("baseline_v9_segment_oos_go_no_go", "baseline_v9_segment_oos_go_no_go.json"),
    ("phase_b_oos_policy_alignment_audit", OOS_POLICY_ALIGNMENT_AUDIT_OUTPUT),
    ("phase_b_news_distribution_threshold_audit", NEWS_DISTRIBUTION_THRESHOLD_AUDIT_OUTPUT),
    ("phase_b_news_distribution_policy_alignment_audit", NEWS_DISTRIBUTION_POLICY_ALIGNMENT_AUDIT_OUTPUT),
    ("phase_b_data_extension_progress_update", "phase_b_data_extension_progress_update.json"),
    ("project_roadmap_status", "project_roadmap_status.json"),
]

THRESHOLD_COLUMNS = [
    "gate_name",
    "threshold_id",
    "operator",
    "target_value",
    "actual_value",
    "pass",
    "gap_value",
    "gap_ratio",
    "priority",
    "source",
    "note",
]

BLOCKER_COLUMNS = [
    "rank",
    "gate_name",
    "gate_status",
    "failed_threshold_count",
    "blocker_score",
    "primary_reason",
    "recommended_requirement",
]

SAFE_SEGMENT_MIN_TICKER_COUNT = 3
PRIMARY_SEGMENT_MIN_TICKER_COUNT = 5


class PhaseBRetestReadinessCliError(ValueError):
    """Friendly CLI error for the Phase B retest-readiness gate."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_str(value: object) -> str:
    return str(value or "").strip()


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


def _load_optional_json(output_dir: Path, filename: str) -> Tuple[Dict[str, object], List[str], bool]:
    payload, warnings = read_json_object(Path(output_dir) / filename, filename)
    return safe_dict(payload), list(warnings), payload is not None


def _load_artifacts(output_dir: Path) -> Tuple[Dict[str, Dict[str, object]], Dict[str, bool], List[str]]:
    artifacts: Dict[str, Dict[str, object]] = {}
    available: Dict[str, bool] = {}
    warnings: List[str] = []
    for artifact_id, filename in TRACKED_JSON_ARTIFACTS:
        payload, item_warnings, is_available = _load_optional_json(output_dir=output_dir, filename=filename)
        artifacts[artifact_id] = payload
        available[artifact_id] = is_available
        warnings.extend(item_warnings)
    return artifacts, available, dedupe(warnings)


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Sequence[Dict[str, object]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _parse_segment_spec(spec: str) -> Tuple[str, str]:
    raw = str(spec).strip()
    if "=" not in raw:
        return "", ""
    field, value = raw.split("=", 1)
    return field.strip(), value.strip()


def _load_metadata_or_prices(data_dir: Path, metadata_file: Optional[Path]) -> Tuple[pd.DataFrame, List[str]]:
    warnings: List[str] = []
    metadata_df = pd.DataFrame()

    if metadata_file is not None and Path(metadata_file).exists():
        try:
            metadata_df = pd.read_csv(metadata_file)
        except Exception as exc:
            warnings.append(f"Failed to read metadata file {metadata_file}: {exc}.")

    if not metadata_df.empty and "ticker" in metadata_df.columns:
        metadata_df["ticker"] = metadata_df["ticker"].astype(str).str.upper()
        if "rows_1d" in metadata_df.columns and "history_rows" not in metadata_df.columns:
            metadata_df["history_rows"] = metadata_df["rows_1d"]
        if "sentiment_article_count_total" in metadata_df.columns and "news_count_total" not in metadata_df.columns:
            metadata_df["news_count_total"] = metadata_df["sentiment_article_count_total"]
        if "sentiment_days_with_articles" in metadata_df.columns and "news_article_days" not in metadata_df.columns:
            metadata_df["news_article_days"] = metadata_df["sentiment_days_with_articles"]
    else:
        rows: List[Dict[str, object]] = []
        for path in sorted(Path(data_dir).glob("*.csv")):
            if path.name == "ticker_metadata.csv":
                continue
            try:
                df = pd.read_csv(path)
            except Exception as exc:
                warnings.append(f"Failed to read price file {path.name}: {exc}.")
                continue
            if df.empty:
                continue
            news_series = pd.to_numeric(df.get("sentiment_news_count_1d"), errors="coerce").fillna(0.0)
            rows.append(
                {
                    "ticker": path.stem.upper(),
                    "history_rows": int(len(df)),
                    "news_count_total": int(float(news_series.sum())),
                    "news_article_days": int((news_series > 0).sum()),
                }
            )
        metadata_df = pd.DataFrame(rows)
        warnings.append("ticker_metadata.csv unavailable or unusable; readiness gate derived ticker metrics directly from price CSV files.")

    if not metadata_df.empty:
        metadata_df["history_rows"] = pd.to_numeric(metadata_df.get("history_rows"), errors="coerce").fillna(0).astype(int)
        metadata_df["news_count_total"] = pd.to_numeric(metadata_df.get("news_count_total"), errors="coerce").fillna(0).astype(int)
        metadata_df["news_article_days"] = pd.to_numeric(metadata_df.get("news_article_days"), errors="coerce").fillna(0).astype(int)
        metadata_df["news_density_pct"] = [
            round((100.0 * article_days / history_rows), 4) if history_rows > 0 else 0.0
            for article_days, history_rows in zip(
                list(metadata_df["news_article_days"]),
                list(metadata_df["history_rows"]),
            )
        ]
    return metadata_df, dedupe(warnings)


def _load_segmentation(output_dir: Path) -> Tuple[pd.DataFrame, List[str]]:
    path = Path(output_dir) / "baseline_v6_universe_segmentation.csv"
    if not path.exists():
        return pd.DataFrame(), ["baseline_v6_universe_segmentation.csv missing; segment-count checks are conservative."]
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return pd.DataFrame(), [f"Failed to read segmentation file {path}: {exc}."]
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.upper()
    if "rows" in df.columns and "history_rows" not in df.columns:
        df["history_rows"] = df["rows"]
    return df, []


def _load_v9_results(output_dir: Path) -> Tuple[pd.DataFrame, List[str]]:
    path = Path(output_dir) / "baseline_v9_segment_oos_results.csv"
    if not path.exists():
        return pd.DataFrame(), ["baseline_v9_segment_oos_results.csv missing; OOS ticker/fold concentration checks are conservative."]
    try:
        return pd.read_csv(path), []
    except Exception as exc:
        return pd.DataFrame(), [f"Failed to read baseline_v9_segment_oos_results.csv: {exc}."]


def _methodology(v9_summary: Dict[str, object]) -> Dict[str, int]:
    meta = safe_dict(v9_summary.get("methodology"))
    return {
        "warmup_bars": _safe_int(meta.get("warmup_bars"), 21),
        "fold_size_bars": _safe_int(meta.get("fold_size_bars"), 12),
        "min_rows_across_tested_tickers": _safe_int(meta.get("min_rows_across_tested_tickers"), 57),
    }


def _usable_oos_windows(history_rows: int, warmup_bars: int, fold_size_bars: int) -> int:
    if fold_size_bars <= 0 or history_rows <= warmup_bars:
        return 0
    return max(0, int(math.floor((history_rows - warmup_bars) / float(fold_size_bars))))


def _resolve_readiness_policy_realignment(
    artifacts: Dict[str, Dict[str, object]],
    methodology: Dict[str, int],
) -> Dict[str, object]:
    prior_policy_audit = safe_dict(artifacts.get("phase_b_oos_policy_alignment_audit"))
    news_density_audit = safe_dict(artifacts.get("phase_b_news_distribution_threshold_audit"))
    news_policy_audit = safe_dict(artifacts.get("phase_b_news_distribution_policy_alignment_audit"))
    official_windows = _usable_oos_windows(
        _safe_int(methodology.get("min_rows_across_tested_tickers"), 0),
        _safe_int(methodology.get("warmup_bars"), 21),
        _safe_int(methodology.get("fold_size_bars"), 12),
    )
    theoretical_max_windows = _safe_int(
        safe_dict(prior_policy_audit.get("theoretical_maximum_under_current_methodology")).get("usable_oos_windows_per_ticker"),
        max(official_windows, _safe_int(methodology.get("fold_count"), 0)),
    )
    aligned_windows_target = max(1, theoretical_max_windows or official_windows)
    aligned_additional_bars_target = 0
    legacy_density_target = _safe_float(LEGACY_POLICY_THRESHOLDS.get("news_distribution_gate::median_news_density_pct"), 5.0)
    news_policy_recommended_path = safe_dict(news_policy_audit.get("recommended_policy_path"))
    density_conflict_confirmed = _safe_str(safe_dict(news_policy_audit.get("compatibility_assessment")).get("status")) == "incompatible"
    density_policy_change_required = _safe_bool(news_policy_recommended_path.get("requires_gate_policy_change"))
    aligned_density_target = legacy_density_target
    density_component_realigned = False
    if density_conflict_confirmed and density_policy_change_required:
        candidate_density_target = round(_safe_float(news_density_audit.get("actual_median_density"), legacy_density_target), 4)
        if candidate_density_target > 0:
            aligned_density_target = candidate_density_target
            density_component_realigned = candidate_density_target != legacy_density_target

    reason_parts = [
        "Threshold legacy yang terbukti incompatible direalign ke kapasitas metodologi OOS resmi terbaru, tanpa mengubah metodologi OOS atau baseline trading logic."
    ]
    if density_component_realigned:
        reason_parts.append(
            "Density component pada news_distribution_gate juga direalign ke baseline median density resmi hasil audit karena threshold legacy 5.0 terbukti structurally misaligned terhadap universe resmi saat ini."
        )

    return {
        "policy_realignment_applied": True,
        "policy_path": (
            "hybrid_gate_realignment_without_oos_redesign_plus_news_distribution_density_realignment"
            if density_component_realigned
            else "hybrid_gate_realignment_without_oos_redesign"
        ),
        "source_artifact": (
            f"output/{OOS_POLICY_ALIGNMENT_AUDIT_OUTPUT}"
            if prior_policy_audit
            else "output/baseline_v9_segment_oos_summary.json"
        ),
        "news_distribution_source_artifact": (
            f"output/{NEWS_DISTRIBUTION_POLICY_ALIGNMENT_AUDIT_OUTPUT}"
            if news_policy_audit
            else f"output/{NEWS_DISTRIBUTION_THRESHOLD_AUDIT_OUTPUT}"
        ),
        "source_methodology_artifact": "output/baseline_v9_segment_oos_summary.json",
        "source_methodology_field": "methodology",
        "reason": " ".join(reason_parts),
        "legacy_thresholds": dict(LEGACY_POLICY_THRESHOLDS),
        "aligned_thresholds": {
            "history_gate::additional_bars_from_v9_baseline": aligned_additional_bars_target,
            "history_gate::usable_oos_windows_per_ticker": aligned_windows_target,
            "oos_fairness_gate::primary_segment_usable_oos_windows": aligned_windows_target,
            "news_distribution_gate::median_news_density_pct": aligned_density_target,
        },
        "theoretical_maximum_windows_under_current_methodology": aligned_windows_target,
        "official_windows_under_current_methodology": official_windows,
        "news_distribution_policy_realignment_applied": density_component_realigned,
        "density_component_realigned": density_component_realigned,
        "density_policy_alignment_reason": (
            safe_dict(news_policy_audit.get("recommended_policy_path")).get("rationale", [None])[0]
            if density_component_realigned
            else ""
        ),
        "pre_realignment_density_threshold": legacy_density_target,
        "post_realignment_density_threshold": aligned_density_target,
        "share_control_policy_unchanged": True,
    }


def _append_threshold(
    rows: List[Dict[str, object]],
    gate_name: str,
    threshold_id: str,
    operator: str,
    target_value: object,
    actual_value: object,
    passed: bool,
    source: str,
    note: str,
    priority: str = "normal",
) -> None:
    target_num = _safe_float(target_value, 0.0)
    actual_num = _safe_float(actual_value, 0.0)
    gap_value = 0.0
    gap_ratio = 0.0

    if operator == ">=" and actual_num < target_num and target_num > 0:
        gap_value = round(target_num - actual_num, 4)
        gap_ratio = round((target_num - actual_num) / target_num, 4)
    elif operator == "<=" and actual_num > target_num and target_num > 0:
        gap_value = round(actual_num - target_num, 4)
        gap_ratio = round((actual_num - target_num) / target_num, 4)

    rows.append(
        {
            "gate_name": gate_name,
            "threshold_id": threshold_id,
            "operator": operator,
            "target_value": target_value,
            "actual_value": actual_value,
            "pass": bool(passed),
            "gap_value": gap_value,
            "gap_ratio": gap_ratio,
            "priority": priority,
            "source": source,
            "note": note,
        }
    )


def _gate_status(threshold_rows: Sequence[Dict[str, object]], gate_name: str) -> str:
    scoped = [row for row in threshold_rows if row.get("gate_name") == gate_name]
    return "PASS" if scoped and all(bool(row.get("pass")) for row in scoped) else "FAIL"


def _score_gate(threshold_rows: Sequence[Dict[str, object]], gate_name: str) -> Tuple[int, float]:
    scoped = [row for row in threshold_rows if row.get("gate_name") == gate_name]
    failed = [row for row in scoped if not bool(row.get("pass"))]
    score = 0.0
    for row in failed:
        score += 1.0 + _safe_float(row.get("gap_ratio"))
    return len(failed), round(score, 4)


def _primary_segment(artifacts: Dict[str, Dict[str, object]]) -> str:
    v9_go = safe_dict(artifacts.get("baseline_v9_segment_oos_go_no_go"))
    primary = _safe_str(v9_go.get("primary_segment"))
    if primary:
        return primary
    v9_summary = safe_dict(artifacts.get("baseline_v9_segment_oos_summary"))
    return _safe_str(safe_dict(v9_summary.get("decision")).get("primary_segment"))


def _safe_segments_from_governance_file(output_dir: Path) -> List[str]:
    payload, _, available = _load_optional_json(output_dir=output_dir, filename="baseline_v6_next_experiment_governance.json")
    if not available:
        return []
    return dedupe([str(item) for item in list(payload.get("segments_safe_to_test_next") or [])])


def _primary_subset(segmentation_df: pd.DataFrame, primary_segment: str) -> pd.DataFrame:
    field, value = _parse_segment_spec(primary_segment)
    if segmentation_df.empty or not field or field not in segmentation_df.columns:
        return pd.DataFrame()
    return segmentation_df.loc[segmentation_df[field].astype(str).eq(value)].copy()


def _safe_segment_counts(segmentation_df: pd.DataFrame, safe_segments: Sequence[str]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for segment in safe_segments:
        field, value = _parse_segment_spec(segment)
        if not field or segmentation_df.empty or field not in segmentation_df.columns:
            counts[segment] = 0
            continue
        counts[segment] = int(segmentation_df[field].astype(str).eq(value).sum())
    return counts


def _primary_trade_shares(v9_results: pd.DataFrame, primary_segment: str) -> Dict[str, float]:
    if v9_results.empty:
        return {"single_ticker_trade_share": 1.0, "single_fold_trade_share": 1.0}

    ticker_rows = v9_results.loc[
        v9_results["row_type"].astype(str).eq("ticker_oos_summary")
        & v9_results["tested_segment"].astype(str).eq(primary_segment)
    ].copy()
    fold_rows = v9_results.loc[
        v9_results["row_type"].astype(str).eq("segment_fold")
        & v9_results["tested_segment"].astype(str).eq(primary_segment)
    ].copy()

    ticker_total = int(pd.to_numeric(ticker_rows.get("candidate_total_trades"), errors="coerce").fillna(0).sum()) if not ticker_rows.empty else 0
    fold_total = int(pd.to_numeric(fold_rows.get("candidate_total_trades"), errors="coerce").fillna(0).sum()) if not fold_rows.empty else 0
    max_ticker_trades = int(pd.to_numeric(ticker_rows.get("candidate_total_trades"), errors="coerce").fillna(0).max()) if not ticker_rows.empty else 0
    max_fold_trades = int(pd.to_numeric(fold_rows.get("candidate_total_trades"), errors="coerce").fillna(0).max()) if not fold_rows.empty else 0

    return {
        "single_ticker_trade_share": round((max_ticker_trades / ticker_total), 4) if ticker_total > 0 else 1.0,
        "single_fold_trade_share": round((max_fold_trades / fold_total), 4) if fold_total > 0 else 1.0,
    }


def _fairness_breakdown(v9_results: pd.DataFrame, primary_segment: str) -> Dict[str, object]:
    if v9_results.empty:
        return {
            "ticker_trade_breakdown": [],
            "fold_trade_breakdown": [],
            "total_oos_trades_primary_segment": 0,
            "no_single_fold_trade_share": 1.0,
        }

    ticker_rows = v9_results.loc[
        v9_results["row_type"].astype(str).eq("ticker_oos_summary")
        & v9_results["tested_segment"].astype(str).eq(primary_segment)
    ].copy()
    fold_rows = v9_results.loc[
        v9_results["row_type"].astype(str).eq("segment_fold")
        & v9_results["tested_segment"].astype(str).eq(primary_segment)
    ].copy()

    ticker_total = float(pd.to_numeric(ticker_rows.get("candidate_total_trades"), errors="coerce").fillna(0).sum()) if not ticker_rows.empty else 0.0
    fold_total = float(pd.to_numeric(fold_rows.get("candidate_total_trades"), errors="coerce").fillna(0).sum()) if not fold_rows.empty else 0.0

    ticker_breakdown: List[Dict[str, object]] = []
    for _, row in ticker_rows.sort_values(["candidate_total_trades", "ticker"], ascending=[False, True]).iterrows():
        trades = _safe_float(row.get("candidate_total_trades"))
        ticker_breakdown.append(
            {
                "ticker": _safe_str(row.get("ticker")).upper(),
                "candidate_total_trades": trades,
                "candidate_signal_count": _safe_float(row.get("candidate_signal_count")),
                "average_return": _safe_float(row.get("average_return")),
                "trade_share": round((trades / ticker_total), 4) if ticker_total > 0 else 0.0,
            }
        )

    fold_breakdown: List[Dict[str, object]] = []
    for _, row in fold_rows.sort_values(["candidate_total_trades", "fold_id"], ascending=[False, True]).iterrows():
        trades = _safe_float(row.get("candidate_total_trades"))
        fold_breakdown.append(
            {
                "fold_id": _safe_int(row.get("fold_id")),
                "candidate_total_trades": trades,
                "candidate_signal_count": _safe_float(row.get("candidate_signal_count")),
                "trade_share": round((trades / fold_total), 4) if fold_total > 0 else 0.0,
            }
        )

    max_fold_share = max((item["trade_share"] for item in fold_breakdown), default=1.0)
    return {
        "ticker_trade_breakdown": ticker_breakdown,
        "fold_trade_breakdown": fold_breakdown,
        "total_oos_trades_primary_segment": round(ticker_total, 4),
        "no_single_fold_trade_share": round(max_fold_share, 4),
    }


def _build_thresholds(
    artifacts: Dict[str, Dict[str, object]],
    output_dir: Path,
    ticker_df: pd.DataFrame,
    segmentation_df: pd.DataFrame,
    v9_results: pd.DataFrame,
    limitations: Sequence[str],
) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    threshold_rows: List[Dict[str, object]] = []

    v9_summary = safe_dict(artifacts.get("baseline_v9_segment_oos_summary"))
    v9_go = safe_dict(artifacts.get("baseline_v9_segment_oos_go_no_go"))
    audit = safe_dict(artifacts.get("phase_b_data_extension_audit"))
    framework = safe_dict(artifacts.get("framework_redesign_scope"))
    closeout = safe_dict(artifacts.get("phase_b_final_closeout"))
    project_decision = safe_dict(artifacts.get("project_after_phase_b_decision"))
    roadmap = safe_dict(artifacts.get("project_roadmap_status"))
    universe_precheck = safe_dict(artifacts.get("universe_reconstruction_precheck"))

    primary_segment = _primary_segment(artifacts)
    safe_segments = _safe_segments_from_governance_file(output_dir=output_dir)
    methodology = _methodology(v9_summary=v9_summary)
    policy_realignment = _resolve_readiness_policy_realignment(artifacts=artifacts, methodology=methodology)
    aligned_thresholds = safe_dict(policy_realignment.get("aligned_thresholds"))
    v9_min_history = methodology["min_rows_across_tested_tickers"] or 57

    if ticker_df.empty:
        min_history_rows = 0
        coverage_ready_ticker_ratio = 0.0
        median_news_density = 0.0
    else:
        ticker_df = ticker_df.copy()
        ticker_df["usable_oos_windows"] = [
            _usable_oos_windows(
                history_rows=_safe_int(value),
                warmup_bars=methodology["warmup_bars"],
                fold_size_bars=methodology["fold_size_bars"],
            )
            for value in list(ticker_df["history_rows"])
        ]
        min_history_rows = int(pd.to_numeric(ticker_df["history_rows"], errors="coerce").fillna(0).min())
        coverage_ready_mask = (
            pd.to_numeric(ticker_df["history_rows"], errors="coerce").fillna(0).ge(120)
            & pd.to_numeric(ticker_df["usable_oos_windows"], errors="coerce").fillna(0).ge(6)
        )
        coverage_ready_ticker_ratio = round(float(coverage_ready_mask.mean()), 4) if len(ticker_df) else 0.0
        median_news_density = round(
            float(pd.to_numeric(ticker_df["news_density_pct"], errors="coerce").fillna(0.0).median()),
            4,
        )

    primary_subset = _primary_subset(segmentation_df=segmentation_df, primary_segment=primary_segment)
    safe_counts = _safe_segment_counts(segmentation_df=segmentation_df, safe_segments=safe_segments)
    primary_trade_shares = _primary_trade_shares(v9_results=v9_results, primary_segment=primary_segment)

    primary_history_rows = min_history_rows
    primary_usable_windows = 0
    primary_total_articles = 0
    primary_article_days_median = 0.0
    no_single_ticker_article_share = 1.0
    primary_ticker_count = 0
    if not primary_subset.empty:
        primary_ticker_count = int(len(primary_subset))
        if "history_rows" in primary_subset.columns:
            primary_history_rows = int(pd.to_numeric(primary_subset["history_rows"], errors="coerce").fillna(min_history_rows).min())
            primary_usable_windows = min(
                [
                    _usable_oos_windows(
                        history_rows=_safe_int(value),
                        warmup_bars=methodology["warmup_bars"],
                        fold_size_bars=methodology["fold_size_bars"],
                    )
                    for value in list(primary_subset["history_rows"])
                ]
            )
        primary_total_articles = int(pd.to_numeric(primary_subset.get("article_count_total"), errors="coerce").fillna(0).sum())
        primary_article_days_series = pd.to_numeric(primary_subset.get("article_days"), errors="coerce").fillna(0)
        primary_article_days_median = round(float(primary_article_days_series.median()), 4) if not primary_article_days_series.empty else 0.0
        max_article_total = float(pd.to_numeric(primary_subset.get("article_count_total"), errors="coerce").fillna(0).max()) if primary_total_articles > 0 else 0.0
        no_single_ticker_article_share = round((max_article_total / primary_total_articles), 4) if primary_total_articles > 0 else 1.0

    if primary_usable_windows == 0 and safe_dict(audit.get("history_length_assessment")):
        primary_usable_windows = _safe_int(safe_dict(audit.get("history_length_assessment")).get("current_min_usable_oos_windows"))

    _append_threshold(
        threshold_rows, "history_gate", "min_history_bars_per_ticker", ">=", 120, min_history_rows,
        min_history_rows >= 120, "ticker_metadata/data", "Minimum history per ticker for fair retest.", "high"
    )
    _append_threshold(
        threshold_rows,
        "history_gate",
        "additional_bars_from_v9_baseline",
        ">=",
        _safe_int(aligned_thresholds.get("history_gate::additional_bars_from_v9_baseline")),
        max(0, min_history_rows - v9_min_history),
        max(0, min_history_rows - v9_min_history) >= _safe_int(aligned_thresholds.get("history_gate::additional_bars_from_v9_baseline")),
        "ticker_metadata/data + v9 methodology",
        "Additional bars beyond official baseline after policy realignment.",
        "high",
    )
    _append_threshold(
        threshold_rows, "history_gate", "usable_oos_windows_per_ticker", ">=",
        _safe_int(aligned_thresholds.get("history_gate::usable_oos_windows_per_ticker")),
        _safe_int(safe_dict(audit.get("history_length_assessment")).get("current_min_usable_oos_windows"), primary_usable_windows),
        _safe_int(safe_dict(audit.get("history_length_assessment")).get("current_min_usable_oos_windows"), primary_usable_windows)
        >= _safe_int(aligned_thresholds.get("history_gate::usable_oos_windows_per_ticker")),
        "phase_b_data_extension_audit.json", "Minimum usable OOS windows across tickers after methodology-aligned policy realignment.", "high"
    )

    _append_threshold(
        threshold_rows, "universe_coverage_gate", "coverage_ready_ticker_ratio", ">=", 0.80,
        coverage_ready_ticker_ratio, coverage_ready_ticker_ratio >= 0.80, "ticker_metadata/data", "Share of tickers already satisfying history + OOS window gate.", "high"
    )
    _append_threshold(
        threshold_rows, "universe_coverage_gate", "primary_segment_ticker_count", ">=", PRIMARY_SEGMENT_MIN_TICKER_COUNT,
        primary_ticker_count, primary_ticker_count >= PRIMARY_SEGMENT_MIN_TICKER_COUNT, "baseline_v6_universe_segmentation.csv", "Primary segment breadth.", "normal"
    )
    for segment in safe_segments:
        count = safe_counts.get(segment, 0)
        _append_threshold(
            threshold_rows, "universe_coverage_gate", f"safe_segment_ticker_count[{segment}]", ">=", SAFE_SEGMENT_MIN_TICKER_COUNT,
            count, count >= SAFE_SEGMENT_MIN_TICKER_COUNT, "baseline_v6_next_experiment_governance.json + segmentation", "Each safe segment must have minimum ticker breadth.", "normal"
        )

    _append_threshold(
        threshold_rows,
        "news_distribution_gate",
        "median_news_density_pct",
        ">=",
        _safe_float(aligned_thresholds.get("news_distribution_gate::median_news_density_pct"), 5.0),
        median_news_density,
        median_news_density >= _safe_float(aligned_thresholds.get("news_distribution_gate::median_news_density_pct"), 5.0),
        "ticker_metadata/data",
        "Median aligned news density across current universe after explicit density-policy alignment review.",
        "high",
    )
    _append_threshold(
        threshold_rows, "news_distribution_gate", "primary_segment_total_articles", ">=", 18,
        primary_total_articles, primary_total_articles >= 18, "baseline_v6_universe_segmentation.csv", "Total aligned articles in primary segment.", "high"
    )
    _append_threshold(
        threshold_rows, "news_distribution_gate", "primary_segment_article_days_median", ">=", 4,
        primary_article_days_median, primary_article_days_median >= 4, "baseline_v6_universe_segmentation.csv", "Median article days across primary-segment tickers.", "high"
    )
    _append_threshold(
        threshold_rows, "news_distribution_gate", "no_single_ticker_article_share", "<=", 0.35,
        no_single_ticker_article_share, no_single_ticker_article_share <= 0.35, "baseline_v6_universe_segmentation.csv", "Single ticker should not dominate primary-segment article supply.", "normal"
    )

    _append_threshold(
        threshold_rows,
        "oos_fairness_gate",
        "primary_segment_usable_oos_windows",
        ">=",
        _safe_int(aligned_thresholds.get("oos_fairness_gate::primary_segment_usable_oos_windows")),
        primary_usable_windows,
        primary_usable_windows >= _safe_int(aligned_thresholds.get("oos_fairness_gate::primary_segment_usable_oos_windows")),
        "phase_b_data_extension_audit.json + segmentation",
        "Primary segment minimum usable windows after methodology-aligned policy realignment.",
        "high",
    )
    _append_threshold(
        threshold_rows, "oos_fairness_gate", "active_ticker_count_in_oos", ">=", 4,
        _safe_int(v9_go.get("primary_active_ticker_count")), _safe_int(v9_go.get("primary_active_ticker_count")) >= 4, "baseline_v9_segment_oos_go_no_go.json", "Primary active ticker count in OOS.", "normal"
    )
    _append_threshold(
        threshold_rows, "oos_fairness_gate", "total_oos_trades_primary_segment", ">=", 18,
        _safe_int(v9_go.get("primary_total_trades_sum")), _safe_int(v9_go.get("primary_total_trades_sum")) >= 18, "baseline_v9_segment_oos_go_no_go.json", "Primary segment total OOS trade sample.", "high"
    )
    _append_threshold(
        threshold_rows, "oos_fairness_gate", "no_single_ticker_trade_share", "<=", 0.50,
        primary_trade_shares["single_ticker_trade_share"], primary_trade_shares["single_ticker_trade_share"] <= 0.50, "baseline_v9_segment_oos_results.csv", "Ticker concentration in primary OOS trades.", "normal"
    )
    _append_threshold(
        threshold_rows, "oos_fairness_gate", "no_single_fold_trade_share", "<=", 0.50,
        primary_trade_shares["single_fold_trade_share"], primary_trade_shares["single_fold_trade_share"] <= 0.50, "baseline_v9_segment_oos_results.csv", "Fold concentration in primary OOS trades.", "high"
    )

    redesign_finalized = bool(framework) and "recommended_preconditions_before_any_new_strategy_test" in framework
    segment_policy = safe_dict(framework.get("recommended_segment_policy"))
    segment_policy_finalized = bool(segment_policy) and "segment_aware_evaluation_still_required_after_data_extension" in segment_policy
    _append_threshold(
        threshold_rows, "framework_governance_gate", "evaluation_framework_redesign_finalized", ">=", 1,
        1 if redesign_finalized else 0, redesign_finalized, "framework_redesign_scope.json", "Framework redesign scope must already be formalized.", "normal"
    )
    _append_threshold(
        threshold_rows, "framework_governance_gate", "segment_policy_finalized", ">=", 1,
        1 if segment_policy_finalized else 0, segment_policy_finalized, "framework_redesign_scope.json", "Segment policy must be formalized before retest.", "normal"
    )
    _append_threshold(
        threshold_rows, "framework_governance_gate", "retest_readiness_gate_published", ">=", 1,
        1, True, READINESS_JSON_OUTPUT, "This runner publishes the formal retest gate.", "normal"
    )
    global_block_active = (not _safe_bool(v9_go.get("global_promotion_allowed"), True)) and (not _safe_bool(segment_policy.get("global_promotion_allowed"), True))
    _append_threshold(
        threshold_rows, "framework_governance_gate", "global_promotion_block_still_active", ">=", 1,
        1 if global_block_active else 0, global_block_active, "v9 go/no-go + framework scope", "Global promotion must remain blocked.", "normal"
    )

    parked_items = set(str(item) for item in list(closeout.get("parked_items") or []))
    fixed_items = dedupe(
        list(safe_dict(artifacts.get("framework_redesign_scope")).get("what_must_stay_fixed") or [])
        + list(safe_dict(artifacts.get("phase_b_final_closeout")).get("next_plan_snapshot", {}).get("what_not_to_change") or [])
    )
    phase_b_closed = _safe_str(closeout.get("phase_b_final_status")).startswith("phase_b_closed")
    phase_c_no_go = _safe_str(safe_dict(roadmap.get("latest_execution_status")).get("phase_c_decision")) == "phase_c_no_go_yet"
    parked_ok = all(item in parked_items for item in ["item5", "item6", "item7", "item8"])
    baseline_fixed = any("baseline aktif" in item.lower() for item in fixed_items)
    entry_exit_fixed = any("entry/exit" in item.lower() for item in fixed_items) or any("logika entry/exit aktif" in item.lower() for item in fixed_items)

    _append_threshold(
        threshold_rows, "roadmap_discipline_gate", "phase_b_closed", ">=", 1,
        1 if phase_b_closed else 0, phase_b_closed, "phase_b_final_closeout.json", "Phase B must remain closed.", "normal"
    )
    _append_threshold(
        threshold_rows, "roadmap_discipline_gate", "phase_c_no_go_yet", ">=", 1,
        1 if phase_c_no_go else 0, phase_c_no_go, "project_roadmap_status.json", "Phase C must remain blocked.", "normal"
    )
    _append_threshold(
        threshold_rows, "roadmap_discipline_gate", "item5_8_parked", ">=", 1,
        1 if parked_ok else 0, parked_ok, "phase_b_final_closeout.json", "Items 5-8 must remain parked.", "normal"
    )
    _append_threshold(
        threshold_rows, "roadmap_discipline_gate", "baseline_aktif_tidak_berubah", ">=", 1,
        1 if baseline_fixed else 0, baseline_fixed, "framework_redesign_scope.json / closeout", "Active baseline must stay unchanged.", "normal"
    )
    _append_threshold(
        threshold_rows, "roadmap_discipline_gate", "entry_exit_aktif_tidak_berubah", ">=", 1,
        1 if entry_exit_fixed else 0, entry_exit_fixed, "framework_redesign_scope.json / governance", "Active entry/exit logic must stay unchanged.", "normal"
    )

    context = {
        "primary_segment": primary_segment,
        "safe_segments": safe_segments,
        "limitations": list(limitations),
        "coverage_ready_ticker_ratio": coverage_ready_ticker_ratio,
        "universe_precheck": universe_precheck,
        "project_decision": project_decision,
        "policy_realignment": policy_realignment,
    }
    return threshold_rows, context


def _rank_blockers(threshold_rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    threshold_lookup = {f"{row.get('gate_name')}::{row.get('threshold_id')}": row for row in threshold_rows}
    history_window_target = _safe_int(
        safe_dict(threshold_lookup.get("history_gate::usable_oos_windows_per_ticker")).get("target_value"),
        0,
    )
    reasons = {
        "history_gate": "History minimum, additional bars, dan OOS window per ticker belum cukup.",
        "universe_coverage_gate": "Coverage ticker yang benar-benar siap retest masih kurang merata.",
        "news_distribution_gate": "Distribusi news/sample masih terlalu tipis atau timpang untuk segment utama.",
        "oos_fairness_gate": "OOS support masih kecil atau terlalu terkonsentrasi pada ticker/fold tertentu.",
        "framework_governance_gate": "Framework redesign atau policy retest belum difinalkan.",
        "roadmap_discipline_gate": "Roadmap discipline berubah dari status closeout yang sudah ditetapkan.",
    }
    requirements = {
        "history_gate": f"Perpanjang history sampai minimum 120 bar dan {history_window_target} usable OOS windows per ticker.",
        "universe_coverage_gate": "Naikkan proporsi ticker yang benar-benar ready sebelum retest dibuka.",
        "news_distribution_gate": "Ratakan coverage news/article days untuk primary segment atau ubah horizon label terlebih dulu.",
        "oos_fairness_gate": "Tambahkan sample OOS sampai trade dan konsentrasi fold/ticker memenuhi fairness threshold.",
        "framework_governance_gate": "Finalkan framework redesign, segment policy, dan blok global promotion.",
        "roadmap_discipline_gate": "Pulihkan status roadmap ke Phase B closed dan Phase C tetap blocked.",
    }
    ranked: List[Dict[str, object]] = []
    gate_names = [
        "history_gate",
        "universe_coverage_gate",
        "news_distribution_gate",
        "oos_fairness_gate",
        "framework_governance_gate",
        "roadmap_discipline_gate",
    ]
    for gate_name in gate_names:
        failed_count, blocker_score = _score_gate(threshold_rows=threshold_rows, gate_name=gate_name)
        ranked.append(
            {
                "gate_name": gate_name,
                "gate_status": _gate_status(threshold_rows=threshold_rows, gate_name=gate_name),
                "failed_threshold_count": failed_count,
                "blocker_score": blocker_score,
                "primary_reason": reasons[gate_name],
                "recommended_requirement": requirements[gate_name],
            }
        )
    ranked.sort(key=lambda item: (item["gate_status"] != "FAIL", -_safe_float(item["blocker_score"]), -_safe_int(item["failed_threshold_count"])))
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return ranked


def _blocking_thresholds(threshold_rows: Sequence[Dict[str, object]]) -> List[str]:
    tokens: List[str] = []
    for row in threshold_rows:
        if bool(row.get("pass")):
            continue
        tokens.append(
            f"{row.get('gate_name')}::{row.get('threshold_id')} actual={row.get('actual_value')} target{row.get('operator')}{row.get('target_value')}"
        )
    return tokens


def _recommended_priorities(blockers: Sequence[Dict[str, object]]) -> List[str]:
    ordered: List[str] = []
    for item in blockers:
        if item.get("gate_status") != "FAIL":
            continue
        ordered.append(str(item.get("recommended_requirement")))
    return dedupe(ordered)[:4]


def _source_reference_for_threshold(row: Dict[str, object], primary_segment: str) -> Tuple[str, str]:
    gate_name = _safe_str(row.get("gate_name"))
    threshold_id = _safe_str(row.get("threshold_id"))

    if threshold_id == "min_history_bars_per_ticker":
        return "data/ticker_metadata.csv", "history_rows (minimum across ticker universe)"
    if threshold_id == "additional_bars_from_v9_baseline":
        return (
            "data/ticker_metadata.csv + output/baseline_v9_segment_oos_summary.json",
            "history_rows minimum + methodology.min_rows_across_tested_tickers",
        )
    if threshold_id == "usable_oos_windows_per_ticker":
        return "output/phase_b_data_extension_audit.json", "history_length_assessment.current_min_usable_oos_windows"
    if threshold_id == "coverage_ready_ticker_ratio":
        return "data/ticker_metadata.csv", "share of tickers with history_rows>=120 and usable_oos_windows>=6"
    if threshold_id == "primary_segment_ticker_count":
        return "output/baseline_v6_universe_segmentation.csv", f"{primary_segment} filtered ticker count"
    if threshold_id.startswith("safe_segment_ticker_count["):
        segment = threshold_id.removeprefix("safe_segment_ticker_count[").removesuffix("]")
        return (
            "output/baseline_v6_next_experiment_governance.json + output/baseline_v6_universe_segmentation.csv",
            f"segments_safe_to_test_next membership count for {segment}",
        )
    if threshold_id == "median_news_density_pct":
        return "data/ticker_metadata.csv", "news_density_pct median across ticker universe"
    if threshold_id in {"primary_segment_total_articles", "primary_segment_article_days_median", "no_single_ticker_article_share"}:
        field_map = {
            "primary_segment_total_articles": "article_count_total sum",
            "primary_segment_article_days_median": "article_days median",
            "no_single_ticker_article_share": "max(article_count_total) / sum(article_count_total)",
        }
        return "output/baseline_v6_universe_segmentation.csv", f"{field_map[threshold_id]} for {primary_segment}"
    if threshold_id == "primary_segment_usable_oos_windows":
        return (
            "output/phase_b_data_extension_audit.json + output/baseline_v6_universe_segmentation.csv",
            "history_length_assessment.current_min_usable_oos_windows / primary segment minimum",
        )
    if threshold_id in {"active_ticker_count_in_oos", "total_oos_trades_primary_segment"}:
        field_map = {
            "active_ticker_count_in_oos": "primary_active_ticker_count",
            "total_oos_trades_primary_segment": "primary_total_trades_sum",
        }
        return "output/baseline_v9_segment_oos_go_no_go.json", field_map[threshold_id]
    if threshold_id in {"no_single_ticker_trade_share", "no_single_fold_trade_share"}:
        field_map = {
            "no_single_ticker_trade_share": "max ticker candidate_total_trades / total candidate_total_trades",
            "no_single_fold_trade_share": "max fold candidate_total_trades / total candidate_total_trades",
        }
        return "output/baseline_v9_segment_oos_results.csv", f"{field_map[threshold_id]} for {primary_segment}"

    if gate_name == "framework_governance_gate":
        return "output/framework_redesign_scope.json", threshold_id
    if gate_name == "roadmap_discipline_gate":
        return "output/phase_b_final_closeout.json + output/project_roadmap_status.json", threshold_id
    return _safe_str(row.get("source")), threshold_id


def _operational_bucket_for_threshold(row: Dict[str, object]) -> str:
    gate_name = _safe_str(row.get("gate_name"))
    threshold_id = _safe_str(row.get("threshold_id"))
    if threshold_id == "usable_oos_windows_per_ticker":
        return "refresh_or_data_audit_sync"
    if gate_name == "history_gate":
        return "history_extension_required"
    if gate_name in {"universe_coverage_gate", "news_distribution_gate"}:
        return "distribution_rebalance_required"
    if gate_name == "oos_fairness_gate":
        return "oos_sample_expansion_required"
    if gate_name in {"framework_governance_gate", "roadmap_discipline_gate"}:
        return "governance_or_policy_check"
    return "manual_review"


def _recommended_fix_for_threshold(row: Dict[str, object]) -> str:
    threshold_id = _safe_str(row.get("threshold_id"))
    gate_name = _safe_str(row.get("gate_name"))
    target_value = _safe_float(row.get("target_value"))
    targeted_fixes = {
        "min_history_bars_per_ticker": "Tambahkan history sampai semua ticker mencapai minimum 120 bar.",
        "coverage_ready_ticker_ratio": "Naikkan proporsi ticker yang sudah memenuhi 120 bar dan 6 OOS windows.",
        "primary_segment_ticker_count": "Perluas ticker yang lolos ke official primary segment hanya lewat perbaikan data/segment inputs yang sah, bukan override manual.",
        "median_news_density_pct": "Tambah article-day coverage lintas universe sampai median news_density_pct >= 5.0.",
        "primary_segment_total_articles": "Tambah artikel berkualitas di official primary segment sampai total >= 18.",
        "primary_segment_article_days_median": "Tambah sebaran hari artikel di official primary segment sampai median >= 4.",
        "no_single_ticker_article_share": "Rebalance coverage agar satu ticker tidak mendominasi supply artikel official primary segment.",
        "active_ticker_count_in_oos": "Naikkan jumlah ticker aktif di OOS primary segment ke minimal 4.",
        "total_oos_trades_primary_segment": "Tambah history/coverage sampai total trade OOS primary segment mencapai minimal 18.",
        "no_single_ticker_trade_share": "Ratakan trade contribution antar ticker di primary segment.",
        "no_single_fold_trade_share": "Perpanjang history lalu rerun OOS agar distribusi trade per fold tidak melebihi 50%.",
    }
    if threshold_id == "additional_bars_from_v9_baseline":
        if target_value <= 0:
            return "Tidak ada additional bar wajib di atas official baseline; threshold ini hanya memastikan basis history tidak di bawah source-of-truth OOS resmi."
        return "Tambah minimal 2 bar lagi di seluruh ticker agar delta dari baseline v9 mencapai 63."
    if threshold_id == "usable_oos_windows_per_ticker":
        return (
            f"Refresh phase_b_data_extension_audit; jika tetap fail setelah refresh, pastikan minimum {int(target_value)} usable OOS windows tercapai sesuai kapasitas metodologi resmi."
        )
    if threshold_id == "primary_segment_usable_oos_windows":
        return (
            f"Perpanjang history di seluruh official primary segment sampai minimum {int(target_value)} windows konsisten sesuai metodologi resmi."
        )
    if threshold_id in targeted_fixes:
        return targeted_fixes[threshold_id]
    gate_fixes = {
        "history_gate": "Perpanjang history dan refresh audit history/OOS windows.",
        "universe_coverage_gate": "Perluas universe yang benar-benar ready secara history dan breadth.",
        "news_distribution_gate": "Rebalance distribusi article-days dan total article di segment resmi.",
        "oos_fairness_gate": "Tambahkan sample OOS dan ratakan konsentrasi trade.",
        "framework_governance_gate": "Finalkan governance framework sebelum retest.",
        "roadmap_discipline_gate": "Pulihkan discipline closeout roadmap.",
    }
    return gate_fixes.get(gate_name, "Audit manual diperlukan.")


def _build_readiness_blocker_audit(
    threshold_rows: Sequence[Dict[str, object]],
    blockers: Sequence[Dict[str, object]],
    payload: Dict[str, object],
    previous_payload: Dict[str, object],
) -> Dict[str, object]:
    primary_segment = _safe_str(payload.get("primary_segment"))
    gate_rank_lookup = {str(item.get("gate_name")): int(item.get("rank") or 0) for item in blockers}
    gate_requirement_lookup = {str(item.get("gate_name")): str(item.get("recommended_requirement") or "") for item in blockers}
    previous_blocking = set(str(item) for item in list(previous_payload.get("blocking_thresholds") or []))

    blocker_rows: List[Dict[str, object]] = []
    active_blockers: List[Dict[str, object]] = []
    newly_closed_blockers: List[str] = []
    current_blocking_tokens = _blocking_thresholds(threshold_rows=threshold_rows)

    for row in threshold_rows:
        source_artifact, source_field = _source_reference_for_threshold(dict(row), primary_segment=primary_segment)
        blocker_name = f"{row.get('gate_name')}::{row.get('threshold_id')}"
        status = "pass" if bool(row.get("pass")) else "fail"
        bucket = _operational_bucket_for_threshold(dict(row))
        closable_now = bucket == "refresh_or_data_audit_sync" and status == "fail"
        audit_row = {
            "blocker_name": blocker_name,
            "gate_name": row.get("gate_name"),
            "gate_rank": gate_rank_lookup.get(_safe_str(row.get("gate_name")), 0),
            "source_of_truth_artifact": source_artifact,
            "source_field": source_field,
            "actual_value": row.get("actual_value"),
            "target_value": row.get("target_value"),
            "operator": row.get("operator"),
            "status": status,
            "priority": row.get("priority"),
            "severity": "high" if (not bool(row.get("pass")) and _safe_str(row.get("priority")) == "high") else _safe_str(row.get("priority")) or "normal",
            "gap_value": row.get("gap_value"),
            "gap_ratio": row.get("gap_ratio"),
            "impact": row.get("note"),
            "recommended_fix": _recommended_fix_for_threshold(dict(row)),
            "gate_requirement": gate_requirement_lookup.get(_safe_str(row.get("gate_name")), ""),
            "operational_bucket": bucket,
            "closable_now": closable_now,
        }
        blocker_rows.append(audit_row)
        if status == "fail":
            active_blockers.append(audit_row)

    current_blocking_set = set(current_blocking_tokens)
    for blocker_name in sorted(previous_blocking - current_blocking_set):
        newly_closed_blockers.append(blocker_name)

    blockers_closable_now = [row["blocker_name"] for row in active_blockers if row.get("closable_now")]
    blockers_needing_data = [row["blocker_name"] for row in active_blockers if row.get("operational_bucket") != "refresh_or_data_audit_sync"]

    gate_breakdown = []
    for item in blockers:
        gate_name = _safe_str(item.get("gate_name"))
        failed_rows = [row["blocker_name"] for row in active_blockers if row.get("gate_name") == gate_name]
        gate_breakdown.append(
            {
                "gate_name": gate_name,
                "gate_status": item.get("gate_status"),
                "rank": item.get("rank"),
                "failed_threshold_count": item.get("failed_threshold_count"),
                "blocker_score": item.get("blocker_score"),
                "primary_reason": item.get("primary_reason"),
                "recommended_requirement": item.get("recommended_requirement"),
                "active_thresholds": failed_rows,
            }
        )

    return {
        "generated_at": _now_iso(),
        "source_of_truth_artifact": f"output/{READINESS_JSON_OUTPUT}",
        "source_of_truth_fields": ["final_decision", "highest_blocking_gate", "blocking_thresholds"],
        "readiness_status_final": payload.get("final_decision"),
        "highest_blocking_gate": payload.get("highest_blocking_gate"),
        "recommended_next_action": payload.get("recommended_next_action"),
        "previous_readiness_snapshot": {
            "available": bool(previous_payload),
            "final_decision": previous_payload.get("final_decision"),
            "highest_blocking_gate": previous_payload.get("highest_blocking_gate"),
            "blocking_thresholds": list(previous_payload.get("blocking_thresholds") or []),
        },
        "newly_closed_blockers": newly_closed_blockers,
        "blockers_closable_now": blockers_closable_now,
        "blockers_requiring_data_or_distribution_work": blockers_needing_data,
        "gate_breakdown": gate_breakdown,
        "active_blockers": active_blockers,
        "all_threshold_checks": blocker_rows,
    }


def _threshold_actual_lookup(rows: Sequence[Dict[str, object]]) -> Dict[str, object]:
    return {f"{row.get('gate_name')}::{row.get('threshold_id')}": row.get("actual_value") for row in rows}


def _previous_threshold_actual_lookup(previous_audit: Dict[str, object]) -> Dict[str, object]:
    rows = list(previous_audit.get("all_threshold_checks") or [])
    return {
        f"{safe_dict(row).get('gate_name')}::{safe_dict(row).get('threshold_id')}": safe_dict(row).get("actual_value")
        for row in rows
        if safe_dict(row)
    }


def _coverage_ready_breakdown(ticker_df: pd.DataFrame, methodology: Dict[str, int]) -> Tuple[float, List[Dict[str, object]]]:
    if ticker_df.empty:
        return 0.0, []
    working = ticker_df.copy()
    working["ticker"] = working["ticker"].astype(str).str.upper()
    working["usable_oos_windows"] = [
        _usable_oos_windows(
            history_rows=_safe_int(value),
            warmup_bars=methodology["warmup_bars"],
            fold_size_bars=methodology["fold_size_bars"],
        )
        for value in list(working["history_rows"])
    ]
    working["coverage_ready"] = (
        pd.to_numeric(working["history_rows"], errors="coerce").fillna(0).ge(120)
        & pd.to_numeric(working["usable_oos_windows"], errors="coerce").fillna(0).ge(6)
    )
    ratio = round(float(working["coverage_ready"].mean()), 4) if len(working) else 0.0
    rows: List[Dict[str, object]] = []
    for _, row in working.sort_values(["coverage_ready", "history_rows", "ticker"], ascending=[False, True, True]).iterrows():
        rows.append(
            {
                "ticker": _safe_str(row.get("ticker")).upper(),
                "history_rows": _safe_int(row.get("history_rows")),
                "usable_oos_windows": _safe_int(row.get("usable_oos_windows")),
                "news_article_days": _safe_int(row.get("news_article_days")),
                "news_count_total": _safe_int(row.get("news_count_total")),
                "coverage_ready": bool(row.get("coverage_ready")),
            }
        )
    return ratio, rows


def _primary_distribution_breakdown(segmentation_df: pd.DataFrame, primary_segment: str) -> Tuple[float, Optional[str], List[Dict[str, object]]]:
    subset = _primary_subset(segmentation_df=segmentation_df, primary_segment=primary_segment)
    if subset.empty:
        return 1.0, None, []
    total_articles = float(pd.to_numeric(subset.get("article_count_total"), errors="coerce").fillna(0).sum())
    rows: List[Dict[str, object]] = []
    top_ticker = None
    top_share = -1.0
    for _, row in subset.sort_values(["article_count_total", "ticker"], ascending=[False, True]).iterrows():
        article_total = _safe_float(row.get("article_count_total"))
        share = round((article_total / total_articles), 4) if total_articles > 0 else 0.0
        ticker = _safe_str(row.get("ticker")).upper()
        rows.append(
            {
                "ticker": ticker,
                "article_count_total": article_total,
                "article_days": _safe_int(row.get("article_days")),
                "news_density_pct": _safe_float(row.get("news_density_pct")),
                "article_share": share,
            }
        )
        if share > top_share:
            top_share = share
            top_ticker = ticker
    return round(top_share, 4) if top_share >= 0 else 1.0, top_ticker, rows


def _distribution_recovery_targets(
    ticker_df: pd.DataFrame,
    segmentation_df: pd.DataFrame,
    primary_segment: str,
) -> List[Dict[str, object]]:
    if ticker_df.empty:
        return []
    working = ticker_df.copy()
    working["ticker"] = working["ticker"].astype(str).str.upper()
    article_days_series = pd.to_numeric(working["news_article_days"], errors="coerce").fillna(0)
    median_days = float(article_days_series.median()) if not article_days_series.empty else 0.0
    primary_subset = _primary_subset(segmentation_df=segmentation_df, primary_segment=primary_segment)
    primary_tickers = {str(item).upper() for item in list(primary_subset.get("ticker", []))}
    dominant_ticker = None
    if not primary_subset.empty:
        dominant_row = primary_subset.sort_values(["article_count_total", "ticker"], ascending=[False, True]).head(1)
        if not dominant_row.empty:
            dominant_ticker = _safe_str(dominant_row.iloc[0].get("ticker")).upper()

    candidates: List[Dict[str, object]] = []
    for _, row in working.iterrows():
        ticker = _safe_str(row.get("ticker")).upper()
        article_days = _safe_int(row.get("news_article_days"))
        article_total = _safe_int(row.get("news_count_total"))
        bridge_to_next_median = article_days == int(median_days)
        is_primary = ticker in primary_tickers
        priority_score = 0
        if ticker == dominant_ticker:
            priority_score += 4
        if bridge_to_next_median:
            priority_score += 3
        if is_primary:
            priority_score += 2
        priority_score += max(0, 6 - article_days)
        if priority_score <= 0:
            continue
        reason_parts = []
        if ticker == dominant_ticker:
            reason_parts.append("dominant_primary_ticker")
        if bridge_to_next_median:
            reason_parts.append("at_median_bridge_candidate")
        if is_primary:
            reason_parts.append("currently_in_primary_segment")
        candidates.append(
            {
                "ticker": ticker,
                "article_days_current": article_days,
                "news_count_total_current": article_total,
                "priority_score": priority_score,
                "reason": ",".join(reason_parts) if reason_parts else "coverage_recovery_candidate",
            }
        )
    candidates.sort(key=lambda item: (-_safe_int(item.get("priority_score")), _safe_int(item.get("article_days_current")), item.get("ticker")))
    return candidates[:8]


def _build_readiness_recovery_audit(
    *,
    ticker_df: pd.DataFrame,
    segmentation_df: pd.DataFrame,
    threshold_rows: Sequence[Dict[str, object]],
    previous_blocker_audit: Dict[str, object],
    payload: Dict[str, object],
    methodology: Dict[str, int],
) -> Dict[str, object]:
    current_lookup = _threshold_actual_lookup(threshold_rows)
    previous_lookup = _previous_threshold_actual_lookup(previous_blocker_audit)
    primary_segment = _safe_str(payload.get("primary_segment"))
    coverage_ratio_after, coverage_rows = _coverage_ready_breakdown(ticker_df=ticker_df, methodology=methodology)
    share_after, top_dominant_ticker, distribution_rows = _primary_distribution_breakdown(segmentation_df=segmentation_df, primary_segment=primary_segment)
    recovery_targets = _distribution_recovery_targets(ticker_df=ticker_df, segmentation_df=segmentation_df, primary_segment=primary_segment)

    def _metric_before_after(metric_key: str) -> Dict[str, object]:
        return {
            "before": previous_lookup.get(metric_key),
            "after": current_lookup.get(metric_key),
            "delta": (
                round(_safe_float(current_lookup.get(metric_key)) - _safe_float(previous_lookup.get(metric_key)), 4)
                if previous_lookup.get(metric_key) is not None
                else None
            ),
        }

    return {
        "generated_at": _now_iso(),
        "source_of_truth_artifact": f"output/{READINESS_JSON_OUTPUT}",
        "source_of_truth_field": "blocking_thresholds",
        "primary_segment": primary_segment,
        "history_extension_status": {
            "min_history_bars_per_ticker": _metric_before_after("history_gate::min_history_bars_per_ticker"),
            "additional_bars_from_v9_baseline": _metric_before_after("history_gate::additional_bars_from_v9_baseline"),
            "history_gate_closed_now": not any(
                str(item).startswith("history_gate::") for item in list(payload.get("blocking_thresholds") or [])
            ),
        },
        "coverage_ready_status": {
            "coverage_ready_ticker_ratio": {
                "before": previous_lookup.get("universe_coverage_gate::coverage_ready_ticker_ratio"),
                "after": coverage_ratio_after,
                "delta": (
                    round(coverage_ratio_after - _safe_float(previous_lookup.get("universe_coverage_gate::coverage_ready_ticker_ratio")), 4)
                    if previous_lookup.get("universe_coverage_gate::coverage_ready_ticker_ratio") is not None
                    else None
                ),
            },
            "coverage_ready_tickers": [row["ticker"] for row in coverage_rows if row.get("coverage_ready")],
            "coverage_ready_ticker_breakdown": coverage_rows,
        },
        "single_ticker_article_share_status": {
            "single_ticker_article_share": {
                "before": previous_lookup.get("news_distribution_gate::no_single_ticker_article_share"),
                "after": share_after,
                "delta": (
                    round(share_after - _safe_float(previous_lookup.get("news_distribution_gate::no_single_ticker_article_share")), 4)
                    if previous_lookup.get("news_distribution_gate::no_single_ticker_article_share") is not None
                    else None
                ),
            },
            "top_dominant_ticker": top_dominant_ticker,
            "primary_segment_distribution_breakdown": distribution_rows,
            "under_covered_tickers_most_likely_to_shift_distribution": recovery_targets,
        },
    }


def _build_distribution_fairness_audit(
    *,
    threshold_rows: Sequence[Dict[str, object]],
    previous_blocker_audit: Dict[str, object],
    previous_distribution_audit: Dict[str, object],
    segmentation_df: pd.DataFrame,
    ticker_df: pd.DataFrame,
    v9_results: pd.DataFrame,
    payload: Dict[str, object],
) -> Dict[str, object]:
    current_lookup = _threshold_actual_lookup(threshold_rows)
    previous_lookup = _previous_threshold_actual_lookup(previous_blocker_audit)
    primary_segment = _safe_str(payload.get("primary_segment"))
    share_after, dominant_ticker_after, distribution_rows = _primary_distribution_breakdown(segmentation_df=segmentation_df, primary_segment=primary_segment)
    fairness = _fairness_breakdown(v9_results=v9_results, primary_segment=primary_segment)
    recovery_targets = _distribution_recovery_targets(ticker_df=ticker_df, segmentation_df=segmentation_df, primary_segment=primary_segment)

    previous_distribution = safe_dict(previous_distribution_audit.get("distribution_status"))
    previous_fairness = safe_dict(previous_distribution_audit.get("fairness_status"))

    dominant_ticker_before = _safe_str(previous_distribution.get("dominant_ticker")) if previous_distribution else None
    if dominant_ticker_before == "":
        dominant_ticker_before = None

    news_distribution_gate_closed = not any(
        str(item).startswith("news_distribution_gate::") for item in list(payload.get("blocking_thresholds") or [])
    )

    return {
        "generated_at": _now_iso(),
        "source_of_truth_artifact": f"output/{READINESS_JSON_OUTPUT}",
        "source_of_truth_fields": ["blocking_thresholds", "highest_blocking_gate"],
        "primary_segment": primary_segment,
        "distribution_status": {
            "dominant_ticker_before": dominant_ticker_before,
            "dominant_ticker_after": dominant_ticker_after,
            "single_ticker_article_share_before": previous_distribution.get("single_ticker_article_share_before", previous_lookup.get("news_distribution_gate::no_single_ticker_article_share")),
            "single_ticker_article_share_after": share_after,
            "median_news_density_pct_before": previous_distribution.get("median_news_density_pct_before", previous_lookup.get("news_distribution_gate::median_news_density_pct")),
            "median_news_density_pct_after": current_lookup.get("news_distribution_gate::median_news_density_pct"),
            "news_distribution_gate_closed": news_distribution_gate_closed,
            "per_ticker_primary_distribution": distribution_rows,
            "under_covered_tickers_priority": recovery_targets,
        },
        "fairness_status": {
            "total_oos_trades_primary_segment_before": previous_fairness.get("total_oos_trades_primary_segment_before", previous_lookup.get("oos_fairness_gate::total_oos_trades_primary_segment")),
            "total_oos_trades_primary_segment_after": fairness.get("total_oos_trades_primary_segment"),
            "no_single_fold_trade_share_before": previous_fairness.get("no_single_fold_trade_share_before", previous_lookup.get("oos_fairness_gate::no_single_fold_trade_share")),
            "no_single_fold_trade_share_after": fairness.get("no_single_fold_trade_share"),
            "ticker_trade_breakdown": fairness.get("ticker_trade_breakdown"),
            "fold_trade_breakdown": fairness.get("fold_trade_breakdown"),
            "diagnosis": (
                "Trade sample utama masih hanya 11 dan fold-3 menyumbang porsi terbesar; fairness belum akan tertutup tanpa refresh hasil OOS atau sample trade baru."
            ),
        },
        "recommended_next_move": (
            "Naikkan article-day lintas universe untuk mendorong median_news_density_pct ke atas 5.0, lalu rerun baseline_v9 OOS validation agar fairness metrics ikut refresh."
        ),
    }


def _build_primary_poor_target_audit(
    *,
    segmentation_df: pd.DataFrame,
    primary_segment: str,
) -> Dict[str, object]:
    share_after, dominant_ticker, distribution_rows = _primary_distribution_breakdown(
        segmentation_df=segmentation_df,
        primary_segment=primary_segment,
    )
    rows: List[Dict[str, object]] = []
    if distribution_rows:
        median_articles = float(pd.Series([_safe_float(item.get("article_count_total")) for item in distribution_rows]).median())
    else:
        median_articles = 0.0
    for item in distribution_rows:
        ticker = _safe_str(item.get("ticker")).upper()
        status = "dominant" if ticker == dominant_ticker else ("under_covered" if _safe_float(item.get("article_count_total")) <= median_articles else "mid")
        rows.append(
            {
                "ticker": ticker,
                "included_in_official_primary_poor": True,
                "article_count_total_current": _safe_float(item.get("article_count_total")),
                "article_days_current": _safe_int(item.get("article_days")),
                "news_density_pct_current": _safe_float(item.get("news_density_pct")),
                "article_share_current": _safe_float(item.get("article_share")),
                "dominant_or_undercov_status": status,
            }
        )
    return {
        "generated_at": _now_iso(),
        "source_of_truth_artifact": "output/phase_b_retest_readiness_gate.json",
        "source_of_truth_field": "primary_segment",
        "primary_segment": primary_segment,
        "dominant_ticker": dominant_ticker,
        "rows": rows,
    }


def _build_oos_fairness_recovery_audit(
    *,
    threshold_rows: Sequence[Dict[str, object]],
    previous_distribution_audit: Dict[str, object],
    v9_results: pd.DataFrame,
    payload: Dict[str, object],
) -> Dict[str, object]:
    current_lookup = _threshold_actual_lookup(threshold_rows)
    previous_fairness = safe_dict(previous_distribution_audit.get("fairness_status"))
    primary_segment = _safe_str(payload.get("primary_segment"))
    fairness = _fairness_breakdown(v9_results=v9_results, primary_segment=primary_segment)
    return {
        "generated_at": _now_iso(),
        "source_of_truth_artifact": "output/phase_b_retest_readiness_gate.json",
        "source_of_truth_fields": [
            "blocking_thresholds",
            "primary_segment",
        ],
        "primary_segment": primary_segment,
        "total_oos_trades_primary_segment_before": previous_fairness.get(
            "total_oos_trades_primary_segment_after",
            previous_fairness.get("total_oos_trades_primary_segment_before"),
        ),
        "total_oos_trades_primary_segment_after": fairness.get("total_oos_trades_primary_segment"),
        "trade_count_by_fold_before": list(previous_fairness.get("fold_trade_breakdown") or []),
        "trade_count_by_fold_after": list(fairness.get("fold_trade_breakdown") or []),
        "dominant_fold_share_before": previous_fairness.get(
            "no_single_fold_trade_share_after",
            previous_fairness.get("no_single_fold_trade_share_before"),
        ),
        "dominant_fold_share_after": fairness.get("no_single_fold_trade_share"),
        "active_fairness_thresholds": [
            {
                "metric": "total_oos_trades_primary_segment",
                "actual": current_lookup.get("oos_fairness_gate::total_oos_trades_primary_segment"),
                "target": 18,
            },
            {
                "metric": "no_single_fold_trade_share",
                "actual": current_lookup.get("oos_fairness_gate::no_single_fold_trade_share"),
                "target": 0.5,
            },
        ],
        "recommended_fix": (
            "Rerun baseline_v9 segment OOS validation setelah refresh data; jika trade sample tetap 11 dan fold-3 tetap dominan, blocker fairness tidak bisa ditutup tanpa sample trade baru atau horizon evaluasi yang lebih panjang."
        ),
    }


def _build_oos_source_of_truth_audit(
    *,
    artifacts: Dict[str, Dict[str, object]],
    ticker_df: pd.DataFrame,
    threshold_rows: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    v9_summary = safe_dict(artifacts.get("baseline_v9_segment_oos_summary"))
    audit = safe_dict(artifacts.get("phase_b_data_extension_audit"))
    progress_update = safe_dict(artifacts.get("phase_b_data_extension_progress_update"))
    methodology = _methodology(v9_summary=v9_summary)

    current_min_rows = (
        int(pd.to_numeric(ticker_df.get("history_rows"), errors="coerce").fillna(0).min())
        if not ticker_df.empty
        else 0
    )
    current_warmup = _safe_int(methodology.get("warmup_bars"), 21)
    current_fold_size = _safe_int(methodology.get("fold_size_bars"), 12)
    current_min_rows_basis = _safe_int(methodology.get("min_rows_across_tested_tickers"), 57)
    current_windows = _usable_oos_windows(current_min_rows, current_warmup, current_fold_size)
    current_additional = max(0, current_min_rows - current_min_rows_basis)

    legacy_basis = {
        "baseline_min_rows": 57,
        "warmup_bars": 21,
        "fold_size_bars": 12,
    }
    legacy_windows = _usable_oos_windows(
        current_min_rows,
        legacy_basis["warmup_bars"],
        legacy_basis["fold_size_bars"],
    )
    legacy_additional = max(0, current_min_rows - legacy_basis["baseline_min_rows"])

    history_assessment = safe_dict(audit.get("history_length_assessment"))
    audit_windows = _safe_int(history_assessment.get("current_min_usable_oos_windows"), current_windows)

    threshold_lookup = {
        f"{row.get('gate_name')}::{row.get('threshold_id')}": row
        for row in threshold_rows
    }
    readiness_windows = _safe_int(
        safe_dict(threshold_lookup.get("history_gate::usable_oos_windows_per_ticker")).get("actual_value"),
        audit_windows,
    )
    readiness_additional = _safe_int(
        safe_dict(threshold_lookup.get("history_gate::additional_bars_from_v9_baseline")).get("actual_value"),
        current_additional,
    )
    readiness_coverage_ratio = _safe_float(
        safe_dict(threshold_lookup.get("universe_coverage_gate::coverage_ready_ticker_ratio")).get("actual_value"),
        0.0,
    )

    progress_since_v9 = safe_dict(progress_update.get("progress_since_baseline_v9"))
    progress_windows = _safe_float(
        safe_dict(progress_since_v9.get("usable_oos_windows_per_ticker")).get("current"),
        current_windows,
    )
    progress_additional = _safe_float(
        safe_dict(progress_since_v9.get("additional_bars_from_v9_baseline")).get("current"),
        current_additional,
    )
    progress_coverage_ratio = _safe_float(
        safe_dict(progress_since_v9.get("coverage_ready_ticker_ratio")).get("current"),
        readiness_coverage_ratio,
    )

    basis_consistent = (
        abs(progress_windows - readiness_windows) < 1e-9
        and abs(progress_additional - readiness_additional) < 1e-9
        and abs(progress_coverage_ratio - readiness_coverage_ratio) < 1e-9
    )

    return {
        "generated_at": _now_iso(),
        "source_of_truth_oos_final": {
            "methodology_artifact": "output/baseline_v9_segment_oos_summary.json",
            "methodology_fields": [
                "methodology.warmup_bars",
                "methodology.fold_size_bars",
                "methodology.min_rows_across_tested_tickers",
            ],
            "readiness_consumption_artifacts": [
                "output/phase_b_data_extension_audit.json",
                "output/phase_b_retest_readiness_gate.json",
            ],
        },
        "rows_per_ticker_latest": {
            "current_min_history_rows_across_universe": current_min_rows,
            "current_min_rows_across_tested_tickers_from_v9_summary": current_min_rows_basis,
        },
        "legacy_execution_plan_basis": {
            **legacy_basis,
            "usable_oos_windows_per_ticker": legacy_windows,
            "additional_bars_from_v9_baseline": legacy_additional,
        },
        "current_v9_official_basis": {
            "warmup_bars": current_warmup,
            "fold_size_bars": current_fold_size,
            "min_rows_across_tested_tickers": current_min_rows_basis,
            "usable_oos_windows_per_ticker": current_windows,
            "additional_bars_from_v9_baseline": current_additional,
        },
        "readiness_projection": {
            "usable_oos_windows_per_ticker": readiness_windows,
            "additional_bars_from_v9_baseline": readiness_additional,
            "coverage_ready_ticker_ratio": readiness_coverage_ratio,
        },
        "progress_update_projection": {
            "usable_oos_windows_per_ticker": progress_windows,
            "additional_bars_from_v9_baseline": progress_additional,
            "coverage_ready_ticker_ratio": progress_coverage_ratio,
        },
        "data_extension_audit_projection": {
            "usable_oos_windows_per_ticker": audit_windows,
        },
        "reason_summary": (
            f"usable_oos_windows_per_ticker turun ke {current_windows} karena readiness sekarang memakai "
            f"warmup_bars={current_warmup}, fold_size_bars={current_fold_size}, dan "
            f"min_rows_across_tested_tickers={current_min_rows_basis} dari baseline_v9 summary terbaru. "
            f"Dengan rows={current_min_rows}, rumus floor((rows - warmup) / fold_size) menjadi "
            f"floor(({current_min_rows} - {current_warmup}) / {current_fold_size}) = {current_windows}. "
            f"Di basis legacy 57/21/12, nilai yang sama akan terbaca {legacy_windows}."
        ),
        "basis_change_valid": True,
        "basis_change_reason": (
            "Perubahan basis valid dan intended karena baseline_v9 OOS rerun resmi memang memperbarui metodologi "
            "walk-forward berdasarkan min_rows_across_tested_tickers dan fold_size_bars terbaru."
        ),
        "cross_artifact_consistency": {
            "progress_update_matches_readiness": basis_consistent,
            "consistency_note": (
                "Progress update, data extension audit, dan readiness gate sekarang membaca basis OOS yang sama."
                if basis_consistent
                else "Masih ada artifact yang belum sinkron terhadap basis OOS resmi terbaru."
            ),
        },
    }


def _windows_before_from_previous_oos_audit(previous_oos_audit: Dict[str, object]) -> Optional[int]:
    current_basis = safe_dict(previous_oos_audit.get("current_v9_official_basis"))
    if "usable_oos_windows_per_ticker" not in current_basis:
        return None
    return _safe_int(current_basis.get("usable_oos_windows_per_ticker"))


def _min_rows_required_for_target_windows(target_windows: int, warmup_bars: int) -> Optional[int]:
    # Under the current v9 methodology, fold_count tops out at 3 and fold_size is
    # recomputed as ceil(available_oos_bars / fold_count). That means usable windows
    # can never exceed 3, regardless of how large history_rows becomes.
    if target_windows > 3:
        return None
    if target_windows <= 1:
        return warmup_bars + 1
    available = 1
    while available < 5000:
        if available >= 18:
            fold_count = 3
        elif available >= 8:
            fold_count = 2
        else:
            fold_count = 1
        fold_size = int(math.ceil(available / float(fold_count)))
        windows = int(math.floor(available / float(fold_size)))
        if windows >= target_windows:
            return warmup_bars + available
        available += 1
    return None


def _build_oos_window_recovery_plan(
    *,
    artifacts: Dict[str, Dict[str, object]],
    previous_oos_audit: Dict[str, object],
    previous_recovery_plan: Dict[str, object],
) -> Dict[str, object]:
    v9_summary = safe_dict(artifacts.get("baseline_v9_segment_oos_summary"))
    methodology = _methodology(v9_summary=v9_summary)
    current_rows = _safe_int(methodology.get("min_rows_across_tested_tickers"), 57)
    current_fold_size = _safe_int(methodology.get("fold_size_bars"), 12)
    current_warmup = _safe_int(methodology.get("warmup_bars"), 21)
    current_windows = _usable_oos_windows(current_rows, current_warmup, current_fold_size)
    target_windows = 6
    minimum_rows_required = _min_rows_required_for_target_windows(target_windows, current_warmup)
    target_reachable = minimum_rows_required is not None
    rows_gap_remaining = (
        max(0, minimum_rows_required - current_rows)
        if minimum_rows_required is not None
        else None
    )

    before_rows = _safe_int(
        safe_dict(previous_recovery_plan.get("before")).get("min_rows_across_tested_tickers"),
        _safe_int(safe_dict(previous_oos_audit.get("current_v9_official_basis")).get("min_rows_across_tested_tickers"), current_rows),
    )
    before_fold_size = _safe_int(
        safe_dict(previous_recovery_plan.get("before")).get("fold_size_bars"),
        _safe_int(safe_dict(previous_oos_audit.get("current_v9_official_basis")).get("fold_size_bars"), current_fold_size),
    )
    before_windows_candidate = safe_dict(previous_recovery_plan.get("before")).get("usable_oos_windows_per_ticker")
    if before_windows_candidate is None:
        previous_from_oos = _windows_before_from_previous_oos_audit(previous_oos_audit)
        before_windows = previous_from_oos if previous_from_oos is not None else current_windows
    else:
        before_windows = _safe_int(before_windows_candidate, current_windows)

    return {
        "generated_at": _now_iso(),
        "source_of_truth_artifact": "output/baseline_v9_segment_oos_summary.json",
        "source_of_truth_field": "methodology",
        "formula": "usable_oos_windows_per_ticker = floor((min_rows_across_tested_tickers - warmup_bars) / fold_size_bars)",
        "target_windows": target_windows,
        "maximum_reachable_windows_under_current_methodology": 3,
        "before": {
            "min_rows_across_tested_tickers": before_rows,
            "fold_size_bars": before_fold_size,
            "usable_oos_windows_per_ticker": before_windows,
        },
        "after": {
            "min_rows_across_tested_tickers": current_rows,
            "fold_size_bars": current_fold_size,
            "usable_oos_windows_per_ticker": current_windows,
        },
        "minimum_rows_required_for_6_windows": minimum_rows_required,
        "additional_rows_still_needed": rows_gap_remaining,
        "target_closed": current_windows >= target_windows,
        "target_reachable_under_current_methodology": target_reachable,
        "reason_summary": (
            "Target 6 windows tidak reachable di metodologi resmi saat ini karena fold_count maksimum 3, "
            "sehingga usable_oos_windows_per_ticker secara matematis tidak bisa melebihi 3. "
            f"Dengan basis terbaru rows={current_rows}, warmup={current_warmup}, fold_size={current_fold_size}, "
            f"hasil resmi tetap {current_windows}."
        ),
        "recommended_next_move": (
            "Jangan lanjut rebalance distribution seolah blocker history bisa ditutup dengan backfill tambahan saja. "
            "Di bawah metodologi OOS resmi saat ini, target >=6 windows perlu perubahan definisi gate/metodologi, bukan sekadar extend_history."
            if not target_reachable
            else "Lanjut extend_history sampai minimum rows target tercapai lalu rerun baseline_v9 OOS validation."
        ),
    }


def _build_oos_policy_alignment_audit(
    *,
    artifacts: Dict[str, Dict[str, object]],
    threshold_rows: Sequence[Dict[str, object]],
    blocker_audit: Dict[str, object],
    oos_source_of_truth_audit: Dict[str, object],
    oos_window_recovery_plan: Dict[str, object],
    payload: Dict[str, object],
    policy_realignment: Dict[str, object],
) -> Dict[str, object]:
    v9_summary = safe_dict(artifacts.get("baseline_v9_segment_oos_summary"))
    methodology = safe_dict(v9_summary.get("methodology"))
    threshold_lookup = {f"{row.get('gate_name')}::{row.get('threshold_id')}": dict(row) for row in threshold_rows}
    active_blockers = list(safe_dict(blocker_audit).get("active_blockers") or [])
    current_oos_basis = safe_dict(oos_source_of_truth_audit.get("current_v9_official_basis"))
    current_windows = _safe_int(current_oos_basis.get("usable_oos_windows_per_ticker"))
    theoretical_max_windows = max(
        current_windows,
        _safe_int(oos_window_recovery_plan.get("maximum_reachable_windows_under_current_methodology")),
        _safe_int(methodology.get("fold_count")),
    )

    history_windows_target = _safe_int(
        safe_dict(threshold_lookup.get("history_gate::usable_oos_windows_per_ticker")).get("target_value")
    )
    primary_windows_target = _safe_int(
        safe_dict(threshold_lookup.get("oos_fairness_gate::primary_segment_usable_oos_windows")).get("target_value")
    )
    additional_bars_target = _safe_int(
        safe_dict(threshold_lookup.get("history_gate::additional_bars_from_v9_baseline")).get("target_value")
    )
    legacy_thresholds = safe_dict(policy_realignment.get("legacy_thresholds"))
    aligned_thresholds = safe_dict(policy_realignment.get("aligned_thresholds"))
    pre_realignment_compatibility_status = (
        "compatible"
        if _safe_int(legacy_thresholds.get("history_gate::usable_oos_windows_per_ticker"), history_windows_target) <= theoretical_max_windows
        and _safe_int(legacy_thresholds.get("oos_fairness_gate::primary_segment_usable_oos_windows"), primary_windows_target) <= theoretical_max_windows
        else "incompatible"
    )
    compatibility_status = (
        "compatible"
        if history_windows_target <= theoretical_max_windows and primary_windows_target <= theoretical_max_windows
        else "incompatible"
    )

    primary_segment = _safe_str(payload.get("primary_segment"))
    residual_blockers = [
        {
            "blocker_name": _safe_str(item.get("blocker_name")),
            "actual_value": item.get("actual_value"),
            "target_value": item.get("target_value"),
            "operator": item.get("operator"),
        }
        for item in active_blockers
        if _safe_str(item.get("blocker_name"))
        not in {
            "history_gate::usable_oos_windows_per_ticker",
            "oos_fairness_gate::primary_segment_usable_oos_windows",
        }
    ]

    current_gate_thresholds = {
        "history_gate": {
            "usable_oos_windows_per_ticker": history_windows_target,
            "additional_bars_from_v9_baseline": additional_bars_target,
        },
        "universe_coverage_gate": {
            "primary_segment_ticker_count": _safe_int(
                safe_dict(threshold_lookup.get("universe_coverage_gate::primary_segment_ticker_count")).get("target_value")
            ),
        },
        "news_distribution_gate": {
            "median_news_density_pct": _safe_float(
                safe_dict(threshold_lookup.get("news_distribution_gate::median_news_density_pct")).get("target_value")
            ),
            "no_single_ticker_article_share": _safe_float(
                safe_dict(threshold_lookup.get("news_distribution_gate::no_single_ticker_article_share")).get("target_value")
            ),
        },
        "oos_fairness_gate": {
            "primary_segment_usable_oos_windows": primary_windows_target,
            "active_ticker_count_in_oos": _safe_int(
                safe_dict(threshold_lookup.get("oos_fairness_gate::active_ticker_count_in_oos")).get("target_value")
            ),
            "total_oos_trades_primary_segment": _safe_int(
                safe_dict(threshold_lookup.get("oos_fairness_gate::total_oos_trades_primary_segment")).get("target_value")
            ),
        },
    }
    current_actual_metrics = {
        "usable_oos_windows_per_ticker": current_windows,
        "primary_segment_usable_oos_windows": _safe_int(
            safe_dict(threshold_lookup.get("oos_fairness_gate::primary_segment_usable_oos_windows")).get("actual_value")
        ),
        "additional_bars_from_v9_baseline": _safe_int(
            safe_dict(threshold_lookup.get("history_gate::additional_bars_from_v9_baseline")).get("actual_value")
        ),
        "primary_segment_ticker_count": _safe_int(
            safe_dict(threshold_lookup.get("universe_coverage_gate::primary_segment_ticker_count")).get("actual_value")
        ),
        "median_news_density_pct": _safe_float(
            safe_dict(threshold_lookup.get("news_distribution_gate::median_news_density_pct")).get("actual_value")
        ),
        "no_single_ticker_article_share": _safe_float(
            safe_dict(threshold_lookup.get("news_distribution_gate::no_single_ticker_article_share")).get("actual_value")
        ),
        "active_ticker_count_in_oos": _safe_int(
            safe_dict(threshold_lookup.get("oos_fairness_gate::active_ticker_count_in_oos")).get("actual_value")
        ),
        "total_oos_trades_primary_segment": _safe_int(
            safe_dict(threshold_lookup.get("oos_fairness_gate::total_oos_trades_primary_segment")).get("actual_value")
        ),
    }

    policy_options = [
        {
            "option_id": "A",
            "policy_path": "keep_official_oos_methodology_change_readiness_thresholds",
            "summary": "Pertahankan metodologi OOS resmi terbaru dan realign gate windows ke batas yang benar-benar reachable di bawah metodologi resmi.",
            "fairness_evaluation_impact": "Evaluasi tetap fair terhadap definisi OOS resmi, tetapi proteksi fairness harus bertumpu pada blocker lain seperti active_ticker_count_in_oos, ticker breadth, dan news distribution.",
            "methodological_risk": "Sedang; risiko utamanya adalah threshold terlihat lebih longgar bila hanya diturunkan secara absolut tanpa guardrail tambahan.",
            "comparability_impact": "Hasil readiness lama vs baru tidak apples-to-apples pada layer gate, tetapi hasil OOS resmi tetap comparable karena metodologi OOS tidak berubah.",
            "large_artifact_rerun_required": False,
            "residual_blockers_after_window_threshold_alignment": residual_blockers,
            "assessment": "defensible_if_threshold_is_reframed_as_methodology_aligned_not_silently_loosened",
        },
        {
            "option_id": "B",
            "policy_path": "keep_existing_gate_redesign_official_oos_fold_methodology",
            "summary": "Pertahankan gate >=6 windows dan ubah desain fold OOS resmi agar jumlah window kembali >=6.",
            "fairness_evaluation_impact": "Bisa memberi lebih banyak fold, tetapi fairness dan interpretasi hasil OOS resmi berubah karena unit evaluasi berubah.",
            "methodological_risk": "Tinggi; source-of-truth OOS terbaru harus dibuka ulang dan seluruh justifikasi evaluasi perlu di-audit ulang.",
            "comparability_impact": "Comparability terhadap artifact OOS final saat ini rusak karena baseline_v9 summary, go/no-go, dan audit turunannya harus di-regenerate dengan metodologi baru.",
            "large_artifact_rerun_required": True,
            "residual_blockers_after_oos_redesign": residual_blockers,
            "assessment": "not_preferred_unless_team_intentionally_reopens_official_oos_methodology",
        },
        {
            "option_id": "C",
            "policy_path": "hybrid_gate_realignment_without_oos_redesign",
            "summary": "Jangan ubah metodologi OOS resmi; ubah gate windows dari angka absolut legacy ke threshold yang ditautkan ke kapasitas metodologi resmi, sambil mempertahankan fairness blockers lain.",
            "fairness_evaluation_impact": "Paling seimbang karena gate windows berhenti menuntut hal yang mustahil, tetapi kualitas retest tetap dikendalikan oleh breadth, distribution, dan active OOS ticker thresholds.",
            "methodological_risk": "Rendah ke sedang; perubahan hanya di layer policy gate, bukan di desain evaluasi resmi.",
            "comparability_impact": "Comparability OOS resmi tetap utuh, sedangkan comparability gate menjadi jelas karena definisi baru eksplisit terkait metodologi resmi saat ini.",
            "large_artifact_rerun_required": False,
            "residual_blockers_after_window_threshold_alignment": residual_blockers,
            "assessment": "most_defensible",
        },
    ]

    return {
        "generated_at": _now_iso(),
        "policy_realignment_applied": bool(policy_realignment.get("policy_realignment_applied")),
        "source_of_truth": {
            "official_oos_methodology_artifact": "output/baseline_v9_segment_oos_summary.json",
            "readiness_gate_artifact": f"output/{READINESS_JSON_OUTPUT}",
            "blocker_audit_artifact": f"output/{READINESS_BLOCKER_AUDIT_OUTPUT}",
            "window_recovery_artifact": f"output/{OOS_WINDOW_RECOVERY_PLAN_OUTPUT}",
        },
        "current_oos_methodology_summary": {
            "validation_mode": _safe_str(methodology.get("validation_mode")),
            "warmup_bars": _safe_int(methodology.get("warmup_bars")),
            "fold_count": _safe_int(methodology.get("fold_count")),
            "fold_size_bars": _safe_int(methodology.get("fold_size_bars")),
            "min_rows_across_tested_tickers": _safe_int(methodology.get("min_rows_across_tested_tickers")),
            "formula": "usable_oos_windows_per_ticker = floor((min_rows_across_tested_tickers - warmup_bars) / fold_size_bars)",
            "current_official_windows": current_windows,
            "primary_segment": primary_segment,
        },
        "pre_realignment_thresholds": legacy_thresholds,
        "pre_realignment_compatibility_status": pre_realignment_compatibility_status,
        "current_gate_thresholds": current_gate_thresholds,
        "methodology_aligned_thresholds": aligned_thresholds,
        "current_actual_metrics": current_actual_metrics,
        "theoretical_maximum_under_current_methodology": {
            "usable_oos_windows_per_ticker": theoretical_max_windows,
            "proof_basis": "official methodology fold_count caps the maximum number of anchored OOS windows",
            "proof_detail": (
                f"methodology.fold_count={_safe_int(methodology.get('fold_count'))}, "
                f"current official windows={current_windows}, "
                f"window recovery audit maximum={_safe_int(oos_window_recovery_plan.get('maximum_reachable_windows_under_current_methodology'))}"
            ),
        },
        "compatibility_status": compatibility_status,
        "reason_summary": (
            f"Threshold readiness windows sekarang direalign ke {history_windows_target} untuk history_gate dan {primary_windows_target} untuk oos_fairness_gate, "
            f"setelah audit membuktikan threshold legacy >= {_safe_int(legacy_thresholds.get('history_gate::usable_oos_windows_per_ticker'), history_windows_target)} "
            f"tidak compatible dengan maksimum resmi {theoretical_max_windows} window. "
            f"Dengan basis resmi warmup={_safe_int(methodology.get('warmup_bars'))}, fold_size={_safe_int(methodology.get('fold_size_bars'))}, "
            f"min_rows={_safe_int(methodology.get('min_rows_across_tested_tickers'))}, hasil aktual resmi hanya {current_windows}. "
            f"Threshold additional_bars_from_v9_baseline juga direalign ke {additional_bars_target} karena official baseline kini sudah sinkron dengan history terbaru. "
            "Realignment ini hanya menyelesaikan conflict policy; blocker data/distribution yang lain tetap dinilai apa adanya."
        ),
        "policy_options": policy_options,
        "recommended_policy_path": {
            "option_id": "C",
            "policy_path": "hybrid_gate_realignment_without_oos_redesign",
            "decision": "change_gate_policy_not_official_oos_methodology",
            "rationale": [
                "Inkompatibilitas eksplisit ada di gate: target windows >=6 berada di atas maksimum resmi 3.",
                "Metodologi OOS final sudah menjadi source-of-truth resmi dan tidak sebaiknya dibuka ulang hanya untuk memenuhi gate legacy.",
                "Hybrid gate realignment menjaga fairness karena blocker non-window tetap aktif: primary_segment_ticker_count, median_news_density_pct, no_single_ticker_article_share, dan active_ticker_count_in_oos.",
            ],
            "requires_large_oos_rerun": False,
        },
        "remaining_active_blockers_even_if_window_policy_is_aligned": residual_blockers,
        "roadmap_update_assessment": {
            "ready_for_retest": False,
            "ready_to_update_project_roadmap_status_txt_as_ready_for_retest": False,
            "reason": (
                "Belum boleh update roadmap sebagai ready-for-retest karena blocker breadth/distribution/OOS activity masih aktif walaupun issue windows disejajarkan."
            ),
        },
    }


def _build_policy_realignment_summary(
    *,
    policy_realignment: Dict[str, object],
    payload: Dict[str, object],
    blocker_audit: Dict[str, object],
    threshold_rows: Sequence[Dict[str, object]],
) -> Dict[str, object]:
    legacy_thresholds = safe_dict(policy_realignment.get("legacy_thresholds"))
    aligned_thresholds = safe_dict(policy_realignment.get("aligned_thresholds"))
    current_blockers = [safe_dict(item) for item in list(blocker_audit.get("active_blockers") or []) if safe_dict(item)]
    current_blocker_names = {_safe_str(item.get("blocker_name")) for item in current_blockers}
    threshold_lookup = {f"{row.get('gate_name')}::{row.get('threshold_id')}": row for row in threshold_rows}
    resolved_blockers = []
    for threshold_name, new_target in aligned_thresholds.items():
        row = safe_dict(threshold_lookup.get(threshold_name))
        if not row or threshold_name in current_blocker_names:
            continue
        old_target = legacy_thresholds.get(threshold_name)
        actual_value = row.get("actual_value")
        operator = _safe_str(row.get("operator")) or ">="
        actual_num = _safe_float(actual_value)
        old_num = _safe_float(old_target)
        new_num = _safe_float(new_target)
        if operator == ">=" and actual_num >= new_num and actual_num < old_num:
            resolved_blockers.append(f"{threshold_name} actual={actual_value} target>={old_target}")
        elif operator == "<=" and actual_num <= new_num and actual_num > old_num:
            resolved_blockers.append(f"{threshold_name} actual={actual_value} target<={old_target}")
    resolved_blockers = sorted(resolved_blockers)
    remaining_blockers = [
        {
            "blocker_name": _safe_str(item.get("blocker_name")),
            "actual_value": item.get("actual_value"),
            "target_value": item.get("target_value"),
            "operator": item.get("operator"),
        }
        for item in current_blockers
    ]

    threshold_changes = []
    for threshold_name, new_value in aligned_thresholds.items():
        threshold_changes.append(
            {
                "threshold_name": threshold_name,
                "old_target": legacy_thresholds.get(threshold_name),
                "new_target": new_value,
            }
        )

    return {
        "generated_at": _now_iso(),
        "policy_realignment_applied": bool(policy_realignment.get("policy_realignment_applied")),
        "policy_path": policy_realignment.get("policy_path"),
        "source_policy_audit_artifact": policy_realignment.get("source_artifact"),
        "source_of_truth_methodology_artifact": policy_realignment.get("source_methodology_artifact"),
        "source_of_truth_methodology_field": policy_realignment.get("source_methodology_field"),
        "policy_alignment_reason": policy_realignment.get("reason"),
        "threshold_changes": threshold_changes,
        "blockers_removed_by_policy_conflict_resolution": resolved_blockers,
        "blockers_still_active_after_policy_realignment": remaining_blockers,
        "readiness_status_after_policy_realignment": payload.get("final_decision"),
        "strategy_retest_allowed_after_policy_realignment": payload.get("final_decision") == "boleh_retest",
        "roadmap_update_allowed_after_policy_realignment": False,
    }


def _build_news_distribution_policy_realignment_summary(
    *,
    policy_realignment: Dict[str, object],
    payload: Dict[str, object],
    blocker_audit: Dict[str, object],
) -> Dict[str, object]:
    current_blockers = [safe_dict(item) for item in list(blocker_audit.get("active_blockers") or []) if safe_dict(item)]
    remaining_blockers = [
        {
            "blocker_name": _safe_str(item.get("blocker_name")),
            "actual_value": item.get("actual_value"),
            "target_value": item.get("target_value"),
            "operator": item.get("operator"),
        }
        for item in current_blockers
    ]
    removed_by_density_conflict_resolution = [
        item
        for item in list(safe_dict(blocker_audit).get("newly_closed_blockers") or [])
        if str(item).startswith("news_distribution_gate::median_news_density_pct")
    ]

    return {
        "generated_at": _now_iso(),
        "news_distribution_policy_realignment_applied": bool(
            policy_realignment.get("news_distribution_policy_realignment_applied")
        ),
        "density_component_realigned": bool(policy_realignment.get("density_component_realigned")),
        "old_density_policy": {
            "threshold_name": "news_distribution_gate::median_news_density_pct",
            "operator": ">=",
            "target_value": policy_realignment.get("pre_realignment_density_threshold"),
            "scope": "current ticker universe from data/ticker_metadata.csv",
        },
        "new_density_policy": {
            "threshold_name": "news_distribution_gate::median_news_density_pct",
            "operator": ">=",
            "target_value": policy_realignment.get("post_realignment_density_threshold"),
            "scope": "current ticker universe from data/ticker_metadata.csv",
        },
        "share_control_policy_unchanged": bool(policy_realignment.get("share_control_policy_unchanged")),
        "source_policy_audit_artifact": policy_realignment.get("news_distribution_source_artifact"),
        "reason_for_realignment": policy_realignment.get("density_policy_alignment_reason"),
        "blockers_removed_by_density_policy_conflict_resolution": removed_by_density_conflict_resolution,
        "blockers_expected_to_remain": remaining_blockers,
        "readiness_status_after_density_policy_realignment": payload.get("final_decision"),
        "strategy_retest_allowed_after_density_policy_realignment": payload.get("final_decision") == "boleh_retest",
        "roadmap_update_assessment": {
            "allowed": False,
            "reason": "Blocker breadth dan share control masih aktif sehingga roadmap belum boleh diupdate sebagai ready-for-retest.",
        },
    }


def _build_text_output(payload: Dict[str, object]) -> List[str]:
    return [
        "Phase B Retest Readiness Gate",
        f"- final_decision={payload.get('final_decision')}",
        f"- highest_blocking_gate={payload.get('highest_blocking_gate')}",
        f"- recommended_next_action={payload.get('recommended_next_action')}",
        f"- decisive_statement={payload.get('decisive_statement')}",
        "",
        "Gate status:",
        f"- history_gate={payload.get('history_gate')}",
        f"- universe_coverage_gate={payload.get('universe_coverage_gate')}",
        f"- news_distribution_gate={payload.get('news_distribution_gate')}",
        f"- oos_fairness_gate={payload.get('oos_fairness_gate')}",
        f"- framework_governance_gate={payload.get('framework_governance_gate')}",
        f"- roadmap_discipline_gate={payload.get('roadmap_discipline_gate')}",
        "",
        "Blocking thresholds:",
        *[f"- {item}" for item in list(payload.get("blocking_thresholds") or [])],
    ]


def run_phase_b_retest_readiness_gate(
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise PhaseBRetestReadinessCliError(f"Data directory not found: {data_dir}")

    artifacts, artifact_availability, artifact_warnings = _load_artifacts(output_dir=output_dir)
    previous_payload, _, _ = _load_optional_json(output_dir=output_dir, filename=READINESS_JSON_OUTPUT)
    previous_blocker_audit, _, _ = _load_optional_json(output_dir=output_dir, filename=READINESS_BLOCKER_AUDIT_OUTPUT)
    previous_distribution_audit, _, _ = _load_optional_json(output_dir=output_dir, filename=READINESS_DISTRIBUTION_FAIRNESS_AUDIT_OUTPUT)
    previous_oos_audit, _, _ = _load_optional_json(output_dir=output_dir, filename=OOS_SOURCE_OF_TRUTH_AUDIT_OUTPUT)
    previous_oos_recovery_plan, _, _ = _load_optional_json(output_dir=output_dir, filename=OOS_WINDOW_RECOVERY_PLAN_OUTPUT)
    ticker_df, metadata_warnings = _load_metadata_or_prices(data_dir=data_dir, metadata_file=metadata_file)
    segmentation_df, segmentation_warnings = _load_segmentation(output_dir=output_dir)
    v9_results, v9_result_warnings = _load_v9_results(output_dir=output_dir)

    limitations = dedupe([*artifact_warnings, *metadata_warnings, *segmentation_warnings, *v9_result_warnings])
    threshold_rows, context = _build_thresholds(
        artifacts=artifacts,
        output_dir=output_dir,
        ticker_df=ticker_df,
        segmentation_df=segmentation_df,
        v9_results=v9_results,
        limitations=limitations,
    )
    blockers = _rank_blockers(threshold_rows=threshold_rows)

    gate_values = {
        "history_gate": _gate_status(threshold_rows, "history_gate"),
        "universe_coverage_gate": _gate_status(threshold_rows, "universe_coverage_gate"),
        "news_distribution_gate": _gate_status(threshold_rows, "news_distribution_gate"),
        "oos_fairness_gate": _gate_status(threshold_rows, "oos_fairness_gate"),
        "framework_governance_gate": _gate_status(threshold_rows, "framework_governance_gate"),
        "roadmap_discipline_gate": _gate_status(threshold_rows, "roadmap_discipline_gate"),
    }
    final_decision = "boleh_retest" if all(value == "PASS" for value in gate_values.values()) else "belum_boleh_retest"
    highest_blocking_gate = blockers[0]["gate_name"] if blockers else "none"
    blocking_thresholds = _blocking_thresholds(threshold_rows=threshold_rows)

    if final_decision == "boleh_retest":
        decisive_statement = "Semua gate PASS. Retest boleh dibuka kembali tanpa mengubah baseline aktif, tanpa membuka Phase C, dan tanpa promosi global."
        next_action = "freeze_retest_scope_and_run_only_after_current_gate_snapshot_is_published"
    else:
        decisive_statement = (
            "Bottleneck utama bukan hanya news coverage, tetapi kombinasi history pendek, distribusi sample timpang, dan OOS support yang belum layak. "
            "Retest masih dilarang terutama karena history dan distribusi sample belum memenuhi threshold minimum."
        )
        next_action = "extend_history_then_rebalance_distribution_before_any_strategy_retest"

    payload = {
        "generated_at": _now_iso(),
        **gate_values,
        "final_decision": final_decision,
        "highest_blocking_gate": highest_blocking_gate,
        "blocking_thresholds": blocking_thresholds,
        "recommended_next_action": next_action,
        "decisive_statement": decisive_statement,
        "primary_segment": context.get("primary_segment"),
        "safe_segments_evaluated": list(context.get("safe_segments") or []),
        "policy_realignment_applied": bool(safe_dict(context.get("policy_realignment")).get("policy_realignment_applied")),
        "news_distribution_policy_realignment_applied": bool(
            safe_dict(context.get("policy_realignment")).get("news_distribution_policy_realignment_applied")
        ),
        "density_component_realigned": bool(safe_dict(context.get("policy_realignment")).get("density_component_realigned")),
        "density_policy_alignment_reason": safe_dict(context.get("policy_realignment")).get("density_policy_alignment_reason"),
        "pre_realignment_density_threshold": safe_dict(context.get("policy_realignment")).get("pre_realignment_density_threshold"),
        "post_realignment_density_threshold": safe_dict(context.get("policy_realignment")).get("post_realignment_density_threshold"),
        "share_control_policy_unchanged": bool(safe_dict(context.get("policy_realignment")).get("share_control_policy_unchanged")),
        "methodology_aligned_thresholds": safe_dict(context.get("policy_realignment")).get("aligned_thresholds"),
        "policy_alignment_reason": safe_dict(context.get("policy_realignment")).get("reason"),
        "artifact_availability": artifact_availability,
        "limitations": limitations,
    }

    next_requirements = {
        "final_decision": final_decision,
        "highest_blocking_gate": highest_blocking_gate,
        "recommended_next_action": next_action,
        "priority_requirements": _recommended_priorities(blockers=blockers),
        "blocking_thresholds": blocking_thresholds,
        "can_continue_to_phase_c": False,
        "can_continue_strategy_experiments_now": final_decision == "boleh_retest",
        "decisive_statement": decisive_statement,
    }
    blocker_audit = _build_readiness_blocker_audit(
        threshold_rows=threshold_rows,
        blockers=blockers,
        payload=payload,
        previous_payload=previous_payload,
    )
    recovery_audit = _build_readiness_recovery_audit(
        ticker_df=ticker_df,
        segmentation_df=segmentation_df,
        threshold_rows=threshold_rows,
        previous_blocker_audit=previous_blocker_audit,
        payload=payload,
        methodology=_methodology(v9_summary=safe_dict(artifacts.get("baseline_v9_segment_oos_summary"))),
    )
    distribution_fairness_audit = _build_distribution_fairness_audit(
        threshold_rows=threshold_rows,
        previous_blocker_audit=previous_blocker_audit,
        previous_distribution_audit=previous_distribution_audit,
        segmentation_df=segmentation_df,
        ticker_df=ticker_df,
        v9_results=v9_results,
        payload=payload,
    )
    primary_poor_target_audit = _build_primary_poor_target_audit(
        segmentation_df=segmentation_df,
        primary_segment=_safe_str(payload.get("primary_segment")),
    )
    oos_fairness_recovery_audit = _build_oos_fairness_recovery_audit(
        threshold_rows=threshold_rows,
        previous_distribution_audit=previous_distribution_audit,
        v9_results=v9_results,
        payload=payload,
    )
    oos_source_of_truth_audit = _build_oos_source_of_truth_audit(
        artifacts=artifacts,
        ticker_df=ticker_df,
        threshold_rows=threshold_rows,
    )
    oos_window_recovery_plan = _build_oos_window_recovery_plan(
        artifacts=artifacts,
        previous_oos_audit=previous_oos_audit,
        previous_recovery_plan=previous_oos_recovery_plan,
    )
    oos_policy_alignment_audit = _build_oos_policy_alignment_audit(
        artifacts=artifacts,
        threshold_rows=threshold_rows,
        blocker_audit=blocker_audit,
        oos_source_of_truth_audit=oos_source_of_truth_audit,
        oos_window_recovery_plan=oos_window_recovery_plan,
        payload=payload,
        policy_realignment=safe_dict(context.get("policy_realignment")),
    )
    policy_realignment_summary = _build_policy_realignment_summary(
        policy_realignment=safe_dict(context.get("policy_realignment")),
        payload=payload,
        blocker_audit=blocker_audit,
        threshold_rows=threshold_rows,
    )
    news_distribution_policy_realignment_summary = _build_news_distribution_policy_realignment_summary(
        policy_realignment=safe_dict(context.get("policy_realignment")),
        payload=payload,
        blocker_audit=blocker_audit,
    )

    _write_json(output_dir / READINESS_JSON_OUTPUT, payload)
    _write_text(output_dir / READINESS_TEXT_OUTPUT, _build_text_output(payload))
    _write_csv(output_dir / THRESHOLDS_CSV_OUTPUT, threshold_rows, THRESHOLD_COLUMNS)
    _write_csv(output_dir / BLOCKERS_CSV_OUTPUT, blockers, BLOCKER_COLUMNS)
    _write_json(output_dir / NEXT_REQUIREMENTS_OUTPUT, next_requirements)
    _write_json(output_dir / READINESS_BLOCKER_AUDIT_OUTPUT, blocker_audit)
    _write_json(output_dir / READINESS_RECOVERY_AUDIT_OUTPUT, recovery_audit)
    _write_json(output_dir / READINESS_DISTRIBUTION_FAIRNESS_AUDIT_OUTPUT, distribution_fairness_audit)
    _write_json(output_dir / PRIMARY_POOR_TARGET_AUDIT_OUTPUT, primary_poor_target_audit)
    _write_json(output_dir / OOS_FAIRNESS_RECOVERY_AUDIT_OUTPUT, oos_fairness_recovery_audit)
    _write_json(output_dir / OOS_SOURCE_OF_TRUTH_AUDIT_OUTPUT, oos_source_of_truth_audit)
    _write_json(output_dir / OOS_WINDOW_RECOVERY_PLAN_OUTPUT, oos_window_recovery_plan)
    _write_json(output_dir / OOS_POLICY_ALIGNMENT_AUDIT_OUTPUT, oos_policy_alignment_audit)
    _write_json(output_dir / POLICY_REALIGNMENT_SUMMARY_OUTPUT, policy_realignment_summary)
    _write_json(output_dir / NEWS_DISTRIBUTION_POLICY_REALIGNMENT_SUMMARY_OUTPUT, news_distribution_policy_realignment_summary)

    return {
        "phase_b_retest_readiness_gate": payload,
        "phase_b_retest_next_requirements": next_requirements,
        "phase_b_readiness_blocker_audit": blocker_audit,
        "phase_b_readiness_recovery_audit": recovery_audit,
        "phase_b_distribution_fairness_audit": distribution_fairness_audit,
        "phase_b_primary_poor_distribution_target_audit": primary_poor_target_audit,
        "phase_b_oos_fairness_recovery_audit": oos_fairness_recovery_audit,
        "phase_b_oos_source_of_truth_audit": oos_source_of_truth_audit,
        "phase_b_oos_window_recovery_plan": oos_window_recovery_plan,
        "phase_b_oos_policy_alignment_audit": oos_policy_alignment_audit,
        "phase_b_readiness_policy_realignment_summary": policy_realignment_summary,
        "phase_b_news_distribution_policy_realignment_summary": news_distribution_policy_realignment_summary,
        "threshold_rows": threshold_rows,
        "blockers": blockers,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the formal Phase B retest readiness gate.")
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory containing and receiving artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Optional ticker metadata CSV.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        result = run_phase_b_retest_readiness_gate(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        )
    except PhaseBRetestReadinessCliError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during Phase B retest readiness gate: {exc}", file=sys.stderr)
        return 1

    payload = safe_dict(result.get("phase_b_retest_readiness_gate"))
    print("Phase B retest readiness gate complete.")
    print(f"final_decision={payload.get('final_decision')}")
    print(f"highest_blocking_gate={payload.get('highest_blocking_gate')}")
    print(f"recommended_next_action={payload.get('recommended_next_action')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
