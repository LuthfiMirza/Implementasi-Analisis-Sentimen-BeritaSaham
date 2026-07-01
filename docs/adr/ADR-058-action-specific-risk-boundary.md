# ADR-058: Action-Specific Risk Boundary

Status: Accepted

## Context
Risk must be tied to a concrete candidate identity and selected decision-grade parameters. Research-risk evidence alone is not enough.

## Decision
Introduce ActionRiskEvaluationService. It evaluates only candidate-specific gross geometry from validated selected-parameter evidence. It does not select candidates, create trade plans, calculate position size, or promote actions.

## Alternatives
- Continue using generic decision risk: rejected because it is not candidate-specific.
- Use research-only optimizer values: rejected by no-fallback policy.

## Consequences
Risk schema evolves to `trading_risk_v1_1`; canonical candidate risk is `action_specific_risk`.

## Risks
Real BUMI/DEWA remain unavailable until Registry has selected decision-grade values.

## Validation Strategy
Unit tests cover missing candidate, research-only parameters, identity mismatch, invalid geometry, and synthetic valid geometry.
