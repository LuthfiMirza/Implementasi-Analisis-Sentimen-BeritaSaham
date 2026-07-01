# ADR-002: Walk-Forward Event Dataset

Status: Accepted

## Context
TP and SL research need a trade-lifecycle dataset where each historical BUY signal becomes one auditable event. This dataset must not train a model or make a trading decision.

## Decision
The event dataset stores one record per BUY event with entry-date features and holding-period outcome metrics. Point-in-time fields such as ATR, RSI, MACD, ADX, VWAP, volume ratio, regime, sentiment, and prediction metadata are captured at entry date. Future OHLCV is used only for outcome fields such as return, MFE, MAE, drawdown, recovery, and exit price.

## Alternatives Considered
- Recompute event features inside every optimizer: rejected because it would duplicate logic and increase look-ahead risk.
- Store only raw OHLCV windows: rejected because later research would need to repeatedly reconstruct the same event semantics.

## Consequences
Optimizers can focus on evaluating exit policies. Quality gates can audit duplicates, overlap, missing values, and price consistency before downstream research.

## Risks
If prediction history is unavailable, BUY signal provenance cannot be independently replayed from model logs. Overlapping holding periods are expected in signal research but must be documented.

## Validation Strategy
The event dataset validator checks required fields, schema version, ticker, duplicate entry dates, missing OHLCV-backed prices, and invalid prices. The Sprint 3 quality gate adds distribution, overlap, missing value, and leakage-risk reporting.
