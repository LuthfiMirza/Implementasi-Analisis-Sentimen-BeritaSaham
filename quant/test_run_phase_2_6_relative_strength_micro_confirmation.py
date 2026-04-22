from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_2_6_relative_strength_micro_confirmation import (
    _freeze_decision,
    _select_micro_policy,
    run_phase_2_6_relative_strength_micro_confirmation,
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


class RunPhase26RelativeStrengthMicroConfirmationTestCase(unittest.TestCase):
    def test_runner_exports_micro_confirmation_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"
            phase_2_5_summary_file = root / "phase_2_5_summary.json"

            frames = []
            tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III"]
            score_offsets = [0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01]
            for ticker, offset in zip(tickers, score_offsets):
                frame = _build_stock_indicator_master_frame().copy()
                frame["ticker"] = ticker
                frame["return_20d"] = offset
                frame["momentum_score"] = offset
                frame["applied_threshold"] = 1.5
                frame["applied_strict_mode"] = False
                frame["phase_1_signal_layer1"] = True
                frames.append(frame)

            pd.concat(frames, ignore_index=True).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame().to_csv(ihsg_file, index=False)
            pd.DataFrame([{"ticker": ticker, "sector": "finance"} for ticker in tickers]).to_csv(
                metadata_file,
                index=False,
            )
            baseline_file.write_text(json.dumps({"default_volume_spike_threshold": 1.5}), encoding="utf-8")
            phase_2_5_summary_file.write_text(
                json.dumps(
                    {
                        "selection_decision": {"selected_variant_id": "top_25pct_return_20d"},
                        "freeze_decision": {
                            "freeze_layer_2_candidate": False,
                            "remaining_blocker": "no_boundary_cut_yet_breaks_slice_concentration_blocker",
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = run_phase_2_6_relative_strength_micro_confirmation(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                phase_2_5_summary_file=phase_2_5_summary_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
                hold_period=2,
            )

            self.assertTrue((output_dir / "phase_2_6_relative_strength_micro_confirmation_per_slice.csv").exists())
            self.assertTrue((output_dir / "phase_2_6_relative_strength_micro_confirmation_per_policy.csv").exists())
            self.assertTrue((output_dir / "phase_2_6_relative_strength_micro_confirmation_summary.json").exists())
            self.assertIn("freeze_decision", result["summary"])

    def test_selection_prefers_positive_slice_robust_micro_policy(self) -> None:
        micro_df = pd.DataFrame(
            [
                {
                    "variant_id": "top_25pct_return_20d_explicit_tie_ceil_policy",
                    "variant_label": "Top 25% by return_20d with explicit tie handling and ceil cut",
                    "full_period_tickers_with_coverage_collapse": 0,
                    "full_period_sample_adequacy_risk": "low",
                    "full_period_avg_delta_average_return": 0.25,
                    "candidate_slice_win_count": 3,
                    "candidate_negative_return_slice_count": 1,
                    "candidate_low_risk_slice_count": 4,
                    "candidate_avg_delta_average_return_range": 0.70,
                    "full_period_median_trade_retention": 50.5,
                    "full_period_total_trades": 4900,
                },
                {
                    "variant_id": "top_25pct_return_20d_integer_floor_policy",
                    "variant_label": "Top 25% by return_20d with integer floor cut per date",
                    "full_period_tickers_with_coverage_collapse": 0,
                    "full_period_sample_adequacy_risk": "low",
                    "full_period_avg_delta_average_return": 0.05,
                    "candidate_slice_win_count": 2,
                    "candidate_negative_return_slice_count": 1,
                    "candidate_low_risk_slice_count": 4,
                    "candidate_avg_delta_average_return_range": 0.55,
                    "full_period_median_trade_retention": 49.0,
                    "full_period_total_trades": 4500,
                },
            ]
        )
        decision = _select_micro_policy(micro_df)
        self.assertEqual("top_25pct_return_20d_explicit_tie_ceil_policy", decision["selected_variant_id"])

    def test_final_decision_locks_not_frozen_when_threshold_not_met(self) -> None:
        micro_df = pd.DataFrame(
            [
                {
                    "variant_id": "top_25pct_return_20d_explicit_tie_ceil_policy",
                    "variant_label": "Top 25% by return_20d with explicit tie handling and ceil cut",
                    "policy_family": "explicit_tie_ceil",
                    "top_pct": 0.25,
                    "full_period_total_trades": 4889,
                    "full_period_median_trade_retention": 50.4202,
                    "full_period_avg_delta_win_rate": -0.6731,
                    "full_period_avg_delta_average_return": 0.2682,
                    "full_period_sample_adequacy_risk": "low",
                    "full_period_tickers_with_coverage_collapse": 0,
                    "slice_count_excluding_full": 6,
                    "candidate_slice_win_count": 2,
                    "candidate_positive_return_slice_count": 5,
                    "candidate_negative_return_slice_count": 1,
                    "candidate_low_risk_slice_count": 4,
                    "candidate_avg_delta_average_return_range": 0.88,
                    "candidate_avg_delta_win_rate_range": 2.5,
                    "candidate_median_trade_retention_range": 18.0,
                }
            ]
        )
        decision = _freeze_decision(
            micro_df,
            candidate_variant_id="top_25pct_return_20d_explicit_tie_ceil_policy",
        )
        self.assertFalse(decision["freeze_layer_2_candidate"])
        self.assertTrue(decision["lock_not_frozen_yet"])
        self.assertEqual(
            "micro_policy_still_does_not_break_slice_concentration_blocker",
            decision["remaining_blocker"],
        )


if __name__ == "__main__":
    unittest.main()
