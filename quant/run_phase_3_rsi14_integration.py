"""Evaluate Layer 3 RSI14 integration on top of frozen Layer 1 and Layer 2 alternative."""

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
from quant.run_phase_2_1_relative_strength_redesign import _prepare_layer1_signal_frame  # noqa: E402
from quant.run_phase_2_alt_non_cross_sectional_filter import (  # noqa: E402
    _compute_alt_features,
)
from quant.run_phase_2_relative_strength_stock_selection import (  # noqa: E402
    PER_TICKER_COLUMNS,
    _classify_sample_adequacy_risk,
    _evaluate_variant_ticker,
)


VARIANT_SUMMARY_COLUMNS = [
    "variant_id",
    "variant_label",
    "layer_2_active",
    "layer_3_active",
    "rsi_gate_min",
    "rsi_gate_max",
    "active_ticker_count_median",
    "active_ticker_count_min",
    "active_ticker_count_max",
    "active_ticker_count_mean",
    "active_single_ticker_day_pct",
    "total_signals",
    "total_trades",
    "median_trade_retention",
    "avg_delta_win_rate",
    "avg_delta_average_return",
    "tickers_with_coverage_collapse",
    "coverage_collapse_tickers",
    "sample_adequacy_risk",
    "sample_adequacy_reason",
]


@dataclass(frozen=True)
class IntegrationVariant:
    variant_id: str
    label: str
    layer_2_active: bool
    layer_3_active: bool
    rsi_gate_min: Optional[float]
    rsi_gate_max: Optional[float]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_variant_registry() -> List[IntegrationVariant]:
    return [
        IntegrationVariant(
            variant_id="layer1_only",
            label="Layer 1 only",
            layer_2_active=False,
            layer_3_active=False,
            rsi_gate_min=None,
            rsi_gate_max=None,
        ),
        IntegrationVariant(
            variant_id="layer1_plus_layer2_alt",
            label="Layer 1 + Layer 2 alternative",
            layer_2_active=True,
            layer_3_active=False,
            rsi_gate_min=None,
            rsi_gate_max=None,
        ),
        IntegrationVariant(
            variant_id="layer1_plus_layer2_alt_plus_layer3_rsi_50_70",
            label="Layer 1 + Layer 2 alternative + Layer 3 RSI 50-70",
            layer_2_active=True,
            layer_3_active=True,
            rsi_gate_min=50.0,
            rsi_gate_max=70.0,
        ),
    ]


def _compute_features(
    frame: pd.DataFrame,
    *,
    momentum_floor_on_return_20d: float = 0.0,
    confirmation_days: int = 0,
    short_term_ema_slope_gate: str = "none",
) -> pd.DataFrame:
    working = _compute_alt_features(
        frame,
        momentum_floor_on_return_20d=float(momentum_floor_on_return_20d),
        short_term_ema_slope_gate=str(short_term_ema_slope_gate),
    )
    minimum_required_streak = max(int(confirmation_days), 0) + 1
    slope_gate_mode = str(short_term_ema_slope_gate)
    if slope_gate_mode == "none":
        slope_gate_pass = True
    elif slope_gate_mode == "ema20_today_gt_ema20_prev_day":
        slope_gate_pass = working["alt_short_term_ema_slope_up"].astype(bool)
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported short-term EMA slope gate: {short_term_ema_slope_gate}")

    base_layer2_condition = (
        working["market_regime_bullish"].astype(bool)
        & working["alt_data_ready"].astype(bool)
        & working["alt_momentum_positive"].astype(bool)
        & working["alt_close_above_ema50"].astype(bool)
        & slope_gate_pass
    )
    working["layer2_base_entry_condition"] = base_layer2_condition
    working["layer2_short_term_ema_slope_gate"] = slope_gate_mode
    working["layer2_confirmation_streak"] = (
        working.groupby("ticker")["layer2_base_entry_condition"]
        .transform(
            lambda series: series.astype(bool)
            .groupby((~series.astype(bool)).cumsum())
            .cumcount()
            .add(1)
            .where(series.astype(bool), 0)
        )
        .astype(int)
    )
    working["layer2_confirmation_days_required"] = int(max(int(confirmation_days), 0))
    working["rsi14_numeric"] = pd.to_numeric(working["rsi14"], errors="coerce")
    working["layer2_alt_active"] = (
        working["layer2_base_entry_condition"].astype(bool)
        & working["layer2_confirmation_streak"].ge(minimum_required_streak)
    )
    working["layer3_rsi_50_70_active"] = (
        working["rsi14_numeric"].notna()
        & working["rsi14_numeric"].ge(50.0)
        & working["rsi14_numeric"].le(70.0)
    )
    working["available_ticker_count"] = working.groupby("date")["ticker"].transform("count").astype(int)
    return working


