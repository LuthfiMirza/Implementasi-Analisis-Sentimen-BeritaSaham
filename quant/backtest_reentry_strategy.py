#!/usr/bin/env python3
"""
Backtest Komparasi: Strategi Baseline vs Trailing Stop Tanpa Re-Entry vs Trailing Stop DENGAN Re-Entry.
Menguji 428 trade historis riil di database Sentimena.
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path

# 1. Load 428 closed trades
with open('/tmp/closed_trades_427.json') as f:
    trades = json.load(f)

# 2. Load historical prices
prices = {}
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

FEE_RATE = 0.004  # 0.40% round-trip broker fee (0.15% buy + 0.25% sell)

def run_simulation(enable_reentry=False, reentry_type='breakout'):
    sim_pnls = []
    sim_wins = 0
    reentry_triggered_count = 0
    reentry_win_count = 0
    
    for t in trades:
        ticker = t['ticker']
        entry_p = float(t['entry_price'])
        entry_d = str(t['entry_date'])[:10]
        exit_d = str(t['exit_date'])[:10] if t['exit_date'] else None
        qty = float(t['quantity'] or (float(t['lot_size'] or 0) * 100))
        if qty == 0 and float(t['position_value'] or 0) > 0:
            qty = float(t['position_value']) / entry_p
        if qty == 0:
            qty = 10_000_000 / entry_p
            
        capital = qty * entry_p
        
        df = prices.get(ticker)
        if df is None:
            act_pnl = float(t['pnl_total'] or 0)
            sim_pnls.append(act_pnl)
            if act_pnl > 0: sim_wins += 1
            continue
            
        match_entry = df[df['date'] >= entry_d]
        if match_entry.empty:
            act_pnl = float(t['pnl_total'] or 0)
            sim_pnls.append(act_pnl)
            if act_pnl > 0: sim_wins += 1
            continue
            
        start_idx = match_entry.index[0]
        if exit_d:
            match_exit = df[df['date'] <= exit_d]
            end_idx = match_exit.index[-1] if not match_exit.empty else start_idx + 10
        else:
            end_idx = start_idx + 10
            
        end_idx = max(start_idx, min(end_idx, start_idx + 15, len(df) - 1))
        
        # --- PHASE 1: INITIAL TRADE ---
        peak_p = entry_p
        exit_p = float(t['exit_price'] or entry_p)
        exited_at_idx = end_idx
        exit_reason = 'time_end'
        is_ts_exit = False
        
        for idx in range(start_idx + 1, end_idx + 1):
            row = df.iloc[idx]
            h = float(row.get('high', row.get('close')))
            l = float(row.get('low', row.get('close')))
            c = float(row['close'])
            
            if h > peak_p:
                peak_p = h
                
            gain_from_entry = (peak_p - entry_p) / entry_p
            
            # Aturan Trailing Stop Dinamis:
            # 1. Cuan >= +5.0% -> Trailing Stop 2.0% dari Puncak
            if gain_from_entry >= 0.05:
                ts_level = peak_p * (1.0 - 0.02)
                if l <= ts_level:
                    exit_p = ts_level
                    exited_at_idx = idx
                    is_ts_exit = True
                    exit_reason = 'ts_profit_lock'
                    break
            # 2. Cuan >= +3.0% -> BEP (+0.4% cover fee)
            elif gain_from_entry >= 0.03:
                bep_level = entry_p * (1.0 + FEE_RATE)
                if l <= bep_level:
                    exit_p = bep_level
                    exited_at_idx = idx
                    is_ts_exit = True
                    exit_reason = 'bep_stop'
                    break
            # 3. Belum cuan 3% -> Hard Stop Loss 3%
            else:
                sl_level = entry_p * 0.97
                if l <= sl_level:
                    exit_p = sl_level
                    exited_at_idx = idx
                    exit_reason = 'hard_sl'
                    break
                    
            if idx == end_idx:
                exit_p = c
                exited_at_idx = idx
                
        # PnL Trade 1
        pnl_1 = ((exit_p - entry_p) - (entry_p * FEE_RATE)) * qty
        
        # --- PHASE 2: RE-ENTRY LOGIC (JIKA DIAKTIFKAN) ---
        pnl_2 = 0.0
        reentered = False
        
        if enable_reentry and is_ts_exit and exited_at_idx < end_idx:
            # Cari peluang re-entry di sisa hari trading (dari exited_at_idx + 1 s/d end_idx)
            reentry_p = 0.0
            reentry_idx = -1
            
            for r_idx in range(exited_at_idx + 1, end_idx + 1):
                r_row = df.iloc[r_idx]
                rh = float(r_row.get('high', r_row.get('close')))
                rl = float(r_row.get('low', r_row.get('close')))
                rc = float(r_row['close'])
                ro = float(r_row.get('open', rc))
                
                if reentry_type == 'breakout':
                    # Model B: Breakout di atas puncak lama (Peak_1)
                    if rh > peak_p * 1.005:
                        reentry_p = peak_p * 1.005
                        reentry_idx = r_idx
                        reentered = True
                        break
                elif reentry_type == 'pullback':
                    # Model A: Pullback dekat entry_p (+/- 1.5%) lalu memantul hijau (Close > Open)
                    if rl <= entry_p * 1.015 and rc > ro:
                        reentry_p = rc
                        reentry_idx = r_idx
                        reentered = True
                        break
                        
            if reentered and reentry_idx != -1:
                reentry_triggered_count += 1
                r_qty = capital / reentry_p  # reinvest modal awal
                r_peak = reentry_p
                r_exit_p = float(df.iloc[end_idx]['close'])
                
                # Simulasi Trade 2 dari reentry_idx + 1 s/d end_idx
                for r2_idx in range(reentry_idx + 1, end_idx + 1):
                    r2_row = df.iloc[r2_idx]
                    r2_h = float(r2_row.get('high', r2_row.get('close')))
                    r2_l = float(r2_row.get('low', r2_row.get('close')))
                    r2_c = float(r2_row['close'])
                    
                    if r2_h > r_peak:
                        r_peak = r2_h
                        
                    r_gain = (r_peak - reentry_p) / reentry_p
                    
                    # Trailing Stop 2% untuk Re-Entry
                    if r_gain >= 0.03:
                        r_ts = r_peak * 0.98
                        if r2_l <= r_ts:
                            r_exit_p = r_ts
                            break
                    else:
                        # Cut loss re-entry 2.5%
                        r_sl = reentry_p * 0.975
                        if r2_l <= r_sl:
                            r_exit_p = r_sl
                            break
                            
                    if r2_idx == end_idx:
                        r_exit_p = r2_c
                        
                pnl_2 = ((r_exit_p - reentry_p) - (reentry_p * FEE_RATE)) * r_qty
                if pnl_2 > 0:
                    reentry_win_count += 1
                    
        total_trade_pnl = pnl_1 + pnl_2
        sim_pnls.append(total_trade_pnl)
        if total_trade_pnl > 0:
            sim_wins += 1
            
    total_pnl = sum(sim_pnls)
    win_rate = (sim_wins / len(trades)) * 100
    return {
        'total_pnl': total_pnl,
        'win_rate': win_rate,
        'sim_wins': sim_wins,
        'sim_losses': len(trades) - sim_wins,
        'reentry_triggered': reentry_triggered_count,
        'reentry_wins': reentry_win_count,
        'reentry_wr': (reentry_win_count / reentry_triggered_count * 100) if reentry_triggered_count > 0 else 0
    }

actual_pnl_total = sum(float(t['pnl_total'] or 0) for t in trades)
actual_wins = sum(1 for t in trades if float(t['pnl_total'] or 0) > 0)
actual_wr = actual_wins / len(trades) * 100

print('=' * 95)
print('HASIL BACKTEST LENGKAP: BASELINE vs TRAILING STOP vs DENGAN RE-ENTRY (428 TRADE)')
print('=' * 95)

# 1. Baseline
print(f'1. STRATEGI BASELINE AKTUAL (Status Quo Saat Ini):')
print(f'   • Win Rate         : {actual_wr:.1f}% ({actual_wins} Win / {len(trades)-actual_wins} Loss)')
print(f'   • Total PnL Bersih : Rp {actual_pnl_total:,.0f}')
print('-' * 95)

# 2. Trailing Stop Kaku (Tanpa Re-Entry)
res_no_reentry = run_simulation(enable_reentry=False)
diff_no_re = res_no_reentry['total_pnl'] - actual_pnl_total
print(f"2. TRAILING STOP BIASA (Tanpa Re-Entry / Sekali Keluar Tidak Masuk Lagi):")
print(f"   • Win Rate         : {res_no_reentry['win_rate']:.1f}% ({res_no_reentry['sim_wins']} Win / {res_no_reentry['sim_losses']} Loss)")
print(f"   • Total PnL Bersih : Rp {res_no_reentry['total_pnl']:,.0f}")
print(f"   • Selisih PnL      : Rp {diff_no_re:+,.0f} (TERPANGKAS BESAR)")
print('-' * 95)

# 3. Trailing Stop + Breakout High Re-Entry (Model B)
res_bo = run_simulation(enable_reentry=True, reentry_type='breakout')
diff_bo_nore = res_bo['total_pnl'] - res_no_reentry['total_pnl']
diff_bo_base = res_bo['total_pnl'] - actual_pnl_total
print(f"3. TRAILING STOP + BREAKOUT HIGH RE-ENTRY (Masuk Lagi Jika Tembus Puncak Baru):")
print(f"   • Re-Entry Terpicu : {res_bo['reentry_triggered']} kali (Win Rate Re-Entry: {res_bo['reentry_wr']:.1f}%)")
print(f"   • Win Rate Total   : {res_bo['win_rate']:.1f}% ({res_bo['sim_wins']} Win / {res_bo['sim_losses']} Loss)")
print(f"   • Total PnL Bersih : Rp {res_bo['total_pnl']:,.0f}")
print(f"   • Selisih vs No-RE : Rp {diff_bo_nore:+,.0f} (RE-ENTRY MENYELAMATKAN CUAN!)")
print(f"   • Selisih vs Base  : Rp {diff_bo_base:+,.0f}")
print('-' * 95)

# 4. Trailing Stop + Pullback Retest Re-Entry (Model A)
res_pb = run_simulation(enable_reentry=True, reentry_type='pullback')
diff_pb_nore = res_pb['total_pnl'] - res_no_reentry['total_pnl']
diff_pb_base = res_pb['total_pnl'] - actual_pnl_total
print(f"4. TRAILING STOP + PULLBACK RETEST RE-ENTRY (Masuk Lagi di Support Pas Rebound Hijau):")
print(f"   • Re-Entry Terpicu : {res_pb['reentry_triggered']} kali (Win Rate Re-Entry: {res_pb['reentry_wr']:.1f}%)")
print(f"   • Win Rate Total   : {res_pb['win_rate']:.1f}% ({res_pb['sim_wins']} Win / {res_pb['sim_losses']} Loss)")
print(f"   • Total PnL Bersih : Rp {res_pb['total_pnl']:,.0f}")
print(f"   • Selisih vs No-RE : Rp {diff_pb_nore:+,.0f}")
print(f"   • Selisih vs Base  : Rp {diff_pb_base:+,.0f}")
print('=' * 95)
