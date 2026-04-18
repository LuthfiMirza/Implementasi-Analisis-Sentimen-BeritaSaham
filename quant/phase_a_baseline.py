"""Utilities for loading and applying the frozen Phase A baseline config."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

DEFAULT_BASELINE_PATHS = [
    Path("output/phase_a_baseline_final.json"),
    Path("config/phase_a_baseline.json"),
]
GROUP_OVERRIDE_PRIORITY = ["market_cap_group", "beta_group", "sector", "category"]
DEFAULT_PHASE_A_BASELINE: Dict[str, object] = {
    "default_volume_spike_threshold": 2.0,
    "strict_mode_default": False,
    "adaptive_threshold_enabled": False,
    "group_threshold_overrides": [],
    "min_trades_floor": 8,
    "readiness_status": "partially_ready",
    "baseline_status": "draft",
    "decision_source": [],
    "generated_at": None,
}


def _safe_float(value: object, default: float) -> float:
    """Convert scalar values into float with fallback."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_bool(value: object, default: bool) -> bool:
    """Convert scalar values into bool with fallback."""

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


def _safe_int(value: object, default: int) -> int:
    """Convert scalar values into int with fallback."""

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _normalize_group_overrides(overrides: object) -> List[Dict[str, object]]:
    """Normalize raw group override payloads into a predictable structure."""

    if not isinstance(overrides, list):
        return []

    normalized: List[Dict[str, object]] = []
    for item in overrides:
        if not isinstance(item, dict):
            continue

        group_field = str(item.get("group_field", "")).strip()
        group_value = str(item.get("group_value", "")).strip()
        if not group_field or not group_value:
            continue

        normalized.append(
            {
                "group_field": group_field,
                "group_value": group_value,
                "threshold": _safe_float(
                    item.get("threshold"),
                    DEFAULT_PHASE_A_BASELINE["default_volume_spike_threshold"],
                ),
                "decision_confidence": str(item.get("decision_confidence", "low")).strip().lower() or "low",
                "sample_status": str(item.get("sample_status", "unknown")).strip().lower() or "unknown",
                "source": str(item.get("source", "phase_a_baseline")).strip() or "phase_a_baseline",
            }
        )

    return normalized


def merge_baseline_defaults(payload: Optional[Dict[str, object]]) -> Dict[str, object]:
    """Merge a raw baseline payload with defaults and normalized types."""

    config = dict(DEFAULT_PHASE_A_BASELINE)
    if payload:
        config.update(payload)

    config["default_volume_spike_threshold"] = _safe_float(
        config.get("default_volume_spike_threshold"),
        DEFAULT_PHASE_A_BASELINE["default_volume_spike_threshold"],
    )
    config["strict_mode_default"] = _safe_bool(
        config.get("strict_mode_default"),
        DEFAULT_PHASE_A_BASELINE["strict_mode_default"],
    )
    config["adaptive_threshold_enabled"] = _safe_bool(
        config.get("adaptive_threshold_enabled"),
        DEFAULT_PHASE_A_BASELINE["adaptive_threshold_enabled"],
    )
    config["min_trades_floor"] = _safe_int(
        config.get("min_trades_floor"),
        DEFAULT_PHASE_A_BASELINE["min_trades_floor"],
    )
    config["readiness_status"] = str(
        config.get("readiness_status", DEFAULT_PHASE_A_BASELINE["readiness_status"])
    ).strip() or str(DEFAULT_PHASE_A_BASELINE["readiness_status"])
    config["baseline_status"] = str(
        config.get("baseline_status", DEFAULT_PHASE_A_BASELINE["baseline_status"])
    ).strip() or str(DEFAULT_PHASE_A_BASELINE["baseline_status"])
    config["decision_source"] = list(config.get("decision_source") or [])
    config["group_threshold_overrides"] = _normalize_group_overrides(
        config.get("group_threshold_overrides")
    )
    return config


def resolve_baseline_config_path(
    baseline_config: Optional[Path] = None,
    search_paths: Optional[Sequence[Path]] = None,
) -> Optional[Path]:
    """Resolve the explicit or first available baseline config path."""

    if baseline_config is not None:
        return Path(baseline_config)

    for candidate in list(search_paths or DEFAULT_BASELINE_PATHS):
        path = Path(candidate)
        if path.exists() and path.is_file():
            return path

    return None


