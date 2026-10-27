// Every Hyperliquid read the Portfolio page makes, from the browser (Portfolio v2, section 6.3).
// Each poll runs only while the tab is visible (pollWhileVisible): a hidden tab costs nothing, and
// coming back refreshes at once. Fast feeds paint first; fills, funding, portfolio, staking, vaults
// and Earn load after first paint, staggered. Fills and funding are incremental: each read asks from
// the newest cached time (inclusive) and replaces that window (utils/portfolio/fillsMerge.js).
// A reply that arrives after the address changed is dropped, so one wallet never shows under another.
import { useCallback, useEffect, useRef, useState } from "react";
import * as hlClient from "../../services/hlClient.js";
import { pollWhileVisible } from "../../utils/visiblePoll.js";
import { mergeWindow, mergeFunding, nextStart, trimWindow } from "../../utils/portfolio/fillsMerge.js";
import { FEEDS } from "./copy.js";

const S = 1000;
export const CADENCE = { fast: 15 * S, venues: 60 * S, spot: 60 * S, orders: 60 * S, fills: 60 * S, mids: 120 * S, portfolio: 300 * S, slow: 600 * S };
const FILL_PAGE = 2000;

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

export default function usePortfolioFeeds(account) {
  const [d, setD] = useState({});
  const [feeds, setFeeds] = useState({});
  const scope = useRef(null);
  const cache = useRef({ fills: [], funding: [], otherDexs: null, sizes: { main: "", xyz: "" } });
  const fastInFlight = useRef(null);

  useEffect(() => {
    const s = { account };
    scope.current = s;
    fastInFlight.current = null;
    setD({}); setFeeds({});
    cache.current = { fills: [], funding: [], otherDexs: null, sizes: { main: "", xyz: "" } };
    return () => { if (scope.current === s) scope.current = null; };
  }, [account]);

  const put = useCallback((key, value) => setD(prev => ({ ...prev, [key]: value })), []);
  const mark = useCallback((name, ok) => setFeeds(prev => ({ ...prev, [name]: { error: !ok, at: ok ? Date.now() : prev[name]?.at ?? null } })), []);

  // One read: answered only while the same address is shown; null counts as a failure.
  const read = useCallback(async (name, load, apply) => {
    const s = scope.current;
    if (!account) return false;
    try {
      const v = await load();
      if (v == null) throw new Error("No reading");
      if (scope.current !== s) return false;
      apply(v);
      mark(name, true);
      return true;
    } catch {
      if (scope.current === s) mark(name, false);
      return false;
    }
  }, [account, mark]);

  const fetchOrders = useCallback(async () => {
    await Promise.all([
      read("orders", () => hlClient.getDexOpenOrders(account, ""), v => put("orders", v)),
      cache.current.hasXyz ? read("ordersXyz", () => hlClient.getDexOpenOrders(account, "xyz"), v => put("ordersXyz", v)) : null,
    ]);
  }, [account, read, put]);

  const fetchFills = useCallback(async (first = false) => {
    const c = cache.current;
    let start = nextStart(c.fills);
    let merged = c.fills;
    for (let page = 0; page < (first ? 6 : 2); page++) {
      let got = null;
      const ok = await read("fills", () => hlClient.getUserFillsByTime(account, start), v => { got = v; });
      if (!ok || !got) return;
      merged = trimWindow(mergeWindow(merged, got, start));
      if (got.length < FILL_PAGE) break;
      start = got.reduce((m, f) => Math.max(m, f.time), start);
    }
    c.fills = merged;
    put("fills", merged);
  }, [account, read, put]);

  const fetchFunding = useCallback(async () => {
    const c = cache.current;
    let start = c.funding.length ? c.funding[c.funding.length - 1].time : Date.now() - 30 * 86400_000;
    let merged = c.funding;
    for (let page = 0; page < 8; page++) {
      let got = null;
      const ok = await read("funding", () => hlClient.getUserFunding(account, start), v => { got = v; });
      if (!ok || !got) return;
      merged = trimWindow(mergeFunding(merged, got, start));
      if (got.length < 500) break;
      start = got[got.length - 1].time;
    }
    c.funding = merged;
    put("funding", merged);
  }, [account, read, put]);

  // Main and xyz every 15 s (the old page's rate). A size change refreshes orders and fills at once.
  // One read at a time: a tick, the tab coming back and an action's refresh never stack up.
  const fetchFast = useCallback(async (fresh = false) => {
    if (!account) return;
    if (fastInFlight.current && !fresh) return fastInFlight.current;
    const run = Promise.all([
      read("main", () => hlClient.getClearinghouseState(account), v => {
        put("main", v);
        const k = sizeKey(v);
        if (cache.current.sizes.main && k !== cache.current.sizes.main) { fetchOrders(); fetchFills(); }
        cache.current.sizes.main = k;
      }),
      read("xyz", () => hlClient.getXyzClearinghouseState(account), v => {
        put("xyz", v);
        cache.current.hasXyz = (v.assetPositions || []).length > 0;
        const k = sizeKey(v);
        if (cache.current.sizes.xyz && k !== cache.current.sizes.xyz) fetchOrders();
        cache.current.sizes.xyz = k;
      }),
    ]).finally(() => { if (fastInFlight.current === run) fastInFlight.current = null; });
    fastInFlight.current = run;
    await run;
  }, [account, read, put, fetchOrders, fetchFills]);

  const fetchVenues = useCallback(async () => {
    const list = cache.current.otherDexs;
    if (!list?.length) return;
    const out = {};
    const oks = await Promise.all(list.map(dex => read("other", () => hlClient.getDexClearinghouseState(account, dex), v => { out[dex] = v; })));
    if (oks.some(Boolean)) setD(prev => ({ ...prev, others: { ...(prev.others || {}), ...out } }));
  }, [account, read]);

  // Once per visit: the builder dexes (each probed once; only those with a balance are polled),
  // spot names, the account mode, then 30 days of fills and funding.
  const fetchOnce = useCallback(async () => {
    await read("meta", () => hlClient.getSpotMeta(), v => put("spotMeta", v));
    await read("other", () => hlClient.getPerpDexs(), async dexs => {
      const names = (dexs || []).filter(Boolean).map(x => x.name).filter(n => n && n !== "xyz");
      const out = {};
      await Promise.all(names.map(dex => hlClient.getDexClearinghouseState(account, dex).then(st => {
        if (parseFloat(st?.marginSummary?.accountValue) || st?.assetPositions?.length) out[dex] = st;
      }).catch(() => {})));
      cache.current.otherDexs = Object.keys(out);
      put("others", out);
    });
    read("abstraction", () => hlClient.getUserAbstraction(account), v => put("abstraction", v));
    await fetchFills(true);
    await fetchFunding();
  }, [account, read, put, fetchFills, fetchFunding]);

  const fetchSlow = useCallback(async () => {
    await Promise.all([
      read("staking", () => hlClient.getDelegatorSummary(account), v => put("delegator", v)),
      read("vaults", () => hlClient.getVaultEquities(account), v => put("vaults", v)),
      read("earn", () => hlClient.getBorrowLendState(account), v => put("earn", v)),
    ]);
  }, [account, read, put]);

  const fetchPortfolio = useCallback(() => read("portfolio", () => hlClient.getPortfolio(account).catch(() => null), v => put("portfolio", portfolioOf(v))), [account, read, put]);
  const fetchSpot = useCallback(() => read("spot", () => hlClient.getSpotState(account), v => put("spot", v)), [account, read, put]);
  const fetchMids = useCallback(() => read("mids", () => hlClient.getAllMids(), v => put("mids", v)), [read, put]);

  useEffect(() => {
    if (!account) return undefined;
    let alive = true;
    const later = (ms, fn) => setTimeout(() => { if (alive) fn(); }, ms);
    // First paint: positions, orders, spot and mids; the rest after, staggered.
    fetchFast().then(() => alive && fetchOrders());
    fetchSpot(); fetchMids();
    const t1 = later(600, fetchPortfolio);
    const t2 = later(1200, fetchSlow);
    const t3 = later(1800, fetchOnce);
    const stops = [
      pollWhileVisible(fetchFast, CADENCE.fast),
      pollWhileVisible(fetchOrders, CADENCE.orders),
      pollWhileVisible(() => fetchFills(), CADENCE.fills),
      pollWhileVisible(fetchSpot, CADENCE.spot),
      pollWhileVisible(fetchMids, CADENCE.mids),
      pollWhileVisible(fetchPortfolio, CADENCE.portfolio),
      pollWhileVisible(fetchSlow, CADENCE.slow),
      pollWhileVisible(fetchFunding, CADENCE.slow),
      pollWhileVisible(fetchVenues, CADENCE.venues),
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
    if (f.has("main") || f.has("xyz")) fetchFast();
    if (f.has("orders") || f.has("ordersXyz")) fetchOrders();
    if (f.has("fills")) fetchFills();
    if (f.has("funding")) fetchFunding();
    if (f.has("spot")) fetchSpot();
    if (f.has("mids")) fetchMids();
    if (f.has("portfolio")) fetchPortfolio();
    if (f.has("staking") || f.has("vaults") || f.has("earn")) fetchSlow();
    if (f.has("other") || f.has("meta")) fetchOnce();
  }, [failed, fetchFast, fetchOrders, fetchFills, fetchFunding, fetchSpot, fetchMids, fetchPortfolio, fetchSlow, fetchOnce]);

  // After a close or cancel: a fresh read of positions and orders, never one already in flight.
  const afterAction = useCallback(async () => { await fetchFast(true); await fetchOrders(); }, [fetchFast, fetchOrders]);

  return {
    ...d, feeds, failed, failedNames: [...new Set(failed.map(k => FEEDS[k] || k))],
    lastMainAt: feeds.main?.at ?? null, ordersRead: { main: !!feeds.orders?.at, xyz: !!feeds.ordersXyz?.at },
    fetchFast: afterAction, retry,
  };
}
