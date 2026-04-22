"""Run the first walk-forward validation pass for the rebuild strategy stack."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

if __package__ is None or __package__ == "":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
)
from quant.run_phase_4_position_sizing import (  # noqa: E402
    _apply_entry_variant,
    _apply_position_sizing,
    _attach_entry_context,
    _build_entry_exit_frame,
    _evaluate_variant_ticker,
)


SUMMARY_OUTPUT = "walk_forward_validation_summary.json"
REPORT_OUTPUT = "walk_forward_validation_report.txt"


@dataclass(frozen=True)
class WalkForwardWindow:
    window_id: str
    label: str
    start_date: str
    end_date: str
    role: str


@dataclass(frozen=True)
class WalkForwardStack:
    stack_id: str
    label: str
    layer_3_active: bool
    position_sizing_active: bool
    risk_per_trade_pct: float
    max_position_pct: float
    initial_capital: float


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_window_registry() -> List[WalkForwardWindow]:
    return [
        WalkForwardWindow(
            window_id="in_sample",
            label="In-sample 2019-2021",
            start_date="2019-01-01",
            end_date="2021-12-31",
            role="in_sample",
        ),
        WalkForwardWindow(
            window_id="out_of_sample",
            label="Out-of-sample 2022-2023",
            start_date="2022-01-01",
            end_date="2023-12-31",
            role="out_of_sample",
        ),
        WalkForwardWindow(
            window_id="final_holdout",
            label="Final holdout 2024-2025",
            start_date="2024-01-01",
            end_date="2025-12-31",
            role="final_holdout",
        ),
    ]


def _build_stack_registry() -> List[WalkForwardStack]:
    return [
        WalkForwardStack(
            stack_id="rebuild_core_without_layer3",
            label="Layer 1 + Layer 2 alternative + Layer 5 ATR trailing stop + Layer 4 sizing",
            layer_3_active=False,
            position_sizing_active=True,
            risk_per_trade_pct=2.0,
            max_position_pct=10.0,
            initial_capital=100_000_000.0,
        ),
        WalkForwardStack(
            stack_id="rebuild_core_with_layer3_optional_toggle",
            label="Layer 1 + Layer 2 alternative + Layer 3 optional + Layer 5 ATR trailing stop + Layer 4 sizing",
            layer_3_active=True,
            position_sizing_active=True,
            risk_per_trade_pct=2.0,
            max_position_pct=10.0,
            initial_capital=100_000_000.0,
        ),
    ]


def _sanitize_for_json(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value


def _profit_factor_from_trades(trades_df: pd.DataFrame) -> Optional[float]:
    if trades_df.empty or "pnl_value" not in trades_df.columns:
        return None
    gross_profit = float(trades_df.loc[trades_df["pnl_value"] > 0, "pnl_value"].sum())
    gross_loss = float(trades_df.loc[trades_df["pnl_value"] < 0, "pnl_value"].sum())
    if gross_profit <= 0 or gross_loss >= 0:
        return None
    return round(gross_profit / abs(gross_loss), 4)


def _pct_degradation(in_sample_value: float, other_value: float) -> Optional[float]:
    baseline = float(in_sample_value)
    comparison = float(other_value)
    if baseline <= 0:
        return None
    return round(((baseline - comparison) / baseline) * 100.0, 4)


def _summarize_sample_adequacy(
    frame: pd.DataFrame,
    per_ticker_df: pd.DataFrame,
) -> tuple[str, str, Dict[str, object]]:
    if frame.empty:
        detail = {
            "active_ticker_count_median": 0.0,
            "active_single_ticker_day_pct": 0.0,
            "tickers_with_coverage_collapse": 0,
            "coverage_collapse_tickers": [],
        }
        return "high", "Window kosong setelah pemotongan tanggal.", detail

    active_by_date = (
        frame.groupby("date")
        .agg(
            active_ticker_count=("active_selected", "sum"),
            available_ticker_count=("available_ticker_count", "max"),
        )
        .reset_index()
    )
    collapse_tickers = (
        per_ticker_df.loc[per_ticker_df["coverage_collapsed"].astype(bool), "ticker"].astype(str).tolist()
        if not per_ticker_df.empty
        else []
    )
    summary = {
        "active_ticker_count_median": round(float(active_by_date["active_ticker_count"].median()), 4),
        "active_single_ticker_day_pct": round(float(active_by_date["active_ticker_count"].eq(1).mean() * 100.0), 4),
        "total_trades": int(per_ticker_df["total_trades"].sum()) if not per_ticker_df.empty else 0,
        "tickers_with_coverage_collapse": int(len(collapse_tickers)),
    }
    universe_max = int(active_by_date["available_ticker_count"].max())
    risk, reason = _classify_walk_forward_sample_adequacy(summary, universe_max=universe_max)
    detail = {
        "active_ticker_count_median": summary["active_ticker_count_median"],
        "active_single_ticker_day_pct": summary["active_single_ticker_day_pct"],
        "tickers_with_coverage_collapse": int(len(collapse_tickers)),
        "coverage_collapse_tickers": collapse_tickers,
    }
    return risk, reason, detail


def _classify_walk_forward_sample_adequacy(
    summary: Dict[str, object],
    *,
    universe_max: int,
) -> tuple[str, str]:
    median_active = float(summary["active_ticker_count_median"])
    single_day_pct = float(summary["active_single_ticker_day_pct"])
    total_trades = int(summary["total_trades"])
    collapse = int(summary["tickers_with_coverage_collapse"])

    if collapse > 0 or median_active <= 2.0 or single_day_pct >= 20.0 or total_trades < 300:
        reasons: List[str] = []
        if collapse > 0:
            reasons.append("ada coverage collapse per ticker")
        if median_active <= 2.0:
            reasons.append("median active ticker terlalu sempit")
        if single_day_pct >= 20.0:
            reasons.append("terlalu banyak single-ticker day")
        if total_trades < 300:
            reasons.append("trade sample di bawah 300")
        return "high", "Sample adequacy tinggi risikonya karena " + ", ".join(reasons) + "."

    if universe_max < 10 or median_active <= 3.0 or total_trades < 600:
        reasons = []
        if universe_max < 10:
            reasons.append(f"available universe window hanya {universe_max} ticker")
        if median_active <= 3.0:
            reasons.append(f"median active ticker hanya {median_active}")
        if total_trades < 600:
            reasons.append(f"total trades window hanya {total_trades}")
        return "moderate", "Prototype masih usable, tetapi sample validation masih tipis karena " + ", ".join(reasons) + "."

    return "low", "Sample cukup untuk prototype dan tidak menunjukkan penyempitan berlebihan."


def _slice_window_frame(frame: pd.DataFrame, window: WalkForwardWindow) -> pd.DataFrame:
    working = frame.copy()
    working["date"] = pd.to_datetime(working["date"])
    start = pd.Timestamp(window.start_date)
    end = pd.Timestamp(window.end_date)
    sliced = working.loc[working["date"].between(start, end)].copy()
    return sliced.sort_values(["date", "ticker"]).reset_index(drop=True)


def _mask_non_tradable_tail_signals(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.sort_values("date").reset_index(drop=True).copy()
    if working.empty:
        return working
    working["entry_signal"] = working["entry_signal"].fillna(False).astype(bool)
    working.loc[working.index[-1], "entry_signal"] = False
    return working


def _evaluate_window(
    prepared_frame: pd.DataFrame,
    stack: WalkForwardStack,
    window: WalkForwardWindow,
    *,
    allow_overlap: bool,
) -> Dict[str, object]:
    class _Variant:
        layer_3_active = stack.layer_3_active
        position_sizing_active = stack.position_sizing_active
        risk_per_trade_pct = stack.risk_per_trade_pct
        max_position_pct = stack.max_position_pct
        initial_capital = stack.initial_capital

    variant_frame = _apply_entry_variant(prepared_frame, _Variant())
    window_frame = _slice_window_frame(variant_frame, window)

    ticker_rows: List[Dict[str, object]] = []
    trade_frames: List[pd.DataFrame] = []
    for ticker, group in window_frame.groupby("ticker"):
        tradable_group = _mask_non_tradable_tail_signals(group.copy())
        ticker_row, ticker_trades = _evaluate_variant_ticker(
            ticker,
            tradable_group,
            layer_3_active=stack.layer_3_active,
            allow_overlap=allow_overlap,
        )
        ticker_rows.append(ticker_row)
        if not ticker_trades.empty:
            trade_frames.append(ticker_trades)

    per_ticker_df = pd.DataFrame(ticker_rows)
    trades_df = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    trades_df = _attach_entry_context(window_frame, trades_df)
    sized_trades_df, sizing_metrics = _apply_position_sizing(trades_df, _Variant())

    sample_risk, sample_reason, sample_detail = _summarize_sample_adequacy(window_frame, per_ticker_df)
    profit_factor = _profit_factor_from_trades(sized_trades_df)

    requested_start = pd.Timestamp(window.start_date)
    requested_end = pd.Timestamp(window.end_date)
    effective_start = window_frame["date"].min() if not window_frame.empty else None
    effective_end = window_frame["date"].max() if not window_frame.empty else None
    first_trade_date = sized_trades_df["entry_date"].min() if not sized_trades_df.empty else None
    last_trade_date = sized_trades_df["exit_date"].max() if not sized_trades_df.empty else None

    return {
        "window_id": window.window_id,
        "window_label": window.label,
        "window_role": window.role,
        "requested_start_date": requested_start.date().isoformat(),
        "requested_end_date": requested_end.date().isoformat(),
        "effective_data_start_date": effective_start.date().isoformat() if effective_start is not None else None,
        "effective_data_end_date": effective_end.date().isoformat() if effective_end is not None else None,
        "first_trade_date": first_trade_date.date().isoformat() if first_trade_date is not None else None,
        "last_trade_date": last_trade_date.date().isoformat() if last_trade_date is not None else None,
        "total_trades": int(len(sized_trades_df)),
        "win_rate": round(float(sized_trades_df["is_win"].mean() * 100.0), 4) if not sized_trades_df.empty else 0.0,
        "average_return_per_trade": round(float(sized_trades_df["return_pct"].mean()), 4)
        if not sized_trades_df.empty
        else 0.0,
        "max_drawdown_pct": sizing_metrics["portfolio_max_drawdown_pct"],
        "profit_factor": profit_factor,
        "portfolio_return_pct": sizing_metrics["portfolio_return_pct"],
        "portfolio_ending_value": sizing_metrics["portfolio_ending_value"],
        "avg_position_size_pct": sizing_metrics["avg_position_size_pct"],
        "cap_hit_rate_pct": sizing_metrics["cap_hit_rate_pct"],
        "sample_adequacy": {
            "risk": sample_risk,
            "reason": sample_reason,
            **sample_detail,
        },
        "window_notes": [
            "Signals dan trade dievaluasi hanya di dalam window ini; trade yang melewati akhir window tidak dihitung."
        ],
    }


def _assess_stack_stability(window_lookup: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    in_sample = window_lookup.get("in_sample", {})
    out_of_sample = window_lookup.get("out_of_sample", {})
    final_holdout = window_lookup.get("final_holdout", {})

    is_avg_return = float(in_sample.get("average_return_per_trade") or 0.0)
    oos_avg_return = float(out_of_sample.get("average_return_per_trade") or 0.0)
    holdout_avg_return = float(final_holdout.get("average_return_per_trade") or 0.0)

    oos_degradation = _pct_degradation(is_avg_return, oos_avg_return)
    holdout_degradation = _pct_degradation(is_avg_return, holdout_avg_return)

    stability_flags = {
        "oos_positive_average_return": bool(oos_avg_return > 0),
        "holdout_positive_average_return": bool(holdout_avg_return > 0),
        "oos_sample_adequacy_not_high": str(out_of_sample.get("sample_adequacy", {}).get("risk")) != "high",
        "holdout_sample_adequacy_not_high": str(final_holdout.get("sample_adequacy", {}).get("risk")) != "high",
    }

    return {
        "oos_degradation_vs_in_sample_pct": oos_degradation,
        "holdout_degradation_vs_in_sample_pct": holdout_degradation,
        "stability_flags": stability_flags,
    }


def _determine_layer3_mode(stack_results: List[Dict[str, object]]) -> Dict[str, object]:
    baseline = next((item for item in stack_results if item["stack_id"] == "rebuild_core_without_layer3"), None)
    with_layer3 = next(
        (item for item in stack_results if item["stack_id"] == "rebuild_core_with_layer3_optional_toggle"),
        None,
    )
    if baseline is None or with_layer3 is None:
        return {
            "without_layer3_more_stable": None,
            "layer_3_recommendation": "insufficient_comparison",
            "reason": "One of the official stack rows is missing.",
        }

    baseline_oos = baseline["window_lookup"]["out_of_sample"]
    baseline_holdout = baseline["window_lookup"]["final_holdout"]
    layer3_oos = with_layer3["window_lookup"]["out_of_sample"]
    layer3_holdout = with_layer3["window_lookup"]["final_holdout"]

    baseline_score = (
        float(baseline_oos["average_return_per_trade"])
        + float(baseline_holdout["average_return_per_trade"])
        + float(baseline_oos["profit_factor"] or 0.0)
        + float(baseline_holdout["profit_factor"] or 0.0)
    )
    layer3_score = (
        float(layer3_oos["average_return_per_trade"])
        + float(layer3_holdout["average_return_per_trade"])
        + float(layer3_oos["profit_factor"] or 0.0)
        + float(layer3_holdout["profit_factor"] or 0.0)
    )

    baseline_deg = baseline["stability_assessment"]["oos_degradation_vs_in_sample_pct"]
    layer3_deg = with_layer3["stability_assessment"]["oos_degradation_vs_in_sample_pct"]
    baseline_deg_score = abs(float(baseline_deg)) if baseline_deg is not None else 10_000.0
    layer3_deg_score = abs(float(layer3_deg)) if layer3_deg is not None else 10_000.0

    without_layer3_more_stable = bool(
        (baseline_score > layer3_score)
        or (baseline_score == layer3_score and baseline_deg_score <= layer3_deg_score)
    )
    recommendation = "optional_on_only" if without_layer3_more_stable else "keep_optional_and_contextual"
    reason = (
        "Stack tanpa Layer 3 lebih stabil pada OOS/holdout, sehingga Layer 3 tetap mode opsional dan tidak menjadi default."
        if without_layer3_more_stable
        else "Layer 3 tidak mengalahkan baseline secara cukup tegas, sehingga tetap diperlakukan sebagai toggle opsional."
    )
    return {
        "without_layer3_more_stable": without_layer3_more_stable,
        "layer_3_recommendation": recommendation,
        "reason": reason,
    }


def _determine_candidate_track(stack_results: List[Dict[str, object]]) -> Dict[str, object]:
    baseline = next((item for item in stack_results if item["stack_id"] == "rebuild_core_without_layer3"), None)
    if baseline is None:
        return {
            "decision": "not_ready",
            "reason": "Baseline stack summary is missing.",
            "failed_checks": ["baseline_stack_missing"],
        }

    oos = baseline["window_lookup"]["out_of_sample"]
    holdout = baseline["window_lookup"]["final_holdout"]
    degradation = baseline["stability_assessment"]["oos_degradation_vs_in_sample_pct"]

    failed_checks: List[str] = []
    if int(oos["total_trades"]) < 200 or int(holdout["total_trades"]) < 200:
        failed_checks.append("insufficient_oos_or_holdout_trades")
    if float(oos["win_rate"]) <= 45.0 or float(holdout["win_rate"]) <= 45.0:
        failed_checks.append("win_rate_below_minimum")
    if (oos["profit_factor"] is None or float(oos["profit_factor"]) <= 1.5) or (
        holdout["profit_factor"] is None or float(holdout["profit_factor"]) <= 1.5
    ):
        failed_checks.append("profit_factor_below_minimum")
    if float(oos["max_drawdown_pct"]) >= 20.0 or float(holdout["max_drawdown_pct"]) >= 20.0:
        failed_checks.append("max_drawdown_above_minimum_gate")
    if degradation is None or float(degradation) >= 30.0:
        failed_checks.append("oos_degradation_above_minimum_gate")
    failed_checks.append("sharpe_not_evaluated_in_first_walk_forward_pass")

    ready = len(failed_checks) == 0
    reason = (
        "Stack memenuhi gate minimum walk-forward yang tersedia."
        if ready
        else "Stack rebuild belum cukup kuat untuk dibuka ke paper-trading candidate track pada first walk-forward pass."
    )
    return {
        "decision": "ready_for_candidate_track" if ready else "not_ready",
        "reason": reason,
        "failed_checks": failed_checks,
    }


def run_walk_forward_validation(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    output_dir: Path,
    allow_overlap: bool = False,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    baseline_payload, baseline_warnings, baseline_source = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    prepared_frame = _build_entry_exit_frame(
        stock_indicator_master_file,
        ihsg_indicator_master_file,
        baseline_payload=baseline_payload,
        metadata_lookup=metadata_lookup,
    )
    prepared_frame["date"] = pd.to_datetime(prepared_frame["date"])

    stacks = _build_stack_registry()
    windows = _build_window_registry()
    stack_results: List[Dict[str, object]] = []

    for stack in stacks:
        window_results = [
            _evaluate_window(
                prepared_frame,
                stack,
                window,
                allow_overlap=allow_overlap,
            )
            for window in windows
        ]
        window_lookup = {item["window_id"]: item for item in window_results}
        stability = _assess_stack_stability(window_lookup)
        stack_results.append(
            {
                "stack_id": stack.stack_id,
                "stack_label": stack.label,
                "layer_1_policy": "IHSG EMA50 > EMA200 with explicit previous-trading-day alignment",
                "layer_2_policy": "return_20d > 0 AND close > ema50 without liquidity gate",
                "layer_3_policy": "RSI14 >= 50 AND RSI14 <= 70" if stack.layer_3_active else "inactive",
                "layer_4_policy": {
                    "risk_per_trade_pct": stack.risk_per_trade_pct,
                    "max_position_pct": stack.max_position_pct,
                },
                "layer_5_policy": {
                    "exit_policy": "atr_trailing_stop",
                    "atr_multiplier": 2.5,
                    "time_stop_days": 15,
                },
                "window_results": window_results,
                "window_lookup": window_lookup,
                "stability_assessment": stability,
            }
        )

    layer3_decision = _determine_layer3_mode(stack_results)
    candidate_track = _determine_candidate_track(stack_results)

    summary_payload = {
        "phase": "walk_forward_validation",
        "status": "completed",
        "generated_at": _now_iso(),
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
            "layer_3_closeout": "output/phase_3_layer_3_closeout.json",
            "layer_5_summary": "output/phase_5_atr_trailing_stop_summary.json",
            "layer_4_summary": "output/phase_4_position_sizing_summary.json",
            "project_roadmap_status": "output/project_roadmap_status.txt",
        },
        "walk_forward_windows": [
            {
                "window_id": window.window_id,
                "label": window.label,
                "start_date": window.start_date,
                "end_date": window.end_date,
                "role": window.role,
            }
            for window in windows
        ],
        "stack_results": stack_results,
        "official_decision": {
            "layer_3_mode_decision": layer3_decision,
            "paper_trading_candidate_track": candidate_track,
            "forbidden_next_step": "Do not open paper trading yet; do not redesign layers before reading this walk-forward result.",
        },
        "warnings": [*baseline_warnings, *metadata_warnings],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / SUMMARY_OUTPUT
    report_path = output_dir / REPORT_OUTPUT
    summary_path.write_text(json.dumps(_sanitize_for_json(summary_payload), indent=2), encoding="utf-8")

    report_lines = [
        "Walk-Forward Validation First Pass",
        "==================================",
        "",
        "Official split:",
        "- In-sample: 2019-01-01 to 2021-12-31",
        "- Out-of-sample: 2022-01-01 to 2023-12-31",
        "- Final holdout: 2024-01-01 to 2025-12-31",
        "",
    ]

    for stack_result in stack_results:
        report_lines.append(f"Stack: {stack_result['stack_id']}")
        report_lines.append(f"- label = {stack_result['stack_label']}")
        for window_result in stack_result["window_results"]:
            report_lines.append(
                f"- {window_result['window_id']}: trades={window_result['total_trades']}, "
                f"win_rate={window_result['win_rate']}, avg_return={window_result['average_return_per_trade']}, "
                f"max_drawdown={window_result['max_drawdown_pct']}, profit_factor={window_result['profit_factor']}, "
                f"sample={window_result['sample_adequacy']['risk']}"
            )
        report_lines.append(
            f"- oos_degradation_vs_in_sample_pct = "
            f"{stack_result['stability_assessment']['oos_degradation_vs_in_sample_pct']}"
        )
        report_lines.append(
            f"- holdout_degradation_vs_in_sample_pct = "
            f"{stack_result['stability_assessment']['holdout_degradation_vs_in_sample_pct']}"
        )
        report_lines.append("")

    report_lines.extend(
        [
            "Decision:",
            f"- without_layer3_more_stable = {layer3_decision['without_layer3_more_stable']}",
            f"- layer_3_recommendation = {layer3_decision['layer_3_recommendation']}",
            f"- layer_3_reason = {layer3_decision['reason']}",
            f"- paper_trading_candidate_track = {candidate_track['decision']}",
            f"- candidate_track_reason = {candidate_track['reason']}",
            f"- failed_checks = {', '.join(candidate_track['failed_checks']) if candidate_track['failed_checks'] else 'none'}",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "summary_path": summary_path,
        "report_path": report_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the first walk-forward validation for the rebuild stack.")
    parser.add_argument(
        "--stock-indicator-master-file",
        default="data/indicator_master/stock_indicator_master.csv",
        help="Stock indicator master CSV for the rebuild universe.",
    )
    parser.add_argument(
        "--ihsg-indicator-master-file",
        default="data/indicator_master/IHSG_indicator_master.csv",
        help="IHSG indicator master CSV for Layer 1 regime alignment.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for output artifacts.")
    parser.add_argument("--allow-overlap", action="store_true", help="Allow overlapping trades.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Frozen Phase A baseline config path.",
    )
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional metadata file for baseline runtime overrides.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    run_walk_forward_validation(
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        output_dir=Path(args.output_dir),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
