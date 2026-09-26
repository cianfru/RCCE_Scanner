import test from 'node:test';
import assert from 'node:assert/strict';
import {formatPercent, formatPrice, evidenceSummary, bestEntrySetups, funding8hPct, hasCoinglass} from './marketPresentation.js';
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
test('prices carry separators and no fake precision',()=>{
 assert.equal(formatPrice(84131),'$84,131.00');
 assert.equal(formatPrice(14.87),'$14.87');
 assert.equal(formatPrice(99.175),'$99.18');
 assert.equal(formatPrice(0.012345),'$0.01235');
 assert.equal(formatPrice(0.0000000123),'$0.0000000123');
 assert.equal(formatPrice(null),'—');
});
