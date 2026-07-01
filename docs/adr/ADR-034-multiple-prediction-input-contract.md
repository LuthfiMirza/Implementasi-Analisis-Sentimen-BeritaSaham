# ADR-034: Multiple Prediction Input Contract

Status: Accepted

## Context
Sprint 7 accepted one prediction snapshot. DEWA can have directional and regime predictions with different semantics, and future engines need a stable multi-signal contract.

## Decision
`trading_decision_v1_1` accepts `predictions[]` as the canonical input and keeps single `prediction` as backward-compatible input. If both are present and inconsistent, the decision normalizes to NO_TRADE. Prediction identity is `variant + semantic_role + generated_at`; duplicate identities are rejected as validation blockers.

## Alternatives Considered
- Merge all prediction objects silently: rejected because duplicates and contradictions must be explicit.
- Treat regime move as directional up: rejected because regime and direction are distinct evidence roles.

## Consequences
Output stores only `prediction_snapshots[]` as canonical evidence. `prediction_snapshot` can remain as a deprecated alias for Sprint 7 consumers.

## Risks
Older callers must migrate to `predictions[]` before the alias is removed.

## Validation Strategy
Tests cover backward compatibility, duplicate identity, conflicting legacy/current inputs, regime-only input, and contradictory directional predictions.
