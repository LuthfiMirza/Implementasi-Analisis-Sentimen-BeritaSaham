"""Build an execution-layer data extension plan after the retest readiness gate."""

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


EXECUTION_PLAN_OUTPUT = "phase_b_data_extension_execution_plan.json"
EXECUTION_PLAN_TEXT_OUTPUT = "phase_b_data_extension_execution_plan.txt"
PRIORITY_TICKERS_OUTPUT = "phase_b_data_extension_priority_tickers.csv"
PRIORITY_SEGMENTS_OUTPUT = "phase_b_data_extension_priority_segments.csv"
PROGRESS_TRACKER_OUTPUT = "phase_b_data_extension_progress_tracker.csv"
RECHECK_TRIGGER_OUTPUT = "phase_b_recheck_trigger.json"

TRACKED_JSON_ARTIFACTS = [
    ("phase_b_retest_readiness_gate", "phase_b_retest_readiness_gate.json"),
    ("phase_b_retest_next_requirements", "phase_b_retest_next_requirements.json"),
    ("phase_b_data_extension_audit", "phase_b_data_extension_audit.json"),
    ("framework_redesign_scope", "framework_redesign_scope.json"),
    ("universe_reconstruction_precheck", "universe_reconstruction_precheck.json"),
    ("phase_b_final_closeout", "phase_b_final_closeout.json"),
    ("project_after_phase_b_decision", "project_after_phase_b_decision.json"),
    ("baseline_v9_segment_oos_summary", "baseline_v9_segment_oos_summary.json"),
    ("baseline_v9_segment_oos_go_no_go", "baseline_v9_segment_oos_go_no_go.json"),
]

TARGET_HISTORY_BARS = 120
TARGET_ADDITIONAL_BARS = 63
TARGET_USABLE_OOS_WINDOWS = 6
TARGET_PRIMARY_TOTAL_ARTICLES = 18
TARGET_PRIMARY_ARTICLE_DAYS_MEDIAN = 4.0
TARGET_PRIMARY_TOTAL_OOS_TRADES = 18
TARGET_SINGLE_FOLD_TRADE_SHARE_MAX = 0.50
TARGET_COVERAGE_READY_RATIO = 0.80
BATCH_BAR_STEP = 21

TICKER_COLUMNS = [
    "priority_rank",
    "ticker",
    "execution_wave",
    "is_primary_segment",
    "safe_segment_overlap_count",
    "safe_segments",
    "history_rows_current",
    "bars_needed_to_120",
    "usable_oos_windows_current",
    "oos_windows_needed_to_6",
    "news_count_total_current",
    "article_days_current",
    "article_days_needed_to_4",
    "primary_oos_trades_current",
    "ticker_trade_share_primary",
    "execution_priority_score",
    "execution_reason",
]

SEGMENT_COLUMNS = [
    "priority_rank",
    "segment_name",
    "segment_role",
    "ticker_count",
    "overlap_with_primary_tickers",
    "history_rows_min",
    "bars_needed_to_120",
    "current_articles_total",
    "target_articles_total",
    "current_article_days_median",
    "target_article_days_median",
    "execution_wave",
    "execution_priority_score",
    "execution_reason",
]

PROGRESS_COLUMNS = [
    "tracker_id",
    "tracker_scope",
    "metric_name",
    "unit",
    "current_value",
    "target_value",
    "gap_to_target",
    "progress_pct",
    "batch_1_target",
    "batch_2_target",
    "batch_3_target",
    "status",
    "recheck_blocking",
    "note",
]


class PhaseBDataExtensionExecutionPlanCliError(ValueError):
    """Friendly CLI error for the data extension execution plan."""


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
        if "sentiment_days_with_articles" in metadata_df.columns and "article_days" not in metadata_df.columns:
            metadata_df["article_days"] = metadata_df["sentiment_days_with_articles"]
    else:
        rows: List[Dict[str, object]] = []
        for path in sorted(Path(data_dir).glob("*.csv")):
            if path.name == "ticker_metadata.csv":
                continue
            try:
                frame = pd.read_csv(path)
            except Exception as exc:
                warnings.append(f"Failed to read price file {path.name}: {exc}.")
                continue
            if frame.empty:
                continue
            news_series = pd.to_numeric(frame.get("sentiment_news_count_1d"), errors="coerce").fillna(0.0)
            rows.append(
                {
                    "ticker": path.stem.upper(),
                    "history_rows": int(len(frame)),
                    "news_count_total": int(float(news_series.sum())),
                    "article_days": int((news_series > 0).sum()),
                }
            )
        metadata_df = pd.DataFrame(rows)
        warnings.append("ticker_metadata.csv unavailable or unusable; execution plan derived ticker metrics directly from price CSV files.")

    if not metadata_df.empty:
        metadata_df["history_rows"] = pd.to_numeric(metadata_df.get("history_rows"), errors="coerce").fillna(0).astype(int)
        metadata_df["news_count_total"] = pd.to_numeric(metadata_df.get("news_count_total"), errors="coerce").fillna(0).astype(int)
        metadata_df["article_days"] = pd.to_numeric(metadata_df.get("article_days"), errors="coerce").fillna(0).astype(int)
        metadata_df["news_density_pct"] = [
            round((100.0 * article_days / history_rows), 4) if history_rows > 0 else 0.0
            for article_days, history_rows in zip(
                list(metadata_df["article_days"]),
                list(metadata_df["history_rows"]),
            )
        ]
    return metadata_df, dedupe(warnings)


