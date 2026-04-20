"""Tests for baseline revision diagnostics and candidate selection."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_baseline_revision_diagnostics import (
    DECISION_VALUES,
    run_baseline_revision_diagnostics,
)


def _write_baseline(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "default_volume_spike_threshold": 1.5,
                "strict_mode_default": False,
                "adaptive_threshold_enabled": False,
                "group_threshold_overrides": [],
                "min_trades_floor": 8,
                "baseline_status": "provisional",
            }
        ),
        encoding="utf-8",
    )


def _write_metadata(path: Path) -> None:
    pd.DataFrame(
        {
            "ticker": ["BBCA", "BMRI", "TLKM"],
            "sector": ["finance", "finance", "telco"],
            "category": ["bank", "bank", "telco"],
            "market_cap_group": ["large", "large", "large"],
        }
    ).to_csv(path, index=False)


def _write_context(output_dir: Path) -> None:
    (output_dir / "phase_b_postmortem.json").write_text(
        json.dumps({"phase_b_status": "phase_b_needs_redesign_before_continue"}),
        encoding="utf-8",
    )
    (output_dir / "phase_b_v2_redesign_decision.json").write_text(
        json.dumps(
            {
                "primary_failure_mode": "baseline needs entry/exit redesign",
                "supporting_signals": {"recommended_realistic_min_trades": 5},
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_redesign_go_no_go.json").write_text(
        json.dumps(
            {
                "decision": "improved_but_keep_experimental",
                "best_global_hold_period": 3,
                "best_global_min_trades": 5,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_redesign_global_summary.json").write_text(
        json.dumps({"config_summaries": []}),
        encoding="utf-8",
    )
    (output_dir / "phase_a_to_phase_b_transition.json").write_text(
        json.dumps({"phase_b_entry_allowed": True, "phase_b_entry_mode": "limited_experiment"}),
        encoding="utf-8",
    )
    (output_dir / "phase_a_to_phase_b_transition_report.txt").write_text(
        "Phase A To Phase B Transition\n=============================\n",
        encoding="utf-8",
    )


class RunBaselineRevisionDiagnosticsTestCase(unittest.TestCase):
    """Validate baseline revision diagnostics artifacts and transition update."""

    def test_baseline_revision_diagnostics_generate_candidates_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = output_dir / "phase_a_baseline_final.json"
            metadata_path = data_dir / "ticker_metadata.csv"
            output_dir.mkdir()

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            _write_baseline(baseline_path)
            _write_metadata(metadata_path)
            _write_context(output_dir)

            result = run_baseline_revision_diagnostics(
                data_dir=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                metadata_file=metadata_path,
            )

            required = [
                output_dir / "baseline_revision_diagnostics.json",
                output_dir / "baseline_revision_diagnostics.txt",
                output_dir / "baseline_v2_candidate_results.csv",
                output_dir / "baseline_v2_best_candidate.json",
                output_dir / "baseline_v2_recommendations.txt",
                output_dir / "baseline_v2_go_no_go.json",
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            candidate_results = pd.read_csv(output_dir / "baseline_v2_candidate_results.csv")
            self.assertIn("candidate_id", candidate_results.columns)
            self.assertGreaterEqual(candidate_results["candidate_id"].nunique(), 4)

            best_candidate = json.loads((output_dir / "baseline_v2_best_candidate.json").read_text(encoding="utf-8"))
            self.assertIn("selected_candidate", best_candidate)
            self.assertTrue(best_candidate["selected_candidate"])

            go_no_go = json.loads((output_dir / "baseline_v2_go_no_go.json").read_text(encoding="utf-8"))
            self.assertIn(go_no_go["decision"], DECISION_VALUES)
            self.assertIn("baseline_v2_candidate_selected", go_no_go)

            transition = json.loads((output_dir / "phase_a_to_phase_b_transition.json").read_text(encoding="utf-8"))
            self.assertIn("baseline_revision_status", transition)
            self.assertIn("baseline_revision_next_action", transition)
            self.assertIn("phase_b_retry_readiness_after_baseline_v2", transition)

            self.assertFalse(result["candidate_results_df"].empty)


if __name__ == "__main__":
    unittest.main()
