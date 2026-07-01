from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.trading_research.walk_forward_event_dataset import (
    EventDatasetConfig,
    build_and_write_event_dataset,
    build_event_dataset,
    load_ohlcv,
    validate_event_dataset,
    write_event_dataset,
)

def _ohlcv() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=30)
    values = pd.Series(range(30), dtype=float)
    return pd.DataFrame({
        "date": dates,
        "open": 100 + values,
        "high": 103 + values,
        "low": 98 + values,
        "close": 101 + values,
        "volume": 1_000_000 + (values * 10_000),
        "sentiment_weighted_1d": 0.1,
    })

def _predictions() -> pd.DataFrame:
    return pd.DataFrame({
        "date": ["2024-01-03", "2024-01-10", "2024-01-17"],
        "ticker": ["BUMI", "BUMI", "BUMI"],
        "signal": ["BUY", "WAIT", "BUY"],
        "prediction_probability": [0.72, 0.2, 0.61],
        "prediction_variant": ["technical", "technical", "technical"],
    }).assign(date=lambda frame: pd.to_datetime(frame["date"]))

class WalkForwardEventDatasetTestCase(unittest.TestCase):
    def test_builds_valid_dataset_from_buy_signals(self) -> None:
        artifact = build_event_dataset(_ohlcv(), _predictions(), EventDatasetConfig(ticker="BUMI", holding_days=5))

        self.assertEqual("walk_forward_event_dataset_v1", artifact["schema_version"])
        self.assertEqual("BUMI", artifact["ticker"])
        self.assertEqual(2, len(artifact["events"]))
        self.assertEqual("2024-01-03", artifact["events"][0]["entry_date"])
        self.assertIn(artifact["events"][0]["trade_outcome"], ["win", "loss"])
        validate_event_dataset(artifact)

    def test_validator_rejects_duplicate_event(self) -> None:
        artifact = build_event_dataset(_ohlcv(), _predictions(), EventDatasetConfig(ticker="BUMI", holding_days=5))
        artifact["events"].append(dict(artifact["events"][0]))

        with self.assertRaisesRegex(ValueError, "duplicate event"):
            validate_event_dataset(artifact)

    def test_validator_rejects_missing_ohlcv_event(self) -> None:
        artifact = build_event_dataset(_ohlcv(), _predictions(), EventDatasetConfig(ticker="BUMI", holding_days=5))
        artifact["events"][0]["entry_price"] = None

        with self.assertRaisesRegex(ValueError, "missing OHLCV"):
            validate_event_dataset(artifact)

    def test_validator_rejects_invalid_schema(self) -> None:
        artifact = build_event_dataset(_ohlcv(), _predictions(), EventDatasetConfig(ticker="BUMI", holding_days=5))
        artifact["schema_version"] = "bad_v1"

        with self.assertRaisesRegex(ValueError, "invalid schema version"):
            validate_event_dataset(artifact)

    def test_writes_output_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = build_event_dataset(_ohlcv(), _predictions(), EventDatasetConfig(ticker="BUMI", holding_days=5))
            output = write_event_dataset(artifact, Path(tmpdir))

            self.assertEqual("BUMI_events_v1.json", output.name)
            payload = json.loads(output.read_text())
            self.assertEqual("walk_forward_event_dataset", payload["artifact_type"])
            self.assertEqual(2, payload["quality"]["event_count"])

    def test_cli_builder_reads_files_and_writes_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ohlcv_path = root / "BUMI.csv"
            prediction_path = root / "predictions.csv"
            _ohlcv().assign(date=lambda frame: frame["date"].dt.strftime("%Y-%m-%d")).to_csv(ohlcv_path, index=False)
            _predictions().assign(date=lambda frame: frame["date"].dt.strftime("%Y-%m-%d")).to_csv(prediction_path, index=False)

            output = build_and_write_event_dataset("BUMI", ohlcv_path, root / "events", prediction_path, holding_days=5)

            self.assertTrue(output.exists())
            validate_event_dataset(json.loads(output.read_text()))

    def test_highest_and_lowest_include_entry_and_exit_prices(self) -> None:
        ohlcv = pd.DataFrame({
            "date": pd.bdate_range("2024-01-02", periods=3),
            "open": [100.0, 90.0, 80.0],
            "high": [95.0, 92.0, 85.0],
            "low": [98.0, 70.0, 75.0],
            "close": [100.0, 90.0, 80.0],
            "volume": [1000.0, 1000.0, 1000.0],
        })
        predictions = pd.DataFrame({
            "date": [pd.Timestamp("2024-01-02")],
            "signal": ["BUY"],
        })

        artifact = build_event_dataset(ohlcv, predictions, EventDatasetConfig(ticker="BUMI", holding_days=2))

        self.assertEqual(100.0, artifact["events"][0]["highest_price"])
        self.assertEqual(70.0, artifact["events"][0]["lowest_price"])

if __name__ == "__main__":
    unittest.main()
