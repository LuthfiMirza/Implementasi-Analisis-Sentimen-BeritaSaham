"""Lightweight quantitative utilities for Python-based signal research."""

from .phase_a import (
    add_trend_features,
    add_volume_features,
    compare_backtest_variants,
    generate_phase_a_signal,
    run_phase_a_backtest_pipeline,
)

__all__ = [
    "add_volume_features",
    "add_trend_features",
    "generate_phase_a_signal",
    "compare_backtest_variants",
    "run_phase_a_backtest_pipeline",
]
