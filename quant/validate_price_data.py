"""Validate per-ticker OHLCV CSV files before running Phase A evaluation.

Example
-------
Preferred execution from project root:

    python3 -m quant.validate_price_data --data-dir data --output-dir output
"""

from __future__ import annotations

import argparse
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a import NUMERIC_COLUMNS, REQUIRED_COLUMNS  # noqa: E402

VALIDATION_COLUMNS = [
    "ticker",
    "file_path",
    "status",
    "rows_raw",
    "rows_after_clean",
    "date_start",
    "date_end",
    "issue_count",
    "issues",
]


class ValidationCliError(ValueError):
    """Friendly CLI error used by the validator."""

    def __init__(self, message: str, suggestions: Optional[Sequence[str]] = None) -> None:
        super().__init__(message)
        self.suggestions = list(suggestions or [])


@dataclass
class ValidationRecord:
    """Validation result for one ticker CSV."""

    ticker: str
    file_path: str
    status: str
    rows_raw: int
    rows_after_clean: int
    date_start: Optional[pd.Timestamp]
    date_end: Optional[pd.Timestamp]
    issues: List[str]


def extract_ticker_from_filename(path: Path) -> str:
    """Extract the ticker symbol from a CSV filename."""

    return path.stem.upper().strip()


def _clean_numeric_series(series: pd.Series) -> pd.Series:
    """Coerce numeric columns that may arrive as strings."""

    if series.dtype == object:
        series = (
            series.astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("_", "", regex=False)
            .str.strip()
        )
    return pd.to_numeric(series, errors="coerce")


def _normalize_ticker_filter(tickers: Optional[Iterable[str]]) -> Optional[set[str]]:
    """Normalize optional CLI ticker filters."""

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
    """Return the sample-data bootstrap command shown to users."""

    return f"python3 -m quant.bootstrap_sample_data --data-dir {shlex.quote(str(data_dir))}"


def _print_next_steps(steps: Sequence[str]) -> None:
    """Print actionable next-step suggestions."""

    cleaned_steps = [step for step in steps if step]
    if not cleaned_steps:
        return

    print("\nNext step suggestions:")
    for step in cleaned_steps:
        print(f"  {step}")


def validate_price_csv(path: Path, min_rows: int = 50) -> ValidationRecord:
    """Validate one OHLCV CSV file."""

    ticker = extract_ticker_from_filename(path)
    issues: List[str] = []

    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return ValidationRecord(
            ticker=ticker,
            file_path=str(path),
            status="invalid",
            rows_raw=0,
            rows_after_clean=0,
            date_start=None,
            date_end=None,
            issues=["CSV is empty."],
        )
    except pd.errors.ParserError as exc:
        return ValidationRecord(
            ticker=ticker,
            file_path=str(path),
            status="invalid",
            rows_raw=0,
            rows_after_clean=0,
            date_start=None,
            date_end=None,
            issues=[f"CSV parser error: {exc}"],
        )

    rows_raw = int(len(frame))
    if frame.empty:
        issues.append("CSV contains no rows.")

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        issues.append(
            f"Missing required columns: {missing_columns}. Expected columns: {REQUIRED_COLUMNS}."
        )
        return ValidationRecord(
            ticker=ticker,
            file_path=str(path),
            status="invalid",
            rows_raw=rows_raw,
            rows_after_clean=0,
            date_start=None,
            date_end=None,
            issues=issues,
        )

    cleaned = frame.copy()
    cleaned["date"] = pd.to_datetime(cleaned["date"], errors="coerce")
    invalid_dates = int(cleaned["date"].isna().sum())
    if invalid_dates:
        issues.append(f"Found {invalid_dates} rows with invalid date values.")

    for column in NUMERIC_COLUMNS:
        cleaned[column] = _clean_numeric_series(cleaned[column])
        invalid_numeric = int(cleaned[column].isna().sum())
        if invalid_numeric:
            issues.append(f"Found {invalid_numeric} non-numeric or NaN values in '{column}'.")

    duplicate_dates = int(cleaned["date"].duplicated(keep=False).sum())
    if duplicate_dates:
        issues.append(f"Found {duplicate_dates} duplicate date rows.")

    if "volume" in cleaned.columns and (cleaned["volume"] < 0).any():
        issues.append("Found negative volume values.")

    candidate = cleaned.dropna(subset=REQUIRED_COLUMNS).copy()
    candidate = candidate.loc[candidate["volume"] >= 0].copy()
    candidate = candidate.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    rows_after_clean = int(len(candidate))

    if rows_after_clean < min_rows:
        issues.append(f"Usable rows after cleaning: {rows_after_clean}. Minimum required: {min_rows}.")
    if rows_after_clean and int((candidate["volume"] > 0).sum()) == 0:
        issues.append("Volume is zero for all usable rows.")
    if rows_after_clean == 0:
        issues.append("No usable OHLCV rows remain after cleaning.")

    date_start = candidate["date"].iloc[0] if rows_after_clean else None
    date_end = candidate["date"].iloc[-1] if rows_after_clean else None
    status = "invalid" if issues else "valid"

    return ValidationRecord(
        ticker=ticker,
        file_path=str(path),
        status=status,
        rows_raw=rows_raw,
        rows_after_clean=rows_after_clean,
        date_start=date_start,
        date_end=date_end,
        issues=issues,
    )


