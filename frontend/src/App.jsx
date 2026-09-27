import OpportunityWatchlist from "./components/OpportunityWatchlist.jsx";
import OpportunityActivity from "./components/OpportunityActivity.jsx";
import SectorStrip from "./components/SectorStrip.jsx";
import { inGroup } from "./utils/sectors.js";
import SetupMap from "./components/SetupMap.jsx";
import ReflexBrand from "./components/ReflexBrand.jsx";
import "./terminal.css";
import { useState, useEffect, useCallback, useMemo, useRef, lazy, Suspense } from "react";
import { useNavigate, useLocation, Routes, Route, Navigate, useParams } from "react-router-dom";
import { T, m, REGIME_META, SIGNAL_META, REGIME_ORDER, MCAP_RANK, formatCacheAge, getBaseSymbol } from "./theme.js";
import { marketHref, timeframeFrom } from "./utils/researchNavigation.js";
import { useTheme } from "./ThemeContext";
import useViewport from "./hooks/useViewport.js";
import { useSharedWorker } from "./hooks/useSharedWorker.js";
import { useWebSocket } from "./hooks/useWebSocket.js";
import FadeIn from "./components/FadeIn.jsx";
import MarketSummary from "./components/MarketSummary.jsx";
import ScannerControls from "./components/ScannerControls.jsx";
import AdminNotice from "./components/AdminNotice.jsx";
import { matchesSignal } from "./utils/marketSummary.js";
import MarketContext from "./components/MarketContext.jsx";
import SignalBar from "./components/SignalBar.jsx";
import PositionAlerts from "./components/PositionAlerts.jsx";
import DataTable from "./components/DataTable.jsx";
import DetailPanel from "./components/DetailPanel.jsx";
import GroupModal from "./components/GroupModal.jsx";
import GlassCard from "./components/GlassCard.jsx";
import NotificationBell from "./components/NotificationBell.jsx";
import SettingsDropdown from "./components/SettingsDropdown.jsx";
import UniverseCoverage from "./components/UniverseCoverage.jsx";
import Tabs from "./components/Tabs.jsx";
import NavDrawer from "./components/NavDrawer.jsx";
import HitRateStrip from "./components/HitRateStrip.jsx";
import ChangesTicker from "./components/ChangesTicker.jsx";
import PageTitle from "./components/PageTitle.jsx";
import PageSkeleton from "./components/PageSkeleton.jsx";
import NotFound from "./components/NotFound.jsx";

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
  "/ai": "chat",
  "/backtest": "backtest",
  "/executor": "executor",
  "/portfolio": "trading",
  "/settings": "settings",
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
  chat: "/ai",
  backtest: "/backtest",
  executor: "/executor",
  trading: "/portfolio",
  settings: "/settings",
};
// Page titles (h1 and browser tab) of the pages without their own title logic.
const TAB_TITLES = {
  traders: "Traders",
  trading: "Portfolio",
  signals: "Signal Log",
  analytics: "Analytics",
  tradfi: "TradFi",
  backtest: "Backtest",
  executor: "Executor",
  chat: "AI Assist",
  settings: "Settings",
  notfound: "Page not found",
};
const DEFAULT_SORT = "priority_score";
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
    return ROUTE_TO_TAB[path] || "notfound";
  }, [path, location.search]);

  // The scanner timeframe last viewed, for AI Assist
  const lastScannerTf = useRef("1d");
  if (activeTab === "4h" || activeTab === "1d") lastScannerTf.current = activeTab;

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

  // Scanner state that lives in the address: ?q, sort, dir, signal, sector, by.
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
  const [sortDir, setSortDir] = useState(() => initialQuery.get("dir"));   // "asc" | "desc"; its default per key arrives with the grid work
  const [statCardFilter, setStatCardFilter] = useState(() => initialQuery.get("signal"));
  const [sectorBy, setSectorBy] = useState(() => initialQuery.get("by") === "ecosystem" ? "ecosystem" : "sector");        // "sector" | "ecosystem"
  const [sectorFilter, setSectorFilter] = useState(() => initialQuery.get("sector"));
  const [lastRefresh, setLastRefresh] = useState(null);

  // Price flash: symbol → "up" | "down" (cleared after 1.2s)
  const [priceFlash, setPriceFlash] = useState(new Map());
  const prevPricesRef = useRef(new Map());

  // TradFi (HIP-3) data
  const [dataTradfi4h, setDataTradfi4h] = useState([]);
  const [dataTradfi1d, setDataTradfi1d] = useState([]);

  // Global metrics & alt season
  const [globalMetrics, setGlobalMetrics] = useState(null);
  const [altSeason, setAltSeason] = useState(null);

  // Sentiment & stablecoin
  const [sentiment, setSentiment] = useState(null);
  const [stablecoin, setStablecoin] = useState(null);

  // CoinGlass macro (ETF flows + Coinbase premium)
  const [macro, setMacro] = useState(null);

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
  // Several writes in one event (Sectors/Ecosystems also clears the sector) build on each other.
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
    setSortDir(params.get("dir"));
    setStatCardFilter(params.get("signal"));
    setSectorFilter(params.get("sector"));
    setSectorBy(params.get("by") === "ecosystem" ? "ecosystem" : "sector");
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

  // Favorites (persisted to localStorage)
  const [favorites, setFavorites] = useState(() => {
    try { return new Set(JSON.parse(localStorage.getItem("reflex_favorites") || "[]")); } catch { return new Set(); }
  });

  // Hydrate favorites from backend on mount (backend is the source of truth for TG)
  useEffect(() => {
    fetch(`${API_BASE}/api/favorites`)
      .then(r => r.json())
      .then(data => {
        if (Array.isArray(data.symbols) && data.symbols.length > 0) {
          setFavorites(prev => {
            const merged = new Set([...prev, ...data.symbols]);
            localStorage.setItem("reflex_favorites", JSON.stringify([...merged]));
            return merged;
          });
        }
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleFavorite = useCallback((symbol) => {
    setFavorites(prev => {
      const next = new Set(prev);
      const wasFav = next.has(symbol);
      wasFav ? next.delete(symbol) : next.add(symbol);
      localStorage.setItem("reflex_favorites", JSON.stringify([...next]));
      // Sync to backend — TG bot reads from here
      const enc = encodeURIComponent(symbol);
      fetch(`${API_BASE}/api/favorites/${enc}`, { method: wasFav ? "DELETE" : "POST" }).catch(() => {});
      return next;
    });
  }, []);

  // Backtest badge tracking
  const [backtestSymbols, setBacktestSymbols] = useState(new Set());

  // ── SharedWorker integration ───────────────────────────────────────────────

  const sw = useSharedWorker();

  // Apply worker main-data updates when supported
  useEffect(() => {
    if (!sw.supported || !sw.mainData) return;
    const d = sw.mainData;
    setData4h(d.r4h?.results || []);
    setData1d(d.r1d?.results || []);
    setConsensus4h(d.r4h?.consensus || null);
    setConsensus1d(d.r1d?.consensus || null);
    setScanRunning(d.r4h?.scan_running || false);
    setCacheAge(d.r4h?.cache_age_seconds ?? null);
    setLastRefresh(new Date(d.timestamp));
    if (d.globalMetrics) setGlobalMetrics(d.globalMetrics);
    if (d.altSeason) setAltSeason(d.altSeason);
    if (d.sentiment) setSentiment(d.sentiment);
    if (d.stablecoin) setStablecoin(d.stablecoin);
    if (d.tradfi4h) setDataTradfi4h(d.tradfi4h.results || []);
    if (d.tradfi1d) setDataTradfi1d(d.tradfi1d.results || []);
    if (d.macro?.etf_flow_usd_7d != null) setMacro(d.macro);
    setLoading(false);
    setError(null);
  }, [sw.supported, sw.mainData]);

  // Forward filter changes to worker
  useEffect(() => {
    if (sw.supported) sw.setFilters(filterRegime, filterSignal);
  }, [sw.supported, sw.setFilters, filterRegime, filterSignal]);

  // ── WebSocket integration (real-time push from backend) ───────────────────

  const wsRef = useWebSocket();

  // Apply WebSocket synthesis-complete updates (overrides SharedWorker/polling data)
  useEffect(() => {
    if (!wsRef.connected || !wsRef.synthesisData) return;
    const d = wsRef.synthesisData;
    setData4h(d.results_4h || []);
    setData1d(d.results_1d || []);
    setConsensus4h(d.consensus_4h || null);
    setConsensus1d(d.consensus_1d || null);
    setCacheAge(d.meta?.cache_age ?? null);
    setLastRefresh(new Date((d.meta?.timestamp || Date.now() / 1000) * 1000));
    setScanRunning(false);
    setLoading(false);
    setError(null);
  }, [wsRef.connected, wsRef.synthesisData]);

  // Delta merge: patch individual symbol updates from drip scan into state
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

  // Sub-second price ticks — patch price + compute flash direction
  useEffect(() => {
    if (!wsRef.priceTicks) return;
    const ticks = wsRef.priceTicks; // {symbol: price, ...}
    const prev = prevPricesRef.current;
    const flashes = new Map();

    for (const [sym, price] of Object.entries(ticks)) {
      const old = prev.get(sym);
      if (old !== undefined && price !== old) {
        flashes.set(sym, price > old ? "up" : "down");
      }
      prev.set(sym, price);
    }

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

    if (flashes.size > 0) {
      setPriceFlash(flashes);
      // Clear flashes after animation completes
      setTimeout(() => setPriceFlash(new Map()), 1200);
    }
  }, [wsRef.priceTicks]);

  // ── Data fetching (fallback when SharedWorker unavailable) ────────────────

  const fetchData = useCallback(async (tf) => {
    const params = new URLSearchParams({ timeframe: tf });
    if (filterRegime !== "ALL") params.append("regime", filterRegime);
    if (filterSignal !== "ALL") params.append("signal", filterSignal);
    const res = await fetch(`${API_BASE}/api/scan?${params}`);
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  }, [filterRegime, filterSignal]);

  const loadAll = useCallback(async () => {
    if (sw.supported) return; // Worker handles polling
    setLoading(true);
    setError(null);
    try {
      const [r4h, r1d] = await Promise.all([fetchData("4h"), fetchData("1d")]);
      setData4h(r4h.results || []);
      setData1d(r1d.results || []);
      setConsensus4h(r4h.consensus || null);
      setConsensus1d(r1d.consensus || null);
      setScanRunning(r4h.scan_running);
      setCacheAge(r4h.cache_age_seconds);
      setLastRefresh(new Date());

      try {
        const [gm, as, sent, stable, tf4h, tf1d, macroData] = await Promise.all([
          fetch(`${API_BASE}/api/global-metrics`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/alt-season?timeframe=1d`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/sentiment`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/stablecoin`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/tradfi?timeframe=4h`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/tradfi?timeframe=1d`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/coinglass/macro`).then(r => r.json()).catch(() => null),
        ]);
        if (gm) setGlobalMetrics(gm);
        if (as) setAltSeason(as);
        if (sent) setSentiment(sent);
        if (stable) setStablecoin(stable);
        if (tf4h) setDataTradfi4h(tf4h.results || []);
        if (tf1d) setDataTradfi1d(tf1d.results || []);
        if (macroData?.etf_flow_usd_7d != null) setMacro(macroData);
      } catch (_) {}
    } catch (e) {
      console.warn("Scanner feed error:", e.message, API_BASE);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [fetchData, sw.supported]);

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

  const triggerScan = async () => {
    if (scanRunning) return;
    setScanRunning(true);
    try {
      const res = await fetch(`${API_BASE}/api/scan/refresh`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (e) {
      console.warn("Scan refresh failed:", e);
      setScanRunning(false);
      return;
    }
    if (wsRef.connected) {
      setTimeout(() => wsRef.refresh(), 3000);
    } else if (sw.supported) {
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

  const computeGroupPerf = useCallback((groupSymbols, scanData) => {
    if (!groupSymbols || groupSymbols.length === 0) return null;
    const symSet = new Set(groupSymbols);
    const btcMom = scanData.find(r => r.symbol === "BTC/USDT")?.momentum ?? 0;
    const members = scanData.filter(r => symSet.has(r.symbol));
    if (members.length === 0) return null;
    const beating = members.filter(r => (r.momentum ?? 0) > btcMom).length;
    return { beating, total: members.length };
  }, []);

  const sortResults = (results) => {
    return [...results].sort((a, b) => {
      // Favorites always first
      const fa = favorites.has(a.symbol) ? 0 : 1;
      const fb = favorites.has(b.symbol) ? 0 : 1;
      if (fa !== fb) return fa - fb;

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
      if (sortKey === "conditions") return (b.conditions_met || 0) - (a.conditions_met || 0);
      if (sortKey === "priority_score") return (b.priority_score || 0) - (a.priority_score || 0);
      return 0;
    });
  };

  const sorted4h = sortResults(filtered4h);
  const sorted1d = sortResults(filtered1d);

  // TradFi sorted data
  const sortedTradfi = useMemo(() => {
    let d = activeTab === "tradfi" ? dataTradfi1d : dataTradfi4h;
    if (searchTerm) { const q = searchTerm.toUpperCase(); d = d.filter(r => r.symbol?.toUpperCase().includes(q)); }
    return sortResults(d);
  }, [activeTab, dataTradfi1d, dataTradfi4h, searchTerm, sortKey]);

  // Apply stat card signal filter to table data
  const inSector = (data) => sectorFilter ? data.filter(r => inGroup(r, sectorFilter.includes("|") ? "pocket" : sectorBy, sectorFilter)) : data;
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
  const visibleColumns = COLUMNS.filter(([, , minW]) => width >= (minW || 0));
  const showDashboard = activeTab === "4h" || activeTab === "1d";
  const scannerTitle = activeGroup ? activeGroup.name : marketKind === "spot" ? "Spot markets" : "Perpetuals";
  const radarTf = activeTab === "radar" ? timeframeFrom(location.search) : null;

  // Browser tab title. The coin page refines its own ("BTC · Reflex") once its data is in.
  useEffect(() => {
    document.title = coinPageSymbol ? `${getBaseSymbol(coinPageSymbol)} · Reflex`
      : showDashboard ? `${scannerTitle} ${activeTab.toUpperCase()} · Reflex`
      : activeTab === "radar" ? `Radar ${radarTf.toUpperCase()} · Reflex`
      : `${TAB_TITLES[activeTab] || "Reflex"} · Reflex`;
  }, [coinPageSymbol, showDashboard, scannerTitle, activeTab, radarTf]);

  // ── Render ────────────────────────────────────────────────────────────────

  const onSort = key => { setSortKey(key); updateScannerQuery("sort", key === DEFAULT_SORT ? null : key); };

  // The old HyperLens address opens Traders, keeping its query.
  if (path === "/hyperlens") return <Navigate to={"/traders" + location.search} replace />;

  const pageMargin = { marginTop: isMobile ? 16 : 20 };

  return (
    <div className="reflex-terminal" style={{ minHeight: "100vh", background: T.bg, color: T.text1, position: "relative" }}>
      {/* Fonts & Global Styles */}
      <style>{`
        :where(.reflex-terminal), :where(.reflex-terminal *) { box-sizing: border-box; margin: 0; padding: 0; font-family: var(--font-geist-sans), sans-serif; }
        body { background: var(--t-bg); -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; font-family: var(--font-geist-sans), sans-serif; font-size: 14px; font-feature-settings: "tnum"; }
        table, th, td, span, div, button, select, input, textarea, p, label { font-family: inherit; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--t-scrollThumb); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--t-scrollHover); }
        tr:hover td { background: transparent !important; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes glow { 0%,100%{box-shadow: 0 0 12px rgba(151,252,228,0.12);} 50%{box-shadow: 0 0 24px rgba(151,252,228,0.25);} }
        @keyframes livePulse { 0%,100%{opacity:1; text-shadow: 0 0 6px rgba(34,197,94,0.6);} 50%{opacity:0.3; text-shadow: none;} }
        @keyframes orbBreathe { 0%,100%{opacity:0.6;transform:scale(1)} 50%{opacity:0.9;transform:scale(1.08)} }
        @keyframes fadeInUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes shimmer { 0% { background-position: -200% 0; } 100% { background-position: 200% 0; } }
        @keyframes anomalyDotPulse { 0%,100%{opacity:1; box-shadow: 0 0 4px rgba(239,68,68,0.6);} 50%{opacity:0.4; box-shadow: none;} }
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

      {/* ── NAV DRAWER ── */}
      <NavDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        activeTab={activeTab === "traders" ? "hyperlens" : activeTab}
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

      {/* ── HEADER ── */}
      <div className="terminal-header" style={{
        padding: `0 ${hPad}px`,
        borderBottom: `1px solid ${mode === "dark" ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)"}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: mode === "dark"
          ? "linear-gradient(90deg, rgba(10,10,14,0.82) 0%, rgba(12,12,18,0.78) 50%, rgba(10,10,14,0.82) 100%)"
          : "linear-gradient(90deg, rgba(255,255,255,0.88) 0%, rgba(248,248,252,0.84) 50%, rgba(255,255,255,0.88) 100%)",
        backdropFilter: "blur(40px) saturate(1.8)", WebkitBackdropFilter: "blur(40px) saturate(1.8)",
        position: "sticky", top: 0, zIndex: 100,
        height: isMobile ? 56 : 56,
        overflow: "visible",
        boxShadow: mode === "dark"
          ? "0 1px 0 rgba(255,255,255,0.04), 0 4px 30px rgba(0,0,0,0.4)"
          : "0 1px 0 rgba(255,255,255,0.6), 0 4px 20px rgba(0,0,0,0.06)",
      }}>
        {/* Aura: cyan band across bottom edge */}
        <div style={{
          position: "absolute", bottom: 0, left: 0, right: 0,
          height: "60%",
          background: mode === "dark"
            ? "linear-gradient(0deg, rgba(151,252,228,0.10) 0%, rgba(151,252,228,0.03) 60%, transparent 100%)"
            : "linear-gradient(0deg, rgba(14,116,144,0.08) 0%, rgba(14,116,144,0.02) 60%, transparent 100%)",
          pointerEvents: "none",
        }} />
        {/* Aura: aquamarine accent band across full header */}
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0,
          height: "100%",
          background: mode === "dark"
            ? "linear-gradient(180deg, rgba(15,57,51,0.55) 0%, rgba(15,57,51,0.18) 60%, transparent 100%)"
            : "linear-gradient(180deg, rgba(14,116,144,0.07) 0%, rgba(14,116,144,0.02) 60%, transparent 100%)",
          pointerEvents: "none",
        }} />
        {/* Left: hamburger + logo + scanning */}
        <div style={{ display: "flex", alignItems: "center", gap: isMobile ? 8 : 12 }}>
          <button
            onClick={() => setDrawerOpen(true)}
            aria-label="Open navigation"
            style={{
              width: 24, height: 24,
              display: "flex",
              flexDirection: "column", alignItems: "center", justifyContent: "center",
              gap: 4, padding: 0, flexShrink: 0,
              border: "none",
              background: "transparent",
              cursor: "pointer",
            }}
          >
            <span style={{ width: 18, height: 1.5, background: T.text2, borderRadius: 1, transition: "background 0.15s" }} />
            <span style={{ width: 18, height: 1.5, background: T.text2, borderRadius: 1, transition: "background 0.15s" }} />
            <span style={{ width: 18, height: 1.5, background: T.text2, borderRadius: 1, transition: "background 0.15s" }} />
          </button>
          <ReflexBrand compact={isMobile} onClick={() => {
            navigate("/scanner");
            setFilterRegime("ALL"); setFilterSignal("ALL"); setStatCardFilter(null);
            setSectorFilter(null); setSearchTerm(""); setSortKey(DEFAULT_SORT); setSortDir(null);
          }} />

        </div>

        {/* Right: timestamp, refresh, cache, theme toggle */}
        <div style={{
          display: "flex", alignItems: "center", gap: isMobile ? 6 : 10,
          flexShrink: 0,
        }}>
          {!isMobile && lastRefresh && (
            <span style={{ fontSize: 12, color: T.text4, letterSpacing: "0.04em", fontFamily: T.font }}>
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={triggerScan}
            disabled={scanRunning}
            title={scanRunning ? "Scan running" : "Refresh scan"}
            aria-label={scanRunning ? "Scan running" : "Refresh scan"}
            style={{
              width: 28, height: 28, borderRadius: 8,
              display: "flex", alignItems: "center", justifyContent: "center",
              padding: 0, flexShrink: 0,
              border: "none",
              background: "transparent",
              color: T.text3,
              cursor: scanRunning ? "default" : "pointer",
              opacity: scanRunning ? 0.5 : 1,
              transition: "all 0.15s ease",
            }}
            onMouseEnter={e => { if (!scanRunning) e.currentTarget.style.color = T.accent; }}
            onMouseLeave={e => { e.currentTarget.style.color = T.text3; }}
          >
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none"
              style={scanRunning ? { animation: "spin 1s linear infinite" } : undefined}>
              <path d="M13.65 2.35A7.96 7.96 0 0 0 8 0a8 8 0 1 0 8 8h-2a6 6 0 1 1-1.76-4.24L10 6h6V0l-2.35 2.35z" fill="currentColor" />
            </svg>
          </button>
          <NotificationBell />
          <SettingsDropdown />
          <button
            onClick={toggle}
            title={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            style={{
              border: "none", background: "transparent", padding: 0,
              cursor: "pointer", flexShrink: 0,
              fontSize: 12, fontFamily: T.font, color: T.text3,
              transition: "color 0.15s ease",
            }}
            onMouseEnter={e => { e.currentTarget.style.color = T.text1; }}
            onMouseLeave={e => { e.currentTarget.style.color = T.text3; }}
          >
            {mode === "dark" ? "Light" : "Dark"}
          </button>
        </div>
      </div>

      {/* Header aura line — 1px gradient separator */}
      <div style={{
        height: 1, width: "100%",
        background: mode === "dark"
          ? "linear-gradient(90deg, transparent 0%, rgba(151,252,228,0.15) 25%, rgba(151,252,228,0.25) 50%, rgba(151,252,228,0.15) 75%, transparent 100%)"
          : "linear-gradient(90deg, transparent 0%, rgba(14,116,144,0.12) 25%, rgba(14,116,144,0.18) 50%, rgba(14,116,144,0.12) 75%, transparent 100%)",
        position: "sticky", top: isMobile ? 56 : 56, zIndex: 99,
      }} />

      {/* Controls bar removed — timeframe toggle moved into ConsensusBar,
          regime/signal dropdowns removed (stat cards + column sort cover the need) */}

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

      <main id="content">
      {/* ── COIN PAGE (dedicated /scanner/:symbol route) ── */}
      {coinPageSymbol && (
        <Suspense fallback={<div style={{ padding: isMobile ? 16 : 24 }}><PageSkeleton /></div>}>
          <CoinPage scanData4h={data4h} scanData1d={data1d} urlSymbol={coinPageSymbol} />
        </Suspense>
      )}

      {/* ── SECTION TITLE (hidden for chat and coin page — full-immersion mode; Radar and 404 draw their own) ── */}
      {!coinPageSymbol && activeTab !== "chat" && activeTab !== "radar" && activeTab !== "notfound" && (
        <div className="scanner-head" style={{
          padding: `${isMobile ? T.sp4 : T.sp3}px ${hPad}px ${T.sp1}px`,
          display: "flex", alignItems: "center", justifyContent: "flex-start", flexWrap: "wrap", gap: "12px 20px",
        }}>
          <PageTitle>{showDashboard ? scannerTitle : TAB_TITLES[activeTab]}</PageTitle>
          {showDashboard && <ScannerControls activeTab={activeTab} onTabChange={setActiveTab} searchTerm={searchTerm}
            onSearchChange={v => { setSearchTerm(v); updateScannerQuery("q", v); }} />}
          {activeTab === "tradfi" && <Tabs label="Timeframe" items={[{ key: "4h", label: "4H" }, { key: "1d", label: "1D" }]} value={tradfiTf} onChange={setTradfiTf} />}

        </div>
      )}

      {/* ── MAIN CONTENT (hidden when on coin page) ── */}
      {!coinPageSymbol && <div style={{ paddingTop: 0, paddingLeft: hPad, paddingRight: hPad, paddingBottom: isMobile ? 80 : 60, position: "relative" }}>

        {showDashboard && tfMarketRows.length > 0 && (
          <MarketSummary regimeRows={consensusRows} signalRows={tfScopeRows} consensus={activeConsensus} sentiment={sentiment}
            timeframe={activeTab === "4h" ? "4h" : "1d"} scopeLabel={scopeLabel} spot={marketKind === "spot"}
            activeSignalFilter={statCardFilter} onSignalFilter={v => { setStatCardFilter(v); updateScannerQuery("signal", v); }} />
        )}

        {showDashboard && <UniverseCoverage marketKind={marketKind} timeframe={activeTab === "4h" ? "4h" : "1d"}/> }
        {showDashboard && <SectorStrip rows={tfScopeRows} baseRows={tfMarketRows} by={sectorBy}
          onByChange={v => { setSectorBy(v); updateScannerQuery("by", v === "ecosystem" ? v : null); }}
          value={sectorFilter} onChange={v => { setSectorFilter(v); updateScannerQuery("sector", v); }} timeframe={activeTab === "4h" ? "4h" : "1d"} spot={marketKind === "spot"} />}
        {showDashboard && <SetupMap results={inSector(activeTab === "4h" ? filtered4h : filtered1d)} timeframe={activeTab === "4h" ? "4h" : "1d"} onSelect={handleSelectCoin}/>}

        {showDashboard && <details className="scanner-context"><summary>Market context & recent activity <span>Dominance, alt season, cross-timeframe signals and changes</span></summary>
          <MarketContext globalMetrics={globalMetrics} altSeason={altSeason} stablecoin={stablecoin} macro={macro} isMobile={isMobile}/>
          <OpportunityActivity />
          <OpportunityWatchlist rows={[...sorted4h, ...sorted1d]} onSelect={handleSelectCoin} />
          <SignalBar data4h={sorted4h} data1d={sorted1d} onSelect={handleSelectCoin} isMobile={isMobile}/>
          <ChangesTicker timeframe={activeTab === "1d" ? "1d" : "4h"} isMobile={isMobile} refreshKey={lastRefresh}/>
        </details>}

        {showDashboard && <PositionAlerts isMobile={isMobile} />}

        {showDashboard && marketKind === "spot" && (
          <p style={{ margin: `${isMobile ? 12 : 16}px 0 0`, fontSize: 12, lineHeight: 1.5, color: T.text3, fontFamily: T.font }}>
            Spot markets have no funding rate, so Strong long is not issued on spot.
          </p>
        )}

        {showDashboard && (
          <div style={{
            display: "flex", flexDirection: isDesktop ? "row" : "column",
            gap: isDesktop ? 16 : 12, marginTop: isMobile ? 12 : 16,
          }}>
            {(activeTab === "4h") && (
              <FadeIn delay={500} style={{ flex: 1, minWidth: 0 }}>
                <DataTable results={display4h} label={null}
                  sortKey={sortKey} onSort={onSort} selected={selected} onSelect={handleSelectCoin}
                  visibleColumns={visibleColumns} isMobile={isMobile} backtestSymbols={backtestSymbols} loading={loading}
                  favorites={favorites} onToggleFavorite={toggleFavorite} priceFlash={priceFlash} />
              </FadeIn>
            )}
            {(activeTab === "1d") && (
              <FadeIn delay={500} style={{ flex: 1, minWidth: 0 }}>
                <DataTable results={display1d} label={null}
                  sortKey={sortKey} onSort={onSort} selected={selected} onSelect={handleSelectCoin}
                  visibleColumns={visibleColumns} isMobile={isMobile} backtestSymbols={backtestSymbols} loading={loading}
                  favorites={favorites} onToggleFavorite={toggleFavorite} priceFlash={priceFlash} />
              </FadeIn>
            )}
          </div>
        )}

        {activeTab === "radar" && (
          <Suspense fallback={<PageSkeleton style={pageMargin} />}>
            <RadarPage results4h={data4h} results1d={data1d} onSelect={handleSelectCoin} />
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

        {activeTab === "notfound" && <NotFound />}
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
