"""Review guardrail eligibility/sample fit and universe segmentation for baseline v6."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant.phase_a_transition_utils import dedupe, read_json_object, safe_dict  # noqa: E402


REVIEW_JSON_OUTPUT = "baseline_v6_guardrail_review.json"
REVIEW_TEXT_OUTPUT = "baseline_v6_guardrail_review.txt"
SCENARIO_CSV_OUTPUT = "baseline_v6_guardrail_scenarios.csv"
SEGMENTATION_CSV_OUTPUT = "baseline_v6_universe_segmentation.csv"
SEGMENT_RECOMMENDATIONS_OUTPUT = "baseline_v6_segment_recommendations.json"
GOVERNANCE_OUTPUT = "baseline_v6_next_experiment_governance.json"

RECOMMENDED_GUARDRAIL_MODES = {
    "keep_global_guardrail",
    "relax_guardrail_slightly",
    "move_to_segment_aware_guardrail",
    "stop_and_collect_more_data",
}
RECOMMENDED_UNIVERSE_MODES = {
    "keep_current_universe",
    "test_only_high_coverage_segment",
    "split_universe_before_next_experiment",
    "collect_more_data_before_any_new_test",
}
DECISION_STATUSES = {
    "no_go",
    "keep_experimental",
    "keep_experimental_for_segment_review",
    "insufficient_segment",
}
GLOBAL_SEGMENT_LABEL = "__global__"
SEGMENT_FIELDS = [
    "news_segment",
    "sentiment_segment",
    "liquidity_segment",
    "volatility_segment",
    "sector",
    "category",
]


class BaselineV6GuardrailReviewCliError(ValueError):
    """Friendly CLI error for the v6 guardrail review."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        if value is None:
            return int(default)
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _safe_str(value: object, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _round_or_none(value: Optional[float], digits: int = 5) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return round(float(value), digits)


def _sanitize_for_json(value: object) -> object:
    if isinstance(value, dict):
        return {key: _sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_for_json(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if pd.isna(value) else float(value)
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


def _load_context_artifacts(output_dir: Path) -> Dict[str, object]:
    artifact_map = {
        "root_cause_postmortem": "baseline_root_cause_postmortem.json",
        "next_experiment_plan": "baseline_next_experiment_plan.json",
        "baseline_v2_validation": "baseline_v2_validation.json",
        "baseline_v3_summary": "baseline_v3_signal_rule_summary.json",
        "baseline_v4_summary": "baseline_v4_quality_gate_summary.json",
        "baseline_v5_summary": "baseline_v5_exit_hold_summary.json",
        "roadmap": "project_roadmap_status.json",
    }
    payloads: Dict[str, object] = {}
    warnings: List[str] = []
    missing: List[str] = []
    for key, filename in artifact_map.items():
        payload, item_warnings = read_json_object(Path(output_dir) / filename, filename)
        payloads[key] = payload if isinstance(payload, dict) else {}
        warnings.extend(item_warnings)
        if payload is None:
            missing.append(filename)
    payloads["warnings"] = dedupe(warnings)
    payloads["missing_artifacts"] = missing
    return payloads


def _load_metadata_frame(metadata_file: Optional[Path]) -> Tuple[pd.DataFrame, List[str]]:
    warnings: List[str] = []
    if metadata_file is None:
        warnings.append("Metadata file not provided. Segmentasi hanya memakai data CSV aktual.")
        return pd.DataFrame(), warnings

    path = Path(metadata_file)
    if not path.exists() or not path.is_file():
        warnings.append(f"Metadata file not found: {path}. Segmentasi hanya memakai data CSV aktual.")
        return pd.DataFrame(), warnings

    try:
        metadata_df = pd.read_csv(path)
    except Exception as exc:
        warnings.append(f"Failed to read metadata file {path}: {exc}. Segmentasi hanya memakai data CSV aktual.")
        return pd.DataFrame(), warnings

    if metadata_df.empty or "ticker" not in metadata_df.columns:
        warnings.append(f"Metadata file {path} tidak punya kolom ticker yang usable.")
        return pd.DataFrame(), warnings

    frame = metadata_df.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    frame = frame.drop_duplicates(subset=["ticker"], keep="first")
    return frame, warnings


def _rank_three_way(series: pd.Series, low_label: str, mid_label: str, high_label: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    output = pd.Series(index=series.index, dtype="object")
    non_null = values.dropna()
    if non_null.empty:
        output.loc[:] = "unknown"
        return output
    if non_null.nunique() == 1:
        token = low_label if float(non_null.iloc[0]) <= 0 else mid_label
        output.loc[:] = token
        return output

    percent_rank = non_null.rank(method="average", pct=True)
    output.loc[percent_rank.index] = np.where(
        percent_rank <= (1.0 / 3.0),
        low_label,
        np.where(percent_rank <= (2.0 / 3.0), mid_label, high_label),
    )
    output = output.fillna("unknown")
    return output


def _binary_split(series: pd.Series, high_label: str, low_label: str) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    output = pd.Series(index=series.index, dtype="object")
    non_null = values.dropna()
    if non_null.empty:
        output.loc[:] = "unknown"
        return output
    threshold = float(non_null.median())
    output.loc[non_null.index] = np.where(non_null >= threshold, high_label, low_label)
    output = output.fillna("unknown")
    return output


def _extract_article_series(frame: pd.DataFrame, metadata_row: Dict[str, object]) -> Tuple[float, int, List[str]]:
    warnings: List[str] = []
    if "sentiment_news_count_1d" in frame.columns:
        news_counts = pd.to_numeric(frame["sentiment_news_count_1d"], errors="coerce").fillna(0.0)
        return float(news_counts.sum()), int(news_counts.gt(0).sum()), warnings

    article_total = metadata_row.get("sentiment_article_count_total")
    article_days = metadata_row.get("sentiment_days_with_articles")
    if article_total is not None or article_days is not None:
        return _safe_float(article_total), _safe_int(article_days), warnings

    warnings.append("sentiment_news_count_1d not available in dataset and metadata lacks article coverage fields.")
    return 0.0, 0, warnings


def _scan_universe(data_dir: Path, metadata_df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str], List[str]]:
    warnings: List[str] = []
    limitations: List[str] = []
    metadata_lookup = (
        metadata_df.set_index("ticker").to_dict(orient="index")
        if not metadata_df.empty and "ticker" in metadata_df.columns
        else {}
    )

    rows: List[Dict[str, object]] = []
    data_dir = Path(data_dir)
    for path in sorted(data_dir.glob("*.csv")):
        if path.name == "ticker_metadata.csv":
            continue
        ticker = path.stem.upper()
        try:
            frame = pd.read_csv(path)
        except Exception as exc:
            warnings.append(f"Failed to read dataset {path}: {exc}.")
            continue

        metadata_row = dict(metadata_lookup.get(ticker) or {})
        close_series = pd.to_numeric(frame.get("close"), errors="coerce")
        volume_series = pd.to_numeric(frame.get("volume"), errors="coerce")
        returns = close_series.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
        article_count_total, article_days, article_warnings = _extract_article_series(frame=frame, metadata_row=metadata_row)
        warnings.extend([f"{ticker}: {item}" for item in article_warnings])

        date_start = None
        date_end = None
        if "date" in frame.columns and not frame["date"].empty:
            try:
                dates = pd.to_datetime(frame["date"], errors="coerce")
                if dates.notna().any():
                    date_start = str(dates.min().date())
                    date_end = str(dates.max().date())
            except Exception:
                pass

        rows.append(
            {
                "ticker": ticker,
                "rows": int(len(frame)),
                "date_start": date_start,
                "date_end": date_end,
                "mean_volume": _round_or_none(float(volume_series.mean())) if volume_series.notna().any() else None,
                "median_volume": _round_or_none(float(volume_series.median())) if volume_series.notna().any() else None,
                "return_volatility_pct": _round_or_none(float(returns.std(ddof=0) * 100.0)),
                "article_count_total": _round_or_none(article_count_total),
                "article_days": int(article_days),
                "news_density_pct": _round_or_none((article_days / max(len(frame), 1)) * 100.0),
                "sector": metadata_row.get("sector"),
                "category": metadata_row.get("category"),
                "company_name": metadata_row.get("company_name"),
            }
        )

    if not rows:
        raise BaselineV6GuardrailReviewCliError(f"No usable ticker CSV files found in {data_dir}.")

    universe_df = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    universe_df["news_segment"] = _rank_three_way(
        universe_df["article_count_total"], "low_news", "mid_news", "high_news"
    )
    universe_df["sentiment_segment"] = _binary_split(
        universe_df["article_days"], "sentiment_rich", "sentiment_poor"
    )
    universe_df["liquidity_segment"] = _binary_split(
        universe_df["median_volume"], "liquid_active", "thin_sparse"
    )
    universe_df["volatility_segment"] = _rank_three_way(
        universe_df["return_volatility_pct"], "lower_volatility", "mixed_volatility", "higher_volatility"
    )

    if metadata_df.empty:
        limitations.append("Metadata tidak tersedia; segmentasi sektor dan kategori bisa kosong.")
    else:
        if "sector" not in metadata_df.columns:
            limitations.append("Metadata tidak punya kolom sector; evaluasi sektor dibatasi.")
        if "category" not in metadata_df.columns:
            limitations.append("Metadata tidak punya kolom category; evaluasi category dibatasi.")

    if universe_df["article_count_total"].fillna(0.0).sum() <= 0:
        limitations.append("Dataset tidak menunjukkan coverage berita yang usable; segment news/sentiment terbatas.")
    if universe_df["median_volume"].isna().all():
        limitations.append("Dataset tidak punya volume usable; segment liquidity terbatas.")
    if universe_df["rows"].nunique() <= 1:
        limitations.append("Seluruh ticker punya panjang seri yang mirip; segment panjang data tidak informatif.")

    return universe_df, dedupe(warnings), dedupe(limitations)


def _candidate_global_snapshot(stage: str, context_payloads: Dict[str, object]) -> Dict[str, object]:
    if stage == "baseline_v2":
        payload = safe_dict(context_payloads.get("baseline_v2_validation"))
        return {
            "candidate_id": payload.get("candidate_id"),
            "eligible_ticker_count": payload.get("eligible_ticker_count"),
            "total_trades_sum": payload.get("total_trades_sum"),
            "mean_average_return": payload.get("average_return"),
            "quality_preserved": payload.get("score_ok"),
            "source_artifact": "baseline_v2_validation.json",
        }

    if stage == "baseline_v3":
        payload = safe_dict(context_payloads.get("baseline_v3_summary"))
        best = safe_dict(payload.get("best_v3_rule"))
        return {
            "candidate_id": best.get("candidate_id"),
            "eligible_ticker_count": best.get("eligible_ticker_count"),
            "total_trades_sum": best.get("total_trades_sum"),
            "mean_average_return": best.get("mean_average_return"),
            "quality_preserved": best.get("quality_preserved"),
            "source_artifact": "baseline_v3_signal_rule_summary.json",
        }

    if stage == "baseline_v4":
        payload = safe_dict(context_payloads.get("baseline_v4_summary"))
        best = safe_dict(payload.get("best_v4_candidate_summary"))
        go_no_go = safe_dict(payload.get("go_no_go"))
        return {
            "candidate_id": best.get("candidate_id"),
            "eligible_ticker_count": best.get("eligible_ticker_count"),
            "total_trades_sum": best.get("total_trades_sum"),
            "mean_average_return": best.get("mean_average_return"),
            "quality_preserved": go_no_go.get("quality_preserved"),
            "source_artifact": "baseline_v4_quality_gate_summary.json",
        }

    if stage == "baseline_v5":
        payload = safe_dict(context_payloads.get("baseline_v5_summary"))
        best = safe_dict(payload.get("best_v5_candidate_summary"))
        go_no_go = safe_dict(payload.get("go_no_go"))
        return {
            "candidate_id": best.get("candidate_id"),
            "eligible_ticker_count": best.get("eligible_ticker_count"),
            "total_trades_sum": best.get("total_trades_sum"),
            "mean_average_return": best.get("mean_average_return"),
            "quality_preserved": go_no_go.get("quality_preserved"),
            "source_artifact": "baseline_v5_exit_hold_summary.json",
        }

    return {}


def _load_v2_candidate_frame(output_dir: Path) -> Tuple[Optional[pd.DataFrame], List[str]]:
    warnings: List[str] = []
    path = Path(output_dir) / "baseline_v2_validation_per_ticker.csv"
    if not path.exists():
        warnings.append(f"baseline_v2 per-ticker results not found: {path}.")
        return None, warnings

    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        warnings.append(f"Failed to read {path}: {exc}.")
        return None, warnings

    if frame.empty:
        warnings.append(f"baseline_v2 per-ticker results are empty: {path}.")
        return None, warnings

    required = [
        "ticker",
        "candidate_id",
        "candidate_total_trades",
        "candidate_eligible_for_analysis",
        "candidate_average_return",
        "candidate_score",
        "min_trades_threshold",
    ]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        warnings.append(f"{path} missing required columns: {', '.join(missing)}.")
        return None, warnings

    result = frame[
        [
            "ticker",
            "candidate_id",
            "candidate_total_trades",
            "candidate_eligible_for_analysis",
            "candidate_average_return",
            "candidate_score",
            "min_trades_threshold",
        ]
    ].copy()
    result.rename(
        columns={
            "candidate_average_return": "average_return",
            "candidate_score": "score",
        },
        inplace=True,
    )
    result["experiment_stage"] = "baseline_v2"
    result["comparison_role"] = "candidate"
    result["source_results_file"] = path.name
    return result, warnings


def _load_standard_candidate_frame(
    output_dir: Path,
    results_file: str,
    id_column: str,
    candidate_id: str,
    experiment_stage: str,
) -> Tuple[Optional[pd.DataFrame], List[str]]:
    warnings: List[str] = []
    path = Path(output_dir) / results_file
    if not candidate_id:
        warnings.append(f"No candidate_id resolved for {experiment_stage}.")
        return None, warnings
    if not path.exists():
        warnings.append(f"Candidate results not found: {path}.")
        return None, warnings

    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        warnings.append(f"Failed to read {path}: {exc}.")
        return None, warnings

    if frame.empty:
        warnings.append(f"Candidate results are empty: {path}.")
        return None, warnings
    if id_column not in frame.columns:
        warnings.append(f"{path} does not contain {id_column}.")
        return None, warnings

    subset = frame.loc[frame[id_column].astype(str).eq(str(candidate_id))].copy()
    if subset.empty:
        warnings.append(f"{path} does not contain candidate {candidate_id}.")
        return None, warnings

    required = [
        "ticker",
        "candidate_total_trades",
        "candidate_eligible_for_analysis",
        "average_return",
        "score",
        "min_trades_threshold",
    ]
    missing = [column for column in required if column not in subset.columns]
    if missing:
        warnings.append(f"{path} missing required columns: {', '.join(missing)}.")
        return None, warnings

    result = subset[required].copy()
    result["candidate_id"] = str(candidate_id)
    result["experiment_stage"] = experiment_stage
    result["comparison_role"] = "candidate"
    result["source_results_file"] = path.name
    return result, warnings


def _load_candidate_frames(output_dir: Path, context_payloads: Dict[str, object]) -> Tuple[List[Dict[str, object]], List[str]]:
    warnings: List[str] = []
    candidates: List[Dict[str, object]] = []

    v2_frame, v2_warnings = _load_v2_candidate_frame(output_dir=output_dir)
    warnings.extend(v2_warnings)
    if v2_frame is not None:
        candidate_id = _safe_str(v2_frame["candidate_id"].iloc[0])
        candidates.append(
            {
                "experiment_stage": "baseline_v2",
                "candidate_id": candidate_id,
                "global_snapshot": _candidate_global_snapshot("baseline_v2", context_payloads),
                "frame": v2_frame,
            }
        )

    v3_summary = safe_dict(context_payloads.get("baseline_v3_summary"))
    v3_candidate = _safe_str(safe_dict(v3_summary.get("best_v3_rule")).get("candidate_id"))
    v3_frame, v3_warnings = _load_standard_candidate_frame(
        output_dir=output_dir,
        results_file="baseline_v3_signal_rule_results.csv",
        id_column="rule_id",
        candidate_id=v3_candidate,
        experiment_stage="baseline_v3",
    )
    warnings.extend(v3_warnings)
    if v3_frame is not None:
        candidates.append(
            {
                "experiment_stage": "baseline_v3",
                "candidate_id": v3_candidate,
                "global_snapshot": _candidate_global_snapshot("baseline_v3", context_payloads),
                "frame": v3_frame,
            }
        )

    v4_summary = safe_dict(context_payloads.get("baseline_v4_summary"))
    v4_candidate = _safe_str(safe_dict(v4_summary.get("best_v4_candidate_summary")).get("candidate_id"))
    v4_frame, v4_warnings = _load_standard_candidate_frame(
        output_dir=output_dir,
        results_file="baseline_v4_quality_gate_results.csv",
        id_column="variant_id",
        candidate_id=v4_candidate,
        experiment_stage="baseline_v4",
    )
    warnings.extend(v4_warnings)
    if v4_frame is not None:
        candidates.append(
            {
                "experiment_stage": "baseline_v4",
                "candidate_id": v4_candidate,
                "global_snapshot": _candidate_global_snapshot("baseline_v4", context_payloads),
                "frame": v4_frame,
            }
        )

    v5_summary = safe_dict(context_payloads.get("baseline_v5_summary"))
    v5_candidate = _safe_str(safe_dict(v5_summary.get("best_v5_candidate_summary")).get("candidate_id"))
    v5_frame, v5_warnings = _load_standard_candidate_frame(
        output_dir=output_dir,
        results_file="baseline_v5_exit_hold_results.csv",
        id_column="variant_id",
        candidate_id=v5_candidate,
        experiment_stage="baseline_v5",
    )
    warnings.extend(v5_warnings)
    if v5_frame is not None:
        candidates.append(
            {
                "experiment_stage": "baseline_v5",
                "candidate_id": v5_candidate,
                "global_snapshot": _candidate_global_snapshot("baseline_v5", context_payloads),
                "frame": v5_frame,
            }
        )

    return candidates, dedupe(warnings)


def _resolve_current_guardrails(context_payloads: Dict[str, object]) -> Dict[str, object]:
    payload = safe_dict(context_payloads.get("baseline_v2_validation"))
    min_trades_threshold = _safe_int(payload.get("min_trades"), 5) or 5
    min_eligible_tickers = _safe_int(payload.get("min_eligible_tickers_required"), 3) or 3
    minimum_trade_sample = _safe_int(payload.get("minimum_trade_sample_required"), max(15, min_trades_threshold * 3)) or max(
        15, min_trades_threshold * 3
    )
    return {
        "min_trades_threshold": int(min_trades_threshold),
        "min_eligible_tickers": int(min_eligible_tickers),
        "minimum_trade_sample_required": int(minimum_trade_sample),
        "eligible_for_analysis_definition": f"candidate_total_trades >= {int(min_trades_threshold)}",
    }


def _summarize_scope(frame: pd.DataFrame, eligible_trade_floor: int) -> Dict[str, object]:
    eligible_mask = pd.to_numeric(frame["candidate_total_trades"], errors="coerce").fillna(0.0) >= float(eligible_trade_floor)
    average_return_all = _round_or_none(frame["average_return"].mean())
    eligible_returns = frame.loc[eligible_mask, "average_return"]
    average_return_eligible = _round_or_none(eligible_returns.mean()) if not eligible_returns.empty else None
    score_all = _round_or_none(frame["score"].mean())
    sample_gap = (
        _round_or_none(float(average_return_all) - float(average_return_eligible))
        if average_return_all is not None and average_return_eligible is not None
        else None
    )
    outlier_bias_risk = bool(
        (average_return_all is not None and average_return_all > 0 and (average_return_eligible is None or average_return_eligible <= 0))
        or (sample_gap is not None and sample_gap >= 3.0)
    )

    return {
        "ticker_count": int(frame["ticker"].nunique()),
        "eligible_ticker_count": int(eligible_mask.sum()),
        "total_trades_sum": int(pd.to_numeric(frame["candidate_total_trades"], errors="coerce").fillna(0.0).sum()),
        "positive_score_ticker_count": int((pd.to_numeric(frame["score"], errors="coerce").fillna(0.0) > 0).sum()),
        "mean_average_return_all": average_return_all,
        "mean_average_return_eligible": average_return_eligible,
        "mean_score_all": score_all,
        "eligible_trade_floor": int(eligible_trade_floor),
        "supportive_but_ineligible_ticker_count": int(((~eligible_mask) & frame["score"].gt(0)).sum()),
        "positive_return_but_ineligible_ticker_count": int(((~eligible_mask) & frame["average_return"].gt(0)).sum()),
        "sample_skew_gap": sample_gap,
        "outlier_bias_risk": outlier_bias_risk,
    }


def _evaluate_status(
    summary: Dict[str, object],
    min_eligible_tickers: int,
    minimum_trade_sample: int,
    min_segment_tickers: int = 0,
) -> Dict[str, object]:
    ticker_count = _safe_int(summary.get("ticker_count"))
    coverage_ok = _safe_int(summary.get("eligible_ticker_count")) >= int(min_eligible_tickers)
    trade_sample_ok = _safe_int(summary.get("total_trades_sum")) >= int(minimum_trade_sample)
    quality_all_ok = _safe_float(summary.get("mean_average_return_all"), -999.0) > 0.0
    quality_eligible_ok = (
        summary.get("mean_average_return_eligible") is not None
        and _safe_float(summary.get("mean_average_return_eligible"), -999.0) > 0.0
    )
    eligible_definition_supported = _safe_int(summary.get("eligible_ticker_count")) > 0
    outlier_bias_risk = _safe_bool(summary.get("outlier_bias_risk"))

    if min_segment_tickers > 0 and ticker_count < int(min_segment_tickers):
        status = "insufficient_segment"
    elif coverage_ok and trade_sample_ok and quality_all_ok and quality_eligible_ok and not outlier_bias_risk:
        status = "keep_experimental"
    else:
        status = "no_go"

    return {
        "status": status,
        "coverage_ok": coverage_ok,
        "trade_sample_ok": trade_sample_ok,
        "quality_all_ok": quality_all_ok,
        "quality_eligible_ok": quality_eligible_ok,
        "eligible_definition_supported": eligible_definition_supported,
        "outlier_bias_risk": outlier_bias_risk,
    }


def _segment_guardrails(
    segment_ticker_count: int,
    current_guardrails: Dict[str, object],
) -> Optional[Dict[str, int]]:
    if int(segment_ticker_count) < 3:
        return None

    current_min_eligible = _safe_int(current_guardrails.get("min_eligible_tickers"), 3)
    current_min_total = _safe_int(current_guardrails.get("minimum_trade_sample_required"), 15)
    min_eligible = max(2, min(current_min_eligible, int(math.ceil(segment_ticker_count * 0.5))))
    minimum_trade_sample = max(10, min(current_min_total, min_eligible * _safe_int(current_guardrails.get("min_trades_threshold"), 5)))
    return {
        "min_eligible_tickers": int(min_eligible),
        "minimum_trade_sample_required": int(minimum_trade_sample),
    }


def _scenario_current_guardrail(current_guardrails: Dict[str, object]) -> Dict[str, object]:
    return {
        "scenario_id": "scenario_a_current_guardrail",
        "scenario_label": "Current global guardrail",
        "scope": "global",
        "eligible_trade_floor": _safe_int(current_guardrails.get("min_trades_threshold"), 5),
        "min_eligible_tickers": _safe_int(current_guardrails.get("min_eligible_tickers"), 3),
        "minimum_trade_sample_required": _safe_int(current_guardrails.get("minimum_trade_sample_required"), 15),
        "supporting_evidence_rule": False,
    }


def _scenario_relaxed_guardrail(current_guardrails: Dict[str, object]) -> Dict[str, object]:
    current_floor = _safe_int(current_guardrails.get("min_trades_threshold"), 5)
    current_min_eligible = _safe_int(current_guardrails.get("min_eligible_tickers"), 3)
    current_min_total = _safe_int(current_guardrails.get("minimum_trade_sample_required"), 15)
    return {
        "scenario_id": "scenario_b_relaxed_sample_gate",
        "scenario_label": "Relaxed sample gate",
        "scope": "global",
        "eligible_trade_floor": max(4, current_floor - 1),
        "min_eligible_tickers": max(2, current_min_eligible - 1),
        "minimum_trade_sample_required": max(12, current_min_total - 3),
        "supporting_evidence_rule": False,
    }


def _build_scenario_rows(
    candidate_frames: Sequence[Dict[str, object]],
    universe_df: pd.DataFrame,
    current_guardrails: Dict[str, object],
) -> Tuple[pd.DataFrame, Dict[str, List[Dict[str, object]]]]:
    scenario_rows: List[Dict[str, object]] = []
    segment_pass_map: Dict[str, List[Dict[str, object]]] = {}
    base_scenarios = [_scenario_current_guardrail(current_guardrails), _scenario_relaxed_guardrail(current_guardrails)]

    universe_columns = ["ticker", *[field for field in SEGMENT_FIELDS if field in universe_df.columns]]
    merge_frame = universe_df[universe_columns].copy()

    for item in candidate_frames:
        candidate_id = str(item["candidate_id"])
        experiment_stage = str(item["experiment_stage"])
        frame = item["frame"].copy()
        frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
        merged = frame.merge(merge_frame, on="ticker", how="left")

        for scenario in base_scenarios:
            summary = _summarize_scope(merged, eligible_trade_floor=_safe_int(scenario["eligible_trade_floor"]))
            decision = _evaluate_status(
                summary=summary,
                min_eligible_tickers=_safe_int(scenario["min_eligible_tickers"]),
                minimum_trade_sample=_safe_int(scenario["minimum_trade_sample_required"]),
            )
            scenario_rows.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "scenario_label": scenario["scenario_label"],
                    "evaluation_scope": "global",
                    "segment_field": GLOBAL_SEGMENT_LABEL,
                    "segment_value": GLOBAL_SEGMENT_LABEL,
                    "segment_ticker_count": _safe_int(summary.get("ticker_count")),
                    "experiment_stage": experiment_stage,
                    "candidate_id": candidate_id,
                    "eligible_trade_floor": _safe_int(scenario["eligible_trade_floor"]),
                    "min_eligible_tickers_required": _safe_int(scenario["min_eligible_tickers"]),
                    "minimum_trade_sample_required": _safe_int(scenario["minimum_trade_sample_required"]),
                    **summary,
                    **decision,
                    "supporting_segment_field": None,
                    "supporting_segment_value": None,
                    "supporting_segment_status": None,
                }
            )

        for segment_field in [field for field in SEGMENT_FIELDS if field in merged.columns]:
            segment_grouped = merged.groupby(segment_field, dropna=False)
            for segment_value, segment_frame in segment_grouped:
                segment_label = _safe_str(segment_value, "unknown")
                segment_guardrails = _segment_guardrails(
                    segment_ticker_count=int(segment_frame["ticker"].nunique()),
                    current_guardrails=current_guardrails,
                )
                if segment_guardrails is None:
                    min_eligible_tickers = 2
                    minimum_trade_sample = 10
                    status_override = "insufficient_segment"
                else:
                    min_eligible_tickers = _safe_int(segment_guardrails.get("min_eligible_tickers"), 2)
                    minimum_trade_sample = _safe_int(segment_guardrails.get("minimum_trade_sample_required"), 10)
                    status_override = None

                summary = _summarize_scope(
                    segment_frame,
                    eligible_trade_floor=_safe_int(current_guardrails.get("min_trades_threshold"), 5),
                )
                decision = _evaluate_status(
                    summary=summary,
                    min_eligible_tickers=min_eligible_tickers,
                    minimum_trade_sample=minimum_trade_sample,
                    min_segment_tickers=3,
                )
                if status_override is not None:
                    decision["status"] = status_override

                scenario_rows.append(
                    {
                        "scenario_id": "scenario_c_segment_aware_guardrail",
                        "scenario_label": "Segment-aware guardrail",
                        "evaluation_scope": "segment",
                        "segment_field": segment_field,
                        "segment_value": segment_label,
                        "segment_ticker_count": _safe_int(summary.get("ticker_count")),
                        "experiment_stage": experiment_stage,
                        "candidate_id": candidate_id,
                        "eligible_trade_floor": _safe_int(current_guardrails.get("min_trades_threshold"), 5),
                        "min_eligible_tickers_required": min_eligible_tickers,
                        "minimum_trade_sample_required": minimum_trade_sample,
                        **summary,
                        **decision,
                        "supporting_segment_field": None,
                        "supporting_segment_value": None,
                        "supporting_segment_status": None,
                    }
                )

                if decision["status"] == "keep_experimental":
                    segment_pass_map.setdefault(candidate_id, []).append(
                        {
                            "segment_field": segment_field,
                            "segment_value": segment_label,
                            "segment_ticker_count": _safe_int(summary.get("ticker_count")),
                            "eligible_ticker_count": _safe_int(summary.get("eligible_ticker_count")),
                            "total_trades_sum": _safe_int(summary.get("total_trades_sum")),
                            "mean_average_return_all": summary.get("mean_average_return_all"),
                            "mean_average_return_eligible": summary.get("mean_average_return_eligible"),
                            "experiment_stage": experiment_stage,
                        }
                    )

        current_global = next(
            (
                row
                for row in scenario_rows
                if row["candidate_id"] == candidate_id and row["scenario_id"] == "scenario_a_current_guardrail"
            ),
            None,
        )
        support_segments = sorted(
            segment_pass_map.get(candidate_id, []),
            key=lambda item: (
                _safe_float(item.get("mean_average_return_eligible"), -999.0),
                _safe_int(item.get("eligible_ticker_count")),
                _safe_int(item.get("total_trades_sum")),
            ),
            reverse=True,
        )
        best_support = dict(support_segments[0]) if support_segments else {}
        summary = _summarize_scope(
            merged,
            eligible_trade_floor=_safe_int(current_guardrails.get("min_trades_threshold"), 5),
        )
        decision = _evaluate_status(
            summary=summary,
            min_eligible_tickers=_safe_int(current_guardrails.get("min_eligible_tickers"), 3),
            minimum_trade_sample=_safe_int(current_guardrails.get("minimum_trade_sample_required"), 15),
        )
        if decision["status"] == "keep_experimental":
            scenario_d_status = "keep_experimental"
        elif current_global is not None and _safe_str(current_global.get("status")) == "no_go" and best_support:
            scenario_d_status = "keep_experimental_for_segment_review"
        else:
            scenario_d_status = "no_go"

        scenario_rows.append(
            {
                "scenario_id": "scenario_d_supporting_evidence_rule",
                "scenario_label": "Keep global gate with supporting evidence rule",
                "evaluation_scope": "global_plus_supporting_segment",
                "segment_field": GLOBAL_SEGMENT_LABEL,
                "segment_value": GLOBAL_SEGMENT_LABEL,
                "segment_ticker_count": _safe_int(summary.get("ticker_count")),
                "experiment_stage": experiment_stage,
                "candidate_id": candidate_id,
                "eligible_trade_floor": _safe_int(current_guardrails.get("min_trades_threshold"), 5),
                "min_eligible_tickers_required": _safe_int(current_guardrails.get("min_eligible_tickers"), 3),
                "minimum_trade_sample_required": _safe_int(current_guardrails.get("minimum_trade_sample_required"), 15),
                **summary,
                **decision,
                "status": scenario_d_status,
                "supporting_segment_field": best_support.get("segment_field"),
                "supporting_segment_value": best_support.get("segment_value"),
                "supporting_segment_status": "keep_experimental" if best_support else None,
            }
        )

    scenario_df = pd.DataFrame(scenario_rows)
    if scenario_df.empty:
        scenario_df = pd.DataFrame(
            columns=[
                "scenario_id",
                "scenario_label",
                "evaluation_scope",
                "segment_field",
                "segment_value",
                "segment_ticker_count",
                "experiment_stage",
                "candidate_id",
                "eligible_trade_floor",
                "min_eligible_tickers_required",
                "minimum_trade_sample_required",
                "ticker_count",
                "eligible_ticker_count",
                "total_trades_sum",
                "positive_score_ticker_count",
                "mean_average_return_all",
                "mean_average_return_eligible",
                "mean_score_all",
                "supportive_but_ineligible_ticker_count",
                "positive_return_but_ineligible_ticker_count",
                "sample_skew_gap",
                "outlier_bias_risk",
                "status",
                "coverage_ok",
                "trade_sample_ok",
                "quality_all_ok",
                "quality_eligible_ok",
                "eligible_definition_supported",
                "supporting_segment_field",
                "supporting_segment_value",
                "supporting_segment_status",
            ]
        )
    return scenario_df, segment_pass_map


def _build_segment_recommendations(
    scenario_df: pd.DataFrame,
    universe_df: pd.DataFrame,
) -> Dict[str, object]:
    segment_rows = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_c_segment_aware_guardrail")].copy()
    if segment_rows.empty:
        return {
            "segment_rankings": [],
            "segments_safe_to_test_next": [],
            "segments_to_avoid": [],
            "recommended_universe_mode": "collect_more_data_before_any_new_test",
        }

    grouped = (
        segment_rows.groupby(["segment_field", "segment_value"], dropna=False)
        .agg(
            candidate_review_count=("candidate_id", "nunique"),
            keep_experimental_count=("status", lambda values: int((values == "keep_experimental").sum())),
            no_go_count=("status", lambda values: int((values == "no_go").sum())),
            insufficient_segment_count=("status", lambda values: int((values == "insufficient_segment").sum())),
            best_eligible_ticker_count=("eligible_ticker_count", "max"),
            best_total_trades_sum=("total_trades_sum", "max"),
            best_mean_average_return_eligible=("mean_average_return_eligible", "max"),
            best_mean_average_return_all=("mean_average_return_all", "max"),
        )
        .reset_index()
    )
    grouped["segment_key"] = grouped["segment_field"].astype(str) + "=" + grouped["segment_value"].astype(str)

    ticker_counts: List[int] = []
    for row in grouped.to_dict(orient="records"):
        segment_field = str(row["segment_field"])
        segment_value = str(row["segment_value"])
        if segment_field in universe_df.columns:
            ticker_count = int(universe_df.loc[universe_df[segment_field].astype(str).eq(segment_value), "ticker"].nunique())
        else:
            ticker_count = 0
        ticker_counts.append(ticker_count)
    grouped["ticker_count"] = ticker_counts

    grouped["recommendation_score"] = (
        grouped["keep_experimental_count"] * 4.0
        + grouped["best_eligible_ticker_count"] * 1.5
        + grouped["best_total_trades_sum"] * 0.10
        + grouped["best_mean_average_return_eligible"].fillna(0.0) * 0.50
        - grouped["no_go_count"] * 1.5
        - grouped["insufficient_segment_count"] * 0.5
    )
    grouped = grouped.sort_values(
        ["recommendation_score", "keep_experimental_count", "best_mean_average_return_eligible", "best_total_trades_sum"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    safe_segments = [
        item["segment_key"]
        for item in grouped.to_dict(orient="records")
        if _safe_int(item.get("keep_experimental_count")) > 0
        and _safe_int(item.get("ticker_count")) >= 3
        and _safe_float(item.get("best_mean_average_return_eligible"), -999.0) > 0.0
    ]
    avoid_segments = [
        item["segment_key"]
        for item in grouped.to_dict(orient="records")
        if _safe_int(item.get("keep_experimental_count")) == 0
        and _safe_int(item.get("no_go_count")) >= 2
        and _safe_int(item.get("ticker_count")) >= 3
    ]

    if len(safe_segments) >= 2:
        recommended_universe_mode = "split_universe_before_next_experiment"
    elif len(safe_segments) == 1:
        recommended_universe_mode = "test_only_high_coverage_segment"
    else:
        recommended_universe_mode = "collect_more_data_before_any_new_test"

    return {
        "generated_at": _now_iso(),
        "segment_rankings": grouped.to_dict(orient="records"),
        "segments_safe_to_test_next": safe_segments,
        "segments_to_avoid": avoid_segments,
        "recommended_universe_mode": recommended_universe_mode,
    }


def _recommend_guardrail_mode(
    scenario_df: pd.DataFrame,
    segment_recommendations: Dict[str, object],
) -> str:
    global_current = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_a_current_guardrail")].copy()
    global_relaxed = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_b_relaxed_sample_gate")].copy()
    segment_aware = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_c_segment_aware_guardrail")].copy()

    if not global_current.empty and (global_current["status"] == "keep_experimental").any():
        return "keep_global_guardrail"
    if not segment_aware.empty and (segment_aware["status"] == "keep_experimental").any():
        return "move_to_segment_aware_guardrail"
    if not global_relaxed.empty and (global_relaxed["status"] == "keep_experimental").any():
        return "relax_guardrail_slightly"
    if list(segment_recommendations.get("segments_safe_to_test_next") or []):
        return "move_to_segment_aware_guardrail"
    return "stop_and_collect_more_data"


def _build_guardrail_audit(
    current_guardrails: Dict[str, object],
    scenario_df: pd.DataFrame,
) -> Dict[str, object]:
    current_rows = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_a_current_guardrail")].copy()
    relaxed_rows = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_b_relaxed_sample_gate")].copy()
    support_rows = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_d_supporting_evidence_rule")].copy()

    skew_candidates = current_rows.loc[
        current_rows["sample_skew_gap"].fillna(0.0).abs().ge(3.0)
        | current_rows["outlier_bias_risk"].fillna(False)
    ]
    relaxed_still_no_go = relaxed_rows.loc[relaxed_rows["status"].eq("no_go")]
    segment_support = support_rows.loc[support_rows["status"].eq("keep_experimental_for_segment_review")]

    return {
        "current_guardrails": current_guardrails,
        "findings": {
            "eligible_ticker_count": (
                "Global minimum eligible ticker count tetap berguna sebagai gate promosi, "
                "tetapi terlalu kasar bila dipakai sendirian untuk universe yang heterogen."
            ),
            "total_trades_sum": (
                "Total trade sample perlu tetap dijaga, namun lebih informatif bila dihitung di level segment yang konsisten "
                "daripada langsung mencampur seluruh universe."
            ),
            "min_trades_threshold": (
                "Menurunkan trade floor per ticker cenderung hanya menaikkan coverage mekanis tanpa memperbaiki quality pada sample yang benar-benar eligible."
            ),
            "eligible_for_analysis": (
                f"Definisi aktif `{current_guardrails['eligible_for_analysis_definition']}` jangan dilonggarkan global karena outlier non-eligible "
                "terbukti bisa mengangkat mean return agregat secara semu."
            ),
            "global_vs_segment": (
                "Guardrail global masih valid sebagai gate terakhir, tetapi review fairness kandidat perlu pindah ke evaluasi per-segmen."
            ),
        },
        "evidence": {
            "current_global_outlier_bias_candidates": sorted(skew_candidates["candidate_id"].astype(str).unique().tolist()),
            "relaxed_gate_still_no_go_candidates": sorted(relaxed_still_no_go["candidate_id"].astype(str).unique().tolist()),
            "supporting_segment_candidates": sorted(segment_support["candidate_id"].astype(str).unique().tolist()),
        },
    }


def _build_decisive_statement(
    recommended_guardrail_mode: str,
    recommended_universe_mode: str,
    safe_segments: Sequence[str],
) -> str:
    if recommended_guardrail_mode == "move_to_segment_aware_guardrail":
        if recommended_universe_mode == "split_universe_before_next_experiment" and safe_segments:
            return (
                "Universe terlalu heterogen; eksperimen berikutnya wajib dijalankan pada subset tertentu. "
                "Guardrail global tetap dipakai sebagai gate promosi akhir, tetapi evaluasi fairness kandidat harus dihitung per-segmen."
            )
        return (
            "Masalah utama ada pada guardrail global yang terlalu menghukum coverage kandidat di subset tertentu, "
            "sementara universe penuh terlalu heterogen untuk satu evaluasi global."
        )

    if recommended_guardrail_mode == "relax_guardrail_slightly":
        return (
            "Guardrail sample global sedikit terlalu keras terhadap dataset saat ini, tetapi pelonggaran harus kecil dan tetap mempertahankan quality gate."
        )

    if recommended_guardrail_mode == "keep_global_guardrail":
        return "Guardrail global saat ini masih tepat; kegagalan kandidat berasal dari kualitas atau coverage yang memang belum cukup."

    return "Data tetap belum cukup, jadi eksperimen berikutnya harus ditunda sampai coverage universe membaik."


def _build_governance_payload(
    context_payloads: Dict[str, object],
    current_guardrails: Dict[str, object],
    scenario_df: pd.DataFrame,
    segment_recommendations: Dict[str, object],
    recommended_guardrail_mode: str,
) -> Dict[str, object]:
    recommended_universe_mode = str(
        segment_recommendations.get("recommended_universe_mode") or "collect_more_data_before_any_new_test"
    )
    if recommended_guardrail_mode == "move_to_segment_aware_guardrail" and recommended_universe_mode == "test_only_high_coverage_segment":
        recommended_universe_mode = "split_universe_before_next_experiment"

    safe_segments = list(segment_recommendations.get("segments_safe_to_test_next") or [])
    avoid_segments = list(segment_recommendations.get("segments_to_avoid") or [])
    decisive_statement = _build_decisive_statement(
        recommended_guardrail_mode=recommended_guardrail_mode,
        recommended_universe_mode=recommended_universe_mode,
        safe_segments=safe_segments,
    )

    next_experiment_plan = safe_dict(context_payloads.get("next_experiment_plan"))
    what_not_to_change = list(next_experiment_plan.get("what_not_to_change") or [])
    what_to_stop = list(next_experiment_plan.get("what_to_stop") or [])

    global_relaxed = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_b_relaxed_sample_gate")].copy()
    global_guardrail_still_valid = not (global_relaxed["status"] == "keep_experimental").any()

    payload = {
        "generated_at": _now_iso(),
        "recommended_guardrail_mode": recommended_guardrail_mode,
        "recommended_universe_mode": recommended_universe_mode,
        "global_guardrail_still_valid": bool(global_guardrail_still_valid),
        "segment_aware_evaluation_recommended": recommended_guardrail_mode == "move_to_segment_aware_guardrail",
        "segments_safe_to_test_next": safe_segments,
        "segments_to_avoid": avoid_segments,
        "what_to_keep_fixed": dedupe(
            [
                "baseline aktif",
                "logika entry/exit aktif",
                f"eligible_for_analysis tetap berbasis minimum trade floor {current_guardrails['min_trades_threshold']}",
                *[str(item) for item in what_not_to_change],
            ]
        ),
        "what_not_to_do": dedupe(
            [
                "jangan hidupkan item 5-8",
                "jangan lanjut ke Phase C",
                "jangan turunkan global min_trades_threshold hanya untuk mengejar coverage",
                "jangan promosikan kandidat yang quality-nya hanya ditopang ticker non-eligible",
                *[str(item) for item in what_to_stop],
            ]
        ),
        "recommended_next_experiment_after_guardrail_review": (
            "Jalankan evaluasi eksperimen berikutnya dengan universe yang sudah di-split per segment aman, "
            "gunakan guardrail sample yang sama di level ticker, dan pakai status `keep_experimental_for_segment_review` "
            "hanya sebagai bukti dukungan subset, bukan promosi global."
            if recommended_guardrail_mode == "move_to_segment_aware_guardrail"
            else "Tunda eksperimen baru sampai guardrail dan coverage universe punya bukti data yang cukup."
        ),
        "decisive_statement": decisive_statement,
    }
    return payload


def _build_review_payload(
    context_payloads: Dict[str, object],
    current_guardrails: Dict[str, object],
    universe_df: pd.DataFrame,
    universe_warnings: Sequence[str],
    universe_limitations: Sequence[str],
    candidate_frames: Sequence[Dict[str, object]],
    scenario_df: pd.DataFrame,
    segment_recommendations: Dict[str, object],
    governance_payload: Dict[str, object],
) -> Dict[str, object]:
    current_rows = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_a_current_guardrail")].copy()
    relaxed_rows = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_b_relaxed_sample_gate")].copy()
    segment_rows = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_c_segment_aware_guardrail")].copy()
    support_rows = scenario_df.loc[scenario_df["scenario_id"].eq("scenario_d_supporting_evidence_rule")].copy()

    candidate_audit = []
    for item in candidate_frames:
        candidate_id = str(item["candidate_id"])
        current_row = (
            current_rows.loc[current_rows["candidate_id"].eq(candidate_id)].head(1).to_dict(orient="records") or [{}]
        )[0]
        relaxed_row = (
            relaxed_rows.loc[relaxed_rows["candidate_id"].eq(candidate_id)].head(1).to_dict(orient="records") or [{}]
        )[0]
        support_row = (
            support_rows.loc[support_rows["candidate_id"].eq(candidate_id)].head(1).to_dict(orient="records") or [{}]
        )[0]
        best_segment = (
            segment_rows.loc[
                segment_rows["candidate_id"].eq(candidate_id) & segment_rows["status"].eq("keep_experimental")
            ]
            .sort_values(
                ["mean_average_return_eligible", "eligible_ticker_count", "total_trades_sum"],
                ascending=[False, False, False],
            )
            .head(1)
            .to_dict(orient="records")
            or [{}]
        )[0]

        candidate_audit.append(
            {
                "experiment_stage": item["experiment_stage"],
                "candidate_id": candidate_id,
                "global_snapshot_from_source": item["global_snapshot"],
                "scenario_a_current": current_row,
                "scenario_b_relaxed": relaxed_row,
                "scenario_c_best_segment": best_segment,
                "scenario_d_supporting_evidence": support_row,
            }
        )

    roadmap = safe_dict(context_payloads.get("roadmap"))
    roadmap_latest = safe_dict(roadmap.get("latest_execution_status"))

    return {
        "generated_at": _now_iso(),
        "roadmap_lock": {
            "phase_a_status": roadmap_latest.get("phase_a_status"),
            "phase_b_status": roadmap_latest.get("phase_b_status"),
            "phase_c_decision": roadmap_latest.get("phase_c_decision"),
            "current_track": roadmap_latest.get("current_track") or safe_dict(context_payloads.get("root_cause_postmortem")).get("recommended_primary_direction"),
        },
        "artifact_gaps": list(context_payloads.get("missing_artifacts") or []),
        "warnings": dedupe([*list(context_payloads.get("warnings") or []), *list(universe_warnings)]),
        "limitations": list(universe_limitations),
        "current_guardrails": current_guardrails,
        "guardrail_audit": _build_guardrail_audit(current_guardrails=current_guardrails, scenario_df=scenario_df),
        "universe_summary": {
            "ticker_count": int(universe_df["ticker"].nunique()),
            "rows_min": int(universe_df["rows"].min()),
            "rows_max": int(universe_df["rows"].max()),
            "article_count_total_sum": _round_or_none(universe_df["article_count_total"].fillna(0.0).sum()),
            "segment_fields_evaluated": [field for field in SEGMENT_FIELDS if field in universe_df.columns],
        },
        "candidate_audit": candidate_audit,
        "scenario_summary": {
            "scenario_a_keep_count": int((current_rows["status"] == "keep_experimental").sum()),
            "scenario_b_keep_count": int((relaxed_rows["status"] == "keep_experimental").sum()),
            "scenario_c_keep_count": int((segment_rows["status"] == "keep_experimental").sum()),
            "scenario_d_keep_for_segment_review_count": int(
                (support_rows["status"] == "keep_experimental_for_segment_review").sum()
            ),
        },
        "segment_recommendations": segment_recommendations,
        "governance": governance_payload,
        "decisive_statement": governance_payload["decisive_statement"],
    }


def _build_review_text(
    review_payload: Dict[str, object],
    scenario_df: pd.DataFrame,
) -> List[str]:
    governance = safe_dict(review_payload.get("governance"))
    guardrail_audit = safe_dict(review_payload.get("guardrail_audit"))
    segment_recommendations = safe_dict(review_payload.get("segment_recommendations"))
    candidate_audit = list(review_payload.get("candidate_audit") or [])
    limitations = list(review_payload.get("limitations") or [])

    lines = [
        "Baseline v6 Guardrail Review",
        "============================",
        "",
        f"- Recommended guardrail mode: {governance.get('recommended_guardrail_mode')}",
        f"- Recommended universe mode: {governance.get('recommended_universe_mode')}",
        f"- Global guardrail still valid: {governance.get('global_guardrail_still_valid')}",
        f"- Segment-aware evaluation recommended: {governance.get('segment_aware_evaluation_recommended')}",
        "",
        f"- Decisive statement: {governance.get('decisive_statement')}",
        "",
        "Guardrail audit:",
        f"- eligible_ticker_count: {safe_dict(guardrail_audit.get('findings')).get('eligible_ticker_count')}",
        f"- total_trades_sum: {safe_dict(guardrail_audit.get('findings')).get('total_trades_sum')}",
        f"- min_trades_threshold: {safe_dict(guardrail_audit.get('findings')).get('min_trades_threshold')}",
        f"- eligible_for_analysis: {safe_dict(guardrail_audit.get('findings')).get('eligible_for_analysis')}",
        f"- global_vs_segment: {safe_dict(guardrail_audit.get('findings')).get('global_vs_segment')}",
        "",
        "Candidate impact:",
    ]

    for item in candidate_audit:
        current_row = safe_dict(item.get("scenario_a_current"))
        relaxed_row = safe_dict(item.get("scenario_b_relaxed"))
        best_segment = safe_dict(item.get("scenario_c_best_segment"))
        supporting = safe_dict(item.get("scenario_d_supporting_evidence"))
        segment_text = (
            f"{best_segment.get('segment_field')}={best_segment.get('segment_value')}"
            if best_segment else "none"
        )
        lines.append(
            f"- {item.get('candidate_id')}: current={current_row.get('status')}, relaxed={relaxed_row.get('status')}, "
            f"best_segment={segment_text}, supporting_rule={supporting.get('status')}"
        )

    lines.extend(
        [
            "",
            "Segments safe to test next:",
        ]
    )
    for item in list(segment_recommendations.get("segments_safe_to_test_next") or []):
        lines.append(f"- {item}")
    if not list(segment_recommendations.get("segments_safe_to_test_next") or []):
        lines.append("- none")

    lines.extend(["", "Segments to avoid:"])
    for item in list(segment_recommendations.get("segments_to_avoid") or []):
        lines.append(f"- {item}")
    if not list(segment_recommendations.get("segments_to_avoid") or []):
        lines.append("- none")

    if limitations:
        lines.extend(["", "Limitations:"])
        for item in limitations:
            lines.append(f"- {item}")

    if scenario_df.empty:
        lines.extend(["", "No scenario rows were produced."])

    return lines


def run_baseline_v6_guardrail_review(
    data_dir: Path,
    output_dir: Path,
    metadata_file: Optional[Path] = None,
) -> Dict[str, object]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    resolved_metadata = Path(metadata_file) if metadata_file is not None else Path(data_dir) / "ticker_metadata.csv"
    context_payloads = _load_context_artifacts(output_dir=output_dir)
    metadata_df, metadata_warnings = _load_metadata_frame(metadata_file=resolved_metadata if resolved_metadata.exists() else metadata_file)
    universe_df, universe_warnings, universe_limitations = _scan_universe(
        data_dir=Path(data_dir),
        metadata_df=metadata_df,
    )
    context_payloads["warnings"] = dedupe([*list(context_payloads.get("warnings") or []), *metadata_warnings])

    candidate_frames, candidate_warnings = _load_candidate_frames(output_dir=output_dir, context_payloads=context_payloads)
    context_payloads["warnings"] = dedupe([*list(context_payloads.get("warnings") or []), *candidate_warnings])
    current_guardrails = _resolve_current_guardrails(context_payloads=context_payloads)

    scenario_df, _ = _build_scenario_rows(
        candidate_frames=candidate_frames,
        universe_df=universe_df,
        current_guardrails=current_guardrails,
    )
    segment_recommendations = _build_segment_recommendations(
        scenario_df=scenario_df,
        universe_df=universe_df,
    )
    recommended_guardrail_mode = _recommend_guardrail_mode(
        scenario_df=scenario_df,
        segment_recommendations=segment_recommendations,
    )
    governance_payload = _build_governance_payload(
        context_payloads=context_payloads,
        current_guardrails=current_guardrails,
        scenario_df=scenario_df,
        segment_recommendations=segment_recommendations,
        recommended_guardrail_mode=recommended_guardrail_mode,
    )
    if governance_payload["recommended_guardrail_mode"] not in RECOMMENDED_GUARDRAIL_MODES:
        raise BaselineV6GuardrailReviewCliError("recommended_guardrail_mode must be explicit and valid.")
    if governance_payload["recommended_universe_mode"] not in RECOMMENDED_UNIVERSE_MODES:
        raise BaselineV6GuardrailReviewCliError("recommended_universe_mode must be explicit and valid.")

    review_payload = _build_review_payload(
        context_payloads=context_payloads,
        current_guardrails=current_guardrails,
        universe_df=universe_df,
        universe_warnings=universe_warnings,
        universe_limitations=universe_limitations,
        candidate_frames=candidate_frames,
        scenario_df=scenario_df,
        segment_recommendations=segment_recommendations,
        governance_payload=governance_payload,
    )
    review_lines = _build_review_text(review_payload=review_payload, scenario_df=scenario_df)

    scenario_output = output_dir / SCENARIO_CSV_OUTPUT
    segmentation_output = output_dir / SEGMENTATION_CSV_OUTPUT
    review_json_output = output_dir / REVIEW_JSON_OUTPUT
    review_text_output = output_dir / REVIEW_TEXT_OUTPUT
    segment_recommendations_output = output_dir / SEGMENT_RECOMMENDATIONS_OUTPUT
    governance_output = output_dir / GOVERNANCE_OUTPUT

    scenario_df.to_csv(scenario_output, index=False)
    universe_df.to_csv(segmentation_output, index=False)
    _write_json(review_json_output, review_payload)
    _write_text(review_text_output, review_lines)
    _write_json(segment_recommendations_output, segment_recommendations)
    _write_json(governance_output, governance_payload)

    return {
        "review_payload": review_payload,
        "scenario_df": scenario_df,
        "universe_df": universe_df,
        "segment_recommendations": segment_recommendations,
        "governance": governance_payload,
        "artifacts": {
            "review_json": str(review_json_output),
            "review_text": str(review_text_output),
            "scenario_csv": str(scenario_output),
            "segmentation_csv": str(segmentation_output),
            "segment_recommendations_json": str(segment_recommendations_output),
            "governance_json": str(governance_output),
        },
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit guardrail/sample eligibility and universe segmentation without changing the active baseline."
    )
    parser.add_argument("--data-dir", default="data", help="Directory containing ticker CSV files. Default: data")
    parser.add_argument("--output-dir", default="output", help="Directory containing artifacts and where v6 outputs will be written. Default: output")
    parser.add_argument(
        "--metadata-file",
        default=None,
        help="Optional metadata CSV path. Defaults to <data-dir>/ticker_metadata.csv when available.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    metadata_file = Path(args.metadata_file) if args.metadata_file else None

    try:
        result = run_baseline_v6_guardrail_review(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            metadata_file=metadata_file,
        )
    except BaselineV6GuardrailReviewCliError as exc:
        print(f"Guardrail review failed: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Unexpected error during guardrail review: {exc}")
        return 1

    governance = result["governance"]
    print("Baseline v6 guardrail review complete.")
    print(f"recommended_guardrail_mode={governance['recommended_guardrail_mode']}")
    print(f"recommended_universe_mode={governance['recommended_universe_mode']}")
    print(f"decisive_statement={governance['decisive_statement']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
