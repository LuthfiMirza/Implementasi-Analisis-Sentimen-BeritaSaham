"""Audit Phase B data sufficiency and define evaluation-framework redesign scope."""

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


DATA_AUDIT_OUTPUT = "phase_b_data_extension_audit.json"
DATA_AUDIT_TEXT_OUTPUT = "phase_b_data_extension_audit.txt"
DATA_GAP_MATRIX_OUTPUT = "phase_b_data_gap_matrix.csv"
FRAMEWORK_SCOPE_OUTPUT = "framework_redesign_scope.json"
FRAMEWORK_SCOPE_TEXT_OUTPUT = "framework_redesign_scope.txt"
UNIVERSE_PRECHECK_OUTPUT = "universe_reconstruction_precheck.json"

MIN_HISTORY_ROWS_FOR_RETEST = 120
MIN_USABLE_OOS_WINDOWS = 6
MIN_SEGMENT_TICKER_COUNT = 6
MIN_MEDIAN_NEWS_DENSITY_PCT_IF_DAILY_LABEL_KEPT = 10.0
MIN_MEDIAN_ARTICLE_DAYS = 5
MIN_TOTAL_OOS_TRADES_FOR_STABILITY = 20

TRACKED_JSON_ARTIFACTS = [
    ("phase_b_final_closeout", "phase_b_final_closeout.json"),
    ("project_after_phase_b_decision", "project_after_phase_b_decision.json"),
    ("baseline_v6_next_experiment_governance", "baseline_v6_next_experiment_governance.json"),
    ("baseline_v9_segment_oos_go_no_go", "baseline_v9_segment_oos_go_no_go.json"),
    ("baseline_v9_segment_oos_summary", "baseline_v9_segment_oos_summary.json"),
    ("project_roadmap_status", "project_roadmap_status.json"),
]

MATRIX_COLUMNS = [
    "row_type",
    "subject",
    "ticker",
    "tested_segment",
    "segment_role",
    "history_rows",
    "usable_oos_windows",
    "news_count_total",
    "news_article_days",
    "news_density",
    "candidate_total_trades",
    "candidate_signal_count",
    "candidate_trade_sample_sign",
    "oos_support_strength",
    "data_gap_severity",
    "primary_gap_reason",
    "limitations",
]


class PhaseBDataExtensionAuditCliError(ValueError):
    """Friendly CLI error for Phase B data extension audit."""


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


def _load_optional_json(output_dir: Path, filename: str) -> Tuple[Dict[str, object], List[str], bool]:
    payload, warnings = read_json_object(Path(output_dir) / filename, filename)
    return safe_dict(payload), list(warnings), payload is not None


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_matrix(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATRIX_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in MATRIX_COLUMNS})


def _usable_oos_windows(history_rows: int, warmup_bars: int, fold_size_bars: int) -> int:
    if fold_size_bars <= 0 or history_rows <= warmup_bars:
        return 0
    return max(0, int(math.floor((history_rows - warmup_bars) / float(fold_size_bars))))


def _load_metadata_from_csv(metadata_file: Path) -> Tuple[pd.DataFrame, List[str]]:
    warnings: List[str] = []
    try:
        df = pd.read_csv(metadata_file)
    except Exception as exc:
        return pd.DataFrame(), [f"Failed to read metadata file {metadata_file}: {exc}."]

    if df.empty:
        warnings.append(f"Metadata file is empty: {metadata_file}.")
        return df, warnings

    rename_map = {
        "rows_1d": "history_rows",
        "date_start": "date_start",
        "date_end": "date_end",
        "sentiment_article_count_total": "news_count_total",
        "sentiment_days_with_articles": "news_article_days",
    }
    for source, target in rename_map.items():
        if source in df.columns and target not in df.columns:
            df[target] = df[source]
    if "ticker" not in df.columns:
        warnings.append(f"Metadata file missing ticker column: {metadata_file}.")
        return pd.DataFrame(), warnings

    df["ticker"] = df["ticker"].astype(str).str.upper()
    return df, warnings


def _summarize_price_csv(path: Path) -> Dict[str, object]:
    df = pd.read_csv(path)
    ticker = path.stem.upper()
    row_count = int(len(df))
    news_series = pd.to_numeric(df.get("sentiment_news_count_1d"), errors="coerce").fillna(0.0)
    news_count_total = int(float(news_series.sum()))
    news_article_days = int((news_series > 0).sum())
    news_density = round((100.0 * news_article_days / row_count), 4) if row_count else 0.0
    return {
        "ticker": ticker,
        "history_rows": row_count,
        "date_start": str(df["date"].iloc[0]) if row_count and "date" in df.columns else "",
        "date_end": str(df["date"].iloc[-1]) if row_count and "date" in df.columns else "",
        "news_count_total": news_count_total,
        "news_article_days": news_article_days,
        "news_density_pct": news_density,
    }