def _apply_variant(frame: pd.DataFrame, variant: IntegrationVariant) -> pd.DataFrame:
    working = frame.sort_values(["date", "ticker"]).reset_index(drop=True).copy()
    if not variant.layer_2_active:
        working["active_selected"] = working["market_regime_bullish"].astype(bool)
    elif not variant.layer_3_active:
        working["active_selected"] = working["layer2_alt_active"].astype(bool)
    else:
        working["active_selected"] = (
            working["layer2_alt_active"].astype(bool)
            & working["layer3_rsi_50_70_active"].astype(bool)
        )

    working["rankable_ticker_count"] = (
        working.groupby("date")["active_selected"].transform("sum").fillna(0).astype(int)
    )
    working["target_selected_count"] = working["rankable_ticker_count"]
    working["phase_2_signal"] = (working["phase_1_signal_layer1"] & working["active_selected"]).fillna(False)
    working["phase_2_entry_skipped"] = (
        working["phase_1_signal_layer1"] & ~working["active_selected"]
    ).fillna(False)
    return working


def _summarize_variant(frame: pd.DataFrame, per_ticker_df: pd.DataFrame, variant: IntegrationVariant) -> Dict[str, object]:
    active_by_date = (
        frame.groupby("date")
        .agg(
            active_ticker_count=("active_selected", "sum"),
            available_ticker_count=("available_ticker_count", "max"),
            target_selected_count=("target_selected_count", "max"),
        )
        .reset_index()
    )
    collapse_tickers = (
        per_ticker_df.loc[per_ticker_df["coverage_collapsed"].astype(bool), "ticker"]
        .astype(str)
        .tolist()
    )
    summary = {
        "variant_id": variant.variant_id,
        "variant_label": variant.label,
        "layer_2_active": bool(variant.layer_2_active),
        "layer_3_active": bool(variant.layer_3_active),
        "rsi_gate_min": variant.rsi_gate_min,
        "rsi_gate_max": variant.rsi_gate_max,
        "active_ticker_count_median": round(float(active_by_date["active_ticker_count"].median()), 4),
        "active_ticker_count_min": int(active_by_date["active_ticker_count"].min()),
        "active_ticker_count_max": int(active_by_date["active_ticker_count"].max()),
        "active_ticker_count_mean": round(float(active_by_date["active_ticker_count"].mean()), 4),
        "active_single_ticker_day_pct": round(
            float(active_by_date["active_ticker_count"].eq(1).mean() * 100.0),
            4,
        ),
        "total_signals": int(per_ticker_df["variant_signals"].sum()),
        "total_trades": int(per_ticker_df["variant_total_trades"].sum()),
        "median_trade_retention": round(float(per_ticker_df["trade_retention_pct"].median()), 4),
        "avg_delta_win_rate": round(float(per_ticker_df["delta_win_rate"].mean()), 4),
        "avg_delta_average_return": round(float(per_ticker_df["delta_average_return"].mean()), 4),
        "tickers_with_coverage_collapse": int(len(collapse_tickers)),
        "coverage_collapse_tickers": collapse_tickers,
    }
    risk, reason = _classify_sample_adequacy_risk(
        summary,
        universe_max=int(active_by_date["available_ticker_count"].max()),
    )
    summary["sample_adequacy_risk"] = risk
    summary["sample_adequacy_reason"] = reason
    return summary


def _layer3_integration_decision(variant_df: pd.DataFrame) -> Dict[str, object]:
    layer2 = variant_df.loc[variant_df["variant_id"] == "layer1_plus_layer2_alt"]
    layer3 = variant_df.loc[variant_df["variant_id"] == "layer1_plus_layer2_alt_plus_layer3_rsi_50_70"]
    if layer2.empty or layer3.empty:
        return {"layer_3_usable_as_integration_layer": False, "reason": "Layer 2 or Layer 3 comparison row is missing."}

    layer2_row = layer2.iloc[0]
    layer3_row = layer3.iloc[0]
    usable = bool(
        int(layer3_row["tickers_with_coverage_collapse"]) == 0
        and str(layer3_row["sample_adequacy_risk"]) != "high"
        and (
            float(layer3_row["avg_delta_average_return"]) > float(layer2_row["avg_delta_average_return"])
            or float(layer3_row["avg_delta_win_rate"]) > float(layer2_row["avg_delta_win_rate"])
        )
    )
    reason = (
        "Layer 3 RSI14 50-70 improves at least one quality metric on top of Layer 2 alternative without collapsing coverage."
        if usable
        else "Layer 3 RSI14 50-70 does not improve quality enough on top of Layer 2 alternative or harms coverage/retention too much."
    )
    return {"layer_3_usable_as_integration_layer": usable, "reason": reason}


