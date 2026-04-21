"""Tests for UNVR/ICBP article root-cause runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_b_unvr_icbp_article_root_cause import (
    run_phase_b_unvr_icbp_article_root_cause,
)


class RunPhaseBUnvrIcbpArticleRootCauseTestCase(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_csv(self, path: Path, frame: pd.DataFrame) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)

    def _price_frame(self, *, rows: int = 118, article_days: set[int] | None = None) -> pd.DataFrame:
        article_days = article_days or set()
        records = []
        for idx in range(rows):
            records.append(
                {
                    "date": f"2026-01-{(idx % 28) + 1:02d}",
                    "open": 100 + idx,
                    "high": 101 + idx,
                    "low": 99 + idx,
                    "close": 100.5 + idx,
                    "volume": 100000 + idx,
                    "sentiment_average_1d": 0.0,
                    "sentiment_weighted_1d": 0.0,
                    "sentiment_news_count_1d": 1 if idx in article_days else 0,
                }
            )
        return pd.DataFrame(records)

    def _prepare_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        data_dir = root / "data"
        output_dir = root / "output"
        metadata_file = data_dir / "ticker_metadata.csv"
        data_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        self._write_csv(data_dir / "UNVR.csv", self._price_frame(article_days=set()))
        self._write_csv(data_dir / "ICBP.csv", self._price_frame(article_days={5}))

        metadata = pd.DataFrame(
            [
                {
                    "ticker": "UNVR",
                    "rows_1d": 118,
                    "date_end": "2026-04-20",
                    "sentiment_days_with_articles": 0,
                    "sentiment_article_count_total": 0,
                },
                {
                    "ticker": "ICBP",
                    "rows_1d": 118,
                    "date_end": "2026-04-20",
                    "sentiment_days_with_articles": 1,
                    "sentiment_article_count_total": 1,
                },
            ]
        )
        self._write_csv(metadata_file, metadata)
        self._write_csv(
            output_dir / "baseline_v6_universe_segmentation.csv",
            pd.DataFrame(
                [
                    {
                        "ticker": "UNVR",
                        "rows": 118,
                        "article_count_total": 0,
                        "article_days": 0,
                        "news_count_total": 0,
                    },
                    {
                        "ticker": "ICBP",
                        "rows": 118,
                        "article_count_total": 1,
                        "article_days": 1,
                        "news_count_total": 1,
                    },
                ]
            ),
        )
        self._write_json(
            output_dir / "phase_b_primary_article_coverage_push.json",
            {
                "fetch_attempts": [
                    {"ticker": "UNVR", "provider": "gnews", "raw": 0, "saved": 0, "updated": 0},
                    {"ticker": "ICBP", "provider": "gnews", "raw": 0, "saved": 0, "updated": 0},
                ]
            },
        )
        self._write_json(
            output_dir / "phase_b_batch1_after_article_push.json",
            {
                "batch_1_status": "batch_1_started_but_not_complete",
                "batch_1_completed": False,
                "checkpoint_material_reached": False,
                "recheck_readiness_gate_allowed": False,
                "primary_segment_total_articles": 11.0,
                "primary_segment_article_days_median": 2.0,
            },
        )
        self._write_json(
            output_dir / "phase_b_batch1_completion_decision.json",
            {
                "batch_1_status": "batch_1_started_but_not_complete",
                "remaining_blockers": [
                    "primary_segment_total_articles actual=11.0 target>=14",
                    "primary_segment_article_days_median actual=2.0 target>=3",
                ]
            },
        )
        self._write_json(output_dir / "phase_b_article_day_recovery_status.json", {"ok": True})
        return data_dir, output_dir, metadata_file

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir))

            def probe(tickers, cwd):
                return {
                    "UNVR": {
                        "db_articles_all": 1,
                        "db_article_days_all": 1,
                        "db_articles_qualifying": 0,
                        "db_article_days_qualifying": 0,
                        "db_title_matches_other_or_null": 0,
                        "all_titles": [{"title": "Unilever article"}],
                        "qualifying_titles": [],
                        "other_match_titles": [],
                    },
                    "ICBP": {
                        "db_articles_all": 1,
                        "db_article_days_all": 1,
                        "db_articles_qualifying": 1,
                        "db_article_days_qualifying": 1,
                        "db_title_matches_other_or_null": 0,
                        "all_titles": [{"title": "ICBP article"}],
                        "qualifying_titles": [{"title": "ICBP article"}],
                        "other_match_titles": [],
                    },
                }

            result = run_phase_b_unvr_icbp_article_root_cause(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                article_probe=probe,
            )

            for name in [
                "phase_b_unvr_icbp_article_root_cause.json",
                "phase_b_unvr_icbp_article_root_cause.txt",
                "phase_b_unvr_icbp_article_pipeline_trace.csv",
                "phase_b_unvr_icbp_article_fix_status.json",
                "phase_b_unvr_icbp_article_next_steps.json",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            payload = result["phase_b_unvr_icbp_article_root_cause"]
            self.assertEqual("external_source_limited", payload["root_cause_class"])
            self.assertFalse(payload["pipeline_bug_confirmed"])
            self.assertFalse(payload["ticker_mapping_gap_detected"])
            self.assertFalse(payload["local_fix_applied"])
            self.assertFalse(payload["article_coverage_improved"])
            self.assertFalse(payload["batch_1_helpful_progress_detected"])
            self.assertIn("external/source-limited", payload["decisive_statement"])
            self.assertIn("local pipeline failure tidak terbukti", payload["decisive_statement"])
            self.assertEqual(
                "do_not_rerun_readiness_gate_or_change_baseline_rerun_article_push_only_if_new_qualifying_articles_exist_for_unvr_or_icbp",
                payload["recommended_next_action"],
            )
            self.assertEqual(
                [
                    "UNVR: article_exists_but_below_quality_threshold",
                    "ICBP: source_article_coverage_still_sparse",
                ],
                payload["current_article_blockers"],
            )

    def test_sparse_source_classification_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir))

            def probe(tickers, cwd):
                return {
                    ticker: {
                        "db_articles_all": 0,
                        "db_article_days_all": 0,
                        "db_articles_qualifying": 0,
                        "db_article_days_qualifying": 0,
                        "db_title_matches_other_or_null": 0,
                        "all_titles": [],
                        "qualifying_titles": [],
                        "other_match_titles": [],
                    }
                    for ticker in tickers
                }

            result = run_phase_b_unvr_icbp_article_root_cause(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                article_probe=probe,
            )

            payload = result["phase_b_unvr_icbp_article_root_cause"]
            self.assertEqual("external_source_limited", payload["root_cause_class"])
            self.assertFalse(payload["ticker_mapping_gap_detected"])
            self.assertFalse(payload["pipeline_bug_confirmed"])
            self.assertEqual(
                [
                    "UNVR: source_article_coverage_still_sparse",
                    "ICBP: source_article_coverage_still_sparse",
                ],
                payload["current_article_blockers"],
            )

    def test_below_quality_threshold_is_not_classified_as_pipeline_bug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir))

            def probe(tickers, cwd):
                return {
                    "UNVR": {
                        "db_articles_all": 1,
                        "db_article_days_all": 1,
                        "db_articles_qualifying": 0,
                        "db_article_days_qualifying": 0,
                        "db_title_matches_other_or_null": 0,
                        "all_titles": [{"title": "UNVR article", "quality": 0.257}],
                        "qualifying_titles": [],
                        "other_match_titles": [],
                    },
                    "ICBP": {
                        "db_articles_all": 1,
                        "db_article_days_all": 1,
                        "db_articles_qualifying": 1,
                        "db_article_days_qualifying": 1,
                        "db_title_matches_other_or_null": 0,
                        "all_titles": [{"title": "ICBP article", "quality": 0.612}],
                        "qualifying_titles": [{"title": "ICBP article", "quality": 0.612}],
                        "other_match_titles": [],
                    },
                }

            result = run_phase_b_unvr_icbp_article_root_cause(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                article_probe=probe,
            )

            payload = result["phase_b_unvr_icbp_article_root_cause"]
            unvr = next(row for row in payload["per_ticker"] if row["ticker"] == "UNVR")
            self.assertEqual("external_source_limited", payload["root_cause_class"])
            self.assertFalse(payload["pipeline_bug_confirmed"])
            self.assertTrue(payload["alignment_export_gap_detected"])
            self.assertEqual("article_exists_but_below_quality_threshold", unvr["ticker_root_cause"])
            self.assertTrue(unvr["below_quality_threshold_detected"])
            self.assertFalse(unvr["pipeline_bug_confirmed"])
            self.assertIn("bukan bukti local pipeline failure", unvr["ticker_decisive_statement"])

    def test_true_qualifying_export_gap_is_classified_as_local_pipeline_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file = self._prepare_fixture(Path(tmp_dir))

            def probe(tickers, cwd):
                return {
                    "UNVR": {
                        "db_articles_all": 3,
                        "db_article_days_all": 3,
                        "db_articles_qualifying": 3,
                        "db_article_days_qualifying": 3,
                        "db_title_matches_other_or_null": 0,
                        "all_titles": [{"title": "UNVR article"}],
                        "qualifying_titles": [{"title": "UNVR article"}],
                        "other_match_titles": [],
                    },
                    "ICBP": {
                        "db_articles_all": 1,
                        "db_article_days_all": 1,
                        "db_articles_qualifying": 1,
                        "db_article_days_qualifying": 1,
                        "db_title_matches_other_or_null": 0,
                        "all_titles": [{"title": "ICBP article"}],
                        "qualifying_titles": [{"title": "ICBP article"}],
                        "other_match_titles": [],
                    },
                }

            result = run_phase_b_unvr_icbp_article_root_cause(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                article_probe=probe,
            )

            payload = result["phase_b_unvr_icbp_article_root_cause"]
            self.assertEqual("qualifying_export_gap_local_pipeline_issue", payload["root_cause_class"])
            self.assertTrue(payload["alignment_export_gap_detected"])
            self.assertTrue(payload["pipeline_bug_confirmed"])
            self.assertEqual(
                "fix_local_article_pipeline_gap_then_rerun_export_and_batch_1_verification",
                payload["recommended_next_action"],
            )


if __name__ == "__main__":
    unittest.main()
