# ADR-090: Position Management Risk Boundary

Date: 2026-07-02
Status: Accepted

## Context

Sprint 18 adds management-specific risk and review planning for reference-only management candidates. Position state remains the canonical source for PnL, holding duration, and stop/target condition facts.

## Decision

Management risk copies and validates canonical position-state metrics, then computes only reference-only derived metrics such as stop breach depth and target exceedance. Management review plans summarize evidence and missing capabilities but never create action plans, quantities, stop updates, target updates, or executable instructions.

## Consequences

Management risk and review plans do not select, approve, promote, or execute management actions. Stop breach does not become CUT_LOSS, target reach does not become SELL, and normal monitoring does not become HOLD.
