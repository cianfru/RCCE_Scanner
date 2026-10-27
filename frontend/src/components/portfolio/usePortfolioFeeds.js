// Every Hyperliquid read the Portfolio page makes, from the browser (Portfolio v2, section 6.3).
// Each poll runs only while the tab is visible (pollWhileVisible): a hidden tab costs nothing, and
// coming back refreshes at once. A reply that arrives after the address changed is dropped, so one
// wallet never shows under another.
//
// Weight. Hyperliquid allows 1200 a minute per IP, /exchange included, so the page counts what it
// sends (utils/portfolio/weight.js). First paint: positions, the main open orders, TradFi, spot, mids
// and the account mode. Then portfolio history, staking, vaults and Earn; spot names and the builder
// dexes with a balance (both kept for the browser session); the last 24 hours of fills and funding.
// The rest of the 30-day window is read one page at a time, only while the last minute's total stays
// under HISTORY_CAP, and joins the page once complete; until then fills and funding are partial
// (`coverage`). After that both stay incremental: each read starts at the newest item on hand
// (inclusive) and replaces only the range a page settles (fillsMerge.pageRange and mergeRange), so a
// page that fails never takes away what an earlier one read.
import { useCallback, useEffect, useRef, useState } from "react";
import * as hlClient from "../../services/hlClient.js";
import { pollWhileVisible } from "../../utils/visiblePoll.js";
import { byTime, byFundingTime, mergeRange, pageRange, trimWindow, WINDOW_DAYS } from "../../utils/portfolio/fillsMerge.js";
import { meter, weightOf, HISTORY_CAP } from "../../utils/portfolio/weight.js";
import { addrHash } from "../../utils/portfolio/since.js";
import { FEEDS } from "./copy.js";

const S = 1000;
export const CADENCE = { fast: 15 * S, venues: 60 * S, spot: 60 * S, orders: 60 * S, fills: 60 * S, mids: 120 * S, portfolio: 300 * S, slow: 600 * S, history: 5 * S };
const DAY = 86400_000;
export const HEAD_MS = DAY;                       // the first read of fills and funding
export const SESSION_MS = 30 * 60 * 1000;         // spot names and the builder dexes, per browser session
export const PAGE = { fills: 2000, funding: 500 };
const TYPE = { fills: "userFillsByTime", funding: "userFunding" };
const CMP = { fills: byTime, funding: byFundingTime };

function portfolioOf(raw) {
  if (!Array.isArray(raw)) return raw || null;
  const out = {};
  for (const [period, d] of raw) {
    out[period] = {
      accountValueHistory: (d.accountValueHistory || []).map(([t, v]) => ({ time: Math.floor(t / 1000), value: parseFloat(v) })),
      pnlHistory: (d.pnlHistory || []).map(([t, v]) => ({ time: Math.floor(t / 1000), value: parseFloat(v) })),
      vlm: parseFloat(d.vlm),
    };
  }
  return out;
}

const sizeKey = st => (st?.assetPositions || []).map(ap => `${ap.position?.coin}:${ap.position?.szi}`).sort().join("|");
const hasBalance = st => !!(parseFloat(st?.marginSummary?.accountValue) || st?.assetPositions?.length);

// Session storage (guarded: blocked storage reads as empty).
function sessionGet(key, now = Date.now()) {
  try {
    const x = JSON.parse(globalThis.sessionStorage?.getItem(key) || "null");
    return x && now - x.at < SESSION_MS ? x.v : null;
  } catch { return null; }
}
function sessionPut(key, v) {
  try { globalThis.sessionStorage?.setItem(key, JSON.stringify({ at: Date.now(), v })); } catch { /* full or blocked */ }
}
// spotMeta, trimmed to what the page reads: pair names with their tokens, token names and indexes.
export const trimSpotMeta = m => (m ? {
  universe: (m.universe || []).map(u => ({ name: u.name, tokens: u.tokens })),
  tokens: (m.tokens || []).map(t => ({ name: t.name, index: t.index })),
} : null);

