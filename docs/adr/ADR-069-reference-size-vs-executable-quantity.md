# ADR-069 — Reference Size vs Executable Quantity

Status: Accepted

Reference units and whole-unit floors are contract arithmetic for analysis. Executable quantity requires separate execution planning with lot policy, cash availability, liquidity, fees/slippage, portfolio risk, broker constraints, and promotion approval.

Sprint 13 always keeps `executable_quantity=null`, selected candidate null, promoted action null, and final safety action WAIT/NO_TRADE.
