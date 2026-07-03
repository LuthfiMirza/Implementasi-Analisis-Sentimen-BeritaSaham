# Investigasi Read-Only — Distribusi TP/SL & Diagnostik Sample Size (BUMI & DEWA)

Sumber: artifact JSON yang sudah ada di `storage/app/trading_research/`. Tidak ada file yang diubah/di-generate. `git status --short storage/` = bersih.
Setiap angka utama disertai `file :: key`.

---

## BAGIAN 1 — Distribusi per-kandidat TP

Catatan granularitas: di `*_tp_optimizer_v1.json`, array `candidates` menyimpan metrik **all-events** (expectancy, hit_rate, downside_tail, sample_size) per `tp_pct`. CI expectancy (`confidence_intervals`), `profitable_fold_ratio` (`stability`), dan validasi walk-forward (`folds`) HANYA tersedia untuk kandidat terpilih/terbaik — **tidak per-kandidat**. Jadi gate CI & fold hanya bisa dinilai penuh untuk best_candidate.

### BUMI (`BUMI_tp_optimizer_v1.json`)
Diurutkan expectancy tertinggi (semua all-events, n=308):

| tp_pct | expectancy% | hit_rate | timeout_rate | downside_tail% |
|---|---|---|---|---|
| 30.0 | +1.266 | 0.166 | 0.834 | -10.93 |
| 25.0 | +1.121 | 0.231 | 0.769 | -10.93 |
| 20.0 | +0.704 | 0.276 | 0.724 | -10.49 |
| 15.0 | +0.237 | 0.357 | 0.643 | -10.45 |
| 12.5 | +0.138 | 0.399 | 0.601 | -9.27 |
| 7.5 | -0.000 | 0.581 | 0.419 | -6.57 |
| 10.0 | -0.125 | 0.477 | 0.523 | -9.06 |
| **5.0 (best_by_score)** | **-0.799** | 0.646 | 0.354 | -4.77 |

- `best_candidate_by_score :: tp_pct = 5.0`, `expectancy_pct = -0.799` → dipilih karena skor tertimbang hit_rate/days_to_hit, **bukan** expectancy.
- CI expectancy (best) `confidence_intervals.expectancy_pct`: lower **-2.123**, upper +0.307, width 2.43. → **lower < 0** (policy min 0.0) → GAGAL.
- `stability.profitable_fold_ratio = 0.25` (1/4) — policy min 0.5 → **GAGAL**. median_fold_exp -0.921, worst_fold -2.194.
- Folds (`folds[].validation_expectancy_pct`): fold_1 -0.771, fold_2 -2.194, fold_3 -1.072, fold_4 **+0.479**. Hanya 1 dari 4 positif.
- `selected = null`, `critical_warnings = []`.

Gate check best (tp=5): expectancy ❌ | CI-lower>0 ❌ | profitable_fold≥0.5 ❌ | effective_sample≥30 ✅ (308) | downside_tail≥-25 ✅ | ci_width≤20 ✅.
**Seberapa jauh:** expectancy -0.799 vs butuh >0 (gap ~0.8pp); profitable_fold 0.25 vs 0.5. Bukan kalah tipis di 1 gate — kalah di 3 gate ekonomi sekaligus. Kandidat expectancy-positif (tp 15–30) hanya positif lewat hit_rate rendah 0.17–0.36 + timeout 0.64–0.83 (bergantung menang besar yang jarang).

### DEWA (`DEWA_tp_optimizer_v1.json`)
Diurutkan expectancy tertinggi (all-events, n=227):

| tp_pct | expectancy% | hit_rate | timeout_rate | downside_tail% |
|---|---|---|---|---|
| 30.0 | +0.789 | 0.106 | 0.894 | -1.09 |
| 25.0 | +0.746 | 0.132 | 0.868 | -0.45 |
| 20.0 | +0.495 | 0.159 | 0.841 | 0.00 |
| 15.0 | +0.347 | 0.203 | 0.797 | 0.00 |
| 12.5 | +0.044 | 0.229 | 0.771 | 0.00 |
| 7.5 | -0.155 | 0.330 | 0.670 | 0.00 |
| 10.0 | -0.179 | 0.260 | 0.740 | 0.00 |
| **5.0 (best_by_score)** | **-0.263** | 0.388 | 0.612 | 0.00 |

- `best_candidate_by_score :: tp_pct = 5.0`, `expectancy_pct = -0.263`.
- CI expectancy (best) `confidence_intervals.expectancy_pct`: lower **-0.032**, upper +1.358, width 1.39. → lower tepat **sedikit di bawah 0** → GAGAL (nyaris).
  - ⚠️ Catatan konsistensi: pusat CI (~+0.66) tidak match expectancy all-events best (-0.263). Field ini top-level; pemetaan ke kandidat spesifik tidak dieksplisitkan di artifact — dilaporkan apa adanya, jangan over-interpretasi.
