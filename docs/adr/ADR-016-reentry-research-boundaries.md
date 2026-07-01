# ADR-016: Re-entry Research Boundaries

Status: Accepted

## Context
Re-entry can easily become martingale or production buy-back logic if boundaries are unclear.

## Decision
Sprint 5 allows at most one re-entry per original episode, constant nominal exposure, and no position-size increase. Results remain research artifacts only and never create BUY_BACK production actions.

## Alternatives Considered
- Unlimited averaging down: rejected as martingale risk.
- Production buy-back zones: rejected until decision-grade validation exists.

## Consequences
Research measures one independent follow-up trade rather than capital escalation.

## Risks
Single re-entry may understate strategies that scale in gradually.

## Validation Strategy
Tests verify selected remains null and maximum reentries equals one.
