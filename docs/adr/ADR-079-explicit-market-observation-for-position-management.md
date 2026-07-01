# ADR-079 — Explicit Market Observation for Position Management

Status: Accepted

Position monitoring requires explicit market observation input. The service must not call market APIs, use prediction output, dashboard cache, database state, or hidden current price.
