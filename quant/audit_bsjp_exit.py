"""Reproducible exploratory BSJP exit comparison on cached public OHLCV.

OHLC path scenarios are sensitivity tests, NOT reconstructed tick executions.
No broker actions, production writes, or strategy promotion.
"""
import csv
import hashlib
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/bsjp_exit_audit_20261009'
JKT = timezone(timedelta(hours=7))
MODELS = ['OPEN', 'TP2.5_SL3', 'TP3.5_SL3', 'TRAIL2_ENTRY', 'TRAIL2_OPEN', 'SL3', 'TIME0915']

def load(ticker, interval):
    result = json.loads((OUT/f'{ticker}_{interval}.json').read_text())['chart']['result'][0]
    q = result['indicators']['quote'][0]
    rows = []
    for i, ts in enumerate(result.get('timestamp', [])):
        vals = {k: q[k][i] for k in ['open','high','low','close','volume']}
        if any(vals[k] is None or vals[k] <= 0 for k in ['open','high','low','close']):
            continue
        if vals['low'] > min(vals['open'],vals['close']) or vals['high'] < max(vals['open'],vals['close']):
            continue
        dt = datetime.fromtimestamp(ts,JKT)
        rows.append(dict(vals, date=str(dt.date()), time=dt.strftime('%H:%M'), timestamp=dt.isoformat()))
    return rows

def tick(price):
    return 1 if price < 200 else 2 if price < 500 else 5 if price < 2000 else 10 if price < 5000 else 25

def down(price):
    return math.floor((price+1e-9)/tick(price))*tick(price)

def up(price):
    return math.ceil((price-1e-9)/tick(price))*tick(price)

def simulate(entry, bars, model, order):
    opening = bars[0]['open']
    if model == 'OPEN':
        return opening, '09:00', 'open_proxy'
    if model == 'TIME0915':
        return bars[-1]['open'], '09:15', 'time_exit'
    trailing = model.startswith('TRAIL')
    peak = entry if model == 'TRAIL2_ENTRY' else opening
    target = up(entry*(1.025 if model == 'TP2.5_SL3' else 1.035)) if model.startswith('TP') else math.inf
    for b in bars:
        stop = down(peak*.98) if trailing else down(entry*.97)
        # Gap execution uses available opening price, never the skipped stop price.
        if b['open'] <= stop:
            return b['open'], b['time'], 'gap_stop'
        if b['open'] >= target:
            return b['open'], b['time'], 'gap_tp'
        if b['time'] == '09:15':
            return b['open'], b['time'], 'time_exit'
        nodes = [b['open'], b['high'], b['low'], b['close']] if order == 'OHLC' else [b['open'], b['low'], b['high'], b['close']]
        for price in nodes:
            if trailing:
                peak = max(peak,price)
                stop = down(peak*.98)
            if price <= stop:
                return stop, b['time'], 'stop'
            if price >= target:
                return target, b['time'], 'tp'
    raise ValueError('Missing deadline bar')

def pnl(entry, exit_price, lots, friction=0):
    cost = lots*100*entry*1.0015
    proceeds = lots*100*exit_price*.9975
    # Extra execution-cost sensitivity, not an assertion of limit fills below limit.
    net = proceeds - cost - lots*100*exit_price*friction
    return net, net/cost*100

def write_csv(path, rows):
    if rows:
        with path.open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def historical_audit():
    groups=defaultdict(list)
    for r in csv.DictReader((ROOT/'data/screener_20_stocks_historical.csv').open()):
        groups[r['ticker']].append(r)
    signals=[]
    for ticker,rows in groups.items():
        rows.sort(key=lambda r:r['date'])
        for i in range(1,len(rows)-1):
            r,p,n=rows[i],rows[i-1],rows[i+1]
            c,o,v=float(r['Close']),float(r['Open']),float(r['Volume'])
            pc,pv=float(p['Close']),float(p['Volume'])
            ma5=statistics.mean(float(x['Close']) for x in rows[i-4:i+1]) if i>=4 else math.inf
            ma10=statistics.mean(float(x['Close']) for x in rows[i-9:i+1]) if i>=9 else math.inf
            if pv>0 and v/pv>1 and c>o and c/pc>=1.03 and c*v>=1e8 and (c>=ma5 or c>=ma10):
                signals.append(dict(ticker=ticker,date=r['date'],entry=c,value=c*v,high=float(n['High']),low=float(n['Low']),open=float(n['Open']),close=float(n['Close'])))
    return dict(n=len(signals), high_above_entry_pct=100*statistics.mean(r['high']>r['entry'] for r in signals),mean_high_return_pct=100*statistics.mean(r['high']/r['entry']-1 for r in signals),close_gross_win_pct=100*statistics.mean(r['close']>r['entry'] for r in signals),ambiguous_tp25_sl25=sum(r['high']>=r['entry']*1.025 and r['low']<=r['entry']*.975 for r in signals), tickers=len(groups))

