# ADR-026: Research Artifact Registry

Status: Accepted

## Context
Research artifacts now span event datasets, trade episodes, TP/SL optimizer outputs, and re-entry research. Consumers need a central metadata registry without modifying artifact payloads or creating trading actions.

## Decision
Create a Laravel-only Research Artifact Registry backed by metadata tables. Filesystem JSON remains the source payload; the registry stores checksums, normalized metadata, quality/usability, warnings, lineage, latest flags, stale/quarantine state, and dependency rows.

## Alternatives Considered
- Read filesystem artifacts directly in every consumer: rejected because checksum, staleness, lineage, and latest resolution would be duplicated.
- Store full JSON payloads in the database: rejected because artifact files are the canonical payload and can be large.

## Consequences
Consumers can query latest valid/research/decision artifacts through a service while payload history remains on disk.

## Risks
Registry metadata can drift from files; verification command mitigates this by rechecking existence and checksum.

## Validation Strategy
Feature tests cover discovery, validation, import idempotency, latest resolution, quarantine, and verification.
