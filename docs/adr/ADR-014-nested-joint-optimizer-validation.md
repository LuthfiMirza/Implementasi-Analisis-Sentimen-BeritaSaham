# ADR-014: Nested Joint Optimizer Validation

Status: Accepted

## Context
Selecting a global best TP-SL pair from validation data biases reported OOS performance.

## Decision
Sprint 4.1 records nested walk-forward evidence: inner selection occurs inside outer training data, and outer validation evaluates one selected pair. Artifacts store selected pair frequency, family frequency, profitable outer-fold ratio, worst fold, median fold, and dispersion.

## Alternatives Considered
- Global best matrix as OOS: rejected due selection bias.
- Random split: rejected due chronological leakage.

## Consequences
Research score and selected decision-grade pair remain separate.

## Risks
Small fold counts can produce unstable nested estimates.

## Validation Strategy
Tests cover chronological fold behavior, deterministic selection, and insufficient fold nullability.
