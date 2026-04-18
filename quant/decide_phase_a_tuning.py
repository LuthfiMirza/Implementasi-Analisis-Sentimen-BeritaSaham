"""Convert Phase A analysis artifacts into concrete tuning decisions.

Example
-------
Preferred execution from project root:

    python3 -m quant.decide_phase_a_tuning \
      --recommendations-file output/phase_a_recommendations.txt \
      --classification-file output/phase_a_ticker_classification.csv \
      --analysis-summary-file output/phase_a_analysis_summary.csv \
      --group-analysis-file output/phase_a_group_analysis.csv \
      --summary-file output/phase_a_summary.csv \
      --output-dir output
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SUPPORTED_METADATA_COLUMNS = ["ticker", "category", "market_cap_group", "sector", "beta_group"]
CLASSIFICATION_REQUIRED_COLUMNS = ["ticker", "classification"]
CLASSIFICATION_OPTIONAL_COLUMNS = [
    "classification_reason",
    "tuning_hint",
    "baseline_total_trades",
    "phase_a_total_trades",
    "delta_trades",
    "trade_reduction_pct",
    "delta_win_rate",
    "delta_average_return",
    "strict_total_trades",
    "strict_win_rate",
    "strict_average_return",
    "strict_delta_trades",
    "strict_delta_win_rate",
    "strict_delta_average_return",
    "strict_trade_retention_pct",
]
CLASSIFICATION_NUMERIC_COLUMNS = [
    "baseline_total_trades",
    "phase_a_total_trades",
    "delta_trades",
    "trade_reduction_pct",
    "delta_win_rate",
    "delta_average_return",
    "strict_total_trades",
    "strict_win_rate",
    "strict_average_return",
    "strict_delta_trades",
    "strict_delta_win_rate",
    "strict_delta_average_return",
    "strict_trade_retention_pct",
]
ANALYSIS_SUMMARY_REQUIRED_COLUMNS = ["section", "metric", "value", "notes"]
GROUP_ANALYSIS_BASE_COLUMNS = [
    "group_field",
    "group_value",
    "ticker_count",
    "cocok_count",
    "netral_count",
    "tidak_cocok_count",
    "cocok_share_pct",
    "mean_delta_trades",
    "mean_delta_win_rate",
    "mean_delta_average_return",
    "median_trade_reduction_pct",
    "threshold_action",
    "threshold_reason",
    "strict_better_share_pct",
    "strict_policy",
]
TICKER_ACTION_COLUMNS = [
    "ticker",
    "classification",
    "action_bucket",
    "action_reason",
    "recommended_threshold_action",
    "strict_mode_action",
    "delta_trades",
    "trade_reduction_pct",
    "delta_win_rate",
    "delta_average_return",
    "baseline_total_trades",
    "phase_a_total_trades",
    "tuning_hint",
    "classification_reason",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
]
GROUP_ACTION_COLUMNS = [
    "group_field",
    "group_value",
    "ticker_count",
    "group_threshold_decision",
    "group_action",
    "group_action_reason",
    "strict_mode_action",
    "sample_quality",
]
EXPERIMENT_COLUMNS = [
    "priority",
    "experiment_id",
    "experiment_name",
    "objective",
    "scope",
    "reason",
    "mandatory_before_phase_b",
]
BUCKET_ORDER = [
    "deploy_candidate",
    "watchlist_candidate",
    "review_needed",
    "avoid_for_now",
]
DEFAULT_THRESHOLD_CODES = {
    "keep_2_0": "keep_threshold_2_0",
    "test_1_5": "test_threshold_1_5",
    "test_2_5": "test_threshold_2_5",
    "adaptive_by_group": "adaptive_threshold_by_group",
    "insufficient_sample": "insufficient_sample",
}
STRICT_POLICY_CODES = {
    "layak_jadi_default": "strict_default_yes",
    "layak_jadi_opsi": "strict_only_for_subset",
    "terlalu_restriktif": "strict_default_no",
    "not_available": "strict_default_no",
    "strict_cocok": "strict_only_for_subset",
    "strict_opsional": "strict_only_for_subset",
    "strict_kurang_menarik": "strict_default_no",
    "insufficient_sample": "strict_default_no",
}


class TuningCliError(ValueError):
    """Friendly CLI error with actionable suggestions."""

    def __init__(self, message: str, suggestions: Optional[Sequence[str]] = None) -> None:
        super().__init__(message)
        self.suggestions = list(suggestions or [])


@dataclass
class LoadedTuningArtifacts:
    """Container for all decision-layer inputs."""

    recommendations_text: str
    recommendations_signals: Dict[str, str]
    classification_df: pd.DataFrame
    analysis_summary_df: Optional[pd.DataFrame]
    group_analysis_df: Optional[pd.DataFrame]
    summary_df: Optional[pd.DataFrame]
    metadata_df: Optional[pd.DataFrame]
    warnings: List[str] = field(default_factory=list)


def _analyzer_command_hint() -> str:
    """Command hint for regenerating analyzer outputs."""

    return (
        "python3 -m quant.analyze_phase_a_results "
        "--summary-file output/phase_a_summary.csv "
        "--aggregate-file output/phase_a_aggregate_summary.csv "
        "--skipped-file output/phase_a_skipped.csv "
        "--output-dir output"
    )


def _evaluator_command_hint() -> str:
    """Command hint for regenerating evaluator outputs."""

    return "python3 -m quant.evaluate_phase_a_real_data --data-dir data --output-dir output --strict"


def _print_next_steps(steps: Sequence[str]) -> None:
    """Print actionable next-step suggestions."""

    cleaned_steps = [step for step in steps if step]
    if not cleaned_steps:
        return

    print("\nNext step suggestions:")
    for step in cleaned_steps:
        print(f"  {step}")


def _safe_float(value: object) -> float:
    """Coerce a scalar into float or NaN."""

    if value is None:
        return np.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _safe_mean(series: pd.Series) -> float:
    """Return a NaN-safe mean."""

    if series.empty:
        return np.nan
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.dropna().empty:
        return np.nan
    return float(numeric.mean())


def _safe_median(series: pd.Series) -> float:
    """Return a NaN-safe median."""

    if series.empty:
        return np.nan
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.dropna().empty:
        return np.nan
    return float(numeric.median())


def _safe_percentage(numerator: float, denominator: float) -> float:
    """Return percentage or NaN when denominator is invalid."""

    if denominator in (0, 0.0) or pd.isna(denominator):
        return np.nan
    return float((numerator / denominator) * 100.0)


def _normalize_ticker_filter(tickers: Optional[Iterable[str]]) -> Optional[set[str]]:
    """Normalize optional ticker filter input."""

    if not tickers:
        return None

    normalized: set[str] = set()
    for item in tickers:
        for token in str(item).split(","):
            token = token.strip().upper()
            if token:
                normalized.add(token)
    return normalized or None


def _read_required_text(path: Path, label: str) -> str:
    """Read a required text file with friendly errors."""

    target = Path(path)
    if not target.exists():
        raise TuningCliError(
            f"{label} file not found: {target}",
            suggestions=[f"Regenerate analyzer outputs with: {_analyzer_command_hint()}"],
        )
    if not target.is_file():
        raise TuningCliError(f"{label} path is not a file: {target}")

    try:
        text = target.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - defensive
        raise TuningCliError(f"Failed to read {label} file {target}: {exc}") from exc

    if not text.strip():
        raise TuningCliError(f"{label} file is empty: {target}")

    return text


def _read_required_csv(path: Path, label: str) -> pd.DataFrame:
    """Read a required CSV file with friendly errors."""

    target = Path(path)
    if not target.exists():
        raise TuningCliError(
            f"{label} file not found: {target}",
            suggestions=[f"Regenerate analyzer outputs with: {_analyzer_command_hint()}"],
        )
    if not target.is_file():
        raise TuningCliError(f"{label} path is not a file: {target}")

    try:
        frame = pd.read_csv(target)
    except pd.errors.EmptyDataError as exc:
        raise TuningCliError(f"{label} file is empty: {target}") from exc
    except pd.errors.ParserError as exc:
        raise TuningCliError(f"{label} CSV parser error in {target}: {exc}") from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise TuningCliError(f"Failed to read {label} file {target}: {exc}") from exc

    if frame.empty:
        raise TuningCliError(f"{label} file contains no rows: {target}")

    return frame


def _read_optional_csv(path: Optional[Path], label: str) -> tuple[Optional[pd.DataFrame], List[str]]:
    """Read an optional CSV file and downgrade failures to warnings."""

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


def parse_recommendations_text(text: str) -> Dict[str, str]:
    """Extract structured hints from the analyzer recommendation text."""

    signals: Dict[str, str] = {}
    patterns = {
        "threshold_action": r"Aksi utama:\s*([A-Za-z0-9_]+)",
        "strict_policy": r"Policy:\s*([A-Za-z0-9_]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            signals[key] = match.group(1).strip()
    return signals


def _standardize_classification_frame(
    classification_df: pd.DataFrame,
    summary_df: Optional[pd.DataFrame] = None,
) -> tuple[pd.DataFrame, List[str]]:
    """Validate and normalize ticker classification CSV."""

    warnings: List[str] = []
    missing_required = [
        column for column in CLASSIFICATION_REQUIRED_COLUMNS if column not in classification_df.columns
    ]
    if missing_required:
        raise TuningCliError(
            "Classification file is missing required columns: "
            f"{missing_required}. Required columns: {CLASSIFICATION_REQUIRED_COLUMNS}"
        )

    frame = classification_df.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    frame["classification"] = (
        frame["classification"].astype(str).str.strip().str.lower().replace(
            {"tidak cocok": "tidak_cocok", "tidak-cocok": "tidak_cocok"}
        )
    )

    duplicate_tickers = int(frame["ticker"].duplicated(keep="last").sum())
    if duplicate_tickers:
        warnings.append(
            f"Classification file contains {duplicate_tickers} duplicate ticker rows. Keeping the latest row."
        )
        frame = frame.drop_duplicates(subset=["ticker"], keep="last").reset_index(drop=True)

    for column in CLASSIFICATION_OPTIONAL_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan

    if summary_df is not None and "ticker" in summary_df.columns:
        summary = summary_df.copy()
        summary["ticker"] = summary["ticker"].astype(str).str.upper().str.strip()
        numeric_overlap = [column for column in CLASSIFICATION_NUMERIC_COLUMNS if column in summary.columns]
        if numeric_overlap:
            merged = frame.merge(summary[["ticker"] + numeric_overlap], on="ticker", how="left", suffixes=("", "_summary"))
            for column in numeric_overlap:
                summary_column = f"{column}_summary"
                if column not in merged.columns:
                    merged[column] = np.nan
                merged[column] = pd.to_numeric(merged[column], errors="coerce")
                merged[column] = merged[column].fillna(pd.to_numeric(merged[summary_column], errors="coerce"))
                merged = merged.drop(columns=[summary_column])
            frame = merged

    for column in CLASSIFICATION_NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    missing_classification = frame["classification"].replace("", np.nan).isna().sum()
    if missing_classification:
        raise TuningCliError("Classification file contains blank classification values.")

    return frame, warnings


def _standardize_analysis_summary(analysis_summary_df: Optional[pd.DataFrame]) -> tuple[Optional[pd.DataFrame], List[str]]:
    """Validate the optional long-form analysis summary CSV."""

    warnings: List[str] = []
    if analysis_summary_df is None:
        return None, warnings

    missing_columns = [
        column for column in ANALYSIS_SUMMARY_REQUIRED_COLUMNS if column not in analysis_summary_df.columns
    ]
    if missing_columns:
        warnings.append(
            "Analysis summary file is missing required columns: "
            f"{missing_columns}. Skipping this optional input."
        )
        return None, warnings

    frame = analysis_summary_df.copy()
    frame["section"] = frame["section"].astype(str).str.strip()
    frame["metric"] = frame["metric"].astype(str).str.strip()
    return frame, warnings


def _standardize_group_analysis(group_analysis_df: Optional[pd.DataFrame]) -> tuple[Optional[pd.DataFrame], List[str]]:
    """Validate and normalize optional group-analysis CSV."""

    warnings: List[str] = []
    if group_analysis_df is None:
        return None, warnings

    missing_minimum = [
        column for column in ["group_field", "group_value", "ticker_count"] if column not in group_analysis_df.columns
    ]
    if missing_minimum:
        warnings.append(
            "Group analysis file is missing minimum columns: "
            f"{missing_minimum}. Skipping this optional input."
        )
        return None, warnings

    frame = group_analysis_df.copy()
    for column in GROUP_ANALYSIS_BASE_COLUMNS:
        if column not in frame.columns:
            frame[column] = np.nan

    frame["group_field"] = frame["group_field"].astype(str).str.strip()
    frame["group_value"] = frame["group_value"].astype(str).str.strip()
    numeric_columns = [
        "ticker_count",
        "cocok_count",
        "netral_count",
        "tidak_cocok_count",
        "cocok_share_pct",
        "mean_delta_trades",
        "mean_delta_win_rate",
        "mean_delta_average_return",
        "median_trade_reduction_pct",
        "strict_better_share_pct",
    ]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    return frame, warnings


def _standardize_metadata(metadata_df: Optional[pd.DataFrame]) -> tuple[Optional[pd.DataFrame], List[str]]:
    """Validate and normalize optional ticker metadata."""

    warnings: List[str] = []
    if metadata_df is None:
        return None, warnings

    if "ticker" not in metadata_df.columns:
        warnings.append("Metadata file does not contain a 'ticker' column. Skipping metadata.")
        return None, warnings

    frame = metadata_df.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    duplicate_tickers = int(frame["ticker"].duplicated(keep="first").sum())
    if duplicate_tickers:
        warnings.append(
            f"Metadata file contains {duplicate_tickers} duplicate ticker rows. Keeping the first occurrence."
        )
        frame = frame.drop_duplicates(subset=["ticker"], keep="first").reset_index(drop=True)

    available_columns = [column for column in SUPPORTED_METADATA_COLUMNS if column in frame.columns]
    return frame[available_columns], warnings


def _extract_summary_metric(
    analysis_summary_df: Optional[pd.DataFrame],
    section: str,
    metric: str,
) -> Optional[str]:
    """Extract one value from the long-form analysis summary."""

    if analysis_summary_df is None or analysis_summary_df.empty:
        return None
    matched = analysis_summary_df.loc[
        (analysis_summary_df["section"] == section) & (analysis_summary_df["metric"] == metric),
        "value",
    ]
    if matched.empty:
        return None
    return str(matched.iloc[-1]).strip()


def load_analysis_artifacts(
    recommendations_file: Path,
    classification_file: Path,
    analysis_summary_file: Optional[Path] = None,
    group_analysis_file: Optional[Path] = None,
    summary_file: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
) -> LoadedTuningArtifacts:
    """Load all mandatory and optional decision-layer inputs."""

    warnings: List[str] = []

    recommendations_text = _read_required_text(Path(recommendations_file), "Recommendations")
    recommendations_signals = parse_recommendations_text(recommendations_text)

    summary_df, summary_warnings = _read_optional_csv(summary_file, "Summary")
    warnings.extend(summary_warnings)
    if summary_df is not None and "ticker" in summary_df.columns:
        summary_df = summary_df.copy()
        summary_df["ticker"] = summary_df["ticker"].astype(str).str.upper().str.strip()
    elif summary_df is not None:
        warnings.append("Summary file does not contain a 'ticker' column. It will not be used for backfilling.")
        summary_df = None

    classification_df = _read_required_csv(Path(classification_file), "Classification")
    classification_df, classification_warnings = _standardize_classification_frame(
        classification_df=classification_df,
        summary_df=summary_df,
    )
    warnings.extend(classification_warnings)

    analysis_summary_df, analysis_summary_warnings = _read_optional_csv(
        analysis_summary_file, "Analysis summary"
    )
    warnings.extend(analysis_summary_warnings)
    analysis_summary_df, normalized_analysis_warnings = _standardize_analysis_summary(analysis_summary_df)
    warnings.extend(normalized_analysis_warnings)

    group_analysis_df, group_analysis_warnings = _read_optional_csv(group_analysis_file, "Group analysis")
    warnings.extend(group_analysis_warnings)
    group_analysis_df, normalized_group_warnings = _standardize_group_analysis(group_analysis_df)
    warnings.extend(normalized_group_warnings)

    metadata_df, metadata_warnings = _read_optional_csv(metadata_file, "Metadata")
    warnings.extend(metadata_warnings)
    metadata_df, normalized_metadata_warnings = _standardize_metadata(metadata_df)
    warnings.extend(normalized_metadata_warnings)

    if summary_df is not None:
        summary_only = sorted(set(summary_df["ticker"]) - set(classification_df["ticker"]))
        classification_only = sorted(set(classification_df["ticker"]) - set(summary_df["ticker"]))
        if summary_only:
            warnings.append(
                f"{len(summary_only)} ticker from summary output are not present in classification output."
            )
        if classification_only:
            warnings.append(
                f"{len(classification_only)} ticker from classification output are not present in summary output."
            )

    if metadata_df is not None:
        missing_metadata = sorted(set(classification_df["ticker"]) - set(metadata_df["ticker"]))
        extra_metadata = sorted(set(metadata_df["ticker"]) - set(classification_df["ticker"]))
        if missing_metadata:
            warnings.append(
                f"{len(missing_metadata)} ticker in classification output do not have metadata rows."
            )
        if extra_metadata:
            warnings.append(
                f"{len(extra_metadata)} metadata ticker are not present in classification output."
            )

    return LoadedTuningArtifacts(
        recommendations_text=recommendations_text,
        recommendations_signals=recommendations_signals,
        classification_df=classification_df,
        analysis_summary_df=analysis_summary_df,
        group_analysis_df=group_analysis_df,
        summary_df=summary_df,
        metadata_df=metadata_df,
        warnings=warnings,
    )


def _compute_global_stats(classified_df: pd.DataFrame) -> Dict[str, float]:
    """Compute shared statistics used by the decision heuristics."""

    total = int(len(classified_df))
    cocok_count = int((classified_df["classification"] == "cocok").sum())
    netral_count = int((classified_df["classification"] == "netral").sum())
    tidak_cocok_count = int((classified_df["classification"] == "tidak_cocok").sum())
    hint_series = classified_df["tuning_hint"].fillna("unknown").astype(str)
    return {
        "ticker_count": total,
        "cocok_share_pct": _safe_percentage(cocok_count, total),
        "netral_share_pct": _safe_percentage(netral_count, total),
        "tidak_cocok_share_pct": _safe_percentage(tidak_cocok_count, total),
        "deterioration_share_pct": _safe_percentage(
            int((classified_df["delta_average_return"].fillna(0) < 0).sum()),
            total,
        ),
        "mean_delta_win_rate": _safe_mean(classified_df["delta_win_rate"]),
        "mean_delta_average_return": _safe_mean(classified_df["delta_average_return"]),
        "median_trade_reduction_pct": _safe_median(classified_df["trade_reduction_pct"]),
        "keep_hint_share_pct": _safe_percentage(int((hint_series == "keep_2_0").sum()), total),
        "looser_hint_share_pct": _safe_percentage(int((hint_series == "test_1_5").sum()), total),
        "tighter_hint_share_pct": _safe_percentage(int((hint_series == "test_2_5").sum()), total),
        "manual_review_hint_share_pct": _safe_percentage(
            int((hint_series == "review_manually").sum()),
            total,
        ),
    }


def decide_default_threshold(
    classified_df: pd.DataFrame,
    analysis_summary_df: Optional[pd.DataFrame] = None,
    group_analysis_df: Optional[pd.DataFrame] = None,
    recommendations_signals: Optional[Dict[str, str]] = None,
) -> Dict[str, object]:
    """Choose one concrete default-threshold decision."""

    stats = _compute_global_stats(classified_df)
    analyzer_action = _extract_summary_metric(analysis_summary_df, "overall", "threshold_action")
    analyzer_action = analyzer_action or (recommendations_signals or {}).get("threshold_action")

    mapped_group_actions: List[str] = []
    if group_analysis_df is not None and not group_analysis_df.empty:
        sufficient_groups = group_analysis_df.loc[group_analysis_df["ticker_count"].fillna(0) >= 2].copy()
        mapped_group_actions = [
            DEFAULT_THRESHOLD_CODES.get(str(item), "insufficient_sample")
            for item in sufficient_groups["threshold_action"].fillna("insufficient_sample").tolist()
        ]
        mapped_group_actions = [
            item for item in mapped_group_actions if item != "insufficient_sample"
        ]

    if len(set(mapped_group_actions)) >= 2:
        decision_code = "adaptive_threshold_by_group"
        reason = (
            "Analisis group menunjukkan aksi threshold yang berbeda antar kelompok saham, "
            "jadi baseline global tunggal belum cukup kuat."
        )
    elif analyzer_action in DEFAULT_THRESHOLD_CODES:
        mapped_action = DEFAULT_THRESHOLD_CODES[analyzer_action]
        if mapped_action == "keep_threshold_2_0" and (
            stats["cocok_share_pct"] >= 50.0
            and stats["deterioration_share_pct"] <= 25.0
            and stats["mean_delta_average_return"] >= 0
        ):
            decision_code = "keep_threshold_2_0"
            reason = (
                "Mayoritas sinyal analyzer konsisten dengan threshold 2.0 dan hasil aggregate masih positif."
            )
        elif mapped_action == "test_threshold_1_5":
            decision_code = "test_threshold_1_5"
            reason = (
                "Analyzer melihat trade turun terlalu dalam. Threshold 1.5 adalah eksperimen minimum "
                "yang paling logis sebelum melangkah ke fase berikutnya."
            )
        elif mapped_action == "test_threshold_2_5":
            decision_code = "test_threshold_2_5"
            reason = (
                "Analyzer mengindikasikan filter saat ini masih terlalu longgar pada bagian data yang buruk."
            )
        elif mapped_action == "adaptive_threshold_by_group":
            decision_code = "adaptive_threshold_by_group"
            reason = "Analyzer sudah menyarankan threshold yang berbeda antar group."
        else:
            decision_code = mapped_action
            reason = "Keputusan mengikuti sinyal utama dari analyzer."
    elif stats["median_trade_reduction_pct"] <= -70.0 and stats["looser_hint_share_pct"] >= 20.0:
        decision_code = "test_threshold_1_5"
        reason = (
            "Trade berkurang terlalu agresif dan cukup banyak ticker mengarah ke threshold yang lebih longgar."
        )
    elif stats["tighter_hint_share_pct"] >= 25.0 and stats["median_trade_reduction_pct"] > -50.0:
        decision_code = "test_threshold_2_5"
        reason = "Banyak ticker memburuk tanpa pengurangan trade besar, sehingga filter lebih ketat layak diuji."
    elif stats["keep_hint_share_pct"] >= 50.0 and stats["cocok_share_pct"] >= 50.0:
        decision_code = "keep_threshold_2_0"
        reason = "Mayoritas ticker yang membaik juga menyiratkan threshold 2.0 masih relevan."
    else:
        decision_code = "adaptive_threshold_by_group"
        reason = "Sinyal tuning bercampur; keputusan paling defensif adalah memisahkan threshold per group."

    return {
        "decision_code": decision_code,
        "reason": reason,
        "analyzer_action": analyzer_action or "not_available",
        "group_action_set": sorted(set(mapped_group_actions)),
        "evidence": stats,
    }


def _strict_subset_tickers(classified_df: pd.DataFrame) -> pd.DataFrame:
    """Return tickers where strict mode improves quality without killing trade count."""

    strict_columns = ["strict_delta_win_rate", "strict_delta_average_return", "strict_trade_retention_pct"]
    if not all(column in classified_df.columns for column in strict_columns):
        return pd.DataFrame(columns=classified_df.columns)

    mask = (
        (classified_df["strict_delta_win_rate"].fillna(0) > 0)
        & (classified_df["strict_delta_average_return"].fillna(0) >= 0)
        & (classified_df["strict_trade_retention_pct"].fillna(0) >= 50.0)
    )
    return classified_df.loc[mask].copy()


def decide_strict_mode(
    classified_df: pd.DataFrame,
    analysis_summary_df: Optional[pd.DataFrame] = None,
    group_analysis_df: Optional[pd.DataFrame] = None,
    recommendations_signals: Optional[Dict[str, str]] = None,
) -> Dict[str, object]:
    """Choose one concrete strict-mode decision."""

    required_columns = ["strict_delta_trades", "strict_delta_win_rate", "strict_delta_average_return"]
    strict_available = all(column in classified_df.columns for column in required_columns) and any(
        classified_df[column].notna().any() for column in required_columns
    )
    analyzer_policy = _extract_summary_metric(analysis_summary_df, "strict_mode", "policy")
    analyzer_policy = analyzer_policy or (recommendations_signals or {}).get("strict_policy")

    if not strict_available:
        return {
            "decision_code": "strict_default_no",
            "reason": "Kolom strict tidak tersedia, jadi strict mode tidak bisa dijadikan default.",
            "policy_source": analyzer_policy or "not_available",
            "subset_tickers": [],
            "subset_groups": [],
            "metrics": {
                "available": False,
                "improved_share_pct": np.nan,
                "mean_delta_trades": np.nan,
                "mean_delta_win_rate": np.nan,
                "mean_delta_average_return": np.nan,
            },
        }

    strict_subset_df = _strict_subset_tickers(classified_df)
    eligible_df = classified_df.loc[classified_df["phase_a_total_trades"].fillna(0) > 0].copy()
    improved_share_pct = _safe_percentage(len(strict_subset_df), len(eligible_df))
    mean_delta_trades = _safe_mean(eligible_df["strict_delta_trades"])
    mean_delta_win_rate = _safe_mean(eligible_df["strict_delta_win_rate"])
    mean_delta_average_return = _safe_mean(eligible_df["strict_delta_average_return"])

    subset_groups: List[Dict[str, object]] = []
    if group_analysis_df is not None and not group_analysis_df.empty:
        candidate_groups = group_analysis_df.loc[
            (group_analysis_df["ticker_count"].fillna(0) >= 2)
            & (group_analysis_df["strict_policy"].isin(["strict_cocok", "strict_opsional"]))
        ].copy()
        for _, row in candidate_groups.iterrows():
            subset_groups.append(
                {
                    "group_field": row["group_field"],
                    "group_value": row["group_value"],
                    "strict_policy": row["strict_policy"],
                }
            )

    analyzer_mapped = STRICT_POLICY_CODES.get(str(analyzer_policy), None) if analyzer_policy else None
    if analyzer_mapped == "strict_default_yes" and improved_share_pct >= 60.0:
        decision_code = "strict_default_yes"
        reason = "Analyzer dan metrik strict sama-sama menunjukkan manfaat luas, sehingga strict layak jadi default."
    elif subset_groups or len(strict_subset_df) >= 1 or analyzer_mapped == "strict_only_for_subset":
        decision_code = "strict_only_for_subset"
        reason = (
            "Strict mode hanya menunjukkan manfaat pada subset kecil ticker/group. "
            "Karena itu strict tidak dipakai global."
        )
    else:
        decision_code = "strict_default_no"
        reason = "Strict mode tidak menunjukkan manfaat yang cukup luas dan tidak layak dijadikan default."

    return {
        "decision_code": decision_code,
        "reason": reason,
        "policy_source": analyzer_policy or "not_available",
        "subset_tickers": strict_subset_df["ticker"].tolist(),
        "subset_groups": subset_groups,
        "metrics": {
            "available": True,
            "improved_share_pct": improved_share_pct,
            "mean_delta_trades": mean_delta_trades,
            "mean_delta_win_rate": mean_delta_win_rate,
            "mean_delta_average_return": mean_delta_average_return,
        },
    }


def _threshold_action_from_hint(hint: str, default_decision_code: str) -> str:
    """Map analyzer hint or global default decision into a ticker-level threshold action."""

    mapping = {
        "keep_2_0": "keep_threshold_2_0",
        "test_1_5": "test_threshold_1_5",
        "test_2_5": "test_threshold_2_5",
        "review_manually": "review_manually",
    }
    if hint in mapping:
        return mapping[hint]
    return default_decision_code


def _merge_classification_with_metadata(
    classified_df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame],
) -> tuple[pd.DataFrame, List[str]]:
    """Merge optional metadata into the classification frame."""

    warnings: List[str] = []
    if metadata_df is None or metadata_df.empty:
        merged = classified_df.copy()
        for column in SUPPORTED_METADATA_COLUMNS[1:]:
            if column not in merged.columns:
                merged[column] = np.nan
        return merged, warnings

    merged = classified_df.merge(metadata_df, on="ticker", how="left")
    missing_metadata = int(merged["category"].isna().sum()) if "category" in merged.columns else 0
    if missing_metadata:
        warnings.append(
            f"{missing_metadata} ticker in classification output do not have full metadata coverage."
        )
    for column in SUPPORTED_METADATA_COLUMNS[1:]:
        if column not in merged.columns:
            merged[column] = np.nan
    return merged, warnings


def _build_group_actions_from_metadata(merged_df: pd.DataFrame) -> pd.DataFrame:
    """Build group decisions directly from classification+metadata when group CSV is absent."""

    rows: List[Dict[str, object]] = []
    for group_field in SUPPORTED_METADATA_COLUMNS[1:]:
        if group_field not in merged_df.columns:
            continue
        subset = merged_df.loc[merged_df[group_field].notna()].copy()
        for group_value, group_df in subset.groupby(group_field):
            ticker_count = int(len(group_df))
            if ticker_count < 2:
                group_threshold_decision = "insufficient_sample"
                group_action = "insufficient_sample"
                group_action_reason = (
                    "Ukuran sampel grup terlalu kecil untuk memaksa keputusan threshold yang layak."
                )
                strict_mode_action = "insufficient_sample"
                sample_quality = "small_sample"
            else:
                stats = _compute_global_stats(group_df)
                if stats["median_trade_reduction_pct"] <= -70.0 and stats["cocok_share_pct"] < 75.0:
                    group_threshold_decision = "test_threshold_1_5"
                    group_action = "test_looser_threshold"
                    group_action_reason = "Trade di grup ini turun terlalu banyak. Uji threshold lebih longgar."
                elif stats["tidak_cocok_share_pct"] >= 40.0 and stats["median_trade_reduction_pct"] > -50.0:
                    group_threshold_decision = "test_threshold_2_5"
                    group_action = "test_tighter_threshold"
                    group_action_reason = "Noise masih tinggi di grup ini. Uji threshold lebih ketat."
                elif stats["cocok_share_pct"] >= 60.0 and stats["deterioration_share_pct"] <= 25.0:
                    group_threshold_decision = "keep_threshold_2_0"
                    group_action = "keep_current_threshold"
                    group_action_reason = "Grup ini cukup stabil dengan threshold 2.0."
                else:
                    group_threshold_decision = "adaptive_threshold_by_group"
                    group_action = "review_group_specific"
                    group_action_reason = "Hasil grup bercampur sehingga perlu tuning khusus."

                improved_subset = _strict_subset_tickers(group_df)
                improved_share_pct = _safe_percentage(len(improved_subset), ticker_count)
                if improved_share_pct >= 50.0:
                    strict_mode_action = "strict_subset_candidate"
                else:
                    strict_mode_action = "strict_not_recommended"
                sample_quality = "enough_sample"

            rows.append(
                {
                    "group_field": group_field,
                    "group_value": group_value,
                    "ticker_count": ticker_count,
                    "group_threshold_decision": group_threshold_decision,
                    "group_action": group_action,
                    "group_action_reason": group_action_reason,
                    "strict_mode_action": strict_mode_action,
                    "sample_quality": sample_quality,
                }
            )

    if not rows:
        return pd.DataFrame(columns=GROUP_ACTION_COLUMNS)

    group_actions_df = pd.DataFrame(rows).reindex(columns=GROUP_ACTION_COLUMNS)
    return group_actions_df.sort_values(
        ["group_field", "ticker_count", "group_value"],
        ascending=[True, False, True],
    ).reset_index(drop=True)


def build_group_action_plan(
    merged_df: pd.DataFrame,
    group_analysis_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Build concrete per-group action decisions."""

    if group_analysis_df is None or group_analysis_df.empty:
        return _build_group_actions_from_metadata(merged_df)

    rows: List[Dict[str, object]] = []
    for _, row in group_analysis_df.iterrows():
        threshold_decision = DEFAULT_THRESHOLD_CODES.get(
            str(row.get("threshold_action", "insufficient_sample")),
            "insufficient_sample",
        )
        if threshold_decision == "keep_threshold_2_0":
            group_action = "keep_current_threshold"
        elif threshold_decision == "test_threshold_1_5":
            group_action = "test_looser_threshold"
        elif threshold_decision == "test_threshold_2_5":
            group_action = "test_tighter_threshold"
        elif threshold_decision == "adaptive_threshold_by_group":
            group_action = "review_group_specific"
        else:
            group_action = "insufficient_sample"

        strict_policy = str(row.get("strict_policy", "not_available"))
        if strict_policy in {"strict_cocok", "strict_opsional"}:
            strict_mode_action = "strict_subset_candidate"
        elif strict_policy == "strict_kurang_menarik":
            strict_mode_action = "strict_not_recommended"
        else:
            strict_mode_action = "insufficient_sample"

        sample_quality = "enough_sample" if _safe_float(row.get("ticker_count")) >= 2 else "small_sample"
        rows.append(
            {
                "group_field": row["group_field"],
                "group_value": row["group_value"],
                "ticker_count": int(_safe_float(row.get("ticker_count"))),
                "group_threshold_decision": threshold_decision,
                "group_action": group_action,
                "group_action_reason": row.get("threshold_reason", ""),
                "strict_mode_action": strict_mode_action,
                "sample_quality": sample_quality,
            }
        )

    group_actions_df = pd.DataFrame(rows).reindex(columns=GROUP_ACTION_COLUMNS)
    return group_actions_df.sort_values(
        ["group_field", "ticker_count", "group_value"],
        ascending=[True, False, True],
    ).reset_index(drop=True)


