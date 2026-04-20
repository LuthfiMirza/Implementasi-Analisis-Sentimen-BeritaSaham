"""Tests for the baseline v6 guardrail review and universe segmentation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_baseline_v6_guardrail_review import (
    GOVERNANCE_OUTPUT,
    REVIEW_JSON_OUTPUT,
    REVIEW_TEXT_OUTPUT,
    SCENARIO_CSV_OUTPUT,
    SEGMENTATION_CSV_OUTPUT,
    SEGMENT_RECOMMENDATIONS_OUTPUT,
    RECOMMENDED_GUARDRAIL_MODES,
    RECOMMENDED_UNIVERSE_MODES,
    run_baseline_v6_guardrail_review,
)


def _write_price_csv(path: Path, base_volume: int, article_pattern: list[int], start_price: float) -> None:
    rows = len(article_pattern)
    dates = pd.date_range("2026-01-02", periods=rows, freq="B")
    close = [start_price + (index * 0.5) for index in range(rows)]
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": [value * 1.01 for value in close],
            "low": [value * 0.99 for value in close],
            "close": close,
            "volume": [base_volume + (index * 1000) for index in range(rows)],
            "sentiment_news_count_1d": article_pattern,
        }
    )
    frame.to_csv(path, index=False)


def _write_metadata(path: Path, minimal: bool = False) -> None:
    base = pd.DataFrame(
        {
            "ticker": ["BBCA", "BMRI", "TLKM", "GOTO", "UNVR", "INDF"],
            "sector": ["finance", "finance", "telco", "technology", "consumer", "consumer"],
            "category": ["bank", "bank", "telco", "internet", "consumer", "consumer"],
            "company_name": [
                "Bank Central Asia",
                "Bank Mandiri",
                "Telkom Indonesia",
                "GoTo",
                "Unilever Indonesia",
                "Indofood Sukses Makmur",
            ],
        }
    )
    if minimal:
        base = base[["ticker"]]
    base.to_csv(path, index=False)


def _write_context(output_dir: Path) -> None:
    (output_dir / "baseline_root_cause_postmortem.json").write_text(
        json.dumps(
            {
                "recommended_primary_direction": "revisit_eligibility_and_sample_guardrails",
                "recommended_secondary_direction_1": "revisit_ticker_universe_segmentation",
                "recommended_secondary_direction_2": "revisit_fast_anchor_with_better_quality_gate",
                "what_to_stop": ["item5", "item6", "item7", "item8", "entry_relaxation_only"],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_next_experiment_plan.json").write_text(
        json.dumps(
            {
                "recommended_primary_direction": "revisit_eligibility_and_sample_guardrails",
                "recommended_secondary_direction_1": "revisit_ticker_universe_segmentation",
                "what_to_stop": ["item5", "item6", "item7", "item8", "entry_relaxation_only"],
                "what_not_to_change": ["baseline aktif", "Phase C"],
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v2_validation.json").write_text(
        json.dumps(
            {
                "candidate_id": "baseline_v2_hold3_with_trend_guard",
                "min_trades": 5,
                "eligible_ticker_count": 1,
                "min_eligible_tickers_required": 3,
                "total_trades_sum": 9,
                "minimum_trade_sample_required": 15,
                "average_return": 1.75,
                "score_ok": False,
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "baseline_v3_signal_rule_summary.json").write_text(
        json.dumps(
            {
                "best_v3_rule": {
                    "candidate_id": "baseline_v3_ema20_trend_guard",
                    "eligible_ticker_count": 3,
                    "total_trades_sum": 19,
                    "mean_average_return": -0.25,
                    "quality_preserved": False,
                }
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
                    "total_trades_sum": 13,
                    "mean_average_return": 4.25,
                },
                "go_no_go": {"quality_preserved": True},
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
                    "total_trades_sum": 8,
                    "mean_average_return": 0.25,
                },
                "go_no_go": {"quality_preserved": False},
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "project_roadmap_status.json").write_text(
        json.dumps(
            {
                "latest_execution_status": {
                    "phase_a_status": "closed_with_notes",
                    "phase_b_status": "phase_b_needs_redesign_before_continue",
                    "phase_c_decision": "phase_c_no_go_yet",
                    "current_track": "redesign_baseline_v2_again",
                }
            }
        ),
        encoding="utf-8",
    )


def _write_candidate_results(output_dir: Path) -> None:
    pd.DataFrame(
        {
            "ticker": ["BBCA", "BMRI", "TLKM", "GOTO", "UNVR", "INDF"],
            "candidate_id": ["baseline_v2_hold3_with_trend_guard"] * 6,
            "candidate_total_trades": [5, 1, 3, 0, 2, 5],
            "candidate_eligible_for_analysis": [True, False, False, False, False, True],
            "candidate_average_return": [-3.0, 2.0, 8.0, 0.0, 4.0, -2.0],
            "candidate_score": [4.0, -20.0, 10.0, -34.0, 8.0, 3.0],
            "min_trades_threshold": [5, 5, 5, 5, 5, 5],
        }
    ).to_csv(output_dir / "baseline_v2_validation_per_ticker.csv", index=False)

    pd.DataFrame(
        {
            "ticker": ["BBCA", "BMRI", "TLKM", "GOTO", "UNVR", "INDF"],
            "rule_id": ["baseline_v3_ema20_trend_guard"] * 6,
            "candidate_total_trades": [5, 6, 5, 3, 5, 5],
            "candidate_eligible_for_analysis": [True, True, True, False, True, True],
            "average_return": [3.0, -3.0, 4.0, -5.0, 2.0, -4.0],
            "score": [12.0, 5.0, 15.0, -10.0, 9.0, 4.0],
            "min_trades_threshold": [5, 5, 5, 5, 5, 5],
        }
    ).to_csv(output_dir / "baseline_v3_signal_rule_results.csv", index=False)

    pd.DataFrame(
        {
            "ticker": ["BBCA", "BMRI", "TLKM", "GOTO", "UNVR", "INDF"],
            "variant_id": ["baseline_v4_quality_gate_guard"] * 6,
            "candidate_total_trades": [6, 0, 5, 2, 2, 5],
            "candidate_eligible_for_analysis": [True, False, True, False, False, True],
            "average_return": [-2.0, 0.0, -1.0, 20.0, 3.0, -2.0],
            "score": [6.0, -34.0, 7.0, 40.0, 11.0, 5.0],
            "min_trades_threshold": [5, 5, 5, 5, 5, 5],
        }
    ).to_csv(output_dir / "baseline_v4_quality_gate_results.csv", index=False)

    pd.DataFrame(
        {
            "ticker": ["BBCA", "BMRI", "TLKM", "GOTO", "UNVR", "INDF"],
            "variant_id": ["baseline_v5_hold4_extension"] * 6,
            "candidate_total_trades": [2, 2, 3, 1, 2, 4],
            "candidate_eligible_for_analysis": [False, False, False, False, False, False],
            "average_return": [1.0, -2.0, 1.5, 0.5, 0.8, -0.3],
            "score": [2.0, -6.0, 4.0, -1.0, 1.5, -2.0],
            "min_trades_threshold": [5, 5, 5, 5, 5, 5],
        }
    ).to_csv(output_dir / "baseline_v5_exit_hold_results.csv", index=False)


class RunBaselineV6GuardrailReviewTestCase(unittest.TestCase):
    def _prepare_fixture(self, root: Path, minimal_metadata: bool = False, skip_some_artifacts: bool = False) -> tuple[Path, Path, Path]:
        data_dir = root / "data"
        output_dir = root / "output"
        data_dir.mkdir()
        output_dir.mkdir()

        _write_price_csv(data_dir / "BBCA.csv", base_volume=1_500_000, article_pattern=[1] + [0] * 23, start_price=100.0)
        _write_price_csv(data_dir / "BMRI.csv", base_volume=3_000_000, article_pattern=[1, 0, 1, 0, 1, 0, 1] + [0] * 17, start_price=110.0)
        _write_price_csv(data_dir / "TLKM.csv", base_volume=900_000, article_pattern=[1, 0, 0, 1] + [0] * 20, start_price=90.0)
        _write_price_csv(data_dir / "GOTO.csv", base_volume=650_000, article_pattern=[1, 0, 1, 0, 1, 0] + [0] * 18, start_price=70.0)
        _write_price_csv(data_dir / "UNVR.csv", base_volume=700_000, article_pattern=[1, 0] + [0] * 22, start_price=82.0)
        _write_price_csv(data_dir / "INDF.csv", base_volume=2_400_000, article_pattern=[1, 0, 1, 0, 1, 0] + [0] * 18, start_price=95.0)
        _write_metadata(data_dir / "ticker_metadata.csv", minimal=minimal_metadata)
        _write_candidate_results(output_dir)

        if not skip_some_artifacts:
            _write_context(output_dir)
        else:
            (output_dir / "baseline_v2_validation.json").write_text(
                json.dumps(
                    {
                        "candidate_id": "baseline_v2_hold3_with_trend_guard",
                        "min_trades": 5,
                        "min_eligible_tickers_required": 3,
                        "minimum_trade_sample_required": 15,
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "baseline_v3_signal_rule_summary.json").write_text(
                json.dumps({"best_v3_rule": {"candidate_id": "baseline_v3_ema20_trend_guard"}}),
                encoding="utf-8",
            )
            (output_dir / "baseline_v4_quality_gate_summary.json").write_text(
                json.dumps({"best_v4_candidate_summary": {"candidate_id": "baseline_v4_quality_gate_guard"}}),
                encoding="utf-8",
            )
            (output_dir / "baseline_v5_exit_hold_summary.json").write_text(
                json.dumps({"best_v5_candidate_summary": {"candidate_id": "baseline_v5_hold4_extension"}}),
                encoding="utf-8",
            )
            (output_dir / "project_roadmap_status.json").write_text(
                json.dumps(
                    {
                        "latest_execution_status": {
                            "phase_a_status": "closed_with_notes",
                            "phase_b_status": "phase_b_needs_redesign_before_continue",
                            "phase_c_decision": "phase_c_no_go_yet",
                        }
                    }
                ),
                encoding="utf-8",
            )

        return data_dir, output_dir, data_dir / "ticker_metadata.csv"

    def test_guardrail_review_generates_outputs_and_explicit_governance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file = self._prepare_fixture(root)

            result = run_baseline_v6_guardrail_review(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            required = [
                output_dir / REVIEW_JSON_OUTPUT,
                output_dir / REVIEW_TEXT_OUTPUT,
                output_dir / SCENARIO_CSV_OUTPUT,
                output_dir / SEGMENTATION_CSV_OUTPUT,
                output_dir / SEGMENT_RECOMMENDATIONS_OUTPUT,
                output_dir / GOVERNANCE_OUTPUT,
            ]
            for path in required:
                self.assertTrue(path.exists(), f"Missing artifact: {path}")

            governance = json.loads((output_dir / GOVERNANCE_OUTPUT).read_text(encoding="utf-8"))
            self.assertIn(governance["recommended_guardrail_mode"], RECOMMENDED_GUARDRAIL_MODES)
            self.assertIn(governance["recommended_universe_mode"], RECOMMENDED_UNIVERSE_MODES)
            self.assertEqual("move_to_segment_aware_guardrail", governance["recommended_guardrail_mode"])
            self.assertEqual("split_universe_before_next_experiment", governance["recommended_universe_mode"])
            self.assertTrue(governance["global_guardrail_still_valid"])
            self.assertTrue(governance["segment_aware_evaluation_recommended"])

            scenarios = pd.read_csv(output_dir / SCENARIO_CSV_OUTPUT)
            self.assertFalse(scenarios.empty)
            self.assertIn("scenario_c_segment_aware_guardrail", set(scenarios["scenario_id"]))
            self.assertIn("scenario_d_supporting_evidence_rule", set(scenarios["scenario_id"]))
            self.assertIn("keep_experimental_for_segment_review", set(scenarios["status"]))

            segmentation = pd.read_csv(output_dir / SEGMENTATION_CSV_OUTPUT)
            self.assertIn("news_segment", segmentation.columns)
            self.assertIn("liquidity_segment", segmentation.columns)
            self.assertIn("sector", segmentation.columns)

            review_payload = json.loads((output_dir / REVIEW_JSON_OUTPUT).read_text(encoding="utf-8"))
            self.assertIn("decisive_statement", review_payload)
            self.assertIn("Universe terlalu heterogen", review_payload["decisive_statement"])
            self.assertIn("artifacts", result)

    def test_review_still_runs_with_missing_artifacts_and_minimal_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file = self._prepare_fixture(
                root,
                minimal_metadata=True,
                skip_some_artifacts=True,
            )

            run_baseline_v6_guardrail_review(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            review_payload = json.loads((output_dir / REVIEW_JSON_OUTPUT).read_text(encoding="utf-8"))
            self.assertTrue((output_dir / REVIEW_TEXT_OUTPUT).exists())
            self.assertTrue((output_dir / SEGMENT_RECOMMENDATIONS_OUTPUT).exists())
            self.assertTrue((output_dir / SCENARIO_CSV_OUTPUT).exists())
            self.assertTrue((output_dir / SEGMENTATION_CSV_OUTPUT).exists())
            self.assertTrue(review_payload["artifact_gaps"])
            self.assertTrue(review_payload["limitations"])
            limitation_text = " ".join(str(item) for item in review_payload["limitations"])
            self.assertIn("sector", limitation_text.lower())


if __name__ == "__main__":
    unittest.main()