def _load_segmentation(output_dir: Path) -> Tuple[pd.DataFrame, List[str]]:
    path = Path(output_dir) / "baseline_v6_universe_segmentation.csv"
    if not path.exists():
        return pd.DataFrame(), ["baseline_v6_universe_segmentation.csv missing; segment priority is conservative."]
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return pd.DataFrame(), [f"Failed to read segmentation file {path}: {exc}."]
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.upper()
    if "rows" in df.columns and "history_rows" not in df.columns:
        df["history_rows"] = df["rows"]
    if "article_count_total" in df.columns and "news_count_total" not in df.columns:
        df["news_count_total"] = df["article_count_total"]
    if "article_days" not in df.columns:
        df["article_days"] = 0
    return df, []


def _load_v9_results(output_dir: Path) -> Tuple[pd.DataFrame, List[str]]:
    path = Path(output_dir) / "baseline_v9_segment_oos_results.csv"
    if not path.exists():
        return pd.DataFrame(), ["baseline_v9_segment_oos_results.csv missing; trade-share planning is conservative."]
    try:
        return pd.read_csv(path), []
    except Exception as exc:
        return pd.DataFrame(), [f"Failed to read baseline_v9_segment_oos_results.csv: {exc}."]


def _parse_segment_spec(spec: str) -> Tuple[str, str]:
    raw = str(spec).strip()
    if "=" not in raw:
        return "", ""
    field, value = raw.split("=", 1)
    return field.strip(), value.strip()


def _usable_oos_windows(history_rows: int, warmup_bars: int, fold_size_bars: int) -> int:
    if fold_size_bars <= 0 or history_rows <= warmup_bars:
        return 0
    return max(0, int(math.floor((history_rows - warmup_bars) / float(fold_size_bars))))


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


def _primary_segment(artifacts: Dict[str, Dict[str, object]]) -> str:
    gate = safe_dict(artifacts.get("phase_b_retest_readiness_gate"))
    if _safe_str(gate.get("primary_segment")):
        return _safe_str(gate.get("primary_segment"))
    v9 = safe_dict(artifacts.get("baseline_v9_segment_oos_go_no_go"))
    return _safe_str(v9.get("primary_segment"))


def _safe_segments(artifacts: Dict[str, Dict[str, object]], output_dir: Path) -> List[str]:
    gate = safe_dict(artifacts.get("phase_b_retest_readiness_gate"))
    values = [str(item) for item in list(gate.get("safe_segments_evaluated") or [])]
    if values:
        return dedupe(values)
    governance, _, available = _load_optional_json(output_dir=output_dir, filename="baseline_v6_next_experiment_governance.json")
    if available:
        return dedupe([str(item) for item in list(governance.get("segments_safe_to_test_next") or [])])
    return []


def _methodology(artifacts: Dict[str, Dict[str, object]]) -> Dict[str, int]:
    summary = safe_dict(artifacts.get("baseline_v9_segment_oos_summary"))
    meta = safe_dict(summary.get("methodology"))
    return {
        "warmup_bars": _safe_int(meta.get("warmup_bars"), 21),
        "fold_size_bars": _safe_int(meta.get("fold_size_bars"), 12),
    }


def _primary_trade_lookup(v9_results: pd.DataFrame, primary_segment: str) -> Tuple[Dict[str, int], Dict[str, float], float]:
    if v9_results.empty:
        return {}, {}, 0.0
    ticker_rows = v9_results.loc[
        v9_results["row_type"].astype(str).eq("ticker_oos_summary")
        & v9_results["tested_segment"].astype(str).eq(primary_segment)
    ].copy()
    trades = {
        str(row["ticker"]).upper(): _safe_int(row.get("candidate_total_trades"))
        for _, row in ticker_rows.iterrows()
    }
    total = sum(trades.values())
    shares = {
        ticker: round((count / total), 4) if total > 0 else 0.0
        for ticker, count in trades.items()
    }
    return trades, shares, float(total)


