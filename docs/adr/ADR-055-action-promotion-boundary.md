# ADR-055: Action Promotion Boundary

Status: Accepted

## Context
A selected candidate must not become BUY/SELL/HOLD until explicit promotion policy and execution readiness exist.

## Decision
Introduce ActionPromotionService. Promotion remains not promoted or eligible-but-disabled in Sprint 10.1. Promoted and executable actions remain null.

## Alternatives
- Promote candidate-ready to BUY: rejected due to blocked risk/plan/sizing/execution.
- Reuse candidate as promoted action: rejected because candidate is non-executable.

## Consequences
Final action remains defensive WAIT/NO_TRADE.

## Risks
Consumers may expect BUY from selected candidates; schema explicitly separates candidate, selected candidate, promoted action, executable action, and safety action.

## Validation Strategy
Promotion tests reject promoted BUY and executable payloads.
