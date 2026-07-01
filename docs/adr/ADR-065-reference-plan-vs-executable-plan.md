# ADR-065: Reference Plan vs Executable Plan

Status: Accepted

## Context
A materialized reference plan still lacks order semantics, position size, execution constraints, and promotion approval.

## Decision
Reference plan may be `materialized`, while execution readiness is at most `reference_ready`; executable status remains false.

## Alternatives
- Treat materialized as executable: rejected because position sizing and execution are blocked.
- Hide materialized plan from output: rejected because it is useful contract evidence.

## Consequences
Selection and promotion stay blocked even when reference plan is materialized.

## Validation Strategy
Tests verify selected candidate null, promoted action null, executable action null, and final WAIT.
