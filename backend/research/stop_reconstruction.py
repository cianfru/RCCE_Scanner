"""Historical stop/re-entry reconstruction anchored to recorded entry candidates.
Prices and exits evolve from native 4H candles and logged signal states, rather
than keeping recorded exits. This cannot reproduce missing intrabar scan ticks
or create unrecorded entry opportunities. Run on a common complete-data cohort.
"""
import argparse,bisect,json,math
from pathlib import Path
from executor_shadow import volatility

EXITS={'TRIM','TRIM_HARD','NO_LONG','RISK_OFF'}
ENTRIES={'STRONG_LONG','LIGHT_LONG','ACCUMULATE','REVIVAL_SEED','LIGHT_SHORT'}


def stop_fill(pos,bar,mode):
    entry=pos['entry_price'];floor=entry*(1-pos['stop']);arm=pos.get('be_arm',.05)
    arm=math.inf if arm is None else arm
    armed=pos['peak']>=arm
    o,h,l,c=[float(bar[k])/pos['divisor'] for k in ('o','h','l','c')]
    if mode=='close':
        pos['peak']=max(pos['peak'],c/entry-1)
        if c<=floor:return c,'STOP_LOSS'
        if pos['peak']>=arm and c<=entry:return c,'BE_STOP'
        return None
    # Resolve two explicit OHLC orderings. Neither is a guaranteed performance bound.
    if o/entry-1>=arm:armed=True
    effective=entry if armed else floor
    if o<=effective:return o,'BE_STOP' if armed else 'STOP_LOSS'
    if mode=='high_then_low':
        armed=armed or h>=entry*(1+arm)
        effective=entry if armed else floor
        if l<=effective:return effective,'BE_STOP' if armed else 'STOP_LOSS'
    else:
        if l<=effective:return effective,'BE_STOP' if armed else 'STOP_LOSS'
        armed=armed or h>=entry*(1+arm)
        if armed and c<=entry:return entry,'BE_STOP'
    pos['peak']=max(pos['peak'],h/entry-1)
    return None


def prepare(rows,directory,events,asof):
    names={p.stem.upper():p for p in Path(directory).glob('*.json')}
    timelines={}
    for e in events:timelines.setdefault(e['symbol'],[]).append((e['timestamp'],e['id'],e['signal']))
    timelines={s:sorted(v) for s,v in timelines.items()}
    kept=[];excluded=[];markets={}
    for row in rows:
        if row.get('side','LONG')!='LONG':
            excluded.append({'id':row['id'],'symbol':row['symbol'],'reason':'Long-only reconstruction'})
            continue
        symbol=row['symbol'];base=symbol.split('/')[0]
        path=names.get(base) or names.get('K'+base)
        reason=None
        if not path or symbol.endswith('/BTC'):reason='No native market mapping'
        else:
            bars=json.loads(path.read_text());bars=[b for b in bars if b['T']/1000<=asof]
            entrybar=[b for b in bars if b['t']/1000<=row['entry_time']<=b['T']/1000]
            if len(entrybar)!=1:reason='No completed entry candle'
            else:
                b=entrybar[0];divs=[d for d in (1,1000) if float(b['l'])/d*.99<=row['entry_price']<=float(b['h'])/d*1.01]
                if len(divs)!=1:reason='Entry unit/range mismatch'
                else:
                    forward=[b for b in bars if b['t']/1000>row['entry_time']]
                    if not forward or asof-forward[-1]['T']/1000>14400 or any(y['t']-x['t']!=14400000 for x,y in zip(forward,forward[1:])):reason='Incomplete candle path through final snapshot'
                    else:
                        prior=[b for b in bars if b['T']/1000<=row['entry_time']][-15:]
                        data={'timestamp':[b['t'] for b in prior],'high':[float(b['h'])/divs[0] for b in prior],'low':[float(b['l'])/divs[0] for b in prior],'close':[float(b['c'])/divs[0] for b in prior]}
                        atr=volatility(data,row['entry_time'])
                        if not atr or atr<=0:reason='Insufficient pre-entry volatility history'
                        elif symbol not in timelines:reason='No signal history'
                        else:
                            kept.append({**row,'divisor':divs[0],'atr':atr});markets[symbol]=bars
        if reason:excluded.append({'id':row['id'],'symbol':symbol,'reason':reason})
    return kept,excluded,markets,timelines


