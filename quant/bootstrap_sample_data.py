"""Generate realistic sample OHLCV CSV files for Phase A evaluation demos.

Example
-------
Preferred execution from project root:

    python3 -m quant.bootstrap_sample_data --data-dir data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REQUIRED_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
DEFAULT_ROWS = 140
TICKER_PROFILES: Dict[str, Dict[str, float | int]] = {
    "BBCA": {
        "seed": 11,
        "start_price": 9300.0,
        "drift_bps": 6.0,
        "volatility": 0.0080,
        "base_volume": 18_500_000,
    },
    "BMRI": {
        "seed": 17,
        "start_price": 6350.0,
        "drift_bps": 7.5,
        "volatility": 0.0100,
        "base_volume": 32_000_000,
    },
    "TLKM": {
        "seed": 23,
        "start_price": 3620.0,
        "drift_bps": 4.5,
        "volatility": 0.0075,
        "base_volume": 21_500_000,
    },
}


def _event_positions(rows: int) -> List[int]:
    """Return deterministic event bars used to trigger volume spikes."""

    candidate_positions = [int(rows * 0.44), int(rows * 0.62), int(rows * 0.79), int(rows * 0.91)]
    return sorted({max(55, min(rows - 8, value)) for value in candidate_positions})


def generate_sample_ticker_dataframe(
    ticker: str,
    rows: int = DEFAULT_ROWS,
    start_date: str = "2025-01-02",
) -> pd.DataFrame:
    """Generate one realistic weekday-only OHLCV sample DataFrame."""

    ticker = ticker.upper()
    if ticker not in TICKER_PROFILES:
        raise ValueError(f"Unsupported sample ticker: {ticker}")
    if rows < 120:
        raise ValueError("rows must be at least 120 to cover MA20 and EMA50 features.")

    profile = TICKER_PROFILES[ticker]
    rng = np.random.default_rng(int(profile["seed"]))
    dates = pd.bdate_range(start=start_date, periods=rows)
    event_positions = _event_positions(rows)

    base_drift = float(profile["drift_bps"]) / 10000.0
    volatility = float(profile["volatility"])
    start_price = float(profile["start_price"])
    base_volume = float(profile["base_volume"])

    cycle = 0.0018 * np.sin(np.linspace(0.0, 4.5 * np.pi, rows))
    regime = np.where(np.arange(rows) > rows * 0.55, 0.0009, -0.0002)
    noise = rng.normal(0.0, volatility, rows)
    returns = base_drift + cycle + regime + noise

    event_boosts = [0.015, 0.018, 0.014, 0.020]
    for index, event_position in enumerate(event_positions):
        returns[event_position] += event_boosts[min(index, len(event_boosts) - 1)]
        if event_position + 1 < rows:
            returns[event_position + 1] += 0.0035

    close = np.empty(rows, dtype=float)
    close[0] = start_price
    for idx in range(1, rows):
        close[idx] = max(close[idx - 1] * (1.0 + returns[idx]), 50.0)

    open_ = np.empty(rows, dtype=float)
    open_[0] = close[0] * (1.0 - 0.0025)
    overnight_gaps = rng.normal(0.0, 0.0035, rows)
    for idx in range(1, rows):
        open_[idx] = close[idx - 1] * (1.0 + overnight_gaps[idx])

    for index, event_position in enumerate(event_positions):
        bullish_gap = 0.002 + (0.0004 * index)
        open_[event_position] = close[event_position - 1] * (1.0 + bullish_gap)
        close[event_position] = max(close[event_position], open_[event_position] * (1.016 + 0.002 * index))

    intraday_up = rng.uniform(0.003, 0.018, rows)
    intraday_down = rng.uniform(0.003, 0.015, rows)
    high = np.maximum(open_, close) * (1.0 + intraday_up)
    low = np.minimum(open_, close) * (1.0 - intraday_down)

    weekday_pattern = np.take([0.08, 0.03, -0.02, 0.01, -0.04], dates.dayofweek)
    volume_noise = rng.normal(0.0, 0.06, rows)
    volume = base_volume * np.clip(1.0 + weekday_pattern + volume_noise, 0.55, None)

    spike_multipliers = [2.35, 2.75, 3.10, 2.55]
    for index, event_position in enumerate(event_positions):
        volume[event_position] = volume[event_position] * spike_multipliers[min(index, len(spike_multipliers) - 1)]

    frame = pd.DataFrame(
        {
            "date": dates,
            "open": np.round(open_, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "volume": np.round(volume).astype(int),
        }
    )

    return frame.reindex(columns=REQUIRED_COLUMNS)


def bootstrap_sample_dataset(
    data_dir: Path,
    rows: int = DEFAULT_ROWS,
    overwrite: bool = False,
) -> List[Path]:
    """Create sample CSV files for BBCA, BMRI, and TLKM."""

    target_dir = Path(data_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    created_files: List[Path] = []
    for ticker in TICKER_PROFILES:
        target_path = target_dir / f"{ticker}.csv"
        if target_path.exists() and not overwrite:
            print(f"Skipping existing file: {target_path}")
            created_files.append(target_path)
            continue

        frame = generate_sample_ticker_dataframe(ticker=ticker, rows=rows)
        frame.to_csv(target_path, index=False)
        print(f"Created sample dataset: {target_path} ({len(frame)} rows)")
        created_files.append(target_path)

    return created_files


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for sample data generation."""

    parser = argparse.ArgumentParser(
        description="Create realistic sample OHLCV CSV files for Phase A evaluation."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory where sample CSV files will be written. Default: data",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=DEFAULT_ROWS,
        help="Number of weekday rows to generate per ticker. Minimum: 120. Default: 140",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing BBCA/BMRI/TLKM CSV files if they already exist.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    args = parse_args(argv)

    try:
        created_files = bootstrap_sample_dataset(
            data_dir=Path(args.data_dir),
            rows=args.rows,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"Failed to bootstrap sample data: {exc}")
        return 1

    print("\nSample data bootstrap complete.")
    print(f"Total files ready: {len(created_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
