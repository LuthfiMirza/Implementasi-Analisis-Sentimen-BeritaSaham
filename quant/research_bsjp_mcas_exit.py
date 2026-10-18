"""MCAS-inspired hypotheses. In-sample research, not executable tick backtest."""
import csv
import json
import statistics
from collections import defaultdict
from audit_bsjp_exit import OUT, load, down, up, tick, pnl, simulate, write_csv

def candidate(entry, bars, model, path):
    if model in ('OPEN','TRAIL2_OPEN'):
        return simulate(entry,bars,model,path)
    if model.startswith('HALF_'):
        price,tm,why=candidate(entry,bars,model[5:],path)
        return (bars[0]['open']+price)/2,tm,'half_open+'+why
    tp=up(entry*(1.08 if model=='TP8' else 1.12)) if model.startswith('TP') else float('inf')
    activation=up(bars[0]['high']+tick(bars[0]['high']))
    trail=.015 if model=='BREAK1_TRAIL1.5' else .02
    active=False; peak=0; stop=down(entry*.97)
    for b in bars:
        o=b['open']
        if o<=stop: return o,b['time'],'gap_stop'
        if o>=tp: return o,b['time'],'gap_tp'
        if b['time']=='09:15': return o,b['time'],'deadline'
        ready=(model.startswith('BREAK1') and b['time']>'09:00') or (model=='WAIT2_TRAIL2' and b['time']>='09:02')
        if ready and not active and (model=='WAIT2_TRAIL2' or o>=activation):
            active=True;peak=o;stop=max(stop,down(peak*(1-trail)))
        nodes=[o,b['high'],b['low'],b['close']] if path=='OHLC' else [o,b['low'],b['high'],b['close']]
        for price in nodes:
            if price<=stop:return stop,b['time'],'stop'
            if price>=tp:return tp,b['time'],'tp'
            if ready and not active and price>=activation:
                active=True;peak=activation
            if active:
                peak=max(peak,price);stop=max(stop,down(peak*(1-trail)))
    raise ValueError('deadline missing')

def main():
    models=['OPEN','TRAIL2_OPEN','TP8','TP12','BREAK1_TRAIL2','BREAK1_TRAIL1.5','WAIT2_TRAIL2','HALF_BREAK1_TRAIL2']
    old=list(csv.DictReader((OUT/'exit_trades.csv').open()))
    signals=[r for r in old if r['model']=='OPEN' and r['path']=='OHLC' and r['extra_cost_bps']=='10']
    cache={};records=[];missing=[]
    for s in signals:
        t=s['ticker']
        if t not in cache:
            bydate=defaultdict(dict)
            for b in load(t,'1m'):bydate[b['date']][b['time']]=b
            cache[t]=bydate
        day=cache[t].get(s['exit_date'],{})
        times=[f'09:{i:02d}' for i in range(16)]
        if any(tm not in day for tm in times):
            missing.append(dict(ticker=t,date=s['exit_date'],reason='outside_1m_window_or_incomplete'));continue
        bars=[day[tm] for tm in times]
        for model in models:
            for path in ['OHLC','OLHC']:
                price,tm,why=candidate(float(s['entry']),bars,model,path)
                # Half scenario uses a 50/50 notional split; actual lot rounding not modelled.
                rp,pct=pnl(float(s['entry']),price,int(s['lots']),.001)
                records.append(dict(ticker=t,date=s['exit_date'],model=model,path=path,exit_price=price,time=tm,reason=why,net_pct=pct,net_rp=rp))
    summaries=[]
    for subset in ['all','without_MCAS']:
      for model in models:
       for path in ['OHLC','OLHC']:
        rr=[r for r in records if r['model']==model and r['path']==path and (subset=='all' or r['ticker']!='MCAS')]
        if rr:
            summaries.append(dict(subset=subset,model=model,path=path,n=len(rr),mean_net_pct=statistics.mean(r['net_pct'] for r in rr),median_net_pct=statistics.median(r['net_pct'] for r in rr),win_pct=100*statistics.mean(r['net_pct']>0 for r in rr)))
    write_csv(OUT/'mcas_hypotheses_trades.csv',records)
    write_csv(OUT/'mcas_hypotheses_summary.csv',summaries)
    write_csv(OUT/'mcas_hypotheses_missing.csv',missing)
    # Explicit user position, independent of Yahoo daily entry value.
    bars=[r for r in load('MCAS','1m') if r['date']=='2026-10-09' and '09:00'<=r['time']<='09:15']
    case=[]
    for model in models:
      for path in ['OHLC','OLHC']:
        price,tm,why=candidate(284,bars,model,path);rp,pct=pnl(284,price,703)
        case.append(dict(model=model,path=path,exit_price=price,time=tm,net_rp=rp,net_pct=pct))
    write_csv(OUT/'mcas_hypotheses_case.csv',case)
    print(json.dumps(dict(summaries=summaries,mcas=case),indent=2))

if __name__=='__main__':main()
