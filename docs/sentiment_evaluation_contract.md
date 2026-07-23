# Sentiment Evaluation Contract

## 1. Purpose

Kontrak ini memisahkan development validation, official test candidate, diagnostic sets, dan historical benchmark untuk pipeline sentiment analysis. Task ini tidak menetapkan target performa baru dan tidak menjalankan training.

Status kontrak: **locked** (per 2026-07-22, lihat §12).

Status kandidat official test 148 baris (`storage/app/sentiment_finetune/test.jsonl`): **likely_contaminated, superseded, tidak dipakai lagi**.

Alasan: audit menemukan exact duplicate dan near-duplicate material antara `storage/app/sentiment_finetune/test.jsonl` dan train/validation aktif. Repository juga tidak punya evidence cukup untuk membuktikan test 148 belum pernah dipakai tuning atau pemilihan eksperimen.

**Official test set resmi sekarang: `sentiment-test-v1` di `data/evaluation/official/sentiment-test-v1/` — lihat §12.**

## 2. Label definition

Label valid hanya:

- `positive`
- `neutral`
- `negative`

Definisi bisnis detail label belum ditemukan sebagai aturan formal yang cukup rinci untuk kasus ambigu. Owner attestation masih dibutuhkan untuk guideline final.

## 3. Ground-truth source

Ground truth training/evaluation harus berasal dari `sentiment_manual_labels`, bukan `sentiment_label`, `ml_sentiment_label`, atau `rule_sentiment_label`.

Fakta struktural:

- Export dataset berasal dari `App\Console\Commands\ExportSentimentFinetuneDatasetCommand::handle()` memakai `SentimentManualLabel::with('article')`.
- Field label export diambil dari `$row->label` pada model `App\Models\SentimentManualLabel`.
- Query export juga menyimpan `ml_sentiment_label` dan `rule_sentiment_label` hanya sebagai metadata, bukan target label.
- DB read-only audit `reports/evaluation_manual_label_db_audit.json` menemukan semua 988 unique article ID di split aktif memiliki manual label row.
- `multi_label_articles=0` untuk article ID di split aktif.
- Hanya satu `user_id` ditemukan dalam DB audit untuk split aktif.

Status: **manual-ground-truth structurally verified but provenance unknown**.

Tidak ada evidence repository yang membuktikan label manual independen dari output model/rule. Owner attestation required.

## 4. Dataset inventory

| Set | Size | Purpose | Source | Used for tuning | Representative | Lock status |
| --- | ---: | ------- | ------ | --------------- | -------------- | ----------- |
| Historical 120-row test | 120 | Historical reference only | `output/prediction_research/sentiment_finetune_report.json` | unverified historically | hard-case/disagreement caveat | not locked; checksum missing |
| Active train | 692 | Training | `storage/app/sentiment_finetune/train.jsonl` from `sentiment:export-finetune-dataset` | yes, train | biased/manual-labeled mix; not proven representative | active split file; not immutable |
| Active validation | 148 | Model selection | `storage/app/sentiment_finetune/val.jsonl` | allowed for selection | biased/manual-labeled mix; not proven representative | active split file; not immutable |
| Active test candidate | 148 | Candidate official test | `storage/app/sentiment_finetune/test.jsonl` | unverified; evidence of leakage | not proven representative; `sample_method` null in file | likely_contaminated; official not created |
| R5b hard-case diagnostic | 153 | Diagnostic robustness | `output/prediction_research/sentiment_r5b_locked_tests/legacy_hard_case_test.jsonl` | diagnostic only | no, hard-case | diagnostic, not primary |
| R5b representative diagnostic | 865 | Diagnostic population sample | `output/prediction_research/sentiment_r5b_locked_tests/representative_random_test.jsonl` | diagnostic only | yes by sample method name, but not official | diagnostic, not primary |

## 5. Train set

