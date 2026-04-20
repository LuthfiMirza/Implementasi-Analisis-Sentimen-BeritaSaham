"""Tests for baseline v3 signal-rule experiment."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_baseline_v2_candidate_validation import _candidate_signal, _feature_frame
from quant.run_baseline_v3_signal_rule_experiment import (
    DECISION_VALUES,
    determine_rule_decision,
    run_baseline_v3_signal_rule_experiment,
)


def _write_baseline(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "default_volume_spike_threshold": 1.5,
                "strict_mode_default": False,
                "adaptive_threshold_enabled": False,
                "group_threshold_overrides": [],
                "min_trades_floor": 5,
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


class RunBaselineV3SignalRuleExperimentTestCase(unittest.TestCase):
    """Validate signal-rule experiment outputs and decisions."""

    def test_signal_rule_experiment_runs_and_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            output_dir.mkdir()

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            _write_baseline(output_dir / "phase_a_baseline_final.json")
            _write_metadata(data_dir / "ticker_metadata.csv")
            _write_candidate(output_dir / "baseline_v2_best_candidate.json")

            result = run_baseline_v3_signal_rule_experiment(
                data_dir=data_dir,
                output_dir=output_dir,
                baseline_config=output_dir / "phase_a_baseline_final.json",
                metadata_file=data_dir / "ticker_metadata.csv",
                candidate_file=output_dir / "baseline_v2_best_candidate.json",
                min_trades=5,
                min_eligible_tickers=3,
                hold_period=3,
                profit_buffer_pct=0.0,
            )

            required = [
                output_dir / "baseline_v3_signal_rule_results.csv",
                output_dir / "baseline_v3_signal_rule_summary.json",
                output_dir / "baseline_v3_signal_rule_report.txt",
                output_dir / "baseline_v3_signal_rule_go_no_go.json",
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            results_df = pd.read_csv(output_dir / "baseline_v3_signal_rule_results.csv")
            self.assertEqual(
                {
                    "baseline_reference",
                    "baseline_v3_ema20_trend",
                    "baseline_v3_ema20_trend_guard",
                    "baseline_v3_ema20_volume_relaxed",
                },
                set(results_df["rule_id"]),
            )
            self.assertIn("candidate_signal_count", results_df.columns)
            self.assertIn("candidate_total_trades", results_df.columns)
            self.assertIn("score", results_df.columns)

            summary = json.loads((output_dir / "baseline_v3_signal_rule_summary.json").read_text(encoding="utf-8"))
            self.assertIn("rule_summaries", summary)
            self.assertIn("recommended_redesign_candidates", summary)

            go_no_go = json.loads((output_dir / "baseline_v3_signal_rule_go_no_go.json").read_text(encoding="utf-8"))
            self.assertIn(go_no_go["decision"], DECISION_VALUES)
            self.assertIn("best_rule", go_no_go)
            self.assertIn("recommended_next_action", go_no_go)

            self.assertFalse(result["results_df"].empty)

    def test_ema20_rule_generates_more_signals_than_ema50_on_short_fixture(self) -> None:
        frame = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=40, freq="D"),
                "open": [100.0 + (index * 0.4) for index in range(40)],
                "high": [100.5 + (index * 0.4) for index in range(40)],
                "low": [99.5 + (index * 0.4) for index in range(40)],
                "close": [100.2 + (index * 0.5) for index in range(40)],
                "volume": [1_000_000 + (index * 1000) for index in range(40)],
            }
        )
        feature_frame = _feature_frame(frame=frame, threshold=1.5)

        ema50_frame, ema50_signal, _ = _candidate_signal(
            feature_frame=feature_frame,
            candidate_id="baseline_v2_hold3_with_simplified_entry",
            threshold=1.5,
            entry_rule="close_gt_ema50",
        )
        ema20_frame, ema20_signal, _ = _candidate_signal(
            feature_frame=feature_frame,
            candidate_id="baseline_v3_ema20_trend",
            threshold=1.5,
            entry_rule="close_gt_ema20",
        )

        ema50_count = int(ema50_frame[ema50_signal].fillna(False).astype(bool).sum())
        ema20_count = int(ema20_frame[ema20_signal].fillna(False).astype(bool).sum())

        self.assertGreater(ema20_count, ema50_count)
        self.assertEqual(0, ema50_count)

    def test_high_coverage_but_bad_quality_is_not_promoted(self) -> None:
        reference = {
            "mean_score": 4.0,
            "mean_average_return": 1.0,
            "mean_max_drawdown": 2.0,
        }
        weak_rule = {
            "rule_id": "baseline_v3_ema20_volume_relaxed",
            "candidate_id": "baseline_v3_ema20_volume_relaxed",
            "entry_rule": "close_gt_ema20_and_volume_spike_relaxed",
            "eligible_ticker_count": 4,
            "coverage_gain_vs_old_rule": 3,
            "mean_score": -6.5,
            "mean_average_return": 0.1,
            "mean_max_drawdown": 8.5,
            "trade_retention_vs_baseline": 2.0,
            "positive_score_ticker_count": 1,
            "score_delta_vs_baseline": -10.5,
            "average_return_delta_vs_baseline": -0.9,
        }

        decision = determine_rule_decision(
            rule_summary=weak_rule,
            reference_summary=reference,
            min_eligible_tickers=3,
        )

        self.assertEqual("no_go", decision["decision"])
        self.assertFalse(decision["quality_preserved"])


if __name__ == "__main__":
    unittest.main()
