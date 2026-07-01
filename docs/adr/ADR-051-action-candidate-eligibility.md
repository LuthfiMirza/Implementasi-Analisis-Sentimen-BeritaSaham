# ADR-051: Action Candidate Eligibility

Status: Accepted

## Context
A long-entry candidate requires directional and decision-grade artifact prerequisites without using probability thresholds.

## Decision
Candidate eligibility is evaluated through deterministic gates: directional-up prediction, no conflict, freshness, decision-ready evidence, decision-usable TP/SL, selected TP/SL, dependency, stale, quarantine, and capability.

## Alternatives
- Use evidence confidence score threshold: rejected because confidence is not action selection.
- Let regime_move imply long entry: rejected because regime is not direction.

## Consequences
Current BUMI/DEWA remain observation-only or blocked. Synthetic decision-ready directional-up evidence may produce candidate-ready.

## Risks
Gate logic is conservative until final promotion exists.

## Validation Strategy
Unit tests cover regime-only, directional-down, research-only, stale, dependency, and synthetic candidate-ready cases.
