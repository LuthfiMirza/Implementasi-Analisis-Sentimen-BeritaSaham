#!/usr/bin/env python3
"""R7 ablation: does input-text construction (title-only / title+summary / entity-prefixed)
change sentiment classification quality?

Discipline (matches the rest of this project):
  * All 3 variants train on the EXACT SAME article pool (data/evaluation/official/sentiment-test-v1
    train/val split, 1348/238 rows) -- only the input-text construction differs. This isolates the
    one variable being tested (input format), unlike comparing against production v1 which was
    trained on an entirely different, smaller, older pool.
  * Evaluation happens on the LOCKED test set (283 rows, same article_ids as sentiment-test-v1/test.jsonl)
    with each variant's own matching text transform (data/evaluation/ablation/{variant}/test.jsonl) --
    the row selection and labels are identical across variants, only text differs, so this remains a
    fair apples-to-apples comparison.
  * title_summary is the CURRENT PRODUCTION FORMULA -- verified byte-identical to the official locked
    test.jsonl before this script runs. It doubles as this ablation's own local baseline (trained on
    the NEW pool) AND is directly comparable to production v1's official macro-F1 (0.8096) since the
    text transform matches exactly (only the training pool differs between this run and production).
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
ABLATION_DIR = Path("data/evaluation/ablation")
CANDIDATE_ROOT = Path("storage/app/sentiment_model/_r7_ablation")
REPORT_JSON = Path("output/prediction_research/sentiment_r7_ablation_report.json")
REPORT_TXT = Path("output/prediction_research/sentiment_r7_ablation_report.txt")
CLASS_ORDER = ["positive", "neutral", "negative"]
MAX_LENGTH = 256
SEED = 42
VARIANTS = ["title_summary", "title_only", "entity_prefix"]
PRODUCTION_OFFICIAL_MACRO_F1 = 0.8096  # indobert_finetuned_v1 on sentiment-test-v1, different training pool


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def train_and_eval(variant: str, epochs: int) -> dict:
    train_rows = load_jsonl(ABLATION_DIR / variant / "train.jsonl")
    val_rows = load_jsonl(ABLATION_DIR / variant / "val.jsonl")
    test_rows = load_jsonl(ABLATION_DIR / variant / "test.jsonl")

    candidate_dir = CANDIDATE_ROOT / variant
    # Resume support: this environment has repeatedly killed long-running background training
    # mid-way (session/turn boundaries, not process crashes). If a complete model was already
    # saved here, skip straight to evaluation instead of retraining from scratch.
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
        # NOTE: trainer.train(resume_from_checkpoint=...) is NOT usable here -- transformers'
        # optimizer/scheduler restore calls torch.load() on optimizer.pt, which is blocked by a
        # security check requiring torch>=2.6 (this env has 2.2.2, CVE-2025-32434). Any partial
        # checkpoint under candidate_dir/checkpoints/ is retrain-from-scratch sunk cost, not resumable.
        trainer.train()

    test_pred = trainer.predict(test_ds)
    test_pred_labels = [id2label[i] for i in np.argmax(test_pred.predictions, axis=-1)]
    test_true_labels = [r["label"] for r in test_rows]
    macro_f1 = round(float(f1_score(test_true_labels, test_pred_labels, labels=CLASS_ORDER, average="macro", zero_division=0)), 4)
    accuracy = round(float(np.mean([a == b for a, b in zip(test_true_labels, test_pred_labels)])), 4)
    report = classification_report(test_true_labels, test_pred_labels, labels=CLASS_ORDER, zero_division=0, output_dict=True)
    per_class = {cls: round(float(report[cls]["f1-score"]), 4) for cls in CLASS_ORDER}

    candidate_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(candidate_dir))
    tokenizer.save_pretrained(str(candidate_dir))

    return {
        "variant": variant, "train_rows": len(train_rows), "val_rows": len(val_rows), "test_rows": len(test_rows),
        "test_macro_f1": macro_f1, "test_accuracy": accuracy, "test_per_class_f1": per_class,
        "candidate_dir": str(candidate_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--variants", nargs="*", default=VARIANTS)
    args = parser.parse_args()

    results = []
    for variant in args.variants:
        print(f"\n=== {variant} (epochs={args.epochs}) ===", flush=True)
        result = train_and_eval(variant, args.epochs)
        print(f"  test_macro_f1={result['test_macro_f1']} accuracy={result['test_accuracy']} per_class={result['test_per_class_f1']}", flush=True)
        results.append(result)

    baseline = next((r for r in results if r["variant"] == "title_summary"), None)
    lines = [
        "R7 Ablation: Input Text Construction",
        "=====================================",
        "",
        f"All variants trained on the SAME pool: data/evaluation/official/sentiment-test-v1 "
        f"(train={results[0]['train_rows']}, val={results[0]['val_rows']}) -- only input-text construction differs.",
        f"Evaluated on the locked official test article_ids (n={results[0]['test_rows']}), each variant's own "
        f"matching text transform.",
        f"For reference (NOT a clean ablation comparison -- different training pool): production "
        f"indobert_finetuned_v1 official macro-F1 on sentiment-test-v1 = {PRODUCTION_OFFICIAL_MACRO_F1}",
        "",
    ]
    for r in results:
        marker = "  <- same formula as production (local baseline for this ablation)" if r["variant"] == "title_summary" else ""
        lines.append(f"{r['variant']:16s} test_macro_f1={r['test_macro_f1']:.4f}  accuracy={r['test_accuracy']:.4f}  "
                     f"per_class={r['test_per_class_f1']}{marker}")
    if baseline:
        lines.append("")
        lines.append("Delta vs title_summary (this ablation's own local baseline, same training pool):")
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
