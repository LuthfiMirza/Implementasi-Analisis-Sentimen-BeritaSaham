# Sentiment Grouping V2 Report

## 1. Mengapa previous candidates ditolak

- Candidate A/B/C ditolak owner: exact leakage tidak nol, negative support hanya 3, neutral sekitar 97%, dan artifact fallback tidak layak.

## 2. Dampak artifact fallback

- Fallback artifact sebelumnya tidak memuat source/entity/date penuh dan menyebabkan grouping salah besar.
- Previous candidates hanya memakai sebagian records karena v1 false/mixed grouping mengecualikan banyak data.

## 3. Database completeness

- DB status: ok (mysql).
- Manual labels valid: 1888.
- Empty title: 0; empty summary: 0; empty snippet: 12; empty full text: 1786; empty URL: 0.
- Field completeness: `reports/database_source_field_completeness.json`.

## 4. Empty-value grouping audit

- Empty/unusable URL keys rejected: 0.
- Empty/unusable text keys rejected: 0.
- Empty/missing/placeholder/hash-empty values are not grouping evidence.

## 5. Unit klasifikasi berbasis target entity

- Unit klasifikasi: `article context + canonical_target_entity`.
- Same article/text across different entities is not true conflict by itself.

## 6. Article-content groups

- Article-content groups: 1849.
- Duplicate article groups: 35.
- Singleton article groups: 1814.

## 7. Classification-instance groups

- Classification-instance groups: 1849.
- Splitter berikutnya must constrain both article-content group and classification-instance group.

## 8. Root cause 253 mixed-label groups

- Previous mixed groups: 253.
- Cross-entity valid differences: 241.
- True conflicts: 9.
- Transitive overmerge: 3.
- False grouping: 0.

## 9. Near-duplicate v2

- Pair count: 44.
- Score buckets: `{">0.95": 44}`.
- Hard threshold remains 0.92; threshold-review CSV created.

## 10. Exact leakage root cause

- Previous leakage root cause: stale/inconsistent v1 grouping versus verifier fingerprint checks.
- Fix: v2 manifest separates article-content and classification-instance groups and maps exact text hash consistently.

## 11. Population accounting

- Source total: 1888.
- Eligible: 1869.
- True conflict records: 19.
- Missing text: 0.
- Invalid: 0.
- Accounted total: 1888.
- Unaccounted: 0.

## 12. Grouping v2 statistics

- Largest group: 4.
- Checksum: `5964fa3191fbe4afce43e5e3d470cfcaab77c935980ab38906be0365d65c775b`.

## 13. Quality gate results

- database_source_read: PASS
- database_read_only: PASS (read-only)
- source_rows_accounted: PASS
- empty_values_not_grouping_evidence: PASS
- target_entity_used_in_conflict_detection: PASS
- exact_leakage_root_cause_done: PASS
- near_duplicate_audit_runs: PASS
- true_conflicts_separated: PASS
- group_ids_deterministic: PASS
- database_write_none: PASS
- group_manifest_checksum_valid: PASS
- no_stale_artifact_unmarked: PASS

## 14. Apakah candidate regeneration aman

- Candidate regeneration allowed: yes.
- Official lock still forbidden in this task.

## 15. Data tambahan yang dibutuhkan

- Human review for true conflict groups before final split lock.
- Optional full-text availability improvement is not required because title+summary exists.

## 16. Known limitations

- Near-duplicate v2 uses deterministic fingerprint/title/entity blocking; semantic event grouping remains conservative.
- Historical 120 membership remains unknown at row level.

## 17. Next safe task

`Regenerate candidate official test splits from sentiment_groups_v2, without locking an official version.`
