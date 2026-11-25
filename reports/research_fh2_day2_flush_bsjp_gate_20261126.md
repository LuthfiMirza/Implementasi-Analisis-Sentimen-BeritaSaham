# Laporan Riset Kuantitatif Fase FH-2: `DAY2_FLUSH_CATCHER` (Skenario B) & *Regime-Gated BSJP Momentum*

> **Tanggal Riset**: 26 November 2026  
> **Dataset**: `186,170` bar 15-menit (`intraday_prices`) & `40,650` baris resmi `idx_daily_summaries` (`idx_scrape`), termasuk biaya broker `0,40%` *round-trip*.

## 1. Backtest Intraday 15m: `DAY2_FLUSH_CATCHER` (Day-1 Dead Low → Day-2 Morning Flush Reversal)

| Split | N | WR (%) | Avg Net (%) | PF | Avg Intraday MFE (%) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| ALL | 236 | 46.2% | +0.07% | **1.05** | +2.78% |
| Discovery (Aug26-Oct14) | 40 | 60.0% | +0.57% | **1.60** | +3.14% |
| Holdout (Oct15-Nov25) | 196 | 43.4% | -0.03% | **0.98** | +2.71% |

## 2. Backtest *Regime-Gated BSJP Momentum* (Exit Pembukaan H+1, Fee 0,40%)

| Varian Filter BSJP | N | WR (%) | Avg Net (%) | PF | Disc PF | **Holdout PF** | **Holdout Avg** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `0_BSJP_Base (4-15%, Vol>=1.5x, Val>=5B)` | 701 | 47.4% | -0.47% | **0.66** | 0.57 | **1.18** | **+0.15%** |
| `1_BSJP_UpperWick<=1.5%` | 229 | 41.5% | -0.34% | **0.66** | 0.63 | **0.80** | **-0.17%** |
| `2_BSJP_Breadth>=40%` | 402 | 46.8% | +0.07% | **1.10** | 1.04 | **1.18** | **+0.19%** |
| `3_BSJP_Breadth>=40% + UW<=1.5%` | 158 | 42.4% | -0.02% | **0.97** | 1.11 | **0.81** | **-0.19%** |
| `4_BSJP_Breadth>=40% + UW<=1.5% + ForeignBuy` | 123 | 46.3% | +0.14% | **1.27** | 1.02 | **1.84** | **+0.57%** |