#!/usr/bin/env python3
"""
Backtest Komprehensif: Strategi GABUNGAN vs MOMENTUM di SEMUA Saham BEI
Periode: 1 Desember 2025 s/d 5 Oktober 2026
Database: sentimena_dashboard (MySQL)
"""
import pymysql
import pandas as pd
import numpy as np
import json
from collections import defaultdict

# 1. Connect to MySQL & load all prices >= 2025-01-01
conn = pymysql.connect(
    host='127.0.0.1',
    user='root',
    password='',
    database='sentimena_dashboard',
    port=3306
)

print("Memuat data harga seluruh saham dari database MySQL...")
query = """
SELECT s.code as ticker, s.company_name, sp.price_date, sp.open, sp.high, sp.low, sp.close, sp.volume
FROM stock_prices sp
JOIN stocks s ON s.id = sp.stock_id
WHERE sp.price_date >= '2025-01-01' AND sp.interval_type = '1d'
ORDER BY s.code, sp.price_date ASC
"""
df_all = pd.read_sql(query, conn)
conn.close()

print(f"Data termuat: {len(df_all):,} baris harga.")

# Group by ticker
stocks_data = {}
ticker_names = {}
for ticker, group in df_all.groupby('ticker'):
    g = group.sort_values('price_date').reset_index(drop=True)
    g['price_date'] = pd.to_datetime(g['price_date']).dt.date
    g['open'] = g['open'].astype(float)
    g['high'] = g['high'].astype(float)
    g['low'] = g['low'].astype(float)
    g['close'] = g['close'].astype(float)
    g['volume'] = g['volume'].astype(float)
    
    # Calculate indicators
    # 1. ret_2d
    g['ret_2d'] = g['close'].pct_change(2)
    
    # 2. dd_20d (drawdown from 20-day high)
    roll_high = g['high'].rolling(20, min_periods=5).max()
    g['dd_20d'] = (g['close'] / roll_high) - 1.0
    
    # 3. RSI14 Wilder
    delta = g['close'].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    g['rsi14'] = 100 - (100 / (1 + rs))
    
    stocks_data[ticker] = g
    ticker_names[ticker] = group.iloc[0]['company_name']

START_DATE = pd.Timestamp("2025-12-01").date()
FEE_RATE = 0.004       # 0.40% round-trip broker fee (0.15% buy + 0.25% sell)
CAPITAL_PER_TRADE = 10_000_000 # Rp 10 Juta per trade

