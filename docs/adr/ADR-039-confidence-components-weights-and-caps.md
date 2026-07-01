# ADR-039: Confidence Components, Weights, and Caps

Status: Accepted

## Context
Confidence must be deterministic and explainable.

## Decision
Use configured weighted components, penalties, and caps. Components cover prediction availability/freshness/semantics/consistency, research coverage, artifact integrity/freshness/quality, decision parameter readiness, and implementation capability.

## Alternatives Considered
- Hardcode scores in service: rejected because weights must be auditable and testable.
- Use trading thresholds: rejected because Sprint 8 does not select aggressive actions.

## Consequences
Changing the weight profile changes decision fingerprint.

## Risks
Weights can be misconfigured; config validation tests cover this.

## Validation Strategy
Tests cover weights, thresholds, caps, penalties, invalid config, and deterministic results.
