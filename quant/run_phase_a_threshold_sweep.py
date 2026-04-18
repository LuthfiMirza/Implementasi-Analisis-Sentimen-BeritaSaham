"""Run a systematic threshold sweep for Phase A volume spike research.

Example
-------
Preferred execution from project root:

    python3 -m quant.run_phase_a_threshold_sweep \
      --data-dir data \
      --output-dir output \
      --thresholds 1.5 2.0 2.5 3.0 \
      --strict \
      --min-trades 8
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.evaluate_phase_a_real_data import (  # noqa: E402
    extract_ticker_from_filename,
    load_price_csv,
)
from quant.phase_a import (  # noqa: E402
    DEFAULT_VOLUME_SPIKE_THRESHOLD,
    backtest_signal_frame,
    generate_phase_a_signal,
)

DEFAULT_THRESHOLDS = [1.5, 2.0, 2.5, 3.0]
DEFAULT_BASELINE_THRESHOLD = DEFAULT_VOLUME_SPIKE_THRESHOLD
SUPPORTED_METADATA_COLUMNS = ["ticker", "category", "market_cap_group", "sector", "beta_group"]
GROUP_FIELDS = ["market_cap_group", "sector", "category", "beta_group"]
PRIORITY_BUCKETS = {"watchlist_candidate", "review_needed"}
GROUP_MIN_TICKERS = 2
RESULT_COLUMNS = [
    "ticker",
    "threshold",
    "strict_mode",
    "rows",
    "date_start",
    "date_end",
    "total_trades",
    "win_rate",
    "average_return",
    "max_drawdown",
    "baseline_threshold",
    "trades_vs_threshold_2_0",
    "trade_retention_vs_threshold_2_0_pct",
    "win_rate_vs_threshold_2_0",
    "average_return_vs_threshold_2_0",
    "max_drawdown_vs_threshold_2_0",
    "eligible_by_min_trades",
    "score_quality_reward",
    "score_trade_penalty",
    "score_drawdown_penalty",
    "score_low_trade_penalty",
    "score_trade_bonus",
    "score",
    "data_warning_count",
    "data_warnings",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
    "prior_action_bucket",
    "prior_recommended_threshold_action",
    "priority_from_previous_artifacts",
]
BEST_BY_TICKER_COLUMNS = [
    "ticker",
    "best_threshold",
    "strict_mode",
    "decision_confidence",
    "decision_margin",
    "trade_floor_override",
    "baseline_threshold",
    "baseline_total_trades",
    "baseline_win_rate",
    "baseline_average_return",
    "baseline_max_drawdown",
    "winning_total_trades",
    "winning_win_rate",
    "winning_average_return",
    "winning_max_drawdown",
    "winning_score",
    "winning_trade_retention_pct",
    "winning_win_rate_delta",
    "winning_average_return_delta",
    "winning_max_drawdown_delta",
    "selection_reason",
    "priority_from_previous_artifacts",
    "prior_action_bucket",
    "prior_recommended_threshold_action",
    "heuristic_alignment",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
]
GLOBAL_SUMMARY_COLUMNS = [
    "threshold",
    "ticker_count",
    "eligible_ticker_count",
    "low_trade_ticker_count",
    "winner_ticker_count",
    "priority_winner_ticker_count",
    "total_trades_sum",
    "total_trades_mean",
    "win_rate_mean",
    "average_return_mean",
    "max_drawdown_mean",
    "mean_score",
    "median_score",
    "trade_retention_vs_threshold_2_0_pct",
    "win_rate_vs_threshold_2_0",
    "average_return_vs_threshold_2_0",
    "max_drawdown_vs_threshold_2_0",
    "aggregate_score_vs_threshold_2_0",
    "threshold_profile",
    "selected_as_global_best",
]
GROUP_SUMMARY_COLUMNS = [
    "group_field",
    "group_value",
    "threshold",
    "ticker_count",
    "eligible_ticker_count",
    "winner_ticker_count",
    "total_trades_sum",
    "total_trades_mean",
    "win_rate_mean",
    "average_return_mean",
    "max_drawdown_mean",
    "mean_score",
    "median_score",
    "trade_retention_vs_threshold_2_0_pct",
    "win_rate_vs_threshold_2_0",
    "average_return_vs_threshold_2_0",
    "max_drawdown_vs_threshold_2_0",
    "aggregate_score_vs_threshold_2_0",
    "sample_status",
]
BEST_BY_GROUP_COLUMNS = [
    "group_field",
    "group_value",
    "best_threshold",
    "decision_confidence",
    "decision_margin",
    "ticker_count",
    "eligible_ticker_count",
    "winner_ticker_count",
    "sample_status",
    "selection_reason",
    "winning_mean_score",
    "winning_total_trades_sum",
    "winning_trade_retention_pct",
    "winning_win_rate_delta",
    "winning_average_return_delta",
    "winning_max_drawdown_delta",
]


class ThresholdSweepCliError(ValueError):
    """Friendly CLI error for threshold sweep execution."""

    def __init__(self, message: str, suggestions: Optional[Sequence[str]] = None) -> None:
        super().__init__(message)
        self.suggestions = list(suggestions or [])


def _bootstrap_command(data_dir: Path) -> str:
    """Build sample-data bootstrap command hint."""

    return f"python3 -m quant.bootstrap_sample_data --data-dir {shlex.quote(str(data_dir))}"


def _print_next_steps(steps: Sequence[str]) -> None:
    """Print actionable follow-up steps."""

    cleaned_steps = [step for step in steps if step]
    if not cleaned_steps:
        return

    print("\nNext step suggestions:")
    for step in cleaned_steps:
        print(f"  {step}")


def _safe_float(value: object, default: float = 0.0) -> float:
    """Convert scalars into float values with a fallback."""

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(numeric):
        return float(default)
    return float(numeric)


def _normalize_ticker_filter(tickers: Optional[Iterable[str]]) -> Optional[set[str]]:
    """Normalize an optional CLI ticker filter list."""

    if not tickers:
        return None

    normalized: set[str] = set()
    for item in tickers:
        for token in str(item).split(","):
            token = token.strip().upper()
            if token:
                normalized.add(token)
    return normalized or None


def _format_threshold(threshold: float) -> str:
    """Format threshold values consistently for human-readable outputs."""

    return f"{float(threshold):.1f}"


def _threshold_action_code(threshold: float, baseline_threshold: float = DEFAULT_BASELINE_THRESHOLD) -> str:
    """Map a numeric threshold into the existing heuristic action vocabulary."""

    if np.isclose(threshold, baseline_threshold):
        return "keep_threshold_2_0"
    if threshold < baseline_threshold:
        return "test_threshold_1_5"
    return "test_threshold_2_5"


def _profile_threshold_row(row: pd.Series) -> str:
    """Classify a threshold as too loose, too tight, or competitive."""

    trade_retention = _safe_float(row.get("trade_retention_vs_threshold_2_0_pct"), default=100.0)
    win_delta = _safe_float(row.get("win_rate_vs_threshold_2_0"))
    avg_delta = _safe_float(row.get("average_return_vs_threshold_2_0"))
    mean_score = _safe_float(row.get("mean_score"))

    if trade_retention < 65.0 and mean_score < 0:
        return "too_tight"
    if trade_retention > 115.0 and (win_delta < 0 or avg_delta < 0):
        return "too_loose"
    if mean_score > 0:
        return "competitive"
    return "mixed"


def _sanitize_for_json(value: object) -> object:
    """Replace numpy/pandas scalars and NaN-like values for JSON export."""

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


def normalize_thresholds(
    thresholds: Optional[Sequence[float]],
    baseline_threshold: float = DEFAULT_BASELINE_THRESHOLD,
) -> Tuple[List[float], List[str]]:
    """Validate, normalize, and de-duplicate the requested sweep thresholds."""

    warnings: List[str] = []
    requested = list(thresholds or DEFAULT_THRESHOLDS)
    if not requested:
        raise ThresholdSweepCliError("Threshold list is empty. Provide at least one threshold.")

    normalized: List[float] = []
    for item in requested:
        try:
            threshold = float(item)
        except (TypeError, ValueError) as exc:
            raise ThresholdSweepCliError(
                f"Invalid threshold value: {item}",
                suggestions=[
                    "Use numeric values only, for example: --thresholds 1.5 2.0 2.5 3.0",
                ],
            ) from exc
        if not np.isfinite(threshold) or threshold <= 0:
            raise ThresholdSweepCliError(
                f"Threshold must be a finite value greater than 0. Found: {item}",
                suggestions=[
                    "Use positive numeric values only, for example: --thresholds 1.5 2.0 2.5 3.0",
                ],
            )
        if threshold not in normalized:
            normalized.append(round(threshold, 4))

    if baseline_threshold not in normalized:
        normalized.append(round(float(baseline_threshold), 4))
        warnings.append(
            f"Baseline threshold {_format_threshold(baseline_threshold)} was not requested and has been added automatically."
        )

    normalized = sorted(normalized)
    return normalized, warnings


def resolve_metadata_file(data_dir: Path, metadata_file: Optional[Path]) -> Optional[Path]:
    """Resolve explicit or auto-detected metadata file path."""

    if metadata_file is not None:
        return Path(metadata_file)

    candidate = Path(data_dir) / "ticker_metadata.csv"
    if candidate.exists():
        return candidate
    return None


def load_metadata(metadata_file: Optional[Path]) -> Tuple[Optional[pd.DataFrame], List[str]]:
    """Load optional ticker metadata used for group summaries."""

    warnings: List[str] = []
    if metadata_file is None:
        return None, warnings

    path = Path(metadata_file)
    if not path.exists():
        warnings.append(f"Metadata file not found: {path}. Group analysis skipped.")
        return None, warnings
    if not path.is_file():
        warnings.append(f"Metadata path is not a file: {path}. Group analysis skipped.")
        return None, warnings

    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        warnings.append(f"Metadata file is empty: {path}. Group analysis skipped.")
        return None, warnings
    except pd.errors.ParserError as exc:
        warnings.append(f"Metadata CSV parser error in {path}: {exc}. Group analysis skipped.")
        return None, warnings
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"Failed to read metadata file {path}: {exc}. Group analysis skipped.")
        return None, warnings

    if frame.empty:
        warnings.append(f"Metadata file contains no rows: {path}. Group analysis skipped.")
        return None, warnings
    if "ticker" not in frame.columns:
        warnings.append(f"Metadata file does not contain a 'ticker' column: {path}. Group analysis skipped.")
        return None, warnings

    frame = frame.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    duplicate_count = int(frame["ticker"].duplicated(keep="first").sum())
    if duplicate_count:
        warnings.append(
            f"Metadata file contains {duplicate_count} duplicate ticker rows. Keeping the first occurrence per ticker."
        )
        frame = frame.drop_duplicates(subset=["ticker"], keep="first").reset_index(drop=True)

    available_columns = [column for column in SUPPORTED_METADATA_COLUMNS if column in frame.columns]
    if available_columns == ["ticker"]:
        warnings.append(
            "Metadata file only contains ticker without supported group fields. Group analysis skipped."
        )
        return frame[available_columns], warnings

    return frame[available_columns], warnings


def load_previous_artifacts(output_dir: Path) -> Dict[str, object]:
    """Load optional tuning artifacts from earlier Phase A runs."""

    warnings: List[str] = []
    output_dir = Path(output_dir)

    decision_payload: Optional[Dict[str, object]] = None
    decision_path = output_dir / "phase_a_tuning_decision.json"
    if decision_path.exists() and decision_path.is_file():
        try:
            decision_payload = json.loads(decision_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            warnings.append(f"Failed to read prior decision JSON {decision_path}: {exc}")

    ticker_actions_df: Optional[pd.DataFrame] = None
    ticker_actions_path = output_dir / "phase_a_ticker_actions.csv"
    if ticker_actions_path.exists() and ticker_actions_path.is_file():
        try:
            ticker_actions_df = pd.read_csv(ticker_actions_path)
            if "ticker" in ticker_actions_df.columns:
                ticker_actions_df["ticker"] = (
                    ticker_actions_df["ticker"].astype(str).str.upper().str.strip()
                )
        except Exception as exc:  # pragma: no cover - defensive
            warnings.append(f"Failed to read prior ticker actions {ticker_actions_path}: {exc}")
            ticker_actions_df = None

    group_actions_df: Optional[pd.DataFrame] = None
    group_actions_path = output_dir / "phase_a_group_actions.csv"
    if group_actions_path.exists() and group_actions_path.is_file():
        try:
            group_actions_df = pd.read_csv(group_actions_path)
        except Exception as exc:  # pragma: no cover - defensive
            warnings.append(f"Failed to read prior group actions {group_actions_path}: {exc}")
            group_actions_df = None

    return {
        "decision_payload": decision_payload,
        "ticker_actions_df": ticker_actions_df,
        "group_actions_df": group_actions_df,
        "warnings": warnings,
    }


def resolve_csv_files(
    data_dir: Path,
    tickers: Optional[Iterable[str]] = None,
    metadata_file: Optional[Path] = None,
) -> List[Path]:
    """Validate the data folder and return the selected price CSV files."""

    folder = Path(data_dir)
    if not folder.exists():
        raise ThresholdSweepCliError(
            f"Data directory not found: {folder}",
            suggestions=[f"Generate sample CSV data with: {_bootstrap_command(folder)}"],
        )
    if not folder.is_dir():
        raise ThresholdSweepCliError(f"Data path is not a directory: {folder}")

    excluded_file = None
    if metadata_file is not None:
        excluded_file = Path(metadata_file).resolve()

    csv_files = []
    for path in sorted(folder.glob("*.csv")):
        if excluded_file is not None and path.resolve() == excluded_file:
            continue
        csv_files.append(path)

    if not csv_files:
        raise ThresholdSweepCliError(
            f"No ticker CSV files found in {folder}",
            suggestions=[f"Generate sample CSV data with: {_bootstrap_command(folder)}"],
        )

    ticker_filter = _normalize_ticker_filter(tickers)
    if ticker_filter is None:
        return csv_files

    selected = [
        path for path in csv_files if extract_ticker_from_filename(path) in ticker_filter
    ]
    if not selected:
        available = ", ".join(extract_ticker_from_filename(path) for path in csv_files[:10])
        suggestions = []
        if available:
            suggestions.append(f"Available tickers in {folder}: {available}")
        raise ThresholdSweepCliError(
            f"No CSV files matched the requested ticker filter in {folder}",
            suggestions=suggestions,
        )

    return selected


def load_price_data(path: Path) -> Tuple[pd.DataFrame, List[str]]:
    """Load one ticker CSV file using the existing evaluator loader."""

    return load_price_csv(Path(path))


def run_single_threshold_evaluation(
    frame: pd.DataFrame,
    ticker: str,
    threshold: float,
    strict: bool,
    hold_period: int,
    allow_overlap: bool,
    data_warnings: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    """Evaluate one ticker at one threshold and return the key metrics."""

    signal_frame = generate_phase_a_signal(
        frame,
        strict=strict,
        volume_spike_threshold=threshold,
    )
    signal_column = "phase_a_signal_strict" if strict else "phase_a_signal"
    backtest_result = backtest_signal_frame(
        signal_frame,
        signal_column=signal_column,
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )

    warnings_text = " | ".join(data_warnings or [])
    return {
        "ticker": ticker,
        "threshold": float(threshold),
        "strict_mode": bool(strict),
        "rows": int(len(signal_frame)),
        "date_start": signal_frame["date"].iloc[0],
        "date_end": signal_frame["date"].iloc[-1],
        "total_trades": int(backtest_result.total_trades),
        "win_rate": float(backtest_result.win_rate),
        "average_return": float(backtest_result.average_return),
        "max_drawdown": float(backtest_result.max_drawdown),
        "data_warning_count": int(len(data_warnings or [])),
        "data_warnings": warnings_text,
    }


def run_ticker_threshold_sweep(
    path: Path,
    thresholds: Sequence[float],
    strict: bool,
    hold_period: int,
    allow_overlap: bool,
) -> Tuple[List[Dict[str, object]], List[str]]:
    """Run all threshold evaluations for a single ticker file."""

    ticker = extract_ticker_from_filename(Path(path))
    frame, warnings = load_price_data(Path(path))
    results: List[Dict[str, object]] = []

    for threshold in thresholds:
        results.append(
            run_single_threshold_evaluation(
                frame=frame,
                ticker=ticker,
                threshold=threshold,
                strict=strict,
                hold_period=hold_period,
                allow_overlap=allow_overlap,
                data_warnings=warnings,
            )
        )

    return results, warnings


def compute_threshold_score(
    row: pd.Series,
    baseline_row: pd.Series,
    min_trades: int = 8,
) -> float:
    """Compute one explicit threshold score relative to baseline threshold 2.0.

    Score components
    ----------------
    - Reward higher win_rate.
    - Reward higher average_return.
    - Penalize worse max_drawdown.
    - Penalize sharp trade loss relative to threshold 2.0.
    - Penalize candidates below the minimum trade floor.
    """

    components = _compute_threshold_score_components(
        row=row,
        baseline_row=baseline_row,
        min_trades=min_trades,
    )
    return float(components["score"])


def _compute_threshold_score_components(
    row: pd.Series,
    baseline_row: pd.Series,
    min_trades: int,
) -> Dict[str, float]:
    """Return full score breakdown for transparency and export."""

    total_trades = _safe_float(row.get("total_trades"))
    baseline_trades = _safe_float(baseline_row.get("total_trades"))
    win_delta = _safe_float(row.get("win_rate")) - _safe_float(baseline_row.get("win_rate"))
    avg_delta = _safe_float(row.get("average_return")) - _safe_float(
        baseline_row.get("average_return")
    )
    drawdown_delta = _safe_float(row.get("max_drawdown")) - _safe_float(
        baseline_row.get("max_drawdown")
    )

    if baseline_trades > 0:
        trade_retention_pct = (total_trades / baseline_trades) * 100.0
    elif total_trades > 0:
        trade_retention_pct = 100.0
    else:
        trade_retention_pct = 0.0

    quality_reward = (win_delta * 1.0) + (avg_delta * 3.0)
    trade_penalty = max(0.0, 100.0 - trade_retention_pct) * 0.12
    drawdown_penalty = max(0.0, drawdown_delta) * 0.75
    trade_bonus = max(0.0, min(15.0, trade_retention_pct - 100.0)) * 0.03
    low_trade_penalty = 0.0
    if total_trades < min_trades:
        low_trade_penalty = 25.0 + ((min_trades - total_trades) * 2.0)

    score = quality_reward - trade_penalty - drawdown_penalty + trade_bonus - low_trade_penalty
    return {
        "trade_retention_pct": round(trade_retention_pct, 4),
        "win_rate_delta": round(win_delta, 4),
        "average_return_delta": round(avg_delta, 4),
        "max_drawdown_delta": round(drawdown_delta, 4),
        "score_quality_reward": round(quality_reward, 4),
        "score_trade_penalty": round(trade_penalty, 4),
        "score_drawdown_penalty": round(drawdown_penalty, 4),
        "score_low_trade_penalty": round(low_trade_penalty, 4),
        "score_trade_bonus": round(trade_bonus, 4),
        "score": round(score, 4),
    }


def score_threshold_candidates(
    results_df: pd.DataFrame,
    baseline_threshold: float = DEFAULT_BASELINE_THRESHOLD,
    min_trades: int = 8,
) -> pd.DataFrame:
    """Score each ticker-threshold pair against the threshold 2.0 baseline."""

    if results_df.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    rows: List[Dict[str, object]] = []
    for ticker, group_df in results_df.groupby("ticker", sort=True):
        baseline_matches = group_df.loc[np.isclose(group_df["threshold"], baseline_threshold)]
        if baseline_matches.empty:
            raise ThresholdSweepCliError(
                f"Ticker {ticker} is missing baseline threshold {_format_threshold(baseline_threshold)}."
            )
        baseline_row = baseline_matches.iloc[0]
        any_eligible = bool((group_df["total_trades"] >= min_trades).any())

        for _, row in group_df.sort_values("threshold").iterrows():
            breakdown = _compute_threshold_score_components(
                row=row,
                baseline_row=baseline_row,
                min_trades=min_trades,
            )
            scored_row = row.to_dict()
            scored_row["baseline_threshold"] = float(baseline_threshold)
            scored_row["trades_vs_threshold_2_0"] = int(
                _safe_float(row.get("total_trades")) - _safe_float(baseline_row.get("total_trades"))
            )
            scored_row["trade_retention_vs_threshold_2_0_pct"] = breakdown["trade_retention_pct"]
            scored_row["win_rate_vs_threshold_2_0"] = breakdown["win_rate_delta"]
            scored_row["average_return_vs_threshold_2_0"] = breakdown["average_return_delta"]
            scored_row["max_drawdown_vs_threshold_2_0"] = breakdown["max_drawdown_delta"]
            scored_row["eligible_by_min_trades"] = bool(
                (_safe_float(row.get("total_trades")) >= min_trades) if any_eligible else True
            )
            scored_row.update(breakdown)
            rows.append(scored_row)

    scored_df = pd.DataFrame(rows)
    return scored_df.reindex(columns=[column for column in RESULT_COLUMNS if column in scored_df.columns] + [column for column in scored_df.columns if column not in RESULT_COLUMNS])


def _build_ticker_selection_reason(
    winner: pd.Series,
    baseline_row: pd.Series,
    confidence: str,
    trade_floor_override: bool,
) -> str:
    """Build a concise, operational reason for the selected threshold."""

    threshold = float(winner["threshold"])
    win_delta = _safe_float(winner.get("win_rate_vs_threshold_2_0"))
    avg_delta = _safe_float(winner.get("average_return_vs_threshold_2_0"))
    trade_retention = _safe_float(winner.get("trade_retention_vs_threshold_2_0_pct"), default=0.0)
    drawdown_delta = _safe_float(winner.get("max_drawdown_vs_threshold_2_0"))

    if np.isclose(threshold, baseline_row["threshold"]):
        reason = (
            f"Threshold {_format_threshold(threshold)} tetap unggul atau paling stabil "
            f"dibanding alternatif lain."
        )
    elif threshold < baseline_row["threshold"]:
        reason = (
            f"Threshold {_format_threshold(threshold)} dipilih karena menangkap trade lebih banyak "
            f"dengan kualitas yang masih lebih baik dari baseline."
        )
    else:
        reason = (
            f"Threshold {_format_threshold(threshold)} dipilih karena kualitas sinyal naik "
            f"cukup besar dibanding baseline."
        )

    details = (
        f" win_rate_delta={win_delta:+.2f} pp, average_return_delta={avg_delta:+.4f}, "
        f"trade_retention={trade_retention:.1f}%, max_drawdown_delta={drawdown_delta:+.4f}."
    )
    if trade_floor_override:
        details += " Semua threshold berada di bawah min_trades, jadi hasil ini low-confidence."
    elif confidence == "low":
        details += " Margin pemenang sempit, jadi keputusan ini masih perlu verifikasi tambahan."
    return reason + details


def compare_with_previous_ticker_actions(
    best_by_ticker_df: pd.DataFrame,
    previous_ticker_actions_df: Optional[pd.DataFrame],
    baseline_threshold: float = DEFAULT_BASELINE_THRESHOLD,
) -> pd.DataFrame:
    """Annotate sweep winners with prior heuristic decisions when available."""

    if previous_ticker_actions_df is None or previous_ticker_actions_df.empty:
        best_by_ticker_df["priority_from_previous_artifacts"] = False
        best_by_ticker_df["prior_action_bucket"] = np.nan
        best_by_ticker_df["prior_recommended_threshold_action"] = np.nan
        best_by_ticker_df["heuristic_alignment"] = "not_available"
        return best_by_ticker_df

    previous = previous_ticker_actions_df.copy()
    if "ticker" not in previous.columns:
        best_by_ticker_df["priority_from_previous_artifacts"] = False
        best_by_ticker_df["prior_action_bucket"] = np.nan
        best_by_ticker_df["prior_recommended_threshold_action"] = np.nan
        best_by_ticker_df["heuristic_alignment"] = "not_available"
        return best_by_ticker_df

    keep_columns = [column for column in ["ticker", "action_bucket", "recommended_threshold_action"] if column in previous.columns]
    previous = previous[keep_columns].drop_duplicates(subset=["ticker"], keep="first")
    previous = previous.rename(
        columns={
            "action_bucket": "prior_action_bucket",
            "recommended_threshold_action": "prior_recommended_threshold_action",
        }
    )

    merged = best_by_ticker_df.merge(previous, on="ticker", how="left")
    if "prior_action_bucket" not in merged.columns:
        merged["prior_action_bucket"] = np.nan
    if "prior_recommended_threshold_action" not in merged.columns:
        merged["prior_recommended_threshold_action"] = np.nan
    merged["priority_from_previous_artifacts"] = merged["prior_action_bucket"].isin(PRIORITY_BUCKETS)
    merged["current_action_code"] = merged["best_threshold"].apply(
        lambda value: _threshold_action_code(value, baseline_threshold=baseline_threshold)
    )
    merged["heuristic_alignment"] = np.where(
        merged["prior_recommended_threshold_action"].isna(),
        "not_available",
        np.where(
            merged["prior_recommended_threshold_action"] == merged["current_action_code"],
            "confirmed",
            "contradicted",
        ),
    )
    return merged.drop(columns=["current_action_code"])


def select_best_threshold_per_ticker(
    scored_df: pd.DataFrame,
    min_trades: int = 8,
    baseline_threshold: float = DEFAULT_BASELINE_THRESHOLD,
    previous_ticker_actions_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Choose the winning threshold per ticker using the explicit score rule."""

    if scored_df.empty:
        return pd.DataFrame(columns=BEST_BY_TICKER_COLUMNS)

    rows: List[Dict[str, object]] = []
    for ticker, group_df in scored_df.groupby("ticker", sort=True):
        group_df = group_df.copy()
        baseline_row = group_df.loc[np.isclose(group_df["threshold"], baseline_threshold)].iloc[0]
        eligible_df = group_df.loc[group_df["eligible_by_min_trades"]].copy()
        trade_floor_override = eligible_df.empty
        if trade_floor_override:
            eligible_df = group_df.copy()

        eligible_df["baseline_preference"] = np.isclose(
            eligible_df["threshold"], baseline_threshold
        ).astype(int)
        eligible_df["threshold_distance"] = (
            eligible_df["threshold"] - baseline_threshold
        ).abs()
        ranked = eligible_df.sort_values(
            ["score", "baseline_preference", "total_trades", "average_return", "win_rate", "threshold_distance"],
            ascending=[False, False, False, False, False, True],
        ).reset_index(drop=True)

        winner = ranked.iloc[0]
        runner_up = ranked.iloc[1] if len(ranked) > 1 else None
        decision_margin = (
            float(winner["score"] - runner_up["score"]) if runner_up is not None else np.nan
        )

        if trade_floor_override or _safe_float(winner["total_trades"]) < min_trades:
            confidence = "low"
        elif pd.isna(decision_margin) or decision_margin < 0.75:
            confidence = "low"
        elif decision_margin < 2.0:
            confidence = "moderate"
        else:
            confidence = "strong"

        rows.append(
            {
                "ticker": ticker,
                "best_threshold": float(winner["threshold"]),
                "strict_mode": bool(winner["strict_mode"]),
                "decision_confidence": confidence,
                "decision_margin": decision_margin,
                "trade_floor_override": trade_floor_override,
                "baseline_threshold": float(baseline_threshold),
                "baseline_total_trades": int(baseline_row["total_trades"]),
                "baseline_win_rate": float(baseline_row["win_rate"]),
                "baseline_average_return": float(baseline_row["average_return"]),
                "baseline_max_drawdown": float(baseline_row["max_drawdown"]),
                "winning_total_trades": int(winner["total_trades"]),
                "winning_win_rate": float(winner["win_rate"]),
                "winning_average_return": float(winner["average_return"]),
                "winning_max_drawdown": float(winner["max_drawdown"]),
                "winning_score": float(winner["score"]),
                "winning_trade_retention_pct": float(
                    winner["trade_retention_vs_threshold_2_0_pct"]
                ),
                "winning_win_rate_delta": float(winner["win_rate_vs_threshold_2_0"]),
                "winning_average_return_delta": float(
                    winner["average_return_vs_threshold_2_0"]
                ),
                "winning_max_drawdown_delta": float(
                    winner["max_drawdown_vs_threshold_2_0"]
                ),
                "selection_reason": _build_ticker_selection_reason(
                    winner=winner,
                    baseline_row=baseline_row,
                    confidence=confidence,
                    trade_floor_override=trade_floor_override,
                ),
            }
        )

    best_by_ticker_df = pd.DataFrame(rows)
    best_by_ticker_df = compare_with_previous_ticker_actions(
        best_by_ticker_df=best_by_ticker_df,
        previous_ticker_actions_df=previous_ticker_actions_df,
        baseline_threshold=baseline_threshold,
    )

    best_by_ticker_df = best_by_ticker_df.sort_values(
        ["priority_from_previous_artifacts", "decision_confidence", "winning_score", "decision_margin"],
        ascending=[False, True, False, False],
        key=lambda series: series.map({"strong": 0, "moderate": 1, "low": 2}) if series.name == "decision_confidence" else series,
    )
    return best_by_ticker_df.reindex(columns=BEST_BY_TICKER_COLUMNS)


