"""Analyze Phase A evaluation outputs and recommend next tuning steps.

Example
-------
Preferred execution from project root:

    python3 -m quant.analyze_phase_a_results \
      --summary-file output/phase_a_summary.csv \
      --aggregate-file output/phase_a_aggregate_summary.csv \
      --skipped-file output/phase_a_skipped.csv \
      --output-dir output
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CORE_SUMMARY_COLUMNS = [
    "ticker",
    "rows",
    "date_start",
    "date_end",
    "baseline_total_trades",
    "baseline_win_rate",
    "baseline_average_return",
    "baseline_max_drawdown",
    "phase_a_total_trades",
    "phase_a_win_rate",
    "phase_a_average_return",
    "phase_a_max_drawdown",
    "delta_trades",
    "delta_win_rate",
    "delta_average_return",
]
STRICT_COLUMNS = [
    "strict_total_trades",
    "strict_win_rate",
    "strict_average_return",
    "strict_max_drawdown",
]
OPTIONAL_SUMMARY_COLUMNS = [
    "volume_spike_total_trades",
    "volume_spike_win_rate",
    "volume_spike_average_return",
    "volume_spike_max_drawdown",
    "baseline_phase_a_total_trades",
    "baseline_phase_a_win_rate",
    "baseline_phase_a_average_return",
    "baseline_phase_a_max_drawdown",
]
NUMERIC_SUMMARY_COLUMNS = [
    column
    for column in CORE_SUMMARY_COLUMNS + STRICT_COLUMNS + OPTIONAL_SUMMARY_COLUMNS
    if column not in {"ticker", "date_start", "date_end"}
]
CLASSIFICATION_ORDER = ["cocok", "netral", "tidak_cocok"]
GROUP_METADATA_COLUMNS = ["category", "market_cap_group", "sector", "beta_group"]
SUMMARY_EXPORT_COLUMNS = ["section", "metric", "value", "notes"]


class AnalysisCliError(ValueError):
    """Friendly CLI error with actionable follow-up suggestions."""

    def __init__(self, message: str, suggestions: Optional[Sequence[str]] = None) -> None:
        super().__init__(message)
        self.suggestions = list(suggestions or [])


@dataclass
class LoadedAnalysisData:
    """Container for loaded input data frames."""

    summary_df: pd.DataFrame
    aggregate_df: Optional[pd.DataFrame]
    skipped_df: Optional[pd.DataFrame]
    metadata_df: Optional[pd.DataFrame]
    warnings: List[str] = field(default_factory=list)


@dataclass
class StrictModeAnalysis:
    """Summary of strict-mode behavior vs default Phase A."""

    available: bool
    policy: str
    policy_reason: str
    eligible_ticker_count: int
    improved_ticker_count: int
    too_restrictive_count: int
    improved_share_pct: float
    too_restrictive_share_pct: float
    mean_delta_trades: float
    mean_delta_win_rate: float
    mean_delta_average_return: float
    median_trade_retention_pct: float
    detail_df: pd.DataFrame
    improved_df: pd.DataFrame
    too_restrictive_df: pd.DataFrame


@dataclass
class MetadataAnalysis:
    """Optional grouped analysis using ticker metadata."""

    available: bool
    merged_df: pd.DataFrame
    group_summary_df: pd.DataFrame
    warnings: List[str] = field(default_factory=list)


def _evaluate_command_hint() -> str:
    """Build the evaluator command shown when summary output is missing."""

    return "python3 -m quant.evaluate_phase_a_real_data --data-dir data --output-dir output --strict"


def _validator_command_hint() -> str:
    """Build the validator command shown in error messages."""

    return "python3 -m quant.validate_price_data --data-dir data --output-dir output"


def _print_next_steps(steps: Sequence[str]) -> None:
    """Print actionable next-step suggestions."""

    steps = [step for step in steps if step]
    if not steps:
        return

    print("\nNext step suggestions:")
    for step in steps:
        print(f"  {step}")


def _safe_float(value: object) -> float:
    """Return a float or NaN for non-numeric values."""

    if value is None:
        return np.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _safe_mean(series: pd.Series) -> float:
    """Compute a NaN-safe mean."""

    if series.empty:
        return np.nan
    cleaned = pd.to_numeric(series, errors="coerce")
    if cleaned.dropna().empty:
        return np.nan
    return float(cleaned.mean())


def _safe_median(series: pd.Series) -> float:
    """Compute a NaN-safe median."""

    if series.empty:
        return np.nan
    cleaned = pd.to_numeric(series, errors="coerce")
    if cleaned.dropna().empty:
        return np.nan
    return float(cleaned.median())


def _safe_percentage(numerator: float, denominator: float) -> float:
    """Return a percentage or NaN when the denominator is unusable."""

    if denominator in (0, 0.0) or pd.isna(denominator):
        return np.nan
    return float((numerator / denominator) * 100.0)


def _normalize_ticker_filter(tickers: Optional[Iterable[str]]) -> Optional[set[str]]:
    """Normalize an optional ticker filter list."""

    if not tickers:
        return None

    normalized: set[str] = set()
    for item in tickers:
        for token in str(item).split(","):
            token = token.strip().upper()
            if token:
                normalized.add(token)
    return normalized or None


def _read_csv_with_validation(path: Path, label: str) -> pd.DataFrame:
    """Read a CSV file and raise a friendly error when it is unavailable."""

    target = Path(path)
    if not target.exists():
        raise AnalysisCliError(
            f"{label} file not found: {target}",
            suggestions=[f"Generate evaluator outputs first with: {_evaluate_command_hint()}"],
        )
    if not target.is_file():
        raise AnalysisCliError(f"{label} path is not a file: {target}")

    try:
        frame = pd.read_csv(target)
    except pd.errors.EmptyDataError as exc:
        raise AnalysisCliError(f"{label} file is empty: {target}") from exc
    except pd.errors.ParserError as exc:
        raise AnalysisCliError(f"{label} CSV parser error in {target}: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise AnalysisCliError(f"Failed to read {label} file {target}: {exc}") from exc

    if frame.empty:
        raise AnalysisCliError(f"{label} file contains no rows: {target}")

    return frame


def _load_optional_csv(path: Optional[Path], label: str) -> tuple[Optional[pd.DataFrame], List[str]]:
    """Read an optional CSV file and return warnings instead of hard failures."""

    warnings: List[str] = []
    if path is None:
        return None, warnings

    target = Path(path)
    if not target.exists():
        warnings.append(f"{label} file not found: {target}. Skipping optional input.")
        return None, warnings
    if not target.is_file():
        warnings.append(f"{label} path is not a file: {target}. Skipping optional input.")
        return None, warnings

    try:
        frame = pd.read_csv(target)
    except pd.errors.EmptyDataError:
        warnings.append(f"{label} file is empty: {target}. Skipping optional input.")
        return None, warnings
    except pd.errors.ParserError as exc:
        warnings.append(f"{label} CSV parser error in {target}: {exc}. Skipping optional input.")
        return None, warnings
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"Failed to read {label} file {target}: {exc}. Skipping optional input.")
        return None, warnings

    if frame.empty:
        warnings.append(f"{label} file contains no rows: {target}. Skipping optional input.")
        return None, warnings

    return frame, warnings


def load_summary_data(
    summary_file: Path,
    aggregate_file: Optional[Path] = None,
    skipped_file: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
) -> LoadedAnalysisData:
    """Load required and optional analysis inputs."""

    summary_df = _read_csv_with_validation(Path(summary_file), "Summary")
    warnings: List[str] = []

    missing_core_columns = [column for column in CORE_SUMMARY_COLUMNS if column not in summary_df.columns]
    if missing_core_columns:
        raise AnalysisCliError(
            "Summary file is missing required columns: "
            f"{missing_core_columns}. Required columns: {CORE_SUMMARY_COLUMNS}"
        )

    summary_df = summary_df.copy()
    summary_df["ticker"] = summary_df["ticker"].astype(str).str.upper().str.strip()
    summary_df["date_start"] = pd.to_datetime(summary_df["date_start"], errors="coerce")
    summary_df["date_end"] = pd.to_datetime(summary_df["date_end"], errors="coerce")

    duplicate_summary_tickers = int(summary_df["ticker"].duplicated(keep="last").sum())
    if duplicate_summary_tickers:
        warnings.append(
            f"Summary file contains {duplicate_summary_tickers} duplicate ticker rows. "
            "Keeping the latest occurrence per ticker."
        )
        summary_df = summary_df.drop_duplicates(subset=["ticker"], keep="last").reset_index(drop=True)

    for column in NUMERIC_SUMMARY_COLUMNS:
        if column not in summary_df.columns:
            summary_df[column] = np.nan
        summary_df[column] = pd.to_numeric(summary_df[column], errors="coerce")

    if summary_df["ticker"].replace("", np.nan).isna().any():
        raise AnalysisCliError("Summary file contains blank ticker values. Clean the evaluator output first.")

    aggregate_df, aggregate_warnings = _load_optional_csv(aggregate_file, "Aggregate")
    warnings.extend(aggregate_warnings)

    skipped_df, skipped_warnings = _load_optional_csv(skipped_file, "Skipped")
    warnings.extend(skipped_warnings)

    metadata_df, metadata_warnings = _load_optional_csv(metadata_file, "Metadata")
    warnings.extend(metadata_warnings)

    if metadata_df is not None:
        if "ticker" not in metadata_df.columns:
            warnings.append(
                "Metadata file does not contain a 'ticker' column. Metadata-based analysis skipped."
            )
            metadata_df = None
        else:
            metadata_df = metadata_df.copy()
            metadata_df["ticker"] = metadata_df["ticker"].astype(str).str.upper().str.strip()
            duplicate_metadata_tickers = int(metadata_df["ticker"].duplicated(keep="first").sum())
            if duplicate_metadata_tickers:
                warnings.append(
                    f"Metadata file contains {duplicate_metadata_tickers} duplicate ticker rows. "
                    "Keeping the first occurrence per ticker."
                )
                metadata_df = metadata_df.drop_duplicates(subset=["ticker"], keep="first").reset_index(drop=True)

    return LoadedAnalysisData(
        summary_df=summary_df,
        aggregate_df=aggregate_df,
        skipped_df=skipped_df,
        metadata_df=metadata_df,
        warnings=warnings,
    )


def _compute_trade_reduction_pct(
    baseline_trades: pd.Series,
    phase_a_trades: pd.Series,
) -> pd.Series:
    """Compute percent change in trade count vs baseline."""

    baseline = pd.to_numeric(baseline_trades, errors="coerce")
    phase_a = pd.to_numeric(phase_a_trades, errors="coerce")
    result = pd.Series(np.nan, index=baseline.index, dtype=float)
    valid = baseline > 0
    result.loc[valid] = ((phase_a.loc[valid] - baseline.loc[valid]) / baseline.loc[valid]) * 100.0
    return result


def _classify_ticker_row(row: pd.Series) -> tuple[str, str]:
    """Classify one ticker into cocok/netral/tidak_cocok with a readable reason."""

    baseline_trades = _safe_float(row.get("baseline_total_trades"))
    phase_a_trades = _safe_float(row.get("phase_a_total_trades"))
    delta_trades = _safe_float(row.get("delta_trades"))
    delta_win_rate = _safe_float(row.get("delta_win_rate"))
    delta_average_return = _safe_float(row.get("delta_average_return"))

    if pd.isna(phase_a_trades) or phase_a_trades <= 0:
        return "tidak_cocok", "Phase A menghilangkan semua trade atau tidak menghasilkan trade yang bisa dievaluasi."

    if pd.isna(baseline_trades) or baseline_trades <= 0:
        return "netral", "Baseline tidak punya trade yang cukup sehingga perbandingan tidak kuat."

    if delta_trades < 0 and delta_win_rate > 0 and delta_average_return >= 0:
        return "cocok", "Trade berkurang sambil win rate dan average return membaik."

    if delta_average_return <= -0.25:
        return "tidak_cocok", "Average return memburuk cukup material setelah Phase A."

    if delta_trades < 0 and delta_win_rate <= 0 and delta_average_return <= 0:
        return "tidak_cocok", "Trade berkurang tetapi kualitas sinyal tidak membaik."

    if delta_trades >= 0 and delta_win_rate < 0 and delta_average_return < 0:
        return "tidak_cocok", "Phase A tidak memperketat trade namun hasilnya tetap lebih buruk."

    return "netral", "Hasil campuran atau perubahannya belum cukup kuat untuk keputusan tegas."


def _derive_tuning_hint(row: pd.Series) -> str:
    """Suggest a threshold-follow-up hint per ticker."""

    classification = row["classification"]
    trade_reduction_pct = _safe_float(row.get("trade_reduction_pct"))
    delta_win_rate = _safe_float(row.get("delta_win_rate"))
    delta_average_return = _safe_float(row.get("delta_average_return"))
    phase_a_trades = _safe_float(row.get("phase_a_total_trades"))

    if classification == "cocok":
        return "keep_2_0"
    if phase_a_trades <= 0:
        return "test_1_5"
    if trade_reduction_pct <= -70.0 and delta_win_rate < 5.0 and delta_average_return < 0.25:
        return "test_1_5"
    if delta_average_return < 0 and trade_reduction_pct > -45.0:
        return "test_2_5"
    return "review_manually"


def classify_ticker_performance(summary_df: pd.DataFrame) -> pd.DataFrame:
    """Add ticker classification, reasons, and derived strict-mode deltas."""

    classified = summary_df.copy()
    classified["trade_reduction_pct"] = _compute_trade_reduction_pct(
        classified["baseline_total_trades"],
        classified["phase_a_total_trades"],
    )
    classification_result = classified.apply(_classify_ticker_row, axis=1, result_type="expand")
    classified["classification"] = classification_result[0]
    classified["classification_reason"] = classification_result[1]

    classified["strict_delta_trades"] = classified["strict_total_trades"] - classified["phase_a_total_trades"]
    classified["strict_delta_win_rate"] = classified["strict_win_rate"] - classified["phase_a_win_rate"]
    classified["strict_delta_average_return"] = (
        classified["strict_average_return"] - classified["phase_a_average_return"]
    )
    classified["strict_trade_retention_pct"] = _compute_trade_reduction_pct(
        baseline_trades=classified["phase_a_total_trades"],
        phase_a_trades=classified["strict_total_trades"],
    ) + 100.0
    classified["tuning_hint"] = classified.apply(_derive_tuning_hint, axis=1)

    ordered_categories = pd.Categorical(
        classified["classification"],
        categories=CLASSIFICATION_ORDER,
        ordered=True,
    )
    classified = classified.assign(classification=ordered_categories)
    classified = classified.sort_values(
        ["classification", "delta_win_rate", "delta_average_return"],
        ascending=[True, False, False],
    ).reset_index(drop=True)
    return classified


def rank_top_movers(classified_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Build the requested top-mover rankings."""

    display_columns = [
        "ticker",
        "classification",
        "tuning_hint",
        "delta_trades",
        "trade_reduction_pct",
        "delta_win_rate",
        "delta_average_return",
        "baseline_total_trades",
        "phase_a_total_trades",
    ]
    rankings = {
        "top_win_rate": classified_df.sort_values(
            ["delta_win_rate", "delta_average_return"],
            ascending=[False, False],
        ).head(10),
        "top_average_return": classified_df.sort_values(
            ["delta_average_return", "delta_win_rate"],
            ascending=[False, False],
        ).head(10),
        "top_trade_reduction": classified_df.sort_values(
            ["delta_trades", "delta_win_rate"],
            ascending=[True, False],
        ).head(10),
        "top_deterioration": classified_df.sort_values(
            ["delta_average_return", "delta_win_rate", "delta_trades"],
            ascending=[True, True, True],
        ).head(10),
    }
    return {name: frame[display_columns].copy() for name, frame in rankings.items()}


