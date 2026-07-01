# ADR-023: Re-entry Family Quality

Status: Accepted

## Context
Sprint 5 stored ATR candidates but did not expose ATR family coverage or usability.

## Decision
Re-entry artifacts report family-level quality for percentage pullback, ATR pullback, and reclaim trigger. Percentage and reclaim families are implemented; ATR pullback is marked implemented in contract but currently not usable until trigger-time ATR evaluation is completed.

## Alternatives Considered
- Hide ATR candidates: rejected because search-space provenance should remain visible.
- Treat ATR as evaluated without coverage: rejected as misleading.

## Consequences
Consumers can distinguish implemented, deferred, covered, and usable candidate families.

## Risks
ATR family needs a follow-up hardening sprint for trigger-time ATR calculation.

## Validation Strategy
Tests verify percentage coverage independent from ATR coverage and family-level usability flags.

## Sprint 5.2 Update
ATR family status must be one of `evaluated`, `implemented_but_unavailable`, `deferred`, or `unsupported`. When coverage is zero, evaluated candidates must be empty, best candidate must remain null, and family research usability must be false.
