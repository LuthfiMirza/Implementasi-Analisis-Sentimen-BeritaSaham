# ADR-063: Entry Reference Evidence Contract

Status: Accepted

## Context
Reference TP/SL prices require an explicit entry reference; hidden current price or prediction output must not be used.

## Decision
Use `trading_entry_reference_v1` evidence with ticker, candidate identity, observed timestamp, source, positive price, and `executable=false`.

## Alternatives
- Fetch market price in service: rejected due to no network/API and hidden-time constraints.
- Use optimizer or prediction-derived entry: rejected as unsafe fallback.

## Consequences
Real BUMI/DEWA remain unavailable; synthetic tests may provide reference entries.

## Validation Strategy
Validator rejects missing source, future/stale timestamps, mismatched candidate identity, non-positive price, and executable entries.
