"""Narrow confirmation for the Layer 1 candidate under multiple IHSG alignment policies."""

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

from quant.phase_a import backtest_signal_frame  # noqa: E402
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.run_phase_1_1_market_regime_filter_refinement import (  # noqa: E402
    _build_base_signal_frame,
    _load_ihsg_indicator_master,
    _load_stock_indicator_master,
)


POLICY_SUMMARY_COLUMNS = [
    "policy_id",
    "policy_label",
    "policy_description",
    "bullish_day_pct",
    "pre_filter_signals",
    "post_filter_signals",
    "skipped_signals",
    "pre_filter_total_trades",
    "post_filter_total_trades",
    "trade_retention_pct_median",
    "avg_delta_win_rate",
    "avg_delta_average_return",
    "tickers_with_coverage_collapse",
    "coverage_collapse_tickers",
    "affected_missing_date_rows",
    "affected_missing_unique_dates",
    "bullish_overrides_on_missing_rows",
]

PER_TICKER_COLUMNS = [
    "policy_id",
    "policy_label",
    "ticker",
    "rows",
    "date_start",
    "date_end",
    "applied_threshold",
    "applied_strict_mode",
    "bullish_days",
    "non_bullish_days",
    "bullish_day_pct",
    "pre_filter_signals",
    "post_filter_signals",
    "skipped_signals",
    "signal_retention_pct",
    "coverage_collapsed",
    "pre_filter_total_trades",
    "post_filter_total_trades",
    "trade_retention_pct",
    "pre_filter_win_rate",
    "post_filter_win_rate",
    "delta_win_rate",
    "pre_filter_average_return",
    "post_filter_average_return",
    "delta_average_return",
    "pre_filter_max_drawdown",
    "post_filter_max_drawdown",
    "delta_max_drawdown",
]


@dataclass(frozen=True)
class AlignmentPolicy:
    policy_id: str
    label: str
    description: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_policy_registry() -> List[AlignmentPolicy]:
    return [
        AlignmentPolicy(
            policy_id="current_non_bullish_on_missing",
            label="Current missing => non-bullish",
            description="Exact same-date IHSG join; missing IHSG dates are forced to non-bullish.",
        ),
        AlignmentPolicy(
            policy_id="carry_forward_previous_available_regime",
            label="Carry-forward previous available regime",
            description="Exact same-date join first, then missing stock dates inherit the latest available IHSG regime state.",
        ),
        AlignmentPolicy(
            policy_id="explicit_previous_trading_day_alignment",
            label="Explicit previous-trading-day alignment",
            description="Each stock date is aligned to the most recent IHSG trading day on or before that date.",
        ),
    ]


def _compute_candidate_regime(ihsg_frame: pd.DataFrame) -> pd.DataFrame:
    working = ihsg_frame.sort_values("date").reset_index(drop=True).copy()
    working["candidate_regime_bullish"] = working["ihsg_ema50"].gt(working["ihsg_ema200"]).fillna(False)
    return working


def _build_direct_alignment(stock_dates: pd.Series, ihsg_frame: pd.DataFrame) -> pd.DataFrame:
    unique_dates = pd.DataFrame({"date": pd.Series(stock_dates.drop_duplicates().sort_values().tolist())})
    direct = unique_dates.merge(
        ihsg_frame[
            [
                "date",
                "ihsg_adj_close",
                "ihsg_ema50",
                "ihsg_ema200",
                "candidate_regime_bullish",
            ]
        ],
        on="date",
        how="left",
    )
    direct["exact_match_available"] = direct["candidate_regime_bullish"].notna()
    return direct