def _resolve_group_threshold_for_ticker(row: pd.Series, group_actions_df: pd.DataFrame) -> Optional[str]:
    """Resolve a ticker-level threshold action from matching group decisions."""

    if group_actions_df.empty:
        return None

    matched_actions: List[str] = []
    priority_fields = ["market_cap_group", "beta_group", "sector", "category"]
    for field in priority_fields:
        if field not in row.index or pd.isna(row[field]):
            continue
        matches = group_actions_df.loc[
            (group_actions_df["group_field"] == field)
            & (group_actions_df["group_value"].astype(str) == str(row[field]))
            & (group_actions_df["sample_quality"] == "enough_sample")
        ]
        if matches.empty:
            continue
        action = str(matches.iloc[0]["group_threshold_decision"])
        if action not in {"adaptive_threshold_by_group", "insufficient_sample"}:
            return action
        matched_actions.append(action)

    if len(set(matched_actions)) == 1 and matched_actions:
        return matched_actions[0]
    if len(set(matched_actions)) > 1:
        return "adaptive_threshold_by_group"
    return None


def _ticker_strict_action(
    ticker: str,
    row: pd.Series,
    strict_mode_decision: Dict[str, object],
) -> str:
    """Resolve ticker-level strict-mode action."""

    decision_code = strict_mode_decision["decision_code"]
    if decision_code == "strict_default_yes":
        return "use_strict_default"
    if decision_code == "strict_default_no":
        return "avoid_strict_default"

    subset_tickers = set(strict_mode_decision.get("subset_tickers", []))
    if ticker in subset_tickers:
        return "use_strict_for_this_ticker"

    for subset_group in strict_mode_decision.get("subset_groups", []):
        field = subset_group.get("group_field")
        value = subset_group.get("group_value")
        if field in row.index and pd.notna(row[field]) and str(row[field]) == str(value):
            return "use_strict_for_this_group"

    return "avoid_strict_default"


