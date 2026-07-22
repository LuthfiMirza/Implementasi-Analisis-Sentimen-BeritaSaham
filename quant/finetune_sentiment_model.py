#!/usr/bin/env python3
"""Fine-tune the production IndoBERT sentiment model on 801 manually labeled
articles (all disagreement cases between ML and rule-based analyzers -- a
biased sample, not a random draw; see report caveat).

Gate: the fine-tuned model is only worth promoting to production if its
held-out test macro-F1 beats the rule-based baseline (59.4% on the full
801-sample validation, recomputed here on the exact same 120-row test split
for a rigorous apples-to-apples comparison against both baselines).
"""
from __future__ import annotations

import json
import argparse
from pathlib import Path

import numpy as np
from datasets import Dataset
from sklearn.metrics import classification_report, f1_score
from transformers import (
    AutoConfig,
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)

CHECKPOINT = "w11wo/indonesian-roberta-base-sentiment-classifier"
DATA_DIR = Path("storage/app/sentiment_finetune")
MODEL_OUT_DIR = Path("storage/app/sentiment_model/indobert_finetuned_v1")
REPORT_JSON_PATH = Path("output/prediction_research/sentiment_finetune_report.json")
REPORT_TXT_PATH = Path("output/prediction_research/sentiment_finetune_report.txt")
CLASS_ORDER = ["positive", "neutral", "negative"]
MAX_LENGTH = 256
SEED = 42


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def macro_f1_for_baseline(rows: list[dict], baseline_key: str) -> dict[str, object]:
    y_true = [row["label"] for row in rows]
    y_pred = [row.get(baseline_key) or "neutral" for row in rows]
    f1 = f1_score(y_true, y_pred, labels=CLASS_ORDER, average="macro", zero_division=0)
    report = classification_report(y_true, y_pred, labels=CLASS_ORDER, zero_division=0, output_dict=True)
    return {"macro_f1": round(float(f1), 4), "report": report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-out-dir", default=str(MODEL_OUT_DIR))
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--report-json", default=str(REPORT_JSON_PATH))
    parser.add_argument("--report-txt", default=str(REPORT_TXT_PATH))
    args = parser.parse_args()

    model_out_dir = Path(args.model_out_dir)
    data_dir = Path(args.data_dir)
    report_json_path = Path(args.report_json)
    report_txt_path = Path(args.report_txt)

    train_rows = load_jsonl(data_dir / "train.jsonl")
    val_rows = load_jsonl(data_dir / "val.jsonl")
    test_rows = load_jsonl(data_dir / "test.jsonl")
    print(f"train={len(train_rows)} val={len(val_rows)} test={len(test_rows)}")

    config = AutoConfig.from_pretrained(CHECKPOINT)
    label2id = dict(config.label2id)
    print("label2id from pretrained checkpoint:", label2id)

    tokenizer = AutoTokenizer.from_pretrained(CHECKPOINT)
    model = AutoModelForSequenceClassification.from_pretrained(CHECKPOINT, num_labels=3)
    model.config.label2id = label2id
    model.config.id2label = {v: k for k, v in label2id.items()}

    def to_hf_dataset(rows: list[dict]) -> Dataset:
        return Dataset.from_dict({
            "text": [row["text"] for row in rows],
            "label": [label2id[row["label"]] for row in rows],
        })

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=MAX_LENGTH)

    train_ds = to_hf_dataset(train_rows).map(tokenize, batched=True)
    val_ds = to_hf_dataset(val_rows).map(tokenize, batched=True)
    test_ds = to_hf_dataset(test_rows).map(tokenize, batched=True)

    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        predictions = np.argmax(logits, axis=-1)
        f1 = f1_score(labels, predictions, average="macro", zero_division=0)
        accuracy = float(np.mean(predictions == labels))
        return {"f1_macro": f1, "accuracy": accuracy}

    training_args = TrainingArguments(
        output_dir=str(model_out_dir / "checkpoints"),
        use_cpu=True,  # this Mac's discrete AMD GPU (MPS backend) has too little VRAM for roberta-base fine-tuning
        num_train_epochs=6,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=16,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        save_total_limit=2,
        logging_steps=20,
        seed=SEED,
        report_to=[],
        disable_tqdm=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    trainer.train()

    test_predictions = trainer.predict(test_ds)
    test_pred_ids = np.argmax(test_predictions.predictions, axis=-1)
    id2label = {v: k for k, v in label2id.items()}
    test_pred_labels = [id2label[i] for i in test_pred_ids]
    test_true_labels = [row["label"] for row in test_rows]

    finetuned_f1 = f1_score(test_true_labels, test_pred_labels, labels=CLASS_ORDER, average="macro", zero_division=0)
    finetuned_report = classification_report(test_true_labels, test_pred_labels, labels=CLASS_ORDER, zero_division=0, output_dict=True)

    rule_baseline = macro_f1_for_baseline(test_rows, "rule_sentiment_label")
    ml_baseline = macro_f1_for_baseline(test_rows, "ml_sentiment_label")

    listicle_rows = [row for row in test_rows if "rekomendasi saham" in row["text"].lower()]
    listicle_result = None
    if listicle_rows:
        listicle_indices = [i for i, row in enumerate(test_rows) if "rekomendasi saham" in row["text"].lower()]
        listicle_true = [test_true_labels[i] for i in listicle_indices]
        listicle_pred_finetuned = [test_pred_labels[i] for i in listicle_indices]
        listicle_pred_ml = [test_rows[i].get("ml_sentiment_label") or "neutral" for i in listicle_indices]
        listicle_result = {
            "n": len(listicle_indices),
            "finetuned_accuracy": round(float(np.mean([a == b for a, b in zip(listicle_true, listicle_pred_finetuned)])), 4),
            "raw_ml_accuracy": round(float(np.mean([a == b for a, b in zip(listicle_true, listicle_pred_ml)])), 4),
        }

    gate_passed = bool(round(finetuned_f1, 4) > rule_baseline["macro_f1"])

    summary = {
        "checkpoint": CHECKPOINT,
        "train_size": len(train_rows),
        "val_size": len(val_rows),
        "test_size": len(test_rows),
        "label2id": label2id,
        "caveat": "Manual labels originate from ML-vs-rule disagreement cases plus Q2 active-learning positive/ambiguous candidates (biased hard-case sample, not a random draw from all articles). Metrics characterize performance on this labeled hard-case distribution, not overall article population.",
        "test_set_results": {
            "finetuned_macro_f1": round(float(finetuned_f1), 4),
            "finetuned_classification_report": finetuned_report,
            "rule_based_baseline_macro_f1": rule_baseline["macro_f1"],
            "raw_ml_baseline_macro_f1": ml_baseline["macro_f1"],
        },
        "listicle_pattern_spot_check": listicle_result,
        "gate": {
            "rule": "finetuned_macro_f1 > rule_based_baseline_macro_f1 (both measured on same held-out 120-row test split)",
            "passed": gate_passed,
        },
    }

    if gate_passed:
        model_out_dir.mkdir(parents=True, exist_ok=True)
        trainer.save_model(str(model_out_dir))
        tokenizer.save_pretrained(str(model_out_dir))
        summary["model_saved_to"] = str(model_out_dir)

    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "Sentiment Fine-Tune Report",
        "==========================",
        "",
        f"Checkpoint: {CHECKPOINT}",
        f"Train/val/test: {len(train_rows)}/{len(val_rows)}/{len(test_rows)}",
        "",
        "Test-set macro F1 (same 120-row held-out split for all three):",
        f"  fine-tuned model : {summary['test_set_results']['finetuned_macro_f1']}",
        f"  rule-based       : {summary['test_set_results']['rule_based_baseline_macro_f1']}",
        f"  raw ML (no tune) : {summary['test_set_results']['raw_ml_baseline_macro_f1']}",
        "",
        f"Gate (finetuned > rule-based): {'PASSED' if gate_passed else 'FAILED'}",
        "",
    ]
    if listicle_result:
        lines.append(f"Listicle spot-check (n={listicle_result['n']}): finetuned_acc={listicle_result['finetuned_accuracy']}, raw_ml_acc={listicle_result['raw_ml_accuracy']}")
    report_txt_path.parent.mkdir(parents=True, exist_ok=True)
    report_txt_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
