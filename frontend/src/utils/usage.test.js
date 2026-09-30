import test from "node:test";
import assert from "node:assert/strict";
import { MAX_BATCH, SESSION_GAP_MS, batchBody, randomId, rollSession, viewEvent } from "./usage.js";

test("page views: the five main views, other pages by name, the rest not counted", () => {
  assert.deepEqual(viewEvent("/scanner"), ["view_scanner", ""]);
  assert.deepEqual(viewEvent("/scanner/"), ["view_scanner", ""]);
  assert.deepEqual(viewEvent("/scanner/BTC-USDT"), ["view_coin", ""]);
  assert.deepEqual(viewEvent("/radar"), ["view_radar", ""]);
  assert.deepEqual(viewEvent("/traders/leaderboard"), ["view_traders", ""]);
  assert.deepEqual(viewEvent("/trader/0x91867345424fb158888ff9c5f1b1b2e7cd7d65d5"), ["view_trader", ""]);
  assert.deepEqual(viewEvent("/ai"), ["view_page", "ai"]);
  assert.equal(viewEvent("/intel"), null);
  assert.equal(viewEvent("/trader/nope"), null);
  assert.equal(viewEvent(undefined), null);
});

test("a session continues within 30 minutes and restarts after", () => {
  let n = 0;
  const id = () => `id${++n}`;
  const a = rollSession(null, 1000, id);
  assert.deepEqual(a, { id: "id1", last: 1000, geo: false });
  const b = rollSession({ ...a, geo: true }, 1000 + SESSION_GAP_MS - 1, id);
  assert.equal(b.id, "id1");
  assert.equal(b.geo, true);
  const c = rollSession(b, b.last + SESSION_GAP_MS, id);
  assert.equal(c.id, "id2");
  assert.equal(c.geo, false);
  assert.equal(rollSession({ id: "x", last: "bad" }, 5, id).id, "id3");
  assert.equal(rollSession(b, b.last - 10, id).id, "id4");          // a clock that went back starts over
});

test("ids fit the server's session pattern", () => {
  assert.match(randomId(), /^[a-f0-9]{16}$/);
});

test("a batch carries the token in its body and at most 50 events", () => {
  const events = Array.from({ length: 70 }, () => ["search", ""]);
  const body = JSON.parse(batchBody({ token: "t1", session: null, sid: "abc12345", events }));
  assert.equal(body.t, "t1");
  assert.equal(body.sid, "abc12345");
  assert.equal(body.e.length, MAX_BATCH);
  assert.equal("s" in body, false);
  assert.equal("t" in JSON.parse(batchBody({ token: null, sid: "abc12345", events: [] })), false);
});