def analyze_strict_mode(classified_df: pd.DataFrame) -> StrictModeAnalysis:
    """Analyze whether strict mode improves default Phase A results."""

    strict_available = all(column in classified_df.columns for column in STRICT_COLUMNS) and any(
        classified_df[column].notna().any() for column in STRICT_COLUMNS
    )
    if not strict_available:
        empty = pd.DataFrame()
        return StrictModeAnalysis(
            available=False,
            policy="not_available",
            policy_reason="Kolom strict tidak tersedia sehingga strict mode tidak bisa dianalisis.",
            eligible_ticker_count=0,
            improved_ticker_count=0,
            too_restrictive_count=0,
            improved_share_pct=np.nan,
            too_restrictive_share_pct=np.nan,
            mean_delta_trades=np.nan,
            mean_delta_win_rate=np.nan,
            mean_delta_average_return=np.nan,
            median_trade_retention_pct=np.nan,
            detail_df=empty,
            improved_df=empty,
            too_restrictive_df=empty,
        )

    detail_df = classified_df.loc[classified_df["phase_a_total_trades"].fillna(0) > 0].copy()
    if detail_df.empty:
        empty = pd.DataFrame()
        return StrictModeAnalysis(
            available=False,
            policy="not_available",
            policy_reason="Tidak ada ticker dengan trade Phase A default yang cukup untuk membandingkan strict mode.",
            eligible_ticker_count=0,
            improved_ticker_count=0,
            too_restrictive_count=0,
            improved_share_pct=np.nan,
            too_restrictive_share_pct=np.nan,
            mean_delta_trades=np.nan,
            mean_delta_win_rate=np.nan,
            mean_delta_average_return=np.nan,
            median_trade_retention_pct=np.nan,
            detail_df=empty,
            improved_df=empty,
            too_restrictive_df=empty,
        )

    detail_df["strict_improves_quality"] = (
        detail_df["strict_delta_win_rate"].fillna(0) > 0
    ) & (detail_df["strict_delta_average_return"].fillna(0) >= 0)
    detail_df["strict_is_better"] = detail_df["strict_improves_quality"] & (
        detail_df["strict_trade_retention_pct"].fillna(0) >= 50.0
    )
    detail_df["strict_too_restrictive"] = (
        ((detail_df["strict_trade_retention_pct"].fillna(100.0) < 60.0) | (detail_df["strict_delta_trades"].fillna(0) <= -2))
        & (detail_df["strict_delta_win_rate"].fillna(0) <= 0)
        & (detail_df["strict_delta_average_return"].fillna(0) <= 0)
    )

    improved_df = detail_df.loc[detail_df["strict_is_better"]].copy()
    too_restrictive_df = detail_df.loc[detail_df["strict_too_restrictive"]].copy()

    eligible_count = int(len(detail_df))
    improved_count = int(len(improved_df))
    too_restrictive_count = int(len(too_restrictive_df))
    improved_share_pct = _safe_percentage(improved_count, eligible_count)
    too_restrictive_share_pct = _safe_percentage(too_restrictive_count, eligible_count)
    mean_delta_trades = _safe_mean(detail_df["strict_delta_trades"])
    mean_delta_win_rate = _safe_mean(detail_df["strict_delta_win_rate"])
    mean_delta_average_return = _safe_mean(detail_df["strict_delta_average_return"])
    median_trade_retention_pct = _safe_median(detail_df["strict_trade_retention_pct"])

    if (
        improved_share_pct >= 60.0
        and mean_delta_win_rate >= 2.0
        and mean_delta_average_return >= 0.0
        and median_trade_retention_pct >= 60.0
    ):
        policy = "layak_jadi_default"
        policy_reason = (
            "Strict mode meningkatkan kualitas pada mayoritas ticker dan masih menyisakan trade yang cukup."
        )
    elif improved_share_pct >= 25.0 and too_restrictive_share_pct < 60.0:
        policy = "layak_jadi_opsi"
        policy_reason = (
            "Strict mode membantu pada sebagian ticker, tetapi belum cukup konsisten untuk dijadikan default."
        )
    else:
        policy = "terlalu_restriktif"
        policy_reason = (
            "Strict mode memangkas trade terlalu banyak atau manfaat kualitasnya tidak cukup luas."
        )

    return StrictModeAnalysis(
        available=True,
        policy=policy,
        policy_reason=policy_reason,
        eligible_ticker_count=eligible_count,
        improved_ticker_count=improved_count,
        too_restrictive_count=too_restrictive_count,
        improved_share_pct=improved_share_pct,
        too_restrictive_share_pct=too_restrictive_share_pct,
        mean_delta_trades=mean_delta_trades,
        mean_delta_win_rate=mean_delta_win_rate,
        mean_delta_average_return=mean_delta_average_return,
        median_trade_retention_pct=median_trade_retention_pct,
        detail_df=detail_df,
        improved_df=improved_df,
        too_restrictive_df=too_restrictive_df,
    )


