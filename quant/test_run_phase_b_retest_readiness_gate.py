"""Tests for the formal Phase B retest-readiness gate."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from quant.run_phase_b_retest_readiness_gate import (
    NEWS_DISTRIBUTION_POLICY_REALIGNMENT_SUMMARY_OUTPUT,
    OOS_POLICY_ALIGNMENT_AUDIT_OUTPUT,
    run_phase_b_retest_readiness_gate,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class RunPhaseBRetestReadinessGateTestCase(unittest.TestCase):
    def _write_price_csv(self, path: Path, history_rows: int, article_days: set[int]) -> None:
        rows = []
        for i in range(history_rows):
            rows.append(
                {
                    "date": f"2026-01-{(i % 28) + 1:02d}",
                    "open": 100 + i,
                    "high": 101 + i,
                    "low": 99 + i,
                    "close": 100 + i,
                    "volume": 1000000 + i,
                    "sentiment_average_1d": 0,
                    "sentiment_weighted_1d": 0,
                    "sentiment_news_count_1d": 1 if i in article_days else 0,
                }
            )
        _write_csv(
            path,
            [
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "sentiment_average_1d",
                "sentiment_weighted_1d",
                "sentiment_news_count_1d",
            ],
            rows,
        )

    def _prepare_fixture(self, root: Path, scenario: str = "fail", include_noncritical_artifacts: bool = True) -> tuple[Path, Path, Path]:
        data_dir = root / "data"
        output_dir = root / "output"
        data_dir.mkdir()
        output_dir.mkdir()

        if scenario == "pass":
            tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
            history_rows = 120
            article_days_map = {
                "AAA": {2, 6, 10, 14, 18, 22},
                "BBB": {3, 7, 11, 15, 19, 23},
                "CCC": {4, 8, 12, 16, 20, 24},
                "DDD": {5, 9, 13, 17, 21, 25},
                "EEE": {26, 30, 34, 38, 42, 46},
                "FFF": {27, 31, 35, 39, 43, 47},
            }
            primary_trades = {"AAA": 3, "BBB": 3, "CCC": 3, "DDD": 3, "EEE": 3, "FFF": 3}
            primary_returns = {"AAA": 0.8, "BBB": 0.7, "CCC": 0.6, "DDD": 0.9, "EEE": 0.5, "FFF": 0.4}
            fold_trades = [6, 6, 6]
        else:
            tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
            history_rows = 57
            article_days_map = {
                "AAA": {2, 6},
                "BBB": {3},
                "CCC": {4},
                "DDD": {5},
                "EEE": set(),
                "FFF": {7},
            }
            primary_trades = {"AAA": 4, "BBB": 3, "CCC": 2, "DDD": 1, "EEE": 1, "FFF": 0}
            primary_returns = {"AAA": -1.5, "BBB": -0.9, "CCC": 0.2, "DDD": -0.4, "EEE": 0.1, "FFF": 0.0}
            fold_trades = [2, 3, 6]

        for ticker in tickers:
            self._write_price_csv(data_dir / f"{ticker}.csv", history_rows=history_rows, article_days=article_days_map[ticker])

        metadata_file = data_dir / "ticker_metadata.csv"
        metadata_rows = []
        segmentation_rows = []
        for ticker in tickers:
            article_days = len(article_days_map[ticker])
            metadata_rows.append(
                {
                    "ticker": ticker,
                    "sector": "generic",
                    "category": "general",
                    "company_name": f"{ticker} Tbk",
                    "interval_type": "1d",
                    "rows_1d": history_rows,
                    "date_start": "2026-01-01",
                    "date_end": "2026-06-30",
                    "sentiment_days_with_articles": article_days,
                    "sentiment_article_count_total": article_days,
                }
            )
            segmentation_rows.append(
                {
                    "ticker": ticker,
                    "rows": history_rows,
                    "date_start": "2026-01-01",
                    "date_end": "2026-06-30",
                    "article_count_total": article_days,
                    "article_days": article_days,
                    "news_density_pct": round((100.0 * article_days / history_rows), 4),
                    "news_segment": "mid_news" if ticker in {"AAA", "BBB", "CCC", "DDD"} else "high_news",
                    "sentiment_segment": "sentiment_poor",
                    "liquidity_segment": "thin_sparse" if ticker in {"AAA", "BBB", "CCC", "EEE"} else "liquid_active",
                    "volatility_segment": "mixed_volatility" if ticker in {"AAA", "BBB", "DDD", "EEE"} else "higher_volatility",
                    "history_rows": history_rows,
                }
            )

        _write_csv(
            metadata_file,
            [
                "ticker",
                "sector",
                "category",
                "company_name",
                "interval_type",
                "rows_1d",
                "date_start",
                "date_end",
                "sentiment_days_with_articles",
                "sentiment_article_count_total",
            ],
            metadata_rows,
        )
        _write_csv(
            output_dir / "baseline_v6_universe_segmentation.csv",
            [
                "ticker",
                "rows",
                "date_start",
                "date_end",
                "article_count_total",
                "article_days",
                "news_density_pct",
                "news_segment",
                "sentiment_segment",
                "liquidity_segment",
                "volatility_segment",
                "history_rows",
            ],
            segmentation_rows,
        )

        _write_json(
            output_dir / "baseline_v6_next_experiment_governance.json",
            {
                "segments_safe_to_test_next": [
                    "volatility_segment=mixed_volatility",
                    "sentiment_segment=sentiment_poor",
                    "liquidity_segment=thin_sparse",
                    "news_segment=mid_news",
                ]
            },
        )
        _write_json(
            output_dir / "phase_b_data_extension_audit.json",
            {
                "current_data_sufficiency_status": "insufficient_for_fair_strategy_retest" if scenario != "pass" else "sufficient",
                "history_length_assessment": {
                    "current_min_usable_oos_windows": 3 if scenario != "pass" else 8,
                },
            },
        )
        _write_json(
            output_dir / "framework_redesign_scope.json",
            {
                "evaluation_framework_redesign_required": True,
                "what_must_stay_fixed": [
                    "baseline aktif",
                    "logika entry/exit aktif",
                    "Phase C = phase_c_no_go_yet",
                ],
                "recommended_segment_policy": {
                    "segment_aware_evaluation_still_required_after_data_extension": True,
                    "global_promotion_allowed": False,
                },
                "recommended_preconditions_before_any_new_strategy_test": ["gate published"],
            },
        )
        _write_json(
            output_dir / "universe_reconstruction_precheck.json",
            {
                "universe_reconstruction_needed": True,
                "whether_current_universe_is_usable_for_any_fair_retest": scenario == "pass",
            },
        )
        _write_json(
            output_dir / "phase_b_final_closeout.json",
            {
                "phase_b_final_status": "phase_b_closed_with_learnings_no_candidate",
                "parked_items": [
                    "item5",
                    "item6",
                    "item7",
                    "item8",
                    "entry_relaxation_only",
                    "volume_relaxed_entry",
                    "exit_hold_only_redesign",
                    "segment-only promotion for current candidate",
                ],
                "can_continue_strategy_experiments_now": False,
            },
        )
        if include_noncritical_artifacts:
            _write_json(
                output_dir / "project_after_phase_b_decision.json",
                {
                    "phase_b_final_status": "phase_b_closed_with_learnings_no_candidate",
                    "recommended_primary_next_step": "stop_and_collect_more_data_then_redesign_framework",
                    "can_continue_strategy_experiments_now": False,
                },
            )
        _write_json(
            output_dir / "baseline_redesign_go_no_go.json",
            {
                "decision": "usable_for_framework_redesign_only" if scenario == "pass" else "improved_but_keep_experimental",
                "usable_for_framework_redesign": scenario == "pass",
            },
        )
        _write_json(
            output_dir / "baseline_v2_validation_go_no_go.json",
            {
                "decision": "candidate_usable_for_framework_redesign_only" if scenario == "pass" else "reject_candidate",
            },
        )
        _write_json(
            output_dir / "phase_b_v2_overlap_audit.json",
            {
                "overall_overlap_risk": "moderate" if scenario == "pass" else "high",
                "overall_conclusion": "overlap audited",
            },
        )
        _write_json(
            output_dir / "phase_b_v2_trade_design_audit.json",
            {
                "hold_period_diagnostics": [{"hold_period": 3}],
                "diagnosis_flags": {
                    "baseline_needs_entry_exit_redesign": scenario != "pass",
                },
            },
        )
        _write_json(
            output_dir / "baseline_v9_segment_oos_go_no_go.json",
            {
                "candidate_id": "baseline_v3_ema20_trend_guard",
                "primary_segment": "sentiment_segment=sentiment_poor",
                "decision": "no_go_even_for_segment" if scenario != "pass" else "keep_experimental_for_segment_only_use",
                "oos_stability_ok": scenario == "pass",
                "ticker_consistency_ok": scenario == "pass",
                "outlier_bias_ok": True,
                "global_promotion_allowed": False,
                "primary_total_trades_sum": sum(primary_trades.values()),
                "primary_active_ticker_count": sum(1 for value in primary_trades.values() if value > 0),
            },
        )
        _write_json(
            output_dir / "baseline_v9_segment_oos_summary.json",
            {
                "methodology": {
                    "warmup_bars": 21,
                    "fold_size_bars": 12,
                    "min_rows_across_tested_tickers": 57,
                },
                "decision": {"primary_segment": "sentiment_segment=sentiment_poor"},
            },
        )
        _write_json(
            output_dir / "project_roadmap_status.json",
            {
                "latest_execution_status": {"phase_c_decision": "phase_c_no_go_yet"},
            },
        )
        density_values = [round((100.0 * len(article_days_map[ticker]) / history_rows), 4) for ticker in tickers]
        actual_median_density = sorted(density_values)[len(density_values) // 2 - 1 if len(density_values) % 2 == 0 else len(density_values) // 2]
        if len(density_values) % 2 == 0:
            actual_median_density = round(
                (sorted(density_values)[len(density_values) // 2 - 1] + sorted(density_values)[len(density_values) // 2]) / 2.0,
                4,
            )
        _write_json(
            output_dir / "phase_b_news_distribution_threshold_audit.json",
            {
                "official_distribution_universe": {
                    "density_gate_scope": "current ticker universe from data/ticker_metadata.csv used by news_distribution_gate::median_news_density_pct",
                    "density_gate_tickers": tickers,
                    "density_gate_ticker_count": len(tickers),
                    "primary_distribution_pool_scope": "sentiment_segment=sentiment_poor",
                    "primary_distribution_pool_tickers": tickers,
                    "primary_distribution_pool_ticker_count": len(tickers),
                },
                "actual_median_density": actual_median_density,
                "threshold_density": 5.0,
                "gap_to_threshold": round(5.0 - actual_median_density, 4),
                "distribution_statistics": {
                    "actual_median_density": actual_median_density,
                    "actual_mean_density": round(sum(density_values) / len(density_values), 4),
                    "actual_min_density": min(density_values),
                    "actual_max_density": max(density_values),
                    "actual_density_range": round(max(density_values) - min(density_values), 4),
                    "actual_median_article_days": round(
                        (
                            sorted(len(article_days_map[t]) for t in tickers)[len(tickers) // 2 - 1]
                            + sorted(len(article_days_map[t]) for t in tickers)[len(tickers) // 2]
                        )
                        / 2.0,
                        4,
                    ) if len(tickers) % 2 == 0 else float(sorted(len(article_days_map[t]) for t in tickers)[len(tickers) // 2]),
                },
                "threshold_realism_assessment": {
                    "status": "incompatible" if actual_median_density < 5.0 else "compatible",
                },
                "operational_feasibility_assessment": {
                    "current_ticker_count_at_or_above_threshold": sum(1 for item in density_values if item >= 5.0),
                    "minimum_tickers_needed_at_or_above_threshold_for_median_pass": 4,
                    "minimum_additional_article_days_total_for_cheapest_path": 0 if actual_median_density >= 5.0 else 24,
                    "threshold_article_days_required_for_typical_ticker": 6 if history_rows == 120 else 3,
                },
            },
        )
        _write_json(
            output_dir / "phase_b_news_distribution_policy_alignment_audit.json",
            {
                "compatibility_assessment": {
                    "status": "incompatible" if actual_median_density < 5.0 else "compatible",
                },
                "recommended_policy_path": {
                    "policy_path": "hybrid_keep_share_controls_realign_density_component_with_sparse_coverage_metric_or_threshold",
                    "requires_gate_policy_change": actual_median_density < 5.0,
                    "requires_strategy_or_oos_change": False,
                    "rationale": [
                        "Masalah eksplisit ada pada density subcheck.",
                    ],
                },
            },
        )

        result_rows = []
        for ticker in tickers:
            result_rows.append(
                {
                    "row_type": "ticker_oos_summary",
                    "tested_segment": "sentiment_segment=sentiment_poor",
                    "ticker": ticker,
                    "candidate_total_trades": primary_trades[ticker],
                    "candidate_signal_count": primary_trades[ticker] + 1,
                    "average_return": primary_returns[ticker],
                }
            )
        for index, trades in enumerate(fold_trades, start=1):
            result_rows.append(
                {
                    "row_type": "segment_fold",
                    "tested_segment": "sentiment_segment=sentiment_poor",
                    "ticker": "__segment__",
                    "fold_id": index,
                    "candidate_total_trades": trades,
                    "candidate_signal_count": trades,
                    "average_return": 0,
                }
            )
        _write_csv(
            output_dir / "baseline_v9_segment_oos_results.csv",
            ["row_type", "tested_segment", "ticker", "fold_id", "candidate_total_trades", "candidate_signal_count", "average_return"],
            result_rows,
        )
        return data_dir, output_dir, metadata_file

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir), scenario="fail")
            result = run_phase_b_retest_readiness_gate(data_dir=data_dir, output_dir=output_dir, metadata_file=metadata_file)

            for name in [
                "phase_b_retest_readiness_gate.json",
                "phase_b_retest_readiness_gate.txt",
                "phase_b_retest_readiness_thresholds.csv",
                "phase_b_retest_blockers_ranked.csv",
                "phase_b_retest_next_requirements.json",
                "phase_b_readiness_blocker_audit.json",
                "phase_b_readiness_recovery_audit.json",
                "phase_b_distribution_fairness_audit.json",
                "phase_b_primary_poor_distribution_target_audit.json",
                "phase_b_oos_fairness_recovery_audit.json",
                "phase_b_oos_source_of_truth_audit.json",
                "phase_b_oos_window_recovery_plan.json",
                OOS_POLICY_ALIGNMENT_AUDIT_OUTPUT,
                "phase_b_readiness_policy_realignment_summary.json",
                NEWS_DISTRIBUTION_POLICY_REALIGNMENT_SUMMARY_OUTPUT,
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertEqual("belum_boleh_retest", result["phase_b_retest_readiness_gate"]["final_decision"])
            self.assertTrue(result["phase_b_retest_readiness_gate"]["policy_realignment_applied"])
            self.assertTrue(result["phase_b_retest_readiness_gate"]["news_distribution_policy_realignment_applied"])
            self.assertTrue(result["phase_b_retest_readiness_gate"]["density_component_realigned"])
            self.assertEqual(5.0, result["phase_b_retest_readiness_gate"]["pre_realignment_density_threshold"])
            self.assertEqual(
                3,
                result["phase_b_retest_readiness_gate"]["methodology_aligned_thresholds"]["history_gate::usable_oos_windows_per_ticker"],
            )
            self.assertEqual(
                1.7544,
                result["phase_b_retest_readiness_gate"]["post_realignment_density_threshold"],
            )
            audit = result["phase_b_readiness_blocker_audit"]
            self.assertEqual("output/phase_b_retest_readiness_gate.json", audit["source_of_truth_artifact"])
            self.assertTrue(audit["active_blockers"])
            sample = audit["active_blockers"][0]
            for field in [
                "blocker_name",
                "source_of_truth_artifact",
                "source_field",
                "actual_value",
                "target_value",
                "status",
                "recommended_fix",
            ]:
                self.assertIn(field, sample)
            recovery = result["phase_b_readiness_recovery_audit"]
            self.assertEqual("output/phase_b_retest_readiness_gate.json", recovery["source_of_truth_artifact"])
            self.assertIn("history_extension_status", recovery)
            self.assertIn("coverage_ready_status", recovery)
            self.assertIn("single_ticker_article_share_status", recovery)
            self.assertTrue(recovery["coverage_ready_status"]["coverage_ready_ticker_breakdown"])
            distribution = result["phase_b_distribution_fairness_audit"]
            self.assertEqual("output/phase_b_retest_readiness_gate.json", distribution["source_of_truth_artifact"])
            self.assertIn("distribution_status", distribution)
            self.assertIn("fairness_status", distribution)
            self.assertTrue(distribution["distribution_status"]["per_ticker_primary_distribution"])
            primary_poor = result["phase_b_primary_poor_distribution_target_audit"]
            self.assertTrue(primary_poor["rows"])
            self.assertIn("included_in_official_primary_poor", primary_poor["rows"][0])
            fairness_recovery = result["phase_b_oos_fairness_recovery_audit"]
            self.assertIn("trade_count_by_fold_after", fairness_recovery)
            oos_source = result["phase_b_oos_source_of_truth_audit"]
            self.assertEqual("output/baseline_v9_segment_oos_summary.json", oos_source["source_of_truth_oos_final"]["methodology_artifact"])
            self.assertIn("fold_size_bars", oos_source["current_v9_official_basis"])
            self.assertIn("progress_update_matches_readiness", oos_source["cross_artifact_consistency"])
            oos_window_plan = result["phase_b_oos_window_recovery_plan"]
            self.assertEqual(6, oos_window_plan["target_windows"])
            self.assertIn("target_reachable_under_current_methodology", oos_window_plan)
            policy_audit = result["phase_b_oos_policy_alignment_audit"]
            self.assertTrue(policy_audit["policy_realignment_applied"])
            self.assertEqual("incompatible", policy_audit["pre_realignment_compatibility_status"])
            self.assertEqual("compatible", policy_audit["compatibility_status"])
            self.assertEqual(3, policy_audit["theoretical_maximum_under_current_methodology"]["usable_oos_windows_per_ticker"])
            self.assertEqual(3, policy_audit["methodology_aligned_thresholds"]["history_gate::usable_oos_windows_per_ticker"])
            self.assertEqual(0, policy_audit["methodology_aligned_thresholds"]["history_gate::additional_bars_from_v9_baseline"])
            self.assertEqual("C", policy_audit["recommended_policy_path"]["option_id"])
            self.assertFalse(policy_audit["roadmap_update_assessment"]["ready_for_retest"])
            residual_names = [item["blocker_name"] for item in policy_audit["remaining_active_blockers_even_if_window_policy_is_aligned"]]
            self.assertNotIn("history_gate::usable_oos_windows_per_ticker", residual_names)
            self.assertNotIn("oos_fairness_gate::primary_segment_usable_oos_windows", residual_names)
            self.assertNotIn("history_gate::additional_bars_from_v9_baseline", residual_names)
            self.assertNotIn("news_distribution_gate::median_news_density_pct", residual_names)
            realignment_summary = result["phase_b_readiness_policy_realignment_summary"]
            self.assertTrue(realignment_summary["policy_realignment_applied"])
            threshold_change_lookup = {
                item["threshold_name"]: (item["old_target"], item["new_target"])
                for item in realignment_summary["threshold_changes"]
            }
            self.assertEqual((63, 0), threshold_change_lookup["history_gate::additional_bars_from_v9_baseline"])
            self.assertEqual((6, 3), threshold_change_lookup["history_gate::usable_oos_windows_per_ticker"])
            self.assertEqual((6, 3), threshold_change_lookup["oos_fairness_gate::primary_segment_usable_oos_windows"])
            self.assertEqual((5.0, 1.7544), threshold_change_lookup["news_distribution_gate::median_news_density_pct"])
            self.assertEqual(
                [
                    "history_gate::additional_bars_from_v9_baseline actual=0 target>=63",
                    "history_gate::usable_oos_windows_per_ticker actual=3 target>=6",
                    "news_distribution_gate::median_news_density_pct actual=1.7544 target>=5.0",
                    "oos_fairness_gate::primary_segment_usable_oos_windows actual=3 target>=6",
                ],
                realignment_summary["blockers_removed_by_policy_conflict_resolution"],
            )
            self.assertFalse(realignment_summary["strategy_retest_allowed_after_policy_realignment"])
            density_summary = result["phase_b_news_distribution_policy_realignment_summary"]
            self.assertTrue(density_summary["news_distribution_policy_realignment_applied"])
            self.assertTrue(density_summary["share_control_policy_unchanged"])
            self.assertEqual(5.0, density_summary["old_density_policy"]["target_value"])
            self.assertEqual(1.7544, density_summary["new_density_policy"]["target_value"])

    def test_one_failed_gate_is_enough_to_block_retest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir), scenario="pass")
            gate_payload = json.loads((output_dir / "baseline_v9_segment_oos_go_no_go.json").read_text(encoding="utf-8"))
            gate_payload["primary_total_trades_sum"] = 17
            _write_json(output_dir / "baseline_v9_segment_oos_go_no_go.json", gate_payload)

            result = run_phase_b_retest_readiness_gate(data_dir=data_dir, output_dir=output_dir, metadata_file=metadata_file)

            self.assertEqual("FAIL", result["phase_b_retest_readiness_gate"]["oos_fairness_gate"])
            self.assertEqual("belum_boleh_retest", result["phase_b_retest_readiness_gate"]["final_decision"])

    def test_all_mock_thresholds_pass_still_keeps_strategy_retry_blocked_without_official_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir), scenario="pass")

            result = run_phase_b_retest_readiness_gate(data_dir=data_dir, output_dir=output_dir, metadata_file=metadata_file)

            payload = result["phase_b_retest_readiness_gate"]
            self.assertEqual("PASS", payload["history_gate"])
            self.assertEqual("PASS", payload["universe_coverage_gate"])
            self.assertEqual("PASS", payload["news_distribution_gate"])
            self.assertEqual("PASS", payload["oos_fairness_gate"])
            self.assertEqual("FAIL", payload["framework_governance_gate"])
            self.assertEqual("PASS", payload["roadmap_discipline_gate"])
            self.assertEqual("belum_boleh_retest", payload["final_decision"])
            self.assertTrue(payload["strategy_retry_still_blocked_by_official_closeout"])
            audit = result["phase_b_readiness_blocker_audit"]
            self.assertTrue(any(item["blocker_name"] == "framework_governance_gate::official_strategy_retry_reopened" for item in audit["active_blockers"]))
            self.assertFalse(payload["news_distribution_policy_realignment_applied"])
            recovery = result["phase_b_readiness_recovery_audit"]
            self.assertEqual(1.0, recovery["coverage_ready_status"]["coverage_ready_ticker_ratio"]["after"])
            self.assertTrue(recovery["history_extension_status"]["history_gate_closed_now"])
            distribution = result["phase_b_distribution_fairness_audit"]
            self.assertEqual(True, distribution["distribution_status"]["news_distribution_gate_closed"])
            primary_poor = result["phase_b_primary_poor_distribution_target_audit"]
            self.assertTrue(all(row["included_in_official_primary_poor"] for row in primary_poor["rows"]))

    def test_script_still_runs_when_noncritical_artifacts_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(
                Path(tmp_dir),
                scenario="fail",
                include_noncritical_artifacts=False,
            )

            result = run_phase_b_retest_readiness_gate(data_dir=data_dir, output_dir=output_dir, metadata_file=metadata_file)

            self.assertEqual("belum_boleh_retest", result["phase_b_retest_readiness_gate"]["final_decision"])
            self.assertTrue((output_dir / "phase_b_retest_readiness_thresholds.csv").exists())
            self.assertTrue(any("project_after_phase_b_decision.json not found" in item for item in result["phase_b_retest_readiness_gate"]["limitations"]))

    def test_previous_blocker_snapshot_marks_newly_closed_thresholds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir), scenario="pass")
            _write_json(
                output_dir / "phase_b_retest_readiness_gate.json",
                {
                    "final_decision": "belum_boleh_retest",
                    "highest_blocking_gate": "history_gate",
                    "blocking_thresholds": [
                        "history_gate::usable_oos_windows_per_ticker actual=3 target>=6",
                        "oos_fairness_gate::total_oos_trades_primary_segment actual=11 target>=18",
                    ],
                },
            )

            result = run_phase_b_retest_readiness_gate(data_dir=data_dir, output_dir=output_dir, metadata_file=metadata_file)

            audit = result["phase_b_readiness_blocker_audit"]
            self.assertIn("history_gate::usable_oos_windows_per_ticker actual=3 target>=6", audit["newly_closed_blockers"])
            self.assertIn("oos_fairness_gate::total_oos_trades_primary_segment actual=11 target>=18", audit["newly_closed_blockers"])
            recovery = result["phase_b_readiness_recovery_audit"]
            self.assertIn("before", recovery["history_extension_status"]["min_history_bars_per_ticker"])
            distribution = result["phase_b_distribution_fairness_audit"]
            self.assertIn("total_oos_trades_primary_segment_after", distribution["fairness_status"])
            fairness_recovery = result["phase_b_oos_fairness_recovery_audit"]
            self.assertIn("dominant_fold_share_after", fairness_recovery)
            oos_source = result["phase_b_oos_source_of_truth_audit"]
            self.assertTrue(oos_source["basis_change_valid"])
            oos_window_plan = result["phase_b_oos_window_recovery_plan"]
            self.assertIn("after", oos_window_plan)
            self.assertIn("minimum_rows_required_for_6_windows", oos_window_plan)
            realignment_summary = result["phase_b_readiness_policy_realignment_summary"]
            threshold_change_lookup = {
                item["threshold_name"]: (item["old_target"], item["new_target"])
                for item in realignment_summary["threshold_changes"]
            }
            self.assertEqual((6, 3), threshold_change_lookup["history_gate::usable_oos_windows_per_ticker"])


if __name__ == "__main__":
    unittest.main()
