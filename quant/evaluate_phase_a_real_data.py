"""Evaluate Phase A signals using real historical CSV data per ticker.

Features
--------
- Scan a folder of CSV files, one file per ticker
- Clean and validate OHLCV data
- Run Phase A feature engineering and backtests
- Compare baseline vs Phase A vs strict Phase A
- Export summary results to CSV and Excel when available

Example
-------
Preferred execution from project root:

    python3 -m quant.evaluate_phase_a_real_data --data-dir data --output-dir output --strict

Direct script execution is also supported:

    python3 quant/evaluate_phase_a_real_data.py --data-dir data --output-dir output --strict
"""

from __future__ import annotations

import argparse
import json
import math
import shlex
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a import (  # noqa: E402
    DEFAULT_SENTIMENT_BASELINE_WINDOW,
    DEFAULT_SENTIMENT_MOMENTUM_MODE,
    DEFAULT_SENTIMENT_MOMENTUM_THRESHOLD,
    DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    DEFAULT_WEEKLY_TREND_METHOD,
    NUMERIC_COLUMNS,
    REQUIRED_COLUMNS,
    SENTIMENT_DAILY_COLUMNS,
    add_trend_features,
    add_sentiment_momentum_features,
    add_volume_features,
    backtest_signal_frame,
    compare_backtest_variants,
    generate_phase_a_signal,
    validate_sentiment_series_columns,
)
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)

SUMMARY_COLUMNS = [
    "ticker",
    "rows",
    "date_start",
    "date_end",
    "baseline_total_trades",
    "baseline_win_rate",
    "baseline_average_return",
    "baseline_max_drawdown",
    "volume_spike_total_trades",
    "volume_spike_win_rate",
    "volume_spike_average_return",
    "volume_spike_max_drawdown",
    "baseline_phase_a_total_trades",
    "baseline_phase_a_win_rate",
    "baseline_phase_a_average_return",
    "baseline_phase_a_max_drawdown",
    "phase_a_total_trades",
    "phase_a_win_rate",
    "phase_a_average_return",
    "phase_a_max_drawdown",
    "strict_total_trades",
    "strict_win_rate",
    "strict_average_return",
    "strict_max_drawdown",
    "delta_trades",
    "delta_win_rate",
    "delta_average_return",
    "phase_a_applied_threshold",
    "phase_a_applied_strict_mode",
    "phase_b_candle_confirmation_enabled",
    "phase_b_candle_confirmation_threshold",
    "phase_b_weekly_trend_enabled",
    "phase_b_weekly_trend_method",
    "phase_b_weekly_require_slope_up",
    "phase_b_weekly_data_ready",
    "phase_b_sentiment_momentum_enabled",
    "phase_b_sentiment_momentum_window",
    "phase_b_sentiment_baseline_window",
    "phase_b_sentiment_momentum_threshold",
    "phase_b_sentiment_momentum_mode",
    "phase_b_sentiment_momentum_data_ready",
    "phase_a_baseline_source",
]
SKIPPED_COLUMNS = ["ticker", "file_path", "reason"]
CANDLE_CONFIRMATION_EXPERIMENT_COLUMNS = [
    "ticker",
    "rows",
    "date_start",
    "date_end",
    "phase_a_applied_threshold",
    "phase_a_applied_strict_mode",
    "control_phase_a_total_trades",
    "experiment_phase_a_total_trades",
    "delta_phase_a_total_trades",
    "trade_retention_pct",
    "control_phase_a_win_rate",
    "experiment_phase_a_win_rate",
    "delta_phase_a_win_rate",
    "control_phase_a_average_return",
    "experiment_phase_a_average_return",
    "delta_phase_a_average_return",
    "control_phase_a_max_drawdown",
    "experiment_phase_a_max_drawdown",
    "delta_phase_a_max_drawdown",
    "candle_volume_confirmation_threshold",
    "phase_a_baseline_source",
]
MULTITIMEFRAME_EXPERIMENT_COLUMNS = [
    "ticker",
    "rows",
    "date_start",
    "date_end",
    "phase_a_applied_threshold",
    "phase_a_applied_strict_mode",
    "baseline_total_trades",
    "candidate_total_trades",
    "delta_total_trades",
    "trade_retention_pct",
    "baseline_win_rate",
    "candidate_win_rate",
    "delta_win_rate",
    "baseline_average_return",
    "candidate_average_return",
    "delta_average_return",
    "baseline_max_drawdown",
    "candidate_max_drawdown",
    "delta_max_drawdown",
    "weekly_trend_method",
    "weekly_require_slope_up",
    "weekly_data_ready",
    "phase_a_baseline_source",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
]
SENTIMENT_MOMENTUM_EXPERIMENT_COLUMNS = [
    "ticker",
    "rows",
    "date_start",
    "date_end",
    "phase_a_applied_threshold",
    "phase_a_applied_strict_mode",
    "baseline_total_trades",
    "candidate_total_trades",
    "delta_total_trades",
    "trade_retention_pct",
    "baseline_win_rate",
    "candidate_win_rate",
    "delta_win_rate",
    "baseline_average_return",
    "candidate_average_return",
    "delta_average_return",
    "baseline_max_drawdown",
    "candidate_max_drawdown",
    "delta_max_drawdown",
    "sentiment_momentum_mode",
    "sentiment_momentum_window",
    "sentiment_baseline_window",
    "sentiment_momentum_threshold",
    "sentiment_data_ready",
    "phase_a_baseline_source",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
]
ITEM7_REQUIRED_DATASET_COLUMNS = [*REQUIRED_COLUMNS, *SENTIMENT_DAILY_COLUMNS]
ITEM7_OPTIONAL_DATASET_COLUMNS = []
ITEM7_ACCEPTED_COLUMN_ALIASES = {
    "sentiment_average_1d": [
        "sentiment_score_daily",
        "sentiment_average_daily",
    ],
    "sentiment_weighted_1d": [
        "sentiment_score_weighted_daily",
        "sentiment_weighted_daily",
    ],
    "sentiment_news_count_1d": [
        "sentiment_article_count_daily",
        "sentiment_count_daily",
    ],
}
ITEM7_INVALID_PATTERNS = [
    "mixed_canonical_and_alias_columns_for_the_same_sentiment_field",
    "multiple_aliases_for_one_sentiment_field",
    "missing_any_required_sentiment_column_after_alias_normalization",
    "blank_or_non_numeric_sentiment_scores",
    "negative_or_fractional_sentiment_article_count",
    "metadata_ticker_missing_when_metadata_file_is_supplied",
    "history_shorter_than_sentiment_baseline_window",
]
ITEM7_SENTIMENT_COLUMN_DESCRIPTIONS = {
    "date": "Tanggal trading harian yang menjadi anchor evaluasi.",
    "open": "Harga open harian.",
    "high": "Harga high harian.",
    "low": "Harga low harian.",
    "close": "Harga close harian.",
    "volume": "Volume harian.",
    "sentiment_average_1d": (
        "Rata-rata skor sentimen artikel pada window trade-date saat ini; 0.0 jika tidak ada artikel."
    ),
    "sentiment_weighted_1d": (
        "Rata-rata tertimbang skor sentimen artikel pada window trade-date saat ini; 0.0 jika tidak ada artikel."
    ),
    "sentiment_news_count_1d": (
        "Jumlah artikel pada window trade-date saat ini; 0 berarti tidak ada artikel dan membedakan dari netral murni."
    ),
}


