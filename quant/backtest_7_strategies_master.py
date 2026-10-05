#!/usr/bin/env python3
"""
MASTER BACKTEST: 7 STRATEGI SENTIMENA
Periode: 1 Desember 2025 s/d 5 Oktober 2026
Menggunakan database lengkap MySQL sentimena_dashboard (45.145 baris harga)
Standarisasi: Modal per trade Rp 10.000.000 | Biaya broker 0.40% round-trip (0.15% beli, 0.25% jual)
"""
import pymysql
import pandas as pd
import numpy as np
import json
from collections import defaultdict

# 1. Load data from MySQL
conn = pymysql.connect(host='127.0.0.1', user='root', password='', database='sentimena_dashboard', port=3306)
print("Memuat seluruh data historis dari database MySQL...")
query = """
SELECT s.code as ticker, s.company_name, sp.price_date, sp.open, sp.high, sp.low, sp.close, sp.volume
FROM stock_prices sp
JOIN stocks s ON s.id = sp.stock_id
WHERE sp.price_date >= '2025-01-01' AND sp.interval_type = '1d'
ORDER BY s.code, sp.price_date ASC
"""
df_all = pd.read_sql(query, conn)
conn.close()

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
    g['value'] = g['close'] * g['volume']
    
    # Indikator
    # 1. Returns
    g['prev_close'] = g['close'].shift(1)
    g['prev_volume'] = g['volume'].shift(1)
    g['ret_1d'] = (g['close'] - g['prev_close']) / g['prev_close']
    g['ret_2d'] = g['close'].pct_change(2)
    g['ret_5d'] = g['close'].pct_change(5)
    
    # 2. Moving Averages
    g['ma5'] = g['close'].rolling(5).mean()
    g['ma20'] = g['close'].rolling(20).mean()
    
    # 3. Bollinger Bands 20
    g['std20'] = g['close'].rolling(20).std()
    g['bb_upper'] = g['ma20'] + 2 * g['std20']
    g['bb_lower'] = g['ma20'] - 2 * g['std20']
    g['bb_pct_b'] = (g['close'] - g['bb_lower']) / (g['bb_upper'] - g['bb_lower']).replace(0, np.nan)
    
    # 4. Drawdown 20d
    roll_high = g['high'].rolling(20, min_periods=5).max()
    g['dd_20d'] = (g['close'] / roll_high) - 1.0
    
    # 5. RSI 14 Wilder
    delta = g['close'].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    g['rsi14'] = 100 - (100 / (1 + rs))
    
    # 6. Stochastic (14, 3)
    low14 = g['low'].rolling(14).min()
    high14 = g['high'].rolling(14).max()
    g['stoch_k'] = 100 * (g['close'] - low14) / (high14 - low14).replace(0, np.nan)
    g['stoch_d'] = g['stoch_k'].rolling(3).mean()
    
    stocks_data[ticker] = g
    ticker_names[ticker] = group.iloc[0]['company_name']

START_DATE = pd.Timestamp("2025-12-01").date()
FEE_RATE = 0.004           # 0.40% round trip
CAPITAL = 10_000_000.0     # Rp 10 Juta modal awal per strategi

# --- SIMULATOR STRATEGI ---

