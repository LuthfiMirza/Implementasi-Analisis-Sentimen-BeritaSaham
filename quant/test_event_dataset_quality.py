from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quant.trading_research.artifact_utils import write_json
from quant.trading_research.event_dataset_quality import audit_event_dataset
from quant.trading_research.walk_forward_event_dataset import SCHEMA_VERSION


def _event(date: str, idx: int) -> dict:
    return {
        "entry_date": date,
        "entry_price": 100.0,
        "holding_days": 5,
        "highest_price": 110.0 + idx,
        "lowest_price": 95.0,
        "exit_price": 103.0,
        "return_pct": 3.0,
        "mfe_pct": 10.0 + idx,
        "mae_pct": -5.0,
        "drawdown_pct": -10.0,
        "recovery_pct": 8.0,
        "atr": 2.0,
        "rsi": 55.0,
        "macd": 1.0,
        "adx": 20.0,
        "vwap": 101.0,
        "volume_ratio": 1.2,
        "market_regime": "1.0",
        "news_sentiment": 0.1,
        "prediction_probability": 0.7,
        "prediction_variant": "synthetic",
        "trade_outcome": "win",
    }


def _artifact(events: list[dict]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "walk_forward_event_dataset",
        "ticker": "BUMI",
        "generated_at": "2026-07-01T00:00:00+00:00",
        "config": {"holding_days": 5},
        "events": events,
        "quality": {"event_count": len(events), "status": "research_dataset"},
    }


class EventDatasetQualityTestCase(unittest.TestCase):
    def test_quality_report_for_valid_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            events = [_event("2024-01-02", 0), _event("2024-01-10", 1)]
            write_json(_artifact(events), path, overwrite=True)

            report = audit_event_dataset(path, Path(tmpdir), overwrite=True)

            self.assertEqual("valid", report["quality"]["status"])
            self.assertEqual(2, report["checks"]["event_count"])
            self.assertEqual(0, report["checks"]["duplicate_event_count"])
            self.assertTrue((Path(tmpdir) / "BUMI_event_quality_v1.json").exists())

    def test_quality_report_documents_duplicate_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            write_json(_artifact([_event("2024-01-02", 0), _event("2024-01-02", 1)]), path, overwrite=True)

            report = audit_event_dataset(path)

            self.assertEqual("invalid", report["quality"]["status"])
            self.assertEqual(1, report["checks"]["duplicate_event_count"])
            self.assertTrue(report["quality"]["critical_warnings"])


if __name__ == "__main__":
    unittest.main()
