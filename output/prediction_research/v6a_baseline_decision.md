# V6A Baseline Decision: 5D Fixed Threshold Directional Model

## Decision

V6A official baseline for the later V6B sentiment contribution study is:

- **Horizon:** 5 trading days
- **Label:** `v2_fixed_1_5pct` (`up` if `future_return_5d > 1.5%`, `down` if `< -1.5%`, otherwise `flat`)
- **Model:** `random_forest`
- **Primary metric:** macro F1
- **Secondary metric:** directional accuracy
- **Scope:** offline directional prediction research only; not a trading strategy, not a P&L backtest, and not a strategy promotion claim.

Final V6A baseline metrics:

| Metric | Random forest | Majority class baseline | Delta |
|---|---:|---:|---:|
| Macro F1 | 0.3673 | 0.1646 | +0.2027 |
| Directional accuracy | 0.4050 | 0.3282 | +0.0769 |

## Rationale

The 5D fixed-threshold candidate is selected because it is the clearest candidate that beats the trivial `majority_class` baseline in **both** fixed metrics while preserving continuity with the existing 5D prediction research dataset and feature workflow.

- **Why not 1D:** the 1D fixed-threshold candidate has the highest macro F1 in the sweep, but all 1D variants lose to `majority_class` on directional accuracy. The selected 1D row has directional accuracy `0.5359` versus majority `0.6567` because the 1D label distribution is flat-heavy (`61.21%` flat), so it is not defensible as the official baseline.
- **Why not 3D:** every 3D variant wins macro F1 but loses directional accuracy versus `majority_class`. The closest 3D row, `v2_fixed_1_5pct`, is only `0.4465` versus majority `0.4514`, so it remains a near-miss rather than a confirmed baseline.
- **Why not 10D:** `v6_atr_k_0.75` wins both metrics, but its directional-accuracy margin is only `0.3704` versus majority `0.3660` (`+0.0044`). That edge is too small to prefer over the 5D fixed-threshold candidate as the main baseline.
- **Why not ATR as baseline:** ATR label variants for `k=0.5` and `k=0.75` across 1D/3D/5D/10D were run and documented, but they do not consistently outperform the 5D fixed-threshold label. They remain useful audit evidence and may inform future risk-level or stop-loss research, but that would require separate governance because strategy/risk-rule work is not opened by V6A.

## Full Label x Horizon Sweep

Source artifact: `output/prediction_research/model_comparison_v6a.json`.

| Horizon | Label variant | Best model | Up | Flat | Down | Macro F1 | Majority macro F1 | Directional accuracy | Majority directional accuracy | Result vs majority |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1D | `v2_fixed_1_5pct` | `random_forest` | 19.83% | 61.21% | 18.96% | 0.4005 | 0.2637 | 0.5359 | 0.6567 | WIN macro F1 only |
| 1D | `v6_atr_k_0.5` | `random_forest` | 22.17% | 56.83% | 21.01% | 0.3646 | 0.2436 | 0.4141 | 0.5760 | WIN macro F1 only |
| 1D | `v6_atr_k_0.75` | `random_baseline` | 13.99% | 73.74% | 12.27% | 0.3346 | 0.2856 | 0.5891 | 0.7494 | WIN macro F1 only |
| 3D | `v2_fixed_1_5pct` | `random_forest` | 30.95% | 41.34% | 27.72% | 0.3917 | 0.2064 | 0.4465 | 0.4514 | WIN macro F1 only |
| 3D | `v6_atr_k_0.5` | `random_forest` | 33.10% | 37.03% | 29.87% | 0.3528 | 0.1844 | 0.3555 | 0.3827 | WIN macro F1 only |
| 3D | `v6_atr_k_0.75` | `random_forest` | 25.86% | 51.75% | 22.39% | 0.3454 | 0.2332 | 0.3633 | 0.5383 | WIN macro F1 only |
| 5D | `v2_fixed_1_5pct` | `random_forest` | 35.57% | 33.82% | 30.61% | 0.3673 | 0.1646 | 0.4050 | 0.3282 | WIN both |
| 5D | `v6_atr_k_0.5` | `random_forest` | 37.51% | 30.11% | 32.38% | 0.3509 | 0.1754 | 0.3538 | 0.3577 | WIN macro F1 only |
| 5D | `v6_atr_k_0.75` | `random_forest` | 31.02% | 42.96% | 26.02% | 0.3450 | 0.2044 | 0.3495 | 0.4425 | WIN macro F1 only |
| 10D | `v2_fixed_1_5pct` | `random_baseline` | 41.46% | 25.14% | 33.40% | 0.3267 | 0.1872 | 0.3420 | 0.3911 | WIN macro F1 only |
| 10D | `v6_atr_k_0.5` | `logistic_regression` | 43.03% | 22.21% | 34.76% | 0.3543 | 0.1947 | 0.3832 | 0.4134 | WIN macro F1 only |
| 10D | `v6_atr_k_0.75` | `logistic_regression` | 37.86% | 32.32% | 29.82% | 0.3585 | 0.1783 | 0.3704 | 0.3660 | WIN both |

## V6B Comparison Policy

V6B should compare sentiment-enhanced prediction against this V6A baseline using the same metric policy: macro F1 as the primary metric and directional accuracy as the secondary metric. Any V6B improvement should be reported against both the V6A random-forest baseline and the `majority_class` baseline, without converting the result into a trading/backtest claim.
