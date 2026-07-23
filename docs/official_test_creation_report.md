# Official Test Creation Report

## 1. Executive summary

- Official `sentiment-test-v1` was not created.
- Status: `owner_selection_required`.
- Reason: all three candidates failed hard quality gate due exact leakage count and limited fallback inventory metadata while DB was unavailable.

## 2. Source population

- Total articles: 1856
- Total manual labels: 1856
- Valid manual labels: 1856
- Invalid labels: 0
- Inventory CSV: `data/evaluation/source_population_v1.csv`.

## 3. Ground-truth status

- Status: `manual_ground_truth_structurally_verified_provenance_unknown`.
- Labels come structurally from manual-label artifacts; DB was unavailable during this run, so full provenance still requires owner attestation.

## 4. Text normalization

- Module: `scripts/lib/sentiment_text_normalization.py`.
- Preserves negation and financial numbers; strips URL tracking params.

## 5. Duplicate grouping

- Total groups: 502
- Singleton groups: 52
- Duplicate groups: 450
- Largest group size: 10
- Mixed-label groups: 253

## 6. Near-duplicate grouping

- Threshold: 0.92
- Near pair count: 3284
- False-positive risk: medium; artifact fallback lacks titles/sources for full DB rows

## 7. Event grouping

- High-confidence event candidates are duplicate/near-duplicate-derived hard constraints.
- Medium/low event candidates are report-only; none created as hard split decisions here.

## 8. Conflict exclusions

- Conflict queue: `reports/official_test_label_review_queue.csv`.
- All conflict groups are excluded from candidate test selection.

## 9. Sample method

- Counts: `{"hard_case": 991, "population_random": 865}`
- Limitation: source population is hard-case heavy and artifact fallback maps unknown cautiously.

## 10. Historical exposure

- Counts: `{"active_test_148": 124, "multiple_previous_test_sets": 24, "no_known_test_exposure": 1579, "r5b_153": 129}`
- Candidate selection prioritized `no_known_test_exposure`.

## 11. Candidate generation

- Script: `scripts/build_official_evaluation_split.py --seed 42`.
- Candidate A: around 15% target.
- Candidate B: around 250 rows.
- Candidate C: around 325 rows.

## 12. Candidate comparison

- candidate-a: test=278, train=380, validation=67, gate=False, exact_leakage=1, score=0.3, labels=positive:5 neutral:270 negative:3.
- candidate-b: test=251, train=403, validation=71, gate=False, exact_leakage=1, score=0.3, labels=positive:6 neutral:242 negative:3.
- candidate-c: test=328, train=337, validation=60, gate=False, exact_leakage=1, score=0.3, labels=positive:7 neutral:318 negative:3.

## 13. Candidate recommendation

- Recommended candidate for owner review: `candidate-a`.
- Owner decision required: true.
- Recommendation reason: best overall score among failed candidates, but hard gates still fail, so no lock.

## 14. Official version status

- `data/evaluation/sentiment-test-v1/` was not created.
- No official checksum was created.

## 15. Final split statistics

- See `reports/official_test_candidate_comparison.csv` and each candidate `split_contract.json`.

## 16. Leakage verification

- Candidate split contracts record exact leakage, near leakage, group crossing, unresolved conflict count.

## 17. Reproducibility

- Seed: 42.
- Same-seed reproducibility covered by Python unittest.

## 18. Checksums

- Candidate directories include `CHECKSUMS.sha256`.
- Group manifest checksum: `data/evaluation/sentiment_groups_v1.sha256`.

## 19. Automated tests

- `python3 -m unittest tests/Python/test_sentiment_evaluation_contract.py`: OK, 34 tests.
- `php artisan test tests/Unit/EvaluationContractVerifierTest.php`: retained.

## 20. Known limitations

- DB unavailable during source inventory generation; script fell back to existing artifacts.
- Source, target entity, URL, and publication date are missing in fallback inventory.
- Official v1 cannot be locked from this run without owner review / DB availability.

## 21. Owner decisions remaining

- Re-run source inventory when MySQL is available, or approve fallback limitations.
- Decide whether to review conflict groups and rebuild groups.
- Decide candidate selection or request candidate regeneration after full DB metadata.

## 22. Next safe task

`Rebuild dan reproduksi baseline IndoBERT pada train/validation baru tanpa membuka official test.` must wait until official test is locked.
