"""Tests for Phase A transition resolution and gate classification."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quant.resolve_phase_a_and_prepare_phase_b import resolve_phase_a_and_prepare_phase_b


def _write_decision_artifacts(output_dir: Path) -> None:
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


class ResolvePhaseAAndPreparePhaseBTestCase(unittest.TestCase):
    """Validate blocked types, limited experiments, and full-start gates."""

    def test_transition_reports_blocked_artifact_when_decisions_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            (output_dir / "phase_a_closeout_status.json").write_text(
                json.dumps(
                    {
                        "status": "closed_with_notes",
                        "reason": "Closeout dapat dibaca.",
                        "blocking_items": [],
                        "notes": ["Tests belum clean untuk full start."],
                        "ojk_backfill": {"ready": True},
                        "macro_regulatory_signal": {"ready": True},
                        "tests": {
                            "python": {"status": "skipped"},
                            "php": {"status": "skipped"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = resolve_phase_a_and_prepare_phase_b(
                output_dir=output_dir,
                data_dir=root / "missing-data",
            )

            payload = result["transition_payload"]
            self.assertEqual("blocked", payload["transition_status"])
            self.assertEqual("blocked_artifact", payload["blocked_type"])
            self.assertFalse(payload["phase_b_entry_allowed"])
            self.assertEqual("blocked", payload["phase_b_entry_mode"])
            self.assertTrue((output_dir / "phase_b_item5_entry_gate.json").exists())

    def test_transition_reports_blocked_environment_when_mysql_runtime_is_unavailable_and_artifact_gate_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            (output_dir / "phase_a_closeout_status.json").write_text(
                json.dumps(
                    {
                        "status": "blocked",
                        "reason": "Runtime closeout gagal.",
                        "blocking_items": [
                            "Gagal membaca backfill historis OJK: SQLSTATE[HY000] [2002] Operation not permitted",
                            "Macro regulatory signal tidak bisa dievaluasi: SQLSTATE[HY000] [2002] Operation not permitted",
                        ],
                        "notes": [],
                        "ojk_backfill": {"ready": False, "error": "SQLSTATE[HY000] [2002] Operation not permitted"},
                        "macro_regulatory_signal": {"ready": False, "error": "SQLSTATE[HY000] [2002] Operation not permitted"},
                        "tests": {
                            "python": {"status": "skipped"},
                            "php": {"status": "skipped"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = resolve_phase_a_and_prepare_phase_b(
                output_dir=output_dir,
                data_dir=root / "missing-data",
            )

            payload = result["transition_payload"]
            self.assertEqual("blocked", payload["transition_status"])
            self.assertEqual("blocked_environment", payload["blocked_type"])
            self.assertFalse(payload["phase_b_entry_allowed"])

    def test_transition_allows_limited_experiment_even_if_full_runtime_closeout_is_still_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            _write_decision_artifacts(output_dir)
            (output_dir / "phase_a_closeout_status.json").write_text(
                json.dumps(
                    {
                        "status": "blocked",
                        "reason": "Runtime closeout penuh masih terhambat koneksi.",
                        "blocking_items": [
                            "Gagal membaca backfill historis OJK: SQLSTATE[HY000] [2002] Operation not permitted",
                            "Macro regulatory signal tidak bisa dievaluasi: SQLSTATE[HY000] [2002] Operation not permitted",
                        ],
                        "notes": ["Artifact baseline tetap bisa dibaca."],
                        "ojk_backfill": {"ready": False, "error": "SQLSTATE[HY000] [2002] Operation not permitted"},
                        "macro_regulatory_signal": {"ready": False, "error": "SQLSTATE[HY000] [2002] Operation not permitted"},
                        "tests": {
                            "python": {"status": "skipped"},
                            "php": {"status": "skipped"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = resolve_phase_a_and_prepare_phase_b(
                output_dir=output_dir,
                data_dir=root / "missing-data",
            )

            payload = result["transition_payload"]
            item5_gate = payload["phase_b_item5_entry_gate"]

            self.assertEqual("limited_experiment", payload["transition_status"])
            self.assertIsNone(payload["blocked_type"])
            self.assertTrue(payload["phase_b_entry_allowed"])
            self.assertEqual("limited_experiment", payload["phase_b_entry_mode"])
            self.assertTrue(item5_gate["allowed"])
            self.assertEqual("limited_experiment", item5_gate["mode"])

    def test_transition_allows_limited_experiment_when_baseline_is_provisional(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            _write_decision_artifacts(output_dir)
            (output_dir / "phase_a_closeout_status.json").write_text(
                json.dumps(
                    {
                        "status": "partially_ready",
                        "reason": "Closeout terbaca, tetapi belum final.",
                        "blocking_items": [],
                        "notes": ["Test suite inti tidak dijalankan pada closeout ini."],
                        "ojk_backfill": {"ready": True},
                        "macro_regulatory_signal": {"ready": True},
                        "tests": {
                            "python": {"status": "skipped"},
                            "php": {"status": "skipped"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = resolve_phase_a_and_prepare_phase_b(
                output_dir=output_dir,
                data_dir=root / "missing-data",
            )

            payload = result["transition_payload"]
            item5_gate = payload["phase_b_item5_entry_gate"]

            self.assertEqual("limited_experiment", payload["transition_status"])
            self.assertIsNone(payload["blocked_type"])
            self.assertTrue(payload["phase_b_entry_allowed"])
            self.assertEqual("limited_experiment", payload["phase_b_entry_mode"])
            self.assertEqual("provisional", payload["phase_a_resolution"]["baseline_artifact"]["baseline_status"])
            self.assertTrue(item5_gate["allowed"])
            self.assertEqual("limited_experiment", item5_gate["mode"])

    def test_transition_allows_full_start_when_baseline_final_and_closeout_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            _write_decision_artifacts(output_dir)
            (output_dir / "phase_a_closeout_status.json").write_text(
                json.dumps(
                    {
                        "status": "closed",
                        "reason": "Phase A closed cleanly.",
                        "blocking_items": [],
                        "notes": [],
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

            result = resolve_phase_a_and_prepare_phase_b(
                output_dir=output_dir,
                data_dir=root / "missing-data",
            )

            payload = result["transition_payload"]
            self.assertEqual("full_start", payload["transition_status"])
            self.assertTrue(payload["phase_b_entry_allowed"])
            self.assertEqual("full_start", payload["phase_b_entry_mode"])
            self.assertEqual("final", payload["phase_a_resolution"]["baseline_artifact"]["baseline_status"])

    def test_transition_reports_item6_post_status_when_go_no_go_artifact_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            _write_decision_artifacts(output_dir)
            (output_dir / "phase_a_closeout_status.json").write_text(
                json.dumps(
                    {
                        "status": "partially_ready",
                        "reason": "Closeout terbaca, tetapi belum final.",
                        "blocking_items": [],
                        "notes": [],
                        "ojk_backfill": {"ready": True},
                        "macro_regulatory_signal": {"ready": True},
                        "tests": {
                            "python": {"status": "skipped"},
                            "php": {"status": "skipped"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_b_item6_go_no_go.json").write_text(
                json.dumps(
                    {
                        "decision": "no_go",
                        "experiment_status": "completed",
                        "next_action": "stop",
                    }
                ),
                encoding="utf-8",
            )

            result = resolve_phase_a_and_prepare_phase_b(
                output_dir=output_dir,
                data_dir=root / "missing-data",
            )

            payload = result["transition_payload"]
            self.assertEqual("failed", payload["item6_experiment_status"])
            self.assertEqual("stop", payload["item6_next_action"])

    def test_transition_reports_item7_post_status_when_go_no_go_artifact_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            _write_decision_artifacts(output_dir)
            (output_dir / "phase_a_closeout_status.json").write_text(
                json.dumps(
                    {
                        "status": "partially_ready",
                        "reason": "Closeout terbaca, tetapi belum final.",
                        "blocking_items": [],
                        "notes": [],
                        "ojk_backfill": {"ready": True},
                        "macro_regulatory_signal": {"ready": True},
                        "tests": {
                            "python": {"status": "skipped"},
                            "php": {"status": "skipped"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_b_item7_go_no_go.json").write_text(
                json.dumps(
                    {
                        "decision": "keep_experimental",
                        "experiment_status": "completed",
                        "next_action": "continue_tuning",
                    }
                ),
                encoding="utf-8",
            )

            result = resolve_phase_a_and_prepare_phase_b(
                output_dir=output_dir,
                data_dir=root / "missing-data",
            )

            payload = result["transition_payload"]
            self.assertEqual("mixed", payload["item7_experiment_status"])
            self.assertEqual("continue_tuning", payload["item7_next_action"])

    def test_transition_preserves_item7_pending_status_from_go_no_go_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            _write_decision_artifacts(output_dir)
            (output_dir / "phase_a_closeout_status.json").write_text(
                json.dumps(
                    {
                        "status": "partially_ready",
                        "reason": "Closeout terbaca, tetapi belum final.",
                        "blocking_items": [],
                        "notes": [],
                        "ojk_backfill": {"ready": True},
                        "macro_regulatory_signal": {"ready": True},
                        "tests": {
                            "python": {"status": "skipped"},
                            "php": {"status": "skipped"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_b_item7_go_no_go.json").write_text(
                json.dumps(
                    {
                        "decision": "keep_experimental",
                        "experiment_status": "pending",
                        "next_action": "refresh_sentiment_data",
                    }
                ),
                encoding="utf-8",
            )

            result = resolve_phase_a_and_prepare_phase_b(
                output_dir=output_dir,
                data_dir=root / "missing-data",
            )

            payload = result["transition_payload"]
            self.assertEqual("pending", payload["item7_experiment_status"])
            self.assertEqual("refresh_sentiment_data", payload["item7_next_action"])

    def test_transition_reports_item8_post_status_when_go_no_go_artifact_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            output_dir = root / "output"
            output_dir.mkdir()
            _write_decision_artifacts(output_dir)
            (output_dir / "phase_a_closeout_status.json").write_text(
                json.dumps(
                    {
                        "status": "partially_ready",
                        "reason": "Closeout terbaca, tetapi belum final.",
                        "blocking_items": [],
                        "notes": [],
                        "ojk_backfill": {"ready": True},
                        "macro_regulatory_signal": {"ready": True},
                        "tests": {
                            "python": {"status": "skipped"},
                            "php": {"status": "skipped"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_b_item8_go_no_go.json").write_text(
                json.dumps(
                    {
                        "decision": "promote_ticker_specific",
                        "experiment_status": "completed",
                        "next_action": "promote_ticker_specific",
                    }
                ),
                encoding="utf-8",
            )

            result = resolve_phase_a_and_prepare_phase_b(
                output_dir=output_dir,
                data_dir=root / "missing-data",
            )

            payload = result["transition_payload"]
            self.assertEqual("promising", payload["item8_experiment_status"])
            self.assertEqual("promote_ticker_specific", payload["item8_next_action"])


if __name__ == "__main__":
    unittest.main()
