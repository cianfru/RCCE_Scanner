import test from 'node:test';
import assert from 'node:assert/strict';
import { coinName, kBase } from '../data/coinNames.js';

test('k markets: base and name from either spelling; ordinary K tickers untouched', () => {
  for (const t of ['kPEPE', 'KPEPE', 'kpepe']) assert.equal(coinName(t), 'Pepe (per 1,000)', t);
  assert.equal(kBase('kSHIB'), 'SHIB');
  assert.equal(kBase('KLUNC'), 'LUNC');
  assert.equal(coinName('kDOGS'), 'Dogs (per 1,000)');
  assert.equal(kBase('kFOO'), 'FOO');                 // a k market Hyperliquid adds later
  assert.equal(coinName('kFOO'), 'FOO (per 1,000)');
  for (const t of ['KAS', 'KAITO', 'PEPE', 'BTC', '', null]) assert.equal(kBase(t), null);
  assert.equal(coinName('PEPE'), 'Pepe');
  assert.equal(coinName('BTC'), 'Bitcoin');
  assert.equal(coinName('KAS'), 'Kaspa');
});
