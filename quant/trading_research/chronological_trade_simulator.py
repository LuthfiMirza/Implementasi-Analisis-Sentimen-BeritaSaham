from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class SimulationConfig:
    same_day_policy: str = "stop_first"


def prepare_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing OHLCV columns: {', '.join(missing)}")
    output = frame.copy()
    output["date"] = pd.to_datetime(output["date"]).dt.normalize()
    for column in ["open", "high", "low", "close", "volume"]:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return output.sort_values("date").reset_index(drop=True)


def simulate_path(
    ohlcv: pd.DataFrame,
    entry_index: int,
    entry_price: float,
    horizon_days: int,
    tp_pct: float | None = None,
    sl_pct: float | None = None,
    same_day_policy: str = "stop_first",
) -> dict[str, Any]:
    if same_day_policy not in {"stop_first", "target_first", "ambiguous_exclude"}:
        raise ValueError("invalid same-day policy")
    end_index = min(entry_index + horizon_days - 1, len(ohlcv) - 1)
    path = ohlcv.iloc[entry_index : end_index + 1]
    tp_price = entry_price * (1 + (tp_pct or 0) / 100) if tp_pct is not None else None
    sl_price = entry_price * (1 - abs(sl_pct or 0) / 100) if sl_pct is not None else None
    tp_hit = sl_hit = False
    tp_date = sl_date = first_hit = None
    ambiguous_same_day_count = 0
    mfe = float("-inf")
    mae = float("inf")
    for offset, (_, row) in enumerate(path.iterrows(), start=1):
        high = float(row["high"])
        low = float(row["low"])
        date = row["date"].date().isoformat()
        mfe = max(mfe, ((high / entry_price) - 1) * 100)
        mae = min(mae, ((low / entry_price) - 1) * 100)
        day_tp = tp_price is not None and high >= tp_price
        day_sl = sl_price is not None and low <= sl_price
        if day_tp and not tp_hit:
            tp_hit = True; tp_date = date
        if day_sl and not sl_hit:
            sl_hit = True; sl_date = date
        if first_hit is None and day_tp and day_sl:
            ambiguous_same_day_count += 1
            if same_day_policy == "ambiguous_exclude":
                first_hit = "ambiguous"; break
            first_hit = "sl" if same_day_policy == "stop_first" else "tp"
            break
        if first_hit is None and day_tp:
            first_hit = "tp"; break
        if first_hit is None and day_sl:
            first_hit = "sl"; break
    exit_close = float(path.iloc[-1]["close"])
    return {
        "tp_hit": tp_hit,
        "tp_first_hit_date": tp_date,
        "sl_hit": sl_hit,
        "sl_first_hit_date": sl_date,
        "first_hit": first_hit,
        "mfe_pct": round(mfe, 6) if mfe != float("-inf") else None,
        "mae_pct": round(mae, 6) if mae != float("inf") else None,
        "horizon_return_pct": round(((exit_close / entry_price) - 1) * 100, 6),
        "trading_days_to_hit": offset if first_hit else None,
        "ambiguous_same_day_count": ambiguous_same_day_count,
    }


def simulate_path_gap_aware(
    ohlcv: pd.DataFrame,
    entry_index: int,
    entry_price: float,
    horizon_days: int,
    tp_pct: float | None = None,
    sl_pct: float | None = None,
    same_day_policy: str = "stop_first",
) -> dict[str, Any]:
    if same_day_policy not in {"stop_first", "target_first", "ambiguous_exclude"}:
        raise ValueError("invalid same-day policy")
    end_index = min(entry_index + horizon_days - 1, len(ohlcv) - 1)
    path = ohlcv.iloc[entry_index : end_index + 1]
    tp_price = entry_price * (1 + (tp_pct or 0) / 100) if tp_pct is not None else None
    sl_price = entry_price * (1 - abs(sl_pct or 0) / 100) if sl_pct is not None else None
    mfe = float("-inf")
    mae = float("inf")
    ambiguous_count = 0
    entry_day_tp = entry_day_sl = False
    for offset, (_, row) in enumerate(path.iterrows(), start=1):
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        date = row["date"].date().isoformat()
        mfe = max(mfe, ((high / entry_price) - 1) * 100)
        mae = min(mae, ((low / entry_price) - 1) * 100)
        stop_fill = None
        target_fill = None
        if sl_price is not None:
            if open_price <= sl_price:
                stop_fill = {"type": "sl", "trigger_price": sl_price, "fill_price": open_price, "fill_reason": "gap_open", "gap_amount": open_price - sl_price, "gap_pct": ((open_price / sl_price) - 1) * 100, "execution_date": date}
            elif low <= sl_price:
                stop_fill = {"type": "sl", "trigger_price": sl_price, "fill_price": sl_price, "fill_reason": "intraday_trigger", "gap_amount": 0.0, "gap_pct": 0.0, "execution_date": date}
        if tp_price is not None:
            if open_price >= tp_price:
                target_fill = {"type": "tp", "trigger_price": tp_price, "fill_price": open_price, "fill_reason": "gap_open", "gap_amount": open_price - tp_price, "gap_pct": ((open_price / tp_price) - 1) * 100, "execution_date": date}
            elif high >= tp_price:
                target_fill = {"type": "tp", "trigger_price": tp_price, "fill_price": tp_price, "fill_reason": "intraday_trigger", "gap_amount": 0.0, "gap_pct": 0.0, "execution_date": date}
        if offset == 1:
            entry_day_tp = target_fill is not None
            entry_day_sl = stop_fill is not None
        if stop_fill and target_fill:
            ambiguous_count += 1
            if same_day_policy == "ambiguous_exclude":
                fill = {"type": "ambiguous", "execution_date": date}
            elif same_day_policy == "target_first":
                fill = target_fill
            else:
                fill = stop_fill
            break
        if stop_fill or target_fill:
            fill = stop_fill or target_fill
            break
    else:
        offset = len(path)
        fill = None
    exit_close = float(path.iloc[-1]["close"])
    fill_price = fill.get("fill_price") if fill and fill.get("type") in {"tp", "sl"} else exit_close
    gross_return = ((float(fill_price) / entry_price) - 1) * 100
    return {
        "first_hit": fill.get("type") if fill else None,
        "fill": fill,
        "gross_realized_return_pct": round(gross_return, 6),
        "horizon_return_pct": round(((exit_close / entry_price) - 1) * 100, 6),
        "mfe_pct": round(mfe, 6) if mfe != float("-inf") else None,
        "mae_pct": round(mae, 6) if mae != float("inf") else None,
        "days_to_exit": offset if fill else horizon_days,
        "entry_day_tp_hit": entry_day_tp,
        "entry_day_sl_hit": entry_day_sl,
        "same_day_tp_sl_count": ambiguous_count,
        "ambiguous_same_day_count": ambiguous_count,
        "execution_policy": "gap_aware_daily_ohlcv",
    }
