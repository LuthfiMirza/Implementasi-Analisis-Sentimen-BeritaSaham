# ADR-071 — Explicit Market and Cash Constraints

Status: Accepted

Market constraints and execution cash context must be explicit normalized inputs. The system must not infer board lots, minimum units, tick sizes, cash balances, fees, slippage, or liquidity from defaults, database state, hidden APIs, or Trade Journal records.

Missing evidence results in unavailable or partial readiness rather than assumed sufficiency.
