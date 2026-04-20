"""Monitor baseline v2 watchlist stability over extended observation windows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional, Sequence

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_baseline import load_optional_metadata_lookup, load_phase_a_baseline  # noqa: E402
from quant.phase_a_transition_utils import dedupe, read_json_object  # noqa: E402
from quant.run_baseline_v2_candidate_validation import load_candidate_file  # noqa: E402
from quant.run_baseline_v2_watchlist_validation import (  # noqa: E402
    RESULT_COLUMNS,
    _read_watchlist_context,
    _resolve_price_files,
    _sanitize_for_json,
    _ticker_metrics_for_windows,
    _write_json,
    _write_text,
    build_report_text,
    build_results_dataframe,
    build_summary_payload,
    build_watchlist_definitions,
)


DECISION_VALUES = {
    "keep_candidate_experimental",
    "promote_for_subset",
    "reject_candidate",
}


class BaselineV2WatchlistMonitoringCliError(ValueError):
    """Friendly CLI error for watchlist monitoring."""


def determine_monitoring_decision(
    results_df: pd.DataFrame,
    candidate_payload: Dict[str, object],
) -> Dict[str, object]:
    stability_rows = []
    for subset_id, frame in results_df.groupby("subset_id", sort=False):
        frame_sorted = frame.sort_values("observation_window").reset_index(drop=True)
        stable_across_windows = bool(
            bool(frame_sorted["candidate_better_than_active"].all())
            and bool((~frame_sorted["noise_risk"]).all())
            and bool((frame_sorted["candidate_eligible_ticker_count"] >= 1).all())
        )
        trend_improving = bool(
            len(frame_sorted) >= 2
            and float(frame_sorted["delta_score_mean"].iloc[-1]) >= float(frame_sorted["delta_score_mean"].iloc[0])
        )
        promote_ready = bool(
            stable_across_windows
            and trend_improving
            and bool((frame_sorted["candidate_score_mean"] > 0).all())
            and bool((frame_sorted["candidate_total_trades"] >= frame_sorted["ticker_count"] * 5).all())
        )
        stability_rows.append(
            {
                "subset_id": subset_id,
                "subset_label": str(frame_sorted["subset_label"].iloc[0]),
                "subset_type": str(frame_sorted["subset_type"].iloc[0]),
                "tickers": str(frame_sorted["tickers"].iloc[0]),
                "stable_across_windows": stable_across_windows,
                "candidate_better_window_count": int(frame_sorted["candidate_better_than_active"].sum()),
                "window_count": int(len(frame_sorted)),
                "trend_improving": trend_improving,
                "promote_ready": promote_ready,
                "last_delta_score_mean": float(frame_sorted["delta_score_mean"].iloc[-1]),
                "last_noise_risk": bool(frame_sorted["noise_risk"].iloc[-1]),
            }
        )

    stability_df = pd.DataFrame(stability_rows).sort_values(
        by=["promote_ready", "stable_across_windows", "candidate_better_window_count", "last_delta_score_mean"],
        ascending=[False, False, False, False],
    )
    if stability_df.empty:
        raise BaselineV2WatchlistMonitoringCliError("No stability rows were produced for monitoring.")

    best_subset = dict(stability_df.iloc[0].to_dict())
    watchlist_supported = bool(results_df["candidate_better_than_active"].any())
    stable_subset_found = bool(stability_df["stable_across_windows"].any())
    can_promote_for_subset = bool(stability_df["promote_ready"].any())
    can_reject_candidate = bool(not watchlist_supported)

    if can_promote_for_subset:
        decision = "promote_for_subset"
        next_action = "promote_candidate_for_watchlist_subset_only"
    elif can_reject_candidate:
        decision = "reject_candidate"
        next_action = "reject_candidate_after_extended_watchlist_monitoring"
    else:
        decision = "keep_candidate_experimental"
        next_action = "keep_candidate_experimental_for_watchlist_subset"

    promoted_rows = stability_df.loc[stability_df["promote_ready"]].copy()
    supported_rows = stability_df.loc[stability_df["candidate_better_window_count"] >= 1].copy()
    source_rows = promoted_rows if not promoted_rows.empty else supported_rows

    recommended_tickers = dedupe(
        [
            ticker
            for tickers_blob in source_rows["tickers"].astype(str).tolist()
            for ticker in tickers_blob.split("|")
            if ticker
        ]
    )
    recommended_groups = dedupe(
        results_df.loc[
            (results_df["subset_type"] == "group")
            & (
                results_df["subset_id"].isin(source_rows["subset_id"].astype(str).tolist())
                if not source_rows.empty
                else results_df["candidate_better_than_active"]
            ),
            "subset_label",
        ].astype(str).tolist()
    )

    return {
        "decision": decision,
        "candidate_id": str(dict(candidate_payload.get("selected_candidate") or {}).get("candidate_id")),
        "still_experimental": bool(decision == "keep_candidate_experimental"),
        "watchlist_supported": bool(watchlist_supported),
        "stable_subset_found": bool(stable_subset_found),
        "recommended_tickers": recommended_tickers,
        "recommended_groups": recommended_groups,
        "can_promote_for_subset": bool(can_promote_for_subset),
        "can_reject_candidate": bool(can_reject_candidate),
        "next_action": next_action,
        "best_subset_id": best_subset.get("subset_id"),
        "best_subset_label": best_subset.get("subset_label"),
        "best_subset_tickers": str(best_subset.get("tickers", "")).split("|"),
        "decision_notes": dedupe(
            [
                "Watchlist monitoring masih melihat subset yang lebih baik daripada baseline aktif."
                if watchlist_supported
                else "Candidate tidak lagi menunjukkan subset yang lebih baik daripada baseline aktif.",
                "Subset stabil lintas horizon observasi lanjutan sudah ditemukan."
                if stable_subset_found
                else "Subset belum stabil lintas horizon observasi lanjutan.",
                "Candidate masih layak dipantau sebagai experimental."
                if decision == "keep_candidate_experimental"
                else "",
            ]
        ),
    }


def build_monitoring_results(results_df: pd.DataFrame) -> pd.DataFrame:
    stability_map: Dict[str, bool] = {}
    for subset_id, frame in results_df.groupby("subset_id", sort=False):
        stable_across_windows = bool(
            bool(frame["candidate_better_than_active"].all())
            and bool((~frame["noise_risk"]).all())
            and bool((frame["candidate_eligible_ticker_count"] >= 1).all())
        )
        stability_map[str(subset_id)] = stable_across_windows

    enriched = results_df.copy()
    enriched["stable_across_windows"] = enriched["subset_id"].map(stability_map).fillna(False)
    return enriched


def update_transition_artifact(output_dir: Path, decision_payload: Dict[str, object]) -> Dict[str, object]:
    transition_path = Path(output_dir) / "phase_a_to_phase_b_transition.json"
    payload, warnings = read_json_object(transition_path, "Phase A to Phase B transition JSON")
    if payload is None:
        return {"updated": False, "path": str(transition_path), "warnings": warnings}

    payload["baseline_v2_watchlist_monitoring_status"] = decision_payload.get("decision")
    payload["baseline_v2_watchlist_monitoring_next_action"] = decision_payload.get("next_action")
    transition_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    report_path = Path(output_dir) / "phase_a_to_phase_b_transition_report.txt"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    appendix = [
        "",
        "Baseline v2 Watchlist Monitoring Update:",
        f"- baseline_v2_watchlist_monitoring_status: {decision_payload.get('decision')}",
        f"- baseline_v2_watchlist_monitoring_next_action: {decision_payload.get('next_action')}",
    ]
    report_path.write_text(report_text.rstrip() + "\n" + "\n".join(appendix) + "\n", encoding="utf-8")
    return {"updated": True, "path": str(transition_path), "report_path": str(report_path), "warnings": warnings}


def run_baseline_v2_watchlist_monitoring(
    data_dir: Path,
    output_dir: Path,
    baseline_config: Optional[Path],
    candidate_file: Path,
    metadata_file: Optional[Path],
    min_trades: int,
    observation_windows: Sequence[int],
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_payload, baseline_warnings, _ = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    candidate_payload = load_candidate_file(candidate_file)
    context = _read_watchlist_context(output_dir=output_dir)

    price_files = _resolve_price_files(Path(data_dir))
    available_tickers = [path.stem.upper() for path in price_files]
    watchlists = build_watchlist_definitions(
        context=context,
        metadata_lookup=metadata_lookup,
        available_tickers=available_tickers,
    )

    ticker_rows = []
    normalized_windows = [int(item) for item in list(observation_windows or [1, 2, 3, 4, 5])]
    for path in price_files:
        ticker_rows.extend(
            _ticker_metrics_for_windows(
                path=path,
                baseline_payload=baseline_payload,
                metadata_lookup=metadata_lookup,
                candidate_payload=candidate_payload,
                observation_windows=normalized_windows,
                min_trades=min_trades,
            )
        )
    ticker_window_df = pd.DataFrame(ticker_rows)
    if ticker_window_df.empty:
        raise BaselineV2WatchlistMonitoringCliError("No ticker window metrics were produced.")

    base_results_df = build_results_dataframe(
        ticker_window_df=ticker_window_df,
        watchlists=watchlists,
        min_trades=min_trades,
    )
    monitoring_results_df = build_monitoring_results(base_results_df)
    decision_payload = determine_monitoring_decision(
        results_df=monitoring_results_df,
        candidate_payload=candidate_payload,
    )
    summary_payload = build_summary_payload(
        results_df=monitoring_results_df,
        watchlists=watchlists,
        go_no_go=decision_payload,
        observation_windows=normalized_windows,
        min_trades=min_trades,
        warnings=dedupe([*list(context.get("warnings") or []), *baseline_warnings, *metadata_warnings]),
    )
    summary_payload["decision"] = _sanitize_for_json(decision_payload)
    report_text = build_report_text(summary_payload=summary_payload, go_no_go=decision_payload).replace(
        "Baseline v2 Watchlist Validation",
        "Baseline v2 Watchlist Monitoring",
    )

    results_path = output_dir / "baseline_v2_watchlist_monitoring_results.csv"
    summary_path = output_dir / "baseline_v2_watchlist_monitoring_summary.json"
    report_path = output_dir / "baseline_v2_watchlist_monitoring_report.txt"
    decision_path = output_dir / "baseline_v2_watchlist_monitoring_decision.json"

    monitoring_results_df.to_csv(results_path, index=False)
    _write_json(summary_path, summary_payload)
    _write_text(report_path, report_text.splitlines())
    _write_json(decision_path, decision_payload)
    transition_update = update_transition_artifact(output_dir=output_dir, decision_payload=decision_payload)

    return {
        "results_df": monitoring_results_df,
        "summary_payload": summary_payload,
        "decision_payload": decision_payload,
        "transition_update": transition_update,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor baseline v2 candidate stability on the watchlist across extended observation windows."
    )
    parser.add_argument("--data-dir", default="data", help="Directory containing per-ticker OHLCV CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory for watchlist monitoring artifacts.")
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
        help="Minimum trades guardrail for watchlist monitoring. Default: 5",
    )
    parser.add_argument(
        "--observation-windows",
        nargs="+",
        type=int,
        default=[1, 2, 3, 4, 5],
        help="Observation windows over trailing slices. Default: 1 2 3 4 5",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = run_baseline_v2_watchlist_monitoring(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        candidate_file=Path(args.candidate_file),
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        min_trades=int(args.min_trades),
        observation_windows=[int(item) for item in list(args.observation_windows or [1, 2, 3, 4, 5])],
    )
    print(f"Decision: {result['decision_payload']['decision']}")
    print(f"Recommended tickers: {', '.join(result['decision_payload']['recommended_tickers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
