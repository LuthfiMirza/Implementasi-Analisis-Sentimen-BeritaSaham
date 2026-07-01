# ADR-019: Extended-Window Purge and Embargo

Status: Accepted

## Context
Re-entry outcomes extend beyond the original trade horizon, increasing leakage risk near walk-forward boundaries.

## Decision
Nested folds store purge windows that include original horizon plus extension window, configurable embargo, and leakage checks. Outer validation is not used for candidate selection.

## Alternatives Considered
- Reuse original horizon purge only: rejected because recovery windows can cross validation boundaries.

## Consequences
Fold evidence is more conservative and transparent.

## Risks
Long extension windows reduce usable training samples.

## Validation Strategy
Tests cover fold isolation, purge metadata, embargo metadata, and deterministic candidate selection.
