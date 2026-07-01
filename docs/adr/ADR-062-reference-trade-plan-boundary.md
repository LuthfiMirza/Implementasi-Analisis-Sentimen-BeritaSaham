# ADR-062: Reference Trade Plan Boundary

Status: Accepted

## Context
Action risk can provide gross geometry, but executable trade plans require execution, sizing, and promotion capabilities that remain blocked.

## Decision
Introduce a reference trade plan boundary. Reference plans are candidate-specific, provenance-backed, non-executable, and never imply orders or recommendations.

## Alternatives
- Emit executable plan fields immediately: rejected because execution and sizing are blocked.
- Keep trade plan null: rejected because downstream contracts need explicit readiness.

## Consequences
Trade plan schema evolves to `trading_trade_plan_v1_1` with embedded `trading_reference_trade_plan_v1`.

## Risks
Reference prices may be misread as order prices; output includes `executable=false` and execution readiness not implemented.

## Validation Strategy
Tests reject order payloads, position size, promoted actions, and executable readiness.