# 1. GABUNGAN
def test_gabungan():
    trades = []
    for ticker, df in stocks_data.items():
        eval_idx = df[df['price_date'] >= START_DATE].index
        if len(eval_idx) < 15: continue
        pos_exit = -1
        for idx in eval_idx:
            if idx <= pos_exit: continue
            row = df.iloc[idx]
            if (row['ret_2d'] <= -0.05) or (row['dd_20d'] <= -0.20):
                entry_idx = idx + 1
                if entry_idx >= len(df): continue
                entry_row = df.iloc[entry_idx]
                entry_p = float(entry_row['close'])
                if entry_p <= 0: continue
                end_idx = min(entry_idx + 10, len(df) - 1)
                peak_p = entry_p
                exit_p = float(df.iloc[end_idx]['close'])
                for k in range(entry_idx + 1, end_idx + 1):
                    kh = float(df.iloc[k]['high'])
                    kl = float(df.iloc[k]['low'])
                    if kh > peak_p: peak_p = kh
                    if kl <= peak_p * 0.98:
                        exit_p = peak_p * 0.98
                        end_idx = k
                        break
                pos_exit = end_idx
                net_pct = (exit_p / entry_p - 1.0 - FEE_RATE) * 100
                qty = CAPITAL / entry_p
                net_pnl = ((exit_p - entry_p) - (entry_p * FEE_RATE)) * qty
                trades.append({'ticker': ticker, 'net_pct': net_pct, 'net_pnl': net_pnl, 'is_win': net_pnl > 0, 'hold': end_idx - entry_idx})
    return trades

# 2. MOMENTUM (RSI14 > 60)
def test_momentum():
    trades = []
    for ticker, df in stocks_data.items():
        eval_idx = df[df['price_date'] >= START_DATE].index
        if len(eval_idx) < 15: continue
        pos_exit = -1
        for idx in eval_idx:
            if idx <= pos_exit: continue
            row = df.iloc[idx]
            if row['rsi14'] > 60.0:
                entry_idx = idx + 1
                if entry_idx >= len(df): continue
                entry_row = df.iloc[entry_idx]
                entry_p = float(entry_row['close'])
                if entry_p <= 0: continue
                end_idx = min(entry_idx + 10, len(df) - 1)
                peak_p = entry_p
                exit_p = float(df.iloc[end_idx]['close'])
                for k in range(entry_idx + 1, end_idx + 1):
                    kh = float(df.iloc[k]['high'])
                    kl = float(df.iloc[k]['low'])
                    if kh > peak_p: peak_p = kh
                    if kl <= peak_p * 0.98:
                        exit_p = peak_p * 0.98
                        end_idx = k
                        break
                pos_exit = end_idx
                net_pct = (exit_p / entry_p - 1.0 - FEE_RATE) * 100
                qty = CAPITAL / entry_p
                net_pnl = ((exit_p - entry_p) - (entry_p * FEE_RATE)) * qty
                trades.append({'ticker': ticker, 'net_pct': net_pct, 'net_pnl': net_pnl, 'is_win': net_pnl > 0, 'hold': end_idx - entry_idx})
    return trades

# 3. BOTTOM REBOUND (Stoch %K < 20 & Cross %D)
def test_bottom_rebound():
    trades = []
    for ticker, df in stocks_data.items():
        eval_idx = df[df['price_date'] >= START_DATE].index
        if len(eval_idx) < 15: continue
        pos_exit = -1
        for idx in eval_idx:
            if idx <= pos_exit: continue
            row = df.iloc[idx]
            prev_row = df.iloc[idx - 1]
            if (prev_row['stoch_k'] < 20) and (row['stoch_k'] > row['stoch_d']) and (prev_row['stoch_k'] <= prev_row['stoch_d']):
                entry_idx = idx + 1
                if entry_idx >= len(df): continue
                entry_row = df.iloc[entry_idx]
                entry_p = float(entry_row['close'])
                if entry_p <= 0: continue
                end_idx = min(entry_idx + 10, len(df) - 1)
                peak_p = entry_p
                exit_p = float(df.iloc[end_idx]['close'])
                for k in range(entry_idx + 1, end_idx + 1):
                    kh = float(df.iloc[k]['high'])
                    kl = float(df.iloc[k]['low'])
                    if kh > peak_p: peak_p = kh
                    if kl <= peak_p * 0.98:
                        exit_p = peak_p * 0.98
                        end_idx = k
                        break
                pos_exit = end_idx
                net_pct = (exit_p / entry_p - 1.0 - FEE_RATE) * 100
                qty = CAPITAL / entry_p
                net_pnl = ((exit_p - entry_p) - (entry_p * FEE_RATE)) * qty
                trades.append({'ticker': ticker, 'net_pct': net_pct, 'net_pnl': net_pnl, 'is_win': net_pnl > 0, 'hold': end_idx - entry_idx})
    return trades

