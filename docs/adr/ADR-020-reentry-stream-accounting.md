# ADR-020: Re-entry Stream Accounting

Status: Accepted

## Context
Sprint 5 summaries left source episodes unaccounted and compared stream subsets with total source counts.

## Decision
Re-entry artifacts must reconcile every source episode into stop, TP, timeout, exclusion, or unclassified buckets. Stream-specific rates use stream denominators only.

## Alternatives Considered
- Keep global denominators: rejected because stream rates become misleading.

## Consequences
Artifacts can be validated for accounting completeness before registry import.

## Risks
Unclassified episodes may reveal simulator limitations requiring follow-up.

## Validation Strategy
Validators reject unreconciled artifacts and tests cover source/exclusion/unclassified accounting.

## Sprint 5.2 Update
Stream accounting now requires reason-level unclassified reconciliation and top-level counts must reconcile exactly to source episode count before registry import.
