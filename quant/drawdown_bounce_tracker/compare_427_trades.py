import json
import pandas as pd
import numpy as np
from pathlib import Path

# Load closed trades
with open('/tmp/closed_trades_427.json') as f:
    trades = json.load(f)

prices = {}

# 1. Load from data/stocks/*.csv
for csv_file in Path('data/stocks').glob('*.csv'):
    ticker = csv_file.stem
    try:
        df = pd.read_csv(csv_file)
        cols = {c: c.lower() for c in df.columns}
        df = df.rename(columns=cols)
        if 'date' in df.columns and 'close' in df.columns and 'high' in df.columns and 'low' in df.columns:
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            df = df.sort_values('date').reset_index(drop=True)
            prices[ticker] = df
    except Exception:
        pass

# 2. Load from ptb_backtest_prices_5y.json
with open('quant/drawdown_bounce_tracker/ptb_backtest_prices_5y.json') as f:
    ptb = json.load(f)
    for ticker, rows in ptb.items():
        if ticker not in prices:
            df = pd.DataFrame(rows)
            cols = {c: c.lower() for c in df.columns}
            df = df.rename(columns=cols)
            if 'date' in df.columns and 'close' in df.columns:
                df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
                df = df.sort_values('date').reset_index(drop=True)
                prices[ticker] = df

COST = 0.008

actual_pnl_total = sum(float(t['pnl_total'] or 0) for t in trades)
actual_wins = sum(1 for t in trades if float(t['pnl_total'] or 0) > 0)
actual_losses = len(trades) - actual_wins

sim_results = []
sim_exits = []
sim_pcts = []
strat_breakdown = {}

for t in trades:
    ticker = t['ticker']
    strat = t['strategy_label'] or 'unknown'
    entry_p = float(t['entry_price'])
    entry_d = str(t['entry_date'])[:10]
    exit_d = str(t['exit_date'])[:10] if t['exit_date'] else None
    qty = float(t['quantity'] or (float(t['lot_size'] or 0) * 100))
    if qty == 0 and float(t['position_value'] or 0) > 0:
        qty = float(t['position_value']) / entry_p
    if qty == 0:
        qty = 10_000_000 / entry_p
        
    df = prices.get(ticker)
    if df is None:
        act_pnl = float(t['pnl_total'] or 0)
        sim_results.append(act_pnl)
        sim_exits.append('no_data_fallback')
        continue
        
    match_entry = df[df['date'] >= entry_d]
    if match_entry.empty:
        act_pnl = float(t['pnl_total'] or 0)
        sim_results.append(act_pnl)
        sim_exits.append('no_data_fallback')
        continue
        
    start_idx = match_entry.index[0]
    if exit_d:
        match_exit = df[df['date'] <= exit_d]
        end_idx = match_exit.index[-1] if not match_exit.empty else start_idx + 10
    else:
        end_idx = start_idx + 10
        
    end_idx = max(start_idx, min(end_idx, start_idx + 15, len(df) - 1))
    
    peak_p = entry_p
    exit_p = float(t['exit_price'] or entry_p)
    exit_reason = 'actual_or_hold'
    
    # Day by day
    for idx in range(start_idx + 1, end_idx + 1):
        row = df.iloc[idx]
        h = float(row.get('high', row.get('close')))
        l = float(row.get('low', row.get('close')))
        c = float(row['close'])
        
        if h > peak_p:
            peak_p = h
            
        gain_from_entry = (peak_p - entry_p) / entry_p
        
        # Tier 3: Cuan >= 7% -> TS 1.0%
        if gain_from_entry >= 0.07:
            ts_stop = peak_p * (1.0 - 0.010)
            if l <= ts_stop:
                exit_p = min(ts_stop, h)
                exit_reason = 'Tier_3_TS_1%_at_7%+'
                break
        # Tier 2: Cuan >= 5% -> TS 1.5%
        elif gain_from_entry >= 0.05:
            ts_stop = peak_p * (1.0 - 0.015)
            if l <= ts_stop:
                exit_p = min(ts_stop, h)
                exit_reason = 'Tier_2_TS_1.5%_at_5%+'
                break
        # Tier 1: Cuan >= 2.5% -> BEP (+0.8% cover fee)
        elif gain_from_entry >= 0.025:
            bep_stop = entry_p * (1.0 + 0.008)
            if l <= bep_stop:
                exit_p = bep_stop
                exit_reason = 'Tier_1_BEP_Cover_Fee'
                break
        # Belum pernah Tier 1: Hard SL 3%
        else:
            sl_price = entry_p * 0.97
            if l <= sl_price:
                exit_p = sl_price
                exit_reason = 'Hard_SL_3%'
                break
                
        if idx == end_idx:
            exit_p = c
            exit_reason = 'Time_End'
            
    net_pnl_per_share = (exit_p - entry_p) - (entry_p * COST)
    trade_pnl = net_pnl_per_share * qty
    net_pct = (exit_p / entry_p - 1.0 - COST) * 100
    
    sim_results.append(trade_pnl)
    sim_exits.append(exit_reason)
    sim_pcts.append(net_pct)
    
    if strat not in strat_breakdown:
        strat_breakdown[strat] = {'act_pnl': 0, 'sim_pnl': 0, 'count': 0, 'act_win': 0, 'sim_win': 0}
    strat_breakdown[strat]['count'] += 1
    strat_breakdown[strat]['act_pnl'] += float(t['pnl_total'] or 0)
    strat_breakdown[strat]['sim_pnl'] += trade_pnl
    if float(t['pnl_total'] or 0) > 0:
        strat_breakdown[strat]['act_win'] += 1
    if trade_pnl > 0:
        strat_breakdown[strat]['sim_win'] += 1

