# sentiment-test-v1 — Official Locked Sentiment Test Set

Status: **official, locked**. Verify integrity before evaluating against this file:

```bash
cd data/evaluation/official/sentiment-test-v1
shasum -a 256 -c SHA256SUMS
```

## Why this exists

The historical `0.5816` macro-F1 benchmark (Fase B) was computed on a 120-row test split that no
longer exists on disk — it was silently overwritten during a later dataset re-export (Fase Q2) and
was never git-tracked. Subsequent experiments (Fase P, R5b) compared candidates against that stale
constant instead of a live, reproducible file, which produced an invalid gate result in R5b (corrected
in commit `6689596`).

An independent audit (`docs/sentiment_evaluation_contract.md`, `reports/evaluation_contract_audit.json`)
found the *next* active test file (`storage/app/sentiment_finetune/test.jsonl`, 148 rows) was itself
`likely_contaminated` — 14 exact overlaps + 13 near-duplicates + 2 label conflicts with train/validation.

This directory is the resolution: a test set built from the **full clean manual-label pool** (1888
labels, only 19 true conflicts excluded — see "Grouping v1 vs v2" below), locked with SHA256 checksums
and committed to git (not gitignored, so it cannot be silently overwritten again).

## How it was built

1. `scripts/build_sentiment_source_inventory.py --require-database` — fresh DB pull, all 1888 manual
   labels with full source/entity/date metadata (confirmed live MySQL connection, not fallback).
2. `scripts/build_sentiment_groups.py` (existing, unmodified) — produced
   `data/evaluation/sentiment_groups_v2.csv`, the corrected grouping.
3. Adapter script (inline, not committed as a reusable tool) remapped v2's column names
   (`classification_instance_group_id`, `true_conflict_status`, `canonical_target_entity`) to the
   column names `scripts/build_official_evaluation_split.py` expects (`group_id`, `conflict_status`,
   `target_entity`), written to `data/evaluation/sentiment_groups_v2_adapted.csv`.
4. `scripts/build_official_evaluation_split.py --groups data/evaluation/sentiment_groups_v2_adapted.csv --seed 42`
   (existing, unmodified) — built 3 candidates; **all 3 passed the quality gate** this time (see
   "Grouping v1 vs v2" for why they failed before). `candidate-a` was selected (script's own
   recommendation logic: gate pass + best representativeness score).
5. Text content joined back from `news_articles` using the exact production input-text formula
   (`ExportSentimentFinetuneDatasetCommand::buildProductionInputText()` — title + summary, 512-char
   truncation), written to `test.jsonl` / `train.jsonl` / `val.jsonl`.

## Grouping v1 vs v2 — why the original 3 candidates failed

`scripts/build_official_evaluation_split.py` originally ran against `sentiment_groups_v1.csv` (its
default `--groups` argument) and **all 3 candidates failed the quality gate**. Investigation found this
was **not** a data contamination problem: `reports/mixed_label_group_root_cause_summary.json` shows
241 of 253 "conflicting" groups in v1 were `same_text_different_entity_valid` — i.e. the v1 grouping
algorithm treated the same article text labeled for *different target stocks* (common for multi-issuer
recommendation articles) as a label conflict, when different entities legitimately having different
sentiment is not a conflict at all. Only 9/253 were genuine same-text-same-entity conflicts. The
corrected `sentiment_groups_v2.csv` (already built by a prior audit, using `classification_instance_group_id`
that accounts for target entity) drops the false-conflict rate from 61% to 1% (19/1888 true conflicts).

## Files

- `test.jsonl` (283 rows) — **locked, never train/tune against this.**
- `train.jsonl` (1348 rows), `val.jsonl` (238 rows) — reusable for future retraining experiments.
- `SHA256SUMS` — checksums for all three files.

## Production baseline on this test set

`indobert_finetuned_v1` (unchanged, same model referenced throughout this project):
**macro-F1 = 0.8096, accuracy = 0.894** — positive F1 0.7209, neutral F1 0.9388, negative F1 0.7692.
Full report: `output/prediction_research/sentiment_official_test_v1_eval_report.json`.

**This number (0.8096) replaces `0.5816` as the reference baseline for all future sentiment
model comparisons.** The old number is not wrong, but it characterized performance on a narrow,
deliberately-hard subset (all ML-vs-rule disagreement cases) — not a representative sample.