def _apply_alignment_policy(
    stock_dates: pd.Series,
    ihsg_frame: pd.DataFrame,
    policy: AlignmentPolicy,
) -> pd.DataFrame:
    direct = _build_direct_alignment(stock_dates, ihsg_frame)
    output = direct.copy()

    if policy.policy_id == "current_non_bullish_on_missing":
        output["aligned_ihsg_date"] = output["date"].where(output["exact_match_available"])
        output["market_regime_bullish"] = (
            pd.Series(output["candidate_regime_bullish"], dtype="boolean").fillna(False).astype(bool)
        )
    elif policy.policy_id == "carry_forward_previous_available_regime":
        output["aligned_ihsg_date"] = output["date"].where(output["exact_match_available"]).ffill()
        carried = pd.Series(output["candidate_regime_bullish"], dtype="boolean").ffill()
        output["market_regime_bullish"] = carried.fillna(False).astype(bool)
    elif policy.policy_id == "explicit_previous_trading_day_alignment":
        aligned = pd.merge_asof(
            direct[["date"]].sort_values("date"),
            ihsg_frame[
                [
                    "date",
                    "ihsg_adj_close",
                    "ihsg_ema50",
                    "ihsg_ema200",
                    "candidate_regime_bullish",
                ]
            ]
            .rename(columns={"date": "aligned_ihsg_date"})
            .sort_values("aligned_ihsg_date"),
            left_on="date",
            right_on="aligned_ihsg_date",
            direction="backward",
        )
        output = direct.drop(
            columns=[
                "ihsg_adj_close",
                "ihsg_ema50",
                "ihsg_ema200",
                "candidate_regime_bullish",
            ]
        ).merge(aligned, on="date", how="left")
        output["market_regime_bullish"] = (
            pd.Series(output["candidate_regime_bullish"], dtype="boolean").fillna(False).astype(bool)
        )
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported alignment policy: {policy.policy_id}")

    output["missing_direct_ihsg_date"] = ~output["exact_match_available"]
    output["aligned_on_missing"] = output["missing_direct_ihsg_date"] & output["aligned_ihsg_date"].notna()
    output["bullish_override_on_missing"] = (
        output["missing_direct_ihsg_date"] & output["market_regime_bullish"]
    ).fillna(False)
    return output[
        [
            "date",
            "aligned_ihsg_date",
            "market_regime_bullish",
            "missing_direct_ihsg_date",
            "aligned_on_missing",
            "bullish_override_on_missing",
        ]
    ]


def _evaluate_ticker_policy(
    ticker: str,
    frame: pd.DataFrame,
    *,
    hold_period: int,
    allow_overlap: bool,
    threshold: float,
    strict_mode: bool,
) -> Dict[str, object]:
    signal_frame = _build_base_signal_frame(frame, threshold=threshold, strict_mode=strict_mode)
    signal_frame["phase_1_signal_candidate"] = (
        signal_frame["phase_1_signal_base"] & signal_frame["market_regime_bullish"]
    ).fillna(False)
    signal_frame["market_regime_entry_skipped"] = (
        signal_frame["phase_1_signal_base"] & ~signal_frame["market_regime_bullish"]
    ).fillna(False)

    pre_signal_count = int(signal_frame["phase_1_signal_base"].fillna(False).astype(bool).sum())
    post_signal_count = int(signal_frame["phase_1_signal_candidate"].fillna(False).astype(bool).sum())
    skipped_signal_count = int(signal_frame["market_regime_entry_skipped"].fillna(False).astype(bool).sum())

    pre_result = backtest_signal_frame(
        signal_frame,
        signal_column="phase_1_signal_base",
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )
    post_result = backtest_signal_frame(
        signal_frame,
        signal_column="phase_1_signal_candidate",
        hold_period=hold_period,
        allow_overlap=allow_overlap,
    )

    bullish_days = int(signal_frame["market_regime_bullish"].astype(bool).sum())
    non_bullish_days = int(len(signal_frame) - bullish_days)
    signal_retention_pct = round((post_signal_count / pre_signal_count) * 100.0, 4) if pre_signal_count else 0.0
    trade_retention_pct = (
        round((post_result.total_trades / pre_result.total_trades) * 100.0, 4)
        if pre_result.total_trades
        else 0.0
    )

    return {
        "ticker": ticker,
        "rows": int(len(signal_frame)),
        "date_start": signal_frame["date"].iloc[0].strftime("%Y-%m-%d"),
        "date_end": signal_frame["date"].iloc[-1].strftime("%Y-%m-%d"),
        "applied_threshold": float(threshold),
        "applied_strict_mode": bool(strict_mode),
        "bullish_days": bullish_days,
        "non_bullish_days": non_bullish_days,
        "bullish_day_pct": round((bullish_days / len(signal_frame)) * 100.0, 4),
        "pre_filter_signals": pre_signal_count,
        "post_filter_signals": post_signal_count,
        "skipped_signals": skipped_signal_count,
        "signal_retention_pct": signal_retention_pct,
        "coverage_collapsed": bool(post_signal_count == 0 and pre_signal_count > 0),
        "pre_filter_total_trades": int(pre_result.total_trades),
        "post_filter_total_trades": int(post_result.total_trades),
        "trade_retention_pct": trade_retention_pct,
        "pre_filter_win_rate": float(pre_result.win_rate),
        "post_filter_win_rate": float(post_result.win_rate),
        "delta_win_rate": round(float(post_result.win_rate) - float(pre_result.win_rate), 4),
        "pre_filter_average_return": float(pre_result.average_return),
        "post_filter_average_return": float(post_result.average_return),
        "delta_average_return": round(
            float(post_result.average_return) - float(pre_result.average_return), 4
        ),
        "pre_filter_max_drawdown": float(pre_result.max_drawdown),
        "post_filter_max_drawdown": float(post_result.max_drawdown),
        "delta_max_drawdown": round(
            float(post_result.max_drawdown) - float(pre_result.max_drawdown), 4
        ),
    }


