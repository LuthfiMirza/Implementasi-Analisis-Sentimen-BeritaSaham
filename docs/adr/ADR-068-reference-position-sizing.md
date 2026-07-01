# ADR-068 — Reference Position Sizing

Status: Accepted

Position sizing in Sprint 13 is gross reference arithmetic only. The raw reference units are `maximum_loss_amount / gross_loss_per_unit`, with optional floor to whole reference units. Entry-reference price may be used only for reference notional.

The result is not a recommendation, not an executable quantity, and does not apply board lots, liquidity, cash validation, broker rules, or portfolio constraints.
