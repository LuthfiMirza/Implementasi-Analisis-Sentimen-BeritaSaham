# ADR-031: Decision Safety Downgrade

Status: Accepted

## Context
Current BUMI and DEWA registry state has research-usable artifacts but no decision-usable TP/SL/re-entry artifacts.

## Decision
The decision service downgrades to WAIT when valid prediction and research evidence exist but decision-grade parameters are unavailable. It downgrades to NO_TRADE when input, prediction, registry availability, integrity, or minimum evidence is invalid.

## Alternatives Considered
- Use research-only best candidates as fallback: rejected because no-fallback policy is required.
- Return exceptions for missing artifacts: rejected because business unavailability must normalize into decision output.

## Consequences
Safety blockers are explicit and deterministic.

## Risks
WAIT can be overused until decision-grade artifacts exist.

## Validation Strategy
Tests cover missing prediction, stale prediction, research-only evidence, decision-ready synthetic evidence, and current BUMI/DEWA state.

## Sprint 7.1 Update
Safe downgrade is reserved for research evidence without decision-grade parameters. Decision-ready evidence blocked only by missing action capability uses `unsupported` action status.
