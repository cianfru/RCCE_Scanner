import test from 'node:test';
import assert from 'node:assert/strict';
import {notificationDigest} from './notificationDigest.js';
test('groups repeated market updates while prioritizing position risk and critical anomalies',()=>{
 const result=notificationDigest({warnings:[{symbol:'BTC/USDT',type:'risk',severity:'high'}],setups:[{symbol:'ETH/USDT',type:'trend'},{symbol:'ETH/USDT',type:'flow'}],anomalies:[{symbol:'SOL/USDT',dedup_key:'sol',severity:'critical'}]});
 assert.deepEqual(result.map(x=>x.symbol),['BTC/USDT','SOL/USDT','ETH/USDT']);
 assert.equal(result[2].entries.length,2);
 assert.equal(result[2].keys.length,2);
});
test('dismissals do not remove unrelated updates and exact spot identity survives',()=>{
 const result=notificationDigest({setups:[{symbol:'HFUN/USDC',type:'trend'},{symbol:'HFUN/USDC',type:'flow'}]},new Set(['setup:trend:HFUN/USDC']));
 assert.equal(result.length,1);assert.equal(result[0].symbol,'HFUN/USDC');assert.equal(result[0].entries.length,1);
});
test('uses actual anomaly context and type rather than generic placeholder text',()=>{
 const [row]=notificationDigest({anomalies:[{symbol:'VVV/USDT',dedup_key:'vvv-volume',anomaly_type:'VOLUME_SPIKE',context:'Relative volume 4.1x normal (z=6.5)',severity:'high'}]});
 assert.equal(row.title,'volume spike');assert.equal(row.entries[0].summary,'Relative volume 4.1x normal');assert.match(row.entries[0].text,/z=6.5/);
});
