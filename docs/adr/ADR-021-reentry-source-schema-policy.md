# ADR-021: Re-entry Source Schema Policy

Status: Accepted

## Context
Sprint 5 used a filename ending in v1 while the source schema was v1_1, creating ambiguity.

## Decision
Re-entry v1_1 validates source schema from JSON root, not filename. `sl_optimizer_v1_1` is required by default; legacy schemas require explicit compatibility mode and warnings.

## Alternatives Considered
- Trust filename: rejected because filenames can lag schema evolution.

## Consequences
Artifact provenance is deterministic and registry-ready.

## Risks
Strict validation can block older experiments unless compatibility is requested.

## Validation Strategy
Tests cover v1_1 acceptance, stale schema rejection, checksum mismatch, and ticker mismatch.
