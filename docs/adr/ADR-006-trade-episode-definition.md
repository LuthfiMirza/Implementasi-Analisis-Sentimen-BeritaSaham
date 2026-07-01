# ADR-006: Trade Episode Definition

Status: Accepted

## Context
Daily BUY observations are descriptive signals, not independent executable trades. Continuous BUY sequences create overlapping holding windows and inflated raw sample sizes.

## Decision
A Trade Episode Dataset is introduced. Primary construction uses `one_position_fixed_horizon`: after an entry, later BUY observations are ignored until the configured research horizon completes. `signal_transition` and `fixed_spacing` remain sensitivity policies. Default entry timing is next available trading-day open.

## Alternatives Considered
- Treat every BUY observation as a trade: rejected because overlap dominates.
- Connected-component clusters as trades: rejected because transitive clusters can collapse long regimes and are not execution policy.

## Consequences
Optimizers use executable non-concurrent episodes. Raw observations remain available for descriptive analysis.

## Risks
One-position fixed horizon may miss valid pyramiding or re-entry behavior, which is intentionally out of scope.

## Validation Strategy
Tests cover continuous BUY sequences, one-position suppression, fixed spacing, next-day entry, deterministic IDs, incomplete horizons, and source checksums.
