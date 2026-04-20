"""Tests for baseline v2 candidate validation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_baseline_v2_candidate_validation import (
    DECISION_VALUES,
    VALIDATION_STATUS_VALUES,
    run_baseline_v2_candidate_validation,
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


def _write_candidate(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "selected_candidate": {
                    "candidate_id": "baseline_v2_hold3_with_trend_guard",
                    "entry_rule": "close_gt_ema50_and_bullish_candle",
                    "hold_period": 3,
                    "min_trades_threshold": 5,
                    "profit_buffer_pct": 0.0,
                }
            }
        ),
        encoding="utf-8",
    )


def _write_transition(output_dir: Path) -> None:
    (output_dir / "phase_a_to_phase_b_transition.json").write_text(
        json.dumps({"phase_b_entry_allowed": True, "phase_b_entry_mode": "limited_experiment"}),
        encoding="utf-8",
    )
    (output_dir / "phase_a_to_phase_b_transition_report.txt").write_text(
        "Phase A To Phase B Transition\n=============================\n",
        encoding="utf-8",
    )


class RunBaselineV2CandidateValidationTestCase(unittest.TestCase):
    """Validate candidate comparison artifacts and transition update."""

    def test_baseline_v2_validation_runs_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = output_dir / "phase_a_baseline_final.json"
            candidate_path = output_dir / "baseline_v2_best_candidate.json"
            metadata_path = data_dir / "ticker_metadata.csv"
            output_dir.mkdir()

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            _write_baseline(baseline_path)
            _write_candidate(candidate_path)
            _write_metadata(metadata_path)
            _write_transition(output_dir)

            result = run_baseline_v2_candidate_validation(
                data_dir=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                candidate_file=candidate_path,
                metadata_file=metadata_path,
                min_trades=5,
                min_eligible_tickers=3,
            )

            required = [
                output_dir / "baseline_v2_validation_results.csv",
                output_dir / "baseline_v2_validation_per_ticker.csv",
                output_dir / "baseline_v2_validation_summary.json",
                output_dir / "baseline_v2_validation.json",
                output_dir / "baseline_v2_validation_report.txt",
                output_dir / "baseline_v2_validation_go_no_go.json",
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            summary_df = pd.read_csv(output_dir / "baseline_v2_validation_results.csv")
            self.assertEqual({"active_baseline", "baseline_v2_candidate"}, set(summary_df["variant"]))

            per_ticker_df = pd.read_csv(output_dir / "baseline_v2_validation_per_ticker.csv")
            self.assertIn("delta_score", per_ticker_df.columns)
            self.assertIn("validation_outcome", per_ticker_df.columns)

            go_no_go = json.loads((output_dir / "baseline_v2_validation_go_no_go.json").read_text(encoding="utf-8"))
            self.assertIn(go_no_go["decision"], DECISION_VALUES)
            self.assertIn("candidate_is_better_than_active_baseline", go_no_go)

            validation = json.loads((output_dir / "baseline_v2_validation.json").read_text(encoding="utf-8"))
            self.assertIn(validation["validation_status"], VALIDATION_STATUS_VALUES)
            self.assertIn("trade_sample_ok", validation)
            self.assertIn("score_ok", validation)
            self.assertIn("recommendation", validation)
            self.assertIn("next_action", validation)

            transition = json.loads((output_dir / "phase_a_to_phase_b_transition.json").read_text(encoding="utf-8"))
            self.assertIn("baseline_v2_validation_status", transition)
            self.assertIn("baseline_v2_validation_next_action", transition)
            self.assertIn("phase_b_retry_readiness_after_candidate_validation", transition)

            self.assertFalse(result["per_ticker_df"].empty)


if __name__ == "__main__":
    unittest.main()
