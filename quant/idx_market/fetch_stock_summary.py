#!/usr/bin/env python3
"""Fetch the IDX end-of-day Stock Summary for a single trading day and print it as JSON on stdout.

The IDX site sits behind Cloudflare and returns 403 to plain HTTP clients, so this uses
curl_cffi's TLS/JA3 browser impersonation to look like a real Chrome request. One request per
run -- this is meant to be called once a day by `php artisan idx:fetch-daily-summary`, matching
the thin-command pattern of quant/foreign_flow_tracker/collect_snapshot.py (all parsing lives
here, the Laravel command just invokes and upserts).

This is PUBLIC end-of-day data that idx.co.id publishes for free public viewing. It is NOT
broker-level or tick data. Not a production model feature -- the Market Alerts page is
descriptive monitoring only.

Usage:
    python3 fetch_stock_summary.py --date 20260828
    python3 fetch_stock_summary.py                # defaults to today (Asia/Jakarta)

Output (stdout): {"date": "2026-08-28", "count": 963, "rows": [ {..raw IDX row..}, ... ]}
Exit code 0 on success, 1 on failure (message on stderr).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

ENDPOINT = "https://www.idx.co.id/primary/TradingSummary/GetStockSummary"
REFERER = "https://www.idx.co.id/en/market-data/trading-summary/stock-summary"
# Jakarta is UTC+7, no DST.
JAKARTA = timezone(timedelta(hours=7))
IMPERSONATE_ORDER = ("chrome", "chrome124", "chrome120", "safari17_0")


def _eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def resolve_date(raw: str | None) -> str:
    """Return YYYYMMDD. Accepts YYYYMMDD or YYYY-MM-DD; default = today in Jakarta."""
    if not raw:
        return datetime.now(JAKARTA).strftime("%Y%m%d")
    cleaned = raw.replace("-", "").strip()
    datetime.strptime(cleaned, "%Y%m%d")  # validate
    return cleaned


def fetch(date_yyyymmdd: str, timeout: int) -> list[dict]:
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            "curl_cffi tidak terpasang di venv ini. Install: pip install curl_cffi"
        ) from exc

    params = {"length": 9999, "start": 0, "date": date_yyyymmdd}
    headers = {
        "Referer": REFERER,
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    }

    last_error: str | None = None
    for profile in IMPERSONATE_ORDER:
        try:
            resp = cffi_requests.get(
                ENDPOINT,
                params=params,
                headers=headers,
                impersonate=profile,
                timeout=timeout,
            )
        except Exception as exc:  # network / TLS error -- try next profile
            last_error = f"{profile}: {exc!r}"
            continue

        if resp.status_code != 200:
            last_error = f"{profile}: HTTP {resp.status_code}"
            continue

        try:
            payload = resp.json()
        except Exception as exc:
            last_error = f"{profile}: response bukan JSON ({exc!r})"
            continue

        rows = payload.get("data") or payload.get("Data") or []
        if not isinstance(rows, list):
            last_error = f"{profile}: field 'data' bukan list"
            continue
        return rows

    raise SystemExit(f"Semua percobaan gagal menembus IDX. Terakhir: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Tanggal bursa (YYYYMMDD atau YYYY-MM-DD). Default: hari ini WIB.")
    parser.add_argument("--timeout", type=int, default=40, help="Timeout HTTP detik (default 40).")
    args = parser.parse_args()

    date_yyyymmdd = resolve_date(args.date)
    rows = fetch(date_yyyymmdd, args.timeout)

    iso_date = f"{date_yyyymmdd[:4]}-{date_yyyymmdd[4:6]}-{date_yyyymmdd[6:8]}"
    json.dump({"date": iso_date, "count": len(rows), "rows": rows}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    _eprint(f"OK {iso_date}: {len(rows)} baris")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover
        _eprint(f"ERROR: {exc!r}")
        raise SystemExit(1)
