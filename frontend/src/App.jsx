import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate, useLocation, Routes, Route, Navigate, useParams } from "react-router-dom";
import { T, m, REGIME_META, SIGNAL_META, REGIME_ORDER, MCAP_RANK, formatCacheAge } from "./theme.js";
import { useTheme } from "./ThemeContext";
import useViewport from "./hooks/useViewport.js";
import { useSharedWorker } from "./hooks/useSharedWorker.js";
import { useWebSocket } from "./hooks/useWebSocket.js";
import FadeIn from "./components/FadeIn.jsx";
import SummaryBar from "./components/SummaryBar.jsx";
import StatCards from "./components/StatCards.jsx";
import ConsensusBar from "./components/ConsensusBar.jsx";
import MarketContext from "./components/MarketContext.jsx";
import SignalBar from "./components/SignalBar.jsx";
import PositionAlerts from "./components/PositionAlerts.jsx";
import DataTable from "./components/DataTable.jsx";
import DetailPanel from "./components/DetailPanel.jsx";
import GroupModal from "./components/GroupModal.jsx";
import GlassCard from "./components/GlassCard.jsx";
import NotificationBell from "./components/NotificationBell.jsx";
import BacktestPanel from "./components/BacktestPanel.jsx";
import ExecutorPanel from "./components/ExecutorPanel.jsx";
import TradingPanel from "./components/TradingPanel.jsx";
import OnChainPanel from "./components/OnChainPanel.jsx";
import SignalLogPanel from "./components/SignalLogPanel.jsx";
import AnalyticsPanel from "./components/AnalyticsPanel.jsx";
import ChatPanel from "./components/ChatPanel.jsx";
import TradFiPanel from "./components/TradFiPanel.jsx";
import NavDrawer from "./components/NavDrawer.jsx";
import HyperLensPanel from "./components/HyperLensPanel.jsx";
import HitRateStrip from "./components/HitRateStrip.jsx";
import ChangesTicker from "./components/ChangesTicker.jsx";
import CoinPage from "./pages/CoinPage.jsx";

// ─── CONFIG ───────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── COLUMN DEFINITIONS ─────────────────────────────────────────────────────
// [sortKey, label, minViewportWidth]

// [sortKey, label, minViewportWidth]
// HEAT absorbs PHASE as a sub-label (EXT/ENTR/EXHS/FADE).
// EXHAUST absorbs FORMING — shows "FLOOR ✓" when floor is confirmed.
const COLUMNS = [
  [null,             "#",       0],
  ["priority_score", "PRI",     0],     // composite ranking 0-100 — always visible
  ["symbol",         "SYMBOL",  0],     // includes price sub-label on desktop
  ["regime",         "REGIME",  0],
  [null,             "SIGNAL",  0],
  ["zscore",         "Z-SCORE", 480],
  [null,             "SPARK",   640],   // moved after Z-SCORE, hidden on small mobile
  [null,             "COND",    640],   // conditions met — entry quality
  ["heat",           "HEAT",    640],   // bar + phase sub-label
  [null,             "CVD",     768],   // net taker pressure
  [null,             "CONF",    768],   // multi-TF confluence
  [null,             "DIV",     900],
  [null,             "EXHAUST", 1024],  // state + ✓ when floor confirmed
  ["energy",         "ENERGY",  1024],
  [null,             "SM",      1200],  // HyperLens smart money consensus
  [null,             "OI",      1440],  // OI trend — wide monitors only
];

// ─── MAIN APP ─────────────────────────────────────────────────────────────────

// ─── ROUTE MAPS ──────────────────────────────────────────────────────────────
const ROUTE_TO_TAB = {
  "/scanner": "1d",
  "/signals": "signals",
  "/analytics": "analytics",
  "/hyperlens": "hyperlens",
  "/tradfi": "tradfi",
  "/ai": "chat",
  "/backtest": "backtest",
  "/executor": "executor",
  "/portfolio": "trading",
  "/onchain": "onchain",
};
const TAB_TO_ROUTE = {
  "1d": "/scanner",
  "4h": "/scanner?tf=4h",
  split: "/scanner?tf=split",
  signals: "/signals",
  analytics: "/analytics",
  hyperlens: "/hyperlens",
  tradfi: "/tradfi",
  chat: "/ai",
  backtest: "/backtest",
  executor: "/executor",
  trading: "/portfolio",
  onchain: "/onchain",
};

