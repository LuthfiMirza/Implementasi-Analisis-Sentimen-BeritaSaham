# ADR-004: Overlapping Trade Events

Status: Accepted

## Context
Sprint 3 quality audit showed almost every BUY event overlaps another holding window. Treating all overlapping events as independent overstates sample size and can make TP evidence look more reliable than it is.

## Decision
TP optimizer keeps `all_events_analysis` for descriptive research but must not treat connected-component cluster count as a primary effective sample estimator. Sprint 3.2 introduces Trade Episode Dataset construction as the primary executable sample definition. Cluster count remains an overlap diagnostic only.

## Alternatives Considered
- Use all events for selection: rejected because overlapping events are not independent.
- Delete overlapping events from source artifacts: rejected because Sprint 2 artifacts are research inputs and should remain auditable.
- Cluster-only selection: deferred; cluster count is reported but purge is simpler and deterministic for Sprint 3.1.

## Consequences
Effective sample size is lower and usability may be downgraded. The artifact remains transparent about both descriptive and decision-evidence views.

## Risks
Purging can discard useful nearby signals and may underrepresent high-signal regimes.

## Validation Strategy
Unit tests verify overlap purge, effective sample size, and that incomplete windows are excluded before optimization.
