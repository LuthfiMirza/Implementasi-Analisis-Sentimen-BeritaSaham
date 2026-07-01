# ADR-029: Registry Quality Classification

Status: Accepted

## Context
Artifact schema validity is different from usability. Research-only artifacts must remain importable without being promoted to decision-usable.

## Decision
Registry normalizes `validation_status`, `usage_tier`, and `quality_grade`. It never upgrades source usability. It may downgrade registry usability for stale, quarantine, checksum mismatch, critical dependency failure, high unclassified rate, or selected-null decision blockers.

## Alternatives Considered
- Treat all valid artifacts as decision usable: rejected as unsafe.
- Reject research-only artifacts: rejected because Sprint 6 is a research registry.

## Consequences
Latest research queries can return valid research-only artifacts, while latest decision queries return null until source evidence is decision-usable.

## Risks
Quality grading is policy-driven and must remain configurable.

## Validation Strategy
Tests cover selected-null acceptance, decision query null, high-unclassified limitation, ATR unavailable limitation, stale policy, and quarantine.