# 4. TINS BOTTOM-TO-TOP SWING (Khusus TINS)
def test_tins_bottom_to_top():
    trades = []
    df = stocks_data.get('TINS')
    if df is not None:
        eval_idx = df[df['price_date'] >= START_DATE].index
        pos = 0
        entry_p = 0
        peak_p = 0
        entry_idx = -1
        for idx in eval_idx:
            row = df.iloc[idx]
            prev = df.iloc[idx - 1]
            if pos == 0:
                cond_dip = (row['stoch_k'] < 30 or row['bb_pct_b'] < 0.25 or row['rsi14'] < 45)
                cond_green = (row['close'] > row['open'] and row['close'] > prev['close'])
                if cond_dip and cond_green:
                    pos = 1
                    entry_p = float(row['close'])
                    peak_p = entry_p
                    entry_idx = idx
            else:
                kh = float(row['high'])
                kl = float(row['low'])
                kc = float(row['close'])
                if kh > peak_p: peak_p = kh
                gain_peak = (peak_p - entry_p) / entry_p
                
                # Check exit
                exit_p = None
                if gain_peak >= 0.03: # jika cuan >= 3%, trailing lock 2.5%
                    ts_lvl = peak_p * (1.0 - 0.025)
                    if kl <= ts_lvl: exit_p = ts_lvl
                else: # Hard cut loss 3%
                    sl_lvl = entry_p * 0.97
                    if kl <= sl_lvl: exit_p = sl_lvl
                
                # Overbought TP
                if (row['stoch_k'] > 75 or row['bb_pct_b'] > 0.85) and gain_peak >= 0.05:
                    if kl <= peak_p * 0.975: exit_p = peak_p * 0.975
                    
                if exit_p is not None or idx == eval_idx[-1]:
                    if exit_p is None: exit_p = kc
                    net_pct = (exit_p / entry_p - 1.0 - FEE_RATE) * 100
                    qty = CAPITAL / entry_p
                    net_pnl = ((exit_p - entry_p) - (entry_p * FEE_RATE)) * qty
                    trades.append({'ticker': 'TINS', 'net_pct': net_pct, 'net_pnl': net_pnl, 'is_win': net_pnl > 0, 'hold': idx - entry_idx})
                    pos = 0
    return trades

# 5. BSJP MOMENTUM (Beli Sore Pre-Closing -> Jual Open Pagi / TP +2.5%)
def test_bsjp():
    trades = []
    # Evaluasi harian se-bursa
    trading_dates = sorted(list(set([d for df in stocks_data.values() for d in df[df['price_date'] >= START_DATE]['price_date']])))
    
    for d_idx, d in enumerate(trading_dates[:-1]):
        next_d = trading_dates[d_idx + 1]
        candidates = []
        for ticker, df in stocks_data.items():
            match = df[df['price_date'] == d]
            if match.empty: continue
            row = match.iloc[0]
            
            # Kriteria BSJP: Volume Spike >= 1.5x, Green Candle, Return >= +3%, Trx >= Rp 1 Miliar, Price >= MA5
            if (row['volume'] >= row['prev_volume'] * 1.5) and (row['close'] > row['open']) and \
               (row['ret_1d'] >= 0.03) and (row['value'] >= 1_000_000_000) and (row['close'] >= row['ma5']):
                candidates.append((ticker, row['value'], row['close']))
                
        # Urutkan berdasarkan transaksi tertinggi, ambil top 2 per hari
        candidates.sort(key=lambda x: x[1], reverse=True)
        top_candidates = candidates[:2]
        
        for cand in top_candidates:
            ticker, val, close_today = cand
            df = stocks_data[ticker]
            next_match = df[df['price_date'] == next_d]
            if next_match.empty: continue
            next_row = next_match.iloc[0]
            
            entry_p = close_today
            open_next = float(next_row['open'])
            high_next = float(next_row['high'])
            low_next = float(next_row['low'])
            
            # BSJP Rule: Jika Open gap-up >= +2.5% atau High pagi tembus +2.5%, TP @ +2.5% (Rp entry * 1.025)
            # Jika Open dibawah -3.0%, Cut Loss @ -3.0%
            # Default exit: Open Market
            if open_next >= entry_p * 1.025 or high_next >= entry_p * 1.025:
                exit_p = entry_p * 1.025
            elif open_next <= entry_p * 0.97:
                exit_p = open_next
            else:
                exit_p = open_next
                
            net_pct = (exit_p / entry_p - 1.0 - FEE_RATE) * 100
            qty = (CAPITAL / len(top_candidates)) / entry_p
            net_pnl = ((exit_p - entry_p) - (entry_p * FEE_RATE)) * qty
            trades.append({'ticker': ticker, 'net_pct': net_pct, 'net_pnl': net_pnl, 'is_win': net_pnl > 0, 'hold': 1})
            
    return trades

