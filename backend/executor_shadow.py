"""Forward-only virtual portfolios. No trading engine or network dependencies.
Versioned state, fixed entry stops and equal starting capital. Uses observed
scan prices (not guaranteed stop fills); paper costs are sensitivity estimates.
"""
import hashlib
import json
import math
import os
from pathlib import Path

VERSION = 'reset-4h-atr14-v1'
CONFIGS = {
    'baseline': {'label': 'Baseline · 8% stop', 'reset': False, 'atr': False},
    'reset_4h': {'label': 'Signal reset + 4h · 8% stop', 'reset': True, 'atr': False},
    'reset_4h_atr': {'label': 'Signal reset + 4h · volatility stop', 'reset': True, 'atr': True},
}
EXIT_SIGNALS = {'TRIM','TRIM_HARD','NO_LONG','RISK_OFF'}


def finite(x):
    return isinstance(x,(float,int)) and math.isfinite(x)


def volatility(data, now):
    """14-bar arithmetic mean true range, closed 4H candles only (not Wilder ATR)."""
    if data is None:return None
    indices=[i for i,t in enumerate(data['timestamp']) if float(t)/1000+14400 <= now][-15:]
    if len(indices)<15:return None
    values=[]
    for a,b in zip(indices,indices[1:]):
        if float(data['timestamp'][b])-float(data['timestamp'][a])!=14400000:return None
        high,low,previous=map(float,(data['high'][b],data['low'][b],data['close'][a]))
        if not all(finite(v) and v>0 for v in (high,low,previous)) or high<low:return None
        values.append(max(high-low,abs(high-previous),abs(low-previous)))
    return sum(values)/14


