"""Read-only, fixed-trade-path sensitivity study; NOT a full strategy backtest.

Usage: PYTHONPATH=backend python backend/research/reentry_replay.py \
  --trades trades.json --performance performance.json --candles candle_dir --out result.json
Recorded sizes/exits/terminal marks stay fixed. Skipped entries do not reset the
cooldown; only exits of accepted positions do. No capital redistribution and no
synthetic new signals. Candle horizons diagnose paths, not achievable returns.
"""
import argparse
import bisect
import hashlib
import json
import math
import statistics
from pathlib import Path
from executor_ledger_audit import closure_issue


def candidates(trades, performance):
    rows=[]
    for index,t in enumerate(trades):
        if closure_issue(t): continue
        if not all(isinstance(t.get(k),(int,float)) and math.isfinite(t[k]) for k in ('pnl_usd','entry_time','exit_time','entry_price','exit_price')): continue
        cost=t.get('cost_usd')
        if cost is None:
            cost=t['pnl_usd']/(t['pnl_pct']/100) if t.get('pnl_pct') else t['volume']*t['entry_price']
        rows.append({**t,'id':'closed-'+str(index),'cost':cost,'pnl':t['pnl_usd'],'open':False})
    for index,p in enumerate(performance['positions']):
        if p.get('valuation_issue') or p.get('unrealized_pnl_usd') is None:continue
        rows.append({**p,'id':'open-'+str(index),'cost':p['cost_usd'],'pnl':p['unrealized_pnl_usd'], 'exit_time':performance['as_of'],'exit_price':p['mark_price'],'open':True})
    return sorted(rows,key=lambda t:(t['entry_time'],t['id']))


def select(rows, hours=0, first_only=False, loss_only=False, resets=None):
    last_exit={};seen=set();kept=[];skipped=[]
    for row in rows:
        symbol=row['symbol'];previous=last_exit.get(symbol)
        reject=first_only and symbol in seen
        if previous:
            ended,pnl=previous
            reject |= row['entry_time'] < ended
            if resets is not None:
                timestamps=resets.get(symbol,[])
                # Events have integer-second timestamps; include the exit scan.
                left=bisect.bisect_left(timestamps,int(ended))
                reject |= left == len(timestamps) or timestamps[left] > row['entry_time']
            if not loss_only or pnl < 0:
                reject |= row['entry_time'] < ended+hours*3600
        if reject:skipped.append(row);continue
        kept.append(row);seen.add(symbol)
        last_exit[symbol]=(row['exit_time'],row['pnl'])
    return kept,skipped


def summary(rows, skipped, capital):
    realized=sum(t['pnl'] for t in rows if not t['open']);unrealized=sum(t['pnl'] for t in rows if t['open'])
    # Cost sensitivity reserves entry + exit/terminal-liquidation costs, including
    # open positions. It is not an assertion about any exchange's actual fee tier.
    turnover=sum(t['cost']*(1+t['exit_price']/t['entry_price']) for t in rows)
    total=realized+unrealized
    return dict(closed=sum(not t['open'] for t in rows),open=sum(t['open'] for t in rows),skipped=len(skipped),realized=realized,unrealized=unrealized,total=total,return_pct=100*total/capital,
        net_5bps=total-turnover*.0005,net_10bps=total-turnover*.001,
        skipped_positive=sum(max(0,t['pnl']) for t in skipped),skipped_negative=sum(min(0,t['pnl']) for t in skipped),
        kept_ids=[t['id'] for t in rows],skipped_ids=[t['id'] for t in skipped])