def recommend_threshold_policy(
    analysis_df: pd.DataFrame,
    label: str = "overall",
) -> Dict[str, object]:
    """Infer whether the current threshold looks too strict, too loose, or acceptable."""

    ticker_count = int(len(analysis_df))
    if ticker_count == 0:
        return {
            "scope": label,
            "action": "insufficient_sample",
            "reason": "Tidak ada ticker yang bisa dianalisis.",
            "median_trade_reduction_pct": np.nan,
            "quality_improvement_share_pct": np.nan,
            "strong_improvement_share_pct": np.nan,
        }

    trade_reduction_pct = _compute_trade_reduction_pct(
        analysis_df["baseline_total_trades"],
        analysis_df["phase_a_total_trades"],
    )
    quality_improvement_mask = (
        analysis_df["delta_win_rate"].fillna(0) > 0
    ) & (analysis_df["delta_average_return"].fillna(0) >= 0)
    strong_improvement_mask = (
        analysis_df["delta_win_rate"].fillna(0) >= 5.0
    ) & (analysis_df["delta_average_return"].fillna(0) >= 0.25)
    deterioration_mask = analysis_df["delta_average_return"].fillna(0) < 0

    median_trade_reduction_pct = _safe_median(trade_reduction_pct)
    quality_improvement_share_pct = _safe_percentage(int(quality_improvement_mask.sum()), ticker_count)
    strong_improvement_share_pct = _safe_percentage(int(strong_improvement_mask.sum()), ticker_count)
    deterioration_share_pct = _safe_percentage(int(deterioration_mask.sum()), ticker_count)

    if median_trade_reduction_pct <= -65.0 and strong_improvement_share_pct < 40.0:
        action = "test_1_5"
        reason = (
            "Trade turun terlalu dalam, tetapi kenaikan kualitas belum cukup luas. "
            "Threshold 2.0 tampak terlalu ketat."
        )
    elif quality_improvement_share_pct >= 60.0 and deterioration_share_pct <= 25.0:
        action = "keep_2_0"
        reason = (
            "Mayoritas ticker membaik secara kualitas dengan trade yang lebih selektif. "
            "Threshold 2.0 masih layak dijadikan baseline."
        )
    elif quality_improvement_share_pct < 35.0 and median_trade_reduction_pct > -45.0:
        action = "test_2_5"
        reason = (
            "Filtering saat ini belum cukup menaikkan kualitas. "
            "Threshold yang lebih ketat seperti 2.5 patut diuji."
        )
    else:
        action = "adaptive_by_group"
        reason = (
            "Hasil tidak seragam antar ticker. Pertahankan 2.0 sebagai kontrol, "
            "lalu uji threshold berbeda per kelompok saham."
        )

    return {
        "scope": label,
        "action": action,
        "reason": reason,
        "median_trade_reduction_pct": median_trade_reduction_pct,
        "quality_improvement_share_pct": quality_improvement_share_pct,
        "strong_improvement_share_pct": strong_improvement_share_pct,
        "deterioration_share_pct": deterioration_share_pct,
    }