def _current_single_fold_trade_share(v9_results: pd.DataFrame, primary_segment: str) -> float:
    if v9_results.empty:
        return 1.0
    fold_rows = v9_results.loc[
        v9_results["row_type"].astype(str).eq("segment_fold")
        & v9_results["tested_segment"].astype(str).eq(primary_segment)
    ].copy()
    if fold_rows.empty:
        return 1.0
    counts = pd.to_numeric(fold_rows.get("candidate_total_trades"), errors="coerce").fillna(0).astype(int)
    total = int(counts.sum())
    return round((float(counts.max()) / total), 4) if total > 0 else 1.0


def _merge_ticker_context(
    metadata_df: pd.DataFrame,
    segmentation_df: pd.DataFrame,
    primary_segment: str,
    safe_segments: Sequence[str],
    methodology: Dict[str, int],
    primary_trades: Dict[str, int],
    primary_trade_shares: Dict[str, float],
) -> pd.DataFrame:
    working = metadata_df.copy() if not metadata_df.empty else pd.DataFrame(columns=["ticker"])
    if not segmentation_df.empty:
        segment_columns = [col for col in segmentation_df.columns if col != "ticker"]
        if working.empty:
            working = segmentation_df.copy()
        else:
            working = working.merge(segmentation_df[["ticker", *segment_columns]], on="ticker", how="left")

    if working.empty:
        return working

    for column in ["history_rows", "news_count_total", "article_days"]:
        if column not in working.columns:
            left = f"{column}_x"
            right = f"{column}_y"
            if left in working.columns or right in working.columns:
                left_values = pd.to_numeric(working[left], errors="coerce") if left in working.columns else pd.Series([None] * len(working))
                right_values = pd.to_numeric(working[right], errors="coerce") if right in working.columns else pd.Series([None] * len(working))
                working[column] = left_values.fillna(right_values)

    working["ticker"] = working["ticker"].astype(str).str.upper()
    working["history_rows"] = pd.to_numeric(working.get("history_rows"), errors="coerce").fillna(0).astype(int)
    working["news_count_total"] = pd.to_numeric(working.get("news_count_total"), errors="coerce").fillna(0).astype(int)
    working["article_days"] = pd.to_numeric(working.get("article_days"), errors="coerce").fillna(0).astype(int)
    working["usable_oos_windows"] = [
        _usable_oos_windows(value, methodology["warmup_bars"], methodology["fold_size_bars"])
        for value in list(working["history_rows"])
    ]
    primary_field, primary_value = _parse_segment_spec(primary_segment)
    working["is_primary_segment"] = working[primary_field].astype(str).eq(primary_value) if primary_field and primary_field in working.columns else False
    safe_tokens: List[List[str]] = []
    for _, row in working.iterrows():
        matched: List[str] = []
        for segment in safe_segments:
            field, value = _parse_segment_spec(segment)
            if field and field in working.columns and _safe_str(row.get(field)) == value:
                matched.append(segment)
        safe_tokens.append(dedupe(matched))
    working["safe_segments"] = safe_tokens
    working["safe_segment_overlap_count"] = [len(item) for item in safe_tokens]
    working["bars_needed_to_120"] = [max(0, TARGET_HISTORY_BARS - value) for value in list(working["history_rows"])]
    working["oos_windows_needed_to_6"] = [max(0, TARGET_USABLE_OOS_WINDOWS - value) for value in list(working["usable_oos_windows"])]
    working["article_days_needed_to_4"] = [
        max(0, int(math.ceil(TARGET_PRIMARY_ARTICLE_DAYS_MEDIAN - value))) if bool(is_primary) else 0
        for value, is_primary in zip(list(working["article_days"]), list(working["is_primary_segment"]))
    ]
    working["primary_oos_trades_current"] = [primary_trades.get(str(ticker).upper(), 0) for ticker in list(working["ticker"])]
    working["ticker_trade_share_primary"] = [primary_trade_shares.get(str(ticker).upper(), 0.0) for ticker in list(working["ticker"])]
    return working


def _ticker_execution_wave(row: Dict[str, object]) -> str:
    is_primary = _safe_bool(row.get("is_primary_segment"))
    trades = _safe_int(row.get("primary_oos_trades_current"))
    if is_primary and trades > 0:
        return "wave_1_primary_active"
    if is_primary:
        return "wave_1_primary_coverage"
    if _safe_int(row.get("safe_segment_overlap_count")) > 0:
        return "wave_2_supporting_overlap"
    return "wave_3_background_universe"


