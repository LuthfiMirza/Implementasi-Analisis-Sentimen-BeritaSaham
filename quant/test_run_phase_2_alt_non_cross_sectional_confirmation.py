from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_2_alt_non_cross_sectional_confirmation import (
    _freeze_decision,
    _pick_best_variant,
    run_phase_2_alt_non_cross_sectional_confirmation,
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
            "volume": 3_000_000 + base * 1000,
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


class RunPhase2AltNonCrossSectionalConfirmationTestCase(unittest.TestCase):
    def test_runner_exports_confirmation_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"
            prior_summary_file = root / "phase_2_alt_summary.json"

            frames = []
            tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III"]
            for idx, ticker in enumerate(tickers):
                frame = _build_stock_indicator_master_frame().copy()
                frame["ticker"] = ticker
                frame["return_20d"] = 0.04 + idx * 0.002
                frame["volume"] = 5_000_000 + idx * 200_000
                frame["volume_ma20"] = 1_500_000 + idx * 200_000
                frames.append(frame)

            pd.concat(frames, ignore_index=True).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame().to_csv(ihsg_file, index=False)
            pd.DataFrame([{"ticker": ticker, "sector": "finance"} for ticker in tickers]).to_csv(
                metadata_file,
                index=False,
            )
            baseline_file.write_text(json.dumps({"default_volume_spike_threshold": 1.5}), encoding="utf-8")
            prior_summary_file.write_text(
                json.dumps(
                    {
                        "best_variant_decision": {"selected_variant_id": "alt_filter_no_liquidity_gate"},
                        "best_liquidity_gate_decision": {"selected_variant_id": "alt_filter_liquidity_gate_5b"},
                        "usability_decision": {"layer_2_alternative_usable_as_prototype": True},
                    }
                ),
                encoding="utf-8",
            )

            result = run_phase_2_alt_non_cross_sectional_confirmation(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                phase_2_alt_summary_file=prior_summary_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
                hold_period=2,
            )

            self.assertTrue((output_dir / "phase_2_alt_non_cross_sectional_confirmation_summary.json").exists())
            self.assertTrue((output_dir / "phase_2_alt_non_cross_sectional_confirmation_report.txt").exists())
            self.assertTrue((output_dir / "phase_2_alt_non_cross_sectional_confirmation_per_slice.csv").exists())
            self.assertTrue((output_dir / "phase_2_alt_non_cross_sectional_confirmation_per_policy.csv").exists())
            self.assertIn("freeze_decision", result["summary"])

    def test_pick_best_variant_prefers_quality_positive_policy(self) -> None:
        confirmation_df = pd.DataFrame(
            [
                {
                    "variant_id": "alt_filter_no_liquidity_gate",
                    "variant_label": "No gate",
                    "full_period_tickers_with_coverage_collapse": 0,
                    "full_period_sample_adequacy_risk": "low",
                    "full_period_avg_delta_average_return": 0.04,
                    "full_period_avg_delta_win_rate": 0.3,
                    "candidate_slice_win_count": 4,
                    "full_period_median_trade_retention": 85.0,
                    "full_period_total_trades": 8500,
                },
                {
                    "variant_id": "alt_filter_liquidity_gate_5b",
                    "variant_label": "5B",
                    "full_period_tickers_with_coverage_collapse": 0,
                    "full_period_sample_adequacy_risk": "low",
                    "full_period_avg_delta_average_return": -0.01,
                    "full_period_avg_delta_win_rate": -0.2,
                    "candidate_slice_win_count": 2,
                    "full_period_median_trade_retention": 75.0,
                    "full_period_total_trades": 6900,
                },
            ]
        )
        decision = _pick_best_variant(confirmation_df)
        self.assertEqual("alt_filter_no_liquidity_gate", decision["selected_variant_id"])

    def test_freeze_decision_blocks_wide_dispersion(self) -> None:
        confirmation_df = pd.DataFrame(
            [
                {
                    "variant_id": "alt_filter_no_liquidity_gate",
                    "variant_label": "No gate",
                    "liquidity_gate_enabled": False,
                    "liquidity_threshold_value": None,
                    "liquidity_threshold_label": "none",
                    "full_period_total_trades": 8507,
                    "full_period_median_trade_retention": 85.5895,
                    "full_period_avg_delta_win_rate": 0.3924,
                    "full_period_avg_delta_average_return": 0.0455,
                    "full_period_tickers_with_coverage_collapse": 0,
                    "full_period_sample_adequacy_risk": "low",
                    "candidate_slice_win_count": 5,
                    "slice_count_excluding_full": 6,
                    "candidate_positive_return_slice_count": 5,
                    "candidate_negative_return_slice_count": 1,
                    "candidate_low_risk_slice_count": 4,
                    "candidate_avg_delta_average_return_range": 0.41,
                    "candidate_avg_delta_win_rate_range": 0.9,
                    "candidate_median_trade_retention_range": 20.0,
                }
            ]
        )
        decision = _freeze_decision(confirmation_df, candidate_variant_id="alt_filter_no_liquidity_gate")
        self.assertFalse(decision["freeze_layer_2_alternative_candidate"])
        self.assertEqual(
            "alt_candidate_slice_dispersion_still_too_wide_for_freeze",
            decision["remaining_blocker"],
        )


if __name__ == "__main__":
    unittest.main()