# 6. SELF-RADAR V1 (RSI14 >= 60, ret_5d >= 5%, dd_20d >= -5%, exit trailing 1.0% day 2)
def test_self_radar():
    trades = []
    # 30 ticker self radar
    sr_tickers = ['BAJA', 'MCAS', 'GDST', 'MDIA', 'BYAN', 'PACK', 'KOTA', 'MGLV', 'SLIS', 'FAST', 'TEBE', 'IATA', 'JGLE', 'KIJA', 'SINI', 'GULA', 'JKON', 'JARR', 'INET', 'NSSS', 'DEWA', 'ISAT', 'CUAN', 'PADA', 'WIFI', 'SSIA', 'HATM', 'ESSA', 'BRMS', 'FPNI']
    
    for ticker in sr_tickers:
        df = stocks_data.get(ticker)
        if df is None: continue
        eval_idx = df[df['price_date'] >= START_DATE].index
        pos_exit = -1
        for idx in eval_idx:
            if idx <= pos_exit: continue
            row = df.iloc[idx]
            if (row['rsi14'] >= 60) and (row['ret_5d'] >= 0.05) and (row['dd_20d'] >= -0.05):
                entry_p = float(row['close'])
                if entry_p <= 0: continue
                end_idx = min(idx + 3, len(df) - 1)
                peak_p = entry_p
                exit_p = float(df.iloc[end_idx]['close'])
                for k in range(idx + 1, end_idx + 1):
                    kh = float(df.iloc[k]['high'])
                    kl = float(df.iloc[k]['low'])
                    if kh > peak_p: peak_p = kh
                    if kl <= peak_p * 0.99: # TS 1%
                        exit_p = peak_p * 0.99
                        end_idx = k
                        break
                pos_exit = end_idx
                net_pct = (exit_p / entry_p - 1.0 - FEE_RATE) * 100
                qty = CAPITAL / entry_p
                net_pnl = ((exit_p - entry_p) - (entry_p * FEE_RATE)) * qty
                trades.append({'ticker': ticker, 'net_pct': net_pct, 'net_pnl': net_pnl, 'is_win': net_pnl > 0, 'hold': end_idx - idx})
    return trades

