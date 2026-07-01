# ADR-001: Research Artifact Format

Status: Accepted

## Context
AI Trading research outputs must be consumed by later services without coupling to model training, Laravel controllers, FastAPI serving, or dashboard code. Artifacts need enough metadata to be audited and regenerated.

## Decision
Research outputs are versioned JSON artifacts with required root fields: `schema_version`, `artifact_type`, `ticker`, `generated_at`, `config`, `source`, `quality`, and domain-specific payload sections. Source artifacts must include a checksum when one artifact depends on another.

## Alternatives Considered
- Database-first persistence: rejected for research sprints because it would create migration and app coupling before schemas stabilize.
- CSV-only output: rejected because nested quality, fold, score, and source metadata would be lossy.

## Consequences
Artifacts are easy to diff, archive, validate, and import later. Later registry work can read stable JSON rather than recomputing research.

## Risks
Schema drift can occur if validators are not updated with every schema change. Large event artifacts can be bulky in source control.

## Validation Strategy
Every artifact writer must call a validator before writing. Unit tests cover valid output, invalid schema, source checksum, missing fields, and quality consistency.
