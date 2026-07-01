# ADR-064: Trade Plan Materialization and Risk Consistency

Status: Accepted

## Context
Trade plan must not recalculate risk geometry independently from Action Risk.

## Decision
Canonical geometry source is `risk.action_specific_risk.metrics`. Materialization copies and validates risk metrics against selected parameters and entry reference.

## Alternatives
- Recalculate geometry in TradePlanService: rejected to avoid divergent calculations.
- Use research-only parameters: rejected by no-fallback policy.

## Consequences
Risk geometry mismatch blocks materialization.

## Validation Strategy
Tests cover mismatch, parameter-ready, materialized, and deterministic TP/SL references.