def _ticker_priority_score(row: Dict[str, object]) -> float:
    is_primary = _safe_bool(row.get("is_primary_segment"))
    trades = _safe_int(row.get("primary_oos_trades_current"))
    article_gap = _safe_int(row.get("article_days_needed_to_4"))
    safe_overlap = _safe_int(row.get("safe_segment_overlap_count"))
    zero_article = _safe_int(row.get("article_days")) == 0
    score = 0.0
    score += 80.0 if is_primary else 20.0 if safe_overlap > 0 else 0.0
    score += min(trades, 4) * 8.0
    score += safe_overlap * 3.0
    score += 6.0 if zero_article and is_primary else 0.0
    score -= article_gap * 2.5
    return round(score, 4)


def _ticker_execution_reason(row: Dict[str, object]) -> str:
    ticker = _safe_str(row.get("ticker"))
    is_primary = _safe_bool(row.get("is_primary_segment"))
    trades = _safe_int(row.get("primary_oos_trades_current"))
    article_gap = _safe_int(row.get("article_days_needed_to_4"))
    if is_primary and trades > 0 and article_gap <= 2:
        return f"{ticker} berada di primary segment, sudah aktif di OOS, dan butuh penutupan article-day gap yang relatif kecil."
    if is_primary and article_gap > 0:
        return f"{ticker} berada di primary segment dan masih menahan median article days primary di bawah target."
    if _safe_int(row.get("safe_segment_overlap_count")) > 0:
        return f"{ticker} membantu coverage segment aman dan tetap relevan untuk kesiapan universe retest."
    return f"{ticker} bukan pengungkit pertama untuk fairness primary, tetapi tetap perlu ikut tertutup di history gate."


def _build_priority_tickers(working: pd.DataFrame) -> List[Dict[str, object]]:
    if working.empty:
        return []
    rows: List[Dict[str, object]] = []
    for _, record in working.iterrows():
        row = record.to_dict()
        score = _ticker_priority_score(row)
        wave = _ticker_execution_wave(row)
        rows.append(
            {
                "ticker": _safe_str(row.get("ticker")),
                "execution_wave": wave,
                "is_primary_segment": bool(row.get("is_primary_segment")),
                "safe_segment_overlap_count": _safe_int(row.get("safe_segment_overlap_count")),
                "safe_segments": "|".join(list(row.get("safe_segments") or [])),
                "history_rows_current": _safe_int(row.get("history_rows")),
                "bars_needed_to_120": _safe_int(row.get("bars_needed_to_120")),
                "usable_oos_windows_current": _safe_int(row.get("usable_oos_windows")),
                "oos_windows_needed_to_6": _safe_int(row.get("oos_windows_needed_to_6")),
                "news_count_total_current": _safe_int(row.get("news_count_total")),
                "article_days_current": _safe_int(row.get("article_days")),
                "article_days_needed_to_4": _safe_int(row.get("article_days_needed_to_4")),
                "primary_oos_trades_current": _safe_int(row.get("primary_oos_trades_current")),
                "ticker_trade_share_primary": round(_safe_float(row.get("ticker_trade_share_primary")), 4),
                "execution_priority_score": score,
                "execution_reason": _ticker_execution_reason(row),
            }
        )
    rows.sort(
        key=lambda item: (
            {"wave_1_primary_active": 0, "wave_1_primary_coverage": 1, "wave_2_supporting_overlap": 2, "wave_3_background_universe": 3}[item["execution_wave"]],
            -_safe_float(item["execution_priority_score"]),
            _safe_int(item["article_days_needed_to_4"]),
            item["ticker"],
        )
    )
    for index, item in enumerate(rows, start=1):
        item["priority_rank"] = index
    return rows


def _segment_priority_row(
    segment_name: str,
    segment_role: str,
    tickers: Sequence[str],
    working: pd.DataFrame,
    primary_tickers: Sequence[str],
) -> Dict[str, object]:
    subset = working.loc[working["ticker"].astype(str).isin(list(tickers))].copy() if not working.empty else pd.DataFrame()
    overlap = len(set(str(item).upper() for item in tickers) & set(str(item).upper() for item in primary_tickers))
    article_total = int(pd.to_numeric(subset.get("news_count_total"), errors="coerce").fillna(0).sum()) if not subset.empty else 0
    median_days = round(float(pd.to_numeric(subset.get("article_days"), errors="coerce").fillna(0).median()), 4) if not subset.empty else 0.0
    min_history = int(pd.to_numeric(subset.get("history_rows"), errors="coerce").fillna(0).min()) if not subset.empty else 0
    bars_needed = max(0, TARGET_HISTORY_BARS - min_history)

    target_articles = TARGET_PRIMARY_TOTAL_ARTICLES if segment_role == "primary" else ""
    target_days = TARGET_PRIMARY_ARTICLE_DAYS_MEDIAN if segment_role == "primary" else ""
    if segment_role == "primary":
        score = 100.0 + overlap * 5.0 + max(0.0, TARGET_PRIMARY_ARTICLE_DAYS_MEDIAN - median_days) * 4.0
        wave = "wave_1_primary"
        reason = "Primary segment memegang blocker langsung pada history, news distribution, dan OOS fairness."
    else:
        score = overlap * 12.0 + max(0.0, 3.0 - median_days) * 3.0
        wave = "wave_2_supporting_overlap" if overlap > 0 else "wave_3_secondary"
        reason = (
            "Segment aman ini overlap dengan ticker primary dan bisa membantu pemerataan coverage."
            if overlap > 0
            else "Segment aman ini tetap dipantau, tetapi bukan pengungkit pertama untuk membuka retest."
        )

    return {
        "segment_name": segment_name,
        "segment_role": segment_role,
        "ticker_count": len(list(tickers)),
        "overlap_with_primary_tickers": overlap,
        "history_rows_min": min_history,
        "bars_needed_to_120": bars_needed,
        "current_articles_total": article_total,
        "target_articles_total": target_articles,
        "current_article_days_median": median_days,
        "target_article_days_median": target_days,
        "execution_wave": wave,
        "execution_priority_score": round(score, 4),
        "execution_reason": reason,
    }


