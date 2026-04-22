from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_1_2_market_regime_alignment_confirmation import (
    run_phase_1_2_market_regime_alignment_confirmation,
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


def _build_ihsg_indicator_master_frame() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=40)
    base = pd.Series(range(40), dtype=float)
    frame = pd.DataFrame(
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
            "ema50": 6990 + base,
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

    # Remove two stock dates to create direct-date alignment gaps.
    return frame.drop(index=[5, 12]).reset_index(drop=True)


class RunPhase12MarketRegimeAlignmentConfirmationTestCase(unittest.TestCase):
    def test_runner_exports_policy_artifacts_and_policy_relationships(self) -> None:
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
            bbb["adj_close"] = bbb["adj_close"] + 10
            bbb["close"] = bbb["close"] + 10
            bbb["open"] = bbb["open"] + 10

            pd.concat([aaa, bbb], ignore_index=True).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame().to_csv(ihsg_file, index=False)
            pd.DataFrame(
                [{"ticker": "AAA", "sector": "finance"}, {"ticker": "BBB", "sector": "finance"}]
            ).to_csv(metadata_file, index=False)
            baseline_file.write_text(json.dumps({"default_volume_spike_threshold": 1.5}), encoding="utf-8")

            result = run_phase_1_2_market_regime_alignment_confirmation(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
                hold_period=2,
            )

            self.assertTrue((output_dir / "phase_1_2_market_regime_alignment_confirmation_per_policy.csv").exists())
            self.assertTrue((output_dir / "phase_1_2_market_regime_alignment_confirmation_summary.json").exists())

            per_policy = pd.read_csv(output_dir / "phase_1_2_market_regime_alignment_confirmation_per_policy.csv")
            self.assertEqual(3, len(per_policy))

            by_policy = per_policy.set_index("policy_id")
            self.assertLess(
                int(by_policy.loc["current_non_bullish_on_missing", "post_filter_signals"]),
                int(by_policy.loc["carry_forward_previous_available_regime", "post_filter_signals"]),
            )
            self.assertEqual(
                int(by_policy.loc["carry_forward_previous_available_regime", "post_filter_signals"]),
                int(by_policy.loc["explicit_previous_trading_day_alignment", "post_filter_signals"]),
            )
            self.assertEqual(
                int(by_policy.loc["carry_forward_previous_available_regime", "post_filter_total_trades"]),
                int(by_policy.loc["explicit_previous_trading_day_alignment", "post_filter_total_trades"]),
            )
            self.assertEqual(
                int(by_policy.loc["current_non_bullish_on_missing", "affected_missing_date_rows"]),
                4,
            )

            self.assertIn("freeze_decision", result["summary"])

    def test_runner_raises_when_ihsg_master_is_missing_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"

            _build_stock_indicator_master_frame().assign(ticker="AAA").to_csv(stock_file, index=False)
            pd.DataFrame([{"date": "2024-01-01", "adj_close": 7000}]).to_csv(ihsg_file, index=False)

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                run_phase_1_2_market_regime_alignment_confirmation(
                    stock_indicator_master_file=stock_file,
                    ihsg_indicator_master_file=ihsg_file,
                    output_dir=root / "output",
                )


if __name__ == "__main__":
    unittest.main()
