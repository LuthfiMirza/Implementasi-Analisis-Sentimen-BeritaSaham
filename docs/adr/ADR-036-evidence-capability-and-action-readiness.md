# ADR-036: Evidence, Capability, and Action Readiness

Status: Accepted

## Context
Recommendation quality alone is insufficient to distinguish research evidence, decision-grade artifacts, and implementation capability.

## Decision
Add separate readiness fields: `evidence_readiness`, `capability_readiness`, and `action_eligibility`. Current BUMI/DEWA are `research_ready/basic_only/blocked`. Synthetic decision-ready evidence becomes `decision_ready/basic_only/eligible_but_not_supported` with action status `unsupported`.

## Alternatives Considered
- Continue using only action_status: rejected because evidence quality and implementation capability are separate concerns.
- Promote decision-ready synthetic evidence to BUY: rejected because action selection is not implemented.

## Consequences
Confidence and Reason Engines can consume a clearer contract without inferring capability from artifact status.

## Risks
Readiness enums must be validated strictly to avoid ambiguous states.

## Validation Strategy
Tests cover unavailable, partial, research-ready, decision-ready, blocked, and unsupported states.

## Sprint 8 Update
Evidence readiness now feeds evidence confidence, while action eligibility controls action confidence availability.