def _aggregate_policy_summary(
    per_ticker_df: pd.DataFrame,
    policy: AlignmentPolicy,
    daily_alignment: pd.DataFrame,
    aligned_stock_frame: pd.DataFrame,
) -> Dict[str, object]:
    coverage_collapse_tickers = (
        per_ticker_df.loc[per_ticker_df["coverage_collapsed"].astype(bool), "ticker"]
        .astype(str)
        .tolist()
    )
    bullish_days = int(daily_alignment["market_regime_bullish"].astype(bool).sum())
    total_days = int(len(daily_alignment))
    affected_dates = daily_alignment.loc[daily_alignment["missing_direct_ihsg_date"], "date"].nunique()

    return {
        "policy_id": policy.policy_id,
        "policy_label": policy.label,
        "policy_description": policy.description,
        "bullish_day_pct": round((bullish_days / total_days) * 100.0, 4) if total_days else 0.0,
        "pre_filter_signals": int(per_ticker_df["pre_filter_signals"].sum()),
        "post_filter_signals": int(per_ticker_df["post_filter_signals"].sum()),
        "skipped_signals": int(per_ticker_df["skipped_signals"].sum()),
        "pre_filter_total_trades": int(per_ticker_df["pre_filter_total_trades"].sum()),
        "post_filter_total_trades": int(per_ticker_df["post_filter_total_trades"].sum()),
        "trade_retention_pct_median": round(
            float(per_ticker_df["trade_retention_pct"].median()) if not per_ticker_df.empty else 0.0,
            4,
        ),
        "avg_delta_win_rate": round(
            float(per_ticker_df["delta_win_rate"].mean()) if not per_ticker_df.empty else 0.0,
            4,
        ),
        "avg_delta_average_return": round(
            float(per_ticker_df["delta_average_return"].mean()) if not per_ticker_df.empty else 0.0,
            4,
        ),
        "tickers_with_coverage_collapse": int(len(coverage_collapse_tickers)),
        "coverage_collapse_tickers": coverage_collapse_tickers,
        "affected_missing_date_rows": int(aligned_stock_frame["missing_direct_ihsg_date"].astype(bool).sum()),
        "affected_missing_unique_dates": int(affected_dates),
        "bullish_overrides_on_missing_rows": int(
            aligned_stock_frame["bullish_override_on_missing"].astype(bool).sum()
        ),
    }


def _build_stability_diagnostics(policy_df: pd.DataFrame) -> Dict[str, object]:
    if policy_df.empty:
        return {"status": "no_data"}

    sorted_df = policy_df.sort_values("policy_id").reset_index(drop=True)
    return {
        "avg_delta_win_rate_range": round(
            float(sorted_df["avg_delta_win_rate"].max() - sorted_df["avg_delta_win_rate"].min()), 4
        ),
        "avg_delta_average_return_range": round(
            float(
                sorted_df["avg_delta_average_return"].max() - sorted_df["avg_delta_average_return"].min()
            ),
            4,
        ),
        "post_filter_total_trades_range": int(
            sorted_df["post_filter_total_trades"].max() - sorted_df["post_filter_total_trades"].min()
        ),
    }


def _pick_best_policy(policy_df: pd.DataFrame) -> Dict[str, object]:
    if policy_df.empty:
        return {"status": "no_candidate", "selected_policy_id": None}

    label_priority = {
        "explicit_previous_trading_day_alignment": 0,
        "carry_forward_previous_available_regime": 1,
        "current_non_bullish_on_missing": 2,
    }
    eligible = policy_df[
        (policy_df["tickers_with_coverage_collapse"] == 0)
    ].copy()
    eligible["priority"] = eligible["policy_id"].map(label_priority).fillna(99)
    eligible = eligible.sort_values(
        by=[
            "avg_delta_average_return",
            "avg_delta_win_rate",
            "trade_retention_pct_median",
            "post_filter_total_trades",
            "priority",
        ],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)
    best = eligible.iloc[0]
    return {
        "status": "selected",
        "selected_policy_id": str(best["policy_id"]),
        "selected_policy_label": str(best["policy_label"]),
        "reason": (
            "Selected the alignment policy with healthy coverage and the strongest quality profile; "
            "ties break toward explicit previous-trading-day semantics."
        ),
    }


