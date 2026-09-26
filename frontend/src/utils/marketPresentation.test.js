import test from 'node:test';
import assert from 'node:assert/strict';
import {formatPercent, evidenceSummary, bestEntrySetups, funding8hPct, hasCoinglass, signalAgreement} from './marketPresentation.js';
test('respects explicit API percentage units without multiplying twice',()=>{
 assert.equal(formatPercent(82),'82%');
 assert.equal(formatPercent(0.82,{ratio:true}),'82%');
 assert.equal(formatPercent(0.82,{digits:2}),'0.82%');
 assert.equal(formatPercent(null),'—');
 assert.equal(formatPercent(0),'0%');
});
test('explains disagreement without claiming a trade will succeed',()=>{
 const text=evidenceSummary({regime:'MARKUP',conditions_met:9,conditions_total:11,confluence:{regime_aligned:true,signal_aligned:false}});
 assert.match(text,/9 of 11/); assert.match(text,/signals differ/);
 assert.match(evidenceSummary({}),/not available/);
});

test('ranks eligible entries by existing score, without changing input order',()=>{
 const rows=[{symbol:'SOL',signal:'LIGHT_LONG',priority_score:70},{symbol:'BTC',signal:'WAIT',priority_score:99},{symbol:'ETH',signal:'ACCUMULATE',priority_score:80},{symbol:'LINK',signal:'STRONG_LONG',priority_score:null}];
 assert.deepEqual(bestEntrySetups(rows).map(r=>r.symbol),['ETH','SOL']);
 assert.equal(rows[0].symbol,'SOL');
});
test('shortlist respects lifecycle and includes confirmed shorts',()=>{
 const rows=[{symbol:'BTC',signal:'STRONG_LONG',priority_score:90,opportunity:{status:'expired'}},{symbol:'ETH',signal:'LIGHT_SHORT',priority_score:60,opportunity:{status:'confirmed'}},{symbol:'SOL',signal:'LIGHT_LONG',priority_score:70,signal_status:'unavailable'}];
 assert.deepEqual(bestEntrySetups(rows).map(r=>r.symbol),['ETH']);
});
test('hourly funding is shown per 8h in percent',()=>{
 assert.ok(Math.abs(funding8hPct(0.0000125)-0.01)<1e-12);assert.equal(funding8hPct(null),null);
});
test('CoinGlass fields count only when the feed is fresh and covers the market',()=>{
 const pos={source_map:{liq:'coinglass'}};
 assert.equal(hasCoinglass({input_quality:{coinglass:{status:'ready'}},positioning:pos}),true);
 assert.equal(hasCoinglass({input_quality:{coinglass:{status:'stale'}},positioning:pos}),false);
 assert.equal(hasCoinglass({input_quality:{coinglass:{status:'ready'}},positioning:{source_map:{}}}),false);
});
test('timeframe agreement is three-way and names the regimes',()=>{
 assert.equal(signalAgreement({signal_aligned:null,signal_4h:'WAIT',signal_1d:'WAIT'}),'waiting');
 assert.equal(signalAgreement({signal_aligned:false,signal_4h:'WAIT',signal_1d:'WAIT'}),'waiting');
 assert.equal(signalAgreement({signal_aligned:true,signal_4h:'LIGHT_LONG',signal_1d:'ACCUMULATE'}),'agree');
 assert.equal(signalAgreement({signal_aligned:false,signal_4h:'LIGHT_LONG',signal_1d:'TRIM'}),'differ');
 const text=evidenceSummary({regime:'REACC',conditions_met:8,conditions_total:11,confluence:{regime_aligned:true,regime_4h:'REACC',regime_1d:'ACCUM',signal_aligned:null,signal_4h:'WAIT',signal_1d:'WAIT'}});
 assert.match(text,/regimes agree \(both in the bullish family: Re-accumulating and Accumulation\)\. Both timeframes are waiting\./);
 assert.doesNotMatch(text,/while/);
});
