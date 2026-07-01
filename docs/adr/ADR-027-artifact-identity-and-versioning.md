# ADR-027: Artifact Identity and Versioning

Status: Accepted

## Context
Filenames are advisory and can change independently from artifact identity. Re-importing changed files must preserve history and detect conflicts.

## Decision
Logical identity is derived from ticker, artifact type, schema version, generated_at, and generator_version when available. Checksum identifies exact file content. Same logical identity with different checksum is a conflict and is not automatically latest.

## Alternatives Considered
- Use filename as identity: rejected because root JSON is authoritative.
- Use checksum only: rejected because versions with the same semantics need logical lineage.

## Consequences
History can store regenerated artifacts and detect modified logical artifacts safely.

## Risks
Artifacts missing generated_at cannot form a valid identity and are rejected or quarantined.

## Validation Strategy
Tests cover unchanged import, changed checksum import, logical identity conflict, and latest flag behavior.
