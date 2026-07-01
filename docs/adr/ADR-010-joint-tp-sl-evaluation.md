# ADR-010: Joint TP-SL Evaluation

Status: Accepted

## Context
TP artifacts are research-only and not decision usable. SL cannot be optimized against a production TP that does not exist.

## Decision
Sprint 4 performs standalone SL analysis and joint TP-SL sensitivity across TP candidates from the TP artifact. `best_tp_sl_pair_by_score` is research evidence only. `selected` remains null unless all quality gates pass, including source TP decision usability.

## Alternatives Considered
- Use TP best candidate as production target: rejected because TP quality is `research_only`.
- Optimize SL standalone only: rejected because stop behavior depends on target interaction and first-hit order.

## Consequences
SL artifacts can be useful for risk diagnostics while remaining decision-unusable.

## Risks
Joint matrix is computationally larger and sensitive to daily OHLCV ambiguity.

## Validation Strategy
Unit tests cover TP-first, SL-first, timeout, same-day ambiguity, best candidate retention, and decision-usability downgrade.

Sprint 4.1 adds nested walk-forward validation and separates best gross pair, best net pair, most frequent nested pair, and selected decision-grade pair.
