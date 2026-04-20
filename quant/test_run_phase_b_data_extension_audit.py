"""Tests for Phase B data extension audit and framework redesign scope."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from quant.run_phase_b_data_extension_audit import run_phase_b_data_extension_audit


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


class RunPhaseBDataExtensionAuditTestCase(unittest.TestCase):
    def _write_price_csv(self, path: Path, rows: list[dict]) -> None:
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

    def _prepare_fixture(self, root: Path, include_metadata: bool = True, include_supporting_artifacts: bool = True) -> tuple[Path, Path, Path]:
        data_dir = root / "data"
        output_dir = root / "output"
        data_dir.mkdir()
        output_dir.mkdir()

        price_rows_aaa = []
        for i in range(57):
            price_rows_aaa.append(
                {
                    "date": f"2026-01-{(i % 28) + 1:02d}",
                    "open": 100 + i,
                    "high": 101 + i,
                    "low": 99 + i,
                    "close": 100 + i,
                    "volume": 1000000 + (i * 10),
                    "sentiment_average_1d": 0,
                    "sentiment_weighted_1d": 0,
                    "sentiment_news_count_1d": 1 if i in {5, 20} else 0,
                }
            )
        price_rows_bbb = []
        for i in range(57):
            price_rows_bbb.append(
                {
                    "date": f"2026-01-{(i % 28) + 1:02d}",
                    "open": 200 + i,
                    "high": 201 + i,
                    "low": 199 + i,
                    "close": 200 + i,
                    "volume": 2000000 + (i * 10),
                    "sentiment_average_1d": 0,
                    "sentiment_weighted_1d": 0,
                    "sentiment_news_count_1d": 1 if i in {10} else 0,
                }
            )

        self._write_price_csv(data_dir / "AAA.csv", price_rows_aaa)
        self._write_price_csv(data_dir / "BBB.csv", price_rows_bbb)

        metadata_file = data_dir / "ticker_metadata.csv"
        if include_metadata:
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
                [
                    {
                        "ticker": "AAA",
                        "sector": "tech",
                        "category": "technology",
                        "company_name": "AAA Tbk",
                        "interval_type": "1d",
                        "rows_1d": 57,
                        "date_start": "2026-01-01",
                        "date_end": "2026-03-31",
                        "sentiment_days_with_articles": 2,
                        "sentiment_article_count_total": 2,
                    },
                    {
                        "ticker": "BBB",
                        "sector": "finance",
                        "category": "finance",
                        "company_name": "BBB Tbk",
                        "interval_type": "1d",
                        "rows_1d": 57,
                        "date_start": "2026-01-01",
                        "date_end": "2026-03-31",
                        "sentiment_days_with_articles": 1,
                        "sentiment_article_count_total": 1,
                    },
                ],
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
            ],
            [
                {
                    "ticker": "AAA",
                    "rows": 57,
                    "date_start": "2026-01-01",
                    "date_end": "2026-03-31",
                    "article_count_total": 2,
                    "article_days": 2,
                    "news_density_pct": 3.5088,
                    "news_segment": "mid_news",
                    "sentiment_segment": "sentiment_poor",
                    "liquidity_segment": "thin_sparse",
                    "volatility_segment": "mixed_volatility",
                },
                {
                    "ticker": "BBB",
                    "rows": 57,
                    "date_start": "2026-01-01",
                    "date_end": "2026-03-31",
                    "article_count_total": 1,
                    "article_days": 1,
                    "news_density_pct": 1.7544,
                    "news_segment": "low_news",
                    "sentiment_segment": "sentiment_poor",
                    "liquidity_segment": "thin_sparse",
                    "volatility_segment": "mixed_volatility",
                },
            ],
        )

        if include_supporting_artifacts:
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
            _write_json(
                output_dir / "project_after_phase_b_decision.json",
                {
                    "phase_b_final_status": "phase_b_closed_with_learnings_no_candidate",
                    "recommended_primary_next_step": "stop_and_collect_more_data_then_redesign_framework",
                },
            )
            _write_json(
                output_dir / "baseline_v6_next_experiment_governance.json",
                {
                    "what_to_keep_fixed": [
                        "baseline aktif",
                        "logika entry/exit aktif",
                        "Jangan lanjut ke Phase C.",
                    ],
                },
            )
            _write_json(
                output_dir / "baseline_v9_segment_oos_go_no_go.json",
                {
                    "candidate_id": "baseline_v3_ema20_trend_guard",
                    "primary_segment": "sentiment_segment=sentiment_poor",
                    "decision": "no_go_even_for_segment",
                    "oos_stability_ok": False,
                    "ticker_consistency_ok": False,
                    "outlier_bias_ok": True,
                    "global_promotion_allowed": False,
                    "recommended_next_action": "drop_candidate_from_primary_segment_even_for_experimental_use",
                    "primary_total_trades_sum": 3,
                    "primary_active_ticker_count": 1,
                    "primary_trade_weighted_average_return": -1.2,
                    "primary_mean_average_return_active": -1.2,
                    "supporting_segments_failed": [
                        "volatility_segment=mixed_volatility",
                        "liquidity_segment=thin_sparse",
                    ],
                },
            )
            _write_json(
                output_dir / "baseline_v9_segment_oos_summary.json",
                {
                    "methodology": {
                        "validation_mode": "anchored_walk_forward_oos",
                        "warmup_bars": 21,
                        "fold_count": 3,
                        "fold_size_bars": 12,
                        "min_rows_across_tested_tickers": 57,
                        "hold_period": 3,
                        "entry_rule": "close_gt_ema20_and_bullish_candle",
                        "min_trades_threshold": 5,
                    },
                    "tested_segments": [
                        {
                            "tested_segment": "sentiment_segment=sentiment_poor",
                            "segment_role": "primary",
                            "tickers": ["AAA", "BBB"],
                            "summary": {
                                "tested_segment": "sentiment_segment=sentiment_poor",
                                "segment_role": "primary",
                                "tickers": ["AAA", "BBB"],
                                "ticker_count": 2,
                                "active_ticker_count": 1,
                                "candidate_signal_count": 5,
                                "candidate_total_trades": 3,
                                "trade_weighted_average_return": -1.2,
                                "oos_stability_ok": False,
                                "ticker_consistency_ok": False,
                                "outlier_bias_ok": True,
                            },
                        }
                    ],
                    "decision": {
                        "primary_segment": "sentiment_segment=sentiment_poor",
                    },
                },
            )
            _write_json(
                output_dir / "project_roadmap_status.json",
                {
                    "phase_a_final_status": {"status": "closed_with_notes"},
                    "latest_execution_status": {
                        "phase_b_status": "phase_b_closed_with_learnings_no_candidate",
                        "phase_c_decision": "phase_c_no_go_yet",
                    },
                },
            )
            _write_csv(
                output_dir / "baseline_v9_segment_oos_results.csv",
                [
                    "row_type",
                    "tested_segment",
                    "ticker",
                    "candidate_total_trades",
                    "candidate_signal_count",
                    "average_return",
                ],
                [
                    {
                        "row_type": "ticker_oos_summary",
                        "tested_segment": "sentiment_segment=sentiment_poor",
                        "ticker": "AAA",
                        "candidate_total_trades": 3,
                        "candidate_signal_count": 5,
                        "average_return": -1.2,
                    },
                    {
                        "row_type": "ticker_oos_summary",
                        "tested_segment": "sentiment_segment=sentiment_poor",
                        "ticker": "BBB",
                        "candidate_total_trades": 0,
                        "candidate_signal_count": 0,
                        "average_return": 0,
                    },
                ],
            )
        return data_dir, output_dir, metadata_file

    def test_script_still_runs_when_supporting_artifacts_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file = self._prepare_fixture(
                root,
                include_metadata=False,
                include_supporting_artifacts=False,
            )

            result = run_phase_b_data_extension_audit(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            self.assertTrue((output_dir / "phase_b_data_extension_audit.json").exists())
            self.assertTrue((output_dir / "framework_redesign_scope.json").exists())
            self.assertTrue((output_dir / "phase_b_data_gap_matrix.csv").exists())
            self.assertFalse(result["phase_b_data_extension_audit"]["strategy_retest_allowed_now"])

    def test_main_artifacts_are_generated_with_explicit_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file = self._prepare_fixture(root)

            result = run_phase_b_data_extension_audit(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            for name in [
                "phase_b_data_extension_audit.json",
                "phase_b_data_extension_audit.txt",
                "phase_b_data_gap_matrix.csv",
                "framework_redesign_scope.json",
                "framework_redesign_scope.txt",
                "universe_reconstruction_precheck.json",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            audit = result["phase_b_data_extension_audit"]
            self.assertEqual("insufficient_for_fair_strategy_retest", audit["current_data_sufficiency_status"])
            self.assertFalse(audit["strategy_retest_allowed_now"])
            self.assertTrue(audit["minimum_data_extension_required"]["minimum_history_rows_per_ticker"] >= 120)

            scope = result["framework_redesign_scope"]
            self.assertTrue(scope["evaluation_framework_redesign_required"])
            self.assertIn("Phase C = phase_c_no_go_yet", scope["what_must_stay_fixed"])

            universe = result["universe_reconstruction_precheck"]
            self.assertTrue(universe["universe_reconstruction_needed"])
            self.assertFalse(universe["whether_current_universe_is_usable_for_any_fair_retest"])

    def test_v9_no_go_and_small_trade_sample_keep_retest_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file = self._prepare_fixture(root)

            result = run_phase_b_data_extension_audit(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            audit = result["phase_b_data_extension_audit"]
            self.assertEqual("combined_history_length_and_distribution_gap", audit["highest_priority_data_gap"])
            self.assertFalse(audit["strategy_retest_allowed_now"])

            scope = result["framework_redesign_scope"]
            self.assertIn(
                "Phase C continuation",
                scope["what_must_not_be_reopened"],
            )

    def test_matrix_still_written_and_limitations_are_safe_when_metadata_is_limited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file = self._prepare_fixture(root, include_metadata=False)

            run_phase_b_data_extension_audit(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
            )

            matrix_path = output_dir / "phase_b_data_gap_matrix.csv"
            self.assertTrue(matrix_path.exists())
            with matrix_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertGreaterEqual(len(rows), 2)
            self.assertTrue(any("ticker_metadata.csv unavailable" in (row.get("limitations") or "") for row in rows))


if __name__ == "__main__":
    unittest.main()
