"""Validate whether a baseline v2 candidate is usable for a limited ticker subset."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_baseline import load_optional_metadata_lookup, load_phase_a_baseline  # noqa: E402
from quant.phase_a_transition_utils import dedupe, read_json_object  # noqa: E402
from quant.run_baseline_v2_candidate_validation import (  # noqa: E402
    build_per_ticker_comparison,
    load_candidate_file,
)


RESULT_COLUMNS = [
    "subset_id",
    "subset_type",
    "subset_label",
    "subset_source",
    "group_field",
    "group_value",
    "tickers",
    "ticker_count",
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
    "active_eligible_ticker_count",
    "candidate_eligible_ticker_count",
    "coverage_improved",
    "improve_ticker_count",
    "neutral_ticker_count",
    "worsen_ticker_count",
    "active_score_mean",
    "candidate_score_mean",
    "delta_score_mean",
    "active_selection_score",
    "candidate_selection_score",
    "delta_selection_score",
    "subset_stable",
    "candidate_better_than_active",
    "noise_risk",
    "can_promote_for_subset",
    "can_retry_phase_b_for_subset",
]

DECISION_VALUES = {
    "reject_candidate",
    "keep_candidate_experimental",
    "promote_for_subset",
    "promote_subset_and_prepare_phase_b_retry",
}


class BaselineV2SubsetValidationCliError(ValueError):
    """Friendly CLI error for subset validation."""


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


def _read_previous_validation_context(output_dir: Path) -> Dict[str, object]:
    summary_payload, summary_warnings = read_json_object(
        Path(output_dir) / "baseline_v2_validation_summary.json",
        "Baseline v2 validation summary JSON",
    )
    go_no_go_payload, go_no_go_warnings = read_json_object(
        Path(output_dir) / "baseline_v2_validation_go_no_go.json",
        "Baseline v2 validation go/no-go JSON",
    )
    per_ticker_path = Path(output_dir) / "baseline_v2_validation_per_ticker.csv"

    improve_tickers: List[str] = []
    worsen_tickers: List[str] = []
    if isinstance(summary_payload, dict):
        stability = dict(summary_payload.get("stability") or {})
        improve_tickers = [str(item).upper() for item in list(stability.get("improve_tickers") or []) if str(item).strip()]
        worsen_tickers = [str(item).upper() for item in list(stability.get("worsen_tickers") or []) if str(item).strip()]

    if per_ticker_path.exists():
        try:
            per_ticker_df = pd.read_csv(per_ticker_path)
        except Exception:
            per_ticker_df = pd.DataFrame()
        if not per_ticker_df.empty and "ticker" in per_ticker_df.columns and "validation_outcome" in per_ticker_df.columns:
            if not improve_tickers:
                improve_tickers = (
                    per_ticker_df.loc[per_ticker_df["validation_outcome"] == "improve", "ticker"].astype(str).str.upper().tolist()
                )
            if not worsen_tickers:
                worsen_tickers = (
                    per_ticker_df.loc[per_ticker_df["validation_outcome"] == "worsen", "ticker"].astype(str).str.upper().tolist()
                )

    return {
        "summary_payload": summary_payload if isinstance(summary_payload, dict) else {},
        "go_no_go_payload": go_no_go_payload if isinstance(go_no_go_payload, dict) else {},
        "improve_tickers": dedupe(improve_tickers),
        "worsen_tickers": dedupe(worsen_tickers),
        "warnings": dedupe([*summary_warnings, *go_no_go_warnings]),
    }


def _normalize_group_value(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _choose_control_tickers(
    per_ticker_df: pd.DataFrame,
    improve_tickers: Sequence[str],
    min_subset_tickers: int,
) -> List[str]:
    control_df = per_ticker_df.loc[~per_ticker_df["ticker"].isin(list(improve_tickers))].copy()
    if control_df.empty:
        return []
    control_df = control_df.sort_values(
        by=["active_total_trades", "candidate_total_trades", "active_score"],
        ascending=[False, False, False],
    )
    limit = max(int(min_subset_tickers), len(list(improve_tickers)) or int(min_subset_tickers))
    return control_df["ticker"].astype(str).head(limit).tolist()


def _add_subset(
    subsets: List[Dict[str, object]],
    seen: set[Tuple[str, ...]],
    *,
    subset_id: str,
    subset_type: str,
    subset_label: str,
    subset_source: str,
    tickers: Sequence[str],
    group_field: Optional[str] = None,
    group_value: Optional[str] = None,
) -> None:
    normalized = tuple(sorted({str(item).upper() for item in tickers if str(item).strip()}))
    if not normalized or normalized in seen:
        return
    seen.add(normalized)
    subsets.append(
        {
            "subset_id": subset_id,
            "subset_type": subset_type,
            "subset_label": subset_label,
            "subset_source": subset_source,
            "group_field": group_field,
            "group_value": group_value,
            "tickers": list(normalized),
        }
    )


def build_subset_candidates(
    per_ticker_df: pd.DataFrame,
    previous_context: Dict[str, object],
    min_subset_tickers: int,
) -> List[Dict[str, object]]:
    available_tickers = set(per_ticker_df["ticker"].astype(str).str.upper())
    improve_tickers = [
        ticker for ticker in list(previous_context.get("improve_tickers") or []) if ticker in available_tickers
    ]
    if not improve_tickers:
        improve_tickers = (
            per_ticker_df.loc[per_ticker_df["validation_outcome"] == "improve", "ticker"].astype(str).str.upper().tolist()
        )
    improve_tickers = dedupe(improve_tickers)

    subsets: List[Dict[str, object]] = []
    seen: set[Tuple[str, ...]] = set()

    if improve_tickers:
        _add_subset(
            subsets,
            seen,
            subset_id="seed_improve_tickers",
            subset_type="seed",
            subset_label="seed_improve_tickers",
            subset_source="baseline_v2_validation_summary",
            tickers=improve_tickers,
        )

    control_tickers = _choose_control_tickers(
        per_ticker_df=per_ticker_df,
        improve_tickers=improve_tickers,
        min_subset_tickers=min_subset_tickers,
    )
    if control_tickers:
        _add_subset(
            subsets,
            seen,
            subset_id="control_tickers",
            subset_type="control",
            subset_label="control_tickers",
            subset_source="non_improve_controls",
            tickers=control_tickers,
        )

    if improve_tickers and len(improve_tickers) < int(min_subset_tickers) and control_tickers:
        blended = dedupe([*improve_tickers, *control_tickers])[: max(int(min_subset_tickers), len(improve_tickers) + 1)]
        _add_subset(
            subsets,
            seen,
            subset_id="seed_plus_controls",
            subset_type="blended",
            subset_label="seed_plus_controls",
            subset_source="improve_tickers_plus_controls",
            tickers=blended,
        )

    group_fields = ["sector", "category", "market_cap_group", "beta_group"]
    for ticker in improve_tickers:
        seed_row = per_ticker_df.loc[per_ticker_df["ticker"] == ticker]
        if seed_row.empty:
            continue
        for field in group_fields:
            group_value = _normalize_group_value(seed_row.iloc[0].get(field))
            if not group_value:
                continue
            matched = (
                per_ticker_df.loc[per_ticker_df[field].astype(str) == str(group_value), "ticker"].astype(str).str.upper().tolist()
            )
            if len(matched) < int(min_subset_tickers):
                continue
            _add_subset(
                subsets,
                seen,
                subset_id=f"group_{field}_{group_value}",
                subset_type="group",
                subset_label=f"{field}:{group_value}",
                subset_source="metadata_group_from_improve_tickers",
                tickers=matched,
                group_field=field,
                group_value=group_value,
            )

    if not subsets:
        raise BaselineV2SubsetValidationCliError("No subset candidates could be constructed.")
    return subsets


def evaluate_subset(
    subset: Dict[str, object],
    per_ticker_df: pd.DataFrame,
    min_trades: int,
    min_subset_tickers: int,
) -> Dict[str, object]:
    tickers = list(subset.get("tickers") or [])
    frame = per_ticker_df.loc[per_ticker_df["ticker"].isin(tickers)].copy()
    if frame.empty:
        raise BaselineV2SubsetValidationCliError(f"Subset {subset.get('subset_id')} has no matching tickers.")

    active_selection_score = (
        float(frame["active_score"].mean())
        + (int(frame["active_eligible_for_analysis"].sum()) * 6.0)
        + (int((frame["active_score"] > 0).sum()) * 3.0)
        + (int(frame["active_total_trades"].sum()) * 0.10)
    )
    candidate_selection_score = (
        float(frame["candidate_score"].mean())
        + (int(frame["candidate_eligible_for_analysis"].sum()) * 6.0)
        + (int((frame["candidate_score"] > 0).sum()) * 3.0)
        + (int(frame["candidate_total_trades"].sum()) * 0.10)
    )
    improve_ticker_count = int((frame["validation_outcome"] == "improve").sum())
    neutral_ticker_count = int((frame["validation_outcome"] == "neutral").sum())
    worsen_ticker_count = int((frame["validation_outcome"] == "worsen").sum())
    candidate_eligible_ticker_count = int(frame["candidate_eligible_for_analysis"].sum())
    active_eligible_ticker_count = int(frame["active_eligible_for_analysis"].sum())
    coverage_improved = candidate_eligible_ticker_count > active_eligible_ticker_count
    candidate_better = (
        candidate_selection_score > active_selection_score + 1.0
        and float(frame["candidate_average_return"].mean()) >= float(frame["active_average_return"].mean()) - 0.25
        and worsen_ticker_count == 0
    )
    subset_stable = bool(
        candidate_better
        and improve_ticker_count >= 1
        and worsen_ticker_count == 0
        and candidate_eligible_ticker_count >= min(1, int(min_subset_tickers))
    )
    noise_risk = bool(
        int(frame["candidate_total_trades"].sum()) < int(min_trades) * max(1, int(min_subset_tickers))
        or candidate_eligible_ticker_count < int(min_subset_tickers)
    )
    can_promote_for_subset = bool(
        candidate_better
        and subset_stable
        and candidate_eligible_ticker_count >= int(min_subset_tickers)
        and improve_ticker_count >= int(min_subset_tickers)
        and float(frame["candidate_score"].mean()) > 0
        and not noise_risk
    )
    can_retry_phase_b_for_subset = bool(
        can_promote_for_subset
        and coverage_improved
        and int(frame["candidate_total_trades"].sum()) >= int(min_trades) * int(min_subset_tickers)
    )

    return {
        "subset_id": subset.get("subset_id"),
        "subset_type": subset.get("subset_type"),
        "subset_label": subset.get("subset_label"),
        "subset_source": subset.get("subset_source"),
        "group_field": subset.get("group_field"),
        "group_value": subset.get("group_value"),
        "tickers": "|".join(tickers),
        "ticker_count": int(len(frame)),
        "active_total_trades": int(frame["active_total_trades"].sum()),
        "candidate_total_trades": int(frame["candidate_total_trades"].sum()),
        "delta_total_trades": int(frame["candidate_total_trades"].sum()) - int(frame["active_total_trades"].sum()),
        "active_win_rate_mean": float(frame["active_win_rate"].mean()),
        "candidate_win_rate_mean": float(frame["candidate_win_rate"].mean()),
        "delta_win_rate_mean": float(frame["candidate_win_rate"].mean()) - float(frame["active_win_rate"].mean()),
        "active_average_return_mean": float(frame["active_average_return"].mean()),
        "candidate_average_return_mean": float(frame["candidate_average_return"].mean()),
        "delta_average_return_mean": float(frame["candidate_average_return"].mean()) - float(frame["active_average_return"].mean()),
        "active_max_drawdown_mean": float(frame["active_max_drawdown"].mean()),
        "candidate_max_drawdown_mean": float(frame["candidate_max_drawdown"].mean()),
        "delta_max_drawdown_mean": float(frame["candidate_max_drawdown"].mean()) - float(frame["active_max_drawdown"].mean()),
        "active_eligible_ticker_count": active_eligible_ticker_count,
        "candidate_eligible_ticker_count": candidate_eligible_ticker_count,
        "coverage_improved": bool(coverage_improved),
        "improve_ticker_count": improve_ticker_count,
        "neutral_ticker_count": neutral_ticker_count,
        "worsen_ticker_count": worsen_ticker_count,
        "active_score_mean": float(frame["active_score"].mean()),
        "candidate_score_mean": float(frame["candidate_score"].mean()),
        "delta_score_mean": float(frame["candidate_score"].mean()) - float(frame["active_score"].mean()),
        "active_selection_score": round(active_selection_score, 4),
        "candidate_selection_score": round(candidate_selection_score, 4),
        "delta_selection_score": round(candidate_selection_score - active_selection_score, 4),
        "subset_stable": bool(subset_stable),
        "candidate_better_than_active": bool(candidate_better),
        "noise_risk": bool(noise_risk),
        "can_promote_for_subset": bool(can_promote_for_subset),
        "can_retry_phase_b_for_subset": bool(can_retry_phase_b_for_subset),
    }


def determine_subset_go_no_go(
    results_df: pd.DataFrame,
    candidate_payload: Dict[str, object],
    min_subset_tickers: int,
) -> Dict[str, object]:
    ranked = results_df.sort_values(
        by=[
            "can_retry_phase_b_for_subset",
            "can_promote_for_subset",
            "candidate_better_than_active",
            "subset_stable",
            "delta_selection_score",
            "candidate_total_trades",
        ],
        ascending=[False, False, False, False, False, False],
    ).reset_index(drop=True)
    best = dict(ranked.iloc[0].to_dict())

    subset_supported = bool(
        (
            results_df["candidate_better_than_active"].fillna(False)
            & results_df["ticker_count"].ge(int(min_subset_tickers))
        ).any()
    )
    can_promote_for_subset = bool(results_df["can_promote_for_subset"].fillna(False).any())
    can_retry_phase_b_for_subset = bool(results_df["can_retry_phase_b_for_subset"].fillna(False).any())

    if not subset_supported:
        decision = "reject_candidate"
        next_action = "reject_candidate_for_subset_use"
    elif can_retry_phase_b_for_subset:
        decision = "promote_subset_and_prepare_phase_b_retry"
        next_action = "promote_subset_and_open_limited_phase_b_retry"
    elif can_promote_for_subset:
        decision = "promote_for_subset"
        next_action = "promote_candidate_for_subset_only"
    else:
        decision = "keep_candidate_experimental"
        next_action = "keep_candidate_experimental_for_watchlist_subset"

    promoted_rows = results_df.loc[results_df["can_promote_for_subset"].fillna(False)].copy()
    supported_rows = results_df.loc[
        results_df["candidate_better_than_active"].fillna(False) & results_df["ticker_count"].ge(int(min_subset_tickers))
    ].copy()
    source_rows = promoted_rows if not promoted_rows.empty else supported_rows
    recommended_tickers = dedupe(
        [
            ticker
            for tickers_blob in source_rows["tickers"].astype(str).tolist()
            for ticker in tickers_blob.split("|")
            if ticker
        ]
    )
    if not recommended_tickers:
        recommended_tickers = [ticker for ticker in str(best.get("tickers", "")).split("|") if ticker]

    recommended_groups = dedupe(
        [
            str(label)
            for label in source_rows.loc[source_rows["subset_type"] == "group", "subset_label"].astype(str).tolist()
            if label and label != "nan"
        ]
    )

    return {
        "decision": decision,
        "candidate_id": str(dict(candidate_payload.get("selected_candidate") or {}).get("candidate_id")),
        "subset_supported": bool(subset_supported),
        "recommended_tickers": recommended_tickers,
        "recommended_groups": recommended_groups,
        "can_promote_for_subset": bool(can_promote_for_subset),
        "can_retry_phase_b_for_subset": bool(can_retry_phase_b_for_subset),
        "next_action": next_action,
        "best_subset_id": best.get("subset_id"),
        "best_subset_label": best.get("subset_label"),
        "best_subset_tickers": str(best.get("tickers", "")).split("|"),
        "decision_notes": dedupe(
            [
                "Subset candidate menunjukkan perbaikan pada subset tertentu."
                if subset_supported
                else "Tidak ada subset yang cukup kuat untuk mendukung candidate ini.",
                "Guardrail subset belum terpenuhi sehingga candidate belum boleh dipromosikan untuk subset."
                if decision == "keep_candidate_experimental"
                else "",
                "Subset terbaik masih terindikasi noise karena trade/coverage belum cukup."
                if bool(best.get("noise_risk"))
                else "",
            ]
        ),
    }


def build_summary_payload(
    results_df: pd.DataFrame,
    previous_context: Dict[str, object],
    go_no_go: Dict[str, object],
    min_trades: int,
    min_subset_tickers: int,
) -> Dict[str, object]:
    best_subset = {}
    if not results_df.empty:
        best_subset = dict(
            results_df.sort_values(
                by=["candidate_better_than_active", "delta_selection_score", "candidate_total_trades"],
                ascending=[False, False, False],
            ).iloc[0].to_dict()
        )

    return {
        "generated_at": _now_iso(),
        "guardrails": {
            "min_trades": int(min_trades),
            "min_subset_tickers": int(min_subset_tickers),
        },
        "seed_context": {
            "improve_tickers": list(previous_context.get("improve_tickers") or []),
            "worsen_tickers": list(previous_context.get("worsen_tickers") or []),
        },
        "subset_count": int(len(results_df)),
        "best_subset": _sanitize_for_json(best_subset),
        "supported_subset_count": int(results_df["candidate_better_than_active"].fillna(False).sum()),
        "promotable_subset_count": int(results_df["can_promote_for_subset"].fillna(False).sum()),
        "retry_ready_subset_count": int(results_df["can_retry_phase_b_for_subset"].fillna(False).sum()),
        "decision": _sanitize_for_json(go_no_go),
        "warnings": list(previous_context.get("warnings") or []),
    }


def build_report_text(summary_payload: Dict[str, object], go_no_go: Dict[str, object]) -> str:
    best_subset = dict(summary_payload.get("best_subset") or {})
    lines = [
        "Baseline v2 Subset Validation",
        "=============================",
        "",
        f"- Decision: {go_no_go['decision']}",
        f"- Candidate: {go_no_go['candidate_id']}",
        f"- Subset supported: {go_no_go['subset_supported']}",
        f"- Can promote for subset: {go_no_go['can_promote_for_subset']}",
        f"- Can retry Phase B for subset: {go_no_go['can_retry_phase_b_for_subset']}",
        f"- Recommended tickers: {', '.join(go_no_go['recommended_tickers']) if go_no_go['recommended_tickers'] else '-'}",
        f"- Recommended groups: {', '.join(go_no_go['recommended_groups']) if go_no_go['recommended_groups'] else '-'}",
        f"- Next action: {go_no_go['next_action']}",
        "",
        "Best subset:",
        f"- subset_id={best_subset.get('subset_id')}",
        f"- subset_label={best_subset.get('subset_label')}",
        f"- tickers={best_subset.get('tickers')}",
        f"- candidate_better_than_active={best_subset.get('candidate_better_than_active')}",
        f"- candidate_eligible_ticker_count={_safe_int(best_subset.get('candidate_eligible_ticker_count'))}",
        f"- delta_selection_score={_safe_float(best_subset.get('delta_selection_score')):+.4f}",
        f"- noise_risk={best_subset.get('noise_risk')}",
    ]
    notes = list(go_no_go.get("decision_notes") or [])
    if notes:
        lines.extend(["", "Decision notes:"])
        for item in notes:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def update_transition_artifact(output_dir: Path, go_no_go: Dict[str, object]) -> Dict[str, object]:
    transition_path = Path(output_dir) / "phase_a_to_phase_b_transition.json"
    payload, warnings = read_json_object(transition_path, "Phase A to Phase B transition JSON")
    if payload is None:
        return {"updated": False, "path": str(transition_path), "warnings": warnings}

    payload["baseline_v2_subset_status"] = go_no_go.get("decision")
    payload["baseline_v2_subset_next_action"] = go_no_go.get("next_action")
    payload["phase_b_subset_retry_readiness"] = (
        "ready_for_subset_retry" if bool(go_no_go.get("can_retry_phase_b_for_subset")) else "not_ready_yet"
    )
    transition_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    report_path = Path(output_dir) / "phase_a_to_phase_b_transition_report.txt"
    report_text = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
    appendix = [
        "",
        "Baseline v2 Subset Validation Update:",
        f"- baseline_v2_subset_status: {go_no_go.get('decision')}",
        f"- baseline_v2_subset_next_action: {go_no_go.get('next_action')}",
        f"- phase_b_subset_retry_readiness: {'ready_for_subset_retry' if bool(go_no_go.get('can_retry_phase_b_for_subset')) else 'not_ready_yet'}",
    ]
    report_path.write_text(report_text.rstrip() + "\n" + "\n".join(appendix) + "\n", encoding="utf-8")
    return {"updated": True, "path": str(transition_path), "report_path": str(report_path), "warnings": warnings}


def run_baseline_v2_subset_validation(
    data_dir: Path,
    output_dir: Path,
    baseline_config: Optional[Path],
    candidate_file: Path,
    metadata_file: Optional[Path],
    min_trades: int,
    min_subset_tickers: int,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline_payload, baseline_warnings, _ = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    candidate_payload = load_candidate_file(candidate_file)
    previous_context = _read_previous_validation_context(output_dir=output_dir)

    per_ticker_df = build_per_ticker_comparison(
        data_dir=Path(data_dir),
        baseline_payload=baseline_payload,
        metadata_lookup=metadata_lookup,
        candidate_payload=candidate_payload,
        min_trades=int(min_trades),
    )
    if per_ticker_df.empty:
        raise BaselineV2SubsetValidationCliError("No per-ticker rows available for subset validation.")

    subsets = build_subset_candidates(
        per_ticker_df=per_ticker_df,
        previous_context=previous_context,
        min_subset_tickers=min_subset_tickers,
    )
    results_df = pd.DataFrame(
        [evaluate_subset(subset=item, per_ticker_df=per_ticker_df, min_trades=min_trades, min_subset_tickers=min_subset_tickers) for item in subsets]
    ).reindex(columns=RESULT_COLUMNS)
    go_no_go = determine_subset_go_no_go(
        results_df=results_df,
        candidate_payload=candidate_payload,
        min_subset_tickers=min_subset_tickers,
    )
    summary_payload = build_summary_payload(
        results_df=results_df,
        previous_context=previous_context,
        go_no_go=go_no_go,
        min_trades=min_trades,
        min_subset_tickers=min_subset_tickers,
    )
    summary_payload["warnings"] = dedupe(
        [*list(summary_payload.get("warnings") or []), *baseline_warnings, *metadata_warnings]
    )
    report_text = build_report_text(summary_payload=summary_payload, go_no_go=go_no_go)

    results_path = output_dir / "baseline_v2_subset_validation_results.csv"
    summary_path = output_dir / "baseline_v2_subset_validation_summary.json"
    report_path = output_dir / "baseline_v2_subset_validation_report.txt"
    go_no_go_path = output_dir / "baseline_v2_subset_go_no_go.json"

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
        description="Validate whether a baseline v2 candidate is usable for a limited ticker subset."
    )
    parser.add_argument("--data-dir", default="data", help="Directory containing per-ticker OHLCV CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory for subset validation artifacts.")
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
        help="Minimum trades guardrail for subset analysis. Default: 5",
    )
    parser.add_argument(
        "--min-subset-tickers",
        type=int,
        default=2,
        help="Minimum ticker count required before subset promotion. Default: 2",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = run_baseline_v2_subset_validation(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        candidate_file=Path(args.candidate_file),
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        min_trades=int(args.min_trades),
        min_subset_tickers=int(args.min_subset_tickers),
    )
    print(f"Decision: {result['go_no_go']['decision']}")
    print(f"Recommended tickers: {', '.join(result['go_no_go']['recommended_tickers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