def analyze_by_metadata(
    classified_df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame],
) -> MetadataAnalysis:
    """Merge optional metadata and summarize results by group."""

    if metadata_df is None or metadata_df.empty:
        return MetadataAnalysis(
            available=False,
            merged_df=classified_df.copy(),
            group_summary_df=pd.DataFrame(),
            warnings=[],
        )

    warnings: List[str] = []
    merged_df = classified_df.merge(metadata_df, on="ticker", how="left", suffixes=("", "_meta"))
    available_fields = [column for column in GROUP_METADATA_COLUMNS if column in merged_df.columns]
    if not available_fields:
        warnings.append(
            "Metadata tersedia tetapi tidak memuat kolom grouping yang didukung: "
            f"{GROUP_METADATA_COLUMNS}."
        )
        return MetadataAnalysis(
            available=False,
            merged_df=merged_df,
            group_summary_df=pd.DataFrame(),
            warnings=warnings,
        )

    group_rows: List[Dict[str, object]] = []
    for group_field in available_fields:
        subset = merged_df.loc[merged_df[group_field].notna()].copy()
        for group_value, group_df in subset.groupby(group_field):
            if len(group_df) < 2:
                group_threshold = {
                    "action": "insufficient_sample",
                    "reason": "Ukuran sampel grup terlalu kecil untuk rekomendasi threshold yang meyakinkan.",
                }
                strict_share_pct = np.nan
                strict_policy = "insufficient_sample"
            else:
                group_threshold = recommend_threshold_policy(group_df, label=f"{group_field}:{group_value}")
                strict_share_pct = np.nan
                strict_policy = "not_available"

            if "strict_trade_retention_pct" in group_df.columns and group_df["strict_trade_retention_pct"].notna().any():
                strict_mask = (
                    (group_df["strict_delta_win_rate"].fillna(0) > 0)
                    & (group_df["strict_delta_average_return"].fillna(0) >= 0)
                    & (group_df["strict_trade_retention_pct"].fillna(0) >= 50.0)
                )
                if len(group_df) >= 2:
                    strict_share_pct = _safe_percentage(int(strict_mask.sum()), len(group_df))
                    if strict_share_pct >= 60.0:
                        strict_policy = "strict_cocok"
                    elif strict_share_pct >= 25.0:
                        strict_policy = "strict_opsional"
                    else:
                        strict_policy = "strict_kurang_menarik"

            group_rows.append(
                {
                    "group_field": group_field,
                    "group_value": group_value,
                    "ticker_count": int(len(group_df)),
                    "cocok_count": int((group_df["classification"] == "cocok").sum()),
                    "netral_count": int((group_df["classification"] == "netral").sum()),
                    "tidak_cocok_count": int((group_df["classification"] == "tidak_cocok").sum()),
                    "cocok_share_pct": _safe_percentage(int((group_df["classification"] == "cocok").sum()), len(group_df)),
                    "mean_delta_trades": _safe_mean(group_df["delta_trades"]),
                    "mean_delta_win_rate": _safe_mean(group_df["delta_win_rate"]),
                    "mean_delta_average_return": _safe_mean(group_df["delta_average_return"]),
                    "median_trade_reduction_pct": _safe_median(group_df["trade_reduction_pct"]),
                    "threshold_action": group_threshold["action"],
                    "threshold_reason": group_threshold["reason"],
                    "strict_better_share_pct": strict_share_pct,
                    "strict_policy": strict_policy,
                }
            )

    group_summary_df = pd.DataFrame(group_rows)
    if not group_summary_df.empty:
        group_summary_df = group_summary_df.sort_values(
            ["group_field", "cocok_share_pct", "mean_delta_average_return"],
            ascending=[True, False, False],
        ).reset_index(drop=True)

    return MetadataAnalysis(
        available=not group_summary_df.empty,
        merged_df=merged_df,
        group_summary_df=group_summary_df,
        warnings=warnings,
    )


