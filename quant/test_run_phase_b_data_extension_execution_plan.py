"""Tests for the Phase B data extension execution plan runner."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from quant.run_phase_b_data_extension_execution_plan import run_phase_b_data_extension_execution_plan


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class RunPhaseBDataExtensionExecutionPlanTestCase(unittest.TestCase):
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

    def _prepare_fixture(
        self,
        root: Path,
        scenario: str = "fail",
        include_metadata: bool = True,
    ) -> tuple[Path, Path, Path]:
        data_dir = root / "data"
        output_dir = root / "output"
        data_dir.mkdir()
        output_dir.mkdir()

        tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
        if scenario == "recheck_ready":
            history_rows = 99
            article_days_map = {
                "AAA": {2, 6, 10, 14},
                "BBB": {3, 7, 11, 15},
                "CCC": {4, 8, 12, 16},
                "DDD": {5, 9, 13},
                "EEE": {18, 22, 26},
                "FFF": {19, 23, 27},
            }
            primary_trades = {"AAA": 4, "BBB": 3, "CCC": 3, "DDD": 2, "EEE": 2, "FFF": 1}
            fold_trades = [5, 5, 5]
        else:
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
            fold_trades = [2, 3, 6]

        for ticker in tickers:
            self._write_price_csv(data_dir / f"{ticker}.csv", history_rows=history_rows, article_days=article_days_map[ticker])

        metadata_file = data_dir / "ticker_metadata.csv"
        if include_metadata:
            metadata_rows = []
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

        segmentation_rows = []
        for ticker in tickers:
            article_days = len(article_days_map[ticker])
            segmentation_rows.append(
                {
                    "ticker": ticker,
                    "rows": history_rows,
                    "history_rows": history_rows,
                    "date_start": "2026-01-01",
                    "date_end": "2026-06-30",
                    "article_count_total": article_days,
                    "news_count_total": article_days,
                    "article_days": article_days,
                    "news_density_pct": round((100.0 * article_days / history_rows), 4),
                    "news_segment": "mid_news" if ticker in {"AAA", "BBB", "CCC", "DDD"} else "high_news",
                    "sentiment_segment": "sentiment_poor",
                    "liquidity_segment": "thin_sparse" if ticker in {"AAA", "BBB", "CCC", "EEE"} else "liquid_active",
                    "volatility_segment": "mixed_volatility" if ticker in {"AAA", "BBB", "DDD", "EEE"} else "higher_volatility",
                }
            )
        _write_csv(
            output_dir / "baseline_v6_universe_segmentation.csv",
            [
                "ticker",
                "rows",
                "history_rows",
                "date_start",
                "date_end",
                "article_count_total",
                "news_count_total",
                "article_days",
                "news_density_pct",
                "news_segment",
                "sentiment_segment",
                "liquidity_segment",
                "volatility_segment",
            ],
            segmentation_rows,
        )
        _write_json(
            output_dir / "phase_b_retest_readiness_gate.json",
            {
                "history_gate": "FAIL",
                "universe_coverage_gate": "FAIL",
                "news_distribution_gate": "FAIL",
                "oos_fairness_gate": "FAIL",
                "framework_governance_gate": "PASS",
                "roadmap_discipline_gate": "PASS",
                "final_decision": "belum_boleh_retest",
                "highest_blocking_gate": "history_gate",
                "primary_segment": "sentiment_segment=sentiment_poor",
                "safe_segments_evaluated": [
                    "volatility_segment=mixed_volatility",
                    "sentiment_segment=sentiment_poor",
                    "liquidity_segment=thin_sparse",
                    "news_segment=mid_news",
                ],
            },
        )
        _write_json(
            output_dir / "phase_b_retest_next_requirements.json",
            {
                "final_decision": "belum_boleh_retest",
                "highest_blocking_gate": "history_gate",
                "priority_requirements": [
                    "Perpanjang history sampai minimum 120 bar dan 6 usable OOS windows per ticker."
                ],
            },
        )
        _write_json(
            output_dir / "phase_b_data_extension_audit.json",
            {
                "history_length_assessment": {
                    "current_min_usable_oos_windows": 6 if scenario == "recheck_ready" else 3,
                },
                "news_distribution_assessment": {
                    "primary_segment_article_count_total": 19 if scenario == "recheck_ready" else 6,
                    "primary_segment_ticker_count": 6,
                },
            },
        )
        _write_json(
            output_dir / "framework_redesign_scope.json",
            {
                "what_must_stay_fixed": ["baseline aktif", "logika entry/exit aktif"],
            },
        )
        _write_json(
            output_dir / "universe_reconstruction_precheck.json",
            {
                "whether_current_universe_is_usable_for_any_fair_retest": False,
            },
        )
        _write_json(
            output_dir / "phase_b_final_closeout.json",
            {
                "phase_b_final_status": "phase_b_closed_with_learnings_no_candidate",
            },
        )
        _write_json(
            output_dir / "project_after_phase_b_decision.json",
            {
                "recommended_primary_next_step": "stop_and_collect_more_data_then_redesign_framework",
            },
        )
        _write_json(
            output_dir / "baseline_v9_segment_oos_summary.json",
            {
                "methodology": {"warmup_bars": 21, "fold_size_bars": 12},
            },
        )
        _write_json(
            output_dir / "baseline_v9_segment_oos_go_no_go.json",
            {
                "primary_segment": "sentiment_segment=sentiment_poor",
                "primary_total_trades_sum": sum(primary_trades.values()),
                "primary_active_ticker_count": sum(1 for value in primary_trades.values() if value > 0),
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
                }
            )
        _write_csv(
            output_dir / "baseline_v9_segment_oos_results.csv",
            ["row_type", "tested_segment", "ticker", "fold_id", "candidate_total_trades"],
            result_rows,
        )

        return data_dir, output_dir, metadata_file

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir))
            result = run_phase_b_data_extension_execution_plan(data_dir=data_dir, output_dir=output_dir, metadata_file=metadata_file)

            for name in [
                "phase_b_data_extension_execution_plan.json",
                "phase_b_data_extension_execution_plan.txt",
                "phase_b_data_extension_priority_tickers.csv",
                "phase_b_data_extension_priority_segments.csv",
                "phase_b_data_extension_progress_tracker.csv",
                "phase_b_recheck_trigger.json",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertTrue(result["phase_b_data_extension_execution_plan"]["execution_plan_ready"])
            self.assertIs(result["phase_b_data_extension_execution_plan"]["recheck_readiness_gate_allowed"], False)

    def test_decision_fields_stay_explicit_and_progress_tracker_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir))
            result = run_phase_b_data_extension_execution_plan(data_dir=data_dir, output_dir=output_dir, metadata_file=metadata_file)

            payload = result["phase_b_data_extension_execution_plan"]
            self.assertIn("highest_priority_execution_target", payload)
            self.assertIn("minimum_progress_needed_before_recheck", payload)
            self.assertIn("recommended_next_action", payload)
            self.assertIn("oos_window_threshold_semantics", payload)
            self.assertEqual(3.0, payload["oos_window_threshold_semantics"]["methodology_minimum_windows"])
            self.assertEqual(
                6.0,
                payload["oos_window_threshold_semantics"]["stretch_target_windows_by_batch"]["batch_2"],
            )
            self.assertIsInstance(payload["recheck_readiness_gate_allowed"], bool)
            self.assertGreater(len(result["progress_tracker"]), 0)

    def test_execution_plan_runs_with_limited_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir), include_metadata=False)
            result = run_phase_b_data_extension_execution_plan(data_dir=data_dir, output_dir=output_dir, metadata_file=metadata_file)

            self.assertTrue(result["phase_b_data_extension_execution_plan"]["execution_plan_ready"])
            self.assertTrue(any("ticker_metadata.csv unavailable" in item for item in result["phase_b_data_extension_execution_plan"]["limitations"]))
            self.assertTrue((output_dir / "phase_b_data_extension_progress_tracker.csv").exists())

    def test_recheck_trigger_can_turn_true_after_material_progress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir), scenario="recheck_ready")
            result = run_phase_b_data_extension_execution_plan(data_dir=data_dir, output_dir=output_dir, metadata_file=metadata_file)

            self.assertIs(result["phase_b_data_extension_execution_plan"]["recheck_readiness_gate_allowed"], True)
            self.assertIs(result["phase_b_recheck_trigger"]["recheck_readiness_gate_allowed"], True)


if __name__ == "__main__":
    unittest.main()
