from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_1_market_regime_filter import run_phase_1_market_regime_filter


def _build_indicator_master_frame(rows: int = 260) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    base = pd.Series(range(rows), dtype=float)
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": 100 + base,
            "high": 101 + base,
            "low": 99 + base,
            "close": 100.5 + base,
            "adj_close": 100.25 + base,
            "volume": 2_000_000 + base,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
            "ema20": 90 + base,
            "ema50": 95 + base,
            "ema200": 80 + base,
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
            "ihsg_adj_close": 7000 + base,
            "ihsg_ema200": 6900 + base,
            "ihsg_regime_ready": True,
            "ihsg_regime_bullish": True,
            "market_regime_basis": "IHSG_adj_close_vs_ema200",
        }
    )
    return frame


class RunPhase1MarketRegimeFilterTestCase(unittest.TestCase):
    def test_runner_exports_before_after_artifacts_and_reduces_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            indicator_file = root / "stock_indicator_master.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"

            aaa = _build_indicator_master_frame().copy()
            aaa["ticker"] = "AAA"
            aaa.loc[100:149, "ihsg_regime_bullish"] = False

            bbb = _build_indicator_master_frame().copy()
            bbb["ticker"] = "BBB"
            bbb.loc[120:159, "ihsg_regime_bullish"] = False

            pd.concat([aaa, bbb], ignore_index=True).to_csv(indicator_file, index=False)
            pd.DataFrame(
                [{"ticker": "AAA", "sector": "finance"}, {"ticker": "BBB", "sector": "finance"}]
            ).to_csv(metadata_file, index=False)
            baseline_file.write_text(json.dumps({"default_volume_spike_threshold": 1.5}), encoding="utf-8")

            result = run_phase_1_market_regime_filter(
                indicator_master_file=indicator_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
            )

            self.assertTrue((output_dir / "phase_1_market_regime_filter_per_ticker.csv").exists())
            self.assertTrue((output_dir / "phase_1_market_regime_filter_summary.json").exists())
            per_ticker = pd.read_csv(output_dir / "phase_1_market_regime_filter_per_ticker.csv")
            self.assertTrue((per_ticker["pre_filter_signals"] >= per_ticker["post_filter_signals"]).all())
            self.assertGreater(int(per_ticker["skipped_signals"].sum()), 0)
            self.assertIn("summary", result)

    def test_runner_raises_when_indicator_master_is_missing_required_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bad_file = root / "bad.csv"
            pd.DataFrame([{"ticker": "AAA", "date": "2024-01-01"}]).to_csv(bad_file, index=False)

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                run_phase_1_market_regime_filter(
                    indicator_master_file=bad_file,
                    output_dir=root / "output",
                )
