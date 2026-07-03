# ADR-101: Management Approval Context Fingerprint

Status: Accepted

Management approval context fingerprint is deterministic SHA-256 over normalized approval inputs before authorization validation.

It binds decision timestamp, portfolio, position, candidate, risk/review status, action policy, action plan ID, proposed action/quantity, reference price identity, impact values, and approval policy identity. It excludes authorization result, approval result, final decision fingerprint, runtime current time, random values, and unordered inputs.
