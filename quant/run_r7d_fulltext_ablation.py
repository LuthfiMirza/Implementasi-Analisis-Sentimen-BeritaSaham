#!/usr/bin/env python3
"""R7d ablation: does adding full_text to the production title+summary formula change
sentiment classification quality?

Discipline (matches quant/run_r7_ablation.py):
  * Both variants train on the EXACT SAME 521-row pool (Fase R7a full_text backfill subset of
    sentiment_manual_labels) and the SAME stratified train/val/test split -- only the input-text
    construction differs (title_summary vs title_summary_fulltext). This isolates the one
    variable being tested.
  * This pool is SMALLER and DIFFERENT from the official sentiment-test-v1 (283-row locked test,
    Fase R6) -- it is NOT directly comparable to the 0.8096 official baseline. It's an exploratory
    ablation, not a re-measurement of production performance. Reported alongside as reference only.
  * Test set has only 4 negative examples (28 total across train/val/test) -- macro-F1 on this
    split has real variance; treat results as directional, not a robust estimate.
  * Production model is NEVER touched. All candidates saved to separate directories.
"""
from __future__ import annotations

import argparse
import json
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
ABLATION_DIR = Path("data/evaluation/r7d_fulltext_ablation")
CANDIDATE_ROOT = Path("storage/app/sentiment_model/_r7d_ablation")
REPORT_JSON = Path("output/prediction_research/sentiment_r7d_fulltext_ablation_report.json")
REPORT_TXT = Path("output/prediction_research/sentiment_r7d_fulltext_ablation_report.txt")
CLASS_ORDER = ["positive", "neutral", "negative"]
MAX_LENGTH = 256
SEED = 42
VARIANTS = ["title_summary", "title_summary_fulltext"]
PRODUCTION_OFFICIAL_MACRO_F1 = 0.8096  # indobert_finetuned_v1 on sentiment-test-v1 (different, larger, disjoint pool)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def train_and_eval(variant: str, epochs: int) -> dict:
    train_rows = load_jsonl(ABLATION_DIR / variant / "train.jsonl")
    val_rows = load_jsonl(ABLATION_DIR / variant / "val.jsonl")
    test_rows = load_jsonl(ABLATION_DIR / variant / "test.jsonl")

    candidate_dir = CANDIDATE_ROOT / variant
    resumed = (candidate_dir / "model.safetensors").is_file()

    config = AutoConfig.from_pretrained(CHECKPOINT)
    label2id = dict(config.label2id)
    id2label = {v: k for k, v in label2id.items()}

    tokenizer = AutoTokenizer.from_pretrained(str(candidate_dir) if resumed else CHECKPOINT)
    model = AutoModelForSequenceClassification.from_pretrained(str(candidate_dir) if resumed else CHECKPOINT, num_labels=3)
    model.config.label2id = label2id
    model.config.id2label = id2label

    def to_hf_dataset(rows):
        return Dataset.from_dict({
            "text": [r["text"] for r in rows],
            "label": [label2id[r["label"]] for r in rows],
        })

    def tokenize(batch):
        return tokenizer(batch["text"], truncation=True, max_length=MAX_LENGTH)

    train_ds = to_hf_dataset(train_rows).map(tokenize, batched=True)
    val_ds = to_hf_dataset(val_rows).map(tokenize, batched=True)
    test_ds = to_hf_dataset(test_rows).map(tokenize, batched=True)
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        return {"f1_macro": f1_score(labels, preds, average="macro", zero_division=0),
                "accuracy": float(np.mean(preds == labels))}

    training_args = TrainingArguments(
        output_dir=str(candidate_dir / "checkpoints"),
        use_cpu=True,
        num_train_epochs=epochs,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=16,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        save_total_limit=1,
        logging_steps=20,
        seed=SEED,
        report_to=[],
        disable_tqdm=True,
    )
    trainer = Trainer(
        model=model, args=training_args, train_dataset=train_ds, eval_dataset=val_ds,
        data_collator=data_collator, compute_metrics=compute_metrics,
    )
    if resumed:
        print(f"  [resume] found complete saved model at {candidate_dir}, skipping training", flush=True)
    else:
        trainer.train()

    test_pred = trainer.predict(test_ds)
    test_pred_labels = [id2label[i] for i in np.argmax(test_pred.predictions, axis=-1)]
    test_true_labels = [r["label"] for r in test_rows]
    macro_f1 = round(float(f1_score(test_true_labels, test_pred_labels, labels=CLASS_ORDER, average="macro", zero_division=0)), 4)
    accuracy = round(float(np.mean([a == b for a, b in zip(test_true_labels, test_pred_labels)])), 4)
    report = classification_report(test_true_labels, test_pred_labels, labels=CLASS_ORDER, zero_division=0, output_dict=True)
    per_class = {cls: round(float(report[cls]["f1-score"]), 4) for cls in CLASS_ORDER}
    per_class_support = {cls: int(report[cls]["support"]) for cls in CLASS_ORDER}

    candidate_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(candidate_dir))
    tokenizer.save_pretrained(str(candidate_dir))

    return {
        "variant": variant, "train_rows": len(train_rows), "val_rows": len(val_rows), "test_rows": len(test_rows),
        "test_macro_f1": macro_f1, "test_accuracy": accuracy, "test_per_class_f1": per_class,
        "test_per_class_support": per_class_support,
        "candidate_dir": str(candidate_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--variants", nargs="*", default=VARIANTS)
    args = parser.parse_args()

    results = []
    for variant in args.variants:
        print(f"\n=== {variant} (epochs={args.epochs}) ===", flush=True)
        result = train_and_eval(variant, args.epochs)
        print(f"  test_macro_f1={result['test_macro_f1']} accuracy={result['test_accuracy']} per_class={result['test_per_class_f1']} support={result['test_per_class_support']}", flush=True)
        results.append(result)

    baseline = next((r for r in results if r["variant"] == "title_summary"), None)
    lines = [
        "R7d Ablation: full_text augmentation",
        "======================================",
        "",
        f"Both variants trained on the SAME 521-row pool (Fase R7a full_text backfill subset, "
        f"train={results[0]['train_rows']}, val={results[0]['val_rows']}) -- only input-text construction differs.",
        f"Evaluated on the same locked test split (n={results[0]['test_rows']}, only 4 negative examples -- "
        f"treat as directional, not a robust estimate).",
        f"NOT directly comparable to official production macro-F1 ({PRODUCTION_OFFICIAL_MACRO_F1}) -- "
        f"different, smaller, disjoint pool (sentiment-test-v1 vs this 521-row full_text subset). Reference only.",
        "",
    ]
    for r in results:
        marker = "  <- baseline (production formula, on this pool)" if r["variant"] == "title_summary" else ""
        lines.append(f"{r['variant']:24s} test_macro_f1={r['test_macro_f1']:.4f}  accuracy={r['test_accuracy']:.4f}  "
                     f"per_class={r['test_per_class_f1']}  support={r['test_per_class_support']}{marker}")
    if baseline:
        lines.append("")
        lines.append("Delta vs title_summary (this ablation's own local baseline, same pool/split):")
        for r in results:
            if r["variant"] == "title_summary":
                continue
            delta = round(r["test_macro_f1"] - baseline["test_macro_f1"], 4)
            lines.append(f"  {r['variant']}: {delta:+.4f}")

    REPORT_TXT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT_JSON.write_text(json.dumps({"results": results, "production_official_macro_f1": PRODUCTION_OFFICIAL_MACRO_F1}, indent=2), encoding="utf-8")
    print("\n" + "\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
