#!/usr/bin/env python3
"""Append today's top-5 net foreign buy/sell snapshot from infovesta.com to a local, append-only
log. See README.md for why this exists and its real limitations (live-only, top-5-only, cannot
be walk-forward validated until months of history accumulate).

Run daily on a trading day:
    python3 quant/foreign_flow_tracker/collect_snapshot.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

OUT_PATH = Path(__file__).parent / "snapshots.jsonl"
URLS = {
    "net_buy": "https://www.infovesta.com/index/data_info/saham/topbuy",
    "net_sell": "https://www.infovesta.com/index/data_info/saham/topsell",
}
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) SentimenaResearch/1.0"


def parse_table(html: str) -> list[dict]:
    """The table pairs a Buy row and a Sell row per stock via rowspan; extract both plus the
    rowspan'd Net figure, which only appears once (on the Buy row)."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    entries: list[dict] = []
    pending_code = None

    for row in rows:
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        cells = [c.replace("&nbsp;", "").strip() for c in cells if c.strip()]
        if not cells:
            continue

        # Buy row: [code, "Buy", buy_volume, net] (4 cells, code has rowspan=2)
        # Sell row: ["Sell", sell_volume] (2 cells, no code -- belongs to the previous Buy row)
        if len(cells) >= 4 and cells[1] == "Buy":
            pending_code = cells[0]
            entries.append({
                "stock_code": cells[0],
                "buy_volume_lembar": _to_int(cells[2]),
                "net_volume_lembar": _to_int(cells[3]),
                "sell_volume_lembar": None,
            })
        elif len(cells) == 2 and cells[0] == "Sell" and pending_code and entries:
            entries[-1]["sell_volume_lembar"] = _to_int(cells[1])
            pending_code = None

    return entries


def _to_int(text: str) -> int | None:
    digits = text.replace(",", "").replace(".", "").strip()
    return int(digits) if digits.lstrip("-").isdigit() else None


def fetch(url: str) -> str | None:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=12)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  [gagal fetch {url}]: {e}")
        return None


def main() -> None:
    snapshot = {"collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    any_success = False

    for label, url in URLS.items():
        html = fetch(url)
        if html is None:
            snapshot[label] = None
            continue
        entries = parse_table(html)
        snapshot[label] = entries
        any_success = True
        print(f"{label}: {len(entries)} saham -> " + ", ".join(e["stock_code"] for e in entries))

    if not any_success:
        print("Kedua fetch gagal, tidak ada yang disimpan.")
        sys.exit(1)

    with OUT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    print(f"\nTersimpan ke {OUT_PATH}")


if __name__ == "__main__":
    main()
