# ADR-066 — Capital Context and Risk Policy

Status: Accepted

Sprint 13 introduces explicit capital context and capital risk policy contracts. Capital context must be supplied as normalized input and must not be inferred from database balances, trade journal records, or defaults. Capital policy must also be explicit; configuration may validate bounds but must not provide a default risk percentage.

Both contracts are reference-only and must set `approved_for_execution=false`. They support only `single_candidate_reference` scope and `fixed_fractional` policy in Sprint 13.
