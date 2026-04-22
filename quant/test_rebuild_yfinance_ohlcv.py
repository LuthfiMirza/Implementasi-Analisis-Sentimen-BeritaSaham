from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.rebuild_yfinance_ohlcv import (
    CSV_COLUMNS,
    DEFAULT_SOURCE,
    _parse_series_args,
    _parse_universe_file,
    normalize_yfinance_frame,
    rebuild_series,
    validate_daily_frame,
    write_metadata,
)


def _clean_daily_frame(start: str, periods: int) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=periods)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": [100 + i for i in range(periods)],
            "High": [101 + i for i in range(periods)],
            "Low": [99 + i for i in range(periods)],
            "Close": [100.5 + i for i in range(periods)],
            "Adj Close": [100.2 + i for i in range(periods)],
            "Volume": [100000 + i for i in range(periods)],
            "Dividends": [0.0 for _ in range(periods)],
            "Stock Splits": [0.0 for _ in range(periods)],
        }
    )


class RebuildYfinanceOhlcvTestCase(unittest.TestCase):
    def test_parse_series_args_accepts_name_symbol_mappings(self) -> None:
        self.assertEqual(
            [("BBCA", "BBCA.JK"), ("IHSG", "^JKSE")],
            _parse_series_args(["BBCA=BBCA.JK", "IHSG=^JKSE"]),
        )

    def test_normalize_yfinance_frame_standardizes_expected_columns(self) -> None:
        normalized = normalize_yfinance_frame(_clean_daily_frame("2025-01-02", periods=5))

        self.assertEqual(CSV_COLUMNS[:-1], list(normalized.columns))
        self.assertEqual("2025-01-02", normalized.iloc[0]["date"])

    def test_normalize_yfinance_frame_keeps_local_trade_date_for_tz_aware_index(self) -> None:
        frame = _clean_daily_frame("2026-03-25", periods=3).copy()
        frame["Date"] = pd.DatetimeIndex(frame["Date"]).tz_localize("Asia/Jakarta")

        normalized = normalize_yfinance_frame(frame)

        self.assertEqual(["2026-03-25", "2026-03-26", "2026-03-27"], normalized["date"].tolist())

    def test_validate_daily_frame_rejects_weekend_and_gap_contamination(self) -> None:
        frame = pd.DataFrame(
            {
                "date": ["2024-01-31", "2024-02-29", "2024-03-31", "2025-01-02"],
                "open": [1, 2, 3, 4],
                "high": [1, 2, 3, 4],
                "low": [1, 2, 3, 4],
                "close": [1, 2, 3, 4],
                "adj_close": [1, 2, 3, 4],
                "volume": [1, 1, 1, 1],
                "dividends": [0, 0, 0, 0],
                "splits": [0, 0, 0, 0],
            }
        )

        issues = validate_daily_frame(frame)

        self.assertIn("weekend_rows_present", issues)
        self.assertIn("non_daily_gap_detected", issues)

    def test_parse_universe_file_only_allows_frozen_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            universe_path = Path(tmpdir) / "universe.csv"
            universe_path.write_text(
                "\n".join(
                    [
                        "ticker,yahoo_symbol,freeze_status",
                        "BBCA,BBCA.JK,candidate_pre_freeze",
                        "BBRI,BBRI.JK,frozen",
                        "TLKM,TLKM.JK,approved",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual([("BBRI", "BBRI.JK"), ("TLKM", "TLKM.JK")], _parse_universe_file(universe_path))

    def test_rebuild_series_writes_clean_csv_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            def fetcher(symbol: str, period: str) -> pd.DataFrame:
                self.assertEqual("max", period)
                self.assertEqual("BBCA.JK", symbol)
                return _clean_daily_frame("2025-01-02", periods=10)

            records = rebuild_series(
                series=[("BBCA", "BBCA.JK")],
                output_dir=output_dir,
                fetcher=fetcher,
            )
            metadata_path = write_metadata(records, output_dir)

            self.assertEqual("rebuilt", records[0].status)
            target = output_dir / "BBCA.csv"
            self.assertTrue(target.exists())
            rebuilt = pd.read_csv(target)
            self.assertEqual(CSV_COLUMNS, list(rebuilt.columns))
            self.assertTrue((rebuilt["source"] == DEFAULT_SOURCE).all())
            self.assertTrue(metadata_path.exists())


if __name__ == "__main__":
    unittest.main()
