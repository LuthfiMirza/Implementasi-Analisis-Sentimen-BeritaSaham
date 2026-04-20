"""Tests for baseline root-cause postmortem finalization."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from quant.finalize_baseline_root_cause_postmortem import (
    finalize_baseline_root_cause_postmortem,
)


def _write_roadmap(output_dir: Path) -> None:
    (output_dir / "project_roadmap_status.json").write_text(
        json.dumps(
            {
                "latest_execution_status": {
                    "phase_b_status": "phase_b_needs_redesign_before_continue",
                    "phase_c_decision": "phase_c_no_go_yet",
                    "current_track": "redesign_baseline_v2_again",
                },
                "phase_a_final_status": {
                    "status": "closed_with_notes",
                },
                "items": [
                    {
                        "phase": "phase_b",
                        "item_name": "Volume confirmation per candlestick",
                        "recommended_next_action": "Biarkan item 5 tetap stop; evaluasi ulang hanya setelah baseline inti direvisi dan tervalidasi.",
                    },
                    {
                        "phase": "phase_b",
                        "item_name": "Multi-timeframe (weekly trend sebelum entry daily)",
                        "recommended_next_action": "Tetap nonaktifkan item 6; kembali ke perbaikan baseline inti sebelum memikirkan gate weekly lagi.",
                    },
                    {
                        "phase": "phase_b",
                        "item_name": "Sentiment momentum (tren 3 hari terakhir)",
                        "recommended_next_action": "Jangan hidupkan lagi item 7; audit relevansi sentiment series dan baseline entry dulu sebelum mencoba gating sentimen baru.",
                    },
                    {
                        "phase": "phase_b",
                        "item_name": "Backtest per saham / model adaptif per ticker",
                        "recommended_next_action": "Tetap parkirkan item 8; revisi baseline inti dulu sebelum memperlebar adaptive search space lagi.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _write_v2(output_dir: Path) -> None:
    (output_dir / "baseline_v2_go_no_go.json").write_text(
        json.dumps({"decision": "reject_candidate"}),
        encoding="utf-8",
    )
    (output_dir / "baseline_v2_validation.json").write_text(
        json.dumps(
            {
                "decision": "reject_candidate",
                "validation_status": "invalid",
                "eligible_ticker_count": 1,
                "min_eligible_tickers_required": 3,
                "total_trades_sum": 10,
                "minimum_trade_sample_required": 15,
            }
        ),
        encoding="utf-8",
    )


def _write_v3(output_dir: Path) -> None:
    (output_dir / "baseline_v3_signal_rule_go_no_go.json").write_text(
        json.dumps(
            {
                "decision": "no_go",
                "best_rule": "baseline_v3_ema20_trend_guard",
                "baseline_reference_rule": {
                    "eligible_ticker_count": 1,
                    "total_trades_sum": 10,
                    "mean_average_return": 4.24329,
                },
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v3_signal_rule_summary.json").write_text(
        json.dumps(
            {
                "best_v3_rule": {
                    "candidate_id": "baseline_v3_ema20_trend_guard",
                    "eligible_ticker_count": 8,
                    "total_trades_sum": 56,
                    "mean_average_return": -0.01014,
                }
            }
        ),
        encoding="utf-8",
    )


def _write_v4(output_dir: Path) -> None:
    (output_dir / "baseline_v4_quality_gate_go_no_go.json").write_text(
        json.dumps(
            {
                "decision": "no_go",
                "eligible_ticker_count": 2,
                "total_trades_sum": 34,
                "mean_average_return": 7.41434,
                "quality_preserved": True,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v4_quality_gate_summary.json").write_text(
        json.dumps(
            {
                "best_v4_candidate_summary": {
                    "candidate_id": "baseline_v4_quality_gate_guard",
                    "eligible_ticker_count": 2,
                    "total_trades_sum": 34,
                    "mean_average_return": 7.41434,
                }
            }
        ),
        encoding="utf-8",
    )


def _write_v5(output_dir: Path) -> None:
    (output_dir / "baseline_v5_exit_hold_go_no_go.json").write_text(
        json.dumps(
            {
                "best_candidate_id": "baseline_v5_hold4_extension",
                "decision": "no_go",
                "eligible_ticker_count": 0,
                "total_trades_sum": 21,
                "mean_average_return": -0.33547,
                "mean_average_return_delta_vs_v4_anchor": 1.738,
                "trade_retention_vs_v4_anchor": 0.7778,
                "quality_preserved": False,
                "supports_exit_hold_hypothesis": False,
                "recommended_next_action": "exit_hold_not_enough_keep_anchor_but_reassess_root_cause",
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v5_exit_hold_summary.json").write_text(
        json.dumps(
            {
                "best_v5_candidate_summary": {
                    "candidate_id": "baseline_v5_hold4_extension",
                    "eligible_ticker_count": 0,
                    "total_trades_sum": 21,
                    "mean_average_return": -0.33547,
                }
            }
        ),
        encoding="utf-8",
    )


class FinalizeBaselineRootCausePostmortemTestCase(unittest.TestCase):
    def test_postmortem_runs_when_some_artifacts_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()
            _write_roadmap(output_dir)
            _write_v3(output_dir)

            result = finalize_baseline_root_cause_postmortem(output_dir=output_dir)

            self.assertTrue(result["postmortem_json_path"].exists())
            self.assertTrue(result["postmortem_txt_path"].exists())
            self.assertTrue(result["root_cause_csv_path"].exists())
            self.assertTrue(result["next_plan_json_path"].exists())
            self.assertTrue(result["next_plan_txt_path"].exists())

            payload = json.loads(result["postmortem_json_path"].read_text(encoding="utf-8"))
            self.assertIn("artifact_gaps", payload)
            self.assertTrue(payload["artifact_gaps"])

    def test_postmortem_generates_matrix_and_plan_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()
            _write_roadmap(output_dir)
            _write_v2(output_dir)
            _write_v3(output_dir)
            _write_v4(output_dir)
            _write_v5(output_dir)

            result = finalize_baseline_root_cause_postmortem(output_dir=output_dir)

            with result["root_cause_csv_path"].open(encoding="utf-8", newline="") as handle:
                rows = {row["stage_id"]: row for row in csv.DictReader(handle)}

            self.assertEqual(4, len(rows))
            self.assertEqual("entry_too_loose_low_quality", rows["baseline_v3"]["primary_root_cause"])
            self.assertEqual("exit_hold_not_primary_problem", rows["baseline_v5"]["primary_root_cause"])

            postmortem = json.loads(result["postmortem_json_path"].read_text(encoding="utf-8"))
            plan = json.loads(result["next_plan_json_path"].read_text(encoding="utf-8"))

            self.assertEqual("revisit_eligibility_and_sample_guardrails", postmortem["recommended_primary_direction"])
            self.assertEqual("revisit_eligibility_and_sample_guardrails", plan["recommended_primary_direction"])
            self.assertIn("entry_relaxation_only", postmortem["what_to_stop"])
            self.assertIn("item5", postmortem["what_to_stop"])
            self.assertIn("fast_anchor_plus_quality_gate", postmortem["what_is_still_explorable"])

    def test_v3_no_go_rejects_entry_relaxation_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()
            _write_roadmap(output_dir)
            _write_v2(output_dir)
            _write_v3(output_dir)
            _write_v4(output_dir)
            _write_v5(output_dir)

            result = finalize_baseline_root_cause_postmortem(output_dir=output_dir)
            postmortem = result["postmortem"]

            self.assertIn("entry_relaxation_only", postmortem["what_to_stop"])
            text = result["postmortem_txt_path"].read_text(encoding="utf-8")
            self.assertIn("Masalah utama bukan lagi entry relaxation", text)

    def test_v5_no_go_marks_exit_hold_not_primary_solution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()
            _write_roadmap(output_dir)
            _write_v2(output_dir)
            _write_v3(output_dir)
            _write_v4(output_dir)
            _write_v5(output_dir)

            result = finalize_baseline_root_cause_postmortem(output_dir=output_dir)
            text = result["postmortem_txt_path"].read_text(encoding="utf-8")
            self.assertIn("Masalah utama bukan exit/hold sebagai solusi tunggal", text)
            self.assertIn("exit_hold_only_redesign", result["postmortem"]["what_to_stop"])


if __name__ == "__main__":
    unittest.main()
