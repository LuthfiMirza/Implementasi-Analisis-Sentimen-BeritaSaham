"""Build the clean indicator master table from rebuilt stock and IHSG datasets.

Example
-------
python3 -m quant.build_indicator_master_table \
  --stocks-dir data/stocks \
  --ihsg-file data/IHSG.csv \
  --output-dir data/indicator_master \
  --artifact-dir output
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


PRICE_BASIS = "adj_close"
STOCK_MASTER_FILENAME = "stock_indicator_master.csv"
IHSG_MASTER_FILENAME = "IHSG_indicator_master.csv"
STATUS_JSON_FILENAME = "phase_0b_3_indicator_master_status.json"
STATUS_TXT_FILENAME = "phase_0b_3_indicator_master_status.txt"
SCHEMA_JSON_FILENAME = "phase_0b_3_indicator_master_schema.json"

REQUIRED_PRICE_COLUMNS = [
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
EXCLUDED_STOCK_FILENAMES = {
    "ticker_metadata.csv",
    "rebuild_ticker_metadata.csv",
    "rebuild_summary.csv",
    "rebuild_summary.txt",
    "rebuild_summary.json",
}


class IndicatorMasterError(ValueError):
    """Friendly error for indicator master table generation."""


@dataclass(frozen=True)
class SourceValidation:
    label: str
    rows: int
    date_start: str
    date_end: str
    max_gap_days: int


def _load_price_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = [column for column in REQUIRED_PRICE_COLUMNS if column not in frame.columns]
    if missing:
        raise IndicatorMasterError(
            f"{path} is missing required columns {missing}. Expected {REQUIRED_PRICE_COLUMNS}."
        )

    working = frame.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce")
    if working["date"].isna().any():
        raise IndicatorMasterError(f"{path} contains invalid date values.")

    for column in ["open", "high", "low", "close", "adj_close", "volume", "dividends", "splits"]:
        working[column] = pd.to_numeric(working[column], errors="coerce")
    if working[["open", "high", "low", "close", "adj_close", "volume"]].isna().any().any():
        raise IndicatorMasterError(f"{path} contains invalid numeric values in core price columns.")

    return working


def _validate_source_frame(frame: pd.DataFrame, label: str) -> SourceValidation:
    if frame.empty:
        raise IndicatorMasterError(f"{label} contains no rows.")

    if frame["date"].duplicated().any():
        raise IndicatorMasterError(f"{label} contains duplicate dates.")

    if not frame["date"].is_monotonic_increasing:
        raise IndicatorMasterError(f"{label} dates are not monotonic ascending.")

    gaps = frame["date"].diff().dt.days.dropna()
    max_gap_days = int(gaps.max()) if not gaps.empty else 0

    return SourceValidation(
        label=label,
        rows=int(len(frame)),
        date_start=frame["date"].iloc[0].strftime("%Y-%m-%d"),
        date_end=frame["date"].iloc[-1].strftime("%Y-%m-%d"),
        max_gap_days=max_gap_days,
    )


def _compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = average_gain / average_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    rsi = rsi.where(average_loss.ne(0), 100.0)
    rsi = rsi.where(~(average_gain.eq(0) & average_loss.eq(0)), 50.0)
    return rsi


def _compute_indicator_frame(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.sort_values("date").reset_index(drop=True).copy()
    basis = pd.to_numeric(working[PRICE_BASIS], errors="coerce")
    if basis.isna().any():
        raise IndicatorMasterError("Indicator basis adj_close contains invalid values.")

    working["ema20"] = basis.ewm(span=20, adjust=False, min_periods=20).mean()
    working["ema50"] = basis.ewm(span=50, adjust=False, min_periods=50).mean()
    working["ema200"] = basis.ewm(span=200, adjust=False, min_periods=200).mean()
    working["return_20d"] = basis.pct_change(periods=20)
    working["momentum_score"] = working["return_20d"]
    working["rsi14"] = _compute_rsi(basis, period=14)
    working["volume_ma20"] = working["volume"].rolling(window=20, min_periods=20).mean()

    working["ema20_ready"] = working["ema20"].notna()
    working["ema50_ready"] = working["ema50"].notna()
    working["ema200_ready"] = working["ema200"].notna()
    working["return_20d_ready"] = working["return_20d"].notna()
    working["momentum_score_ready"] = working["momentum_score"].notna()
    working["rsi14_ready"] = working["rsi14"].notna()
    working["volume_ma20_ready"] = working["volume_ma20"].notna()
    working["indicator_warmup_complete"] = (
        working["ema200_ready"]
        & working["return_20d_ready"]
        & working["momentum_score_ready"]
        & working["rsi14_ready"]
        & working["volume_ma20_ready"]
    )

    return working


def _load_stock_sources(stocks_dir: Path) -> list[tuple[str, Path]]:
    if not stocks_dir.exists():
        raise IndicatorMasterError(f"Stocks directory not found: {stocks_dir}")

    sources: list[tuple[str, Path]] = []
    for path in sorted(stocks_dir.glob("*.csv")):
        if path.name in EXCLUDED_STOCK_FILENAMES:
            continue
        ticker = path.stem.upper()
        sources.append((ticker, path))

    if not sources:
        raise IndicatorMasterError(f"No stock CSV files found in {stocks_dir}.")

    return sources


def build_indicator_master_table(
    *,
    stocks_dir: Path,
    ihsg_file: Path,
    output_dir: Path,
    artifact_dir: Path,
) -> dict:
    stock_sources = _load_stock_sources(stocks_dir)
    ihsg_raw = _load_price_frame(ihsg_file)
    ihsg_validation = _validate_source_frame(ihsg_raw, "IHSG")
    ihsg_master = _compute_indicator_frame(ihsg_raw)
    ihsg_master["market_regime_ready"] = ihsg_master["ema200_ready"]
    ihsg_master["market_regime_bullish"] = (
        ihsg_master["market_regime_ready"] & ihsg_master[PRICE_BASIS].gt(ihsg_master["ema200"])
    )
    ihsg_master["indicator_price_basis"] = PRICE_BASIS

    stock_frames: list[pd.DataFrame] = []
    stock_validations: list[SourceValidation] = []
    for ticker, path in stock_sources:
        raw = _load_price_frame(path)
        stock_validations.append(_validate_source_frame(raw, ticker))
        enriched = _compute_indicator_frame(raw)
        enriched["ticker"] = ticker
        enriched["indicator_price_basis"] = PRICE_BASIS
        stock_frames.append(enriched)

    combined = pd.concat(stock_frames, ignore_index=True)
    ihsg_join = ihsg_master[
        [
            "date",
            PRICE_BASIS,
            "ema200",
            "market_regime_ready",
            "market_regime_bullish",
        ]
    ].rename(
        columns={
            PRICE_BASIS: "ihsg_adj_close",
            "ema200": "ihsg_ema200",
            "market_regime_ready": "ihsg_regime_ready",
            "market_regime_bullish": "ihsg_regime_bullish",
        }
    )
    combined = combined.merge(ihsg_join, on="date", how="left")
    combined["market_regime_basis"] = "IHSG_adj_close_vs_ema200"

    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    stock_master_path = output_dir / STOCK_MASTER_FILENAME
    ihsg_master_path = output_dir / IHSG_MASTER_FILENAME
    combined.sort_values(["ticker", "date"]).to_csv(stock_master_path, index=False)
    ihsg_master.sort_values("date").to_csv(ihsg_master_path, index=False)

    final_columns = list(combined.columns)
    schema_payload = {
        "phase": "phase_0b_3_indicator_master_table",
        "status": "completed",
        "output_location": str(output_dir),
        "stock_output_file": str(stock_master_path),
        "ihsg_output_file": str(ihsg_master_path),
        "source_files": {
            "stocks_dir": str(stocks_dir),
            "stock_files": [str(path) for _, path in stock_sources],
            "ihsg_file": str(ihsg_file),
        },
        "price_policy": {
            "official_indicator_basis": PRICE_BASIS,
            "regime_return_momentum_ema_use": PRICE_BASIS,
            "raw_ohlc_for_atr_exit": "not_official_yet",
        },
        "generated_columns": final_columns,
        "warmup_policy": {
            "ema20_ready_after_rows": 20,
            "ema50_ready_after_rows": 50,
            "ema200_ready_after_rows": 200,
            "return_20d_ready_after_rows": 21,
            "rsi14_ready_after_rows": 14,
            "volume_ma20_ready_after_rows": 20,
            "indicator_warmup_complete": "all core ready flags true",
        },
    }
    schema_path = artifact_dir / SCHEMA_JSON_FILENAME
    schema_path.write_text(json.dumps(schema_payload, indent=2), encoding="utf-8")

    status_payload = {
        "phase": "phase_0b_3_indicator_master_table",
        "status": "completed",
        "stock_sources_used": len(stock_sources),
        "stock_rows": int(len(combined)),
        "ihsg_rows": int(len(ihsg_master)),
        "stocks": [validation.__dict__ for validation in stock_validations],
        "ihsg": ihsg_validation.__dict__,
        "price_policy": schema_payload["price_policy"],
        "layer_1_regime_ready": bool(ihsg_master["market_regime_ready"].any()),
        "layer_5_atr_exit_ready": False,
        "layer_5_blocker": (
            "raw_ohlc_corporate_action_policy_not_frozen; back_adjusted_ohlc_or_split_aware_policy_required"
        ),
        "next_action": "phase_1_market_regime_filter",
    }
    status_json_path = artifact_dir / STATUS_JSON_FILENAME
    status_json_path.write_text(json.dumps(status_payload, indent=2), encoding="utf-8")

    status_lines = [
        "Phase 0B.3 - Indicator Master Table",
        "===================================",
        "",
        "Status: completed",
        f"Stock output: {stock_master_path}",
        f"IHSG output: {ihsg_master_path}",
        f"Stock sources used: {len(stock_sources)}",
        f"Stock rows: {len(combined)}",
        f"IHSG rows: {len(ihsg_master)}",
        "",
        "Price policy:",
        f"- official indicator basis = {PRICE_BASIS}",
        f"- regime / return / momentum / EMA = {PRICE_BASIS}",
        "- raw OHLC for ATR / exit = not official yet",
        "",
        "Layer readiness:",
        f"- Layer 1 regime ready = {status_payload['layer_1_regime_ready']}",
        f"- Layer 5 ATR/exit ready = {status_payload['layer_5_atr_exit_ready']}",
        f"- Layer 5 blocker = {status_payload['layer_5_blocker']}",
    ]
    status_txt_path = artifact_dir / STATUS_TXT_FILENAME
    status_txt_path.write_text("\n".join(status_lines) + "\n", encoding="utf-8")

    return {
        "schema": schema_payload,
        "status": status_payload,
        "stock_output_file": stock_master_path,
        "ihsg_output_file": ihsg_master_path,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the clean indicator master table.")
    parser.add_argument("--stocks-dir", default="data/stocks", help="Directory containing clean stock CSV files.")
    parser.add_argument("--ihsg-file", default="data/IHSG.csv", help="Clean IHSG CSV file.")
    parser.add_argument(
        "--output-dir",
        default="data/indicator_master",
        help="Directory for the master indicator datasets.",
    )
    parser.add_argument(
        "--artifact-dir",
        default="output",
        help="Directory for status/schema artifacts.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    build_indicator_master_table(
        stocks_dir=Path(args.stocks_dir),
        ihsg_file=Path(args.ihsg_file),
        output_dir=Path(args.output_dir),
        artifact_dir=Path(args.artifact_dir),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
