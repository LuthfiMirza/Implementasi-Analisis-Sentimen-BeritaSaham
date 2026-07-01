# ADR-050: Action Candidate vs Final Action

Status: Accepted

## Context
Risk and trade-plan contracts need an action identity, but final aggressive actions remain blocked. Candidate and final action must not be conflated.

## Decision
Introduce a non-executable action candidate contract. Candidates are internal hypotheses for downstream analysis and never replace final decision action in Sprint 10.

## Alternatives
- Promote candidate directly to BUY: rejected because promotion, risk, and plan readiness are incomplete.
- Keep candidate absent: rejected because risk needs action-specific identity.

## Consequences
Decision output gains `action_candidate` and `action_promotion`, while final supported actions remain WAIT/NO_TRADE.

## Risks
Consumers may misread candidate as recommendation; schema uses `execution_status=non_executable` and promotion `not_implemented`.

## Validation Strategy
Tests verify candidate-ready synthetic output still returns WAIT and no BUY.
