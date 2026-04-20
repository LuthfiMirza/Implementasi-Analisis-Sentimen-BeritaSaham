"""Tests for the formal Phase B retest-readiness gate."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from quant.run_phase_b_retest_readiness_gate import run_phase_b_retest_readiness_gate


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
            },
        )
        if include_noncritical_artifacts:
            _write_json(
                output_dir / "project_after_phase_b_decision.json",
                {
                    "phase_b_final_status": "phase_b_closed_with_learnings_no_candidate",
                    "recommended_primary_next_step": "stop_and_collect_more_data_then_redesign_framework",
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
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertEqual("belum_boleh_retest", result["phase_b_retest_readiness_gate"]["final_decision"])

    def test_one_failed_gate_is_enough_to_block_retest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir), scenario="pass")
            gate_payload = json.loads((output_dir / "baseline_v9_segment_oos_go_no_go.json").read_text(encoding="utf-8"))
            gate_payload["primary_total_trades_sum"] = 17
            _write_json(output_dir / "baseline_v9_segment_oos_go_no_go.json", gate_payload)

            result = run_phase_b_retest_readiness_gate(data_dir=data_dir, output_dir=output_dir, metadata_file=metadata_file)

            self.assertEqual("FAIL", result["phase_b_retest_readiness_gate"]["oos_fairness_gate"])
            self.assertEqual("belum_boleh_retest", result["phase_b_retest_readiness_gate"]["final_decision"])

    def test_all_mock_thresholds_pass_allows_retest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir), scenario="pass")

            result = run_phase_b_retest_readiness_gate(data_dir=data_dir, output_dir=output_dir, metadata_file=metadata_file)

            payload = result["phase_b_retest_readiness_gate"]
            self.assertEqual("PASS", payload["history_gate"])
            self.assertEqual("PASS", payload["universe_coverage_gate"])
            self.assertEqual("PASS", payload["news_distribution_gate"])
            self.assertEqual("PASS", payload["oos_fairness_gate"])
            self.assertEqual("PASS", payload["framework_governance_gate"])
            self.assertEqual("PASS", payload["roadmap_discipline_gate"])
            self.assertEqual("boleh_retest", payload["final_decision"])

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


if __name__ == "__main__":
    unittest.main()