def _load_ticker_universe(data_dir: Path, metadata_file: Optional[Path]) -> Tuple[pd.DataFrame, List[str], List[str]]:
    warnings: List[str] = []
    limitations: List[str] = []
    metadata_df = pd.DataFrame()
    if metadata_file is not None and Path(metadata_file).exists():
        metadata_df, metadata_warnings = _load_metadata_from_csv(Path(metadata_file))
        warnings.extend(metadata_warnings)

    if metadata_df.empty:
        price_rows: List[Dict[str, object]] = []
        for path in sorted(Path(data_dir).glob("*.csv")):
            if path.name == "ticker_metadata.csv":
                continue
            try:
                price_rows.append(_summarize_price_csv(path))
            except Exception as exc:
                warnings.append(f"Failed to summarize price file {path.name}: {exc}.")
        metadata_df = pd.DataFrame(price_rows)
        limitations.append("ticker_metadata.csv unavailable or unusable; ticker summary derived directly from price CSV files.")
    else:
        if "news_density_pct" not in metadata_df.columns:
            history_rows = pd.to_numeric(metadata_df.get("history_rows"), errors="coerce").fillna(0.0)
            article_days = pd.to_numeric(metadata_df.get("news_article_days"), errors="coerce").fillna(0.0)
            metadata_df["news_density_pct"] = [
                round((100.0 * days / rows), 4) if rows > 0 else 0.0
                for rows, days in zip(history_rows, article_days)
            ]

    if metadata_df.empty:
        limitations.append("Ticker universe summary unavailable; decisions fall back to conservative governance block.")
    return metadata_df, dedupe(warnings), dedupe(limitations)


def _load_segmentation(output_dir: Path) -> Tuple[pd.DataFrame, List[str], List[str]]:
    path = Path(output_dir) / "baseline_v6_universe_segmentation.csv"
    if not path.exists():
        return pd.DataFrame(), [], ["baseline_v6_universe_segmentation.csv missing; segment labels in matrix may be incomplete."]
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return pd.DataFrame(), [f"Failed to read segmentation file {path}: {exc}."], [
            "Segmentation file unreadable; segment-level distribution analysis is limited."
        ]
    if "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.upper()
    return df, [], []


def _load_v9_results(output_dir: Path) -> Tuple[pd.DataFrame, List[str], List[str]]:
    path = Path(output_dir) / "baseline_v9_segment_oos_results.csv"
    if not path.exists():
        return pd.DataFrame(), [], ["baseline_v9_segment_oos_results.csv missing; per-ticker OOS sample mapping is limited."]
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        return pd.DataFrame(), [f"Failed to read v9 results CSV {path}: {exc}."], [
            "V9 results unreadable; OOS support per ticker cannot be derived."
        ]
    return df, [], []


def _load_artifacts(output_dir: Path) -> Tuple[Dict[str, Dict[str, object]], List[str], Dict[str, bool]]:
    artifacts: Dict[str, Dict[str, object]] = {}
    warnings: List[str] = []
    availability: Dict[str, bool] = {}
    for artifact_id, filename in TRACKED_JSON_ARTIFACTS:
        payload, item_warnings, available = _load_optional_json(output_dir=output_dir, filename=filename)
        artifacts[artifact_id] = payload
        warnings.extend(item_warnings)
        availability[artifact_id] = available
    return artifacts, dedupe(warnings), availability


def _extract_methodology(v9_summary: Dict[str, object]) -> Dict[str, int]:
    methodology = safe_dict(v9_summary.get("methodology"))
    warmup_bars = _safe_int(methodology.get("warmup_bars"), 21)
    fold_size_bars = _safe_int(methodology.get("fold_size_bars"), 12)
    fold_count = _safe_int(methodology.get("fold_count"), 3)
    return {
        "warmup_bars": warmup_bars,
        "fold_size_bars": fold_size_bars,
        "fold_count": fold_count,
    }


def _primary_segment(artifacts: Dict[str, Dict[str, object]]) -> str:
    v9_go = safe_dict(artifacts.get("baseline_v9_segment_oos_go_no_go"))
    if _safe_str(v9_go.get("primary_segment")):
        return _safe_str(v9_go.get("primary_segment"))
    v9_summary = safe_dict(artifacts.get("baseline_v9_segment_oos_summary"))
    decision = safe_dict(v9_summary.get("decision"))
    return _safe_str(decision.get("primary_segment"))


def _parse_segment_spec(spec: str) -> Tuple[str, str]:
    raw = str(spec).strip()
    if "=" not in raw:
        return "", ""
    field, value = raw.split("=", 1)
    return field.strip(), value.strip()


def _ticker_result_lookup(v9_results: pd.DataFrame, primary_segment: str) -> Dict[str, Dict[str, object]]:
    if v9_results.empty:
        return {}
    filtered = v9_results.loc[
        v9_results["row_type"].astype(str).eq("ticker_oos_summary")
        & v9_results["tested_segment"].astype(str).eq(primary_segment)
    ].copy()
    if filtered.empty:
        return {}
    return {
        str(row["ticker"]).upper(): row.to_dict()
        for _, row in filtered.iterrows()
    }


def _candidate_trade_sample_sign(primary_member: bool, result_row: Dict[str, object]) -> str:
    if not primary_member:
        return "not_in_primary_segment"
    if not result_row:
        return "not_tested"
    trade_count = _safe_int(result_row.get("candidate_total_trades"))
    average_return = _safe_float(result_row.get("average_return"))
    if trade_count <= 0:
        return "zero_trade"
    if average_return > 0:
        return "positive"
    if average_return < 0:
        return "negative"
    return "flat"


def _oos_support_strength(primary_member: bool, result_row: Dict[str, object]) -> str:
    if not primary_member:
        return "not_in_primary_segment"
    if not result_row:
        return "not_available"
    trade_count = _safe_int(result_row.get("candidate_total_trades"))
    average_return = _safe_float(result_row.get("average_return"))
    if trade_count <= 0:
        return "no_trade_support"
    if average_return > 1.0 and trade_count >= 3:
        return "positive_support"
    if average_return > 0:
        return "weak_positive_support"
    if average_return < -1.0:
        return "negative_support"
    return "weak_negative_support"