def build_ticker_action_plan(
    classified_df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame],
    default_threshold_decision: Dict[str, object],
    strict_mode_decision: Dict[str, object],
    group_actions_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """Assign each ticker to one concrete operational bucket."""

    merged_df, warnings = _merge_classification_with_metadata(classified_df, metadata_df)
    action_rows: List[Dict[str, object]] = []

    for _, row in merged_df.iterrows():
        ticker = row["ticker"]
        threshold_action = _resolve_group_threshold_for_ticker(row, group_actions_df)
        if threshold_action is None:
            threshold_action = _threshold_action_from_hint(
                str(row.get("tuning_hint", "")),
                default_threshold_decision["decision_code"],
            )

        strict_mode_action = _ticker_strict_action(ticker, row, strict_mode_decision)
        classification = str(row["classification"])
        delta_win_rate = _safe_float(row.get("delta_win_rate"))
        delta_average_return = _safe_float(row.get("delta_average_return"))
        trade_reduction_pct = _safe_float(row.get("trade_reduction_pct"))
        phase_a_trades = _safe_float(row.get("phase_a_total_trades"))

        strong_quality = (
            delta_win_rate >= 5.0
            and delta_average_return >= 0.25
            and phase_a_trades >= 5
            and trade_reduction_pct >= -75.0
        )

        if (
            classification == "cocok"
            and strong_quality
            and threshold_action == "keep_threshold_2_0"
        ):
            action_bucket = "deploy_candidate"
            action_reason = (
                "Ticker sudah cocok dengan Phase A, kualitas sinyal naik, dan trade masih cukup."
            )
        elif classification == "cocok":
            action_bucket = "watchlist_candidate"
            action_reason = (
                "Ticker terlihat menjanjikan, tetapi trade terlalu sedikit atau threshold final belum stabil."
            )
        elif classification == "netral":
            if delta_win_rate > 0 or delta_average_return >= 0:
                action_bucket = "watchlist_candidate"
                action_reason = "Sinyalnya campuran tetapi belum jelas cukup buruk untuk dibuang."
            else:
                action_bucket = "review_needed"
                action_reason = "Ticker netral tanpa keunggulan jelas. Butuh eksperimen threshold tambahan."
        else:
            if threshold_action in {
                "test_threshold_1_5",
                "test_threshold_2_5",
                "adaptive_threshold_by_group",
                "review_manually",
            }:
                action_bucket = "review_needed"
                action_reason = "Ticker memburuk, tetapi masih ada hipotesis tuning yang layak diuji."
            else:
                action_bucket = "avoid_for_now"
                action_reason = "Ticker memburuk tanpa hipotesis tuning yang cukup meyakinkan."

        if delta_average_return <= -0.75 and delta_win_rate <= 0:
            action_bucket = "avoid_for_now"
            action_reason = "Average return memburuk terlalu besar sehingga tidak layak diprioritaskan."

        action_rows.append(
            {
                "ticker": ticker,
                "classification": classification,
                "action_bucket": action_bucket,
                "action_reason": action_reason,
                "recommended_threshold_action": threshold_action,
                "strict_mode_action": strict_mode_action,
                "delta_trades": row.get("delta_trades"),
                "trade_reduction_pct": row.get("trade_reduction_pct"),
                "delta_win_rate": row.get("delta_win_rate"),
                "delta_average_return": row.get("delta_average_return"),
                "baseline_total_trades": row.get("baseline_total_trades"),
                "phase_a_total_trades": row.get("phase_a_total_trades"),
                "tuning_hint": row.get("tuning_hint"),
                "classification_reason": row.get("classification_reason"),
                "category": row.get("category"),
                "market_cap_group": row.get("market_cap_group"),
                "sector": row.get("sector"),
                "beta_group": row.get("beta_group"),
            }
        )

    action_df = pd.DataFrame(action_rows).reindex(columns=TICKER_ACTION_COLUMNS)
    action_df["action_bucket"] = pd.Categorical(
        action_df["action_bucket"],
        categories=BUCKET_ORDER,
        ordered=True,
    )
    action_df = action_df.sort_values(
        ["action_bucket", "delta_average_return", "delta_win_rate"],
        ascending=[True, False, False],
    ).reset_index(drop=True)

    return action_df, merged_df, warnings