- Path: `storage/app/sentiment_finetune/train.jsonl`.
- Size: 692.
- Label distribution: positive 215, neutral 403, negative 74.
- SHA256: `bbf9e1cdc410f5ff1bda3be74278d3f7c8dddf1508ed8a430ba4443e927ff890`.
- Duplicate article IDs: 0.
- Duplicate normalized input text: 9.
- Usage: training only.

## 6. Validation set

- Path: `storage/app/sentiment_finetune/val.jsonl`.
- Size: 148.
- Label distribution: positive 46, neutral 86, negative 16.
- SHA256: `6e32ab4d19648b9a0db1f1c1a2e39d7f3d7272c6242784fb53b286c73b88ccc7`.
- Duplicate article IDs: 0.
- Duplicate normalized input text: 1.
- Allowed usage: model selection, hyperparameter selection, input format selection, early stopping, threshold selection.

## 7. Official test candidate

- Path: `storage/app/sentiment_finetune/test.jsonl`.
- Size: 148.
- Label distribution: positive 46, neutral 87, negative 15.
- SHA256 of source file: `6b5a7863dfdb58c4a307983a4b9b998e89de230eb16cd07a730d721b0492c5a5`.
- Candidate manifest: `data/evaluation/candidate_test_manifest.csv`.
- Candidate manifest SHA256: `8bf1b53bd17d211c330aa404db1a5fe76897000e004d8fc6067996a1faf8a187`.
- Official manifest: not created.
- Status: **likely_contaminated**.

Evidence against official lock:

- `reports/evaluation_overlap.csv` contains 14 material exact normalized title/text overlaps between active test and active train/validation.
- `reports/evaluation_near_duplicates.csv` contains 13 material near-duplicates between active test and active train/validation at threshold `0.92`.
- `reports/evaluation_label_conflicts.csv` contains 2 identical-text label conflicts between active train and active test.
- Repository lacks evidence that this test was never used for tuning, checkpoint selection, preprocessing changes, guideline changes, or repeated experiment selection.

## 8. Hard-case diagnostic set

- Path: `output/prediction_research/sentiment_r5b_locked_tests/legacy_hard_case_test.jsonl`.
- Size: 153.
- Label distribution: positive 47, neutral 88, negative 18.
- SHA256: `538db53806305de07b315c12bf878caf34b80c2a525a65fc670d611f8dd3b60c`.
- Role: diagnostic robustness/error analysis, not primary performance claim.

## 9. Historical benchmark

- Evidence path: `output/prediction_research/sentiment_finetune_report.json`.
- Size: 120 test rows.
- Macro-F1: `0.5816`.
- Role: historical reference only.
- Not official final benchmark for current project per owner decision.
- Missing: original test file path, checksum, experiment date, commit, exact command.

## 10. Primary metric

`macro-F1 = rata-rata F1 positive, neutral, dan negative tanpa pembobotan berdasarkan jumlah kelas.`

Primary metric: `macro_f1`.

## 11. Secondary metrics

Wajib dilaporkan bersama primary metric:

- accuracy;
- weighted-F1;
- precision per class;
- recall per class;
- F1 per class;
- support per class;
- confusion matrix.

## 12. Model-selection rules

- Model selection hanya boleh menggunakan validation set.
- Hyperparameter selection hanya boleh menggunakan validation set.
- Input format selection hanya boleh menggunakan train/validation.
- Early stopping hanya boleh memakai validation set.
- Threshold selection hanya boleh memakai validation set.
- Official test tidak boleh dipakai untuk memilih model, checkpoint, preprocessing, label guideline, threshold, atau eksperimen.

## 13. Test-access rules

- Official test hanya dipakai setelah kandidat final dipilih.
- Official test dipakai untuk laporan hasil utama.
- Jika official test dipakai untuk dasar perubahan berikutnya, wajib buat versi eksperimen/test-set baru.
- Diagnostic set boleh dipakai berulang untuk error categorization, tetapi tidak boleh jadi angka utama.

## 14. Leakage rules

Test set tidak boleh overlap dengan train/validation pada:

