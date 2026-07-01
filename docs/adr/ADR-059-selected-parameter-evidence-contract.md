# ADR-059: Selected Parameter Evidence Contract

Status: Accepted

## Context
Action risk requires TP/SL values with provenance. Registry metadata currently proves availability but may not contain selected values.

## Decision
Action risk accepts a normalized `trading_selected_parameters_v1` evidence object. Real flow does not synthesize it from research-only artifacts or filesystem payloads.

## Alternatives
- Read artifact JSON directly: rejected because services must use normalized evidence only.
- Use filename/default TP/SL values: rejected as unsafe fallback.

## Consequences
Synthetic unit tests may provide decision-grade selected parameter evidence directly; real BUMI/DEWA action risk remains unavailable.

## Risks
A future Registry enhancement must surface selected values explicitly before production risk can evaluate.

## Validation Strategy
Validator rejects missing checksum, stale/quarantined sources, research-only sources, selected false, unsupported units, and identity mismatch.