def prioritize_next_experiments(
    default_threshold_decision: Dict[str, object],
    strict_mode_decision: Dict[str, object],
    ticker_actions_df: pd.DataFrame,
    group_actions_df: pd.DataFrame,
) -> pd.DataFrame:
    """Prioritize the next experiments from highest value to highest complexity."""

    rows: List[Dict[str, object]] = []
    deploy_count = int((ticker_actions_df["action_bucket"] == "deploy_candidate").sum())
    review_count = int((ticker_actions_df["action_bucket"] == "review_needed").sum())
    watchlist_count = int((ticker_actions_df["action_bucket"] == "watchlist_candidate").sum())

    decision_code = default_threshold_decision["decision_code"]
    if decision_code == "test_threshold_1_5":
        rows.append(
            {
                "priority": 1,
                "experiment_id": "threshold_sweep_looser",
                "experiment_name": "Sweep volume_ratio 1.5 vs 2.0",
                "objective": "Cari apakah trade yang hilang bisa kembali tanpa menurunkan kualitas terlalu jauh.",
                "scope": "Ticker/group dengan trade reduction paling besar.",
                "reason": default_threshold_decision["reason"],
                "mandatory_before_phase_b": "yes",
            }
        )
    elif decision_code == "test_threshold_2_5":
        rows.append(
            {
                "priority": 1,
                "experiment_id": "threshold_sweep_tighter",
                "experiment_name": "Sweep volume_ratio 2.0 vs 2.5",
                "objective": "Kurangi false signal pada ticker yang masih noisy.",
                "scope": "Ticker/group yang average return-nya memburuk.",
                "reason": default_threshold_decision["reason"],
                "mandatory_before_phase_b": "yes",
            }
        )
    elif decision_code == "adaptive_threshold_by_group":
        rows.append(
            {
                "priority": 1,
                "experiment_id": "adaptive_threshold_by_group",
                "experiment_name": "Threshold by group",
                "objective": "Tetapkan threshold berbeda per group saham dengan sinyal yang memang tidak seragam.",
                "scope": "Group dengan keputusan threshold berbeda atau review_group_specific.",
                "reason": default_threshold_decision["reason"],
                "mandatory_before_phase_b": "yes",
            }
        )
    else:
        rows.append(
            {
                "priority": 1,
                "experiment_id": "confirm_threshold_2_0",
                "experiment_name": "Confirm threshold 2.0 baseline",
                "objective": "Bekukan baseline agar tidak terus bergeser sebelum Fase B.",
                "scope": "Deploy dan watchlist candidate.",
                "reason": default_threshold_decision["reason"],
                "mandatory_before_phase_b": "no",
            }
        )

    if strict_mode_decision["decision_code"] == "strict_only_for_subset":
        subset_scope = ", ".join(strict_mode_decision.get("subset_tickers", [])[:10]) or "subset group"
        rows.append(
            {
                "priority": 2,
                "experiment_id": "strict_subset_validation",
                "experiment_name": "Validate strict mode only on subset",
                "objective": "Pastikan strict benar-benar membantu subset yang disebutkan, bukan hanya noise statistik.",
                "scope": subset_scope,
                "reason": strict_mode_decision["reason"],
                "mandatory_before_phase_b": "yes",
            }
        )
    elif strict_mode_decision["decision_code"] == "strict_default_yes":
        rows.append(
            {
                "priority": 2,
                "experiment_id": "strict_default_confirmation",
                "experiment_name": "Confirm strict mode as default",
                "objective": "Validasi terakhir sebelum strict dijadikan baseline.",
                "scope": "Seluruh ticker deploy/watchlist.",
                "reason": strict_mode_decision["reason"],
                "mandatory_before_phase_b": "no",
            }
        )

    if review_count > 0:
        rows.append(
            {
                "priority": 3,
                "experiment_id": "review_bucket_follow_up",
                "experiment_name": "Targeted review on uncertain tickers",
                "objective": "Pisahkan review list menjadi kandidat threshold 1.5, 2.5, atau drop.",
                "scope": f"{review_count} ticker di bucket review_needed.",
                "reason": "Review bucket masih cukup besar sehingga belum bisa dianggap final.",
                "mandatory_before_phase_b": "yes" if decision_code != "keep_threshold_2_0" else "no",
            }
        )

    if not group_actions_df.empty and (
        group_actions_df["group_action"].isin(["test_looser_threshold", "test_tighter_threshold"]).any()
    ):
        rows.append(
            {
                "priority": 4,
                "experiment_id": "group_threshold_validation",
                "experiment_name": "Validate group-specific threshold",
                "objective": "Uji apakah aturan by group benar-benar lebih stabil daripada baseline global.",
                "scope": "Group dengan action test_looser_threshold atau test_tighter_threshold.",
                "reason": "Ada sinyal group-specific yang cukup kuat untuk diuji secara terpisah.",
                "mandatory_before_phase_b": "yes" if decision_code == "adaptive_threshold_by_group" else "no",
            }
        )

    rows.append(
        {
            "priority": 5,
            "experiment_id": "phase_b_gate",
            "experiment_name": "Freeze final Phase A baseline",
            "objective": "Bekukan whitelist, blacklist, dan threshold final sebelum masuk Fase B.",
            "scope": f"{deploy_count} deploy, {watchlist_count} watchlist, {review_count} review.",
            "reason": "Fase B sebaiknya hanya dimulai setelah baseline keputusan cukup stabil.",
            "mandatory_before_phase_b": "yes",
        }
    )

    experiments_df = pd.DataFrame(rows).reindex(columns=EXPERIMENT_COLUMNS)
    return experiments_df.sort_values(["priority", "experiment_id"]).reset_index(drop=True)


