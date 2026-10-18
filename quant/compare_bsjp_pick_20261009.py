"""As-of afternoon candidate comparison. Daily signals, next-session open proxy."""
import csv
import json
import statistics as st
from datetime import datetime
import audit_bsjp_exit as a

OUT=a.ROOT/'output/bsjp_pick_20261009'
a.OUT=OUT
TICKERS=['BRRC','ARCI','GULA','ESSA','BRPT']

def stats(rr):
    v=[r['net_pct'] for r in rr]
    return dict(n=len(v),mean=st.mean(v) if v else None,median=st.median(v) if v else None,win=100*st.mean(x>0 for x in v) if v else None,worst=min(v) if v else None)

def main():
    details=[];summary=[];snap=[]
    histories={t:a.load(t,'1d') for t in TICKERS}
    dates=sorted({r['date'] for rows in histories.values() for r in rows})
    next_session=dict(zip(dates,dates[1:]))
    for t in TICKERS:
        rows=histories[t];gain=loss=None
        for i,r in enumerate(rows):
            if i:
                d=r['close']-rows[i-1]['close']
                if i==14:
                    ds=[rows[k]['close']-rows[k-1]['close'] for k in range(1,15)]
                    gain=st.mean(max(x,0) for x in ds);loss=st.mean(max(-x,0) for x in ds)
                elif i>14:
                    gain=(gain*13+max(d,0))/14;loss=(loss*13+max(-d,0))/14
            r['rsi']=100-100/(1+gain/loss) if loss else (100 if gain else None)
            r['ret']=100*(r['close']/rows[i-1]['close']-1) if i else 0
            r['ratio']=r['volume']/rows[i-1]['volume'] if i and rows[i-1]['volume'] else 0
            r['signal']=i>0 and r['close']>r['open'] and r['ret']>=3 and r['ratio']>=1.5 and r['close']*r['volume']>=1e8
            if i and rows[i-1]['signal'] and '2025-12-01'<=rows[i-1]['date']<'2026-10-09' and next_session[rows[i-1]['date']]==r['date']:
                p=rows[i-1];pct=100*((r['open']*.9965)/(p['close']*1.0015)-1)
                details.append(dict(ticker=t,entry_date=p['date'],exit_date=r['date'],entry=p['close'],exit_open=r['open'],net_pct=pct,friday=datetime.fromisoformat(p['date']).weekday()==4))
        rr=[r for r in details if r['ticker']==t]
        for period in ['full','early','late','friday']:
            subset=[r for r in rr if period=='full' or (period=='early' and r['entry_date']<'2026-07-01') or (period=='late' and r['entry_date']>='2026-07-01') or (period=='friday' and r['friday'])]
            summary.append(dict(ticker=t,period=period,**stats(subset)))
        r=rows[-1];prev=rows[-2];last20=rows[-21:-1]
        raw=json.loads((OUT/f'{t}_1m.json').read_text())['chart']['result'][0]
        meta=raw['meta'];bars=a.load(t,'1m');last=bars[-1]
        snap.append(dict(ticker=t,date=r['date'],daily_snapshot_price=r['close'],latest_1m_close=last['close'],latest_1m_time=last['timestamp'],quote_time=datetime.fromtimestamp(meta['regularMarketTime'],a.JKT).isoformat(),open=r['open'],high=r['high'],low=r['low'],return_pct=r['ret'],volume_ratio=r['ratio'],value_proxy=r['close']*r['volume'],rsi14=r['rsi'],sma5=st.mean(x['close'] for x in rows[-5:]),sma20=st.mean(x['close'] for x in rows[-20:]),prior20_high=max(x['high'] for x in last20),prior20_low=min(x['low'] for x in last20),close_location=(r['close']-r['low'])/(r['high']-r['low']) if r['high']>r['low'] else None,bsjp_signal=r['signal']))
    a.write_csv(OUT/'backtest_trades.csv',details);a.write_csv(OUT/'backtest_summary.csv',summary);a.write_csv(OUT/'technical_snapshot.csv',snap)
    print(json.dumps(dict(snapshot=snap,summary=summary),indent=2))

if __name__=='__main__':main()
