import os
import pandas as pd
import numpy as np
import mysql.connector

# Connect to database to get full history of BUMI and IHSG
conn = mysql.connector.connect(
    host='127.0.0.1',
    user='root',
    password='',
    database='sentimena_dashboard'
)

query_bumi = """
SELECT price_date, open, high, low, close, volume 
FROM stock_prices 
WHERE stock_id = (SELECT id FROM stocks WHERE code = 'BUMI' LIMIT 1)
ORDER BY price_date ASC
"""

df = pd.read_sql(query_bumi, conn)
conn.close()

df['price_date'] = pd.to_datetime(df['price_date'])
df['ret_1d'] = df['close'].pct_change() * 100
df['roll_max_20'] = df['close'].rolling(20).max()
df['dd_20d'] = (df['close'] - df['roll_max_20']) / df['roll_max_20'] * 100

# Future returns from close
df['fwd_open_1d'] = (df['open'].shift(-1) - df['close']) / df['close'] * 100
df['fwd_high_1d'] = (df['high'].shift(-1) - df['close']) / df['close'] * 100
df['fwd_low_1d'] = (df['low'].shift(-1) - df['close']) / df['close'] * 100
df['fwd_ret_1d'] = (df['close'].shift(-1) - df['close']) / df['close'] * 100

df['fwd_high_2d'] = (df['high'].shift(-2) - df['close']) / df['close'] * 100
df['fwd_ret_2d'] = (df['close'].shift(-2) - df['close']) / df['close'] * 100

df['fwd_high_5d'] = (df[['high']].shift(-1).rolling(5).max()['high'] - df['close']) / df['close'] * 100 # next 5 days
df['fwd_ret_5d'] = (df['close'].shift(-5) - df['close']) / df['close'] * 100
df['fwd_ret_10d'] = (df['close'].shift(-10) - df['close']) / df['close'] * 100

print(f"Total data BUMI: {len(df)} baris dari {df['price_date'].min().date()} hingga {df['price_date'].max().date()}")

# Case 1: All days where BUMI daily return <= -5.0%
d5 = df[df['ret_1d'] <= -5.0].copy()
print(f"\n=======================================================")
print(f"CASE 1: KETIKA BUMI JATUH >= 5% DALAM 1 HARI (Total: {len(d5)} kejadian)")
print(f"=======================================================")
win_1d = (d5['fwd_ret_1d'] > 0).mean() * 100
avg_ret_1d = d5['fwd_ret_1d'].mean()
median_ret_1d = d5['fwd_ret_1d'].median()
avg_high_1d = d5['fwd_high_1d'].mean()
avg_low_1d = d5['fwd_low_1d'].mean()

win_2d = (d5['fwd_ret_2d'] > 0).mean() * 100
avg_ret_2d = d5['fwd_ret_2d'].mean()

win_5d = (d5['fwd_ret_5d'] > 0).mean() * 100
avg_ret_5d = d5['fwd_ret_5d'].mean()
avg_high_5d = (df.loc[d5.index, 'fwd_high_5d']).mean()

print(f"--- BESOKNYA (T+1) ---")
print(f"Peluang Rebound Positif T+1 (Win Rate Close > Close): {win_1d:.1f}%")
print(f"Rata-rata Return T+1 Close: {avg_ret_1d:+.2f}% (Median: {median_ret_1d:+.2f}%)")
print(f"Rata-rata High T+1 (Peluang Jual di Puncak Intraday Besok): {avg_high_1d:+.2f}%")
print(f"Rata-rata Low T+1 (Kedalaman Panic Besok Pagi): {avg_low_1d:+.2f}%")

print(f"\n--- SWING 2-5 HARI (T+2 & T+5) ---")
print(f"Peluang Rebound T+2: {win_2d:.1f}% | Rata-rata Return T+2: {avg_ret_2d:+.2f}%")
print(f"Peluang Rebound T+5: {win_5d:.1f}% | Rata-rata Return T+5: {avg_ret_5d:+.2f}%")
print(f"Rata-rata High Tertinggi dalam 5 Hari: {avg_high_5d:+.2f}%")

# Case 2: Filter ketat Gabungan Drawdown (ret_1d <= -5% AND dd_20d <= -20%)
d_combo = df[(df['ret_1d'] <= -5.0) & (df['dd_20d'] <= -20.0)].copy()
print(f"\n=======================================================")
print(f"CASE 2: BUMI JATUH >= 5% SAAT SUDAH OVERSOLD / DRAWDOWN >= 20% (Total: {len(d_combo)} kejadian)")
print(f"=======================================================")
win_c_1d = (d_combo['fwd_ret_1d'] > 0).mean() * 100
avg_c_ret_1d = d_combo['fwd_ret_1d'].mean()
avg_c_high_1d = d_combo['fwd_high_1d'].mean()
avg_c_low_1d = d_combo['fwd_low_1d'].mean()

win_c_2d = (d_combo['fwd_ret_2d'] > 0).mean() * 100
avg_c_ret_2d = d_combo['fwd_ret_2d'].mean()

win_c_5d = (d_combo['fwd_ret_5d'] > 0).mean() * 100
avg_c_ret_5d = d_combo['fwd_ret_5d'].mean()

win_c_10d = (d_combo['fwd_ret_10d'] > 0).mean() * 100
avg_c_ret_10d = d_combo['fwd_ret_10d'].mean()

print(f"Peluang Rebound T+1: {win_c_1d:.1f}% | Rata-rata Return T+1: {avg_c_ret_1d:+.2f}% (Rata High: {avg_c_high_1d:+.2f}%)")
print(f"Peluang Rebound T+2: {win_c_2d:.1f}% | Rata-rata Return T+2: {avg_c_ret_2d:+.2f}%")
print(f"Peluang Rebound T+5: {win_c_5d:.1f}% | Rata-rata Return T+5: {avg_c_ret_5d:+.2f}%")
print(f"Peluang Rebound T+10: {win_c_10d:.1f}% | Rata-rata Return T+10: {avg_c_ret_10d:+.2f}%")

print("\n10 Contoh Kejadian Terakhir Case 2 (Drawdown Deep Drop):")
sample = d_combo[['price_date', 'close', 'ret_1d', 'dd_20d', 'fwd_open_1d', 'fwd_high_1d', 'fwd_ret_1d', 'fwd_ret_5d']].tail(10)
print(sample.to_string(index=False))