def _gap_reason_for_ticker(
    history_rows: int,
    usable_oos_windows: int,
    news_count_total: int,
    news_article_days: int,
    news_density: float,
    primary_member: bool,
    trade_count: int,
) -> Tuple[str, str]:
    reasons: List[str] = []
    if history_rows < MIN_HISTORY_ROWS_FOR_RETEST or usable_oos_windows < MIN_USABLE_OOS_WINDOWS:
        reasons.append("history_and_oos_window_shortfall")
    if news_article_days < MIN_MEDIAN_ARTICLE_DAYS or news_density < MIN_MEDIAN_NEWS_DENSITY_PCT_IF_DAILY_LABEL_KEPT:
        reasons.append("sparse_news_distribution")
    if primary_member and trade_count < 5:
        reasons.append("trade_sample_too_small")
    if primary_member and trade_count == 0:
        reasons.append("no_candidate_trade_support")

    unique_reasons = dedupe(reasons)
    if len(unique_reasons) >= 3:
        return "critical", "combined_history_distribution_and_trade_gap"
    if len(unique_reasons) == 2:
        return "high", "combined_history_and_distribution_gap"
    if len(unique_reasons) == 1:
        token = unique_reasons[0]
        if token == "history_and_oos_window_shortfall":
            return "high", "history_length_shortfall"
        if token == "sparse_news_distribution":
            return "high", "news_distribution_gap"
        if token == "trade_sample_too_small":
            return "high", "trade_sample_too_small"
        if token == "no_candidate_trade_support":
            return "critical", "no_candidate_trade_support"
    return "medium", "monitor_data_distribution"


def _gap_reason_for_segment(summary: Dict[str, object], tickers: Sequence[str], ticker_df: pd.DataFrame) -> Tuple[str, str]:
    trade_count = _safe_int(summary.get("candidate_total_trades"))
    active_tickers = _safe_int(summary.get("active_ticker_count"))
    ticker_count = _safe_int(summary.get("ticker_count"), len(list(tickers)))
    news_density = _safe_float(summary.get("mean_news_density"), 0.0)
    history_short = bool(
        not ticker_df.empty
        and (
            int(pd.to_numeric(ticker_df["history_rows"], errors="coerce").min()) < MIN_HISTORY_ROWS_FOR_RETEST
            or int(pd.to_numeric(ticker_df["usable_oos_windows"], errors="coerce").min()) < MIN_USABLE_OOS_WINDOWS
        )
    )

    reasons: List[str] = []
    if history_short:
        reasons.append("history_and_oos_window_shortfall")
    if ticker_count < MIN_SEGMENT_TICKER_COUNT:
        reasons.append("segment_ticker_count_too_small")
    if news_density < MIN_MEDIAN_NEWS_DENSITY_PCT_IF_DAILY_LABEL_KEPT:
        reasons.append("segment_news_density_too_sparse")
    if trade_count < MIN_TOTAL_OOS_TRADES_FOR_STABILITY or active_tickers < MIN_SEGMENT_TICKER_COUNT:
        reasons.append("oos_trade_sample_too_small")

    unique_reasons = dedupe(reasons)
    if len(unique_reasons) >= 3:
        return "critical", "combined_history_distribution_and_oos_sample_gap"
    if "oos_trade_sample_too_small" in unique_reasons and len(unique_reasons) == 1:
        return "high", "oos_trade_sample_too_small"
    if "segment_news_density_too_sparse" in unique_reasons and len(unique_reasons) == 1:
        return "high", "segment_news_distribution_gap"
    if "history_and_oos_window_shortfall" in unique_reasons and len(unique_reasons) == 1:
        return "high", "history_length_shortfall"
    return "high" if unique_reasons else "medium", (
        "combined_history_and_distribution_gap" if unique_reasons else "monitor_segment_distribution"
    )


def _segment_news_density(tickers: Sequence[str], ticker_df: pd.DataFrame) -> float:
    if ticker_df.empty:
        return 0.0
    subset = ticker_df.loc[ticker_df["ticker"].astype(str).isin(list(tickers))]
    if subset.empty:
        return 0.0
    return round(float(pd.to_numeric(subset["news_density_pct"], errors="coerce").fillna(0.0).mean()), 4)


