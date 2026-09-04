# Rencana Eksperimen

## Setup

- Periode awal: `2025-12-01`
- Data: `quant/drawdown_bounce_tracker/ptb_backtest_prices_5y.json`
- Exit eksplorasi: hold 10 hari bursa
- Biaya: 0.8% round-trip
- Episode: trigger per ticker dengan jarak <= 15 hari kalender digabung

## Metrik

- total PnL level episode
- win rate level episode
- average PnL episode
- median PnL episode
- jumlah trade dan episode

## Command

```bash
python3 quant/drawdown_bounce_tracker/backtest_strategy_compare_december.py
```
