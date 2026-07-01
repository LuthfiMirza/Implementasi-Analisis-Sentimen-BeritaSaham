from __future__ import annotations

import argparse
import random
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from quant.trading_research.artifact_utils import pct_summary, read_json, sha256_file, write_json
from quant.trading_research.walk_forward_event_dataset import REQUIRED_EVENT_FIELDS, SCHEMA_VERSION as EVENT_SCHEMA_VERSION, validate_event_dataset

SCHEMA_VERSION = "tp_optimizer_v1"
ARTIFACT_TYPE = "tp_optimizer"
GENERATOR_VERSION = "tp_optimizer_1_1"
DEFAULT_CANDIDATES = [5.0, 7.5, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0]
DEFAULT_SELECTION_WEIGHTS = {"expectancy": 0.35, "hit_rate": 0.15, "days_to_hit": 0.10, "drawdown": 0.15, "downside_tail": 0.15, "stability": 0.10}

@dataclass(frozen=True)
class TPOptimizerConfig:
    candidates: list[float] = field(default_factory=lambda: list(DEFAULT_CANDIDATES))
    minimum_sample_size: int = 30
    fold_count: int = 4
    minimum_fold_count: int = 2
    selection_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SELECTION_WEIGHTS))
    min_segment_sample_size: int = 30
    consistency_tolerance_pct: float = 5.0
    overlap_policy: str = "purge_overlapping"
    minimum_validation_expectancy_pct: float = 0.0
    minimum_profitable_fold_ratio: float = 0.5
    minimum_effective_sample_size: int = 30
    minimum_validation_sample_size: int = 10
    maximum_downside_tail_pct: float = -25.0
    maximum_expectancy_ci_width_pct: float = 20.0
    minimum_tradable_movement_rate: float = 0.10
    random_seed: int = 42
    bootstrap_iterations: int = 200


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)

def _mean(values: list[float]) -> float | None:
    return None if not values else sum(values) / len(values)

def _median(values: list[float]) -> float | None:
    return None if not values else float(statistics.median(values))

def _stdev(values: list[float]) -> float:
    return 0.0 if len(values) < 2 else float(statistics.pstdev(values))

def _downside_tail(values: list[float]) -> float | None:
    return None if not values else pct_summary(values)["p25"]

def normalize_candidates(candidates: Iterable[float]) -> list[float]:
    normalized = [round(float(value), 6) for value in candidates]
    if len(set(normalized)) != len(normalized):
        raise ValueError("candidate TP values must be unique")
    if any(value <= 0 or value > 100 for value in normalized):
        raise ValueError("candidate TP values must be within 0-100")
    return sorted(normalized)

