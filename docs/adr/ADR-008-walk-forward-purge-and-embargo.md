# ADR-008: Walk-Forward Purge and Embargo

Status: Accepted

## Context
Trade outcomes use future horizon windows. Walk-forward validation must prevent training outcome windows from leaking into validation periods.

## Decision
Overlap is controlled first by episode construction. Walk-forward research must also store purge and embargo metadata around train-validation boundaries and validate no leakage. Sprint 3.2 establishes this requirement for downstream optimizers.

## Alternatives Considered
- Remove all transitive overlap clusters: rejected because it destroys most training data and is not a boundary-specific leakage control.
- Ignore boundary purge: rejected because future outcome windows can cross validation boundaries.

## Consequences
Future optimizer folds must report before/after purge counts and leakage checks.

## Risks
Overly large purge/embargo windows can reduce validation power.

## Validation Strategy
Unit tests cover no-leakage semantics and nullability when valid folds are insufficient.
