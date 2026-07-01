# ADR-007: Chronological Trade Path Simulation

Status: Accepted

## Context
Aggregated MFE/MAE cannot determine whether TP or SL was touched first. Daily OHLCV also cannot determine intraday order when both are touched on the same day.

## Decision
A chronological path simulator reads canonical OHLCV rows from episode anchors. It reports TP hit, SL hit, first-hit date, MFE, MAE, horizon return, and days to hit. Same-day ambiguity is configurable with default `stop_first`.

## Alternatives Considered
- Use only highest/lowest aggregates: rejected because first-hit order is unknowable.
- Assume target first: rejected as optimistic default.

## Consequences
TP/SL research can later use consistent path semantics and conservative ambiguity handling.

## Risks
Daily OHLCV remains less precise than intraday data. Same-day policy can materially affect outcomes.

## Validation Strategy
Tests cover TP first, SL first, separate-day hits, same-day stop-first, and ambiguous exclusion.

Sprint 4.1 extends the simulator with gap-aware fill metadata and entry-day trigger audit fields.
