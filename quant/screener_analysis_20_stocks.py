#!/usr/bin/env python3
"""
Analisis Mendalam 20 Saham Stockbit Screener & Backtest Kuantitatif
Data Historis: 1 Desember 2025 s/d 21 September 2026
Modal Awal: Rp 10.000.000
"""

import os
import pandas as pd
import numpy as np

HIST_FILE = 'data/screener_20_stocks_historical.csv'
INFO_FILE = 'data/screener_20_stocks_info.csv'
OUT_REPORT = 'reports/screener_20_stocks_deep_dive.md'

os.makedirs('reports', exist_ok=True)

df_hist = pd.read_csv(HIST_FILE)
df_info = pd.read_csv(INFO_FILE)

df_hist['date'] = pd.to_datetime(df_hist['date'])
df_hist = df_hist.sort_values(['ticker', 'date']).reset_index(drop=True)

# Hitung indikator teknikal per ticker
dfs = []
for ticker, group in df_hist.groupby('ticker'):
    g = group.copy().sort_values('date').reset_index(drop=True)
    g['prev_close'] = g['Close'].shift(1)
    g['prev_vol'] = g['Volume'].shift(1)
    g['ret_1d'] = (g['Close'] - g['prev_close']) / g['prev_close'] * 100
    g['ma5'] = g['Close'].rolling(5).mean()
    g['ma10'] = g['Close'].rolling(10).mean()
    g['value_est'] = g['Close'] * g['Volume']
    g['vol_ratio'] = g['Volume'] / g['prev_vol'].replace(0, np.nan)
    g['is_bullish'] = g['Close'] > g['Open']
    
    # Kriteria Screener Stockbit:
    # 1. Volume > Prev Volume
    # 2. Bullish Candle (Close > Open)
    # 3. Kenaikan Hari Ini >= 3%
    # 4. Nilai Transaksi >= Rp 100 Juta
    # 5. Uji Resistance MA: Close >= MA5 atau Close >= MA10
    g['screener_match'] = (
        (g['vol_ratio'] > 1.0) &
        (g['is_bullish']) &
        (g['ret_1d'] >= 3.0) &
        (g['value_est'] >= 100_000_000) &
        ((g['Close'] >= g['ma5']) | (g['Close'] >= g['ma10']))
    )
    
    # Data forward H+1 (Next Day)
    g['next_open'] = g['Open'].shift(-1)
    g['next_high'] = g['High'].shift(-1)
    g['next_low'] = g['Low'].shift(-1)
    g['next_close'] = g['Close'].shift(-1)
    
    g['next_open_ret'] = (g['next_open'] - g['Close']) / g['Close'] * 100
    g['next_max_ret'] = (g['next_high'] - g['Close']) / g['Close'] * 100
    g['next_close_ret'] = (g['next_close'] - g['Close']) / g['Close'] * 100
    g['h3_close_ret'] = (g['Close'].shift(-3) - g['Close']) / g['Close'] * 100
    g['h5_close_ret'] = (g['Close'].shift(-5) - g['Close']) / g['Close'] * 100
    
    dfs.append(g)

df_all = pd.concat(dfs, ignore_index=True)

# Analisis Hari Ini (2026-09-21)
latest_date = df_all['date'].max()
today_df = df_all[df_all['date'] == latest_date].copy()
today_merged = today_df.merge(df_info, on='ticker', how='left')
today_merged = today_merged.sort_values('ret_1d', ascending=False)

# Simulasi Backtest Historis
signals = df_all[df_all['screener_match'] & (df_all['date'] < latest_date)].copy()
signals = signals.sort_values(['date', 'value_est'], ascending=[True, False]).reset_index(drop=True)

FEE = 0.004 # 0.4% round-trip broker & exchange fee

def run_simulation(name, exit_rule):
    capital = 10_000_000.0
    records = []
    
    for dt, day_signals in signals.groupby('date'):
        # Pilih saham dengan transaksi paling likuid per hari sinyal
        best = day_signals.iloc[0]
        buy_p = best['Close']
        n_open = best['next_open']
        n_high = best['next_high']
        n_low = best['next_low']
        n_close = best['next_close']
        
        if pd.isna(buy_p) or pd.isna(n_open) or pd.isna(n_high) or buy_p <= 0:
            continue
            
        sell_p = exit_rule(buy_p, n_open, n_high, n_low, n_close)
        net_ret = (sell_p / buy_p) * (1 - FEE) - 1.0
        capital *= (1 + net_ret)
        
        records.append({
            'date': dt.strftime('%Y-%m-%d'),
            'ticker': best['ticker'],
            'buy': buy_p,
            'sell': sell_p,
            'ret_pct': net_ret * 100,
            'capital': capital
        })
        
    res = pd.DataFrame(records)
    wr = (res['ret_pct'] > 0).mean() * 100
    tot_ret = (capital - 10_000_000.0) / 10_000_000.0 * 100
    return {
        'name': name,
        'final_capital': capital,
        'total_return': tot_ret,
        'win_rate': wr,
        'total_trades': len(res),
        'best_trade': res['ret_pct'].max(),
        'worst_trade': res['ret_pct'].min()
    }

sim1 = run_simulation('1. Beli Sore, Jual Sore H+1 (Naive EOD Hold)', lambda b, o, h, l, c: c)
sim2 = run_simulation('2. Beli Sore, Jual Open H+1 09:00 WIB (BSJP Murni)', lambda b, o, h, l, c: o)
sim3 = run_simulation('3. Scalp Pagi (TP +2.5%, SL -2.5%, exit Sore jika tidak kena)', 
                      lambda b, o, h, l, c: b * 1.025 if h >= b * 1.025 else (b * 0.975 if l <= b * 0.975 else c))
sim4 = run_simulation('4. Scalp Pagi (TP +3.5%, SL -3.0%, exit Sore jika tidak kena)', 
                      lambda b, o, h, l, c: b * 1.035 if h >= b * 1.035 else (b * 0.97 if l <= b * 0.97 else c))

print("Simulation completed:")
for s in [sim1, sim2, sim3, sim4]:
    print(f"{s['name']}: Rp {s['final_capital']:,.0f} ({s['total_return']:+.2f}%), WR: {s['win_rate']:.1f}%")
