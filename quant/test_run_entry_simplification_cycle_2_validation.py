from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_entry_simplification_cycle_2_validation import (
    _apply_entry_policy,
    _build_variant_registry,
    run_entry_simplification_cycle_2_validation,
)


def _build_stock_indicator_master_frame(
    *,
    ticker: str,
    rows: int,
    start: str = "2018-01-02",
    momentum_positive: bool,
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
            "return_20d": 0.04 if momentum_positive else -0.04,
            "momentum_score": 0.04 if momentum_positive else -0.04,
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
    return pd.DataFrame(
        {
            "date": dates,
            "open": 7000 + base * 0.8,
            "high": 7010 + base * 0.8,
            "low": 6990 + base * 0.8,
            "close": 7005 + base * 0.8,
            "adj_close": 7005 + base * 0.8,
            "volume": 10_000_000 + base,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
            "ema20": 6980 + base * 0.8,
            "ema50": 6990 + base * 0.8,
            "ema200": 6970 + base * 0.8,
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


class RunEntrySimplificationCycle2ValidationTestCase(unittest.TestCase):
    def test_candidate_entry_policy_is_broader_than_control(self) -> None:
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-03"]),
                "ticker": ["AAA", "BBB", "AAA", "BBB"],
                "market_regime_bullish": [True, True, True, True],
                "alt_data_ready": [True, True, True, True],
                "alt_momentum_positive": [True, False, True, False],
                "phase_1_signal_layer1": [True, True, True, True],
            }
        )
        variants = {variant.variant_id: variant for variant in _build_variant_registry()}
        control = _apply_entry_policy(frame, variants["control_phase1_layer1_plus_return20d_positive"])
        candidate = _apply_entry_policy(frame, variants["candidate_phase1_plus_layer1_only"])

        self.assertEqual(2, int(control["entry_signal"].sum()))
        self.assertEqual(4, int(candidate["entry_signal"].sum()))

    def test_runner_exports_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            stock_file = root / "stock_indicator_master.csv"
            ihsg_file = root / "IHSG_indicator_master.csv"
            metadata_file = root / "ticker_metadata.csv"
            baseline_file = root / "phase_a_baseline_final.json"

            rows = len(pd.bdate_range("2018-01-02", "2025-12-31"))
            stock_frames = []
            for ticker, momentum_positive in [
                ("AAA", True),
                ("BBB", True),
                ("CCC", True),
                ("DDD", False),
                ("EEE", False),
                ("FFF", False),
            ]:
                stock_frames.append(
                    _build_stock_indicator_master_frame(
                        ticker=ticker,
                        rows=rows,
                        momentum_positive=momentum_positive,
                    )
                )

            pd.concat(stock_frames, ignore_index=True).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame(rows=rows).to_csv(ihsg_file, index=False)
            pd.DataFrame([{"ticker": ticker, "sector": "test"} for ticker in ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]]).to_csv(
                metadata_file,
                index=False,
            )
            baseline_file.write_text(json.dumps({"default_volume_spike_threshold": 1.5}), encoding="utf-8")

            result = run_entry_simplification_cycle_2_validation(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
            )

            self.assertTrue((output_dir / "entry_simplification_cycle_2_summary.json").exists())
            self.assertTrue((output_dir / "entry_simplification_cycle_2_report.txt").exists())
            self.assertTrue((output_dir / "entry_simplification_cycle_2_closeout.json").exists())
            self.assertTrue((output_dir / "entry_simplification_cycle_2_closeout.txt").exists())
            self.assertIn("decision", result["summary"])
            self.assertIn("current_official_decision", result["closeout"])


if __name__ == "__main__":
    unittest.main()