def build_analysis_summary_dataframe(
    classified_df: pd.DataFrame,
    rankings: Dict[str, pd.DataFrame],
    strict_analysis: StrictModeAnalysis,
    overall_threshold: Dict[str, object],
    aggregate_df: Optional[pd.DataFrame] = None,
    skipped_df: Optional[pd.DataFrame] = None,
    metadata_analysis: Optional[MetadataAnalysis] = None,
) -> pd.DataFrame:
    """Build a long-form CSV-friendly summary table."""

    rows: List[Dict[str, object]] = []
    total_tickers = int(len(classified_df))
    cocok_count = int((classified_df["classification"] == "cocok").sum())
    netral_count = int((classified_df["classification"] == "netral").sum())
    tidak_cocok_count = int((classified_df["classification"] == "tidak_cocok").sum())

    overall_rows = [
        ("ticker_count", total_tickers, "Total ticker yang dianalisis."),
        ("cocok_count", cocok_count, "Ticker yang cocok dengan Phase A."),
        ("netral_count", netral_count, "Ticker dengan hasil campuran."),
        ("tidak_cocok_count", tidak_cocok_count, "Ticker yang tidak cocok dengan Phase A."),
        ("mean_delta_trades", _safe_mean(classified_df["delta_trades"]), "Rata-rata perubahan jumlah trade."),
        ("mean_delta_win_rate", _safe_mean(classified_df["delta_win_rate"]), "Rata-rata perubahan win rate."),
        (
            "mean_delta_average_return",
            _safe_mean(classified_df["delta_average_return"]),
            "Rata-rata perubahan average return.",
        ),
        (
            "median_trade_reduction_pct",
            overall_threshold["median_trade_reduction_pct"],
            "Median persentase penurunan trade vs baseline.",
        ),
        (
            "threshold_action",
            overall_threshold["action"],
            overall_threshold["reason"],
        ),
    ]

    for metric, value, notes in overall_rows:
        rows.append({"section": "overall", "metric": metric, "value": value, "notes": notes})

    if aggregate_df is not None and not aggregate_df.empty:
        aggregate_row = aggregate_df.iloc[0]
        for metric in aggregate_df.columns:
            rows.append(
                {
                    "section": "aggregate_input",
                    "metric": metric,
                    "value": aggregate_row[metric],
                    "notes": "Nilai dari output aggregate evaluator.",
                }
            )

    skipped_count = int(len(skipped_df)) if skipped_df is not None else 0
    rows.append(
        {
            "section": "input_quality",
            "metric": "skipped_file_count",
            "value": skipped_count,
            "notes": "Jumlah file yang di-skip evaluator sebelumnya.",
        }
    )

    if strict_analysis.available:
        strict_rows = [
            ("policy", strict_analysis.policy, strict_analysis.policy_reason),
            ("eligible_ticker_count", strict_analysis.eligible_ticker_count, "Ticker yang bisa dibandingkan Phase A vs strict."),
            ("improved_share_pct", strict_analysis.improved_share_pct, "Persentase ticker yang membaik dengan strict."),
            (
                "too_restrictive_share_pct",
                strict_analysis.too_restrictive_share_pct,
                "Persentase ticker yang kehilangan trade tanpa manfaat strict.",
            ),
            ("mean_delta_trades", strict_analysis.mean_delta_trades, "Rata-rata perubahan trade dari default ke strict."),
            ("mean_delta_win_rate", strict_analysis.mean_delta_win_rate, "Rata-rata perubahan win rate dari default ke strict."),
            (
                "mean_delta_average_return",
                strict_analysis.mean_delta_average_return,
                "Rata-rata perubahan average return dari default ke strict.",
            ),
        ]
        for metric, value, notes in strict_rows:
            rows.append({"section": "strict_mode", "metric": metric, "value": value, "notes": notes})

    if metadata_analysis is not None and metadata_analysis.available:
        rows.append(
            {
                "section": "metadata",
                "metric": "group_row_count",
                "value": int(len(metadata_analysis.group_summary_df)),
                "notes": "Jumlah baris analisis group berdasarkan metadata ticker.",
            }
        )

    ranking_metric_map = {
        "top_win_rate": "delta_win_rate",
        "top_average_return": "delta_average_return",
        "top_trade_reduction": "delta_trades",
        "top_deterioration": "delta_average_return",
    }
    for ranking_name, ranking_df in rankings.items():
        metric_name = ranking_metric_map[ranking_name]
        for rank_index, (_, row) in enumerate(ranking_df.iterrows(), start=1):
            rows.append(
                {
                    "section": ranking_name,
                    "metric": f"rank_{rank_index}",
                    "value": row["ticker"],
                    "notes": (
                        f"{metric_name}={_safe_float(row[metric_name]):.4f}; "
                        f"delta_win_rate={_safe_float(row['delta_win_rate']):.4f}; "
                        f"delta_average_return={_safe_float(row['delta_average_return']):.4f}; "
                        f"delta_trades={_safe_float(row['delta_trades']):.4f}"
                    ),
                }
            )

    summary_df = pd.DataFrame(rows)
    return summary_df.reindex(columns=SUMMARY_EXPORT_COLUMNS)


