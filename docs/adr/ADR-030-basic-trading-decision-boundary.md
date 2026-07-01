# ADR-030: Basic Trading Decision Boundary

Status: Accepted

## Context
Research artifacts are now registry-indexed, but no production decision boundary exists. Current TP, SL, and re-entry artifacts are research-only and selected parameters are null.

## Decision
Create an in-memory `TradingDecisionService` that accepts a normalized prediction snapshot and registry evidence, then returns a schema-versioned `trading_decision_v1` result. Sprint 7 supports only WAIT and NO_TRADE and does not produce trade plans, risk, confidence, or persistence.

## Alternatives Considered
- Integrate directly into prediction controllers: rejected because the service contract must stabilize first.
- Emit BUY/SELL from prediction probability: rejected because artifact evidence is not decision-grade.

## Consequences
Consumers can test the decision boundary safely without production trading actions.

## Risks
Users may mistake WAIT for a trade recommendation; reason codes and quality status make safe downgrade explicit.

## Validation Strategy
Unit and integration tests assert no aggressive actions, null confidence/risk/trade_plan, deterministic output, and registry-backed evidence.

## Sprint 7.1 Update
The decision schema evolves to `trading_decision_v1_1` with canonical `prediction_snapshots`, scope fields, readiness fields, gate consistency, and deterministic fingerprint. Supported actions remain WAIT and NO_TRADE.

## Sprint 8 Update
Decision schema evolves to `trading_decision_v1_2`. Confidence and reason engines enrich the output but supported actions remain WAIT and NO_TRADE.
