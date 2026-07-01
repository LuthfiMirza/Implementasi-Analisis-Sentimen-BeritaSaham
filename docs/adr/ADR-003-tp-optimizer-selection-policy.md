# ADR-003: TP Optimizer Selection Policy

Status: Accepted

## Context
TP research must evaluate candidate take-profit values historically without becoming a BUY decision engine or a production hardcoded recommendation.

## Decision
Candidate TP values come from CLI/config. For each candidate, realized return is calculated as candidate TP when MFE reaches the candidate during the holding period; otherwise realized return uses the event `return_pct`. Candidate scoring uses deterministic, transparent weighted components: expectancy, hit rate, days to hit, drawdown, downside tail, and stability. Weights are stored in config and in the artifact. Sprint 3.1 separates `best_candidate_by_score` from `selected`: a candidate is selected only if the usability policy gates pass.

## Alternatives Considered
- Select highest hit rate: rejected because it can favor tiny TPs with poor expectancy.
- Select highest average return over all history only: rejected because it ignores chronological validation stability.
- Embed static production TP defaults: rejected because Sprint 3 is research-only.

## Consequences
The artifact explains why a TP candidate scored best and preserves out-of-sample fold evidence. Decision services can later require `selected` plus `usable_for_decision=true`; research can still inspect `best_candidate_by_score` when gates fail.

## Risks
MFE-based TP hit detection does not know exact intraday path and approximates days to hit from event-level summary data. Fold stability can be sensitive to candidate spacing.

## Validation Strategy
Unit tests cover hit and timeout realized returns, candidate metrics, chronological folds, no train-validation leakage, deterministic selection, selected TP membership, insufficient segment samples, source checksum, and CLI output.
