"""Download public research inputs locally, without starting the trading engine.

Caches native 4H candles and paginated 4H signal transitions. Candle requests
are spaced five seconds apart; rate limits stop downloads for a later retry.
No exchange fallback or guessed token migration. Supply exported read-only
executor status and trades snapshots. Run --help for arguments.
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path


def request(url, body=None):
    req=urllib.request.Request(url,data=json.dumps(body).encode() if body else None,
                               headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)


def main():
    p=argparse.ArgumentParser()
    for key in ('status','trades','out'):p.add_argument('--'+key,required=True)
    p.add_argument('--api',default='https://rccescanner-production.up.railway.app')
    args=p.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    status=json.loads(Path(args.status).read_text());trades=json.loads(Path(args.trades).read_text())['trades']
    records=trades+list(status['positions'].values())
    info='https://api.hyperliquid.xyz/info'
    meta=request(info,{'type':'meta'});(out/'meta.json').write_text(json.dumps(meta))
    names={r['name'].upper():r['name'] for r in meta['universe']}
    first=int(min(x['entry_time'] for x in records)*1000)-14400000
    end=int(status['last_execution_time']*1000)
    coverage={}
    for symbol in sorted({r['symbol'] for r in records}):
        base=symbol.split('/')[0];coin=names.get(base) or names.get('K'+base)
        if not coin or symbol.endswith('/BTC'):coverage[symbol]='unmapped';continue
        path=out/(coin+'.json')
        if not path.exists():
            data=request(info,{'type':'candleSnapshot','req':{'coin':coin,'interval':'4h','startTime':first,'endTime':end}})
            path.write_text(json.dumps(data));time.sleep(5)
        coverage[symbol]=len(json.loads(path.read_text()))
    (out/'coverage.json').write_text(json.dumps(coverage,indent=2))
    events={};offset=0
    while True:
        path=out/f'events-{offset}.json'
        if not path.exists():
            page=request(args.api+'/api/signals/history?timeframe=4h&limit=200&offset='+str(offset))
            path.write_text(json.dumps(page));time.sleep(.5)
        page=json.loads(path.read_text())
        for event in page['events']:events[event['id']]=event
        if not page['events']:break
        offset+=200
    (out/'signals.json').write_text(json.dumps(list(events.values())))
    print('Markets:',len(coverage),'signal transitions:',len(events))

if __name__=='__main__':main()