def backtest_strategy(strategy_type='GABUNGAN'):
    all_trades = []
    per_stock_stats = {}
    
    for ticker, df in stocks_data.items():
        # filter window
        eval_indices = df[df['price_date'] >= START_DATE].index
        if len(eval_indices) < 15:
            continue
            
        trades = []
        in_position = False
        pos_exit_idx = -1
        
        for idx in eval_indices:
            if idx <= pos_exit_idx:
                continue # masih dalam posisi
                
            row = df.iloc[idx]
            trigger = False
            
            if strategy_type == 'GABUNGAN':
                # ret_2d <= -5% OR dd_20d <= -20%
                if (row['ret_2d'] <= -0.05) or (row['dd_20d'] <= -0.20):
                    trigger = True
            elif strategy_type == 'MOMENTUM':
                # rsi14 > 60.0
                if row['rsi14'] > 60.0:
                    trigger = True
                    
            if trigger:
                entry_idx = idx + 1
                if entry_idx >= len(df):
                    continue
                    
                entry_row = df.iloc[entry_idx]
                entry_p = float(entry_row['close'])
                entry_d = entry_row['price_date']
                
                if entry_p <= 0:
                    continue
                    
                # exit simulation (10 days max hold or TS 2%)
                end_idx = min(entry_idx + 10, len(df) - 1)
                peak_p = entry_p
                exit_p = float(df.iloc[end_idx]['close'])
                exit_d = df.iloc[end_idx]['price_date']
                exit_reason = 'time_10d'
                
                for k in range(entry_idx + 1, end_idx + 1):
                    k_row = df.iloc[k]
                    kh = float(k_row['high'])
                    kl = float(k_row['low'])
                    kc = float(k_row['close'])
                    
                    if kh > peak_p:
                        peak_p = kh
                        
                    # Trailing stop 2% jika harga mundur 2% dari puncak
                    ts_stop = peak_p * (1.0 - 0.02)
                    if kl <= ts_stop:
                        exit_p = ts_stop
                        exit_d = k_row['price_date']
                        exit_reason = 'ts_2pct'
                        end_idx = k
                        break
                        
                holding_days = (end_idx - entry_idx)
                pos_exit_idx = end_idx
                
                qty = CAPITAL_PER_TRADE / entry_p
                gross_pct = (exit_p / entry_p - 1.0) * 100
                net_pct = (exit_p / entry_p - 1.0 - FEE_RATE) * 100
                net_pnl_rp = ((exit_p - entry_p) - (entry_p * FEE_RATE)) * qty
                
                trade_info = {
                    'ticker': ticker,
                    'entry_date': entry_d,
                    'entry_price': entry_p,
                    'exit_date': exit_d,
                    'exit_price': exit_p,
                    'holding_days': holding_days,
                    'gross_pct': gross_pct,
                    'net_pct': net_pct,
                    'net_pnl_rp': net_pnl_rp,
                    'is_win': net_pnl_rp > 0,
                    'exit_reason': exit_reason
                }
                trades.append(trade_info)
                all_trades.append(trade_info)
                
        if trades:
            wins = sum(1 for t in trades if t['is_win'])
            total = len(trades)
            tot_pnl = sum(t['net_pnl_rp'] for t in trades)
            avg_pct = np.mean([t['net_pct'] for t in trades])
            avg_hold = np.mean([t['holding_days'] for t in trades])
            per_stock_stats[ticker] = {
                'ticker': ticker,
                'name': ticker_names.get(ticker, ''),
                'total_trades': total,
                'wins': wins,
                'losses': total - wins,
                'win_rate': (wins / total) * 100,
                'total_pnl': tot_pnl,
                'avg_pct': avg_pct,
                'avg_hold': avg_hold
            }
            
    return all_trades, per_stock_stats

print("Menjalankan simulasi Strategi GABUNGAN...")
gab_trades, gab_stock_stats = backtest_strategy('GABUNGAN')

print("Menjalankan simulasi Strategi MOMENTUM...")
mom_trades, mom_stock_stats = backtest_strategy('MOMENTUM')

# Aggregate overall
def get_overall(trades):
    tot = len(trades)
    wins = sum(1 for t in trades if t['is_win'])
    losses = tot - wins
    wr = (wins / tot * 100) if tot > 0 else 0
    tot_pnl = sum(t['net_pnl_rp'] for t in trades)
    avg_pct = np.mean([t['net_pct'] for t in trades]) if tot > 0 else 0
    avg_hold = np.mean([t['holding_days'] for t in trades]) if tot > 0 else 0
    ts_count = sum(1 for t in trades if t['exit_reason'] == 'ts_2pct')
    return {
        'total_trades': tot,
        'wins': wins,
        'losses': losses,
        'win_rate': wr,
        'total_pnl': tot_pnl,
        'avg_pct': avg_pct,
        'avg_hold': avg_hold,
        'ts_count': ts_count
    }

gab_overall = get_overall(gab_trades)
mom_overall = get_overall(mom_trades)

print("\n" + "=" * 95)
print("LAPORAN HASIL BACKTEST RESMI: GABUNGAN vs MOMENTUM (SEMUA SAHAM BEI)")
print("Periode: 1 Desember 2025 s/d 5 Oktober 2026 (Modal Rp 10 Juta per Trade)")
print("=" * 95)
print(f"{'Metrik Utama':<32s} | {'Strategi GABUNGAN':<28s} | {'Strategi MOMENTUM':<28s}")
print("-" * 95)
print(f"{'Total Saham Aktif Ditest':<32s} | {len(gab_stock_stats):<28d} | {len(mom_stock_stats):<28d}")
print(f"{'Total Trade Terekseskusi':<32s} | {gab_overall['total_trades']:<28d} | {mom_overall['total_trades']:<28d}")
print(f"{'Trade Menang (Win)':<32s} | {gab_overall['wins']:<28d} | {mom_overall['wins']:<28d}")
print(f"{'Trade Kalah (Loss)':<32s} | {gab_overall['losses']:<28d} | {mom_overall['losses']:<28d}")
print(f"{'Win Rate Keseluruhan':<32s} | {gab_overall['win_rate']:<27.1f}% | {mom_overall['win_rate']:<27.1f}%")
print(f"{'Rata-rata Return per Trade':<32s} | {gab_overall['avg_pct']:+27.2f}% | {mom_overall['avg_pct']:+27.2f}%")
print(f"{'Rata-rata Hari Tahan':<32s} | {gab_overall['avg_hold']:<25.1f} hari | {mom_overall['avg_hold']:<25.1f} hari")
print(f"{'Total Akumulasi Cuan Bersih':<32s} | Rp {gab_overall['total_pnl']:<25,.0f} | Rp {mom_overall['total_pnl']:<25,.0f}")
print("=" * 95)

