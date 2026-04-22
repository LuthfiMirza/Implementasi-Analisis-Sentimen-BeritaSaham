from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_2_alt_non_cross_sectional_filter import (
    _pick_best_liquidity_gate_variant,
    _pick_best_variant,
    _usability_decision,
    run_phase_2_alt_non_cross_sectional_filter,
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


class RunPhase2AltNonCrossSectionalFilterTestCase(unittest.TestCase):
    def test_runner_exports_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"

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

            result = run_phase_2_alt_non_cross_sectional_filter(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
                hold_period=2,
            )

            self.assertTrue((output_dir / "phase_2_alt_non_cross_sectional_filter_summary.json").exists())
            self.assertTrue((output_dir / "phase_2_alt_non_cross_sectional_filter_report.txt").exists())
            self.assertTrue((output_dir / "phase_2_alt_non_cross_sectional_filter_per_ticker.csv").exists())
            self.assertTrue((output_dir / "phase_2_alt_non_cross_sectional_filter_active_by_date.csv").exists())
            self.assertIn("variant_results", result["summary"])

    def test_pick_best_liquidity_gate_variant(self) -> None:
        variant_df = pd.DataFrame(
            [
                {
                    "variant_id": "alt_filter_liquidity_gate_5b",
                    "variant_label": "5B",
                    "liquidity_gate_enabled": True,
                    "tickers_with_coverage_collapse": 0,
                    "avg_delta_average_return": 0.05,
                    "avg_delta_win_rate": -0.3,
                    "median_trade_retention": 60.0,
                    "total_trades": 3000,
                    "liquidity_threshold_label": ">= 5B IDR",
                },
                {
                    "variant_id": "alt_filter_liquidity_gate_10b",
                    "variant_label": "10B",
                    "liquidity_gate_enabled": True,
                    "tickers_with_coverage_collapse": 0,
                    "avg_delta_average_return": 0.09,
                    "avg_delta_win_rate": -0.2,
                    "median_trade_retention": 58.0,
                    "total_trades": 2800,
                    "liquidity_threshold_label": ">= 10B IDR",
                },
            ]
        )
        decision = _pick_best_liquidity_gate_variant(variant_df)
        self.assertEqual("alt_filter_liquidity_gate_10b", decision["selected_variant_id"])

    def test_usability_decision_flags_positive_variant(self) -> None:
        variant_df = pd.DataFrame(
            [
                {
                    "variant_id": "layer1_full_universe",
                    "tickers_with_coverage_collapse": 0,
                    "sample_adequacy_risk": "low",
                    "avg_delta_average_return": 0.0,
                    "avg_delta_win_rate": 0.0,
                },
                {
                    "variant_id": "alt_filter_no_liquidity_gate",
                    "tickers_with_coverage_collapse": 0,
                    "sample_adequacy_risk": "low",
                    "avg_delta_average_return": 0.08,
                    "avg_delta_win_rate": -0.2,
                },
            ]
        )
        best_variant = _pick_best_variant(
            pd.DataFrame(
                [
                    {
                        "variant_id": "layer1_full_universe",
                        "variant_label": "Layer 1",
                        "tickers_with_coverage_collapse": 0,
                        "avg_delta_average_return": 0.0,
                        "avg_delta_win_rate": 0.0,
                        "median_trade_retention": 100.0,
                        "total_trades": 4000,
                    },
                    {
                        "variant_id": "alt_filter_no_liquidity_gate",
                        "variant_label": "Alt",
                        "tickers_with_coverage_collapse": 0,
                        "avg_delta_average_return": 0.08,
                        "avg_delta_win_rate": -0.2,
                        "median_trade_retention": 70.0,
                        "total_trades": 2500,
                    },
                ]
            )
        )
        decision = _usability_decision(variant_df, best_variant)
        self.assertTrue(decision["layer_2_alternative_usable_as_prototype"])


if __name__ == "__main__":
    unittest.main()