def assess_phase_b_readiness(
    ticker_actions_df: pd.DataFrame,
    default_threshold_decision: Dict[str, object],
    strict_mode_decision: Dict[str, object],
    group_actions_df: pd.DataFrame,
) -> Dict[str, object]:
    """Assess whether Phase A is mature enough to move toward Phase B."""

    total = int(len(ticker_actions_df))
    deploy_count = int((ticker_actions_df["action_bucket"] == "deploy_candidate").sum())
    watchlist_count = int((ticker_actions_df["action_bucket"] == "watchlist_candidate").sum())
    review_count = int((ticker_actions_df["action_bucket"] == "review_needed").sum())
    avoid_count = int((ticker_actions_df["action_bucket"] == "avoid_for_now").sum())

    deploy_share = _safe_percentage(deploy_count, total)
    review_share = _safe_percentage(review_count, total)
    unresolved_group_actions = int(
        group_actions_df["group_action"].isin(["test_looser_threshold", "test_tighter_threshold", "review_group_specific"]).sum()
    ) if not group_actions_df.empty else 0

    blocking_items: List[str] = []
    if default_threshold_decision["decision_code"] != "keep_threshold_2_0":
        blocking_items.append("Threshold baseline belum final dan masih butuh eksperimen lanjutan.")
    if strict_mode_decision["decision_code"] == "strict_only_for_subset":
        blocking_items.append("Subset strict mode masih perlu validasi terpisah.")
    if review_count > deploy_count:
        blocking_items.append("Jumlah ticker review_needed masih lebih besar daripada deploy_candidate.")
    if unresolved_group_actions > 0:
        blocking_items.append("Masih ada group yang meminta tuning khusus.")

    if (
        default_threshold_decision["decision_code"] == "keep_threshold_2_0"
        and strict_mode_decision["decision_code"] in {"strict_default_yes", "strict_default_no"}
        and deploy_share >= 30.0
        and review_share <= 25.0
        and unresolved_group_actions == 0
    ):
        status = "ready"
        reason = "Threshold baseline dan policy strict sudah cukup final untuk dijadikan titik masuk ke Fase B."
    elif (deploy_share + _safe_percentage(watchlist_count, total)) >= 50.0:
        status = "partially_ready"
        reason = (
            "Arah tuning sudah cukup jelas, tetapi masih ada eksperimen minimum yang wajib "
            "diselesaikan sebelum baseline dinyatakan final."
        )
    else:
        status = "not_ready"
        reason = "Keputusan tuning masih terlalu banyak bergantung pada review tambahan."

    return {
        "status": status,
        "is_ready": status == "ready",
        "reason": reason,
        "blocking_items": blocking_items,
        "metrics": {
            "ticker_count": total,
            "deploy_count": deploy_count,
            "watchlist_count": watchlist_count,
            "review_count": review_count,
            "avoid_count": avoid_count,
            "deploy_share_pct": deploy_share,
            "review_share_pct": review_share,
        },
    }


