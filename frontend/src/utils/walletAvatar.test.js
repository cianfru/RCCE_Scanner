import test from 'node:test';
import assert from 'node:assert/strict';
import { AVATAR_PALETTE, avatarShapes, avatarSpec, avatarSvg, walletColor } from './walletAvatar.js';
import { markerTags } from './walletName.js';

const A1 = '0x9cd0a696c7cbb9d44de99268194cb08e5684e5fe';
const addr = i => `0x${(Math.imul(i + 1, 2654435761) >>> 0).toString(16).padStart(8, '0')}${'ab'.repeat(16)}`;

test('avatar is deterministic and ignores case', () => {
  assert.deepEqual(avatarSpec(A1), avatarSpec(A1));
  assert.deepEqual(avatarSpec(A1), avatarSpec(A1.toUpperCase().replace('0X', '0x')));
  assert.equal(avatarSvg(A1, 28), avatarSvg(` ${A1} `, 28));
  assert.notEqual(avatarSvg(A1), avatarSvg(addr(1)));
});

test('avatar colours come from the palette, body and background differ, ink is readable', () => {
  const colours = new Set(AVATAR_PALETTE.map(p => p.c));
  assert.equal(colours.size, AVATAR_PALETTE.length);
  for (let i = 0; i < 300; i++) {
    const s = avatarSpec(addr(i));
    assert.ok(colours.has(s.bg) && colours.has(s.body));
    assert.notEqual(s.bg, s.body);
    assert.ok(['#0b1411', '#f4faf7'].includes(s.ink));
    assert.equal(walletColor(addr(i)), s.body);
    assert.equal(walletColor(addr(i), true), s.bodyLight);
  }
});

test('shapes vary with the address and stay inside the view', () => {
  const seen = { eyes: new Set(), mouth: new Set(), round: new Set(), body: new Set() };
  for (let i = 0; i < 400; i++) {
    const s = avatarSpec(addr(i));
    seen.eyes.add(s.eyes); seen.mouth.add(s.mouth); seen.round.add(s.round); seen.body.add(s.body);
    const sh = avatarShapes(s);
    // Every eye and mouth point stays well inside the round crop (radius 18 around 18,18).
    for (const e of [...sh.eyes, sh.mouth]) {
      const pts = 'x1' in e ? [[e.x1, e.y1], [e.x2, e.y2]] : 'cx' in e ? [[e.cx, e.cy]] : [];
      for (const [x, y] of pts) assert.ok(Math.hypot(x - 18, y - 18) < 15, `${x},${y}`);
    }
  }
  assert.equal(seen.eyes.size, 3);
  assert.equal(seen.mouth.size, 4);
  assert.equal(seen.round.size, 2);
  assert.equal(seen.body.size, AVATAR_PALETTE.length);
});

test('svg string is self-contained', () => {
  const svg = avatarSvg(A1, 44);
  assert.match(svg, /^<svg xmlns="http:\/\/www.w3.org\/2000\/svg" width="44" height="44"/);
  assert.ok(!/https?:\/\/(?!www\.w3\.org)/.test(svg));
  assert.ok(!svg.includes('NaN') && !svg.includes('undefined'));
});

test('chart tags are the codename initials, numbered on a clash', () => {
  const tags = markerTags([A1, A1.toUpperCase().replace('0X', '0x')]);
  assert.equal(tags.size, 1);
  assert.equal(tags.get(A1), 'OR'); // Opal Reindeer
  const byTag = new Map();
  let pair = null;
  for (let i = 0; i < 500 && !pair; i++) {
    const t = markerTags([addr(i)]).get(addr(i));
    if (byTag.has(t)) pair = [byTag.get(t), addr(i)]; else byTag.set(t, addr(i));
  }
  const two = markerTags(pair);
  assert.equal(two.get(pair[1]), `${two.get(pair[0])}2`);
});