def _build_gap_matrix(
    ticker_df: pd.DataFrame,
    segmentation_df: pd.DataFrame,
    v9_results: pd.DataFrame,
    v9_summary: Dict[str, object],
    primary_segment: str,
    methodology: Dict[str, int],
    limitations: Sequence[str],
) -> Tuple[List[Dict[str, object]], pd.DataFrame]:
    rows: List[Dict[str, object]] = []
    if ticker_df.empty:
        return rows, pd.DataFrame()

    working = ticker_df.copy()
    working["ticker"] = working["ticker"].astype(str).str.upper()
    working["history_rows"] = pd.to_numeric(working.get("history_rows"), errors="coerce").fillna(0).astype(int)
    working["news_count_total"] = pd.to_numeric(working.get("news_count_total"), errors="coerce").fillna(0).astype(int)
    working["news_article_days"] = pd.to_numeric(working.get("news_article_days"), errors="coerce").fillna(0).astype(int)
    working["news_density_pct"] = pd.to_numeric(working.get("news_density_pct"), errors="coerce").fillna(0.0)
    working["usable_oos_windows"] = [
        _usable_oos_windows(value, methodology["warmup_bars"], methodology["fold_size_bars"])
        for value in list(working["history_rows"])
    ]

    if not segmentation_df.empty:
        segment_cols = [col for col in segmentation_df.columns if col not in working.columns or col == "ticker"]
        working = working.merge(segmentation_df[segment_cols], on="ticker", how="left")

    field, value = _parse_segment_spec(primary_segment)
    result_lookup = _ticker_result_lookup(v9_results=v9_results, primary_segment=primary_segment)

    for _, row in working.sort_values("ticker").iterrows():
        ticker = str(row["ticker"]).upper()
        primary_member = bool(field and _safe_str(row.get(field)) == value)
        result_row = result_lookup.get(ticker, {})
        trade_count = _safe_int(result_row.get("candidate_total_trades"))
        severity, reason = _gap_reason_for_ticker(
            history_rows=_safe_int(row.get("history_rows")),
            usable_oos_windows=_safe_int(row.get("usable_oos_windows")),
            news_count_total=_safe_int(row.get("news_count_total")),
            news_article_days=_safe_int(row.get("news_article_days")),
            news_density=_safe_float(row.get("news_density_pct")),
            primary_member=primary_member,
            trade_count=trade_count,
        )
        row_limitations = list(limitations)
        if not primary_member:
            row_limitations.append("Ticker not part of the v9 primary segment.")
        if primary_member and not result_row:
            row_limitations.append("Primary-segment ticker has no explicit per-ticker v9 result row.")

        rows.append(
            {
                "row_type": "ticker",
                "subject": ticker,
                "ticker": ticker,
                "tested_segment": primary_segment if primary_member else "",
                "segment_role": "primary" if primary_member else "",
                "history_rows": _safe_int(row.get("history_rows")),
                "usable_oos_windows": _safe_int(row.get("usable_oos_windows")),
                "news_count_total": _safe_int(row.get("news_count_total")),
                "news_article_days": _safe_int(row.get("news_article_days")),
                "news_density": round(_safe_float(row.get("news_density_pct")), 4),
                "candidate_total_trades": trade_count if primary_member else "",
                "candidate_signal_count": _safe_int(result_row.get("candidate_signal_count")) if primary_member else "",
                "candidate_trade_sample_sign": _candidate_trade_sample_sign(primary_member=primary_member, result_row=result_row),
                "oos_support_strength": _oos_support_strength(primary_member=primary_member, result_row=result_row),
                "data_gap_severity": severity,
                "primary_gap_reason": reason,
                "limitations": "; ".join(dedupe(row_limitations)),
            }
        )

    tested_segments = list(v9_summary.get("tested_segments") or [])
    for item in tested_segments:
        segment = safe_dict(item)
        summary = safe_dict(segment.get("summary"))
        tickers = [str(value).upper() for value in list(segment.get("tickers") or summary.get("tickers") or [])]
        segment_key = _safe_str(segment.get("tested_segment"))
        subset = working.loc[working["ticker"].astype(str).isin(tickers)] if tickers else pd.DataFrame()
        mean_news_density = _segment_news_density(tickers=tickers, ticker_df=working)
        severity, reason = _gap_reason_for_segment(summary=summary, tickers=tickers, ticker_df=subset)
        weighted_return = _safe_float(summary.get("trade_weighted_average_return"))
        trade_sign = "zero_trade"
        if _safe_int(summary.get("candidate_total_trades")) > 0:
            if weighted_return > 0:
                trade_sign = "positive"
            elif weighted_return < 0:
                trade_sign = "negative"
            else:
                trade_sign = "flat"

        oos_strength = "failed_oos"
        if bool(summary.get("oos_stability_ok")) and bool(summary.get("ticker_consistency_ok")):
            oos_strength = "passed_oos"
        elif bool(summary.get("outlier_bias_ok")) and _safe_int(summary.get("candidate_total_trades")) > 0:
            oos_strength = "mixed_oos_support"

        rows.append(
            {
                "row_type": "segment",
                "subject": segment_key,
                "ticker": "",
                "tested_segment": segment_key,
                "segment_role": _safe_str(segment.get("segment_role")),
                "history_rows": int(pd.to_numeric(subset["history_rows"], errors="coerce").min()) if not subset.empty else "",
                "usable_oos_windows": int(pd.to_numeric(subset["usable_oos_windows"], errors="coerce").min()) if not subset.empty else "",
                "news_count_total": int(pd.to_numeric(subset["news_count_total"], errors="coerce").sum()) if not subset.empty else "",
                "news_article_days": int(pd.to_numeric(subset["news_article_days"], errors="coerce").sum()) if not subset.empty else "",
                "news_density": mean_news_density,
                "candidate_total_trades": _safe_int(summary.get("candidate_total_trades")),
                "candidate_signal_count": _safe_int(summary.get("candidate_signal_count")),
                "candidate_trade_sample_sign": trade_sign,
                "oos_support_strength": oos_strength,
                "data_gap_severity": severity,
                "primary_gap_reason": reason,
                "limitations": "; ".join(dedupe(limitations)),
            }
        )

    return rows, working


