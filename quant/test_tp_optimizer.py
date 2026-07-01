from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quant.trading_research.artifact_utils import sha256_file, write_json
from quant.trading_research.tp_optimizer import (
    TPOptimizerConfig,
    build_chronological_folds,
    build_tp_optimizer_artifact,
    calculate_candidate_metrics,
    candidate_event_result,
    main,
    validate_tp_optimizer_artifact,
)
from quant.trading_research.walk_forward_event_dataset import SCHEMA_VERSION


def _event(index: int, mfe: float = 12.0, ret: float = 2.0, probability: float | None = 0.7) -> dict:
    day = index + 1
    month = 1 + (day - 1) // 20
    dom = 1 + (day - 1) % 20
    return {
        "entry_date": f"2024-{month:02d}-{dom:02d}",
        "entry_price": 100.0,
        "holding_days": 10,
        "highest_price": 100.0 + mfe,
        "lowest_price": 94.0,
        "exit_price": 100.0 + ret,
        "return_pct": ret,
        "mfe_pct": mfe,
        "mae_pct": -6.0,
        "drawdown_pct": -8.0,
        "recovery_pct": 8.5,
        "atr": 3.0,
        "rsi": 55.0,
        "macd": 1.0,
        "adx": 20.0,
        "vwap": 101.0,
        "volume_ratio": 1.0,
        "market_regime": "bull" if index % 2 == 0 else "bear",
        "news_sentiment": 0.0,
        "prediction_probability": probability,
        "prediction_variant": "synthetic",
        "trade_outcome": "win" if ret > 0 else "loss",
    }


def _events(count: int = 40) -> list[dict]:
    return [_event(i, mfe=15.0 if i % 3 else 6.0, ret=4.0 if i % 4 else -3.0) for i in range(count)]


def _artifact(events: list[dict], schema: str = SCHEMA_VERSION) -> dict:
    return {
        "schema_version": schema,
        "artifact_type": "walk_forward_event_dataset",
        "ticker": "BUMI",
        "generated_at": "2026-07-01T00:00:00+00:00",
        "config": {"holding_days": 10},
        "events": events,
        "quality": {"event_count": len(events), "status": "research_dataset"},
    }


