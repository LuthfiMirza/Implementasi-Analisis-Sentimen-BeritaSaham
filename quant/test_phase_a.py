"""Basic unit tests for Phase A signal and backtest helpers."""

import unittest

import pandas as pd

from quant.phase_a import (
    add_sentiment_momentum_features,
    add_trend_features,
    add_candlestick_volume_confirmation_features,
    add_weekly_trend_confirmation_features,
    add_volume_features,
    aggregate_weekly_ohlcv,
    compare_backtest_variants,
    generate_phase_a_signal,
    make_example_ohlcv_dataframe,
)


def _with_sentiment_columns(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    frame["sentiment_average_1d"] = 0.0
    frame["sentiment_weighted_1d"] = 0.0
    frame["sentiment_news_count_1d"] = 0

    frame.loc[55:64, "sentiment_average_1d"] = -0.2
    frame.loc[55:64, "sentiment_weighted_1d"] = -0.25
    frame.loc[55:64, "sentiment_news_count_1d"] = 1
    frame.loc[70:79, "sentiment_average_1d"] = 0.35
    frame.loc[70:79, "sentiment_weighted_1d"] = 0.45
    frame.loc[70:79, "sentiment_news_count_1d"] = 2

    return frame


class PhaseATestCase(unittest.TestCase):
    """Simple coverage for Phase A feature engineering and backtests."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.df = make_example_ohlcv_dataframe(length=80, seed=7)
        cls.df.loc[79, "volume"] = 4200
        cls.df.loc[79, "close"] = cls.df.loc[79, "close"] + 3.0
        cls.df.loc[79, "open"] = cls.df.loc[79, "close"] - 1.5

    def test_add_volume_features_creates_expected_columns(self) -> None:
        frame = add_volume_features(self.df)

        self.assertIn("vol_ma20", frame.columns)
        self.assertIn("volume_ratio", frame.columns)
        self.assertIn("is_volume_spike", frame.columns)
        self.assertIn("spike_level", frame.columns)

        self.assertTrue(pd.isna(frame.loc[0, "vol_ma20"]))
        self.assertGreaterEqual(frame.loc[79, "volume_ratio"], 2.0)
        self.assertIn(frame.loc[79, "spike_level"], {"strong", "extreme"})

    def test_add_trend_features_creates_expected_columns(self) -> None:
        frame = add_trend_features(self.df)

        self.assertIn("ema50", frame.columns)
        self.assertIn("trend_ok", frame.columns)
        self.assertIn("ema50_slope_up", frame.columns)

        self.assertTrue(pd.isna(frame.loc[10, "ema50"]))
        self.assertTrue(bool(frame.loc[79, "trend_ok"]))

    def test_generate_phase_a_signal_supports_minimum_and_strict(self) -> None:
        minimum = generate_phase_a_signal(self.df, strict=False)
        strict = generate_phase_a_signal(self.df, strict=True)

        self.assertIn("phase_a_signal", minimum.columns)
        self.assertIn("phase_a_signal_strict", strict.columns)
        self.assertTrue(bool(minimum.loc[79, "phase_a_signal"]))
        self.assertTrue(bool(strict.loc[79, "phase_a_signal_strict"]))

    def test_generate_phase_a_signal_accepts_custom_volume_threshold(self) -> None:
        tuned_df = self.df.copy()
        base_features = add_volume_features(tuned_df)
        tuned_df.loc[79, "volume"] = int(base_features.loc[79, "vol_ma20"] * 1.6)

        default_signal = generate_phase_a_signal(tuned_df, strict=False)
        loose_signal = generate_phase_a_signal(
            tuned_df,
            strict=False,
            volume_spike_threshold=1.5,
        )

        self.assertFalse(bool(default_signal.loc[79, "phase_a_signal"]))
        self.assertTrue(bool(loose_signal.loc[79, "phase_a_signal"]))

    def test_candlestick_volume_confirmation_is_optional_and_blocks_when_requested(self) -> None:
        tuned_df = self.df.copy()
        base_features = add_volume_features(tuned_df)
        tuned_df.loc[79, "volume"] = int(base_features.loc[79, "vol_ma20"] * 1.6)

        confirmation_frame = add_candlestick_volume_confirmation_features(
            tuned_df,
            candle_volume_confirmation_threshold=2.0,
        )
        without_confirmation = generate_phase_a_signal(
            tuned_df,
            strict=False,
            volume_spike_threshold=1.5,
            require_candle_volume_confirmation=False,
        )
        with_confirmation = generate_phase_a_signal(
            tuned_df,
            strict=False,
            volume_spike_threshold=1.5,
            require_candle_volume_confirmation=True,
            candle_volume_confirmation_threshold=2.0,
        )

        self.assertIn("candle_volume_confirmed", confirmation_frame.columns)
        self.assertFalse(bool(confirmation_frame.loc[79, "candle_volume_confirmed"]))
        self.assertTrue(bool(without_confirmation.loc[79, "phase_a_signal"]))
        self.assertFalse(bool(with_confirmation.loc[79, "phase_a_signal"]))

    def test_aggregate_weekly_ohlcv_rolls_daily_bars_into_weekly_bars(self) -> None:
        weekly = aggregate_weekly_ohlcv(self.df)

        self.assertLess(len(weekly), len(self.df))
        self.assertIn("date", weekly.columns)
        self.assertIn("open", weekly.columns)
        self.assertIn("close", weekly.columns)

    def test_weekly_trend_confirmation_is_optional_and_exposed_on_frame(self) -> None:
        weekly_frame = add_weekly_trend_confirmation_features(
            self.df,
            weekly_trend_method="ema20",
            weekly_require_slope_up=True,
        )
        without_weekly = generate_phase_a_signal(
            self.df,
            strict=False,
            require_weekly_trend_confirmation=False,
        )
        with_weekly = generate_phase_a_signal(
            self.df,
            strict=False,
            require_weekly_trend_confirmation=True,
            weekly_trend_method="ema20",
            weekly_require_slope_up=True,
        )

        self.assertIn("weekly_trend_confirmed", weekly_frame.columns)
        self.assertIn("weekly_ema20", weekly_frame.columns)
        self.assertIn("phase_a_signal", with_weekly.columns)
        self.assertGreaterEqual(
            int(without_weekly["phase_a_signal"].sum()),
            int(with_weekly["phase_a_signal"].sum()),
        )

    def test_sentiment_momentum_helper_creates_expected_columns(self) -> None:
        frame = add_sentiment_momentum_features(
            _with_sentiment_columns(self.df),
            sentiment_momentum_window=3,
            sentiment_baseline_window=7,
            sentiment_momentum_threshold=0.0,
            sentiment_momentum_mode="weighted",
        )

        self.assertIn("sentiment_weighted_recent", frame.columns)
        self.assertIn("sentiment_weighted_baseline", frame.columns)
        self.assertIn("sentiment_momentum_confirmed", frame.columns)
        self.assertTrue(bool(frame.loc[79, "sentiment_momentum_data_ready"]))
        self.assertTrue(bool(frame.loc[79, "sentiment_momentum_confirmed"]))

    def test_sentiment_momentum_is_optional_and_can_gate_phase_a_signal(self) -> None:
        sentiment_df = _with_sentiment_columns(self.df)
        without_momentum = generate_phase_a_signal(
            sentiment_df,
            strict=False,
            require_sentiment_momentum=False,
        )
        with_momentum = generate_phase_a_signal(
            sentiment_df,
            strict=False,
            require_sentiment_momentum=True,
            sentiment_momentum_window=3,
            sentiment_baseline_window=7,
            sentiment_momentum_threshold=0.0,
            sentiment_momentum_mode="weighted",
        )

        self.assertIn("phase_a_signal", with_momentum.columns)
        self.assertIn("sentiment_momentum_confirmed", with_momentum.columns)
        self.assertGreaterEqual(
            int(without_momentum["phase_a_signal"].sum()),
            int(with_momentum["phase_a_signal"].sum()),
        )

    def test_compare_backtest_variants_returns_required_metrics(self) -> None:
        summary, results, feature_frame = compare_backtest_variants(self.df, hold_period=3)

        self.assertEqual(
            list(summary["strategy"]),
            [
                "baseline_old",
                "baseline_plus_volume_spike",
                "baseline_plus_volume_spike_ema50",
            ],
        )
        self.assertTrue(
            {"total_trades", "win_rate", "average_return", "max_drawdown"}.issubset(
                summary.columns
            )
        )
        self.assertIn("baseline_old", results)
        self.assertIn("baseline_plus_volume_spike_ema50", results)
        self.assertIn("ema50", feature_frame.columns)

    def test_compare_backtest_variants_respects_custom_volume_threshold(self) -> None:
        loose_summary, _, _ = compare_backtest_variants(
            self.df,
            hold_period=3,
            volume_spike_threshold=1.5,
        )
        tight_summary, _, _ = compare_backtest_variants(
            self.df,
            hold_period=3,
            volume_spike_threshold=3.0,
        )

        loose_trades = loose_summary.set_index("strategy").loc[
            "baseline_plus_volume_spike", "total_trades"
        ]
        tight_trades = tight_summary.set_index("strategy").loc[
            "baseline_plus_volume_spike", "total_trades"
        ]

        self.assertGreaterEqual(loose_trades, tight_trades)


if __name__ == "__main__":
    unittest.main()
