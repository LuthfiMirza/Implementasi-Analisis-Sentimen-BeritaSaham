# ADR-017: Post-Exit Recovery Definition

Status: Accepted

## Context
Recovery after stop, pullback after TP, and continuation after timeout have different behavior and must not be mixed.

## Decision
Sprint 5 separates three streams: after-stop recovery, after-TP pullback, and after-timeout continuation. Each stream reports counts, rates, and timing using post-exit OHLCV only.

## Alternatives Considered
- Single combined recovery metric: rejected because it confuses distinct exit regimes.

## Consequences
Research can identify whether recovery is specific to stop exits or broad continuation behavior.

## Risks
Small stream samples can reduce fold stability.

## Validation Strategy
Tests verify each stream exists and produces separate metrics.
