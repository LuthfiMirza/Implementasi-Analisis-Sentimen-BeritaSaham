from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_2_4_relative_strength_robustness import (
    _freeze_decision,
    run_phase_2_4_relative_strength_robustness,
)


def _build_stock_indicator_master_frame(rows: int = 90) -> pd.DataFrame:
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


def _build_ihsg_indicator_master_frame(rows: int = 90) -> pd.DataFrame:
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


class RunPhase24RelativeStrengthRobustnessTestCase(unittest.TestCase):
    def test_runner_exports_slice_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"
            phase_2_3_summary_file = root / "phase_2_3_summary.json"

            frames = []
            tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III"]
            score_offsets = [0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01]
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
            phase_2_3_summary_file.write_text(
                json.dumps(
                    {
                        "freeze_decision": {
                            "candidate_still_best": True,
                            "freeze_layer_2_candidate": False,
                            "remaining_blocker": "narrow_sensitivity_between_nearby_rs_cuts_and_quality_tradeoff_not_decisive_enough",
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = run_phase_2_4_relative_strength_robustness(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                phase_2_3_summary_file=phase_2_3_summary_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
                hold_period=2,
            )

            self.assertTrue((output_dir / "phase_2_4_relative_strength_robustness_per_slice.csv").exists())
            self.assertTrue((output_dir / "phase_2_4_relative_strength_robustness_summary.json").exists())
            self.assertIn("freeze_decision", result["summary"])

            per_slice = pd.read_csv(output_dir / "phase_2_4_relative_strength_robustness_per_slice.csv")
            self.assertIn("full_period", per_slice["slice_id"].tolist())
            self.assertIn("top_25pct_return_20d", per_slice["variant_id"].tolist())

    def test_freeze_decision_flags_specific_slice_blocker(self) -> None:
        slice_variant_df = pd.DataFrame(
            [
                {"slice_id": "full_period", "variant_id": "top_25pct_return_20d", "tickers_with_coverage_collapse": 0, "sample_adequacy_risk": "low", "avg_delta_average_return": 0.1, "median_trade_retention": 55.0},
                {"slice_id": "time_early", "variant_id": "top_25pct_return_20d", "avg_delta_average_return": 0.12, "avg_delta_win_rate": -0.2, "median_trade_retention": 60.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
                {"slice_id": "time_mid", "variant_id": "top_25pct_return_20d", "avg_delta_average_return": -0.09, "avg_delta_win_rate": -1.1, "median_trade_retention": 48.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
                {"slice_id": "time_late", "variant_id": "top_25pct_return_20d", "avg_delta_average_return": 0.11, "avg_delta_win_rate": -0.3, "median_trade_retention": 53.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
                {"slice_id": "regime_low_strength", "variant_id": "top_25pct_return_20d", "avg_delta_average_return": 0.08, "avg_delta_win_rate": -0.2, "median_trade_retention": 51.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
                {"slice_id": "regime_mid_strength", "variant_id": "top_25pct_return_20d", "avg_delta_average_return": 0.07, "avg_delta_win_rate": -0.2, "median_trade_retention": 52.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
                {"slice_id": "regime_high_strength", "variant_id": "top_25pct_return_20d", "avg_delta_average_return": 0.06, "avg_delta_win_rate": -0.1, "median_trade_retention": 54.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
                {"slice_id": "time_early", "variant_id": "top_30pct_return_20d", "avg_delta_average_return": 0.02, "avg_delta_win_rate": -0.4, "median_trade_retention": 61.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
                {"slice_id": "time_mid", "variant_id": "top_30pct_return_20d", "avg_delta_average_return": 0.01, "avg_delta_win_rate": -0.3, "median_trade_retention": 57.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
                {"slice_id": "time_late", "variant_id": "top_30pct_return_20d", "avg_delta_average_return": 0.01, "avg_delta_win_rate": -0.2, "median_trade_retention": 56.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
                {"slice_id": "regime_low_strength", "variant_id": "top_30pct_return_20d", "avg_delta_average_return": 0.01, "avg_delta_win_rate": -0.2, "median_trade_retention": 53.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
                {"slice_id": "regime_mid_strength", "variant_id": "top_30pct_return_20d", "avg_delta_average_return": 0.01, "avg_delta_win_rate": -0.2, "median_trade_retention": 53.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
                {"slice_id": "regime_high_strength", "variant_id": "top_30pct_return_20d", "avg_delta_average_return": 0.01, "avg_delta_win_rate": -0.2, "median_trade_retention": 53.0, "sample_adequacy_risk": "low", "tickers_with_coverage_collapse": 0},
            ]
        )
        decision = _freeze_decision(slice_variant_df, candidate_variant_id="top_25pct_return_20d")
        self.assertFalse(decision["freeze_layer_2_candidate"])
        self.assertEqual(
            "candidate_turns_materially_negative_in_specific_time_or_regime_slice",
            decision["remaining_blocker"],
        )


if __name__ == "__main__":
    unittest.main()
