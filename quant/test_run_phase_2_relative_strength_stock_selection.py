from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_2_relative_strength_stock_selection import (
    run_phase_2_relative_strength_stock_selection,
)


def _build_stock_indicator_master_frame(rows: int = 40) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    base = pd.Series(range(rows), dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": 100 + base,
            "high": 102 + base,
            "low": 99 + base,
            "close": 101 + base,
            "adj_close": 101 + base,
            "volume": 2_000_000 + base,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
            "ema20": 95 + base,
            "ema50": 96 + base,
            "ema200": 90 + base,
            "return_20d": 0.05,
            "momentum_score": 0.05,
            "rsi14": 55.0,
            "volume_ma20": 1_000_000.0,
            "ema20_ready": True,
            "ema50_ready": True,
            "ema200_ready": True,
            "return_20d_ready": True,
            "momentum_score_ready": True,
            "rsi14_ready": True,
            "volume_ma20_ready": True,
            "indicator_warmup_complete": True,
            "indicator_price_basis": "adj_close",
        }
    )


def _build_ihsg_indicator_master_frame(rows: int = 40) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    base = pd.Series(range(rows), dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": 7000 + base,
            "high": 7010 + base,
            "low": 6990 + base,
            "close": 7005 + base,
            "adj_close": 7005 + base,
            "volume": 10_000_000 + base,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
            "ema20": 6980 + base,
            "ema50": 6995 + base,
            "ema200": 6985 + base,
            "return_20d": 0.02,
            "momentum_score": 0.02,
            "rsi14": 55.0,
            "volume_ma20": 5_000_000.0,
            "ema20_ready": True,
            "ema50_ready": True,
            "ema200_ready": True,
            "return_20d_ready": True,
            "momentum_score_ready": True,
            "rsi14_ready": True,
            "volume_ma20_ready": True,
            "indicator_warmup_complete": True,
            "market_regime_ready": True,
            "market_regime_bullish": True,
            "indicator_price_basis": "adj_close",
        }
    )


class RunPhase2RelativeStrengthStockSelectionTestCase(unittest.TestCase):
    def test_runner_exports_variant_artifacts_and_selection_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"

            frames = []
            tickers = ["AAA", "BBB", "CCC", "DDD"]
            score_offsets = [0.04, 0.03, 0.02, 0.01]
            for ticker, offset in zip(tickers, score_offsets):
                frame = _build_stock_indicator_master_frame().copy()
                frame["ticker"] = ticker
                frame["return_20d"] = offset
                frame["momentum_score"] = offset
                frames.append(frame)

            pd.concat(frames, ignore_index=True).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame().to_csv(ihsg_file, index=False)
            pd.DataFrame([{"ticker": ticker, "sector": "finance"} for ticker in tickers]).to_csv(
                metadata_file,
                index=False,
            )
            baseline_file.write_text(json.dumps({"default_volume_spike_threshold": 1.5}), encoding="utf-8")

            result = run_phase_2_relative_strength_stock_selection(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
                hold_period=2,
            )

            self.assertTrue((output_dir / "phase_2_relative_strength_selection_per_variant.csv").exists())
            self.assertTrue((output_dir / "phase_2_relative_strength_selection_summary.json").exists())
            self.assertTrue((output_dir / "phase_2_relative_strength_selection_active_universe_by_date.csv").exists())

            per_variant = pd.read_csv(output_dir / "phase_2_relative_strength_selection_per_variant.csv")
            self.assertEqual(3, len(per_variant))
            by_variant = per_variant.set_index("variant_id")
            self.assertGreater(
                int(by_variant.loc["layer1_full_universe", "total_signals"]),
                int(by_variant.loc["top_30pct_return_20d", "total_signals"]),
            )
            self.assertGreater(
                int(by_variant.loc["top_30pct_return_20d", "total_signals"]),
                int(by_variant.loc["top_25pct_return_20d", "total_signals"]),
            )
            self.assertEqual(
                float(by_variant.loc["top_25pct_return_20d", "active_ticker_count_median"]),
                1.0,
            )
            self.assertEqual(
                float(by_variant.loc["top_30pct_return_20d", "active_ticker_count_median"]),
                2.0,
            )

            self.assertIn("best_variant_decision", result["summary"])

    def test_runner_raises_when_stock_master_missing_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"

            pd.DataFrame([{"ticker": "AAA", "date": "2024-01-01"}]).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame().to_csv(ihsg_file, index=False)

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                run_phase_2_relative_strength_stock_selection(
                    stock_indicator_master_file=stock_file,
                    ihsg_indicator_master_file=ihsg_file,
                    output_dir=root / "output",
                )


if __name__ == "__main__":
    unittest.main()
