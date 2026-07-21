#!/usr/bin/env python3
"""Class-weighted fine-tune EXPERIMENT for the IndoBERT sentiment model.

Motivation (see plan.md Fase P): the production fine-tuned model (quant/finetune_sentiment_model.py
-> indobert_finetuned_v1) reaches macro-F1 0.5816, dragged down almost entirely by the positive
class (F1 0.377, recall 0.323 -- the model defaults to "neutral" when unsure about positive
articles). This experiment rebalances the training loss via class weighting to raise positive
recall, hopefully lifting macro-F1.

Discipline (identical rigor to the rest of this project):
  * Scheme selection is done ONLY on the val split -- never on test (no data-snooping).
  * The winning scheme is then measured on the held-out test split across 3 seeds and reported as
    mean +/- std, because the test set is small (n=120; positive n=31, negative n=14) and a single
    seed is high-variance.
  * The candidate model is saved to a SEPARATE dir (indobert_finetuned_v2_weighted) and NEVER
    overwrites production. Promotion is a human decision made after reading the report.

This is deliberately a standalone experiment script, not a change to the production trainer.
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path
from statistics import mean, pstdev

import numpy as np
import torch
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
CANDIDATE_DIR = Path("storage/app/sentiment_model/indobert_finetuned_v2_weighted")
SWEEP_ROOT = Path("storage/app/sentiment_model/_weighted_sweep")
REPORT_JSON_PATH = Path("output/prediction_research/sentiment_weighted_experiment_report.json")
REPORT_TXT_PATH = Path("output/prediction_research/sentiment_weighted_experiment_report.txt")
CLASS_ORDER = ["positive", "neutral", "negative"]
MAX_LENGTH = 256

# Baselines from the current production report (same 120-row held-out test split), for context.
PRODUCTION_FINETUNED_MACRO_F1 = 0.5816
RULE_BASELINE_MACRO_F1 = 0.5482

SELECTION_SEED = 42
CONFIRMATION_SEEDS = [0, 123]
SCHEMES = ["none", "inverse", "sqrt_inverse"]


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def macro_f1_for_baseline(rows: list[dict], baseline_key: str) -> float:
    y_true = [row["label"] for row in rows]
    y_pred = [row.get(baseline_key) or "neutral" for row in rows]
    return round(float(f1_score(y_true, y_pred, labels=CLASS_ORDER, average="macro", zero_division=0)), 4)


def compute_class_weights(train_rows: list[dict], scheme: str, id2label: dict[int, str]) -> torch.Tensor | None:
    """Weights indexed by model label-id order. None => unweighted (standard CrossEntropy)."""
    if scheme == "none":
        return None
    counts = Counter(row["label"] for row in train_rows)
    total = sum(counts.values())
    n_classes = len(counts)
    raw: dict[str, float] = {}
    for label, count in counts.items():
        if scheme == "inverse":
            raw[label] = total / (n_classes * count)
        elif scheme == "sqrt_inverse":
            raw[label] = (total / (n_classes * count)) ** 0.5
        else:
            raise ValueError(f"Unknown scheme: {scheme}")
    # Normalize to mean 1 so the loss magnitude stays comparable across schemes.
    scale = mean(raw.values())
    ordered = [raw[id2label[i]] / scale for i in range(len(id2label))]
    return torch.tensor(ordered, dtype=torch.float32)


class WeightedTrainer(Trainer):
    """Trainer with an optional fixed class-weight vector on the CrossEntropy loss."""

    def __init__(self, *args, class_weights: torch.Tensor | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._class_weights = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits
        weight = self._class_weights.to(logits.device) if self._class_weights is not None else None
        loss = torch.nn.functional.cross_entropy(logits, labels, weight=weight)
        return (loss, outputs) if return_outputs else loss


def train_one(scheme: str, seed: int, train_rows, val_rows, test_rows, epochs: int, save_dir: Path | None) -> dict:
    # Resume support: a prior run of this script can be killed mid-way (session boundary, etc.)
    # after a scheme's model was already fully trained and saved to save_dir. Re-training from
    # scratch would waste real CPU-hours already spent -- if a complete saved model is found,
    # skip straight to evaluation instead.
    resumed = bool(save_dir is not None and (save_dir / "model.safetensors").is_file())

    config = AutoConfig.from_pretrained(CHECKPOINT)
    label2id = dict(config.label2id)
    id2label = {v: k for k, v in label2id.items()}

    tokenizer = AutoTokenizer.from_pretrained(str(save_dir) if resumed else CHECKPOINT)
    model = AutoModelForSequenceClassification.from_pretrained(str(save_dir) if resumed else CHECKPOINT, num_labels=3)
    model.config.label2id = label2id
    model.config.id2label = id2label

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
        return {
            "f1_macro": f1_score(labels, predictions, average="macro", zero_division=0),
            "accuracy": float(np.mean(predictions == labels)),
        }

    training_args = TrainingArguments(
        output_dir=str((save_dir or SWEEP_ROOT / f"tmp_{scheme}_{seed}") / "checkpoints"),
        use_cpu=True,  # discrete AMD GPU (MPS) has too little VRAM for roberta-base fine-tuning
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
        seed=seed,
        report_to=[],
        disable_tqdm=True,
    )

    class_weights = compute_class_weights(train_rows, scheme, id2label)

    trainer = WeightedTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        class_weights=class_weights,
    )
    if resumed:
        print(f"  [resume] found complete saved model at {save_dir}, skipping training, evaluating only", flush=True)
    else:
        trainer.train()

    val_eval = trainer.evaluate()
    val_macro_f1 = round(float(val_eval["eval_f1_macro"]), 4)

    test_pred = trainer.predict(test_ds)
    test_pred_labels = [id2label[i] for i in np.argmax(test_pred.predictions, axis=-1)]
    test_true_labels = [row["label"] for row in test_rows]
    test_macro_f1 = round(float(f1_score(test_true_labels, test_pred_labels, labels=CLASS_ORDER, average="macro", zero_division=0)), 4)
    test_accuracy = round(float(np.mean([a == b for a, b in zip(test_true_labels, test_pred_labels)])), 4)
    report = classification_report(test_true_labels, test_pred_labels, labels=CLASS_ORDER, zero_division=0, output_dict=True)

    if save_dir is not None:
        save_dir.mkdir(parents=True, exist_ok=True)
        trainer.save_model(str(save_dir))
        tokenizer.save_pretrained(str(save_dir))

    per_class = {cls: round(float(report[cls]["f1-score"]), 4) for cls in CLASS_ORDER}
    weights_used = None
    if class_weights is not None:
        weights_used = {id2label[i]: round(float(class_weights[i]), 4) for i in range(len(id2label))}

    return {
        "scheme": scheme,
        "seed": seed,
        "val_macro_f1": val_macro_f1,
        "test_macro_f1": test_macro_f1,
        "test_accuracy": test_accuracy,
        "test_per_class_f1": per_class,
        "class_weights": weights_used,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Class-weighted sentiment fine-tune experiment.")
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--schemes", nargs="*", default=SCHEMES, help="Subset of schemes for a quick smoke test.")
    parser.add_argument("--skip-confirmation-seeds", action="store_true", help="Smoke test: skip the multi-seed confirmation.")
    args = parser.parse_args()

    train_rows = load_jsonl(DATA_DIR / "train.jsonl")
    val_rows = load_jsonl(DATA_DIR / "val.jsonl")
    test_rows = load_jsonl(DATA_DIR / "test.jsonl")
    print(f"train={len(train_rows)} val={len(val_rows)} test={len(test_rows)}", flush=True)

    SWEEP_ROOT.mkdir(parents=True, exist_ok=True)

    # --- Phase 1: sweep schemes at the selection seed, save each candidate model ---
    sweep_results = []
    for scheme in args.schemes:
        print(f"\n=== SWEEP scheme={scheme} seed={SELECTION_SEED} ===", flush=True)
        save_dir = SWEEP_ROOT / f"model_{scheme}"
        result = train_one(scheme, SELECTION_SEED, train_rows, val_rows, test_rows, args.epochs, save_dir)
        print(f"  val_macro_f1={result['val_macro_f1']} test_macro_f1={result['test_macro_f1']} "
              f"acc={result['test_accuracy']} per_class={result['test_per_class_f1']}", flush=True)
        sweep_results.append(result)

    # Selection strictly by VAL macro-F1 (never test).
    winner = max(sweep_results, key=lambda r: r["val_macro_f1"])
    print(f"\n=== WINNER (by val): scheme={winner['scheme']} val={winner['val_macro_f1']} ===", flush=True)

    # --- Phase 2: confirm winner across additional seeds (test is high-variance at n=120) ---
    winner_runs = [winner]  # already includes the selection-seed test result
    if not args.skip_confirmation_seeds:
        for seed in CONFIRMATION_SEEDS:
            print(f"\n=== CONFIRM winner scheme={winner['scheme']} seed={seed} ===", flush=True)
            result = train_one(winner["scheme"], seed, train_rows, val_rows, test_rows, args.epochs, save_dir=None)
            print(f"  test_macro_f1={result['test_macro_f1']} acc={result['test_accuracy']} "
                  f"per_class={result['test_per_class_f1']}", flush=True)
            winner_runs.append(result)

    test_f1s = [r["test_macro_f1"] for r in winner_runs]
    test_accs = [r["test_accuracy"] for r in winner_runs]
    test_f1_mean = round(mean(test_f1s), 4)
    test_f1_std = round(pstdev(test_f1s), 4) if len(test_f1s) > 1 else 0.0

    # Gate: mean test macro-F1 must beat production by a margin larger than its own std (not noise).
    gate_margin = round(test_f1_mean - PRODUCTION_FINETUNED_MACRO_F1, 4)
    gate_passed = bool(gate_margin > test_f1_std and gate_margin > 0)
    verdict = (
        "PROMOTE-WORTHY" if gate_passed
        else ("INCONCLUSIVE (improvement within noise)" if gate_margin > 0 else "NO IMPROVEMENT")
    )

    # Keep only the winner's candidate model; discard the losing sweep dirs.
    for scheme in args.schemes:
        loser_dir = SWEEP_ROOT / f"model_{scheme}"
        if scheme == winner["scheme"]:
            continue
        shutil.rmtree(loser_dir, ignore_errors=True)
    winner_model_dir = SWEEP_ROOT / f"model_{winner['scheme']}"
    if winner_model_dir.exists():
        if CANDIDATE_DIR.exists():
            shutil.rmtree(CANDIDATE_DIR, ignore_errors=True)
        CANDIDATE_DIR.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(winner_model_dir), str(CANDIDATE_DIR))
    shutil.rmtree(SWEEP_ROOT, ignore_errors=True)

    summary = {
        "experiment": "class_weighted_sentiment_finetune",
        "checkpoint": CHECKPOINT,
        "epochs": args.epochs,
        "caveat": "801 labels are all ML-vs-rule disagreement cases (biased hard-case sample). Metrics characterize hard cases, not the overall article population.",
        "baselines_same_test_split": {
            "production_finetuned_macro_f1": PRODUCTION_FINETUNED_MACRO_F1,
            "rule_based_macro_f1": RULE_BASELINE_MACRO_F1,
        },
        "sweep_selection_by_val": [
            {"scheme": r["scheme"], "val_macro_f1": r["val_macro_f1"], "test_macro_f1": r["test_macro_f1"],
             "test_accuracy": r["test_accuracy"], "test_per_class_f1": r["test_per_class_f1"],
             "class_weights": r["class_weights"]}
            for r in sweep_results
        ],
        "winner": {
            "scheme": winner["scheme"],
            "selected_by": "val_macro_f1",
            "val_macro_f1": winner["val_macro_f1"],
            "seeds": [r["seed"] for r in winner_runs],
            "test_macro_f1_per_seed": test_f1s,
            "test_accuracy_per_seed": test_accs,
            "test_macro_f1_mean": test_f1_mean,
            "test_macro_f1_std": test_f1_std,
            "selection_seed_per_class_f1": winner["test_per_class_f1"],
            "class_weights": winner["class_weights"],
        },
        "gate": {
            "rule": "mean test macro-F1 across seeds must exceed production (0.5816) by more than its own std",
            "margin_vs_production": gate_margin,
            "std": test_f1_std,
            "passed": gate_passed,
            "verdict": verdict,
        },
        "candidate_model_dir": str(CANDIDATE_DIR) if CANDIDATE_DIR.exists() else None,
        "production_model_untouched": "storage/app/sentiment_model/indobert_finetuned_v1",
    }
    REPORT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "Class-Weighted Sentiment Fine-Tune Experiment",
        "=============================================",
        "",
        f"Checkpoint: {CHECKPOINT}  |  epochs: {args.epochs}",
        f"Baselines (same 120-row test split): production fine-tuned={PRODUCTION_FINETUNED_MACRO_F1}, rule-based={RULE_BASELINE_MACRO_F1}",
        "",
        "Scheme sweep (selection by VAL macro-F1, test shown for transparency only):",
    ]
    for r in sweep_results:
        marker = "  <- WINNER" if r["scheme"] == winner["scheme"] else ""
        lines.append(f"  {r['scheme']:14s} val={r['val_macro_f1']:.4f}  test={r['test_macro_f1']:.4f}  "
                     f"acc={r['test_accuracy']:.4f}  pos/neu/neg F1={r['test_per_class_f1']}{marker}")
    lines += [
        "",
        f"Winner: {winner['scheme']} (chosen by val)",
        f"  test macro-F1 across seeds {[r['seed'] for r in winner_runs]}: {test_f1s}",
        f"  mean={test_f1_mean}  std={test_f1_std}",
        f"  test accuracy per seed: {test_accs}",
        f"  per-class F1 (selection seed): {winner['test_per_class_f1']}",
        "",
        f"Gate (mean test macro-F1 beats production 0.5816 by > std):",
        f"  margin={gate_margin}  std={test_f1_std}  -> {verdict}",
        "",
        f"Candidate saved to: {summary['candidate_model_dir']} (production v1 untouched).",
    ]
    REPORT_TXT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
