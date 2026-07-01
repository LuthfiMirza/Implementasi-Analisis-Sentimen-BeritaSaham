# ADR-013: Transaction Cost and Slippage Model

Status: Accepted

## Context
Gross expectancy can overstate trade quality when fees, taxes, and slippage are omitted.

## Decision
SL artifacts store a configurable execution-cost model and separate gross and net metrics. Default costs are zero for backward-compatible research, with an explicit `execution costs disabled` warning.

## Alternatives Considered
- Hardcode market costs: rejected because assumptions must be user-controlled.
- Ignore costs until production: rejected because optimizer ranking can change after costs.

## Consequences
Decision usability must use net metrics, while gross metrics remain diagnostic.

## Risks
Zero-cost defaults can still be misread if warnings are ignored.

## Validation Strategy
Unit tests cover zero-cost compatibility and gross vs net semantics.
