# ADR-042: Confidence Scope Model

Status: Accepted

## Context
Sprint 8 action confidence could be read as copied evidence confidence.

## Decision
Split confidence into evidence, safety-decision, and trade-action scopes. Evidence confidence scores evidence quality; safety-decision confidence supports WAIT/NO_TRADE; trade-action confidence requires an action identity and remains unavailable without an action candidate.

## Alternatives Considered
- Keep scalar action confidence: rejected because it lacks action identity.
- Remove confidence entirely: rejected because evidence quality remains useful.

## Consequences
Decision schema moves to `trading_decision_v1_3`; confidence schema moves to `trading_confidence_v1_1`.

## Risks
Consumers must migrate from `action_confidence` to scoped confidence fields.

## Validation Strategy
Tests assert evidence confidence is not copied to trade-action confidence and action identity is required.
