#!/usr/bin/env python3
"""
Screener Momentum BSJP (Beli Sore Jual Pagi)
Kriteria:
1. Volume Spike: Volume > Previous Volume (Rasio > 1.5x)
2. Bullish Candle: Price > Open Price
3. Price Return: +3.0% s/d +15.0%
4. Liquidity: Value >= Rp 100.000.000
5. Resistance/Trend: Price >= MA5 dan Price >= MA10
"""

import sys
import pandas as pd
import numpy as np

def run_screener(csv_path='data/screener_20_stocks_historical.csv', min_vol_ratio=1.5, min_ret=3.0, min_val=100_000_000):
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error loading {csv_path}: {e}")
        return

    df['date'] = pd.to_datetime(df['date'])
    latest_date = df['date'].max()
    
    results = []
    for ticker, g in df.groupby('ticker'):
        g = g.sort_values('date').reset_index(drop=True)
        if len(g) < 10:
            continue
            
        latest = g.iloc[-1]
        prev = g.iloc[-2]
        
        close = latest['Close']
        open_p = latest['Open']
        prev_close = prev['Close']
        vol = latest['Volume']
        prev_vol = prev['Volume']
        
        if prev_close <= 0 or prev_vol <= 0:
            continue
            
        ret_pct = (close - prev_close) / prev_close * 100
        vol_ratio = vol / prev_vol
        val = close * vol
        ma5 = g['Close'].tail(5).mean()
        ma10 = g['Close'].tail(10).mean()
        
        # Filter check
        is_bullish = close > open_p
        pass_vol = vol_ratio >= min_vol_ratio
        pass_ret = ret_pct >= min_ret
        pass_val = val >= min_val
        pass_ma = (close >= ma5) or (close >= ma10)
        
        if is_bullish and pass_vol and pass_ret and pass_val and pass_ma:
            results.append({
                'ticker': ticker,
                'price': close,
                'open': open_p,
                'ret_pct': ret_pct,
                'vol_ratio': vol_ratio,
                'value': val,
                'ma5': ma5,
                'ma10': ma10,
                'date': latest['date'].strftime('%Y-%m-%d')
            })
            
    res_df = pd.DataFrame(results)
    if res_df.empty:
        print("Tidak ada saham yang lolos kriteria pada tanggal terbaru.")
        return
        
    res_df = res_df.sort_values('ret_pct', ascending=False)
    print(f"\n=======================================================")
    print(f"   HASIL SCREENER MOMENTUM BSJP (Per {latest_date.strftime('%Y-%m-%d')})")
    print(f"=======================================================")
    print(f"Total Saham Lolos: {len(res_df)}")
    print("------------------------------------------------------------------------------------------------")
    print(f"{'Ticker':<7} | {'Harga':<7} | {'Kenaikan':<8} | {'Vol Spike':<10} | {'Nilai Trx (Rp)':<16} | {'MA5':<7} | {'MA10':<7}")
    print("------------------------------------------------------------------------------------------------")
    for _, r in res_df.iterrows():
        val_str = f"Rp {r['value']:,.0f}"
        print(f"{r['ticker']:<7} | Rp{r['price']:<5.0f} | {r['ret_pct']:+6.2f}% | {r['vol_ratio']:>7.2f}x   | {val_str:<16} | {r['ma5']:<7.1f} | {r['ma10']:<7.1f}")
    print("------------------------------------------------------------------------------------------------\n")

if __name__ == '__main__':
    run_screener()