def generate_recommendations(
    classified_df: pd.DataFrame,
    strict_analysis: StrictModeAnalysis,
    metadata_analysis: MetadataAnalysis,
    rankings: Dict[str, pd.DataFrame],
    overall_threshold: Dict[str, object],
    aggregate_df: Optional[pd.DataFrame] = None,
    skipped_df: Optional[pd.DataFrame] = None,
) -> str:
    """Build a human-readable recommendation report."""

    total_tickers = int(len(classified_df))
    cocok_count = int((classified_df["classification"] == "cocok").sum())
    netral_count = int((classified_df["classification"] == "netral").sum())
    tidak_cocok_count = int((classified_df["classification"] == "tidak_cocok").sum())
    cocok_share_pct = _safe_percentage(cocok_count, total_tickers)
    mean_delta_win_rate = _safe_mean(classified_df["delta_win_rate"])
    mean_delta_average_return = _safe_mean(classified_df["delta_average_return"])
    median_trade_reduction_pct = overall_threshold["median_trade_reduction_pct"]

    if cocok_share_pct >= 50.0 and mean_delta_average_return >= 0:
        phase_a_effectiveness = "Phase A efektif secara umum untuk subset ticker yang diuji."
    elif cocok_share_pct >= 30.0:
        phase_a_effectiveness = "Phase A cenderung selektif: bekerja pada subset ticker tertentu, tetapi tidak merata."
    else:
        phase_a_effectiveness = "Phase A belum terlihat efektif secara luas pada kumpulan ticker ini."

    lines: List[str] = [
        "Phase A Result Analysis",
        "=======================",
        "",
        "Catatan penting:",
        "- Rekomendasi threshold di bawah ini adalah inferensi dari hasil threshold saat ini (volume_ratio >= 2.0).",
        "- Ini belum membuktikan bahwa 1.5 atau 2.5 lebih baik; rekomendasinya adalah prioritas eksperimen berikutnya.",
        "",
        "Ringkasan umum:",
        f"- Total ticker dianalisis: {total_tickers}",
        f"- Cocok: {cocok_count}",
        f"- Netral: {netral_count}",
        f"- Tidak cocok: {tidak_cocok_count}",
        f"- Rata-rata delta win rate: {mean_delta_win_rate:.4f}",
        f"- Rata-rata delta average return: {mean_delta_average_return:.4f}",
        f"- Median penurunan trade vs baseline: {median_trade_reduction_pct:.4f}%",
        f"- Kesimpulan umum: {phase_a_effectiveness}",
    ]

    if aggregate_df is not None and not aggregate_df.empty:
        aggregate_row = aggregate_df.iloc[0]
        lines.extend(
            [
                "",
                "Ringkasan aggregate evaluator:",
                f"- Baseline total trades sum: {aggregate_row.get('baseline_total_trades_sum', 'n/a')}",
                f"- Phase A total trades sum: {aggregate_row.get('phase_a_total_trades_sum', 'n/a')}",
                f"- Mean delta win rate aggregate: {aggregate_row.get('delta_win_rate_mean', 'n/a')}",
                f"- Mean delta average return aggregate: {aggregate_row.get('delta_average_return_mean', 'n/a')}",
            ]
        )

    skipped_count = int(len(skipped_df)) if skipped_df is not None else 0
    lines.extend(
        [
            "",
            "Klasifikasi ticker:",
            f"- Cocok biasanya berarti trade berkurang tetapi win rate dan average return membaik.",
            f"- Tidak cocok berarti trade turun tanpa peningkatan kualitas, atau average return memburuk jelas.",
            f"- File evaluator yang sebelumnya di-skip: {skipped_count}",
        ]
    )

    lines.extend(
        [
            "",
            "Rekomendasi threshold:",
            f"- Aksi utama: {overall_threshold['action']}",
            f"- Alasan: {overall_threshold['reason']}",
        ]
    )

    if overall_threshold["action"] == "keep_2_0":
        lines.append("- Rekomendasi praktis: pertahankan 2.0 sebagai baseline eksperimen berikutnya.")
    elif overall_threshold["action"] == "test_1_5":
        lines.append("- Rekomendasi praktis: uji threshold 1.5 lebih dulu pada ticker dengan trade terlalu sedikit.")
    elif overall_threshold["action"] == "test_2_5":
        lines.append("- Rekomendasi praktis: uji threshold 2.5 pada ticker yang masih penuh false signal.")
    else:
        lines.append("- Rekomendasi praktis: siapkan adaptive threshold per kelompok saham.")

    if strict_analysis.available:
        lines.extend(
            [
                "",
                "Analisis strict mode:",
                f"- Policy: {strict_analysis.policy}",
                f"- Alasan: {strict_analysis.policy_reason}",
                f"- Persentase ticker yang membaik dengan strict: {strict_analysis.improved_share_pct:.4f}%",
                f"- Persentase ticker yang terlalu terpangkas oleh strict: {strict_analysis.too_restrictive_share_pct:.4f}%",
                f"- Rata-rata delta trades strict vs default: {strict_analysis.mean_delta_trades:.4f}",
                f"- Rata-rata delta win rate strict vs default: {strict_analysis.mean_delta_win_rate:.4f}",
                f"- Rata-rata delta average return strict vs default: {strict_analysis.mean_delta_average_return:.4f}",
            ]
        )
        if strict_analysis.policy == "layak_jadi_default":
            lines.append("- Keputusan: strict mode layak dipertimbangkan sebagai default.")
        elif strict_analysis.policy == "layak_jadi_opsi":
            lines.append("- Keputusan: strict mode sebaiknya tetap menjadi opsi, bukan default.")
        else:
            lines.append("- Keputusan: strict mode jangan dijadikan default pada tahap ini.")
    else:
        lines.extend(
            [
                "",
                "Analisis strict mode:",
                "- Kolom strict tidak tersedia atau tidak cukup untuk dianalisis.",
            ]
        )

    if metadata_analysis.available and not metadata_analysis.group_summary_df.empty:
        lines.extend(["", "Analisis berdasarkan metadata:"])
        for _, row in metadata_analysis.group_summary_df.iterrows():
            if int(row["ticker_count"]) < 2:
                continue
            lines.append(
                f"- {row['group_field']}={row['group_value']}: "
                f"mean_delta_win_rate={_safe_float(row['mean_delta_win_rate']):.4f}, "
                f"mean_delta_average_return={_safe_float(row['mean_delta_average_return']):.4f}, "
                f"threshold={row['threshold_action']}."
            )

        market_cap_rows = metadata_analysis.group_summary_df.loc[
            metadata_analysis.group_summary_df["group_field"] == "market_cap_group"
        ]
        if not market_cap_rows.empty:
            big_cap_rows = market_cap_rows.loc[
                market_cap_rows["group_value"].astype(str).str.contains("big", case=False, na=False)
            ]
            if not big_cap_rows.empty and (big_cap_rows["threshold_action"] == "test_1_5").any():
                lines.append("- Big cap cenderung kehilangan trade terlalu banyak; uji threshold 1.5 lebih dulu pada grup ini.")

        beta_rows = metadata_analysis.group_summary_df.loc[
            metadata_analysis.group_summary_df["group_field"] == "beta_group"
        ]
        if not beta_rows.empty:
            high_beta_rows = beta_rows.loc[
                beta_rows["group_value"].astype(str).str.contains("high", case=False, na=False)
            ]
            if not high_beta_rows.empty and (high_beta_rows["threshold_action"] == "test_2_5").any():
                lines.append("- Saham high beta terlihat lebih noisy; threshold lebih ketat seperti 2.5 patut diuji.")
    else:
        lines.extend(
            [
                "",
                "Analisis berdasarkan metadata:",
                "- Metadata ticker tidak tersedia, jadi rekomendasi group-based belum dihitung.",
            ]
        )

    lines.extend(
        [
            "",
            "Top movers:",
            f"- Top delta win rate: {', '.join(rankings['top_win_rate']['ticker'].tolist()) if not rankings['top_win_rate'].empty else 'n/a'}",
            f"- Top delta average return: {', '.join(rankings['top_average_return']['ticker'].tolist()) if not rankings['top_average_return'].empty else 'n/a'}",
            f"- Trade reduction terbesar: {', '.join(rankings['top_trade_reduction']['ticker'].tolist()) if not rankings['top_trade_reduction'].empty else 'n/a'}",
            f"- Memburuk paling jelas: {', '.join(rankings['top_deterioration']['ticker'].tolist()) if not rankings['top_deterioration'].empty else 'n/a'}",
        ]
    )

    lines.extend(
        [
            "",
            "Eksperimen berikutnya:",
            "- Pertahankan evaluator saat ini sebagai baseline kontrol.",
            "- Tambahkan pengujian threshold volume_ratio 1.5, 2.0, dan 2.5 pada ticker/group yang disarankan laporan ini.",
            "- Bandingkan default vs strict hanya pada ticker yang masih menghasilkan trade cukup.",
            "- Setelah metadata ticker lengkap, ulangi analisis untuk market_cap_group, sector, dan beta_group.",
        ]
    )

    return "\n".join(lines) + "\n"


