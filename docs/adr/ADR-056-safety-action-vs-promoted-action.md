# ADR-056: Safety Action vs Promoted Action

Status: Accepted

## Context
Top-level decision action currently represents safety behavior, not final trading action.

## Decision
Decision output exposes `safety_action`, `promoted_action`, and `executable_action`. While promoted action is null, top-level `action` must equal safety action.

## Alternatives
- Let top-level action show candidate intent: rejected because it would imply recommendation.
- Hide safety action: rejected because WAIT/NO_TRADE remains the consumer-facing action.

## Consequences
WAIT/NO_TRADE stay stable while promotion evolves independently.

## Risks
Output has redundant-looking fields; validator enforces consistency.

## Validation Strategy
Decision tests assert top-level action equals selection safety action and promoted/executable action null.