def _build_priority_segments(
    working: pd.DataFrame,
    primary_segment: str,
    safe_segments: Sequence[str],
) -> List[Dict[str, object]]:
    if working.empty:
        return []
    rows: List[Dict[str, object]] = []
    primary_field, primary_value = _parse_segment_spec(primary_segment)
    primary_tickers = list(
        working.loc[working["is_primary_segment"].astype(bool), "ticker"].astype(str)
    )
    rows.append(
        _segment_priority_row(
            segment_name=primary_segment,
            segment_role="primary",
            tickers=primary_tickers,
            working=working,
            primary_tickers=primary_tickers,
        )
    )
    for segment in safe_segments:
        if segment == primary_segment:
            continue
        field, value = _parse_segment_spec(segment)
        if not field or field not in working.columns:
            tickers: List[str] = []
        else:
            tickers = list(working.loc[working[field].astype(str).eq(value), "ticker"].astype(str))
        rows.append(
            _segment_priority_row(
                segment_name=segment,
                segment_role="supporting",
                tickers=tickers,
                working=working,
                primary_tickers=primary_tickers,
            )
        )
    rows.sort(key=lambda item: ({"wave_1_primary": 0, "wave_2_supporting_overlap": 1, "wave_3_secondary": 2}[item["execution_wave"]], -_safe_float(item["execution_priority_score"]), item["segment_name"]))
    for index, item in enumerate(rows, start=1):
        item["priority_rank"] = index
    return rows


def _progress_pct(current: float, target: float, operator: str = ">=") -> float:
    if target <= 0:
        return 100.0
    if operator == ">=":
        return round(min(100.0, max(0.0, (current / target) * 100.0)), 2)
    if current <= 0:
        return 0.0
    return round(min(100.0, max(0.0, (target / current) * 100.0)), 2)


def _tracker_row(
    tracker_id: str,
    tracker_scope: str,
    metric_name: str,
    unit: str,
    current_value: float,
    target_value: float,
    batch_1_target: float,
    batch_2_target: float,
    batch_3_target: float,
    operator: str,
    note: str,
    recheck_blocking: bool = True,
) -> Dict[str, object]:
    if operator == ">=":
        status = "done" if current_value >= target_value else "pending"
        gap = round(max(0.0, target_value - current_value), 4)
    else:
        status = "done" if current_value <= target_value else "pending"
        gap = round(max(0.0, current_value - target_value), 4)
    return {
        "tracker_id": tracker_id,
        "tracker_scope": tracker_scope,
        "metric_name": metric_name,
        "unit": unit,
        "current_value": current_value,
        "target_value": target_value,
        "gap_to_target": gap,
        "progress_pct": _progress_pct(current_value, target_value, operator=operator),
        "batch_1_target": batch_1_target,
        "batch_2_target": batch_2_target,
        "batch_3_target": batch_3_target,
        "status": status,
        "recheck_blocking": recheck_blocking,
        "note": note,
    }