def load_event_artifact(path: Path, ticker: str | None = None) -> dict[str, Any]:
    artifact = read_json(path)
    if artifact.get("schema_version") == "trade_episode_dataset_v1":
        if ticker and artifact.get("ticker") != ticker.upper():
            raise ValueError("episode artifact ticker mismatch")
        events = []
        for episode in artifact.get("episodes", []):
            outcome = episode.get("outcome_summary", {})
            events.append({
                "entry_date": episode["entry_date"],
                "entry_price": episode["entry_price"],
                "holding_days": episode["holding_days"],
                "highest_price": episode["entry_price"] * (1 + (outcome.get("mfe_pct") or 0) / 100),
                "lowest_price": episode["entry_price"] * (1 + (outcome.get("mae_pct") or 0) / 100),
                "exit_price": episode["entry_price"] * (1 + (outcome.get("horizon_return_pct") or 0) / 100),
                "return_pct": outcome.get("horizon_return_pct"),
                "mfe_pct": outcome.get("mfe_pct"),
                "mae_pct": outcome.get("mae_pct"),
                "drawdown_pct": outcome.get("mae_pct"),
                "recovery_pct": 0.0,
                "atr": 0.0,
                "rsi": 0.0,
                "macd": 0.0,
                "adx": 0.0,
                "vwap": episode["entry_price"],
                "volume_ratio": 0.0,
                "prediction_probability": episode.get("prediction_probability"),
                "prediction_variant": episode.get("prediction_variant"),
                "market_regime": episode.get("market_regime"),
                "news_sentiment": episode.get("news_sentiment"),
                "trade_outcome": "win" if (outcome.get("horizon_return_pct") or 0) > 0 else "loss",
            })
        return {"schema_version": artifact["schema_version"], "artifact_type": "trade_episode_dataset", "ticker": artifact["ticker"], "generated_at": artifact.get("generated_at"), "config": {"holding_days": artifact.get("config", {}).get("horizon_days")}, "events": events, "quality": artifact.get("quality", {})}
    validate_event_dataset(artifact)
    if artifact.get("schema_version") != EVENT_SCHEMA_VERSION:
        raise ValueError("invalid event schema version")
    if artifact.get("artifact_type") != "walk_forward_event_dataset":
        raise ValueError("invalid event artifact type")
    if ticker and artifact.get("ticker") != ticker.upper():
        raise ValueError("event artifact ticker mismatch")
    if artifact.get("quality", {}).get("status") != "research_dataset":
        raise ValueError("event artifact quality status is not research_dataset")
    if not artifact.get("generated_at"):
        raise ValueError("event artifact generated_at is required")
    return artifact

def has_full_future_window(event: dict[str, Any], configured_holding_days: int | None) -> bool:
    return configured_holding_days is None or int(event.get("holding_days") or 0) >= int(configured_holding_days)

