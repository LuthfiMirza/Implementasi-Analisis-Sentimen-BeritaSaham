# ADR-084: Management Candidate vs Management Action

Date: 2026-07-02
Status: Accepted

## Context

Sprint 16.1 extends position monitoring with explicit reference-only policy, review candidates, and selection contracts. Stop or target conditions are observations and cannot directly become HOLD, SELL, CUT_LOSS, or executable instructions.

## Decision

Use explicit position-bound, ticker-bound, side-bound policy input to map normalized position-state conditions into non-executable review hypotheses. Candidate identity is deterministic and includes policy, rule, state, observation, condition, schema, and decision timestamp. Selection remains contract-only because management risk, management plan, portfolio approval, promotion, and execution are not implemented.

## Consequences

No default policy is stored in config, no Trade Journal or database fallback is allowed, no implicit HOLD is formed from normal monitoring, and all management selected/promoted/executable fields remain null. Final top-level action remains WAIT or NO_TRADE.
