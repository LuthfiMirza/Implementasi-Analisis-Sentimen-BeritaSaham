# ADR-045: Reason Prioritization and Aggregation

Status: Accepted

## Context
Sprint 8 produced 24-27 complete reasons, but primary reasons needed clearer prioritization.

## Decision
Keep canonical all reasons, then derive primary, supporting, and diagnostic groups. Dominant blocker follows configured priority. Duplicate reason sources are aggregated where possible.

## Alternatives Considered
- Drop diagnostic reasons: rejected because auditability needs all reasons.

## Consequences
Primary reasons remain short while all reasons are preserved.

## Validation Strategy
Tests cover primary limits, supportive counts, dominant blocker priority, and compatibility derivation.
