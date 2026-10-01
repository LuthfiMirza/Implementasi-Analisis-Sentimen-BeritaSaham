#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, time, timedelta
import pandas as pd
import yfinance as yf

input_file = "quant/drawdown_bounce_tracker/radar_logs_input.json"
output_file = "quant/drawdown_bounce_tracker/radar_logs_updates.json"

with open(input_file, "r") as f:
    logs = json.load(f)

print(f"Total rows loaded: {len(logs)}")

tickers = sorted(list(set(l['ticker'] for l in logs)))
yf_tickers = [f"{t}.JK" for t in tickers]

print(f"Downloading 5m and 1d data for {len(tickers)} tickers: {', '.join(tickers)}...")
df5m = yf.download(yf_tickers, start="2026-09-01", end="2026-10-03", interval="5m", progress=False, auto_adjust=False)
df1d = yf.download(yf_tickers, start="2026-09-01", end="2026-10-03", interval="1d", progress=False, auto_adjust=False)

def get_ticker_df(df, ticker):
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        try:
            sub = df.xs(f"{ticker}.JK", axis=1, level=1)
            return sub.dropna(subset=['Close'])
        except Exception:
            return pd.DataFrame()
    return df.dropna(subset=['Close'])

# Process each log
updates = []
results = []

for log in logs:
    log_id = log['id']
    ticker = log['ticker']
    sig_date = str(log['signal_date'])[:10]
    first_seen = float(log['price_at_first_seen']) if log['price_at_first_seen'] else 0.0
    latest = float(log['latest_price']) if log['latest_price'] else first_seen
    
    # Keep manual user fill/exit if present (e.g. ID 64)
    if log['fill_price'] is not None and log['exit_price'] is not None:
        pnl = float(log['pnl_pct']) if log['pnl_pct'] is not None else 0.0
        results.append({
            'id': log_id,
            'ticker': ticker,
            'date': sig_date,
            'fill': float(log['fill_price']),
            'exit': float(log['exit_price']),
            'pnl': pnl,
            'result': log['result'],
            'note': 'Already manual filled'
        })
        continue

    # Default entry price is price_at_first_seen (or latest_price)
    fill_price = first_seen if first_seen > 0 else latest
    if fill_price <= 0:
        continue
        
    entry_dt = f"{sig_date} 15:40:00"

    # If signal is today (2026-10-01), mark as filled OPEN
    if sig_date == "2026-10-01":
        updates.append({
            'id': log_id,
            'fill_price': fill_price,
            'filled_at': entry_dt,
            'exit_price': None,
            'exited_at': None,
            'pnl_pct': None,
            'result': None
        })
        results.append({
            'id': log_id,
            'ticker': ticker,
            'date': sig_date,
            'fill': fill_price,
            'exit': None,
            'pnl': None,
            'result': None,
            'note': 'OPEN today'
        })
        continue

    # For past dates, find next trading day H+1
    t5m = get_ticker_df(df5m, ticker)
    t1d = get_ticker_df(df1d, ticker)

    h1_date = None
    exit_price = None
    exit_dt = None

    if not t5m.empty:
        t5m_local = t5m.copy()
        if t5m_local.index.tz is None:
            t5m_local.index = t5m_local.index.tz_localize('UTC').tz_convert('Asia/Jakarta')
        else:
            t5m_local.index = t5m_local.index.tz_convert('Asia/Jakarta')

        t5m_local['date_str'] = t5m_local.index.strftime('%Y-%m-%d')
        t5m_local['time_str'] = t5m_local.index.strftime('%H:%M')

        available_dates = sorted([d for d in t5m_local['date_str'].unique() if d > sig_date])
        if available_dates:
            h1_date = available_dates[0]
            day_bars = t5m_local[t5m_local['date_str'] == h1_date].sort_index()

            peak = fill_price
            hit_ts = False

            for bar_idx, row in day_bars.iterrows():
                h = float(row['High'])
                l = float(row['Low'])
                t = row['time_str']
                if h > peak:
                    peak = h
                
                # Trailing stop 1% active at >= 09:30 WIB
                if t >= "09:30":
                    ts_level = peak * 0.99
                    if l <= ts_level:
                        exit_price = ts_level
                        exit_dt = f"{h1_date} {t}:00"
                        hit_ts = True
                        break

            if not hit_ts and len(day_bars) > 0:
                exit_price = float(day_bars.iloc[-1]['Close'])
                exit_dt = f"{h1_date} 15:50:00"

    # Fallback to 1d if 5m was not found or incomplete
    if exit_price is None and not t1d.empty:
        t1d_dates = sorted([d.strftime('%Y-%m-%d') for d in t1d.index if d.strftime('%Y-%m-%d') > sig_date])
        if t1d_dates:
            h1_date = t1d_dates[0]
            # Try to get row by date string or timestamp
            try:
                h1_row = t1d.loc[h1_date]
            except Exception:
                h1_row = t1d[t1d.index.strftime('%Y-%m-%d') == h1_date].iloc[0]
                
            h1_high = float(h1_row['High'])
            h1_close = float(h1_row['Close'])
            h1_low = float(h1_row['Low'])
            
            if h1_low <= h1_high * 0.99:
                exit_price = h1_high * 0.99
            else:
                exit_price = h1_close
            exit_dt = f"{h1_date} 15:50:00"

    if exit_price is None:
        # If no future price exists (e.g. yesterday's trade without next day yet)
        exit_price = latest
        exit_dt = f"{sig_date} 16:00:00"

    # Fraksi harga IDX (round to tick)
    if exit_price < 200:
        exit_price = round(exit_price)
    elif exit_price < 500:
        exit_price = round(exit_price / 2) * 2
    elif exit_price < 2000:
        exit_price = round(exit_price / 5) * 5
    elif exit_price < 5000:
        exit_price = round(exit_price / 10) * 10
    else:
        exit_price = round(exit_price / 25) * 25

    pnl_pct = round((exit_price - fill_price) / fill_price * 100, 2)
    result = 'WIN' if pnl_pct > 0 else ('LOSS' if pnl_pct < 0 else 'DRAW')

    updates.append({
        'id': log_id,
        'fill_price': fill_price,
        'filled_at': entry_dt,
        'exit_price': exit_price,
        'exited_at': exit_dt,
        'pnl_pct': pnl_pct,
        'result': result
    })

    results.append({
        'id': log_id,
        'ticker': ticker,
        'date': sig_date,
        'fill': fill_price,
        'exit': exit_price,
        'pnl': pnl_pct,
        'result': result,
        'note': 'Evaluated H+1 trailing stop'
    })

