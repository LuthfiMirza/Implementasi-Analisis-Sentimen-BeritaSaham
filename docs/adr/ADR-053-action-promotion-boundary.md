# ADR-053: Action Promotion Boundary

Status: Accepted

## Context
Candidate-ready is not enough to expose BUY/SELL/HOLD. A separate promotion stage is required.

## Decision
Sprint 10 adds `action_promotion` with status `not_implemented`, final action null, and reason `ACTION_PROMOTION_NOT_IMPLEMENTED`.

## Alternatives
- Promote eligible candidate directly: rejected because final promotion policy is blocked.
- Hide promotion status: rejected because downstream consumers need explicit blocker semantics.

## Consequences
Synthetic candidate-ready remains final WAIT with unsupported status.

## Risks
More verbose output, mitigated by structured reasons and reason summary.

## Validation Strategy
Tests verify candidate-ready is not promoted and final action remains WAIT/NO_TRADE.
