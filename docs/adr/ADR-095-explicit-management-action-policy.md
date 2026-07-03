# ADR-095: Explicit Management Action Policy

Status: Accepted

Management action proposals must come from an explicit, versioned, position-bound, ticker-bound, candidate-bound policy. There is no default action policy and no direct condition-to-action mapping.

A stop breach does not imply `exit_position`, and a target reach does not imply `reduce_position`. Policy approval flags for selection, mutation, and execution must remain false in this contract foundation.
