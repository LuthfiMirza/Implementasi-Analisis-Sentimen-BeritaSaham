from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_2_5_relative_strength_boundary_refinement import (
    _freeze_decision,
    _select_boundary_cut,
    run_phase_2_5_relative_strength_boundary_refinement,
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


class RunPhase25RelativeStrengthBoundaryRefinementTestCase(unittest.TestCase):
    def test_runner_exports_boundary_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"
            phase_2_4_summary_file = root / "phase_2_4_summary.json"

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
            phase_2_4_summary_file.write_text(
                json.dumps(
                    {
                        "freeze_decision": {
                            "candidate_variant_id": "top_25pct_return_20d",
                            "freeze_layer_2_candidate": False,
                            "remaining_blocker": "candidate_advantage_is_concentrated_in_too_few_time_or_regime_slices",
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = run_phase_2_5_relative_strength_boundary_refinement(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                phase_2_4_summary_file=phase_2_4_summary_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
                hold_period=2,
            )

            self.assertTrue((output_dir / "phase_2_5_relative_strength_boundary_refinement_per_slice.csv").exists())
            self.assertTrue((output_dir / "phase_2_5_relative_strength_boundary_refinement_per_cut.csv").exists())
            self.assertTrue((output_dir / "phase_2_5_relative_strength_boundary_refinement_summary.json").exists())
            self.assertIn("freeze_decision", result["summary"])

            per_cut = pd.read_csv(output_dir / "phase_2_5_relative_strength_boundary_refinement_per_cut.csv")
            self.assertIn("top_25pct_return_20d", per_cut["variant_id"].tolist())
            self.assertIn("candidate_slice_win_count", per_cut.columns.tolist())

    def test_boundary_selection_prefers_more_robust_positive_cut(self) -> None:
        boundary_df = pd.DataFrame(
            [
                {
                    "variant_id": "top_22_5pct_return_20d",
                    "variant_label": "Top 22.5% by return_20d",
                    "full_period_tickers_with_coverage_collapse": 0,
                    "full_period_sample_adequacy_risk": "low",
                    "full_period_avg_delta_average_return": 0.10,
                    "candidate_slice_win_count": 2,
                    "candidate_negative_return_slice_count": 1,
                    "candidate_low_risk_slice_count": 4,
                    "candidate_avg_delta_average_return_range": 0.40,
                    "full_period_median_trade_retention": 51.0,
                    "full_period_total_trades": 4300,
                },
                {
                    "variant_id": "top_27_5pct_return_20d",
                    "variant_label": "Top 27.5% by return_20d",
                    "full_period_tickers_with_coverage_collapse": 0,
                    "full_period_sample_adequacy_risk": "low",
                    "full_period_avg_delta_average_return": 0.08,
                    "candidate_slice_win_count": 4,
                    "candidate_negative_return_slice_count": 1,
                    "candidate_low_risk_slice_count": 5,
                    "candidate_avg_delta_average_return_range": 0.28,
                    "full_period_median_trade_retention": 54.0,
                    "full_period_total_trades": 4700,
                },
            ]
        )
        decision = _select_boundary_cut(boundary_df)
        self.assertEqual("top_27_5pct_return_20d", decision["selected_variant_id"])

    def test_freeze_decision_blocks_wide_dispersion(self) -> None:
        boundary_df = pd.DataFrame(
            [
                {
                    "variant_id": "top_25pct_return_20d",
                    "variant_label": "Top 25% by return_20d",
                    "top_pct": 0.25,
                    "full_period_total_trades": 4889,
                    "full_period_median_trade_retention": 50.4202,
                    "full_period_avg_delta_win_rate": -0.6731,
                    "full_period_avg_delta_average_return": 0.2682,
                    "full_period_sample_adequacy_risk": "low",
                    "full_period_tickers_with_coverage_collapse": 0,
                    "slice_count_excluding_full": 6,
                    "candidate_slice_win_count": 4,
                    "candidate_positive_return_slice_count": 5,
                    "candidate_negative_return_slice_count": 1,
                    "candidate_low_risk_slice_count": 4,
                    "candidate_avg_delta_average_return_range": 0.91,
                    "candidate_avg_delta_win_rate_range": 1.2,
                    "candidate_median_trade_retention_range": 8.0,
                }
            ]
        )
        decision = _freeze_decision(boundary_df, candidate_variant_id="top_25pct_return_20d")
        self.assertFalse(decision["freeze_layer_2_candidate"])
        self.assertEqual(
            "best_boundary_cut_still_has_too_wide_slice_quality_dispersion",
            decision["remaining_blocker"],
        )


if __name__ == "__main__":
    unittest.main()