with open(output_file, "w") as f:
    json.dump(updates, f, indent=2)

print(f"Generated {len(updates)} updates in {output_file}")

df_res = pd.DataFrame(results)
closed = df_res.dropna(subset=['pnl'])
wins = closed[closed['result'] == 'WIN']
losses = closed[closed['result'] == 'LOSS']
win_rate = len(wins) / len(closed) * 100 if len(closed) > 0 else 0
avg_pnl = closed['pnl'].mean()
total_pnl = closed['pnl'].sum()

print("\n" + "="*50)
print("=== HASIL EVALUASI LENGKAP SELF_RADAR_V1 ===")
print("="*50)
print(f"Total Sinyal: {len(df_res)}")
print(f"Posisi Closed: {len(closed)}")
print(f"Posisi Open Hari Ini: {len(df_res) - len(closed)}")
print(f"WIN: {len(wins)}")
print(f"LOSS: {len(losses)}")
print(f"Win Rate: {win_rate:.1f}%")
print(f"Rata-rata PnL per Trade: {avg_pnl:+.2f}%")
print(f"Akumulasi Return Bersih: {total_pnl:+.2f}%")
print("="*50)

# Group by ticker
by_ticker = closed.groupby('ticker').agg(
    trades=('pnl', 'count'),
    wins=('result', lambda s: (s == 'WIN').sum()),
    win_rate=('result', lambda s: (s == 'WIN').mean() * 100),
    avg_pnl=('pnl', 'mean'),
    total_pnl=('pnl', 'sum')
).sort_values('total_pnl', ascending=False)

print("\nLeaderboard Performa per Ticker:")
print(by_ticker.round(2).to_string())

print("\nTop 5 Cuan Terbesar:")
print(closed.sort_values('pnl', ascending=False).head(5)[['ticker', 'date', 'fill', 'exit', 'pnl']].to_string(index=False))

print("\nTop 5 Koreksi / Loss Terbesar:")
print(closed.sort_values('pnl', ascending=True).head(5)[['ticker', 'date', 'fill', 'exit', 'pnl']].to_string(index=False))
