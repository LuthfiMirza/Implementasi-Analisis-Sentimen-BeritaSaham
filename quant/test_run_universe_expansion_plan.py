from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from quant.run_universe_expansion_plan import main


class RunUniverseExpansionPlanTestCase(unittest.TestCase):
    def test_generates_expansion_summary_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_dir = root / "data"
            stocks_dir = data_dir / "stocks"
            universe_dir = data_dir / "universe"
            output_dir = root / "output"
            stocks_dir.mkdir(parents=True)
            universe_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)

            (data_dir / "ticker_metadata.csv").write_text(
                "\n".join(
                    [
                        "ticker,sector,rows_1d,date_start,date_end",
                        "BBCA,perbankan,2600,2004-01-01,2026-04-22",
                        "BBRI,perbankan,2600,2004-01-01,2026-04-22",
                        "TLKM,telekomunikasi,2600,2004-01-01,2026-04-22",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (stocks_dir / "rebuild_ticker_metadata.csv").write_text(
                "\n".join(
                    [
                        "ticker,symbol,status,rows,date_start,date_end,issues,output_path",
                        "BBCA,BBCA.JK,rebuilt,5392,2004-06-08,2026-04-22,,data/stocks/BBCA.csv",
                        "BBRI,BBRI.JK,rebuilt,5543,2003-11-10,2026-04-22,,data/stocks/BBRI.csv",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (output_dir / "phase_2_relative_strength_selection_summary.json").write_text(
                json.dumps(
                    {
                        "universe_size_assessment": {
                            "max_rankable_tickers_on_any_date": 7,
                        }
                    }
                ),
                encoding="utf-8",
            )
            (output_dir / "phase_2_1_relative_strength_redesign_summary.json").write_text(
                json.dumps(
                    {
                        "variant_results": [
                            {
                                "variant_id": "layer1_full_universe",
                                "active_ticker_count_median": 6.0,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (universe_dir / "layer2_expansion_target_candidates.csv").write_text(
                "\n".join(
                    [
                        "ticker,yahoo_symbol,company_name,sector_group,freeze_status,selection_source,availability_status,history_precheck,liquidity_precheck,manual_review_required,notes",
                        "BBCA,BBCA.JK,Bank Central Asia Tbk,finance,candidate_pre_freeze,repo_anchor,in_repo_clean_rebuild,pass,pass,yes,anchor",
                        "BBRI,BBRI.JK,Bank Rakyat Indonesia Tbk,finance,candidate_pre_freeze,repo_anchor,in_repo_clean_rebuild,pass,pass,yes,anchor",
                        "TLKM,TLKM.JK,Telkom Indonesia Tbk,telco,candidate_pre_freeze,repo_anchor,in_repo_clean_rebuild,pass,pass,yes,anchor",
                        "ADRO,ADRO.JK,Adaro Energy Indonesia Tbk,energy,candidate_pre_freeze,repo_present,in_repo_raw_only,pass,pass,yes,present",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "--metadata-file",
                    str(data_dir / "ticker_metadata.csv"),
                    "--rebuild-metadata-file",
                    str(stocks_dir / "rebuild_ticker_metadata.csv"),
                    "--phase-2-summary-file",
                    str(output_dir / "phase_2_relative_strength_selection_summary.json"),
                    "--phase-2-1-summary-file",
                    str(output_dir / "phase_2_1_relative_strength_redesign_summary.json"),
                    "--candidate-file",
                    str(universe_dir / "layer2_expansion_target_candidates.csv"),
                    "--output-dir",
                    str(output_dir),
                ]
            )

            self.assertEqual(0, exit_code)
            summary = json.loads((output_dir / "universe_expansion_plan_summary.json").read_text(encoding="utf-8"))
            self.assertEqual("custom_30_liquid_long_history_manual_freeze", summary["target_universe_decision"]["recommended_universe_policy"])
            self.assertEqual(30, summary["target_universe_decision"]["recommended_target_size"])
            self.assertFalse(summary["repo_metadata_assessment"]["enough_for_expanded_universe_freeze_without_external_or_manual_list"])
            self.assertEqual(4, summary["candidate_file_summary"]["candidate_count"])
            self.assertTrue((output_dir / "universe_expansion_plan_report.txt").exists())


if __name__ == "__main__":
    unittest.main()
