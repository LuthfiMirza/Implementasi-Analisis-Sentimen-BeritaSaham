from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from quant.run_phase_2_1_relative_strength_redesign import (
    run_phase_2_1_relative_strength_redesign,
)


def _build_ihsg_indicator_master_frame(rows: int = 60) -> pd.DataFrame:
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


def _build_ticker_frame(ticker: str, daily_returns: np.ndarray) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=len(daily_returns))
    price = 100.0
    prices = []
    for r in daily_returns:
        price *= 1.0 + float(r)
        prices.append(price)
    adj_close = pd.Series(prices)
    return_20d = adj_close.pct_change(periods=20)
    base = pd.Series(range(len(daily_returns)), dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": adj_close - 0.25,
            "high": adj_close + 0.5,
            "low": adj_close - 0.75,
            "close": adj_close,
            "adj_close": adj_close,
            "volume": 2_000_000 + base,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
            "ema20": adj_close - 1.5,
            "ema50": adj_close - 1.0,
            "ema200": adj_close - 2.0,
            "return_20d": return_20d,
            "momentum_score": return_20d,
            "rsi14": 55.0,
            "volume_ma20": 1_000_000.0,
            "ema20_ready": True,
            "ema50_ready": True,
            "ema200_ready": True,
            "return_20d_ready": return_20d.notna(),
            "momentum_score_ready": return_20d.notna(),
            "rsi14_ready": True,
            "volume_ma20_ready": True,
            "indicator_warmup_complete": True,
            "ticker": ticker,
            "indicator_price_basis": "adj_close",
        }
    )


class RunPhase21RelativeStrengthRedesignTestCase(unittest.TestCase):
    def test_runner_exports_redesign_artifacts_and_variant_relationships(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            phase2_summary_file = output_dir / "phase_2_relative_strength_selection_summary.json"
            phase2_per_ticker_file = output_dir / "phase_2_relative_strength_selection_per_ticker.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"
            output_dir.mkdir(parents=True, exist_ok=True)

            rows = 60
            ticker_frames = [
                _build_ticker_frame("AAA", np.full(rows, 0.004)),
                _build_ticker_frame("BBB", np.tile([0.007, 0.001, 0.005, -0.001], rows // 4 + 1)[:rows]),
                _build_ticker_frame("CCC", np.tile([0.018, -0.012, 0.02, -0.01], rows // 4 + 1)[:rows]),
                _build_ticker_frame("DDD", np.full(rows, 0.0015)),
                _build_ticker_frame("EEE", np.full(rows, -0.002)),
            ]
            pd.concat(ticker_frames, ignore_index=True).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame(rows=rows).to_csv(ihsg_file, index=False)

            phase2_summary_file.write_text(
                json.dumps(
                    {
                        "variant_results": [
                            {
                                "variant_id": "top_25pct_return_20d",
                                "active_ticker_count_median": 2.0,
                                "total_trades": 200,
                                "median_trade_retention": 50.0,
                                "avg_delta_win_rate": -2.0,
                                "avg_delta_average_return": -0.1,
                            },
                            {
                                "variant_id": "top_30pct_return_20d",
                                "active_ticker_count_median": 2.0,
                                "total_trades": 220,
                                "median_trade_retention": 55.0,
                                "avg_delta_win_rate": -1.5,
                                "avg_delta_average_return": -0.08,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                [
                    {
                        "variant_id": "top_25pct_return_20d",
                        "ticker": "AAA",
                        "trade_retention_pct": 50.0,
                        "delta_win_rate": -2.0,
                        "delta_average_return": -0.1,
                    },
                    {
                        "variant_id": "top_30pct_return_20d",
                        "ticker": "BBB",
                        "trade_retention_pct": 55.0,
                        "delta_win_rate": -1.5,
                        "delta_average_return": -0.08,
                    },
                ]
            ).to_csv(phase2_per_ticker_file, index=False)
            pd.DataFrame(
                [{"ticker": ticker, "sector": "finance"} for ticker in ["AAA", "BBB", "CCC", "DDD", "EEE"]]
            ).to_csv(metadata_file, index=False)
            baseline_file.write_text(json.dumps({"default_volume_spike_threshold": 1.5}), encoding="utf-8")

            result = run_phase_2_1_relative_strength_redesign(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                phase_2_summary_file=phase2_summary_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
                hold_period=2,
            )

            self.assertTrue((output_dir / "phase_2_1_relative_strength_redesign_per_variant.csv").exists())
            self.assertTrue((output_dir / "phase_2_1_relative_strength_redesign_summary.json").exists())
            self.assertTrue((output_dir / "phase_2_1_relative_strength_redesign_active_universe_by_date.csv").exists())

            per_variant = pd.read_csv(output_dir / "phase_2_1_relative_strength_redesign_per_variant.csv")
            self.assertEqual(5, len(per_variant))
            by_variant = per_variant.set_index("variant_id")
            self.assertEqual(float(by_variant.loc["top_40pct_return_20d", "active_ticker_count_median"]), 2.0)
            self.assertEqual(float(by_variant.loc["top_50pct_return_20d", "active_ticker_count_median"]), 3.0)
            self.assertEqual(float(by_variant.loc["above_median_return_20d", "active_ticker_count_median"]), 2.0)
            self.assertEqual(
                float(by_variant.loc["top_50pct_vol_adjusted_return_20d", "active_ticker_count_median"]),
                3.0,
            )
            self.assertGreater(
                int(by_variant.loc["top_50pct_return_20d", "total_signals"]),
                int(by_variant.loc["top_40pct_return_20d", "total_signals"]),
            )

            self.assertIn("formal_decision", result["summary"])
            self.assertIn(result["summary"]["formal_decision"]["decision_code"], {
                "layer_2_candidate_identified",
                "universe_too_small_for_relative_strength_validation",
            })

    def test_runner_handles_missing_phase2_per_ticker_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            phase2_summary_file = output_dir / "phase_2_relative_strength_selection_summary.json"
            output_dir.mkdir(parents=True, exist_ok=True)

            pd.concat(
                [
                    _build_ticker_frame("AAA", np.full(60, 0.004)),
                    _build_ticker_frame("BBB", np.full(60, 0.003)),
                ],
                ignore_index=True,
            ).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame(rows=60).to_csv(ihsg_file, index=False)
            phase2_summary_file.write_text(json.dumps({"variant_results": []}), encoding="utf-8")

            result = run_phase_2_1_relative_strength_redesign(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                phase_2_summary_file=phase2_summary_file,
                output_dir=output_dir,
            )

            self.assertIn("phase_2_failure_audit", result["summary"])
            self.assertEqual(
                [],
                result["summary"]["phase_2_failure_audit"]["worst_ticker_drags"]["top_25pct_return_20d"],
            )


if __name__ == "__main__":
    unittest.main()
