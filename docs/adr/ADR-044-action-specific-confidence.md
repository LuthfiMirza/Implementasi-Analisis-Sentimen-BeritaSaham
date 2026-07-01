# ADR-044: Action-Specific Confidence

Status: Accepted

## Context
Future BUY/SELL/HOLD confidence must be tied to a concrete action candidate.

## Decision
Trade-action confidence requires action, candidate version, action-specific evidence, eligibility gates, source artifacts, and score interpretation. Sprint 8.1 returns action null, score null, and unavailable status.

## Alternatives Considered
- Populate trade-action score from evidence score: rejected as misleading.

## Consequences
Synthetic decision-ready evidence no longer creates trade-action confidence without action candidate.

## Validation Strategy
Tests assert synthetic decision-ready output has unavailable trade-action confidence.
