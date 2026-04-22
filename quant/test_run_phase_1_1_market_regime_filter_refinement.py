from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_1_1_market_regime_filter_refinement import (
    run_phase_1_1_market_regime_filter_refinement,
)


def _build_stock_indicator_master_frame(rows: int = 260) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    base = pd.Series(range(rows), dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": 100 + base,
            "high": 101 + base,
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
            "ticker": "AAA",
            "indicator_price_basis": "adj_close",
        }
    )


def _build_ihsg_indicator_master_frame(rows: int = 260) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    base = pd.Series(range(rows), dtype=float)
    ema200 = 7000 + (base * 0.5)
    ema50 = ema200 + 25
    adj_close = ema200 + 35

    # Below EMA200 but inside the 1% soft band.
    adj_close.iloc[120:150] = ema200.iloc[120:150] * 0.995
    # Above EMA200 but below the +1% hard buffer.
    adj_close.iloc[150:180] = ema200.iloc[150:180] * 1.004
    # Clearly bearish.
    adj_close.iloc[180:210] = ema200.iloc[180:210] * 0.97
    # Golden-cross failure while price stays above EMA200.
    ema50.iloc[210:235] = ema200.iloc[210:235] - 10
    adj_close.iloc[210:235] = ema200.iloc[210:235] * 1.003

    return pd.DataFrame(
        {
            "date": dates,
            "open": adj_close - 5,
            "high": adj_close + 5,
            "low": adj_close - 10,
            "close": adj_close,
            "adj_close": adj_close,
            "volume": 10_000_000 + base,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
            "ema20": ema50 + 10,
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
            "market_regime_bullish": adj_close > ema200,
            "indicator_price_basis": "adj_close",
        }
    )


class RunPhase11MarketRegimeFilterRefinementTestCase(unittest.TestCase):
    def test_runner_exports_variant_artifacts_and_variant_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"

            aaa = _build_stock_indicator_master_frame().copy()
            aaa["ticker"] = "AAA"
            bbb = _build_stock_indicator_master_frame().copy()
            bbb["ticker"] = "BBB"
            bbb["adj_close"] = bbb["adj_close"] + 20
            bbb["close"] = bbb["close"] + 20
            bbb["open"] = bbb["open"] + 20

            pd.concat([aaa, bbb], ignore_index=True).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame().to_csv(ihsg_file, index=False)
            pd.DataFrame(
                [{"ticker": "AAA", "sector": "finance"}, {"ticker": "BBB", "sector": "finance"}]
            ).to_csv(metadata_file, index=False)
            baseline_file.write_text(json.dumps({"default_volume_spike_threshold": 1.5}), encoding="utf-8")

            result = run_phase_1_1_market_regime_filter_refinement(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
            )

            self.assertTrue((output_dir / "phase_1_1_market_regime_filter_refinement_per_ticker.csv").exists())
            self.assertTrue((output_dir / "phase_1_1_market_regime_filter_refinement_per_variant.csv").exists())
            self.assertTrue((output_dir / "phase_1_1_market_regime_filter_refinement_summary.json").exists())
            self.assertTrue((output_dir / "phase_1_1_market_regime_filter_refinement_report.txt").exists())

            per_variant = pd.read_csv(output_dir / "phase_1_1_market_regime_filter_refinement_per_variant.csv")
            self.assertEqual(5, len(per_variant))
            self.assertEqual(
                {
                    "price_above_ema200",
                    "price_above_ema200_and_slope_up",
                    "price_above_ema200_buffer_1pct",
                    "ema50_above_ema200",
                    "soft_risk_off_near_ema200",
                },
                set(per_variant["variant_id"]),
            )

            by_variant = per_variant.set_index("variant_id")
            self.assertGreaterEqual(
                int(by_variant.loc["soft_risk_off_near_ema200", "post_filter_signals"]),
                int(by_variant.loc["price_above_ema200", "post_filter_signals"]),
            )
            self.assertLessEqual(
                int(by_variant.loc["price_above_ema200_buffer_1pct", "post_filter_signals"]),
                int(by_variant.loc["price_above_ema200", "post_filter_signals"]),
            )

            summary = result["summary"]
            self.assertIn("final_candidate_decision", summary)
            self.assertEqual(5, len(summary["variants_tested"]))

    def test_runner_raises_when_ihsg_master_is_missing_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"

            _build_stock_indicator_master_frame().to_csv(stock_file, index=False)
            pd.DataFrame([{"date": "2024-01-01", "adj_close": 7000}]).to_csv(ihsg_file, index=False)

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                run_phase_1_1_market_regime_filter_refinement(
                    stock_indicator_master_file=stock_file,
                    ihsg_indicator_master_file=ihsg_file,
                    output_dir=root / "output",
                )


if __name__ == "__main__":
    unittest.main()