def _build_progress_tracker(
    working: pd.DataFrame,
    artifacts: Dict[str, Dict[str, object]],
    v9_results: pd.DataFrame,
    primary_segment: str,
) -> List[Dict[str, object]]:
    gate = safe_dict(artifacts.get("phase_b_retest_readiness_gate"))
    audit = safe_dict(artifacts.get("phase_b_data_extension_audit"))
    history_assessment = safe_dict(audit.get("history_length_assessment"))
    news_assessment = safe_dict(audit.get("news_distribution_assessment"))
    v9_go = safe_dict(artifacts.get("baseline_v9_segment_oos_go_no_go"))

    if working.empty:
        current_history = 0.0
        coverage_ready_ratio = 0.0
        primary_total_articles = 0.0
        primary_article_days_median = 0.0
    else:
        current_history = float(pd.to_numeric(working["history_rows"], errors="coerce").fillna(0).min())
        current_additional = max(0.0, current_history - 57.0)
        coverage_mask = (
            pd.to_numeric(working["history_rows"], errors="coerce").fillna(0).ge(TARGET_HISTORY_BARS)
            & pd.Series([_usable_oos_windows(_safe_int(value), 21, 12) for value in list(working["history_rows"])]).ge(TARGET_USABLE_OOS_WINDOWS)
        )
        coverage_ready_ratio = round(float(coverage_mask.mean()), 4) if len(working) else 0.0
        primary_subset = working.loc[working["is_primary_segment"].astype(bool)].copy()
        primary_total_articles = float(pd.to_numeric(primary_subset.get("news_count_total"), errors="coerce").fillna(0).sum()) if not primary_subset.empty else 0.0
        primary_article_days_median = round(float(pd.to_numeric(primary_subset.get("article_days"), errors="coerce").fillna(0).median()), 4) if not primary_subset.empty else 0.0

    current_additional = max(0.0, current_history - 57.0)
    derived_windows = _usable_oos_windows(int(current_history), 21, 12)
    # Audit artifacts can lag after backfill; do not let an older cached window count
    # override a higher window count that is already visible in the current snapshot.
    current_windows = float(
        max(
            _safe_int(history_assessment.get("current_min_usable_oos_windows"), derived_windows),
            derived_windows,
        )
    )
    current_trades = float(_safe_int(v9_go.get("primary_total_trades_sum")))
    current_fold_share = float(_current_single_fold_trade_share(v9_results=v9_results, primary_segment=primary_segment))

    rows = [
        _tracker_row(
            "history_min_rows",
            "global",
            "min_history_bars_per_ticker",
            "bars",
            current_history,
            TARGET_HISTORY_BARS,
            78.0,
            99.0,
            120.0,
            ">=",
            "History minimum adalah blocker tertinggi dan harus ditutup di seluruh universe.",
        ),
        _tracker_row(
            "history_added_rows",
            "global",
            "additional_bars_from_v9_baseline",
            "bars",
            current_additional,
            TARGET_ADDITIONAL_BARS,
            21.0,
            42.0,
            63.0,
            ">=",
            "Tambahan bar dihitung relatif terhadap baseline v9 sebesar 57 bar.",
        ),
        _tracker_row(
            "history_oos_windows",
            "global",
            "usable_oos_windows_per_ticker",
            "windows",
            current_windows,
            TARGET_USABLE_OOS_WINDOWS,
            4.0,
            6.0,
            8.0,
            ">=",
            "Usable OOS windows naik seiring extension history.",
        ),
        _tracker_row(
            "coverage_ready_ratio",
            "global",
            "coverage_ready_ticker_ratio",
            "ratio",
            coverage_ready_ratio,
            TARGET_COVERAGE_READY_RATIO,
            0.0,
            0.0,
            1.0,
            ">=",
            "Coverage-ready ratio praktis baru akan bergerak penuh saat history gate tertutup di seluruh ticker.",
        ),
        _tracker_row(
            "primary_articles_total",
            "primary_segment",
            "primary_segment_total_articles",
            "articles",
            primary_total_articles,
            TARGET_PRIMARY_TOTAL_ARTICLES,
            13.0,
            14.0,
            18.0,
            ">=",
            "Target interim dibuat untuk mengecek apakah article supply primary segment mulai bergerak material.",
        ),
        _tracker_row(
            "primary_article_days_median",
            "primary_segment",
            "primary_segment_article_days_median",
            "days",
            primary_article_days_median,
            TARGET_PRIMARY_ARTICLE_DAYS_MEDIAN,
            3.0,
            3.0,
            4.0,
            ">=",
            "Median article days primary harus naik sebelum retest gate diulang.",
        ),
        _tracker_row(
            "primary_total_oos_trades",
            "derived_oos",
            "total_oos_trades_primary_segment",
            "trades",
            current_trades,
            TARGET_PRIMARY_TOTAL_OOS_TRADES,
            13.0,
            15.0,
            18.0,
            ">=",
            "Ini metric turunan; nilainya harus diukur ulang setelah batch data baru masuk.",
        ),
        _tracker_row(
            "primary_single_fold_trade_share",
            "derived_oos",
            "no_single_fold_trade_share",
            "ratio",
            current_fold_share,
            TARGET_SINGLE_FOLD_TRADE_SHARE_MAX,
            0.60,
            0.55,
            0.50,
            "<=",
            "Konsentrasi fold hanya bisa dievaluasi ulang setelah OOS rerun pada data yang sudah diperpanjang.",
        ),
    ]
    return rows


