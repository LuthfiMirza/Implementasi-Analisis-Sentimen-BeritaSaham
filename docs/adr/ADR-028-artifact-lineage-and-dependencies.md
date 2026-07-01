# ADR-028: Artifact Lineage and Dependencies

Status: Accepted

## Context
Optimizers and re-entry artifacts depend on source artifacts and OHLCV files. Decision consumers need to know whether dependencies exist and match expected checksums.

## Decision
Store dependency metadata separately from artifact rows. Artifact dependencies are resolved to registry records when possible; external sources such as OHLCV are stored with `external_source` resolution.

## Alternatives Considered
- Store dependencies only inside summary JSON: rejected because dependency queries and resolution require relational indexes.
- Require dependencies to be imported first: rejected because unresolved dependencies must be visible and resolvable later.

## Consequences
Artifacts can be imported out of order while preserving unresolved lineage.

## Risks
Different artifact schemas name source fields differently; validation extracts dependencies with conservative adapters.

## Validation Strategy
Tests cover resolved, unresolved, checksum/schema/ticker mismatch, external dependencies, and duplicate prevention.