def _history_assessment(ticker_df: pd.DataFrame, methodology: Dict[str, int]) -> Dict[str, object]:
    if ticker_df.empty:
        return {
            "status": "insufficient_evidence",
            "minimum_history_rows_required": MIN_HISTORY_ROWS_FOR_RETEST,
            "minimum_usable_oos_windows_required": MIN_USABLE_OOS_WINDOWS,
            "current_min_history_rows": 0,
            "current_median_history_rows": 0,
            "current_min_usable_oos_windows": 0,
            "fair_oos_possible_now": False,
        }

    history_rows = pd.to_numeric(ticker_df["history_rows"], errors="coerce").fillna(0).astype(int)
    usable_windows = pd.to_numeric(ticker_df["usable_oos_windows"], errors="coerce").fillna(0).astype(int)
    current_min_history = int(history_rows.min())
    current_median_history = int(history_rows.median())
    current_min_windows = int(usable_windows.min())
    return {
        "status": "insufficient" if current_min_history < MIN_HISTORY_ROWS_FOR_RETEST else "sufficient",
        "methodology_reference": {
            "warmup_bars": methodology["warmup_bars"],
            "fold_size_bars": methodology["fold_size_bars"],
            "fold_count_seen_in_v9": methodology["fold_count"],
        },
        "minimum_history_rows_required": MIN_HISTORY_ROWS_FOR_RETEST,
        "minimum_usable_oos_windows_required": MIN_USABLE_OOS_WINDOWS,
        "current_min_history_rows": current_min_history,
        "current_median_history_rows": current_median_history,
        "current_max_history_rows": int(history_rows.max()),
        "current_min_usable_oos_windows": current_min_windows,
        "current_median_usable_oos_windows": int(usable_windows.median()),
        "fair_oos_possible_now": current_min_history >= MIN_HISTORY_ROWS_FOR_RETEST and current_min_windows >= MIN_USABLE_OOS_WINDOWS,
        "additional_rows_needed_per_ticker_from_current_minimum": max(0, MIN_HISTORY_ROWS_FOR_RETEST - current_min_history),
    }


def _universe_assessment(
    ticker_df: pd.DataFrame,
    primary_segment: str,
    v9_go_no_go: Dict[str, object],
) -> Dict[str, object]:
    if ticker_df.empty:
        return {
            "status": "insufficient_evidence",
            "total_tickers": 0,
            "primary_segment": primary_segment,
            "primary_segment_ticker_count": 0,
            "primary_segment_active_ticker_count": _safe_int(v9_go_no_go.get("primary_active_ticker_count")),
            "coverage_evenness": "unknown",
        }

    total_tickers = int(len(ticker_df))
    field, value = _parse_segment_spec(primary_segment)
    primary_ticker_count = 0
    if field and field in ticker_df.columns:
        primary_ticker_count = int(ticker_df[field].astype(str).eq(value).sum())

    coverage_evenness = "thin_but_even_history"
    if total_tickers < 12 or primary_ticker_count < MIN_SEGMENT_TICKER_COUNT:
        coverage_evenness = "too_thin_for_subset_retest"
    return {
        "status": "insufficient" if primary_ticker_count < MIN_SEGMENT_TICKER_COUNT else "borderline",
        "total_tickers": total_tickers,
        "primary_segment": primary_segment,
        "primary_segment_ticker_count": primary_ticker_count,
        "primary_segment_active_ticker_count": _safe_int(v9_go_no_go.get("primary_active_ticker_count")),
        "coverage_evenness": coverage_evenness,
        "comment": (
            "Universe history length is uniform, but the tested subset stays too small once OOS activity is considered."
        ),
    }


def _news_assessment(ticker_df: pd.DataFrame, primary_segment: str) -> Dict[str, object]:
    if ticker_df.empty:
        return {
            "status": "insufficient_evidence",
            "median_news_density_pct": 0.0,
            "median_news_article_days": 0,
            "primary_segment_news_density_pct": 0.0,
            "highest_priority_issue": "news_distribution_unknown",
        }

    density = pd.to_numeric(ticker_df["news_density_pct"], errors="coerce").fillna(0.0)
    article_days = pd.to_numeric(ticker_df["news_article_days"], errors="coerce").fillna(0).astype(int)
    field, value = _parse_segment_spec(primary_segment)
    primary_density = 0.0
    primary_articles = 0
    primary_tickers = 0
    if field and field in ticker_df.columns:
        subset = ticker_df.loc[ticker_df[field].astype(str).eq(value)]
        if not subset.empty:
            primary_density = round(float(pd.to_numeric(subset["news_density_pct"], errors="coerce").fillna(0.0).mean()), 4)
            primary_articles = int(pd.to_numeric(subset["news_count_total"], errors="coerce").fillna(0).sum())
            primary_tickers = int(len(subset))

    status = "insufficient"
    if float(density.median()) >= MIN_MEDIAN_NEWS_DENSITY_PCT_IF_DAILY_LABEL_KEPT and int(article_days.median()) >= MIN_MEDIAN_ARTICLE_DAYS:
        status = "sufficient"
    return {
        "status": status,
        "median_news_density_pct": round(float(density.median()), 4),
        "mean_news_density_pct": round(float(density.mean()), 4),
        "median_news_article_days": int(article_days.median()),
        "min_news_article_days": int(article_days.min()),
        "primary_segment_news_density_pct": primary_density,
        "primary_segment_article_count_total": primary_articles,
        "primary_segment_ticker_count": primary_tickers,
        "highest_priority_issue": "sparse_and_uneven_aligned_news_distribution",
    }


def _oos_feasibility_assessment(
    v9_go_no_go: Dict[str, object],
    v9_summary: Dict[str, object],
) -> Dict[str, object]:
    primary_total_trades = _safe_int(v9_go_no_go.get("primary_total_trades_sum"))
    active_ticker_count = _safe_int(v9_go_no_go.get("primary_active_ticker_count"))
    tested_segments = list(v9_summary.get("tested_segments") or [])
    supporting_failed = list(v9_go_no_go.get("supporting_segments_failed") or [])
    fold_count = _safe_int(safe_dict(v9_summary.get("methodology")).get("fold_count"), 0)
    return {
        "status": (
            "insufficient"
            if primary_total_trades < MIN_TOTAL_OOS_TRADES_FOR_STABILITY
            or active_ticker_count < MIN_SEGMENT_TICKER_COUNT
            or _safe_str(v9_go_no_go.get("decision")) == "no_go_even_for_segment"
            else "borderline"
        ),
        "primary_total_trades_sum": primary_total_trades,
        "primary_active_ticker_count": active_ticker_count,
        "primary_trade_weighted_average_return": round(_safe_float(v9_go_no_go.get("primary_trade_weighted_average_return")), 4),
        "primary_mean_average_return_active": round(_safe_float(v9_go_no_go.get("primary_mean_average_return_active")), 4),
        "supporting_segments_failed": supporting_failed,
        "tested_segment_count": len(tested_segments),
        "fold_count_seen_in_v9": fold_count,
        "fair_strategy_retest_possible_now": False,
    }


