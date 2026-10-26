import test from "node:test";
import assert from "node:assert/strict";
import { readSlots, writeCurrent, snapKey, buildSnapshot, sinceChanges, sinceSummary, BASE_AFTER_MS } from "./since.js";

function memStorage() {
  const m = new Map();
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), m };
}
const ADDR = "0xABCDEFabcdef0000000000000000000000000001";
const snap = (t, coins = {}, o = {}) => ({ v: 1, t, equity: 1000, upnl: 10, lastFillT: null, coins, ...o });

test("key is per address, lowercased", () => {
  assert.equal(snapKey(ADDR), `reflex.pf.snap.v1.${ADDR.toLowerCase()}`);
});

test("two slots: a first visit has no baseline; a cur older than 30 min becomes the baseline", () => {
  const s = memStorage();
  const t0 = 1_000_000_000_000;
  assert.deepEqual(readSlots(s, ADDR, t0), { base: null, cur: null, ok: true });
  writeCurrent(s, ADDR, null, snap(t0));
  // Back two hours later: the old cur is the baseline.
  const later = t0 + 2 * 3600_000;
  const r = readSlots(s, ADDR, later);
  assert.equal(r.base.t, t0);
  writeCurrent(s, ADDR, r.base, snap(later));
  // A reload ten minutes on keeps that baseline (cur is recent).
  const reload = readSlots(s, ADDR, later + 10 * 60_000);
  assert.equal(reload.base.t, t0);
  assert.equal(reload.cur.t, later);
  // Exactly at 30 minutes it is still the current visit.
  assert.equal(readSlots(s, ADDR, later + BASE_AFTER_MS).base.t, t0);
  assert.equal(readSlots(s, ADDR, later + BASE_AFTER_MS + 1).base.t, later);
});

test("storage throwing leaves no crash and behaves as a first visit", () => {
  const bad = { getItem() { throw new Error("SecurityError"); }, setItem() { throw new Error("QuotaExceeded"); } };
  assert.deepEqual(readSlots(bad, ADDR, 1), { base: null, cur: null, ok: false });
  assert.equal(writeCurrent(bad, ADDR, null, snap(1)), false);
  assert.deepEqual(readSlots(null, ADDR, 1), { base: null, cur: null, ok: true });
  const junk = memStorage(); junk.setItem(snapKey(ADDR), "{not json");
  assert.equal(readSlots(junk, ADDR, 1).ok, false);
  const old = memStorage(); old.setItem(snapKey(ADDR), JSON.stringify({ base: { v: 0, t: 1 }, cur: null }));
  assert.equal(readSlots(old, ADDR, 2).base, null);              // another version is ignored
});

test("snapshot carries the coins' readings", () => {
  const rows = [{ coin: "HYPE", side: "long", szi: 3, upnl: 5.123, mark: 80, dist: { pct: 31.2, atr: 2.4 },
    ctx: { h4: { signal: "STRONG_LONG", regime: "MARKUP", heat: 74 }, d1: { signal: "LIGHT_LONG" }, band: { state: "above" }, traders: { long: { n: 9 }, short: { n: 2 } } } }];
  const s = buildSnapshot({ t: 5, equity: 100.456, upnl: 5.123, lastFillT: 4, rows });
  assert.deepEqual(s.coins.HYPE, { side: "long", szi: 3, upnl: 5.12, mark: 80, liqPct: 31.2, liqAtr: 2.4, h4: "STRONG_LONG", d1: "LIGHT_LONG", reg4h: "MARKUP", heat: 74, band: "above", tl: 9, ts: 2 });
  assert.equal(s.v, 1);
});

const c = (o = {}) => ({ side: "long", szi: 1, upnl: 0, mark: 100, liqPct: 30, liqAtr: 4, h4: "LIGHT_LONG", d1: "WAIT", reg4h: "MARKUP", heat: 60, band: "above", tl: 6, ts: 2, ...o });

test("changes are ranked: trips, liquidation, signals (against first), regime, band, heat, traders, price", () => {
  const base = snap(0, { SOL: c(), HYPE: c(), LINK: c({ heat: 80 }), BTC: c(), NEAR: c(), XMR: c({ mark: 100 }) });
  const cur = snap(1, {
    NEW: c({ side: "short" }),
    HYPE: c({ h4: "STRONG_LONG" }),
    LINK: c({ heat: 87, h4: "TRIM", tl: 3 }),
    BTC: c({ liqPct: 22, liqAtr: 2 }),
    NEAR: c({ band: "inside", reg4h: "REACC" }),
    XMR: c({ mark: 107 }),
  });
  const ch = sinceChanges(base, cur, { trips: [{ coin: "SOL", closedAt: 0.5, pnl: 824 }] });
  const kinds = ch.map(x => `${x.kind}:${x.coin}${x.tf ? ":" + x.tf : ""}`);
  assert.deepEqual(kinds, ["trip:NEW", "trip:SOL", "liq:BTC", "signal:LINK:h4", "signal:HYPE:h4", "regime:NEAR", "band:NEAR", "heat:LINK", "traders:LINK", "price:XMR"]);
  assert.equal(ch.find(x => x.coin === "SOL").pnl, 824);
  assert.equal(ch.find(x => x.kind === "signal" && x.coin === "LINK").against, true);
});

test("thresholds: liq down under 5 points, heat moves not crossing 85/95, traders under 5 holders, price under 5%", () => {
  const base = snap(0, { A: c({ liqPct: 30, heat: 70, tl: 2, ts: 1, mark: 100 }) });
  const cur = snap(1, { A: c({ liqPct: 26, liqAtr: 3.5, heat: 84, tl: 4, ts: 0, mark: 104 }) });
  assert.deepEqual(sinceChanges(base, cur), []);
  const red = sinceChanges(snap(0, { A: c({ liqPct: 17, liqAtr: null }) }), snap(1, { A: c({ liqPct: 14, liqAtr: null }) }));
  assert.equal(red[0].kind, "liq");
  assert.equal(red[0].red, true);
  assert.deepEqual(sinceChanges(null, cur), []);
});

test("summary: closed P&L net of fees, funding and the change in open P&L since the baseline", () => {
  const base = snap(1000, {}, { upnl: 100 });
  const fills = [{ time: 900, closedPnl: "50", fee: "1" }, { time: 1500, closedPnl: "20", fee: "0.5" }, { time: 1600, closedPnl: "0", fee: "0.5" }];
  const funding = [{ time: 1200, delta: { usdc: "-3" } }];
  const s = sinceSummary(base, { fills, funding, upnl: 150 });
  assert.equal(s.fills, 2);
  assert.ok(Math.abs(s.pnl - (19 - 3 + 50)) < 1e-9);
});
