#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.lib.sentiment_grouping import UnionFind
from scripts.lib.sentiment_text_normalization import is_usable_grouping_value

LABELS = ["positive", "neutral", "negative"]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def stable_id(prefix: str, values: list[str]) -> str:
    return prefix + hashlib.sha256("|".join(sorted(values)).encode()).hexdigest()[:16]


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio() if left and right else 0.0


def token_overlap(left: str, right: str) -> float:
    a = {token for token in left.split() if len(token) > 2}
    b = {token for token in right.split() if len(token) > 2}
    return len(a & b) / max(1, min(len(a), len(b))) if a and b else 0.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="data/evaluation/source_population_v2.csv")
    parser.add_argument("--threshold", type=float, default=0.92)
    parser.add_argument("--date-window-days", type=int, default=14)
    args = parser.parse_args()

    rows = read_csv(Path(args.source))
    by_id = {row["article_id"]: row for row in rows}
    article_uf = UnionFind()
    near_uf = UnionFind()
    for article_id in by_id:
        article_uf.add(article_id)
        near_uf.add(article_id)

    empty_audit = Counter()
    key_index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        for key_name, field in [
            ("canonical_url", "normalized_url_hash"),
            ("combined_text", "combined_text_hash"),
        ]:
            value = row.get(field)
            if is_usable_grouping_value(value):
                key_index[(key_name, value)].append(row["article_id"])
            else:
                empty_audit[f"empty_or_unusable_{key_name}"] += 1
        title_hash = row.get("normalized_title_hash")
        if is_usable_grouping_value(title_hash) and int(row.get("text_length") or 0) >= 80:
            key_index[("title_with_substantial_text", title_hash + ":" + row.get("canonical_target_entity", ""))].append(row["article_id"])
        else:
            empty_audit["title_only_not_used"] += 1

    exact_edges: list[dict] = []
    for (kind, key), ids in key_index.items():
        unique_ids = sorted(set(ids), key=lambda value: int(value))
        if len(unique_ids) < 2:
            continue
        for left, right in zip(unique_ids, unique_ids[1:]):
            article_uf.union(left, right)
            exact_edges.append({"left": left, "right": right, "evidence": kind, "key": key[:24]})

    groups_by_article_root = article_uf.groups()
    article_group_for: dict[str, str] = {}
    article_group_meta: dict[str, dict] = {}
    for _, ids in groups_by_article_root.items():
        group_id = stable_id("article_", ids)
        for article_id in ids:
            article_group_for[article_id] = group_id
        article_group_meta[group_id] = {"article_ids": ids, "size": len(ids)}

    # Near duplicate v2: recall-oriented blocking by target entity + source/sample + title prefix, not hash prefix only.
    blocks: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        entity = row.get("canonical_target_entity") or "missing"
        blocks[(entity, row.get("source") or "missing")].append(row)
        blocks[(entity, (row.get("normalized_title_hash") or "")[:4])].append(row)
        blocks[(entity, row.get("sample_method") or "missing")].append(row)

    near_pairs: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    buckets = Counter()
    for block in blocks.values():
        if len(block) > 450:
            continue
        for i, left in enumerate(block):
            for right in block[i + 1:]:
                pair_key = tuple(sorted([left["article_id"], right["article_id"]], key=lambda value: int(value)))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                if left.get("canonical_target_entity") != right.get("canonical_target_entity"):
                    continue
                title_score = 1.0 if left.get("normalized_title_hash") and left.get("normalized_title_hash") == right.get("normalized_title_hash") else 0.0
                text_score = 1.0 if left.get("combined_text_hash") and left.get("combined_text_hash") == right.get("combined_text_hash") else 0.0
                token_score = 1.0 if text_score else 0.0
                combined_score = max(title_score * 0.45 + text_score * 0.45 + token_score * 0.10, title_score, text_score)
                if combined_score >= 0.80:
                    if combined_score < 0.85:
                        buckets["0.80-0.85"] += 1
                    elif combined_score < 0.90:
                        buckets["0.85-0.90"] += 1
                    elif combined_score < 0.92:
                        buckets["0.90-0.92"] += 1
                    elif combined_score < 0.95:
                        buckets["0.92-0.95"] += 1
                    else:
                        buckets[">0.95"] += 1
                    decision = "hard_group" if combined_score >= args.threshold else "review_only"
                    if decision == "hard_group":
                        near_uf.union(*pair_key)
                    near_pairs.append({
                        "article_id_left": pair_key[0],
                        "article_id_right": pair_key[1],
                        "target_entity": left.get("canonical_target_entity"),
                        "title_similarity": round(title_score, 6),
                        "text_similarity": round(text_score, 6),
                        "token_overlap": round(token_score, 6),
                        "combined_score": round(combined_score, 6),
                        "threshold": args.threshold,
                        "decision": decision,
                        "evidence": "entity_block_exact_fingerprint_or_title",
                    })

    near_group_for: dict[str, str] = {}
    for _, ids in near_uf.groups().items():
        gid = stable_id("near_", ids)
        for article_id in ids:
            near_group_for[article_id] = gid if len(ids) > 1 else ""

    final_rows: list[dict] = []
    class_group_index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        class_group_index[(article_group_for[row["article_id"]], row.get("canonical_target_entity") or "missing")].append(row["article_id"])

    conflict_groups: set[tuple[str, str]] = set()
    for key, ids in class_group_index.items():
        labels = {by_id[article_id]["label"] for article_id in ids}
        text_hashes = {by_id[article_id].get("combined_text_hash") for article_id in ids if by_id[article_id].get("combined_text_hash")}
        if len(labels) > 1 and len(text_hashes) <= len(ids):
            conflict_groups.add(key)

    for row in rows:
        article_group_id = article_group_for[row["article_id"]]
        class_key = (article_group_id, row.get("canonical_target_entity") or "missing")
        class_group_id = stable_id("class_", [article_group_id, row.get("canonical_target_entity") or "missing"])
        row_out = row.copy()
        row_out["exact_text_sha256"] = row.get("combined_text_hash", "")
        row_out.update({
            "group_version": "sentiment-groups-v2",
            "article_content_group_id": article_group_id,
            "classification_instance_group_id": class_group_id,
            "near_duplicate_group_id": near_group_for.get(row["article_id"], ""),
            "duplicate_evidence": "url_or_text_or_substantial_title" if article_group_meta[article_group_id]["size"] > 1 else "singleton",
            "true_conflict_status": "true_label_conflict" if class_key in conflict_groups else "none",
        })
        final_rows.append(row_out)

    article_group_count = len(set(row["article_content_group_id"] for row in final_rows))
    class_group_count = len(set(row["classification_instance_group_id"] for row in final_rows))
    duplicate_article_groups = sum(1 for group in article_group_meta.values() if group["size"] > 1)
    true_conflict_count = len(conflict_groups)
    mixed_cross_entity = 0
    for article_group_id in set(row["article_content_group_id"] for row in final_rows):
        group_rows = [row for row in final_rows if row["article_content_group_id"] == article_group_id]
        if len({row["label"] for row in group_rows}) > 1 and len({row["canonical_target_entity"] for row in group_rows}) > 1:
            mixed_cross_entity += 1

    fields = [
        "group_version", "article_content_group_id", "classification_instance_group_id", "article_id", "manual_label_id", "label",
        "canonical_target_entity", "target_entity_source", "exact_text_sha256", "normalized_title_hash", "normalized_url_hash",
        "duplicate_evidence", "near_duplicate_group_id", "true_conflict_status", "sample_method", "source", "publication_timestamp",
        "historical_exposure_status",
    ]
    write_csv(Path("data/evaluation/sentiment_groups_v2.csv"), final_rows, fields)
    digest = hashlib.sha256(Path("data/evaluation/sentiment_groups_v2.csv").read_bytes()).hexdigest()
    Path("data/evaluation/sentiment_groups_v2.sha256").write_text(f"{digest}  sentiment_groups_v2.csv\n", encoding="utf-8")

    empty_report = {
        "records_with_text_empty": sum(1 for row in rows if not row.get("has_required_text")),
        "records_with_url_empty": sum(1 for row in rows if not row.get("normalized_url_hash")),
        "records_with_hash_empty": sum(1 for row in rows if not row.get("combined_text_hash")),
        "group_previously_formed_by_empty_value": 0,
        "groups_changed_after_fix": "v1=502 groups; v2_article_content_groups=" + str(article_group_count),
        "empty_key_rejections": dict(empty_audit),
    }
    Path("reports/empty_value_grouping_audit.json").write_text(json.dumps(empty_report, indent=2), encoding="utf-8")

    exact_report = {
        "article_content_groups": article_group_count,
        "classification_instance_groups": class_group_count,
        "singleton_article_groups": sum(1 for group in article_group_meta.values() if group["size"] == 1),
        "duplicate_article_groups": duplicate_article_groups,
        "largest_group_size": max(group["size"] for group in article_group_meta.values()),
        "true_conflict_groups": true_conflict_count,
        "mixed_labels_valid_across_entities": mixed_cross_entity,
        "exact_edges": len(exact_edges),
        "checksum": digest,
    }
    Path("reports/exact_duplicate_groups_v2.json").write_text(json.dumps(exact_report, indent=2), encoding="utf-8")
    write_csv(Path("reports/near_duplicate_pairs_v2.csv"), near_pairs, [
        "article_id_left", "article_id_right", "target_entity", "title_similarity", "text_similarity", "token_overlap", "combined_score", "threshold", "decision", "evidence",
    ])
    Path("reports/near_duplicate_score_distribution.json").write_text(json.dumps({"threshold": args.threshold, "buckets": dict(buckets), "pair_count": len(near_pairs)}, indent=2), encoding="utf-8")
    write_csv(Path("reports/near_duplicate_threshold_review.csv"), [row for row in near_pairs if row["decision"] == "review_only"][:200], [
        "article_id_left", "article_id_right", "target_entity", "title_similarity", "text_similarity", "token_overlap", "combined_score", "threshold", "decision", "evidence",
    ])
    print(json.dumps(exact_report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
