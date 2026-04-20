"""Tests for baseline v2 watchlist monitoring."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_baseline_v2_watchlist_monitoring import (
    DECISION_VALUES,
    run_baseline_v2_watchlist_monitoring,
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


def _write_metadata(path: Path) -> None:
    pd.DataFrame(
        {
            "ticker": ["BBCA", "BBRI", "BMRI", "GOTO", "TLKM"],
            "sector": ["perbankan", "perbankan", "perbankan", "teknologi", "telekomunikasi"],
            "category": ["finance", "finance", "finance", "technology", "telco"],
            "market_cap_group": ["large", "large", "large", "large", "large"],
        }
    ).to_csv(path, index=False)


def _duplicate_price_files(data_dir: Path) -> None:
    bmri = pd.read_csv(data_dir / "BMRI.csv")
    bbca = pd.read_csv(data_dir / "BBCA.csv")
    tlkm = pd.read_csv(data_dir / "TLKM.csv")
    bmri.to_csv(data_dir / "BBRI.csv", index=False)
    tlkm.to_csv(data_dir / "GOTO.csv", index=False)
    bbca.to_csv(data_dir / "ADRO.csv", index=False)


def _write_previous_subset_artifacts(output_dir: Path) -> None:
    (output_dir / "baseline_v2_subset_go_no_go.json").write_text(
        json.dumps(
            {
                "decision": "keep_candidate_experimental",
                "candidate_id": "baseline_v2_hold3_with_trend_guard",
                "subset_supported": True,
                "recommended_tickers": ["BMRI", "GOTO", "BBCA", "BBRI"],
                "recommended_groups": ["sector:perbankan"],
                "best_subset_tickers": ["BMRI", "GOTO"],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v2_subset_validation_summary.json").write_text(
        json.dumps({"decision": {"best_subset_tickers": ["BMRI", "GOTO"]}}),
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


class RunBaselineV2WatchlistMonitoringTestCase(unittest.TestCase):
    """Validate monitoring artifacts and transition updates."""

    def test_watchlist_monitoring_runs_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = output_dir / "phase_a_baseline_final.json"
            candidate_path = output_dir / "baseline_v2_best_candidate.json"
            metadata_path = data_dir / "ticker_metadata.csv"
            output_dir.mkdir()

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            _duplicate_price_files(data_dir)
            _write_baseline(baseline_path)
            _write_candidate(candidate_path)
            _write_metadata(metadata_path)
            _write_previous_subset_artifacts(output_dir)
            _write_transition(output_dir)

            result = run_baseline_v2_watchlist_monitoring(
                data_dir=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                candidate_file=candidate_path,
                metadata_file=metadata_path,
                min_trades=5,
                observation_windows=[1, 2, 3, 4, 5],
            )

            required = [
                output_dir / "baseline_v2_watchlist_monitoring_results.csv",
                output_dir / "baseline_v2_watchlist_monitoring_summary.json",
                output_dir / "baseline_v2_watchlist_monitoring_report.txt",
                output_dir / "baseline_v2_watchlist_monitoring_decision.json",
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            results_df = pd.read_csv(output_dir / "baseline_v2_watchlist_monitoring_results.csv")
            self.assertIn("ticker_goto", set(results_df["subset_id"]))
            self.assertIn("group_sector_perbankan", set(results_df["subset_id"]))
            self.assertEqual({1, 2, 3, 4, 5}, set(results_df["observation_window"]))
            self.assertIn("stable_across_windows", results_df.columns)

            decision_payload = json.loads(
                (output_dir / "baseline_v2_watchlist_monitoring_decision.json").read_text(encoding="utf-8")
            )
            self.assertIn(decision_payload["decision"], DECISION_VALUES)
            self.assertIn("still_experimental", decision_payload)

            transition = json.loads((output_dir / "phase_a_to_phase_b_transition.json").read_text(encoding="utf-8"))
            self.assertIn("baseline_v2_watchlist_monitoring_status", transition)
            self.assertIn("baseline_v2_watchlist_monitoring_next_action", transition)

            self.assertFalse(result["results_df"].empty)


if __name__ == "__main__":
    unittest.main()