class TPOptimizerTestCase(unittest.TestCase):
    def test_tp_hit_calculation(self) -> None:
        result = candidate_event_result(_event(0, mfe=12.0), 10.0)
        self.assertTrue(result["tp_hit"])
        self.assertEqual(10.0, result["realized_return_pct"])

    def test_tp_timeout_uses_event_return(self) -> None:
        result = candidate_event_result(_event(0, mfe=4.0, ret=-2.5), 10.0)
        self.assertFalse(result["tp_hit"])
        self.assertEqual(-2.5, result["realized_return_pct"])

    def test_candidate_metrics(self) -> None:
        metrics = calculate_candidate_metrics([_event(0, mfe=12.0), _event(1, mfe=4.0, ret=-1.0)], 10.0)
        self.assertEqual(2, metrics["event_count"])
        self.assertEqual(1, metrics["tp_hit_count"])
        self.assertEqual(0.5, metrics["tp_hit_rate"])
        self.assertEqual(4.5, metrics["expectancy_pct"])

    def test_chronological_folds_have_no_leakage(self) -> None:
        folds = build_chronological_folds(_events(20), 3)
        self.assertTrue(folds)
        for fold in folds:
            self.assertLess(fold["train_end"], fold["validation_start"])

    def test_builds_valid_artifact_and_source_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            write_json(_artifact(_events(45)), path, overwrite=True)
            artifact = build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(candidates=[5.0, 10.0, 15.0], minimum_sample_size=10, minimum_effective_sample_size=1, min_segment_sample_size=50))

            self.assertEqual("tp_optimizer_v1", artifact["schema_version"])
            self.assertIn(artifact["best_candidate_by_score"]["tp_pct"], [5.0, 10.0, 15.0])
            self.assertEqual(sha256_file(path), artifact["source"]["source_checksum"])
            validate_tp_optimizer_artifact(artifact, path)

    def test_invalid_input_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            write_json(_artifact(_events(10), schema="bad"), path, overwrite=True)

            with self.assertRaisesRegex(ValueError, "invalid schema"):
                build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(minimum_sample_size=5))

    def test_duplicate_event_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            events = _events(10)
            events[1]["entry_date"] = events[0]["entry_date"]
            write_json(_artifact(events), path, overwrite=True)

            with self.assertRaisesRegex(ValueError, "duplicate event"):
                build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(minimum_sample_size=5))

    def test_insufficient_sample_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            write_json(_artifact(_events(8)), path, overwrite=True)
            artifact = build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(candidates=[5.0, 10.0], minimum_sample_size=30))

            self.assertFalse(artifact["quality"]["usable_for_decision"])
            self.assertIn("sample size below minimum", artifact["quality"]["warnings"])

    def test_deterministic_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            write_json(_artifact(_events(45)), path, overwrite=True)
            config = TPOptimizerConfig(candidates=[5.0, 10.0, 15.0], minimum_sample_size=10)
            first = build_tp_optimizer_artifact(path, "BUMI", config)
            second = build_tp_optimizer_artifact(path, "BUMI", config)

            self.assertEqual(first["best_candidate_by_score"]["tp_pct"], second["best_candidate_by_score"]["tp_pct"])
            self.assertEqual(first["best_candidate_by_score"]["selection_score"], second["best_candidate_by_score"]["selection_score"])

    def test_segment_insufficient_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            write_json(_artifact(_events(20)), path, overwrite=True)
            artifact = build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(candidates=[5.0, 10.0], minimum_sample_size=5, min_segment_sample_size=50))

            statuses = [item["status"] for item in artifact["segments"]["market_regime"]]
            self.assertIn("insufficient_sample", statuses)

    def test_invalid_output_artifact_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            write_json(_artifact(_events(45)), path, overwrite=True)
            artifact = build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(candidates=[5.0, 10.0], minimum_sample_size=10, minimum_effective_sample_size=1, minimum_validation_expectancy_pct=-100, minimum_profitable_fold_ratio=0))
            if artifact["selected"] is None:
                artifact["selected"] = {"tp_pct": 99.0}
            else:
                artifact["selected"]["tp_pct"] = 99.0

            with self.assertRaisesRegex(ValueError, "selected TP"):
                validate_tp_optimizer_artifact(artifact, path)

    def test_cli_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            path = root / "events.json"
            write_json(_artifact(_events(45)), path, overwrite=True)

            exit_code = main(["--ticker", "BUMI", "--events", str(path), "--output-dir", str(root / "tp"), "--candidate-tp", "5", "10", "--minimum-sample-size", "10", "--overwrite"])

            self.assertEqual(0, exit_code)
            output = root / "tp" / "BUMI_tp_optimizer_v1.json"
            self.assertTrue(output.exists())
            validate_tp_optimizer_artifact(json.loads(output.read_text()), path)

    def test_negative_oos_expectancy_selected_null_and_best_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            write_json(_artifact([_event(i, mfe=1.0, ret=-5.0) for i in range(45)]), path, overwrite=True)
            artifact = build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(candidates=[10.0], minimum_sample_size=10, minimum_effective_sample_size=1, overlap_policy="allow_all"))

            self.assertIsNone(artifact["selected"])
            self.assertFalse(artifact["quality"]["usable_for_decision"])
            self.assertIsNotNone(artifact["best_candidate_by_score"])
            self.assertIn("validation expectancy below minimum", artifact["quality"]["warnings"])

    def test_selection_stability_differs_from_expectancy_stability(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            events = [_event(i, mfe=8.0, ret=(20.0 if i % 7 == 0 else -10.0)) for i in range(80)]
            write_json(_artifact(events), path, overwrite=True)
            artifact = build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(candidates=[10.0], minimum_sample_size=10, minimum_effective_sample_size=1, overlap_policy="allow_all"))

            self.assertEqual(1.0, artifact["stability"]["selection_stability"])
            self.assertLess(artifact["stability"]["expectancy_stability"], 1.0)

    def test_overlap_purge_and_effective_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            write_json(_artifact(_events(45)), path, overwrite=True)
            artifact = build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(candidates=[5.0, 10.0], minimum_sample_size=10))

            self.assertGreater(artifact["purged_event_count"], 0)
            self.assertLess(artifact["effective_sample_size"], artifact["eligible_event_count"])

    def test_incomplete_future_window_excluded_not_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            events = _events(12)
            events[-1]["holding_days"] = 3
            write_json(_artifact(events), path, overwrite=True)
            artifact = build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(candidates=[5.0], minimum_sample_size=1, minimum_effective_sample_size=1))

            self.assertEqual(1, artifact["exclusions"]["insufficient_future_ohlcv"])
            self.assertEqual(11, artifact["eligible_event_count"])
            self.assertEqual(11, artifact["all_events_analysis"]["candidates"][0]["event_count"])

    def test_zero_return_and_stale_price_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            events = [_event(i, mfe=0.0, ret=0.0) for i in range(20)]
            for event in events:
                event["highest_price"] = event["entry_price"]
                event["lowest_price"] = event["entry_price"]
                event["exit_price"] = event["entry_price"]
                event["mfe_pct"] = 0.0
                event["mae_pct"] = 0.0
                event["drawdown_pct"] = 0.0
            write_json(_artifact(events), path, overwrite=True)
            artifact = build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(candidates=[5.0], minimum_sample_size=1, minimum_effective_sample_size=1))

            self.assertEqual(1.0, artifact["zero_return_audit"]["zero_return_rate"])
            self.assertTrue(artifact["zero_return_audit"]["stale_price_warning"])

    def test_confidence_interval_quality_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            events = [_event(i, mfe=20.0, ret=(80.0 if i % 2 else -80.0)) for i in range(80)]
            write_json(_artifact(events), path, overwrite=True)
            artifact = build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(candidates=[30.0], minimum_sample_size=10, minimum_effective_sample_size=1, maximum_expectancy_ci_width_pct=0.1, overlap_policy="allow_all"))

            self.assertIn("expectancy confidence interval too wide", artifact["quality"]["warnings"])

    def test_schema_accepts_selected_null_and_rejects_inconsistency(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "events.json"
            write_json(_artifact([_event(i, mfe=1.0, ret=-2.0) for i in range(20)]), path, overwrite=True)
            artifact = build_tp_optimizer_artifact(path, "BUMI", TPOptimizerConfig(candidates=[5.0], minimum_sample_size=10, minimum_effective_sample_size=1))
            validate_tp_optimizer_artifact(artifact, path)
            artifact["quality"]["usable_for_decision"] = True
            with self.assertRaisesRegex(ValueError, "usable artifact requires selected"):
                validate_tp_optimizer_artifact(artifact, path)


if __name__ == "__main__":
    unittest.main()