def _freeze_decision(policy_df: pd.DataFrame, best_policy: Dict[str, object]) -> Dict[str, object]:
    if policy_df.empty or not best_policy.get("selected_policy_id"):
        return {
            "freeze_layer_1": False,
            "reason": "No usable policy result was available.",
        }

    selected = policy_df.loc[policy_df["policy_id"] == best_policy["selected_policy_id"]].iloc[0]
    reasonable = policy_df[
        policy_df["policy_id"].isin(
            [
                "carry_forward_previous_available_regime",
                "explicit_previous_trading_day_alignment",
            ]
        )
    ].copy()
    stable = (
        reasonable["avg_delta_average_return"].nunique() == 1
        and reasonable["avg_delta_win_rate"].nunique() == 1
        and reasonable["post_filter_total_trades"].nunique() == 1
    )
    can_freeze = bool(
        stable
        and int(selected["tickers_with_coverage_collapse"]) == 0
        and float(selected["avg_delta_average_return"]) >= 0.0
        and float(selected["avg_delta_win_rate"]) >= -0.25
    )

    if can_freeze:
        reason = (
            "Reasonable alignment policies are operationally identical on this dataset, coverage stays healthy, "
            "and the selected policy keeps average return delta positive while win-rate delta is close to flat."
        )
    else:
        reason = (
            "Candidate remains too sensitive or still too weak on the quality deltas, so Layer 1 should not be frozen yet."
        )
    return {
        "freeze_layer_1": can_freeze,
        "reason": reason,
        "stable_reasonable_policy_cluster": stable,
    }


