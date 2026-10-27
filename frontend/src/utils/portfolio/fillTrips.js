// Fills placed against the running position, and round trips (a port of backend trader_profile.py
// classify_fills and round_trips, with its cases in fillTrips.test.js). Used for a position's open
// time, adds and trims, realised P&L and fees since it opened, the chart's fill marks and the last
// closed trip. includeDex: also builder-dex markets ("xyz:TSLA"), which the backend leaves out.
import { feeUsd } from "./fees.js";

// A perp fill: "Open Long", "Close Short", "Long > Short", ... and "Settlement", which closes a
// builder-dex position when its market settles (its startPosition and size end the trip).
export function isPerpFill(f, { includeDex = false } = {}) {
  const coin = String(f?.coin || "");
  const d = String(f?.dir || "");
  return !!coin && !coin.startsWith("@") && !coin.includes("/") && (includeDex || !coin.includes(":"))
    && (d.includes("Long") || d.includes("Short") || d === "Settlement");
}

const dec = x => {
  if (x == null || x === "") return null;
  const n = typeof x === "number" ? x : parseFloat(x);
  return Number.isFinite(n) ? n : null;
};
const sign = x => (x > 0) - (x < 0);
// Decimal-safe sizes: sums of fill sizes are rounded to 10 places (the Python port uses Decimal).
const r10 = x => Math.round(x * 1e10) / 1e10;

// Time order; fills in the same millisecond chain by their starting size (rising for buys, falling for sells).
function cmp(a, b) {
  if (a.time !== b.time) return a.time - b.time;
  const ca = a.coin || "", cb = b.coin || "";
  if (ca !== cb) return ca < cb ? -1 : 1;
  const ka = (dec(a.startPosition) || 0) * (a.side === "B" ? 1 : -1);
  const kb = (dec(b.startPosition) || 0) * (b.side === "B" ? 1 : -1);
  return ka - kb;
}

export function classifyFills(fills, opts = {}) {
  let fs = (fills || []).filter(f => isPerpFill(f, opts)).slice().sort(cmp);
  const regular = new Set(fs.filter(f => !f.twap).map(f => `${f.coin}|${f.side}|${f.time}`));
  fs = fs.filter(f => !(f.twap && regular.has(`${f.coin}|${f.side}|${f.time}`)));
  const state = new Map();
  const out = [];
  for (const f of fs) {
    const coin = f.coin;
    const sz = dec(f.sz), price = dec(f.px);
    if (!sz || price == null) continue;
    let st = state.get(coin);
    if (!st) { st = { pos: null, avg: null }; state.set(coin, st); }
    let before = dec(f.startPosition);
    if (before == null) before = st.pos != null ? st.pos : 0;
    if (st.pos == null || (before !== st.pos && sign(before) !== sign(st.pos))) st.avg = null;
    const delta = f.side === "B" ? sz : -sz;
    const after = r10(before + delta);
    const sb = sign(before), sa = sign(after);
    let kind;
    if (sb === 0) kind = "open";
    else if (sa === 0) kind = "close";
    else if (sa !== sb) kind = "flip";
    else if (Math.abs(after) > Math.abs(before)) kind = "add";
    else kind = "trim";
    let avg = st.avg;
    if (kind === "open" || kind === "flip") avg = price;
    else if (kind === "add") avg = avg != null ? (avg * Math.abs(before) + price * sz) / Math.abs(after) : null;
    else if (kind === "close") avg = null;
    st.pos = after; st.avg = avg;
    const sideSign = kind === "open" || kind === "add" || kind === "flip" ? sa : sb;
    // Perp fees are in the dex's collateral; px (token name -> price) values any other fee token.
    const fee = opts.px ? feeUsd(f, opts.px) ?? 0 : dec(f.fee) || 0;
    // Unrounded: sums (a trip's realised, its fees) are rounded once, for display.
    const pnl = (dec(f.closedPnl) || 0) - fee;
    out.push({
      t: f.time / 1000, coin, kind, side: sideSign > 0 ? "long" : "short",
      px: price, sz, usd: price * sz, before, after,
      pnl, fee, avgEntry: avg, twap: !!f.twap, closedPnl: dec(f.closedPnl) || 0,
    });
  }
  return out;
}

