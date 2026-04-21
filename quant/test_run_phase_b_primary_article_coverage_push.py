"""Tests for Phase B primary article coverage push runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.run_phase_b_batch1_completion_check import run_phase_b_batch1_completion_check
from quant.run_phase_b_post_backfill_batch_verification import run_phase_b_post_backfill_batch_verification
from quant.run_phase_b_primary_article_coverage_push import (
    DEFAULT_PRIORITY_TICKERS,
    DEFAULT_PROVIDER_PLAN,
    run_phase_b_primary_article_coverage_push,
)
from quant.test_run_phase_b_data_extension_ingest_audit import (
    RunPhaseBDataExtensionIngestAuditTestCase,
)


class RunPhaseBPrimaryArticleCoveragePushTestCase(unittest.TestCase):
    def test_default_priority_tickers_follow_official_primary_segment(self) -> None:
        self.assertEqual(["BBCA", "BMRI", "GOTO", "INDF", "UNVR"], DEFAULT_PRIORITY_TICKERS)

    def _prepare_fixture(self, root: Path) -> tuple[Path, Path, Path, RunPhaseBDataExtensionIngestAuditTestCase]:
        helper = RunPhaseBDataExtensionIngestAuditTestCase()
        data_dir, output_dir, metadata_file = helper._prepare_fixture(root=root, scenario="baseline", include_metadata=True)
        updated_article_days_map = {
            "AAA": {2, 6},
            "BBB": {3},
            "CCC": {4},
            "DDD": {5},
            "EEE": set(),
            "FFF": {7},
        }
        for ticker in updated_article_days_map:
            helper._write_price_csv(data_dir / f"{ticker}.csv", history_rows=118, article_days=updated_article_days_map[ticker])
        metadata = pd.read_csv(metadata_file)
        metadata["rows_1d"] = 118
        metadata["date_end"] = "2026-10-20"
        metadata["sentiment_days_with_articles"] = [len(updated_article_days_map[ticker]) for ticker in metadata["ticker"]]
        metadata["sentiment_article_count_total"] = metadata["sentiment_days_with_articles"]
        metadata.to_csv(metadata_file, index=False)
        run_phase_b_post_backfill_batch_verification(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
        )
        run_phase_b_batch1_completion_check(
            data_dir=data_dir,
            output_dir=output_dir,
            metadata_file=metadata_file,
        )
        return data_dir, output_dir, metadata_file, helper

    def test_main_artifacts_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file, _ = self._prepare_fixture(Path(tmp_dir))

            def coverage_probe(tickers, cwd):
                return {ticker: {"article_count_total": 0, "article_days": 0, "high_quality_count": 0, "by_provider": {}} for ticker in tickers}

            def article_detail_probe(ticker, cwd):
                return {"ticker": ticker, "rows": []}

            result = run_phase_b_primary_article_coverage_push(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                priority_tickers=["AAA", "BBB", "CCC"],
                providers=["gnews"],
                command_executor=lambda command, cwd: {"command": " ".join(command), "returncode": 0, "stdout": "", "stderr": "", "combined_output": "AAA: raw 0, saved 0, updated 0", "succeeded": True},
                coverage_probe=coverage_probe,
                article_detail_probe=article_detail_probe,
            )

            for name in [
                "phase_b_primary_article_coverage_push.json",
                "phase_b_primary_article_coverage_push.txt",
                "phase_b_primary_article_coverage_ticker_breakdown.csv",
                "phase_b_primary_article_drop_reasons_per_provider.json",
                "phase_b_primary_article_dropped_samples_per_provider.json",
                "phase_b_primary_article_official_metric_delta_per_ticker.json",
                "phase_b_official_primary_segment_membership_audit.json",
                "bbca_article_day_audit.json",
                "phase_b_batch1_after_article_push.json",
                "phase_b_batch1_after_article_push.txt",
            ]:
                self.assertTrue((output_dir / name).exists(), f"Missing artifact: {name}")

            self.assertIn("phase_b_batch1_after_article_push", result)

    def test_batch_remains_not_complete_when_article_push_is_insufficient(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file, _ = self._prepare_fixture(Path(tmp_dir))

            def coverage_probe(tickers, cwd):
                return {ticker: {"article_count_total": 1, "article_days": 1, "high_quality_count": 1, "by_provider": {"mock": 1}} for ticker in tickers}

            result = run_phase_b_primary_article_coverage_push(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                priority_tickers=["AAA", "BBB", "CCC"],
                providers=["gnews"],
                command_executor=lambda command, cwd: {"command": " ".join(command), "returncode": 0, "stdout": "", "stderr": "", "combined_output": "AAA: raw 0, saved 0, updated 0", "succeeded": True},
                coverage_probe=coverage_probe,
                article_detail_probe=lambda ticker, cwd: {"ticker": ticker, "rows": []},
            )

            payload = result["phase_b_batch1_after_article_push"]
            self.assertEqual("batch_1_started_but_not_complete", payload["batch_1_status"])
            self.assertFalse(payload["batch_1_completed"])
            self.assertFalse(payload["checkpoint_material_reached"])
            self.assertFalse(payload["recheck_readiness_gate_allowed"])

    def test_batch_becomes_complete_when_article_push_closes_batch_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file, helper = self._prepare_fixture(root)

            def after_fetch_hook(data_dir: Path, output_dir: Path, metadata_file: Path) -> None:
                updated_article_days_map = {
                    "AAA": {2, 6, 12},
                    "BBB": {3, 10, 14},
                    "CCC": {4, 11, 15},
                    "DDD": {5, 12, 16},
                    "EEE": {13, 17, 21},
                    "FFF": {8, 18, 22},
                }
                for ticker in updated_article_days_map:
                    helper._write_price_csv(data_dir / f"{ticker}.csv", history_rows=118, article_days=updated_article_days_map[ticker])
                metadata = pd.read_csv(metadata_file)
                metadata["rows_1d"] = 118
                metadata["date_end"] = "2026-10-20"
                metadata["sentiment_days_with_articles"] = [len(updated_article_days_map[ticker]) for ticker in metadata["ticker"]]
                metadata["sentiment_article_count_total"] = metadata["sentiment_days_with_articles"]
                metadata.to_csv(metadata_file, index=False)

            def coverage_probe(tickers, cwd):
                return {ticker: {"article_count_total": 3, "article_days": 3, "high_quality_count": 3, "by_provider": {"mock": 3}} for ticker in tickers}

            result = run_phase_b_primary_article_coverage_push(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                priority_tickers=["AAA", "BBB", "CCC"],
                providers=["gnews"],
                command_executor=lambda command, cwd: {"command": " ".join(command), "returncode": 0, "stdout": "", "stderr": "", "combined_output": "AAA: raw 3, saved 3, updated 0", "succeeded": True},
                coverage_probe=coverage_probe,
                article_detail_probe=lambda ticker, cwd: {"ticker": ticker, "rows": []},
                after_fetch_hook=after_fetch_hook,
            )

            payload = result["phase_b_batch1_after_article_push"]
            self.assertEqual("batch_1_complete_but_checkpoint_not_material", payload["batch_1_status"])
            self.assertTrue(payload["batch_1_completed"])
            self.assertFalse(payload["checkpoint_material_reached"])
            self.assertFalse(payload["recheck_readiness_gate_allowed"])

    def test_default_provider_plan_includes_finnhub_and_writes_drop_reason_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir, output_dir, metadata_file, _ = self._prepare_fixture(Path(tmp_dir))
            attempted_fetches: list[tuple[str, str]] = []

            def coverage_probe(tickers, cwd):
                return {
                    ticker: {"article_count_total": 0, "article_days": 0, "high_quality_count": 0, "by_provider": {}}
                    for ticker in tickers
                }

            def command_executor(command, cwd):
                command_str = " ".join(command)
                if "news:fetch" in command_str:
                    stock = next(part.split("=", 1)[1] for part in command if part.startswith("--stock="))
                    provider = next(part.split("=", 1)[1] for part in command if part.startswith("--provider="))
                    attempted_fetches.append((stock, provider))
                    payload = {
                        "ticker": stock,
                        "provider": provider,
                        "raw": 2 if provider == "finnhub" else 0,
                        "saved": 1 if provider == "finnhub" else 0,
                        "updated": 0,
                        "dropped_relevance": 1 if provider == "gnews" else 0,
                        "dropped_quality": 1 if provider == "rss_local" else 0,
                        "dropped_exclusion": 1 if provider == "newsapi" else 0,
                        "skipped_dedup": 1 if provider == "gdelt" else 0,
                        "failed": 0,
                        "dropped_samples": {
                            "relevance": [
                                {
                                    "title": "UNVR raw hit gugur relevance",
                                    "reason": "relevance_below_threshold",
                                    "relevance": 0.24,
                                }
                            ] if provider == "gnews" else [],
                            "quality": [
                                {
                                    "title": "UNVR raw hit gugur quality",
                                    "reason": "quality_below_threshold",
                                    "final_quality": 0.31,
                                }
                            ] if provider == "rss_local" else [],
                            "exclusion": [
                                {
                                    "title": "Noise keyword",
                                    "reason": "matched_exclusion_keyword",
                                    "detail": "promo",
                                }
                            ] if provider == "newsapi" else [],
                        },
                    }
                    return {
                        "command": command_str,
                        "returncode": 0,
                        "stdout": "",
                        "stderr": "",
                        "combined_output": f"FETCH_RESULT_JSON:{json.dumps(payload)}",
                        "succeeded": True,
                    }

                return {
                    "command": command_str,
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                    "combined_output": "",
                    "succeeded": True,
                }

            result = run_phase_b_primary_article_coverage_push(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                priority_tickers=["AAA"],
                command_executor=command_executor,
                coverage_probe=coverage_probe,
                article_detail_probe=lambda ticker, cwd: {"ticker": ticker, "rows": []},
            )

            push_payload = result["phase_b_primary_article_coverage_push"]
            self.assertEqual(DEFAULT_PROVIDER_PLAN, push_payload["providers_attempted"])
            self.assertIn(("AAA", "finnhub"), attempted_fetches)

            diagnostic = json.loads(
                (output_dir / "phase_b_primary_article_drop_reasons_per_provider.json").read_text(encoding="utf-8")
            )
            self.assertEqual(["AAA"], diagnostic["priority_tickers_checked"])
            self.assertEqual(DEFAULT_PROVIDER_PLAN, diagnostic["providers_attempted"])
            self.assertEqual(len(DEFAULT_PROVIDER_PLAN), len(diagnostic["rows"]))

            finnhub_row = next(row for row in diagnostic["rows"] if row["provider"] == "finnhub")
            self.assertEqual("AAA", finnhub_row["ticker"])
            self.assertEqual(2, finnhub_row["raw_count"])
            self.assertEqual(1, finnhub_row["saved_count"])
            self.assertEqual(0, finnhub_row["failed"])

            dropped_samples = json.loads(
                (output_dir / "phase_b_primary_article_dropped_samples_per_provider.json").read_text(encoding="utf-8")
            )
            gnews_row = next(row for row in dropped_samples["rows"] if row["provider"] == "gnews")
            self.assertEqual("AAA", gnews_row["ticker"])
            self.assertEqual("UNVR raw hit gugur relevance", gnews_row["relevance_samples"][0]["title"])
            rss_row = next(row for row in dropped_samples["rows"] if row["provider"] == "rss_local")
            self.assertEqual("UNVR raw hit gugur quality", rss_row["quality_samples"][0]["title"])
            newsapi_row = next(row for row in dropped_samples["rows"] if row["provider"] == "newsapi")
            self.assertEqual("matched_exclusion_keyword", newsapi_row["exclusion_samples"][0]["reason"])

    def test_official_metric_delta_artifact_tracks_before_after_and_negative_contributors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir, output_dir, metadata_file, helper = self._prepare_fixture(root)
            before_completion = json.loads(
                (output_dir / "phase_b_batch1_completion_decision.json").read_text(encoding="utf-8")
            )
            before_rows = {
                row["ticker"]: row
                for row in before_completion["article_day_status"]["per_ticker"]
            }

            def after_fetch_hook(data_dir: Path, output_dir: Path, metadata_file: Path) -> None:
                updated_article_days_map = {
                    "AAA": {2},
                    "BBB": {3},
                    "CCC": {4},
                    "DDD": {5},
                    "EEE": set(),
                    "FFF": {7},
                }
                for ticker, article_days in updated_article_days_map.items():
                    helper._write_price_csv(data_dir / f"{ticker}.csv", history_rows=118, article_days=article_days)
                metadata = pd.read_csv(metadata_file)
                metadata["rows_1d"] = 118
                metadata["date_end"] = "2026-10-20"
                metadata["sentiment_days_with_articles"] = [len(updated_article_days_map[ticker]) for ticker in metadata["ticker"]]
                metadata["sentiment_article_count_total"] = metadata["sentiment_days_with_articles"]
                metadata.to_csv(metadata_file, index=False)

            result = run_phase_b_primary_article_coverage_push(
                data_dir=data_dir,
                output_dir=output_dir,
                metadata_file=metadata_file,
                priority_tickers=["AAA", "BBB", "CCC"],
                providers=["google_news_rss", "business_site_search"],
                command_executor=lambda command, cwd: {
                    "command": " ".join(command),
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                    "combined_output": "FETCH_RESULT_JSON:{\"raw\": 2, \"saved\": 1, \"updated\": 0}",
                    "succeeded": True,
                },
                coverage_probe=lambda tickers, cwd: {
                    ticker: {"article_count_total": 2, "article_days": 2, "high_quality_count": 1, "by_provider": {"mock": 2}}
                    for ticker in tickers
                },
                article_detail_probe=lambda ticker, cwd: {
                    "ticker": ticker,
                    "rows": [
                        {
                            "title": "Row before",
                            "published_date": "2026-10-10",
                            "source_provider": "mock",
                            "source_url": "https://example.com/before",
                            "final_quality_score": 0.7,
                        },
                        {
                            "title": "Row after",
                            "published_date": "2026-10-11",
                            "source_provider": "mock",
                            "source_url": "https://example.com/after",
                            "final_quality_score": 0.8,
                        },
                    ] if ticker == "BBCA" else [],
                },
                after_fetch_hook=after_fetch_hook,
            )

            artifact = json.loads(
                (output_dir / "phase_b_primary_article_official_metric_delta_per_ticker.json").read_text(encoding="utf-8")
            )
            membership = json.loads(
                (output_dir / "phase_b_official_primary_segment_membership_audit.json").read_text(encoding="utf-8")
            )
            self.assertEqual(["AAA", "BBB", "CCC"], artifact["priority_tickers_checked"])
            self.assertIn("progress_since_baseline_v9", artifact["official_metric_basis"])
            self.assertEqual(len(artifact["official_primary_tickers_checked"]), len(artifact["rows"]))
            self.assertIn("top_negative_contributors", artifact)
            self.assertIn("priority_tickers_outside_official_primary_segment", artifact)
            self.assertIn("official_primary_tickers_missing_from_fetch_plan", artifact)
            self.assertIn("source_of_truth_artifact", membership)
            self.assertIn("official_primary_segment_tickers", membership)
            self.assertIn("rows", membership)
            self.assertTrue(all("included_in_official_primary_segment" in row for row in membership["rows"]))
            self.assertTrue(all("reason" in row for row in membership["rows"]))

            if artifact["top_negative_contributors"]:
                negative_ticker = artifact["top_negative_contributors"][0]["ticker"]
                negative_row = next(row for row in artifact["rows"] if row["ticker"] == negative_ticker)
            else:
                negative_row = artifact["rows"][0]
            self.assertEqual(
                negative_row["after_article_count_total"] - negative_row["before_article_count_total"],
                negative_row["delta_article_count_total"],
            )
            self.assertEqual(
                negative_row["after_article_days"] - negative_row["before_article_days"],
                negative_row["delta_article_days"],
            )
            self.assertTrue(isinstance(negative_row["provider_contribution_summary"], list))
            self.assertIn("still_blocking", negative_row)
            self.assertIn("was_in_fetch_priority_plan", negative_row)

            self.assertEqual(
                round(sum(row["before_article_count_total"] for row in artifact["rows"]), 4),
                artifact["total_before"],
            )
            self.assertEqual(
                round(sum(row["after_article_count_total"] for row in artifact["rows"]), 4),
                artifact["total_after"],
            )
            self.assertEqual(
                round(artifact["total_after"] - artifact["total_before"], 4),
                artifact["total_delta"],
            )
            self.assertIn("phase_b_primary_article_official_metric_delta_per_ticker", result)
            self.assertIn("phase_b_official_primary_segment_membership_audit", result)
            self.assertIn("bbca_article_day_audit", result)

            bbca_audit = json.loads(
                (output_dir / "bbca_article_day_audit.json").read_text(encoding="utf-8")
            )
            self.assertEqual("BBCA", bbca_audit["ticker"])
            self.assertIn("provider_fetch_summary", bbca_audit)
            self.assertIn("before_by_date", bbca_audit)
            self.assertIn("after_by_date", bbca_audit)
            self.assertIn("clustering_summary", bbca_audit)


if __name__ == "__main__":
    unittest.main()
