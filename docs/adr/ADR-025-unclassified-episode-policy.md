# ADR-025: Unclassified Episode Policy

Status: Accepted

## Context
Sprint 5 prototype left a gap between source episode count and classified stop/TP/timeout counts. Without reason-level accounting, unclassified episodes can mask simulator coverage gaps, unsupported families, or missing execution results.

## Decision
Every unclassified episode must have exactly one reason in `unclassified_reasons`: `outside_outer_validation`, `no_valid_nested_pair`, `unsupported_candidate_family`, `missing_execution_result`, `insufficient_stream_sample`, or `other`. The sum of reason counts must equal `unclassified_count`, and total episode accounting must reconcile to `source_episode_count`.

Artifacts expose `maximum_unclassified_rate`. If the unclassified rate exceeds the configured maximum, a quality warning is mandatory and overall re-entry research usability is disabled when policy requires it. Episodes must not be moved to exclusions merely to improve the unclassified rate.

## Alternatives Considered
- Treat unclassified as excluded: rejected because exclusions and unclassified states have different meanings.
- Allow unmatched unclassified counts: rejected because registry validation needs a closed accounting contract.

## Consequences
High unclassified rates remain visible as research limitations. Registry ingestion can reject artifacts with incomplete accounting.

## Validation Strategy
Validator checks reason reconciliation and accounting totals. Regression tests cover reason mismatch, unclassified-rate warnings, and usability downgrade.