- `stability.profitable_fold_ratio = 0.5` (2/4) = **pas min 0.5** (lolos batas). median_fold_exp +0.068, worst_fold -0.687.
- Folds (`folds[].validation_expectancy_pct`): fold_1 -0.687, fold_2 -0.309, fold_3 +0.444, fold_4 **+3.232** (val_hit 0.867 — outlier ekstrem). → 2/4 positif, tapi sisi positif ditopang fold_4.
- `selected = null`, `critical_warnings = []`.

Gate check best (tp=5): expectancy ❌ (-0.263) | CI-lower>0 ❌ (-0.032, nyaris) | profitable_fold≥0.5 ✅ (0.5) | effective_sample≥30 ✅ (227) | downside_tail≥-25 ✅.
**Seberapa jauh:** lebih dekat dari BUMI — CI-lower hanya -0.032, profitable_fold pas 0.5 — TAPI positifnya digerakkan satu fold outlier (fold_4 +3.232).

`usability_policy` (identik kedua ticker): min_validation_expectancy 0.0 · min_validation_sample 10 · min_effective_sample 30 · min_profitable_fold_ratio 0.5 · max_downside_tail -25.0 · max_ci_width 20.0 · min_tradable_movement_rate 0.1.

---

## BAGIAN 2 — SL & joint TP-SL (`*_sl_optimizer_v1_1.json`)

> ⚠️ **KRITIS — `transaction_cost_model` = SEMUA NOL** (entry/exit fee, slippage, tax, min_fixed = 0.0) untuk kedua ticker. Karena itu `best_net_joint_pair` == `best_gross_joint_pair` (net exp = gross exp, identik). **Semua expectancy joint di bawah ini adalah GROSS/zero-cost.**

### Standalone SL (`standalone_candidates`, metrik = average_horizon_return_pct, gross)
- BUMI (n=308): fixed_pct 3%→+2.83, 5%→+2.56, 7.5%→+3.56, 10%→+3.39, 12.5%→+3.17, 15%→+2.81. cvar makin dalam saat SL longgar (-9.9 → -19.7). 12 kandidat.
- DEWA (n=227): 3%→+0.43, 5%→+0.04, 7.5%→+1.08, 10%→+1.17, 12.5%→+0.82, 15%→+1.00. cvar -8.2 → -19.3.

### Joint TP-SL matrix (`joint_tp_sl_matrix`, 96 pasangan tiap ticker, gross)
- **BUMI:** 85/96 pasangan expectancy POSITIF, range [-0.947, +1.720].
- **DEWA:** 96/96 pasangan expectancy POSITIF, range [+0.064, +0.790].
- `best_net_joint_pair` (== gross):
  - BUMI: expectancy **+0.792%**, episode_count 289, loss_rate 0.813, median_realized **-0.022** (negatif), payoff_ratio 20.3, profit_factor 4.40, premature_stop_rate 0.483, max_loss -14.29, selection_score **-0.087**.
  - DEWA: expectancy **+0.790%**, episode_count 122 (dari 227; 105 excluded), loss_rate 0.836, median_realized **-0.089** (negatif), payoff_ratio 30.3, profit_factor 3.27, premature_stop_rate 0.510, max_loss -8.60, selection_score **-0.111**.
- `selected = null` untuk keduanya (selection_score negatif → tak ada yang lolos), `critical_warnings = []`.

### Extreme-winner dependency (`extreme_winner_analysis`)
| metrik | BUMI | DEWA |
|---|---|---|
| return_skewness | 3.748 | 3.580 |
| median_return | -0.022 | -0.089 |
| top_1_contribution | 0.146 | 0.286 |
| top_5_contribution | 0.288 | 0.818 |
| top_10_pct_contribution | 0.792 | **1.440** |
| expectancy_excl_best_trade | 0.679 | 0.569 |
| expectancy_excl_top_5_pct | 0.428 | **0.065** |
| max_win / max_loss | +33.3 / -14.3 | +27.5 / -8.6 |
| **warning** | null | **"extreme_winner_dependency"** |

- BUMI: 79% profit dari top-10% trade; buang top-5% → expectancy turun ke +0.43 (masih positif gross). Skew tinggi, median negatif. Tidak diberi warning.
- DEWA: top-10% menyumbang **144%** profit (tanpa mereka → negatif); buang top-5% → expectancy runtuh ke **+0.065**. **Diberi warning `extreme_winner_dependency` eksplisit.** Median negatif.

---

## BAGIAN 3 — Diagnostik sample size

Angka mentah (`*_trade_episodes_v1.json` + `*_event_quality_v1.json`):

