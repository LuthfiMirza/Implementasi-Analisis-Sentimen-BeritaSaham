# ADR-012: Gap-Aware Trade Execution

Status: Accepted

## Context
Sprint 4 assumed exact trigger fills. This understated gap risk and made CVaR equal to stop distance.

## Decision
Use gap-aware daily OHLCV fills: long stops fill at open when open gaps below stop, otherwise at stop when low crosses; targets fill at open when open gaps above target, otherwise at target when high crosses. Same-day TP/SL remains configurable with `stop_first` default.

## Alternatives Considered
- Exact trigger fills: rejected as optimistic for gaps.
- Intraday reconstruction: unavailable from daily OHLCV.

## Consequences
Artifacts can report trigger price, fill price, fill reason, gap amount, and gap-adjusted return.

## Risks
Daily OHLCV still cannot order intraday high/low after open.

## Validation Strategy
Unit tests cover gap stop, gap target, intraday fills, and same-day ambiguity.
