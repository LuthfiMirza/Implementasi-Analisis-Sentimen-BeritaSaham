"""Smoke tests for real-data Phase A evaluation."""

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from quant.evaluate_phase_a_real_data import (
    EvaluationCliError,
    build_multitimeframe_go_no_go,
    build_sentiment_momentum_go_no_go,
    evaluate_folder,
    inspect_item7_sentiment_dataset,
    load_price_csv,
)
from quant.phase_a import make_example_ohlcv_dataframe


def _with_sentiment_columns(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    frame["sentiment_average_1d"] = 0.0
    frame["sentiment_weighted_1d"] = 0.0
    frame["sentiment_news_count_1d"] = 0
    frame.loc[55:70, "sentiment_average_1d"] = -0.15
    frame.loc[55:70, "sentiment_weighted_1d"] = -0.2
    frame.loc[55:70, "sentiment_news_count_1d"] = 1
    frame.loc[71:, "sentiment_average_1d"] = 0.3
    frame.loc[71:, "sentiment_weighted_1d"] = 0.4
    frame.loc[71:, "sentiment_news_count_1d"] = 2
    return frame


def _with_invalid_sentiment_columns(df: pd.DataFrame) -> pd.DataFrame:
    frame = _with_sentiment_columns(df)
    frame["sentiment_weighted_1d"] = frame["sentiment_weighted_1d"].astype(object)
    frame.loc[80, "sentiment_weighted_1d"] = "bad-data"
    return frame


class EvaluatePhaseARealDataTestCase(unittest.TestCase):
    """Validate folder evaluation and CSV loading on small fixtures."""

    def test_load_price_csv_cleans_duplicate_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "BBCA.csv"
            df = make_example_ohlcv_dataframe(length=70, seed=11)
            duplicated = pd.concat([df, df.iloc[[-1]]], ignore_index=True)
            duplicated.to_csv(csv_path, index=False)

            cleaned, warnings = load_price_csv(csv_path)

            self.assertEqual(len(cleaned), len(df))
            self.assertTrue(any("duplicate date" in item.lower() for item in warnings))

    def test_evaluate_folder_handles_success_and_skipped_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir) / "data"
            output_dir = Path(tmp_dir) / "output"
            data_dir.mkdir()

            make_example_ohlcv_dataframe(length=80, seed=3).to_csv(
                data_dir / "BBCA.csv", index=False
            )
            pd.DataFrame({"date": ["2025-01-01"], "open": [1]}).to_csv(
                data_dir / "BROKEN.csv", index=False
            )

            summary_df, skipped_df, aggregate_df = evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
                evaluate_strict=True,
            )

            self.assertFalse(summary_df.empty)
            self.assertIn("BBCA", summary_df["ticker"].tolist())
            self.assertFalse(skipped_df.empty)
            self.assertIn("BROKEN", skipped_df["ticker"].tolist())
            self.assertFalse(aggregate_df.empty)
            self.assertTrue((output_dir / "phase_a_summary.csv").exists())

    def test_evaluate_folder_reports_missing_data_directory_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_dir = Path(tmp_dir) / "missing-data"

            with self.assertRaises(EvaluationCliError) as context:
                evaluate_folder(folder_path=missing_dir)

            self.assertIn("Data directory not found", str(context.exception))

    def test_evaluate_folder_can_apply_frozen_baseline_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = root / "phase_a_baseline_final.json"
            metadata_path = root / "ticker_metadata.csv"
            data_dir.mkdir()

            make_example_ohlcv_dataframe(length=80, seed=3).to_csv(data_dir / "BBCA.csv", index=False)
            pd.DataFrame(
                {
                    "ticker": ["BBCA"],
                    "sector": ["finance"],
                    "market_cap_group": ["big_cap"],
                    "category": ["bank"],
                    "beta_group": ["medium"],
                }
            ).to_csv(metadata_path, index=False)
            baseline_path.write_text(
                json.dumps(
                    {
                        "default_volume_spike_threshold": 2.0,
                        "strict_mode_default": True,
                        "adaptive_threshold_enabled": True,
                        "group_threshold_overrides": [
                            {
                                "group_field": "sector",
                                "group_value": "finance",
                                "threshold": 2.5,
                                "decision_confidence": "strong",
                                "sample_status": "enough_sample",
                            }
                        ],
                        "min_trades_floor": 8,
                        "readiness_status": "partially_ready",
                        "baseline_status": "provisional",
                    }
                ),
                encoding="utf-8",
            )

            summary_df, _, _ = evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                metadata_file=metadata_path,
            )

            self.assertEqual(2.5, float(summary_df.loc[0, "phase_a_applied_threshold"]))
            self.assertTrue(bool(summary_df.loc[0, "phase_a_applied_strict_mode"]))

    def test_evaluate_folder_can_run_with_candle_volume_confirmation_starter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            data_dir.mkdir()

            make_example_ohlcv_dataframe(length=90, seed=13).to_csv(data_dir / "BBCA.csv", index=False)

            summary_df, _, _ = evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
                require_candle_volume_confirmation=True,
                candle_volume_confirmation_threshold=1.2,
            )

            self.assertIn("phase_b_candle_confirmation_enabled", summary_df.columns)
            self.assertIn("phase_b_candle_confirmation_threshold", summary_df.columns)
            self.assertTrue(bool(summary_df.loc[0, "phase_b_candle_confirmation_enabled"]))
            self.assertEqual(1.2, float(summary_df.loc[0, "phase_b_candle_confirmation_threshold"]))

    def test_evaluate_folder_exports_official_candle_confirmation_experiment_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = root / "phase_a_baseline_final.json"
            data_dir.mkdir()

            make_example_ohlcv_dataframe(length=90, seed=13).to_csv(data_dir / "BBCA.csv", index=False)
            make_example_ohlcv_dataframe(length=90, seed=21).to_csv(data_dir / "BMRI.csv", index=False)
            baseline_path.write_text(
                json.dumps(
                    {
                        "default_volume_spike_threshold": 2.0,
                        "strict_mode_default": False,
                        "adaptive_threshold_enabled": False,
                        "group_threshold_overrides": [],
                        "min_trades_floor": 8,
                        "readiness_status": "ready",
                        "baseline_status": "final",
                        "strict_mode_decision_code": "strict_default_no",
                    }
                ),
                encoding="utf-8",
            )

            evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                require_candle_volume_confirmation=True,
                candle_volume_confirmation_threshold=1.0,
            )

            per_ticker_path = output_dir / "phase_b_item5_candle_confirmation_per_ticker.csv"
            summary_path = output_dir / "phase_b_item5_candle_confirmation_summary.json"
            report_path = output_dir / "phase_b_item5_candle_confirmation_report.txt"

            self.assertTrue(per_ticker_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertTrue(report_path.exists())

            per_ticker_df = pd.read_csv(per_ticker_path)
            payload = json.loads(summary_path.read_text(encoding="utf-8"))

            self.assertFalse(per_ticker_df.empty)
            self.assertIn("delta_phase_a_total_trades", per_ticker_df.columns)
            self.assertEqual("measured", payload["comparison_status"])
            self.assertEqual(
                "baseline_phase_a_vs_baseline_plus_candle_confirmation",
                payload["comparison_scope"],
            )
            self.assertEqual(2, payload["aggregate"]["ticker_count"])
            self.assertEqual(1.0, payload["experiment_arm"]["candle_volume_confirmation_threshold"])

    def test_evaluate_folder_can_run_with_weekly_trend_confirmation_starter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            data_dir.mkdir()

            make_example_ohlcv_dataframe(length=140, seed=31).to_csv(data_dir / "BBCA.csv", index=False)

            summary_df, _, _ = evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
                require_weekly_trend_confirmation=True,
                weekly_trend_method="ema20",
                weekly_require_slope_up=True,
            )

            self.assertIn("phase_b_weekly_trend_enabled", summary_df.columns)
            self.assertIn("phase_b_weekly_trend_method", summary_df.columns)
            self.assertIn("phase_b_weekly_require_slope_up", summary_df.columns)
            self.assertTrue(bool(summary_df.loc[0, "phase_b_weekly_trend_enabled"]))
            self.assertEqual("ema20", summary_df.loc[0, "phase_b_weekly_trend_method"])
            self.assertTrue(bool(summary_df.loc[0, "phase_b_weekly_require_slope_up"]))

    def test_evaluate_folder_default_run_does_not_emit_multitimeframe_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            data_dir.mkdir()

            make_example_ohlcv_dataframe(length=140, seed=31).to_csv(data_dir / "BBCA.csv", index=False)

            evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
            )

            self.assertFalse((output_dir / "phase_b_item6_multitimeframe_per_ticker.csv").exists())
            self.assertFalse((output_dir / "phase_b_item6_multitimeframe_summary.json").exists())
            self.assertFalse((output_dir / "phase_b_item6_multitimeframe_report.txt").exists())
            self.assertFalse((output_dir / "phase_b_item6_go_no_go.json").exists())

    def test_evaluate_folder_exports_official_multitimeframe_experiment_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = root / "phase_a_baseline_final.json"
            metadata_path = root / "ticker_metadata.csv"
            data_dir.mkdir()

            make_example_ohlcv_dataframe(length=140, seed=13).to_csv(data_dir / "BBCA.csv", index=False)
            make_example_ohlcv_dataframe(length=140, seed=21).to_csv(data_dir / "BMRI.csv", index=False)
            baseline_path.write_text(
                json.dumps(
                    {
                        "default_volume_spike_threshold": 2.0,
                        "strict_mode_default": False,
                        "adaptive_threshold_enabled": False,
                        "group_threshold_overrides": [],
                        "min_trades_floor": 8,
                        "readiness_status": "ready",
                        "baseline_status": "final",
                        "strict_mode_decision_code": "strict_default_no",
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                {
                    "ticker": ["BBCA", "BMRI"],
                    "sector": ["finance", "finance"],
                    "category": ["bank", "bank"],
                }
            ).to_csv(metadata_path, index=False)

            evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                metadata_file=metadata_path,
                require_weekly_trend_confirmation=True,
                weekly_trend_method="ema20",
            )

            per_ticker_path = output_dir / "phase_b_item6_multitimeframe_per_ticker.csv"
            summary_path = output_dir / "phase_b_item6_multitimeframe_summary.json"
            report_path = output_dir / "phase_b_item6_multitimeframe_report.txt"
            go_no_go_path = output_dir / "phase_b_item6_go_no_go.json"

            self.assertTrue(per_ticker_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertTrue(report_path.exists())
            self.assertTrue(go_no_go_path.exists())

            per_ticker_df = pd.read_csv(per_ticker_path)
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            go_no_go_payload = json.loads(go_no_go_path.read_text(encoding="utf-8"))

            self.assertFalse(per_ticker_df.empty)
            self.assertIn("weekly_trend_method", per_ticker_df.columns)
            self.assertEqual("measured", summary_payload["comparison_status"])
            self.assertEqual("completed", go_no_go_payload["experiment_status"])
            self.assertIn(go_no_go_payload["decision"], {"no_go", "keep_experimental", "promote_for_subset", "promote_global"})

    def test_build_multitimeframe_go_no_go_returns_no_go_when_trade_retention_collapses(self) -> None:
        comparison_df = pd.DataFrame(
            [
                {
                    "ticker": "BBCA",
                    "baseline_total_trades": 2,
                    "candidate_total_trades": 0,
                    "trade_retention_pct": 0.0,
                    "delta_win_rate": 0.0,
                    "delta_average_return": 1.2,
                    "delta_max_drawdown": 0.0,
                    "weekly_data_ready": True,
                    "sector": "finance",
                    "category": "bank",
                    "market_cap_group": "big_cap",
                    "beta_group": "medium",
                },
                {
                    "ticker": "BMRI",
                    "baseline_total_trades": 2,
                    "candidate_total_trades": 0,
                    "trade_retention_pct": 0.0,
                    "delta_win_rate": 0.0,
                    "delta_average_return": 0.8,
                    "delta_max_drawdown": 0.0,
                    "weekly_data_ready": True,
                    "sector": "finance",
                    "category": "bank",
                    "market_cap_group": "big_cap",
                    "beta_group": "medium",
                },
                {
                    "ticker": "TLKM",
                    "baseline_total_trades": 1,
                    "candidate_total_trades": 0,
                    "trade_retention_pct": 0.0,
                    "delta_win_rate": 0.0,
                    "delta_average_return": 2.5,
                    "delta_max_drawdown": 0.0,
                    "weekly_data_ready": True,
                    "sector": "telco",
                    "category": "telco",
                    "market_cap_group": "big_cap",
                    "beta_group": "medium",
                },
            ]
        )
        summary_payload = {
            "aggregate": {
                "ticker_count": 3,
                "weekly_data_ready_ticker_count": 3,
                "comparable_ticker_count": 3,
                "trade_retention_mean_pct": 0.0,
                "delta_average_return_mean": 1.5,
                "delta_win_rate_mean": 0.0,
            }
        }

        payload = build_multitimeframe_go_no_go(comparison_df, summary_payload)

        self.assertEqual("no_go", payload["decision"])
        self.assertEqual("stop", payload["next_action"])
        self.assertFalse(payload["promote_default"])
        self.assertFalse(payload["promote_subset_only"])

    def test_evaluate_folder_default_run_does_not_emit_sentiment_momentum_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            data_dir.mkdir()

            _with_sentiment_columns(make_example_ohlcv_dataframe(length=140, seed=31)).to_csv(
                data_dir / "BBCA.csv",
                index=False,
            )

            evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
            )

            self.assertFalse((output_dir / "phase_b_item7_sentiment_momentum_per_ticker.csv").exists())
            self.assertFalse((output_dir / "phase_b_item7_sentiment_momentum_summary.json").exists())
            self.assertFalse((output_dir / "phase_b_item7_sentiment_momentum_report.txt").exists())
            self.assertFalse((output_dir / "phase_b_item7_go_no_go.json").exists())

    def test_inspect_item7_sentiment_dataset_marks_valid_schema_as_usable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "BBCA.csv"
            _with_sentiment_columns(make_example_ohlcv_dataframe(length=140, seed=31)).to_csv(
                csv_path,
                index=False,
            )

            payload = inspect_item7_sentiment_dataset(csv_path)

            self.assertEqual("valid", payload["schema_status"])
            self.assertTrue(bool(payload["dataset_has_sentiment_series"]))
            self.assertTrue(bool(payload["usable_for_item7"]))
            self.assertGreater(int(payload["usable_row_count"]), 0)

    def test_inspect_item7_sentiment_dataset_marks_invalid_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "BBCA.csv"
            _with_invalid_sentiment_columns(
                make_example_ohlcv_dataframe(length=140, seed=31)
            ).to_csv(csv_path, index=False)

            payload = inspect_item7_sentiment_dataset(csv_path)

            self.assertEqual("sentiment_schema_invalid", payload["schema_status"])
            self.assertFalse(bool(payload["usable_for_item7"]))
            self.assertTrue(any("schema is invalid" in item.lower() for item in payload["invalid_reasons"]))

    def test_evaluate_folder_validate_item7_readiness_writes_blocked_artifacts_for_ohlcv_only_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            data_dir.mkdir()

            make_example_ohlcv_dataframe(length=140, seed=31).to_csv(data_dir / "BBCA.csv", index=False)

            evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
                validate_item7_readiness=True,
            )

            readiness_path = output_dir / "phase_b_item7_data_readiness.json"
            report_path = output_dir / "phase_b_item7_data_readiness_report.txt"
            checklist_path = output_dir / "phase_b_item7_rerun_checklist.txt"
            per_ticker_path = output_dir / "phase_b_item7_data_readiness_per_ticker.csv"
            schema_contract_path = output_dir / "phase_b_item7_schema_contract.json"
            runbook_path = output_dir / "phase_b_item7_execution_runbook.txt"

            self.assertTrue(readiness_path.exists())
            self.assertTrue(report_path.exists())
            self.assertTrue(checklist_path.exists())
            self.assertTrue(per_ticker_path.exists())
            self.assertTrue(schema_contract_path.exists())
            self.assertTrue(runbook_path.exists())

            readiness_payload = json.loads(readiness_path.read_text(encoding="utf-8"))
            per_ticker_df = pd.read_csv(per_ticker_path)
            schema_contract_payload = json.loads(schema_contract_path.read_text(encoding="utf-8"))
            self.assertEqual("blocked_missing_sentiment_series", readiness_payload["readiness_status"])
            self.assertFalse(bool(readiness_payload["dataset_has_sentiment_series"]))
            self.assertEqual(0, readiness_payload["valid_ticker_count"])
            self.assertEqual(1, readiness_payload["invalid_ticker_count"])
            self.assertIn("readiness_status", per_ticker_df.columns)
            self.assertEqual("ohlcv_only", per_ticker_df.loc[0, "readiness_status"])
            self.assertIn("accepted_aliases", schema_contract_payload)

    def test_evaluate_folder_require_sentiment_momentum_writes_pending_status_when_sentiment_series_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = root / "phase_a_baseline_final.json"
            data_dir.mkdir()

            make_example_ohlcv_dataframe(length=140, seed=31).to_csv(data_dir / "BBCA.csv", index=False)
            baseline_path.write_text(
                json.dumps(
                    {
                        "default_volume_spike_threshold": 2.0,
                        "strict_mode_default": False,
                        "adaptive_threshold_enabled": False,
                        "group_threshold_overrides": [],
                        "min_trades_floor": 8,
                        "readiness_status": "ready",
                        "baseline_status": "final",
                        "strict_mode_decision_code": "strict_default_no",
                    }
                ),
                encoding="utf-8",
            )

            evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                require_sentiment_momentum=True,
            )

            readiness_payload = json.loads(
                (output_dir / "phase_b_item7_data_readiness.json").read_text(encoding="utf-8")
            )
            go_no_go_payload = json.loads(
                (output_dir / "phase_b_item7_go_no_go.json").read_text(encoding="utf-8")
            )
            summary_payload = json.loads(
                (output_dir / "phase_b_item7_sentiment_momentum_summary.json").read_text(encoding="utf-8")
            )

            self.assertEqual("blocked_missing_sentiment_series", readiness_payload["readiness_status"])
            self.assertEqual("blocked_missing_sentiment_data", summary_payload["comparison_status"])
            self.assertEqual("pending", go_no_go_payload["experiment_status"])
            self.assertEqual("refresh_sentiment_data", go_no_go_payload["next_action"])

    def test_evaluate_folder_exports_official_sentiment_momentum_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "data"
            output_dir = root / "output"
            baseline_path = root / "phase_a_baseline_final.json"
            metadata_path = root / "ticker_metadata.csv"
            data_dir.mkdir()

            _with_sentiment_columns(make_example_ohlcv_dataframe(length=140, seed=13)).to_csv(
                data_dir / "BBCA.csv",
                index=False,
            )
            _with_sentiment_columns(make_example_ohlcv_dataframe(length=140, seed=21)).to_csv(
                data_dir / "BMRI.csv",
                index=False,
            )
            baseline_path.write_text(
                json.dumps(
                    {
                        "default_volume_spike_threshold": 2.0,
                        "strict_mode_default": False,
                        "adaptive_threshold_enabled": False,
                        "group_threshold_overrides": [],
                        "min_trades_floor": 8,
                        "readiness_status": "ready",
                        "baseline_status": "final",
                        "strict_mode_decision_code": "strict_default_no",
                    }
                ),
                encoding="utf-8",
            )
            pd.DataFrame(
                {
                    "ticker": ["BBCA", "BMRI"],
                    "sector": ["finance", "finance"],
                    "category": ["bank", "bank"],
                }
            ).to_csv(metadata_path, index=False)

            evaluate_folder(
                folder_path=data_dir,
                output_dir=output_dir,
                baseline_config=baseline_path,
                metadata_file=metadata_path,
                require_sentiment_momentum=True,
                sentiment_momentum_window=3,
                sentiment_baseline_window=7,
                sentiment_momentum_threshold=0.0,
                sentiment_momentum_mode="weighted",
            )

            per_ticker_path = output_dir / "phase_b_item7_sentiment_momentum_per_ticker.csv"
            summary_path = output_dir / "phase_b_item7_sentiment_momentum_summary.json"
            report_path = output_dir / "phase_b_item7_sentiment_momentum_report.txt"
            go_no_go_path = output_dir / "phase_b_item7_go_no_go.json"
            readiness_path = output_dir / "phase_b_item7_data_readiness.json"
            checklist_path = output_dir / "phase_b_item7_rerun_checklist.txt"
            readiness_per_ticker_path = output_dir / "phase_b_item7_data_readiness_per_ticker.csv"
            schema_contract_path = output_dir / "phase_b_item7_schema_contract.json"
            runbook_path = output_dir / "phase_b_item7_execution_runbook.txt"

            self.assertTrue(per_ticker_path.exists())
            self.assertTrue(summary_path.exists())
            self.assertTrue(report_path.exists())
            self.assertTrue(go_no_go_path.exists())
            self.assertTrue(readiness_path.exists())
            self.assertTrue(checklist_path.exists())
            self.assertTrue(readiness_per_ticker_path.exists())
            self.assertTrue(schema_contract_path.exists())
            self.assertTrue(runbook_path.exists())

            per_ticker_df = pd.read_csv(per_ticker_path)
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            go_no_go_payload = json.loads(go_no_go_path.read_text(encoding="utf-8"))
            readiness_payload = json.loads(readiness_path.read_text(encoding="utf-8"))
            readiness_per_ticker_df = pd.read_csv(readiness_per_ticker_path)

            self.assertFalse(per_ticker_df.empty)
            self.assertIn("sentiment_momentum_mode", per_ticker_df.columns)
            self.assertEqual("measured", summary_payload["comparison_status"])
            self.assertEqual("completed", go_no_go_payload["experiment_status"])
            self.assertEqual("ready", readiness_payload["readiness_status"])
            self.assertTrue(bool(readiness_payload["dataset_is_item7_ready"]))
            self.assertIn("blocker_reason", readiness_per_ticker_df.columns)
            self.assertTrue(readiness_per_ticker_df["metadata_synced"].fillna(False).all())
            self.assertIn(go_no_go_payload["decision"], {"no_go", "keep_experimental", "promote_for_subset", "promote_global"})

    def test_build_sentiment_momentum_go_no_go_returns_no_go_when_trade_retention_collapses(self) -> None:
        comparison_df = pd.DataFrame(
            [
                {
                    "ticker": "BBCA",
                    "baseline_total_trades": 2,
                    "candidate_total_trades": 0,
                    "trade_retention_pct": 0.0,
                    "delta_win_rate": 0.0,
                    "delta_average_return": 1.2,
                    "delta_max_drawdown": 0.0,
                    "sentiment_data_ready": True,
                    "sector": "finance",
                    "category": "bank",
                    "market_cap_group": "big_cap",
                    "beta_group": "medium",
                },
                {
                    "ticker": "BMRI",
                    "baseline_total_trades": 2,
                    "candidate_total_trades": 0,
                    "trade_retention_pct": 0.0,
                    "delta_win_rate": 0.0,
                    "delta_average_return": 0.8,
                    "delta_max_drawdown": 0.0,
                    "sentiment_data_ready": True,
                    "sector": "finance",
                    "category": "bank",
                    "market_cap_group": "big_cap",
                    "beta_group": "medium",
                },
                {
                    "ticker": "TLKM",
                    "baseline_total_trades": 1,
                    "candidate_total_trades": 0,
                    "trade_retention_pct": 0.0,
                    "delta_win_rate": 0.0,
                    "delta_average_return": 2.5,
                    "delta_max_drawdown": 0.0,
                    "sentiment_data_ready": True,
                    "sector": "telco",
                    "category": "telco",
                    "market_cap_group": "big_cap",
                    "beta_group": "medium",
                },
            ]
        )
        summary_payload = {
            "aggregate": {
                "ticker_count": 3,
                "sentiment_data_ready_ticker_count": 3,
                "comparable_ticker_count": 3,
                "trade_retention_mean_pct": 0.0,
                "delta_average_return_mean": 1.5,
                "delta_win_rate_mean": 0.0,
            }
        }

        payload = build_sentiment_momentum_go_no_go(comparison_df, summary_payload)

        self.assertEqual("no_go", payload["decision"])
        self.assertEqual("stop", payload["next_action"])
        self.assertFalse(payload["promote_default"])
        self.assertFalse(payload["promote_subset_only"])


if __name__ == "__main__":
    unittest.main()
