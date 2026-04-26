#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild the prediction research dataset offline with label v2 and stronger technical features.")
    parser.add_argument("--input-dataset", default="output/prediction_research/dataset.csv")
    parser.add_argument("--output-dataset", default="output/prediction_research/dataset.csv")
    parser.add_argument("--per-ticker-dir", default="output/prediction_research/tickers")
    parser.add_argument("--stocks-dir", default="data/stocks")
    parser.add_argument("--ihsg-csv", default="data/IHSG.csv")
    parser.add_argument("--threshold-v2", type=float, default=0.015)
    return parser.parse_args()


def adjusted_stock_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    factor = np.where(
        (frame["close"].astype(float) != 0.0) & frame["adj_close"].notna(),
        frame["adj_close"].astype(float) / frame["close"].astype(float),
        1.0,
    )
    frame["date"] = pd.to_datetime(frame["date"])
    frame["close_adj"] = frame["adj_close"].fillna(frame["close"]).astype(float)
    frame["high_adj"] = frame["high"].astype(float) * factor
    frame["low_adj"] = frame["low"].astype(float) * factor
    frame["volume"] = frame["volume"].fillna(0).astype(float)
    return frame.sort_values("date").reset_index(drop=True)


def calculate_rsi_series(closes: pd.Series, period: int = 14) -> pd.Series:
    values = closes.astype(float).tolist()
    output = [np.nan] * len(values)
    for idx in range(period, len(values)):
        window = values[idx - period : idx + 1]
        changes = np.diff(window)
        gains = changes[changes > 0]
        losses = np.abs(changes[changes < 0])
        avg_gain = gains.mean() if gains.size else 0.0
        avg_loss = losses.mean() if losses.size else 0.0
        if avg_loss == 0.0:
            output[idx] = 70.0
            continue
        rs = avg_gain / avg_loss
        output[idx] = 100 - (100 / (1 + rs))
    return pd.Series(output, index=closes.index)