def run_phase_3_rsi14_integration(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    output_dir: Path,
    hold_period: int = 5,
    allow_overlap: bool = False,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    baseline_payload, baseline_warnings, baseline_source = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    prepared_frame = _prepare_layer1_signal_frame(
        stock_indicator_master_file,
        ihsg_indicator_master_file,
        baseline_payload=baseline_payload,
        metadata_lookup=metadata_lookup,
    )
    prepared_frame = _compute_features(prepared_frame)
    variants = _build_variant_registry()

    per_ticker_rows: List[Dict[str, object]] = []
    variant_rows: List[Dict[str, object]] = []
    active_by_date_frames: List[pd.DataFrame] = []

    for variant in variants:
        variant_frame = _apply_variant(prepared_frame, variant)
        variant_frame["variant_id"] = variant.variant_id
        variant_frame["variant_label"] = variant.label
        active_by_date_frames.append(variant_frame)

        ticker_rows: List[Dict[str, object]] = []
        for ticker, group in variant_frame.groupby("ticker"):
            ticker_rows.append(
                {
                    "variant_id": variant.variant_id,
                    "variant_label": variant.label,
                    **_evaluate_variant_ticker(
                        ticker,
                        group.copy(),
                        hold_period=hold_period,
                        allow_overlap=allow_overlap,
                    ),
                }
            )
        per_ticker_df = pd.DataFrame(ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
        per_ticker_rows.extend(per_ticker_df.to_dict(orient="records"))
        variant_rows.append(_summarize_variant(variant_frame, per_ticker_df, variant))

    variant_df = pd.DataFrame(variant_rows).reindex(columns=VARIANT_SUMMARY_COLUMNS)
    per_ticker_df = pd.DataFrame(per_ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
    active_by_date_df = (
        pd.concat(active_by_date_frames, ignore_index=True)
        .groupby(["variant_id", "variant_label", "date"], as_index=False)
        .agg(
            active_ticker_count=("active_selected", "sum"),
            available_ticker_count=("available_ticker_count", "max"),
            target_selected_count=("target_selected_count", "max"),
        )
        .sort_values(["variant_id", "date"])
        .reset_index(drop=True)
    )
    integration_decision = _layer3_integration_decision(variant_df)

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "phase_3_rsi14_integration_summary.json"
    report_path = output_dir / "phase_3_rsi14_integration_report.txt"
    per_ticker_path = output_dir / "phase_3_rsi14_integration_per_ticker.csv"
    active_by_date_path = output_dir / "phase_3_rsi14_integration_active_by_date.csv"

    per_ticker_df.to_csv(per_ticker_path, index=False)
    active_by_date_df.to_csv(active_by_date_path, index=False)

    summary_payload = {
        "phase": "phase_3_rsi14_integration",
        "status": "completed",
        "generated_at": _now_iso(),
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "layer_2_active_policy": "alt_filter_no_liquidity_gate",
        "layer_3_definition": "RSI14 >= 50 AND RSI14 <= 70",
        "variant_results": variant_df.to_dict(orient="records"),
        "integration_decision": integration_decision,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 3 - RSI14 Integration",
        "===========================",
        "",
        "Layer 2 active policy:",
        "- Layer1 bullish AND return_20d > 0 AND close > ema50",
        "",
        "Layer 3 rule:",
        "- RSI14 >= 50 AND RSI14 <= 70",
        "",
        "Variant results:",
    ]
    for _, row in variant_df.iterrows():
        report_lines.append(
            f"- {row['variant_id']}: signals={row['total_signals']}, trades={row['total_trades']}, "
            f"retention={row['median_trade_retention']}, delta_win_rate={row['avg_delta_win_rate']}, "
            f"delta_avg_return={row['avg_delta_average_return']}, collapse={row['tickers_with_coverage_collapse']}, "
            f"sample={row['sample_adequacy_risk']}"
        )
    report_lines.extend(
        [
            "",
            "Decision:",
            f"- layer_3_usable_as_integration_layer = {integration_decision['layer_3_usable_as_integration_layer']}",
            f"- reason = {integration_decision['reason']}",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "summary_path": summary_path,
        "report_path": report_path,
        "per_ticker_path": per_ticker_path,
        "active_by_date_path": active_by_date_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Layer 3 RSI14 integration on top of frozen Layer 2 alternative.")
    parser.add_argument(
        "--stock-indicator-master-file",
        default="data/indicator_master/stock_indicator_master.csv",
        help="Stock indicator master CSV for the frozen 50-ticker universe.",
    )
    parser.add_argument(
        "--ihsg-indicator-master-file",
        default="data/indicator_master/IHSG_indicator_master.csv",
        help="IHSG indicator master CSV with frozen Layer 1 inputs.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for output artifacts.")
    parser.add_argument("--hold-period", default=5, type=int, help="Backtest hold period.")
    parser.add_argument("--allow-overlap", action="store_true", help="Allow overlapping trades.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Frozen Phase A baseline config path.",
    )
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional metadata file for threshold overrides.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    run_phase_3_rsi14_integration(
        stock_indicator_master_file=Path(args.stock_indicator_master_file),
        ihsg_indicator_master_file=Path(args.ihsg_indicator_master_file),
        output_dir=Path(args.output_dir),
        hold_period=int(args.hold_period),
        allow_overlap=bool(args.allow_overlap),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