def _highest_priority_gap(history: Dict[str, object], news: Dict[str, object], oos: Dict[str, object]) -> str:
    history_short = not bool(history.get("fair_oos_possible_now"))
    news_sparse = _safe_str(news.get("status")) != "sufficient"
    oos_small = _safe_str(oos.get("status")) == "insufficient"
    if history_short and news_sparse and oos_small:
        return "combined_history_length_and_distribution_gap"
    if history_short and news_sparse:
        return "combined_history_and_news_distribution_gap"
    if history_short:
        return "history_length_shortfall"
    if news_sparse:
        return "news_distribution_gap"
    return "oos_sample_instability"


def _minimum_data_extension_required(history: Dict[str, object]) -> Dict[str, object]:
    current_min_rows = _safe_int(history.get("current_min_history_rows"))
    return {
        "minimum_history_rows_per_ticker": MIN_HISTORY_ROWS_FOR_RETEST,
        "minimum_additional_rows_per_ticker_from_current_minimum": max(0, MIN_HISTORY_ROWS_FOR_RETEST - current_min_rows),
        "minimum_usable_oos_windows": MIN_USABLE_OOS_WINDOWS,
        "minimum_segment_ticker_count_for_retest": MIN_SEGMENT_TICKER_COUNT,
        "minimum_median_news_article_days_per_ticker_if_daily_sentiment_label_kept": MIN_MEDIAN_ARTICLE_DAYS,
        "minimum_median_news_density_pct_if_daily_sentiment_label_kept": MIN_MEDIAN_NEWS_DENSITY_PCT_IF_DAILY_LABEL_KEPT,
    }


def _build_framework_scope(
    artifacts: Dict[str, Dict[str, object]],
    primary_segment: str,
    minimum_data_extension_required: Dict[str, object],
    highest_priority_gap: str,
) -> Dict[str, object]:
    closeout = safe_dict(artifacts.get("phase_b_final_closeout"))
    roadmap = safe_dict(artifacts.get("project_roadmap_status"))
    governance = safe_dict(artifacts.get("baseline_v6_next_experiment_governance"))

    parked_items = list(closeout.get("parked_items") or [])
    must_stay_fixed = dedupe(
        [
            "baseline aktif",
            "logika entry/exit aktif",
            "guardrail global promosi akhir tetap fixed",
            "Phase A = closed_with_notes",
            "Phase B = phase_b_closed_with_learnings_no_candidate",
            "Phase C = phase_c_no_go_yet",
            "global_promotion_allowed = false",
            *list(governance.get("what_to_keep_fixed") or []),
        ]
    )
    must_not_reopen = dedupe(
        [
            *parked_items,
            "global promotion",
            "Phase C continuation",
        ]
    )
    return {
        "evaluation_framework_redesign_required": True,
        "redesign_reason": (
            "Framework evaluasi saat ini belum bisa menjamin fairness OOS karena history terlalu pendek, distribusi news terlalu tipis, dan sample trade v9 hanya 11 pada primary segment."
        ),
        "highest_priority_gap": highest_priority_gap,
        "what_must_stay_fixed": must_stay_fixed,
        "what_must_not_be_reopened": must_not_reopen,
        "what_must_be_redefined": [
            "minimum_data_sufficiency gate sebelum strategy test dibuka lagi",
            "fair OOS validation definition dan jumlah window minimum",
            "alignment antara label sentiment dan return horizon",
            "trigger universe reconstruction setelah data extension",
            "struktur pelaporan per ticker, per segment, dan per fold yang wajib lulus sebelum interpretasi hasil",
        ],
        "recommended_validation_structure": {
            "pre_validation_gate": [
                "Audit history rows per ticker wajib lulus sebelum kandidat apa pun diuji.",
                "Audit coverage news dan density wajib lulus atau label horizon harus diubah lebih dulu.",
                "Dokumen guardrail evaluasi harus dibekukan sebelum retest dimulai.",
            ],
            "candidate_evaluation_flow": [
                "Kandidat tetap harus frozen; tidak boleh tuning ulang memakai hasil OOS.",
                "Laporan wajib memisahkan kelayakan data, hasil in-sample, dan hasil OOS.",
                "Keputusan retest diblok jika data sufficiency gate gagal.",
            ],
        },
        "recommended_oos_structure": {
            "minimum_history_rows_per_ticker": minimum_data_extension_required["minimum_history_rows_per_ticker"],
            "minimum_usable_oos_windows": minimum_data_extension_required["minimum_usable_oos_windows"],
            "minimum_segment_ticker_count": minimum_data_extension_required["minimum_segment_ticker_count_for_retest"],
            "minimum_total_oos_trades_for_stability": MIN_TOTAL_OOS_TRADES_FOR_STABILITY,
            "no_global_promotion_under_phase_b_closeout": True,
            "notes": [
                "OOS harus dijalankan pada kandidat yang dibekukan, bukan pada rule yang sedang dituning.",
                "Fairness OOS baru boleh diinterpretasi jika jumlah window dan coverage segment memenuhi gate minimum.",
            ],
        },
        "recommended_segment_policy": {
            "segment_aware_evaluation_still_required_after_data_extension": True,
            "segment_policy_reason": (
                f"Primary subset terakhir tetap {primary_segment or 'unknown'} dan universe heterogen belum boleh diasumsikan homogen sebelum reconstruction diulang."
            ),
            "supporting_segments_only_for_robustness_check": True,
            "global_promotion_allowed": False,
        },
        "recommended_preconditions_before_any_new_strategy_test": [
            f"Setiap ticker dalam universe retest memiliki minimal {MIN_HISTORY_ROWS_FOR_RETEST} daily rows.",
            f"Konfigurasi OOS yang dipakai menghasilkan minimal {MIN_USABLE_OOS_WINDOWS} usable windows per ticker.",
            (
                f"Jika daily sentiment label tetap dipakai, median aligned news density universe harus minimal "
                f"{MIN_MEDIAN_NEWS_DENSITY_PCT_IF_DAILY_LABEL_KEPT:.1f}% dan median article days minimal {MIN_MEDIAN_ARTICLE_DAYS}."
            ),
            "Jika target density tidak bisa dicapai, label horizon dan return horizon harus didefinisikan ulang lebih dulu.",
            "Universe reconstruction dan segment policy harus dihitung ulang setelah data extension selesai.",
            "Phase C tetap tertutup dan eksperimen strategi baru tetap dilarang sampai semua prasyarat ini lulus.",
        ],
        "roadmap_guardrail_snapshot": {
            "phase_a_status": safe_dict(roadmap.get("phase_a_final_status")).get("status"),
            "phase_b_status": closeout.get("phase_b_final_status"),
            "phase_c_status": safe_dict(roadmap.get("latest_execution_status")).get("phase_c_decision"),
        },
    }


