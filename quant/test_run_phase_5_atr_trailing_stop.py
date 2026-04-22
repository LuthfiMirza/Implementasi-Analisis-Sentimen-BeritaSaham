from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_5_atr_trailing_stop import (
    _backtest_atr_trailing_stop,
    run_phase_5_atr_trailing_stop,
)


def _build_stock_indicator_master_frame(rows: int = 120) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=rows)
    base = pd.Series(range(rows), dtype=float)
    return pd.DataFrame(
        {
            "date": dates,
            "open": 100 + base * 0.4,
            "high": 102 + base * 0.45,
            "low": 99 + base * 0.35,
            "close": 101 + base * 0.42,
            "adj_close": 101 + base * 0.42,
            "volume": 3_000_000 + base * 1000,
            "dividends": 0.0,
            "splits": 0.0,
            "source": "test",
            "ema20": 95 + base * 0.35,
            "ema50": 96 + base * 0.34,
            "ema200": 90 + base * 0.30,
            "return_20d": 0.05,
            "momentum_score": 0.05,
            "rsi14": 60.0,
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


def _build_ihsg_indicator_master_frame(rows: int = 120) -> pd.DataFrame:
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


class RunPhase5AtrTrailingStopTestCase(unittest.TestCase):
    def test_atr_backtest_exits_with_time_stop(self) -> None:
        dates = pd.bdate_range("2024-01-02", periods=40)
        frame = pd.DataFrame(
            {
                "date": dates,
                "open": [100 + i for i in range(40)],
                "high": [101 + i for i in range(40)],
                "low": [99 + i for i in range(40)],
                "close": [100.5 + i for i in range(40)],
                "atr14": [1.0] * 40,
                "entry_signal": [False] * 40,
            }
        )
        frame.loc[10, "entry_signal"] = True
        trades = _backtest_atr_trailing_stop(frame, signal_column="entry_signal", atr_multiplier=2.5, time_stop_days=15)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["exit_reason"], "time_stop")
        self.assertEqual(int(trades.iloc[0]["holding_period_bars"]), 15)

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
                frame["rsi14"] = 52.0 + idx
                frames.append(frame)

            pd.concat(frames, ignore_index=True).to_csv(stock_file, index=False)
            _build_ihsg_indicator_master_frame().to_csv(ihsg_file, index=False)
            pd.DataFrame([{"ticker": ticker, "sector": "finance"} for ticker in tickers]).to_csv(
                metadata_file,
                index=False,
            )
            baseline_file.write_text(json.dumps({"default_volume_spike_threshold": 1.5}), encoding="utf-8")

            result = run_phase_5_atr_trailing_stop(
                stock_indicator_master_file=stock_file,
                ihsg_indicator_master_file=ihsg_file,
                output_dir=output_dir,
                baseline_config=baseline_file,
                metadata_file=metadata_file,
            )

            self.assertTrue((output_dir / "phase_5_atr_trailing_stop_summary.json").exists())
            self.assertTrue((output_dir / "phase_5_atr_trailing_stop_report.txt").exists())
            self.assertTrue((output_dir / "phase_5_atr_trailing_stop_per_ticker.csv").exists())
            self.assertTrue((output_dir / "phase_5_atr_trailing_stop_trades.csv").exists())
            self.assertIn("integration_decision", result["summary"])


if __name__ == "__main__":
    unittest.main()