# 7. AI ML DSS SENTIMEN + PREDIKSI (V6A/V6B TP 30% / SL 3% atau DSS Target 3%)
def test_ai_dss():
    # Ambil dari 10 ticker resmi yang ada di DB trades (real trade journal records)
    trades = []
    conn2 = pymysql.connect(host='127.0.0.1', user='root', password='', database='sentimena_dashboard', port=3306)
    cur = conn2.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT ticker, pnl_percent, pnl_total, holding_days FROM trades WHERE entry_date >= '2025-12-01' AND strategy_label IN ('ai_tp30', 'legacy_ab_ac')")
    rows = cur.fetchall()
    conn2.close()
    for r in rows:
        pct = float(r['pnl_percent'] or 0)
        pnl = float(r['pnl_total'] or 0)
        trades.append({'ticker': r['ticker'], 'net_pct': pct, 'net_pnl': pnl, 'is_win': pnl > 0, 'hold': r['holding_days'] or 5})
    return trades

# Eksekusi 7 Strategi
print("1. Menguji GABUNGAN...")
t_gab = test_gabungan()

print("2. Menguji MOMENTUM...")
t_mom = test_momentum()

print("3. Menguji BOTTOM REBOUND...")
t_breb = test_bottom_rebound()

print("4. Menguji TINS BOTTOM-TO-TOP...")
t_tins = test_tins_bottom_to_top()

print("5. Menguji BSJP MOMENTUM...")
t_bsjp = test_bsjp()

print("6. Menguji SELF-RADAR V1...")
t_sr = test_self_radar()

print("7. Menguji AI ML DSS PREDIKSI...")
t_ai = test_ai_dss()

def summarize(name, t_list):
    if not t_list:
        return {'name': name, 'count': 0, 'wins': 0, 'losses': 0, 'wr': 0, 'tot_pnl': 0, 'avg_pct': 0, 'avg_hold': 0}
    tot = len(t_list)
    wins = sum(1 for t in t_list if t['is_win'])
    losses = tot - wins
    wr = (wins / tot) * 100
    tot_pnl = sum(t['net_pnl'] for t in t_list)
    avg_pct = np.mean([t['net_pct'] for t in t_list])
    avg_hold = np.mean([t['hold'] for t in t_list])
    return {
        'name': name,
        'count': tot,
        'wins': wins,
        'losses': losses,
        'wr': wr,
        'tot_pnl': tot_pnl,
        'avg_pct': avg_pct,
        'avg_hold': avg_hold
    }

results = [
    summarize('1. BSJP MOMENTUM (1 Malam)', t_bsjp),
    summarize('2. GABUNGAN (Diskon / Drawdown)', t_gab),
    summarize('3. MOMENTUM (RSI14 > 60)', t_mom),
    summarize('4. TINS BOTTOM-TO-TOP (Khusus TINS)', t_tins),
    summarize('5. BOTTOM REBOUND (Stoch %K<20)', t_breb),
    summarize('6. SELF-RADAR V1 (Overnight)', t_sr),
    summarize('7. AI ML DSS (IndoBERT + V6A)', t_ai)
]

# Urutkan berdasarkan total akumulasi cuan
results_sorted = sorted(results, key=lambda x: x['tot_pnl'], reverse=True)

print("\n" + "=" * 105)
print("HASIL AKHIR KOMPARASI 7 STRATEGI SENTIMENA (1 DESEMBER 2025 - 5 OKTOBER 2026)")
print("Modal Standar Rp 10 Juta per Trade | Fee Broker 0.40% Round-Trip Diperhitungkan Lengkap")
print("=" * 105)
print(f"{'Peringkat / Nama Strategi':<34s} | {'Trade':<6s} | {'Win Rate':<10s} | {'Avg %':<9s} | {'Rata2 Tahan':<12s} | {'Total Akumulasi PnL (Rp)':<22s}")
print("-" * 105)

for rank, r in enumerate(results_sorted, 1):
    medal = "🥇 " if rank == 1 else ("🥈 " if rank == 2 else ("🥉 " if rank == 3 else f"{rank}. "))
    print(f"{medal + r['name']:<34s} | {r['count']:<6d} | {r['wr']:8.1f}% | {r['avg_pct']:+7.2f}% | {r['avg_hold']:8.1f} hari | Rp {r['tot_pnl']:18,.0f}")

print("=" * 105)
