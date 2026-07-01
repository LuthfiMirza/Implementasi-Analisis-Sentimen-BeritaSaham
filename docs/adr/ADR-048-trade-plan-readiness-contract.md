# ADR-048: Trade Plan Readiness Contract

Status: Accepted

## Context
A trade plan can become executable. Sprint 9 must define readiness without producing production entry, TP, SL, holding, or re-entry instructions.

## Decision
Trade Plan output is structured but unavailable unless action candidate, decision risk, selected entry/TP/SL, supported action capability, and valid decision-usable sources exist. Research-only parameters are not promoted into plan fields.

## Alternatives
- Build a research-only trade plan: rejected because it resembles an executable recommendation.
- Keep `trade_plan` null: rejected because downstream services need blocker semantics.

## Consequences
Current BUMI/DEWA return `trading_trade_plan_v1` with unavailable sections and null numeric fields.

## Risks
Downstream UI must render unavailable sections carefully and not imply hidden plan values.

## Validation Strategy
Unit tests verify unavailable sections, null fields, no HOLD for open trades, and no research candidate promotion.