def simulate(rows,markets,timelines,asof,rule,mode):
    signals={s:([e[0] for e in v],v) for s,v in timelines.items()}
    def state(symbol,t):
        ts,es=signals[symbol];i=bisect.bisect_right(ts,t)-1
        return es[i][2] if i>=0 else None
    events=[]
    for r in rows:events.append((r['entry_time'],1,'entry',r))
    for s,bars in markets.items():
        for b in bars:events.append((b['T']/1000,0,'bar',(s,b)))
    events.sort(key=lambda e:(e[0],e[1]))
    positions={};last_exit={};trades=[];skipped=[];realized=0.;fees=0.;peak=10000.;dd=0.;curve=[]
    def close(symbol,price,t,reason):
        nonlocal realized,fees
        p=positions.pop(symbol);pnl=p['cost']*(price/p['entry_price']-1)
        realized+=pnl;fees+=p['cost']*price/p['entry_price']*.0005
        trades.append({'id':p['id'],'symbol':symbol,'entry_time':p['entry_time'],'exit_time':t,'entry_price':p['entry_price'],'exit_price':price,'stop_pct':p['stop']*100,'cost':p['cost'],'pnl':pnl,'reason':reason})
        last_exit[symbol]=t
    for event_index,(t,_,kind,payload) in enumerate(events):
        if t>asof:continue
        if kind=='entry':
            r=payload;s=r['symbol'];reason=None
            if s in positions:reason='Position still open under reconstructed exits'
            elif rule not in ('baseline','baseline_no_be') and s in last_exit:
                last=last_exit[s]
                if t-last<14400:reason='Four-hour cooldown'
                else:
                    ts,es=signals[s];lo=bisect.bisect_right(ts,last);hi=bisect.bisect_right(ts,t)
                    if state(s,last) in ENTRIES and not any(e[2] not in ENTRIES for e in es[lo:hi]):reason='No signal reset'
            stop=.08
            if rule=='atr':stop=max(.04,min(.12,2*r['atr']/r['entry_price']))
            if rule in ('reset6','reset10','reset12'):stop={'reset6':.06,'reset10':.10,'reset12':.12}[rule]
            cost=r['cost']*min(1,.08/stop)
            cash=10000+realized-fees-sum(x['cost'] for x in positions.values())
            if cost*1.0005>cash:reason=reason or 'Insufficient virtual cash'
            if reason:skipped.append({'id':r['id'],'reason':reason});continue
            positions[s]={**r,'be_arm':None if rule in ('reset_no_be','baseline_no_be') else .10 if rule=='reset_be10' else .05,'stop':stop,'cost':cost,'peak':0.,'mark':r['entry_price']};fees+=cost*.0005
        else:
            s,b=payload;p=positions.get(s)
            if not p or b['T']/1000<=p['entry_time']:continue
            p['mark']=float(b['c'])/p['divisor']
            # Entry candle extremes include pre-entry prices; use only its close.
            fill=stop_fill(p,b,'close' if b['t']/1000<=p['entry_time'] else mode)
            if fill:close(s,fill[0],t,fill[1])
            elif state(s,t) in EXITS:close(s,p['mark'],t,state(s,t))
        if event_index+1<len(events) and events[event_index+1][0]==t:continue
        upnl=sum(x['cost']*(x['mark']/x['entry_price']-1) for x in positions.values())
        equity=10000+realized+upnl-fees;peak=max(peak,equity);dd=max(dd,(peak-equity)/peak*100)
        curve.append([t,equity])
    upnl=sum(x['cost']*(x['mark']/x['entry_price']-1) for x in positions.values())
    return {'rule':rule,'fill_mode':mode,'closed':len(trades),'open':len(positions),'skipped':len(skipped),'realized':realized,'unrealized':upnl,'combined':realized+upnl,'return_pct':(realized+upnl)/100,'estimated_costs':fees,'net':realized+upnl-fees,'sampled_max_drawdown_pct':dd,'trades':trades,'positions':positions,'skipped_entries':skipped,'curve':curve}


def main():
    p=argparse.ArgumentParser()
    for k in ('source','candles','signals','out'):p.add_argument('--'+k,required=True)
    a=p.parse_args();source=json.loads(Path(a.source).read_text());events=json.loads(Path(a.signals).read_text())
    rows,excluded,markets,timelines=prepare(source['rows'],a.candles,events,source['as_of'])
    variants=[simulate(rows,markets,timelines,source['as_of'],rule,mode) for mode in ('close','high_then_low','low_then_high') for rule in ('baseline','reset','reset6','reset10','reset12','atr','reset_be10','reset_no_be','baseline_no_be')]
    result={'as_of':source['as_of'],'included_candidates':len(rows),'excluded':excluded,'markets':len(markets),'recorded_cohort_pnl':sum(r['pnl'] for r in rows),'variants':variants}
    Path(a.out).write_text(json.dumps(result,indent=2))
    print(json.dumps({**{k:v for k,v in result.items() if k not in ('excluded','variants')},'exclusions':len(excluded),'variants':[{k:v for k,v in x.items() if k not in ('trades','positions','skipped_entries','curve')} for x in variants]},indent=2))

if __name__=='__main__':main()