def summarize_global_thresholds(
    scored_df: pd.DataFrame,
    best_by_ticker_df: pd.DataFrame,
    baseline_threshold: float = DEFAULT_BASELINE_THRESHOLD,
) -> pd.DataFrame:
    """Summarize threshold behavior across the full ticker universe."""

    if scored_df.empty:
        return pd.DataFrame(columns=GLOBAL_SUMMARY_COLUMNS)

    summary = (
        scored_df.groupby("threshold", dropna=False)
        .agg(
            ticker_count=("ticker", "nunique"),
            eligible_ticker_count=("eligible_by_min_trades", "sum"),
            low_trade_ticker_count=("eligible_by_min_trades", lambda values: int((~values.astype(bool)).sum())),
            total_trades_sum=("total_trades", "sum"),
            total_trades_mean=("total_trades", "mean"),
            win_rate_mean=("win_rate", "mean"),
            average_return_mean=("average_return", "mean"),
            max_drawdown_mean=("max_drawdown", "mean"),
            mean_score=("score", "mean"),
            median_score=("score", "median"),
        )
        .reset_index()
    )

    winner_counts = (
        best_by_ticker_df.groupby("best_threshold")
        .agg(
            winner_ticker_count=("ticker", "count"),
            priority_winner_ticker_count=("priority_from_previous_artifacts", "sum"),
        )
        .reset_index()
        .rename(columns={"best_threshold": "threshold"})
    )
    summary = summary.merge(winner_counts, on="threshold", how="left")
    summary["winner_ticker_count"] = summary["winner_ticker_count"].fillna(0).astype(int)
    summary["priority_winner_ticker_count"] = (
        summary["priority_winner_ticker_count"].fillna(0).astype(int)
    )

    baseline_row = summary.loc[np.isclose(summary["threshold"], baseline_threshold)]
    if baseline_row.empty:
        raise ThresholdSweepCliError(
            f"Global summary is missing baseline threshold {_format_threshold(baseline_threshold)}."
        )
    baseline_row = baseline_row.iloc[0]

    rows: List[Dict[str, object]] = []
    for _, row in summary.sort_values("threshold").iterrows():
        working_row = row.copy()
        breakdown = _compute_threshold_score_components(
            row=pd.Series(
                {
                    "total_trades": row["total_trades_sum"],
                    "win_rate": row["win_rate_mean"],
                    "average_return": row["average_return_mean"],
                    "max_drawdown": row["max_drawdown_mean"],
                }
            ),
            baseline_row=pd.Series(
                {
                    "total_trades": baseline_row["total_trades_sum"],
                    "win_rate": baseline_row["win_rate_mean"],
                    "average_return": baseline_row["average_return_mean"],
                    "max_drawdown": baseline_row["max_drawdown_mean"],
                }
            ),
            min_trades=0,
        )
        working_row["trade_retention_vs_threshold_2_0_pct"] = breakdown["trade_retention_pct"]
        working_row["win_rate_vs_threshold_2_0"] = breakdown["win_rate_delta"]
        working_row["average_return_vs_threshold_2_0"] = breakdown["average_return_delta"]
        working_row["max_drawdown_vs_threshold_2_0"] = breakdown["max_drawdown_delta"]
        working_row["aggregate_score_vs_threshold_2_0"] = breakdown["score"]
        working_row["threshold_profile"] = _profile_threshold_row(working_row)
        rows.append(working_row.to_dict())

    summary = pd.DataFrame(rows)
    summary["selected_as_global_best"] = False

    ranked = summary.copy()
    ranked["baseline_preference"] = np.isclose(ranked["threshold"], baseline_threshold).astype(int)
    ranked["threshold_distance"] = (ranked["threshold"] - baseline_threshold).abs()
    ranked = ranked.sort_values(
        ["mean_score", "winner_ticker_count", "median_score", "baseline_preference", "threshold_distance"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)

    if not ranked.empty:
        selected_threshold = float(ranked.iloc[0]["threshold"])
        summary.loc[np.isclose(summary["threshold"], selected_threshold), "selected_as_global_best"] = True

    return summary.reindex(columns=GLOBAL_SUMMARY_COLUMNS)


def _build_summary_selection_reason(
    winner: pd.Series,
    baseline_threshold: float,
    scope_label: str,
    trade_floor_override: bool,
) -> str:
    """Describe why a threshold was selected for a group/global summary."""

    threshold = float(winner["threshold"])
    mean_score = _safe_float(winner.get("mean_score"))
    win_delta = _safe_float(winner.get("win_rate_vs_threshold_2_0"))
    avg_delta = _safe_float(winner.get("average_return_vs_threshold_2_0"))
    trade_retention = _safe_float(winner.get("trade_retention_vs_threshold_2_0_pct"), default=0.0)

    if np.isclose(threshold, baseline_threshold):
        reason = (
            f"{scope_label} tetap paling stabil di threshold {_format_threshold(threshold)} "
            f"dengan mean_score {mean_score:+.2f}."
        )
    elif threshold < baseline_threshold:
        reason = (
            f"{scope_label} lebih cocok ke threshold {_format_threshold(threshold)} "
            f"karena trade retention lebih tinggi tanpa kehilangan kualitas utama."
        )
    else:
        reason = (
            f"{scope_label} lebih cocok ke threshold {_format_threshold(threshold)} "
            f"karena peningkatan kualitas sinyal mengimbangi pengetatan trade."
        )

    reason += (
        f" win_rate_delta={win_delta:+.2f} pp, average_return_delta={avg_delta:+.4f}, "
        f"trade_retention={trade_retention:.1f}%."
    )
    if trade_floor_override:
        reason += " Keputusan ini low-confidence karena semua kandidat kekurangan trade."
    return reason


def summarize_group_thresholds(
    scored_df: pd.DataFrame,
    best_by_ticker_df: pd.DataFrame,
    baseline_threshold: float = DEFAULT_BASELINE_THRESHOLD,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Summarize threshold behavior for each available metadata group."""

    available_fields = [
        column
        for column in GROUP_FIELDS
        if column in scored_df.columns and scored_df[column].notna().any()
    ]
    if not available_fields:
        return pd.DataFrame(columns=GROUP_SUMMARY_COLUMNS), pd.DataFrame(columns=BEST_BY_GROUP_COLUMNS)

    group_rows: List[Dict[str, object]] = []
    for field in available_fields:
        valid_df = scored_df.loc[
            scored_df[field].notna() & scored_df[field].astype(str).str.strip().ne("")
        ].copy()
        if valid_df.empty:
            continue

        field_summary = (
            valid_df.groupby([field, "threshold"], dropna=False)
            .agg(
                ticker_count=("ticker", "nunique"),
                eligible_ticker_count=("eligible_by_min_trades", "sum"),
                total_trades_sum=("total_trades", "sum"),
                total_trades_mean=("total_trades", "mean"),
                win_rate_mean=("win_rate", "mean"),
                average_return_mean=("average_return", "mean"),
                max_drawdown_mean=("max_drawdown", "mean"),
                mean_score=("score", "mean"),
                median_score=("score", "median"),
            )
            .reset_index()
            .rename(columns={field: "group_value"})
        )
        field_summary["group_field"] = field

        winner_counts = (
            best_by_ticker_df.loc[
                best_by_ticker_df[field].notna()
                & best_by_ticker_df[field].astype(str).str.strip().ne("")
            ]
            .groupby([field, "best_threshold"], dropna=False)
            .agg(winner_ticker_count=("ticker", "count"))
            .reset_index()
            .rename(columns={field: "group_value", "best_threshold": "threshold"})
        )
        field_summary = field_summary.merge(
            winner_counts,
            on=["group_value", "threshold"],
            how="left",
        )
        field_summary["winner_ticker_count"] = field_summary["winner_ticker_count"].fillna(0).astype(int)

        for group_value, summary_group in field_summary.groupby("group_value", dropna=False):
            baseline_row = summary_group.loc[
                np.isclose(summary_group["threshold"], baseline_threshold)
            ]
            if baseline_row.empty:
                continue
            baseline_row = baseline_row.iloc[0]
            for _, row in summary_group.sort_values("threshold").iterrows():
                breakdown = _compute_threshold_score_components(
                    row=pd.Series(
                        {
                            "total_trades": row["total_trades_sum"],
                            "win_rate": row["win_rate_mean"],
                            "average_return": row["average_return_mean"],
                            "max_drawdown": row["max_drawdown_mean"],
                        }
                    ),
                    baseline_row=pd.Series(
                        {
                            "total_trades": baseline_row["total_trades_sum"],
                            "win_rate": baseline_row["win_rate_mean"],
                            "average_return": baseline_row["average_return_mean"],
                            "max_drawdown": baseline_row["max_drawdown_mean"],
                        }
                    ),
                    min_trades=0,
                )
                group_rows.append(
                    {
                        "group_field": row["group_field"],
                        "group_value": group_value,
                        "threshold": float(row["threshold"]),
                        "ticker_count": int(row["ticker_count"]),
                        "eligible_ticker_count": int(row["eligible_ticker_count"]),
                        "winner_ticker_count": int(row["winner_ticker_count"]),
                        "total_trades_sum": float(row["total_trades_sum"]),
                        "total_trades_mean": float(row["total_trades_mean"]),
                        "win_rate_mean": float(row["win_rate_mean"]),
                        "average_return_mean": float(row["average_return_mean"]),
                        "max_drawdown_mean": float(row["max_drawdown_mean"]),
                        "mean_score": float(row["mean_score"]),
                        "median_score": float(row["median_score"]),
                        "trade_retention_vs_threshold_2_0_pct": breakdown["trade_retention_pct"],
                        "win_rate_vs_threshold_2_0": breakdown["win_rate_delta"],
                        "average_return_vs_threshold_2_0": breakdown["average_return_delta"],
                        "max_drawdown_vs_threshold_2_0": breakdown["max_drawdown_delta"],
                        "aggregate_score_vs_threshold_2_0": breakdown["score"],
                        "sample_status": (
                            "enough_sample"
                            if int(row["ticker_count"]) >= GROUP_MIN_TICKERS
                            else "insufficient_group_sample"
                        ),
                    }
                )

    group_summary_df = pd.DataFrame(group_rows).reindex(columns=GROUP_SUMMARY_COLUMNS)
    if group_summary_df.empty:
        return group_summary_df, pd.DataFrame(columns=BEST_BY_GROUP_COLUMNS)

    best_rows: List[Dict[str, object]] = []
    for (group_field, group_value), group_df in group_summary_df.groupby(
        ["group_field", "group_value"], dropna=False
    ):
        candidate_df = group_df.loc[
            (group_df["sample_status"] == "enough_sample")
            & (group_df["eligible_ticker_count"] >= np.minimum(group_df["ticker_count"], 2))
        ].copy()
        trade_floor_override = candidate_df.empty
        if trade_floor_override:
            candidate_df = group_df.copy()

        candidate_df["baseline_preference"] = np.isclose(
            candidate_df["threshold"], baseline_threshold
        ).astype(int)
        candidate_df["threshold_distance"] = (
            candidate_df["threshold"] - baseline_threshold
        ).abs()
        ranked = candidate_df.sort_values(
            ["mean_score", "winner_ticker_count", "median_score", "baseline_preference", "threshold_distance"],
            ascending=[False, False, False, False, True],
        ).reset_index(drop=True)

        winner = ranked.iloc[0]
        runner_up = ranked.iloc[1] if len(ranked) > 1 else None
        decision_margin = (
            float(winner["mean_score"] - runner_up["mean_score"]) if runner_up is not None else np.nan
        )

        if winner["sample_status"] != "enough_sample" or trade_floor_override:
            confidence = "low"
        elif pd.isna(decision_margin) or decision_margin < 0.5:
            confidence = "low"
        elif decision_margin < 1.5:
            confidence = "moderate"
        else:
            confidence = "strong"

        best_rows.append(
            {
                "group_field": group_field,
                "group_value": group_value,
                "best_threshold": float(winner["threshold"]),
                "decision_confidence": confidence,
                "decision_margin": decision_margin,
                "ticker_count": int(winner["ticker_count"]),
                "eligible_ticker_count": int(winner["eligible_ticker_count"]),
                "winner_ticker_count": int(winner["winner_ticker_count"]),
                "sample_status": winner["sample_status"],
                "selection_reason": _build_summary_selection_reason(
                    winner=winner,
                    baseline_threshold=baseline_threshold,
                    scope_label=f"Group {group_field}={group_value}",
                    trade_floor_override=trade_floor_override,
                ),
                "winning_mean_score": float(winner["mean_score"]),
                "winning_total_trades_sum": float(winner["total_trades_sum"]),
                "winning_trade_retention_pct": float(
                    winner["trade_retention_vs_threshold_2_0_pct"]
                ),
                "winning_win_rate_delta": float(winner["win_rate_vs_threshold_2_0"]),
                "winning_average_return_delta": float(
                    winner["average_return_vs_threshold_2_0"]
                ),
                "winning_max_drawdown_delta": float(
                    winner["max_drawdown_vs_threshold_2_0"]
                ),
            }
        )

    best_by_group_df = pd.DataFrame(best_rows).reindex(columns=BEST_BY_GROUP_COLUMNS)
    best_by_group_df = best_by_group_df.sort_values(
        ["decision_confidence", "winning_mean_score", "ticker_count"],
        ascending=[True, False, False],
        key=lambda series: series.map({"strong": 0, "moderate": 1, "low": 2}) if series.name == "decision_confidence" else series,
    )
    return group_summary_df, best_by_group_df


def compare_with_previous_decisions(
    global_summary_df: pd.DataFrame,
    best_by_ticker_df: pd.DataFrame,
    best_by_group_df: pd.DataFrame,
    previous_artifacts: Dict[str, object],
    baseline_threshold: float = DEFAULT_BASELINE_THRESHOLD,
) -> Dict[str, object]:
    """Compare sweep outputs with the older heuristic decision layer."""

    previous_decision = previous_artifacts.get("decision_payload")
    previous_group_actions_df = previous_artifacts.get("group_actions_df")

    comparison: Dict[str, object] = {
        "available": False,
        "global_alignment": "not_available",
        "previous_default_decision_code": None,
        "previous_readiness_status": None,
        "priority_ticker_confirmed": 0,
        "priority_ticker_contradicted": 0,
        "group_confirmed": 0,
        "group_contradicted": 0,
    }

    selected_global = global_summary_df.loc[global_summary_df["selected_as_global_best"]]
    current_threshold = (
        float(selected_global.iloc[0]["threshold"]) if not selected_global.empty else baseline_threshold
    )
    current_action_code = _threshold_action_code(current_threshold, baseline_threshold=baseline_threshold)

    if previous_decision:
        comparison["available"] = True
        previous_default = (
            previous_decision.get("default_threshold_decision", {})
            if isinstance(previous_decision, dict)
            else {}
        )
        previous_code = previous_default.get("decision_code")
        comparison["previous_default_decision_code"] = previous_code
        comparison["previous_readiness_status"] = (
            previous_decision.get("ready_for_phase_b", {}).get("status")
            if isinstance(previous_decision, dict)
            else None
        )
        if previous_code:
            if previous_code == "adaptive_threshold_by_group" and not best_by_group_df.empty:
                comparison["global_alignment"] = "confirmed"
            elif previous_code == current_action_code:
                comparison["global_alignment"] = "confirmed"
            else:
                comparison["global_alignment"] = "contradicted"

    if "heuristic_alignment" in best_by_ticker_df.columns:
        priority_df = best_by_ticker_df.loc[best_by_ticker_df["priority_from_previous_artifacts"]]
        comparison["priority_ticker_confirmed"] = int(
            (priority_df["heuristic_alignment"] == "confirmed").sum()
        )
        comparison["priority_ticker_contradicted"] = int(
            (priority_df["heuristic_alignment"] == "contradicted").sum()
        )

    if (
        previous_group_actions_df is not None
        and not previous_group_actions_df.empty
        and not best_by_group_df.empty
        and {"group_field", "group_value"}.issubset(previous_group_actions_df.columns)
    ):
        previous_group = previous_group_actions_df.copy()
        current_group = best_by_group_df.copy()
        previous_group["group_value"] = previous_group["group_value"].astype(str)
        current_group["group_value"] = current_group["group_value"].astype(str)
        merged_group = current_group.merge(
            previous_group,
            on=["group_field", "group_value"],
            how="left",
            suffixes=("", "_prev"),
        )

        def _group_alignment(row: pd.Series) -> str:
            prior_decision = row.get("group_threshold_decision")
            prior_action = row.get("group_action")
            best_threshold = _safe_float(row.get("best_threshold"), default=baseline_threshold)
            if pd.isna(prior_decision) and pd.isna(prior_action):
                return "not_available"
            if prior_decision == "adaptive_threshold_by_group":
                return "confirmed"
            if prior_decision == _threshold_action_code(best_threshold, baseline_threshold):
                return "confirmed"
            if prior_action == "test_looser_threshold" and best_threshold < baseline_threshold:
                return "confirmed"
            if prior_action == "test_tighter_threshold" and best_threshold > baseline_threshold:
                return "confirmed"
            if prior_action == "keep_default_threshold" and np.isclose(best_threshold, baseline_threshold):
                return "confirmed"
            return "contradicted"

        merged_group["alignment"] = merged_group.apply(_group_alignment, axis=1)
        comparison["group_confirmed"] = int((merged_group["alignment"] == "confirmed").sum())
        comparison["group_contradicted"] = int((merged_group["alignment"] == "contradicted").sum())

    return comparison


def determine_global_policy(
    global_summary_df: pd.DataFrame,
    best_by_group_df: pd.DataFrame,
    baseline_threshold: float = DEFAULT_BASELINE_THRESHOLD,
) -> Dict[str, object]:
    """Determine the current best global baseline and whether group adaptation is supported."""

    if global_summary_df.empty:
        raise ThresholdSweepCliError("Global summary is empty. No threshold decision can be produced.")

    ranked_global = global_summary_df.loc[global_summary_df["selected_as_global_best"]]
    if ranked_global.empty:
        raise ThresholdSweepCliError("No global threshold winner could be selected.")

    winner = ranked_global.iloc[0]
    sorted_global = global_summary_df.sort_values(
        ["mean_score", "winner_ticker_count", "median_score"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    runner_up = sorted_global.iloc[1] if len(sorted_global) > 1 else None
    decision_margin = (
        float(winner["mean_score"] - runner_up["mean_score"]) if runner_up is not None else np.nan
    )
    if pd.isna(decision_margin) or decision_margin < 0.5:
        confidence = "low"
    elif decision_margin < 1.5:
        confidence = "moderate"
    else:
        confidence = "strong"

    sufficient_groups = pd.DataFrame(columns=best_by_group_df.columns)
    if not best_by_group_df.empty:
        sufficient_groups = best_by_group_df.loc[
            (best_by_group_df["sample_status"] == "enough_sample")
            & (best_by_group_df["decision_confidence"] != "low")
        ].copy()

    distinct_group_thresholds = sorted(
        {_format_threshold(value) for value in sufficient_groups["best_threshold"].tolist()}
    )
    adaptive_supported = len(distinct_group_thresholds) >= 2
    adaptive_reason = (
        "Adaptive threshold by group didukung karena group cukup-sample memilih threshold yang berbeda."
        if adaptive_supported
        else "Adaptive threshold by group belum didukung cukup kuat karena winner group belum terpecah secara konsisten."
    )

    selected_threshold = float(winner["threshold"])
    if adaptive_supported:
        mode = "adaptive_by_group"
        decision_code = "adaptive_threshold_by_group"
    elif np.isclose(selected_threshold, baseline_threshold):
        mode = "global_fixed"
        decision_code = "keep_threshold_2_0"
    elif selected_threshold < baseline_threshold:
        mode = "global_fixed"
        decision_code = "set_threshold_1_5"
    else:
        mode = "global_fixed"
        decision_code = f"set_threshold_{_format_threshold(selected_threshold).replace('.', '_')}"

    if adaptive_supported and np.isclose(selected_threshold, baseline_threshold):
        reason = (
            f"Threshold {_format_threshold(baseline_threshold)} tetap paling stabil secara global, "
            "tetapi subset group yang cukup-sample sudah menunjukkan kebutuhan override spesifik."
        )
    elif adaptive_supported:
        reason = (
            f"Threshold global terbaik bergeser ke {_format_threshold(selected_threshold)}, "
            "dan hasil group juga cukup heterogen untuk membenarkan override spesifik."
        )
    elif np.isclose(selected_threshold, baseline_threshold):
        reason = (
            f"Threshold {_format_threshold(baseline_threshold)} masih menjadi baseline global terbaik "
            "setelah sweep sistematis."
        )
    else:
        reason = (
            f"Threshold {_format_threshold(selected_threshold)} mengungguli baseline "
            f"{_format_threshold(baseline_threshold)} secara global."
        )

    return {
        "mode": mode,
        "decision_code": decision_code,
        "selected_default_threshold": selected_threshold,
        "keep_default_2_0": bool(np.isclose(selected_threshold, baseline_threshold)),
        "decision_confidence": confidence,
        "decision_margin": decision_margin,
        "reason": reason,
        "adaptive_threshold_by_group": {
            "supported": adaptive_supported,
            "reason": adaptive_reason,
            "sufficient_group_count": int(len(sufficient_groups)),
            "distinct_thresholds": distinct_group_thresholds,
        },
    }


def determine_readiness(
    policy: Dict[str, object],
    best_by_ticker_df: pd.DataFrame,
    best_by_group_df: pd.DataFrame,
    metadata_df: Optional[pd.DataFrame],
) -> Dict[str, object]:
    """Assess whether the threshold sweep is strong enough to finalize Phase A baseline."""

    ambiguous_tickers = best_by_ticker_df.loc[best_by_ticker_df["decision_confidence"] == "low", "ticker"].tolist()
    priority_ambiguous = best_by_ticker_df.loc[
        (best_by_ticker_df["decision_confidence"] == "low")
        & (best_by_ticker_df["priority_from_previous_artifacts"]),
        "ticker",
    ].tolist()

    blocking_items: List[str] = []
    if policy["decision_confidence"] == "low":
        blocking_items.append("Keputusan threshold global masih lemah karena margin pemenang terlalu sempit.")
    if priority_ambiguous:
        blocking_items.append(
            "Ticker prioritas dari decision layer lama masih ambigu: "
            + ", ".join(priority_ambiguous[:10])
        )
    if metadata_df is not None and not best_by_group_df.empty:
        unresolved_groups = best_by_group_df.loc[
            (best_by_group_df["sample_status"] == "insufficient_group_sample")
            | (best_by_group_df["decision_confidence"] == "low")
        ]
        if not unresolved_groups.empty and policy["adaptive_threshold_by_group"]["supported"]:
            blocking_items.append(
                "Adaptive threshold by group sudah muncul, tetapi sebagian group winner masih low-confidence."
            )

    if not blocking_items:
        status = "ready"
        reason = "Sweep threshold sudah cukup kuat untuk menetapkan baseline final Fase A."
    else:
        status = "partially_ready"
        reason = "Sweep threshold sudah informatif, tetapi masih ada area ambigu yang harus ditutup."

    return {
        "status": status,
        "reason": reason,
        "ambiguous_tickers": ambiguous_tickers,
        "priority_ambiguous_tickers": priority_ambiguous,
        "blocking_items": blocking_items,
    }


def build_next_required_experiments(
    policy: Dict[str, object],
    readiness: Dict[str, object],
    best_by_ticker_df: pd.DataFrame,
    best_by_group_df: pd.DataFrame,
) -> List[str]:
    """Generate the minimum next experiments when the sweep is not yet decisive."""

    if readiness["status"] == "ready":
        return ["Tidak ada eksperimen threshold minimum yang wajib sebelum baseline Phase A dibekukan."]

    experiments: List[str] = []
    ambiguous_priority = readiness.get("priority_ambiguous_tickers", [])
    ambiguous_tickers = readiness.get("ambiguous_tickers", [])

    if ambiguous_priority:
        experiments.append(
            "Jalankan validasi walk-forward 2-split hanya untuk ticker prioritas ambigu: "
            + ", ".join(ambiguous_priority[:10])
        )
    elif ambiguous_tickers:
        experiments.append(
            "Jalankan validasi walk-forward 2-split untuk ticker ambigu: "
            + ", ".join(ambiguous_tickers[:10])
        )

    if policy["adaptive_threshold_by_group"]["supported"]:
        low_conf_groups = best_by_group_df.loc[
            (best_by_group_df["sample_status"] != "enough_sample")
            | (best_by_group_df["decision_confidence"] == "low"),
            ["group_field", "group_value"],
        ]
        if not low_conf_groups.empty:
            group_labels = [
                f"{row['group_field']}={row['group_value']}" for _, row in low_conf_groups.head(10).iterrows()
            ]
            experiments.append(
                "Lengkapi sampel group atau metadata untuk mengonfirmasi adaptive threshold pada: "
                + ", ".join(group_labels)
            )

    if not experiments:
        experiments.append(
            "Ulangi sweep threshold pada window data yang lebih panjang untuk memastikan margin winner tetap stabil."
        )

    return experiments


def build_threshold_recommendations(
    policy: Dict[str, object],
    readiness: Dict[str, object],
    global_summary_df: pd.DataFrame,
    best_by_ticker_df: pd.DataFrame,
    best_by_group_df: pd.DataFrame,
    prior_comparison: Dict[str, object],
    next_experiments: Sequence[str],
    warnings: Sequence[str],
    baseline_threshold: float = DEFAULT_BASELINE_THRESHOLD,
) -> str:
    """Create the required operational recommendation text."""

    global_winner = global_summary_df.loc[global_summary_df["selected_as_global_best"]].iloc[0]
    better_15 = best_by_ticker_df.loc[np.isclose(best_by_ticker_df["best_threshold"], 1.5), "ticker"].tolist()
    better_25 = best_by_ticker_df.loc[np.isclose(best_by_ticker_df["best_threshold"], 2.5), "ticker"].tolist()
    better_30 = best_by_ticker_df.loc[np.isclose(best_by_ticker_df["best_threshold"], 3.0), "ticker"].tolist()

    looser_groups = pd.DataFrame(columns=best_by_group_df.columns)
    tighter_groups = pd.DataFrame(columns=best_by_group_df.columns)
    if not best_by_group_df.empty:
        looser_groups = best_by_group_df.loc[
            (best_by_group_df["sample_status"] == "enough_sample")
            & (best_by_group_df["best_threshold"] < baseline_threshold)
        ]
        tighter_groups = best_by_group_df.loc[
            (best_by_group_df["sample_status"] == "enough_sample")
            & (best_by_group_df["best_threshold"] > baseline_threshold)
        ]

    threshold_profiles = ", ".join(
        f"{_format_threshold(row['threshold'])}={row['threshold_profile']}"
        for _, row in global_summary_df.sort_values("threshold").iterrows()
    )

    lines = [
        "Phase A Threshold Sweep Recommendation",
        "=====================================",
        "",
        "1. Apakah threshold default 2.0 tetap dipertahankan atau tidak?",
        (
            f"- Keputusan: {'tetap dipertahankan' if policy['keep_default_2_0'] else 'tidak dipertahankan'}."
            if policy["mode"] == "global_fixed"
            else (
                f"- Keputusan: {_format_threshold(baseline_threshold)} tetap dipakai sebagai fallback global, "
                "tetapi threshold operasional beralih ke adaptive-by-group."
                if policy["keep_default_2_0"]
                else f"- Keputusan: {_format_threshold(baseline_threshold)} tidak dipakai lagi sebagai default tunggal."
            )
        ),
        f"- Policy: {policy['mode']}",
        f"- Threshold global terbaik: {_format_threshold(policy['selected_default_threshold'])}",
        f"- Confidence: {policy['decision_confidence']}",
        f"- Reason: {policy['reason']}",
        (
            f"- Bukti global: mean_score={_safe_float(global_winner['mean_score']):+.2f}, "
            f"winner_ticker_count={int(global_winner['winner_ticker_count'])}, "
            f"trade_retention_vs_2_0={_safe_float(global_winner['trade_retention_vs_threshold_2_0_pct']):.1f}%."
        ),
        "",
        "2. Ticker mana yang lebih cocok threshold 1.5?",
        f"- {_format_list(better_15)}",
        "",
        "3. Ticker mana yang lebih cocok threshold 2.5 atau 3.0?",
        f"- Threshold 2.5: {_format_list(better_25)}",
        f"- Threshold 3.0: {_format_list(better_30)}",
        "",
        "4. Apakah adaptive threshold by group benar-benar didukung data?",
        f"- Keputusan: {'ya' if policy['adaptive_threshold_by_group']['supported'] else 'tidak'}",
        f"- Reason: {policy['adaptive_threshold_by_group']['reason']}",
        "",
        "5. Group mana yang cocok threshold lebih longgar?",
        f"- {_format_group_list(looser_groups)}",
        "",
        "6. Group mana yang cocok threshold lebih ketat?",
        f"- {_format_group_list(tighter_groups)}",
        "",
        "7. Apakah hasil sweep cukup untuk menaikkan readiness dari partially_ready ke ready?",
        f"- Status: {readiness['status']}",
        f"- Reason: {readiness['reason']}",
        (
            "- Blocking items: "
            + ("; ".join(readiness["blocking_items"]) if readiness["blocking_items"] else "tidak ada")
        ),
        "",
        "8. Eksperimen minimum berikutnya jika keputusan masih belum final?",
    ]

    for item in next_experiments:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "Catatan sweep global:",
            f"- Profil threshold universe: {threshold_profiles}",
        ]
    )

    if prior_comparison.get("available"):
        lines.extend(
            [
                "",
                "Perbandingan dengan decision layer sebelumnya:",
                f"- Global alignment: {prior_comparison['global_alignment']}",
                (
                    f"- Priority ticker confirmed={prior_comparison['priority_ticker_confirmed']}, "
                    f"contradicted={prior_comparison['priority_ticker_contradicted']}"
                ),
                (
                    f"- Group confirmed={prior_comparison['group_confirmed']}, "
                    f"contradicted={prior_comparison['group_contradicted']}"
                ),
            ]
        )

    if warnings:
        lines.extend(["", "Warnings:"])
        for item in warnings:
            lines.append(f"- {item}")

    return "\n".join(lines) + "\n"


def _format_list(values: Sequence[object]) -> str:
    """Format a flat list for text output."""

    cleaned = [str(value) for value in values if str(value).strip()]
    return ", ".join(cleaned) if cleaned else "tidak ada"


def _format_group_list(group_df: pd.DataFrame) -> str:
    """Format grouped winners as a flat string list."""

    if group_df.empty:
        return "tidak ada group dengan bukti cukup"
    labels = [f"{row['group_field']}={row['group_value']}" for _, row in group_df.iterrows()]
    return ", ".join(labels)


def create_plots(
    results_df: pd.DataFrame,
    best_by_ticker_df: pd.DataFrame,
    global_summary_df: pd.DataFrame,
    output_dir: Path,
) -> List[str]:
    """Create optional matplotlib plots for quick visual inspection."""

    warnings: List[str] = []
    try:
        os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
        os.environ.setdefault("XDG_CACHE_HOME", "/tmp")
        Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
        Path(os.environ["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        warnings.append("matplotlib is not installed. Plot export skipped.")
        return warnings
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"Plot setup failed: {exc}")
        return warnings

    try:
        ordered_tickers = best_by_ticker_df["ticker"].tolist()
        pivot = (
            results_df.pivot_table(index="ticker", columns="threshold", values="score", aggfunc="first")
            .reindex(ordered_tickers)
        )
        if not pivot.empty:
            fig, ax = plt.subplots(figsize=(max(10, len(ordered_tickers) * 0.8), 6))
            for threshold in pivot.columns:
                ax.plot(
                    pivot.index,
                    pivot[threshold],
                    marker="o",
                    linewidth=1.6,
                    label=f"thr={_format_threshold(threshold)}",
                )
            ax.axhline(0.0, color="#666666", linewidth=1.0, linestyle="--")
            ax.set_title("Phase A Threshold Score by Ticker")
            ax.set_xlabel("Ticker")
            ax.set_ylabel("Score")
            ax.tick_params(axis="x", rotation=45)
            ax.legend()
            fig.tight_layout()
            fig.savefig(output_dir / "phase_a_threshold_score_by_ticker.png", dpi=150)
            plt.close(fig)

        if not global_summary_df.empty:
            fig, axes = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
            axes[0].plot(
                global_summary_df["threshold"],
                global_summary_df["mean_score"],
                marker="o",
                linewidth=1.8,
                color="#1f77b4",
            )
            axes[0].set_ylabel("Mean Score")
            axes[0].set_title("Phase A Threshold Global Comparison")
            axes[0].axhline(0.0, color="#666666", linewidth=1.0, linestyle="--")

            axes[1].plot(
                global_summary_df["threshold"],
                global_summary_df["winner_ticker_count"],
                marker="o",
                linewidth=1.8,
                color="#2ca02c",
            )
            axes[1].set_ylabel("Winner Count")

            axes[2].plot(
                global_summary_df["threshold"],
                global_summary_df["trade_retention_vs_threshold_2_0_pct"],
                marker="o",
                linewidth=1.8,
                color="#d62728",
            )
            axes[2].set_ylabel("Trade Retention %")
            axes[2].set_xlabel("Threshold")

            for axis in axes:
                axis.grid(alpha=0.25)

            fig.tight_layout()
            fig.savefig(output_dir / "phase_a_threshold_global_comparison.png", dpi=150)
            plt.close(fig)
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"Plot export failed: {exc}")

    return warnings


def export_threshold_sweep_outputs(
    output_dir: Path,
    results_df: pd.DataFrame,
    best_by_ticker_df: pd.DataFrame,
    global_summary_df: pd.DataFrame,
    group_summary_df: pd.DataFrame,
    best_by_group_df: pd.DataFrame,
    recommendations_text: str,
    decision_payload: Dict[str, object],
) -> List[str]:
    """Export all required threshold sweep outputs."""

    output_dir.mkdir(parents=True, exist_ok=True)

    results_path = output_dir / "phase_a_threshold_sweep_results.csv"
    results_df.to_csv(results_path, index=False)
    print(f"Saved threshold sweep results to {results_path}")

    best_by_ticker_path = output_dir / "phase_a_threshold_best_by_ticker.csv"
    best_by_ticker_df.to_csv(best_by_ticker_path, index=False)
    print(f"Saved best-by-ticker summary to {best_by_ticker_path}")

    global_summary_path = output_dir / "phase_a_threshold_global_summary.csv"
    global_summary_df.to_csv(global_summary_path, index=False)
    print(f"Saved global threshold summary to {global_summary_path}")

    if not group_summary_df.empty:
        group_summary_path = output_dir / "phase_a_threshold_group_summary.csv"
        group_summary_df.to_csv(group_summary_path, index=False)
        print(f"Saved group threshold summary to {group_summary_path}")

    if not best_by_group_df.empty:
        best_by_group_path = output_dir / "phase_a_threshold_best_by_group.csv"
        best_by_group_df.to_csv(best_by_group_path, index=False)
        print(f"Saved best-by-group summary to {best_by_group_path}")

    recommendations_path = output_dir / "phase_a_threshold_recommendations.txt"
    recommendations_path.write_text(recommendations_text, encoding="utf-8")
    print(f"Saved threshold recommendations to {recommendations_path}")

    decision_path = output_dir / "phase_a_threshold_decision.json"
    decision_path.write_text(
        json.dumps(_sanitize_for_json(decision_payload), indent=2, ensure_ascii=True, allow_nan=False),
        encoding="utf-8",
    )
    print(f"Saved threshold decision JSON to {decision_path}")

    return create_plots(
        results_df=results_df,
        best_by_ticker_df=best_by_ticker_df,
        global_summary_df=global_summary_df,
        output_dir=output_dir,
    )


def run_phase_a_threshold_sweep(
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
    thresholds: Optional[Sequence[float]] = None,
    tickers: Optional[Iterable[str]] = None,
    strict: bool = False,
    hold_period: int = 5,
    allow_overlap: bool = False,
    min_trades: int = 8,
) -> Dict[str, object]:
    """Run the end-to-end Phase A threshold sweep experiment."""

    if hold_period < 1:
        raise ThresholdSweepCliError("hold_period must be >= 1.")
    if min_trades < 0:
        raise ThresholdSweepCliError("min_trades must be >= 0.")

    baseline_threshold = DEFAULT_BASELINE_THRESHOLD
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    metadata_path = resolve_metadata_file(data_dir=data_dir, metadata_file=metadata_file)

    thresholds_normalized, threshold_warnings = normalize_thresholds(
        thresholds=thresholds,
        baseline_threshold=baseline_threshold,
    )
    metadata_df, metadata_warnings = load_metadata(metadata_path)
    previous_artifacts = load_previous_artifacts(output_dir)
    csv_files = resolve_csv_files(
        data_dir=data_dir,
        tickers=tickers,
        metadata_file=metadata_path,
    )

    warnings = list(threshold_warnings) + list(metadata_warnings) + list(previous_artifacts["warnings"])
    successful_rows: List[Dict[str, object]] = []
    skipped_rows: List[Dict[str, str]] = []

    print(f"Selected {len(csv_files)} ticker files for threshold sweep.")
    for path in csv_files:
        ticker = extract_ticker_from_filename(path)
        print(f"Processing {ticker}...")
        try:
            ticker_rows, ticker_warnings = run_ticker_threshold_sweep(
                path=path,
                thresholds=thresholds_normalized,
                strict=strict,
                hold_period=hold_period,
                allow_overlap=allow_overlap,
            )
            successful_rows.extend(ticker_rows)
            for warning in ticker_warnings:
                print(f"  warning: {warning}")
        except Exception as exc:
            message = str(exc)
            print(f"  skipped: {message}")
            skipped_rows.append(
                {
                    "ticker": ticker,
                    "file_path": str(path),
                    "reason": message,
                }
            )

    if not successful_rows:
        raise ThresholdSweepCliError(
            "No ticker files produced valid threshold sweep results.",
            suggestions=[f"Generate sample CSV data with: {_bootstrap_command(data_dir)}"],
        )

    results_df = pd.DataFrame(successful_rows)
    if metadata_df is not None and not metadata_df.empty:
        results_df = results_df.merge(metadata_df, on="ticker", how="left")

    previous_ticker_actions_df = previous_artifacts.get("ticker_actions_df")
    if previous_ticker_actions_df is not None and not previous_ticker_actions_df.empty:
        previous_columns = [
            column
            for column in ["ticker", "action_bucket", "recommended_threshold_action"]
            if column in previous_ticker_actions_df.columns
        ]
        if previous_columns:
            previous_merge = (
                previous_ticker_actions_df[previous_columns]
                .drop_duplicates(subset=["ticker"], keep="first")
                .rename(
                    columns={
                        "action_bucket": "prior_action_bucket",
                        "recommended_threshold_action": "prior_recommended_threshold_action",
                    }
                )
            )
            results_df = results_df.merge(previous_merge, on="ticker", how="left")
            if "prior_action_bucket" not in results_df.columns:
                results_df["prior_action_bucket"] = np.nan
            if "prior_recommended_threshold_action" not in results_df.columns:
                results_df["prior_recommended_threshold_action"] = np.nan
            results_df["priority_from_previous_artifacts"] = results_df["prior_action_bucket"].isin(
                PRIORITY_BUCKETS
            )
        else:
            results_df["prior_action_bucket"] = np.nan
            results_df["prior_recommended_threshold_action"] = np.nan
            results_df["priority_from_previous_artifacts"] = False
    else:
        results_df["prior_action_bucket"] = np.nan
        results_df["prior_recommended_threshold_action"] = np.nan
        results_df["priority_from_previous_artifacts"] = False

    scored_df = score_threshold_candidates(
        results_df=results_df,
        baseline_threshold=baseline_threshold,
        min_trades=min_trades,
    )
    best_by_ticker_df = select_best_threshold_per_ticker(
        scored_df=scored_df,
        min_trades=min_trades,
        baseline_threshold=baseline_threshold,
        previous_ticker_actions_df=previous_ticker_actions_df,
    )

    if metadata_df is not None and not metadata_df.empty:
        best_by_ticker_df = best_by_ticker_df.drop(
            columns=[column for column in GROUP_FIELDS if column in best_by_ticker_df.columns],
            errors="ignore",
        )
        best_by_ticker_df = best_by_ticker_df.merge(
            metadata_df,
            on="ticker",
            how="left",
        )
    else:
        for column in GROUP_FIELDS:
            if column not in best_by_ticker_df.columns:
                best_by_ticker_df[column] = np.nan

    global_summary_df = summarize_global_thresholds(
        scored_df=scored_df,
        best_by_ticker_df=best_by_ticker_df,
        baseline_threshold=baseline_threshold,
    )
    group_summary_df, best_by_group_df = summarize_group_thresholds(
        scored_df=scored_df,
        best_by_ticker_df=best_by_ticker_df,
        baseline_threshold=baseline_threshold,
    )
    policy = determine_global_policy(
        global_summary_df=global_summary_df,
        best_by_group_df=best_by_group_df,
        baseline_threshold=baseline_threshold,
    )
    prior_comparison = compare_with_previous_decisions(
        global_summary_df=global_summary_df,
        best_by_ticker_df=best_by_ticker_df,
        best_by_group_df=best_by_group_df,
        previous_artifacts=previous_artifacts,
        baseline_threshold=baseline_threshold,
    )
    readiness = determine_readiness(
        policy=policy,
        best_by_ticker_df=best_by_ticker_df,
        best_by_group_df=best_by_group_df,
        metadata_df=metadata_df,
    )
    next_experiments = build_next_required_experiments(
        policy=policy,
        readiness=readiness,
        best_by_ticker_df=best_by_ticker_df,
        best_by_group_df=best_by_group_df,
    )
    recommendations_text = build_threshold_recommendations(
        policy=policy,
        readiness=readiness,
        global_summary_df=global_summary_df,
        best_by_ticker_df=best_by_ticker_df,
        best_by_group_df=best_by_group_df,
        prior_comparison=prior_comparison,
        next_experiments=next_experiments,
        warnings=warnings,
        baseline_threshold=baseline_threshold,
    )

    decision_payload = {
        "config": {
            "data_dir": str(data_dir),
            "output_dir": str(output_dir),
            "metadata_file": str(metadata_path) if metadata_path is not None else None,
            "thresholds": thresholds_normalized,
            "tickers": sorted(_normalize_ticker_filter(tickers) or []),
            "strict_mode": bool(strict),
            "hold_period": int(hold_period),
            "allow_overlap": bool(allow_overlap),
            "min_trades": int(min_trades),
            "baseline_threshold": float(baseline_threshold),
        },
        "default_threshold_decision": {
            "decision_code": policy["decision_code"],
            "mode": policy["mode"],
            "selected_default_threshold": policy["selected_default_threshold"],
            "keep_default_2_0": policy["keep_default_2_0"],
            "decision_confidence": policy["decision_confidence"],
            "decision_margin": policy["decision_margin"],
            "reason": policy["reason"],
        },
        "adaptive_threshold_by_group": policy["adaptive_threshold_by_group"],
        "readiness": readiness,
        "global_summary": global_summary_df.to_dict(orient="records"),
        "tickers_by_selected_threshold": {
            _format_threshold(threshold): best_by_ticker_df.loc[
                np.isclose(best_by_ticker_df["best_threshold"], threshold),
                "ticker",
            ].tolist()
            for threshold in thresholds_normalized
        },
        "groups_by_selected_threshold": {
            _format_threshold(threshold): (
                []
                if best_by_group_df.empty
                else [
                    f"{row['group_field']}={row['group_value']}"
                    for _, row in best_by_group_df.loc[
                        np.isclose(best_by_group_df["best_threshold"], threshold)
                    ].iterrows()
                ]
            )
            for threshold in thresholds_normalized
        },
        "priority_ticker_summary": {
            "priority_ticker_count": int(best_by_ticker_df["priority_from_previous_artifacts"].sum()),
            "priority_confirmed": prior_comparison["priority_ticker_confirmed"],
            "priority_contradicted": prior_comparison["priority_ticker_contradicted"],
        },
        "prior_artifact_comparison": prior_comparison,
        "next_required_experiments": list(next_experiments),
        "warnings": warnings,
        "skipped_files": skipped_rows,
    }

    export_warnings = export_threshold_sweep_outputs(
        output_dir=output_dir,
        results_df=scored_df.reindex(columns=RESULT_COLUMNS),
        best_by_ticker_df=best_by_ticker_df.reindex(columns=BEST_BY_TICKER_COLUMNS),
        global_summary_df=global_summary_df.reindex(columns=GLOBAL_SUMMARY_COLUMNS),
        group_summary_df=group_summary_df.reindex(columns=GROUP_SUMMARY_COLUMNS),
        best_by_group_df=best_by_group_df.reindex(columns=BEST_BY_GROUP_COLUMNS),
        recommendations_text=recommendations_text,
        decision_payload=decision_payload,
    )

    if export_warnings:
        warnings.extend(export_warnings)
        decision_payload["warnings"] = warnings
        (output_dir / "phase_a_threshold_decision.json").write_text(
            json.dumps(_sanitize_for_json(decision_payload), indent=2, ensure_ascii=True, allow_nan=False),
            encoding="utf-8",
        )

    print("\nThreshold sweep complete.")
    print(f"Successful ticker files: {results_df['ticker'].nunique()}")
    print(f"Skipped ticker files: {len(skipped_rows)}")
    print(f"Global best threshold: {_format_threshold(policy['selected_default_threshold'])}")
    print(f"Readiness: {readiness['status']}")

    return {
        "results_df": scored_df.reindex(columns=RESULT_COLUMNS),
        "best_by_ticker_df": best_by_ticker_df.reindex(columns=BEST_BY_TICKER_COLUMNS),
        "global_summary_df": global_summary_df.reindex(columns=GLOBAL_SUMMARY_COLUMNS),
        "group_summary_df": group_summary_df.reindex(columns=GROUP_SUMMARY_COLUMNS),
        "best_by_group_df": best_by_group_df.reindex(columns=BEST_BY_GROUP_COLUMNS),
        "recommendations_text": recommendations_text,
        "decision_payload": decision_payload,
        "warnings": warnings,
        "skipped_rows": skipped_rows,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for the threshold sweep experiment."""

    parser = argparse.ArgumentParser(
        description="Run a systematic Phase A threshold sweep on historical per-ticker CSV files."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing per-ticker historical CSV files. Default: data",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory to save threshold sweep artifacts. Default: output",
    )
    parser.add_argument(
        "--metadata-file",
        default=None,
        help="Optional ticker metadata CSV. Example: data/ticker_metadata.csv",
    )
    parser.add_argument(
        "--thresholds",
        nargs="*",
        type=float,
        default=DEFAULT_THRESHOLDS,
        help="Thresholds to test, for example: --thresholds 1.5 2.0 2.5 3.0",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=None,
        help="Optional ticker filter, for example: --tickers BBCA BMRI TLKM or --tickers BBCA,BMRI",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Use strict Phase A signal instead of the default minimum signal.",
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
        "--min-trades",
        type=int,
        default=8,
        help="Minimum trade floor required before a threshold can win by default. Default: 8",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)

    try:
        run_phase_a_threshold_sweep(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=Path(args.metadata_file) if args.metadata_file else None,
            thresholds=args.thresholds,
            tickers=args.tickers,
            strict=args.strict,
            hold_period=args.hold_period,
            allow_overlap=args.allow_overlap,
            min_trades=args.min_trades,
        )
    except ThresholdSweepCliError as exc:
        print(str(exc))
        _print_next_steps(exc.suggestions)
        return 1
    except Exception as exc:
        print(f"Unexpected threshold sweep failure: {exc}")
        _print_next_steps(
            [
                f"Validate the input data folder exists and contains OHLCV CSV files: {data_dir}",
                f"Generate sample CSV data with: {_bootstrap_command(data_dir)}",
            ]
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
