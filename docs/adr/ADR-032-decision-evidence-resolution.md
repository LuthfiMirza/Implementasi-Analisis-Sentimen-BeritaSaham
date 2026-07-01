# ADR-032: Decision Evidence Resolution

Status: Accepted

## Context
Registry has separate latest valid, latest research-usable, and latest decision-usable resolution methods.

## Decision
Decision evidence resolves each artifact type through the registry service boundary and records all three availability levels. The service never scans filesystem, reads JSON directly, or falls back from decision-usable to research-only.

## Alternatives Considered
- Query registry models from the decision service directly: rejected to preserve registry boundary.
- Use latest valid artifacts for decision: rejected because validity is not usability.

## Consequences
Evidence snapshots remain metadata-only and source payloads are not copied.

## Risks
Registry metadata must be imported before decision evaluation.

## Validation Strategy
Integration tests consume registry records and assert decision queries return null for current TP/SL/re-entry.

## Sprint 7.1 Update
Source artifact snapshots now include explicit latest resolution categories for valid, research-usable, and decision-usable metadata.