def _build_universe_precheck(
    primary_segment: str,
    history_assessment: Dict[str, object],
    news_assessment: Dict[str, object],
) -> Dict[str, object]:
    return {
        "universe_reconstruction_needed": True,
        "why": (
            "Universe segmentation saat ini dibangun dari history 57 bar dengan aligned news yang sangat tipis, sehingga belum cukup kuat untuk retest yang fair."
        ),
        "trigger_conditions": [
            f"History minimum per ticker sudah mencapai {MIN_HISTORY_ROWS_FOR_RETEST} bar.",
            "Coverage news dan density sudah naik atau horizon label sudah didefinisikan ulang.",
            "Framework data sufficiency dan OOS fairness sudah dibekukan.",
        ],
        "what_data_must_exist_first": [
            f"Tambahan history minimal {history_assessment.get('additional_rows_needed_per_ticker_from_current_minimum', 0)} bar dari kondisi minimum sekarang.",
            "Metadata ticker yang konsisten untuk seluruh universe retest.",
            "Aligned sentiment coverage yang cukup untuk horizon evaluasi yang dipilih.",
        ],
        "whether_current_universe_is_usable_for_any_fair_retest": False,
        "current_primary_segment": primary_segment,
        "current_news_distribution_status": news_assessment.get("status"),
    }


def _build_data_audit_text(payload: Dict[str, object]) -> List[str]:
    minimum = safe_dict(payload.get("minimum_data_extension_required"))
    return [
        "Phase B Data Extension Audit",
        f"- current_data_sufficiency_status={payload.get('current_data_sufficiency_status')}",
        f"- strategy_retest_allowed_now={payload.get('strategy_retest_allowed_now')}",
        f"- highest_priority_data_gap={payload.get('highest_priority_data_gap')}",
        (
            "- minimum_data_extension_required="
            f"history_rows_per_ticker>={minimum.get('minimum_history_rows_per_ticker')}, "
            f"usable_oos_windows>={minimum.get('minimum_usable_oos_windows')}, "
            f"median_news_density_pct_if_daily_label_kept>={minimum.get('minimum_median_news_density_pct_if_daily_sentiment_label_kept')}"
        ),
        f"- decisive_statement={payload.get('decisive_statement')}",
        "",
        "History assessment:",
        json.dumps(safe_dict(payload.get("history_length_assessment")), ensure_ascii=True, indent=2),
        "",
        "Universe coverage assessment:",
        json.dumps(safe_dict(payload.get("universe_coverage_assessment")), ensure_ascii=True, indent=2),
        "",
        "News distribution assessment:",
        json.dumps(safe_dict(payload.get("news_distribution_assessment")), ensure_ascii=True, indent=2),
        "",
        "OOS feasibility assessment:",
        json.dumps(safe_dict(payload.get("oos_feasibility_assessment")), ensure_ascii=True, indent=2),
    ]


def _build_framework_scope_text(payload: Dict[str, object]) -> List[str]:
    return [
        "Framework Redesign Scope",
        f"- evaluation_framework_redesign_required={payload.get('evaluation_framework_redesign_required')}",
        f"- redesign_reason={payload.get('redesign_reason')}",
        f"- highest_priority_gap={payload.get('highest_priority_gap')}",
        "",
        "What must stay fixed:",
        *[f"- {item}" for item in list(payload.get("what_must_stay_fixed") or [])],
        "",
        "What must not be reopened:",
        *[f"- {item}" for item in list(payload.get("what_must_not_be_reopened") or [])],
        "",
        "What must be redefined:",
        *[f"- {item}" for item in list(payload.get("what_must_be_redefined") or [])],
        "",
        "Recommended preconditions before any new strategy test:",
        *[f"- {item}" for item in list(payload.get("recommended_preconditions_before_any_new_strategy_test") or [])],
    ]


