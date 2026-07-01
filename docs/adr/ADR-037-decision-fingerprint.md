# ADR-037: Decision Fingerprint

Status: Accepted

## Context
Decision outputs need deterministic auditability across identical input and Registry states.

## Decision
Add SHA-256 `decision_fingerprint` over normalized ticker, decision_at, prediction snapshots, source artifact IDs/checksums/usage tiers, open-trade identity, schema version, and service contract version. Exclude random data, hidden current time, unordered maps, and runtime-specific values.

## Alternatives Considered
- Use generated timestamp UUID: rejected because it is not deterministic.
- Hash full artifact payloads: rejected because the Registry metadata checksum is sufficient and avoids large payload copies.

## Consequences
Changing a prediction or artifact checksum changes the fingerprint, while ordering noise does not.

## Risks
Fingerprint compatibility must be maintained when schema evolves.

## Validation Strategy
Tests assert same input/state same fingerprint and prediction/checksum changes alter the fingerprint.

## Sprint 8 Update
Fingerprint now includes confidence schema/version/profile, component results, reason schema, and primary reason codes.