def create_visual_summary(classified_df: pd.DataFrame, output_dir: Path) -> List[str]:
    """Export simple histogram and scatter plots when matplotlib is available."""

    cache_root = Path("/tmp") / "quant-phase-a-mpl"
    cache_root.mkdir(parents=True, exist_ok=True)
    mpl_config_dir = cache_root / "mplconfig"
    xdg_cache_dir = cache_root / "cache"
    mpl_config_dir.mkdir(parents=True, exist_ok=True)
    xdg_cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_config_dir))
    os.environ.setdefault("XDG_CACHE_HOME", str(xdg_cache_dir))

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return ["matplotlib is not installed. PNG visual summary skipped."]

    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: List[str] = []
    plot_specs = [
        (
            "phase_a_delta_win_rate.png",
            "hist",
            "delta_win_rate",
            "Delta Win Rate",
        ),
        (
            "phase_a_delta_average_return.png",
            "hist",
            "delta_average_return",
            "Delta Average Return",
        ),
        (
            "phase_a_trade_vs_winrate.png",
            "scatter",
            ("delta_trades", "delta_win_rate"),
            "Delta Trades vs Delta Win Rate",
        ),
        (
            "phase_a_trade_vs_avgreturn.png",
            "scatter",
            ("delta_trades", "delta_average_return"),
            "Delta Trades vs Delta Average Return",
        ),
    ]

    for filename, plot_type, columns, title in plot_specs:
        target_path = output_dir / filename
        fig, axis = plt.subplots(figsize=(7, 4.5))
        try:
            if plot_type == "hist":
                series = pd.to_numeric(classified_df[columns], errors="coerce").dropna()
                if series.empty:
                    warnings.append(f"Skipped plot {filename} because '{columns}' has no valid values.")
                    plt.close(fig)
                    continue
                bins = min(20, max(6, len(series)))
                axis.hist(series, bins=bins, color="#1f77b4", edgecolor="black", alpha=0.85)
                axis.axvline(0.0, color="red", linestyle="--", linewidth=1.0)
                axis.set_xlabel(columns)
                axis.set_ylabel("Ticker Count")
            else:
                x_column, y_column = columns
                plot_df = classified_df[[x_column, y_column]].apply(pd.to_numeric, errors="coerce").dropna()
                if plot_df.empty:
                    warnings.append(
                        f"Skipped plot {filename} because '{x_column}'/'{y_column}' have no valid values."
                    )
                    plt.close(fig)
                    continue
                axis.scatter(plot_df[x_column], plot_df[y_column], color="#2ca02c", alpha=0.8)
                axis.axvline(0.0, color="red", linestyle="--", linewidth=1.0)
                axis.axhline(0.0, color="red", linestyle="--", linewidth=1.0)
                axis.set_xlabel(x_column)
                axis.set_ylabel(y_column)

            axis.set_title(title)
            axis.grid(alpha=0.2)
            fig.tight_layout()
            fig.savefig(target_path, dpi=140)
        finally:
            plt.close(fig)

    return warnings


def export_analysis_outputs(
    output_dir: Path,
    summary_metrics_df: pd.DataFrame,
    classification_df: pd.DataFrame,
    recommendations_text: str,
    rankings: Dict[str, pd.DataFrame],
    strict_analysis: StrictModeAnalysis,
    metadata_analysis: MetadataAnalysis,
) -> None:
    """Export all analysis artifacts to disk."""

    output_dir.mkdir(parents=True, exist_ok=True)

    summary_csv = output_dir / "phase_a_analysis_summary.csv"
    summary_metrics_df.to_csv(summary_csv, index=False)
    print(f"Saved analysis summary to {summary_csv}")

    classification_csv = output_dir / "phase_a_ticker_classification.csv"
    classification_df.to_csv(classification_csv, index=False)
    print(f"Saved ticker classification to {classification_csv}")

    recommendations_txt = output_dir / "phase_a_recommendations.txt"
    recommendations_txt.write_text(recommendations_text, encoding="utf-8")
    print(f"Saved recommendations to {recommendations_txt}")

    if metadata_analysis.available and not metadata_analysis.group_summary_df.empty:
        group_csv = output_dir / "phase_a_group_analysis.csv"
        metadata_analysis.group_summary_df.to_csv(group_csv, index=False)
        print(f"Saved group analysis to {group_csv}")

    workbook_path = output_dir / "phase_a_analysis_summary.xlsx"
    try:
        with pd.ExcelWriter(workbook_path) as writer:
            summary_metrics_df.to_excel(writer, sheet_name="summary_metrics", index=False)
            classification_df.to_excel(writer, sheet_name="ticker_classification", index=False)
            for sheet_name, ranking_df in rankings.items():
                ranking_df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
            if strict_analysis.available and not strict_analysis.detail_df.empty:
                strict_analysis.detail_df.to_excel(writer, sheet_name="strict_mode", index=False)
            if metadata_analysis.available and not metadata_analysis.group_summary_df.empty:
                metadata_analysis.group_summary_df.to_excel(writer, sheet_name="group_analysis", index=False)
        print(f"Saved Excel workbook to {workbook_path}")
    except ImportError:
        print("Warning: openpyxl/xlsxwriter is not installed. Excel export skipped.")
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Warning: Excel export failed: {exc}")

    plot_warnings = create_visual_summary(classification_df, output_dir)
    for warning in plot_warnings:
        print(f"Warning: {warning}")


