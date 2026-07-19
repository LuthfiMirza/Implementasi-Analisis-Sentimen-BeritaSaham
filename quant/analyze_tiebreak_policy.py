#!/usr/bin/env python3
"""Empirically decide the sentiment tiebreak policy: on the held-out test
split, restricted to rows where the FINE-TUNED ML disagrees with the
rule-based analyzer (the actual condition SentimentTiebreakResolver acts on),
which one matches the human label more often?
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

TEST_PATH = Path("storage/app/sentiment_finetune/test.jsonl")
API_URL = "http://127.0.0.1:8002/sentiment"
REPORT_PATH = Path("output/prediction_research/sentiment_tiebreak_policy_analysis.json")


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    rows = load_jsonl(TEST_PATH)
    print(f"Loaded {len(rows)} test rows")

    for row in rows:
        response = requests.post(API_URL, json={"inputs": row["text"]}, timeout=15)
        response.raise_for_status()
        row["finetuned_ml_label"] = response.json()["label"]

    disagreement_rows = [r for r in rows if r["finetuned_ml_label"] != r["rule_sentiment_label"]]
    agreement_rows = [r for r in rows if r["finetuned_ml_label"] == r["rule_sentiment_label"]]

    print(f"Disagreement (finetuned ML vs rule): {len(disagreement_rows)}/{len(rows)}")
    print(f"Agreement: {len(agreement_rows)}/{len(rows)}")

    def accuracy(subset: list[dict], pred_key: str) -> tuple[int, int, float]:
        correct = sum(1 for r in subset if r[pred_key] == r["label"])
        total = len(subset)
        return correct, total, round(correct / total, 4) if total else 0.0

    ml_correct, ml_total, ml_acc = accuracy(disagreement_rows, "finetuned_ml_label")
    rule_correct, rule_total, rule_acc = accuracy(disagreement_rows, "rule_sentiment_label")

    # Also: old policy comparison for context -- old raw ML vs rule on this same disagreement subset
    old_ml_correct, old_ml_total, old_ml_acc = accuracy(disagreement_rows, "ml_sentiment_label")

    # Overall accuracy (all 120 rows) for both, for context
    ml_overall_correct, ml_overall_total, ml_overall_acc = accuracy(rows, "finetuned_ml_label")
    rule_overall_correct, rule_overall_total, rule_overall_acc = accuracy(rows, "rule_sentiment_label")

    recommendation = "finetuned_ml_wins_tiebreak" if ml_acc > rule_acc else (
        "rule_wins_tiebreak" if rule_acc > ml_acc else "tie_no_clear_winner"
    )

    summary = {
        "test_set_size": len(rows),
        "disagreement_count": len(disagreement_rows),
        "disagreement_share": round(len(disagreement_rows) / len(rows), 4),
        "on_disagreement_subset": {
            "finetuned_ml_accuracy": {"correct": ml_correct, "total": ml_total, "accuracy": ml_acc},
            "rule_based_accuracy": {"correct": rule_correct, "total": rule_total, "accuracy": rule_acc},
            "old_raw_ml_accuracy_for_context": {"correct": old_ml_correct, "total": old_ml_total, "accuracy": old_ml_acc},
        },
        "overall_test_set_accuracy_for_context": {
            "finetuned_ml": ml_overall_acc,
            "rule_based": rule_overall_acc,
        },
        "recommendation": recommendation,
    }

    REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
