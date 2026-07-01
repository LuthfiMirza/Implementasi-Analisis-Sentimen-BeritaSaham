# ADR-033: Prediction Semantics Normalization

Status: Accepted

## Context
Prediction variants can be directional or regime-based. DEWA regime `move` does not mean directional up.

## Decision
Normalize prediction semantics into directional and regime categories: directional_up, directional_down, directional_neutral, regime_move, regime_no_move, and unknown. Probability is stored as evidence only and never used as a BUY/SELL threshold in Sprint 7.

## Alternatives Considered
- Treat all positive/move outputs as bullish: rejected because regime models do not encode direction.
- Hardcode variant-specific trading thresholds: rejected because Confidence and Risk Engines are blocked.

## Consequences
The service can evaluate prediction validity without implying trade direction.

## Risks
Unknown variants may produce NO_TRADE until mapped.

## Validation Strategy
Tests assert DEWA regime move is not interpreted as up and unknown semantics remain safe.

## Sprint 7.1 Update
Prediction semantics are role-aware. Regime `move` is never directional `up`; multiple directional predictions with contradictory semantics are blocking.
