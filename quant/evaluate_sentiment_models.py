#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from datasets import Dataset
from sklearn.metrics import classification_report, f1_score
from transformers import AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding, Trainer, TrainingArguments

CLASS_ORDER = ["positive", "neutral", "negative"]
MAX_LENGTH = 256
PRODUCTION_HARD_CASE_MACRO_F1 = 0.5816
ALLOWED_DEGRADATION = 0.05


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def baseline(rows: list[dict], key: str) -> dict[str, object]:
    y_true = [row["label"] for row in rows]
    y_pred = [row.get(key) or "neutral" for row in rows]
    return metrics(y_true, y_pred)


def metrics(y_true: list[str], y_pred: list[str]) -> dict[str, object]:
    return {
        "macro_f1": round(float(f1_score(y_true, y_pred, labels=CLASS_ORDER, average="macro", zero_division=0)), 4),
        "accuracy": round(float(np.mean([a == b for a, b in zip(y_true, y_pred)])), 4),
        "classification_report": classification_report(y_true, y_pred, labels=CLASS_ORDER, zero_division=0, output_dict=True),
    }


def evaluate_model(model_dir: Path, rows: list[dict]) -> dict[str, object]:
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    id2label = {int(k): v for k, v in model.config.id2label.items()}

    dataset = Dataset.from_dict({"text": [row["text"] for row in rows]}).map(
        lambda batch: tokenizer(batch["text"], truncation=True, max_length=MAX_LENGTH),
        batched=True,
    )
    trainer = Trainer(
        model=model,
        args=TrainingArguments(output_dir="/tmp/sentimena_eval", use_cpu=True, report_to=[], per_device_eval_batch_size=16),
        data_collator=DataCollatorWithPadding(tokenizer=tokenizer),
    )
    predictions = trainer.predict(dataset)
    labels = [id2label[int(i)] for i in np.argmax(predictions.predictions, axis=-1)]

    return metrics([row["label"] for row in rows], labels)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-model", default="storage/app/sentiment_model/indobert_finetuned_v1")
    parser.add_argument("--candidate-model", default="storage/app/sentiment_model/indobert_finetuned_r5b_candidate")
    parser.add_argument("--hard-test", default="storage/app/sentiment_finetune/r5b_train/test.jsonl")
    parser.add_argument("--representative-test", default="storage/app/sentiment_finetune/r5b_representative/test.jsonl")
    parser.add_argument("--report-json", default="output/prediction_research/sentiment_r5b_dual_eval_report.json")
    parser.add_argument("--report-txt", default="output/prediction_research/sentiment_r5b_dual_eval_report.txt")
    args = parser.parse_args()

    datasets = {
        "legacy_hard_case": load_jsonl(Path(args.hard_test)),
        "representative_random": load_jsonl(Path(args.representative_test)),
    }
    payload: dict[str, object] = {
        "datasets": {},
        "models": {"production": args.production_model, "candidate": args.candidate_model},
        "caveat": "legacy_hard_case and representative_random are separate populations; representative_random is not comparable to the old hard-case 0.5816 benchmark.",
    }

    for name, rows in datasets.items():
        payload["datasets"][name] = {
            "size": len(rows),
            "label_distribution": {label: sum(1 for row in rows if row["label"] == label) for label in CLASS_ORDER},
            "production": evaluate_model(Path(args.production_model), rows),
            "candidate": evaluate_model(Path(args.candidate_model), rows),
            "rule_based": baseline(rows, "rule_sentiment_label"),
            "stored_ml": baseline(rows, "ml_sentiment_label"),
        }

    hard = payload["datasets"]["legacy_hard_case"]
    hard_floor = round(PRODUCTION_HARD_CASE_MACRO_F1 - ALLOWED_DEGRADATION, 4)
    payload["gate"] = {
        "rule": "candidate_macro_f1 on legacy_hard_case must not degrade by more than 0.05 vs original production hard-case benchmark 0.5816; representative_random is reported separately only",
        "production_hard_case_macro_f1": PRODUCTION_HARD_CASE_MACRO_F1,
        "allowed_degradation": ALLOWED_DEGRADATION,
        "hard_case_floor": hard_floor,
        "passed": bool(hard["candidate"]["macro_f1"] >= hard_floor),
    }

    report_json = Path(args.report_json)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = ["Sentiment R5b Dual Evaluation", "==============================", ""]
    for name in ["legacy_hard_case", "representative_random"]:
        row = payload["datasets"][name]
        lines.extend([
            f"{name} (n={row['size']}, labels={row['label_distribution']}):",
            f"  production macro-F1 : {row['production']['macro_f1']}",
            f"  candidate macro-F1  : {row['candidate']['macro_f1']}",
            f"  rule-based macro-F1 : {row['rule_based']['macro_f1']}",
            f"  stored ML macro-F1  : {row['stored_ml']['macro_f1']}",
            "",
        ])
    lines.extend([
        f"Gate: {'PASSED' if payload['gate']['passed'] else 'FAILED'}",
        f"Gate rule: candidate legacy_hard_case macro-F1 >= {payload['gate']['hard_case_floor']} (0.5816 - 0.05)",
    ])
    report_txt = Path(args.report_txt)
    report_txt.parent.mkdir(parents=True, exist_ok=True)
    report_txt.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