def run_phase_1_2_market_regime_alignment_confirmation(
    *,
    stock_indicator_master_file: Path,
    ihsg_indicator_master_file: Path,
    output_dir: Path,
    hold_period: int = 5,
    allow_overlap: bool = False,
    baseline_config: Optional[Path] = None,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    stock_frame = _load_stock_indicator_master(stock_indicator_master_file)
    ihsg_frame = _compute_candidate_regime(_load_ihsg_indicator_master(ihsg_indicator_master_file))

    baseline_payload, baseline_warnings, baseline_source = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    policies = _build_policy_registry()

    per_ticker_rows: List[Dict[str, object]] = []
    policy_rows: List[Dict[str, object]] = []
    policy_alignment_diagnostics: List[Dict[str, object]] = []

    unique_stock_dates = stock_frame["date"].drop_duplicates().sort_values().reset_index(drop=True)

    for policy in policies:
        daily_alignment = _apply_alignment_policy(unique_stock_dates, ihsg_frame, policy=policy)
        policy_frame = stock_frame.merge(
            daily_alignment,
            on="date",
            how="left",
        )

        ticker_rows: List[Dict[str, object]] = []
        for ticker, group in policy_frame.groupby("ticker"):
            runtime = resolve_phase_a_runtime_settings(
                ticker=ticker,
                baseline_config=baseline_payload,
                metadata_lookup=metadata_lookup,
            )
            ticker_row = _evaluate_ticker_policy(
                ticker=ticker,
                frame=group.copy(),
                hold_period=hold_period,
                allow_overlap=allow_overlap,
                threshold=float(runtime["threshold"]),
                strict_mode=bool(runtime["strict_mode"]),
            )
            ticker_rows.append(
                {
                    "policy_id": policy.policy_id,
                    "policy_label": policy.label,
                    **ticker_row,
                }
            )

        per_ticker_df = pd.DataFrame(ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
        per_ticker_rows.extend(per_ticker_df.to_dict(orient="records"))
        policy_rows.append(_aggregate_policy_summary(per_ticker_df, policy, daily_alignment, policy_frame))
        policy_alignment_diagnostics.append(
            {
                "policy_id": policy.policy_id,
                "policy_label": policy.label,
                "missing_direct_rows": int(daily_alignment["missing_direct_ihsg_date"].astype(bool).sum()),
                "missing_direct_unique_dates": int(
                    daily_alignment.loc[daily_alignment["missing_direct_ihsg_date"], "date"].nunique()
                ),
                "bullish_override_on_missing_dates": int(
                    daily_alignment["bullish_override_on_missing"].astype(bool).sum()
                ),
                "sample_missing_dates": daily_alignment.loc[
                    daily_alignment["missing_direct_ihsg_date"],
                    ["date", "aligned_ihsg_date", "market_regime_bullish"],
                ]
                .head(10)
                .assign(
                    date=lambda df: df["date"].dt.strftime("%Y-%m-%d"),
                    aligned_ihsg_date=lambda df: df["aligned_ihsg_date"].dt.strftime("%Y-%m-%d"),
                )
                .to_dict(orient="records"),
            }
        )

    policy_df = pd.DataFrame(policy_rows).reindex(columns=POLICY_SUMMARY_COLUMNS)
    per_ticker_df = pd.DataFrame(per_ticker_rows).reindex(columns=PER_TICKER_COLUMNS)
    best_policy = _pick_best_policy(policy_df)
    freeze_decision = _freeze_decision(policy_df, best_policy)
    stability = _build_stability_diagnostics(policy_df)

    output_dir.mkdir(parents=True, exist_ok=True)
    per_ticker_path = output_dir / "phase_1_2_market_regime_alignment_confirmation_per_ticker.csv"
    per_policy_path = output_dir / "phase_1_2_market_regime_alignment_confirmation_per_policy.csv"
    summary_path = output_dir / "phase_1_2_market_regime_alignment_confirmation_summary.json"
    report_path = output_dir / "phase_1_2_market_regime_alignment_confirmation_report.txt"

    per_ticker_df.to_csv(per_ticker_path, index=False)
    policy_df.to_csv(per_policy_path, index=False)

    summary_payload = {
        "phase": "phase_1_2_market_regime_alignment_confirmation",
        "status": "completed",
        "generated_at": _now_iso(),
        "candidate_definition": "ihsg_ema50 > ihsg_ema200",
        "source_files": {
            "stock_indicator_master_file": str(stock_indicator_master_file),
            "ihsg_indicator_master_file": str(ihsg_indicator_master_file),
            "baseline_config": str(baseline_source) if baseline_source else None,
            "metadata_file": str(metadata_file) if metadata_file is not None else None,
        },
        "policies_tested": [
            {
                "policy_id": policy.policy_id,
                "policy_label": policy.label,
                "policy_description": policy.description,
            }
            for policy in policies
        ],
        "policy_results": policy_df.to_dict(orient="records"),
        "alignment_diagnostics": policy_alignment_diagnostics,
        "stability_diagnostics": stability,
        "best_policy_decision": best_policy,
        "freeze_decision": freeze_decision,
        "warnings": [*baseline_warnings, *metadata_warnings],
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    report_lines = [
        "Phase 1.2 - Narrow Confirmation for Layer 1 Candidate",
        "=====================================================",
        "",
        "Candidate:",
        "- ihsg_ema50 > ihsg_ema200",
        "",
        "Policy results:",
    ]
    for row in policy_df.to_dict(orient="records"):
        report_lines.extend(
            [
                f"- {row['policy_id']}: {row['policy_description']}",
                f"  bullish_day_pct={row['bullish_day_pct']}, pre_filter_signals={row['pre_filter_signals']}, post_filter_signals={row['post_filter_signals']}, skipped_signals={row['skipped_signals']}",
                f"  total_trades={row['post_filter_total_trades']}, median_trade_retention={row['trade_retention_pct_median']}, avg_delta_win_rate={row['avg_delta_win_rate']}, avg_delta_average_return={row['avg_delta_average_return']}",
                f"  coverage_collapse={row['tickers_with_coverage_collapse']}, affected_missing_date_rows={row['affected_missing_date_rows']}, bullish_overrides_on_missing_rows={row['bullish_overrides_on_missing_rows']}",
            ]
        )

    report_lines.extend(
        [
            "",
            "Decision:",
            f"- best_policy = {best_policy.get('selected_policy_id')}",
            f"- freeze_layer_1 = {freeze_decision['freeze_layer_1']}",
            f"- reason = {freeze_decision['reason']}",
        ]
    )
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "per_ticker_path": per_ticker_path,
        "per_policy_path": per_policy_path,
        "summary_path": summary_path,
        "report_path": report_path,
        "summary": summary_payload,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 1.2 Layer 1 alignment confirmation.")
    parser.add_argument(
        "--stock-indicator-master-file",
        default="data/indicator_master/stock_indicator_master.csv",
        help="Stock indicator master CSV for the rebuild path.",
    )
    parser.add_argument(
        "--ihsg-indicator-master-file",
        default="data/indicator_master/IHSG_indicator_master.csv",
        help="IHSG indicator master CSV with EMA50 and EMA200.",
    )
    parser.add_argument("--output-dir", default="output", help="Directory for Phase 1.2 artifacts.")
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
    run_phase_1_2_market_regime_alignment_confirmation(
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