- article ID;
- exact normalized title;
- exact normalized input text;
- exact URL bila tersedia;
- near-duplicate title/content di atas threshold kontrak;
- event yang sama bila dapat dideteksi;
- label conflict pada teks identik.

Near-duplicate threshold audit saat ini: `0.92`, configurable melalui `scripts/audit_evaluation_contract.py --near-threshold`.

## 15. Duplicate policy

- Duplicate article ID harus 0 di setiap split.
- Exact duplicate text lintas train/validation/test harus dianggap material leakage.
- Exact duplicate text dengan label berbeda harus dianggap label conflict.
- Near-duplicate lintas split harus direview manual sebelum official lock.
- Jika duplicate material tidak bisa dibersihkan tanpa mengubah test lama, status official candidate tetap tidak boleh `verified_clean`.

## 16. Checksum policy

- Official manifest harus immutable dan punya SHA256.
- Verification script wajib gagal non-zero jika checksum, row count, article ID uniqueness, label set, atau distribution berubah.
- Karena active test 148 berstatus `likely_contaminated`, hanya candidate checksum dibuat: `data/evaluation/candidate_test_manifest.sha256`.
- Official checksum tidak dibuat.

## 17. Artifact-version policy

- `storage/app/sentiment_model/indobert_finetuned_v1` tidak boleh ditimpa.
- Kandidat model berikutnya harus disimpan ke directory baru.
- Artifact promotion hanya boleh setelah evaluation contract official disahkan owner.
- Setiap artifact baru wajib mencatat model dir, base checkpoint, tokenizer, label mapping, metrics, split checksums, commit, command, dan timestamp.

## 18. Database read-only policy

- Database diperlakukan read-only untuk evaluation contract.
- Tidak boleh migration, backfill, update label, atau update `news_articles` pada task kontrak.
- Script verifier `scripts/verify_evaluation_contract.py` tidak memerlukan DB access.
- DB hanya boleh dibaca untuk audit provenance/manifest metadata.

## 19. Reproducibility requirements

Setiap evaluasi official berikutnya wajib menyimpan:

- git commit;
- timestamp;
- exact command;
- model artifact path;
- model config hash;
- tokenizer hash atau directory hash;
- train/validation/test manifest checksum;
- package versions;
- metric lengkap;
- confusion matrix;
- row-level prediction export jika disetujui owner.

## 20. Conditions requiring a new test-set version

Buat versi test baru jika:

- official test pernah dipakai untuk tuning;
- duplicate/leakage material ditemukan;
- label guideline berubah;
- preprocessing/input text berubah secara material;
- target populasi berubah;
- artikel ambiguous/noisy dikeluarkan;
- manual labels direvisi;
- artifact/model family berubah dan evaluasi sebelumnya sudah dipakai untuk keputusan iterasi.

## 21. Unresolved owner decisions

- Apakah active 148 test tetap mau dipakai meskipun audit menemukan leakage material?
- Apakah perlu membentuk official test baru yang group-aware dan deduplicated?
- Apakah label conflicts pada exact duplicate text harus direview manusia sebelum split baru?
- Apakah `sample_method=null` pada active split boleh diterima sebagai official provenance metadata?
- Format versioning manifest official yang diinginkan apa?

## Appendix: Owner Decisions Applied

- Test 148 ditolak sebagai official dan tetap menjadi contaminated diagnostic set.
- R5b 153 menjadi hard-case diagnostic set.
- Test 120 menjadi historical benchmark.
- Official test versioning memakai `sentiment-test-v1`, `sentiment-test-v2`, dan seterusnya; locked version tidak boleh ditimpa.
- Group-aware split policy: group duplicate/near-duplicate/event high-confidence tidak boleh melintasi split.
- Same-event grouping policy: High-confidence event groups menjadi hard grouping constraint. Medium-confidence event groups hanya warning/report dan bukan hard constraint. Low-confidence tidak memengaruhi split.
- Label conflict policy: unresolved conflict group dikeluarkan dari official test sampai owner review.
- Official test access policy: baca official test butuh `--allow-official-test`, checksum valid, status final candidate, commit dan artifact checksum tercatat, serta access log.
- Production artifact protection: `storage/app/sentiment_model/indobert_finetuned_v1` tidak boleh ditimpa.

