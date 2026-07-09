#!/usr/bin/env python3
"""
Simulasi backtest JUJUR sistem AI trading BUMI & DEWA, Des 2025 -> Jul 2026.
Pakai harga OHLC ASLI dari database. Aturan sesuai parameter tervalidasi OOS:
  - take profit 30% (fixed pct), stop loss 3% (fixed pct)
  - hold maksimum 40 hari bursa
  - re-entry hari berikutnya (continuous exposure) sampai data habis
Tidak ada angka dikarang -- semua exit ditentukan oleh high/low harian riil.
"""
# prices_clean.csv = ekspor OHLC harian BUMI & DEWA dari tabel stock_prices sejak
# 2025-12-01, HANYA baris non-seed (WHERE source<>'seed' OR source IS NULL),
# dedup 1 baris per tanggal (ambil id terbesar). Baris source='seed' WAJIB dibuang
# karena mengcontaminasi seri harga (lihat journal_sim_dec2025_jul2026.md).
import csv, json
from collections import defaultdict

PRICES = defaultdict(list)
with open('prices_clean.csv') as f:
    for row in csv.DictReader(f):
        PRICES[row['code']].append({
            'date': row['date'],
            'open': float(row['open']), 'high': float(row['high']),
            'low': float(row['low']), 'close': float(row['close']),
        })

TP_PCT = 0.30
SL_PCT = 0.03
MAX_HOLD = 40
FEE = 0.0025  # ~0.25% round-trip (beli 0.15% + jual 0.10% khas broker ritel IDX), pendekatan konservatif

def simulate(code, capital):
    bars = PRICES[code]
    trades = []
    i = 0
    n = len(bars)
    # entry di close hari pertama data (awal Desember)
    while i < n - 1:
        entry_bar = bars[i]
        entry = entry_bar['close']
        tp_price = entry * (1 + TP_PCT)
        sl_price = entry * (1 - SL_PCT)
        exit_price = None; exit_date = None; reason = None
        j = i + 1
        held = 0
        while j < n and held < MAX_HOLD:
            bar = bars[j]
            held += 1
            # SL diperiksa lebih dulu (asumsi konservatif: kalau satu hari sentuh dua-duanya, anggap SL kena)
            if bar['low'] <= sl_price:
                exit_price = sl_price; exit_date = bar['date']; reason = 'SL'; break
            if bar['high'] >= tp_price:
                exit_price = tp_price; exit_date = bar['date']; reason = 'TP'; break
            j += 1
        if exit_price is None:
            # hold habis / data habis -> keluar di close bar terakhir yang tercapai
            last = bars[min(j, n-1)]
            exit_price = last['close']; exit_date = last['date']
            reason = 'HOLD_EXPIRE' if held >= MAX_HOLD else 'DATA_END'
        gross_pct = (exit_price - entry) / entry
        net_pct = gross_pct - FEE
        trades.append({
            'code': code, 'entry_date': entry_bar['date'], 'exit_date': exit_date,
            'entry': round(entry,2), 'exit': round(exit_price,2),
            'reason': reason, 'held_days': held,
            'gross_pct': round(gross_pct*100,2), 'net_pct': round(net_pct*100,2),
        })
        # re-entry di bar setelah exit
        # cari index exit_date
        i = next((k for k in range(i+1, n) if bars[k]['date'] == exit_date), n-1) + 1
    return trades

def compound(trades, capital):
    equity = capital
    for t in trades:
        equity *= (1 + t['net_pct']/100)
        t['equity_after'] = round(equity,0)
    return equity

MODAL_TOTAL = 33_000_000
per_stock = MODAL_TOTAL / 2

results = {}
for code in ['DEWA','BUMI']:
    trades = simulate(code, per_stock)
    final_eq = compound(trades, per_stock)
    wins = [t for t in trades if t['net_pct'] > 0]
    results[code] = {
        'trades': trades,
        'n': len(trades),
        'win_rate': round(len(wins)/len(trades)*100,1) if trades else 0,
        'modal': per_stock,
        'final_equity': round(final_eq,0),
        'pnl': round(final_eq - per_stock,0),
        'pnl_pct': round((final_eq/per_stock-1)*100,2),
    }
    # buy & hold pembanding
    bars = PRICES[code]
    bh = (bars[-1]['close'] - bars[0]['close'])/bars[0]['close']
    results[code]['buyhold_pct'] = round(bh*100,2)
    results[code]['buyhold_final'] = round(per_stock*(1+bh),0)

print(json.dumps(results, indent=2))
print("\n==== RINGKASAN ====")
tot_ai = sum(r['final_equity'] for r in results.values())
tot_bh = sum(r['buyhold_final'] for r in results.values())
print(f"Modal awal total       : Rp {MODAL_TOTAL:,.0f}")
print(f"Nilai akhir (AI TP/SL) : Rp {tot_ai:,.0f}  ({(tot_ai/MODAL_TOTAL-1)*100:+.2f}%)")
print(f"Nilai akhir (Buy&Hold) : Rp {tot_bh:,.0f}  ({(tot_bh/MODAL_TOTAL-1)*100:+.2f}%)")
for code,r in results.items():
    print(f"\n{code}: {r['n']} trade, win rate {r['win_rate']}%, "
          f"AI {r['pnl_pct']:+.2f}% vs Buy&Hold {r['buyhold_pct']:+.2f}%")
