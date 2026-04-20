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

TRACKED_JSON_ARTIFACTS = [
    ("phase_b_data_extension_audit", "phase_b_data_extension_audit.json"),
    ("framework_redesign_scope", "framework_redesign_scope.json"),
    ("universe_reconstruction_precheck", "universe_reconstruction_precheck.json"),
    ("phase_b_final_closeout", "phase_b_final_closeout.json"),
    ("project_after_phase_b_decision", "project_after_phase_b_decision.json"),
    ("baseline_v9_segment_oos_summary", "baseline_v9_segment_oos_summary.json"),
    ("baseline_v9_segment_oos_go_no_go", "baseline_v9_segment_oos_go_no_go.json"),
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
        threshold_rows, "history_gate", "additional_bars_from_v9_baseline", ">=", 63, max(0, min_history_rows - v9_min_history),
        max(0, min_history_rows - v9_min_history) >= 63, "ticker_metadata/data + v9 methodology", "Additional bars beyond v9 baseline minimum.", "high"
    )
    _append_threshold(
        threshold_rows, "history_gate", "usable_oos_windows_per_ticker", ">=", 6,
        _safe_int(safe_dict(audit.get("history_length_assessment")).get("current_min_usable_oos_windows"), primary_usable_windows),
        _safe_int(safe_dict(audit.get("history_length_assessment")).get("current_min_usable_oos_windows"), primary_usable_windows) >= 6,
        "phase_b_data_extension_audit.json", "Minimum usable OOS windows across tickers.", "high"
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
        threshold_rows, "news_distribution_gate", "median_news_density_pct", ">=", 5.0,
        median_news_density, median_news_density >= 5.0, "ticker_metadata/data", "Median aligned news density across current universe.", "high"
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
        threshold_rows, "oos_fairness_gate", "primary_segment_usable_oos_windows", ">=", 6,
        primary_usable_windows, primary_usable_windows >= 6, "phase_b_data_extension_audit.json + segmentation", "Primary segment minimum usable windows.", "high"
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
    }
    return threshold_rows, context


def _rank_blockers(threshold_rows: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    reasons = {
        "history_gate": "History minimum, additional bars, dan OOS window per ticker belum cukup.",
        "universe_coverage_gate": "Coverage ticker yang benar-benar siap retest masih kurang merata.",
        "news_distribution_gate": "Distribusi news/sample masih terlalu tipis atau timpang untuk segment utama.",
        "oos_fairness_gate": "OOS support masih kecil atau terlalu terkonsentrasi pada ticker/fold tertentu.",
        "framework_governance_gate": "Framework redesign atau policy retest belum difinalkan.",
        "roadmap_discipline_gate": "Roadmap discipline berubah dari status closeout yang sudah ditetapkan.",
    }
    requirements = {
        "history_gate": "Perpanjang history sampai minimum 120 bar dan 6 usable OOS windows per ticker.",
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

    _write_json(output_dir / READINESS_JSON_OUTPUT, payload)
    _write_text(output_dir / READINESS_TEXT_OUTPUT, _build_text_output(payload))
    _write_csv(output_dir / THRESHOLDS_CSV_OUTPUT, threshold_rows, THRESHOLD_COLUMNS)
    _write_csv(output_dir / BLOCKERS_CSV_OUTPUT, blockers, BLOCKER_COLUMNS)
    _write_json(output_dir / NEXT_REQUIREMENTS_OUTPUT, next_requirements)

    return {
        "phase_b_retest_readiness_gate": payload,
        "phase_b_retest_next_requirements": next_requirements,
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
