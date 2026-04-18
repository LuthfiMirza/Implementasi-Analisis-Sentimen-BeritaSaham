"""Phase A signal research utilities based on OHLCV data.

This module adds:
1. Volume spike features
2. EMA50 trend features
3. Phase A buy signals
4. A simple, reusable backtest comparison pipeline
5. An optional Phase B candlestick-volume confirmation starter

Assumed input columns:
['date', 'open', 'high', 'low', 'close', 'volume']
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ["date", "open", "high", "low", "close", "volume"]
NUMERIC_COLUMNS = ["open", "high", "low", "close", "volume"]
DEFAULT_VOLUME_SPIKE_THRESHOLD = 2.0
DEFAULT_CANDLE_VOLUME_CONFIRMATION_THRESHOLD = 1.0
DEFAULT_WEEKLY_TREND_METHOD = "ema20"
DEFAULT_SENTIMENT_MOMENTUM_WINDOW = 3
DEFAULT_SENTIMENT_BASELINE_WINDOW = 7
DEFAULT_SENTIMENT_MOMENTUM_THRESHOLD = 0.0
DEFAULT_SENTIMENT_MOMENTUM_MODE = "weighted"
SENTIMENT_DAILY_COLUMNS = [
    "sentiment_average_1d",
    "sentiment_weighted_1d",
    "sentiment_news_count_1d",
]
SENTIMENT_SCORE_COLUMNS = [
    "sentiment_average_1d",
    "sentiment_weighted_1d",
]


@dataclass(frozen=True)
class BacktestResult:
    """Container for one strategy backtest result."""

    strategy: str
    total_trades: int
    win_rate: float
    average_return: float
    max_drawdown: float
    trades: pd.DataFrame
    equity_curve: pd.DataFrame


def _validate_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize an OHLCV DataFrame.

    Parameters
    ----------
    df:
        Input DataFrame with OHLCV columns.

    Returns
    -------
    pd.DataFrame
        A sorted copy of the input DataFrame with normalized dtypes.

    Raises
    ------
    TypeError
        If the input is not a pandas DataFrame.
    ValueError
        If required columns are missing or the frame is empty.
    """

    if not isinstance(df, pd.DataFrame):
        raise TypeError("Input must be a pandas DataFrame.")

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(
            "Missing required OHLCV columns: "
            f"{missing}. Expected columns are {REQUIRED_COLUMNS}."
        )

    if df.empty:
        raise ValueError("Input DataFrame is empty. Provide at least one OHLCV row.")

    frame = df.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if frame["date"].isna().all():
        raise ValueError("Column 'date' could not be parsed as datetime values.")

    frame = frame.sort_values("date").reset_index(drop=True)

    for column in NUMERIC_COLUMNS:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    invalid_numeric = [column for column in NUMERIC_COLUMNS if frame[column].isna().all()]
    if invalid_numeric:
        raise ValueError(
            "Numeric OHLCV columns contain no usable numeric values: "
            f"{invalid_numeric}."
        )

    return frame


