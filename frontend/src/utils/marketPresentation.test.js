import test from 'node:test';
import assert from 'node:assert/strict';
import {formatPercent, evidenceSummary, bestEntrySetups} from './marketPresentation.js';
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
