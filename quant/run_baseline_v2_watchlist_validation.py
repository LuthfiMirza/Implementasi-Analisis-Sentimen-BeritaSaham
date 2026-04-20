"""Validate baseline v2 candidate stability on a small watchlist across observation windows."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.evaluate_phase_a_real_data import load_price_csv  # noqa: E402
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.phase_a_transition_utils import dedupe, read_json_object  # noqa: E402
from quant.run_baseline_v2_candidate_validation import (  # noqa: E402
    _evaluate_one_variant,
    _feature_frame,
    load_candidate_file,
)


RESULT_COLUMNS = [
    "subset_id",
    "subset_type",
    "subset_label",
    "group_field",
    "group_value",
    "tickers",
    "observation_window",
    "window_label",
    "ticker_count",
    "date_start",
    "date_end",
    "active_total_trades",
    "candidate_total_trades",
    "delta_total_trades",
    "active_win_rate_mean",
    "candidate_win_rate_mean",
    "delta_win_rate_mean",
    "active_average_return_mean",
    "candidate_average_return_mean",
    "delta_average_return_mean",
    "active_max_drawdown_mean",
    "candidate_max_drawdown_mean",
    "delta_max_drawdown_mean",
    "active_score_mean",
    "candidate_score_mean",
    "delta_score_mean",
    "active_eligible_ticker_count",
    "candidate_eligible_ticker_count",
    "coverage_improved",
    "candidate_better_than_active",
    "noise_risk",
    "subset_stable_snapshot",
]

DECISION_VALUES = {
    "keep_candidate_experimental",
    "promote_for_subset",
    "reject_candidate",
}


class BaselineV2WatchlistValidationCliError(ValueError):
    """Friendly CLI error for watchlist validation."""


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


def _read_watchlist_context(output_dir: Path) -> Dict[str, object]:
    subset_payload, subset_warnings = read_json_object(
        Path(output_dir) / "baseline_v2_subset_go_no_go.json",
        "Baseline v2 subset go/no-go JSON",
    )
    subset_summary, subset_summary_warnings = read_json_object(
        Path(output_dir) / "baseline_v2_subset_validation_summary.json",
        "Baseline v2 subset validation summary JSON",
    )
    payload = subset_payload if isinstance(subset_payload, dict) else {}
    summary = subset_summary if isinstance(subset_summary, dict) else {}
    return {
        "subset_go_no_go": payload,
        "subset_summary": summary,
        "warnings": dedupe([*subset_warnings, *subset_summary_warnings]),
    }


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


def _array_split_indices(length: int, parts: int) -> List[List[int]]:
    if length <= 0:
        return []
    base = length // parts
    remainder = length % parts
    chunks: List[List[int]] = []
    start = 0
    for part in range(parts):
        size = base + (1 if part < remainder else 0)
        if size <= 0:
            continue
        stop = start + size
        chunks.append(list(range(start, stop)))
        start = stop
    return [chunk for chunk in chunks if chunk]


def _split_trailing_windows(frame: pd.DataFrame, max_window: int) -> Dict[int, pd.DataFrame]:
    if frame.empty:
        return {}

    ordered = frame.sort_values("date").reset_index(drop=True)
    slice_count = max(3, int(max_window))
    index_slices = _array_split_indices(length=len(ordered), parts=slice_count)
    windows: Dict[int, pd.DataFrame] = {}
    for window in range(1, int(max_window) + 1):
        selected = index_slices[-window:]
        flat_indices = [int(item) for chunk in selected for item in chunk]
        windows[window] = ordered.iloc[flat_indices].copy().reset_index(drop=True)
    return windows


def _ticker_metrics_for_windows(
    path: Path,
    baseline_payload: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    candidate_payload: Dict[str, object],
    observation_windows: Sequence[int],
    min_trades: int,
) -> List[Dict[str, object]]:
    selected = dict(candidate_payload.get("selected_candidate") or {})
    candidate_id = str(selected.get("candidate_id"))
    hold_period = _safe_int(selected.get("hold_period"), 3)
    profit_buffer_pct = _safe_float(selected.get("profit_buffer_pct"), 0.0)
    active_candidate_id = "baseline_v2_hold3" if profit_buffer_pct == 0.0 else "baseline_v2_hold3_with_min_return_buffer"

    ticker = path.stem.upper()
    frame, _ = load_price_csv(path)
    runtime = resolve_phase_a_runtime_settings(
        ticker=ticker,
        baseline_config=baseline_payload,
        metadata_lookup=metadata_lookup,
    )
    metadata_row = dict(runtime.get("metadata_row") or {})
    max_window = max(int(window) for window in observation_windows)
    windows = _split_trailing_windows(frame=frame, max_window=max_window)

    rows: List[Dict[str, object]] = []
    for observation_window in [int(window) for window in observation_windows]:
        window_frame = windows.get(observation_window)
        if window_frame is None or window_frame.empty:
            continue
        feature_frame = _feature_frame(frame=window_frame, threshold=float(runtime["threshold"]))
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
        )
        rows.append(
            {
                "ticker": ticker,
                "observation_window": int(observation_window),
                "date_start": str(pd.to_datetime(window_frame["date"]).min().date()),
                "date_end": str(pd.to_datetime(window_frame["date"]).max().date()),
                "active_total_trades": int(active_metrics["total_trades"]),
                "candidate_total_trades": int(candidate_metrics["total_trades"]),
                "active_win_rate": float(active_metrics["win_rate"]),
                "candidate_win_rate": float(candidate_metrics["win_rate"]),
                "active_average_return": float(active_metrics["average_return"]),
                "candidate_average_return": float(candidate_metrics["average_return"]),
                "active_max_drawdown": float(active_metrics["max_drawdown"]),
                "candidate_max_drawdown": float(candidate_metrics["max_drawdown"]),
                "active_score": float(active_metrics["score"]),
                "candidate_score": float(candidate_metrics["score"]),
                "active_eligible_for_analysis": bool(active_metrics["eligible_for_analysis"]),
                "candidate_eligible_for_analysis": bool(candidate_metrics["eligible_for_analysis"]),
                "category": metadata_row.get("category"),
                "market_cap_group": metadata_row.get("market_cap_group"),
                "sector": metadata_row.get("sector"),
                "beta_group": metadata_row.get("beta_group"),
            }
        )
    return rows


def _group_tickers_from_metadata(
    metadata_lookup: Dict[str, Dict[str, object]],
    group_field: str,
    group_value: str,
    available_tickers: Iterable[str],
) -> List[str]:
    available = {str(item).upper() for item in available_tickers}
    matched: List[str] = []
    for ticker, row in metadata_lookup.items():
        if ticker not in available:
            continue
        value = str(row.get(group_field, "")).strip()
        if value == str(group_value).strip():
            matched.append(str(ticker).upper())
    return sorted(set(matched))


def build_watchlist_definitions(
    context: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    available_tickers: Sequence[str],
) -> List[Dict[str, object]]:
    available = {str(item).upper() for item in available_tickers}
    subset_go_no_go = dict(context.get("subset_go_no_go") or {})
    mandatory_tickers = [ticker for ticker in ["BMRI", "GOTO", "BBCA", "BBRI"] if ticker in available]

    best_subset_tickers = [
        str(item).upper()
        for item in list(subset_go_no_go.get("best_subset_tickers") or ["BMRI", "GOTO"])
        if str(item).upper() in available
    ]
    recommended_tickers = [
        str(item).upper()
        for item in list(subset_go_no_go.get("recommended_tickers") or mandatory_tickers)
        if str(item).upper() in available
    ]
    if not recommended_tickers:
        recommended_tickers = mandatory_tickers

    group_specs = [str(item) for item in list(subset_go_no_go.get("recommended_groups") or ["sector:perbankan"])]
    watchlists: List[Dict[str, object]] = []

    for ticker in mandatory_tickers:
        watchlists.append(
            {
                "subset_id": f"ticker_{ticker.lower()}",
                "subset_type": "ticker",
                "subset_label": ticker,
                "group_field": None,
                "group_value": None,
                "tickers": [ticker],
            }
        )

    if best_subset_tickers:
        watchlists.append(
            {
                "subset_id": "best_subset_bmri_goto",
                "subset_type": "subset",
                "subset_label": "BMRI|GOTO",
                "group_field": None,
                "group_value": None,
                "tickers": best_subset_tickers,
            }
        )

    if recommended_tickers:
        watchlists.append(
            {
                "subset_id": "recommended_watchlist",
                "subset_type": "subset",
                "subset_label": "recommended_watchlist",
                "group_field": None,
                "group_value": None,
                "tickers": dedupe(recommended_tickers),
            }
        )

    for item in group_specs:
        if ":" not in item:
            continue
        group_field, group_value = item.split(":", 1)
        matched = _group_tickers_from_metadata(
            metadata_lookup=metadata_lookup,
            group_field=group_field.strip(),
            group_value=group_value.strip(),
            available_tickers=available,
        )
        if matched:
            watchlists.append(
                {
                    "subset_id": f"group_{group_field.strip()}_{group_value.strip()}",
                    "subset_type": "group",
                    "subset_label": f"{group_field.strip()}:{group_value.strip()}",
                    "group_field": group_field.strip(),
                    "group_value": group_value.strip(),
                    "tickers": matched,
                }
            )

    deduped: List[Dict[str, object]] = []
    seen: set[Tuple[str, ...]] = set()
    for item in watchlists:
        key = tuple(sorted(set(item["tickers"])))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    if not deduped:
        raise BaselineV2WatchlistValidationCliError("No watchlist definitions could be resolved.")
    return deduped


def build_results_dataframe(
    ticker_window_df: pd.DataFrame,
    watchlists: Sequence[Dict[str, object]],
    min_trades: int,
) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    for watchlist in watchlists:
        subset_tickers = list(watchlist.get("tickers") or [])
        subset_df = ticker_window_df.loc[ticker_window_df["ticker"].isin(subset_tickers)].copy()
        if subset_df.empty:
            continue
        for observation_window, frame in subset_df.groupby("observation_window", sort=True):
            active_total_trades = int(frame["active_total_trades"].sum())
            candidate_total_trades = int(frame["candidate_total_trades"].sum())
            active_eligible = int(frame["active_eligible_for_analysis"].sum())
            candidate_eligible = int(frame["candidate_eligible_for_analysis"].sum())
            delta_score_mean = float(frame["candidate_score"].mean()) - float(frame["active_score"].mean())
            candidate_better = bool(
                delta_score_mean > 1.0
                and float(frame["candidate_average_return"].mean()) >= float(frame["active_average_return"].mean()) - 0.25
            )
            noise_risk = bool(
                candidate_total_trades < int(min_trades) * max(1, len(subset_tickers))
                or candidate_eligible < 1
            )
            rows.append(
                {
                    "subset_id": watchlist["subset_id"],
                    "subset_type": watchlist["subset_type"],
                    "subset_label": watchlist["subset_label"],
                    "group_field": watchlist.get("group_field"),
                    "group_value": watchlist.get("group_value"),
                    "tickers": "|".join(subset_tickers),
                    "observation_window": int(observation_window),
                    "window_label": f"last_{int(observation_window)}_slice",
                    "ticker_count": int(len(frame)),
                    "date_start": str(frame["date_start"].min()),
                    "date_end": str(frame["date_end"].max()),
                    "active_total_trades": active_total_trades,
                    "candidate_total_trades": candidate_total_trades,
                    "delta_total_trades": candidate_total_trades - active_total_trades,
                    "active_win_rate_mean": float(frame["active_win_rate"].mean()),
                    "candidate_win_rate_mean": float(frame["candidate_win_rate"].mean()),
                    "delta_win_rate_mean": float(frame["candidate_win_rate"].mean()) - float(frame["active_win_rate"].mean()),
                    "active_average_return_mean": float(frame["active_average_return"].mean()),
                    "candidate_average_return_mean": float(frame["candidate_average_return"].mean()),
                    "delta_average_return_mean": float(frame["candidate_average_return"].mean()) - float(frame["active_average_return"].mean()),
                    "active_max_drawdown_mean": float(frame["active_max_drawdown"].mean()),
                    "candidate_max_drawdown_mean": float(frame["candidate_max_drawdown"].mean()),
                    "delta_max_drawdown_mean": float(frame["candidate_max_drawdown"].mean()) - float(frame["active_max_drawdown"].mean()),
                    "active_score_mean": float(frame["active_score"].mean()),
                    "candidate_score_mean": float(frame["candidate_score"].mean()),
                    "delta_score_mean": delta_score_mean,
                    "active_eligible_ticker_count": active_eligible,
                    "candidate_eligible_ticker_count": candidate_eligible,
                    "coverage_improved": bool(candidate_eligible > active_eligible),
                    "candidate_better_than_active": candidate_better,
                    "noise_risk": noise_risk,
                    "subset_stable_snapshot": bool(candidate_better and not noise_risk),
                }
            )
    results_df = pd.DataFrame(rows)
    if results_df.empty:
        raise BaselineV2WatchlistValidationCliError("Watchlist validation produced no result rows.")
    return results_df.reindex(columns=RESULT_COLUMNS).sort_values(
        by=["subset_id", "observation_window"]
    ).reset_index(drop=True)


def determine_watchlist_go_no_go(
    results_df: pd.DataFrame,
    candidate_payload: Dict[str, object],
) -> Dict[str, object]:
    stability_rows: List[Dict[str, object]] = []
    for subset_id, frame in results_df.groupby("subset_id", sort=False):
        candidate_better_windows = int(frame["candidate_better_than_active"].sum())
        stable_over_windows = bool(
            candidate_better_windows == len(frame)
            and bool((~frame["noise_risk"]).all())
            and bool((frame["candidate_eligible_ticker_count"] >= 1).all())
        )
        promote_ready = bool(
            stable_over_windows
            and len(frame) >= 2
            and bool((frame["candidate_score_mean"] > 0).all())
            and bool((frame["candidate_total_trades"] >= frame["ticker_count"] * 5).all())
        )
        stability_rows.append(
            {
                "subset_id": subset_id,
                "subset_label": str(frame["subset_label"].iloc[0]),
                "subset_type": str(frame["subset_type"].iloc[0]),
                "tickers": str(frame["tickers"].iloc[0]),
                "candidate_better_windows": candidate_better_windows,
                "window_count": int(len(frame)),
                "stable_over_windows": stable_over_windows,
                "promote_ready": promote_ready,
                "latest_delta_score_mean": float(frame.sort_values("observation_window")["delta_score_mean"].iloc[-1]),
                "latest_candidate_total_trades": int(frame.sort_values("observation_window")["candidate_total_trades"].iloc[-1]),
            }
        )
    stability_df = pd.DataFrame(stability_rows).sort_values(
        by=["promote_ready", "stable_over_windows", "candidate_better_windows", "latest_delta_score_mean"],
        ascending=[False, False, False, False],
    )
    best_subset = dict(stability_df.iloc[0].to_dict())
    watchlist_supported = bool(results_df["candidate_better_than_active"].any())
    stable_subset_found = bool(stability_df["stable_over_windows"].any())
    can_promote_for_subset = bool(stability_df["promote_ready"].any())
    can_reject_candidate = bool(not watchlist_supported)

    if can_promote_for_subset:
        decision = "promote_for_subset"
        next_action = "promote_candidate_for_watchlist_subset_only"
    elif can_reject_candidate:
        decision = "reject_candidate"
        next_action = "reject_candidate_after_watchlist_monitoring"
    else:
        decision = "keep_candidate_experimental"
        next_action = "keep_candidate_experimental_for_watchlist_subset"

    promoted_rows = stability_df.loc[stability_df["promote_ready"]].copy()
    supported_rows = stability_df.loc[stability_df["candidate_better_windows"] >= 1].copy()
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
            results_df["subset_type"] == "group",
            "subset_label",
        ].astype(str).tolist()
        if not promoted_rows.empty
        else results_df.loc[
            (results_df["subset_type"] == "group") & (results_df["candidate_better_than_active"]),
            "subset_label",
        ].astype(str).tolist()
    )

    return {
        "decision": decision,
        "candidate_id": str(dict(candidate_payload.get("selected_candidate") or {}).get("candidate_id")),
        "watchlist_supported": watchlist_supported,
        "stable_subset_found": stable_subset_found,
        "recommended_tickers": recommended_tickers,
        "recommended_groups": recommended_groups,
        "can_promote_for_subset": can_promote_for_subset,
        "can_reject_candidate": can_reject_candidate,
        "next_action": next_action,
        "best_subset_id": best_subset.get("subset_id"),
        "best_subset_label": best_subset.get("subset_label"),
        "best_subset_tickers": str(best_subset.get("tickers", "")).split("|"),
        "decision_notes": dedupe(
            [
                "Watchlist subset menunjukkan improvement terhadap baseline aktif."
                if watchlist_supported
                else "Tidak ada subset watchlist yang konsisten mengungguli baseline aktif.",
                "Subset stabil lintas horizon observasi sudah terlihat."
                if stable_subset_found
                else "Subset belum cukup stabil lintas horizon observasi.",
                "Signal masih cenderung noise karena trade atau coverage belum cukup."
                if decision == "keep_candidate_experimental"
                else "",
            ]
        ),
    }


def build_summary_payload(
    results_df: pd.DataFrame,
    watchlists: Sequence[Dict[str, object]],
    go_no_go: Dict[str, object],
    observation_windows: Sequence[int],
    min_trades: int,
    warnings: Sequence[str],
) -> Dict[str, object]:
    best_rows = results_df.sort_values(
        by=["candidate_better_than_active", "subset_stable_snapshot", "delta_score_mean"],
        ascending=[False, False, False],
    )
    return {
        "generated_at": _now_iso(),
        "guardrails": {
            "min_trades": int(min_trades),
            "observation_windows": [int(item) for item in observation_windows],
        },
        "watchlists": _sanitize_for_json(list(watchlists)),
        "best_snapshot": _sanitize_for_json(dict(best_rows.iloc[0].to_dict())),
        "supported_snapshot_count": int(results_df["candidate_better_than_active"].sum()),
        "stable_snapshot_count": int(results_df["subset_stable_snapshot"].sum()),
        "decision": _sanitize_for_json(go_no_go),
        "warnings": list(warnings),
    }


def build_report_text(summary_payload: Dict[str, object], go_no_go: Dict[str, object]) -> str:
    best_snapshot = dict(summary_payload.get("best_snapshot") or {})
    lines = [
        "Baseline v2 Watchlist Validation",
        "================================",
        "",
        f"- Decision: {go_no_go['decision']}",
        f"- Candidate: {go_no_go['candidate_id']}",
        f"- Watchlist supported: {go_no_go['watchlist_supported']}",
        f"- Stable subset found: {go_no_go['stable_subset_found']}",
        f"- Can promote for subset: {go_no_go['can_promote_for_subset']}",
        f"- Can reject candidate: {go_no_go['can_reject_candidate']}",
        f"- Recommended tickers: {', '.join(go_no_go['recommended_tickers']) if go_no_go['recommended_tickers'] else '-'}",
        f"- Recommended groups: {', '.join(go_no_go['recommended_groups']) if go_no_go['recommended_groups'] else '-'}",
        f"- Next action: {go_no_go['next_action']}",
        "",
        "Best snapshot:",
        f"- subset_id={best_snapshot.get('subset_id')}",
        f"- subset_label={best_snapshot.get('subset_label')}",
        f"- observation_window={best_snapshot.get('observation_window')}",
        f"- tickers={best_snapshot.get('tickers')}",
        f"- candidate_better_than_active={best_snapshot.get('candidate_better_than_active')}",
        f"- delta_score_mean={_safe_float(best_snapshot.get('delta_score_mean')):+.4f}",
        f"- noise_risk={best_snapshot.get('noise_risk')}",
    ]
    for note in list(go_no_go.get("decision_notes") or []):
        lines.append(f"- Note: {note}")
    return "\n".join(lines) + "\n"


def update_transition_artifact(output_dir: Path, go_no_go: Dict[str, object]) -> Dict[str, object]:
    transition_path = Path(output_dir) / "phase_a_to_phase_b_transition.json"
    payload, warnings = read_json_object(transition_path, "Phase A to Phase B transition JSON")
    if payload is None:
        return {"updated": False, "path": str(transition_path), "warnings": warnings}

    payload["baseline_v2_watchlist_status"] = go_no_go.get("decision")
    payload["baseline_v2_watchlist_next_action"] = go_no_go.get("next_action")
    transition_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    report_path = Path(output_dir) / "phase_a_to_phase_b_transition_report.txt"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    appendix = [
        "",
        "Baseline v2 Watchlist Validation Update:",
        f"- baseline_v2_watchlist_status: {go_no_go.get('decision')}",
        f"- baseline_v2_watchlist_next_action: {go_no_go.get('next_action')}",
    ]
    report_path.write_text(report_text.rstrip() + "\n" + "\n".join(appendix) + "\n", encoding="utf-8")
    return {"updated": True, "path": str(transition_path), "report_path": str(report_path), "warnings": warnings}


def run_baseline_v2_watchlist_validation(
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

    available_price_files = _resolve_price_files(Path(data_dir))
    available_tickers = [path.stem.upper() for path in available_price_files]
    watchlists = build_watchlist_definitions(
        context=context,
        metadata_lookup=metadata_lookup,
        available_tickers=available_tickers,
    )

    ticker_rows: List[Dict[str, object]] = []
    observation_windows = [int(item) for item in observation_windows]
    for path in available_price_files:
        ticker_rows.extend(
            _ticker_metrics_for_windows(
                path=path,
                baseline_payload=baseline_payload,
                metadata_lookup=metadata_lookup,
                candidate_payload=candidate_payload,
                observation_windows=observation_windows,
                min_trades=min_trades,
            )
        )
    ticker_window_df = pd.DataFrame(ticker_rows)
    if ticker_window_df.empty:
        raise BaselineV2WatchlistValidationCliError("No ticker window metrics were produced.")

    results_df = build_results_dataframe(
        ticker_window_df=ticker_window_df,
        watchlists=watchlists,
        min_trades=min_trades,
    )
    go_no_go = determine_watchlist_go_no_go(
        results_df=results_df,
        candidate_payload=candidate_payload,
    )
    summary_payload = build_summary_payload(
        results_df=results_df,
        watchlists=watchlists,
        go_no_go=go_no_go,
        observation_windows=observation_windows,
        min_trades=min_trades,
        warnings=dedupe([*list(context.get("warnings") or []), *baseline_warnings, *metadata_warnings]),
    )
    report_text = build_report_text(summary_payload=summary_payload, go_no_go=go_no_go)

    results_path = output_dir / "baseline_v2_watchlist_validation_results.csv"
    summary_path = output_dir / "baseline_v2_watchlist_validation_summary.json"
    report_path = output_dir / "baseline_v2_watchlist_validation_report.txt"
    go_no_go_path = output_dir / "baseline_v2_watchlist_go_no_go.json"

    results_df.to_csv(results_path, index=False)
    _write_json(summary_path, summary_payload)
    _write_text(report_path, report_text.splitlines())
    _write_json(go_no_go_path, go_no_go)
    transition_update = update_transition_artifact(output_dir=output_dir, go_no_go=go_no_go)

    return {
        "results_df": results_df,
        "summary_payload": summary_payload,
        "go_no_go": go_no_go,
        "transition_update": transition_update,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate baseline v2 candidate stability on a watchlist across observation windows."
    )
    parser.add_argument("--data-dir", default="data", help="Directory containing per-ticker OHLCV CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory for watchlist validation artifacts.")
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
        help="Minimum trades guardrail for watchlist analysis. Default: 5",
    )
    parser.add_argument(
        "--observation-windows",
        nargs="+",
        type=int,
        default=[1, 2, 3],
        help="Observation windows over trailing slices. Default: 1 2 3",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = run_baseline_v2_watchlist_validation(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        candidate_file=Path(args.candidate_file),
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        min_trades=int(args.min_trades),
        observation_windows=[int(item) for item in list(args.observation_windows or [1, 2, 3])],
    )
    print(f"Decision: {result['go_no_go']['decision']}")
    print(f"Recommended tickers: {', '.join(result['go_no_go']['recommended_tickers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
