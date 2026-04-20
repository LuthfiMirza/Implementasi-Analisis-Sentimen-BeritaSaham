"""Tests for Phase B v2 redesign diagnostics."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.bootstrap_sample_data import bootstrap_sample_dataset
from quant.run_phase_b_v2_redesign_diagnostics import run_phase_b_v2_redesign_diagnostics


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


def _enrich_sentiment_columns(data_dir: Path) -> None:
    for index, path in enumerate(sorted(data_dir.glob("*.csv"))):
        frame = pd.read_csv(path)
        if path.stem == "BBCA":
            frame["sentiment_average_1d"] = [0.4 if i % 25 == 0 else 0.0 for i in range(len(frame))]
            frame["sentiment_weighted_1d"] = [0.5 if i % 25 == 0 else 0.0 for i in range(len(frame))]
            frame["sentiment_news_count_1d"] = [1 if i % 25 == 0 else 0 for i in range(len(frame))]
        elif path.stem == "BMRI":
            frame["sentiment_average_1d"] = [((i % 10) - 5) / 20 for i in range(len(frame))]
            frame["sentiment_weighted_1d"] = [((i % 8) - 4) / 18 for i in range(len(frame))]
            frame["sentiment_news_count_1d"] = [1 if i % 7 == 0 else 0 for i in range(len(frame))]
        else:
            frame["sentiment_average_1d"] = [((i % 6) - 3) / 12 for i in range(len(frame))]
            frame["sentiment_weighted_1d"] = [((i % 5) - 2) / 10 for i in range(len(frame))]
            frame["sentiment_news_count_1d"] = [2 if i % 5 == 0 else 0 for i in range(len(frame))]
        frame.to_csv(path, index=False)


def _write_phase_b_artifacts(output_dir: Path) -> None:
    (output_dir / "phase_b_item5_go_no_go.json").write_text(
        json.dumps(
            {
                "decision": "no_go",
                "best_global_threshold": 1.5,
                "blocked_from_default": [
                    "Semua threshold yang diuji collapse ke effective confirmation threshold 1.5 karena baseline Phase A aktif sudah menuntut volume_ratio minimal itu."
                ],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "phase_b_item5_recommendations.txt").write_text(
        "Phase B Item 5 Recommendations\n- Decision: no_go\n",
        encoding="utf-8",
    )
    (output_dir / "phase_b_item7_data_readiness.json").write_text(
        json.dumps(
            {
                "valid_ticker_count": 2,
                "unusable_ticker_count": 1,
                "dataset_is_item7_ready": True,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "phase_b_item8_go_no_go.json").write_text(
        json.dumps({"decision": "no_go", "adaptive_model_supported": False}),
        encoding="utf-8",
    )
    (output_dir / "phase_b_item8_global_summary.json").write_text(
        json.dumps(
            {
                "thresholds_tested": [1.5, 2.0, 2.5],
                "strict_options_tested": [False, True],
                "eligible_best_ticker_count": 0,
                "adaptive_model_supported": False,
            }
        ),
        encoding="utf-8",
    )


class RunPhaseBV2RedesignDiagnosticsTestCase(unittest.TestCase):
    """Validate minimum redesign toolkit artifacts."""

    def test_redesign_diagnostics_generate_all_required_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = output_dir / "phase_a_baseline_final.json"
            metadata_path = data_dir / "ticker_metadata.csv"
            output_dir.mkdir()

            bootstrap_sample_dataset(data_dir=data_dir, rows=140)
            _enrich_sentiment_columns(data_dir)
            _write_baseline(baseline_path)
            _write_metadata(metadata_path)
            _write_phase_b_artifacts(output_dir)

            run_phase_b_v2_redesign_diagnostics(
                data_dir=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                metadata_file=metadata_path,
                hold_period_options=[3, 5, 7],
                min_trades_options=[5, 8, 10],
            )

            required_paths = [
                output_dir / "phase_b_v2_overlap_audit.json",
                output_dir / "phase_b_v2_overlap_audit.txt",
                output_dir / "phase_b_v2_trade_design_audit.json",
                output_dir / "phase_b_v2_trade_design_audit.txt",
                output_dir / "phase_b_v2_sample_coverage.csv",
                output_dir / "phase_b_v2_sample_coverage_summary.json",
                output_dir / "phase_b_v2_sentiment_relevance.csv",
                output_dir / "phase_b_v2_sentiment_relevance_summary.json",
                output_dir / "phase_b_v2_sentiment_relevance_report.txt",
                output_dir / "phase_b_v2_redesign_decision.json",
                output_dir / "phase_b_v2_redesign_decision.txt",
                output_dir / "phase_b_v2_next_best_experiment.json",
                output_dir / "phase_b_v2_next_best_experiment.txt",
            ]
            for path in required_paths:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            overlap = json.loads((output_dir / "phase_b_v2_overlap_audit.json").read_text(encoding="utf-8"))
            self.assertIn("overall_overlap_risk", overlap)

            trade_audit = json.loads((output_dir / "phase_b_v2_trade_design_audit.json").read_text(encoding="utf-8"))
            self.assertIn("hold_period_diagnostics", trade_audit)

            sample_summary = json.loads(
                (output_dir / "phase_b_v2_sample_coverage_summary.json").read_text(encoding="utf-8")
            )
            self.assertIn("recommended_realistic_min_trades", sample_summary)

            sentiment_summary = json.loads(
                (output_dir / "phase_b_v2_sentiment_relevance_summary.json").read_text(encoding="utf-8")
            )
            self.assertIn("verdict", sentiment_summary)

            redesign_decision = json.loads(
                (output_dir / "phase_b_v2_redesign_decision.json").read_text(encoding="utf-8")
            )
            self.assertIn("primary_failure_mode", redesign_decision)
            self.assertIn("next_experiment_after_redesign", redesign_decision)

            next_experiment = json.loads(
                (output_dir / "phase_b_v2_next_best_experiment.json").read_text(encoding="utf-8")
            )
            self.assertIn("selected_experiment_code", next_experiment)
            self.assertTrue(next_experiment["selected_experiment_code"])


if __name__ == "__main__":
    unittest.main()
