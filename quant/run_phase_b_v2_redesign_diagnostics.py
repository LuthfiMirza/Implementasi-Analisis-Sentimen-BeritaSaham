"""Run minimum redesign diagnostics for Phase B v2."""

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

from quant.evaluate_phase_a_real_data import evaluate_folder  # noqa: E402
from quant.phase_a import REQUIRED_COLUMNS, SENTIMENT_DAILY_COLUMNS  # noqa: E402
from quant.phase_a_baseline import (  # noqa: E402
    load_optional_metadata_lookup,
    load_phase_a_baseline,
    resolve_phase_a_runtime_settings,
)
from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402


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


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _write_text(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_text(path: Path, label: str) -> Tuple[Optional[str], List[str]]:
    warnings: List[str] = []
    target = Path(path)
    if not target.exists():
        warnings.append(f"{label} not found: {target}.")
        return None, warnings
    if not target.is_file():
        warnings.append(f"{label} is not a file: {target}.")
        return None, warnings

    try:
        return target.read_text(encoding="utf-8"), warnings
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(f"Failed to read {label} {target}: {exc}.")
        return None, warnings


def _resolve_price_csv_files(data_dir: Path) -> List[Path]:
    candidates = sorted(Path(data_dir).glob("*.csv"))
    valid_paths: List[Path] = []
    for path in candidates:
        try:
            preview = pd.read_csv(path, nrows=2)
        except Exception:
            continue
        columns = set(preview.columns.astype(str))
        if set(REQUIRED_COLUMNS).issubset(columns):
            valid_paths.append(path)
    return valid_paths


def _load_phase_b_artifacts(output_dir: Path) -> Dict[str, object]:
    artifact_names = {
        "item5_go_no_go": "phase_b_item5_go_no_go.json",
        "item5_report": "phase_b_item5_recommendations.txt",
        "item6_go_no_go": "phase_b_item6_go_no_go.json",
        "item7_go_no_go": "phase_b_item7_go_no_go.json",
        "item7_data_readiness": "phase_b_item7_data_readiness.json",
        "item8_go_no_go": "phase_b_item8_go_no_go.json",
        "item8_summary": "phase_b_item8_global_summary.json",
        "postmortem": "phase_b_postmortem.json",
    }
    payloads: Dict[str, object] = {"warnings": []}
    warnings: List[str] = []
    for key, filename in artifact_names.items():
        path = Path(output_dir) / filename
        if filename.endswith(".json"):
            payload, item_warnings = read_json_object(path, filename)
            payloads[key] = payload
            warnings.extend(item_warnings)
        else:
            payload, item_warnings = _load_text(path, filename)
            payloads[key] = payload
            warnings.extend(item_warnings)
    payloads["warnings"] = dedupe(warnings)
    return payloads


def build_overlap_audit(
    baseline_config: Dict[str, object],
    metadata_lookup: Dict[str, Dict[str, object]],
    price_files: Sequence[Path],
    phase_b_artifacts: Dict[str, object],
    generated_at: str,
) -> Dict[str, object]:
    item5_go = safe_dict(phase_b_artifacts.get("item5_go_no_go"))
    item8_go = safe_dict(phase_b_artifacts.get("item8_go_no_go"))
    item8_summary = safe_dict(phase_b_artifacts.get("item8_summary"))
    item7_readiness = safe_dict(phase_b_artifacts.get("item7_data_readiness"))
    item5_report = str(phase_b_artifacts.get("item5_report") or "")

    runtime_rows: List[Dict[str, object]] = []
    for path in price_files:
        ticker = path.stem.upper()
        runtime_rows.append(
            {
                "ticker": ticker,
                **resolve_phase_a_runtime_settings(
                    ticker=ticker,
                    baseline_config=baseline_config,
                    metadata_lookup=metadata_lookup,
                ),
            }
        )

    runtime_df = pd.DataFrame(runtime_rows)
    baseline_threshold = _safe_float(baseline_config.get("default_volume_spike_threshold"), 2.0)
    baseline_strict_mode = bool(baseline_config.get("strict_mode_default"))
    runtime_thresholds = sorted(
        {round(_safe_float(value, baseline_threshold), 4) for value in list(runtime_df.get("threshold", []))}
    )
    unique_runtime_config_count = int(
        runtime_df[["threshold", "strict_mode"]].drop_duplicates().shape[0]
    ) if not runtime_df.empty else 0

    item5_blocked = " ".join(str(item) for item in list(item5_go.get("blocked_from_default") or [])).lower()
    item5_high_overlap = (
        math.isclose(_safe_float(item5_go.get("best_global_threshold"), -999.0), baseline_threshold)
        or "collapse ke effective confirmation threshold" in item5_blocked
        or "baseline phase a aktif" in item5_blocked
    )

    item8_thresholds = [float(value) for value in list(item8_summary.get("thresholds_tested") or [])]
    item8_strict_options = [bool(value) for value in list(item8_summary.get("strict_options_tested") or [])]
    item8_span = (
        max(item8_thresholds) - min(item8_thresholds)
        if item8_thresholds
        else 0.0
    )
    item8_includes_baseline = baseline_threshold in item8_thresholds and baseline_strict_mode in item8_strict_options
    item8_high_overlap = (
        item8_includes_baseline
        and item8_span <= 1.0
        and not bool(baseline_config.get("adaptive_threshold_enabled"))
    )

    payload = {
        "generated_at": generated_at,
        "baseline_runtime": {
            "default_volume_spike_threshold": baseline_threshold,
            "strict_mode_default": baseline_strict_mode,
            "adaptive_threshold_enabled": bool(baseline_config.get("adaptive_threshold_enabled")),
            "group_override_count": int(len(list(baseline_config.get("group_threshold_overrides") or []))),
            "unique_runtime_config_count": unique_runtime_config_count,
            "runtime_thresholds": runtime_thresholds,
        },
        "overlap_assessment": {
            "item5": {
                "overlap_level": "high" if item5_high_overlap else "medium",
                "best_global_threshold": item5_go.get("best_global_threshold"),
                "same_as_baseline_threshold": math.isclose(
                    _safe_float(item5_go.get("best_global_threshold"), -999.0),
                    baseline_threshold,
                ),
                "redundancy_signals": dedupe(
                    [
                        "Item 5 threshold terbaik sama dengan baseline aktif."
                        if math.isclose(_safe_float(item5_go.get("best_global_threshold"), -999.0), baseline_threshold)
                        else "",
                        "Artifact item 5 sudah menyatakan threshold collapse ke aturan baseline."
                        if "collapse ke effective confirmation threshold" in item5_blocked or "baseline phase a aktif" in item5_blocked
                        else "",
                        "Filter tambahan item 5 menambah syarat tetapi tidak menghasilkan kandidat baru."
                        if str(item5_go.get("decision")) == "no_go"
                        else "",
                    ]
                ),
            },
            "item6": {
                "overlap_level": "low",
                "redundancy_signals": [
                    "Filter weekly trend relatif orthogonal terhadap baseline, tetapi tidak menambah informasi yang cukup untuk menjaga retention trade."
                ],
            },
            "item7": {
                "overlap_level": "low",
                "sentiment_ready_ticker_count": item7_readiness.get("valid_ticker_count"),
                "sentiment_unusable_ticker_count": item7_readiness.get("unusable_ticker_count"),
                "redundancy_signals": [
                    "Sentiment momentum bukan overlap langsung dengan baseline, tetapi sinyal tambahannya tidak cukup usable pada data real."
                ],
            },
            "item8": {
                "overlap_level": "high" if item8_high_overlap else "medium",
                "thresholds_tested": item8_thresholds,
                "strict_options_tested": item8_strict_options,
                "includes_baseline_config": item8_includes_baseline,
                "search_space_span": item8_span,
                "redundancy_signals": dedupe(
                    [
                        "Adaptive search space item 8 masih berpusat pada threshold yang sangat dekat dengan baseline."
                        if item8_span <= 1.0 and item8_thresholds
                        else "",
                        "Baseline config persis ikut masuk ke adaptive search space."
                        if item8_includes_baseline
                        else "",
                        "Adaptive baseline belum didukung override/group model, sehingga variasi konfigurasi praktis masih sempit."
                        if not bool(baseline_config.get("adaptive_threshold_enabled"))
                        else "",
                        "Artifact item 8 menyatakan model adaptive belum usable."
                        if not bool(item8_go.get("adaptive_model_supported"))
                        else "",
                    ]
                ),
            },
        },
        "overall_overlap_risk": (
            "high" if item5_high_overlap or item8_high_overlap else "medium"
        ),
        "overall_conclusion": (
            "Baseline aktif sudah menyerap sebagian besar variasi threshold sederhana; eksperimen item 5 dan item 8 terutama terlihat redundant atau terlalu sempit."
            if item5_high_overlap or item8_high_overlap
            else "Ada overlap parsial, tetapi bukan satu-satunya penyebab gagal Phase B."
        ),
        "warnings": list(phase_b_artifacts.get("warnings") or []),
        "evidence_excerpt": item5_report.splitlines()[:12] if item5_report else [],
    }
    return payload


def _evaluate_hold_matrix(
    data_dir: Path,
    baseline_config_path: Optional[Path],
    metadata_file: Optional[Path],
    hold_period_options: Sequence[int],
) -> Tuple[Dict[int, Dict[str, object]], Dict[int, pd.DataFrame]]:
    hold_payloads: Dict[int, Dict[str, object]] = {}
    hold_summaries: Dict[int, pd.DataFrame] = {}

    for hold_period in hold_period_options:
        summary_df, skipped_df, aggregate_df = evaluate_folder(
            folder_path=data_dir,
            output_dir=None,
            baseline_config=baseline_config_path,
            metadata_file=metadata_file,
            hold_period=int(hold_period),
            log_progress=False,
        )
        aggregate = (
            aggregate_df.iloc[0].to_dict() if not aggregate_df.empty else {}
        )
        hold_summaries[int(hold_period)] = summary_df.copy()
        hold_payloads[int(hold_period)] = {
            "summary_df": summary_df,
            "skipped_df": skipped_df,
            "aggregate": aggregate,
        }
    return hold_payloads, hold_summaries


def build_trade_design_audit(
    hold_results: Dict[int, Dict[str, object]],
    min_trades_options: Sequence[int],
    baseline_min_trades_floor: int,
    generated_at: str,
) -> Dict[str, object]:
    current_hold = 5 if 5 in hold_results else sorted(hold_results)[0]
    current_floor = int(baseline_min_trades_floor)
    hold_metrics: List[Dict[str, object]] = []

    for hold_period in sorted(hold_results):
        summary_df = hold_results[hold_period]["summary_df"]
        aggregate = safe_dict(hold_results[hold_period]["aggregate"])
        phase_a_total_trades_sum = _safe_float(aggregate.get("phase_a_total_trades_sum"))
        baseline_total_trades_sum = _safe_float(aggregate.get("baseline_total_trades_sum"))
        coverage_by_min = {
            str(option): int((summary_df["phase_a_total_trades"] >= int(option)).sum()) if not summary_df.empty else 0
            for option in min_trades_options
        }
        hold_metrics.append(
            {
                "hold_period": int(hold_period),
                "ticker_count": int(len(summary_df)),
                "phase_a_total_trades_sum": phase_a_total_trades_sum,
                "baseline_total_trades_sum": baseline_total_trades_sum,
                "trade_retention_vs_baseline_pct": (
                    round((phase_a_total_trades_sum / baseline_total_trades_sum) * 100.0, 2)
                    if baseline_total_trades_sum > 0
                    else None
                ),
                "phase_a_win_rate_mean": _safe_float(aggregate.get("phase_a_win_rate_mean")),
                "phase_a_average_return_mean": _safe_float(aggregate.get("phase_a_average_return_mean")),
                "zero_trade_ticker_count": int((summary_df["phase_a_total_trades"] <= 0).sum()) if not summary_df.empty else 0,
                "eligible_ticker_count_by_min_trades": coverage_by_min,
            }
        )

    hold_metrics.sort(key=lambda item: item["hold_period"])
    current_metrics = next(item for item in hold_metrics if item["hold_period"] == current_hold)
    best_hold_for_coverage = max(
        hold_metrics,
        key=lambda item: (
            int(safe_dict(item["eligible_ticker_count_by_min_trades"]).get(str(current_floor), 0)),
            _safe_float(item["phase_a_total_trades_sum"]),
            _safe_float(item["phase_a_average_return_mean"]),
        ),
    )
    return_range = (
        max(_safe_float(item["phase_a_average_return_mean"]) for item in hold_metrics)
        - min(_safe_float(item["phase_a_average_return_mean"]) for item in hold_metrics)
    )
    win_rate_range = (
        max(_safe_float(item["phase_a_win_rate_mean"]) for item in hold_metrics)
        - min(_safe_float(item["phase_a_win_rate_mean"]) for item in hold_metrics)
    )

    baseline_needs_entry_exit_redesign = (
        int(safe_dict(current_metrics["eligible_ticker_count_by_min_trades"]).get(str(current_floor), 0)) == 0
        and int(safe_dict(best_hold_for_coverage["eligible_ticker_count_by_min_trades"]).get(str(current_floor), 0)) == 0
    ) or _safe_float(current_metrics.get("trade_retention_vs_baseline_pct")) < 20.0

    scoring_eval_redesign_needed = (
        return_range > 0.75 or win_rate_range > 10.0
    ) and not baseline_needs_entry_exit_redesign

    payload = {
        "generated_at": generated_at,
        "current_hold_period": int(current_hold),
        "baseline_min_trades_floor": int(current_floor),
        "hold_period_diagnostics": hold_metrics,
        "best_hold_period_for_coverage": int(best_hold_for_coverage["hold_period"]),
        "best_hold_period_improves_current_coverage": (
            int(safe_dict(best_hold_for_coverage["eligible_ticker_count_by_min_trades"]).get(str(current_floor), 0))
            > int(safe_dict(current_metrics["eligible_ticker_count_by_min_trades"]).get(str(current_floor), 0))
        ),
        "labeling_sensitivity": {
            "average_return_range": round(return_range, 6),
            "win_rate_range": round(win_rate_range, 6),
        },
        "diagnosis_flags": {
            "baseline_needs_entry_exit_redesign": bool(baseline_needs_entry_exit_redesign),
            "baseline_usable_but_needs_scoring_eval_redesign": bool(scoring_eval_redesign_needed),
            "current_hold_is_not_best_for_coverage": int(best_hold_for_coverage["hold_period"]) != int(current_hold),
        },
        "conclusion": (
            "Desain trade baseline masih terlalu ketat terhadap data yang tersedia; redesign entry/exit dan/atau labeling perlu didahulukan."
            if baseline_needs_entry_exit_redesign
            else "Baseline masih usable, tetapi scoring/evaluasi perlu dikalibrasi ulang sebelum eksperimen filter baru diulang."
            if scoring_eval_redesign_needed
            else "Trade design baseline belum menunjukkan blocker besar pada sweep hold period minimum."
        ),
    }
    return payload


def build_sample_coverage(
    hold_summaries: Dict[int, pd.DataFrame],
    min_trades_options: Sequence[int],
    baseline_min_trades_floor: int,
    generated_at: str,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    current_hold = 5 if 5 in hold_summaries else sorted(hold_summaries)[0]
    current_summary = hold_summaries[current_hold].copy()
    current_summary = current_summary.sort_values("ticker").reset_index(drop=True)

    coverage_df = current_summary[["ticker", "phase_a_applied_threshold", "phase_a_applied_strict_mode"]].copy()
    coverage_df.rename(
        columns={
            "phase_a_applied_threshold": "applied_threshold",
            "phase_a_applied_strict_mode": "applied_strict_mode",
        },
        inplace=True,
    )

    for hold_period, summary_df in sorted(hold_summaries.items()):
        renamed = summary_df[["ticker", "phase_a_total_trades"]].copy()
        renamed.rename(columns={"phase_a_total_trades": f"total_trades_hold_{int(hold_period)}"}, inplace=True)
        coverage_df = coverage_df.merge(renamed, on="ticker", how="left")

    default_trade_column = f"total_trades_hold_{int(current_hold)}"
    for min_trades in min_trades_options:
        coverage_df[f"eligible_min_trades_{int(min_trades)}"] = (
            coverage_df[default_trade_column].fillna(0) >= int(min_trades)
        )

    ticker_count = int(len(coverage_df))
    target_coverage = max(3, math.ceil(ticker_count * 0.5))
    recommended_min_trades = int(min(min_trades_options))
    coverage_by_min: Dict[str, Dict[str, int]] = {}
    for option in sorted(min_trades_options):
        eligible_count = int(coverage_df[f"eligible_min_trades_{int(option)}"].sum())
        coverage_by_min[str(option)] = {
            "eligible_ticker_count": eligible_count,
            "auto_unusable_ticker_count": ticker_count - eligible_count,
        }
        if eligible_count >= target_coverage:
            recommended_min_trades = int(option)

    summary_payload = {
        "generated_at": generated_at,
        "current_hold_period": int(current_hold),
        "ticker_count": ticker_count,
        "coverage_target_ticker_count": int(target_coverage),
        "baseline_min_trades_floor": int(baseline_min_trades_floor),
        "coverage_by_min_trades": coverage_by_min,
        "recommended_realistic_min_trades": int(recommended_min_trades),
        "current_floor_is_too_strict": int(coverage_by_min.get(str(baseline_min_trades_floor), {}).get("eligible_ticker_count", 0)) < target_coverage,
        "current_zero_trade_ticker_count": int(coverage_df[default_trade_column].fillna(0).le(0).sum()),
    }
    return coverage_df, summary_payload


def build_sentiment_relevance(
    price_files: Sequence[Path],
    item7_readiness: Optional[Dict[str, object]],
    generated_at: str,
) -> Tuple[pd.DataFrame, Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for path in price_files:
        ticker = path.stem.upper()
        frame = pd.read_csv(path)
        missing_columns = [column for column in SENTIMENT_DAILY_COLUMNS if column not in frame.columns]
        if missing_columns:
            rows.append(
                {
                    "ticker": ticker,
                    "rows": int(len(frame)),
                    "has_sentiment_columns": False,
                    "article_day_count": 0,
                    "article_count_total": 0.0,
                    "article_day_ratio": 0.0,
                    "sentiment_average_std": 0.0,
                    "sentiment_weighted_std": 0.0,
                    "sentiment_average_change_ratio": 0.0,
                    "sentiment_weighted_change_ratio": 0.0,
                    "too_sparse": True,
                    "too_flat": True,
                    "usable_for_momentum": False,
                    "notes": "missing_sentiment_columns",
                }
            )
            continue

        article_count = pd.to_numeric(frame["sentiment_news_count_1d"], errors="coerce").fillna(0.0)
        average = pd.to_numeric(frame["sentiment_average_1d"], errors="coerce").fillna(0.0)
        weighted = pd.to_numeric(frame["sentiment_weighted_1d"], errors="coerce").fillna(0.0)
        article_day_ratio = float((article_count > 0).mean()) if len(frame) else 0.0
        avg_std = float(average.std()) if len(frame) > 1 else 0.0
        weighted_std = float(weighted.std()) if len(frame) > 1 else 0.0
        avg_change_ratio = float(average.diff().abs().gt(1e-9).mean()) if len(frame) > 1 else 0.0
        weighted_change_ratio = float(weighted.diff().abs().gt(1e-9).mean()) if len(frame) > 1 else 0.0
        too_sparse = bool(article_count.sum() <= 0 or article_day_ratio < 0.08 or (article_count > 0).sum() < 3)
        too_flat = bool(max(avg_std, weighted_std) < 0.03 or max(avg_change_ratio, weighted_change_ratio) < 0.08)
        usable_for_momentum = not too_sparse and not too_flat
        note_tokens = []
        if too_sparse:
            note_tokens.append("sparse")
        if too_flat:
            note_tokens.append("flat")
        if not note_tokens:
            note_tokens.append("informative")
        rows.append(
            {
                "ticker": ticker,
                "rows": int(len(frame)),
                "has_sentiment_columns": True,
                "article_day_count": int((article_count > 0).sum()),
                "article_count_total": float(article_count.sum()),
                "article_day_ratio": round(article_day_ratio, 6),
                "sentiment_average_std": round(avg_std, 6),
                "sentiment_weighted_std": round(weighted_std, 6),
                "sentiment_average_change_ratio": round(avg_change_ratio, 6),
                "sentiment_weighted_change_ratio": round(weighted_change_ratio, 6),
                "too_sparse": bool(too_sparse),
                "too_flat": bool(too_flat),
                "usable_for_momentum": bool(usable_for_momentum),
                "notes": ",".join(note_tokens),
            }
        )

    relevance_df = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    ticker_count = int(len(relevance_df))
    informative_count = int(relevance_df["usable_for_momentum"].sum()) if not relevance_df.empty else 0
    sparse_count = int(relevance_df["too_sparse"].sum()) if not relevance_df.empty else 0
    flat_count = int(relevance_df["too_flat"].sum()) if not relevance_df.empty else 0
    no_article_count = int((relevance_df["article_count_total"] <= 0).sum()) if not relevance_df.empty else 0
    verdict = (
        "sentiment_feature_not_informative_enough_yet"
        if ticker_count == 0 or informative_count < max(3, math.ceil(ticker_count * 0.5))
        else "sentiment_feature_has_partial_signal"
    )
    payload = {
        "generated_at": generated_at,
        "ticker_count": ticker_count,
        "informative_ticker_count": informative_count,
        "sparse_ticker_count": sparse_count,
        "flat_ticker_count": flat_count,
        "no_article_ticker_count": no_article_count,
        "article_day_ratio_mean": round(float(relevance_df["article_day_ratio"].mean()) if not relevance_df.empty else 0.0, 6),
        "sentiment_average_std_mean": round(float(relevance_df["sentiment_average_std"].mean()) if not relevance_df.empty else 0.0, 6),
        "sentiment_weighted_std_mean": round(float(relevance_df["sentiment_weighted_std"].mean()) if not relevance_df.empty else 0.0, 6),
        "sentiment_average_change_ratio_mean": round(float(relevance_df["sentiment_average_change_ratio"].mean()) if not relevance_df.empty else 0.0, 6),
        "sentiment_weighted_change_ratio_mean": round(float(relevance_df["sentiment_weighted_change_ratio"].mean()) if not relevance_df.empty else 0.0, 6),
        "verdict": verdict,
        "item7_readiness_context": {
            "valid_ticker_count": safe_dict(item7_readiness).get("valid_ticker_count"),
            "unusable_ticker_count": safe_dict(item7_readiness).get("unusable_ticker_count"),
            "dataset_is_item7_ready": safe_dict(item7_readiness).get("dataset_is_item7_ready"),
        },
    }
    return relevance_df, payload


def build_redesign_decision(
    overlap_audit: Dict[str, object],
    trade_design_audit: Dict[str, object],
    sample_coverage_summary: Dict[str, object],
    sentiment_summary: Dict[str, object],
    generated_at: str,
) -> Dict[str, object]:
    diagnosis_flags = safe_dict(trade_design_audit.get("diagnosis_flags"))
    primary_failure_mode = "baseline usable as-is"
    secondary_failure_modes: List[str] = []
    minimum_required_changes: List[str] = []

    if bool(diagnosis_flags.get("baseline_needs_entry_exit_redesign")):
        primary_failure_mode = "baseline needs entry/exit redesign"
        minimum_required_changes.extend(
            [
                "Rekalibrasi hold period baseline ke opsi dengan coverage terbaik dari audit.",
                "Turunkan ketergantungan pada trade floor saat coverage riil belum memadai.",
                "Review ulang aturan entry baseline agar trade retention tidak collapse terhadap baseline lama.",
            ]
        )
    elif bool(diagnosis_flags.get("baseline_usable_but_needs_scoring_eval_redesign")):
        primary_failure_mode = "baseline usable but needs scoring/eval redesign"
        minimum_required_changes.extend(
            [
                "Kalibrasi ulang scoring dan success criteria agar tidak terlalu sensitif pada sampel kecil.",
                "Pisahkan evaluasi coverage versus evaluasi quality supaya no-go tidak ditentukan hanya oleh sedikit trade.",
            ]
        )

    if str(sentiment_summary.get("verdict")) == "sentiment_feature_not_informative_enough_yet":
        secondary_failure_modes.append("sentiment feature not informative enough yet")
        minimum_required_changes.append(
            "Gunakan sentiment hanya setelah audit sparsity/flatness menunjukkan sinyal harian cukup berubah."
        )

    item8_overlap = safe_dict(safe_dict(overlap_audit.get("overlap_assessment")).get("item8"))
    if str(item8_overlap.get("overlap_level")) == "high":
        secondary_failure_modes.append("adaptive search space too narrow or redundant")
        minimum_required_changes.append(
            "Perlebar dan bersihkan adaptive search space setelah baseline stabil, bukan bersamaan."
        )

    if primary_failure_mode == "baseline usable as-is" and secondary_failure_modes:
        primary_failure_mode = secondary_failure_modes[0]

    if primary_failure_mode == "baseline needs entry/exit redesign":
        recommended_track = "baseline_trade_design_first"
        next_experiment = "retry_baseline_with_hold_period_labeling_redesign"
        can_retry = True
    elif primary_failure_mode == "baseline usable but needs scoring/eval redesign":
        recommended_track = "scoring_eval_recalibration"
        next_experiment = "retry_baseline_with_scoring_eval_redesign"
        can_retry = True
    elif primary_failure_mode == "sentiment feature not informative enough yet":
        recommended_track = "sentiment_signal_quality_first"
        next_experiment = "no_retry_yet_until_baseline_revised"
        can_retry = False
    elif primary_failure_mode == "adaptive search space too narrow or redundant":
        recommended_track = "adaptive_space_cleanup_after_baseline"
        next_experiment = "retry_item8_with_cleaner_search_space"
        can_retry = True
    else:
        recommended_track = "baseline_usable_no_major_redesign"
        next_experiment = "retry_phase_b_smallest_failure_case"
        can_retry = True

    minimum_required_changes = dedupe(minimum_required_changes)[:5]
    payload = {
        "generated_at": generated_at,
        "primary_failure_mode": primary_failure_mode,
        "secondary_failure_modes": dedupe(secondary_failure_modes)[:4],
        "recommended_redesign_track": recommended_track,
        "can_retry_phase_b_after_redesign": bool(can_retry),
        "minimum_required_changes": minimum_required_changes,
        "next_experiment_after_redesign": next_experiment,
        "supporting_signals": {
            "overall_overlap_risk": overlap_audit.get("overall_overlap_risk"),
            "current_floor_is_too_strict": sample_coverage_summary.get("current_floor_is_too_strict"),
            "recommended_realistic_min_trades": sample_coverage_summary.get("recommended_realistic_min_trades"),
            "sentiment_verdict": sentiment_summary.get("verdict"),
        },
    }
    return payload


def build_next_best_experiment(
    redesign_decision: Dict[str, object],
    trade_design_audit: Dict[str, object],
    sample_coverage_summary: Dict[str, object],
    sentiment_summary: Dict[str, object],
    generated_at: str,
) -> Dict[str, object]:
    primary_mode = str(redesign_decision.get("primary_failure_mode"))
    best_hold = trade_design_audit.get("best_hold_period_for_coverage")
    realistic_min_trades = sample_coverage_summary.get("recommended_realistic_min_trades")

    if primary_mode == "baseline needs entry/exit redesign":
        experiment_code = "retry_baseline_with_hold_period_labeling_redesign"
        summary = (
            "Ulang baseline saja dengan hold period hasil audit dan trade floor yang lebih realistis; jangan tambah sentiment/adaptive dulu."
        )
        can_start = True
    elif primary_mode == "baseline usable but needs scoring/eval redesign":
        experiment_code = "retry_baseline_with_scoring_eval_redesign"
        summary = "Ulang baseline dengan scoring dan success criteria baru sebelum mencoba filter tambahan."
        can_start = True
    elif primary_mode == "adaptive search space too narrow or redundant":
        experiment_code = "retry_item8_with_cleaner_search_space"
        summary = "Ulang adaptive hanya setelah baseline stabil dan search space dibersihkan dari konfigurasi redundant."
        can_start = True
    elif primary_mode == "sentiment feature not informative enough yet":
        experiment_code = "no_retry_yet_until_baseline_revised"
        summary = "Jangan ulang item 7 dulu; revisi baseline dan audit sentiment relevance lebih dulu."
        can_start = False
    else:
        experiment_code = "retry_phase_b_smallest_failure_case"
        summary = "Pilih retry terkecil dengan perubahan tunggal setelah redesign minimum selesai."
        can_start = True

    payload = {
        "generated_at": generated_at,
        "selected_experiment_code": experiment_code,
        "can_start_immediately_after_redesign": bool(can_start),
        "summary": summary,
        "proposed_runtime": {
            "hold_period": best_hold,
            "min_trades": realistic_min_trades,
        },
        "why_this_is_best_next": (
            "Baseline tetap menjadi blocker paling hulu; memperbaiki trade design lebih dulu memberi nilai informasi paling tinggi."
            if experiment_code.startswith("retry_baseline")
            else "Eksperimen ini dipilih karena paling langsung menyerang failure mode primer."
        ),
        "why_not_item7_yet": (
            "Sentiment belum cukup informatif pada banyak ticker."
            if str(sentiment_summary.get("verdict")) == "sentiment_feature_not_informative_enough_yet"
            else "Item 7 tetap ditunda sampai fondasi baseline stabil."
        ),
        "why_not_item8_yet": "Adaptive search space masih redundant terhadap baseline atau belum usable.",
    }
    return payload


def run_phase_b_v2_redesign_diagnostics(
    data_dir: Path,
    output_dir: Path,
    baseline_config: Optional[Path],
    metadata_file: Optional[Path],
    hold_period_options: Sequence[int],
    min_trades_options: Sequence[int],
) -> Dict[str, object]:
    generated_at = _now_iso()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = Path(data_dir)

    baseline_payload, baseline_warnings, baseline_path = load_phase_a_baseline(baseline_config=baseline_config)
    metadata_lookup, metadata_warnings = load_optional_metadata_lookup(metadata_file)
    phase_b_artifacts = _load_phase_b_artifacts(output_dir)
    price_files = _resolve_price_csv_files(data_dir)

    overlap_audit = build_overlap_audit(
        baseline_config=baseline_payload,
        metadata_lookup=metadata_lookup,
        price_files=price_files,
        phase_b_artifacts=phase_b_artifacts,
        generated_at=generated_at,
    )
    hold_results, hold_summaries = _evaluate_hold_matrix(
        data_dir=data_dir,
        baseline_config_path=baseline_path,
        metadata_file=metadata_file,
        hold_period_options=hold_period_options,
    )
    trade_design_audit = build_trade_design_audit(
        hold_results=hold_results,
        min_trades_options=min_trades_options,
        baseline_min_trades_floor=_safe_int(baseline_payload.get("min_trades_floor"), 8),
        generated_at=generated_at,
    )
    sample_coverage_df, sample_coverage_summary = build_sample_coverage(
        hold_summaries=hold_summaries,
        min_trades_options=min_trades_options,
        baseline_min_trades_floor=_safe_int(baseline_payload.get("min_trades_floor"), 8),
        generated_at=generated_at,
    )
    sentiment_df, sentiment_summary = build_sentiment_relevance(
        price_files=price_files,
        item7_readiness=safe_dict(phase_b_artifacts.get("item7_data_readiness")),
        generated_at=generated_at,
    )
    redesign_decision = build_redesign_decision(
        overlap_audit=overlap_audit,
        trade_design_audit=trade_design_audit,
        sample_coverage_summary=sample_coverage_summary,
        sentiment_summary=sentiment_summary,
        generated_at=generated_at,
    )
    next_best_experiment = build_next_best_experiment(
        redesign_decision=redesign_decision,
        trade_design_audit=trade_design_audit,
        sample_coverage_summary=sample_coverage_summary,
        sentiment_summary=sentiment_summary,
        generated_at=generated_at,
    )

    overlap_audit["warnings"] = dedupe(
        [*list(overlap_audit.get("warnings") or []), *baseline_warnings, *metadata_warnings]
    )
    trade_design_audit["warnings"] = dedupe([*baseline_warnings, *metadata_warnings])
    sample_coverage_summary["warnings"] = dedupe([*baseline_warnings, *metadata_warnings])
    sentiment_summary["warnings"] = dedupe([*baseline_warnings, *metadata_warnings])

    _write_json(output_dir / "phase_b_v2_overlap_audit.json", overlap_audit)
    _write_text(
        output_dir / "phase_b_v2_overlap_audit.txt",
        [
            "Phase B v2 Overlap Audit",
            "========================",
            "",
            f"- Generated at: {generated_at}",
            f"- Baseline threshold: {baseline_payload.get('default_volume_spike_threshold')}",
            f"- Baseline strict mode: {baseline_payload.get('strict_mode_default')}",
            f"- Overall overlap risk: {overlap_audit['overall_overlap_risk']}",
            f"- Conclusion: {overlap_audit['overall_conclusion']}",
            "",
            "Item findings:",
            f"- item5 overlap={safe_dict(overlap_audit['overlap_assessment']).get('item5', {}).get('overlap_level')}",
            f"- item6 overlap={safe_dict(overlap_audit['overlap_assessment']).get('item6', {}).get('overlap_level')}",
            f"- item7 overlap={safe_dict(overlap_audit['overlap_assessment']).get('item7', {}).get('overlap_level')}",
            f"- item8 overlap={safe_dict(overlap_audit['overlap_assessment']).get('item8', {}).get('overlap_level')}",
        ],
    )

    _write_json(output_dir / "phase_b_v2_trade_design_audit.json", trade_design_audit)
    trade_lines = [
        "Phase B v2 Trade Design Audit",
        "=============================",
        "",
        f"- Generated at: {generated_at}",
        f"- Current hold period: {trade_design_audit['current_hold_period']}",
        f"- Baseline min trades floor: {trade_design_audit['baseline_min_trades_floor']}",
        f"- Best hold for coverage: {trade_design_audit['best_hold_period_for_coverage']}",
        f"- Conclusion: {trade_design_audit['conclusion']}",
        "",
        "Hold diagnostics:",
    ]
    for item in list(trade_design_audit.get("hold_period_diagnostics") or []):
        trade_lines.append(
            f"- hold={item['hold_period']} | trades_sum={item['phase_a_total_trades_sum']} | "
            f"retention={item['trade_retention_vs_baseline_pct']} | "
            f"eligible@floor={safe_dict(item['eligible_ticker_count_by_min_trades']).get(str(trade_design_audit['baseline_min_trades_floor']))}"
        )
    _write_text(output_dir / "phase_b_v2_trade_design_audit.txt", trade_lines)

    sample_coverage_df.to_csv(output_dir / "phase_b_v2_sample_coverage.csv", index=False)
    _write_json(output_dir / "phase_b_v2_sample_coverage_summary.json", sample_coverage_summary)

    sentiment_df.to_csv(output_dir / "phase_b_v2_sentiment_relevance.csv", index=False)
    _write_json(output_dir / "phase_b_v2_sentiment_relevance_summary.json", sentiment_summary)
    sentiment_lines = [
        "Phase B v2 Sentiment Relevance",
        "==============================",
        "",
        f"- Generated at: {generated_at}",
        f"- Verdict: {sentiment_summary['verdict']}",
        f"- Informative tickers: {sentiment_summary['informative_ticker_count']}/{sentiment_summary['ticker_count']}",
        f"- Sparse tickers: {sentiment_summary['sparse_ticker_count']}",
        f"- Flat tickers: {sentiment_summary['flat_ticker_count']}",
        f"- No article tickers: {sentiment_summary['no_article_ticker_count']}",
    ]
    _write_text(output_dir / "phase_b_v2_sentiment_relevance_report.txt", sentiment_lines)

    _write_json(output_dir / "phase_b_v2_redesign_decision.json", redesign_decision)
    _write_text(
        output_dir / "phase_b_v2_redesign_decision.txt",
        [
            "Phase B v2 Redesign Decision",
            "============================",
            "",
            f"- Generated at: {generated_at}",
            f"- Primary failure mode: {redesign_decision['primary_failure_mode']}",
            f"- Recommended redesign track: {redesign_decision['recommended_redesign_track']}",
            f"- Can retry Phase B after redesign: {redesign_decision['can_retry_phase_b_after_redesign']}",
            f"- Next experiment after redesign: {redesign_decision['next_experiment_after_redesign']}",
            "",
            "Minimum required changes:",
            *[f"- {item}" for item in list(redesign_decision.get("minimum_required_changes") or [])],
        ],
    )

    _write_json(output_dir / "phase_b_v2_next_best_experiment.json", next_best_experiment)
    _write_text(
        output_dir / "phase_b_v2_next_best_experiment.txt",
        [
            "Phase B v2 Next Best Experiment",
            "===============================",
            "",
            f"- Generated at: {generated_at}",
            f"- Selected experiment: {next_best_experiment['selected_experiment_code']}",
            f"- Can start immediately after redesign: {next_best_experiment['can_start_immediately_after_redesign']}",
            f"- Summary: {next_best_experiment['summary']}",
            f"- Proposed hold period: {safe_dict(next_best_experiment.get('proposed_runtime')).get('hold_period')}",
            f"- Proposed min trades: {safe_dict(next_best_experiment.get('proposed_runtime')).get('min_trades')}",
        ],
    )

    return {
        "overlap_audit": overlap_audit,
        "trade_design_audit": trade_design_audit,
        "sample_coverage_summary": sample_coverage_summary,
        "sentiment_summary": sentiment_summary,
        "redesign_decision": redesign_decision,
        "next_best_experiment": next_best_experiment,
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Phase B v2 minimum redesign diagnostics."
    )
    parser.add_argument("--data-dir", default="data", help="Directory containing real per-ticker CSV files.")
    parser.add_argument("--output-dir", default="output", help="Directory containing and receiving artifacts.")
    parser.add_argument(
        "--baseline-config",
        default="output/phase_a_baseline_final.json",
        help="Path to frozen baseline config JSON.",
    )
    parser.add_argument(
        "--metadata-file",
        default="data/ticker_metadata.csv",
        help="Optional metadata CSV path.",
    )
    parser.add_argument(
        "--hold-period-options",
        nargs="+",
        type=int,
        default=[3, 5, 7],
        help="Hold period options to diagnose. Default: 3 5 7",
    )
    parser.add_argument(
        "--min-trades-options",
        nargs="+",
        type=int,
        default=[5, 8, 10],
        help="Min trades options to diagnose. Default: 5 8 10",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    result = run_phase_b_v2_redesign_diagnostics(
        data_dir=Path(args.data_dir),
        output_dir=Path(args.output_dir),
        baseline_config=Path(args.baseline_config) if args.baseline_config else None,
        metadata_file=Path(args.metadata_file) if args.metadata_file else None,
        hold_period_options=args.hold_period_options,
        min_trades_options=args.min_trades_options,
    )
    print(f"Primary failure mode: {result['redesign_decision']['primary_failure_mode']}")
    print(f"Next experiment: {result['next_best_experiment']['selected_experiment_code']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