def run_phase_b_data_extension_audit(
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise PhaseBDataExtensionAuditCliError(f"Data directory not found: {data_dir}")

    artifacts, artifact_warnings, artifact_available = _load_artifacts(output_dir=output_dir)
    ticker_df, metadata_warnings, metadata_limitations = _load_ticker_universe(
        data_dir=data_dir,
        metadata_file=metadata_file,
    )
    segmentation_df, segmentation_warnings, segmentation_limitations = _load_segmentation(output_dir=output_dir)
    v9_results, v9_result_warnings, v9_result_limitations = _load_v9_results(output_dir=output_dir)

    warnings = dedupe([*artifact_warnings, *metadata_warnings, *segmentation_warnings, *v9_result_warnings])
    limitations = dedupe([*metadata_limitations, *segmentation_limitations, *v9_result_limitations])

    v9_summary = safe_dict(artifacts.get("baseline_v9_segment_oos_summary"))
    methodology = _extract_methodology(v9_summary=v9_summary)
    primary_segment = _primary_segment(artifacts=artifacts)

    gap_matrix_rows, enriched_ticker_df = _build_gap_matrix(
        ticker_df=ticker_df,
        segmentation_df=segmentation_df,
        v9_results=v9_results,
        v9_summary=v9_summary,
        primary_segment=primary_segment,
        methodology=methodology,
        limitations=limitations,
    )
    history_assessment = _history_assessment(
        ticker_df=enriched_ticker_df if not enriched_ticker_df.empty else ticker_df,
        methodology=methodology,
    )
    news_assessment = _news_assessment(
        ticker_df=enriched_ticker_df if not enriched_ticker_df.empty else ticker_df,
        primary_segment=primary_segment,
    )
    universe_assessment = _universe_assessment(
        ticker_df=enriched_ticker_df if not enriched_ticker_df.empty else ticker_df,
        primary_segment=primary_segment,
        v9_go_no_go=safe_dict(artifacts.get("baseline_v9_segment_oos_go_no_go")),
    )
    oos_assessment = _oos_feasibility_assessment(
        v9_go_no_go=safe_dict(artifacts.get("baseline_v9_segment_oos_go_no_go")),
        v9_summary=v9_summary,
    )
    highest_priority_gap = _highest_priority_gap(
        history=history_assessment,
        news=news_assessment,
        oos=oos_assessment,
    )
    minimum_extension = _minimum_data_extension_required(history=history_assessment)

    data_audit = {
        "generated_at": _now_iso(),
        "current_data_sufficiency_status": "insufficient_for_fair_strategy_retest",
        "minimum_data_extension_required": minimum_extension,
        "highest_priority_data_gap": highest_priority_gap,
        "history_length_assessment": history_assessment,
        "universe_coverage_assessment": universe_assessment,
        "news_distribution_assessment": news_assessment,
        "oos_feasibility_assessment": oos_assessment,
        "strategy_retest_allowed_now": False,
        "decisive_statement": (
            "Data saat ini belum cukup untuk strategy retest; prioritas utama adalah memperpanjang history dan meratakan coverage sample. "
            "Framework evaluasi perlu di-redesign sebelum eksperimen baru karena fairness OOS belum bisa dijamin. "
            "Strategy retest tetap dilarang sampai syarat minimum coverage dan OOS window terpenuhi."
        ),
        "limitations": limitations,
        "warnings": warnings,
        "artifact_availability": artifact_available,
    }

    framework_scope = _build_framework_scope(
        artifacts=artifacts,
        primary_segment=primary_segment,
        minimum_data_extension_required=minimum_extension,
        highest_priority_gap=highest_priority_gap,
    )
    universe_precheck = _build_universe_precheck(
        primary_segment=primary_segment,
        history_assessment=history_assessment,
        news_assessment=news_assessment,
    )

    _write_json(output_dir / DATA_AUDIT_OUTPUT, data_audit)
    _write_text(output_dir / DATA_AUDIT_TEXT_OUTPUT, _build_data_audit_text(data_audit))
    _write_matrix(output_dir / DATA_GAP_MATRIX_OUTPUT, gap_matrix_rows)
    _write_json(output_dir / FRAMEWORK_SCOPE_OUTPUT, framework_scope)
    _write_text(output_dir / FRAMEWORK_SCOPE_TEXT_OUTPUT, _build_framework_scope_text(framework_scope))
    _write_json(output_dir / UNIVERSE_PRECHECK_OUTPUT, universe_precheck)

    return {
        "phase_b_data_extension_audit": data_audit,
        "framework_redesign_scope": framework_scope,
        "universe_reconstruction_precheck": universe_precheck,
        "gap_matrix_rows": gap_matrix_rows,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit Phase B data sufficiency and define evaluation-framework redesign scope."
    )
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory containing and receiving artifacts.")
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional ticker metadata CSV. Falls back to direct CSV summarization when unavailable.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    metadata_file = Path(args.metadata_file) if args.metadata_file else None

    try:
        result = run_phase_b_data_extension_audit(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=metadata_file,
        )
    except PhaseBDataExtensionAuditCliError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during Phase B data extension audit: {exc}", file=sys.stderr)
        return 1

    audit = safe_dict(result.get("phase_b_data_extension_audit"))
    print("Phase B data extension audit complete.")
    print(f"current_data_sufficiency_status={audit.get('current_data_sufficiency_status')}")
    print(f"strategy_retest_allowed_now={audit.get('strategy_retest_allowed_now')}")
    print(f"highest_priority_data_gap={audit.get('highest_priority_data_gap')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
