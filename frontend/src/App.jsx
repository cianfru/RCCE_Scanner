import SectorStrip from "./components/SectorStrip.jsx";
import { inGroup, SECTOR_SHORT } from "./utils/sectors.js";
import "./terminal.css";
import "./traders.css";
import { useState, useEffect, useCallback, useMemo, useRef, lazy, Suspense } from "react";
import { useNavigate, useLocation, Navigate } from "react-router-dom";
import { T, REGIME_ORDER, MCAP_RANK, getBaseSymbol } from "./theme.js";
import { marketHref, timeframeFrom } from "./utils/researchNavigation.js";
import { activeMainTab as mainTabFor, mainTabTargets, readLastScanner, writeLastScanner } from "./utils/mainNav.js";
import { addressFromPath, profilePath } from "./utils/traderBoard.js";
import { codename } from "./utils/walletName.js";
import { useTheme } from "./ThemeContext";
import useViewport from "./hooks/useViewport.js";
import useFavorites from "./hooks/useFavorites.js";
import { useSharedWorker } from "./hooks/useSharedWorker.js";
import { useWebSocket } from "./hooks/useWebSocket.js";
import { feedNeeds, needsKey } from "./utils/feedNeeds.js";
import { overlayPrices, priceMoves } from "./utils/livePrices.js";
import FadeIn from "./components/FadeIn.jsx";
import MarketSummary from "./components/MarketSummary.jsx";
import ScannerControls from "./components/ScannerControls.jsx";
import AdminNotice from "./components/AdminNotice.jsx";
import { matchesSignal } from "./utils/marketSummary.js";
import { ladderItems } from "./components/SignalLadder.jsx";
import PositionAlerts from "./components/PositionAlerts.jsx";
import DataTable from "./components/DataTable.jsx";
import DetailPanel from "./components/DetailPanel.jsx";
import GroupModal from "./components/GroupModal.jsx";
import GlassCard from "./components/GlassCard.jsx";
import AppHeader from "./components/AppHeader.jsx";
import MobileTabBar from "./components/MobileTabBar.jsx";
import SettingsPage from "./pages/SettingsPage.jsx";
import Tabs from "./components/Tabs.jsx";
import NavDrawer from "./components/NavDrawer.jsx";
import HitRateStrip from "./components/HitRateStrip.jsx";
import PageTitle from "./components/PageTitle.jsx";
import PageSkeleton from "./components/PageSkeleton.jsx";
import NotFound from "./components/NotFound.jsx";
import GlobalSearch from "./components/GlobalSearch.jsx";
import { trackView } from "./usage.js";

// Pages load their code on first visit; the shell and the scanner stay in the main bundle.
const BacktestPanel = lazy(() => import("./components/BacktestPanel.jsx"));
const ExecutorPanel = lazy(() => import("./components/ExecutorPanel.jsx"));
const TradingPanel = lazy(() => import("./components/TradingPanel.jsx"));
const SignalLogPanel = lazy(() => import("./components/SignalLogPanel.jsx"));
const AnalyticsPanel = lazy(() => import("./components/AnalyticsPanel.jsx"));
const ChatPanel = lazy(() => import("./components/ChatPanel.jsx"));
const TradFiPanel = lazy(() => import("./components/TradFiPanel.jsx"));
const HyperLensPanel = lazy(() => import("./components/HyperLensPanel.jsx"));
const CoinPage = lazy(() => import("./pages/CoinPage.jsx"));
const RadarPage = lazy(() => import("./pages/RadarPage.jsx"));
const BridgePage = lazy(() => import("./pages/BridgePage.jsx"));
const TraderPage = lazy(() => import("./pages/TraderPage.jsx"));
const IntelPage = lazy(() => import("./pages/IntelPage.jsx"));

// ─── CONFIG ───────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── COLUMN DEFINITIONS ─────────────────────────────────────────────────────
// [sortKey, label, minViewportWidth]

// [sortKey, label, minViewportWidth]
// HEAT absorbs PHASE as a sub-label (EXT/ENTR/EXHS/FADE).
// EXHAUST absorbs FORMING — shows "FLOOR ✓" when floor is confirmed.
import { SCANNER_COLUMNS as COLUMNS } from "./scannerColumns.js";

// ─── MAIN APP ─────────────────────────────────────────────────────────────────

// ─── ROUTE MAPS ──────────────────────────────────────────────────────────────
const ROUTE_TO_TAB = {
  "/scanner": "1d",
  "/radar": "radar",
  "/traders": "traders",
  "/signals": "signals",
  "/analytics": "analytics",
  "/tradfi": "tradfi",
  "/bridge": "bridge",
  "/ai": "chat",
  "/backtest": "backtest",
  "/executor": "executor",
  "/portfolio": "trading",
  "/settings": "settings",
  "/intel": "intel",
};
const TAB_TO_ROUTE = {
  "1d": "/scanner",
  "4h": "/scanner?tf=4h",
  radar: "/radar",
  traders: "/traders",
  hyperlens: "/traders",
  signals: "/signals",
  analytics: "/analytics",
  tradfi: "/tradfi",
  bridge: "/bridge",
  chat: "/ai",
  backtest: "/backtest",
  executor: "/executor",
  trading: "/portfolio",
  settings: "/settings",
  intel: "/intel",
};
// Page titles (h1 and browser tab) of the pages without their own title logic.
const TAB_TITLES = {
  traders: "Traders",
  trading: "Portfolio",
  signals: "Signal Log",
  analytics: "Analytics",
  tradfi: "TradFi",
  bridge: "Bridge",
  backtest: "Backtest",
  executor: "Executor",
  chat: "AI Assist",
  settings: "Settings",
  intel: "Intel",
  notfound: "Page not found",
};
const DEFAULT_SORT = "priority_score";
// A header's first click sorts this way; a second click flips it. Symbol is by market cap, regime by cycle order.
const SORT_DEFAULT_DIR = { priority_score: "desc", zscore: "desc", heat: "desc", conditions: "desc", energy: "desc", momentum: "desc", symbol: "asc", mcap: "asc", regime: "asc" };
const defaultDir = key => SORT_DEFAULT_DIR[key] || "desc";
const validDir = d => (d === "asc" || d === "desc" ? d : null);
const cleanPath = pathname => pathname.replace(/\/$/, "") || "/scanner";

