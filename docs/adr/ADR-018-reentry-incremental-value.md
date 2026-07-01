# ADR-018: Re-entry Incremental Value

Status: Accepted

## Context
A profitable re-entry trade is not necessarily useful if doing nothing would have been better or if extra costs erase the gain.

## Decision
Primary re-entry metric is incremental value versus no re-entry. Artifacts report zero-cost and non-zero-cost profiles, combined net return, incremental expectancy, CVaR, and worsened/improved rates.

## Alternatives Considered
- Report standalone re-entry return only: rejected because it ignores opportunity baseline.

## Consequences
Research focuses on whether re-entry adds value after the original exit.

## Risks
Cost assumptions are configurable and not production defaults.

## Validation Strategy
Tests cover zero-cost, non-zero-cost, and gross-positive/net-worse behavior.
