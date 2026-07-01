# ADR-005: Research Artifact Usability Policy

Status: Accepted

## Context
A valid schema does not mean an artifact is safe for decision use. Sprint 3 produced a BUMI TP artifact with negative out-of-sample expectancy but `usable_for_decision=true`.

## Decision
`usable_for_decision` is controlled by deterministic configurable gates: validation expectancy, profitable fold ratio, effective sample size, fold count, downside tail, confidence interval width, source validity, leakage checks, and critical warnings. If gates fail, `selected` is null, quality becomes `research_only`, and `best_candidate_by_score` remains available for analysis.

## Alternatives Considered
- Always select the best score: rejected because weak OOS performance should not become decision evidence.
- Hardcode BUMI/DEWA exceptions: rejected because policy must be general and auditable.

## Consequences
Artifacts can be valid research outputs while not usable for decisions. Later Decision Engine work can safely consume quality flags.

## Risks
Conservative gates can mark potentially useful research as not usable until enough independent evidence exists.

## Validation Strategy
Unit tests cover negative OOS expectancy, selected-null schema, quality inconsistency rejection, confidence interval failure, effective sample minimum, and ticker artifact regressions.
