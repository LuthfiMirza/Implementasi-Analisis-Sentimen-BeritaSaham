# ADR-046: Research Risk vs Decision Risk

Status: Accepted

## Context
Sprint 9 introduces risk as a structured contract. Existing Registry metadata can describe research-risk evidence, but production decision risk requires an action-specific candidate and decision-usable parameters.

## Decision
Separate research-risk evidence from decision risk. Research risk may be available from Registry metadata and remains non-executable. Decision risk remains unavailable unless an action candidate, selected TP/SL, decision-usable artifacts, integrity checks, and calculation capability are present.

## Alternatives
- Reuse research-only risk as decision risk: rejected because it would promote non-production evidence.
- Keep `risk` null: rejected because downstream contracts need explicit readiness and blockers.

## Consequences
Risk output becomes a structured object in `trading_decision_v1_4`. Current BUMI/DEWA can expose research-risk availability while decision risk remains unavailable.

## Risks
Users may misread research-risk evidence as executable risk. The schema therefore keeps decision metrics null and requires reason codes.

## Validation Strategy
Unit tests validate nullability, no fallback, action identity requirements, and deterministic output. Integration tests validate real Registry metadata without reading payload files.
