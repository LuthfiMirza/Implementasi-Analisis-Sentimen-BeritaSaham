# ADR-015: Joint TP-SL Source Usability Policy

Status: Accepted

## Context
Standalone TP artifacts are research-only, but their candidate list can still be valid search-space provenance for joint TP-SL research.

## Decision
Joint SL research may use schema-valid TP candidate lists even when standalone TP is not decision usable. Decision usability depends on joint evidence gates, source checksums, net OOS metrics, CI lower bound, fold quality, boundary effects, extreme-winner dependency, gap risk, and cost policy.

## Alternatives Considered
- Block all joint research when TP is not decision usable: rejected because joint exit objectives differ.
- Promote joint results despite TP source weakness: rejected until joint gates pass.

## Consequences
Artifacts can be risk-analysis usable while decision-unusable.

## Risks
Users may confuse best research score with selected decision-grade output.

## Validation Strategy
Tests verify selected remains null when gates fail and TP candidate provenance remains accepted.
