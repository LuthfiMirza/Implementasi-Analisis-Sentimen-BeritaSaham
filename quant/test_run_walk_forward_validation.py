from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_walk_forward_validation import run_walk_forward_validation


def _build_stock_indicator_master_frame(
    *,
    ticker: str,
    rows: int,
    start: str = "2018-01-02",
    layer3_active: bool = True,
) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=rows)
    base = pd.Series(range(rows), dtype=float)
    frame = pd.DataFrame(
        {
            "date": dates,
            "ticker": ticker,
            "open": 100 + base * 0.15,
            "high": 101 + base * 0.17,
            "low": 99 + base * 0.13,
            "close": 100.5 + base * 0.16,
            "adj_close": 100.5 + base * 0.16,
            "volume": 4_000_000 + base * 500,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
            "ema20": 98 + base * 0.14,
            "ema50": 97 + base * 0.13,
            "ema200": 95 + base * 0.11,
            "return_20d": 0.04,
            "momentum_score": 0.04,
            "rsi14": 60.0 if layer3_active else 75.0,
            "volume_ma20": 1_500_000.0,
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
    return frame


def _build_ihsg_indicator_master_frame(rows: int, start: str = "2018-01-02") -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=rows)
    base = pd.Series(range(rows), dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": 7000 + base * 0.8,
            "high": 7010 + base * 0.8,
            "low": 6990 + base * 0.8,
            "close": 7005 + base * 0.8,
            "adj_close": 7005 + base * 0.8,
            "volume": 10_000_000 + base,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
            "ema20": 6980 + base * 0.8,
            "ema50": 6990 + base * 0.8,
            "ema200": 6970 + base * 0.8,
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


class RunWalkForwardValidationTestCase(unittest.TestCase):
    def test_runner_exports_walk_forward_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"

            rows = len(pd.bdate_range("2018-01-02", "2025-12-31"))
            stock_frames = []
            for ticker, layer3_active in [
                ("AAA", True),
                ("BBB", True),
                ("CCC", True),
                ("DDD", False),
                ("EEE", False),
                ("FFF", False),
            ]:
                stock_frames.append(
                    _build_stock_indicator_master_frame(
                        ticker=ticker,
                        rows=rows,
                        layer3_active=layer3_active,
                    )
                )

            pd.concat(stock_frames, ignore_index=True).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame(rows=rows).to_csv(ihsg_file, index=False)
            pd.DataFrame([{"ticker": ticker, "sector": "test"} for ticker in ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]]).to_csv(
                metadata_file,
                index=False,
            )
            baseline_file.write_text(json.dumps({"default_volume_spike_threshold": 1.5}), encoding="utf-8")

            result = run_walk_forward_validation(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
            )

            self.assertTrue((output_dir / "walk_forward_validation_summary.json").exists())
            self.assertTrue((output_dir / "walk_forward_validation_report.txt").exists())
            self.assertIn("official_decision", result["summary"])
            self.assertEqual(2, len(result["summary"]["stack_results"]))
            self.assertEqual(3, len(result["summary"]["walk_forward_windows"]))

            stack_lookup = {item["stack_id"]: item for item in result["summary"]["stack_results"]}
            self.assertIn("rebuild_core_without_layer3", stack_lookup)
            self.assertIn("rebuild_core_with_layer3_optional_toggle", stack_lookup)
            self.assertEqual(3, len(stack_lookup["rebuild_core_without_layer3"]["window_results"]))
            self.assertEqual(
                "not_ready",
                result["summary"]["official_decision"]["paper_trading_candidate_track"]["decision"],
            )


if __name__ == "__main__":
    unittest.main()
