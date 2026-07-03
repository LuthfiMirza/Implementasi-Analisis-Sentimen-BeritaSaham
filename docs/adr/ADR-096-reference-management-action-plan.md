# ADR-096: Reference Management Action Plan

Status: Accepted

A management action plan materializes a proposed reference action and quantity only after an explicit action-policy evaluation matches. It is non-executable, contains no order semantics, and cannot mutate positions.

Supported quantity modes are `full_position`, `explicit_units`, and `explicit_fraction`. The canonical price basis is the current reference price from position state.
