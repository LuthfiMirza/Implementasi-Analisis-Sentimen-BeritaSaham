# OOS Walk-Forward Validation: kandidat regime-filter + hold 40d (BUMI & DEWA)

Scope: trading research only; graduation test for the candidate_experimental strategy, not a trading recommendation

Kriteria lolos (pre-registered, ditetapkan SEBELUM melihat hasil):
- P1: selected-pair OOS net expectancy > 0
- P2: selected-pair OOS net expectancy > naive buy-hold on same test episodes
- P3: selected-pair OOS excl-top-5% net expectancy > 0
- P4: bootstrap 95% CI lower bound of OOS mean net return > 0
- Overall PASS requires all four on the primary 70/30 split.

## DEWA

### primary_split_70_30 (train n=112, test n=48, test window 2021-02-05 -> 2026-03-03)
- Pair terpilih di TRAIN saja: tp=30.0 / sl={'type': 'fixed_pct', 'value': 3.0} (train net exp +1.0664%)
- Sama dengan kandidat asli tp30/sl3? YA
- OOS pair terpilih: net exp +3.2130% | excl-top5% +2.0831% | win rate 22.9% | CI95 [+0.0418%, +6.8493%]
- OOS kandidat beku tp30/sl3 (bias ke atas, dipilih pakai full sample): net exp +3.2130% | excl-top5% +2.0831% | CI95 [+0.0418%, +6.8493%]
- Naive buy-hold 40d di test episodes yang sama: +8.1358%
- P1_oos_net_expectancy_positive: PASS
- P2_beats_naive_buy_hold: FAIL
- P3_excl_top5pct_positive: PASS
- P4_bootstrap_ci_lower_positive: PASS
- **Verdict split ini: FAIL**

### sensitivity_split_60_40 (train n=96, test n=64, test window 2018-01-08 -> 2026-03-03)
- Pair terpilih di TRAIN saja: tp=30.0 / sl={'type': 'atr_multiple', 'value': 1.0} (train net exp +0.6706%)
- Sama dengan kandidat asli tp30/sl3? TIDAK
- OOS pair terpilih: net exp +0.7094% | excl-top5% -0.0607% | win rate 5.3% | CI95 [-0.8806%, +3.0860%]
- OOS kandidat beku tp30/sl3 (bias ke atas, dipilih pakai full sample): net exp +4.0379% | excl-top5% +2.8004% | CI95 [+1.1305%, +7.1364%]
- Naive buy-hold 40d di test episodes yang sama: +5.8668%
- P1_oos_net_expectancy_positive: PASS
- P2_beats_naive_buy_hold: FAIL
- P3_excl_top5pct_positive: FAIL
- P4_bootstrap_ci_lower_positive: FAIL
- **Verdict split ini: FAIL**

## BUMI

### primary_split_70_30 (train n=154, test n=67, test window 2017-10-11 -> 2026-02-26)
- Pair terpilih di TRAIN saja: tp=30.0 / sl={'type': 'fixed_pct', 'value': 7.5} (train net exp +2.4581%)
- Sama dengan kandidat asli tp30/sl3? TIDAK
- OOS pair terpilih: net exp +1.6196% | excl-top5% +0.3268% | win rate 29.9% | CI95 [-2.2924%, +5.6843%]
- OOS kandidat beku tp30/sl3 (bias ke atas, dipilih pakai full sample): net exp +0.1085% | excl-top5% -1.2552% | CI95 [-2.2398%, +2.7195%]
- Naive buy-hold 40d di test episodes yang sama: +5.1990%
- P1_oos_net_expectancy_positive: PASS
- P2_beats_naive_buy_hold: FAIL
- P3_excl_top5pct_positive: PASS
- P4_bootstrap_ci_lower_positive: FAIL
- **Verdict split ini: FAIL**

### sensitivity_split_60_40 (train n=132, test n=89, test window 2015-01-13 -> 2026-02-26)
- Pair terpilih di TRAIN saja: tp=30.0 / sl={'type': 'fixed_pct', 'value': 7.5} (train net exp +2.3761%)
- Sama dengan kandidat asli tp30/sl3? TIDAK
- OOS pair terpilih: net exp +1.9485% | excl-top5% +0.6660% | win rate 29.2% | CI95 [-1.3847%, +5.4908%]
- OOS kandidat beku tp30/sl3 (bias ke atas, dipilih pakai full sample): net exp +0.7266% | excl-top5% -0.6133% | CI95 [-1.5084%, +3.2421%]
- Naive buy-hold 40d di test episodes yang sama: +3.9861%
- P1_oos_net_expectancy_positive: PASS
- P2_beats_naive_buy_hold: FAIL
- P3_excl_top5pct_positive: PASS
- P4_bootstrap_ci_lower_positive: FAIL
- **Verdict split ini: FAIL**

