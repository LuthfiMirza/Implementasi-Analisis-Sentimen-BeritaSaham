from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from quant.trading_research.artifact_utils import histogram, pct_summary, read_json, sha256_file, write_json
from quant.trading_research.walk_forward_event_dataset import REQUIRED_EVENT_FIELDS, SCHEMA_VERSION, validate_event_dataset

QUALITY_SCHEMA_VERSION = "event_dataset_quality_v1"
GENERATOR_VERSION = "event_dataset_quality_1"
NUMERIC_FIELDS = [
    "entry_price", "highest_price", "lowest_price", "exit_price", "return_pct", "mfe_pct", "mae_pct",
    "drawdown_pct", "recovery_pct", "atr", "rsi", "macd", "adx", "vwap", "volume_ratio",
    "news_sentiment", "prediction_probability",
]
PRICE_FIELDS = ["entry_price", "highest_price", "lowest_price", "exit_price"]


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bucket_probability(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return "missing"
    if number < 0.6:
        return "lt_0_60"
    if number < 0.7:
        return "0_60_to_0_70"
    if number < 0.8:
        return "0_70_to_0_80"
    return "gte_0_80"


def audit_event_dataset(path: Path, output_dir: Path | None = None, overwrite: bool = True) -> dict[str, Any]:
    artifact = read_json(path)
    events = artifact.get("events", [])
    warnings: list[str] = []
    critical: list[str] = []

    try:
        validate_event_dataset(artifact)
        schema_valid = True
    except ValueError as exc:
        schema_valid = False
        critical.append(str(exc))

    identities = [(artifact.get("ticker"), event.get("entry_date"), event.get("prediction_variant")) for event in events]
    counts = Counter(identities)
    duplicate_identities = [identity for identity, count in counts.items() if count > 1]
    duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
    if duplicate_count:
        critical.append(f"duplicate events found: {duplicate_count}")

    missing_by_field = {field: 0 for field in REQUIRED_EVENT_FIELDS}
    invalid_numeric_by_field = {field: 0 for field in NUMERIC_FIELDS}
    invalid_price_count = 0
    price_consistency_violations = 0
    insufficient_future_ohlcv_count = 0
    valid_buy_signal_count = 0
    overlapping_count = 0
    previous_end: datetime | None = None

    sorted_events = sorted(events, key=lambda item: str(item.get("entry_date", "")))
    for event in sorted_events:
        for field in REQUIRED_EVENT_FIELDS:
            if field not in event or event.get(field) is None:
                missing_by_field[field] += 1
        for field in NUMERIC_FIELDS:
            value = _as_float(event.get(field))
            if event.get(field) is not None and value is None:
                invalid_numeric_by_field[field] += 1
        prices = {field: _as_float(event.get(field)) for field in PRICE_FIELDS}
        if any(value is None or value <= 0 for value in prices.values()):
            invalid_price_count += 1
        if all(value is not None for value in prices.values()):
            if prices["highest_price"] < prices["entry_price"] or prices["highest_price"] < prices["exit_price"] or prices["lowest_price"] > prices["entry_price"] or prices["lowest_price"] > prices["exit_price"]:
                price_consistency_violations += 1
        entry_date = datetime.fromisoformat(str(event.get("entry_date")))
        holding_days = int(event.get("holding_days") or 0)
        if holding_days < int(artifact.get("config", {}).get("holding_days", holding_days)):
            insufficient_future_ohlcv_count += 1
        event_end = entry_date.toordinal() + holding_days
        if previous_end is not None and entry_date.toordinal() <= previous_end.toordinal():
            overlapping_count += 1
        previous_end = datetime.fromordinal(max(previous_end.toordinal() if previous_end else 0, event_end))
        if event.get("entry_price") is not None and event.get("highest_price") is not None:
            valid_buy_signal_count += 1

    if price_consistency_violations:
        critical.append(f"price consistency violations: {price_consistency_violations}")
    if invalid_price_count:
        critical.append(f"invalid price events: {invalid_price_count}")
    if insufficient_future_ohlcv_count:
        warnings.append(f"events with shorter than configured future OHLCV: {insufficient_future_ohlcv_count}")
    if overlapping_count:
        warnings.append(f"overlapping holding periods: {overlapping_count}")

    report = {
        "schema_version": QUALITY_SCHEMA_VERSION,
        "artifact_type": "event_dataset_quality",
        "ticker": artifact.get("ticker"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_version": GENERATOR_VERSION,
        "source": {
            "event_artifact_path": str(path),
            "event_schema_version": artifact.get("schema_version"),
            "event_generated_at": artifact.get("generated_at"),
            "event_count": len(events),
            "source_checksum": sha256_file(path),
            "data_start": sorted_events[0].get("entry_date") if sorted_events else None,
            "data_end": sorted_events[-1].get("entry_date") if sorted_events else None,
        },
        "checks": {
            "schema_valid": schema_valid,
            "event_count": len(events),
            "unique_identity_count": len(counts),
            "duplicate_event_count": duplicate_count,
            "duplicate_event_keys": [list(identity) for identity in duplicate_identities[:50]],
            "valid_buy_signal_event_count": valid_buy_signal_count,
            "overlapping_holding_period_count": overlapping_count,
            "missing_value_by_field": missing_by_field,
            "invalid_numeric_by_field": invalid_numeric_by_field,
            "invalid_price_count": invalid_price_count,
            "price_consistency_violation_count": price_consistency_violations,
            "insufficient_future_ohlcv_count": insufficient_future_ohlcv_count,
            "lookahead_leakage_assessment": {
                "status": "review_required",
                "notes": "Entry features are stored on event entry date; outcome metrics use future OHLCV by design. Source prediction history is absent for Sprint 2 artifacts, so BUY signal provenance cannot be independently replayed from prediction logs.",
            },
        },
        "distributions": {
            "holding_days": histogram([event.get("holding_days") for event in events]),
            "trade_outcome": histogram([event.get("trade_outcome") for event in events]),
            "prediction_probability_bucket": histogram([_bucket_probability(event.get("prediction_probability")) for event in events]),
            "market_regime": histogram([event.get("market_regime") for event in events]),
            "return_pct": pct_summary([_as_float(event.get("return_pct")) for event in events]),
            "mfe_pct": pct_summary([_as_float(event.get("mfe_pct")) for event in events]),
            "mae_pct": pct_summary([_as_float(event.get("mae_pct")) for event in events]),
            "drawdown_pct": pct_summary([_as_float(event.get("drawdown_pct")) for event in events]),
            "prediction_probability": pct_summary([_as_float(event.get("prediction_probability")) for event in events]),
        },
        "quality": {
            "status": "valid" if schema_valid and not critical else "invalid",
            "sample_size": len(events),
            "warnings": warnings,
            "critical_warnings": critical,
        },
    }
    if output_dir is not None:
        write_json(report, output_dir / f"{artifact.get('ticker')}_event_quality_v1.json", overwrite=overwrite)
    return report


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit walk-forward event dataset artifacts.")
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("storage/app/trading_research/quality"))
    parser.add_argument("--overwrite", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    report = audit_event_dataset(args.events, args.output_dir, overwrite=args.overwrite)
    print(args.output_dir / f"{report['ticker']}_event_quality_v1.json")
    return 0 if report["quality"]["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
