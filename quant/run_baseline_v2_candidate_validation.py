"""Validate one selected baseline v2 candidate against the active baseline."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.evaluate_phase_a_real_data import load_price_csv  # noqa: E402
from quant.phase_a import add_trend_features, add_volume_features, backtest_signal_frame  # noqa: E402
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.phase_a_transition_utils import dedupe, read_json_object  # noqa: E402


SUMMARY_COLUMNS = [
    "variant",
    "candidate_id",
    "entry_rule",
    "hold_period",
    "min_trades_threshold",
    "profit_buffer_pct",
    "ticker_count",
    "eligible_ticker_count",
    "positive_score_ticker_count",
    "total_trades_sum",
    "signal_count_sum",
    "mean_score",
    "mean_win_rate",
    "mean_buffered_win_rate",
    "mean_average_return",
    "mean_max_drawdown",
    "global_selection_score",
]

PER_TICKER_COLUMNS = [
    "ticker",
    "hold_period",
    "min_trades_threshold",
    "profit_buffer_pct",
    "active_entry_rule",
    "candidate_id",
    "candidate_entry_rule",
    "active_signal_count",
    "candidate_signal_count",
    "delta_signal_count",
    "active_total_trades",
    "candidate_total_trades",
    "delta_total_trades",
    "active_win_rate",
    "candidate_win_rate",
    "delta_win_rate",
    "active_buffered_win_rate",
    "candidate_buffered_win_rate",
    "delta_buffered_win_rate",
    "active_average_return",
    "candidate_average_return",
    "delta_average_return",
    "active_max_drawdown",
    "candidate_max_drawdown",
    "delta_max_drawdown",
    "active_score",
    "candidate_score",
    "delta_score",
    "active_eligible_for_analysis",
    "candidate_eligible_for_analysis",
    "coverage_improved",
    "validation_outcome",
    "candidate_positive_signal",
    "category",
    "market_cap_group",
    "sector",
    "beta_group",
]

DECISION_VALUES = {
    "reject_candidate",
    "keep_candidate_experimental",
    "candidate_usable_for_framework_redesign_only",
}

VALIDATION_STATUS_VALUES = {
    "invalid",
    "weak",
    "usable",
    "promotable",
}


class BaselineV2ValidationCliError(ValueError):
    """Friendly CLI error for baseline v2 validation."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _sanitize_for_json(value: object) -> object:
    if isinstance(value, dict):
        return {key: _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize_for_json(payload), indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _resolve_price_files(data_dir: Path) -> List[Path]:
    candidates = sorted(Path(data_dir).glob("*.csv"))
    valid_paths: List[Path] = []
    required = {"date", "open", "high", "low", "close", "volume"}
    for path in candidates:
        try:
            preview = pd.read_csv(path, nrows=2)
        except Exception:
            continue
        if required.issubset({str(column) for column in preview.columns}):
            valid_paths.append(path)
    return valid_paths


def _feature_frame(frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    return add_trend_features(add_volume_features(frame, volume_spike_threshold=float(threshold)))


def _candidate_signal(
    feature_frame: pd.DataFrame,
    candidate_id: str,
    threshold: float,
    entry_rule: Optional[str] = None,
) -> Tuple[pd.DataFrame, str, str]:
    working = feature_frame.copy()
    normalized_entry_rule = str(entry_rule or "").strip()

    if normalized_entry_rule == "close_gt_ema50_and_volume_spike_threshold":
        signal_column = "signal_active_baseline"
        working[signal_column] = (
            working["close"].gt(working["ema50"]) & working["volume_ratio"].ge(float(threshold))
        ).fillna(False)
        return working, signal_column, normalized_entry_rule

    if normalized_entry_rule == "close_gt_ema50":
        signal_column = "signal_simplified_entry"
        working[signal_column] = working["close"].gt(working["ema50"]).fillna(False)
        return working, signal_column, normalized_entry_rule

    if normalized_entry_rule == "close_gt_ema50_and_bullish_candle":
        signal_column = "signal_trend_guard"
        working[signal_column] = (
            working["close"].gt(working["ema50"]) & working["close"].gt(working["open"])
        ).fillna(False)
        return working, signal_column, normalized_entry_rule

    if normalized_entry_rule == "close_gt_ema20":
        signal_column = "signal_ema20_trend"
        if "ema20" not in working.columns:
            working["ema20"] = working["close"].ewm(span=20, adjust=False, min_periods=20).mean()
        working[signal_column] = (
            working["close"].gt(working["ema20"]) & working["ema20"].notna()
        ).fillna(False)
        return working, signal_column, normalized_entry_rule

    if normalized_entry_rule == "close_gt_ema20_and_bullish_candle":
        signal_column = "signal_ema20_trend_guard"
        if "ema20" not in working.columns:
            working["ema20"] = working["close"].ewm(span=20, adjust=False, min_periods=20).mean()
        working[signal_column] = (
            working["close"].gt(working["ema20"])
            & working["ema20"].notna()
            & working["close"].gt(working["open"])
        ).fillna(False)
        return working, signal_column, normalized_entry_rule

    if normalized_entry_rule == "close_gt_ema20_and_volume_spike_relaxed":
        signal_column = "signal_ema20_volume_relaxed"
        if "ema20" not in working.columns:
            working["ema20"] = working["close"].ewm(span=20, adjust=False, min_periods=20).mean()
        working[signal_column] = (
            working["close"].gt(working["ema20"])
            & working["ema20"].notna()
            & working["volume_ratio"].ge(1.2)
        ).fillna(False)
        return working, signal_column, normalized_entry_rule

    if candidate_id == "baseline_v2_hold3":
        signal_column = "signal_active_baseline"
        entry_rule = "close_gt_ema50_and_volume_spike_threshold"
        working[signal_column] = (
            working["close"].gt(working["ema50"]) & working["volume_ratio"].ge(float(threshold))
        ).fillna(False)
        return working, signal_column, entry_rule

    if candidate_id == "baseline_v2_hold3_with_min_return_buffer":
        signal_column = "signal_active_baseline_buffer"
        entry_rule = "close_gt_ema50_and_volume_spike_threshold"
        working[signal_column] = (
            working["close"].gt(working["ema50"]) & working["volume_ratio"].ge(float(threshold))
        ).fillna(False)
        return working, signal_column, entry_rule

    if candidate_id == "baseline_v2_hold3_with_simplified_entry":
        signal_column = "signal_simplified_entry"
        entry_rule = "close_gt_ema50"
        working[signal_column] = working["close"].gt(working["ema50"]).fillna(False)
        return working, signal_column, entry_rule

    if candidate_id == "baseline_v2_hold3_with_trend_guard":
        signal_column = "signal_trend_guard"
        entry_rule = "close_gt_ema50_and_bullish_candle"
        working[signal_column] = (
            working["close"].gt(working["ema50"]) & working["close"].gt(working["open"])
        ).fillna(False)
        return working, signal_column, entry_rule

    if candidate_id == "baseline_v3_ema20_trend":
        signal_column = "signal_ema20_trend"
        entry_rule = "close_gt_ema20"
        if "ema20" not in working.columns:
            working["ema20"] = working["close"].ewm(span=20, adjust=False, min_periods=20).mean()
        working[signal_column] = (
            working["close"].gt(working["ema20"]) & working["ema20"].notna()
        ).fillna(False)
        return working, signal_column, entry_rule

    if candidate_id == "baseline_v3_ema20_trend_guard":
        signal_column = "signal_ema20_trend_guard"
        entry_rule = "close_gt_ema20_and_bullish_candle"
        if "ema20" not in working.columns:
            working["ema20"] = working["close"].ewm(span=20, adjust=False, min_periods=20).mean()
        working[signal_column] = (
            working["close"].gt(working["ema20"])
            & working["ema20"].notna()
            & working["close"].gt(working["open"])
        ).fillna(False)
        return working, signal_column, entry_rule

    if candidate_id == "baseline_v3_ema20_volume_relaxed":
        signal_column = "signal_ema20_volume_relaxed"
        entry_rule = "close_gt_ema20_and_volume_spike_relaxed"
        if "ema20" not in working.columns:
            working["ema20"] = working["close"].ewm(span=20, adjust=False, min_periods=20).mean()
        working[signal_column] = (
            working["close"].gt(working["ema20"])
            & working["ema20"].notna()
            & working["volume_ratio"].ge(1.2)
        ).fillna(False)
        return working, signal_column, entry_rule

    raise BaselineV2ValidationCliError(f"Unsupported candidate_id: {candidate_id}")


def _buffered_win_rate(trades_df: pd.DataFrame, profit_buffer_pct: float) -> float:
    if trades_df.empty:
        return 0.0
    return round(float(trades_df["return_pct"].gt(float(profit_buffer_pct)).mean() * 100.0), 4)


def _compute_score_components(
    total_trades: int,
    buffered_win_rate: float,
    average_return: float,
    max_drawdown: float,
    min_trades_threshold: int,
) -> Dict[str, float]:
    quality_reward = (float(buffered_win_rate) * 0.25) + (float(average_return) * 2.50)
    trade_support_reward = min(int(total_trades), int(min_trades_threshold)) * 3.50
    drawdown_penalty = max(0.0, float(max_drawdown)) * 0.45
    low_trade_penalty = 0.0
    if int(total_trades) < int(min_trades_threshold):
        low_trade_penalty = 14.0 + ((int(min_trades_threshold) - int(total_trades)) * 4.0)
    score = quality_reward + trade_support_reward - drawdown_penalty - low_trade_penalty
    return {
        "score_quality_reward": round(quality_reward, 4),
        "score_trade_support_reward": round(trade_support_reward, 4),
        "score_drawdown_penalty": round(drawdown_penalty, 4),
        "score_low_trade_penalty": round(low_trade_penalty, 4),
        "score": round(score, 4),
    }


def _evaluate_one_variant(
    feature_frame: pd.DataFrame,
    candidate_id: str,
    threshold: float,
    hold_period: int,
    min_trades: int,
    profit_buffer_pct: float,
    entry_rule: Optional[str] = None,
) -> Dict[str, object]:
    candidate_frame, signal_column, entry_rule = _candidate_signal(
        feature_frame=feature_frame,
        candidate_id=candidate_id,
        threshold=threshold,
        entry_rule=entry_rule,
    )
    signal_count = int(candidate_frame[signal_column].fillna(False).astype(bool).sum())
    result = backtest_signal_frame(
        candidate_frame,
        signal_column=signal_column,
        hold_period=int(hold_period),
        allow_overlap=False,
    )
    buffered_win_rate = _buffered_win_rate(result.trades, profit_buffer_pct=profit_buffer_pct)
    score_components = _compute_score_components(
        total_trades=int(result.total_trades),
        buffered_win_rate=float(buffered_win_rate),
        average_return=float(result.average_return),
        max_drawdown=float(result.max_drawdown),
        min_trades_threshold=int(min_trades),
    )
    return {
        "entry_rule": entry_rule,
        "signal_count": signal_count,
        "total_trades": int(result.total_trades),
        "win_rate": float(result.win_rate),
        "buffered_win_rate": float(buffered_win_rate),
        "average_return": float(result.average_return),
        "max_drawdown": float(result.max_drawdown),
        "eligible_for_analysis": bool(int(result.total_trades) >= int(min_trades)),
        **score_components,
    }


def _classify_validation_outcome(
    active_metrics: Dict[str, object],
    candidate_metrics: Dict[str, object],
) -> str:
    delta_score = _safe_float(candidate_metrics.get("score")) - _safe_float(active_metrics.get("score"))
    delta_avg = _safe_float(candidate_metrics.get("average_return")) - _safe_float(active_metrics.get("average_return"))
    delta_trades = _safe_int(candidate_metrics.get("total_trades")) - _safe_int(active_metrics.get("total_trades"))
    delta_buffered = _safe_float(candidate_metrics.get("buffered_win_rate")) - _safe_float(active_metrics.get("buffered_win_rate"))

    if (
        delta_score >= 2.0
        and delta_avg >= -0.25
        and delta_trades >= -1
        and delta_buffered >= 0
    ):
        return "improve"
    if delta_score <= -2.0 and delta_avg < 0:
        return "worsen"
    return "neutral"


def load_candidate_file(candidate_file: Path) -> Dict[str, object]:
    payload, warnings = read_json_object(Path(candidate_file), "Baseline v2 best candidate JSON")
    if payload is None:
        detail = "; ".join(warnings) if warnings else "candidate file invalid"
        raise BaselineV2ValidationCliError(detail)
    selected = payload.get("selected_candidate")
    if not isinstance(selected, dict):
        raise BaselineV2ValidationCliError("Baseline v2 candidate file does not contain selected_candidate.")
    return payload


def build_per_ticker_comparison(
    data_dir: Path,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    candidate_payload: Dict[str, object],
    min_trades: int,
) -> pd.DataFrame:
    selected = dict(candidate_payload.get("selected_candidate") or {})
    candidate_id = str(selected.get("candidate_id"))
    candidate_entry_rule = str(selected.get("entry_rule") or "").strip() or None
    hold_period = int(float(selected.get("hold_period", 3)))
    profit_buffer_pct = float(selected.get("profit_buffer_pct", 0.0))
    active_candidate_id = "baseline_v2_hold3" if profit_buffer_pct == 0.0 else "baseline_v2_hold3_with_min_return_buffer"

    rows: List[Dict[str, object]] = []
    for path in _resolve_price_files(data_dir):
        ticker = path.stem.upper()
        frame, _ = load_price_csv(path)
        runtime = resolve_phase_a_runtime_settings(
            ticker=ticker,
            baseline_config=baseline_payload,
            metadata_lookup=metadata_lookup,
        )
        metadata_row = dict(runtime.get("metadata_row") or {})
        feature_frame = _feature_frame(frame=frame, threshold=float(runtime["threshold"]))

        active_metrics = _evaluate_one_variant(
            feature_frame=feature_frame,
            candidate_id=active_candidate_id,
            threshold=float(runtime["threshold"]),
            hold_period=hold_period,
            min_trades=min_trades,
            profit_buffer_pct=profit_buffer_pct,
        )
        candidate_metrics = _evaluate_one_variant(
            feature_frame=feature_frame,
            candidate_id=candidate_id,
            threshold=float(runtime["threshold"]),
            hold_period=hold_period,
            min_trades=min_trades,
            profit_buffer_pct=profit_buffer_pct,
            entry_rule=candidate_entry_rule,
        )
        outcome = _classify_validation_outcome(active_metrics=active_metrics, candidate_metrics=candidate_metrics)
        row = {
            "ticker": ticker,
            "hold_period": hold_period,
            "min_trades_threshold": int(min_trades),
            "profit_buffer_pct": profit_buffer_pct,
            "active_entry_rule": active_metrics["entry_rule"],
            "candidate_id": candidate_id,
            "candidate_entry_rule": candidate_metrics["entry_rule"],
            "active_signal_count": int(active_metrics["signal_count"]),
            "candidate_signal_count": int(candidate_metrics["signal_count"]),
            "delta_signal_count": int(candidate_metrics["signal_count"]) - int(active_metrics["signal_count"]),
            "active_total_trades": int(active_metrics["total_trades"]),
            "candidate_total_trades": int(candidate_metrics["total_trades"]),
            "delta_total_trades": int(candidate_metrics["total_trades"]) - int(active_metrics["total_trades"]),
            "active_win_rate": float(active_metrics["win_rate"]),
            "candidate_win_rate": float(candidate_metrics["win_rate"]),
            "delta_win_rate": float(candidate_metrics["win_rate"]) - float(active_metrics["win_rate"]),
            "active_buffered_win_rate": float(active_metrics["buffered_win_rate"]),
            "candidate_buffered_win_rate": float(candidate_metrics["buffered_win_rate"]),
            "delta_buffered_win_rate": float(candidate_metrics["buffered_win_rate"]) - float(active_metrics["buffered_win_rate"]),
            "active_average_return": float(active_metrics["average_return"]),
            "candidate_average_return": float(candidate_metrics["average_return"]),
            "delta_average_return": float(candidate_metrics["average_return"]) - float(active_metrics["average_return"]),
            "active_max_drawdown": float(active_metrics["max_drawdown"]),
            "candidate_max_drawdown": float(candidate_metrics["max_drawdown"]),
            "delta_max_drawdown": float(candidate_metrics["max_drawdown"]) - float(active_metrics["max_drawdown"]),
            "active_score": float(active_metrics["score"]),
            "candidate_score": float(candidate_metrics["score"]),
            "delta_score": float(candidate_metrics["score"]) - float(active_metrics["score"]),
            "active_eligible_for_analysis": bool(active_metrics["eligible_for_analysis"]),
            "candidate_eligible_for_analysis": bool(candidate_metrics["eligible_for_analysis"]),
            "coverage_improved": bool(candidate_metrics["eligible_for_analysis"]) and not bool(active_metrics["eligible_for_analysis"]),
            "validation_outcome": outcome,
            "candidate_positive_signal": bool(
                float(candidate_metrics["score"]) > float(active_metrics["score"])
                and float(candidate_metrics["average_return"]) >= float(active_metrics["average_return"])
            ),
            "category": metadata_row.get("category"),
            "market_cap_group": metadata_row.get("market_cap_group"),
            "sector": metadata_row.get("sector"),
            "beta_group": metadata_row.get("beta_group"),
        }
        rows.append(row)

    per_ticker_df = pd.DataFrame(rows)
    return per_ticker_df.reindex(columns=PER_TICKER_COLUMNS).sort_values("ticker").reset_index(drop=True)


def build_validation_assessment(
    summary_df: pd.DataFrame,
    per_ticker_df: pd.DataFrame,
    candidate_payload: Dict[str, object],
    min_trades: int,
    min_eligible_tickers: int,
) -> Dict[str, object]:
    selected = dict(candidate_payload.get("selected_candidate") or {})
    active = dict(summary_df.loc[summary_df["variant"] == "active_baseline"].iloc[0].to_dict())
    candidate = dict(summary_df.loc[summary_df["variant"] == "baseline_v2_candidate"].iloc[0].to_dict())

    eligible_ticker_count = _safe_int(candidate.get("eligible_ticker_count"))
    total_trades_sum = _safe_int(candidate.get("total_trades_sum"))
    signal_count_sum = _safe_int(candidate.get("signal_count_sum"))
    mean_score = _safe_float(candidate.get("mean_score"))
    mean_average_return = _safe_float(candidate.get("mean_average_return"))
    active_mean_score = _safe_float(active.get("mean_score"))
    active_average_return = _safe_float(active.get("mean_average_return"))
    positive_ticker_count = int((per_ticker_df["validation_outcome"] == "improve").sum())
    worsen_ticker_count = int((per_ticker_df["validation_outcome"] == "worsen").sum())
    minimum_trade_sample = max(int(min_trades) * max(1, int(min_eligible_tickers)), int(min_trades) * 2)
    trade_sample_ok = total_trades_sum >= minimum_trade_sample
    no_trade_collapse = total_trades_sum > 0 and signal_count_sum > 0
    score_ok = mean_score > -5.0
    coverage_ok = eligible_ticker_count >= int(min_eligible_tickers)
    candidate_is_better = (
        _safe_float(candidate.get("global_selection_score")) > _safe_float(active.get("global_selection_score")) + 1.0
        and mean_average_return >= active_average_return - 0.25
    )
    small_sample_risk = not trade_sample_ok or eligible_ticker_count < max(1, int(min_eligible_tickers))
    improvement_ok = mean_score >= active_mean_score - 0.5 and positive_ticker_count >= worsen_ticker_count

    if not no_trade_collapse or not score_ok:
        validation_status = "invalid"
        recommendation = "Kandidat redesign belum usable. Perlu redesign lagi sebelum validasi ulang."
        next_action = "redesign_baseline_v2_again"
    elif coverage_ok and trade_sample_ok and candidate_is_better and mean_score > 0 and improvement_ok:
        validation_status = "promotable"
        recommendation = (
            "Kandidat baseline v2 terlihat usable untuk memperjelas redesign framework evaluasi, "
            "tetapi tetap tidak boleh dipromosikan menjadi baseline operasional atau membuka retry Phase B."
        )
        next_action = "archive_candidate_for_framework_redesign_only"
    elif candidate_is_better and no_trade_collapse and mean_score > -1.0 and (
        trade_sample_ok or eligible_ticker_count >= max(1, int(min_eligible_tickers) - 1)
    ):
        validation_status = "usable"
        recommendation = "Kandidat baseline v2 masih bersifat audit-only dan hanya boleh dipakai sebagai input redesign framework."
        next_action = "hold_candidate_for_framework_redesign_only"
    else:
        validation_status = "weak"
        recommendation = "Kandidat baseline v2 belum cukup kuat untuk promosi. Tetap eksperimental sambil redesign atau observasi tambahan."
        next_action = "keep_baseline_v2_experimental"

    return {
        "generated_at": _now_iso(),
        "candidate_id": str(selected.get("candidate_id") or ""),
        "entry_rule": str(selected.get("entry_rule") or ""),
        "hold_period": _safe_int(selected.get("hold_period"), 3),
        "min_trades": _safe_int(selected.get("min_trades"), _safe_int(selected.get("min_trades_threshold"), min_trades)),
        "validation_status": validation_status,
        "eligible_ticker_count": eligible_ticker_count,
        "min_eligible_tickers_required": int(min_eligible_tickers),
        "total_trades_sum": total_trades_sum,
        "minimum_trade_sample_required": minimum_trade_sample,
        "trade_sample_ok": bool(trade_sample_ok),
        "no_trade_collapse": bool(no_trade_collapse),
        "score": mean_score,
        "score_ok": bool(score_ok),
        "candidate_is_better_than_active_baseline": bool(candidate_is_better),
        "coverage_ok": bool(coverage_ok),
        "small_sample_risk": bool(small_sample_risk),
        "positive_ticker_count": positive_ticker_count,
        "worsen_ticker_count": worsen_ticker_count,
        "average_return": mean_average_return,
        "win_rate": _safe_float(candidate.get("mean_win_rate")),
        "max_drawdown": _safe_float(candidate.get("mean_max_drawdown")),
        "recommendation": recommendation,
        "next_action": next_action,
    }


def build_summary_results(
    per_ticker_df: pd.DataFrame,
    candidate_payload: Dict[str, object],
) -> pd.DataFrame:
    selected = dict(candidate_payload.get("selected_candidate") or {})
    hold_period = _safe_int(selected.get("hold_period"), 3)
    min_trades_threshold = _safe_int(selected.get("min_trades_threshold"), 5)
    profit_buffer_pct = _safe_float(selected.get("profit_buffer_pct"), 0.0)
    candidate_id = str(selected.get("candidate_id"))

    rows: List[Dict[str, object]] = []
    for variant in ["active_baseline", "baseline_v2_candidate"]:
        prefix = "active" if variant == "active_baseline" else "candidate"
        rows.append(
            {
                "variant": variant,
                "candidate_id": candidate_id if variant == "baseline_v2_candidate" else "baseline_active_eval_aligned",
                "entry_rule": (
                    str(per_ticker_df["active_entry_rule"].iloc[0])
                    if prefix == "active"
                    else str(per_ticker_df["candidate_entry_rule"].iloc[0])
                ),
                "hold_period": hold_period,
                "min_trades_threshold": min_trades_threshold,
                "profit_buffer_pct": profit_buffer_pct,
                "ticker_count": int(len(per_ticker_df)),
                "eligible_ticker_count": int(per_ticker_df[f"{prefix}_eligible_for_analysis"].sum()),
                "positive_score_ticker_count": int((per_ticker_df[f"{prefix}_score"] > 0).sum()),
                "total_trades_sum": int(per_ticker_df[f"{prefix}_total_trades"].sum()),
                "signal_count_sum": int(per_ticker_df[f"{prefix}_signal_count"].sum()),
                "mean_score": float(per_ticker_df[f"{prefix}_score"].mean()),
                "mean_win_rate": float(per_ticker_df[f"{prefix}_win_rate"].mean()),
                "mean_buffered_win_rate": float(per_ticker_df[f"{prefix}_buffered_win_rate"].mean()),
                "mean_average_return": float(per_ticker_df[f"{prefix}_average_return"].mean()),
                "mean_max_drawdown": float(per_ticker_df[f"{prefix}_max_drawdown"].mean()),
            }
        )
    summary_df = pd.DataFrame(rows)
    summary_df["global_selection_score"] = (
        summary_df["mean_score"]
        + (summary_df["eligible_ticker_count"] * 6.0)
        + (summary_df["positive_score_ticker_count"] * 3.0)
        + (summary_df["total_trades_sum"] * 0.10)
    )
    return summary_df.reindex(columns=SUMMARY_COLUMNS)


def determine_go_no_go(
    assessment: Dict[str, object],
    summary_df: pd.DataFrame,
    per_ticker_df: pd.DataFrame,
    candidate_payload: Dict[str, object],
    min_eligible_tickers: int,
) -> Dict[str, object]:
    active = dict(summary_df.loc[summary_df["variant"] == "active_baseline"].iloc[0].to_dict())
    candidate = dict(summary_df.loc[summary_df["variant"] == "baseline_v2_candidate"].iloc[0].to_dict())

    candidate_is_better = (
        _safe_float(candidate.get("global_selection_score")) > _safe_float(active.get("global_selection_score")) + 1.0
        and _safe_float(candidate.get("mean_average_return")) >= _safe_float(active.get("mean_average_return")) - 0.25
    )
    coverage_improved = (
        _safe_int(candidate.get("eligible_ticker_count")) > _safe_int(active.get("eligible_ticker_count"))
    )
    eligible_ticker_count = _safe_int(candidate.get("eligible_ticker_count"))
    positive_ticker_count = int((per_ticker_df["validation_outcome"] == "improve").sum())
    neutral_ticker_count = int((per_ticker_df["validation_outcome"] == "neutral").sum())
    worsen_ticker_count = int((per_ticker_df["validation_outcome"] == "worsen").sum())

    usable_for_framework_redesign = bool(
        candidate_is_better
        and eligible_ticker_count >= int(min_eligible_tickers)
        and positive_ticker_count >= int(min_eligible_tickers)
        and _safe_float(candidate.get("mean_score")) > 0
        and bool(assessment.get("trade_sample_ok"))
    )

    validation_status = str(assessment.get("validation_status") or "")

    if validation_status == "invalid" or not candidate_is_better:
        decision = "reject_candidate"
        recommended_next_action = "revise_baseline_further"
    elif validation_status in {"promotable", "usable"} and usable_for_framework_redesign:
        decision = "candidate_usable_for_framework_redesign_only"
        recommended_next_action = "hold_candidate_for_framework_redesign_and_data_extension"
    else:
        decision = "keep_candidate_experimental"
        recommended_next_action = "keep_candidate_experimental_and_continue_validation"

    return {
        "decision": decision,
        "candidate_id": str(dict(candidate_payload.get("selected_candidate") or {}).get("candidate_id")),
        "validation_status": validation_status,
        "candidate_is_better_than_active_baseline": bool(candidate_is_better),
        "coverage_improved": bool(coverage_improved),
        "eligible_ticker_count": eligible_ticker_count,
        "positive_ticker_count": positive_ticker_count,
        "neutral_ticker_count": neutral_ticker_count,
        "worsen_ticker_count": worsen_ticker_count,
        "can_promote_baseline_v2": False,
        "can_retry_phase_b_after_validation": False,
        "usable_for_framework_redesign_only": usable_for_framework_redesign,
        "recommended_next_action": recommended_next_action,
        "decision_notes": dedupe(
            [
                "Candidate mengungguli baseline aktif pada setting evaluasi yang sama."
                if candidate_is_better
                else "Candidate tidak cukup mengungguli baseline aktif pada setting evaluasi yang sama.",
                "Coverage eligible ticker belum mencapai guardrail minimum."
                if eligible_ticker_count < int(min_eligible_tickers)
                else "",
                "Candidate hanya boleh dipakai sebagai input redesign framework; baseline operasional tetap Phase A aktif."
                if decision == "candidate_usable_for_framework_redesign_only"
                else "",
                "Candidate hanya cocok untuk subset kecil ticker sehingga belum layak dipromosikan penuh."
                if decision == "keep_candidate_experimental"
                else "",
            ]
        ),
    }


def build_summary_payload(
    summary_df: pd.DataFrame,
    per_ticker_df: pd.DataFrame,
    candidate_payload: Dict[str, object],
    min_trades: int,
    min_eligible_tickers: int,
) -> Dict[str, object]:
    active = dict(summary_df.loc[summary_df["variant"] == "active_baseline"].iloc[0].to_dict())
    candidate = dict(summary_df.loc[summary_df["variant"] == "baseline_v2_candidate"].iloc[0].to_dict())
    improve_tickers = per_ticker_df.loc[per_ticker_df["validation_outcome"] == "improve", "ticker"].astype(str).tolist()
    worsen_tickers = per_ticker_df.loc[per_ticker_df["validation_outcome"] == "worsen", "ticker"].astype(str).tolist()
    subset_candidates = per_ticker_df.loc[
        per_ticker_df["candidate_eligible_for_analysis"] & per_ticker_df["candidate_positive_signal"],
        "ticker",
    ].astype(str).tolist()

    return {
        "generated_at": _now_iso(),
        "candidate_context": _sanitize_for_json(dict(candidate_payload.get("selected_candidate") or {})),
        "guardrails": {
            "min_trades": int(min_trades),
            "min_eligible_tickers": int(min_eligible_tickers),
        },
        "active_baseline_summary": _sanitize_for_json(active),
        "candidate_summary": _sanitize_for_json(candidate),
        "delta_summary": {
            "delta_eligible_ticker_count": _safe_int(candidate.get("eligible_ticker_count")) - _safe_int(active.get("eligible_ticker_count")),
            "delta_positive_score_ticker_count": _safe_int(candidate.get("positive_score_ticker_count")) - _safe_int(active.get("positive_score_ticker_count")),
            "delta_total_trades_sum": _safe_int(candidate.get("total_trades_sum")) - _safe_int(active.get("total_trades_sum")),
            "delta_signal_count_sum": _safe_int(candidate.get("signal_count_sum")) - _safe_int(active.get("signal_count_sum")),
            "delta_mean_score": _safe_float(candidate.get("mean_score")) - _safe_float(active.get("mean_score")),
            "delta_mean_average_return": _safe_float(candidate.get("mean_average_return")) - _safe_float(active.get("mean_average_return")),
        },
        "stability": {
            "improve_ticker_count": int((per_ticker_df["validation_outcome"] == "improve").sum()),
            "neutral_ticker_count": int((per_ticker_df["validation_outcome"] == "neutral").sum()),
            "worsen_ticker_count": int((per_ticker_df["validation_outcome"] == "worsen").sum()),
            "coverage_improved_ticker_count": int(per_ticker_df["coverage_improved"].sum()),
            "subset_candidate_tickers": subset_candidates,
            "improve_tickers": improve_tickers,
            "worsen_tickers": worsen_tickers,
        },
    }


def build_report_text(
    summary_payload: Dict[str, object],
    validation_assessment: Dict[str, object],
    go_no_go: Dict[str, object],
) -> str:
    active = dict(summary_payload.get("active_baseline_summary") or {})
    candidate = dict(summary_payload.get("candidate_summary") or {})
    lines = [
        "Baseline v2 Candidate Validation",
        "================================",
        "",
        f"- Validation status: {validation_assessment['validation_status']}",
        f"- Decision: {go_no_go['decision']}",
        f"- Candidate: {go_no_go['candidate_id']}",
        f"- Candidate better than active baseline: {go_no_go['candidate_is_better_than_active_baseline']}",
        f"- Coverage improved: {go_no_go['coverage_improved']}",
        f"- Eligible ticker count: {go_no_go['eligible_ticker_count']}",
        f"- Min eligible tickers required: {validation_assessment['min_eligible_tickers_required']}",
        f"- Trade sample ok: {validation_assessment['trade_sample_ok']}",
        f"- No trade collapse: {validation_assessment['no_trade_collapse']}",
        f"- Score ok: {validation_assessment['score_ok']}",
        f"- Positive ticker count: {go_no_go['positive_ticker_count']}",
        f"- Can promote baseline v2: {go_no_go['can_promote_baseline_v2']}",
        f"- Can retry Phase B after validation: {go_no_go['can_retry_phase_b_after_validation']}",
        f"- Usable for framework redesign only: {go_no_go.get('usable_for_framework_redesign_only')}",
        f"- Recommendation: {validation_assessment['recommendation']}",
        f"- Recommended next action: {validation_assessment['next_action']}",
        "",
        "Active baseline summary:",
        f"- eligible_ticker_count={_safe_int(active.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_int(active.get('total_trades_sum'))}",
        f"- mean_score={_safe_float(active.get('mean_score')):+.4f}",
        f"- mean_average_return={_safe_float(active.get('mean_average_return')):+.4f}",
        "",
        "Candidate summary:",
        f"- eligible_ticker_count={_safe_int(candidate.get('eligible_ticker_count'))}",
        f"- total_trades_sum={_safe_int(candidate.get('total_trades_sum'))}",
        f"- mean_score={_safe_float(candidate.get('mean_score')):+.4f}",
        f"- mean_average_return={_safe_float(candidate.get('mean_average_return')):+.4f}",
        "",
        "Stability:",
        f"- improve_ticker_count={safe_int(summary_payload.get('stability', {}).get('improve_ticker_count'))}",
        f"- neutral_ticker_count={safe_int(summary_payload.get('stability', {}).get('neutral_ticker_count'))}",
        f"- worsen_ticker_count={safe_int(summary_payload.get('stability', {}).get('worsen_ticker_count'))}",
    ]
    if go_no_go.get("decision_notes"):
        lines.extend(["", "Decision notes:"])
        for item in list(go_no_go.get("decision_notes") or []):
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def update_transition_artifact(output_dir: Path, go_no_go: Dict[str, object]) -> Dict[str, object]:
    transition_path = Path(output_dir) / "phase_a_to_phase_b_transition.json"
    payload, warnings = read_json_object(transition_path, "Phase A to Phase B transition JSON")
    if payload is None:
        return {"updated": False, "path": str(transition_path), "warnings": warnings}

    payload["baseline_v2_validation_status"] = go_no_go.get("decision")
    payload["baseline_v2_validation_next_action"] = go_no_go.get("recommended_next_action")
    payload["phase_b_retry_readiness_after_candidate_validation"] = "not_ready_yet"
    payload["baseline_v2_validation_scope"] = "framework_redesign_only"
    transition_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    report_path = Path(output_dir) / "phase_a_to_phase_b_transition_report.txt"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    appendix = [
        "",
        "Baseline v2 Validation Update:",
        f"- baseline_v2_validation_status: {go_no_go.get('decision')}",
        f"- baseline_v2_validation_next_action: {go_no_go.get('recommended_next_action')}",
        "- baseline_v2_validation_scope: framework_redesign_only",
        "- phase_b_retry_readiness_after_candidate_validation: not_ready_yet",
    ]
    report_path.write_text(report_text.rstrip() + "\n" + "\n".join(appendix) + "\n", encoding="utf-8")
    return {"updated": True, "path": str(transition_path), "report_path": str(report_path), "warnings": warnings}


def run_baseline_v2_candidate_validation(
    data_dir: Path,
    output_dir: Path,
    baseline_config: Optional[Path],
    candidate_file: Path,
    metadata_file: Optional[Path],
    min_trades: int,
    min_eligible_tickers: int,
) -> Dict[str, object]:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_payload, baseline_warnings, _ = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    candidate_payload = load_candidate_file(candidate_file)

    per_ticker_df = build_per_ticker_comparison(
        data_dir=data_dir,
        baseline_payload=baseline_payload,
        metadata_lookup=metadata_lookup,
        candidate_payload=candidate_payload,
        min_trades=int(min_trades),
    )
    if per_ticker_df.empty:
        raise BaselineV2ValidationCliError("No per-ticker validation rows were produced.")

    results_df = build_summary_results(per_ticker_df=per_ticker_df, candidate_payload=candidate_payload)
    summary_payload = build_summary_payload(
        summary_df=results_df,
        per_ticker_df=per_ticker_df,
        candidate_payload=candidate_payload,
        min_trades=min_trades,
        min_eligible_tickers=min_eligible_tickers,
    )
    summary_payload["warnings"] = dedupe([*baseline_warnings, *metadata_warnings])
    validation_assessment = build_validation_assessment(
        summary_df=results_df,
        per_ticker_df=per_ticker_df,
        candidate_payload=candidate_payload,
        min_trades=min_trades,
        min_eligible_tickers=min_eligible_tickers,
    )
    go_no_go = determine_go_no_go(
        assessment=validation_assessment,
        summary_df=results_df,
        per_ticker_df=per_ticker_df,
        candidate_payload=candidate_payload,
        min_eligible_tickers=min_eligible_tickers,
    )
    report_text = build_report_text(
        summary_payload=summary_payload,
        validation_assessment=validation_assessment,
        go_no_go=go_no_go,
    )

    results_path = output_dir / "baseline_v2_validation_results.csv"
    per_ticker_path = output_dir / "baseline_v2_validation_per_ticker.csv"
    summary_path = output_dir / "baseline_v2_validation_summary.json"
    validation_path = output_dir / "baseline_v2_validation.json"
    report_path = output_dir / "baseline_v2_validation_report.txt"
    go_no_go_path = output_dir / "baseline_v2_validation_go_no_go.json"

    results_df.to_csv(results_path, index=False)
    per_ticker_df.to_csv(per_ticker_path, index=False)
    _write_json(summary_path, summary_payload)
    _write_json(validation_path, validation_assessment)
    _write_text(report_path, report_text.splitlines())
    _write_json(go_no_go_path, go_no_go)

    transition_update = update_transition_artifact(output_dir=output_dir, go_no_go=go_no_go)

    return {
        "results_df": results_df,
        "per_ticker_df": per_ticker_df,
        "summary_payload": summary_payload,
        "validation_assessment": validation_assessment,
        "go_no_go": go_no_go,
        "transition_update": transition_update,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one selected baseline v2 candidate against the active baseline."
    )
    parser.add_argument("--data-dir", default="data", help="Directory containing per-ticker OHLCV CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory for validation artifacts.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Path to active baseline config JSON.",
    )
    parser.add_argument(
        "--candidate-file",
        default="output/baseline_v2_best_candidate.json",
        help="Path to selected baseline v2 candidate JSON.",
    )
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional metadata CSV path.",
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=5,
        help="Minimum trades guardrail for analysis. Default: 5",
    )
    parser.add_argument(
        "--min-eligible-tickers",
        type=int,
        default=3,
        help="Minimum eligible tickers required before promotion/retry. Default: 3",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = run_baseline_v2_candidate_validation(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        candidate_file=Path(args.candidate_file),
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        min_trades=int(args.min_trades),
        min_eligible_tickers=int(args.min_eligible_tickers),
    )
    print(f"Decision: {result['go_no_go']['decision']}")
    print(f"Candidate better than active baseline: {result['go_no_go']['candidate_is_better_than_active_baseline']}")
    return 0


def safe_int(value: object, default: int = 0) -> int:
    return _safe_int(value, default=default)


if __name__ == "__main__":
    raise SystemExit(main())