# Top 10 Gabungan
print("\n🏆 TOP 10 SAHAM TERBAIK — STRATEGI GABUNGAN (Cuan Tertinggi):")
print(f"{'Ticker':<8s} | {'Nama Saham':<26s} | {'Trade':<6s} | {'Win Rate':<10s} | {'Avg %':<10s} | {'Total PnL (Rp)':<18s}")
print("-" * 95)
top_gab = sorted(gab_stock_stats.values(), key=lambda x: x['total_pnl'], reverse=True)[:10]
for s in top_gab:
    print(f"{s['ticker']:<8s} | {s['name'][:26]:<26s} | {s['total_trades']:<6d} | {s['win_rate']:8.1f}% | {s['avg_pct']:+8.2f}% | Rp {s['total_pnl']:14,.0f}")

# Top 10 Momentum
print("\n🚀 TOP 10 SAHAM TERBAIK — STRATEGI MOMENTUM (Cuan Tertinggi):")
print(f"{'Ticker':<8s} | {'Nama Saham':<26s} | {'Trade':<6s} | {'Win Rate':<10s} | {'Avg %':<10s} | {'Total PnL (Rp)':<18s}")
print("-" * 95)
top_mom = sorted(mom_stock_stats.values(), key=lambda x: x['total_pnl'], reverse=True)[:10]
for s in top_mom:
    print(f"{s['ticker']:<8s} | {s['name'][:26]:<26s} | {s['total_trades']:<6d} | {s['win_rate']:8.1f}% | {s['avg_pct']:+8.2f}% | Rp {s['total_pnl']:14,.0f}")

# Perbandingan Spesifik Saham-saham Populer
print("\n📊 PERBANDINGAN PADA SAHAM-SAHAM POPULER (BUMI, DEWA, BRPT, PTRO, ENRG, DSSA, ADRO, ANTM):")
print(f"{'Ticker':<8s} | {'--- GABUNGAN ---':<36s} | {'--- MOMENTUM ---':<36s}")
print(f"{'':<8s} | {'Trade':<6s} {'Win Rate':<10s} {'Total PnL':<18s} | {'Trade':<6s} {'Win Rate':<10s} {'Total PnL':<18s}")
print("-" * 85)
popular = ['BUMI', 'DEWA', 'BRPT', 'PTRO', 'ENRG', 'DSSA', 'ADRO', 'ANTM', 'TINS', 'ESSA', 'UNVR', 'BBCA', 'BBRI']
for p in popular:
    g_info = gab_stock_stats.get(p, {'total_trades': 0, 'win_rate': 0, 'total_pnl': 0})
    m_info = mom_stock_stats.get(p, {'total_trades': 0, 'win_rate': 0, 'total_pnl': 0})
    g_str = f"{g_info['total_trades']:<6d} {g_info['win_rate']:8.1f}% Rp {g_info['total_pnl']:13,.0f}" if g_info['total_trades'] > 0 else f"{'-':<6s} {'-':<10s} {'-':<18s}"
    m_str = f"{m_info['total_trades']:<6d} {m_info['win_rate']:8.1f}% Rp {m_info['total_pnl']:13,.0f}" if m_info['total_trades'] > 0 else f"{'-':<6s} {'-':<10s} {'-':<18s}"
    print(f"{p:<8s} | {g_str} | {m_str}")
print("=" * 85)