## Commands

```bash
python3 scripts/build_sentiment_source_inventory.py
```

```bash
python3 scripts/build_sentiment_groups.py
```

```bash
python3 scripts/build_official_evaluation_split.py --seed 42
```

```bash
python3 scripts/verify_evaluation_contract.py --candidate candidate-a
```

Official version command, only after `sentiment-test-v1` exists and owner authorizes official access:

```bash
python3 scripts/verify_evaluation_contract.py --version sentiment-test-v1 --allow-official-test
```

## Grouping V2 Update

- Previous Candidate A/B/C (built against `sentiment_groups_v1.csv`, all `quality_gate_pass=false`)
  superseded and must not be used.
- Test 148 (`storage/app/sentiment_finetune/test.jsonl`) remains contaminated diagnostic — do not
  evaluate against it for any official claim.
- Grouping v2 uses database source, target-entity-aware conflict detection, and excludes empty/missing
  values from duplicate evidence.

## 12. Resolution — `sentiment-test-v1` official test LOCKED (2026-07-22)

**Status: locked.** Root cause of the v1 candidate gate failures: `reports/mixed_label_group_root_cause_summary.json`
shows 241/253 "conflicts" in v1 grouping were `same_text_different_entity_valid` (multi-issuer
recommendation articles legitimately labeled differently per target stock, not true conflicts). Only
9/253 were genuine conflicts. Re-running `scripts/build_official_evaluation_split.py` against the
corrected `sentiment_groups_v2.csv` (column-adapted to the schema the script expects) produced **3/3
candidates passing the quality gate** (`exact_leakage_count=0`, `group_crossing_count=0`,
`unresolved_conflict_count=0`, `min_class_support>=5`, `previous_test_exposure_count=0`).

`candidate-a` selected (script's own recommendation logic). Locked at
`data/evaluation/official/sentiment-test-v1/` (`test.jsonl` 283 rows, `train.jsonl` 1348 rows,
`val.jsonl` 238 rows, `SHA256SUMS`), committed to git (not gitignored). Full rationale and build steps:
`data/evaluation/official/sentiment-test-v1/README.md`.

**Production `indobert_finetuned_v1` evaluated on `sentiment-test-v1`: macro-F1 = 0.8096, accuracy =
0.894** (positive F1 0.7209, neutral F1 0.9388, negative F1 0.7692). Full report:
`output/prediction_research/sentiment_official_test_v1_eval_report.json`.

**This replaces `0.5816` as the reference baseline for all future sentiment model comparisons.** The
old number was measured on a narrow, deliberately-hard subset (all ML-vs-rule disagreement cases,
n=120) — not wrong, but not representative. `sentiment-test-v1` is drawn from the full clean label
pool and is the number to beat going forward.

## 13. Ground-truth attestation (owner-confirmed, formalizing §3's "provenance unknown" finding)

Per §3, structural evidence alone could not prove label independence from ML/rule output without
owner confirmation. **The project owner (Luthfi) confirmed directly, in conversation, on 2026-07-22:**
manual labels are entered independently by reading the article and choosing a label; the ML and
rule-based scores shown in the labeling UI (`SentimentValidationController`, both the disagreement
mode and the `/sentiment-validation/representative` mode) are sampling hints only, not followed as
the answer — this matches the UI's own on-screen copy ("Skor ML/rule hanya petunjuk sampling, bukan
jawaban"). All 1888 manual labels currently in `sentiment_manual_labels` were entered by a single
`user_id` — there is no second annotator, so inter-annotator agreement cannot be computed from
existing data. This remains a genuine limitation worth disclosing in the thesis (see
`reports/ground_truth_validation.json` for the original audit finding), not one this attestation
resolves — it only confirms the *existing* labels are independent human judgments, not that they are
free of individual annotator bias or error.
- `sentiment-test-v1` was not created.
