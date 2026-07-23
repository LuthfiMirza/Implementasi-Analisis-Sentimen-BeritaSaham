#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

LABELS = {"positive", "neutral", "negative"}
DEFAULT_SETS = {
    "active_train": "storage/app/sentiment_finetune/train.jsonl",
    "active_validation": "storage/app/sentiment_finetune/val.jsonl",
    "active_test_candidate": "storage/app/sentiment_finetune/test.jsonl",
    "r5b_hard_case_diagnostic": "output/prediction_research/sentiment_r5b_locked_tests/legacy_hard_case_test.jsonl",
    "r5b_representative_diagnostic": "output/prediction_research/sentiment_r5b_locked_tests/representative_random_test.jsonl",
}
HISTORICAL_REPORT = "output/prediction_research/sentiment_finetune_report.json"


def normalize(value: Any) -> str:
    text = "" if value is None else str(value).lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path, split: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["_split"] = split
        row["_source_path"] = str(path)
        row["_row_number"] = index
        row["_article_id"] = str(row.get("news_article_id") or row.get("article_id") or row.get("id") or "")
        row["_label"] = row.get("label")
        row["_sample_method"] = row.get("sample_method")
        row["_text"] = str(row.get("text") or "")
        row["_title"] = str(row.get("title") or "")
        row["_url"] = str(row.get("source_url") or row.get("url") or "")
        row["_normalized_title"] = normalize(row["_title"] or row["_text"][:160])
        row["_normalized_text"] = normalize(row["_text"])
        row["_normalized_url"] = normalize(row["_url"])
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def token_set(text: str) -> set[str]:
    return {token for token in text.split() if len(token) > 2}


def cheap_candidate(left: str, right: str) -> bool:
    if not left or not right:
        return False
    short, long = sorted((len(left), len(right)))
    if short == 0 or short / long < 0.55:
        return False
    left_tokens = token_set(left[:600])
    right_tokens = token_set(right[:600])
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
    return overlap >= 0.55


def similarity(left: str, right: str) -> float:
    if not cheap_candidate(left, right):
        return 0.0
    return SequenceMatcher(None, left[:700], right[:700]).ratio()


def add_overlap(overlaps: list[dict[str, Any]], left: dict[str, Any], right: dict[str, Any], kind: str, score: float) -> None:
    overlaps.append({
        "left_split": left["_split"],
        "right_split": right["_split"],
        "left_article_id": left["_article_id"],
        "right_article_id": right["_article_id"],
        "similarity": round(score, 6),
        "overlap_type": kind,
        "left_label": left.get("_label"),
        "right_label": right.get("_label"),
        "left_sample_method": left.get("_sample_method"),
        "right_sample_method": right.get("_sample_method"),
        "left_source_path": left.get("_source_path"),
        "right_source_path": right.get("_source_path"),
        "left_row_number": left.get("_row_number"),
        "right_row_number": right.get("_row_number"),
    })