def _validate_volume_spike_threshold(volume_spike_threshold: float) -> float:
    """Validate the configurable volume spike threshold."""

    try:
        threshold = float(volume_spike_threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("volume_spike_threshold must be a numeric value.") from exc

    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("volume_spike_threshold must be a finite value greater than 0.")

    return threshold


def _validate_candle_volume_confirmation_threshold(
    candle_volume_confirmation_threshold: float,
) -> float:
    """Validate the optional candlestick confirmation volume ratio."""

    try:
        threshold = float(candle_volume_confirmation_threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "candle_volume_confirmation_threshold must be a numeric value."
        ) from exc

    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError(
            "candle_volume_confirmation_threshold must be a finite value greater than 0."
        )

    return threshold


def _validate_weekly_trend_method(weekly_trend_method: str) -> str:
    """Validate the supported multi-timeframe trend method."""

    method = str(weekly_trend_method or "").strip().lower()
    if method != DEFAULT_WEEKLY_TREND_METHOD:
        raise ValueError(
            "weekly_trend_method must be 'ema20' for the current limited experiment."
        )
    return method


def _validate_sentiment_window(value: int, label: str) -> int:
    """Validate sentiment rolling-window inputs."""

    try:
        window = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer >= 1.") from exc

    if window < 1:
        raise ValueError(f"{label} must be an integer >= 1.")

    return window


def _validate_sentiment_momentum_threshold(sentiment_momentum_threshold: float) -> float:
    """Validate the optional sentiment momentum threshold."""

    try:
        threshold = float(sentiment_momentum_threshold)
    except (TypeError, ValueError) as exc:
        raise ValueError("sentiment_momentum_threshold must be a numeric value.") from exc

    if not np.isfinite(threshold):
        raise ValueError("sentiment_momentum_threshold must be finite.")

    return threshold


def _validate_sentiment_momentum_mode(sentiment_momentum_mode: str) -> str:
    """Validate the supported sentiment momentum modes."""

    mode = str(sentiment_momentum_mode or "").strip().lower()
    if mode not in {"average", "weighted", "delta"}:
        raise ValueError(
            "sentiment_momentum_mode must be one of: average, weighted, delta."
        )
    return mode


def validate_sentiment_series_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize the optional daily sentiment columns.

    The export path is expected to emit a complete value on every trading row.
    Missing columns, blank cells, non-numeric values, negative article counts,
    or fractional article counts are treated as schema errors so the evaluator
    can fail loudly instead of silently degrading into zero-filled data.
    """

    frame = _validate_ohlcv_frame(df)
    missing_columns = [column for column in SENTIMENT_DAILY_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(
            "Sentiment momentum requires daily sentiment columns: "
            f"{missing_columns}. Re-export the dataset with sentiment series enabled."
        )

    working = frame.copy()
    invalid_details = []

    for column in SENTIMENT_SCORE_COLUMNS:
        raw_series = working[column]
        numeric_series = pd.to_numeric(raw_series, errors="coerce")
        invalid_mask = raw_series.isna() | numeric_series.isna()
        invalid_count = int(invalid_mask.sum())
        if invalid_count:
            invalid_details.append(f"{column} has {invalid_count} invalid or blank rows")
        working[column] = numeric_series

    count_column = "sentiment_news_count_1d"
    raw_count_series = working[count_column]
    numeric_count_series = pd.to_numeric(raw_count_series, errors="coerce")
    invalid_count_mask = raw_count_series.isna() | numeric_count_series.isna()
    invalid_count_total = int(invalid_count_mask.sum())
    if invalid_count_total:
        invalid_details.append(f"{count_column} has {invalid_count_total} invalid or blank rows")
    else:
        fractional_mask = (numeric_count_series % 1).ne(0)
        fractional_total = int(fractional_mask.sum())
        if fractional_total:
            invalid_details.append(f"{count_column} has {fractional_total} non-integer rows")
        negative_total = int((numeric_count_series < 0).sum())
        if negative_total:
            invalid_details.append(f"{count_column} has {negative_total} negative rows")

    if invalid_details:
        detail_text = "; ".join(invalid_details)
        raise ValueError(
            "Sentiment momentum found daily sentiment columns but the schema is invalid: "
            f"{detail_text}."
        )

    working[count_column] = numeric_count_series.astype(int)

    return working


def add_volume_features(
    df: pd.DataFrame,
    volume_spike_threshold: float = DEFAULT_VOLUME_SPIKE_THRESHOLD,
) -> pd.DataFrame:
    """Add MA20 volume and spike classification features.

    Added columns
    -------------
    vol_ma20:
        Rolling 20-bar mean of volume.
    volume_ratio:
        Current volume divided by vol_ma20.
    is_volume_spike:
        True when volume_ratio is above the configured threshold.
    spike_level:
        One of: none, mild, strong, extreme.

    Notes
    -----
    - The first 19 rows will contain NaN for vol_ma20 and volume_ratio.
    - Division by zero is avoided when vol_ma20 equals zero.
    """

    threshold = _validate_volume_spike_threshold(volume_spike_threshold)
    frame = _validate_ohlcv_frame(df)

    frame["vol_ma20"] = frame["volume"].rolling(window=20, min_periods=20).mean()

    volume_values = frame["volume"].to_numpy(dtype=float)
    vol_ma20_values = frame["vol_ma20"].to_numpy(dtype=float)
    valid_denominator = np.isfinite(vol_ma20_values) & (vol_ma20_values != 0)

    volume_ratio = np.full(len(frame), np.nan, dtype=float)
    np.divide(
        volume_values,
        vol_ma20_values,
        out=volume_ratio,
        where=valid_denominator,
    )

    frame["volume_ratio"] = volume_ratio
    frame["is_volume_spike"] = frame["volume_ratio"].ge(threshold).fillna(False)

    conditions = [
        frame["volume_ratio"].ge(3.0),
        frame["volume_ratio"].ge(2.0) & frame["volume_ratio"].lt(3.0),
        frame["volume_ratio"].ge(1.5) & frame["volume_ratio"].lt(2.0),
    ]
    labels = ["extreme", "strong", "mild"]
    frame["spike_level"] = np.select(conditions, labels, default="none")

    return frame


def add_trend_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add EMA50 trend filter features.

    Added columns
    -------------
    ema50:
        50-period EMA of close.
    trend_ok:
        True when close > ema50.
    ema50_slope_up:
        True when ema50 is above its prior value.

    Notes
    -----
    - The first 49 rows will contain NaN for ema50 because `min_periods=50`.
    - Derived boolean columns default to False when EMA history is incomplete.
    """

    frame = _validate_ohlcv_frame(df)

    frame["ema50"] = frame["close"].ewm(span=50, adjust=False, min_periods=50).mean()

    frame["trend_ok"] = (
        frame["close"].gt(frame["ema50"]) & frame["ema50"].notna()
    ).fillna(False)
    frame["ema50_slope_up"] = (
        frame["ema50"].gt(frame["ema50"].shift(1))
        & frame["ema50"].notna()
        & frame["ema50"].shift(1).notna()
    ).fillna(False)

    return frame


def add_candlestick_volume_confirmation_features(
    df: pd.DataFrame,
    candle_volume_confirmation_threshold: float = DEFAULT_CANDLE_VOLUME_CONFIRMATION_THRESHOLD,
) -> pd.DataFrame:
    """Add optional candlestick confirmation features for the Phase B starter.

    Added columns
    -------------
    is_bullish_candle:
        True when close > open.
    candle_body_ratio:
        Absolute candle body divided by the full candle range.
    candle_volume_confirmed:
        True when a bullish candle is backed by volume at or above the chosen
        rolling MA20 ratio.

    Notes
    -----
    - This helper is backward-compatible: it reuses existing `volume_ratio`
      when available and computes volume features only when needed.
    - The default confirmation threshold is 1.0, meaning volume must at least
      match the 20-bar rolling average.
    """

    threshold = _validate_candle_volume_confirmation_threshold(
        candle_volume_confirmation_threshold
    )
    frame = _validate_ohlcv_frame(df)

    if "volume_ratio" not in frame.columns or "vol_ma20" not in frame.columns:
        frame = add_volume_features(frame)

    candle_range = (frame["high"] - frame["low"]).to_numpy(dtype=float)
    candle_body = (frame["close"] - frame["open"]).abs().to_numpy(dtype=float)
    valid_range = np.isfinite(candle_range) & (candle_range > 0)

    body_ratio = np.zeros(len(frame), dtype=float)
    np.divide(candle_body, candle_range, out=body_ratio, where=valid_range)

    frame["is_bullish_candle"] = frame["close"].gt(frame["open"]).fillna(False)
    frame["candle_body_ratio"] = body_ratio
    frame["candle_volume_confirmed"] = (
        frame["is_bullish_candle"] & frame["volume_ratio"].ge(threshold)
    ).fillna(False)

    return frame


def aggregate_weekly_ohlcv(
    df: pd.DataFrame,
    week_anchor: str = "W-FRI",
) -> pd.DataFrame:
    """Aggregate daily OHLCV bars into weekly bars ending on Friday."""

    frame = _validate_ohlcv_frame(df)
    working = frame.copy()
    working["week_end"] = working["date"].dt.to_period(week_anchor).dt.end_time.dt.normalize()

    weekly = (
        working.groupby("week_end", as_index=False)
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .rename(columns={"week_end": "date"})
    )

    return weekly.reindex(columns=REQUIRED_COLUMNS)


def add_weekly_trend_confirmation_features(
    df: pd.DataFrame,
    weekly_trend_method: str = DEFAULT_WEEKLY_TREND_METHOD,
    weekly_require_slope_up: bool = False,
) -> pd.DataFrame:
    """Add lagged weekly trend features used to gate daily entries.

    Notes
    -----
    - The weekly signal is shifted forward by one week before joining back to
      daily bars so daily entries never see an unfinished weekly candle.
    - EMA20 uses a short warmup (`min_periods=5`) so limited-experiment
      datasets with only a few months of history can still be measured.
    """

    method = _validate_weekly_trend_method(weekly_trend_method)
    frame = _validate_ohlcv_frame(df)

    weekly = aggregate_weekly_ohlcv(frame)
    if method == DEFAULT_WEEKLY_TREND_METHOD:
        weekly["weekly_ema20"] = weekly["close"].ewm(
            span=20,
            adjust=False,
            min_periods=5,
        ).mean()
        weekly["weekly_trend_ok"] = (
            weekly["close"].gt(weekly["weekly_ema20"]) & weekly["weekly_ema20"].notna()
        ).fillna(False)
    else:  # pragma: no cover - guarded by validator
        raise ValueError(f"Unsupported weekly trend method: {method}")

    weekly["weekly_ema20_slope_up"] = (
        weekly["weekly_ema20"].gt(weekly["weekly_ema20"].shift(1))
        & weekly["weekly_ema20"].notna()
        & weekly["weekly_ema20"].shift(1).notna()
    ).fillna(False)
    weekly["weekly_trend_data_ready"] = weekly["weekly_ema20"].notna().fillna(False)
    weekly["weekly_trend_confirmed"] = weekly["weekly_trend_ok"]
    if weekly_require_slope_up:
        weekly["weekly_trend_confirmed"] = (
            weekly["weekly_trend_confirmed"] & weekly["weekly_ema20_slope_up"]
        ).fillna(False)

    weekly["apply_week_end"] = weekly["date"] + pd.Timedelta(days=7)
    daily = frame.copy()
    daily["week_end"] = daily["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
    merged = daily.merge(
        weekly[
            [
                "date",
                "apply_week_end",
                "close",
                "weekly_ema20",
                "weekly_trend_ok",
                "weekly_ema20_slope_up",
                "weekly_trend_data_ready",
                "weekly_trend_confirmed",
            ]
        ].rename(
            columns={
                "date": "weekly_reference_week_end",
                "close": "weekly_close",
            }
        ),
        left_on="week_end",
        right_on="apply_week_end",
        how="left",
    )

    for column in [
        "weekly_trend_ok",
        "weekly_ema20_slope_up",
        "weekly_trend_data_ready",
        "weekly_trend_confirmed",
    ]:
        merged[column] = (
            pd.Series(merged[column], index=merged.index, dtype="boolean")
            .fillna(False)
            .astype(bool)
        )
    return merged.drop(columns=["apply_week_end"])


def add_sentiment_momentum_features(
    df: pd.DataFrame,
    sentiment_momentum_window: int = DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    sentiment_baseline_window: int = DEFAULT_SENTIMENT_BASELINE_WINDOW,
    sentiment_momentum_threshold: float = DEFAULT_SENTIMENT_MOMENTUM_THRESHOLD,
    sentiment_momentum_mode: str = DEFAULT_SENTIMENT_MOMENTUM_MODE,
) -> pd.DataFrame:
    """Add rolling sentiment momentum features used to gate Phase B entries.

    Required optional columns
    -------------------------
    - sentiment_average_1d
    - sentiment_weighted_1d
    - sentiment_news_count_1d

    Notes
    -----
    - The helper is backward-compatible because it only runs when explicitly
      requested by the caller.
    - Daily sentiment is aligned to each trading bar. Missing daily sentiment
      values are treated as 0, but `sentiment_momentum_data_ready` only becomes
      True when the rolling window exists and at least one article is present.
    """

    momentum_window = _validate_sentiment_window(
        sentiment_momentum_window,
        "sentiment_momentum_window",
    )
    baseline_window = _validate_sentiment_window(
        sentiment_baseline_window,
        "sentiment_baseline_window",
    )
    if baseline_window < momentum_window:
        raise ValueError(
            "sentiment_baseline_window must be greater than or equal to "
            "sentiment_momentum_window."
        )

    threshold = _validate_sentiment_momentum_threshold(sentiment_momentum_threshold)
    mode = _validate_sentiment_momentum_mode(sentiment_momentum_mode)
    working = validate_sentiment_series_columns(df)
    sentiment_average = working["sentiment_average_1d"].astype(float)
    sentiment_weighted = working["sentiment_weighted_1d"].astype(float)
    sentiment_news_count = working["sentiment_news_count_1d"].astype(float)

    working["sentiment_average_recent"] = sentiment_average.rolling(
        window=momentum_window,
        min_periods=momentum_window,
    ).mean()
    working["sentiment_average_baseline"] = sentiment_average.rolling(
        window=baseline_window,
        min_periods=baseline_window,
    ).mean()
    working["sentiment_weighted_recent"] = sentiment_weighted.rolling(
        window=momentum_window,
        min_periods=momentum_window,
    ).mean()
    working["sentiment_weighted_baseline"] = sentiment_weighted.rolling(
        window=baseline_window,
        min_periods=baseline_window,
    ).mean()
    working["sentiment_momentum_news_count_recent"] = sentiment_news_count.rolling(
        window=momentum_window,
        min_periods=momentum_window,
    ).sum()
    working["sentiment_momentum_news_count_baseline"] = sentiment_news_count.rolling(
        window=baseline_window,
        min_periods=baseline_window,
    ).sum()

    working["sentiment_average_delta"] = (
        working["sentiment_average_recent"] - working["sentiment_average_baseline"]
    )
    working["sentiment_weighted_delta"] = (
        working["sentiment_weighted_recent"] - working["sentiment_weighted_baseline"]
    )
    working["sentiment_momentum_data_ready"] = (
        working["sentiment_average_recent"].notna()
        & working["sentiment_average_baseline"].notna()
        & working["sentiment_weighted_recent"].notna()
        & working["sentiment_weighted_baseline"].notna()
        & (
            working["sentiment_momentum_news_count_recent"].gt(0)
            | working["sentiment_momentum_news_count_baseline"].gt(0)
        )
    ).fillna(False)

    if mode == "average":
        working["sentiment_momentum_value"] = working["sentiment_average_delta"]
        working["sentiment_momentum_confirmed"] = (
            working["sentiment_momentum_data_ready"]
            & working["sentiment_average_delta"].ge(threshold)
        ).fillna(False)
    elif mode == "weighted":
        working["sentiment_momentum_value"] = working["sentiment_weighted_delta"]
        working["sentiment_momentum_confirmed"] = (
            working["sentiment_momentum_data_ready"]
            & working["sentiment_weighted_recent"].gt(0)
            & working["sentiment_weighted_delta"].ge(threshold)
        ).fillna(False)
    else:
        working["sentiment_momentum_value"] = working["sentiment_weighted_delta"]
        working["sentiment_momentum_confirmed"] = (
            working["sentiment_momentum_data_ready"]
            & working["sentiment_weighted_delta"].ge(threshold)
        ).fillna(False)

    return working


def generate_phase_a_signal(
    df: pd.DataFrame,
    strict: bool = False,
    volume_spike_threshold: float = DEFAULT_VOLUME_SPIKE_THRESHOLD,
    require_candle_volume_confirmation: bool = False,
    candle_volume_confirmation_threshold: float = DEFAULT_CANDLE_VOLUME_CONFIRMATION_THRESHOLD,
    require_weekly_trend_confirmation: bool = False,
    weekly_trend_method: str = DEFAULT_WEEKLY_TREND_METHOD,
    weekly_require_slope_up: bool = False,
    require_sentiment_momentum: bool = False,
    sentiment_momentum_window: int = DEFAULT_SENTIMENT_MOMENTUM_WINDOW,
    sentiment_baseline_window: int = DEFAULT_SENTIMENT_BASELINE_WINDOW,
    sentiment_momentum_threshold: float = DEFAULT_SENTIMENT_MOMENTUM_THRESHOLD,
    sentiment_momentum_mode: str = DEFAULT_SENTIMENT_MOMENTUM_MODE,
) -> pd.DataFrame:
    """Generate Phase A buy signals.

    Minimum Phase A signal
    ----------------------
    - close > ema50
    - volume_ratio >= 2

    Strict Phase A signal
    ---------------------
    - close > ema50
    - ema50_slope_up == True
    - volume_ratio >= 2
    - close > open

    Parameters
    ----------
    df:
        Input OHLCV DataFrame.
    strict:
        When True, use the stricter signal definition.
    volume_spike_threshold:
        Minimum volume_ratio required to qualify as a Phase A volume spike.
    require_candle_volume_confirmation:
        When True, require the signal candle to be bullish and backed by at
        least the configured rolling volume ratio. Default is False so the
        existing Phase A behavior is unchanged.
    candle_volume_confirmation_threshold:
        Minimum `volume_ratio` used by the optional candlestick confirmation
        filter. Default: 1.0.
    require_weekly_trend_confirmation:
        When True, require the last completed weekly bar to confirm the trend
        before daily entries are allowed. Default is False.
    weekly_trend_method:
        Weekly trend method used by the limited experiment. Default: ema20.
    weekly_require_slope_up:
        When True, the weekly EMA20 must also slope upward.
    require_sentiment_momentum:
        When True, require the recent sentiment window to be stronger than the
        baseline sentiment window according to the configured mode.
    sentiment_momentum_window:
        Rolling window length used for the recent sentiment average.
    sentiment_baseline_window:
        Rolling window length used for the baseline sentiment average.
    sentiment_momentum_threshold:
        Minimum delta required for the chosen sentiment momentum mode.
    sentiment_momentum_mode:
        One of average, weighted, or delta.

    Returns
    -------
    pd.DataFrame
        Feature-enriched DataFrame with the signal column added.
    """

    threshold = _validate_volume_spike_threshold(volume_spike_threshold)
    frame = add_trend_features(add_volume_features(df, volume_spike_threshold=threshold))
    frame = add_candlestick_volume_confirmation_features(
        frame,
        candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
    )
    if require_weekly_trend_confirmation:
        frame = add_weekly_trend_confirmation_features(
            frame,
            weekly_trend_method=weekly_trend_method,
            weekly_require_slope_up=weekly_require_slope_up,
        )
    if require_sentiment_momentum:
        frame = add_sentiment_momentum_features(
            frame,
            sentiment_momentum_window=sentiment_momentum_window,
            sentiment_baseline_window=sentiment_baseline_window,
            sentiment_momentum_threshold=sentiment_momentum_threshold,
            sentiment_momentum_mode=sentiment_momentum_mode,
        )

    signal_column = "phase_a_signal_strict" if strict else "phase_a_signal"

    minimum_signal = frame["close"].gt(frame["ema50"]) & frame["volume_ratio"].ge(threshold)
    if require_candle_volume_confirmation:
        minimum_signal = minimum_signal & frame["candle_volume_confirmed"]
    if require_weekly_trend_confirmation:
        minimum_signal = minimum_signal & frame["weekly_trend_confirmed"]
    if require_sentiment_momentum:
        minimum_signal = minimum_signal & frame["sentiment_momentum_confirmed"]

    if strict:
        frame[signal_column] = (
            minimum_signal
            & frame["ema50_slope_up"]
            & frame["close"].gt(frame["open"])
        ).fillna(False)
    else:
        frame[signal_column] = minimum_signal.fillna(False)

    return frame


def generate_baseline_signal(
    df: pd.DataFrame,
    column_name: str = "baseline_signal",
) -> pd.DataFrame:
    """Generate a conservative default baseline signal.

    The repository did not include an existing Python baseline signal pipeline, so
    this baseline uses a simple bullish-candle rule:
    - close > open

    This makes comparison against Phase A explicit and easy to replace later.
    """

    frame = _validate_ohlcv_frame(df)
    frame[column_name] = frame["close"].gt(frame["open"]).fillna(False)
    return frame


def backtest_signal_frame(
    df: pd.DataFrame,
    signal_column: str,
    hold_period: int = 5,
    allow_overlap: bool = False,
) -> BacktestResult:
    """Backtest a boolean signal column with next-open entry.

    Entry and exit rules
    --------------------
    - Signal is evaluated at bar `t` close.
    - Entry is executed at bar `t+1` open.
    - Exit is executed at bar `t+hold_period` close.

    Output metrics are expressed in percentages.
    """

    if hold_period < 1:
        raise ValueError("hold_period must be >= 1.")

    frame = _validate_ohlcv_frame(df)
    if signal_column not in frame.columns:
        raise ValueError(
            f"Signal column '{signal_column}' was not found. "
            "Generate the signal before calling the backtest."
        )

    signal_series = frame[signal_column].fillna(False).astype(bool).to_numpy()
    trades = []
    next_eligible_index = 0

    for signal_index, is_signal in enumerate(signal_series):
        if not is_signal:
            continue
        if not allow_overlap and signal_index < next_eligible_index:
            continue

        entry_index = signal_index + 1
        exit_index = signal_index + hold_period

        if entry_index >= len(frame) or exit_index >= len(frame):
            continue

        entry_price = frame.at[entry_index, "open"]
        exit_price = frame.at[exit_index, "close"]

        if pd.isna(entry_price) or pd.isna(exit_price) or entry_price <= 0:
            continue

        trade_return = (exit_price - entry_price) / entry_price
        trades.append(
            {
                "signal_date": frame.at[signal_index, "date"],
                "entry_date": frame.at[entry_index, "date"],
                "exit_date": frame.at[exit_index, "date"],
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "return": float(trade_return),
                "return_pct": float(trade_return * 100.0),
                "is_win": bool(trade_return > 0),
            }
        )

        if not allow_overlap:
            next_eligible_index = exit_index + 1

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        empty_curve = pd.DataFrame(columns=["trade_number", "equity", "drawdown"])
        return BacktestResult(
            strategy=signal_column,
            total_trades=0,
            win_rate=0.0,
            average_return=0.0,
            max_drawdown=0.0,
            trades=trades_df,
            equity_curve=empty_curve,
        )

    equity = (1.0 + trades_df["return"]).cumprod()
    running_peak = equity.cummax()
    drawdown = (equity / running_peak) - 1.0

    equity_curve = pd.DataFrame(
        {
            "trade_number": np.arange(1, len(trades_df) + 1, dtype=int),
            "equity": equity,
            "drawdown": drawdown,
        }
    )

    total_trades = int(len(trades_df))
    win_rate = float(trades_df["is_win"].mean() * 100.0)
    average_return = float(trades_df["return_pct"].mean())
    max_drawdown = float(abs(drawdown.min()) * 100.0)

    return BacktestResult(
        strategy=signal_column,
        total_trades=total_trades,
        win_rate=round(win_rate, 2),
        average_return=round(average_return, 4),
        max_drawdown=round(max_drawdown, 4),
        trades=trades_df,
        equity_curve=equity_curve,
    )


def compare_backtest_variants(
    df: pd.DataFrame,
    hold_period: int = 5,
    allow_overlap: bool = False,
    baseline_signal_func: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = None,
    volume_spike_threshold: float = DEFAULT_VOLUME_SPIKE_THRESHOLD,
) -> Tuple[pd.DataFrame, Dict[str, BacktestResult], pd.DataFrame]:
    """Compare baseline and Phase A feature-filtered strategies.

    Strategies compared
    -------------------
    - baseline_old
    - baseline_plus_volume_spike
    - baseline_plus_volume_spike_ema50
    """

    baseline_signal_func = baseline_signal_func or generate_baseline_signal

    threshold = _validate_volume_spike_threshold(volume_spike_threshold)
    frame = add_trend_features(add_volume_features(df, volume_spike_threshold=threshold))
    frame = baseline_signal_func(frame)

    if "baseline_signal" not in frame.columns:
        raise ValueError(
            "baseline_signal_func must return a DataFrame containing "
            "'baseline_signal'."
        )

    frame["baseline_signal"] = frame["baseline_signal"].fillna(False).astype(bool)
    frame["baseline_plus_volume_spike"] = (
        frame["baseline_signal"] & frame["volume_ratio"].ge(threshold)
    ).fillna(False)
    frame["baseline_plus_volume_spike_ema50"] = (
        frame["baseline_plus_volume_spike"] & frame["close"].gt(frame["ema50"])
    ).fillna(False)

    variant_columns = [
        "baseline_signal",
        "baseline_plus_volume_spike",
        "baseline_plus_volume_spike_ema50",
    ]

    results: Dict[str, BacktestResult] = {}
    summary_rows = []

    for column in variant_columns:
        result = backtest_signal_frame(
            frame,
            signal_column=column,
            hold_period=hold_period,
            allow_overlap=allow_overlap,
        )
        strategy_name = column.replace("baseline_signal", "baseline_old")
        results[strategy_name] = BacktestResult(
            strategy=strategy_name,
            total_trades=result.total_trades,
            win_rate=result.win_rate,
            average_return=result.average_return,
            max_drawdown=result.max_drawdown,
            trades=result.trades,
            equity_curve=result.equity_curve,
        )
        summary_rows.append(
            {
                "strategy": strategy_name,
                "total_trades": result.total_trades,
                "win_rate": result.win_rate,
                "average_return": result.average_return,
                "max_drawdown": result.max_drawdown,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    return summary_df, results, frame


def run_phase_a_backtest_pipeline(
    df: pd.DataFrame,
    hold_period: int = 5,
    strict: bool = False,
    allow_overlap: bool = False,
    volume_spike_threshold: float = DEFAULT_VOLUME_SPIKE_THRESHOLD,
    require_candle_volume_confirmation: bool = False,
    candle_volume_confirmation_threshold: float = DEFAULT_CANDLE_VOLUME_CONFIRMATION_THRESHOLD,
) -> Dict[str, object]:
    """Run the complete Phase A research pipeline.

    Returns a dictionary containing:
    - feature_frame
    - comparison_summary
    - comparison_results
    - phase_a_backtest
    """

    feature_frame = generate_phase_a_signal(
        df,
        strict=strict,
        volume_spike_threshold=volume_spike_threshold,
        require_candle_volume_confirmation=require_candle_volume_confirmation,
        candle_volume_confirmation_threshold=candle_volume_confirmation_threshold,
    )
    summary_df, comparison_results, feature_frame = compare_backtest_variants(
        feature_frame,
        hold_period=hold_period,
        allow_overlap=allow_overlap,
        volume_spike_threshold=volume_spike_threshold,
    )

    phase_a_column = "phase_a_signal_strict" if strict else "phase_a_signal"
    phase_a_result = backtest_signal_frame(
        feature_frame,
        signal_column=phase_a_column,
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )

    return {
        "feature_frame": feature_frame,
        "comparison_summary": summary_df,
        "comparison_results": comparison_results,
        "phase_a_backtest": phase_a_result,
    }


def make_example_ohlcv_dataframe(length: int = 90, seed: int = 42) -> pd.DataFrame:
    """Create a deterministic sample OHLCV DataFrame for demo/testing."""

    if length < 60:
        raise ValueError("length must be at least 60 to demonstrate MA20/EMA50 features.")

    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-01", periods=length, freq="B")

    base = np.linspace(100.0, 132.0, num=length)
    noise = rng.normal(0.0, 0.7, size=length).cumsum()
    close = base + noise
    open_ = close - rng.normal(0.25, 0.35, size=length)
    volume = rng.integers(850, 1350, size=length).astype(float)

    signal_bars = {
        length - 32: 2600.0,
        length - 24: 3000.0,
        length - 18: 2800.0,
        length - 12: 2400.0,
        length - 8: 3100.0,
        length - 2: 3400.0,
    }
    for idx, spike_volume in signal_bars.items():
        if 0 <= idx < length:
            close[idx] += 1.1
            open_[idx] = close[idx] - 0.9
            volume[idx] = spike_volume

    high = np.maximum(open_, close) + rng.uniform(0.2, 1.4, size=length)
    low = np.minimum(open_, close) - rng.uniform(0.2, 1.2, size=length)

    return pd.DataFrame(
        {
            "date": dates,
            "open": np.round(open_, 2),
            "high": np.round(high, 2),
            "low": np.round(low, 2),
            "close": np.round(close, 2),
            "volume": volume.astype(int),
        }
    )


def _demo() -> None:
    """Run a small example and print the last 10 bars plus backtest summaries."""

    sample_df = make_example_ohlcv_dataframe()
    pipeline = run_phase_a_backtest_pipeline(sample_df, hold_period=5, strict=False)
    feature_frame = pipeline["feature_frame"]
    comparison_summary = pipeline["comparison_summary"]
    phase_a_result = pipeline["phase_a_backtest"]

    display_columns = [
        "date",
        "open",
        "close",
        "volume",
        "vol_ma20",
        "volume_ratio",
        "is_volume_spike",
        "spike_level",
        "ema50",
        "trend_ok",
        "ema50_slope_up",
        "phase_a_signal",
    ]

    print("\nLast 10 bars with Phase A features:\n")
    print(feature_frame[display_columns].tail(10).to_string(index=False))

    print("\nBacktest comparison summary:\n")
    print(comparison_summary.to_string(index=False))

    print("\nPhase A backtest summary:\n")
    print(
        pd.DataFrame(
            [
                {
                    "strategy": phase_a_result.strategy,
                    "total_trades": phase_a_result.total_trades,
                    "win_rate": phase_a_result.win_rate,
                    "average_return": phase_a_result.average_return,
                    "max_drawdown": phase_a_result.max_drawdown,
                }
            ]
        ).to_string(index=False)
    )


if __name__ == "__main__":
    _demo()