def main():
    tickers=sorted({r['ticker'] for r in csv.DictReader((ROOT/'data/screener_20_stocks_historical.csv').open())}|{'MCAS'})
    daily={t:load(t,'1d') for t in tickers}
    intraday={t:load(t,'5m') for t in tickers}
    sessions=sorted({r['date'] for rows in daily.values() for r in rows if r['date']<='2026-10-09'})
    nxt=dict(zip(sessions,sessions[1:]))
    candidates=[]; exclusions=[]; ranked=[]
    for t,rows in daily.items():
        bydate=defaultdict(dict)
        for b in intraday[t]:
            bydate[b['date']][b['time']]=b
        available=min(bydate)
        for i,r in enumerate(rows):
            if i==0 or r['date']<available or r['date'] not in nxt:
                continue
            prev=rows[i-1]
            if not prev['volume'] or not r['volume']:
                continue
            ratio=r['volume']/prev['volume']
            if not (ratio>=1.5 and r['close']>r['open'] and r['close']/prev['close']>=1.03 and r['close']*r['volume']>=1e8):
                continue
            exitday=nxt[r['date']]
            ranked.append(dict(ticker=t,date=r['date'],ratio=ratio,value=r['close']*r['volume']))
            bmap=bydate.get(exitday,{})
            needed=['09:00','09:05','09:10','09:15']
            if any(tm not in bmap for tm in needed):
                exclusions.append(dict(ticker=t,date=r['date'],exit_date=exitday,reason='incomplete_opening_bars'));continue
            bars=[bmap[tm] for tm in needed]
            candidates.append(dict(ticker=t,date=r['date'],exit_date=exitday,entry=r['close'],ratio=ratio,value=r['close']*r['volume'],bars=bars,zero_open_volume=not bars[0]['volume']))
    candidates.sort(key=lambda r:(r['date'],-r['ratio'],-r['value'],r['ticker']))
    # Ranking is on entry-day data, before the subsequent returns are examined.
    chosen={}
    for c in sorted(ranked,key=lambda r:(r['date'],-r['ratio'],-r['value'],r['ticker'])):
        chosen.setdefault(c['date'], c['ticker'])
    dates=sorted(chosen); split=dates[int(len(dates)*2/3)]
    records=[]
    for c in candidates:
        lots=math.floor(20_000_000/(100*c['entry']*1.0015))
        for model in MODELS:
            for order in ['OHLC','OLHC']:
                price,tm,reason=simulate(c['entry'],c['bars'],model,order)
                for friction in [0,.001,.003]:
                    rp,pct=pnl(c['entry'],price,lots,friction)
                    records.append(dict(ticker=c['ticker'],entry_date=c['date'],exit_date=c['exit_date'],entry=c['entry'],lots=lots,model=model,path=order,extra_cost_bps=int(friction*10000),exit_price=price,exit_time=tm,reason=reason,net_pct=pct,net_rp=rp,top1=c['ticker']==chosen[c['date']],period='late' if c['date']>=split else 'early',zero_open_volume=c['zero_open_volume']))
    summaries=[]
    for subset in ['all','top1']:
      for period in ['full','early','late']:
       for model in MODELS:
        for order in ['OHLC','OLHC']:
         for cost in [0,10,30]:
          rr=[r for r in records if r['model']==model and r['path']==order and r['extra_cost_bps']==cost and (subset=='all' or r['top1']) and (period=='full' or r['period']==period)]
          if not rr: continue
          vals=[r['net_pct'] for r in rr]; gains=sum(max(x,0) for x in vals); losses=-sum(min(x,0) for x in vals)
          summaries.append(dict(subset=subset,period=period,model=model,path=order,extra_cost_bps=cost,n=len(rr),mean_net_pct=statistics.mean(vals),median_net_pct=statistics.median(vals),win_pct=100*statistics.mean(x>0 for x in vals),worst_pct=min(vals),profit_factor=gains/losses if losses else None))
    write_csv(OUT/'exit_trades.csv',records);write_csv(OUT/'exit_summary.csv',summaries);write_csv(OUT/'excluded_signals.csv',exclusions)
    mcas=[r for r in load('MCAS','1m') if r['date']=='2026-10-09' and '09:00'<=r['time']<='09:15']
    write_csv(OUT/'MCAS_20261009_1m.csv',mcas)
    mresults=[]
    for model in MODELS:
        for order in ['OHLC','OLHC']:
            p,tm,why=simulate(284,mcas,model,order);rp,pct=pnl(284,p,703)
            mresults.append(dict(model=model,path=order,exit_price=p,time=tm,reason=why,net_pct=pct,net_rp=rp))
    write_csv(OUT/'MCAS_exit_scenarios.csv',mresults)
    metadata=dict(source='Yahoo Finance chart raw OHLCV; indicative secondary market data',historical_audit=historical_audit(),tickers=tickers,first_entry=min(c['date'] for c in candidates),last_entry=max(c['date'] for c in candidates),signals=len(candidates),dates=len(dates),late_start=split,excluded=len(exclusions),zero_open_volume=sum(c['zero_open_volume'] for c in candidates),sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*_*.json') if 'probe' not in p.name})
    (OUT/'audit_metadata.json').write_text(json.dumps(metadata,indent=2))
    print(json.dumps({k:v for k,v in metadata.items() if k!='sha256'},indent=2))
    for r in summaries:
        if r['period']=='full' and r['extra_cost_bps']==10:
            print(r)
    print('MCAS',json.dumps(mresults,indent=2))

if __name__=='__main__':
    main()
