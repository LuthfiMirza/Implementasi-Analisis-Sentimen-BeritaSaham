# ADR-038: Confidence Semantics

Status: Accepted

## Context
Prediction probability is model output, not decision confidence. Sprint 8 needs confidence without enabling BUY/SELL.

## Decision
Separate prediction probability, evidence confidence, and action confidence. Evidence confidence may exist for research-only evidence; action confidence is null unless decision-grade evidence and selected parameters are available.

## Alternatives Considered
- Use prediction probability as confidence: rejected because it ignores artifact readiness and calibration.
- Hide confidence until BUY is possible: rejected because research evidence quality is useful for audit.

## Consequences
BUMI/DEWA can show research-only evidence confidence while action confidence remains unavailable.

## Risks
Consumers may confuse evidence confidence with action confidence; schema labels and reasons mitigate this.

## Validation Strategy
Tests verify probability magnitude does not raise confidence and action confidence is null for research-only artifacts.