sim_pnl_total = sum(sim_results)
sim_wins = sum(1 for p in sim_results if p > 0)
sim_losses = len(sim_results) - sim_wins

print('=' * 85)
print('SIMULASI KINERJA 427 TRADE DENGAN ATURAN "MULTI-TIER PROFIT LOCK"')
print('=' * 85)
print(f'Parameter:')
print(f'  • Tier 1: Cuan >= +2.5%  -> Geser SL ke Break-Even (+0.8% cover fee broker)')
print(f'  • Tier 2: Cuan >= +5.0%  -> Kunci Trailing Stop 1.5% dari Puncak')
print(f'  • Tier 3: Cuan >= +7.0%  -> Kunci Trailing Stop KETAT 1.0% dari Puncak')
print(f'  • Initial Protection     -> Hard Stop Loss 3.0% (sebelum menyentuh +2.5%)')
print('-' * 85)
print(f'{"Metrik Utama":<28s} | {"Baseline Aktual (Saat Ini)":<25s} | {"Dengan Multi-Tier Lock":<25s}')
print('-' * 85)
print(f'{"Total Trade Selesai":<28s} | {len(trades):<25d} | {len(sim_results):<25d}')
print(f'{"Trade Menang (Win)":<28s} | {actual_wins:<25d} | {sim_wins:<25d}')
print(f'{"Trade Kalah (Loss)":<28s} | {actual_losses:<25d} | {sim_losses:<25d}')
print(f'{"Win Rate":<28s} | {actual_wins/len(trades)*100:<24.1f}% | {sim_wins/len(sim_results)*100:<24.1f}%')
print(f'{"Total PnL Bersih":<28s} | Rp {actual_pnl_total:<22,.0f} | Rp {sim_pnl_total:<22,.0f}')
print(f'{"Estimasi Nilai Akun (Rp)":<28s} | Rp {251507378:<22,.0f} | Rp {251507378 + (sim_pnl_total - actual_pnl_total):<22,.0f}')
print(f'{"Selisih PnL Nominal":<28s} | {"-":<25s} | Rp {sim_pnl_total - actual_pnl_total:+22,.0f}')
print('-' * 85)

print('\nBREAKDOWN PER STRATEGI:')
print(f'{"Strategi":<22s} | {"N":<4s} | {"WR Aktual":<10s} | {"WR Simulasi":<11s} | {"PnL Aktual":<18s} | {"PnL Multi-Tier":<18s} | {"Selisih":<18s}')
print('-' * 115)
for s, d in strat_breakdown.items():
    diff = d['sim_pnl'] - d['act_pnl']
    wr_act = d['act_win'] / d['count'] * 100
    wr_sim = d['sim_win'] / d['count'] * 100
    print(f'{s:<22s} | {d["count"]:<4d} | {wr_act:9.1f}% | {wr_sim:10.1f}% | Rp {d["act_pnl"]:15,.0f} | Rp {d["sim_pnl"]:15,.0f} | Rp {diff:+15,.0f}')

print('\nBREAKDOWN TIPE EKSEKUSI EXIT:')
exit_s = pd.Series(sim_exits).value_counts()
for r, c in exit_s.items():
    print(f'  • {r:<25s}: {c:3d} trade ({c/len(trades)*100:.1f}%)')
