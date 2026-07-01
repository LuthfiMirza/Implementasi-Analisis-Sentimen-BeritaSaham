# ADR-052: Action Candidate Identity

Status: Accepted

## Context
Downstream risk needs stable candidate identity for auditability and deterministic fingerprints.

## Decision
Candidate-ready output gets SHA-256 candidate ID from ticker, decision fingerprint seed, intent, direction, position context, prediction identities, artifact IDs/checksums, and candidate contract version.

## Alternatives
- Random IDs: rejected because they break determinism.
- No candidate ID: rejected because risk cannot reference candidate identity.

## Consequences
Same input and Registry state produce the same ID; prediction or checksum changes alter ID.

## Risks
Identity stability depends on normalized input ordering.

## Validation Strategy
Tests assert deterministic ID and ID changes when prediction/artifact checksum changes.
