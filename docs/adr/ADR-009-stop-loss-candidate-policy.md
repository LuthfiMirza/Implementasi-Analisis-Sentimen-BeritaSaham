# ADR-009: Stop-Loss Candidate Policy

Status: Accepted

## Context
Stop-loss research must measure downside risk without becoming a production sell rule.

## Decision
Sprint 4 evaluates fixed-percentage and ATR-multiple SL candidates from config/CLI. ATR candidates use entry-time ATR only; missing or invalid ATR excludes that candidate for the episode. SL is not selected from stop-hit rate alone; scoring includes expectancy, downside tail, CVaR, premature stops, recovery, duration, and fold quality.

## Alternatives Considered
- Select lowest stop-hit rate: rejected because loose stops can hide large drawdowns.
- Fallback ATR to fixed percent: rejected because it masks missing feature coverage.

## Consequences
Artifacts separate downside research from decision usability and preserve ATR coverage diagnostics.

## Risks
Episode snapshots currently have limited feature payload; ATR coverage may be low until entry snapshots are enriched.

## Validation Strategy
Unit tests cover fixed SL, ATR exclusions, source checksums, nullability, and quality downgrade.

Sprint 4.1 adds per-family quality so fixed-percent and ATR candidates can have different coverage and usability.
