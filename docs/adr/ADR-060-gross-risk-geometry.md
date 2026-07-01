# ADR-060: Gross Risk Geometry

Status: Accepted

## Context
Sprint 11 can compute deterministic upside/downside geometry but cannot compute probabilities, costs, or capital exposure.

## Decision
For long-entry percentage TP/SL, compute gross upside, gross downside, and gross reward/risk ratio. Optional entry reference computes reference TP/SL prices, explicitly non-executable.

## Alternatives
- Compute expected value/probability from prediction probability: rejected because no calibrated action-risk evidence exists.
- Use RR threshold for selection: rejected because selection policy is blocked.

## Consequences
Geometry is metric-only and never a recommendation.

## Risks
Users may overinterpret RR. Output includes unavailable net/probabilistic/capital metrics and non-executable reason codes.

## Validation Strategy
Tests validate ratio invariant, entry-reference formulas, rounding, null probabilistic/net/capital metrics, and invalid denominator rejection.