def load_phase_a_baseline(
    baseline_config: Optional[Path] = None,
    search_paths: Optional[Sequence[Path]] = None,
) -> Tuple[Dict[str, object], List[str], Optional[Path]]:
    """Load a baseline config file with safe fallbacks."""

    warnings: List[str] = []
    resolved_path = resolve_baseline_config_path(
        baseline_config=baseline_config,
        search_paths=search_paths,
    )
    if resolved_path is None:
        warnings.append(
            "Phase A baseline config not found. Falling back to safe defaults "
            "(threshold 2.0, strict false, adaptive false)."
        )
        return merge_baseline_defaults(None), warnings, None

    try:
        payload = json.loads(Path(resolved_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        warnings.append(
            f"Phase A baseline config not found: {resolved_path}. Falling back to safe defaults."
        )
        return merge_baseline_defaults(None), warnings, None
    except json.JSONDecodeError as exc:
        warnings.append(
            f"Phase A baseline config is invalid JSON ({resolved_path}: {exc}). "
            "Falling back to safe defaults."
        )
        return merge_baseline_defaults(None), warnings, None
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(
            f"Failed to read Phase A baseline config {resolved_path}: {exc}. "
            "Falling back to safe defaults."
        )
        return merge_baseline_defaults(None), warnings, None

    config = merge_baseline_defaults(payload if isinstance(payload, dict) else None)
    if str(resolved_path) not in config["decision_source"]:
        config["decision_source"] = [str(resolved_path), *config["decision_source"]]
    return config, warnings, resolved_path


def load_optional_metadata_lookup(
    metadata_file: Optional[Path],
) -> Tuple[Dict[str, Dict[str, object]], List[str]]:
    """Load optional ticker metadata and return a simple lookup dict."""

    warnings: List[str] = []
    if metadata_file is None:
        return {}, warnings

    path = Path(metadata_file)
    if not path.exists() or not path.is_file():
        warnings.append(f"Metadata file not found: {path}. Group overrides cannot be resolved.")
        return {}, warnings

    try:
        metadata_df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        warnings.append(f"Metadata file is empty: {path}. Group overrides cannot be resolved.")
        return {}, warnings
    except pd.errors.ParserError as exc:
        warnings.append(
            f"Metadata CSV parser error in {path}: {exc}. Group overrides cannot be resolved."
        )
        return {}, warnings
    except Exception as exc:  # pragma: no cover - defensive
        warnings.append(
            f"Failed to read metadata file {path}: {exc}. Group overrides cannot be resolved."
        )
        return {}, warnings

    if metadata_df.empty or "ticker" not in metadata_df.columns:
        warnings.append(
            f"Metadata file {path} does not contain usable ticker rows. Group overrides cannot be resolved."
        )
        return {}, warnings

    frame = metadata_df.copy()
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    frame = frame.drop_duplicates(subset=["ticker"], keep="first")
    lookup = frame.set_index("ticker").to_dict(orient="index")
    return lookup, warnings


def resolve_group_override(
    metadata_row: Optional[Dict[str, object]],
    baseline_config: Dict[str, object],
    priority_fields: Optional[Iterable[str]] = None,
) -> Optional[Dict[str, object]]:
    """Return the first matching group override for one ticker metadata row."""

    if not metadata_row or not baseline_config.get("adaptive_threshold_enabled"):
        return None

    overrides = baseline_config.get("group_threshold_overrides", [])
    if not overrides:
        return None

    fields = list(priority_fields or GROUP_OVERRIDE_PRIORITY)
    for field in fields:
        if field not in metadata_row:
            continue
        raw_value = metadata_row.get(field)
        if raw_value is None or str(raw_value).strip() == "":
            continue
        for override in overrides:
            if (
                str(override.get("group_field")) == field
                and str(override.get("group_value")) == str(raw_value)
            ):
                return override

    return None


def resolve_phase_a_runtime_settings(
    ticker: Optional[str],
    baseline_config: Dict[str, object],
    metadata_lookup: Optional[Dict[str, Dict[str, object]]] = None,
) -> Dict[str, object]:
    """Resolve the threshold and strict mode to apply for one ticker."""

    normalized_ticker = str(ticker or "").upper().strip()
    metadata_row = (metadata_lookup or {}).get(normalized_ticker)
    override = resolve_group_override(metadata_row, baseline_config)

    threshold = _safe_float(
        (override or {}).get("threshold"),
        baseline_config.get("default_volume_spike_threshold", 2.0),
    )
    strict_mode = _safe_bool(
        baseline_config.get("strict_mode_default"),
        DEFAULT_PHASE_A_BASELINE["strict_mode_default"],
    )
    return {
        "threshold": threshold,
        "strict_mode": strict_mode,
        "group_override": override,
        "metadata_row": metadata_row,
        "baseline_status": baseline_config.get("baseline_status", "draft"),
    }
