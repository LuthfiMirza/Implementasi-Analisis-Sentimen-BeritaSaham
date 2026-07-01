# ADR-035: Decision Scope and Open Trade Semantics

Status: Accepted

## Context
The decision service may receive open-trade state before position-management actions are implemented.

## Decision
Add explicit `decision_scope`, `position_context`, and `position_management_status`. Valid open trades switch scope to `position_management` and add a blocker because position management is not implemented. Sprint 7.1 still never emits HOLD, SELL, CUT_LOSS, or BUY_BACK.

## Alternatives Considered
- Implicit HOLD for valid open trades: rejected because HOLD has production semantics not defined in Sprint 7.1.
- Ignore open_trade input: rejected because callers need explicit unsupported status.

## Consequences
Open trades are safely represented without performing PnL, risk, or trade-plan calculations.

## Risks
Position-management consumers remain blocked until a dedicated sprint.

## Validation Strategy
Tests cover no trade, valid open trade, ticker mismatch, invalid entry price, closed status, and no implicit HOLD.