def build_decision_payload(
    default_threshold_decision: Dict[str, object],
    strict_mode_decision: Dict[str, object],
    ticker_actions_df: pd.DataFrame,
    group_actions_df: pd.DataFrame,
    next_experiments_df: pd.DataFrame,
    readiness: Dict[str, object],
    warnings: Sequence[str],
) -> Dict[str, object]:
    """Build the JSON-serializable tuning decision payload."""

    def bucket_list(bucket: str) -> List[str]:
        return ticker_actions_df.loc[ticker_actions_df["action_bucket"] == bucket, "ticker"].tolist()

    return {
        "default_threshold_decision": default_threshold_decision,
        "strict_mode_decision": strict_mode_decision,
        "deploy_candidates": bucket_list("deploy_candidate"),
        "watchlist_candidates": bucket_list("watchlist_candidate"),
        "review_needed": bucket_list("review_needed"),
        "avoid_for_now": bucket_list("avoid_for_now"),
        "group_actions": group_actions_df.to_dict(orient="records") if not group_actions_df.empty else [],
        "next_experiments": next_experiments_df.to_dict(orient="records"),
        "ready_for_phase_b": readiness,
        "warnings": list(warnings),
    }


def generate_tuning_plan(
    default_threshold_decision: Dict[str, object],
    strict_mode_decision: Dict[str, object],
    ticker_actions_df: pd.DataFrame,
    group_actions_df: pd.DataFrame,
    next_experiments_df: pd.DataFrame,
    readiness: Dict[str, object],
) -> str:
    """Generate a human-readable tuning plan."""

    deploy = ticker_actions_df.loc[ticker_actions_df["action_bucket"] == "deploy_candidate", "ticker"].tolist()
    watchlist = ticker_actions_df.loc[ticker_actions_df["action_bucket"] == "watchlist_candidate", "ticker"].tolist()
    review = ticker_actions_df.loc[ticker_actions_df["action_bucket"] == "review_needed", "ticker"].tolist()
    avoid = ticker_actions_df.loc[ticker_actions_df["action_bucket"] == "avoid_for_now", "ticker"].tolist()

    lines = [
        "Phase A Tuning Decision",
        "=======================",
        "",
        "Kondisi sekarang:",
        f"- Total ticker dievaluasi: {len(ticker_actions_df)}",
        f"- Deploy candidate: {len(deploy)}",
        f"- Watchlist candidate: {len(watchlist)}",
        f"- Review needed: {len(review)}",
        f"- Avoid for now: {len(avoid)}",
        "",
        "Keputusan threshold default:",
        f"- Decision: {default_threshold_decision['decision_code']}",
        f"- Reason: {default_threshold_decision['reason']}",
        "",
        "Keputusan strict mode:",
        f"- Decision: {strict_mode_decision['decision_code']}",
        f"- Reason: {strict_mode_decision['reason']}",
    ]

    if strict_mode_decision.get("subset_tickers"):
        lines.append(
            f"- Strict subset tickers: {', '.join(strict_mode_decision['subset_tickers'])}"
        )
    if strict_mode_decision.get("subset_groups"):
        subset_groups = [
            f"{item['group_field']}={item['group_value']}"
            for item in strict_mode_decision["subset_groups"]
        ]
        lines.append(f"- Strict subset groups: {', '.join(subset_groups)}")

    lines.extend(
        [
            "",
            "Ticker action list:",
            f"- Deploy candidate: {', '.join(deploy) if deploy else 'None'}",
            f"- Watchlist candidate: {', '.join(watchlist) if watchlist else 'None'}",
            f"- Review needed: {', '.join(review) if review else 'None'}",
            f"- Avoid for now: {', '.join(avoid) if avoid else 'None'}",
        ]
    )

    if not group_actions_df.empty:
        lines.extend(["", "Group action list:"])
        for _, row in group_actions_df.iterrows():
            lines.append(
                f"- {row['group_field']}={row['group_value']}: "
                f"{row['group_action']} ({row['group_threshold_decision']})"
            )
    else:
        lines.extend(
            [
                "",
                "Group action list:",
                "- Tidak ada metadata/group analysis yang cukup untuk keputusan by-group.",
            ]
        )

    lines.extend(["", "Eksperimen prioritas:"])
    for _, row in next_experiments_df.head(3).iterrows():
        lines.append(
            f"- P{int(row['priority'])}: {row['experiment_name']} | mandatory_before_phase_b={row['mandatory_before_phase_b']}"
        )
        lines.append(f"  Scope: {row['scope']}")
        lines.append(f"  Reason: {row['reason']}")

    lines.extend(
        [
            "",
            "Status menuju Fase B:",
            f"- Ready status: {readiness['status']}",
            f"- Reason: {readiness['reason']}",
        ]
    )
    if readiness["blocking_items"]:
        lines.append("- Blocking items:")
        for item in readiness["blocking_items"]:
            lines.append(f"  - {item}")

    return "\n".join(lines) + "\n"


