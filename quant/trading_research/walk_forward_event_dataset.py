from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

SCHEMA_VERSION = "walk_forward_event_dataset_v1"
ARTIFACT_TYPE = "walk_forward_event_dataset"
REQUIRED_EVENT_FIELDS = [
    "entry_date",
    "entry_price",
    "holding_days",
    "highest_price",
    "lowest_price",
    "exit_price",
    "return_pct",
    "mfe_pct",
    "mae_pct",
    "drawdown_pct",
    "recovery_pct",
    "atr",
    "rsi",
    "macd",
    "adx",
    "vwap",
    "volume_ratio",
    "market_regime",
    "news_sentiment",
    "prediction_probability",
    "prediction_variant",
    "trade_outcome",
]

@dataclass(frozen=True)
class EventDatasetConfig:
    ticker: str
    holding_days: int = 20
    schema_version: str = SCHEMA_VERSION
    buy_threshold: float = 0.5
    outcome_win_threshold_pct: float = 0.0

def _round(value: Any, digits: int = 6) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)

def _read_csv(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    frame = pd.read_csv(path)
    if "date" not in frame.columns and "reference_date" in frame.columns:
        frame = frame.rename(columns={"reference_date": "date"})
    if "date" not in frame.columns:
        raise ValueError(f"{path} must contain date column")
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame.sort_values("date").reset_index(drop=True)

def load_ohlcv(path: Path) -> pd.DataFrame:
    frame = _read_csv(path)
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing OHLCV columns: {', '.join(missing)}")
    if frame["date"].duplicated().any():
        raise ValueError("duplicate OHLCV dates")
    for column in ["open", "high", "low", "close", "volume"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame

def _prepare_price_basis(ohlcv: pd.DataFrame) -> pd.DataFrame:
    frame = ohlcv.copy()
    factor = 1.0
    if "adj_close" in frame.columns:
        factor = frame["adj_close"].where(frame["adj_close"].notna(), frame["close"]).astype(float) / frame["close"].replace(0, math.nan).astype(float)
    frame["entry_price_basis"] = frame.get("adj_close", frame["close"]).fillna(frame["close"]).astype(float)
    frame["high_basis"] = frame["high"].astype(float) * factor
    frame["low_basis"] = frame["low"].astype(float) * factor
    return frame

def add_technical_features(ohlcv: pd.DataFrame, feature_frame: pd.DataFrame | None = None) -> pd.DataFrame:
    frame = _prepare_price_basis(ohlcv)
    close = frame["entry_price_basis"]
    prev_close = close.shift(1)
    true_range = pd.concat([
        frame["high_basis"] - frame["low_basis"],
        (frame["high_basis"] - prev_close).abs(),
        (frame["low_basis"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    frame["atr"] = true_range.rolling(14, min_periods=1).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
    rs = gain / loss.replace(0, math.nan)
    frame["rsi"] = (100 - (100 / (1 + rs))).fillna(50.0)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    frame["macd"] = ema12 - ema26

    high_diff = frame["high_basis"].diff()
    low_diff = -frame["low_basis"].diff()
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
    atr_sum = true_range.rolling(14, min_periods=1).sum().replace(0, math.nan)
    plus_di = 100 * plus_dm.rolling(14, min_periods=1).sum() / atr_sum
    minus_di = 100 * minus_dm.rolling(14, min_periods=1).sum() / atr_sum
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, math.nan)) * 100
    frame["adx"] = dx.rolling(14, min_periods=1).mean().fillna(0.0)

    typical = (frame["high_basis"] + frame["low_basis"] + close) / 3
    volume = frame["volume"].fillna(0).astype(float)
    frame["vwap"] = (typical * volume).rolling(20, min_periods=1).sum() / volume.rolling(20, min_periods=1).sum().replace(0, math.nan)
    frame["volume_ratio"] = volume / volume.rolling(20, min_periods=1).mean().replace(0, math.nan)
    frame["market_regime"] = frame.get("market_regime", "unknown")
    frame["news_sentiment"] = frame.get("sentiment_weighted_1d", frame.get("sentiment_average_1d", 0.0))

    if feature_frame is not None and not feature_frame.empty:
        features = feature_frame.copy()
        if "reference_date" in features.columns and "date" not in features.columns:
            features = features.rename(columns={"reference_date": "date"})
        features = features.rename(columns={
            "atr14_pct": "atr",
            "rsi14": "rsi",
            "volume_ratio_20d": "volume_ratio",
            "weighted_sentiment_5d": "news_sentiment",
            "market_regime_bullish": "market_regime",
        })
        features["date"] = pd.to_datetime(features["date"]).dt.normalize()
        overlay = [c for c in ["atr", "rsi", "macd", "adx", "vwap", "volume_ratio", "market_regime", "news_sentiment"] if c in features.columns]
        if overlay:
            frame = frame.merge(features[["date", *overlay]], on="date", how="left", suffixes=("", "_feature"))
            for column in overlay:
                feature_column = f"{column}_feature"
                frame[column] = frame[feature_column].combine_first(frame[column])
                frame = frame.drop(columns=[feature_column])
    return frame

def load_prediction_history(path: Path | None, ticker: str) -> pd.DataFrame:
    frame = _read_csv(path)
    if frame.empty:
        return frame
    if "ticker" in frame.columns:
        frame = frame.loc[frame["ticker"].astype(str).str.upper().eq(ticker.upper())].copy()
    return frame

def _is_buy_signal(row: pd.Series, buy_threshold: float) -> bool:
    for column in ["signal", "action", "prediction", "prediction_label", "label"]:
        if column in row and str(row[column]).upper() == "BUY":
            return True
    if "prediction_probability" in row and not pd.isna(row["prediction_probability"]):
        return float(row["prediction_probability"]) >= buy_threshold
    if "probability" in row and not pd.isna(row["probability"]):
        return float(row["probability"]) >= buy_threshold
    return False

def _prediction_value(row: pd.Series, *columns: str) -> Any:
    for column in columns:
        if column in row and not pd.isna(row[column]):
            return row[column]
    return None

def build_event_dataset(
    ohlcv: pd.DataFrame,
    prediction_history: pd.DataFrame | None,
    config: EventDatasetConfig,
    feature_frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    prices = add_technical_features(ohlcv, feature_frame).reset_index(drop=True)
    predictions = prediction_history if prediction_history is not None else pd.DataFrame()
    if predictions.empty:
        predictions = prices[["date"]].copy()
        predictions["prediction_probability"] = None
        predictions["prediction_variant"] = None
        predictions["signal"] = "BUY"
    merged = predictions.merge(prices, on="date", how="left", suffixes=("_prediction", ""))
    events: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        if not _is_buy_signal(row, config.buy_threshold):
            continue
        if pd.isna(row.get("entry_price_basis")):
            event = {field: None for field in REQUIRED_EVENT_FIELDS}
            event["entry_date"] = row["date"].date().isoformat()
            events.append(event)
            continue
        entry_index = prices.index[prices["date"].eq(row["date"])]
        if len(entry_index) == 0:
            continue
        start = int(entry_index[0])
        end = min(start + config.holding_days, len(prices) - 1)
        window = prices.iloc[start : end + 1]
        entry_price = float(prices.loc[start, "entry_price_basis"])
        exit_price = float(prices.loc[end, "entry_price_basis"])
        highest_price = max(float(window["high_basis"].max()), entry_price, exit_price)
        lowest_price = min(float(window["low_basis"].min()), entry_price, exit_price)
        return_pct = ((exit_price / entry_price) - 1) * 100
        recovery_pct = ((exit_price / lowest_price) - 1) * 100 if lowest_price > 0 else None
        event = {
            "entry_date": row["date"].date().isoformat(),
            "entry_price": _round(entry_price),
            "holding_days": int(end - start),
            "highest_price": _round(highest_price),
            "lowest_price": _round(lowest_price),
            "exit_price": _round(exit_price),
            "return_pct": _round(return_pct),
            "mfe_pct": _round(((highest_price / entry_price) - 1) * 100),
            "mae_pct": _round(((lowest_price / entry_price) - 1) * 100),
            "drawdown_pct": _round(((lowest_price / highest_price) - 1) * 100 if highest_price > 0 else None),
            "recovery_pct": _round(recovery_pct),
            "atr": _round(row.get("atr")),
            "rsi": _round(row.get("rsi")),
            "macd": _round(row.get("macd")),
            "adx": _round(row.get("adx")),
            "vwap": _round(row.get("vwap")),
            "volume_ratio": _round(row.get("volume_ratio")),
            "market_regime": str(row.get("market_regime", "unknown")),
            "news_sentiment": _round(row.get("news_sentiment")),
            "prediction_probability": _round(_prediction_value(row, "prediction_probability", "probability")),
            "prediction_variant": _prediction_value(row, "prediction_variant", "variant", "model_variant"),
            "trade_outcome": "win" if return_pct > config.outcome_win_threshold_pct else "loss",
        }
        events.append(event)
    artifact = {
        "schema_version": config.schema_version,
        "artifact_type": ARTIFACT_TYPE,
        "ticker": config.ticker.upper(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {"holding_days": config.holding_days, "buy_threshold": config.buy_threshold},
        "events": events,
        "quality": {"event_count": len(events), "status": "research_dataset"},
    }
    validate_event_dataset(artifact)
    return artifact

def validate_event_dataset(artifact: dict[str, Any]) -> None:
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid schema version")
    if artifact.get("artifact_type") != ARTIFACT_TYPE:
        raise ValueError("invalid artifact type")
    ticker = artifact.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("ticker is required")
    seen: set[str] = set()
    for event in artifact.get("events", []):
        missing = [field for field in REQUIRED_EVENT_FIELDS if field not in event]
        if missing:
            raise ValueError(f"missing required event fields: {', '.join(missing)}")
        entry_date = event["entry_date"]
        if entry_date in seen:
            raise ValueError(f"duplicate event: {entry_date}")
        seen.add(entry_date)
        price_fields = ["entry_price", "highest_price", "lowest_price", "exit_price"]
        if any(event[field] is None for field in price_fields):
            raise ValueError(f"missing OHLCV for event: {entry_date}")
        if any(float(event[field]) <= 0 for field in price_fields):
            raise ValueError(f"invalid price for event: {entry_date}")
        if float(event["highest_price"]) < float(event["lowest_price"]):
            raise ValueError(f"invalid price range for event: {entry_date}")

def write_event_dataset(artifact: dict[str, Any], output_dir: Path) -> Path:
    validate_event_dataset(artifact)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{artifact['ticker']}_events_v1.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    return path

def build_and_write_event_dataset(
    ticker: str,
    ohlcv_path: Path,
    output_dir: Path,
    prediction_history_path: Path | None = None,
    feature_path: Path | None = None,
    holding_days: int = 20,
    buy_threshold: float = 0.5,
) -> Path:
    config = EventDatasetConfig(ticker=ticker, holding_days=holding_days, buy_threshold=buy_threshold)
    artifact = build_event_dataset(
        ohlcv=load_ohlcv(ohlcv_path),
        prediction_history=load_prediction_history(prediction_history_path, ticker),
        feature_frame=_read_csv(feature_path) if feature_path else None,
        config=config,
    )
    return write_event_dataset(artifact, output_dir)

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build walk-forward BUY event research dataset artifacts.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--ohlcv", required=True, type=Path)
    parser.add_argument("--prediction-history", type=Path)
    parser.add_argument("--features", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("storage/app/trading_research/events"))
    parser.add_argument("--holding-days", type=int, default=20)
    parser.add_argument("--buy-threshold", type=float, default=0.5)
    return parser.parse_args(argv)

def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    path = build_and_write_event_dataset(
        ticker=args.ticker,
        ohlcv_path=args.ohlcv,
        prediction_history_path=args.prediction_history,
        feature_path=args.features,
        output_dir=args.output_dir,
        holding_days=args.holding_days,
        buy_threshold=args.buy_threshold,
    )
    print(path)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
