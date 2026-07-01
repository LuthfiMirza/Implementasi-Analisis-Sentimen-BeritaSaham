# ADR-054: Action Selection Boundary

Status: Accepted

## Context
Action candidates are internal hypotheses. Sprint 10.1 needs a separate selection contract before promotion or execution can exist.

## Decision
Introduce ActionSelectionService. It evaluates candidate, confidence, risk, trade-plan, identity, and capability gates, but never promotes actions and never changes top-level safety action.

## Alternatives
- Select directly in TradingDecisionService: rejected because selection must be auditable and independent.
- Select by score threshold: rejected because no production selection policy exists.

## Consequences
Real BUMI/DEWA keep selected candidate null. Synthetic contract tests can prove identity checks while selection remains disabled.

## Risks
Additional contract verbosity is mitigated by structured gates and reason codes.

## Validation Strategy
Unit tests cover unavailable, blocked, identity mismatch, risk/plan unavailable, capability disabled, and deterministic gate order.
