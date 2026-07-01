# ADR-049: No Research Parameter Promotion

Status: Accepted

## Context
Research artifacts can contain candidate TP/SL/re-entry parameters, but Sprint 9 has no Action Selection, Position Sizing, or production Trade Plan capability.

## Decision
Research-only candidates must not be promoted to selected decision parameters, decision risk metrics, or executable trade-plan fields. Only Registry metadata and selected decision-usable availability may be used by Risk and Trade Plan contracts.

## Alternatives
- Use best research candidate as selected: rejected because it bypasses Registry decision-usability gates.
- Use hardcoded default TP/SL: rejected as a magic trading threshold.

## Consequences
Risk and Trade Plan contracts expose limitations and blockers instead of numeric production parameters.

## Risks
Decision output remains conservative for current artifacts, which is intentional until selection and plan engines are explicitly designed.

## Validation Strategy
Tests reject numeric TP/SL/RR fields when unavailable and assert no fallback from research candidates.