export default function App() {
  const { width, isMobile, isTablet, isDesktop } = useViewport();
  const { mode, toggle } = useTheme();
  const hPad = isMobile ? 16 : isTablet ? 20 : 24;
  const navigate = useNavigate();
  const location = useLocation();

  // Derive activeTab from URL
  const activeTab = useMemo(() => {
    const p = location.pathname.replace(/\/$/, "") || "/scanner";
    // Scanner route — check tf query param first
    if (p === "/scanner") {
      const sp = new URLSearchParams(location.search);
      const tf = sp.get("tf");
      if (tf === "4h") return "4h";
      if (tf === "split" && !isMobile) return "split";
      return "1d";
    }
    // Check known routes (non-scanner)
    for (const [route, tab] of Object.entries(ROUTE_TO_TAB)) {
      if (p === route || p.startsWith(route + "/")) return tab;
    }
    return "1d";
  }, [location.pathname, location.search, isMobile]);

  // Detect /scanner/:symbol route for dedicated coin page
  const coinPageSymbol = useMemo(() => {
    const m = location.pathname.match(/^\/scanner\/([^/]+)$/);
    return m ? m[1] : null;
  }, [location.pathname]);

  // Navigate to coin page on row click (shift+click → DetailPanel slide-out)
  const handleSelectCoin = useCallback((row, event) => {
    if (event?.shiftKey) {
      setSelected(row);
    } else {
      const base = (row.symbol || "").replace("/USDT", "").replace("/USD", "");
      navigate(`/scanner/${base}`);
    }
  }, [navigate]);

  const setActiveTab = useCallback((tab) => {
    navigate(TAB_TO_ROUTE[tab] || "/scanner");
  }, [navigate]);

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
  const [sortKey, setSortKey] = useState("priority_score");
  const [statCardFilter, setStatCardFilter] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);

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
  const [searchTerm, setSearchTerm] = useState("");

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

  // Force off split view on mobile
  useEffect(() => {
    if (isMobile && activeTab === "split") setActiveTab("4h");
  }, [isMobile, activeTab, setActiveTab]);

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

  // Sub-second price ticks — patch price field without re-creating arrays
  useEffect(() => {
    if (!wsRef.priceTicks) return;
    const ticks = wsRef.priceTicks; // {symbol: price, ...}

    const patchPrices = (prev) => {
      let changed = false;
      const next = prev.map((r) => {
        const newPrice = ticks[r.symbol];
        if (newPrice !== undefined && newPrice !== r.price) {
          changed = true;
          return { ...r, price: newPrice };
        }
        return r;
      });
      return changed ? next : prev;
    };

    setData4h(patchPrices);
    setData1d(patchPrices);
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
    await fetch(`${API_BASE}/api/scan/refresh`, { method: "POST" });
    setScanRunning(true);
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
      setActiveGroupId(prev => (!prev && data.length > 0) ? data[0].id : prev);
    } catch (_) {}
  }, []);

  useEffect(() => { loadGroups(); }, [loadGroups]);

  const createGroup = async (name, symbols = [], color = "#22d3ee") => {
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
    let d = data4h;
    if (activeGroupSymbols) d = d.filter(r => activeGroupSymbols.has(r.symbol));
    if (searchTerm) { const q = searchTerm.toUpperCase(); d = d.filter(r => r.symbol?.toUpperCase().includes(q)); }
    return d;
  }, [data4h, activeGroupSymbols, searchTerm]);

  const filtered1d = useMemo(() => {
    let d = data1d;
    if (activeGroupSymbols) d = d.filter(r => activeGroupSymbols.has(r.symbol));
    if (searchTerm) { const q = searchTerm.toUpperCase(); d = d.filter(r => r.symbol?.toUpperCase().includes(q)); }
    return d;
  }, [data1d, activeGroupSymbols, searchTerm]);

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
  const applyStatFilter = (data) => {
    if (!statCardFilter) return data;
    const getSig = r => r.unified_signal || r.signal;
    if (statCardFilter === "TRIM") return data.filter(r => { const s = getSig(r); return s === "TRIM" || s === "TRIM_HARD"; });
    return data.filter(r => getSig(r) === statCardFilter);
  };
  const display4h = applyStatFilter(sorted4h);
  const display1d = applyStatFilter(sorted1d);
  const displayTradfi = applyStatFilter(sortedTradfi);

  const activeConsensus = activeTab === "1d" ? consensus1d : consensus4h;
  const visibleColumns = COLUMNS.filter(([, , minW]) => width >= (minW || 0));
  const showDashboard = activeTab !== "backtest" && activeTab !== "executor" && activeTab !== "trading" && activeTab !== "onchain" && activeTab !== "signals" && activeTab !== "analytics" && activeTab !== "chat" && activeTab !== "tradfi" && activeTab !== "hyperlens";

  const tabOptions = isMobile
    ? [["4h", "4H"], ["1d", "1D"], ["tradfi", "TRADFI"], ["chat", "AI"], ["backtest", "BACKTEST"], ["executor", "EXECUTOR"], ["trading", "PORTFOLIO"], ["signals", "SIGNALS"], ["onchain", "ON-CHAIN"]]
    : [["4h", "4H"], ["1d", "1D"], ["split", "SPLIT"], ["tradfi", "TRADFI"], ["chat", "AI ASSIST"], ["backtest", "BACKTEST"], ["executor", "EXECUTOR"], ["trading", "PORTFOLIO"], ["signals", "SIGNALS"], ["onchain", "ON-CHAIN"]];

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ minHeight: "100vh", background: T.bg, color: T.text1, position: "relative" }}>
      {/* Fonts & Global Styles */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@400;500;600;700;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
        body { background: var(--t-bg); -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; font-feature-settings: "tnum"; }
        table, th, td, span, div, button, select, input, textarea, p, label { font-family: inherit; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--t-scrollThumb); border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--t-scrollHover); }
        tr:hover td { background: transparent !important; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes glow { 0%,100%{box-shadow: 0 0 12px rgba(34,211,238,0.12);} 50%{box-shadow: 0 0 24px rgba(34,211,238,0.25);} }
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
          background: linear-gradient(180deg, #2ee0f8 0%, #1ab8d4 100%);
          border: 1px solid rgba(34,211,238,0.5);
          color: #000;
          box-shadow: 0 1px 3px var(--t-shadow), inset 0 1px 0 var(--t-overlay20);
        }
        .apple-btn-accent:hover {
          background: linear-gradient(180deg, #40e8ff 0%, #22d3ee 100%);
          border-color: rgba(34,211,238,0.7);
          box-shadow: 0 2px 12px rgba(34,211,238,0.25), inset 0 1px 0 var(--t-overlay25);
          color: #000;
        }
        .apple-btn-accent:active {
          background: linear-gradient(180deg, #18b8d0 0%, #1aa8c0 100%);
          box-shadow: 0 0px 1px var(--t-shadow), inset 0 1px 3px var(--t-shadow);
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
          border-color: rgba(34,211,238,0.4);
          box-shadow: 0 0 0 3px rgba(34,211,238,0.08), 0 1px 2px var(--t-shadow);
        }
      `}</style>

      {/* ── AMBIENT BACKGROUND ORBS ── */}
      <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0, overflow: "hidden" }}>
        <div style={{
          position: "absolute", top: "-10%", left: "15%", width: 600, height: 600,
          borderRadius: "50%", background: "radial-gradient(circle, rgba(34,211,238,0.06) 0%, transparent 70%)",
          filter: "blur(80px)", animation: "orbBreathe 10s ease-in-out infinite",
        }} />
        <div style={{
          position: "absolute", top: "40%", right: "10%", width: 500, height: 500,
          borderRadius: "50%", background: "radial-gradient(circle, rgba(168,85,247,0.04) 0%, transparent 70%)",
          filter: "blur(80px)", animation: "orbBreathe 10s ease-in-out infinite 3s",
        }} />
        <div style={{
          position: "absolute", bottom: "10%", left: "30%", width: 450, height: 450,
          borderRadius: "50%", background: "radial-gradient(circle, rgba(52,211,153,0.04) 0%, transparent 70%)",
          filter: "blur(80px)", animation: "orbBreathe 10s ease-in-out infinite 6s",
        }} />
        <div style={{
          position: "absolute", top: "20%", left: "60%", width: 400, height: 400,
          borderRadius: "50%", background: "radial-gradient(circle, rgba(251,191,36,0.03) 0%, transparent 70%)",
          filter: "blur(80px)", animation: "orbBreathe 10s ease-in-out infinite 8s",
        }} />
      </div>

      {/* ── NAV DRAWER ── */}
      <NavDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        isMobile={isMobile}
        groups={groups}
        activeGroupId={activeGroupId}
        onGroupChange={setActiveGroupId}
        onGroupCreate={() => { setEditingGroup(null); setShowGroupModal(true); }}
        onGroupEdit={(g) => { setEditingGroup(g); setShowGroupModal(true); }}
        onWatchlistSelect={(gId) => { setActiveGroupId(gId); if (activeTab !== "4h" && activeTab !== "1d" && activeTab !== "split") setActiveTab("1d"); }}
        scanData={activeTab === "1d" || activeTab === "split" ? data1d : data4h}
      />

      {/* ── HEADER ── */}
      <div style={{
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
            ? "linear-gradient(0deg, rgba(34,211,238,0.10) 0%, rgba(34,211,238,0.03) 60%, transparent 100%)"
            : "linear-gradient(0deg, rgba(14,116,144,0.08) 0%, rgba(14,116,144,0.02) 60%, transparent 100%)",
          pointerEvents: "none",
        }} />
        {/* Aura: purple accent band across full header */}
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0,
          height: "100%",
          background: mode === "dark"
            ? "linear-gradient(180deg, rgba(168,85,247,0.10) 0%, rgba(168,85,247,0.03) 60%, transparent 100%)"
            : "linear-gradient(180deg, rgba(126,34,206,0.07) 0%, rgba(126,34,206,0.02) 60%, transparent 100%)",
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
          <img
            src="/logo.png"
            alt="Reflex"
            onClick={() => { navigate("/scanner"); setFilterRegime("ALL"); setFilterSignal("ALL"); setStatCardFilter(null); }}
            style={{
              height: isMobile ? 32 : 40,
              width: "auto",
              objectFit: "contain",
              flexShrink: 0,
              display: "block",
              filter: mode === "light" ? "invert(1) hue-rotate(180deg)" : "none",
              cursor: "pointer",
            }}
          />
          <div style={{
            display: "flex", alignItems: "center", gap: 6,
            padding: "4px 12px",
            fontSize: 10, color: T.text3, letterSpacing: "0.08em",
            fontFamily: T.mono, fontWeight: 600,
          }}>
            <span style={{ color: "#22c55e", animation: "livePulse 2s ease-in-out infinite" }}>{"\u25cf"}</span> LIVE
          </div>
        </div>

        {/* Right: timestamp, refresh, cache, theme toggle */}
        <div style={{
          display: "flex", alignItems: "center", gap: isMobile ? 6 : 10,
          flexShrink: 0,
        }}>
          {!isMobile && lastRefresh && (
            <span style={{ fontSize: 11, color: T.text4, letterSpacing: "0.04em", fontFamily: T.font }}>
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={triggerScan}
            title="Refresh scan"
            style={{
              width: 28, height: 28, borderRadius: 8,
              display: "flex", alignItems: "center", justifyContent: "center",
              padding: 0, flexShrink: 0,
              border: "none",
              background: "transparent",
              color: T.text3,
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={e => { e.currentTarget.style.color = T.accent; }}
            onMouseLeave={e => { e.currentTarget.style.color = T.text3; }}
          >
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
              <path d="M13.65 2.35A7.96 7.96 0 0 0 8 0a8 8 0 1 0 8 8h-2a6 6 0 1 1-1.76-4.24L10 6h6V0l-2.35 2.35z" fill="currentColor" />
            </svg>
          </button>
          <NotificationBell />
          <button
            onClick={toggle}
            title={mode === "dark" ? "Switch to light mode" : "Switch to dark mode"}
            style={{
              position: "relative",
              width: 44, height: 24,
              borderRadius: 12,
              border: "none",
              cursor: "pointer",
              padding: 0,
              background: mode === "dark" ? T.accent : T.overlay15,
              transition: "background 0.3s ease",
              flexShrink: 0,
            }}
          >
            <span style={{
              position: "absolute",
              top: 2, left: mode === "dark" ? 22 : 2,
              width: 20, height: 20,
              borderRadius: "50%",
              background: mode === "dark" ? T.bg : "#fff",
              boxShadow: `0 1px 3px ${T.shadow}`,
              transition: "left 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, lineHeight: 1,
            }}>{mode === "dark" ? "\uD83C\uDF19" : "\u2600\uFE0F"}</span>
          </button>
        </div>
      </div>

      {/* Header aura line — 1px gradient separator */}
      <div style={{
        height: 1, width: "100%",
        background: mode === "dark"
          ? "linear-gradient(90deg, transparent 0%, rgba(34,211,238,0.15) 25%, rgba(34,211,238,0.25) 50%, rgba(34,211,238,0.15) 75%, transparent 100%)"
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
            <span style={{ color: "#f87171", fontSize: 14 }}>{"\u26a0"}</span>
            <span style={{ fontSize: 13, color: "#fca5a5", fontFamily: T.font }}>
              API Error: {error} {"\u2014"} ensure backend is running on {API_BASE}
            </span>
          </GlassCard>
        </div>
      )}

      {/* ── COIN PAGE (dedicated /scanner/:symbol route) ── */}
      {coinPageSymbol && (
        <CoinPage scanData4h={data4h} scanData1d={data1d} urlSymbol={coinPageSymbol} />
      )}

      {/* ── SECTION TITLE (hidden for chat and coin page — full-immersion mode) ── */}
      {!coinPageSymbol && activeTab !== "chat" && (
        <div style={{
          padding: `${isMobile ? T.sp4 : T.sp3}px ${hPad}px ${T.sp1}px`,
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <span style={{
            fontSize: m(T.textXl, isMobile),
            fontWeight: 700,
            color: T.text1,
            fontFamily: T.font,
            letterSpacing: "-0.02em",
          }}>
            {activeTab === "backtest" ? "Backtest" :
             activeTab === "executor" ? "Executor" :
             activeTab === "trading" ? "Portfolio" :
             activeTab === "signals" ? "Signal Log" :
             activeTab === "analytics" ? "Analytics" :
             activeTab === "onchain" ? "On-Chain" :
             activeTab === "tradfi" ? "TradFi" :
             activeTab === "hyperlens" ? "HyperLens" :
             activeGroup ? activeGroup.name : "Scanner"}
          </span>
          {showDashboard && (
            <button
              onClick={() => { setEditingGroup(activeGroup || null); setShowGroupModal(true); }}
              style={{
                fontFamily: T.mono, fontSize: m(T.textSm, isMobile), fontWeight: 600,
                padding: isMobile ? "6px 14px" : "4px 12px", borderRadius: 6, cursor: "pointer",
                border: `1px solid ${T.border}`,
                background: "transparent",
                color: T.text4,
                transition: "all 0.15s ease",
              }}
            >
              + Manage
            </button>
          )}
        </div>
      )}

      {/* ── MAIN CONTENT (hidden when on coin page) ── */}
      {!coinPageSymbol && <div style={{ paddingTop: 0, paddingLeft: hPad, paddingRight: hPad, paddingBottom: isMobile ? 80 : 60, position: "relative" }}>

        {showDashboard && (data4h.length > 0 || data1d.length > 0) && (
          <FadeIn>
            <SummaryBar results={activeTab === "1d" ? sorted1d : sorted4h} />
            <StatCards results={activeTab === "1d" ? sorted1d : sorted4h} isMobile={isMobile} isTablet={isTablet} activeSignalFilter={statCardFilter} onSignalFilter={setStatCardFilter} />
          </FadeIn>
        )}

        {showDashboard && <ConsensusBar consensus={activeConsensus} isMobile={isMobile} activeTab={activeTab} onTabChange={setActiveTab} searchTerm={searchTerm} onSearchChange={setSearchTerm} />}

        {/* HitRateStrip removed — replaced by unified signal outcome tracking */}

        {showDashboard && (
          <MarketContext globalMetrics={globalMetrics} altSeason={altSeason} sentiment={sentiment} stablecoin={stablecoin} macro={macro} isMobile={isMobile} />
        )}

        {showDashboard && <SignalBar data4h={sorted4h} data1d={sorted1d} onSelect={handleSelectCoin} isMobile={isMobile} />}

        {showDashboard && <ChangesTicker timeframe={activeTab === "1d" ? "1d" : "4h"} isMobile={isMobile} refreshKey={lastRefresh} />}

        {showDashboard && <PositionAlerts isMobile={isMobile} />}

        {showDashboard && (
          <div style={{
            display: "flex", flexDirection: isDesktop ? "row" : "column",
            gap: isDesktop ? 16 : 12, marginTop: isMobile ? 12 : 16,
          }}>
            {(activeTab === "4h" || activeTab === "split") && (
              <FadeIn delay={500} style={{ flex: 1, minWidth: 0 }}>
                <DataTable results={display4h} label={activeTab === "split" ? "4H TIMEFRAME" : null}
                  sortKey={sortKey} onSort={setSortKey} selected={selected} onSelect={handleSelectCoin}
                  visibleColumns={visibleColumns} isMobile={isMobile} backtestSymbols={backtestSymbols} loading={loading}
                  favorites={favorites} onToggleFavorite={toggleFavorite} />
              </FadeIn>
            )}
            {activeTab === "split" && (
              <div style={{ width: isDesktop ? 1 : "100%", height: isDesktop ? undefined : 1, background: T.border, flexShrink: 0 }} />
            )}
            {(activeTab === "1d" || activeTab === "split") && (
              <FadeIn delay={activeTab === "split" ? 600 : 500} style={{ flex: 1, minWidth: 0 }}>
                <DataTable results={display1d} label={activeTab === "split" ? "DAILY TIMEFRAME" : null}
                  sortKey={sortKey} onSort={setSortKey} selected={selected} onSelect={handleSelectCoin}
                  visibleColumns={visibleColumns} isMobile={isMobile} backtestSymbols={backtestSymbols} loading={loading}
                  favorites={favorites} onToggleFavorite={toggleFavorite} />
              </FadeIn>
            )}
          </div>
        )}

        {activeTab === "backtest" && (
          <FadeIn delay={300} style={{ marginTop: isMobile ? 16 : 20 }}>
            <BacktestPanel isMobile={isMobile} onBacktestComplete={refreshBacktestSymbols} />
          </FadeIn>
        )}

        {activeTab === "executor" && (
          <FadeIn delay={300} style={{ marginTop: isMobile ? 16 : 20 }}>
            <ExecutorPanel api={API_BASE} />
          </FadeIn>
        )}

        {activeTab === "trading" && (
          <FadeIn delay={300} style={{ marginTop: isMobile ? 16 : 20 }}>
            <TradingPanel api={API_BASE} />
          </FadeIn>
        )}

        {activeTab === "signals" && (
          <FadeIn delay={300} style={{ marginTop: isMobile ? 16 : 20 }}>
            <SignalLogPanel api={API_BASE} isMobile={isMobile} scanData4h={data4h} scanData1d={data1d} />
          </FadeIn>
        )}

        {activeTab === "analytics" && (
          <FadeIn delay={300} style={{ marginTop: isMobile ? 16 : 20 }}>
            <AnalyticsPanel isMobile={isMobile} />
          </FadeIn>
        )}

        {activeTab === "onchain" && (
          <FadeIn delay={300} style={{ marginTop: isMobile ? 16 : 20 }}>
            <OnChainPanel isMobile={isMobile} />
          </FadeIn>
        )}

        {activeTab === "tradfi" && (
          <FadeIn delay={300} style={{ marginTop: isMobile ? 16 : 20 }}>
            <TradFiPanel
              results={displayTradfi}
              data4h={dataTradfi4h}
              data1d={dataTradfi1d}
              sortKey={sortKey}
              onSort={setSortKey}
              selected={selected}
              onSelect={setSelected}
              visibleColumns={visibleColumns}
              isMobile={isMobile}
              loading={loading}
            />
          </FadeIn>
        )}

        {activeTab === "chat" && (
          <ChatPanel isMobile={isMobile} selectedSymbol={selected?.symbol || null} />
        )}

        {activeTab === "hyperlens" && (
          <FadeIn delay={300} style={{ marginTop: isMobile ? 16 : 20 }}>
            <HyperLensPanel isMobile={isMobile} />
          </FadeIn>
        )}
      </div>}

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
      <DetailPanel selected={selected} isMobile={isMobile} isTablet={isTablet} onClose={() => setSelected(null)} api={API_BASE} />
    </div>
  );
}