def horizon_returns(row,bars,as_of):
    """Use full 4H candle closes only; infer no intrabar order or signal resets."""
    entry_ms=row['entry_time']*1000
    containing=[b for b in bars if b['t']<=entry_ms<=b['T']]
    if len(containing)!=1:return None
    b=containing[0];entry=row['entry_price']
    # Validate units separately per recorded entry (legacy k-contract mix).
    divisors=[d for d in (1,1000) if float(b['l'])/d*.99<=entry<=float(b['h'])/d*1.01]
    if len(divisors)!=1:return None
    divisor=divisors[0];out={}
    for days in (1,7,30):
        target=entry_ms+days*86400000
        if target>as_of*1000:continue
        path=[c for c in bars if c['t']>entry_ms and c['T']<=target]
        if not path or target-path[-1]['T']>14400000:continue
        if path[0]['t']-entry_ms>14400000:continue
        if any(right['t']-left['t']!=14400000 for left,right in zip(path,path[1:])):continue
        price=float(path[-1]['c'])/divisor
        out[str(days)]=(price/entry-1)*100*(1 if row.get('side','LONG')=='LONG' else -1)
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--signals')
    for name in ('trades','performance','candles','out'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();performance=json.loads(Path(args.performance).read_text())
    rows=candidates(json.loads(Path(args.trades).read_text())['trades'],performance)
    variants={}
    configs=[('baseline',0,False,False)]+[(f'cooldown_{h}h',h,False,False) for h in (4,24,48,168)]+[('loss_cooldown_24h',24,False,True),('one_entry_per_token',0,True,False)]
    for name,h,first,loss in configs:
        kept,skipped=select(rows,h,first,loss);variants[name]=summary(kept,skipped,performance['initial_balance_usd'])
    signal_coverage=None
    if args.signals:
        events=json.loads(Path(args.signals).read_text())
        resets={}
        entry_signals={'STRONG_LONG','LIGHT_LONG','ACCUMULATE','REVIVAL_SEED','LIGHT_SHORT'}
        for event in events:
            if event['signal'] not in entry_signals:
                resets.setdefault(event['symbol'],[]).append(event['timestamp'])
        # A non-entry state already active at an exit also constitutes a reset;
        # the logger records transitions, not one state row per scan.
        timelines={}
        for event in events:
            timelines.setdefault(event['symbol'],[]).append((event['timestamp'],event['id'],event['signal']))
        timelines={s:sorted(v) for s,v in timelines.items()}
        matches=0;known=0
        for row in rows:
            timeline=timelines.get(row['symbol'],[])
            ts=[e[0] for e in timeline]
            at_entry=bisect.bisect_right(ts,int(row['entry_time']))-1
            if at_entry>=0:
                known+=1;matches+=timeline[at_entry][2]==row['entry_signal']
            at_exit=bisect.bisect_right(ts,int(row['exit_time']))-1
            if at_exit>=0 and timeline[at_exit][2] not in entry_signals:
                resets.setdefault(row['symbol'],[]).append(int(row['exit_time']))
        resets={s:sorted(set(v)) for s,v in resets.items()}
        signal_coverage={'known_entry_states':known,'matching_entry_states':matches,'events':len(events)}
        for name,h in [('signal_reset',0),('signal_reset_4h',4)]:
            kept,skipped=select(rows,h,resets=resets)
            variants[name]=summary(kept,skipped,performance['initial_balance_usd'])
    paths={};coverage=[]
    for row in rows:
        base=row['symbol'].split('/')[0]
        files=[f for f in Path(args.candles).glob('*.json') if f.stem.upper() in (base,'K'+base)]
        if len(files)!=1 or row['symbol'].endswith('/BTC'):continue
        bars=json.loads(files[0].read_text())
        path=horizon_returns(row,bars,performance['as_of'])
        if path is not None: paths[row['id']]=path;coverage.append(row['id'])
    for v in variants.values():
        v['skipped_price_paths']={}
        for days in ('1','7','30'):
            vals=[paths[i][days] for i in v['skipped_ids'] if days in paths.get(i,{})]
            v['skipped_price_paths'][days]={'count':len(vals),'median_return_pct':statistics.median(vals) if vals else None,'positive':sum(x>0 for x in vals)}
    # Descriptive time cohorts, NOT unseen validation: all outcomes end at the
    # same snapshot and the historical executor may have changed during the period.
    first=min(t['entry_time'] for t in rows);split=first+(performance['as_of']-first)*2/3
    for v in variants.values():
        kept=[t for t in rows if t['id'] in v['kept_ids']]
        v['entry_cohorts']={label:sum(t['pnl'] for t in kept if (t['entry_time']>=split)==later) for label,later in [('first_two_thirds',False),('last_third',True)]}
    manifest={name:hashlib.sha256(Path(value).read_bytes()).hexdigest() for name,value in [('trades',args.trades),('performance',args.performance),('signals',args.signals)] if value}
    candle_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(args.candles).glob('*.json') if not f.name.startswith(('events-','signal','coverage','meta'))}
    result={'candle_sha256':candle_hashes,'signal_coverage':signal_coverage,'input_sha256':manifest,'as_of':performance['as_of'],'candidate_count':len(rows),'validated_price_entries':len(coverage),'variants':variants,'rows':rows,'paths':paths,'cohort_split':split}
    Path(args.out).write_text(json.dumps(result,indent=2))
    print(json.dumps({name:{k:v for k,v in val.items() if k not in ('kept_ids','skipped_ids')} for name,val in variants.items()},indent=2))

if __name__=='__main__':main()
