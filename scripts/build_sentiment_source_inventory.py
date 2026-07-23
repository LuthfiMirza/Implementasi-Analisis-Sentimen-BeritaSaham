#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.lib.sentiment_text_normalization import is_usable_grouping_value, normalized_fields, normalize_text

LABELS = {"positive", "neutral", "negative"}
PREVIOUS_SETS = {
    "active_train": "storage/app/sentiment_finetune/train.jsonl",
    "active_validation": "storage/app/sentiment_finetune/val.jsonl",
    "active_test_148": "storage/app/sentiment_finetune/test.jsonl",
    "r5b_153": "output/prediction_research/sentiment_r5b_locked_tests/legacy_hard_case_test.jsonl",
}


def ids_from_jsonl(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ids.add(str(json.loads(line).get("news_article_id", "")))
    return ids


def safe_user(value: object) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()[:16] if value not in (None, "") else ""


def php_query() -> str:
    return r'''require "vendor/autoload.php"; $app=require "bootstrap/app.php"; $app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap(); $rows=Illuminate\Support\Facades\DB::table("sentiment_manual_labels as sml")->leftJoin("news_articles as na","na.id","=","sml.news_article_id")->leftJoin("stocks as s","s.id","=","na.stock_id")->select(["sml.id as manual_label_id","sml.news_article_id as article_id","sml.user_id","sml.label as manual_label","sml.sample_method","sml.created_at as annotation_timestamp","na.title","na.summary","na.content_snippet","na.full_text","na.source_provider as source","na.source_url as url","na.published_at as publication_timestamp","s.code as stock_code","s.id as issuer_id"])->orderBy("sml.news_article_id")->orderBy("sml.id")->get(); echo json_encode(["driver"=>Illuminate\Support\Facades\DB::connection()->getDriverName(),"database"=>Illuminate\Support\Facades\DB::connection()->getDatabaseName(),"rows"=>$rows], JSON_UNESCAPED_UNICODE);'''


def fetch_rows(require_database: bool) -> tuple[dict, list[dict]]:
    if require_database and os.environ.get("SENTIMENT_INVENTORY_FORCE_DB_UNAVAILABLE") == "1":
        print(json.dumps({"status": "database_unavailable", "error": "forced"}), file=sys.stderr)
        raise SystemExit(2)
    try:
        payload = json.loads(subprocess.check_output(["php", "-r", php_query()], text=True, stderr=subprocess.DEVNULL))
        return {"status": "ok", "driver": payload.get("driver"), "database": payload.get("database")}, payload.get("rows", [])
    except Exception as exc:
        if require_database:
            print(json.dumps({"status": "database_unavailable", "error": type(exc).__name__}), file=sys.stderr)
            raise SystemExit(2)
        raise


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def field_stats(rows: list[dict], field: str, safe_for_grouping: bool) -> dict:
    values = [row.get(field) for row in rows]
    non_null = [value for value in values if value is not None]
    strings = [str(value) for value in non_null]
    return {
        "column_name": field,
        "non_null_count": len(non_null),
        "null_count": len(values) - len(non_null),
        "empty_string_count": sum(1 for value in strings if value.strip() == ""),
        "distinct_count": len(set(strings)),
        "length_example": max([len(value) for value in strings] or [0]),
        "safe_for_grouping": safe_for_grouping,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-database", action="store_true")
    parser.add_argument("--output-json", default="reports/sentiment_source_inventory.json")
    parser.add_argument("--output-csv", default="data/evaluation/source_population_v2.csv")
    args = parser.parse_args()

    db, rows = fetch_rows(args.require_database)
    memberships = {name: ids_from_jsonl(Path(path)) for name, path in PREVIOUS_SETS.items()}
    output_rows: list[dict] = []
    invalid = 0
    missing_article = 0
    for row in rows:
        article_id = str(row.get("article_id") or "")
        label = row.get("manual_label")
        if label not in LABELS:
            invalid += 1
            continue
        if not row.get("title"):
            missing_article += 1
        target = str(row.get("stock_code") or row.get("issuer_id") or "").strip().upper()
        nf = normalized_fields({**row, "target_entity": target})
        text_for_required = normalize_text(" ".join(str(row.get(k) or "") for k in ["title", "summary", "content_snippet"]))
        exposure = []
        if article_id in memberships["active_test_148"]:
            exposure.append("active_test_148")
        if article_id in memberships["r5b_153"]:
            exposure.append("r5b_153")
        historical = "multiple_previous_test_sets" if len(exposure) > 1 else (exposure[0] if exposure else "no_known_test_exposure")
        existing = [name for name in ["active_train", "active_validation", "active_test_148"] if article_id in memberships[name]]
        output_rows.append({
            "article_id": article_id,
            "manual_label_id": str(row.get("manual_label_id") or ""),
            "label": label,
            "user_id_hash": safe_user(row.get("user_id")),
            "sample_method": row.get("sample_method") or "",
            "source": row.get("source") or "",
            "publication_timestamp": row.get("publication_timestamp") or "",
            "canonical_target_entity": target,
            "target_entity_source": "stock_code" if row.get("stock_code") else ("issuer_id" if row.get("issuer_id") else "missing"),
            "full_text_available": bool(row.get("full_text")),
            "existing_split": "|".join(existing),
            "historical_exposure_status": historical,
            "historical_test_120_membership": "unknown",
            "active_test_148_membership": article_id in memberships["active_test_148"],
            "r5b_153_membership": article_id in memberships["r5b_153"],
            "normalized_title_hash": nf["normalized_title_sha256"] if is_usable_grouping_value(nf["normalized_title"]) else "",
            "combined_text_hash": nf["exact_text_sha256"] if is_usable_grouping_value(nf["normalized_combined_text"]) else "",
            "normalized_url_hash": nf["normalized_url_hash"] if is_usable_grouping_value(nf["normalized_url"]) else "",
            "text_length": len(nf["normalized_combined_text"]),
            "has_required_text": is_usable_grouping_value(text_for_required) and len(text_for_required) >= 20,
        })

    labels = Counter(row["label"] for row in output_rows)
    samples = Counter(row["sample_method"] or "missing" for row in output_rows)
    sources = Counter(row["source"] or "missing" for row in output_rows)
    entities = Counter(row["canonical_target_entity"] or "missing" for row in output_rows)
    dates = [row["publication_timestamp"] for row in output_rows if row["publication_timestamp"]]
    exposure = Counter(row["historical_exposure_status"] for row in output_rows)
    missing_text = sum(1 for row in output_rows if not row["has_required_text"])
    summary = {
        "database": {"connection_status": db["status"], "driver": db.get("driver"), "database_masked": (db.get("database") or "")[:2] + "***"},
        "total_articles": len(set(row["article_id"] for row in output_rows)),
        "total_manual_labels": len(rows),
        "valid_manual_labels": len(output_rows),
        "invalid_labels": invalid,
        "missing_article_rows": missing_article,
        "duplicate_article_ids": len(output_rows) - len(set(row["article_id"] for row in output_rows)),
        "duplicate_manual_label_ids": len(output_rows) - len(set(row["manual_label_id"] for row in output_rows)),
        "label_distribution": dict(labels),
        "sample_method_distribution": dict(samples),
        "source_distribution": dict(sources),
        "target_entity_distribution": dict(entities),
        "date_range": {"min": min(dates) if dates else None, "max": max(dates) if dates else None},
        "missing_fields": {
            "missing_required_text": missing_text,
            "empty_title": sum(1 for row in rows if not str(row.get("title") or "").strip()),
            "empty_summary": sum(1 for row in rows if not str(row.get("summary") or "").strip()),
            "empty_snippet": sum(1 for row in rows if not str(row.get("content_snippet") or "").strip()),
            "empty_full_text": sum(1 for row in rows if not str(row.get("full_text") or "").strip()),
            "empty_url": sum(1 for row in rows if not str(row.get("url") or "").strip()),
        },
        "historical_memberships": dict(exposure),
        "source_population_csv": args.output_csv,
    }
    completeness = {field: field_stats(rows, field, field in {"article_id", "url", "title", "summary", "content_snippet", "stock_code", "issuer_id"}) for field in ["article_id", "manual_label_id", "manual_label", "stock_code", "issuer_id", "title", "summary", "content_snippet", "full_text", "url", "source", "publication_timestamp", "sample_method", "user_id"]}
    completeness["text_fields"] = summary["missing_fields"]
    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    Path("reports/database_source_field_completeness.json").write_text(json.dumps(completeness, indent=2), encoding="utf-8")
    fields = list(output_rows[0])
    write_csv(Path(args.output_csv), output_rows, fields)
    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
