# ADR-041: Evidence Confidence vs Action Confidence

Status: Accepted

## Context
Research-ready evidence is not sufficient for production trading action.

## Decision
Evidence confidence scores input and artifact quality. Action confidence is calculated only for decision-ready evidence with selected TP/SL, resolved dependencies, non-stale/non-quarantined artifacts, and directional requirements satisfied.

## Alternatives Considered
- Always produce action confidence: rejected because research-only artifacts lack production parameters.
- Treat action confidence as action recommendation: rejected because action selection remains blocked.

## Consequences
Synthetic decision-ready fixtures can produce action confidence but still output WAIT with unsupported status.

## Risks
Action confidence may appear before action selection exists; capability reasons make this explicit.

## Validation Strategy
Tests assert current BUMI/DEWA action confidence null and synthetic decision-ready action confidence available while action remains WAIT.
