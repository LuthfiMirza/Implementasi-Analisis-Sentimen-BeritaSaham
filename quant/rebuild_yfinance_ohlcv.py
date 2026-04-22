"""Rebuild clean daily OHLCV datasets from yfinance for research/backtests.

Example
-------
python3 -m quant.rebuild_yfinance_ohlcv \
  --series BBCA=BBCA.JK \
  --series BBRI=BBRI.JK \
  --output-dir data/stocks
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


VENDOR_PY = Path(__file__).resolve().parent.parent / ".vendor-py"
if VENDOR_PY.exists():
    sys.path.insert(0, str(VENDOR_PY))


DEFAULT_SOURCE = "yfinance_raw_daily"
MAX_ALLOWED_GAP_DAYS = 14
CSV_COLUMNS = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "dividends",
    "splits",
    "source",
]
ALLOWED_FREEZE_STATUSES = {"frozen", "approved"}


class RebuildCliError(ValueError):
    """Friendly CLI error for rebuild failures."""


@dataclass
class RebuildRecord:
    name: str
    symbol: str
    output_path: str
    status: str
    rows: int
    date_start: str | None
    date_end: str | None
    issues: list[str]


def _get_yfinance_module():
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - friendly runtime path
        raise RebuildCliError(
            "yfinance is not available. Install it first, for example: "
            "python3 -m pip install --target ./.vendor-py yfinance"
        ) from exc
    return yf


def _parse_series_args(items: Sequence[str]) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for item in items:
        token = str(item).strip()
        if not token:
            continue
        if "=" not in token:
            raise RebuildCliError(f"Invalid --series entry '{token}'. Expected NAME=SYMBOL.")
        name, symbol = token.split("=", 1)
        name = name.strip().upper()
        symbol = symbol.strip()
        if not name or not symbol:
            raise RebuildCliError(f"Invalid --series entry '{token}'. Expected NAME=SYMBOL.")
        parsed.append((name, symbol))
    if not parsed:
        raise RebuildCliError("No series requested. Pass at least one --series NAME=SYMBOL.")
    return parsed


def _parse_universe_file(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        raise RebuildCliError(f"Universe file not found: {path}")

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or [])

    required = {"ticker", "yahoo_symbol", "freeze_status"}
    missing = sorted(required - fieldnames)
    if missing:
        raise RebuildCliError(
            f"Universe file {path} is missing required columns {missing}. "
            "Expected at least ticker,yahoo_symbol,freeze_status."
        )

    parsed: list[tuple[str, str]] = []
    for row in rows:
        freeze_status = str(row.get("freeze_status") or "").strip().lower()
        if freeze_status not in ALLOWED_FREEZE_STATUSES:
            continue
        name = str(row.get("ticker") or "").strip().upper()
        symbol = str(row.get("yahoo_symbol") or "").strip()
        if not name or not symbol:
            raise RebuildCliError(f"Universe file {path} contains an invalid frozen row without ticker/symbol.")
        parsed.append((name, symbol))

    if not parsed:
        raise RebuildCliError(
            f"Universe file {path} contains no rows with freeze_status in {sorted(ALLOWED_FREEZE_STATUSES)}. "
            "Freeze the universe list before mass rebuild."
        )

    return parsed


def fetch_history_from_yfinance(symbol: str, period: str = "max") -> pd.DataFrame:
    yf = _get_yfinance_module()
    frame = yf.Ticker(symbol).history(
        period=period,
        interval="1d",
        auto_adjust=False,
        actions=True,
    )
    return frame


def normalize_yfinance_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=CSV_COLUMNS[:-1])

    working = frame.copy()
    if isinstance(working.index, pd.MultiIndex):
        working = working.reset_index()
    else:
        working = working.reset_index()

    date_column = "Date" if "Date" in working.columns else working.columns[0]
    working = working.rename(
        columns={
            date_column: "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
            "Dividends": "dividends",
            "Stock Splits": "splits",
        }
    )

    missing_columns = [column for column in CSV_COLUMNS[:-1] if column not in working.columns]
    for column in missing_columns:
        working[column] = 0.0 if column in {"dividends", "splits"} else pd.NA

    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    if getattr(working["date"].dt, "tz", None) is not None:
        working["date"] = working["date"].dt.tz_localize(None)
    working["date"] = working["date"].dt.normalize()
    working["volume"] = pd.to_numeric(working["volume"], errors="coerce").fillna(0).astype("int64")

    numeric_columns = ["open", "high", "low", "close", "adj_close", "dividends", "splits"]
    for column in numeric_columns:
        working[column] = pd.to_numeric(working[column], errors="coerce")

    working = working.loc[:, CSV_COLUMNS[:-1]].copy()
    working = working.sort_values("date").reset_index(drop=True)
    working["date"] = working["date"].dt.strftime("%Y-%m-%d")

    return working


def validate_daily_frame(frame: pd.DataFrame) -> list[str]:
    issues: list[str] = []
    if frame.empty:
        return ["empty_history"]

    dates = pd.to_datetime(frame["date"], errors="coerce")
    if dates.isna().any():
        issues.append("invalid_dates_present")
        return issues

    if not dates.is_monotonic_increasing:
        issues.append("dates_not_ascending")
    if dates.duplicated().any():
        issues.append("duplicate_dates_present")
    if (dates.dt.dayofweek >= 5).any():
        issues.append("weekend_rows_present")

    gaps = dates.diff().dt.days.fillna(1)
    if not gaps.empty and int(gaps.max()) > MAX_ALLOWED_GAP_DAYS:
        issues.append("non_daily_gap_detected")

    interior_years = dates.dt.year.value_counts().sort_index()
    if not interior_years.empty:
        first_year = int(dates.iloc[0].year)
        last_year = int(dates.iloc[-1].year)
        suspicious = [
            int(year)
            for year, count in interior_years.items()
            if first_year < int(year) < last_year and int(count) < 120
        ]
        if suspicious:
            issues.append("mixed_frequency_contamination_detected")

    required_price_columns = ["open", "high", "low", "close", "adj_close"]
    if frame[required_price_columns].isna().any().any():
        issues.append("missing_price_values")

    return issues


def rebuild_series(
    series: Iterable[tuple[str, str]],
    output_dir: Path,
    *,
    period: str = "max",
    fetcher: Callable[[str, str], pd.DataFrame] = fetch_history_from_yfinance,
) -> list[RebuildRecord]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[RebuildRecord] = []

    for name, symbol in series:
        raw = fetcher(symbol, period)
        normalized = normalize_yfinance_frame(raw)
        issues = validate_daily_frame(normalized)
        target_path = output_dir / f"{name}.csv"

        if issues:
            records.append(
                RebuildRecord(
                    name=name,
                    symbol=symbol,
                    output_path=str(target_path),
                    status="invalid",
                    rows=int(len(normalized)),
                    date_start=None if normalized.empty else str(normalized.iloc[0]["date"]),
                    date_end=None if normalized.empty else str(normalized.iloc[-1]["date"]),
                    issues=issues,
                )
            )
            continue

        normalized = normalized.copy()
        normalized["source"] = DEFAULT_SOURCE
        normalized.to_csv(target_path, index=False)
        records.append(
            RebuildRecord(
                name=name,
                symbol=symbol,
                output_path=str(target_path),
                status="rebuilt",
                rows=int(len(normalized)),
                date_start=str(normalized.iloc[0]["date"]),
                date_end=str(normalized.iloc[-1]["date"]),
                issues=[],
            )
        )

    return records


def write_metadata(records: Sequence[RebuildRecord], output_dir: Path) -> Path:
    path = output_dir / "rebuild_ticker_metadata.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ticker", "symbol", "status", "rows", "date_start", "date_end", "issues", "output_path"],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "ticker": record.name,
                    "symbol": record.symbol,
                    "status": record.status,
                    "rows": record.rows,
                    "date_start": record.date_start,
                    "date_end": record.date_end,
                    "issues": "|".join(record.issues),
                    "output_path": record.output_path,
                }
            )
    return path


def write_summary(records: Sequence[RebuildRecord], output_dir: Path) -> tuple[Path, Path]:
    json_path = output_dir / "rebuild_summary.json"
    txt_path = output_dir / "rebuild_summary.txt"
    payload = {
        "series": [
            {
                "name": record.name,
                "symbol": record.symbol,
                "status": record.status,
                "rows": record.rows,
                "date_start": record.date_start,
                "date_end": record.date_end,
                "issues": list(record.issues),
                "output_path": record.output_path,
            }
            for record in records
        ]
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = []
    for record in records:
        lines.append(
            f"{record.name} ({record.symbol}): {record.status}, rows={record.rows}, "
            f"range={record.date_start}..{record.date_end}, issues={','.join(record.issues) or '-'}"
        )
    txt_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return json_path, txt_path


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rebuild clean OHLCV datasets from yfinance.")
    parser.add_argument(
        "--series",
        action="append",
        default=[],
        help="Series mapping in NAME=SYMBOL format. Example: BBCA=BBCA.JK or IHSG=^JKSE",
    )
    parser.add_argument(
        "--universe-file",
        default=None,
        help="CSV file with ticker,yahoo_symbol,freeze_status. Only frozen/approved rows will be fetched.",
    )
    parser.add_argument("--output-dir", default="data/stocks", help="Directory for rebuilt CSV files.")
    parser.add_argument("--period", default="max", help="yfinance period argument. Default: max")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    try:
        series: list[tuple[str, str]] = []
        if args.series:
            series.extend(_parse_series_args(args.series))
        if args.universe_file:
            series.extend(_parse_universe_file(Path(args.universe_file)))
        if not series:
            raise RebuildCliError("No series requested. Pass --series NAME=SYMBOL or --universe-file PATH.")
        output_dir = Path(args.output_dir)
        records = rebuild_series(series=series, output_dir=output_dir, period=str(args.period))
        write_metadata(records, output_dir)
        write_summary(records, output_dir)
    except RebuildCliError as exc:
        parser.error(str(exc))
        return 2

    invalid = [record for record in records if record.status != "rebuilt"]
    if invalid:
        for record in invalid:
            print(f"{record.name}: invalid rebuild ({', '.join(record.issues)})", file=sys.stderr)
        return 1

    for record in records:
        print(f"rebuilt {record.name} -> {record.output_path} ({record.rows} rows)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
