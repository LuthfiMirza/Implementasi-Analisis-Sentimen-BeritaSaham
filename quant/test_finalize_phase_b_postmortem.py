"""Tests for Phase B postmortem finalization."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from quant.finalize_phase_b_postmortem import finalize_phase_b_postmortem


def _write_transition(output_dir: Path) -> None:
    payload = {
        "generated_at": "2026-04-18T13:08:54.338122+00:00",
        "phase_a_status": "blocked",
        "transition_status": "limited_experiment",
        "phase_b_entry_allowed": True,
        "phase_b_entry_mode": "limited_experiment",
        "item5_experiment_status": "failed",
        "item5_next_action": "stop",
        "item6_experiment_status": "failed",
        "item6_next_action": "stop",
        "item7_experiment_status": "failed",
        "item7_next_action": "stop",
        "item8_experiment_status": "failed",
        "item8_next_action": "stop",
    }
    (output_dir / "phase_a_to_phase_b_transition.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    (output_dir / "phase_a_to_phase_b_transition_report.txt").write_text(
        "Phase A To Phase B Transition\n=============================\n",
        encoding="utf-8",
    )


def _write_item5(output_dir: Path) -> None:
    (output_dir / "phase_b_item5_go_no_go.json").write_text(
        json.dumps(
            {
                "decision": "no_go",
                "best_global_threshold": 1.0,
                "promote_default": False,
                "promote_subset_only": False,
                "recommended_groups": [],
                "recommended_tickers": [],
                "blocked_from_default": [
                    "Skor global item 5 tidak positif.",
                    "Trade retention global terlalu rendah untuk default.",
                    "Semua threshold yang diuji collapse ke effective confirmation threshold 1.5 karena baseline Phase A aktif sudah menuntut volume_ratio minimal itu.",
                    "Tidak ada threshold item 5 yang memenuhi min_trades=8, jadi dukungan sampelnya belum cukup untuk promosi.",
                ],
                "next_action": "stop",
                "item5_experiment_status": "failed",
                "item5_next_action": "stop",
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "phase_b_item5_recommendations.txt").write_text(
        "\n".join(
            [
                "Phase B Item 5 Recommendations",
                "================================",
                "",
                "- Decision: no_go",
                "- mean_score=-50.4133",
                "- delta_win_rate_mean=-3.3330",
                "- delta_average_return_mean=-0.0268",
                "- trade_retention_mean_pct=40.00",
                "- threshold_profile=negative",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_item6(output_dir: Path) -> None:
    (output_dir / "phase_b_item6_go_no_go.json").write_text(
        json.dumps(
            {
                "decision": "no_go",
                "experiment_status": "completed",
                "promote_default": False,
                "promote_subset_only": False,
                "recommended_tickers": [],
                "recommended_groups": [],
                "next_action": "stop",
                "blocked_from_default": [
                    "Trade retention rata-rata masih terlalu rendah.",
                    "Tidak ada ticker comparable yang improve dengan retention memadai.",
                    "Ticker yang memburuk minimal sama banyak dengan yang improve.",
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "phase_b_item6_multitimeframe_report.txt").write_text(
        "\n".join(
            [
                "Phase B Item 6 Multi-Timeframe Experiment",
                "==========================================",
                "",
                "- Comparison status: measured",
                "- Weekly trend method: ema20",
                "- Ticker count: 10",
                "- Weekly-data-ready tickers: 10",
                "- Comparable baseline tickers: 4",
                "- Delta total trades sum: -3.0",
                "- Mean delta win rate: 0.0",
                "- Mean delta average return: 1.50275",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "phase_b_item6_multitimeframe_summary.json").write_text(
        json.dumps(
            {
                "comparison_status": "measured",
                "experiment_arm": {"weekly_trend_method": "ema20"},
                "aggregate": {
                    "ticker_count": 10,
                    "weekly_data_ready_ticker_count": 10,
                    "comparable_ticker_count": 4,
                    "baseline_total_trades_sum": 6.0,
                    "candidate_total_trades_sum": 3.0,
                    "delta_total_trades_sum": -3.0,
                    "trade_retention_mean_pct": 25.0,
                    "delta_win_rate_mean": 0.0,
                    "delta_average_return_mean": 1.50275,
                },
            }
        ),
        encoding="utf-8",
    )


def _write_item7(output_dir: Path) -> None:
    (output_dir / "phase_b_item7_go_no_go.json").write_text(
        json.dumps(
            {
                "decision": "no_go",
                "experiment_status": "completed",
                "promote_default": False,
                "promote_subset_only": False,
                "recommended_tickers": [],
                "recommended_groups": [],
                "next_action": "stop",
                "blocked_from_default": [
                    "Trade retention rata-rata masih terlalu rendah.",
                    "Win rate rata-rata tidak membaik.",
                    "Tidak ada ticker comparable yang improve dengan retention memadai.",
                    "Ticker yang memburuk minimal sama banyak dengan yang improve.",
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "phase_b_item7_sentiment_momentum_report.txt").write_text(
        "\n".join(
            [
                "Phase B Item 7 Sentiment Momentum Experiment",
                "===========================================",
                "",
                "- Comparison status: measured",
                "- Sentiment momentum mode: weighted",
                "- Ticker count: 10",
                "- Sentiment-data-ready tickers: 9",
                "- Comparable baseline tickers: 4",
                "- Delta total trades sum: -6.0",
                "- Mean delta win rate: -34.218",
                "- Mean delta average return: -2.51608",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "phase_b_item7_sentiment_momentum_summary.json").write_text(
        json.dumps(
            {
                "comparison_status": "measured",
                "experiment_arm": {"sentiment_momentum_mode": "weighted"},
                "aggregate": {
                    "ticker_count": 10,
                    "sentiment_data_ready_ticker_count": 9,
                    "comparable_ticker_count": 4,
                    "baseline_total_trades_sum": 96.0,
                    "candidate_total_trades_sum": 0.0,
                    "delta_total_trades_sum": -96.0,
                    "trade_retention_mean_pct": 0.0,
                    "delta_win_rate_mean": -34.218,
                    "delta_average_return_mean": -2.51608,
                },
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "phase_b_item7_data_readiness.json").write_text(
        json.dumps(
            {
                "selected_ticker_count": 10,
                "valid_ticker_count": 9,
                "unusable_ticker_count": 1,
                "dataset_is_item7_ready": True,
                "experiment_can_run": True,
            }
        ),
        encoding="utf-8",
    )


def _write_item8(output_dir: Path) -> None:
    (output_dir / "phase_b_item8_go_no_go.json").write_text(
        json.dumps(
            {
                "decision": "no_go",
                "experiment_status": "completed",
                "adaptive_model_supported": False,
                "promote_ticker_specific": False,
                "promote_group_specific": False,
                "recommended_tickers": [],
                "recommended_groups": [],
                "blocked_from_broader_promotion": [
                    "Ticker yang benar-benar layak masih terlalu sedikit.",
                    "Belum ada group dengan sinyal adaptive yang cukup konsisten.",
                    "Sebagian ticker masih tidak punya kandidat yang lolos min_trades.",
                    "Ticker yang memburuk masih terlalu banyak dibanding yang improve.",
                ],
                "next_action": "stop",
                "item8_experiment_status": "failed",
                "item8_next_action": "stop",
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "phase_b_item8_recommendations.txt").write_text(
        "\n".join(
            [
                "Phase B Item 8 Adaptive Recommendations",
                "=======================================",
                "",
                "- Decision: no_go",
                "- Adaptive model supported: False",
                "- Promote ticker specific: False",
                "- Promote group specific: False",
                "- Next action: stop",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "phase_b_item8_global_summary.json").write_text(
        json.dumps(
            {
                "ticker_count": 10,
                "evaluated_config_count": 60,
                "eligible_best_ticker_count": 0,
                "recommended_ticker_count": 0,
                "recommended_group_count": 0,
                "adaptive_model_supported": False,
                "decision": "no_go",
                "ticker_outcome_counts": {"improve": 0, "neutral": 0, "worsen": 10},
                "notes": [
                    "Tidak ada konfigurasi adaptive yang lolos min_trades=8 sekaligus memperbaiki baseline secara konsisten."
                ],
            }
        ),
        encoding="utf-8",
    )


class FinalizePhaseBPostmortemTestCase(unittest.TestCase):
    """Validate postmortem artifact generation and strategic decision rules."""

    def test_postmortem_runs_when_some_artifacts_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()
            _write_transition(output_dir)
            _write_item5(output_dir)

            result = finalize_phase_b_postmortem(output_dir=output_dir)

            self.assertTrue(result["postmortem_json_path"].exists())
            self.assertTrue(result["postmortem_txt_path"].exists())
            self.assertTrue(result["root_cause_csv_path"].exists())
            self.assertTrue(result["final_status_path"].exists())
            self.assertTrue(result["next_phase_path"].exists())

            payload = json.loads(result["postmortem_json_path"].read_text(encoding="utf-8"))
            self.assertEqual("phase_b_keep_experimental", payload["phase_b_status"])
            self.assertIn("Phase B item 6 go/no-go JSON not found", " ".join(payload["artifact_gaps"]))

            with result["root_cause_csv_path"].open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(4, len(rows))

    def test_postmortem_generates_final_status_phase_c_decision_and_redesign(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "output"
            output_dir.mkdir()
            _write_transition(output_dir)
            _write_item5(output_dir)
            _write_item6(output_dir)
            _write_item7(output_dir)
            _write_item8(output_dir)

            result = finalize_phase_b_postmortem(output_dir=output_dir)

            final_status = json.loads(result["final_status_path"].read_text(encoding="utf-8"))
            self.assertEqual("phase_b_needs_redesign_before_continue", final_status["phase_b_status"])

            next_phase = json.loads(result["next_phase_path"].read_text(encoding="utf-8"))
            self.assertEqual("phase_c_no_go_yet", next_phase["phase_c_decision"])
            self.assertFalse(bool(next_phase["can_continue_to_phase_c"]))

            self.assertIsNotNone(result["redesign_paths"])
            self.assertTrue((output_dir / "phase_b_v2_redesign_plan.json").exists())
            self.assertTrue((output_dir / "phase_b_v2_redesign_plan.txt").exists())

            with result["root_cause_csv_path"].open(encoding="utf-8", newline="") as handle:
                rows = {row["item_id"]: row for row in csv.DictReader(handle)}
            self.assertEqual("signal_collapse", rows["item7"]["primary_root_cause"])
            self.assertEqual("adaptive_config_not_usable", rows["item8"]["primary_root_cause"])

            transition = json.loads(
                (output_dir / "phase_a_to_phase_b_transition.json").read_text(encoding="utf-8")
            )
            self.assertEqual("limited_experiment", transition["phase_b_entry_mode"])
            self.assertEqual("phase_b_needs_redesign_before_continue", transition["phase_b_status"])
            self.assertIn("redesign", transition["next_phase_recommendation"])


if __name__ == "__main__":
    unittest.main()
