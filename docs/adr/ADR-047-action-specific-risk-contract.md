# ADR-047: Action-Specific Risk Contract

Status: Accepted

## Context
Risk values such as RR, expected loss, drawdown, or CVaR are meaningful only for a concrete action with entry/TP/SL semantics.

## Decision
Decision risk must include action identity and action candidate version before numeric metrics can be populated. Without a candidate, `decision_risk.status` is `unavailable`, `action` is null, all numeric metrics are null, and reason codes explain missing prerequisites.

## Alternatives
- Scalar risk independent of action: rejected because it hides entry and exit assumptions.
- Infer BUY from directional prediction: rejected because Action Selection Engine is blocked.

## Consequences
Synthetic decision-ready artifacts still cannot produce decision risk without an action candidate. Risk Engine does not choose actions.

## Risks
The contract may feel conservative until Action Selection exists, but this prevents accidental production trading parameters.

## Validation Strategy
Tests cover missing action candidates, selected TP/SL requirements, numeric nullability, and no production TP/SL fallback.
