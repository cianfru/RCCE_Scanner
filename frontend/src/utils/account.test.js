import test from "node:test";
import assert from "node:assert/strict";
import { delayedLine, lockHelp, nextQuiet, quietText, refusal, sendsSession, shortAddress, toHex } from "./account.js";

const API = "https://api.test";
const A = "0x" + "ab".repeat(20);

test("only account-aware paths carry the session", () => {
  for (const p of ["/api/me", "/api/me/follows", `/api/me/follows/${A}`, "/api/auth/wallet/logout",
    "/api/setup-map?tf=1d", "/api/setup-map/ladder?coin=BTC", "/api/setup-map/watch", "/api/setup-map/watch/SUI",
    `/api/traders/${A}`, `/api/traders/${A}/fills?coin=BTC`, "/api/hyperlens/followed"]) {
    assert.equal(sendsSession(API + p, API), true, p);
  }
  for (const p of ["/api/scan?tf=4h", "/api/traders/leaderboard", "/api/setup-map/mine", "/api/meh", "/api/auth/login",
    "/api/hyperlens/consensus"]) {
    assert.equal(sendsSession(API + p, API), false, p);
  }
  assert.equal(sendsSession("https://elsewhere.test/api/me", API), false);
});

test("refusals: holder, sign in, other", () => {
  assert.equal(refusal(403, "holder"), "holder");
  assert.equal(refusal(403, "Sign in with a wallet"), "signin");
  assert.equal(refusal(403, "Admin key required for changes"), null);
  assert.equal(refusal(400, "holder"), null);
});

test("lock help names the way in, and says when the wallet holds too little", () => {
  assert.equal(lockHelp(null).length, 1);
  assert.equal(lockHelp({ address: A, tier: "free" }).length, 2);
  assert.equal(lockHelp({ address: A, tier: "holder" }).length, 1);
  const words = /\b(will|expect|likely|predict|target|probability|odds)\b/i;
  assert.ok(lockHelp({ address: A, tier: "free" }).every(l => !words.test(l)));
});

test("delayed Radar line", () => {
  assert.equal(delayedLine({ coins: [] }), null);
  assert.equal(delayedLine({ delayed: true, delay_min: 60, as_of: null }), "Delayed 60 min · no map that old yet");
  assert.match(delayedLine({ delayed: true, delay_min: 60, as_of: 1_790_000_000 }), /^Delayed 60 min · as of \d\d:\d\d$/);
});

test("helpers", () => {
  assert.equal(shortAddress(A), "0xabab…abab");
  assert.equal(toHex("Hi é"), "0x486920c3a9");
  assert.deepEqual(nextQuiet(["23:00", "07:30"]), ["22:00", "08:00"]);
  assert.equal(nextQuiet(["00:00", "07:00"]), null);
  assert.deepEqual(nextQuiet(null), ["23:00", "07:30"]);
  assert.equal(quietText(null), "off");
});
