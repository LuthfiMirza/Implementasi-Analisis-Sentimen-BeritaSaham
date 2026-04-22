from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.build_indicator_master_table import build_indicator_master_table


def _make_clean_frame(start: str, periods: int) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=periods)
    values = pd.Series(range(periods), dtype=float)
    frame = pd.DataFrame(
        {
            "date": dates.strftime("%Y-%m-%d"),
            "open": 100 + values,
            "high": 101 + values,
            "low": 99 + values,
            "close": 100.5 + values,
            "adj_close": 100.25 + values,
            "volume": 1_000_000 + values,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
        }
    )
    return frame


class BuildIndicatorMasterTableTestCase(unittest.TestCase):
    def test_build_indicator_master_table_writes_outputs_and_warmup_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stocks_dir = root / "stocks"
            output_dir = root / "indicator_master"
            artifact_dir = root / "artifacts"
            stocks_dir.mkdir()

            _make_clean_frame("2024-01-02", 260).to_csv(stocks_dir / "AAA.csv", index=False)
            _make_clean_frame("2024-01-02", 260).to_csv(stocks_dir / "BBB.csv", index=False)
            _make_clean_frame("2023-01-02", 400).to_csv(root / "IHSG.csv", index=False)

            result = build_indicator_master_table(
                stocks_dir=stocks_dir,
                ihsg_file=root / "IHSG.csv",
                output_dir=output_dir,
                artifact_dir=artifact_dir,
            )

            self.assertTrue((output_dir / "stock_indicator_master.csv").exists())
            self.assertTrue((output_dir / "IHSG_indicator_master.csv").exists())
            stock_master = pd.read_csv(output_dir / "stock_indicator_master.csv")
            ihsg_master = pd.read_csv(output_dir / "IHSG_indicator_master.csv")

            self.assertIn("ticker", stock_master.columns)
            self.assertIn("ema200", stock_master.columns)
            self.assertIn("ihsg_regime_bullish", stock_master.columns)
            self.assertIn("indicator_warmup_complete", stock_master.columns)
            self.assertTrue(ihsg_master["market_regime_ready"].astype(bool).any())
            self.assertEqual("adj_close", result["schema"]["price_policy"]["official_indicator_basis"])

            aaa = stock_master.loc[stock_master["ticker"].eq("AAA")].reset_index(drop=True)
            self.assertFalse(bool(aaa.loc[0, "ema20_ready"]))
            self.assertTrue(bool(aaa.loc[220, "indicator_warmup_complete"]))

    def test_build_indicator_master_table_rejects_duplicate_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stocks_dir = root / "stocks"
            stocks_dir.mkdir()

            frame = _make_clean_frame("2024-01-02", 30)
            duplicate = pd.concat([frame.iloc[[0]], frame], ignore_index=True)
            duplicate.to_csv(stocks_dir / "AAA.csv", index=False)
            _make_clean_frame("2023-01-02", 260).to_csv(root / "IHSG.csv", index=False)

            with self.assertRaisesRegex(ValueError, "duplicate dates"):
                build_indicator_master_table(
                    stocks_dir=stocks_dir,
                    ihsg_file=root / "IHSG.csv",
                    output_dir=root / "indicator_master",
                    artifact_dir=root / "artifacts",
                )


if __name__ == "__main__":
    unittest.main()
