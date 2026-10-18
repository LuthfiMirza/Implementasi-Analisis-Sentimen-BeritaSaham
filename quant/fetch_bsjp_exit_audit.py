"""Download public, unadjusted Yahoo chart bars; never modifies trading records."""
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/bsjp_exit_audit_20261009'

def fetch(job):
    ticker, interval, period = job
    path = OUT / f'{ticker}_{interval}.json'
    info = dict(ticker=ticker, interval=interval, retrieved_utc=datetime.now(timezone.utc).isoformat())
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.JK'
    info['url'] = url
    info['params'] = dict(range=period, interval=interval)
    try:
        r = requests.get(url, params=info['params'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=25)
        info['status'] = r.status_code
        r.raise_for_status()
        data = r.json()
        result = data['chart']['result'][0]
        info['bars'] = len(result.get('timestamp', []))
        path.write_text(json.dumps(data))
    except Exception as e:
        info['error'] = str(e)
    return info

if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    tickers = sorted({r['ticker'] for r in csv.DictReader((ROOT/'data/screener_20_stocks_historical.csv').open())} | {'MCAS'})
    jobs = [(t, i, p) for t in tickers for i, p in [('5m','60d'), ('1d','6mo')]] + [('MCAS','1m','7d')]
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(fetch, jobs))
    (OUT/'download_manifest.json').write_text(json.dumps(records, indent=2))
    for r in records:
        print(r['ticker'], r['interval'], r.get('bars', r.get('error')))