def audit_sets(set_paths: dict[str, Path], near_threshold: float, output_dir: Path) -> dict[str, Any]:
    split_rows = {name: load_jsonl(path, name) for name, path in set_paths.items()}
    all_rows = [row for rows in split_rows.values() for row in rows]

    inventory_rows = []
    for name, rows in split_rows.items():
        labels = Counter(row.get("_label") for row in rows)
        samples = Counter(row.get("_sample_method") for row in rows)
        article_ids = [row["_article_id"] for row in rows if row["_article_id"]]
        texts = [row["_normalized_text"] for row in rows if row["_normalized_text"]]
        inventory_rows.append({
            "set": name,
            "path": str(set_paths[name]),
            "exists": set_paths[name].exists(),
            "sha256": sha256_file(set_paths[name]),
            "size": len(rows),
            "positive": labels.get("positive", 0),
            "neutral": labels.get("neutral", 0),
            "negative": labels.get("negative", 0),
            "sample_methods": json.dumps(dict(samples), sort_keys=True),
            "unique_article_ids": len(set(article_ids)),
            "duplicate_article_ids": len(article_ids) - len(set(article_ids)),
            "duplicate_texts": len(texts) - len(set(texts)),
            "invalid_labels": sum(1 for row in rows if row.get("_label") not in LABELS),
        })

    overlaps: list[dict[str, Any]] = []
    near_duplicates: list[dict[str, Any]] = []
    label_conflicts: list[dict[str, Any]] = []

    names = list(split_rows)
    for left_index, left_name in enumerate(names):
        for right_name in names[left_index:]:
            left_rows = split_rows[left_name]
            right_rows = split_rows[right_name]
            same_split = left_name == right_name
            for i, left in enumerate(left_rows):
                start = i + 1 if same_split else 0
                for right in right_rows[start:]:
                    if left["_article_id"] and left["_article_id"] == right["_article_id"]:
                        add_overlap(overlaps, left, right, "article_id", 1.0)
                    if left["_normalized_url"] and left["_normalized_url"] == right["_normalized_url"]:
                        add_overlap(overlaps, left, right, "url", 1.0)
                    if left["_normalized_title"] and left["_normalized_title"] == right["_normalized_title"]:
                        add_overlap(overlaps, left, right, "normalized_title", 1.0)
                    if left["_normalized_text"] and left["_normalized_text"] == right["_normalized_text"]:
                        add_overlap(overlaps, left, right, "normalized_text", 1.0)
                        if left.get("_label") != right.get("_label"):
                            add_overlap(label_conflicts, left, right, "identical_text_label_conflict", 1.0)
                    title_score = similarity(left["_normalized_title"], right["_normalized_title"])
                    text_score = similarity(left["_normalized_text"], right["_normalized_text"])
                    if 0 < title_score >= near_threshold and left["_normalized_title"] != right["_normalized_title"]:
                        add_overlap(near_duplicates, left, right, "near_duplicate_title", title_score)
                    if 0 < text_score >= near_threshold and left["_normalized_text"] != right["_normalized_text"]:
                        add_overlap(near_duplicates, left, right, "near_duplicate_text", text_score)

    active_test_material = [row for row in overlaps + near_duplicates if {
        row["left_split"], row["right_split"]
    } & {"active_test_candidate"} and {
        row["left_split"], row["right_split"]
    } & {"active_train", "active_validation"}]

    status = "unverified"
    reasons = [
        "No repository evidence proves active test was never used for tuning/checkpoint/preprocessing/guideline decisions.",
        "Ground-truth labels structurally come from exported manual-label dataset, but annotator independence requires owner attestation.",
    ]
    if active_test_material:
        status = "likely_contaminated"
        reasons.append("Active test has overlap or near-duplicate findings with active train/validation.")

    summary = {
        "contract_version": "1.0",
        "status": status,
        "near_duplicate_threshold": near_threshold,
        "sets": inventory_rows,
        "overlap_count": len(overlaps),
        "near_duplicate_count": len(near_duplicates),
        "label_conflict_count": len(label_conflicts),
        "active_test_material_findings": len(active_test_material),
        "status_reasons": reasons,
        "historical_report": {
            "path": HISTORICAL_REPORT,
            "exists": Path(HISTORICAL_REPORT).exists(),
            "sha256": sha256_file(Path(HISTORICAL_REPORT)),
        },
    }

    write_csv(output_dir / "evaluation_split_inventory.csv", inventory_rows, [
        "set", "path", "exists", "sha256", "size", "positive", "neutral", "negative",
        "sample_methods", "unique_article_ids", "duplicate_article_ids", "duplicate_texts", "invalid_labels",
    ])
    write_csv(output_dir / "evaluation_overlap.csv", overlaps, [
        "left_split", "right_split", "left_article_id", "right_article_id", "similarity", "overlap_type",
        "left_label", "right_label", "left_sample_method", "right_sample_method", "left_source_path",
        "right_source_path", "left_row_number", "right_row_number",
    ])
    write_csv(output_dir / "evaluation_near_duplicates.csv", near_duplicates, [
        "left_split", "right_split", "left_article_id", "right_article_id", "similarity", "overlap_type",
        "left_label", "right_label", "left_sample_method", "right_sample_method", "left_source_path",
        "right_source_path", "left_row_number", "right_row_number",
    ])
    write_csv(output_dir / "evaluation_label_conflicts.csv", label_conflicts, [
        "left_split", "right_split", "left_article_id", "right_article_id", "similarity", "overlap_type",
        "left_label", "right_label", "left_sample_method", "right_sample_method", "left_source_path",
        "right_source_path", "left_row_number", "right_row_number",
    ])
    (output_dir / "evaluation_contract_audit.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit sentiment evaluation split inventory and leakage without mutating data.")
    parser.add_argument("--near-threshold", type=float, default=0.92)
    parser.add_argument("--output-dir", default="reports")
    for name, default in DEFAULT_SETS.items():
        parser.add_argument(f"--{name.replace('_', '-')}", default=default)
    args = parser.parse_args()
    set_paths = {name: Path(getattr(args, name)) for name in DEFAULT_SETS}
    summary = audit_sets(set_paths, args.near_threshold, Path(args.output_dir))
    print(json.dumps({
        "status": summary["status"],
        "overlap_count": summary["overlap_count"],
        "near_duplicate_count": summary["near_duplicate_count"],
        "label_conflict_count": summary["label_conflict_count"],
        "active_test_material_findings": summary["active_test_material_findings"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
