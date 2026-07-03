# ADR-097: Management Portfolio Impact Simulation

Status: Accepted

Position and portfolio impact simulation is reference-only. Local impact uses current quantity, proposed reference quantity, remaining reference quantity, and current reference price.

Portfolio impact is computed only from explicit portfolio context, exposure aggregation, and matching portfolio position snapshot. Capital-at-risk impact requires an explicit reconciled capital-risk source. Realized PnL, proceeds, released cash, and execution costs remain null.