def split_eligible_events(events: list[dict[str, Any]], configured_holding_days: int | None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    eligible, exclusions = [], {"insufficient_future_ohlcv": 0, "invalid_price": 0, "missing_required_field": 0, "other": 0}
    for event in events:
        if any(field not in event or event.get(field) is None for field in REQUIRED_EVENT_FIELDS if field not in {"prediction_probability", "prediction_variant"}):
            exclusions["missing_required_field"] += 1; continue
        if any(float(event[field]) <= 0 for field in ["entry_price", "highest_price", "lowest_price", "exit_price"]):
            exclusions["invalid_price"] += 1; continue
        if not has_full_future_window(event, configured_holding_days):
            exclusions["insufficient_future_ohlcv"] += 1; continue
        eligible.append(event)
    return eligible, exclusions

def purge_overlapping_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    selected, current_end = [], None
    for event in sorted(events, key=lambda item: item["entry_date"]):
        start = datetime.fromisoformat(event["entry_date"]).toordinal()
        end = start + int(event["holding_days"])
        if current_end is None or start > current_end:
            selected.append(event); current_end = end
        else:
            current_end = max(current_end, end)
    return selected, len(events) - len(selected), len(selected)

def cluster_overlapping_events(events: list[dict[str, Any]]) -> int:
    clusters, current_end = 0, None
    for event in sorted(events, key=lambda item: item["entry_date"]):
        start = datetime.fromisoformat(event["entry_date"]).toordinal()
        end = start + int(event["holding_days"])
        if current_end is None or start > current_end:
            clusters += 1; current_end = end
        else:
            current_end = max(current_end, end)
    return clusters

def candidate_event_result(event: dict[str, Any], tp_pct: float) -> dict[str, Any]:
    hit = float(event["mfe_pct"]) >= float(tp_pct)
    holding_days = int(event["holding_days"])
    days_to_hit = max(1, min(holding_days, round((float(tp_pct) / max(float(event["mfe_pct"]), 0.000001)) * holding_days))) if hit else None
    mae_before_hit = max(float(event["mae_pct"]), float(event["drawdown_pct"])) if hit else None
    return {"tp_hit": hit, "realized_return_pct": float(tp_pct) if hit else float(event["return_pct"]), "days_to_hit": days_to_hit, "mae_before_hit_pct": mae_before_hit, "timeout": not hit}

def realized_returns(events: list[dict[str, Any]], tp_pct: float) -> list[float]:
    return [float(candidate_event_result(event, tp_pct)["realized_return_pct"]) for event in events]

def calculate_candidate_metrics(events: list[dict[str, Any]], tp_pct: float, warnings: list[str] | None = None) -> dict[str, Any]:
    results = [candidate_event_result(event, tp_pct) for event in events]
    hit_results = [r for r in results if r["tp_hit"]]
    realized = [float(r["realized_return_pct"]) for r in results]
    days = [float(r["days_to_hit"]) for r in hit_results if r["days_to_hit"] is not None]
    mae = [float(r["mae_before_hit_pct"]) for r in hit_results if r["mae_before_hit_pct"] is not None]
    drawdowns = [float(e["drawdown_pct"]) for e in events]
    mfes = [float(e["mfe_pct"]) for e in events]
    n, hits = len(events), len(hit_results)
    return {"tp_pct": _round(tp_pct), "event_count": n, "tp_hit_count": hits, "tp_hit_rate": _round(hits / n if n else 0), "timeout_count": n - hits, "timeout_rate": _round((n - hits) / n if n else 0), "average_realized_return_pct": _round(_mean(realized)), "median_realized_return_pct": _round(_median(realized)), "expectancy_pct": _round(_mean(realized)), "average_days_to_hit": _round(_mean(days)), "median_days_to_hit": _round(_median(days)), "average_mae_before_hit_pct": _round(_mean(mae)), "median_mae_before_hit_pct": _round(_median(mae)), "average_drawdown_pct": _round(_mean(drawdowns)), "median_drawdown_pct": _round(_median(drawdowns)), "average_mfe_pct": _round(_mean(mfes)), "positive_outcome_rate": _round(len([v for v in realized if v > 0]) / n if n else 0), "downside_tail_pct": _round(_downside_tail(realized)), "sample_size": n, "warnings": warnings or []}

def build_chronological_folds(events: list[dict[str, Any]], fold_count: int) -> list[dict[str, Any]]:
    ordered = sorted(events, key=lambda event: event["entry_date"])
    validation_size = max(1, len(ordered) // (fold_count + 1))
    folds = []
    for idx in range(fold_count):
        vs, ve = validation_size * (idx + 1), min(validation_size * (idx + 2), len(ordered))
        train, validation = ordered[:vs], ordered[vs:ve]
        if train and validation:
            folds.append({"fold_id": f"fold_{idx + 1}", "train_events": train, "validation_events": validation, "train_start": train[0]["entry_date"], "train_end": train[-1]["entry_date"], "validation_start": validation[0]["entry_date"], "validation_end": validation[-1]["entry_date"]})
    return folds

def _score_metrics(metrics: dict[str, Any], weights: dict[str, float], max_days: float) -> tuple[float, dict[str, float]]:
    components = {"expectancy": max(min((metrics["expectancy_pct"] or 0) / 30.0, 1.0), -1.0), "hit_rate": metrics["tp_hit_rate"] or 0.0, "days_to_hit": 0.0 if metrics["average_days_to_hit"] is None else max(0.0, 1.0 - metrics["average_days_to_hit"] / max_days), "drawdown": -max(min(abs(metrics["average_drawdown_pct"] or 0) / 50.0, 1.0), 0.0), "downside_tail": -max(min(abs(metrics["downside_tail_pct"] or 0) / 50.0, 1.0), 0.0), "stability": 0.0}
    return round(sum(float(weights.get(k, 0)) * v for k, v in components.items()), 6), {k: round(v, 6) for k, v in components.items()}

def select_candidate(metrics_by_candidate: list[dict[str, Any]], weights: dict[str, float], max_days: float) -> dict[str, Any]:
    scored = []
    for metrics in metrics_by_candidate:
        score, components = _score_metrics(metrics, weights, max_days)
        scored.append({**metrics, "selection_score": score, "selection_score_components": components})
    return sorted(scored, key=lambda item: (item["selection_score"], item["expectancy_pct"], -float(item["tp_pct"])), reverse=True)[0]

def evaluate_walk_forward(events: list[dict[str, Any]], candidates: list[float], config: TPOptimizerConfig) -> tuple[list[dict[str, Any]], list[float]]:
    folds, selected_tps = [], []
    for fold in build_chronological_folds(events, config.fold_count):
        train_metrics = [calculate_candidate_metrics(fold["train_events"], c) for c in candidates]
        selected = select_candidate(train_metrics, config.selection_weights, max(1, max(int(e["holding_days"]) for e in fold["train_events"])))
        validation = calculate_candidate_metrics(fold["validation_events"], selected["tp_pct"])
        selected_tps.append(float(selected["tp_pct"]))
        folds.append({"fold_id": fold["fold_id"], "train_start": fold["train_start"], "train_end": fold["train_end"], "validation_start": fold["validation_start"], "validation_end": fold["validation_end"], "train_event_count": len(fold["train_events"]), "validation_event_count": len(fold["validation_events"]), "selected_tp_pct": selected["tp_pct"], "selection_score": selected["selection_score"], "selection_score_components": selected["selection_score_components"], "validation_metrics": validation, "validation_expectancy_pct": validation["expectancy_pct"], "validation_hit_rate": validation["tp_hit_rate"], "validation_drawdown_pct": validation["average_drawdown_pct"], "warnings": []})
    return folds, selected_tps

def stability_metrics(folds: list[dict[str, Any]], selected_tps: list[float], tolerance_pct: float) -> dict[str, Any]:
    exps = [float(f["validation_expectancy_pct"] or 0) for f in folds]
    hits = [float(f["validation_hit_rate"] or 0) for f in folds]
    dds = [float(f["validation_drawdown_pct"] or 0) for f in folds]
    med_tp = statistics.median(selected_tps) if selected_tps else 0
    freq = Counter(selected_tps)
    enough = len(exps) >= 2
    return {"selection_stability": _round(len([tp for tp in selected_tps if abs(tp - med_tp) <= tolerance_pct]) / len(selected_tps)) if len(selected_tps) >= 2 else None, "selection_stability_numerator": len([tp for tp in selected_tps if abs(tp - med_tp) <= tolerance_pct]) if selected_tps else 0, "selection_stability_denominator": len(selected_tps), "expectancy_stability": _round(max(0.0, 1.0 - (_stdev(exps) / 10.0))) if enough else None, "hit_rate_stability": _round(max(0.0, 1.0 - _stdev(hits))) if enough else None, "drawdown_stability": _round(max(0.0, 1.0 - (_stdev(dds) / 25.0))) if enough else None, "performance_dispersion": _round(_stdev(exps)) if enough else None, "profitable_fold_ratio": _round(len([v for v in exps if v > 0]) / len(exps)) if exps else None, "profitable_fold_numerator": len([v for v in exps if v > 0]), "profitable_fold_denominator": len(exps), "worst_fold_expectancy_pct": _round(min(exps)) if exps else None, "median_fold_expectancy_pct": _round(_median(exps)) if exps else None, "selected_candidate_frequency": {str(k): v for k, v in sorted(freq.items())}}

def confidence_intervals(values: list[float], seed: int, iterations: int) -> dict[str, Any]:
    if len(values) < 2:
        return {"expectancy_pct": {"lower": None, "upper": None, "width": None, "status": "insufficient_sample"}, "hit_rate": {"lower": None, "upper": None, "width": None, "status": "insufficient_sample"}, "random_seed": seed, "iterations": iterations}
    rng = random.Random(seed)
    means, hit_rates = [], []
    for _ in range(iterations):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(sum(sample) / len(sample)); hit_rates.append(len([v for v in sample if v > 0]) / len(sample))
    means.sort(); hit_rates.sort()
    lo, hi = int(iterations * 0.025), min(iterations - 1, int(iterations * 0.975))
    return {"expectancy_pct": {"lower": _round(means[lo]), "upper": _round(means[hi]), "width": _round(means[hi] - means[lo])}, "hit_rate": {"lower": _round(hit_rates[lo]), "upper": _round(hit_rates[hi]), "width": _round(hit_rates[hi] - hit_rates[lo])}, "random_seed": seed, "iterations": iterations}

def zero_return_audit(events: list[dict[str, Any]], min_movement_rate: float) -> dict[str, Any]:
    zero = [e for e in events if float(e["return_pct"]) == 0.0]
    unchanged = [e for e in events if float(e["highest_price"]) == float(e["lowest_price"]) == float(e["entry_price"])]
    max_run = run = 0; prev_price = object()
    for event in sorted(events, key=lambda e: e["entry_date"]):
        price = event["entry_price"]
        run = run + 1 if price == prev_price else 1; max_run = max(max_run, run); prev_price = price
    tradable = [e for e in events if abs(float(e["return_pct"])) > 0 or abs(float(e["mfe_pct"])) >= 1 or abs(float(e["mae_pct"])) >= 1]
    rate = len(tradable) / len(events) if events else 0
    return {"zero_return_event_count": len(zero), "zero_return_rate": _round(len(zero) / len(events) if events else 0), "unchanged_window_count": len(unchanged), "unchanged_window_rate": _round(len(unchanged) / len(events) if events else 0), "distinct_entry_date_count": len({e["entry_date"] for e in events}), "distinct_entry_price_count": len({e["entry_price"] for e in events}), "maximum_consecutive_unchanged_days": max_run, "stale_price_warning": rate < min_movement_rate, "tradable_movement_event_count": len(tradable), "tradable_movement_rate": _round(rate)}

def _segment_key(event: dict[str, Any], mode: str) -> str:
    if mode == "market_regime": return str(event.get("market_regime", "unknown"))
    if mode == "volatility_bucket":
        ratio = float(event.get("atr") or 0) / max(float(event.get("entry_price") or 1), 1)
        return "low" if ratio < 0.03 else "medium" if ratio < 0.07 else "high"
    p = event.get("prediction_probability")
    if p is None: return "missing"
    p = float(p)
    return "lt_0_60" if p < 0.6 else "0_60_to_0_70" if p < 0.7 else "0_70_to_0_80" if p < 0.8 else "gte_0_80"

def build_segments(events: list[dict[str, Any]], candidates: list[float], config: TPOptimizerConfig) -> dict[str, list[dict[str, Any]]]:
    out = {"market_regime": [], "volatility_bucket": [], "prediction_probability_bucket": []}
    for mode in out:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for e in events: buckets.setdefault(_segment_key(e, mode), []).append(e)
        for key, seg in sorted(buckets.items()):
            if len(seg) < config.min_segment_sample_size:
                out[mode].append({"segment": key, "status": "insufficient_sample", "sample_size": len(seg), "selected_tp_pct": None, "warnings": ["segment sample below minimum"]})
            else:
                metrics = [calculate_candidate_metrics(seg, c) for c in candidates]
                best = select_candidate(metrics, config.selection_weights, max(1, max(int(e["holding_days"]) for e in seg)))
                out[mode].append({"segment": key, "status": "valid", "sample_size": len(seg), "selected_tp_pct": best["tp_pct"], "selection_score": best["selection_score"], "metrics": best, "warnings": []})
    return out

def build_tp_optimizer_artifact(event_path: Path, ticker: str, config: TPOptimizerConfig) -> dict[str, Any]:
    candidates = normalize_candidates(config.candidates)
    event_artifact = load_event_artifact(event_path, ticker)
    raw_events = sorted(event_artifact["events"], key=lambda e: e["entry_date"])
    configured_holding = event_artifact.get("config", {}).get("holding_days")
    eligible, exclusions = split_eligible_events(raw_events, configured_holding)
    non_overlap, purged_count, cluster_count = purge_overlapping_events(eligible)
    cluster_total = cluster_overlapping_events(eligible)
    selection_events = non_overlap if config.overlap_policy == "purge_overlapping" else eligible
    effective_sample_size = len(non_overlap) if config.overlap_policy == "purge_overlapping" else cluster_total
    all_metrics = [calculate_candidate_metrics(eligible, c) for c in candidates]
    selected_metrics = [calculate_candidate_metrics(selection_events, c) for c in candidates]
    best = select_candidate(selected_metrics, config.selection_weights, max(1, max([int(e["holding_days"]) for e in selection_events] or [1]))) if selected_metrics else None
    folds, selected_tps = evaluate_walk_forward(selection_events, candidates, config) if selection_events else ([], [])
    stability = stability_metrics(folds, selected_tps, config.consistency_tolerance_pct)
    validation_returns = []
    for fold in folds:
        validation_returns.extend(realized_returns([e for e in selection_events if fold["validation_start"] <= e["entry_date"] <= fold["validation_end"]], fold["selected_tp_pct"]))
    ci = confidence_intervals(validation_returns, config.random_seed, config.bootstrap_iterations)
    zero_audit = zero_return_audit(eligible, config.minimum_tradable_movement_rate)
    validation_expectancy = _mean([float(f["validation_expectancy_pct"] or 0) for f in folds])
    validation_hit_rate = _mean([float(f["validation_hit_rate"] or 0) for f in folds])
    validation_drawdown = _mean([float(f["validation_drawdown_pct"] or 0) for f in folds])
    warnings, critical = [], []
    if len(eligible) < config.minimum_sample_size: warnings.extend(["sample size below minimum", "eligible sample size below minimum"])
    if effective_sample_size < config.minimum_effective_sample_size: warnings.append("effective sample size below minimum")
    if len(folds) < config.minimum_fold_count: warnings.append("fold count below minimum")
    if validation_expectancy is None or validation_expectancy <= config.minimum_validation_expectancy_pct: warnings.append("validation expectancy below minimum")
    if stability["profitable_fold_ratio"] is None or stability["profitable_fold_ratio"] < config.minimum_profitable_fold_ratio: warnings.append("profitable fold ratio below minimum")
    if stability["worst_fold_expectancy_pct"] is not None and stability["worst_fold_expectancy_pct"] <= config.maximum_downside_tail_pct: warnings.append("downside tail beyond policy limit")
    if ci["expectancy_pct"]["width"] is not None and ci["expectancy_pct"]["width"] > config.maximum_expectancy_ci_width_pct: warnings.append("expectancy confidence interval too wide")
    if ci["expectancy_pct"].get("lower") is not None and ci["expectancy_pct"]["lower"] <= config.minimum_validation_expectancy_pct: warnings.append("expectancy confidence interval lower bound below minimum")
    if zero_audit["stale_price_warning"]: warnings.append("tradable movement rate below minimum")
    if ci["expectancy_pct"].get("status") == "insufficient_sample": warnings.append("expectancy confidence interval insufficient sample")
    usable = not warnings and not critical
    selected = None if not usable else {"tp_pct": best["tp_pct"], "selection_score": best["selection_score"], "selection_score_components": best["selection_score_components"], "validation_expectancy_pct": _round(validation_expectancy), "validation_hit_rate": _round(validation_hit_rate), "median_days_to_hit": best["median_days_to_hit"], "average_drawdown_pct": _round(validation_drawdown), "selection_stability": stability["selection_stability"], "expectancy_stability": stability["expectancy_stability"], "fold_stability": stability["selection_stability"], "sample_size": len(selection_events), "effective_sample_size": effective_sample_size}
    artifact = {"schema_version": SCHEMA_VERSION, "artifact_type": ARTIFACT_TYPE, "ticker": ticker.upper(), "generated_at": datetime.now(timezone.utc).isoformat(), "generator_version": GENERATOR_VERSION, "config": {"candidates": candidates, "minimum_sample_size": config.minimum_sample_size, "fold_count": config.fold_count, "minimum_fold_count": config.minimum_fold_count, "selection_weights": config.selection_weights, "min_segment_sample_size": config.min_segment_sample_size, "consistency_tolerance_pct": config.consistency_tolerance_pct, "return_policy": "TP hit realizes candidate TP; timeout realizes event return_pct.", "random_seed": config.random_seed}, "selection_policy": {"overlap_policy": config.overlap_policy, "score_weights": config.selection_weights}, "usability_policy": {"minimum_validation_expectancy_pct": config.minimum_validation_expectancy_pct, "minimum_profitable_fold_ratio": config.minimum_profitable_fold_ratio, "minimum_effective_sample_size": config.minimum_effective_sample_size, "minimum_validation_sample_size": config.minimum_validation_sample_size, "maximum_downside_tail_pct": config.maximum_downside_tail_pct, "maximum_expectancy_ci_width_pct": config.maximum_expectancy_ci_width_pct, "minimum_tradable_movement_rate": config.minimum_tradable_movement_rate}, "source": {"event_artifact_path": str(event_path), "event_schema_version": event_artifact.get("schema_version"), "event_generated_at": event_artifact.get("generated_at"), "event_count": len(raw_events), "source_checksum": sha256_file(event_path), "data_start": raw_events[0]["entry_date"] if raw_events else None, "data_end": raw_events[-1]["entry_date"] if raw_events else None}, "exclusions": exclusions, "all_events_analysis": {"event_count": len(eligible), "candidates": all_metrics}, "non_overlapping_analysis": {"event_count": len(selection_events), "candidates": selected_metrics}, "raw_event_count": len(raw_events), "eligible_event_count": len(eligible), "overlapping_event_count": purged_count, "purged_event_count": purged_count, "cluster_count": cluster_total, "effective_sample_size": effective_sample_size, "overlap_policy": config.overlap_policy, "zero_return_audit": zero_audit, "candidates": selected_metrics, "folds": folds, "stability": stability, "confidence_intervals": ci, "best_candidate_by_score": best, "selected": selected, "segments": build_segments(selection_events, candidates, config), "quality": {"status": "valid" if usable else "research_only", "usable_for_decision": usable, "sample_size": len(selection_events), "raw_sample_size": len(raw_events), "eligible_sample_size": len(eligible), "minimum_sample_size": config.minimum_sample_size, "fold_count": len(folds), "fold_stability": stability["selection_stability"], "selection_stability": stability["selection_stability"], "expectancy_stability": stability["expectancy_stability"], "effective_sample_size": effective_sample_size, "warnings": warnings, "critical_warnings": critical}, "critical_warnings": critical, "notes": ["Research evidence only; not a BUY recommendation.", "SL Optimizer is intentionally out of scope for Sprint 3.1."]}
    validate_tp_optimizer_artifact(artifact, event_path)
    return artifact

def validate_tp_optimizer_artifact(artifact: dict[str, Any], event_path: Path | None = None) -> None:
    if artifact.get("schema_version") != SCHEMA_VERSION: raise ValueError("invalid schema_version")
    if artifact.get("artifact_type") != ARTIFACT_TYPE: raise ValueError("invalid artifact_type")
    if not artifact.get("ticker"): raise ValueError("ticker is required")
    if not artifact.get("generated_at"): raise ValueError("generated_at is required")
    candidates = artifact.get("config", {}).get("candidates", [])
    if normalize_candidates(candidates) != candidates: raise ValueError("candidates must be unique sorted values in valid range")
    if not artifact.get("source", {}).get("source_checksum"): raise ValueError("source checksum is required")
    if event_path is not None and sha256_file(event_path) != artifact["source"]["source_checksum"]: raise ValueError("source hash mismatch")
    candidate_tps = {float(item.get("tp_pct")) for item in artifact.get("candidates", [])}
    if candidate_tps != {float(v) for v in candidates}: raise ValueError("candidate metrics do not match config candidates")
    prev_end, fold_ids = None, set()
    for fold in artifact.get("folds", []):
        if fold.get("fold_id") in fold_ids: raise ValueError("duplicate fold")
        fold_ids.add(fold.get("fold_id"))
        if fold["train_end"] >= fold["validation_start"]: raise ValueError("train-validation leakage")
        if prev_end is not None and fold["validation_start"] <= prev_end: raise ValueError("duplicate or overlapping validation fold")
        prev_end = fold["validation_end"]
        if float(fold["selected_tp_pct"]) not in candidate_tps: raise ValueError("fold selected TP must come from candidates")
    selected = artifact.get("selected")
    quality = artifact.get("quality", {})
    if selected is None:
        if quality.get("usable_for_decision"): raise ValueError("quality inconsistency: usable artifact requires selected TP")
    elif float(selected.get("tp_pct")) not in candidate_tps:
        raise ValueError("selected TP must come from candidates")
    if quality.get("usable_for_decision") and quality.get("status") != "valid": raise ValueError("quality usable_for_decision requires valid status")
    if not quality.get("usable_for_decision") and quality.get("status") == "valid": raise ValueError("quality inconsistency: valid status requires usable artifact")
    for item in artifact.get("candidates", []):
        for key in ["tp_hit_rate", "timeout_rate", "positive_outcome_rate"]:
            value = item.get(key)
            if value is None or not 0 <= float(value) <= 1: raise ValueError("invalid percentage metric")

def write_tp_optimizer_artifact(artifact: dict[str, Any], output_dir: Path, overwrite: bool = False) -> Path:
    return write_json(artifact, output_dir / f"{artifact['ticker']}_tp_optimizer_v1.json", overwrite=overwrite)

def parse_weights(value: str | None) -> dict[str, float]:
    if not value: return dict(DEFAULT_SELECTION_WEIGHTS)
    weights = dict(DEFAULT_SELECTION_WEIGHTS)
    for part in value.split(","):
        key, raw = part.split("=", 1); weights[key.strip()] = float(raw)
    return weights

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TP optimizer research artifact from event dataset.")
    parser.add_argument("--ticker", required=True); parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("storage/app/trading_research/tp_optimizer"))
    parser.add_argument("--candidate-tp", nargs="+", type=float, default=DEFAULT_CANDIDATES)
    parser.add_argument("--minimum-sample-size", type=int, default=30); parser.add_argument("--fold-count", type=int, default=4)
    parser.add_argument("--selection-weights", type=str); parser.add_argument("--overwrite", action="store_true", default=False)
    parser.add_argument("--overlap-policy", choices=["allow_all", "purge_overlapping", "cluster_overlapping"], default="purge_overlapping")
    parser.add_argument("--minimum-validation-expectancy-pct", type=float, default=0.0)
    parser.add_argument("--minimum-effective-sample-size", type=int, default=30)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args(argv)

def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    config = TPOptimizerConfig(candidates=list(args.candidate_tp), minimum_sample_size=args.minimum_sample_size, fold_count=args.fold_count, selection_weights=parse_weights(args.selection_weights), overlap_policy=args.overlap_policy, minimum_validation_expectancy_pct=args.minimum_validation_expectancy_pct, minimum_effective_sample_size=args.minimum_effective_sample_size, random_seed=args.random_seed)
    artifact = build_tp_optimizer_artifact(args.events, args.ticker, config)
    print(write_tp_optimizer_artifact(artifact, args.output_dir, overwrite=args.overwrite))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
