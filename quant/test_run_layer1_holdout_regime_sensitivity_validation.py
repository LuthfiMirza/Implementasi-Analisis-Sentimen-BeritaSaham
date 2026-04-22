from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_layer1_holdout_regime_sensitivity_validation import (
    _build_variant_alignment,
    _build_variant_registry,
    run_layer1_holdout_regime_sensitivity_validation,
)


def _build_stock_indicator_master_frame(
    *,
    ticker: str,
    rows: int,
    start: str = "2018-01-02",
) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=rows)
    base = pd.Series(range(rows), dtype=float)
    close_series = 100 + base * 0.12
    return pd.DataFrame(
        {
            "date": dates,
            "ticker": ticker,
            "open": 99.5 + base * 0.12,
            "high": 101 + base * 0.13,
            "low": 99 + base * 0.11,
            "close": close_series,
            "adj_close": close_series,
            "volume": 4_000_000 + base * 500,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
            "ema20": close_series - 0.8,
            "ema50": close_series - 1.0,
            "ema200": close_series - 2.0,
            "return_20d": 0.03,
            "momentum_score": 0.03,
            "rsi14": 60.0,
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


def _build_ihsg_indicator_master_frame(rows: int, start: str = "2018-01-02") -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=rows)
    base = pd.Series(range(rows), dtype=float)
    ema200 = 7000 + base * 0.12
    ema50 = ema200 + pd.Series([2.0 if idx % 10 < 5 else 15.0 for idx in range(rows)], dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": 7000 + base * 0.2,
            "high": 7010 + base * 0.2,
            "low": 6990 + base * 0.2,
            "close": 7005 + base * 0.2,
            "adj_close": 7005 + base * 0.2,
            "volume": 10_000_000 + base,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
            "ema20": ema50 + 5.0,
            "ema50": ema50,
            "ema200": ema200,
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


class RunLayer1HoldoutRegimeSensitivityValidationTestCase(unittest.TestCase):
    def test_buffer_variant_is_narrower_than_current_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ihsg_file = root / "IHSG_indicator_master.csv"
            _build_ihsg_indicator_master_frame(rows=80).to_csv(ihsg_file, index=False)
            stock_dates = pd.bdate_range("2018-01-02", periods=80).to_series(index=None)
            variants = {variant.variant_id: variant for variant in _build_variant_registry()}

            current_alignment = _build_variant_alignment(
                stock_dates.reset_index(drop=True),
                ihsg_file,
                variants["current_ema50_above_ema200"],
            )
            buffered_alignment = _build_variant_alignment(
                stock_dates.reset_index(drop=True),
                ihsg_file,
                variants["ema50_above_ema200_buffer_0p5pct"],
            )

            self.assertGreater(
                int(current_alignment["market_regime_bullish"].sum()),
                int(buffered_alignment["market_regime_bullish"].sum()),
            )

    def test_runner_exports_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"

            rows = len(pd.bdate_range("2018-01-02", "2025-12-31"))
            stock_frames = [
                _build_stock_indicator_master_frame(ticker=ticker, rows=rows)
                for ticker in ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
            ]
            pd.concat(stock_frames, ignore_index=True).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame(rows=rows).to_csv(ihsg_file, index=False)
            pd.DataFrame([{"ticker": ticker, "sector": "test"} for ticker in ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]]).to_csv(
                metadata_file,
                index=False,
            )
            baseline_file.write_text(json.dumps({"default_volume_spike_threshold": 1.5}), encoding="utf-8")

            result = run_layer1_holdout_regime_sensitivity_validation(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
            )

            self.assertTrue((output_dir / "layer1_holdout_regime_sensitivity_summary.json").exists())
            self.assertTrue((output_dir / "layer1_holdout_regime_sensitivity_report.txt").exists())
            self.assertTrue((output_dir / "layer1_holdout_regime_sensitivity_closeout.json").exists())
            self.assertTrue((output_dir / "layer1_holdout_regime_sensitivity_closeout.txt").exists())
            self.assertIn("decision", result["summary"])
            self.assertIn("current_official_decision", result["closeout"])


if __name__ == "__main__":
    unittest.main()
