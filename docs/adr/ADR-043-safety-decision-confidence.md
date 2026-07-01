# ADR-043: Safety Decision Confidence

Status: Accepted

## Context
WAIT/NO_TRADE are the only supported actions, but evidence confidence does not explain confidence in safety outcomes.

## Decision
Add safety-decision confidence for supported safety actions. It uses blocker completeness, registry integrity, decision parameter unavailability, and capability limitations. It does not measure profit probability or market risk.

## Alternatives Considered
- Use evidence confidence directly: rejected because safety support is a different scope.

## Consequences
BUMI/DEWA can expose confidence that WAIT is supported by blockers while trade-action confidence remains unavailable.

## Validation Strategy
Tests cover WAIT/NO_TRADE safety confidence and interpretations.
