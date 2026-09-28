import test from 'node:test';
import assert from 'node:assert/strict';
import {signalContext, setupAlignment, signalDirection, marketWideMissing, friendlyReason, plainReason} from './signalPresentation.js';
import {candleChange, rangeRuler} from './chartPresentation.js';
test('missing core names and consequences are visible without a bearish verdict',()=>{
 const row={regime:'MARKUP',signal:'LIGHT_LONG',strong_long_blockers:['core context unavailable'],conditions_detail:[{group:'core',available:false,label:'Funding'}],signal_warnings:['Tracked-wallet consensus BULLISH by position size (conviction 80%)']};
 const c=signalContext(row);assert.equal(c[0].kind,'missing');assert.match(c[0].text,/Funding/);assert.match(c[0].text,/Strong Long/);assert.equal(c[1].kind,'bullish');assert.equal(setupAlignment(row).state,'incomplete');
});
test('bearish context supports shorts but conflicts with longs',()=>{
 assert.equal(signalContext({signal:'LIGHT_SHORT',signal_warnings:['Tracked-wallet consensus BEARISH by position size (conviction 40%)']})[0].kind,'bearish');
 assert.equal(signalContext({signal:'LIGHT_LONG',signal_warnings:['Tracked-wallet consensus BEARISH by position size (conviction 40%)']})[0].kind,'conflict');
 assert.equal(signalContext({signal:'STRONG_LONG',signal_warnings:['BEAR-DIV active — STRONG_LONG blocked']})[0].kind,'caution');
});
test('only actual entry signals earn directional alignment; transitions do not glow',()=>{
 assert.equal(setupAlignment({regime:'MARKUP',signal:'STRONG_LONG'}).strength,2);
 assert.equal(setupAlignment({regime:'MARKUP',signal:'LIGHT_LONG'}).strength,1);
 assert.equal(setupAlignment({regime:'MARKDOWN',signal:'LIGHT_SHORT'}).state,'bearish');
 for(const signal of ['TRIM','TRIM_HARD','NO_LONG','RISK_OFF','WAIT']) assert.equal(signalDirection(signal),null);
 for(const regime of ['BLOWOFF','CAP','ABSORBING','ACCUM','FLAT']) assert.equal(setupAlignment({regime,signal:'STRONG_LONG'}).strength,0);
 assert.equal(setupAlignment({regime:'MARKDOWN',signal:'LIGHT_LONG'}).state,'conflict');
 assert.equal(setupAlignment({regime:'MARKUP',signal:'STRONG_LONG',entry_blocked:true}).strength,0);
});
test('candle return is open to close and rejects invalid opens',()=>{
 assert.equal(candleChange({open:100,close:102}),2);assert.equal(candleChange({open:100,close:97}),-3);assert.equal(candleChange({open:0,close:10}),null);
});
test('range ruler illustrates total magnitude without doubling it',()=>{
 const r=rangeRuler(100,6);assert.equal(r.top-r.bottom,6);assert.equal(r.size,6);assert.equal(rangeRuler(0,6),null);assert.equal(rangeRuler(100,NaN),null);
});
test('stale candles read as a pause and withdrawn notes are not repeated',()=>{
 const c=signalContext({signal:'WAIT',signal_status:'unavailable',signal_reason:'Candle snapshot stale; new entries unavailable',signal_warnings:['REACC LIGHT_LONG demoted: no CVD/spot confirmation']});
 assert.equal(c.length,1);assert.equal(c[0].kind,'missing');assert.match(c[0].text,/paused/);
});
test('downgrades, forced exits and crowded positive funding are cautions, not neutral notes',()=>{
 for(const w of ['REACC LIGHT_LONG demoted: no CVD/spot confirmation (34% WR zone)','Heat at 96/95 — forced exit','Extreme funding: +120% annualized funding (0.01%/h) | hyperliquid only'])
  assert.equal(signalContext({signal:'WAIT',signal_warnings:[w]})[0].kind,'caution',w);
 assert.equal(signalContext({signal:'WAIT',signal_warnings:['Extreme funding: -90% annualized funding']})[0].kind,'info');
});
test('a core input missing across the market is reported once, not per row',()=>{
 const row={regime:'MARKUP',signal:'LIGHT_LONG',strong_long_blockers:['core context unavailable'],conditions_detail:[{group:'core',available:false,label:'Not Greedy'}]};
 const rows=Array.from({length:20},()=>row);
 assert.deepEqual(marketWideMissing(rows),['Not Greedy']);
 assert.equal(signalContext(row,{marketWide:['Not Greedy']}).some(i=>i.kind==='missing'),false);
 assert.equal(setupAlignment(row,{marketWide:['Not Greedy']}).state,'bullish');
 assert.equal(signalContext(row).some(i=>i.kind==='missing'),true);
 assert.deepEqual(marketWideMissing(rows.slice(0,5)),[]);
});
test('spot funding is not applicable: no market-wide banner and no per-row missing note',()=>{
 const row={market_kind:'spot',regime:'MARKUP',signal:'LIGHT_LONG',strong_long_blockers:['core context unavailable'],conditions_detail:[{group:'core',available:false,name:'funding_ok',label:'Funding OK'}]};
 const rows=Array.from({length:20},()=>row);
 assert.deepEqual(marketWideMissing(rows),[]);
 assert.equal(signalContext(row).some(i=>i.kind==='missing'),false);
 assert.equal(setupAlignment(row).state,'bullish');
 const perp={...row,market_kind:'perpetual'};
 assert.deepEqual(marketWideMissing(Array.from({length:20},()=>perp)),['Funding OK']);
 assert.equal(signalContext(perp).some(i=>i.kind==='missing'),true);
});
test('a BMSB block names the band, not the entry checks',()=>{
 const macro=signalContext({signal:'WAIT',entry_blocked:true,signal_reason:'Macro blocked (BMSB bearish) — MARKUP regime, long entries blocked'});
 assert.match(macro[0].text,/below the weekly bull-market support band/);
 const nodata=signalContext({signal:'WAIT',entry_blocked:true,signal_reason:'BMSB data unavailable (weekly history too short) — ACCUM regime, all entries blocked'});
 assert.match(nodata[0].text,/not enough weekly history/);
 assert.match(signalContext({signal:'WAIT',entry_blocked:true,signal_reason:'Exhaustion climax detected'})[0].text,/Inspect the entry checks/);
});
test('engine codes and win-rate tallies are rewritten for readers',()=>{
 const c=signalContext({signal:'ACCUMULATE',signal_warnings:['REACC LIGHT_LONG demoted: no CVD/spot confirmation (34% WR zone)']});
 assert.equal(c[0].text,'Held at Accumulate: no taker-buying confirmation');assert.equal(c[0].kind,'caution');
 assert.equal(friendlyReason('Late entry (40.7% WR zone) in MARKUP'),'Late entry in MARKUP');
});
test('plainReason turns engine reason strings into plain words', () => {
 const a = plainReason('MARKUP + z=2.14 + conf=100% + consensus=RISK-ON + heat=5 + vs=1.15 [MARKUP extended]');
 assert.equal(a, 'Uptrend · Stretched above its mean · 100% regime confidence · Market risk-on · Heat 5 · Uptrend extended');
 const b = plainReason('ZEREBRO + z=0.10 + conf=41% [13/15 cond, 11.8/13 eff (90%) MARKUP-strict]'.replace('ZEREBRO', 'ACCUM'));
 assert.equal(b, 'Accumulation · Near its mean · 41% regime confidence · 13 of 15 entry checks');
 assert.match(plainReason('REACC + z=-1.24 + conf=92% + consensus=MIXED + heat=7 [REACC no CVD demand → ACCUMULATE]'), /held at Accumulate$/);
 assert.match(plainReason('REACC + z=-0.28 + conf=32% + wallets=BULLISH(6%) [7.5/10 effective (75%) — insufficient]'), /Tracked wallets bullish \(6%\) · Entry checks 75%, not enough for an entry$/);
 assert.equal(plainReason('Macro blocked (BMSB bearish) — REACC regime, long entries blocked'), 'Long entries blocked: price is below the weekly bull-market support band (BMSB).');
 assert.equal(plainReason('[Agent] Squeeze setup: -73% annualized funding (z=-3.0, 14.1σ vs history) | confirmed: hyperliquid: -84%, binance: -73%'), 'Squeeze setup: -73% annualized funding · confirmed on Hyperliquid: -84%, Binance: -73%');
 assert.equal(plainReason('smart_money_long(lsr=2.51)'), 'Smart money long (long/short 2.51)');
 assert.equal(plainReason('REACC LIGHT_LONG demoted: no CVD/spot confirmation (34% WR zone)'), 'Held at Accumulate: no taker-buying confirmation');
 assert.equal(plainReason(''), '');
 for (const s of [a, b]) assert.doesNotMatch(s, /z=|conf=|\+ /);
});
