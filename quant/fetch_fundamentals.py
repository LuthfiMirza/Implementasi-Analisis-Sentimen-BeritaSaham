#!/usr/bin/env python3
"""Fetch live fundamental ratios (PBV/PER/ROE/DER/EPS/dividend yield) via yfinance
for the project's active tickers. Outputs JSON to stdout for SyncStockFundamentalsCommand
to consume.

Two data-quality issues found during manual testing (2026-07-20) and handled here:
  1. yfinance's debtToEquity is reported as a PERCENTAGE (e.g. 44.1 meaning DER=0.441x),
     while calculateFundamentalScore() in DecisionSupportService.php expects a plain
     decimal ratio (0.8, 1.0, 5.2 ...). Divide by 100 before output.
  2. Occasional garbage values from the upstream source (observed: ADRO priceToBook
     returning 14823.529, clearly not a real ratio). Sanity-bound every ratio and drop
     (null) anything outside a plausible range rather than silently poisoning the DB.
"""
from __future__ import annotations

import json
import sys

import yfinance as yf

TICKERS = ["BBCA", "BBRI", "BMRI", "TLKM", "ASII", "GOTO", "INDF", "ICBP", "ADRO", "UNVR", "BUMI", "DEWA",
           "BRPT", "SMGR", "ESSA"]

BOUNDS = {
    "pbv": (0, 100),
    "per": (0, 300),
    "roe": (-500, 500),   # percent
    "der": (0, 50),       # decimal ratio, after /100 conversion
    "eps": (-100000, 100000),
    "dividend_yield": (0, 50),  # percent
}


def sane(value: float | None, key: str) -> float | None:
    if value is None:
        return None
    low, high = BOUNDS[key]
    if not (low <= value <= high):
        return None
    return round(value, 4)


def fetch_one(code: str) -> dict[str, object]:
    info = yf.Ticker(f"{code}.JK").info
    roe_pct = info.get("returnOnEquity")
    der_decimal = info.get("debtToEquity")
    div_yield_pct = info.get("dividendYield")

    return {
        "code": code,
        "pbv": sane(info.get("priceToBook"), "pbv"),
        "per": sane(info.get("trailingPE"), "per"),
        "roe": sane(roe_pct * 100 if roe_pct is not None else None, "roe"),
        "der": sane(der_decimal / 100 if der_decimal is not None else None, "der"),
        "eps": sane(info.get("trailingEps"), "eps"),
        "dividend_yield": sane(div_yield_pct, "dividend_yield"),
        "book_value_per_share": info.get("bookValue"),
    }


def main() -> None:
    results = []
    for code in TICKERS:
        try:
            results.append(fetch_one(code))
        except Exception as exc:  # noqa: BLE001 -- one ticker failing shouldn't kill the batch
            results.append({"code": code, "error": str(exc)})

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    sys.exit(main())