class ShadowStudy:
    def __init__(self,path,capital,sizing):
        self.path=Path(path);self.capital=capital;self.sizing=sizing;self.error=None
        self.signature=hashlib.sha256(json.dumps({'version':VERSION,'capital':capital,'sizing':sizing},sort_keys=True).encode()).hexdigest()
        self.state=None;self.last_saved=0
        if self.path.exists():
            try:
                self.state=json.loads(self.path.read_text())
                if self.state.get('signature')!=self.signature:raise ValueError('configuration differs from saved experiment')
                if set(self.state['portfolios'])!=set(CONFIGS):raise ValueError('incomplete saved experiment')
                for p in self.state['portfolios'].values():
                    for k in ('positions','last_exit','reset_seen','skipped'):
                        if not isinstance(p[k],dict):raise ValueError('invalid saved portfolio maps')
                    if not isinstance(p['trades'],list):raise ValueError('invalid saved trade list')
                    for k in ('realized','closed','fees','peak_equity','max_drawdown_pct'):
                        if not finite(p[k]):raise ValueError('invalid saved portfolio metrics')
                    if p['peak_equity']<=0:raise ValueError('invalid saved equity peak')
                    for pos in p['positions'].values():
                        for k in ('entry','cost','entry_time','stop_fraction','stop_price','peak','mark','observed_at','planned_risk_usd'):
                            if not finite(pos[k]):raise ValueError('invalid saved position')
                        if pos['entry']<=0 or pos['cost']<=0 or not 0<pos['stop_fraction']<1:raise ValueError('invalid saved entry or stop')
            except (OSError,ValueError,KeyError,TypeError) as exc:
                self.state=None
                self.error=f'Shadow study paused: {exc}. Saved state was not overwritten.'

    def process(self,rows,eligible,market_data,now,allocation_count=None):
        if self.error:return
        if self.state is None:
            if not eligible:return
            self.state={'version':VERSION,'signature':self.signature,'started_at':now,'last_update':now,'eligible_count':len(eligible),'portfolios':{k:{'positions':{},'last_exit':{},'reset_seen':{},'realized':0.,'closed':0,'fees':0.,'peak_equity':self.capital,'max_drawdown_pct':0.,'skipped':{},'trades':[]} for k in CONFIGS}}
        events=False
        self.state['last_update']=now;self.state['eligible_count']=len(eligible)
        for row in rows:
            symbol=row.get('symbol');signal=row.get('signal','WAIT');price=row.get('price')
            md=market_data.get(symbol,{})
            observed=md.get('observed_at')
            if not finite(price) or price<=0 or not finite(observed) or not 0<=now-observed<=21600:continue
            conf=row.get('confluence',{});conf=conf.get('label','UNKNOWN') if isinstance(conf,dict) else 'UNKNOWN'
            # Current experiment is long-only, matching the audited portfolios.
            entry=signal in self.sizing and signal!='LIGHT_SHORT'
            for key,config in CONFIGS.items():
                p=self.state['portfolios'][key];pos=p['positions'].get(symbol)
                if not entry:p['reset_seen'][symbol]=True
                if pos:
                    pos['mark']=price;pos['observed_at']=observed
                    move=price/pos['entry']-1;pos['peak']=max(pos['peak'],move)
                    reason='STOP_LOSS' if move<=-pos['stop_fraction'] else 'BE_STOP' if pos['peak']>=.05 and move<=0 else signal if signal in EXIT_SIGNALS else None
                    if reason:
                        pnl=pos['cost']*move;fee=pos['cost']*(price/pos['entry'])*.0005
                        p['realized']+=pnl;p['fees']+=fee;p['closed']+=1
                        p['trades'].append({**pos,'symbol':symbol,'exit_time':now,'exit_price':price,'exit_signal':reason,'pnl_usd':pnl,'exit_cost_estimate':fee})
                        p['trades']=p['trades'][-200:]
                        del p['positions'][symbol];p['last_exit'][symbol]=now;p['reset_seen'][symbol]=not entry;events=True
                    continue
                if symbol not in eligible or not entry:continue
                rejection=None
                if config['reset'] and symbol in p['last_exit']:
                    if now-p['last_exit'][symbol]<14400:rejection='Cooldown'
                    elif not p['reset_seen'].get(symbol,False):rejection='Awaiting signal reset'
                stop=.08;atr=md.get('atr')
                if config['atr']:
                    if not finite(atr) or atr<=0:rejection=rejection or 'Missing completed-candle volatility'
                    else:stop=max(.04,min(.12,2*atr/price))
                cost=self.capital/max(1,allocation_count if allocation_count is not None else len(eligible))*self.sizing[signal].get(conf,0)
                if config['atr']:cost*=min(1,.08/stop)
                available=self.capital+p['realized']-p['fees']-sum(x['cost'] for x in p['positions'].values())
                if cost<5:rejection=rejection or 'Below minimum size'
                elif cost*1.0005>available:rejection=rejection or 'Insufficient virtual cash'
                if rejection:
                    # State reason per symbol; repeated scans do not inflate trade counts.
                    p['skipped'][symbol]=rejection;continue
                p['skipped'].pop(symbol,None)
                p['positions'][symbol]={'entry':price,'cost':cost,'entry_time':now,'signal':signal,'confluence':conf,'stop_fraction':stop,'stop_price':price*(1-stop),'atr_at_entry':atr if config['atr'] else None,'peak':0.,'mark':price,'observed_at':observed,'planned_risk_usd':cost*stop}
                p['fees']+=cost*.0005;p['reset_seen'][symbol]=False;events=True
        for p in self.state['portfolios'].values():
            if all(0<=now-x['observed_at']<=21600 for x in p['positions'].values()):
                equity=self.capital+p['realized']+sum(x['cost']*(x['mark']/x['entry']-1) for x in p['positions'].values())-p['fees']
                p['peak_equity']=max(p['peak_equity'],equity)
                p['max_drawdown_pct']=max(p['max_drawdown_pct'],100*(p['peak_equity']-equity)/p['peak_equity'])
        if events or now-self.last_saved>=60:
            try:
                self.path.parent.mkdir(parents=True,exist_ok=True)
                temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(self.state,allow_nan=False));os.replace(temporary,self.path);self.last_saved=now
            except (OSError,ValueError) as exc:self.error=f'Shadow persistence failed; experiment paused: {exc}'

    def status(self,now):
        result={'version':VERSION,'error':self.error,'started_at':self.state['started_at'] if self.state else None,'capital':self.capital,'long_only':True,'portfolios':[]}
        if not self.state:return result
        result['last_update']=self.state['last_update'];result['eligible_count']=self.state['eligible_count']
        for key,p in self.state['portfolios'].items():
            fresh=all(0<=now-x['observed_at']<=21600 for x in p['positions'].values())
            upnl=sum(x['cost']*(x['mark']/x['entry']-1) for x in p['positions'].values())
            total=p['realized']+upnl
            result['portfolios'].append({'id':key,'label':CONFIGS[key]['label'],'closed':p['closed'],'open':len(p['positions']),'realized':p['realized'],'unrealized':upnl if fresh else None,'combined':total if fresh else None,'net_estimate':total-p['fees'] if fresh else None,'return_pct':100*total/self.capital if fresh else None,'max_drawdown_pct':p['max_drawdown_pct'],'cost_estimate':p['fees'],'fresh':fresh,'waiting':p['skipped'],'positions':p['positions'],'recent_trades':p['trades']})
        return result
