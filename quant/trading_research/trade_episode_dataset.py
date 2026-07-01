from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from quant.trading_research.artifact_utils import sha256_file, write_json, read_json
from quant.trading_research.chronological_trade_simulator import prepare_ohlcv, simulate_path
from quant.trading_research.walk_forward_event_dataset import validate_event_dataset

SCHEMA_VERSION = "trade_episode_dataset_v1"
GENERATOR_VERSION = "trade_episode_dataset_1"


def _median(values: list[float]) -> float | None:
    return None if not values else float(statistics.median(values))


def _event_signal(event: dict[str, Any]) -> bool:
    return event.get("entry_price") is not None


def _episode_id(ticker: str, policy: str, entry_date: str, source_index: int) -> str:
    return f"{ticker}_{policy}_{entry_date}_{source_index:06d}"


def load_events(path: Path) -> dict[str, Any]:
    artifact = read_json(path)
    validate_event_dataset(artifact)
    return artifact


def select_episode_indices(events: list[dict[str, Any]], policy: str, horizon_days: int, spacing_days: int) -> list[int]:
    selected: list[int] = []
    previous_buy = False
    active_until = -1
    last_selected = -10**9
    for index, event in enumerate(events):
        is_buy = _event_signal(event)
        if policy == "signal_transition":
            if is_buy and not previous_buy:
                selected.append(index)
            previous_buy = is_buy
        elif policy == "one_position_fixed_horizon":
            if is_buy and index > active_until:
                selected.append(index)
                active_until = index + horizon_days - 1
        elif policy == "fixed_spacing":
            if is_buy and index - last_selected >= spacing_days:
                selected.append(index)
                last_selected = index
        else:
            raise ValueError("invalid episode policy")
    return selected


def build_episode(
    ticker: str,
    event: dict[str, Any],
    source_index: int,
    policy: str,
    ohlcv: pd.DataFrame,
    ohlcv_path: Path,
    horizon_days: int,
    entry_timing: str,
) -> tuple[dict[str, Any] | None, str | None]:
    signal_date = pd.Timestamp(event["entry_date"]).normalize()
    matches = ohlcv.index[ohlcv["date"].eq(signal_date)]
    if len(matches) == 0:
        return None, "missing_signal_ohlcv"
    signal_index = int(matches[0])
    entry_index = signal_index if entry_timing == "signal_close" else signal_index + 1
    if entry_index >= len(ohlcv):
        return None, "insufficient_future_ohlcv"
    entry_row = ohlcv.iloc[entry_index]
    entry_price = float(entry_row["close"] if entry_timing == "signal_close" else entry_row["open"])
    end_index = entry_index + horizon_days - 1
    complete = end_index < len(ohlcv)
    actual_end = min(end_index, len(ohlcv) - 1)
    if not complete:
        return None, "insufficient_future_ohlcv"
    outcome = simulate_path(ohlcv, entry_index, entry_price, horizon_days)
    episode = {
        "episode_id": _episode_id(ticker, policy, entry_row["date"].date().isoformat(), source_index),
        "ticker": ticker,
        "signal_date": signal_date.date().isoformat(),
        "entry_date": entry_row["date"].date().isoformat(),
        "entry_price": round(entry_price, 6),
        "entry_price_source": "close" if entry_timing == "signal_close" else "next_open",
        "horizon_end_date": ohlcv.iloc[actual_end]["date"].date().isoformat(),
        "holding_days": horizon_days,
        "complete_horizon": complete,
        "sampling_policy": policy,
        "source_event_id": f"{ticker}_event_{source_index:06d}",
        "source_ohlcv_reference": {
            "path": str(ohlcv_path),
            "checksum": sha256_file(ohlcv_path),
            "start_row_index": entry_index,
            "end_row_index": actual_end,
            "available_trading_day_count": int(actual_end - entry_index + 1),
        },
        "prediction_probability": event.get("prediction_probability"),
        "prediction_variant": event.get("prediction_variant"),
        "market_regime": event.get("market_regime"),
        "news_sentiment": event.get("news_sentiment"),
        "entry_feature_snapshot": {
            "source": "walk_forward_event_dataset",
            "entry_date": event.get("entry_date"),
            "atr": event.get("atr"),
            "atr_format": "absolute_price" if event.get("atr") is not None else None,
            "rsi": event.get("rsi"),
            "macd": event.get("macd"),
            "adx": event.get("adx"),
            "vwap": event.get("vwap"),
            "volume_ratio": event.get("volume_ratio"),
        },
        "outcome_summary": outcome,
    }
    return episode, None


def connected_component_count(events: list[dict[str, Any]]) -> int:
    count = 0; current_end = None
    for event in events:
        start = pd.Timestamp(event["entry_date"]).toordinal()
        end = start + int(event.get("holding_days") or 0)
        if current_end is None or start > current_end:
            count += 1; current_end = end
        else:
            current_end = max(current_end, end)
    return count


