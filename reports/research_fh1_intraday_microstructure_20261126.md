# Laporan Riset Kuantitatif Fase FH-1: Evaluasi OOS Fitur *Intraday Microstructure* (`VWAP` & *Late-Session Volume*)

> **Tanggal Riset**: 26 November 2026  
> **Dataset**: `241` trade dengan bar 15-menit hari entry (`intraday_prices`, `2026-08-26` s/d `2026-11-24`), split Discovery vs Holdout Krisis.

## 1. Posisi Harga Penutupan vs Intraday VWAP (`close_vs_vwap_pct`)

| Bucket VWAP | N | WR (%) | Avg PnL (%) | PF | Disc WR | **Holdout WR** | **Holdout Avg** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Deep Below VWAP (<-1.5%) | 58 | 46.6% | +1.91% | **2.19** | 43.8% | **47.6%** | **+2.12%** |
| Below VWAP (-1.5%..0%) | 71 | 50.7% | +2.37% | **2.93** | 61.1% | **47.2%** | **+2.19%** |
| Above VWAP (0%..+1.5%) | 61 | 67.2% | +2.70% | **3.73** | 70.4% | **64.7%** | **+1.62%** |
| Strong Above VWAP (>+1.5%) | 51 | 60.8% | +2.35% | **2.93** | 54.5% | **62.5%** | **+2.65%** |

## 2. Rasio Volume Penutupan Sesi 2 (`14:30–16:00` / Total Harian)

| Bucket Late-Session Vol | N | WR (%) | Avg PnL (%) | PF | Disc WR | **Holdout WR** | **Holdout Avg** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Dry Late (<15%) | 31 | 29.0% | -0.70% | **0.71** | 66.7% | **25.0%** | **-1.36%** |
| Normal Late (15-30%) | 109 | 51.4% | +2.11% | **2.59** | 51.9% | **51.2%** | **+2.15%** |
| Strong Late (30-45%) | 79 | 69.6% | +3.44% | **5.16** | 63.3% | **73.5%** | **+3.62%** |
| Climax Late (>45%) | 22 | 68.2% | +3.77% | **5.93** | 66.7% | **70.0%** | **+5.03%** |