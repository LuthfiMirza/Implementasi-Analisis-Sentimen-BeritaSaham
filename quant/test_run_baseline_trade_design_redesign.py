"""Tests for baseline trade-design redesign experiment."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_baseline_trade_design_redesign import (
    GO_NO_GO_DECISIONS,
    run_baseline_trade_design_redesign,
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
                "readiness_status": "partially_ready",
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


def _write_transition(output_dir: Path) -> None:
    (output_dir / "phase_a_to_phase_b_transition.json").write_text(
        json.dumps(
            {
                "phase_b_entry_mode": "limited_experiment",
                "phase_b_entry_allowed": True,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "phase_a_to_phase_b_transition_report.txt").write_text(
        "Phase A To Phase B Transition\n=============================\n",
        encoding="utf-8",
    )


class RunBaselineTradeDesignRedesignTestCase(unittest.TestCase):
    """Validate output artifacts and config coverage for baseline redesign."""

    def test_baseline_redesign_runs_and_writes_outputs(self) -> None:
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
            _write_transition(output_dir)

            result = run_baseline_trade_design_redesign(
                data_dir=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                metadata_file=metadata_path,
                hold_period_options=[3, 5, 7],
                min_trades_options=[5, 8, 10],
            )

            self.assertFalse(result["results_df"].empty)
            self.assertFalse(result["best_df"].empty)
            self.assertTrue((output_dir / "baseline_redesign_results.csv").exists())
            self.assertTrue((output_dir / "baseline_redesign_best_config_per_ticker.csv").exists())
            self.assertTrue((output_dir / "baseline_redesign_global_summary.json").exists())
            self.assertTrue((output_dir / "baseline_redesign_recommendations.txt").exists())
            self.assertTrue((output_dir / "baseline_redesign_go_no_go.json").exists())
            self.assertTrue((output_dir / "baseline_v2_redesign_results.csv").exists())
            self.assertTrue((output_dir / "baseline_v2_best_candidate.json").exists())
            self.assertTrue((output_dir / "baseline_v2_redesign_report.txt").exists())

            results_df = pd.read_csv(output_dir / "baseline_redesign_results.csv")
            self.assertEqual({3, 5, 7}, set(results_df["hold_period"].astype(int)))
            self.assertEqual({5, 8, 10}, set(results_df["min_trades_threshold"].astype(int)))

            best_df = pd.read_csv(output_dir / "baseline_redesign_best_config_per_ticker.csv")
            self.assertFalse(best_df.empty)

            go_no_go = json.loads((output_dir / "baseline_redesign_go_no_go.json").read_text(encoding="utf-8"))
            self.assertIn(go_no_go["decision"], GO_NO_GO_DECISIONS)
            self.assertIn("best_global_hold_period", go_no_go)
            self.assertIn("best_global_min_trades", go_no_go)

            best_candidate = json.loads((output_dir / "baseline_v2_best_candidate.json").read_text(encoding="utf-8"))
            self.assertIn("candidate_id", best_candidate)
            self.assertIn("hold_period", best_candidate)
            self.assertIn("min_trades", best_candidate)
            self.assertIn("score", best_candidate)
            self.assertIn("eligible_ticker_count", best_candidate)
            self.assertIn("average_return", best_candidate)
            self.assertIn("win_rate", best_candidate)
            self.assertIn("max_drawdown", best_candidate)
            self.assertIn("why_selected", best_candidate)
            self.assertIn("why_not_selected_if_weak", best_candidate)

            transition = json.loads((output_dir / "phase_a_to_phase_b_transition.json").read_text(encoding="utf-8"))
            self.assertIn("baseline_redesign_status", transition)
            self.assertIn("baseline_redesign_next_action", transition)
            self.assertIn("phase_b_retry_readiness", transition)


if __name__ == "__main__":
    unittest.main()