def _minimum_progress_needed_before_recheck() -> Dict[str, object]:
    return {
        "checkpoint_name": "batch_2_material_progress_checkpoint",
        "required_metrics": [
            {"metric": "min_history_bars_per_ticker", "operator": ">=", "value": 99},
            {"metric": "additional_bars_from_v9_baseline", "operator": ">=", "value": 42},
            {"metric": "usable_oos_windows_per_ticker", "operator": ">=", "value": 6},
            {"metric": "primary_segment_total_articles", "operator": ">=", "value": 14},
            {"metric": "primary_segment_article_days_median", "operator": ">=", "value": 3},
            {"metric": "metadata_and_segmentation_refreshed", "operator": "==", "value": True},
        ],
        "reason": (
            "Recheck sebelum checkpoint batch-2 terlalu dini karena blocker ranking belum berubah secara material. "
            "Checkpoint ini cukup besar untuk menguji apakah history dan distribusi sample benar-benar membaik."
        ),
    }


def _recheck_allowed(progress_tracker: Sequence[Dict[str, object]]) -> bool:
    lookup = {str(row.get("metric_name")): row for row in progress_tracker}
    return (
        _safe_float(safe_dict(lookup.get("min_history_bars_per_ticker")).get("current_value")) >= 99.0
        and _safe_float(safe_dict(lookup.get("additional_bars_from_v9_baseline")).get("current_value")) >= 42.0
        and _safe_float(safe_dict(lookup.get("usable_oos_windows_per_ticker")).get("current_value")) >= 6.0
        and _safe_float(safe_dict(lookup.get("primary_segment_total_articles")).get("current_value")) >= 14.0
        and _safe_float(safe_dict(lookup.get("primary_segment_article_days_median")).get("current_value")) >= 3.0
    )


def _build_recheck_trigger(
    progress_tracker: Sequence[Dict[str, object]],
    highest_priority_execution_target: str,
) -> Dict[str, object]:
    allowed = _recheck_allowed(progress_tracker)
    return {
        "minimum_progress_needed_before_recheck": _minimum_progress_needed_before_recheck(),
        "recheck_readiness_gate_allowed": allowed,
        "current_status": "allowed" if allowed else "not_allowed_yet",
        "highest_priority_execution_target": highest_priority_execution_target,
        "not_allowed_reason": (
            "Retest gate tidak boleh dijalankan ulang sebelum threshold progress minimum tercapai."
            if not allowed
            else ""
        ),
        "recommended_recheck_moment": (
            "Setelah seluruh ticker mencapai minimal 99 bar, primary articles minimal 14, median article days primary minimal 3, dan artifact metadata/segmentation diperbarui."
        ),
    }


def _build_text_output(payload: Dict[str, object]) -> List[str]:
    return [
        "Phase B Data Extension Execution Plan",
        f"- execution_plan_ready={payload.get('execution_plan_ready')}",
        f"- highest_priority_execution_target={payload.get('highest_priority_execution_target')}",
        f"- recommended_next_action={payload.get('recommended_next_action')}",
        f"- recheck_readiness_gate_allowed={payload.get('recheck_readiness_gate_allowed')}",
        f"- decisive_statement={payload.get('decisive_statement')}",
        "",
        "Priority tickers:",
        *[f"- {item}" for item in list(payload.get("priority_tickers") or [])],
        "",
        "Priority segments:",
        *[f"- {item}" for item in list(payload.get("priority_segments") or [])],
    ]


