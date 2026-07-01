from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(payload: dict[str, Any], path: Path, overwrite: bool = False) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"artifact already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_iso_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pct_summary(values: list[float | None]) -> dict[str, float | None]:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return {"min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None}

    def quantile(q: float) -> float:
        position = (len(clean) - 1) * q
        lower = int(position)
        upper = min(lower + 1, len(clean) - 1)
        if lower == upper:
            return clean[lower]
        return clean[lower] + (clean[upper] - clean[lower]) * (position - lower)

    return {
        "min": round(clean[0], 6),
        "p25": round(quantile(0.25), 6),
        "median": round(quantile(0.50), 6),
        "p75": round(quantile(0.75), 6),
        "max": round(clean[-1], 6),
        "mean": round(sum(clean) / len(clean), 6),
    }


def histogram(values: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = "null" if value is None else str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