export function roundTrips(classified) {
  const cur = new Map();
  const closed = [];
  const start = (coin, f, partial) => ({
    coin, side: f.side, openedAt: partial ? null : f.t, firstT: f.t, partial,
    inSz: 0, inUsd: 0, outSz: 0, outUsd: 0, pnl: 0, fees: 0, fills: 0, peakSize: 0, adds: 0, trims: 0,
  });
  const finish = (tr, t) => {
    tr.closedAt = t;
    tr.entryPx = tr.inSz && !tr.partial ? tr.inUsd / tr.inSz : null;
    tr.exitPx = tr.outSz ? tr.outUsd / tr.outSz : null;
    const basis = tr.entryPx ? tr.entryPx * tr.outSz : null;
    tr.pnl = Math.round(tr.pnl * 100) / 100;
    tr.pnlPct = basis ? Math.round((tr.pnl / basis) * 10000) / 100 : null;
    tr.peakUsd = Math.round(tr.peakSize * (tr.entryPx || tr.exitPx || 0));
    delete tr.inSz; delete tr.inUsd; delete tr.outSz; delete tr.outUsd;
    return tr;
  };
  for (const f of classified || []) {
    const { coin, kind } = f;
    let tr = cur.get(coin);
    if (kind === "open" || !tr) {
      tr = start(coin, f, kind !== "open");
      cur.set(coin, tr);
    }
    tr.fills += 1;
    tr.fees += f.fee || 0;
    if (kind === "open" || kind === "add") {
      tr.inSz += f.sz; tr.inUsd += f.usd; tr.pnl += f.pnl;
      if (kind === "add") tr.adds += 1;
      tr.peakSize = Math.max(tr.peakSize, Math.abs(f.after));
    } else if (kind === "trim") {
      tr.outSz += f.sz; tr.outUsd += f.usd; tr.pnl += f.pnl; tr.trims += 1;
      tr.peakSize = Math.max(tr.peakSize, Math.abs(f.before));
    } else if (kind === "close") {
      tr.outSz += f.sz; tr.outUsd += f.usd; tr.pnl += f.pnl;
      tr.peakSize = Math.max(tr.peakSize, Math.abs(f.before));
      cur.delete(coin);
      closed.push(finish(tr, f.t));
    } else if (kind === "flip") {
      const closing = Math.abs(f.before);
      const share = f.sz ? closing / f.sz : 1;
      const fee = f.fee;
      tr.outSz += closing; tr.outUsd += closing * f.px;
      // closedPnl on a flip is the closing half's; the fee is split by size.
      tr.pnl += f.pnl + fee - fee * share;
      tr.fees += fee * share - fee;
      tr.peakSize = Math.max(tr.peakSize, closing);
      tr.side = f.before > 0 ? "long" : "short";
      cur.delete(coin);
      closed.push(finish(tr, f.t));
      const nt = start(coin, f, false);
      nt.fills = 1;
      nt.inSz = Math.abs(f.after); nt.inUsd = Math.abs(f.after) * f.px;
      nt.pnl = -fee * (1 - share); nt.fees = fee * (1 - share);
      nt.peakSize = Math.abs(f.after);
      cur.set(coin, nt);
    }
  }
  closed.sort((a, b) => b.closedAt - a.closedAt);
  const open = {};
  for (const [coin, tr] of cur) {
    open[coin] = {
      coin, side: tr.side, openedAt: tr.openedAt, firstT: tr.firstT, partial: tr.partial, fills: tr.fills,
      adds: tr.adds, trims: tr.trims, realized: Math.round(tr.pnl * 100) / 100, fees: Math.round(tr.fees * 100) / 100,
    };
  }
  return { closed, open };
}

// Chart marks for a busy book: at most `max` marks. Opens, closes and flips stay; adds and trims are
// netted per bucket of candles into one mark (an add or a trim of the net size, at the bucket's
// average price), so a grid of hundreds of fills still leaves the candles readable.
// all: a hard cap, opens, closes and flips included: a bucket that holds one keeps its latest
// open, close or flip in place of the netted adds and trims.
export function thinMarks(marks, max = 48, { all = false } = {}) {
  if (!marks || marks.length <= max) return marks || [];
  const first = marks[0].index, last = marks[marks.length - 1].index;
  const k = Math.max(1, Math.ceil((last - first + 1) / max));
  const keep = [];
  const buckets = new Map();
  const life = new Map();
  for (const m of marks) {
    if (m.kind === "open" || m.kind === "close" || m.kind === "flip") {
      if (all) life.set(Math.floor((m.index - first) / k), m); else keep.push(m);
      continue;
    }
    const b = Math.floor((m.index - first) / k);
    const g = buckets.get(b) || { net: 0, sz: 0, pxSz: 0, n: 0, pnl: 0 };
    g.net += (m.kind === "add" ? 1 : -1) * m.sz;
    g.sz += m.sz; g.pxSz += (m.px || 0) * m.sz; g.n += m.n || 1; g.pnl += m.pnl || 0;
    g.index = m.index; g.time = m.time; g.side = m.side; g.t0 = g.t0 ?? m.t0; g.t1 = m.t1;
    buckets.set(b, g);
  }
  for (const m of life.values()) keep.push(m);
  for (const [b, g] of buckets) {
    if (life.has(b) || !g.sz || Math.abs(g.net) < 1e-12) continue;
    const px = g.pxSz / g.sz;
    const kind = g.net > 0 ? "add" : "trim";
    keep.push({ index: g.index, time: g.time, kind, side: g.side, usd: Math.abs(g.net) * px, sz: Math.abs(g.net), n: g.n, pnl: g.pnl,
      px, t0: g.t0, t1: g.t1, buy: kind === "add" ? g.side === "long" : g.side === "short" });
  }
  return keep.sort((a, b) => a.index - b.index);
}

// Fills as chart marks for one coin since a time (utils/traderBoard.fillMarks reads {t, kind, side, px, sz, usd, pnl}).
export const marksInput = (classified, coin, sinceSec = 0) =>
  (classified || []).filter(f => f.coin === coin && f.t >= sinceSec).map(f => ({ t: f.t, kind: f.kind, side: f.side, px: f.px, sz: f.sz, usd: f.usd, pnl: f.pnl }));