| metrik | key | BUMI | DEWA |
|---|---|---|---|
| raw BUY observations | episodes.observation_summary.raw_signal_observation_count | 6177 | 4554 |
| overlapping observations | observation_summary.overlapping_observation_count | 6176 | 4553 |
| connected-component cluster | observation_summary.connected_component_cluster_count | 1 | 1 |
| one_position_fixed_horizon | episode_summary.one_position_episode_count | 309 | 228 |
| complete_horizon episodes | episode_summary.complete_horizon_episode_count | 308 | 227 |
| independence_proxy (effective) | episode_summary.independence_proxy | 308 | 227 |
| effective_sample_size (TP opt) | tp_optimizer.effective_sample_size | 308 | 227 |
| median_episode_spacing (hari) | episode_summary.median_episode_spacing | 28.0 | 29.0 |
| median_holding_horizon (hari) | episode_summary.median_holding_horizon | 20.0 | 20.0 |
| horizon_days / fixed_spacing_days | episodes.config | 20 / 20 | 20 / 20 |

**Rasio raw : effective** — BUMI **6177 : 308** (≈20:1) · DEWA **4554 : 227** (≈20:1). (Bukan 6177:2 seperti contoh di brief — effective ratusan, bukan satuan.)

**Apakah horizon penyebab overlap?** Ya, langsung terbukti dari holding-day distribution (`quality.distributions.holding_days`):
- BUMI: **6157 dari 6177** observasi held tepat **20 hari** (99.7%); sisanya 1 tiap bucket 0–19.
- DEWA: **4534 dari 4554** held tepat **20 hari** (99.6%).
- Karena horizon fix 20 hari + sinyal BUY harian, tiap observasi tumpang-tindih dengan ±20 hari tetangganya → 6176/4553 overlapping, meng-collapse ke 308/227 episode non-overlap (spacing 20 hari).

**Data untuk menilai "kalau horizon lebih pendek / sampling lebih longgar":** (tanpa hitung ulang)
- median_episode_spacing (28–29 hari) sudah > horizon (20 hari) → 308/227 episode SUDAH non-overlapping.
- Batas atas kasar independen ≈ jumlah hari-BUY unik / spacing. Dengan 6177/4554 sinyal harian mentah, memperpendek horizon (mis. 5–10 hari) berpotensi menaikkan episode independen beberapa kali lipat — tapi ini penilaian arah untuk Anda; artifact tidak menyediakan hitungan skenario horizon-alternatif.
- Kunci: effective 308/227 **sudah 10×** di atas gate `min_effective_sample_size = 30`.

---

## BAGIAN 4 — Ringkasan keputusan (fakta saja)

| | BUMI | DEWA |
|---|---|---|
| best TP expectancy (all-events, best_by_score tp=5) | -0.799% | -0.263% |
| best TP expectancy tertinggi lintas kandidat | +1.266% (tp30, hit 0.17) | +0.789% (tp30, hit 0.11) |
| CI expectancy lower (best) | -2.123 | -0.032 |
| profitable_fold_ratio | 0.25 (1/4) | 0.50 (2/4) |
| best joint TP-SL expectancy (GROSS, zero-cost) | +0.792% | +0.790% |
| joint pairs positif | 85/96 | 96/96 |
| effective sample | 308 | 227 |
| eligible episodes untuk joint | 289 (19 excl) | 122 (105 excl) |
| extreme_winner warning | null (top10%=79%) | **YES** (top10%=144%) |
| selected | null | null |
| gate yang paling sering gagal | expectancy<0 + profitable_fold<0.5 + CI_lower<0 | expectancy<0 + CI_lower<0 (nyaris) |

### Baris pembeda (berdasar angka Bagian 1–3)

- **BUMI → [A]** — semua kandidat jauh dari profitable di banyak gate. Bukti: best_by_score exp -0.799; hanya 1/4 fold positif; profitable_fold 0.25; CI-lower -2.12; kandidat expectancy-positif hanya lewat hit_rate 0.17–0.36 + timeout ≤0.83. **Sample size BUKAN blocker** (effective 308 ≫ 30).

- **DEWA → [C]** — campuran. Bukti "dekat": CI-lower hanya -0.032, profitable_fold pas 0.5, joint gross +0.79. Bukti "rapuh": positifnya ditopang fold_4 (+3.232) & warning `extreme_winner_dependency` (top-10% = 144% profit, buang top-5% → +0.065), plus 105/227 episode ter-exclude di joint. **Sample size BUKAN blocker** (effective 227 ≫ 30).

- **Untuk kedua ticker: [B] TIDAK berlaku** — tidak ada kasus "nyaris lolos, blocker dominan = sample size". Effective sample (308 / 227) sudah 7–10× di atas gate 30; blocker dominan adalah **expectancy/edge**, dan seluruh "profit" bersifat GROSS zero-cost (transaction_cost_model = 0).

---
*File ini read-only report; tidak ada artifact produksi yang diubah.*
