import { useState, useEffect, useCallback, useMemo } from "react";
import { T, m, REGIME_META, SIGNAL_META, REGIME_ORDER, MCAP_RANK, formatCacheAge } from "./theme.js";
import { useTheme } from "./ThemeContext";
import useViewport from "./hooks/useViewport.js";
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
import ChatPanel from "./components/ChatPanel.jsx";
import TradFiPanel from "./components/TradFiPanel.jsx";
import NavDrawer from "./components/NavDrawer.jsx";
import HitRateStrip from "./components/HitRateStrip.jsx";
import ChangesTicker from "./components/ChangesTicker.jsx";

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
  [null,             "OI",      1440],  // OI trend — wide monitors only
];

// ─── MAIN APP ─────────────────────────────────────────────────────────────────

export default function App() {
  const { width, isMobile, isTablet, isDesktop } = useViewport();
  const { mode, toggle } = useTheme();
  const hPad = isMobile ? 16 : isTablet ? 20 : 24;

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
  const [activeTab, setActiveTab] = useState("1d");
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

  // Market pulse (narrative + regime distribution)
  const [pulse, setPulse] = useState(null);

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
  }, [isMobile, activeTab]);

  // ── Data fetching ─────────────────────────────────────────────────────────

  const fetchData = useCallback(async (tf) => {
    const params = new URLSearchParams({ timeframe: tf });
    if (filterRegime !== "ALL") params.append("regime", filterRegime);
    if (filterSignal !== "ALL") params.append("signal", filterSignal);
    const res = await fetch(`${API_BASE}/api/scan?${params}`);
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  }, [filterRegime, filterSignal]);

  const loadAll = useCallback(async () => {
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
        const [gm, as, sent, stable, tf4h, tf1d, macroData, pulseData] = await Promise.all([
          fetch(`${API_BASE}/api/global-metrics`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/alt-season?timeframe=${activeTab === "1d" ? "1d" : "4h"}`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/sentiment`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/stablecoin`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/tradfi?timeframe=4h`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/tradfi?timeframe=1d`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/coinglass/macro`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/market-pulse?timeframe=${activeTab === "1d" ? "1d" : "4h"}`).then(r => r.json()).catch(() => null),
        ]);
        if (gm) setGlobalMetrics(gm);
        if (as) setAltSeason(as);
        if (sent) setSentiment(sent);
        if (stable) setStablecoin(stable);
        if (tf4h) setDataTradfi4h(tf4h.results || []);
        if (tf1d) setDataTradfi1d(tf1d.results || []);
        if (macroData?.etf_flow_usd_7d != null) setMacro(macroData);
        if (pulseData?.narrative) setPulse(pulseData);
      } catch (_) {}
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [fetchData, activeTab]);

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 60 * 1000);
    return () => clearInterval(interval);
  }, [loadAll]);

  const triggerScan = async () => {
    await fetch(`${API_BASE}/api/scan/refresh`, { method: "POST" });
    setScanRunning(true);
    setTimeout(loadAll, 3000);
  };

  // ── Portfolio group management ───────────────────────────────────────────

  const loadGroups = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/groups`);
      const data = await res.json();
      setGroups(data || []);
      if (!activeGroupId && data.length > 0) setActiveGroupId(data[0].id);
    } catch (_) {}
  }, [activeGroupId]);

  useEffect(() => { loadGroups(); }, []);

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
    if (statCardFilter === "TRIM") return data.filter(r => r.signal === "TRIM" || r.signal === "TRIM_HARD");
    return data.filter(r => r.signal === statCardFilter);
  };
  const display4h = applyStatFilter(sorted4h);
  const display1d = applyStatFilter(sorted1d);
  const displayTradfi = applyStatFilter(sortedTradfi);

  const activeConsensus = activeTab === "1d" ? consensus1d : consensus4h;
  const visibleColumns = COLUMNS.filter(([, , minW]) => width >= (minW || 0));
  const showDashboard = activeTab !== "backtest" && activeTab !== "executor" && activeTab !== "trading" && activeTab !== "onchain" && activeTab !== "signals" && activeTab !== "chat" && activeTab !== "tradfi";

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
        body { background: var(--t-bg); -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; }
        table, th, td, span, div, button, select, input, textarea, p, label { font-family: inherit; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--t-scrollThumb); border-radius: 6px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--t-scrollHover); }
        tr:hover td { background: transparent !important; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes glow { 0%,100%{box-shadow: 0 0 12px rgba(34,211,238,0.12);} 50%{box-shadow: 0 0 24px rgba(34,211,238,0.25);} }
        @keyframes livePulse { 0%,100%{opacity:1; text-shadow: 0 0 6px rgba(34,197,94,0.6);} 50%{opacity:0.3; text-shadow: none;} }
        @keyframes orbBreathe { 0%,100%{opacity:0.6;transform:scale(1)} 50%{opacity:0.9;transform:scale(1.08)} }
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
            onClick={() => { setActiveTab("1d"); setFilterRegime("ALL"); setFilterSignal("ALL"); setStatCardFilter(null); }}
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

      {/* ── SECTION TITLE (hidden for chat — full-immersion mode) ── */}
      {activeTab !== "chat" && (
        <div style={{
          padding: `${isMobile ? T.sp4 : T.sp3}px ${hPad}px ${T.sp1}px`,
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
           activeTab === "onchain" ? "On-Chain" :
           activeTab === "tradfi" ? "TradFi" :
           "Scanner"}
        </div>
      )}

      {/* ── MAIN CONTENT ── */}
      <div style={{ paddingTop: 0, paddingLeft: hPad, paddingRight: hPad, paddingBottom: isMobile ? 80 : 60, position: "relative" }}>

        {showDashboard && (data4h.length > 0 || data1d.length > 0) && (
          <FadeIn>
            <SummaryBar results={activeTab === "1d" ? sorted1d : sorted4h} />
            <StatCards results={activeTab === "1d" ? sorted1d : sorted4h} isMobile={isMobile} isTablet={isTablet} activeSignalFilter={statCardFilter} onSignalFilter={setStatCardFilter} />
          </FadeIn>
        )}

        {showDashboard && <ConsensusBar consensus={activeConsensus} pulse={pulse} isMobile={isMobile} activeTab={activeTab} onTabChange={setActiveTab} searchTerm={searchTerm} onSearchChange={setSearchTerm} />}

        {showDashboard && <HitRateStrip timeframe={activeTab === "1d" ? "1d" : "4h"} isMobile={isMobile} />}

        {showDashboard && (
          <MarketContext globalMetrics={globalMetrics} altSeason={altSeason} sentiment={sentiment} stablecoin={stablecoin} macro={macro} isMobile={isMobile} />
        )}

        {showDashboard && <SignalBar data4h={sorted4h} data1d={sorted1d} onSelect={setSelected} isMobile={isMobile} />}

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
                  sortKey={sortKey} onSort={setSortKey} selected={selected} onSelect={setSelected}
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
                  sortKey={sortKey} onSort={setSortKey} selected={selected} onSelect={setSelected}
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
            <SignalLogPanel api={API_BASE} isMobile={isMobile} />
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
      </div>

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
