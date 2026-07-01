# ADR-011: Premature Stop and Recovery

Status: Accepted

## Context
A stop hit is not automatically a good stop. Price may recover to entry or reach a TP candidate later in the same research horizon.

## Decision
A premature stop occurs when SL is hit first and the remaining horizon later recovers to entry or reaches a TP candidate. Artifacts report recovered-to-entry, reached-TP-after-stop, recovery days, maximum recovery, loss avoided, and whether the stop prevented a larger horizon loss.

## Alternatives Considered
- Count every stop hit as correct: rejected because it overstates risk control.
- Ignore post-stop path: rejected because recovery is material to SL quality.

## Consequences
Candidate scoring can penalize overly tight stops that exit recoverable trades.

## Risks
Daily OHLCV cannot fully order intraday recovery after a stop on the same day.

## Validation Strategy
Unit tests cover premature stop, recovery, loss avoided, and same-day ambiguity policy.
