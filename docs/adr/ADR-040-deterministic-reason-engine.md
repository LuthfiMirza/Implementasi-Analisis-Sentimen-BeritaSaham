# ADR-040: Deterministic Reason Engine

Status: Accepted

## Context
Reasons must be audit-ready and non-generative.

## Decision
Generate structured reasons from deterministic rules using prediction evidence, Registry metadata, gates, confidence components, warnings, blockers, and capability status. Reasons have category, severity, polarity, impact, source metadata, evidence, and rank.

## Alternatives Considered
- LLM-generated explanations: rejected because Sprint 8 requires deterministic auditability.
- Free-text-only reasons: rejected because downstream engines need structured codes.

## Consequences
Warnings and blockers derive from canonical structured reasons.

## Risks
Rule coverage can miss nuance; future sprints can add deterministic rules.

## Validation Strategy
Tests cover ordering, deduplication, severity escalation, dominant blocker, and no aggressive wording.
