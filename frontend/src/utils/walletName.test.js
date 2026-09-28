import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { ADJECTIVES, NOUNS, codename, nameIn, shortAddr, viewNames } from './walletName.js';

// Measured once against GET /api/hyperlens/roster (517 wallets, 2026-09-28):
// 136 x 128 words give 514 distinct codenames, 3 names shared by 2 wallets each
// (Sienna Crane, Neon Puma, Winter Falcon); viewNames() leaves 0 clashes (517 distinct).
// Block0's 16 x 16 lists and hash gave 213 distinct names for the same 517 wallets.

const A1 = '0x9cd0a696c7cbb9d44de99268194cb08e5684e5fe';

test('word lists: large, distinct, one word each, Block0 words first', () => {
  assert.ok(ADJECTIVES.length >= 96 && NOUNS.length >= 96);
  assert.equal(new Set(ADJECTIVES).size, ADJECTIVES.length);
  assert.equal(new Set(NOUNS).size, NOUNS.length);
  for (const w of [...ADJECTIVES, ...NOUNS]) assert.match(w, /^[A-Z][a-z]+$/);
  const nouns = new Set(NOUNS);
  assert.equal(ADJECTIVES.filter(w => nouns.has(w)).length, 0);
  assert.deepEqual(ADJECTIVES.slice(0, 4), ['Silent', 'Golden', 'Crimson', 'Azure']);
  assert.deepEqual(NOUNS.slice(0, 4), ['Fox', 'Whale', 'Falcon', 'Wolf']);
});

test('codename is deterministic and ignores case and spaces', () => {
  assert.equal(codename(A1), 'Opal Reindeer');
  assert.equal(codename(A1), codename(A1));
  assert.equal(codename(A1.toUpperCase().replace('0X', '0x')), 'Opal Reindeer');
  assert.equal(codename(` ${A1} `), 'Opal Reindeer');
  assert.equal(codename(''), '');
});

test('codenames spread over the lists', () => {
  const seen = new Set();
  for (let i = 0; i < 2000; i++) seen.add(codename(`0x${(i * 2654435761 >>> 0).toString(16).padStart(40, '0')}`));
  assert.ok(seen.size > 1850, `only ${seen.size} distinct names in 2000`);
});

test('viewNames adds the address tail only to names that clash in the view', () => {
  // Two roster wallets that share "Sienna Crane".
  const a = '0xcf67e4da9e9cd38c0afd26338d0fbddb3036eb24';
  const b = '0x6eba10acaaf584f662691a13795aef5741287359';
  assert.equal(codename(a), 'Sienna Crane');
  assert.equal(codename(b), 'Sienna Crane');
  assert.equal(viewNames([a, A1]).get(a), 'Sienna Crane');
  const names = viewNames([a, A1, b.toUpperCase().replace('0X', '0x'), a]);
  assert.equal(names.size, 3);
  assert.equal(names.get(A1), 'Opal Reindeer');
  assert.equal(names.get(a), 'Sienna Crane ·eb24');
  assert.equal(names.get(b), 'Sienna Crane ·7359');
  assert.equal(nameIn(names, A1.toUpperCase().replace('0X', '0x')), 'Opal Reindeer');
  assert.equal(nameIn(null, A1), 'Opal Reindeer');
  assert.equal(shortAddr(A1), '0x9cd0…e5fe');
});

test('viewNames lengthens the tail until the clashing wallets differ', () => {
  // Brute-force two addresses with the same codename and the same last 4 characters.
  const byName = new Map();
  let pair = null;
  for (let i = 0; i < 400000 && !pair; i++) {
    const addr = `0x${i.toString(16).padStart(34, '0')}00beef`;
    const key = codename(addr);
    if (byName.has(key)) pair = [byName.get(key), addr]; else byName.set(key, addr);
  }
  assert.ok(pair);
  const names = viewNames(pair);
  assert.notEqual(names.get(pair[0]), names.get(pair[1]));
  assert.match(names.get(pair[0]), / ·[0-9a-f]{5,}$/);
});

// The Python mirror (backend/wallet_names.py) is checked against these same values.
test('fixed codenames shared with the backend', () => {
  const url = new URL('../../../backend/tests/fixtures/wallet_names.json', import.meta.url);
  const fixed = JSON.parse(fs.readFileSync(url, 'utf8'));
  assert.equal(Object.keys(fixed).length, 20);
  for (const [addr, name] of Object.entries(fixed)) assert.equal(codename(addr), name, addr);
});