def build_stock_features(ticker: str, stocks_dir: Path) -> pd.DataFrame:
    frame = adjusted_stock_frame(stocks_dir / f"{ticker}.csv")
    close = frame["close_adj"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            frame["high_adj"] - frame["low_adj"],
            (frame["high_adj"] - prev_close).abs(),
            (frame["low_adj"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    true_range.iloc[0] = np.nan

    frame["return_1d"] = close.div(close.shift(1)).sub(1)
    frame["return_3d"] = close.div(close.shift(3)).sub(1)
    frame["return_5d"] = close.div(close.shift(5)).sub(1)
    frame["return_20d"] = close.div(close.shift(20)).sub(1)
    frame["atr14"] = true_range.rolling(14, min_periods=14).mean()
    frame["atr_ratio"] = frame["atr14"].div(close)
    frame["atr14_pct"] = frame["atr_ratio"]
    frame["volume_ma5"] = frame["volume"].rolling(5, min_periods=5).mean()
    frame["volume_ma20"] = frame["volume"].rolling(20, min_periods=20).mean()
    frame["volume_ratio_5d"] = frame["volume_ma5"].div(frame["volume_ma20"])
    frame["volume_ratio_20d"] = frame["volume"].div(frame["volume_ma20"])
    frame["ema20"] = close.ewm(span=20, adjust=False).mean()
    frame["ema50"] = close.ewm(span=50, adjust=False).mean()
    frame["price_vs_ema20_pct"] = close.div(frame["ema20"]).sub(1)
    frame["price_vs_ema50"] = close.div(frame["ema50"]).sub(1)
    frame["rsi14"] = calculate_rsi_series(close, 14)
    frame["rsi_slope_5d"] = frame["rsi14"] - frame["rsi14"].shift(5)
    frame["volume_spike_flag"] = (frame["volume"] > (frame["volume_ma20"] * 2)).astype(float)

    frame.loc[frame.index < 19, "price_vs_ema20_pct"] = np.nan
    frame.loc[frame.index < 49, "price_vs_ema50"] = np.nan
    frame.loc[frame["volume_ma20"].isna(), "volume_spike_flag"] = np.nan

    return frame[
        [
            "date",
            "return_1d",
            "return_3d",
            "return_5d",
            "return_20d",
            "atr_ratio",
            "atr14_pct",
            "volume_ratio_5d",
            "volume_ratio_20d",
            "price_vs_ema20_pct",
            "price_vs_ema50",
            "rsi_slope_5d",
            "volume_spike_flag",
        ]
    ].copy()


def build_ihsg_regime(ihsg_csv: Path) -> pd.DataFrame:
    frame = adjusted_stock_frame(ihsg_csv)
    close = frame["close_adj"]
    ema50 = close.ewm(span=50, adjust=False).mean()
    ema200 = close.ewm(span=200, adjust=False).mean()
    bullish = (ema50 > ema200).astype(float)
    bullish.iloc[:199] = np.nan

    durations: list[float] = []
    current_duration = 0
    previous_state: float | None = None
    for value in bullish.tolist():
        if pd.isna(value):
            current_duration = 0
            durations.append(np.nan)
            continue
        state = float(value)
        if previous_state is None or state != previous_state:
            current_duration = 1
        else:
            current_duration += 1
        durations.append(float(current_duration))
        previous_state = state

    return pd.DataFrame(
        {
            "reference_date": frame["date"],
            "market_regime_bullish": bullish.astype("float"),
            "regime_duration": durations,
        }
    )


def label_direction(series: pd.Series, threshold: float) -> pd.Series:
    return np.where(series >= threshold, "up", np.where(series <= (-threshold), "down", "flat"))


def main() -> None:
    args = parse_args()
    input_dataset = Path(args.input_dataset)
    output_dataset = Path(args.output_dataset)
    per_ticker_dir = Path(args.per_ticker_dir)
    stocks_dir = Path(args.stocks_dir)
    ihsg_csv = Path(args.ihsg_csv)

    dataset = pd.read_csv(input_dataset)
    dataset["reference_date"] = pd.to_datetime(dataset["reference_date"])

    technical_frames = []
    for ticker in sorted(dataset["ticker"].dropna().unique().tolist()):
        stock_path = stocks_dir / f"{ticker}.csv"
        if not stock_path.is_file():
            raise SystemExit(f"Missing stock CSV for {ticker}: {stock_path}")

        technical = build_stock_features(ticker, stocks_dir)
        technical["ticker"] = ticker
        technical_frames.append(technical)

    technical_dataset = pd.concat(technical_frames, ignore_index=True)
    technical_dataset = technical_dataset.rename(columns={"date": "reference_date"})
    technical_dataset["reference_date"] = pd.to_datetime(technical_dataset["reference_date"])

    rebuilt = dataset.drop(
        columns=[
            "return_1d",
            "return_3d",
            "return_5d",
            "return_20d",
            "atr_ratio",
            "atr14_pct",
            "volume_ratio_5d",
            "volume_ratio_20d",
            "price_vs_ema20_pct",
            "price_vs_ema50",
            "rsi_slope_5d",
            "return_5d_cross_section_rank",
            "volume_spike_flag",
            "market_regime_bullish",
            "regime_duration",
            "label_v2",
        ],
        errors="ignore",
    ).merge(
        technical_dataset,
        on=["ticker", "reference_date"],
        how="left",
    )

    rebuilt = rebuilt.merge(build_ihsg_regime(ihsg_csv), on="reference_date", how="left")

    group_sizes = rebuilt.groupby("reference_date")["ticker"].transform("size")
    ranks = rebuilt.groupby("reference_date")["return_5d"].rank(method="average")
    rebuilt["return_5d_cross_section_rank"] = np.where(
        group_sizes > 1,
        (ranks - 1) / (group_sizes - 1),
        0.5,
    )
    rebuilt["label_v2"] = label_direction(rebuilt["future_return_5d"].astype(float), args.threshold_v2)
    rebuilt["prediction_feature_version"] = "technical_prediction_research_v2"
    rebuilt["reference_date"] = rebuilt["reference_date"].dt.strftime("%Y-%m-%d")

    numeric_columns = [
        "future_return_5d",
        "return_1d",
        "return_3d",
        "return_5d",
        "return_20d",
        "atr_ratio",
        "atr14_pct",
        "volume_ratio_5d",
        "volume_ratio_20d",
        "price_vs_ema20_pct",
        "price_vs_ema50",
        "rsi_slope_5d",
        "return_5d_cross_section_rank",
        "market_regime_bullish",
        "regime_duration",
    ]
    for column in numeric_columns:
        rebuilt[column] = rebuilt[column].round(6)

    rebuilt["volume_spike_flag"] = rebuilt["volume_spike_flag"].round().astype("Int64")
    rebuilt["market_regime_bullish"] = rebuilt["market_regime_bullish"].round().astype("Int64")
    rebuilt["regime_duration"] = rebuilt["regime_duration"].round().astype("Int64")

    required_columns = [
        "return_1d",
        "return_3d",
        "return_5d",
        "return_20d",
        "atr_ratio",
        "atr14_pct",
        "volume_ratio_5d",
        "volume_ratio_20d",
        "price_vs_ema20_pct",
        "price_vs_ema50",
        "rsi_slope_5d",
        "return_5d_cross_section_rank",
        "volume_spike_flag",
        "market_regime_bullish",
        "regime_duration",
        "label_v2",
    ]
    missing_rows = rebuilt[required_columns].isna().any(axis=1).sum()
    if missing_rows:
        raise SystemExit(f"Rebuilt dataset still contains {missing_rows} rows with missing required v2 fields.")

    rebuilt = rebuilt.sort_values(["reference_date", "ticker"]).reset_index(drop=True)

    output_dataset.parent.mkdir(parents=True, exist_ok=True)
    rebuilt.to_csv(output_dataset, index=False)

    per_ticker_dir.mkdir(parents=True, exist_ok=True)
    for ticker, ticker_frame in rebuilt.groupby("ticker", sort=True):
        ticker_frame.to_csv(per_ticker_dir / f"{ticker}.csv", index=False)

    print(
        {
            "rows": int(len(rebuilt)),
            "tickers": int(rebuilt["ticker"].nunique()),
            "label_v2_distribution": rebuilt["label_v2"].value_counts(normalize=True).round(6).to_dict(),
            "output_dataset": str(output_dataset),
        }
    )


if __name__ == "__main__":
    main()