def build_trade_episode_dataset(
    events_path: Path,
    ohlcv_path: Path,
    output_dir: Path | None = None,
    horizon_days: int = 20,
    entry_timing: str = "next_open",
    primary_policy: str = "one_position_fixed_horizon",
    fixed_spacing_days: int = 20,
    overwrite: bool = True,
) -> dict[str, Any]:
    event_artifact = load_events(events_path)
    ticker = event_artifact["ticker"]
    raw_events = sorted(event_artifact["events"], key=lambda e: e["entry_date"])
    ohlcv = prepare_ohlcv(pd.read_csv(ohlcv_path))
    policies = ["signal_transition", "one_position_fixed_horizon", "fixed_spacing"]
    policy_counts = {p: len(select_episode_indices(raw_events, p, horizon_days, fixed_spacing_days)) for p in policies}
    selected_indices = select_episode_indices(raw_events, primary_policy, horizon_days, fixed_spacing_days)
    episodes: list[dict[str, Any]] = []
    exclusions = {"insufficient_future_ohlcv": 0, "missing_signal_ohlcv": 0, "other": 0}
    for idx in selected_indices:
        episode, reason = build_episode(ticker, raw_events[idx], idx, primary_policy, ohlcv, ohlcv_path, horizon_days, entry_timing)
        if episode is None:
            exclusions[reason or "other"] = exclusions.get(reason or "other", 0) + 1
        else:
            episodes.append(episode)
    entry_ordinals = [pd.Timestamp(ep["entry_date"]).toordinal() for ep in episodes]
    spacings = [b - a for a, b in zip(entry_ordinals, entry_ordinals[1:])]
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "trade_episode_dataset",
        "ticker": ticker,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_version": GENERATOR_VERSION,
        "config": {"horizon_days": horizon_days, "entry_timing": entry_timing, "primary_policy": primary_policy, "fixed_spacing_days": fixed_spacing_days},
        "source": {"event_artifact_path": str(events_path), "event_checksum": sha256_file(events_path), "ohlcv_path": str(ohlcv_path), "ohlcv_checksum": sha256_file(ohlcv_path)},
        "observation_summary": {"raw_signal_observation_count": len(raw_events), "overlapping_observation_count": max(0, len(raw_events) - connected_component_count(raw_events)), "connected_component_cluster_count": connected_component_count(raw_events), "note": "cluster count is an overlap diagnostic, not effective sample size"},
        "episode_summary": {"signal_transition_episode_count": policy_counts["signal_transition"], "one_position_episode_count": policy_counts["one_position_fixed_horizon"], "fixed_spacing_episode_count": policy_counts["fixed_spacing"], "complete_horizon_episode_count": len(episodes), "median_episode_spacing": _median([float(v) for v in spacings]), "median_holding_horizon": _median([float(ep["holding_days"]) for ep in episodes]), "independence_proxy": len(episodes)},
        "exclusions": exclusions,
        "episodes": episodes,
        "quality": {"status": "valid", "primary_policy_has_concurrent_position": False, "warnings": []},
        "notes": ["Signal observations remain descriptive evidence only.", "Connected-component cluster count is not treated as effective sample size."],
    }
    validate_trade_episode_dataset(artifact)
    if output_dir is not None:
        write_json(artifact, output_dir / f"{ticker}_trade_episodes_v1.json", overwrite=overwrite)
    return artifact


def validate_trade_episode_dataset(artifact: dict[str, Any]) -> None:
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid episode schema")
    if artifact.get("artifact_type") != "trade_episode_dataset":
        raise ValueError("invalid artifact type")
    seen = set()
    for episode in artifact.get("episodes", []):
        if episode["episode_id"] in seen:
            raise ValueError("duplicate episode")
        seen.add(episode["episode_id"])
        if not episode.get("complete_horizon"):
            raise ValueError("incomplete episode included")
        if episode["entry_date"] < episode["signal_date"]:
            raise ValueError("entry before signal")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build trade episode dataset from BUY signal observations.")
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--ohlcv", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("storage/app/trading_research/episodes"))
    parser.add_argument("--horizon-days", type=int, default=20)
    parser.add_argument("--entry-timing", choices=["next_open", "signal_close"], default="next_open")
    parser.add_argument("--primary-policy", choices=["one_position_fixed_horizon", "signal_transition", "fixed_spacing"], default="one_position_fixed_horizon")
    parser.add_argument("--fixed-spacing-days", type=int, default=20)
    parser.add_argument("--overwrite", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    artifact = build_trade_episode_dataset(args.events, args.ohlcv, args.output_dir, args.horizon_days, args.entry_timing, args.primary_policy, args.fixed_spacing_days, args.overwrite)
    print(args.output_dir / f"{artifact['ticker']}_trade_episodes_v1.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
