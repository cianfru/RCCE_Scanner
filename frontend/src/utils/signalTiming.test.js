import test from 'node:test';
import assert from 'node:assert/strict';
import { signalCandleTime } from './signalTiming.js';
const day = 86400;
const candles = Array.from({length:31},(_,i)=>({time:(100+i)*day}));
test('anchors a 25-day-old signal to its recorded candle, not today',()=>{
  assert.equal(signalCandleTime(candles,105*day+3600,day),105*day);
});
test('maps 4H boundaries to the containing candle',()=>{
  assert.equal(signalCandleTime([{time:day},{time:day+14400}],day+14400,14400),day+14400);
});
test('does not invent timestamps for missing history, gaps, or unknown times',()=>{
  for (const ts of [null,undefined,NaN,0,99*day,132*day]) assert.equal(signalCandleTime(candles,ts,day),null);
  assert.equal(signalCandleTime([{time:day},{time:3*day}],2*day+100,day),null);
});
