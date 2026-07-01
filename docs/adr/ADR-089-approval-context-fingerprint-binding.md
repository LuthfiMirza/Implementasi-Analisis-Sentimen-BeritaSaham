# ADR-089: Approval Context Fingerprint Binding

Date: 2026-07-02
Status: Accepted

## Context

Sprint 17 introduces portfolio approval and authorization contracts above portfolio risk evaluation. Portfolio risk passing is not approval, reference approval is not production approval, and production approval is not execution authorization.

## Decision

Use explicit portfolio-approval policy input and explicit reference authorization evidence. Authorization binds to portfolio ID, candidate ID, policy ID/version, approval scope, issuer, validity interval, and an approval-context fingerprint computed before authorization validation. Portfolio approval remains non-executable and never selects or promotes actions.

## Consequences

No default approval policy, no default authorization, no auto-approval, no cryptographic trust claim, no database/Trade Journal fallback, and no broker/order payload are introduced. Production approval and execution authorization remain not implemented.