def _normalize_item7_sentiment_aliases(
    frame: pd.DataFrame,
    warnings: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Normalize accepted item-7 sentiment aliases into canonical column names."""

    working = frame.copy()
    normalized_warnings = warnings if warnings is not None else []

    for canonical, aliases in ITEM7_ACCEPTED_COLUMN_ALIASES.items():
        present_aliases = [alias for alias in aliases if alias in working.columns]
        if canonical in working.columns and present_aliases:
            raise ValueError(
                "Ambiguous sentiment schema: found canonical column "
                f"'{canonical}' together with aliases {present_aliases}."
            )
        if len(present_aliases) > 1:
            raise ValueError(
                "Ambiguous sentiment schema: multiple aliases found for "
                f"'{canonical}': {present_aliases}."
            )
        if canonical not in working.columns and len(present_aliases) == 1:
            alias = present_aliases[0]
            working = working.rename(columns={alias: canonical})
            normalized_warnings.append(
                f"Normalized sentiment alias '{alias}' into canonical column '{canonical}'."
            )

    return working


class EvaluationCliError(ValueError):
    """Friendly CLI error with actionable next-step suggestions."""

    def __init__(self, message: str, suggestions: Optional[Sequence[str]] = None) -> None:
        super().__init__(message)
        self.suggestions = list(suggestions or [])


@dataclass
class EvaluationRecord:
    """One successful ticker evaluation result."""

    ticker: str
    rows: int
    date_start: pd.Timestamp
    date_end: pd.Timestamp
    metrics: Dict[str, float | int | str | pd.Timestamp]
    warnings: List[str] = field(default_factory=list)


@dataclass
class SkipRecord:
    """One skipped file record."""

    ticker: str
    file_path: str
    reason: str


def extract_ticker_from_filename(path: Path) -> str:
    """Extract ticker name from a CSV filename."""

    return path.stem.upper().strip()


def _clean_numeric_series(series: pd.Series) -> pd.Series:
    """Coerce possibly string-formatted numeric series to float."""

    if series.dtype == object:
        series = (
            series.astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("_", "", regex=False)
            .str.strip()
        )
    return pd.to_numeric(series, errors="coerce")


def load_price_csv(path: Path) -> Tuple[pd.DataFrame, List[str]]:
    """Load and clean one OHLCV CSV file.

    Parameters
    ----------
    path:
        Path to the CSV file.

    Returns
    -------
    tuple[pd.DataFrame, list[str]]
        Cleaned DataFrame and warning messages.

    Raises
    ------
    ValueError
        If the file is empty, malformed, or missing required columns.
    """

    warnings: List[str] = []

    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError as exc:
        raise ValueError("CSV is empty.") from exc
    except pd.errors.ParserError as exc:
        raise ValueError(f"CSV parser error: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Failed to read CSV: {exc}") from exc

    if frame.empty:
        raise ValueError("CSV contains no rows.")

    frame = _normalize_item7_sentiment_aliases(frame, warnings)

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}. "
            f"Expected columns: {REQUIRED_COLUMNS}."
        )

    frame = frame.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    invalid_date_count = int(frame["date"].isna().sum())
    if invalid_date_count:
        warnings.append(f"Dropped {invalid_date_count} rows with invalid date.")

    for column in NUMERIC_COLUMNS:
        frame[column] = _clean_numeric_series(frame[column])

    for column in [
        "sentiment_average_1d",
        "sentiment_weighted_1d",
        "sentiment_news_count_1d",
    ]:
        if column in frame.columns:
            frame[column] = _clean_numeric_series(frame[column])

    initial_rows = len(frame)
    frame = frame.dropna(subset=REQUIRED_COLUMNS)
    dropped_nan_rows = initial_rows - len(frame)
    if dropped_nan_rows:
        warnings.append(f"Dropped {dropped_nan_rows} rows with NaN in required OHLCV fields.")

    if frame.empty:
        raise ValueError("No valid OHLCV rows remain after cleaning.")

    duplicate_dates = int(frame["date"].duplicated(keep="last").sum())
    if duplicate_dates:
        warnings.append(f"Removed {duplicate_dates} duplicate date rows (kept latest occurrence).")
        frame = frame.drop_duplicates(subset=["date"], keep="last")

    frame = frame.sort_values("date").reset_index(drop=True)

    negative_volume_count = int((frame["volume"] < 0).sum())
    if negative_volume_count:
        warnings.append(f"Dropped {negative_volume_count} rows with negative volume.")
        frame = frame.loc[frame["volume"] >= 0].copy()

    if frame.empty:
        raise ValueError("All rows were removed during validation.")

    zero_volume_count = int((frame["volume"] == 0).sum())
    if zero_volume_count:
        warnings.append(f"Found {zero_volume_count} rows with zero volume.")

    if len(frame) < 20:
        warnings.append("History shorter than 20 rows; MA20 volume will be incomplete.")
    if len(frame) < 50:
        warnings.append("History shorter than 50 rows; EMA50 will be incomplete.")

    return frame, warnings


def inspect_item7_sentiment_dataset(
    path: Path,
    sentiment_momentum_window: int = DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    sentiment_baseline_window: int = DEFAULT_SENTIMENT_BASELINE_WINDOW,
) -> Dict[str, object]:
    """Inspect one CSV for Phase B item 7 readiness."""

    ticker = extract_ticker_from_filename(path)

    try:
        frame, warnings = load_price_csv(path)
    except ValueError as exc:
        return {
            "ticker": ticker,
            "file_path": str(path),
            "schema_status": "invalid_ohlcv",
            "readiness_status": "sentiment_schema_invalid",
            "dataset_has_sentiment_series": False,
            "usable_for_item7": False,
            "has_sentiment_columns": False,
            "has_weighted_sentiment": False,
            "has_article_count": False,
            "missing_columns": [],
            "invalid_reasons": [str(exc)],
            "blocker_reason": str(exc),
            "warnings": [],
            "rows": 0,
            "date_start": None,
            "date_end": None,
            "article_day_count": 0,
            "article_count_total": 0,
            "usable_row_count": 0,
            "usable_date_start": None,
            "usable_date_end": None,
            "insufficient_history": False,
            "sufficient_history": False,
            "no_articles_in_history": False,
            "date_alignment_valid": False,
            "metadata_synced": True,
            "metadata_status": "not_checked",
        }

    missing_sentiment_columns = [
        column for column in SENTIMENT_DAILY_COLUMNS if column not in frame.columns
    ]
    all_missing = len(missing_sentiment_columns) == len(SENTIMENT_DAILY_COLUMNS)
    partial_missing = bool(missing_sentiment_columns) and not all_missing
    date_start = frame["date"].iloc[0].date().isoformat()
    date_end = frame["date"].iloc[-1].date().isoformat()

    inspection: Dict[str, object] = {
        "ticker": ticker,
        "file_path": str(path),
        "dataset_has_sentiment_series": not missing_sentiment_columns,
        "usable_for_item7": False,
        "has_sentiment_columns": "sentiment_average_1d" in frame.columns,
        "has_weighted_sentiment": "sentiment_weighted_1d" in frame.columns,
        "has_article_count": "sentiment_news_count_1d" in frame.columns,
        "missing_columns": missing_sentiment_columns,
        "invalid_reasons": [],
        "blocker_reason": "",
        "warnings": warnings,
        "rows": int(len(frame)),
        "date_start": date_start,
        "date_end": date_end,
        "article_day_count": 0,
        "article_count_total": 0,
        "usable_row_count": 0,
        "usable_date_start": None,
        "usable_date_end": None,
        "insufficient_history": len(frame) < int(sentiment_baseline_window),
        "sufficient_history": len(frame) >= int(sentiment_baseline_window),
        "no_articles_in_history": False,
        "date_alignment_valid": True,
        "metadata_synced": True,
        "metadata_status": "not_checked",
    }

    if all_missing:
        inspection["schema_status"] = "ohlcv_only"
        inspection["readiness_status"] = "ohlcv_only"
        inspection["invalid_reasons"] = [
            "Dataset hanya memiliki kolom OHLCV; seri sentimen harian belum diexport."
        ]
        inspection["blocker_reason"] = inspection["invalid_reasons"][0]
        return inspection

    if partial_missing:
        inspection["schema_status"] = "sentiment_columns_incomplete"
        inspection["readiness_status"] = "sentiment_schema_invalid"
        inspection["invalid_reasons"] = [
            "Kolom sentimen harian tidak lengkap; schema export item 7 harus memakai seluruh kolom wajib."
        ]
        inspection["blocker_reason"] = inspection["invalid_reasons"][0]
        return inspection

    try:
        sentiment_frame = validate_sentiment_series_columns(frame)
    except ValueError as exc:
        inspection["schema_status"] = "sentiment_schema_invalid"
        inspection["invalid_reasons"] = [str(exc)]
        inspection["readiness_status"] = "sentiment_schema_invalid"
        inspection["blocker_reason"] = str(exc)
        return inspection

    sentiment_count = pd.to_numeric(sentiment_frame["sentiment_news_count_1d"], errors="coerce")
    inspection["article_day_count"] = int(sentiment_count.gt(0).sum())
    inspection["article_count_total"] = int(sentiment_count.sum())
    inspection["no_articles_in_history"] = bool(int(sentiment_count.sum()) == 0)

    feature_frame = add_sentiment_momentum_features(
        sentiment_frame,
        sentiment_momentum_window=sentiment_momentum_window,
        sentiment_baseline_window=sentiment_baseline_window,
        sentiment_momentum_threshold=0.0,
        sentiment_momentum_mode=DEFAULT_SENTIMENT_MOMENTUM_MODE,
    )
    usable_mask = pd.Series(
        feature_frame["sentiment_momentum_data_ready"],
        index=feature_frame.index,
        dtype="boolean",
    ).fillna(False)
    usable_row_count = int(usable_mask.sum())
    usable_dates = feature_frame.loc[usable_mask, "date"]

    inspection["usable_row_count"] = usable_row_count
    inspection["usable_date_start"] = (
        usable_dates.iloc[0].date().isoformat() if usable_row_count else None
    )
    inspection["usable_date_end"] = (
        usable_dates.iloc[-1].date().isoformat() if usable_row_count else None
    )
    inspection["usable_for_item7"] = usable_row_count > 0
    inspection["schema_status"] = "valid" if usable_row_count > 0 else "valid_but_unusable"
    inspection["readiness_status"] = "ready" if usable_row_count > 0 else "valid_but_unusable"

    if usable_row_count == 0:
        reasons: List[str] = []
        if inspection["insufficient_history"]:
            reasons.append(
                "Riwayat trading lebih pendek dari baseline sentiment window sehingga momentum belum bisa dihitung."
            )
        if inspection["no_articles_in_history"]:
            reasons.append(
                "Kolom sentimen ada tetapi seluruh sentiment_news_count_1d bernilai 0."
            )
        if not reasons:
            reasons.append(
                "Kolom sentimen valid tetapi belum menghasilkan window momentum yang usable."
            )
        inspection["invalid_reasons"] = reasons
        inspection["blocker_reason"] = "; ".join(reasons)
    else:
        inspection["blocker_reason"] = ""

    return inspection


def build_item7_data_readiness(
    folder_path: Path,
    tickers: Optional[Iterable[str]] = None,
    output_dir: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
    sentiment_momentum_window: int = DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    sentiment_baseline_window: int = DEFAULT_SENTIMENT_BASELINE_WINDOW,
) -> Dict[str, object]:
    """Build dataset-level readiness payload for Phase B item 7."""

    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    _, csv_files = _resolve_csv_files(
        folder_path=Path(folder_path),
        tickers=tickers,
        output_dir=output_dir,
        metadata_file=metadata_file,
    )

    per_ticker = [
        inspect_item7_sentiment_dataset(
            path,
            sentiment_momentum_window=sentiment_momentum_window,
            sentiment_baseline_window=sentiment_baseline_window,
        )
        for path in csv_files
    ]
    metadata_required = metadata_file is not None
    for item in per_ticker:
        ticker = str(item["ticker"]).upper().strip()
        metadata_present = ticker in metadata_lookup
        item["metadata_synced"] = (not metadata_required) or metadata_present
        item["metadata_status"] = (
            "synced"
            if item["metadata_synced"]
            else "missing_ticker_row"
            if metadata_required
            else "not_checked"
        )
        if metadata_required and not metadata_present:
            item["invalid_reasons"] = list(item.get("invalid_reasons") or [])
            item["invalid_reasons"].append(
                "Ticker tidak ditemukan di metadata_file sehingga grouping item 7 menjadi ambigu."
            )
            item["blocker_reason"] = "; ".join(item["invalid_reasons"])
            if str(item.get("readiness_status")) == "ready":
                item["readiness_status"] = "sentiment_schema_invalid"
                item["usable_for_item7"] = False
                item["schema_status"] = "sentiment_schema_invalid"

    selected_ticker_count = len(per_ticker)
    valid_tickers = [
        item["ticker"]
        for item in per_ticker
        if bool(item["usable_for_item7"]) and str(item["readiness_status"]) == "ready"
    ]
    invalid_tickers = [
        item["ticker"]
        for item in per_ticker
        if str(item["readiness_status"]) in {"ohlcv_only", "sentiment_schema_invalid"}
    ]
    unusable_tickers = [
        item["ticker"] for item in per_ticker if str(item["readiness_status"]) == "valid_but_unusable"
    ]
    insufficient_history_tickers = [
        item["ticker"] for item in per_ticker if bool(item["insufficient_history"])
    ]
    missing_columns = sorted(
        {
            column
            for item in per_ticker
            for column in list(item.get("missing_columns") or [])
        }
    )
    all_have_sentiment_columns = bool(per_ticker) and all(
        bool(item["dataset_has_sentiment_series"]) for item in per_ticker
    )
    metadata_synced_ticker_count = int(sum(1 for item in per_ticker if bool(item["metadata_synced"])))
    experiment_can_run = bool(valid_tickers) and not invalid_tickers

    if selected_ticker_count == 0:
        readiness_status = "not_available"
        next_action = "refresh_sentiment_data"
    elif invalid_tickers and not valid_tickers:
        if all(str(item["schema_status"]) == "ohlcv_only" for item in per_ticker):
            readiness_status = "blocked_missing_sentiment_series"
        else:
            readiness_status = "blocked_invalid_sentiment_schema"
        next_action = "refresh_sentiment_data"
    elif valid_tickers and not invalid_tickers and not unusable_tickers:
        readiness_status = "ready"
        next_action = "rerun_item7_experiment"
    elif unusable_tickers and not valid_tickers and not invalid_tickers:
        readiness_status = "blocked_insufficient_sentiment_history"
        next_action = "refresh_sentiment_data"
    else:
        readiness_status = "partial"
        next_action = "rerun_item7_experiment" if experiment_can_run else "refresh_sentiment_data"

    return {
        "generated_at": _now_iso(),
        "experiment_id": "phase_b_item7_data_readiness",
        "data_dir": str(Path(folder_path)),
        "metadata_file": str(metadata_file) if metadata_file is not None else None,
        "metadata_warnings": metadata_warnings,
        "required_columns": ITEM7_REQUIRED_DATASET_COLUMNS,
        "optional_columns": ITEM7_OPTIONAL_DATASET_COLUMNS,
        "sentiment_columns": list(SENTIMENT_DAILY_COLUMNS),
        "accepted_aliases": ITEM7_ACCEPTED_COLUMN_ALIASES,
        "invalid_patterns": ITEM7_INVALID_PATTERNS,
        "sentiment_momentum_window": int(sentiment_momentum_window),
        "sentiment_baseline_window": int(sentiment_baseline_window),
        "selected_ticker_count": int(selected_ticker_count),
        "dataset_has_sentiment_series": bool(all_have_sentiment_columns),
        "dataset_is_item7_ready": experiment_can_run,
        "experiment_can_run": experiment_can_run,
        "readiness_status": readiness_status,
        "valid_ticker_count": int(len(valid_tickers)),
        "invalid_ticker_count": int(len(invalid_tickers)),
        "unusable_ticker_count": int(len(unusable_tickers)),
        "metadata_synced_ticker_count": metadata_synced_ticker_count,
        "missing_columns": missing_columns,
        "invalid_tickers": invalid_tickers,
        "unusable_tickers": unusable_tickers,
        "insufficient_history_tickers": insufficient_history_tickers,
        "next_action": next_action,
        "per_ticker": _sanitize_for_json(per_ticker),
    }


def build_item7_schema_contract() -> Dict[str, object]:
    """Build the explicit CSV schema contract for Phase B item 7."""

    return {
        "generated_at": _now_iso(),
        "experiment_id": "phase_b_item7_schema_contract",
        "required_columns": ITEM7_REQUIRED_DATASET_COLUMNS,
        "optional_columns": ITEM7_OPTIONAL_DATASET_COLUMNS,
        "accepted_aliases": ITEM7_ACCEPTED_COLUMN_ALIASES,
        "invalid_patterns": ITEM7_INVALID_PATTERNS,
        "canonical_export_columns": ITEM7_REQUIRED_DATASET_COLUMNS,
        "canonical_export_note": (
            "Export resmi phase-a:export-real-data --include-sentiment-series selalu menulis "
            "nama kolom canonical. Alias hanya diterima untuk kompatibilitas evaluator."
        ),
        "example_valid_csv_header": ",".join(ITEM7_REQUIRED_DATASET_COLUMNS),
        "next_action_if_missing": "refresh_sentiment_data",
    }


def export_item7_schema_contract_artifacts(output_dir: Path) -> Dict[str, object]:
    """Write explicit schema-contract artifacts for item 7."""

    payload = build_item7_schema_contract()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "phase_b_item7_schema_contract.json"
    text_path = output_dir / "phase_b_item7_schema_contract.txt"
    json_path.write_text(
        json.dumps(_sanitize_for_json(payload), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    lines = [
        "Phase B Item 7 Schema Contract",
        "==============================",
        "",
        f"- Required columns: {', '.join(payload['required_columns'])}",
        f"- Optional columns: {', '.join(payload['optional_columns']) if payload['optional_columns'] else 'none'}",
        f"- Example valid CSV header: {payload['example_valid_csv_header']}",
        f"- Next action if missing: {payload['next_action_if_missing']}",
        "",
        "Accepted aliases:",
    ]
    for canonical, aliases in ITEM7_ACCEPTED_COLUMN_ALIASES.items():
        lines.append(f"- {canonical}: {', '.join(aliases) if aliases else 'none'}")
    lines.extend(["", "Invalid patterns:"])
    for pattern in ITEM7_INVALID_PATTERNS:
        lines.append(f"- {pattern}")
    lines.extend(
        [
            "",
            "Canonical export note:",
            f"- {payload['canonical_export_note']}",
        ]
    )
    text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved item 7 schema contract JSON to {json_path}")
    print(f"Saved item 7 schema contract report to {text_path}")
    return payload


def _build_item7_readiness_per_ticker_dataframe(
    per_ticker: Sequence[Dict[str, object]],
) -> pd.DataFrame:
    """Flatten item-7 readiness payload into a stable per-ticker CSV."""

    rows = []
    for item in per_ticker:
        rows.append(
            {
                "ticker": item.get("ticker"),
                "readiness_status": item.get("readiness_status"),
                "schema_status": item.get("schema_status"),
                "has_sentiment_columns": item.get("has_sentiment_columns"),
                "has_weighted_sentiment": item.get("has_weighted_sentiment"),
                "has_article_count": item.get("has_article_count"),
                "sufficient_history": item.get("sufficient_history"),
                "usable_for_item7": item.get("usable_for_item7"),
                "metadata_synced": item.get("metadata_synced"),
                "date_alignment_valid": item.get("date_alignment_valid"),
                "rows": item.get("rows"),
                "article_day_count": item.get("article_day_count"),
                "article_count_total": item.get("article_count_total"),
                "usable_row_count": item.get("usable_row_count"),
                "blocker_reason": item.get("blocker_reason"),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "ticker",
                "readiness_status",
                "schema_status",
                "has_sentiment_columns",
                "has_weighted_sentiment",
                "has_article_count",
                "sufficient_history",
                "usable_for_item7",
                "metadata_synced",
                "date_alignment_valid",
                "rows",
                "article_day_count",
                "article_count_total",
                "usable_row_count",
                "blocker_reason",
            ]
        )

    return pd.DataFrame(rows)


def export_item7_data_readiness_artifacts(
    folder_path: Path,
    output_dir: Path,
    tickers: Optional[Iterable[str]] = None,
    metadata_file: Optional[Path] = None,
    sentiment_momentum_window: int = DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    sentiment_baseline_window: int = DEFAULT_SENTIMENT_BASELINE_WINDOW,
) -> Dict[str, object]:
    """Write JSON/TXT readiness artifacts for Phase B item 7."""

    payload = build_item7_data_readiness(
        folder_path=folder_path,
        tickers=tickers,
        output_dir=output_dir,
        metadata_file=metadata_file,
        sentiment_momentum_window=sentiment_momentum_window,
        sentiment_baseline_window=sentiment_baseline_window,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    export_item7_schema_contract_artifacts(output_dir)
    readiness_json_path = output_dir / "phase_b_item7_data_readiness.json"
    readiness_report_path = output_dir / "phase_b_item7_data_readiness_report.txt"
    readiness_per_ticker_path = output_dir / "phase_b_item7_data_readiness_per_ticker.csv"

    readiness_json_path.write_text(
        json.dumps(_sanitize_for_json(payload), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    _build_item7_readiness_per_ticker_dataframe(payload["per_ticker"]).to_csv(
        readiness_per_ticker_path,
        index=False,
    )

    report_lines = [
        "Phase B Item 7 Data Readiness",
        "=============================",
        "",
        f"- Data dir: {payload['data_dir']}",
        f"- Readiness status: {payload['readiness_status']}",
        f"- Dataset has sentiment series: {payload['dataset_has_sentiment_series']}",
        f"- Dataset ready for item 7 rerun: {payload['dataset_is_item7_ready']}",
        f"- Experiment can run: {payload['experiment_can_run']}",
        f"- Selected ticker count: {payload['selected_ticker_count']}",
        f"- Valid ticker count: {payload['valid_ticker_count']}",
        f"- Invalid ticker count: {payload['invalid_ticker_count']}",
        f"- Unusable ticker count: {payload['unusable_ticker_count']}",
        f"- Metadata synced ticker count: {payload['metadata_synced_ticker_count']}",
        f"- Missing columns: {', '.join(payload['missing_columns']) if payload['missing_columns'] else 'none'}",
        f"- Insufficient history tickers: {', '.join(payload['insufficient_history_tickers']) if payload['insufficient_history_tickers'] else 'none'}",
        f"- Next action: {payload['next_action']}",
        "",
        "Required CSV schema:",
    ]
    for column in ITEM7_REQUIRED_DATASET_COLUMNS:
        report_lines.append(f"- {column}: {ITEM7_SENTIMENT_COLUMN_DESCRIPTIONS[column]}")

    report_lines.extend(
        [
            "",
            "Aggregation contract:",
            "- Sentiment columns must exist on every trading row for every ticker.",
            "- Sentiment values are aligned to each trade date using articles after the previous trade date up to the current trade date, inclusive.",
            "- No-article windows must be exported as 0.0 / 0.0 / 0, not blank cells.",
            "",
            "Per ticker status:",
        ]
    )
    for item in payload["per_ticker"]:
        reasons = list(item.get("invalid_reasons") or [])
        reason_text = "; ".join(reasons) if reasons else "ready"
        report_lines.append(
            f"- {item['ticker']}: readiness={item['readiness_status']}, schema={item['schema_status']}, "
            f"usable_for_item7={item['usable_for_item7']}, metadata_synced={item['metadata_synced']}, "
            f"rows={item['rows']}, article_count_total={item['article_count_total']}, "
            f"usable_row_count={item['usable_row_count']}, reason={reason_text}"
        )

    readiness_report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"Saved item 7 data readiness JSON to {readiness_json_path}")
    print(f"Saved item 7 data readiness report to {readiness_report_path}")
    print(f"Saved item 7 readiness per-ticker CSV to {readiness_per_ticker_path}")

    return payload


def export_item7_rerun_checklist(
    output_dir: Path,
    data_dir: Path,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
    sentiment_momentum_window: int = DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    sentiment_baseline_window: int = DEFAULT_SENTIMENT_BASELINE_WINDOW,
    sentiment_momentum_threshold: float = DEFAULT_SENTIMENT_MOMENTUM_THRESHOLD,
    sentiment_momentum_mode: str = DEFAULT_SENTIMENT_MOMENTUM_MODE,
) -> Path:
    """Write a short operational checklist for rerunning Phase B item 7."""

    output_dir.mkdir(parents=True, exist_ok=True)
    checklist_path = output_dir / "phase_b_item7_rerun_checklist.txt"
    export_command = (
        "php artisan phase-a:export-real-data "
        f"--data-dir={shlex.quote(str(data_dir))} "
        "--include-sentiment-series"
    )
    if metadata_file is not None:
        export_command += f" --metadata-file={shlex.quote(str(metadata_file))}"
    readiness_command = _item7_readiness_command(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=metadata_file,
        sentiment_momentum_window=sentiment_momentum_window,
        sentiment_baseline_window=sentiment_baseline_window,
    )
    experiment_command = _item7_experiment_command(
        data_dir=data_dir,
        output_dir=output_dir,
        baseline_config=baseline_config,
        metadata_file=metadata_file,
        sentiment_momentum_window=sentiment_momentum_window,
        sentiment_baseline_window=sentiment_baseline_window,
        sentiment_momentum_threshold=sentiment_momentum_threshold,
        sentiment_momentum_mode=sentiment_momentum_mode,
    )

    lines = [
        "Phase B Item 7 Rerun Checklist",
        "==============================",
        "",
        "1. Cek MySQL aktif dan koneksi aplikasi sudah bisa membuka 127.0.0.1:3306.",
        "2. Jalankan export real data dengan sentiment series:",
        export_command,
        "3. Validasi readiness dataset item 7:",
        readiness_command,
        "4. Rerun evaluator item 7:",
        experiment_command,
        "5. Baca keputusan final di output/phase_b_item7_go_no_go.json.",
    ]
    checklist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved item 7 rerun checklist to {checklist_path}")
    return checklist_path


def export_item7_execution_runbook(
    output_dir: Path,
    data_dir: Path,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
    sentiment_momentum_window: int = DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    sentiment_baseline_window: int = DEFAULT_SENTIMENT_BASELINE_WINDOW,
    sentiment_momentum_threshold: float = DEFAULT_SENTIMENT_MOMENTUM_THRESHOLD,
    sentiment_momentum_mode: str = DEFAULT_SENTIMENT_MOMENTUM_MODE,
) -> Path:
    """Write the operational runbook from DB recovery to final item-7 decision."""

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "phase_b_item7_execution_runbook.txt"
    export_command = (
        "php artisan phase-a:export-real-data "
        f"--data-dir={shlex.quote(str(data_dir))} "
        "--metadata-file="
        f"{shlex.quote(str(metadata_file if metadata_file is not None else data_dir / 'ticker_metadata.csv'))} "
        "--min-rows=50 "
        "--include-sentiment-series"
    )
    readiness_command = _item7_readiness_command(
        data_dir=data_dir,
        output_dir=output_dir,
        metadata_file=metadata_file,
        sentiment_momentum_window=sentiment_momentum_window,
        sentiment_baseline_window=sentiment_baseline_window,
    )
    experiment_command = _item7_experiment_command(
        data_dir=data_dir,
        output_dir=output_dir,
        baseline_config=baseline_config,
        metadata_file=metadata_file,
        sentiment_momentum_window=sentiment_momentum_window,
        sentiment_baseline_window=sentiment_baseline_window,
        sentiment_momentum_threshold=sentiment_momentum_threshold,
        sentiment_momentum_mode=sentiment_momentum_mode,
    )
    lines = [
        "Phase B Item 7 Execution Runbook",
        "================================",
        "",
        "Step 1 - Pulihkan DB / MySQL",
        "- Pastikan mysqld aktif dan aplikasi bisa membuka 127.0.0.1:3306.",
        "- Pastikan tabel stocks, stock_prices, dan news_articles berisi data yang up-to-date.",
        "",
        "Step 2 - Jalankan export sentiment series",
        export_command,
        "",
        "Step 3 - Validasi readiness dataset item 7",
        readiness_command,
        "- Baca output/phase_b_item7_data_readiness.json dan output/phase_b_item7_data_readiness_per_ticker.csv.",
        "- Lanjut jika dataset_is_item7_ready=true. Status bisa tetap partial bila ada subset ticker yang unusable tetapi sampel valid masih cukup untuk eksperimen.",
        "",
        "Step 4 - Rerun evaluator item 7",
        experiment_command,
        "",
        "Step 5 - Baca keputusan final",
        "- Cek output/phase_b_item7_go_no_go.json.",
        "- Decision final yang sah harus salah satu dari: no_go, keep_experimental, promote_for_subset, promote_global.",
        "",
        "Jika readiness belum ready",
        "- blocked_missing_sentiment_series: rerun export dengan --include-sentiment-series setelah DB valid.",
        "- sentiment_schema_invalid: perbaiki schema CSV agar cocok dengan phase_b_item7_schema_contract.",
        "- valid_but_unusable: tambahkan history/artikel sampai window 3d/7d menghasilkan sentiment_momentum_data_ready.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved item 7 execution runbook to {path}")
    return path


def _safe_metric(value: Optional[float | int]) -> float:
    """Normalize missing numeric metrics into NaN-friendly floats."""

    if value is None:
        return np.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _json_metric(value: Optional[float | int]) -> Optional[float]:
    """Convert a metric into a JSON-safe float or None."""

    numeric = _safe_metric(value)
    if pd.isna(numeric):
        return None
    return float(numeric)


def _now_iso() -> str:
    """Return a stable UTC timestamp for exported artifacts."""

    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: object, default: int = 0) -> int:
    """Convert scalars into int with a fallback."""

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _dedupe(items: Sequence[str]) -> List[str]:
    """Deduplicate ordered strings."""

    seen = set()
    ordered: List[str] = []
    for item in items:
        token = str(item).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _sanitize_for_json(value: object) -> object:
    """Recursively convert pandas/numpy payloads into JSON-safe primitives."""

    if isinstance(value, dict):
        return {str(key): _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _sanitize_for_json(value.item())
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def _record_strategy_metrics(prefix: str, result, target: Dict[str, object]) -> None:
    """Write one backtest result into the summary metric dictionary."""

    target[f"{prefix}_total_trades"] = int(result.total_trades)
    target[f"{prefix}_win_rate"] = _safe_metric(result.win_rate)
    target[f"{prefix}_average_return"] = _safe_metric(result.average_return)
    target[f"{prefix}_max_drawdown"] = _safe_metric(result.max_drawdown)


def evaluate_single_ticker(
    path: Path,
    hold_period: int = 5,
    allow_overlap: bool = False,
    evaluate_strict: bool = False,
    phase_a_volume_spike_threshold: float = 2.0,
    phase_a_strict_mode: bool = False,
    require_candle_volume_confirmation: bool = False,
    candle_volume_confirmation_threshold: float = 1.0,
    require_weekly_trend_confirmation: bool = False,
    weekly_trend_method: str = DEFAULT_WEEKLY_TREND_METHOD,
    weekly_require_slope_up: bool = False,
    require_sentiment_momentum: bool = False,
    sentiment_momentum_window: int = DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    sentiment_baseline_window: int = DEFAULT_SENTIMENT_BASELINE_WINDOW,
    sentiment_momentum_threshold: float = DEFAULT_SENTIMENT_MOMENTUM_THRESHOLD,
    sentiment_momentum_mode: str = DEFAULT_SENTIMENT_MOMENTUM_MODE,
    phase_a_baseline_source: Optional[str] = None,
) -> EvaluationRecord:
    """Evaluate one ticker CSV file and return backtest metrics."""

    ticker = extract_ticker_from_filename(path)
    frame, warnings = load_price_csv(path)

    # Run explicit feature functions first to make the evaluation flow easy to inspect.
    feature_frame = add_volume_features(frame, volume_spike_threshold=phase_a_volume_spike_threshold)
    feature_frame = add_trend_features(feature_frame)
    phase_a_frame = generate_phase_a_signal(
        feature_frame,
        strict=phase_a_strict_mode,
        volume_spike_threshold=phase_a_volume_spike_threshold,
        require_candle_volume_confirmation=require_candle_volume_confirmation,
        candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
        require_weekly_trend_confirmation=require_weekly_trend_confirmation,
        weekly_trend_method=weekly_trend_method,
        weekly_require_slope_up=weekly_require_slope_up,
        require_sentiment_momentum=require_sentiment_momentum,
        sentiment_momentum_window=sentiment_momentum_window,
        sentiment_baseline_window=sentiment_baseline_window,
        sentiment_momentum_threshold=sentiment_momentum_threshold,
        sentiment_momentum_mode=sentiment_momentum_mode,
    )

    comparison_summary, comparison_results, comparison_frame = compare_backtest_variants(
        phase_a_frame,
        hold_period=hold_period,
        allow_overlap=allow_overlap,
        volume_spike_threshold=phase_a_volume_spike_threshold,
    )
    _ = comparison_summary  # The per-ticker summary table is rebuilt below.

    phase_a_signal_column = "phase_a_signal_strict" if phase_a_strict_mode else "phase_a_signal"
    phase_a_default_result = backtest_signal_frame(
        phase_a_frame,
        signal_column=phase_a_signal_column,
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )

    strict_result = None
    if evaluate_strict:
        strict_frame = generate_phase_a_signal(
            feature_frame,
            strict=True,
            volume_spike_threshold=phase_a_volume_spike_threshold,
            require_candle_volume_confirmation=require_candle_volume_confirmation,
            candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
            require_weekly_trend_confirmation=require_weekly_trend_confirmation,
            weekly_trend_method=weekly_trend_method,
            weekly_require_slope_up=weekly_require_slope_up,
            require_sentiment_momentum=require_sentiment_momentum,
            sentiment_momentum_window=sentiment_momentum_window,
            sentiment_baseline_window=sentiment_baseline_window,
            sentiment_momentum_threshold=sentiment_momentum_threshold,
            sentiment_momentum_mode=sentiment_momentum_mode,
        )
        strict_result = backtest_signal_frame(
            strict_frame,
            signal_column="phase_a_signal_strict",
            hold_period=hold_period,
            allow_overlap=allow_overlap,
        )

    metrics: Dict[str, object] = {
        "ticker": ticker,
        "rows": int(len(comparison_frame)),
        "date_start": comparison_frame["date"].iloc[0],
        "date_end": comparison_frame["date"].iloc[-1],
        "phase_a_applied_threshold": float(phase_a_volume_spike_threshold),
        "phase_a_applied_strict_mode": bool(phase_a_strict_mode),
        "phase_b_candle_confirmation_enabled": bool(require_candle_volume_confirmation),
        "phase_b_candle_confirmation_threshold": float(candle_volume_confirmation_threshold),
        "phase_b_weekly_trend_enabled": bool(require_weekly_trend_confirmation),
        "phase_b_weekly_trend_method": (
            str(weekly_trend_method) if require_weekly_trend_confirmation else None
        ),
        "phase_b_weekly_require_slope_up": bool(weekly_require_slope_up),
        "phase_b_weekly_data_ready": bool(
            phase_a_frame["weekly_trend_data_ready"].any()
        )
        if "weekly_trend_data_ready" in phase_a_frame.columns
        else False,
        "phase_b_sentiment_momentum_enabled": bool(require_sentiment_momentum),
        "phase_b_sentiment_momentum_window": (
            int(sentiment_momentum_window) if require_sentiment_momentum else None
        ),
        "phase_b_sentiment_baseline_window": (
            int(sentiment_baseline_window) if require_sentiment_momentum else None
        ),
        "phase_b_sentiment_momentum_threshold": (
            float(sentiment_momentum_threshold) if require_sentiment_momentum else None
        ),
        "phase_b_sentiment_momentum_mode": (
            str(sentiment_momentum_mode) if require_sentiment_momentum else None
        ),
        "phase_b_sentiment_momentum_data_ready": bool(
            phase_a_frame["sentiment_momentum_data_ready"].any()
        )
        if "sentiment_momentum_data_ready" in phase_a_frame.columns
        else False,
        "phase_a_baseline_source": phase_a_baseline_source,
    }

    baseline_result = comparison_results["baseline_old"]
    volume_spike_result = comparison_results["baseline_plus_volume_spike"]
    baseline_phase_a_result = comparison_results["baseline_plus_volume_spike_ema50"]

    _record_strategy_metrics("baseline", baseline_result, metrics)
    _record_strategy_metrics("volume_spike", volume_spike_result, metrics)
    _record_strategy_metrics("baseline_phase_a", baseline_phase_a_result, metrics)
    _record_strategy_metrics("phase_a", phase_a_default_result, metrics)

    if strict_result is not None:
        _record_strategy_metrics("strict", strict_result, metrics)
    else:
        metrics["strict_total_trades"] = np.nan
        metrics["strict_win_rate"] = np.nan
        metrics["strict_average_return"] = np.nan
        metrics["strict_max_drawdown"] = np.nan

    metrics["delta_trades"] = _safe_metric(metrics["phase_a_total_trades"]) - _safe_metric(
        metrics["baseline_total_trades"]
    )
    metrics["delta_win_rate"] = _safe_metric(metrics["phase_a_win_rate"]) - _safe_metric(
        metrics["baseline_win_rate"]
    )
    metrics["delta_average_return"] = _safe_metric(
        metrics["phase_a_average_return"]
    ) - _safe_metric(metrics["baseline_average_return"])

    return EvaluationRecord(
        ticker=ticker,
        rows=int(len(comparison_frame)),
        date_start=comparison_frame["date"].iloc[0],
        date_end=comparison_frame["date"].iloc[-1],
        metrics=metrics,
        warnings=warnings,
    )


def build_summary_dataframe(results: Sequence[EvaluationRecord]) -> pd.DataFrame:
    """Convert successful evaluation records into one summary DataFrame."""

    if not results:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    summary = pd.DataFrame([record.metrics for record in results])
    summary = summary.reindex(columns=SUMMARY_COLUMNS)
    summary = summary.sort_values(["delta_win_rate", "delta_average_return"], ascending=False)
    summary = summary.reset_index(drop=True)
    return summary


def build_skipped_dataframe(skipped: Sequence[SkipRecord]) -> pd.DataFrame:
    """Build a DataFrame of skipped files and reasons."""

    if not skipped:
        return pd.DataFrame(columns=SKIPPED_COLUMNS)

    return pd.DataFrame(
        [{"ticker": item.ticker, "file_path": item.file_path, "reason": item.reason} for item in skipped]
    ).reindex(columns=SKIPPED_COLUMNS)


def _normalize_ticker_filter(tickers: Optional[Iterable[str]]) -> Optional[set[str]]:
    """Normalize CLI ticker filters."""

    if not tickers:
        return None

    normalized: set[str] = set()
    for item in tickers:
        for token in str(item).split(","):
            token = token.strip().upper()
            if token:
                normalized.add(token)
    return normalized or None


def _bootstrap_command(data_dir: Path) -> str:
    """Build the sample-data bootstrap command shown to users."""

    return f"python3 -m quant.bootstrap_sample_data --data-dir {shlex.quote(str(data_dir))}"


def _validator_command(data_dir: Path, output_dir: Optional[Path]) -> str:
    """Build the validator command shown to users."""

    resolved_output = output_dir if output_dir is not None else Path("output")
    return (
        "python3 -m quant.validate_price_data "
        f"--data-dir {shlex.quote(str(data_dir))} "
        f"--output-dir {shlex.quote(str(resolved_output))}"
    )


def _item7_readiness_command(
    data_dir: Path,
    output_dir: Optional[Path],
    metadata_file: Optional[Path] = None,
    sentiment_momentum_window: int = DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    sentiment_baseline_window: int = DEFAULT_SENTIMENT_BASELINE_WINDOW,
) -> str:
    """Build the item-7 readiness validation command."""

    resolved_output = output_dir if output_dir is not None else Path("output")
    command = [
        "python3",
        "-m",
        "quant.evaluate_phase_a_real_data",
        "--data-dir",
        str(data_dir),
        "--output-dir",
        str(resolved_output),
        "--validate-item7-readiness",
        "--sentiment-momentum-window",
        str(int(sentiment_momentum_window)),
        "--sentiment-baseline-window",
        str(int(sentiment_baseline_window)),
    ]
    if metadata_file is not None:
        command.extend(["--metadata-file", str(metadata_file)])
    return " ".join(shlex.quote(token) for token in command)


def _item7_experiment_command(
    data_dir: Path,
    output_dir: Optional[Path],
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
    sentiment_momentum_window: int = DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    sentiment_baseline_window: int = DEFAULT_SENTIMENT_BASELINE_WINDOW,
    sentiment_momentum_threshold: float = DEFAULT_SENTIMENT_MOMENTUM_THRESHOLD,
    sentiment_momentum_mode: str = DEFAULT_SENTIMENT_MOMENTUM_MODE,
) -> str:
    """Build the rerun command for the item-7 experiment."""

    resolved_output = output_dir if output_dir is not None else Path("output")
    command = [
        "python3",
        "-m",
        "quant.evaluate_phase_a_real_data",
        "--data-dir",
        str(data_dir),
        "--output-dir",
        str(resolved_output),
        "--require-sentiment-momentum",
        "--sentiment-momentum-window",
        str(int(sentiment_momentum_window)),
        "--sentiment-baseline-window",
        str(int(sentiment_baseline_window)),
        "--sentiment-momentum-threshold",
        str(float(sentiment_momentum_threshold)),
        "--sentiment-momentum-mode",
        str(sentiment_momentum_mode),
    ]
    if baseline_config is not None:
        command.extend(["--baseline-config", str(baseline_config)])
    if metadata_file is not None:
        command.extend(["--metadata-file", str(metadata_file)])
    return " ".join(shlex.quote(token) for token in command)


def _print_next_steps(steps: Sequence[str]) -> None:
    """Print actionable next-step suggestions."""

    cleaned_steps = [step for step in steps if step]
    if not cleaned_steps:
        return

    print("\nNext step suggestions:")
    for step in cleaned_steps:
        print(f"  {step}")


def build_candle_confirmation_experiment_dataframe(
    control_summary_df: pd.DataFrame,
    experiment_summary_df: pd.DataFrame,
    candle_volume_confirmation_threshold: float,
) -> pd.DataFrame:
    """Compare the control Phase A arm with the candle-confirmed experiment arm."""

    if control_summary_df.empty or experiment_summary_df.empty:
        return pd.DataFrame(columns=CANDLE_CONFIRMATION_EXPERIMENT_COLUMNS)

    control_columns = {
        "rows": "rows",
        "date_start": "date_start",
        "date_end": "date_end",
        "phase_a_applied_threshold": "phase_a_applied_threshold",
        "phase_a_applied_strict_mode": "phase_a_applied_strict_mode",
        "phase_a_total_trades": "control_phase_a_total_trades",
        "phase_a_win_rate": "control_phase_a_win_rate",
        "phase_a_average_return": "control_phase_a_average_return",
        "phase_a_max_drawdown": "control_phase_a_max_drawdown",
        "phase_a_baseline_source": "phase_a_baseline_source",
    }
    experiment_columns = {
        "phase_a_total_trades": "experiment_phase_a_total_trades",
        "phase_a_win_rate": "experiment_phase_a_win_rate",
        "phase_a_average_return": "experiment_phase_a_average_return",
        "phase_a_max_drawdown": "experiment_phase_a_max_drawdown",
    }

    control_df = control_summary_df.loc[:, ["ticker", *control_columns.keys()]].rename(
        columns=control_columns
    )
    experiment_df = experiment_summary_df.loc[:, ["ticker", *experiment_columns.keys()]].rename(
        columns=experiment_columns
    )

    merged = control_df.merge(experiment_df, on="ticker", how="outer", indicator=True)
    merged = merged.loc[merged["_merge"] == "both"].drop(columns="_merge")

    if merged.empty:
        return pd.DataFrame(columns=CANDLE_CONFIRMATION_EXPERIMENT_COLUMNS)

    merged["delta_phase_a_total_trades"] = (
        pd.to_numeric(merged["experiment_phase_a_total_trades"], errors="coerce")
        - pd.to_numeric(merged["control_phase_a_total_trades"], errors="coerce")
    )
    control_trades = pd.to_numeric(merged["control_phase_a_total_trades"], errors="coerce")
    experiment_trades = pd.to_numeric(merged["experiment_phase_a_total_trades"], errors="coerce")
    merged["trade_retention_pct"] = np.where(
        control_trades > 0,
        (experiment_trades / control_trades) * 100.0,
        np.nan,
    )
    merged["delta_phase_a_win_rate"] = (
        pd.to_numeric(merged["experiment_phase_a_win_rate"], errors="coerce")
        - pd.to_numeric(merged["control_phase_a_win_rate"], errors="coerce")
    )
    merged["delta_phase_a_average_return"] = (
        pd.to_numeric(merged["experiment_phase_a_average_return"], errors="coerce")
        - pd.to_numeric(merged["control_phase_a_average_return"], errors="coerce")
    )
    merged["delta_phase_a_max_drawdown"] = (
        pd.to_numeric(merged["experiment_phase_a_max_drawdown"], errors="coerce")
        - pd.to_numeric(merged["control_phase_a_max_drawdown"], errors="coerce")
    )
    merged["candle_volume_confirmation_threshold"] = float(candle_volume_confirmation_threshold)

    merged = merged.reindex(columns=CANDLE_CONFIRMATION_EXPERIMENT_COLUMNS)
    merged = merged.sort_values(
        ["delta_phase_a_average_return", "delta_phase_a_win_rate", "delta_phase_a_total_trades"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    return merged


def build_candle_confirmation_experiment_summary(
    comparison_df: pd.DataFrame,
    candle_volume_confirmation_threshold: float,
    baseline_config: Optional[Path] = None,
) -> Dict[str, object]:
    """Build aggregate JSON payload for the official Phase B item 5 experiment."""

    if comparison_df.empty:
        return {
            "generated_at": _now_iso(),
            "experiment_id": "phase_b_item5_candle_confirmation",
            "comparison_status": "not_available",
            "reason": "Control and experiment arms did not produce overlapping ticker results.",
            "control_arm": {
                "baseline_config": str(baseline_config) if baseline_config else None,
                "candle_confirmation_enabled": False,
            },
            "experiment_arm": {
                "candle_confirmation_enabled": True,
                "candle_volume_confirmation_threshold": float(candle_volume_confirmation_threshold),
            },
            "aggregate": {
                "ticker_count": 0,
                "delta_phase_a_total_trades_sum": 0.0,
                "delta_phase_a_win_rate_mean": None,
                "delta_phase_a_average_return_mean": None,
                "delta_phase_a_max_drawdown_mean": None,
            },
        }

    control_trades = pd.to_numeric(comparison_df["control_phase_a_total_trades"], errors="coerce")
    experiment_trades = pd.to_numeric(
        comparison_df["experiment_phase_a_total_trades"], errors="coerce"
    )
    delta_avg_return = pd.to_numeric(
        comparison_df["delta_phase_a_average_return"], errors="coerce"
    )
    delta_win_rate = pd.to_numeric(comparison_df["delta_phase_a_win_rate"], errors="coerce")
    delta_drawdown = pd.to_numeric(
        comparison_df["delta_phase_a_max_drawdown"], errors="coerce"
    )

    best_avg = comparison_df.sort_values(
        ["delta_phase_a_average_return", "delta_phase_a_win_rate"],
        ascending=[False, False],
    ).head(5)
    biggest_trade_cut = comparison_df.sort_values(
        ["delta_phase_a_total_trades", "delta_phase_a_average_return"],
        ascending=[True, False],
    ).head(5)

    return {
        "generated_at": _now_iso(),
        "experiment_id": "phase_b_item5_candle_confirmation",
        "comparison_status": "measured",
        "comparison_scope": "baseline_phase_a_vs_baseline_plus_candle_confirmation",
        "control_arm": {
            "baseline_config": str(baseline_config) if baseline_config else None,
            "candle_confirmation_enabled": False,
        },
        "experiment_arm": {
            "candle_confirmation_enabled": True,
            "candle_volume_confirmation_threshold": float(candle_volume_confirmation_threshold),
        },
        "aggregate": {
            "ticker_count": int(len(comparison_df)),
            "control_phase_a_total_trades_sum": float(control_trades.sum()),
            "experiment_phase_a_total_trades_sum": float(experiment_trades.sum()),
            "delta_phase_a_total_trades_sum": float(
                pd.to_numeric(comparison_df["delta_phase_a_total_trades"], errors="coerce").sum()
            ),
            "trade_retention_mean_pct": _json_metric(
                pd.to_numeric(comparison_df["trade_retention_pct"], errors="coerce").mean()
            ),
            "delta_phase_a_win_rate_mean": _json_metric(delta_win_rate.mean()),
            "delta_phase_a_average_return_mean": _json_metric(delta_avg_return.mean()),
            "delta_phase_a_max_drawdown_mean": _json_metric(delta_drawdown.mean()),
            "tickers_with_trade_reduction": int(
                (pd.to_numeric(comparison_df["delta_phase_a_total_trades"], errors="coerce") < 0).sum()
            ),
            "tickers_with_win_rate_improvement": int((delta_win_rate > 0).sum()),
            "tickers_with_average_return_improvement": int((delta_avg_return > 0).sum()),
            "tickers_with_lower_drawdown": int((delta_drawdown < 0).sum()),
        },
        "top_average_return_improvements": [
            {
                "ticker": str(row["ticker"]),
                "delta_phase_a_average_return": _json_metric(row["delta_phase_a_average_return"]),
                "delta_phase_a_win_rate": _json_metric(row["delta_phase_a_win_rate"]),
                "delta_phase_a_total_trades": _json_metric(row["delta_phase_a_total_trades"]),
            }
            for _, row in best_avg.iterrows()
        ],
        "largest_trade_reductions": [
            {
                "ticker": str(row["ticker"]),
                "delta_phase_a_total_trades": _json_metric(row["delta_phase_a_total_trades"]),
                "trade_retention_pct": _json_metric(row["trade_retention_pct"]),
                "delta_phase_a_average_return": _json_metric(row["delta_phase_a_average_return"]),
            }
            for _, row in biggest_trade_cut.iterrows()
        ],
    }


def build_multitimeframe_experiment_dataframe(
    control_summary_df: pd.DataFrame,
    experiment_summary_df: pd.DataFrame,
    weekly_trend_method: str,
    weekly_require_slope_up: bool,
    metadata_lookup: Optional[Dict[str, Dict[str, object]]] = None,
) -> pd.DataFrame:
    """Compare control Phase A versus the weekly-trend-filtered candidate."""

    if control_summary_df.empty or experiment_summary_df.empty:
        return pd.DataFrame(columns=MULTITIMEFRAME_EXPERIMENT_COLUMNS)

    control_columns = {
        "rows": "rows",
        "date_start": "date_start",
        "date_end": "date_end",
        "phase_a_applied_threshold": "phase_a_applied_threshold",
        "phase_a_applied_strict_mode": "phase_a_applied_strict_mode",
        "phase_a_total_trades": "baseline_total_trades",
        "phase_a_win_rate": "baseline_win_rate",
        "phase_a_average_return": "baseline_average_return",
        "phase_a_max_drawdown": "baseline_max_drawdown",
        "phase_a_baseline_source": "phase_a_baseline_source",
    }
    experiment_columns = {
        "phase_a_total_trades": "candidate_total_trades",
        "phase_a_win_rate": "candidate_win_rate",
        "phase_a_average_return": "candidate_average_return",
        "phase_a_max_drawdown": "candidate_max_drawdown",
        "phase_b_weekly_data_ready": "weekly_data_ready",
    }

    control_df = control_summary_df.loc[:, ["ticker", *control_columns.keys()]].rename(
        columns=control_columns
    )
    experiment_df = experiment_summary_df.loc[:, ["ticker", *experiment_columns.keys()]].rename(
        columns=experiment_columns
    )

    merged = control_df.merge(experiment_df, on="ticker", how="outer", indicator=True)
    merged = merged.loc[merged["_merge"] == "both"].drop(columns="_merge")
    if merged.empty:
        return pd.DataFrame(columns=MULTITIMEFRAME_EXPERIMENT_COLUMNS)

    merged["delta_total_trades"] = (
        pd.to_numeric(merged["candidate_total_trades"], errors="coerce")
        - pd.to_numeric(merged["baseline_total_trades"], errors="coerce")
    )
    baseline_trades = pd.to_numeric(merged["baseline_total_trades"], errors="coerce")
    candidate_trades = pd.to_numeric(merged["candidate_total_trades"], errors="coerce")
    merged["trade_retention_pct"] = np.where(
        baseline_trades > 0,
        (candidate_trades / baseline_trades) * 100.0,
        np.nan,
    )
    merged["delta_win_rate"] = (
        pd.to_numeric(merged["candidate_win_rate"], errors="coerce")
        - pd.to_numeric(merged["baseline_win_rate"], errors="coerce")
    )
    merged["delta_average_return"] = (
        pd.to_numeric(merged["candidate_average_return"], errors="coerce")
        - pd.to_numeric(merged["baseline_average_return"], errors="coerce")
    )
    merged["delta_max_drawdown"] = (
        pd.to_numeric(merged["candidate_max_drawdown"], errors="coerce")
        - pd.to_numeric(merged["baseline_max_drawdown"], errors="coerce")
    )
    merged["weekly_trend_method"] = str(weekly_trend_method)
    merged["weekly_require_slope_up"] = bool(weekly_require_slope_up)

    for column in ["category", "market_cap_group", "sector", "beta_group"]:
        merged[column] = pd.Series([None] * len(merged), index=merged.index, dtype="object")
    if metadata_lookup:
        for index, ticker in merged["ticker"].items():
            metadata_row = (metadata_lookup or {}).get(str(ticker).upper().strip(), {})
            for column in ["category", "market_cap_group", "sector", "beta_group"]:
                merged.at[index, column] = metadata_row.get(column)

    merged = merged.reindex(columns=MULTITIMEFRAME_EXPERIMENT_COLUMNS)
    merged = merged.sort_values(
        ["delta_average_return", "delta_win_rate", "delta_total_trades"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    return merged


def build_multitimeframe_experiment_summary(
    comparison_df: pd.DataFrame,
    weekly_trend_method: str,
    weekly_require_slope_up: bool,
    baseline_config: Optional[Path] = None,
) -> Dict[str, object]:
    """Build aggregate JSON payload for the weekly trend confirmation experiment."""

    if comparison_df.empty:
        return {
            "generated_at": _now_iso(),
            "experiment_id": "phase_b_item6_multitimeframe",
            "comparison_status": "not_available",
            "reason": "Control and weekly-filter experiment arms did not produce overlapping ticker results.",
            "control_arm": {
                "baseline_config": str(baseline_config) if baseline_config else None,
                "weekly_trend_enabled": False,
            },
            "experiment_arm": {
                "weekly_trend_enabled": True,
                "weekly_trend_method": str(weekly_trend_method),
                "weekly_require_slope_up": bool(weekly_require_slope_up),
            },
            "aggregate": {
                "ticker_count": 0,
                "delta_total_trades_sum": 0.0,
                "delta_win_rate_mean": None,
                "delta_average_return_mean": None,
                "delta_max_drawdown_mean": None,
            },
        }

    delta_avg = pd.to_numeric(comparison_df["delta_average_return"], errors="coerce")
    delta_win = pd.to_numeric(comparison_df["delta_win_rate"], errors="coerce")
    delta_drawdown = pd.to_numeric(comparison_df["delta_max_drawdown"], errors="coerce")
    baseline_trades = pd.to_numeric(comparison_df["baseline_total_trades"], errors="coerce")
    candidate_trades = pd.to_numeric(comparison_df["candidate_total_trades"], errors="coerce")
    ready_count = int(pd.Series(comparison_df["weekly_data_ready"]).fillna(False).astype(bool).sum())

    group_snapshots: List[Dict[str, object]] = []
    for field in ["market_cap_group", "sector", "category", "beta_group"]:
        if field not in comparison_df.columns:
            continue
        working = comparison_df.loc[
            comparison_df[field].notna() & comparison_df[field].astype(str).str.strip().ne("")
        ].copy()
        if working.empty:
            continue
        grouped = (
            working.groupby(field)
            .agg(
                ticker_count=("ticker", "count"),
                trade_retention_mean_pct=("trade_retention_pct", "mean"),
                delta_win_rate_mean=("delta_win_rate", "mean"),
                delta_average_return_mean=("delta_average_return", "mean"),
                delta_max_drawdown_mean=("delta_max_drawdown", "mean"),
            )
            .reset_index()
            .rename(columns={field: "group_value"})
        )
        grouped["group_field"] = field
        group_snapshots.extend(grouped.to_dict(orient="records"))

    return {
        "generated_at": _now_iso(),
        "experiment_id": "phase_b_item6_multitimeframe",
        "comparison_status": "measured",
        "comparison_scope": "baseline_phase_a_vs_baseline_plus_weekly_filter",
        "control_arm": {
            "baseline_config": str(baseline_config) if baseline_config else None,
            "weekly_trend_enabled": False,
        },
        "experiment_arm": {
            "weekly_trend_enabled": True,
            "weekly_trend_method": str(weekly_trend_method),
            "weekly_require_slope_up": bool(weekly_require_slope_up),
        },
        "aggregate": {
            "ticker_count": int(len(comparison_df)),
            "weekly_data_ready_ticker_count": ready_count,
            "comparable_ticker_count": int(
                (
                    pd.to_numeric(comparison_df["baseline_total_trades"], errors="coerce") > 0
                ).sum()
            ),
            "baseline_total_trades_sum": float(baseline_trades.sum()),
            "candidate_total_trades_sum": float(candidate_trades.sum()),
            "delta_total_trades_sum": float(pd.to_numeric(comparison_df["delta_total_trades"], errors="coerce").sum()),
            "trade_retention_mean_pct": _json_metric(pd.to_numeric(comparison_df["trade_retention_pct"], errors="coerce").mean()),
            "delta_win_rate_mean": _json_metric(delta_win.mean()),
            "delta_average_return_mean": _json_metric(delta_avg.mean()),
            "delta_max_drawdown_mean": _json_metric(delta_drawdown.mean()),
            "tickers_with_trade_reduction": int((pd.to_numeric(comparison_df["delta_total_trades"], errors="coerce") < 0).sum()),
            "tickers_with_win_rate_improvement": int((delta_win > 0).sum()),
            "tickers_with_average_return_improvement": int((delta_avg > 0).sum()),
            "tickers_with_lower_drawdown": int((delta_drawdown < 0).sum()),
        },
        "group_snapshots": _sanitize_for_json(group_snapshots),
    }


def build_multitimeframe_go_no_go(
    comparison_df: pd.DataFrame,
    summary_payload: Dict[str, object],
) -> Dict[str, object]:
    """Determine the go/no-go posture for the multi-timeframe experiment."""

    if comparison_df.empty:
        return {
            "decision": "keep_experimental",
            "experiment_status": "pending",
            "promote_default": False,
            "promote_subset_only": False,
            "recommended_tickers": [],
            "recommended_groups": [],
            "next_action": "continue_tuning",
            "blocked_from_default": ["Eksperimen item 6 belum menghasilkan perbandingan yang bisa dinilai."],
        }

    ready_mask = pd.Series(comparison_df["weekly_data_ready"]).fillna(False).astype(bool)
    ready_df = comparison_df.loc[ready_mask].copy()
    comparable_mask = ready_mask & (
        pd.to_numeric(comparison_df["baseline_total_trades"], errors="coerce") > 0
    )
    comparable_df = comparison_df.loc[comparable_mask].copy()
    working_df = comparable_df if not comparable_df.empty else ready_df
    if working_df.empty:
        working_df = comparison_df.copy()

    retention = pd.to_numeric(working_df["trade_retention_pct"], errors="coerce")
    delta_avg = pd.to_numeric(working_df["delta_average_return"], errors="coerce")
    delta_win = pd.to_numeric(working_df["delta_win_rate"], errors="coerce")
    delta_drawdown = pd.to_numeric(working_df["delta_max_drawdown"], errors="coerce")
    candidate_trades = pd.to_numeric(working_df["candidate_total_trades"], errors="coerce")

    improve_mask = (
        (candidate_trades > 0)
        & (retention >= 60.0)
        & ((delta_avg > 0) | (delta_win > 0))
        & (delta_drawdown <= 0.5)
    )
    worsen_mask = (
        (candidate_trades <= 0)
        | (retention < 60.0)
        | (delta_avg < 0)
        | (delta_win < 0)
        | (delta_drawdown > 0.5)
    )

    improve_tickers = working_df.loc[improve_mask, "ticker"].astype(str).tolist()
    improve_count = int(len(improve_tickers))
    worsen_count = int(worsen_mask.sum())
    ticker_count = int(len(working_df))
    improve_share = (improve_count / ticker_count) if ticker_count else 0.0
    worsen_share = (worsen_count / ticker_count) if ticker_count else 0.0

    recommended_groups: List[str] = []
    for field in ["market_cap_group", "sector", "category", "beta_group"]:
        if field not in working_df.columns:
            continue
        grouped = (
            working_df.loc[working_df[field].notna() & working_df[field].astype(str).str.strip().ne("")]
            .groupby(field)
            .agg(
                ticker_count=("ticker", "count"),
                improve_count=("ticker", lambda values: int(
                    improve_mask.loc[values.index].sum()
                )),
                worsen_count=("ticker", lambda values: int(
                    worsen_mask.loc[values.index].sum()
                )),
                trade_retention_mean_pct=("trade_retention_pct", "mean"),
                delta_average_return_mean=("delta_average_return", "mean"),
                delta_win_rate_mean=("delta_win_rate", "mean"),
            )
            .reset_index()
        )
        for _, row in grouped.iterrows():
            if (
                int(row["ticker_count"]) >= 2
                and int(row["improve_count"]) > int(row["worsen_count"])
                and _safe_metric(row["trade_retention_mean_pct"]) >= 60.0
                and _safe_metric(row["delta_average_return_mean"]) >= 0
                and _safe_metric(row["delta_win_rate_mean"]) >= 0
            ):
                recommended_groups.append(f"{field}={row[field]}")

    blocked_from_default: List[str] = []
    aggregate = summary_payload.get("aggregate", {})
    comparable_ticker_count = _safe_int(aggregate.get("comparable_ticker_count"))
    if _safe_int(aggregate.get("weekly_data_ready_ticker_count")) == 0:
        blocked_from_default.append("Weekly history belum cukup matang untuk ticker yang diuji.")
    if comparable_ticker_count == 0:
        blocked_from_default.append("Belum ada ticker dengan trade baseline Phase A yang cukup untuk dibandingkan.")
    if comparable_ticker_count < 3:
        blocked_from_default.append("Sampel ticker comparable masih terlalu kecil untuk promosi resmi.")
    if _safe_metric(aggregate.get("trade_retention_mean_pct")) < 75.0:
        blocked_from_default.append("Trade retention rata-rata masih terlalu rendah.")
    if _safe_metric(aggregate.get("delta_average_return_mean")) <= 0:
        blocked_from_default.append("Average return rata-rata tidak membaik.")
    if _safe_metric(aggregate.get("delta_win_rate_mean")) < 0:
        blocked_from_default.append("Win rate rata-rata tidak membaik.")
    if improve_count == 0:
        blocked_from_default.append("Tidak ada ticker comparable yang improve dengan retention memadai.")
    if worsen_count >= improve_count:
        blocked_from_default.append("Ticker yang memburuk minimal sama banyak dengan yang improve.")

    if (
        improve_share >= 0.6
        and worsen_share <= 0.2
        and _safe_metric(aggregate.get("delta_average_return_mean")) > 0
        and _safe_metric(aggregate.get("delta_win_rate_mean")) >= 0
        and _safe_metric(aggregate.get("trade_retention_mean_pct")) >= 75.0
        and comparable_ticker_count >= 5
        and _safe_int(aggregate.get("weekly_data_ready_ticker_count")) >= max(3, math.ceil(ticker_count * 0.5))
    ):
        decision = "promote_global"
        next_action = "promote_global"
    elif comparable_ticker_count >= 3 and (recommended_groups or len(improve_tickers) >= 2):
        decision = "promote_for_subset"
        next_action = "promote_subset"
    elif _safe_int(aggregate.get("weekly_data_ready_ticker_count")) == 0 or comparable_ticker_count < 3:
        decision = "keep_experimental"
        next_action = "continue_tuning"
    elif improve_count > 0:
        decision = "keep_experimental"
        next_action = "continue_tuning"
    else:
        decision = "no_go"
        next_action = "stop"

    return {
        "decision": decision,
        "experiment_status": "completed",
        "promote_default": decision == "promote_global",
        "promote_subset_only": decision == "promote_for_subset",
        "recommended_tickers": improve_tickers if decision in {"promote_for_subset", "promote_global"} else [],
        "recommended_groups": recommended_groups if decision == "promote_for_subset" else [],
        "next_action": next_action,
        "blocked_from_default": _dedupe(blocked_from_default),
    }


def export_multitimeframe_experiment_results(
    control_summary_df: pd.DataFrame,
    experiment_summary_df: pd.DataFrame,
    output_dir: Path,
    weekly_trend_method: str,
    weekly_require_slope_up: bool,
    baseline_config: Optional[Path] = None,
    metadata_lookup: Optional[Dict[str, Dict[str, object]]] = None,
) -> Tuple[pd.DataFrame, Dict[str, object], Dict[str, object]]:
    """Export per-ticker and aggregate artifacts for the weekly trend experiment."""

    comparison_df = build_multitimeframe_experiment_dataframe(
        control_summary_df=control_summary_df,
        experiment_summary_df=experiment_summary_df,
        weekly_trend_method=weekly_trend_method,
        weekly_require_slope_up=weekly_require_slope_up,
        metadata_lookup=metadata_lookup,
    )
    summary_payload = build_multitimeframe_experiment_summary(
        comparison_df=comparison_df,
        weekly_trend_method=weekly_trend_method,
        weekly_require_slope_up=weekly_require_slope_up,
        baseline_config=baseline_config,
    )
    go_no_go_payload = build_multitimeframe_go_no_go(
        comparison_df=comparison_df,
        summary_payload=summary_payload,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    per_ticker_path = output_dir / "phase_b_item6_multitimeframe_per_ticker.csv"
    summary_path = output_dir / "phase_b_item6_multitimeframe_summary.json"
    report_path = output_dir / "phase_b_item6_multitimeframe_report.txt"
    go_no_go_path = output_dir / "phase_b_item6_go_no_go.json"

    comparison_df.to_csv(per_ticker_path, index=False)
    summary_path.write_text(
        json.dumps(_sanitize_for_json(summary_payload), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    go_no_go_path.write_text(
        json.dumps(_sanitize_for_json(go_no_go_payload), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    report_lines = [
        "Phase B Item 6 Multi-Timeframe Experiment",
        "==========================================",
        "",
        f"- Comparison status: {summary_payload['comparison_status']}",
        f"- Baseline config: {summary_payload['control_arm']['baseline_config'] or 'runtime defaults'}",
        f"- Weekly trend method: {summary_payload['experiment_arm']['weekly_trend_method']}",
        f"- Weekly slope required: {summary_payload['experiment_arm']['weekly_require_slope_up']}",
        f"- Ticker count: {_safe_int(summary_payload['aggregate']['ticker_count'])}",
        f"- Weekly-data-ready tickers: {_safe_int(summary_payload['aggregate'].get('weekly_data_ready_ticker_count'))}",
        f"- Comparable baseline tickers: {_safe_int(summary_payload['aggregate'].get('comparable_ticker_count'))}",
        f"- Delta total trades sum: {_safe_metric(summary_payload['aggregate']['delta_total_trades_sum'])}",
        f"- Mean delta win rate: {_safe_metric(summary_payload['aggregate']['delta_win_rate_mean'])}",
        f"- Mean delta average return: {_safe_metric(summary_payload['aggregate']['delta_average_return_mean'])}",
        f"- Mean delta max drawdown: {_safe_metric(summary_payload['aggregate']['delta_max_drawdown_mean'])}",
        "",
        "Decision:",
        f"- {go_no_go_payload['decision']}",
        f"- next_action={go_no_go_payload['next_action']}",
    ]

    blocked = list(go_no_go_payload.get("blocked_from_default") or [])
    if blocked:
        report_lines.extend(["", "Blocked from default:"])
        for item in blocked:
            report_lines.append(f"- {item}")

    recommended_tickers = list(go_no_go_payload.get("recommended_tickers") or [])
    if recommended_tickers:
        report_lines.extend(["", "Recommended tickers:"])
        for item in recommended_tickers:
            report_lines.append(f"- {item}")

    recommended_groups = list(go_no_go_payload.get("recommended_groups") or [])
    if recommended_groups:
        report_lines.extend(["", "Recommended groups:"])
        for item in recommended_groups:
            report_lines.append(f"- {item}")

    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"Saved multi-timeframe experiment CSV to {per_ticker_path}")
    print(f"Saved multi-timeframe experiment JSON to {summary_path}")
    print(f"Saved multi-timeframe experiment report to {report_path}")
    print(f"Saved multi-timeframe go/no-go JSON to {go_no_go_path}")

    return comparison_df, summary_payload, go_no_go_payload


def build_sentiment_momentum_experiment_dataframe(
    control_summary_df: pd.DataFrame,
    experiment_summary_df: pd.DataFrame,
    sentiment_momentum_mode: str,
    sentiment_momentum_window: int,
    sentiment_baseline_window: int,
    sentiment_momentum_threshold: float,
    metadata_lookup: Optional[Dict[str, Dict[str, object]]] = None,
) -> pd.DataFrame:
    """Compare control Phase A versus the sentiment-momentum-gated candidate."""

    if control_summary_df.empty or experiment_summary_df.empty:
        return pd.DataFrame(columns=SENTIMENT_MOMENTUM_EXPERIMENT_COLUMNS)

    control_columns = {
        "rows": "rows",
        "date_start": "date_start",
        "date_end": "date_end",
        "phase_a_applied_threshold": "phase_a_applied_threshold",
        "phase_a_applied_strict_mode": "phase_a_applied_strict_mode",
        "phase_a_total_trades": "baseline_total_trades",
        "phase_a_win_rate": "baseline_win_rate",
        "phase_a_average_return": "baseline_average_return",
        "phase_a_max_drawdown": "baseline_max_drawdown",
        "phase_a_baseline_source": "phase_a_baseline_source",
    }
    experiment_columns = {
        "phase_a_total_trades": "candidate_total_trades",
        "phase_a_win_rate": "candidate_win_rate",
        "phase_a_average_return": "candidate_average_return",
        "phase_a_max_drawdown": "candidate_max_drawdown",
        "phase_b_sentiment_momentum_data_ready": "sentiment_data_ready",
    }

    control_df = control_summary_df.loc[:, ["ticker", *control_columns.keys()]].rename(
        columns=control_columns
    )
    experiment_df = experiment_summary_df.loc[:, ["ticker", *experiment_columns.keys()]].rename(
        columns=experiment_columns
    )

    merged = control_df.merge(experiment_df, on="ticker", how="outer", indicator=True)
    merged = merged.loc[merged["_merge"] == "both"].drop(columns="_merge")
    if merged.empty:
        return pd.DataFrame(columns=SENTIMENT_MOMENTUM_EXPERIMENT_COLUMNS)

    merged["delta_total_trades"] = (
        pd.to_numeric(merged["candidate_total_trades"], errors="coerce")
        - pd.to_numeric(merged["baseline_total_trades"], errors="coerce")
    )
    baseline_trades = pd.to_numeric(merged["baseline_total_trades"], errors="coerce")
    candidate_trades = pd.to_numeric(merged["candidate_total_trades"], errors="coerce")
    merged["trade_retention_pct"] = np.where(
        baseline_trades > 0,
        (candidate_trades / baseline_trades) * 100.0,
        np.nan,
    )
    merged["delta_win_rate"] = (
        pd.to_numeric(merged["candidate_win_rate"], errors="coerce")
        - pd.to_numeric(merged["baseline_win_rate"], errors="coerce")
    )
    merged["delta_average_return"] = (
        pd.to_numeric(merged["candidate_average_return"], errors="coerce")
        - pd.to_numeric(merged["baseline_average_return"], errors="coerce")
    )
    merged["delta_max_drawdown"] = (
        pd.to_numeric(merged["candidate_max_drawdown"], errors="coerce")
        - pd.to_numeric(merged["baseline_max_drawdown"], errors="coerce")
    )
    merged["sentiment_momentum_mode"] = str(sentiment_momentum_mode)
    merged["sentiment_momentum_window"] = int(sentiment_momentum_window)
    merged["sentiment_baseline_window"] = int(sentiment_baseline_window)
    merged["sentiment_momentum_threshold"] = float(sentiment_momentum_threshold)

    for column in ["category", "market_cap_group", "sector", "beta_group"]:
        merged[column] = pd.Series([None] * len(merged), index=merged.index, dtype="object")
    if metadata_lookup:
        for index, ticker in merged["ticker"].items():
            metadata_row = (metadata_lookup or {}).get(str(ticker).upper().strip(), {})
            for column in ["category", "market_cap_group", "sector", "beta_group"]:
                merged.at[index, column] = metadata_row.get(column)

    merged = merged.reindex(columns=SENTIMENT_MOMENTUM_EXPERIMENT_COLUMNS)
    merged = merged.sort_values(
        ["delta_average_return", "delta_win_rate", "delta_total_trades"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    return merged


def build_sentiment_momentum_experiment_summary(
    comparison_df: pd.DataFrame,
    sentiment_momentum_mode: str,
    sentiment_momentum_window: int,
    sentiment_baseline_window: int,
    sentiment_momentum_threshold: float,
    baseline_config: Optional[Path] = None,
    experiment_skip_reasons: Optional[Sequence[str]] = None,
    data_readiness_payload: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Build aggregate JSON payload for the official Phase B item 7 experiment."""

    if comparison_df.empty:
        skip_reasons = [str(item) for item in (experiment_skip_reasons or []) if str(item).strip()]
        blocked_missing_sentiment_data = any(
            "Sentiment momentum requires daily sentiment columns" in item
            for item in skip_reasons
        )
        blocked_invalid_sentiment_schema = any(
            "schema is invalid" in item.lower()
            or "kolom sentimen harian tidak lengkap" in item.lower()
            for item in skip_reasons
        )
        blocked_insufficient_sentiment_history = False
        if data_readiness_payload is not None:
            readiness_status = str(data_readiness_payload.get("readiness_status") or "").strip()
            blocked_missing_sentiment_data = (
                blocked_missing_sentiment_data
                or readiness_status == "blocked_missing_sentiment_series"
            )
            blocked_invalid_sentiment_schema = (
                blocked_invalid_sentiment_schema
                or readiness_status == "blocked_invalid_sentiment_schema"
            )
            blocked_insufficient_sentiment_history = (
                readiness_status == "blocked_insufficient_sentiment_history"
            )
        return {
            "generated_at": _now_iso(),
            "experiment_id": "phase_b_item7_sentiment_momentum",
            "comparison_status": (
                "blocked_missing_sentiment_data"
                if blocked_missing_sentiment_data
                else "blocked_invalid_sentiment_schema"
                if blocked_invalid_sentiment_schema
                else "blocked_insufficient_sentiment_history"
                if blocked_insufficient_sentiment_history
                else "not_available"
            ),
            "reason": (
                "Dataset belum memiliki seri sentimen harian. Refresh export dengan "
                "--include-sentiment-series lalu rerun eksperimen item 7."
                if blocked_missing_sentiment_data
                else "Dataset memiliki kolom sentimen tetapi formatnya tidak sah untuk evaluator item 7. "
                "Perbaiki schema export lalu rerun."
                if blocked_invalid_sentiment_schema
                else "Dataset sudah punya kolom sentimen, tetapi history/article coverage belum cukup "
                "untuk menghitung momentum item 7."
                if blocked_insufficient_sentiment_history
                else "Control and sentiment-momentum experiment arms did not produce overlapping ticker results."
            ),
            "control_arm": {
                "baseline_config": str(baseline_config) if baseline_config else None,
                "sentiment_momentum_enabled": False,
            },
            "experiment_arm": {
                "sentiment_momentum_enabled": True,
                "sentiment_momentum_mode": str(sentiment_momentum_mode),
                "sentiment_momentum_window": int(sentiment_momentum_window),
                "sentiment_baseline_window": int(sentiment_baseline_window),
                "sentiment_momentum_threshold": float(sentiment_momentum_threshold),
            },
            "aggregate": {
                "ticker_count": 0,
                "delta_total_trades_sum": 0.0,
                "delta_win_rate_mean": None,
                "delta_average_return_mean": None,
                "delta_max_drawdown_mean": None,
            },
            "skip_reasons": _dedupe(skip_reasons),
            "data_readiness": _sanitize_for_json(data_readiness_payload) if data_readiness_payload else None,
        }

    delta_avg = pd.to_numeric(comparison_df["delta_average_return"], errors="coerce")
    delta_win = pd.to_numeric(comparison_df["delta_win_rate"], errors="coerce")
    delta_drawdown = pd.to_numeric(comparison_df["delta_max_drawdown"], errors="coerce")
    baseline_trades = pd.to_numeric(comparison_df["baseline_total_trades"], errors="coerce")
    candidate_trades = pd.to_numeric(comparison_df["candidate_total_trades"], errors="coerce")
    ready_count = int(pd.Series(comparison_df["sentiment_data_ready"]).fillna(False).astype(bool).sum())

    group_snapshots: List[Dict[str, object]] = []
    for field in ["market_cap_group", "sector", "category", "beta_group"]:
        if field not in comparison_df.columns:
            continue
        working = comparison_df.loc[
            comparison_df[field].notna() & comparison_df[field].astype(str).str.strip().ne("")
        ].copy()
        if working.empty:
            continue
        grouped = (
            working.groupby(field)
            .agg(
                ticker_count=("ticker", "count"),
                trade_retention_mean_pct=("trade_retention_pct", "mean"),
                delta_win_rate_mean=("delta_win_rate", "mean"),
                delta_average_return_mean=("delta_average_return", "mean"),
                delta_max_drawdown_mean=("delta_max_drawdown", "mean"),
            )
            .reset_index()
            .rename(columns={field: "group_value"})
        )
        grouped["group_field"] = field
        group_snapshots.extend(grouped.to_dict(orient="records"))

    return {
        "generated_at": _now_iso(),
        "experiment_id": "phase_b_item7_sentiment_momentum",
        "comparison_status": "measured",
        "comparison_scope": "baseline_phase_a_vs_baseline_plus_sentiment_momentum",
        "control_arm": {
            "baseline_config": str(baseline_config) if baseline_config else None,
            "sentiment_momentum_enabled": False,
        },
        "experiment_arm": {
            "sentiment_momentum_enabled": True,
            "sentiment_momentum_mode": str(sentiment_momentum_mode),
            "sentiment_momentum_window": int(sentiment_momentum_window),
            "sentiment_baseline_window": int(sentiment_baseline_window),
            "sentiment_momentum_threshold": float(sentiment_momentum_threshold),
        },
        "aggregate": {
            "ticker_count": int(len(comparison_df)),
            "sentiment_data_ready_ticker_count": ready_count,
            "comparable_ticker_count": int(
                (
                    pd.to_numeric(comparison_df["baseline_total_trades"], errors="coerce") > 0
                ).sum()
            ),
            "baseline_total_trades_sum": float(baseline_trades.sum()),
            "candidate_total_trades_sum": float(candidate_trades.sum()),
            "delta_total_trades_sum": float(
                pd.to_numeric(comparison_df["delta_total_trades"], errors="coerce").sum()
            ),
            "trade_retention_mean_pct": _json_metric(
                pd.to_numeric(comparison_df["trade_retention_pct"], errors="coerce").mean()
            ),
            "delta_win_rate_mean": _json_metric(delta_win.mean()),
            "delta_average_return_mean": _json_metric(delta_avg.mean()),
            "delta_max_drawdown_mean": _json_metric(delta_drawdown.mean()),
            "tickers_with_trade_reduction": int(
                (pd.to_numeric(comparison_df["delta_total_trades"], errors="coerce") < 0).sum()
            ),
            "tickers_with_win_rate_improvement": int((delta_win > 0).sum()),
            "tickers_with_average_return_improvement": int((delta_avg > 0).sum()),
            "tickers_with_lower_drawdown": int((delta_drawdown < 0).sum()),
        },
        "group_snapshots": _sanitize_for_json(group_snapshots),
    }


def build_sentiment_momentum_go_no_go(
    comparison_df: pd.DataFrame,
    summary_payload: Dict[str, object],
) -> Dict[str, object]:
    """Determine the go/no-go posture for the sentiment momentum experiment."""

    if comparison_df.empty:
        blocked_reason = str(summary_payload.get("reason") or "").strip()
        comparison_status = str(summary_payload.get("comparison_status") or "").strip()
        next_action = (
            "refresh_sentiment_data"
            if comparison_status
            in {
                "blocked_missing_sentiment_data",
                "blocked_invalid_sentiment_schema",
                "blocked_insufficient_sentiment_history",
            }
            else "continue_tuning"
        )
        return {
            "decision": "keep_experimental",
            "experiment_status": "pending",
            "promote_default": False,
            "promote_subset_only": False,
            "recommended_tickers": [],
            "recommended_groups": [],
            "next_action": next_action,
            "blocked_from_default": [
                blocked_reason or "Eksperimen item 7 belum menghasilkan perbandingan yang bisa dinilai."
            ],
        }

    ready_mask = pd.Series(comparison_df["sentiment_data_ready"]).fillna(False).astype(bool)
    ready_df = comparison_df.loc[ready_mask].copy()
    comparable_mask = ready_mask & (
        pd.to_numeric(comparison_df["baseline_total_trades"], errors="coerce") > 0
    )
    comparable_df = comparison_df.loc[comparable_mask].copy()
    working_df = comparable_df if not comparable_df.empty else ready_df
    if working_df.empty:
        working_df = comparison_df.copy()

    retention = pd.to_numeric(working_df["trade_retention_pct"], errors="coerce")
    delta_avg = pd.to_numeric(working_df["delta_average_return"], errors="coerce")
    delta_win = pd.to_numeric(working_df["delta_win_rate"], errors="coerce")
    delta_drawdown = pd.to_numeric(working_df["delta_max_drawdown"], errors="coerce")
    candidate_trades = pd.to_numeric(working_df["candidate_total_trades"], errors="coerce")

    improve_mask = (
        (candidate_trades > 0)
        & (retention >= 60.0)
        & ((delta_avg > 0) | (delta_win > 0))
        & (delta_drawdown <= 0.5)
    )
    worsen_mask = (
        (candidate_trades <= 0)
        | (retention < 60.0)
        | (delta_avg < 0)
        | (delta_win < 0)
        | (delta_drawdown > 0.5)
    )

    improve_tickers = working_df.loc[improve_mask, "ticker"].astype(str).tolist()
    improve_count = int(len(improve_tickers))
    worsen_count = int(worsen_mask.sum())
    ticker_count = int(len(working_df))
    improve_share = (improve_count / ticker_count) if ticker_count else 0.0
    worsen_share = (worsen_count / ticker_count) if ticker_count else 0.0

    recommended_groups: List[str] = []
    for field in ["market_cap_group", "sector", "category", "beta_group"]:
        if field not in working_df.columns:
            continue
        grouped = (
            working_df.loc[working_df[field].notna() & working_df[field].astype(str).str.strip().ne("")]
            .groupby(field)
            .agg(
                ticker_count=("ticker", "count"),
                improve_count=("ticker", lambda values: int(improve_mask.loc[values.index].sum())),
                worsen_count=("ticker", lambda values: int(worsen_mask.loc[values.index].sum())),
                trade_retention_mean_pct=("trade_retention_pct", "mean"),
                delta_average_return_mean=("delta_average_return", "mean"),
                delta_win_rate_mean=("delta_win_rate", "mean"),
            )
            .reset_index()
        )
        for _, row in grouped.iterrows():
            if (
                int(row["ticker_count"]) >= 2
                and int(row["improve_count"]) > int(row["worsen_count"])
                and _safe_metric(row["trade_retention_mean_pct"]) >= 60.0
                and _safe_metric(row["delta_average_return_mean"]) >= 0
                and _safe_metric(row["delta_win_rate_mean"]) >= 0
            ):
                recommended_groups.append(f"{field}={row[field]}")

    blocked_from_default: List[str] = []
    aggregate = summary_payload.get("aggregate", {})
    comparable_ticker_count = _safe_int(aggregate.get("comparable_ticker_count"))
    if _safe_int(aggregate.get("sentiment_data_ready_ticker_count")) == 0:
        blocked_from_default.append("Data sentiment harian belum cukup untuk ticker yang diuji.")
    if comparable_ticker_count == 0:
        blocked_from_default.append("Belum ada ticker dengan trade baseline Phase A yang cukup untuk dibandingkan.")
    if comparable_ticker_count < 3:
        blocked_from_default.append("Sampel ticker comparable masih terlalu kecil untuk promosi resmi.")
    if _safe_metric(aggregate.get("trade_retention_mean_pct")) < 75.0:
        blocked_from_default.append("Trade retention rata-rata masih terlalu rendah.")
    if _safe_metric(aggregate.get("delta_average_return_mean")) <= 0:
        blocked_from_default.append("Average return rata-rata tidak membaik.")
    if _safe_metric(aggregate.get("delta_win_rate_mean")) < 0:
        blocked_from_default.append("Win rate rata-rata tidak membaik.")
    if improve_count == 0:
        blocked_from_default.append("Tidak ada ticker comparable yang improve dengan retention memadai.")
    if worsen_count >= improve_count:
        blocked_from_default.append("Ticker yang memburuk minimal sama banyak dengan yang improve.")

    if (
        improve_share >= 0.6
        and worsen_share <= 0.2
        and _safe_metric(aggregate.get("delta_average_return_mean")) > 0
        and _safe_metric(aggregate.get("delta_win_rate_mean")) >= 0
        and _safe_metric(aggregate.get("trade_retention_mean_pct")) >= 75.0
        and comparable_ticker_count >= 5
        and _safe_int(aggregate.get("sentiment_data_ready_ticker_count")) >= max(3, math.ceil(ticker_count * 0.5))
    ):
        decision = "promote_global"
        next_action = "promote_global"
    elif comparable_ticker_count >= 3 and (recommended_groups or len(improve_tickers) >= 2):
        decision = "promote_for_subset"
        next_action = "promote_subset"
    elif _safe_int(aggregate.get("sentiment_data_ready_ticker_count")) == 0 or comparable_ticker_count < 3:
        decision = "keep_experimental"
        next_action = "continue_tuning"
    elif improve_count > 0:
        decision = "keep_experimental"
        next_action = "continue_tuning"
    else:
        decision = "no_go"
        next_action = "stop"

    return {
        "decision": decision,
        "experiment_status": "completed",
        "promote_default": decision == "promote_global",
        "promote_subset_only": decision == "promote_for_subset",
        "recommended_tickers": improve_tickers if decision in {"promote_for_subset", "promote_global"} else [],
        "recommended_groups": recommended_groups if decision == "promote_for_subset" else [],
        "next_action": next_action,
        "blocked_from_default": _dedupe(blocked_from_default),
    }


def export_sentiment_momentum_experiment_results(
    control_summary_df: pd.DataFrame,
    experiment_summary_df: pd.DataFrame,
    output_dir: Path,
    sentiment_momentum_mode: str,
    sentiment_momentum_window: int,
    sentiment_baseline_window: int,
    sentiment_momentum_threshold: float,
    baseline_config: Optional[Path] = None,
    metadata_lookup: Optional[Dict[str, Dict[str, object]]] = None,
    experiment_skip_reasons: Optional[Sequence[str]] = None,
    data_readiness_payload: Optional[Dict[str, object]] = None,
) -> Tuple[pd.DataFrame, Dict[str, object], Dict[str, object]]:
    """Export per-ticker and aggregate artifacts for the sentiment momentum experiment."""

    comparison_df = build_sentiment_momentum_experiment_dataframe(
        control_summary_df=control_summary_df,
        experiment_summary_df=experiment_summary_df,
        sentiment_momentum_mode=sentiment_momentum_mode,
        sentiment_momentum_window=sentiment_momentum_window,
        sentiment_baseline_window=sentiment_baseline_window,
        sentiment_momentum_threshold=sentiment_momentum_threshold,
        metadata_lookup=metadata_lookup,
    )
    summary_payload = build_sentiment_momentum_experiment_summary(
        comparison_df=comparison_df,
        sentiment_momentum_mode=sentiment_momentum_mode,
        sentiment_momentum_window=sentiment_momentum_window,
        sentiment_baseline_window=sentiment_baseline_window,
        sentiment_momentum_threshold=sentiment_momentum_threshold,
        baseline_config=baseline_config,
        experiment_skip_reasons=experiment_skip_reasons,
        data_readiness_payload=data_readiness_payload,
    )
    go_no_go_payload = build_sentiment_momentum_go_no_go(
        comparison_df=comparison_df,
        summary_payload=summary_payload,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    per_ticker_path = output_dir / "phase_b_item7_sentiment_momentum_per_ticker.csv"
    summary_path = output_dir / "phase_b_item7_sentiment_momentum_summary.json"
    report_path = output_dir / "phase_b_item7_sentiment_momentum_report.txt"
    go_no_go_path = output_dir / "phase_b_item7_go_no_go.json"

    comparison_df.to_csv(per_ticker_path, index=False)
    summary_path.write_text(
        json.dumps(_sanitize_for_json(summary_payload), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    go_no_go_path.write_text(
        json.dumps(_sanitize_for_json(go_no_go_payload), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    report_lines = [
        "Phase B Item 7 Sentiment Momentum Experiment",
        "===========================================",
        "",
        f"- Comparison status: {summary_payload['comparison_status']}",
        f"- Baseline config: {summary_payload['control_arm']['baseline_config'] or 'runtime defaults'}",
        f"- Sentiment momentum mode: {summary_payload['experiment_arm']['sentiment_momentum_mode']}",
        f"- Sentiment momentum window: {summary_payload['experiment_arm']['sentiment_momentum_window']}",
        f"- Sentiment baseline window: {summary_payload['experiment_arm']['sentiment_baseline_window']}",
        f"- Sentiment threshold: {summary_payload['experiment_arm']['sentiment_momentum_threshold']}",
        f"- Ticker count: {_safe_int(summary_payload['aggregate']['ticker_count'])}",
        f"- Sentiment-data-ready tickers: {_safe_int(summary_payload['aggregate'].get('sentiment_data_ready_ticker_count'))}",
        f"- Comparable baseline tickers: {_safe_int(summary_payload['aggregate'].get('comparable_ticker_count'))}",
        f"- Delta total trades sum: {_safe_metric(summary_payload['aggregate']['delta_total_trades_sum'])}",
        f"- Mean delta win rate: {_safe_metric(summary_payload['aggregate']['delta_win_rate_mean'])}",
        f"- Mean delta average return: {_safe_metric(summary_payload['aggregate']['delta_average_return_mean'])}",
        f"- Mean delta max drawdown: {_safe_metric(summary_payload['aggregate']['delta_max_drawdown_mean'])}",
        f"- Data readiness artifact: {output_dir / 'phase_b_item7_data_readiness.json'}",
        "",
        "Decision:",
        f"- {go_no_go_payload['decision']}",
        f"- next_action={go_no_go_payload['next_action']}",
    ]

    blocked = list(go_no_go_payload.get("blocked_from_default") or [])
    if blocked:
        report_lines.extend(["", "Blocked from default:"])
        for item in blocked:
            report_lines.append(f"- {item}")

    recommended_tickers = list(go_no_go_payload.get("recommended_tickers") or [])
    if recommended_tickers:
        report_lines.extend(["", "Recommended tickers:"])
        for item in recommended_tickers:
            report_lines.append(f"- {item}")

    recommended_groups = list(go_no_go_payload.get("recommended_groups") or [])
    if recommended_groups:
        report_lines.extend(["", "Recommended groups:"])
        for item in recommended_groups:
            report_lines.append(f"- {item}")

    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"Saved sentiment momentum experiment CSV to {per_ticker_path}")
    print(f"Saved sentiment momentum experiment JSON to {summary_path}")
    print(f"Saved sentiment momentum experiment report to {report_path}")
    print(f"Saved sentiment momentum go/no-go JSON to {go_no_go_path}")

    return comparison_df, summary_payload, go_no_go_payload


def export_candle_confirmation_experiment_results(
    control_summary_df: pd.DataFrame,
    experiment_summary_df: pd.DataFrame,
    output_dir: Path,
    candle_volume_confirmation_threshold: float,
    baseline_config: Optional[Path] = None,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """Export per-ticker and aggregate artifacts for the candle confirmation experiment."""

    comparison_df = build_candle_confirmation_experiment_dataframe(
        control_summary_df=control_summary_df,
        experiment_summary_df=experiment_summary_df,
        candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
    )
    summary_payload = build_candle_confirmation_experiment_summary(
        comparison_df=comparison_df,
        candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
        baseline_config=baseline_config,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    per_ticker_path = output_dir / "phase_b_item5_candle_confirmation_per_ticker.csv"
    summary_path = output_dir / "phase_b_item5_candle_confirmation_summary.json"
    report_path = output_dir / "phase_b_item5_candle_confirmation_report.txt"

    comparison_df.to_csv(per_ticker_path, index=False)
    summary_path.write_text(
        json.dumps(summary_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    report_lines = [
        "Phase B Item 5 Candle Confirmation Experiment",
        "=============================================",
        "",
        f"- Comparison status: {summary_payload['comparison_status']}",
        f"- Baseline config: {summary_payload['control_arm']['baseline_config'] or 'runtime defaults'}",
        f"- Candle confirmation threshold: {float(candle_volume_confirmation_threshold):.2f}",
        f"- Ticker count: {_safe_int(summary_payload['aggregate']['ticker_count'])}",
        f"- Delta total trades sum: {_safe_metric(summary_payload['aggregate']['delta_phase_a_total_trades_sum'])}",
        f"- Mean delta win rate: {_safe_metric(summary_payload['aggregate']['delta_phase_a_win_rate_mean'])}",
        f"- Mean delta average return: {_safe_metric(summary_payload['aggregate']['delta_phase_a_average_return_mean'])}",
        f"- Mean delta max drawdown: {_safe_metric(summary_payload['aggregate']['delta_phase_a_max_drawdown_mean'])}",
        "",
        "Interpretation:",
        "- Control arm = frozen Phase A runtime settings without candle confirmation.",
        "- Experiment arm = same runtime settings plus bullish-candle and volume confirmation gate.",
    ]

    top_improvements = summary_payload.get("top_average_return_improvements", [])
    if top_improvements:
        report_lines.extend(["", "Top average-return improvements:"])
        for item in top_improvements:
            report_lines.append(
                f"- {item['ticker']}: delta_avg_return={item['delta_phase_a_average_return']}, "
                f"delta_win_rate={item['delta_phase_a_win_rate']}, "
                f"delta_trades={item['delta_phase_a_total_trades']}"
            )

    trade_reductions = summary_payload.get("largest_trade_reductions", [])
    if trade_reductions:
        report_lines.extend(["", "Largest trade reductions:"])
        for item in trade_reductions:
            report_lines.append(
                f"- {item['ticker']}: delta_trades={item['delta_phase_a_total_trades']}, "
                f"trade_retention_pct={item['trade_retention_pct']}, "
                f"delta_avg_return={item['delta_phase_a_average_return']}"
            )

    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"Saved candle confirmation experiment CSV to {per_ticker_path}")
    print(f"Saved candle confirmation experiment JSON to {summary_path}")
    print(f"Saved candle confirmation experiment report to {report_path}")

    return comparison_df, summary_payload


def _resolve_csv_files(
    folder_path: Path,
    tickers: Optional[Iterable[str]] = None,
    output_dir: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
) -> Tuple[List[Path], List[Path]]:
    """Validate the data directory and resolve selected CSV files."""

    folder = Path(folder_path)
    if not folder.exists():
        raise EvaluationCliError(
            f"Data directory not found: {folder}",
            suggestions=[f"Generate sample CSV data with: {_bootstrap_command(folder)}"],
        )
    if not folder.is_dir():
        raise EvaluationCliError(f"Data path is not a directory: {folder}")

    excluded_file = Path(metadata_file).resolve() if metadata_file is not None else None
    all_csv_files = []
    for path in sorted(folder.glob("*.csv")):
        if excluded_file is not None and path.resolve() == excluded_file:
            continue
        all_csv_files.append(path)
    if not all_csv_files:
        raise EvaluationCliError(
            f"No CSV files found in {folder}",
            suggestions=[f"Generate sample CSV data with: {_bootstrap_command(folder)}"],
        )

    ticker_filter = _normalize_ticker_filter(tickers)
    if ticker_filter is not None:
        csv_files = [
            path for path in all_csv_files if extract_ticker_from_filename(path) in ticker_filter
        ]
    else:
        csv_files = all_csv_files

    if not csv_files:
        available_tickers = ", ".join(
            extract_ticker_from_filename(path) for path in all_csv_files[:10]
        )
        suggestions = [f"Inspect files with: {_validator_command(folder, output_dir)}"]
        if available_tickers:
            suggestions.insert(0, f"Available tickers in {folder}: {available_tickers}")
        raise EvaluationCliError(
            f"No CSV files matched the requested ticker filter in {folder}",
            suggestions=suggestions,
        )

    return all_csv_files, csv_files


def evaluate_folder(
    folder_path: Path,
    output_dir: Optional[Path] = None,
    evaluate_strict: bool = False,
    tickers: Optional[Iterable[str]] = None,
    hold_period: int = 5,
    allow_overlap: bool = False,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
    require_candle_volume_confirmation: bool = False,
    candle_volume_confirmation_threshold: float = 1.0,
    require_weekly_trend_confirmation: bool = False,
    weekly_trend_method: str = DEFAULT_WEEKLY_TREND_METHOD,
    weekly_require_slope_up: bool = False,
    require_sentiment_momentum: bool = False,
    sentiment_momentum_window: int = DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    sentiment_baseline_window: int = DEFAULT_SENTIMENT_BASELINE_WINDOW,
    sentiment_momentum_threshold: float = DEFAULT_SENTIMENT_MOMENTUM_THRESHOLD,
    sentiment_momentum_mode: str = DEFAULT_SENTIMENT_MOMENTUM_MODE,
    validate_item7_readiness: bool = False,
    log_progress: bool = True,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Evaluate all CSV files in a folder and optionally export outputs."""

    folder = Path(folder_path)
    if validate_item7_readiness:
        if output_dir is None:
            raise EvaluationCliError(
                "Item 7 readiness validation requires an output directory.",
                suggestions=[
                    _item7_readiness_command(
                        data_dir=folder,
                        output_dir=Path("output"),
                        metadata_file=metadata_file,
                        sentiment_momentum_window=sentiment_momentum_window,
                        sentiment_baseline_window=sentiment_baseline_window,
                    )
                ],
            )
        readiness_payload = export_item7_data_readiness_artifacts(
            folder_path=folder,
            output_dir=Path(output_dir),
            tickers=tickers,
            metadata_file=metadata_file,
            sentiment_momentum_window=sentiment_momentum_window,
            sentiment_baseline_window=sentiment_baseline_window,
        )
        export_item7_rerun_checklist(
            output_dir=Path(output_dir),
            data_dir=folder,
            baseline_config=baseline_config,
            metadata_file=metadata_file,
            sentiment_momentum_window=sentiment_momentum_window,
            sentiment_baseline_window=sentiment_baseline_window,
            sentiment_momentum_threshold=sentiment_momentum_threshold,
            sentiment_momentum_mode=sentiment_momentum_mode,
        )
        export_item7_execution_runbook(
            output_dir=Path(output_dir),
            data_dir=folder,
            baseline_config=baseline_config,
            metadata_file=metadata_file,
            sentiment_momentum_window=sentiment_momentum_window,
            sentiment_baseline_window=sentiment_baseline_window,
            sentiment_momentum_threshold=sentiment_momentum_threshold,
            sentiment_momentum_mode=sentiment_momentum_mode,
        )
        if log_progress:
            print("\nItem 7 readiness validation complete.")
            print(f"Readiness status: {readiness_payload['readiness_status']}")
            print(f"Valid ticker count: {readiness_payload['valid_ticker_count']}")
            print(f"Invalid ticker count: {readiness_payload['invalid_ticker_count']}")
            print(f"Unusable ticker count: {readiness_payload['unusable_ticker_count']}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    all_csv_files, csv_files = _resolve_csv_files(
        folder_path=folder,
        tickers=tickers,
        output_dir=output_dir,
        metadata_file=metadata_file,
    )
    baseline_payload = None
    baseline_source = None
    metadata_lookup: Dict[str, Dict[str, object]] = {}
    baseline_warnings: List[str] = []

    if baseline_config is not None:
        baseline_payload, baseline_warnings, baseline_source = load_phase_a_baseline(
            baseline_config=baseline_config
        )
        metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
        baseline_warnings.extend(metadata_warnings)
        if log_progress:
            for warning in baseline_warnings:
                print(f"baseline warning: {warning}")

    successful_results: List[EvaluationRecord] = []
    skipped_results: List[SkipRecord] = []

    for path in csv_files:
        ticker = extract_ticker_from_filename(path)
        if log_progress:
            print(f"Processing {ticker}...")
        try:
            runtime_settings = (
                resolve_phase_a_runtime_settings(
                    ticker=ticker,
                    baseline_config=baseline_payload,
                    metadata_lookup=metadata_lookup,
                )
                if baseline_payload is not None
                else {
                    "threshold": 2.0,
                    "strict_mode": False,
                }
            )
            record = evaluate_single_ticker(
                path,
                hold_period=hold_period,
                allow_overlap=allow_overlap,
                evaluate_strict=evaluate_strict,
                phase_a_volume_spike_threshold=float(runtime_settings["threshold"]),
                phase_a_strict_mode=bool(runtime_settings["strict_mode"]),
                require_candle_volume_confirmation=require_candle_volume_confirmation,
                candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
                require_weekly_trend_confirmation=require_weekly_trend_confirmation,
                weekly_trend_method=weekly_trend_method,
                weekly_require_slope_up=weekly_require_slope_up,
                require_sentiment_momentum=require_sentiment_momentum,
                sentiment_momentum_window=sentiment_momentum_window,
                sentiment_baseline_window=sentiment_baseline_window,
                sentiment_momentum_threshold=sentiment_momentum_threshold,
                sentiment_momentum_mode=sentiment_momentum_mode,
                phase_a_baseline_source=str(baseline_source) if baseline_source else None,
            )
            successful_results.append(record)

            if log_progress and record.warnings:
                for warning in record.warnings:
                    print(f"  warning: {warning}")
        except Exception as exc:
            message = str(exc)
            if log_progress:
                print(f"  skipped: {message}")
            skipped_results.append(
                SkipRecord(
                    ticker=ticker,
                    file_path=str(path),
                    reason=message,
                )
            )

    summary_df = build_summary_dataframe(successful_results)
    skipped_df = build_skipped_dataframe(skipped_results)
    aggregate_df = build_aggregate_summary(summary_df)

    if output_dir is not None:
        export_results(summary_df, skipped_df, aggregate_df, Path(output_dir))
        if require_candle_volume_confirmation:
            control_summary_df, _, _ = evaluate_folder(
                folder_path=folder,
                output_dir=None,
                evaluate_strict=evaluate_strict,
                tickers=tickers,
                hold_period=hold_period,
                allow_overlap=allow_overlap,
                baseline_config=baseline_config,
                metadata_file=metadata_file,
                require_candle_volume_confirmation=False,
                candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
                require_weekly_trend_confirmation=require_weekly_trend_confirmation,
                weekly_trend_method=weekly_trend_method,
                weekly_require_slope_up=weekly_require_slope_up,
                require_sentiment_momentum=require_sentiment_momentum,
                sentiment_momentum_window=sentiment_momentum_window,
                sentiment_baseline_window=sentiment_baseline_window,
                sentiment_momentum_threshold=sentiment_momentum_threshold,
                sentiment_momentum_mode=sentiment_momentum_mode,
                log_progress=False,
            )
            export_candle_confirmation_experiment_results(
                control_summary_df=control_summary_df,
                experiment_summary_df=summary_df,
                output_dir=Path(output_dir),
                candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
                baseline_config=baseline_config,
            )
        if require_weekly_trend_confirmation:
            control_summary_df, _, _ = evaluate_folder(
                folder_path=folder,
                output_dir=None,
                evaluate_strict=evaluate_strict,
                tickers=tickers,
                hold_period=hold_period,
                allow_overlap=allow_overlap,
                baseline_config=baseline_config,
                metadata_file=metadata_file,
                require_candle_volume_confirmation=require_candle_volume_confirmation,
                candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
                require_weekly_trend_confirmation=False,
                weekly_trend_method=weekly_trend_method,
                weekly_require_slope_up=weekly_require_slope_up,
                require_sentiment_momentum=require_sentiment_momentum,
                sentiment_momentum_window=sentiment_momentum_window,
                sentiment_baseline_window=sentiment_baseline_window,
                sentiment_momentum_threshold=sentiment_momentum_threshold,
                sentiment_momentum_mode=sentiment_momentum_mode,
                log_progress=False,
            )
            export_multitimeframe_experiment_results(
                control_summary_df=control_summary_df,
                experiment_summary_df=summary_df,
                output_dir=Path(output_dir),
                weekly_trend_method=weekly_trend_method,
                weekly_require_slope_up=weekly_require_slope_up,
                baseline_config=baseline_config,
                metadata_lookup=metadata_lookup,
            )
        if require_sentiment_momentum:
            readiness_payload = export_item7_data_readiness_artifacts(
                folder_path=folder,
                output_dir=Path(output_dir),
                tickers=tickers,
                metadata_file=metadata_file,
                sentiment_momentum_window=sentiment_momentum_window,
                sentiment_baseline_window=sentiment_baseline_window,
            )
            export_item7_rerun_checklist(
                output_dir=Path(output_dir),
                data_dir=folder,
                baseline_config=baseline_config,
                metadata_file=metadata_file,
                sentiment_momentum_window=sentiment_momentum_window,
                sentiment_baseline_window=sentiment_baseline_window,
                sentiment_momentum_threshold=sentiment_momentum_threshold,
                sentiment_momentum_mode=sentiment_momentum_mode,
            )
            export_item7_execution_runbook(
                output_dir=Path(output_dir),
                data_dir=folder,
                baseline_config=baseline_config,
                metadata_file=metadata_file,
                sentiment_momentum_window=sentiment_momentum_window,
                sentiment_baseline_window=sentiment_baseline_window,
                sentiment_momentum_threshold=sentiment_momentum_threshold,
                sentiment_momentum_mode=sentiment_momentum_mode,
            )
            control_summary_df, _, _ = evaluate_folder(
                folder_path=folder,
                output_dir=None,
                evaluate_strict=evaluate_strict,
                tickers=tickers,
                hold_period=hold_period,
                allow_overlap=allow_overlap,
                baseline_config=baseline_config,
                metadata_file=metadata_file,
                require_candle_volume_confirmation=require_candle_volume_confirmation,
                candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
                require_weekly_trend_confirmation=require_weekly_trend_confirmation,
                weekly_trend_method=weekly_trend_method,
                weekly_require_slope_up=weekly_require_slope_up,
                require_sentiment_momentum=False,
                sentiment_momentum_window=sentiment_momentum_window,
                sentiment_baseline_window=sentiment_baseline_window,
                sentiment_momentum_threshold=sentiment_momentum_threshold,
                sentiment_momentum_mode=sentiment_momentum_mode,
                log_progress=False,
            )
            export_sentiment_momentum_experiment_results(
                control_summary_df=control_summary_df,
                experiment_summary_df=summary_df,
                output_dir=Path(output_dir),
                sentiment_momentum_mode=sentiment_momentum_mode,
                sentiment_momentum_window=sentiment_momentum_window,
                sentiment_baseline_window=sentiment_baseline_window,
                sentiment_momentum_threshold=sentiment_momentum_threshold,
                baseline_config=baseline_config,
                metadata_lookup=metadata_lookup,
                experiment_skip_reasons=skipped_df["reason"].tolist()
                if not skipped_df.empty
                else None,
                data_readiness_payload=readiness_payload,
            )

    if log_progress:
        print("\nEvaluation complete.")
        print(f"Total files found: {len(all_csv_files)}")
        print(f"Total files selected: {len(csv_files)}")
        print(f"Total files succeeded: {len(successful_results)}")
        print(f"Total files skipped: {len(skipped_results)}")

    return summary_df, skipped_df, aggregate_df


def build_aggregate_summary(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Build a cross-ticker aggregate summary."""

    if summary_df.empty:
        return pd.DataFrame(
            [
                {
                    "ticker_count": 0,
                    "baseline_total_trades_sum": 0,
                    "phase_a_total_trades_sum": 0,
                    "baseline_win_rate_mean": np.nan,
                    "phase_a_win_rate_mean": np.nan,
                    "baseline_average_return_mean": np.nan,
                    "phase_a_average_return_mean": np.nan,
                    "delta_win_rate_mean": np.nan,
                    "delta_average_return_mean": np.nan,
                }
            ]
        )

    return pd.DataFrame(
        [
            {
                "ticker_count": int(len(summary_df)),
                "baseline_total_trades_sum": float(summary_df["baseline_total_trades"].sum()),
                "phase_a_total_trades_sum": float(summary_df["phase_a_total_trades"].sum()),
                "baseline_win_rate_mean": float(summary_df["baseline_win_rate"].mean()),
                "phase_a_win_rate_mean": float(summary_df["phase_a_win_rate"].mean()),
                "baseline_average_return_mean": float(summary_df["baseline_average_return"].mean()),
                "phase_a_average_return_mean": float(summary_df["phase_a_average_return"].mean()),
                "delta_win_rate_mean": float(summary_df["delta_win_rate"].mean()),
                "delta_average_return_mean": float(summary_df["delta_average_return"].mean()),
            }
        ]
    )


def export_results(
    summary_df: pd.DataFrame,
    skipped_df: pd.DataFrame,
    aggregate_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Export evaluation outputs to disk."""

    output_dir.mkdir(parents=True, exist_ok=True)

    summary_csv = output_dir / "phase_a_summary.csv"
    summary_df.to_csv(summary_csv, index=False)
    print(f"Saved CSV summary to {summary_csv}")

    skipped_csv = output_dir / "phase_a_skipped.csv"
    skipped_df.to_csv(skipped_csv, index=False)
    print(f"Saved skipped-file report to {skipped_csv}")

    aggregate_csv = output_dir / "phase_a_aggregate_summary.csv"
    aggregate_df.to_csv(aggregate_csv, index=False)
    print(f"Saved aggregate summary to {aggregate_csv}")

    summary_xlsx = output_dir / "phase_a_summary.xlsx"
    try:
        with pd.ExcelWriter(summary_xlsx) as writer:
            summary_df.to_excel(writer, sheet_name="summary", index=False)
            aggregate_df.to_excel(writer, sheet_name="aggregate", index=False)
            skipped_df.to_excel(writer, sheet_name="skipped", index=False)
        print(f"Saved Excel summary to {summary_xlsx}")
    except ImportError:
        print("Warning: openpyxl/xlsxwriter is not installed. Excel export skipped.")
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Warning: Excel export failed: {exc}")


def _top_rankings(summary_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Compute top ranking tables for quick analysis."""

    if summary_df.empty:
        empty = pd.DataFrame()
        return {
            "win_rate": empty,
            "average_return": empty,
            "trade_reduction": empty,
        }

    top_win_rate = summary_df.sort_values("delta_win_rate", ascending=False).head(10)
    top_average_return = summary_df.sort_values(
        "delta_average_return", ascending=False
    ).head(10)
    top_trade_reduction = summary_df.sort_values("delta_trades", ascending=True).head(10)

    return {
        "win_rate": top_win_rate,
        "average_return": top_average_return,
        "trade_reduction": top_trade_reduction,
    }


def print_analysis(summary_df: pd.DataFrame, skipped_df: pd.DataFrame, aggregate_df: pd.DataFrame) -> None:
    """Print human-readable summary, rankings, and skipped files."""

    if summary_df.empty:
        print("\nNo successful ticker evaluations.")
        if not skipped_df.empty:
            print("\nSkipped files:")
            print(skipped_df.to_string(index=False))
        return

    rankings = _top_rankings(summary_df)

    print("\nSummary table (first 20 rows):\n")
    print(summary_df.head(20).to_string(index=False))

    print("\nAggregate summary across all processed tickers:\n")
    print(aggregate_df.to_string(index=False))

    print("\nTop 10 tickers by delta win_rate:\n")
    print(
        rankings["win_rate"][
            [
                "ticker",
                "baseline_win_rate",
                "phase_a_win_rate",
                "delta_win_rate",
                "baseline_total_trades",
                "phase_a_total_trades",
            ]
        ].to_string(index=False)
    )

    print("\nTop 10 tickers by delta average_return:\n")
    print(
        rankings["average_return"][
            [
                "ticker",
                "baseline_average_return",
                "phase_a_average_return",
                "delta_average_return",
                "baseline_total_trades",
                "phase_a_total_trades",
            ]
        ].to_string(index=False)
    )

    print("\nTop 10 tickers by trade reduction:\n")
    print(
        rankings["trade_reduction"][
            [
                "ticker",
                "baseline_total_trades",
                "phase_a_total_trades",
                "delta_trades",
                "delta_win_rate",
                "delta_average_return",
            ]
        ].to_string(index=False)
    )

    if not skipped_df.empty:
        print("\nSkipped files:\n")
        print(skipped_df.to_string(index=False))
    else:
        print("\nSkipped files:\nNone")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Evaluate Phase A on real historical CSV data per ticker."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing per-ticker CSV files. Default: data",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory to save summary exports. Default: output",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also evaluate strict Phase A signal.",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=None,
        help="Optional ticker filter, e.g. --tickers BBCA BMRI TLKM or --tickers BBCA,BMRI",
    )
    parser.add_argument(
        "--hold-period",
        type=int,
        default=5,
        help="Holding period in bars for each backtest trade. Default: 5",
    )
    parser.add_argument(
        "--allow-overlap",
        action="store_true",
        help="Allow overlapping trades during backtest.",
    )
    parser.add_argument(
        "--baseline-config",
        default=None,
        help="Optional frozen baseline JSON. If provided, the main Phase A run uses that threshold/strict default.",
    )
    parser.add_argument(
        "--metadata-file",
        default=None,
        help="Optional ticker metadata CSV used to resolve adaptive group overrides from the baseline config.",
    )
    parser.add_argument(
        "--require-candle-volume-confirmation",
        action="store_true",
        help="Experimental Phase B starter: require bullish candles to be backed by at least the configured rolling MA20 volume ratio.",
    )
    parser.add_argument(
        "--candle-volume-confirmation-threshold",
        type=float,
        default=1.0,
        help="Minimum volume_ratio for the experimental candle confirmation filter. Default: 1.0",
    )
    parser.add_argument(
        "--require-weekly-trend-confirmation",
        action="store_true",
        help="Experimental Phase B item 6: require the last completed weekly trend to confirm the daily Phase A entry.",
    )
    parser.add_argument(
        "--weekly-trend-method",
        default=DEFAULT_WEEKLY_TREND_METHOD,
        help="Weekly trend method for the experimental multi-timeframe filter. Default: ema20",
    )
    parser.add_argument(
        "--weekly-require-slope-up",
        action="store_true",
        help="Also require the weekly EMA20 slope to be upward in the experimental multi-timeframe filter.",
    )
    parser.add_argument(
        "--require-sentiment-momentum",
        action="store_true",
        help="Experimental Phase B item 7: require recent sentiment momentum to confirm the daily Phase A entry.",
    )
    parser.add_argument(
        "--sentiment-momentum-window",
        type=int,
        default=DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
        help="Recent rolling window used by the sentiment momentum experiment. Default: 3",
    )
    parser.add_argument(
        "--sentiment-baseline-window",
        type=int,
        default=DEFAULT_SENTIMENT_BASELINE_WINDOW,
        help="Baseline rolling window used by the sentiment momentum experiment. Default: 7",
    )
    parser.add_argument(
        "--sentiment-momentum-threshold",
        type=float,
        default=DEFAULT_SENTIMENT_MOMENTUM_THRESHOLD,
        help="Minimum sentiment delta required by the sentiment momentum experiment. Default: 0.0",
    )
    parser.add_argument(
        "--sentiment-momentum-mode",
        default=DEFAULT_SENTIMENT_MOMENTUM_MODE,
        help="Sentiment momentum mode for the experimental filter. One of: average, weighted, delta. Default: weighted",
    )
    parser.add_argument(
        "--validate-item7-readiness",
        action="store_true",
        help="Validate whether the exported CSV dataset is ready for the Phase B item 7 sentiment-momentum experiment.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    try:
        summary_df, skipped_df, aggregate_df = evaluate_folder(
            folder_path=data_dir,
            output_dir=output_dir,
            evaluate_strict=args.strict,
            tickers=args.tickers,
            hold_period=args.hold_period,
            allow_overlap=args.allow_overlap,
            baseline_config=Path(args.baseline_config) if args.baseline_config else None,
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            require_candle_volume_confirmation=args.require_candle_volume_confirmation,
            candle_volume_confirmation_threshold=args.candle_volume_confirmation_threshold,
            require_weekly_trend_confirmation=args.require_weekly_trend_confirmation,
            weekly_trend_method=args.weekly_trend_method,
            weekly_require_slope_up=args.weekly_require_slope_up,
            require_sentiment_momentum=args.require_sentiment_momentum,
            sentiment_momentum_window=args.sentiment_momentum_window,
            sentiment_baseline_window=args.sentiment_baseline_window,
            sentiment_momentum_threshold=args.sentiment_momentum_threshold,
            sentiment_momentum_mode=args.sentiment_momentum_mode,
            validate_item7_readiness=args.validate_item7_readiness,
        )
    except EvaluationCliError as exc:
        print(str(exc))
        _print_next_steps(exc.suggestions)
        return 1
    except Exception as exc:
        print(f"Unexpected evaluation failure: {exc}")
        _print_next_steps([f"Validate input files with: {_validator_command(data_dir, output_dir)}"])
        return 1

    if args.validate_item7_readiness:
        readiness_path = output_dir / "phase_b_item7_data_readiness.json"
        readiness_payload = json.loads(readiness_path.read_text(encoding="utf-8"))
        ready = bool(readiness_payload.get("dataset_is_item7_ready"))
        if not ready:
            print(
                "\nItem 7 readiness is not complete. "
                "Inspect output/phase_b_item7_data_readiness_report.txt for details."
            )
            return 1
        print("\nItem 7 readiness is complete.")
        return 0

    print_analysis(summary_df, skipped_df, aggregate_df)

    if summary_df.empty:
        print(
            "\nNo valid ticker files were processed. "
            "Check required columns: date, open, high, low, close, volume"
        )
        _print_next_steps([f"Validate input files with: {_validator_command(data_dir, output_dir)}"])
        return 1

    if not skipped_df.empty:
        _print_next_steps([f"Validate skipped files with: {_validator_command(data_dir, output_dir)}"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
