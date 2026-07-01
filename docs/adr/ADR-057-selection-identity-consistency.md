# ADR-057: Selection Identity Consistency

Status: Accepted

## Context
Selection must ensure confidence, risk, and trade plan refer to the same candidate.

## Decision
Selection gates validate candidate ID and intent consistency across trade-action confidence, decision risk, and trade plan. Mismatches block selection.

## Alternatives
- Trust downstream objects without identity checks: rejected for auditability.
- Match only intent: rejected because multiple candidates may share intent.

## Consequences
Synthetic contract-ready fixtures can prove matching contracts while capability remains disabled.

## Risks
Early contracts may be rejected until identity fields are complete.

## Validation Strategy
Unit tests cover confidence/risk/plan identity mismatch and selected candidate nullability.