def print_analysis_console(
    classified_df: pd.DataFrame,
    rankings: Dict[str, pd.DataFrame],
    strict_analysis: StrictModeAnalysis,
    metadata_analysis: MetadataAnalysis,
    warnings: Sequence[str],
) -> None:
    """Print a concise console summary of the analysis."""

    if warnings:
        print("\nInput warnings:")
        for warning in warnings:
            print(f"- {warning}")

    print("\nTicker classification summary:")
    counts = classified_df["classification"].value_counts().reindex(CLASSIFICATION_ORDER, fill_value=0)
    for label in CLASSIFICATION_ORDER:
        print(f"- {label}: {int(counts[label])}")

    for label in CLASSIFICATION_ORDER:
        table = classified_df.loc[classified_df["classification"] == label, [
            "ticker",
            "classification_reason",
            "tuning_hint",
            "delta_trades",
            "delta_win_rate",
            "delta_average_return",
        ]]
        print(f"\nTicker {label}:")
        if table.empty:
            print("None")
        else:
            print(table.to_string(index=False))

    ranking_titles = {
        "top_win_rate": "Top 10 delta win rate",
        "top_average_return": "Top 10 delta average return",
        "top_trade_reduction": "Top 10 trade reduction",
        "top_deterioration": "Top 10 deterioration",
    }
    for name, title in ranking_titles.items():
        print(f"\n{title}:")
        table = rankings[name]
        if table.empty:
            print("None")
        else:
            print(table.to_string(index=False))

    print("\nStrict mode summary:")
    if strict_analysis.available:
        print(f"- policy: {strict_analysis.policy}")
        print(f"- reason: {strict_analysis.policy_reason}")
        print(f"- improved_share_pct: {strict_analysis.improved_share_pct:.4f}")
        print(f"- too_restrictive_share_pct: {strict_analysis.too_restrictive_share_pct:.4f}")
    else:
        print(f"- {strict_analysis.policy_reason}")

    print("\nMetadata analysis:")
    if metadata_analysis.available and not metadata_analysis.group_summary_df.empty:
        print(metadata_analysis.group_summary_df.to_string(index=False))
    else:
        print("None")


def analyze_phase_a_results(
    summary_file: Path,
    aggregate_file: Optional[Path] = None,
    skipped_file: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
    output_dir: Path = Path("output"),
) -> Dict[str, object]:
    """Run the full analysis workflow and export outputs."""

    loaded = load_summary_data(
        summary_file=summary_file,
        aggregate_file=aggregate_file,
        skipped_file=skipped_file,
        metadata_file=metadata_file,
    )

    classified_df = classify_ticker_performance(loaded.summary_df)
    rankings = rank_top_movers(classified_df)
    strict_analysis = analyze_strict_mode(classified_df)
    metadata_analysis = analyze_by_metadata(classified_df, loaded.metadata_df)
    overall_threshold = recommend_threshold_policy(classified_df)
    summary_metrics_df = build_analysis_summary_dataframe(
        classified_df=classified_df,
        rankings=rankings,
        strict_analysis=strict_analysis,
        overall_threshold=overall_threshold,
        aggregate_df=loaded.aggregate_df,
        skipped_df=loaded.skipped_df,
        metadata_analysis=metadata_analysis,
    )
    recommendations_text = generate_recommendations(
        classified_df=classified_df,
        strict_analysis=strict_analysis,
        metadata_analysis=metadata_analysis,
        rankings=rankings,
        overall_threshold=overall_threshold,
        aggregate_df=loaded.aggregate_df,
        skipped_df=loaded.skipped_df,
    )

    export_analysis_outputs(
        output_dir=Path(output_dir),
        summary_metrics_df=summary_metrics_df,
        classification_df=classified_df,
        recommendations_text=recommendations_text,
        rankings=rankings,
        strict_analysis=strict_analysis,
        metadata_analysis=metadata_analysis,
    )
    print_analysis_console(
        classified_df=classified_df,
        rankings=rankings,
        strict_analysis=strict_analysis,
        metadata_analysis=metadata_analysis,
        warnings=loaded.warnings + metadata_analysis.warnings,
    )

    return {
        "summary_metrics_df": summary_metrics_df,
        "classification_df": classified_df,
        "rankings": rankings,
        "strict_analysis": strict_analysis,
        "metadata_analysis": metadata_analysis,
        "recommendations_text": recommendations_text,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Analyze Phase A evaluation outputs and recommend threshold tuning steps."
    )
    parser.add_argument(
        "--summary-file",
        default="output/phase_a_summary.csv",
        help="Required summary CSV from the evaluator. Default: output/phase_a_summary.csv",
    )
    parser.add_argument(
        "--aggregate-file",
        default="output/phase_a_aggregate_summary.csv",
        help="Optional aggregate CSV from the evaluator. Default: output/phase_a_aggregate_summary.csv",
    )
    parser.add_argument(
        "--skipped-file",
        default="output/phase_a_skipped.csv",
        help="Optional skipped-file CSV from the evaluator. Default: output/phase_a_skipped.csv",
    )
    parser.add_argument(
        "--metadata-file",
        default=None,
        help="Optional ticker metadata CSV with fields like category, market_cap_group, sector, beta_group.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory for analysis outputs. Default: output",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)

    try:
        analyze_phase_a_results(
            summary_file=Path(args.summary_file),
            aggregate_file=Path(args.aggregate_file) if args.aggregate_file else None,
            skipped_file=Path(args.skipped_file) if args.skipped_file else None,
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            output_dir=Path(args.output_dir),
        )
        return 0
    except AnalysisCliError as exc:
        print(str(exc))
        suggestions = list(exc.suggestions)
        if "phase_a_summary.csv" in str(exc):
            suggestions.append(f"Validate raw input data first with: {_validator_command_hint()}")
        _print_next_steps(suggestions)
        return 1
    except Exception as exc:
        print(f"Analysis failed: {exc}")
        _print_next_steps(
            [
                f"Check that the evaluator output exists: {shlex.quote(str(args.summary_file))}",
                f"Regenerate evaluator output if needed: {_evaluate_command_hint()}",
            ]
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
