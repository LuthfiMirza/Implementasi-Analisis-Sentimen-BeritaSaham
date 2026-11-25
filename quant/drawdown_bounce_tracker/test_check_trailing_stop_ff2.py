#!/usr/bin/env python3
"""Unit tests for Fase FF-2 check_trailing_stop.py 2.0% Activation Buffer & Chronological Hard SL."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import check_trailing_stop as cts


def make_15m_df(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(ts, tz="Asia/Jakarta") for ts, *_ in rows])
    return pd.DataFrame(
        [{"Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000} for _, o, h, l, c in rows],
        index=idx,
    )


class CheckTrailingStopFf2Test(unittest.TestCase):
    def test_chronological_sl_not_skipped_when_peak_below_2pct_buffer(self):
        """Regression for Bug #1: entry=100, peak=101 (+1%, below 2% buffer), midday close=96 (<=96.5 SL),
        EOD close=98.5 (pullback 2.47% >= 2%). Must catch chronological Hard SL at 96.0!"""
        df = make_15m_df([
            ("2026-11-24 15:45", 100, 100, 100, 100),
            ("2026-11-25 09:15", 100, 101, 99.5, 100.5),
            ("2026-11-25 14:00", 98, 98, 95.5, 96.0),
            ("2026-11-25 15:45", 97, 99, 97, 98.5),
        ])
        with patch.object(cts, "fetch_15m_since", return_value=df):
            snap = cts.compute_snapshot("BUMI", "2026-11-24", 100.0, strategy="GABUNGAN")
        self.assertIsNotNone(snap)
        self.assertLessEqual(snap["current"], 96.5, "Must catch earlier chronological SL breach at 96.0")

    def test_ts_does_not_fire_below_2pct_buffer_without_sl_breach(self):
        """Peak=+1.5% (below 2% buffer), pullback=2.5% to 99.0 (above SL 96.5) -> no TS & no SL."""
        df = make_15m_df([
            ("2026-11-24 15:45", 100, 100, 100, 100),
            ("2026-11-25 09:15", 100, 101.5, 99.5, 101.0),
            ("2026-11-25 15:45", 100, 100, 98.5, 99.0),
        ])
        with patch.object(cts, "fetch_15m_since", return_value=df):
            snap = cts.compute_snapshot("ENRG", "2026-11-24", 100.0, strategy="GABUNGAN")
        self.assertIsNotNone(snap)
        # Peak < 102 so check_position's TS guard stays False, and current=99 > SL=96.5
        self.assertLess(snap["peak"], 102.0)
        self.assertGreater(snap["current"], 96.5)

    def test_ts_fires_chronologically_once_peak_reaches_2pct_buffer(self):
        """Peak=104 (+4% >= 2% buffer), pulls back to 101.5 (-2.4%) then recovers to 103.5 -> catches 101.5 TS!"""
        df = make_15m_df([
            ("2026-11-24 15:45", 100, 100, 100, 100),
            ("2026-11-25 09:15", 102, 104, 102, 103.5),
            ("2026-11-25 11:00", 103, 103, 101, 101.5),
            ("2026-11-25 15:45", 102, 103.5, 102, 103.5),
        ])
        with patch.object(cts, "fetch_15m_since", return_value=df):
            snap = cts.compute_snapshot("ENRG", "2026-11-24", 100.0, strategy="GABUNGAN")
        self.assertIsNotNone(snap)
        self.assertGreaterEqual(snap["peak"], 102.0)
        self.assertGreaterEqual(snap["pullback"], 0.02)
        self.assertEqual(snap["current"], 101.5)


if __name__ == "__main__":
    unittest.main()