def build_validation_summary(records: Sequence[ValidationRecord]) -> pd.DataFrame:
    """Convert validation records into a DataFrame."""

    if not records:
        return pd.DataFrame(columns=VALIDATION_COLUMNS)

    summary = pd.DataFrame(
        [
            {
                "ticker": record.ticker,
                "file_path": record.file_path,
                "status": record.status,
                "rows_raw": record.rows_raw,
                "rows_after_clean": record.rows_after_clean,
                "date_start": record.date_start,
                "date_end": record.date_end,
                "issue_count": len(record.issues),
                "issues": "; ".join(record.issues),
            }
            for record in records
        ]
    )
    summary = summary.reindex(columns=VALIDATION_COLUMNS)
    summary = summary.sort_values(["status", "issue_count", "ticker"], ascending=[True, True, True])
    summary = summary.reset_index(drop=True)
    return summary


def export_validation_summary(summary_df: pd.DataFrame, output_dir: Path) -> Path:
    """Export validation results to CSV."""

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "data_validation_summary.csv"
    summary_df.to_csv(target_path, index=False)
    print(f"Saved validation summary to {target_path}")
    return target_path


def validate_folder(
    folder_path: Path,
    output_dir: Optional[Path] = None,
    tickers: Optional[Iterable[str]] = None,
    min_rows: int = 50,
) -> pd.DataFrame:
    """Validate all CSV files in a folder and optionally export the results."""

    folder = Path(folder_path)
    if not folder.exists():
        raise ValidationCliError(
            f"Data directory not found: {folder}",
            suggestions=[f"Generate sample CSV data with: {_bootstrap_command(folder)}"],
        )
    if not folder.is_dir():
        raise ValidationCliError(f"Data path is not a directory: {folder}")

    ticker_filter = _normalize_ticker_filter(tickers)
    all_csv_files = sorted(folder.glob("*.csv"))
    if not all_csv_files:
        raise ValidationCliError(
            f"No CSV files found in {folder}",
            suggestions=[f"Generate sample CSV data with: {_bootstrap_command(folder)}"],
        )

    if ticker_filter is not None:
        csv_files = [
            path for path in all_csv_files if extract_ticker_from_filename(path) in ticker_filter
        ]
    else:
        csv_files = all_csv_files

    if not csv_files:
        raise ValidationCliError("No CSV files matched the requested ticker filter.")

    records: List[ValidationRecord] = []
    for path in csv_files:
        ticker = extract_ticker_from_filename(path)
        print(f"Validating {ticker}...")
        records.append(validate_price_csv(path, min_rows=min_rows))

    summary_df = build_validation_summary(records)
    if output_dir is not None:
        export_validation_summary(summary_df, Path(output_dir))

    print("\nValidation complete.")
    print(f"Total files found: {len(all_csv_files)}")
    print(f"Total files selected: {len(csv_files)}")
    print(f"Valid files: {int((summary_df['status'] == 'valid').sum())}")
    print(f"Invalid files: {int((summary_df['status'] == 'invalid').sum())}")

    return summary_df


def print_validation_report(summary_df: pd.DataFrame) -> None:
    """Print a readable validation report."""

    if summary_df.empty:
        print("\nNo files were validated.")
        return

    valid_df = summary_df.loc[summary_df["status"] == "valid"].copy()
    invalid_df = summary_df.loc[summary_df["status"] == "invalid"].copy()

    print("\nValidation summary:\n")
    print(summary_df.to_string(index=False))

    print("\nValid files:\n")
    if valid_df.empty:
        print("None")
    else:
        print(valid_df[["ticker", "rows_after_clean", "date_start", "date_end"]].to_string(index=False))

    print("\nInvalid files:\n")
    if invalid_df.empty:
        print("None")
    else:
        print(invalid_df[["ticker", "issues"]].to_string(index=False))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Validate per-ticker OHLCV CSV files before running Phase A evaluation."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing per-ticker CSV files. Default: data",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory to save validation exports. Default: output",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        default=None,
        help="Optional ticker filter, e.g. --tickers BBCA BMRI or --tickers BBCA,BMRI",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=50,
        help="Minimum usable row count required per file. Default: 50",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)

    try:
        summary_df = validate_folder(
            folder_path=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            tickers=args.tickers,
            min_rows=args.min_rows,
        )
    except ValidationCliError as exc:
        print(str(exc))
        _print_next_steps(exc.suggestions)
        return 1
    except Exception as exc:
        print(f"Validation failed: {exc}")
        return 1

    print_validation_report(summary_df)
    return 0 if not summary_df.empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