const freshHist = () => ({ items: [], cursor: null, from: null, headOk: false, headErr: false, back: null, backFrom: null, buf: [], backErr: false, done: false, busy: null, backBusy: false, retryAt: 0 });
const freshCache = () => ({ fills: freshHist(), funding: freshHist(), otherDexs: null, probeFailed: [], dexList: null, sizes: { main: "", xyz: "" }, hasXyz: false });

export default function usePortfolioFeeds(account) {
  const [d, setD] = useState({});
  const [feeds, setFeeds] = useState({});
  const [coverage, setCoverage] = useState({ fills: null, funding: null });
  const scope = useRef(null);
  const cache = useRef(freshCache());
  const fastInFlight = useRef(null);

  useEffect(() => {
    const s = { account };
    scope.current = s;
    fastInFlight.current = null;
    setD({}); setFeeds({}); setCoverage({ fills: null, funding: null });
    cache.current = freshCache();
    return () => { if (scope.current === s) scope.current = null; };
  }, [account]);

  const put = useCallback((key, value) => setD(prev => ({ ...prev, [key]: value })), []);
  const mark = useCallback((name, ok) => setFeeds(prev => ({ ...prev, [name]: { error: !ok, at: ok ? Date.now() : prev[name]?.at ?? null } })), []);

  // One read, counted on the meter: {v} when it answered for the address shown, else {fail} or {stale}.
  // items(v): the number of items returned, for the reads that weigh more per item.
  const get = useCallback(async (type, load, items = null) => {
    const s = scope.current;
    meter.add(weightOf(type));
    try {
      const v = await load();
      if (v == null) throw new Error("No reading");
      if (items) meter.add(weightOf(type, items(v)) - weightOf(type));
      return scope.current === s ? { v } : { stale: true };
    } catch {
      return scope.current === s ? { fail: true } : { stale: true };
    }
  }, []);

  const read = useCallback(async (name, type, load, apply) => {
    if (!account) return false;
    const r = await get(type, load);
    if (r.stale) return false;
    if (r.fail) { mark(name, false); return false; }
    apply(r.v);
    mark(name, true);
    return true;
  }, [account, get, mark]);

  // ---- fills and funding ------------------------------------------------------------------------
  const loadPage = useCallback((kind, s, end) => (kind === "fills"
    ? hlClient.getUserFillsByTime(account, s, end) : hlClient.getUserFunding(account, s, end)), [account]);

  // What the page has of the window: from (ms; null before the first read answered) and whether it is
  // complete, i.e. the window's older part is in and the newest read reached now.
  const showCoverage = useCallback(kind => {
    const h = cache.current[kind];
    setCoverage(prev => ({ ...prev, [kind]: h.from == null ? null : { from: h.from, complete: h.done && h.headOk } }));
    mark(kind, !(h.headErr || h.backErr));
  }, [mark]);

  // Forward from the cursor (the newest item on hand, inclusive; at first 24 hours back) to now, each
  // page merged as it lands. The feed is marked at the end, never OK while the last page was full.
  const forward = useCallback(kind => {
    const h = cache.current[kind];
    if (!account) return Promise.resolve(false);
    if (h.busy) return h.busy;
    const run = (async () => {
      const start0 = h.cursor ?? Date.now() - HEAD_MS;
      let s = start0;
      for (let i = 0; i < 50; i++) {
        const r = await get(TYPE[kind], () => loadPage(kind, s), v => v.length);
        if (r.stale) return false;
        if (r.fail) { h.headErr = true; h.headOk = false; showCoverage(kind); return false; }
        const range = pageRange(r.v, s, PAGE[kind]);
        if (h.from == null) h.from = start0;
        h.items = trimWindow(mergeRange(h.items, r.v, range.lo, range.hi, CMP[kind]));
        put(kind, h.items);
        if (range.next == null) {
          h.cursor = h.items.length ? Math.max(s, h.items[h.items.length - 1].time) : s;
          h.headOk = true; h.headErr = false;
          showCoverage(kind);
          return true;
        }
        s = range.next;
        h.cursor = s;
        h.headOk = false;
      }
      showCoverage(kind);
      return false;
    })().finally(() => { h.busy = null; });
    h.busy = run;
    return run;
  }, [account, get, loadPage, put, showCoverage]);

  // One page of the window's older part ([30 days ago, from)), set aside until that part is complete,
  // then joined: the page never shows a history with a hole in it. Sent only while the last minute's
  // weight, with this page, stays under HISTORY_CAP.
  const backfill = useCallback(async kind => {
    const h = cache.current[kind];
    if (!account || h.from == null || h.done || h.backBusy || Date.now() < h.retryAt) return false;
    const now = Date.now();
    if (h.back == null) { h.backFrom = Math.max(now - WINDOW_DAYS * DAY, 0); h.back = h.backFrom; }
    if (h.back >= h.from) { h.done = true; showCoverage(kind); return false; }
    const end = h.from - 1;
    // The page's weight, from the rate of the items on hand (a full page at most).
    const rate = h.items.length / Math.max(1, now - h.from);
    const est = weightOf(TYPE[kind], Math.min(PAGE[kind], rate * (end - h.back)));
    if (!meter.allows(est, HISTORY_CAP, now)) return false;
    h.backBusy = true;
    try {
      const s = h.back;
      const r = await get(TYPE[kind], () => loadPage(kind, s, end), v => v.length);
      if (r.stale) return false;
      if (r.fail) { h.backErr = true; h.retryAt = Date.now() + 30_000; showCoverage(kind); return false; }
      h.backErr = false;
      const range = pageRange(r.v, s, PAGE[kind]);
      h.buf = mergeRange(h.buf, r.v, range.lo, Math.min(range.hi, end), CMP[kind]);
      if (range.next == null || range.next > end) {
        h.items = trimWindow([...h.buf, ...h.items].sort(CMP[kind]));
        h.from = h.backFrom;
        h.buf = [];
        h.done = true;
        put(kind, h.items);
      } else {
        h.back = range.next;
      }
      showCoverage(kind);
      return true;
    } finally {
      h.backBusy = false;
    }
  }, [account, get, loadPage, put, showCoverage]);

  // One history page per tick at most: fills first, then funding (a part waiting to retry steps aside).
  const pump = useCallback(async () => {
    for (const kind of ["fills", "funding"]) {
      const h = cache.current[kind];
      if (h.done || h.from == null || Date.now() < h.retryAt) continue;
      await backfill(kind);
      return;
    }
  }, [backfill]);

  // ---- positions, orders, balances ---------------------------------------------------------------
  // The main open orders are read with the positions every 15 s (fetchFast), as the old page did, so
  // a Cancel button and "No stop" are never more than one tick behind. TradFi (xyz) orders, which the
  // old page did not read and which have no Cancel here, every 60 s and when an xyz size changes.
  const fetchOrdersXyz = useCallback(async () => {
    if (!cache.current.hasXyz) return;
    await read("ordersXyz", "frontendOpenOrders", () => hlClient.getDexOpenOrders(account, "xyz"), v => put("ordersXyz", v));
  }, [account, read, put]);

  // Main perps, their open orders and xyz every 15 s (the old page's rate and reads). A size change
  // refreshes the fills (and the xyz orders) at once. One read at a time: a tick, the tab coming back
  // and an action's refresh never stack up.
  const fetchFast = useCallback(async (fresh = false) => {
    if (!account) return;
    if (fastInFlight.current && !fresh) return fastInFlight.current;
    const run = Promise.all([
      read("main", "clearinghouseState", () => hlClient.getClearinghouseState(account), v => {
        put("main", v);
        const k = sizeKey(v);
        if (cache.current.sizes.main && k !== cache.current.sizes.main && cache.current.fills.from != null) forward("fills");
        cache.current.sizes.main = k;
      }),
      read("orders", "frontendOpenOrders", () => hlClient.getDexOpenOrders(account, ""), v => put("orders", v)),
      read("xyz", "clearinghouseState", () => hlClient.getXyzClearinghouseState(account), v => {
        put("xyz", v);
        cache.current.hasXyz = (v.assetPositions || []).length > 0;
        const k = sizeKey(v);
        if (cache.current.sizes.xyz && k !== cache.current.sizes.xyz) fetchOrdersXyz();
        cache.current.sizes.xyz = k;
      }),
    ]).finally(() => { if (fastInFlight.current === run) fastInFlight.current = null; });
    fastInFlight.current = run;
    await run;
  }, [account, read, put, fetchOrdersXyz, forward]);

  // The builder dexes with a balance. Every listed dex is probed once per browser session; only those
  // with a balance (and any whose probe failed, until it answers) are read again, every 60 s. A failed
  // probe or read is a failed "Other venues" feed: the title offers Retry and Equity reads partial.
  const fetchVenues = useCallback(async () => {
    const c = cache.current;
    const list = [...new Set([...(c.otherDexs || []), ...c.probeFailed])];
    if (!list.length) return;
    const s = scope.current;
    const res = await Promise.all(list.map(dex => get("clearinghouseState", () => hlClient.getDexClearinghouseState(account, dex)).then(r => [dex, r])));
    if (scope.current !== s || res.some(([, r]) => r.stale)) return;
    const out = {};
    const failed = [];
    for (const [dex, r] of res) {
      if (r.fail) { failed.push(dex); continue; }
      if (hasBalance(r.v)) out[dex] = r.v;
    }
    // Kept: the dexes with a balance, and any held before whose read failed (its last state stays).
    c.otherDexs = [...new Set([...Object.keys(out), ...(c.otherDexs || []).filter(x => failed.includes(x))])];
    c.probeFailed = failed;
    if (!failed.length) sessionPut(`reflex.pf.dexs.v1.${addrHash(account)}`, Object.keys(out));
    setD(prev => {
      const others = { ...(prev.others || {}) };
      for (const dex of list) if (!failed.includes(dex)) { if (out[dex]) others[dex] = out[dex]; else delete others[dex]; }
      return { ...prev, others };
    });
    mark("other", failed.length === 0);
  }, [account, get, mark]);

  // The dex list and the first probe of each (skipped while this session already probed this address).
  const fetchDexList = useCallback(async () => {
    const c = cache.current;
    const known = sessionGet(`reflex.pf.dexs.v1.${addrHash(account)}`);
    if (known) { c.otherDexs = known; c.probeFailed = []; await fetchVenues(); if (!known.length) { put("others", {}); mark("other", true); } return; }
    let names = sessionGet("reflex.pf.perpdexs.v1");
    if (!names) {
      const r = await get("perpDexs", () => hlClient.getPerpDexs());
      if (r.stale) return;
      if (r.fail) { mark("other", false); return; }
      names = (r.v || []).filter(Boolean).map(x => x.name).filter(n => n && n !== "xyz");
      sessionPut("reflex.pf.perpdexs.v1", names);
    }
    c.dexList = names;
    c.otherDexs = [];
    c.probeFailed = names;           // every dex is "to probe" until it answers
    if (!names.length) { put("others", {}); mark("other", true); return; }
    await fetchVenues();
  }, [account, get, mark, put, fetchVenues]);

  const fetchMeta = useCallback(async () => {
    const hit = sessionGet("reflex.pf.spotmeta.v1");
    if (hit) { put("spotMeta", hit); mark("meta", true); return; }
    await read("meta", "spotMeta", () => hlClient.getSpotMeta(), v => { const t = trimSpotMeta(v); sessionPut("reflex.pf.spotmeta.v1", t); put("spotMeta", t); });
  }, [read, put, mark]);

  // After first paint: spot names, the builder dexes and the last 24 hours of fills and funding.
  const fetchOnce = useCallback(async () => {
    await Promise.all([fetchMeta(), fetchDexList()]);
    await forward("fills");
    await forward("funding");
  }, [fetchMeta, fetchDexList, forward]);

  const fetchAbstraction = useCallback(() => read("abstraction", "userAbstraction", () => hlClient.getUserAbstraction(account), v => put("abstraction", v)), [account, read, put]);
  const fetchSlow = useCallback(async () => {
    await Promise.all([
      read("staking", "delegatorSummary", () => hlClient.getDelegatorSummary(account), v => put("delegator", v)),
      read("vaults", "userVaultEquities", () => hlClient.getVaultEquities(account), v => put("vaults", v)),
      read("earn", "borrowLendUserState", () => hlClient.getBorrowLendState(account), v => put("earn", v)),
    ]);
  }, [account, read, put]);
  const fetchSlowAll = useCallback(() => Promise.all([fetchSlow(), fetchAbstraction()]), [fetchSlow, fetchAbstraction]);

  const fetchPortfolio = useCallback(() => read("portfolio", "portfolio", () => hlClient.getPortfolio(account).catch(() => null), v => put("portfolio", portfolioOf(v))), [account, read, put]);
  const fetchSpot = useCallback(() => read("spot", "spotClearinghouseState", () => hlClient.getSpotState(account), v => put("spot", v)), [account, read, put]);
  const fetchMids = useCallback(() => read("mids", "allMids", () => hlClient.getAllMids(), v => put("mids", v)), [read, put]);
  // The newest fills and funding; also the first 24 hours again when that read failed.
  const fetchFundingNew = useCallback(() => forward("funding"), [forward]);
  const fetchFillsNew = useCallback(() => forward("fills"), [forward]);

  useEffect(() => {
    if (!account) return undefined;
    let alive = true;
    const later = (ms, fn) => setTimeout(() => { if (alive) fn(); }, ms);
    // First paint: positions, orders, TradFi, spot, mids and the account mode; the rest after, staggered.
    fetchFast().then(() => alive && fetchOrdersXyz());
    fetchSpot(); fetchMids(); fetchAbstraction();
    const t1 = later(600, fetchPortfolio);
    const t2 = later(1200, fetchSlow);
    const t3 = later(1800, fetchOnce);
    const stops = [
      pollWhileVisible(fetchFast, CADENCE.fast),
      pollWhileVisible(fetchOrdersXyz, CADENCE.orders),
      pollWhileVisible(fetchFillsNew, CADENCE.fills),
      pollWhileVisible(fetchSpot, CADENCE.spot),
      pollWhileVisible(fetchMids, CADENCE.mids),
      pollWhileVisible(fetchPortfolio, CADENCE.portfolio),
      pollWhileVisible(fetchSlowAll, CADENCE.slow),
      pollWhileVisible(fetchFundingNew, CADENCE.slow),
      pollWhileVisible(fetchVenues, CADENCE.venues),
      pollWhileVisible(pump, CADENCE.history),
    ];
    // Back from a hidden tab: the positions refresh at once (old values stay, dimmed, until then).
    const onVisible = () => { if (!document.hidden) fetchFast(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive = false;
      [t1, t2, t3].forEach(clearTimeout);
      stops.forEach(s => s());
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [account]); // eslint-disable-line react-hooks/exhaustive-deps

  const failed = Object.entries(feeds).filter(([, f]) => f.error).map(([k]) => k);
  const retry = useCallback(() => {
    const f = new Set(failed);
    const c = cache.current;
    if (f.has("main") || f.has("xyz") || f.has("orders")) fetchFast();
    if (f.has("ordersXyz")) fetchOrdersXyz();
    for (const kind of ["fills", "funding"]) {
      if (!f.has(kind)) continue;
      const h = c[kind];
      h.retryAt = 0;
      if (h.headErr || h.from == null) forward(kind); else pump();
    }
    if (f.has("spot")) fetchSpot();
    if (f.has("mids")) fetchMids();
    if (f.has("portfolio")) fetchPortfolio();
    if (f.has("staking") || f.has("vaults") || f.has("earn")) fetchSlow();
    if (f.has("abstraction")) fetchAbstraction();
    if (f.has("meta")) fetchMeta();
    if (f.has("other")) { if (c.otherDexs == null) fetchDexList(); else fetchVenues(); }
  }, [failed, fetchFast, fetchOrdersXyz, forward, pump, fetchSpot, fetchMids, fetchPortfolio, fetchSlow, fetchAbstraction, fetchMeta, fetchDexList, fetchVenues]);

  // After a close or cancel: a fresh read of positions and the main open orders (the old page's
  // fetchFast), never one already in flight.
  const afterAction = useCallback(async () => { await fetchFast(true); }, [fetchFast]);

  return {
    ...d, feeds, failed, failedNames: [...new Set(failed.map(k => FEEDS[k] || k))], coverage,
    lastMainAt: feeds.main?.at ?? null, ordersRead: { main: !!feeds.orders?.at, xyz: !!feeds.ordersXyz?.at },
    fetchFast: afterAction, retry,
  };
}