def _json_default(value: object) -> object:
    """Convert numpy/pandas scalars into JSON-friendly values."""

    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if pd.isna(value) else float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def _sanitize_for_json(value: object) -> object:
    """Recursively replace NaN-like values so the JSON stays standards-compliant."""

    if isinstance(value, dict):
        return {key: _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if pd.isna(value) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def export_tuning_outputs(
    output_dir: Path,
    decision_payload: Dict[str, object],
    tuning_plan_text: str,
    ticker_actions_df: pd.DataFrame,
    next_experiments_df: pd.DataFrame,
    group_actions_df: pd.DataFrame,
) -> None:
    """Export all decision-layer outputs."""

    output_dir.mkdir(parents=True, exist_ok=True)

    decision_json = output_dir / "phase_a_tuning_decision.json"
    decision_json.write_text(
        json.dumps(
            _sanitize_for_json(decision_payload),
            indent=2,
            ensure_ascii=True,
            default=_json_default,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    print(f"Saved tuning decision JSON to {decision_json}")

    plan_txt = output_dir / "phase_a_tuning_plan.txt"
    plan_txt.write_text(tuning_plan_text, encoding="utf-8")
    print(f"Saved tuning plan to {plan_txt}")

    ticker_actions_csv = output_dir / "phase_a_ticker_actions.csv"
    ticker_actions_df.to_csv(ticker_actions_csv, index=False)
    print(f"Saved ticker actions to {ticker_actions_csv}")

    experiments_csv = output_dir / "phase_a_next_experiments.csv"
    next_experiments_df.to_csv(experiments_csv, index=False)
    print(f"Saved next experiments to {experiments_csv}")

    if not group_actions_df.empty:
        group_actions_csv = output_dir / "phase_a_group_actions.csv"
        group_actions_df.to_csv(group_actions_csv, index=False)
        print(f"Saved group actions to {group_actions_csv}")


def print_decision_console(
    default_threshold_decision: Dict[str, object],
    strict_mode_decision: Dict[str, object],
    ticker_actions_df: pd.DataFrame,
    next_experiments_df: pd.DataFrame,
    readiness: Dict[str, object],
    warnings: Sequence[str],
) -> None:
    """Print a concise console summary."""

    if warnings:
        print("\nInput warnings:")
        for warning in warnings:
            print(f"- {warning}")

    print("\nDefault threshold decision:")
    print(f"- {default_threshold_decision['decision_code']}")
    print(f"- {default_threshold_decision['reason']}")

    print("\nStrict mode decision:")
    print(f"- {strict_mode_decision['decision_code']}")
    print(f"- {strict_mode_decision['reason']}")

    for bucket in BUCKET_ORDER:
        bucket_df = ticker_actions_df.loc[ticker_actions_df["action_bucket"] == bucket, ["ticker", "recommended_threshold_action", "strict_mode_action"]]
        print(f"\n{bucket}:")
        if bucket_df.empty:
            print("None")
        else:
            print(bucket_df.to_string(index=False))

    print("\nNext experiments:")
    print(next_experiments_df.to_string(index=False))

    print("\nPhase B readiness:")
    print(f"- status: {readiness['status']}")
    print(f"- reason: {readiness['reason']}")
    if readiness["blocking_items"]:
        for item in readiness["blocking_items"]:
            print(f"- blocking: {item}")


def decide_phase_a_tuning(
    recommendations_file: Path,
    classification_file: Path,
    analysis_summary_file: Optional[Path] = None,
    group_analysis_file: Optional[Path] = None,
    summary_file: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
    output_dir: Path = Path("output"),
) -> Dict[str, object]:
    """Run the full decision-layer workflow."""

    artifacts = load_analysis_artifacts(
        recommendations_file=recommendations_file,
        classification_file=classification_file,
        analysis_summary_file=analysis_summary_file,
        group_analysis_file=group_analysis_file,
        summary_file=summary_file,
        metadata_file=metadata_file,
    )

    default_threshold_decision = decide_default_threshold(
        classified_df=artifacts.classification_df,
        analysis_summary_df=artifacts.analysis_summary_df,
        group_analysis_df=artifacts.group_analysis_df,
        recommendations_signals=artifacts.recommendations_signals,
    )
    strict_mode_decision = decide_strict_mode(
        classified_df=artifacts.classification_df,
        analysis_summary_df=artifacts.analysis_summary_df,
        group_analysis_df=artifacts.group_analysis_df,
        recommendations_signals=artifacts.recommendations_signals,
    )
    merged_df, metadata_warnings = _merge_classification_with_metadata(
        artifacts.classification_df,
        artifacts.metadata_df,
    )
    group_actions_df = build_group_action_plan(
        merged_df=merged_df,
        group_analysis_df=artifacts.group_analysis_df,
    )
    ticker_actions_df, _, ticker_action_warnings = build_ticker_action_plan(
        classified_df=artifacts.classification_df,
        metadata_df=artifacts.metadata_df,
        default_threshold_decision=default_threshold_decision,
        strict_mode_decision=strict_mode_decision,
        group_actions_df=group_actions_df,
    )
    next_experiments_df = prioritize_next_experiments(
        default_threshold_decision=default_threshold_decision,
        strict_mode_decision=strict_mode_decision,
        ticker_actions_df=ticker_actions_df,
        group_actions_df=group_actions_df,
    )
    readiness = assess_phase_b_readiness(
        ticker_actions_df=ticker_actions_df,
        default_threshold_decision=default_threshold_decision,
        strict_mode_decision=strict_mode_decision,
        group_actions_df=group_actions_df,
    )

    all_warnings = artifacts.warnings + metadata_warnings + ticker_action_warnings
    decision_payload = build_decision_payload(
        default_threshold_decision=default_threshold_decision,
        strict_mode_decision=strict_mode_decision,
        ticker_actions_df=ticker_actions_df,
        group_actions_df=group_actions_df,
        next_experiments_df=next_experiments_df,
        readiness=readiness,
        warnings=all_warnings,
    )
    tuning_plan_text = generate_tuning_plan(
        default_threshold_decision=default_threshold_decision,
        strict_mode_decision=strict_mode_decision,
        ticker_actions_df=ticker_actions_df,
        group_actions_df=group_actions_df,
        next_experiments_df=next_experiments_df,
        readiness=readiness,
    )

    export_tuning_outputs(
        output_dir=Path(output_dir),
        decision_payload=decision_payload,
        tuning_plan_text=tuning_plan_text,
        ticker_actions_df=ticker_actions_df,
        next_experiments_df=next_experiments_df,
        group_actions_df=group_actions_df,
    )
    print_decision_console(
        default_threshold_decision=default_threshold_decision,
        strict_mode_decision=strict_mode_decision,
        ticker_actions_df=ticker_actions_df,
        next_experiments_df=next_experiments_df,
        readiness=readiness,
        warnings=all_warnings,
    )

    return {
        "decision_payload": decision_payload,
        "ticker_actions_df": ticker_actions_df,
        "group_actions_df": group_actions_df,
        "next_experiments_df": next_experiments_df,
        "readiness": readiness,
        "tuning_plan_text": tuning_plan_text,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Convert Phase A analysis artifacts into concrete tuning decisions."
    )
    parser.add_argument(
        "--recommendations-file",
        default="output/phase_a_recommendations.txt",
        help="Required analyzer recommendation text. Default: output/phase_a_recommendations.txt",
    )
    parser.add_argument(
        "--classification-file",
        default="output/phase_a_ticker_classification.csv",
        help="Required ticker classification CSV. Default: output/phase_a_ticker_classification.csv",
    )
    parser.add_argument(
        "--analysis-summary-file",
        default="output/phase_a_analysis_summary.csv",
        help="Optional long-form analyzer summary CSV. Default: output/phase_a_analysis_summary.csv",
    )
    parser.add_argument(
        "--group-analysis-file",
        default="output/phase_a_group_analysis.csv",
        help="Optional analyzer group summary CSV. Default: output/phase_a_group_analysis.csv",
    )
    parser.add_argument(
        "--summary-file",
        default="output/phase_a_summary.csv",
        help="Optional evaluator summary CSV. Default: output/phase_a_summary.csv",
    )
    parser.add_argument(
        "--metadata-file",
        default=None,
        help="Optional ticker metadata CSV. Example: data/ticker_metadata.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory for tuning decision outputs. Default: output",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)

    try:
        decide_phase_a_tuning(
            recommendations_file=Path(args.recommendations_file),
            classification_file=Path(args.classification_file),
            analysis_summary_file=Path(args.analysis_summary_file) if args.analysis_summary_file else None,
            group_analysis_file=Path(args.group_analysis_file) if args.group_analysis_file else None,
            summary_file=Path(args.summary_file) if args.summary_file else None,
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            output_dir=Path(args.output_dir),
        )
        return 0
    except TuningCliError as exc:
        print(str(exc))
        _print_next_steps(exc.suggestions)
        return 1
    except Exception as exc:
        print(f"Tuning decision failed: {exc}")
        _print_next_steps(
            [
                f"Regenerate analyzer artifacts with: {_analyzer_command_hint()}",
                f"If evaluator outputs are also missing, rerun: {_evaluator_command_hint()}",
            ]
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
