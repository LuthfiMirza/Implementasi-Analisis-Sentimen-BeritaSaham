# ADR-061: Probabilistic and Capital Risk Deferral

Status: Accepted

## Context
Action-specific probability, expected value, CVaR, and capital risk require calibrated evidence, costs, account context, and position sizing.

## Decision
Sprint 11 defers probabilistic, net, capital, portfolio, execution, and position-management risk. Fields remain null and explicitly unavailable.

## Alternatives
- Use prediction probability as probability of profit: rejected because model probability is not calibrated action outcome probability.
- Assume zero fees/slippage or account balance: rejected as hidden production assumption.

## Consequences
Risk can be evaluated for gross geometry only. Position sizing remains not implemented.

## Risks
Completeness is limited but contract safety is preserved.

## Validation Strategy
Tests reject populated probability/net/capital metrics without corresponding contracts.