def run_phase_b_data_extension_execution_plan(
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise PhaseBDataExtensionExecutionPlanCliError(f"Data directory not found: {data_dir}")

    artifacts, artifact_availability, artifact_warnings = _load_artifacts(output_dir=output_dir)
    metadata_df, metadata_warnings = _load_metadata_or_prices(data_dir=data_dir, metadata_file=metadata_file)
    segmentation_df, segmentation_warnings = _load_segmentation(output_dir=output_dir)
    v9_results, v9_warnings = _load_v9_results(output_dir=output_dir)
    limitations = dedupe([*artifact_warnings, *metadata_warnings, *segmentation_warnings, *v9_warnings])

    primary_segment = _primary_segment(artifacts=artifacts)
    safe_segments = _safe_segments(artifacts=artifacts, output_dir=output_dir)
    methodology = _methodology(artifacts=artifacts)
    primary_trades, primary_trade_shares, _ = _primary_trade_lookup(v9_results=v9_results, primary_segment=primary_segment)
    working = _merge_ticker_context(
        metadata_df=metadata_df,
        segmentation_df=segmentation_df,
        primary_segment=primary_segment,
        safe_segments=safe_segments,
        methodology=methodology,
        primary_trades=primary_trades,
        primary_trade_shares=primary_trade_shares,
    )

    priority_ticker_rows = _build_priority_tickers(working=working)
    priority_segment_rows = _build_priority_segments(
        working=working,
        primary_segment=primary_segment,
        safe_segments=safe_segments,
    )
    progress_tracker = _build_progress_tracker(
        working=working,
        artifacts=artifacts,
        v9_results=v9_results,
        primary_segment=primary_segment,
    )

    top_tickers = [row["ticker"] for row in priority_ticker_rows[:5]]
    top_segments = [row["segment_name"] for row in priority_segment_rows[:4]]
    highest_priority_execution_target = "history_extension_all_tickers_with_primary_segment_article_day_recovery"
    recheck_trigger = _build_recheck_trigger(
        progress_tracker=progress_tracker,
        highest_priority_execution_target=highest_priority_execution_target,
    )

    execution_plan = {
        "generated_at": _now_iso(),
        "execution_plan_ready": True,
        "highest_priority_execution_target": highest_priority_execution_target,
        "priority_tickers": top_tickers,
        "priority_segments": top_segments,
        "minimum_progress_needed_before_recheck": recheck_trigger["minimum_progress_needed_before_recheck"],
        "recheck_readiness_gate_allowed": recheck_trigger["recheck_readiness_gate_allowed"],
        "recommended_next_action": "execute_history_extension_batch_1_then_raise_primary_segment_article_day_coverage_before_any_recheck",
        "execution_batches": [
            {
                "batch_id": "batch_1",
                "focus": "close_history_gap_first_and_start_primary_article_day_recovery",
                "targets": {
                    "min_history_bars_per_ticker": 78,
                    "additional_bars_from_v9_baseline": 21,
                    "usable_oos_windows_per_ticker": 4,
                    "primary_segment_total_articles": 13,
                    "primary_segment_article_days_median": 3,
                },
            },
            {
                "batch_id": "batch_2",
                "focus": "reach_material_progress_checkpoint_before_recheck",
                "targets": {
                    "min_history_bars_per_ticker": 99,
                    "additional_bars_from_v9_baseline": 42,
                    "usable_oos_windows_per_ticker": 6,
                    "primary_segment_total_articles": 14,
                    "primary_segment_article_days_median": 3,
                },
            },
            {
                "batch_id": "batch_3",
                "focus": "close_full_history_and_distribution_targets_then_prepare_gate_rerun",
                "targets": {
                    "min_history_bars_per_ticker": 120,
                    "additional_bars_from_v9_baseline": 63,
                    "usable_oos_windows_per_ticker": 8,
                    "primary_segment_total_articles": 18,
                    "primary_segment_article_days_median": 4,
                },
            },
        ],
        "decisive_statement": (
            "Langkah berikutnya adalah menutup gap history sebelum retest gate diperiksa ulang. "
            "News extension saja tidak cukup; progress minimum harus menutup history, article-day coverage, dan OOS sample fairness. "
            "Retest gate tidak boleh dijalankan ulang sebelum threshold progress minimum tercapai."
        ),
        "artifact_availability": artifact_availability,
        "limitations": limitations,
    }

    _write_json(output_dir / EXECUTION_PLAN_OUTPUT, execution_plan)
    _write_text(output_dir / EXECUTION_PLAN_TEXT_OUTPUT, _build_text_output(execution_plan))
    _write_csv(output_dir / PRIORITY_TICKERS_OUTPUT, priority_ticker_rows, TICKER_COLUMNS)
    _write_csv(output_dir / PRIORITY_SEGMENTS_OUTPUT, priority_segment_rows, SEGMENT_COLUMNS)
    _write_csv(output_dir / PROGRESS_TRACKER_OUTPUT, progress_tracker, PROGRESS_COLUMNS)
    _write_json(output_dir / RECHECK_TRIGGER_OUTPUT, recheck_trigger)

    return {
        "phase_b_data_extension_execution_plan": execution_plan,
        "phase_b_recheck_trigger": recheck_trigger,
        "priority_tickers": priority_ticker_rows,
        "priority_segments": priority_segment_rows,
        "progress_tracker": progress_tracker,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the Phase B data extension execution plan.")
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory containing and receiving artifacts.")
    parser.add_argument("--metadata-file", default="data/ticker_metadata.csv", help="Optional ticker metadata CSV.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        result = run_phase_b_data_extension_execution_plan(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        )
    except PhaseBDataExtensionExecutionPlanCliError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during data extension execution plan build: {exc}", file=sys.stderr)
        return 1

    payload = safe_dict(result.get("phase_b_data_extension_execution_plan"))
    print("Phase B data extension execution plan complete.")
    print(f"execution_plan_ready={payload.get('execution_plan_ready')}")
    print(f"highest_priority_execution_target={payload.get('highest_priority_execution_target')}")
    print(f"recheck_readiness_gate_allowed={payload.get('recheck_readiness_gate_allowed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
