# BUMI & DEWA v3 Trading Experiment: Regime-Filtered Entry & Longer Hold

Scope: prediction/trading research only; no strategy, P&L, or trading recommendation
Robustness rule: pair must stay net-positive after excluding the top-5% winning episodes (excl_top5pct), same rule as BUMI_DEWA_net_cost_verdict.md
Sentiment-conditioned entry: SKIPPED: news_sentiment is non-zero for 1/308 BUMI episodes and 0/227 DEWA episodes at entry dates (~0% usable coverage); not a testable filter with current data.

## BUMI

| variant | episodes | pairs net-pos @ MID | pairs robust (excl top5%) | best full net exp % | naive buy-hold same horizon % | beats naive? | verdict |
|---|---|---|---|---|---|---|---|
| baseline_all_episodes | 308 | 53/96 | 0/96 | +0.9197 | +2.4735 | no | NET_POSITIVE_BUT_FAT_TAIL_ONLY |
| regime_filtered_bullish_only | 221 | 41/96 | 0/96 | +1.0247 | +3.0357 | no | NET_POSITIVE_BUT_FAT_TAIL_ONLY |
| longer_hold_40d | 308 | 55/96 | 1/96 | +2.1320 | +6.1219 | no | ROBUST_BUT_DOMINATED_BY_NAIVE_HOLD |
| longer_hold_60d | 308 | 61/96 | 3/96 | +2.8144 | +10.5934 | no | ROBUST_BUT_DOMINATED_BY_NAIVE_HOLD |
| regime_filtered_plus_longer_hold_40d | 221 | 38/96 | 1/96 | +2.2039 | +6.9602 | no | ROBUST_BUT_DOMINATED_BY_NAIVE_HOLD |

## DEWA

| variant | episodes | pairs net-pos @ MID | pairs robust (excl top5%) | best full net exp % | naive buy-hold same horizon % | beats naive? | verdict |
|---|---|---|---|---|---|---|---|
| baseline_all_episodes | 227 | 0/96 | 0/96 | -0.0098 | +0.2593 | no | DEAD_no_net_positive_pair |
| regime_filtered_bullish_only | 160 | 7/96 | 0/96 | +0.4771 | -0.1148 | YES | NET_POSITIVE_BUT_FAT_TAIL_ONLY |
| longer_hold_40d | 227 | 48/96 | 0/96 | +1.1929 | +1.9497 | no | NET_POSITIVE_BUT_FAT_TAIL_ONLY |
| longer_hold_60d | 227 | 74/96 | 21/96 | +2.4412 | +3.7501 | no | ROBUST_BUT_DOMINATED_BY_NAIVE_HOLD |
| regime_filtered_plus_longer_hold_40d | 160 | 47/96 | 3/96 | +1.7103 | +0.6699 | YES | ALIVE_robust_edge_beats_naive_hold |

## Overall conclusion

**Critical check added after the first pass:** a TP/SL pair being net-positive (even robustly, excl-top-5%) is not enough -- it must also beat simply buying and holding for the same number of days with no TP/SL at all. BUMI and DEWA both have strong positive price drift over the sample period (naive buy-hold net expectancy grows with horizon: BUMI ~+2.5% at 20d up to ~+10.6% at 60d; DEWA ~+0.3% at 20d up to ~+3.8% at 60d), so a longer holding window mechanically captures more of that drift regardless of the TP/SL rule used. See the beats-naive-hold column above.

At least one variant/pair found a ROBUST net-of-cost edge that ALSO beats naive buy-and-hold over the same horizon. See table above for which ticker/variant/pair.

## Deep-dive on the one surviving candidate: DEWA regime_filtered_plus_longer_hold_40d, tp=30/sl=3

- 160 episodes (bullish-regime entries only, 40-day hold).
- net_expectancy_full = +1.71%, net_expectancy_excl_top5pct = **+0.26%** -- still positive, but drops ~85% once
  the top 5% winners (8 episodes) are removed. This passes the ">0 after excl-top5%" bar, but only barely; it
  is fragile, not a strong edge.
- Beats naive buy-hold on the same 160 filtered episodes (+1.71% vs +0.67%), and (unusually for this batch)
  the naive baseline itself is weak here, so the TP/SL rule is doing real work rather than just riding drift.
- Caveat that matters most: this candidate was found by scanning 96 TP/SL pairs x 5 entry/hold variants x 2
  tickers = 960 hypotheses tested against one full, non-split sample. Finding one pair that "just barely"
  clears a robustness bar is close to what random search would produce by chance at this scale. No
  out-of-sample / walk-forward split was run for this candidate (unlike the project's official sl_optimizer
  artifacts, which do use nested walk-forward folds).

**Verdict: keep as `candidate_experimental` only -- do not promote.** Before this could be taken seriously it
would need: (1) a genuine walk-forward split (train regime/pair selection on one period, test net-of-cost on a
later, untouched period), (2) re-confirmation that DEWA's bullish-regime filter and 40d hold still produce
positive expectancy on that held-out period, (3) bootstrap CI on the excl-top5% number specifically, since
+0.26% could easily be indistinguishable from zero. This mirrors exactly why the project's own Phase B closed
its baseline-v2 candidate as "experimental, not promoted" rather than declaring victory on a single full-sample
pass.

