# ADR-073 — No Default Execution Assumptions

Status: Accepted

Sprint 14 forbids default execution assumptions. There is no default unit step, minimum order, available cash, fee, slippage, liquidity cap, broker policy, or portfolio-risk allowance.

All execution evidence must include provenance, timestamps, identity, and `approved_for_execution=false`.
