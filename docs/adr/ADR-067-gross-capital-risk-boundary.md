# ADR-067 — Gross Capital Risk Boundary

Status: Accepted

Capital risk converts explicit capital context and explicit policy into a reference risk budget for one candidate. It depends on evaluated action-specific risk and uses `risk.action_specific_risk.metrics.gross_loss_per_unit` as the canonical loss source.

Capital risk does not model fees, slippage, taxes, portfolio exposure, or execution approval. Net capital risk and portfolio risk remain unavailable/not implemented.
