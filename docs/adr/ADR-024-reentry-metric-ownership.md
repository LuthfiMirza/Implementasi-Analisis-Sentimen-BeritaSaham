# ADR-024: Re-entry Metric Ownership

Status: Accepted

## Context
Sprint 5.1 exposed top-level expectancy and confidence interval fields that could be misread as applying equally to after-stop, after-TP, and after-timeout streams. Some streams have very different denominators and sample quality.

## Decision
`reentry_research_v1_1` keeps decision metrics owned by stream. Each stream owns its OOS non-zero incremental expectancy, confidence interval, fold counts, sample status, top-5% contribution, trimmed expectancy, quality, and warnings. Top-level `summary` may only contain pointers, stream statuses, or explicitly documented aggregates.

Confidence intervals must record estimator, observation count, confidence level, bootstrap iterations, random seed, bounds, and sample identity. Validators reject top-level CI fields that obscure stream ownership and reject stream CI objects whose observation count does not match the stream sample count.

## Alternatives Considered
- Keep a single top-level CI: rejected because it hides stream ownership and can mix incompatible samples.
- Duplicate one stream metric into all streams: rejected because it creates false evidence for low-sample streams.

## Consequences
Registry consumers must read stream-owned metrics directly. Aggregates remain allowed only when the weighting method is explicit and not confused with stream expectancy.

## Validation Strategy
Regression tests assert that stream metrics exist independently, top-level CI is empty, CI sample identity matches outer-validation incremental returns, and validator rejects ambiguous top-level CI.
