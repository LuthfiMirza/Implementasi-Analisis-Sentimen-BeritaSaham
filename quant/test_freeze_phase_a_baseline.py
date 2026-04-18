"""Tests for freezing the final Phase A baseline."""

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.freeze_phase_a_baseline import freeze_phase_a_baseline


class FreezePhaseABaselineTestCase(unittest.TestCase):
    """Validate baseline freeze outputs and safe fallbacks."""

    def test_freeze_uses_threshold_and_tuning_artifacts_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()

            (output_dir / "phase_a_threshold_decision.json").write_text(
                json.dumps(
                    {
                        "config": {"min_trades": 8},
                        "default_threshold_decision": {
                            "selected_default_threshold": 2.0,
                            "decision_confidence": "strong",
                            "mode": "global_fixed",
                        },
                        "adaptive_threshold_by_group": {"supported": True},
                        "readiness": {"status": "partially_ready"},
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_a_tuning_decision.json").write_text(
                json.dumps(
                    {
                        "strict_mode_decision": {"decision_code": "strict_default_no"},
                        "ready_for_phase_b": {"status": "partially_ready"},
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                [
                    {
                        "group_field": "sector",
                        "group_value": "finance",
                        "best_threshold": 2.5,
                        "decision_confidence": "strong",
                        "sample_status": "enough_sample",
                    },
                    {
                        "group_field": "beta_group",
                        "group_value": "high",
                        "best_threshold": 2.0,
                        "decision_confidence": "moderate",
                        "sample_status": "enough_sample",
                    },
                ]
            ).to_csv(output_dir / "phase_a_threshold_best_by_group.csv", index=False)
            pd.DataFrame(
                [{"ticker": "BBCA", "best_threshold": 2.0}, {"ticker": "BMRI", "best_threshold": 2.5}]
            ).to_csv(output_dir / "phase_a_threshold_best_by_ticker.csv", index=False)

            artifacts = freeze_phase_a_baseline(output_dir=output_dir)

            self.assertTrue((output_dir / "phase_a_baseline_final.json").exists())
            self.assertTrue((output_dir / "phase_a_baseline_report.txt").exists())
            self.assertTrue((output_dir / "phase_a_baseline_gate_report.txt").exists())
            payload = artifacts["baseline_payload"]
            self.assertEqual(2.0, payload["default_volume_spike_threshold"])
            self.assertFalse(payload["strict_mode_default"])
            self.assertTrue(payload["adaptive_threshold_enabled"])
            self.assertEqual("provisional", payload["baseline_status"])
            self.assertEqual(1, len(payload["group_threshold_overrides"]))
            self.assertIn("final_missing_requirements", payload)

    def test_freeze_falls_back_to_safe_defaults_when_artifacts_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"

            artifacts = freeze_phase_a_baseline(output_dir=output_dir)
            payload = artifacts["baseline_payload"]

            self.assertEqual(2.0, payload["default_volume_spike_threshold"])
            self.assertFalse(payload["strict_mode_default"])
            self.assertFalse(payload["adaptive_threshold_enabled"])
            self.assertEqual("draft", payload["baseline_status"])
            self.assertEqual("partially_ready", payload["readiness_status"])
            self.assertTrue((output_dir / "phase_a_baseline_final.json").exists())
            self.assertTrue((output_dir / "phase_a_baseline_report.txt").exists())
            self.assertTrue((output_dir / "phase_a_baseline_gate_report.txt").exists())

    def test_freeze_marks_baseline_final_when_closeout_supports_final(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()

            (output_dir / "phase_a_threshold_decision.json").write_text(
                json.dumps(
                    {
                        "config": {"min_trades": 8},
                        "default_threshold_decision": {
                            "selected_default_threshold": 2.0,
                            "decision_confidence": "strong",
                            "mode": "global_fixed",
                        },
                        "adaptive_threshold_by_group": {"supported": False},
                        "readiness": {"status": "ready"},
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_a_tuning_decision.json").write_text(
                json.dumps(
                    {
                        "strict_mode_decision": {"decision_code": "strict_default_no"},
                        "ready_for_phase_b": {"status": "ready"},
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_a_closeout_status.json").write_text(
                json.dumps(
                    {
                        "status": "closed_with_notes",
                        "blocking_items": [],
                        "notes": ["UI verification tetap manual."],
                        "ojk_backfill": {"ready": True},
                        "macro_regulatory_signal": {"ready": True},
                        "tests": {
                            "python": {"status": "passed"},
                            "php": {"status": "passed"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            artifacts = freeze_phase_a_baseline(output_dir=output_dir)
            payload = artifacts["baseline_payload"]

            self.assertEqual("final", payload["baseline_status"])
            self.assertEqual("closed_with_notes", payload["closeout_support_status"])
            self.assertTrue(payload["final_requirements_met"])


if __name__ == "__main__":
    unittest.main()