export default function App() {
  const { width, isMobile, isTablet, isDesktop } = useViewport();
  const { mode, toggle } = useTheme();
  const hPad = isMobile ? 16 : isTablet ? 20 : 24;
  const navigate = useNavigate();
  const location = useLocation();

  const path = cleanPath(location.pathname);
  const onScanner = path === "/scanner";
  const marketKind = new URLSearchParams(location.search).get("market") === "spot" ? "spot" : "perpetual";
  // The scanner's query (filters, search, sort) as last seen, so leaving and coming back keeps it.
  const lastScannerSearch = useRef(onScanner ? location.search : "");
  const scannerParams = () => new URLSearchParams(onScanner ? location.search : lastScannerSearch.current);
  const changeMarket = (kind) => {
    setActiveGroupId(null);
    setSearchTerm("");
    setStatCardFilter(null);
    const params = scannerParams();
    for (const k of ["q", "signal", "from"]) params.delete(k);
    params.set("market", kind);
    if (activeTab !== "4h") params.delete("tf");
    navigate(`/scanner?${params}`);
  };
  // Derive activeTab from URL
  const activeTab = useMemo(() => {
    // Scanner route — check tf query param first
    if (path === "/scanner") {
      const sp = new URLSearchParams(location.search);
      const tf = sp.get("tf");
      if (tf === "4h") return "4h";
      return "1d";
    }
    if (/^\/scanner\/[^/]+$/.test(path)) return "1d";      // coin page
    if (path === "/hyperlens") return "traders";            // redirected below
    if (path === "/traders/leaderboard") return "traders";  // the Traders page's Leaderboard view
    if (addressFromPath(path)) return "trader";             // a trader's profile: /trader/0x...
    return ROUTE_TO_TAB[path] || "notfound";
  }, [path, location.search]);

  // Page views for the owner's Intel page (usage.js): one per path, not per filter change.
  useEffect(() => { trackView(path); }, [path]);

  // The scanner timeframe last viewed, for AI Assist
  const lastScannerTf = useRef("1d");
  if (activeTab === "4h" || activeTab === "1d") lastScannerTf.current = activeTab;

  // /trader/:address, the address always lowercase (a mixed-case link is redirected below).
  const traderAddress = activeTab === "trader" ? addressFromPath(path) : null;

  // Detect /scanner/:symbol route for dedicated coin page
  const coinPageSymbol = useMemo(() => {
    const m = path.match(/^\/scanner\/([^/]+)$/);
    if (!m) return null;
    try { return decodeURIComponent(m[1]); } catch { return m[1]; }
  }, [path]);

  // Navigate to coin page on row click (shift+click → DetailPanel slide-out).
  // The coin page gets the timeframe and the view to return to (?from=), plus the scroll position.
  const handleSelectCoin = useCallback((row, event, fromHref) => {
    if (event?.shiftKey) {
      setSelected(row);
      return;
    }
    const tf = row.timeframe === "4h" || row.timeframe === "1d" ? row.timeframe : timeframeFrom(location.search);
    const from = fromHref || (onScanner ? `/scanner${location.search}` : "/scanner");
    const scroll = window.scrollY;
    // The browser's Back button returns to the same spot too.
    navigate(`${location.pathname}${location.search}`, { replace: true, state: { ...location.state, restoreScroll: scroll } });
    navigate(`${marketHref(row, tf)}&from=${encodeURIComponent(from)}`, { state: { scannerScroll: scroll } });
  }, [navigate, location.pathname, location.search, location.state, onScanner]);

  const setActiveTab = useCallback((tab) => {
    if (tab === "4h" || tab === "1d") {
      // Switching timeframe keeps the scanner's filters, search and sort.
      const params = new URLSearchParams(onScanner ? location.search : lastScannerSearch.current);
      params.delete("from");
      if (onScanner || !params.get("market")) params.set("market", marketKind);
      tab === "4h" ? params.set("tf", "4h") : params.delete("tf");
      navigate(`/scanner?${params}`);
    } else {
      navigate(TAB_TO_ROUTE[tab] || "/scanner");
    }
  }, [navigate, marketKind, onScanner, location.search]);

  // Scanner state that lives in the address: ?q, sort, dir, signal, sector.
  const [initialQuery] = useState(() => new URLSearchParams(onScanner ? location.search : ""));

  const [data4h, setData4h] = useState([]);
  const [data1d, setData1d] = useState([]);
  const [consensus4h, setConsensus4h] = useState(null);
  const [consensus1d, setConsensus1d] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scanRunning, setScanRunning] = useState(false);
  const [cacheAge, setCacheAge] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [filterRegime, setFilterRegime] = useState("ALL");
  const [filterSignal, setFilterSignal] = useState("ALL");
  const [sortKey, setSortKey] = useState(() => initialQuery.get("sort") || DEFAULT_SORT);
  const [sortDir, setSortDir] = useState(() => validDir(initialQuery.get("dir")));   // "asc" | "desc"; null = the key's default
  const [statCardFilter, setStatCardFilter] = useState(() => initialQuery.get("signal"));
  const [sectorFilter, setSectorFilter] = useState(() => initialQuery.get("sector"));
  const [lastRefresh, setLastRefresh] = useState(null);

  // Price flash: symbol → "up" | "down" (cleared after 1.2s)
  const [priceFlash, setPriceFlash] = useState(new Map());
  const prevPricesRef = useRef(new Map());

  // TradFi (HIP-3) data
  const [dataTradfi4h, setDataTradfi4h] = useState([]);
  const [dataTradfi1d, setDataTradfi1d] = useState([]);

  // Fear & Greed, for the summary card
  const [sentiment, setSentiment] = useState(null);

  // Portfolio groups
  const [groups, setGroups] = useState([]);
  const [activeGroupId, setActiveGroupId] = useState(null);
  const [showGroupModal, setShowGroupModal] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null);

  // Nav drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState(() => initialQuery.get("q") || "");
  const [tradfiTf, setTradfiTf] = useState("1d");            // TradFi timeframe, in the title row

  // Write one scanner setting into the address (replace, so Back still leaves the scanner).
  // Several writes in one event (a sort writes sort and dir) build on each other.
  const pendingSearch = useRef(null);
  useEffect(() => { pendingSearch.current = null; }, [location.key, location.search]);
  const updateScannerQuery = useCallback((key, value) => {
    const params = new URLSearchParams(pendingSearch.current ?? location.search);
    value ? params.set(key, value) : params.delete(key);
    const qs = params.toString();
    pendingSearch.current = qs ? `?${qs}` : "";
    // A scroll position to restore belongs to the arrival only, not to later filter changes.
    const { restoreScroll, ...state } = location.state || {};
    navigate(`${location.pathname}${pendingSearch.current}`, { replace: true, state });
  }, [navigate, location.pathname, location.search, location.state]);

  // The address drives the scanner: arriving from a back link, a pasted link or history restores it.
  useEffect(() => {
    if (!onScanner) return;
    const params = new URLSearchParams(location.search);
    setSearchTerm(params.get("q") || "");
    setSortKey(params.get("sort") || DEFAULT_SORT);
    setSortDir(validDir(params.get("dir")));
    setStatCardFilter(params.get("signal"));
    setSectorFilter(params.get("sector"));
    lastScannerSearch.current = location.search;
  }, [onScanner, location.search]);

  // Coming back from a coin page: return to the scroll position the coin was opened from.
  // Cards above the grid can settle a moment later, so the position is held briefly unless the user scrolls.
  useEffect(() => {
    const target = location.state?.restoreScroll;
    if (target == null || !(onScanner || path === "/radar")) return undefined;
    let frame = 0, stopped = false;
    const t0 = performance.now();
    const stop = () => { stopped = true; cancelAnimationFrame(frame); };
    const events = ["wheel", "touchstart", "keydown", "pointerdown"];
    events.forEach(e => window.addEventListener(e, stop, { passive: true }));
    const hold = () => {
      if (stopped) return;
      if (Math.abs(window.scrollY - target) > 1) window.scrollTo(0, target);
      if (performance.now() - t0 < 1500) frame = requestAnimationFrame(hold);
    };
    frame = requestAnimationFrame(hold);
    return () => { stop(); events.forEach(e => window.removeEventListener(e, stop)); };
  }, [location.key]); // eslint-disable-line react-hooks/exhaustive-deps

  // Favorites: pinned first, kept in localStorage and synced to /api/favorites (shared store)
  const { favorites, toggle: toggleFavorite } = useFavorites();

  // Backtest badge tracking
  const [backtestSymbols, setBacktestSymbols] = useState(new Set());

  // ── SharedWorker integration ───────────────────────────────────────────────

  const sw = useSharedWorker();
  const wsRef = useWebSocket();

  // Latest price per symbol from the WebSocket (ticks and snapshots); laid over fresh scan rows.
  const livePrice = (rows) => (wsRef.connected ? overlayPrices(rows, prevPricesRef.current) : rows);

  // The header clock only moves forward: a feed refreshed later (TradFi, another tab) can carry an
  // older scan time than a scan notice already seen.
  const clockRef = useRef(0);
  const bumpClock = useCallback((receivedMs, ageS) => {
    const age = Number.isFinite(ageS) ? ageS : null;
    const dataTime = receivedMs - (age && age > 0 ? age * 1000 : 0);
    if (dataTime < clockRef.current) return;
    clockRef.current = dataTime;
    setLastRefresh(new Date(receivedMs));
    setCacheAge(age);
  }, []);

  // Apply worker main-data updates when supported
  useEffect(() => {
    if (!sw.supported || !sw.mainData) return;
    const d = sw.mainData;
    // A feed this page does not show may not be loaded yet; keep what is there.
    if (d.r4h) { setData4h(livePrice(d.r4h.results || [])); setConsensus4h(d.r4h.consensus || null); }
    if (d.r1d) { setData1d(livePrice(d.r1d.results || [])); setConsensus1d(d.r1d.consensus || null); }
    setScanRunning(!!(d.r4h?.scan_running || d.r1d?.scan_running));
    bumpClock(d.timestamp, d.cacheAge !== undefined ? d.cacheAge : d.r4h?.cache_age_seconds);
    if (d.sentiment) setSentiment(d.sentiment);
    if (d.tradfi4h) setDataTradfi4h(d.tradfi4h.results || []);
    if (d.tradfi1d) setDataTradfi1d(d.tradfi1d.results || []);
    setLoading(false);
    setError(null);
  }, [sw.supported, sw.mainData]); // eslint-disable-line react-hooks/exhaustive-deps

  // Forward filter changes to worker
  useEffect(() => {
    if (sw.supported) sw.setFilters(filterRegime, filterSignal);
  }, [sw.supported, sw.setFilters, filterRegime, filterSignal]);

  // Only the feeds this page shows are kept fresh (utils/feedNeeds.js).
  const needs = useMemo(() => feedNeeds(activeTab, { coinPage: !!coinPageSymbol, wsConnected: wsRef.connected,
    lastScannerTf: lastScannerTf.current }), [activeTab, coinPageSymbol, wsRef.connected]);
  const needsId = needsKey(needs);
  const needsRef = useRef(needs);
  needsRef.current = needs;
  useEffect(() => {
    if (sw.supported) sw.setNeeds(needs);
  }, [sw.supported, sw.setNeeds, needsId]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── WebSocket integration (real-time push from backend) ───────────────────

  // Older servers push the full scan state (synthesis-complete); current ones send a scan notice.
  useEffect(() => {
    if (!wsRef.connected || !wsRef.synthesisData) return;
    const d = wsRef.synthesisData;
    setData4h(d.results_4h || []);
    setData1d(d.results_1d || []);
    setConsensus4h(d.consensus_4h || null);
    setConsensus1d(d.consensus_1d || null);
    bumpClock((d.meta?.timestamp || Date.now() / 1000) * 1000, d.meta?.cache_age ?? null);
    setScanRunning(false);
    setLoading(false);
    setError(null);
  }, [wsRef.connected, wsRef.synthesisData, bumpClock]);

  // Delta merge: patch individual symbol updates from drip scan into state (older servers)
  useEffect(() => {
    if (!wsRef.connected || !wsRef.symbolUpdate) return;
    const { symbol, result_4h, result_1d } = wsRef.symbolUpdate;
    if (!symbol) return;

    const merge = (prev, update) => {
      if (!update) return prev;
      const idx = prev.findIndex((r) => r.symbol === symbol);
      if (idx >= 0) {
        const next = [...prev];
        // Preserve synthesized fields (signal, unified_signal, etc.) and merge raw updates
        next[idx] = { ...next[idx], ...update };
        return next;
      }
      // New symbol — append
      return [...prev, update];
    };

    if (result_4h) setData4h((prev) => merge(prev, result_4h));
    if (result_1d) setData1d((prev) => merge(prev, result_1d));
  }, [wsRef.connected, wsRef.symbolUpdate]);

  // Price ticks (every 5 s while visible) patch prices and flash; a snapshot (on connect and when the
  // tab is shown again) patches without flashing.
  const applyPrices = useCallback((ticks, flash) => {
    const flashes = priceMoves(prevPricesRef.current, ticks);
    const patchPrices = (prevData) => {
      let changed = false;
      const next = prevData.map((r) => {
        const newPrice = ticks[r.symbol];
        if (newPrice !== undefined && newPrice !== r.price) {
          changed = true;
          return { ...r, price: newPrice };
        }
        return r;
      });
      return changed ? next : prevData;
    };

    setData4h(patchPrices);
    setData1d(patchPrices);

    if (flash && flashes.size > 0) {
      setPriceFlash(flashes);
      // Clear flashes after animation completes
      setTimeout(() => setPriceFlash(new Map()), 1200);
    }
  }, []);

  useEffect(() => {
    if (wsRef.priceTicks) applyPrices(wsRef.priceTicks, true);
  }, [wsRef.priceTicks, applyPrices]);

  useEffect(() => {
    if (wsRef.priceSnapshot) applyPrices(wsRef.priceSnapshot, false);
  }, [wsRef.priceSnapshot, applyPrices]);

  // ── Data fetching (fallback when SharedWorker unavailable) ────────────────
  // The browser revalidates with the ETag, so an unchanged feed is an empty 304.

  const fetchData = useCallback(async (tf) => {
    const params = new URLSearchParams({ timeframe: tf });
    if (filterRegime !== "ALL") params.append("regime", filterRegime);
    if (filterSignal !== "ALL") params.append("signal", filterSignal);
    const res = await fetch(`${API_BASE}/api/scan?${params}`);
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  }, [filterRegime, filterSignal]);

  // Feed -> when it last loaded. Every feed loads once; after that only what the page shows.
  const fallbackLoaded = useRef({});
  const loadAll = useCallback(async () => {
    if (sw.supported) return; // Worker handles polling
    const n = needsRef.current, loaded = fallbackLoaded.current, now = Date.now();
    const tfs = ["4h", "1d"].filter(tf => n.scan.includes(tf) || !loaded[`scan:${tf}`]);
    const wantTradfi = n.tradfi || !loaded.tradfi;
    const wantSentiment = !loaded.sentiment || (n.sentiment && now - loaded.sentiment >= 300_000);
    setLoading(true);
    setError(null);
    try {
      const scans = await Promise.all(tfs.map(tf => fetchData(tf)));
      tfs.forEach((tf, i) => {
        const r = scans[i];
        loaded[`scan:${tf}`] = now;
        if (tf === "4h") { setData4h(livePrice(r.results || [])); setConsensus4h(r.consensus || null); }
        else { setData1d(livePrice(r.results || [])); setConsensus1d(r.consensus || null); }
      });
      if (scans.length) {
        setScanRunning(!!scans[0].scan_running);
        bumpClock(Date.now(), scans[0].cache_age_seconds);
      }

      try {
        const [sent, tf4h, tf1d] = await Promise.all([
          wantSentiment ? fetch(`${API_BASE}/api/sentiment`).then(r => r.json()).catch(() => null) : null,
          wantTradfi ? fetch(`${API_BASE}/api/tradfi?timeframe=4h`).then(r => r.json()).catch(() => null) : null,
          wantTradfi ? fetch(`${API_BASE}/api/tradfi?timeframe=1d`).then(r => r.json()).catch(() => null) : null,
        ]);
        if (sent) { setSentiment(sent); loaded.sentiment = now; }
        if (tf4h) setDataTradfi4h(tf4h.results || []);
        if (tf1d) setDataTradfi1d(tf1d.results || []);
        if (tf4h && tf1d) loaded.tradfi = now;
      } catch (_) {}
    } catch (e) {
      console.warn("Scanner feed error:", e.message, API_BASE);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [fetchData, sw.supported, bumpClock]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fallback polling — only runs when SharedWorker is unavailable
  useEffect(() => {
    if (sw.supported) return;
    loadAll();
    let interval = setInterval(loadAll, 60 * 1000);

    const handleVisibility = () => {
      clearInterval(interval);
      if (!document.hidden) {
        loadAll();
        interval = setInterval(loadAll, 60 * 1000);
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [loadAll, sw.supported]);

  // A page that shows another feed loads it at once (the fallback; the worker does this itself).
  const needsSeen = useRef(needsId);
  useEffect(() => {
    if (sw.supported || needsSeen.current === needsId) return;
    needsSeen.current = needsId;
    loadAll();
  }, [needsId, sw.supported, loadAll]);

  // A new scan is ready: refetch what this page shows (unchanged feeds come back as empty 304s).
  // Pages without scanner rows only move the header clock.
  useEffect(() => {
    const u = wsRef.scanUpdated;
    if (!u) return;
    if (!needsRef.current.scan.length) bumpClock(u.at, 0);
    setScanRunning(false);
    if (sw.supported) sw.refresh();
    else if (!document.hidden) loadAll();
  }, [wsRef.scanUpdated]); // eslint-disable-line react-hooks/exhaustive-deps

  // Rescan (the watch-group dialog's "Scan now"). Without the admin key the server refuses (403).
  // "Scan already in progress" keeps scanRunning until that scan's data arrives (the feed effects
  // above clear it), for at most 90s.
  const scanWait = useRef(0);
  useEffect(() => () => clearTimeout(scanWait.current), []);
  const triggerScan = async () => {
    if (scanRunning) return;
    setScanRunning(true);
    clearTimeout(scanWait.current);
    let res;
    try {
      res = await fetch(`${API_BASE}/api/scan/refresh`, { method: "POST" });
    } catch (e) {
      console.warn("Scan refresh failed:", e);
      setScanRunning(false);
      return;
    }
    if (!res.ok) {
      console.warn("Scan refresh failed: HTTP", res.status);
      setScanRunning(false);
      return;
    }
    const body = await res.json().catch(() => null);
    if (body?.ok === false) {
      scanWait.current = setTimeout(() => setScanRunning(false), 90 * 1000);
      return;
    }
    // The scan notice refetches when the pass completes; this covers a server without it.
    if (sw.supported) {
      setTimeout(() => sw.refresh(), 3000);
    } else {
      setTimeout(loadAll, 3000);
    }
  };

  // ── Portfolio group management ───────────────────────────────────────────

  const loadGroups = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/groups`);
      if (!res.ok) return;
      const data = await res.json();
      setGroups(data || []);
      // Keep activeGroupId as null (All Assets) by default — only preserve existing selection
      setActiveGroupId(null);
    } catch (_) {}
  }, []);

  useEffect(() => { loadGroups(); }, [loadGroups]);

  const createGroup = async (name, symbols = [], color = "#97FCE4") => {
    try {
      const res = await fetch(`${API_BASE}/api/groups`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, symbols, color }),
      });
      if (res.ok) {
        const g = await res.json();
        await loadGroups();
        setActiveGroupId(g.id);
        return g;
      }
    } catch (_) {}
  };

  const updateGroup = async (id, updates) => {
    try {
      await fetch(`${API_BASE}/api/groups/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      });
      await loadGroups();
    } catch (_) {}
  };

  const deleteGroup = async (id) => {
    try {
      await fetch(`${API_BASE}/api/groups/${id}`, { method: "DELETE" });
      await loadGroups();
      if (activeGroupId === id) {
        setActiveGroupId(groups.length > 1 ? groups.find(g => g.id !== id)?.id : null);
      }
    } catch (_) {}
  };

  const addSymbolToGroup = async (groupId, symbol) => {
    try {
      await fetch(`${API_BASE}/api/groups/${groupId}/symbols`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol }),
      });
      await loadGroups();
    } catch (_) {}
  };

  const removeSymbolFromGroup = async (groupId, symbol) => {
    try {
      await fetch(`${API_BASE}/api/groups/${groupId}/symbols/${encodeURIComponent(symbol)}`, { method: "DELETE" });
      await loadGroups();
    } catch (_) {}
  };

  const loadHyperliquidPerps = async (groupId) => {
    if (!groupId) return;
    try {
      const res = await fetch(`${API_BASE}/api/perpetuals/hyperliquid`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.symbols && data.symbols.length > 0) {
        await fetch(`${API_BASE}/api/groups/${groupId}/symbols/batch`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbols: data.symbols }),
        });
        await loadGroups();
      }
    } catch (e) {
      console.error("Hyperliquid perps fetch failed:", e);
    }
  };

  // Backtest badge
  const refreshBacktestSymbols = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/backtest/symbols`);
      const data = await res.json();
      setBacktestSymbols(new Set(data.symbols || []));
    } catch (_) {}
  }, []);

  useEffect(() => { refreshBacktestSymbols(); }, [refreshBacktestSymbols]);

  // ── Computed data ─────────────────────────────────────────────────────────

  const activeGroup = useMemo(() => groups.find(g => g.id === activeGroupId), [groups, activeGroupId]);
  const activeGroupSymbols = useMemo(() => {
    if (!activeGroup) return null;
    return new Set(activeGroup.symbols);
  }, [activeGroup]);

  const filtered4h = useMemo(() => {
    let d = data4h.filter(r => r.market_kind === marketKind);
    if (activeGroupSymbols) d = d.filter(r => activeGroupSymbols.has(r.symbol));
    if (searchTerm) { const q = searchTerm.toUpperCase(); d = d.filter(r => r.symbol?.toUpperCase().includes(q)); }
    return d;
  }, [data4h, activeGroupSymbols, searchTerm, marketKind]);

  const filtered1d = useMemo(() => {
    let d = data1d.filter(r => r.market_kind === marketKind);
    if (activeGroupSymbols) d = d.filter(r => activeGroupSymbols.has(r.symbol));
    if (searchTerm) { const q = searchTerm.toUpperCase(); d = d.filter(r => r.symbol?.toUpperCase().includes(q)); }
    return d;
  }, [data1d, activeGroupSymbols, searchTerm, marketKind]);

  // Summary card and sector strip: the whole market (or the watch group), never the search box.
  const marketRows4h = useMemo(() => data4h.filter(r => r.market_kind === marketKind), [data4h, marketKind]);
  const marketRows1d = useMemo(() => data1d.filter(r => r.market_kind === marketKind), [data1d, marketKind]);
  const tfMarketRows = activeTab === "4h" ? marketRows4h : marketRows1d;
  const tfScopeRows = useMemo(() => activeGroupSymbols ? tfMarketRows.filter(r => activeGroupSymbols.has(r.symbol)) : tfMarketRows,
    [tfMarketRows, activeGroupSymbols]);
  const scopeLabel = activeGroup ? `in ${activeGroup.name}` : marketKind === "spot" ? "spot markets" : "perps";

  // The direction in effect: the address's ?dir, or the key's default.
  const activeDir = sortDir || defaultDir(sortKey);
  const sortResults = (results) => {
    const flip = activeDir === defaultDir(sortKey) ? 1 : -1;
    const condRatio = r => (r.conditions_total ? (r.conditions_met || 0) / r.conditions_total : 0);
    const compare = (a, b) => {
      if (sortKey === "mcap" || sortKey === "symbol") {
        return (MCAP_RANK[a.symbol] ?? 999) - (MCAP_RANK[b.symbol] ?? 999);
      }
      if (sortKey === "regime") {
        const ri = REGIME_ORDER.indexOf(a.regime) - REGIME_ORDER.indexOf(b.regime);
        if (ri !== 0) return ri;
        return (b.zscore || 0) - (a.zscore || 0);
      }
      if (sortKey === "zscore") return (b.zscore || 0) - (a.zscore || 0);
      if (sortKey === "momentum") return (b.momentum || 0) - (a.momentum || 0);
      if (sortKey === "heat") return (b.heat || 0) - (a.heat || 0);
      if (sortKey === "energy") return (b.energy || 0) - (a.energy || 0);
      if (sortKey === "conditions") return condRatio(b) - condRatio(a);
      if (sortKey === "priority_score") return (b.priority_score || 0) - (a.priority_score || 0);
      return 0;
    };
    return [...results].sort((a, b) => {
      // Favorites always first, in either direction
      const fa = favorites.has(a.symbol) ? 0 : 1;
      const fb = favorites.has(b.symbol) ? 0 : 1;
      if (fa !== fb) return fa - fb;
      return flip * compare(a, b);
    });
  };

  const sorted4h = sortResults(filtered4h);
  const sorted1d = sortResults(filtered1d);

  // TradFi sorted data
  const sortedTradfi = useMemo(() => {
    let d = activeTab === "tradfi" ? dataTradfi1d : dataTradfi4h;
    if (searchTerm) { const q = searchTerm.toUpperCase(); d = d.filter(r => r.symbol?.toUpperCase().includes(q)); }
    return sortResults(d);
  }, [activeTab, dataTradfi1d, dataTradfi4h, searchTerm, sortKey, activeDir]);

  // Apply stat card signal filter to table data
  const inSector = (data) => sectorFilter ? data.filter(r => inGroup(r, sectorFilter.includes("|") ? "pocket" : "sector", sectorFilter)) : data;
  const applyStatFilter = (rows) => {
    const data = inSector(rows);
    if (!statCardFilter) return data;
    return data.filter(r => matchesSignal(r, statCardFilter));
  };
  const display4h = applyStatFilter(sorted4h);
  const display1d = applyStatFilter(sorted1d);
  const displayTradfi = applyStatFilter(sortedTradfi);

  // The engine consensus (every scanned market, perps and spot) and the rows it was counted on.
  const activeConsensus = activeTab === "4h" ? consensus4h : consensus1d;
  const consensusRows = activeTab === "4h" ? data4h : data1d;
  const showDashboard = activeTab === "4h" || activeTab === "1d";
  const scannerTitle = activeGroup ? activeGroup.name : marketKind === "spot" ? "Spot markets" : "Perpetuals";
  const radarTf = activeTab === "radar" ? timeframeFrom(location.search) : null;

  // Main tabs: which is active, and where each goes. Scanner returns to the last scanner view
  // (kept for the session); Radar opens on that view's timeframe.
  const mainTab = mainTabFor(location.pathname, location.search);
  const scannerTarget = onScanner ? `/scanner${location.search}` : (readLastScanner() || "/scanner");
  useEffect(() => { if (onScanner) writeLastScanner(`/scanner${location.search}`); }, [onScanner, location.search]);
  const lastTf = timeframeFrom(scannerTarget.split("?")[1] || "");
  const tabTargets = mainTabTargets({ lastScanner: scannerTarget, lastScannerTf: lastTf });

  // Coins-and-traders search in the header, on every page. Hyperliquid's market list feeds it; the
  // scanner rows, where loaded, carry a coin's timeframe to its page.
  const searchRows = data1d.length ? data1d : data4h;

  // The header's compact 4H | 1D drives the page's own timeframe (scanner or Radar).
  const setHeaderTimeframe = (tf) => {
    if (activeTab !== "radar") { setActiveTab(tf); return; }
    const params = new URLSearchParams(location.search);
    params.set("tf", tf);
    navigate(`/radar?${params}`, { replace: true, state: location.state });
  };

  // Browser tab title. The coin page refines its own ("BTC · Reflex") once its data is in.
  useEffect(() => {
    document.title = coinPageSymbol ? `${getBaseSymbol(coinPageSymbol)} · Reflex`
      : showDashboard ? `${scannerTitle} ${activeTab.toUpperCase()} · Reflex`
      : activeTab === "radar" ? `Radar ${radarTf.toUpperCase()} · Reflex`
      : activeTab === "trader" ? `${codename(traderAddress)} · Reflex`
      : `${TAB_TITLES[activeTab] || "Reflex"} · Reflex`;
  }, [coinPageSymbol, showDashboard, scannerTitle, activeTab, radarTf, traderAddress]);

  // ── Render ────────────────────────────────────────────────────────────────

  // Same header again flips the direction; a new header starts from its default. Both live in the address.
  const onSort = key => {
    const next = key === sortKey ? (activeDir === "desc" ? "asc" : "desc") : defaultDir(key);
    const dir = next === defaultDir(key) ? null : next;
    setSortKey(key); setSortDir(dir);
    updateScannerQuery("sort", key === DEFAULT_SORT ? null : key);
    updateScannerQuery("dir", dir);
  };
  // The grid toolbar: what the view is narrowed by, in each filter's own colour, and one Clear.
  const signalWord = statCardFilter && ladderItems().find(([k]) => k === statCardFilter);
  const filterWords = [
    statCardFilter && { text: signalWord ? signalWord[1] : statCardFilter.replaceAll("_", " ").toLowerCase(), color: signalWord ? signalWord[2] : T.text1 },
    sectorFilter && { text: sectorFilter.split("|").map(n => SECTOR_SHORT[n] || n).join(" · "), color: T.accent },
    searchTerm && { text: `\u201c${searchTerm.trim().toLowerCase()}\u201d`, color: T.text1 },
  ].filter(Boolean);
  const clearGridFilters = () => {
    setStatCardFilter(null); setSectorFilter(null); setSearchTerm("");
    updateScannerQuery("signal", null); updateScannerQuery("sector", null); updateScannerQuery("q", null);
  };

  // The old HyperLens address opens Traders, keeping its query.
  if (path === "/hyperlens") return <Navigate to={"/traders" + location.search} replace />;
  if (traderAddress && traderAddress !== traderAddress.toLowerCase()) return <Navigate to={profilePath(traderAddress) + location.search} replace />;

  const pageMargin = { marginTop: isMobile ? 16 : 20 };

  // AI Assist fits the viewport and scrolls only its thread, so the page itself has nothing to scroll
  // (a scrolled page slides the chat's top row under the floating capsule): no min-height, no bottom pad.
  return (
    <div className="reflex-terminal" style={{ minHeight: activeTab === "chat" ? undefined : "100vh", background: T.bg, color: T.text1, position: "relative" }}>
      {/* Fonts & Global Styles */}
      <style>{`
        :where(.reflex-terminal), :where(.reflex-terminal *) { box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font-geist-sans), sans-serif; }
        body { background: var(--t-bg); -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; font-family: var(--font-geist-sans), sans-serif; font-size: 14px; font-feature-settings: "tnum"; }
        table, th, td, span, div, button, select, input, textarea, p, label { font-family: inherit; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--t-scrollThumb); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--t-scrollHover); }
        tr:hover td:not(.scanner-symbol) { background: transparent !important; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes glow { 0%,100%{box-shadow: 0 0 12px rgba(151,252,228,0.12);} 50%{box-shadow: 0 0 24px rgba(151,252,228,0.25);} }
        @keyframes orbBreathe { 0%,100%{opacity:0.6;transform:scale(1)} 50%{opacity:0.9;transform:scale(1.08)} }
        @keyframes fadeInUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
        .fade-in-up { animation: fadeInUp 0.4s ease-out both; }
        .shimmer-loading {
          background: linear-gradient(90deg, var(--t-overlay04) 25%, var(--t-overlay10) 50%, var(--t-overlay04) 75%);
          background-size: 200% 100%;
          animation: shimmer 1.5s infinite;
          border-radius: 6px;
        }
        select { outline: none; appearance: none; -webkit-appearance: none; }
        select option { background: var(--t-selectBg); color: var(--t-text3); }
        .notable-scroll::-webkit-scrollbar { display: none; }
        .notable-scroll { scrollbar-width: none; -ms-overflow-style: none; }
        .apple-btn {
          position: relative;
          background: linear-gradient(180deg, var(--t-overlay10) 0%, var(--t-overlay04) 100%);
          border: 1px solid var(--t-overlay15);
          border-radius: 10px;
          color: var(--t-text2);
          cursor: pointer;
          transition: all 0.2s cubic-bezier(0.25, 0.46, 0.45, 0.94);
          box-shadow: 0 1px 2px var(--t-shadow), inset 0 1px 0 var(--t-overlay06);
        }
        .apple-btn:hover {
          background: linear-gradient(180deg, var(--t-overlay15) 0%, var(--t-overlay08) 100%);
          border-color: var(--t-overlay25);
          box-shadow: 0 2px 8px var(--t-shadowDeep), inset 0 1px 0 var(--t-overlay08);
          color: var(--t-text1);
        }
        .apple-btn:active {
          background: linear-gradient(180deg, var(--t-overlay06) 0%, var(--t-overlay08) 100%);
          box-shadow: 0 0px 1px var(--t-shadow), inset 0 1px 3px var(--t-shadow);
          transform: scale(0.98);
        }
        .apple-btn-accent {
          background: var(--t-accent);
          border: 1px solid var(--t-accent);
          color: var(--t-bg);
          box-shadow: none;
        }
        .apple-btn-accent:hover {
          background: var(--t-accent);
          border-color: var(--t-accent);
          filter: brightness(1.08);
          color: var(--t-bg);
        }
        .apple-btn-accent:active {
          background: var(--t-accent);
          box-shadow: none;
          transform: scale(0.98);
        }
        .apple-select {
          border: 1px solid var(--t-overlay15);
          border-radius: 10px;
          box-shadow: 0 1px 2px var(--t-shadow), inset 0 1px 0 var(--t-overlay06);
          transition: all 0.2s cubic-bezier(0.25, 0.46, 0.45, 0.94);
          outline: none; appearance: none; -webkit-appearance: none;
        }
        .apple-select:hover {
          border-color: var(--t-overlay25);
          box-shadow: 0 2px 8px var(--t-shadowDeep), inset 0 1px 0 var(--t-overlay08);
        }
        .apple-select:focus {
          border-color: rgba(151,252,228,0.4);
          box-shadow: 0 0 0 3px rgba(151,252,228,0.08), 0 1px 2px var(--t-shadow);
        }
      `}</style>

      {/* ── AMBIENT BACKGROUND ORBS ── */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0, overflow: "hidden" }}>
        <div style={{
          position: "absolute", top: "-10%", left: "15%", width: 600, height: 600,
          borderRadius: "50%", background: "radial-gradient(circle, rgba(151,252,228,0.07) 0%, transparent 70%)",
          filter: "blur(80px)", animation: "orbBreathe 10s ease-in-out infinite",
        }} />
        <div style={{
          position: "absolute", bottom: "10%", left: "30%", width: 450, height: 450,
          borderRadius: "50%", background: "radial-gradient(circle, rgba(52,211,153,0.04) 0%, transparent 70%)",
          filter: "blur(80px)", animation: "orbBreathe 10s ease-in-out infinite 6s",
        }} />
      </div>

      {/* ── NAV DRAWER (More) ── */}
      <NavDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        isMobile={isMobile}
        groups={groups}
        marketKind={marketKind}
        onMarketChange={changeMarket}
        activeGroupId={activeGroupId}
        onGroupChange={setActiveGroupId}
        onGroupCreate={() => { setEditingGroup(null); setShowGroupModal(true); }}
        onGroupEdit={(g) => { setEditingGroup(g); setShowGroupModal(true); }}
        onWatchlistSelect={(gId) => { setActiveGroupId(gId); if (activeTab !== "4h" && activeTab !== "1d") setActiveTab("1d"); }}
        scanData={activeTab === "1d" ? data1d : data4h}
      />

      {/* ── PHONE TAB BAR (below 900px; before the header so the header's menus open above it) ── */}
      {width < 900 && activeTab !== "chat" && <MobileTabBar activeKey={mainTab} targets={tabTargets} />}

      {/* ── HEADER ── */}
      <AppHeader
        width={width} isMobile={isMobile} mode={mode} onToggleTheme={toggle}
        activeTab={activeTab} activeMainTab={mainTab} tabTargets={tabTargets} radarTf={radarTf || lastTf}
        drawerOpen={drawerOpen} onOpenDrawer={() => setDrawerOpen(true)}
        onBrand={() => {
          navigate("/scanner");
          setFilterRegime("ALL"); setFilterSignal("ALL"); setStatCardFilter(null);
          setSectorFilter(null); setSearchTerm(""); setSortKey(DEFAULT_SORT); setSortDir(null);
        }}
        lastRefresh={lastRefresh} cacheAge={cacheAge} error={error} scanRunning={scanRunning}
        timeframe={activeTab === "radar" ? radarTf : activeTab === "4h" ? "4h" : "1d"}
        onTimeframe={setHeaderTimeframe}
        compactTfRoute={showDashboard ? "scanner" : activeTab === "radar" ? "radar" : null}
        search={<GlobalSearch rows={searchRows} radarTf={radarTf || lastTf} phone={isMobile} compact={width >= 900 && width < 1280}
          onOpenCoin={row => handleSelectCoin(row)} />}
      />

      {/* ── ERROR ── */}
      {error && (
        <div style={{
          padding: `0 ${hPad}px`, marginTop: 16,
          ...(isMobile && {
            position: "fixed", top: 70, left: 0, right: 0,
            zIndex: 200, padding: "0 12px",
          }),
        }}>
          <GlassCard style={{
            padding: "12px 18px",
            border: "1px solid rgba(248,113,113,0.15)",
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <span style={{ fontSize: 13, color: T.red, fontFamily: T.font }}>
              The scanner feed is unavailable. Retrying.
            </span>
          </GlassCard>
        </div>
      )}

      <main id="content" style={activeTab === "chat" ? undefined : { paddingBottom: "calc(var(--tabbar-space) + 16px)" }}>
      {/* ── COIN PAGE (dedicated /scanner/:symbol route) ── */}
      {coinPageSymbol && (
        <Suspense fallback={<div style={{ padding: isMobile ? 16 : 24 }}><PageSkeleton /></div>}>
          <CoinPage scanData4h={data4h} scanData1d={data1d} urlSymbol={coinPageSymbol} />
        </Suspense>
      )}

      {/* ── SECTION TITLE (hidden for chat and coin page — full-immersion mode; Radar and 404 draw their own) ── */}
      {!coinPageSymbol && activeTab !== "chat" && activeTab !== "radar" && activeTab !== "notfound" && activeTab !== "trader" && (
        <div className="scanner-head" style={{
          padding: `${isMobile ? T.sp4 : T.sp3}px ${hPad}px ${T.sp1}px`,
          display: "flex", alignItems: "center", justifyContent: "flex-start", flexWrap: "wrap", gap: "12px 20px",
        }}>
          <PageTitle>{showDashboard ? scannerTitle : TAB_TITLES[activeTab]}</PageTitle>
          {showDashboard && <ScannerControls activeTab={activeTab} onTabChange={setActiveTab} marketKind={marketKind} onMarketChange={changeMarket} />}
          {activeTab === "tradfi" && <Tabs label="Timeframe" items={[{ key: "4h", label: "4H" }, { key: "1d", label: "1D" }]} value={tradfiTf} onChange={setTradfiTf} />}

        </div>
      )}

      {/* ── MAIN CONTENT (hidden when on coin page) ── */}
      {!coinPageSymbol && <div style={{ paddingTop: 0, paddingLeft: hPad, paddingRight: hPad, paddingBottom: activeTab === "chat" ? 0 : isMobile ? 80 : 60, position: "relative" }}>

        {/* Until the first scan arrives, a glass placeholder holds the summary's space so nothing below jumps. */}
        {showDashboard && tfMarketRows.length === 0 && (
          <GlassCard className="ms-skeleton" style={{ position: "relative", overflow: "hidden" }}>
            <div className="shimmer-loading" aria-hidden="true" />
          </GlassCard>
        )}
        {showDashboard && tfMarketRows.length > 0 && (
          <MarketSummary regimeRows={consensusRows} signalRows={tfScopeRows} consensus={activeConsensus} sentiment={sentiment}
            timeframe={activeTab === "4h" ? "4h" : "1d"} scopeLabel={scopeLabel} spot={marketKind === "spot"}
            activeSignalFilter={statCardFilter} onSignalFilter={v => { setStatCardFilter(v); updateScannerQuery("signal", v); }} />
        )}

        {showDashboard && <SectorStrip rows={tfScopeRows} baseRows={tfMarketRows} loading={tfMarketRows.length === 0}
          value={sectorFilter} onChange={v => { setSectorFilter(v); updateScannerQuery("sector", v); }} timeframe={activeTab === "4h" ? "4h" : "1d"} spot={marketKind === "spot"} />}

        {showDashboard && <PositionAlerts isMobile={isMobile} />}

        {showDashboard && marketKind === "spot" && (
          <p style={{ margin: `${isMobile ? 12 : 16}px 0 0`, fontSize: 12, lineHeight: 1.5, color: T.text3, fontFamily: T.font }}>
            Spot markets have no funding rate, so Strong long is not issued on spot.
          </p>
        )}

        {showDashboard && (
          <div id="market-grid" style={{ scrollMarginTop: 100,
            display: "flex", flexDirection: isDesktop ? "row" : "column",
            gap: isDesktop ? 16 : 12,
          }}>
            {(activeTab === "4h" || activeTab === "1d") && (
              <FadeIn key={activeTab} delay={150} style={{ flex: 1, minWidth: 0 }}>
                <DataTable variant="scanner" tf={activeTab} results={activeTab === "4h" ? display4h : display1d} label={null}
                  sortKey={sortKey} sortDir={activeDir} onSort={onSort} selected={selected} onSelect={handleSelectCoin}
                  visibleColumns={COLUMNS} isMobile={isMobile} backtestSymbols={backtestSymbols} loading={loading}
                  favorites={favorites} onToggleFavorite={toggleFavorite} priceFlash={priceFlash}
                  totalCount={tfScopeRows.length} scopeLabel={scopeLabel} filterWords={filterWords} onClear={clearGridFilters} />
              </FadeIn>
            )}
          </div>
        )}

        {activeTab === "radar" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <RadarPage results4h={data4h} results1d={data1d} onSelect={row => handleSelectCoin(row, null, `${location.pathname}${location.search}`)} />
          </Suspense>
        )}

        {activeTab === "backtest" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <FadeIn delay={300} style={pageMargin}>
              <BacktestPanel isMobile={isMobile} onBacktestComplete={refreshBacktestSymbols} />
            </FadeIn>
          </Suspense>
        )}

        {activeTab === "executor" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <FadeIn delay={300} style={pageMargin}>
              <ExecutorPanel api={API_BASE} />
            </FadeIn>
          </Suspense>
        )}

        {activeTab === "trading" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <FadeIn delay={300} style={pageMargin}>
              <TradingPanel api={API_BASE} />
            </FadeIn>
          </Suspense>
        )}

        {activeTab === "signals" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <FadeIn delay={300} style={pageMargin}>
              <SignalLogPanel api={API_BASE} isMobile={isMobile} scanData4h={data4h} scanData1d={data1d} />
            </FadeIn>
          </Suspense>
        )}

        {activeTab === "analytics" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <FadeIn delay={300} style={pageMargin}>
              <AnalyticsPanel isMobile={isMobile} />
            </FadeIn>
          </Suspense>
        )}

        {activeTab === "tradfi" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
          <FadeIn delay={300} style={pageMargin}>
            <TradFiPanel
              results={displayTradfi}
              data4h={dataTradfi4h}
              data1d={dataTradfi1d}
              tfView={tradfiTf}
              selected={selected}
              onSelect={setSelected}
              isMobile={isMobile}
              loading={loading}
            />
          </FadeIn>
          </Suspense>
        )}

        {activeTab === "bridge" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <BridgePage style={pageMargin} />
          </Suspense>
        )}

        {activeTab === "chat" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <ChatPanel isMobile={isMobile} timeframe={lastScannerTf.current}
              selectedSymbol={selected && !selected.tradfi_coin ? selected.symbol : null} />
          </Suspense>
        )}

        {activeTab === "traders" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <FadeIn delay={300} style={pageMargin}>
              <HyperLensPanel isMobile={isMobile} />
            </FadeIn>
          </Suspense>
        )}

        {activeTab === "trader" && traderAddress && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <TraderPage address={traderAddress.toLowerCase()} />
          </Suspense>
        )}

        {activeTab === "settings" && <SettingsPage style={pageMargin} />}

        {activeTab === "intel" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <IntelPage style={pageMargin} />
          </Suspense>
        )}

        {activeTab === "notfound" && <NotFound targets={tabTargets} radarTf={lastTf} />}
      </div>}
      </main>

      {/* ── GROUP MODAL ── */}
      {showGroupModal && (
        <GroupModal
          editingGroup={editingGroup} groups={groups}
          onClose={() => setShowGroupModal(false)}
          onCreateGroup={createGroup} onUpdateGroup={updateGroup} onDeleteGroup={deleteGroup}
          onAddSymbol={addSymbolToGroup} onRemoveSymbol={removeSymbolFromGroup}
          onLoadHyperliquidPerps={loadHyperliquidPerps} onScanNow={triggerScan} isMobile={isMobile}
        />
      )}

      {/* ── DETAIL PANEL ── */}
      <AdminNotice />
      <DetailPanel selected={selected} isMobile={isMobile} isTablet={isTablet} onClose={() => setSelected(null)} api={API_BASE} />
    </div>
  );
}
