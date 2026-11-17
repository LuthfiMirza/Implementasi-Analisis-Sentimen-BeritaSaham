#!/usr/bin/env python3
"""
Simulasi & Riset Komprehensif BSJP (Beli Sore Jual Pagi)
Memanfaatkan Data Harian & Intraday 15-Menit (Agustus - November 2026)
"""

import pymysql
import pandas as pd
import numpy as np
import math
from datetime import datetime

def tick(price):
    if price < 200:
        return 1
    elif price < 500:
        return 2
    elif price < 2000:
        return 5
    elif price < 5000:
        return 10
    else:
        return 25

def round_down_tick(price):
    t = tick(price)
    return math.floor((price + 1e-9) / t) * t

def round_up_tick(price):
    t = tick(price)
    return math.ceil((price - 1e-9) / t) * t

def net_return(entry, exit_price, buy_fee=0.0015, sell_fee=0.0025):
    cost = entry * (1 + buy_fee)
    proceeds = exit_price * (1 - sell_fee)
    return ((proceeds / cost) - 1.0) * 100.0

def main():
    conn = pymysql.connect(
        host="127.0.0.1", port=3306, user="root", database="sentimena_dashboard"
    )

    print("1. Mengambil data harian...")
    # Ambil data harian stock_prices + stocks
    query_daily = """
        SELECT s.code as ticker, s.company_name, p.price_date as date, 
               p.open, p.high, p.low, p.close, p.volume
        FROM stock_prices p
        JOIN stocks s ON p.stock_id = s.id
        WHERE p.price_date >= '2026-08-01'
        ORDER BY s.code, p.price_date ASC
    """
    df_daily = pd.read_sql(query_daily, conn)
    df_daily['date'] = pd.to_datetime(df_daily['date']).dt.date
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df_daily[col] = df_daily[col].astype(float)
    df_daily['value'] = df_daily['close'] * df_daily['volume']

    print("2. Mengambil data intraday 15m...")
    query_intra = """
        SELECT stock_code as ticker, bar_time, open, high, low, close, volume
        FROM intraday_prices
        ORDER BY stock_code, bar_time ASC
    """
    df_intra = pd.read_sql(query_intra, conn)
    df_intra['bar_time'] = pd.to_datetime(df_intra['bar_time'])
    df_intra['date'] = df_intra['bar_time'].dt.date
    df_intra['time'] = df_intra['bar_time'].dt.strftime('%H:%M')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df_intra[col] = df_intra[col].astype(float)

    # Index intraday by (ticker, date)
    intra_groups = {}
    for (t, d), g in df_intra.groupby(['ticker', 'date']):
        intra_groups[(t, d)] = g.sort_values('bar_time').reset_index(drop=True)

    print(f"Total bar intraday terindeks: {len(df_intra):,} bar across {len(intra_groups)} ticker-days.")

    # 3. Deteksi sinyal BSJP
    signals = []
    daily_groups = df_daily.groupby('ticker')

    for ticker, g in daily_groups:
        g = g.sort_values('date').reset_index(drop=True)
        if len(g) < 5:
            continue
        for i in range(1, len(g) - 1):
            curr = g.iloc[i]
            prev = g.iloc[i - 1]
            next_day = g.iloc[i + 1]

            close = curr['close']
            open_p = curr['open']
            prev_close = prev['close']
            vol = curr['volume']
            prev_vol = prev['volume']
            val = curr['value']

            if prev_close <= 0 or prev_vol <= 0:
                continue

            ret_pct = (close - prev_close) / prev_close * 100.0
            vol_ratio = vol / prev_vol

            # BSJP Rules:
            # 1. Close > Open
            # 2. Ret >= +3.0%
            # 3. Vol Spike >= 1.5x
            # 4. Trx Value >= Rp 100 Juta
            if close > open_p and ret_pct >= 3.0 and vol_ratio >= 1.5 and val >= 100_000_000:
                signal_date = curr['date']
                next_date = next_day['date']
                
                # Cek ketersediaan intraday hari berikutnya
                intra_bars = intra_groups.get((ticker, next_date))

                signals.append({
                    'ticker': ticker,
                    'name': curr['company_name'],
                    'signal_date': signal_date,
                    'next_date': next_date,
                    'entry_price': close,
                    'return_pct': ret_pct,
                    'vol_ratio': vol_ratio,
                    'trx_value': val,
                    'next_open': next_day['open'],
                    'next_high': next_day['high'],
                    'next_low': next_day['low'],
                    'next_close': next_day['close'],
                    'intra_bars': intra_bars
                })

    df_sig = pd.DataFrame(signals)
    print(f"\n3. Ditemukan {len(df_sig)} Sinyal BSJP dari {len(daily_groups)} saham pada periode Aug - Nov 2026.")

    if len(df_sig) == 0:
        return

    # 4. Evaluasi Skenario Exit
    # Skenario 1: Open 09:00 WIB
    # Skenario 2: Target Profit +2.5% vs SL -3.0% (Limit TP)
    # Skenario 3: Target Profit +3.5% vs SL -3.0%
    # Skenario 4: Trailing Stop 2.0% dari Peak Pagi (Intraday)
    # Skenario 5: Time Exit 09:15 WIB

    results = []

    for idx, s in df_sig.iterrows():
        entry = s['entry_price']
        next_open = s['next_open']
        next_high = s['next_high']
        next_low = s['next_low']
        intra = s['intra_bars']

        # Kategori
        is_rocket = s['return_pct'] >= 15.0
        category = 'rocket' if is_rocket else 'sweetspot'

        # Skenario 1: Jual di Open 09:00
        pnl_open = net_return(entry, next_open)
        
        # MFE / MAE dari High & Low H+1
        mfe_pct = (next_high - entry) / entry * 100.0
        mae_pct = (next_low - entry) / entry * 100.0

        # Skenario 2: TP +2.5% vs SL -3.0%
        # TP price round up tick, SL round down tick
        tp25 = round_up_tick(entry * 1.025)
        sl30 = round_down_tick(entry * 0.97)

        # Evaluasi intraday jika bar tersedia
        hit_tp25 = False
        hit_sl30 = False
        exit_tp25_price = next_open
        exit_trail2_price = next_open
        exit_time0915_price = next_open

        if intra is not None and len(intra) > 0:
            # Bar 09:00
            bar0 = intra.iloc[0]
            # Bar 09:15
            bar1 = intra.iloc[1] if len(intra) > 1 else bar0

            # TP25 evaluation
            if next_open >= tp25:
                # Gap up melampaui TP -> dpt harga Open!
                exit_tp25_price = next_open
                hit_tp25 = True
            elif next_open <= sl30:
                # Gap down tembus SL
                exit_tp25_price = next_open
                hit_sl30 = True
            else:
                # Cek high/low pagi (09:00 - 10:00)
                morning_bars = intra[intra['time'] <= '10:00']
                m_high = morning_bars['high'].max()
                m_low = morning_bars['low'].min()
                if m_high >= tp25:
                    exit_tp25_price = tp25
                    hit_tp25 = True
                elif m_low <= sl30:
                    exit_tp25_price = sl30
                    hit_sl30 = True
                else:
                    exit_tp25_price = bar1['close']

            # Trailing Stop 2% dari Peak Intraday
            peak = max(entry, next_open)
            trail_exit = None
            for b_idx, b in intra.iterrows():
                b_high = b['high']
                b_low = b['low']
                b_close = b['close']
                
                if b_high > peak:
                    peak = b_high
                
                # Pullback 2%
                trail_stop = round_down_tick(peak * 0.98)
                if peak > entry and b_low <= trail_stop:
                    trail_exit = max(trail_stop, b_low)
                    break
                elif b_low <= sl30:
                    trail_exit = sl30
                    break
                # Batas jam 10:00 jika tidak hit
                if b['time'] >= '10:00':
                    trail_exit = b_close
                    break
            exit_trail2_price = trail_exit if trail_exit is not None else next_open

            # Exit 09:15 WIB
            exit_time0915_price = bar1['open'] if len(intra) > 1 else bar0['close']
        else:
            # Fallback jika intraday bar tidak ada, pakai daily
            if next_open >= tp25:
                exit_tp25_price = next_open
            elif next_high >= tp25:
                exit_tp25_price = tp25
            elif next_low <= sl30:
                exit_tp25_price = sl30
            else:
                exit_tp25_price = s['next_close']
            exit_trail2_price = next_open
            exit_time0915_price = next_open

        pnl_tp25 = net_return(entry, exit_tp25_price)
        pnl_trail2 = net_return(entry, exit_trail2_price)
        pnl_time0915 = net_return(entry, exit_time0915_price)

        results.append({
            'ticker': s['ticker'],
            'signal_date': s['signal_date'],
            'entry': entry,
            'category': category,
            'vol_ratio': s['vol_ratio'],
            'return_pct': s['return_pct'],
            'trx_value': s['trx_value'],
            'next_open': next_open,
            'next_high': next_high,
            'mfe_pct': mfe_pct,
            'mae_pct': mae_pct,
            'pnl_open': pnl_open,
            'pnl_tp25': pnl_tp25,
            'pnl_trail2': pnl_trail2,
            'pnl_time0915': pnl_time0915,
        })

    res_df = pd.DataFrame(results)

    print("\n" + "="*80)
    print("HASIL BACKTEST 5 SKENARIO EXIT BSJP (AUG - NOV 2026)")
    print("="*80)
    print(f"Total Sampel Sinyal: {len(res_df)} Trade")
    print(f"- Sweetspot (3% - 15%): {len(res_df[res_df['category']=='sweetspot'])} Trade")
    print(f"- Super Rocket (> 15%): {len(res_df[res_df['category']=='rocket'])} Trade\n")

    methods = [
        ('1. Jual di Open 09:00 WIB', 'pnl_open'),
        ('2. Target Profit +2.5% / SL -3.0%', 'pnl_tp25'),
        ('3. Trailing Stop 2.0% dari Peak', 'pnl_trail2'),
        ('4. Time Exit 09:15 WIB', 'pnl_time0915'),
    ]

    for label, col in methods:
        win_rate = (res_df[col] > 0).mean() * 100.0
        mean_pnl = res_df[col].mean()
        median_pnl = res_df[col].median()
        total_pnl = res_df[col].sum()
        wins = res_df[res_df[col] > 0][col].sum()
        losses = abs(res_df[res_df[col] <= 0][col].sum())
        pf = wins / losses if losses > 0 else 999.0
        
        print(f"📌 {label}:")
        print(f"   Win Rate    : {win_rate:.1f}%")
        print(f"   Mean Net    : {mean_pnl:+.2f}% (Median: {median_pnl:+.2f}%)")
        print(f"   Profit Factor: {pf:.2f}")
        print(f"   Total Cuan %: {total_pnl:+.1f}%\n")

    print("="*80)
    print("DISTRIBUSI EKSCURSI INTRADAY PAGI (MFE & MAE):")
    print("="*80)
    print(f"Rata-rata Puncak Lompatan Pagi (MFE) : {res_df['mfe_pct'].mean():+.2f}%")
    print(f"Median Puncak Lompatan Pagi (MFE)    : {res_df['mfe_pct'].median():+.2f}%")
    print(f"Proporsi Sinyal Yang Naik >= +2.0%   : {(res_df['mfe_pct'] >= 2.0).mean()*100:.1f}%")
    print(f"Proporsi Sinyal Yang Naik >= +3.0%   : {(res_df['mfe_pct'] >= 3.0).mean()*100:.1f}%")
    print(f"Proporsi Sinyal Yang Naik >= +5.0%   : {(res_df['mfe_pct'] >= 5.0).mean()*100:.1f}%")
    print(f"Rata-rata Penurunan Terendah (MAE)   : {res_df['mae_pct'].mean():+.2f}%\n")

    print("="*80)
    print("PERBANDINGAN KATEGORI: SWEETSPOT VS SUPER ROCKET (METODE TP2.5)")
    print("="*80)
    sw = res_df[res_df['category'] == 'sweetspot']
    rk = res_df[res_df['category'] == 'rocket']
    print(f"🎯 SWEETSPOT (N={len(sw)}): Win Rate {(sw['pnl_tp25'] > 0).mean()*100:.1f}%, Mean Net {sw['pnl_tp25'].mean():+.2f}%, MFE {sw['mfe_pct'].mean():+.2f}%")
    print(f"🚀 SUPER ROCKET (N={len(rk)}): Win Rate {(rk['pnl_tp25'] > 0).mean()*100:.1f}%, Mean Net {rk['pnl_tp25'].mean():+.2f}%, MFE {rk['mfe_pct'].mean():+.2f}%")

    # Save details to CSV
    res_df.to_csv('quant/bsjp_comprehensive_simulation_2026.csv', index=False)
    print("\nData simulasi lengkap disimpan ke: quant/bsjp_comprehensive_simulation_2026.csv")

if __name__ == '__main__':
    main()

