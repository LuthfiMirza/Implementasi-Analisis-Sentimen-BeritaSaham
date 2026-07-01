# ADR-022: Recovery Timing Contract

Status: Accepted

## Context
Sprint 5 reported high recovery rates but null median recovery days.

## Decision
Recovered episodes must store recoverable timing evidence. Recovery counts only include episodes with first recovery date/day available; medians are computed from recovered samples only.

## Alternatives Considered
- Allow rate without timing: rejected because recovery speed is central to re-entry quality.

## Consequences
Recovery rate and recovery timing are internally consistent.

## Risks
More episodes may become non-recovered if timing cannot be established.

## Validation Strategy
Validator rejects recovery count with null median and tests cover recovered/non-recovered timing nullability.
