import test from 'node:test';
import assert from 'node:assert/strict';
import { coinEntries, coinTier, editDistance, parseHlMarkets, isFullAddress, searchAll, searchCoins, searchTraders } from './search.js';
import { codename } from './walletName.js';

const entry = (ticker, name, volume) => ({ kind: 'coin', key: ticker, ticker, name, volume, oi: 0 });
const COINS = [
  entry('BTC', 'Bitcoin', 900), entry('BCH', 'Bitcoin Cash', 50), entry('AR', 'Arweave', 5), entry('ARB', 'Arbitrum', 40),
  entry('NEAR', 'NEAR Protocol', 30), entry('HBAR', 'Hedera', 20), entry('ADA', 'Cardano', 60), entry('FET', 'Fetch.ai', 10), entry('LTC', 'Litecoin', 70),
];

test('tiers: exact ticker, ticker prefix, name prefix, contains, typo', () => {
  assert.equal(coinTier('ar', 'AR', 'Arweave'), 0);
  assert.equal(coinTier('ar', 'ARB', 'Arbitrum'), 1);
  assert.equal(coinTier('ar', 'XX', 'Artificial Superintelligence Alliance'), 2);
  assert.equal(coinTier('ar', 'ADA', 'Cardano'), 3);
  assert.equal(coinTier('bitcon', 'BTC', 'Bitcoin'), 4);
  assert.equal(coinTier('zz', 'BTC', 'Bitcoin'), null);
});

test('ranking: tier first, then volume', () => {
  assert.deepEqual(searchCoins('ar', COINS).map(c => c.ticker), ['AR', 'ARB', 'ADA', 'NEAR', 'HBAR']);
  assert.deepEqual(searchCoins('bitcoin', COINS).map(c => c.ticker), ['BTC', 'BCH']);
  assert.equal(searchCoins('bitcon', COINS)[0].ticker, 'BTC');
});

test('typos: none under four letters', () => {
  assert.equal(editDistance('bitcon', 'bitcoin'), 1);
  assert.equal(editDistance('ehtereum', 'ethereum'), 1);
  assert.deepEqual(searchCoins('btx', COINS), []);
});

test('traders: codename from three letters; an address is one row', () => {
  const a = '0x77375a8c9d13bf79afb2a87f1b0ac1dfd5f5bf66';
  const word = codename(a).split(' ')[1].toLowerCase();
  assert.deepEqual(searchTraders(word.slice(0, 2), [{ address: a, pnl: 1 }]), []);
  assert.equal(searchTraders(word.slice(0, 3), [{ address: a, pnl: 1 }])[0].address, a);
  assert.ok(isFullAddress(a));
  const r = searchAll(` ${a.toUpperCase().replace('0X', '0x')} `, { coins: COINS, traders: [] });
  assert.equal(r.address.address, a);
  assert.equal(r.coins.length, 0);
});

test('Hyperliquid markets: perps without delisted or HIP-3; spot as the app analyses it', () => {
  const perp = [{ universe: [{ name: 'BTC' }, { name: 'OLD', isDelisted: true }, { name: 'xyz:TSLA' }, { name: 'kPEPE' }] },
    [{ markPx: '100', prevDayPx: '80', dayNtlVlm: '5', openInterest: '2' }, { markPx: '1' }, { markPx: '1' }, { markPx: '0.01', prevDayPx: '0.01', dayNtlVlm: '1', openInterest: '10' }]];
  const tokens = [{ name: 'USDC', index: 0 }, { name: 'HYPE', index: 1, fullName: 'Hyperliquid' }, { name: 'USDT0', index: 2 }, { name: 'DUST', index: 3 }];
  const spot = [{ tokens, universe: [{ name: '@1', index: 1, tokens: [1, 0] }, { name: '@2', index: 2, tokens: [2, 0] }, { name: '@3', index: 3, tokens: [3, 0] }] },
    [{ coin: '@1', markPx: '40', prevDayPx: '50', dayNtlVlm: '9000000' }, { coin: '@2', markPx: '1', dayNtlVlm: '9000000' }, { coin: '@3', markPx: '1', dayNtlVlm: '100' }]];
  const m = parseHlMarkets(perp, spot);
  assert.deepEqual(m.map(x => x.symbol), ['BTC/USDT', 'KPEPE/USDT', 'HYPE/USDC']);
  assert.equal(m[0].oi, 200);
  assert.equal(m[2].name, 'Hyperliquid');
  assert.deepEqual(parseHlMarkets(null, spot).map(x => x.kind), ['spot']);
  const e = coinEntries(m, [], new Map());
  assert.equal(e[0].change, 0.25);
  assert.equal(e[2].row.market_kind, 'spot');
  assert.equal(e[2].spot, true);
  assert.equal(e[2].status, 'Spot');
});

test('spot ranks after perps of the same match quality', () => {
  const hype = [{ ...entry('HYPE', 'Hyperliquid', 10), spot: true }, entry('HYPE', 'Hyperliquid', 1), entry('HYPER', 'Hyperlane', 99)];
  assert.deepEqual(searchCoins('hype', hype).map(c => `${c.ticker}${c.spot ? ' spot' : ''}`), ['HYPE', 'HYPE spot', 'HYPER']);
});

test('without Hyperliquid the scanner rows stand in', () => {
  const rows = [{ symbol: 'BTC/USDT', market_kind: 'perpetual', price: 1 }, { symbol: 'HYPE/USDC', market_kind: 'spot', market_coin: '@107', price: 2 }];
  const e = coinEntries(null, rows, new Map());
  assert.deepEqual(e.map(x => [x.ticker, x.spot, x.name]), [['BTC', false, 'Bitcoin'], ['HYPE', true, 'Hyperliquid']]);
});

test('k markets (per 1,000 tokens): found by the base name, named with their unit, Radar state by the app key', () => {
  const names = ['kPEPE', 'kBONK', 'KAS', 'kNEIRO'];
  const perp = [{ universe: names.map(name => ({ name })) },
    names.map(() => ({ markPx: '0.0098', prevDayPx: '0.01', dayNtlVlm: '1000', openInterest: '1' }))];
  const m = parseHlMarkets(perp, null);
  assert.deepEqual(m.map(x => x.symbol), ['KPEPE/USDT', 'KBONK/USDT', 'KAS/USDT', 'KNEIRO/USDT']);
  assert.deepEqual(m.map(x => x.name), ['Pepe (per 1,000)', 'Bonk (per 1,000)', 'Kaspa', 'Neiro (per 1,000)']);
  const radar = new Map([['KPEPE', { coin: 'KPEPE', zone: 'watch', entry: { in_zone: true } }]]);
  const e = coinEntries(m, [], radar);
  for (const q of ['pepe', 'PEPE', 'kpepe', '1000pepe', 'pepe (per']) {
    const hit = searchCoins(q, e)[0];
    assert.equal(hit?.ticker, 'kPEPE', q);
    assert.equal(hit.row.symbol, 'KPEPE/USDT');
    assert.equal(hit.status, 'Early setup · entry zone');
  }
  assert.equal(searchCoins('kas', e)[0].ticker, 'KAS');
  assert.equal(searchCoins('1000kas', e).length, 0);
  // Without Hyperliquid's list the scanner rows stand in, under the same key.
  const rows = coinEntries(null, [{ symbol: 'KBONK/USDT', market_kind: 'perpetual', market_coin: 'kBONK', price: 0.02 }], radar);
  assert.equal(searchCoins('bonk', rows)[0].ticker, 'kBONK');
  assert.equal(rows[0].name, 'Bonk (per 1,000)');
});
