import { useState, useEffect, useCallback, useMemo } from "react";
import { T, REGIME_META, SIGNAL_META, REGIME_ORDER, MCAP_RANK, formatCacheAge } from "./theme.js";
import { useTheme } from "./ThemeContext";
import useViewport from "./hooks/useViewport.js";
import FadeIn from "./components/FadeIn.jsx";
import SummaryBar from "./components/SummaryBar.jsx";
import StatCards from "./components/StatCards.jsx";
import ConsensusBar from "./components/ConsensusBar.jsx";
import MarketContext from "./components/MarketContext.jsx";
import NotableSignals from "./components/NotableSignals.jsx";
import WarmingUp from "./components/WarmingUp.jsx";
import DataTable from "./components/DataTable.jsx";
import DetailPanel from "./components/DetailPanel.jsx";
import GroupModal from "./components/GroupModal.jsx";
import GlassCard from "./components/GlassCard.jsx";
import BacktestPanel from "./components/BacktestPanel.jsx";
import ExecutorPanel from "./components/ExecutorPanel.jsx";
import TradingPanel from "./components/TradingPanel.jsx";
import OnChainPanel from "./components/OnChainPanel.jsx";
import SignalLogPanel from "./components/SignalLogPanel.jsx";
import ChatPanel from "./components/ChatPanel.jsx";

// ─── CONFIG ───────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── COLUMN DEFINITIONS ─────────────────────────────────────────────────────
// [sortKey, label, minViewportWidth]

const COLUMNS = [
  ["priority_score", "PRI",    0],
  ["symbol",     "SYMBOL",     0],
  ["regime",     "REGIME",     0],
  [null,         "SIGNAL",     0],
  ["conditions", "COND",       480],
  [null,         "SPARK",      480],
  ["zscore",     "Z-SCORE",    480],
  ["momentum",   "MOM",        480],
  [null,         "PRICE",      480],
  ["heat",       "HEAT",       768],
  [null,         "DIV",        768],
  [null,         "EXHAUST",    768],
  [null,         "FUNDING",    1024],
  [null,         "OI",         1024],
  [null,         "CONF",       1024],
  [null,         "ENERGY",     1200],
  [null,         "PHASE",      1200],
  [null,         "FLOOR",      1200],
];

// ─── MAIN APP ─────────────────────────────────────────────────────────────────

export default function App() {
  const { width, isMobile, isTablet, isDesktop } = useViewport();
  const { mode, toggle } = useTheme();
  const hPad = isMobile ? 12 : isTablet ? 20 : 24;

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
  const [activeTab, setActiveTab] = useState("1d");
  const [lastRefresh, setLastRefresh] = useState(null);

  // Global metrics & alt season
  const [globalMetrics, setGlobalMetrics] = useState(null);
  const [altSeason, setAltSeason] = useState(null);

  // Sentiment & stablecoin
  const [sentiment, setSentiment] = useState(null);
  const [stablecoin, setStablecoin] = useState(null);

  // Portfolio groups
  const [groups, setGroups] = useState([]);
  const [activeGroupId, setActiveGroupId] = useState(null);
  const [showGroupModal, setShowGroupModal] = useState(false);
  const [editingGroup, setEditingGroup] = useState(null);

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
        const [gm, as, sent, stable] = await Promise.all([
          fetch(`${API_BASE}/api/global-metrics`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/alt-season?timeframe=${activeTab === "1d" ? "1d" : "4h"}`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/sentiment`).then(r => r.json()).catch(() => null),
          fetch(`${API_BASE}/api/stablecoin`).then(r => r.json()).catch(() => null),
        ]);
        if (gm) setGlobalMetrics(gm);
        if (as) setAltSeason(as);
        if (sent) setSentiment(sent);
        if (stable) setStablecoin(stable);
      } catch (_) {}
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [fetchData, activeTab]);

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 5 * 60 * 1000);
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
    if (!activeGroupSymbols) return data4h;
    return data4h.filter(r => activeGroupSymbols.has(r.symbol));
  }, [data4h, activeGroupSymbols]);

  const filtered1d = useMemo(() => {
    if (!activeGroupSymbols) return data1d;
    return data1d.filter(r => activeGroupSymbols.has(r.symbol));
  }, [data1d, activeGroupSymbols]);

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
  const SIGNALS_NOTABLE = ["STRONG_LONG", "LIGHT_LONG", "TRIM_HARD", "TRIM", "RISK_OFF"];
  const notable4h = sorted4h.filter(r => SIGNALS_NOTABLE.includes(r.signal));
  const notable1d = sorted1d.filter(r => SIGNALS_NOTABLE.includes(r.signal));
  const activeConsensus = activeTab === "1d" ? consensus1d : consensus4h;
  const visibleColumns = COLUMNS.filter(([, , minW]) => width >= (minW || 0));
  const showDashboard = activeTab !== "backtest" && activeTab !== "executor" && activeTab !== "trading" && activeTab !== "onchain" && activeTab !== "signals" && activeTab !== "chat";

  const tabOptions = isMobile
    ? [["4h", "4H"], ["1d", "1D"], ["chat", "AI"], ["backtest", "BACKTEST"], ["executor", "EXECUTOR"], ["trading", "PORTFOLIO"], ["signals", "SIGNALS"], ["onchain", "ON-CHAIN"]]
    : [["4h", "4H"], ["1d", "1D"], ["split", "SPLIT"], ["chat", "AI ASSIST"], ["backtest", "BACKTEST"], ["executor", "EXECUTOR"], ["trading", "PORTFOLIO"], ["signals", "SIGNALS"], ["onchain", "ON-CHAIN"]];

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ minHeight: "100vh", background: T.bg, color: T.text1, position: "relative" }}>
      {/* Fonts & Global Styles */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: var(--t-bg); -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--t-scrollThumb); border-radius: 6px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--t-scrollHover); }
        tr:hover td { background: transparent !important; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes glow { 0%,100%{box-shadow: 0 0 12px rgba(34,211,238,0.12);} 50%{box-shadow: 0 0 24px rgba(34,211,238,0.25);} }
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

      {/* ── HEADER ── */}
      <div style={{
        padding: `0 ${hPad}px`,
        borderBottom: `1px solid ${T.border}`,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: T.headerBg,
        backdropFilter: "blur(24px) saturate(1.4)", WebkitBackdropFilter: "blur(24px) saturate(1.4)",
        position: "sticky", top: 0, zIndex: 100,
      }}>
        {/* Left: logo + scanning */}
        <div style={{ display: "flex", alignItems: "center", gap: isMobile ? 8 : 16 }}>
          <img
            src="/logo.png"
            alt="Reflex"
            style={{
              height: isMobile ? 36 : 48,
              width: "auto",
              objectFit: "contain",
              flexShrink: 0,
              display: "block",
              margin: isMobile ? "6px 0" : "8px 0",
              filter: mode === "light" ? "invert(1) hue-rotate(180deg)" : "none",
            }}
          />
          {scanRunning && (
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "4px 12px",
              background: T.accentDim,
              border: `1px solid ${T.accent}20`,
              borderRadius: "20px",
              fontSize: 9, color: T.accent, letterSpacing: "0.08em",
              fontFamily: T.mono, fontWeight: 600,
              animation: "glow 2s ease infinite",
            }}>
              <span style={{ animation: "pulse 1s infinite" }}>{"\u25cf"}</span> SCANNING
            </div>
          )}
        </div>

        {/* Right: timestamp, cache, theme toggle — all on one line */}
        <div style={{
          display: "flex", alignItems: "center", gap: isMobile ? 8 : 12,
          flexShrink: 0,
        }}>
          {lastRefresh && (
            <span style={{ fontSize: 9, color: T.text4, letterSpacing: "0.06em", fontFamily: T.font }}>
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          {cacheAge != null && (
            <span style={{
              fontSize: 9, color: T.text4, fontFamily: T.mono,
              padding: "2px 8px", background: T.surface, borderRadius: "20px",
              border: `1px solid ${T.border}`,
            }}>{formatCacheAge(cacheAge)}</span>
          )}
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

      {/* ── GROUP TABS ── */}
      <div style={{
        padding: `6px ${hPad}px`,
        borderBottom: `1px solid ${T.border}`,
        display: "flex", alignItems: "center", gap: 4,
        background: `linear-gradient(180deg, ${T.overlay02} 0%, transparent 100%)`,
        overflowX: "auto", WebkitOverflowScrolling: "touch",
        scrollbarWidth: "none", msOverflowStyle: "none",
      }}>
        {groups.map(g => {
          const isActive = g.id === activeGroupId;
          const perf = computeGroupPerf(g.symbols, activeTab === "1d" ? data1d : data4h);
          const gColor = g.color || T.accent;
          return (
            <button
              key={g.id}
              onClick={() => setActiveGroupId(g.id)}
              onContextMenu={(e) => {
                e.preventDefault();
                setEditingGroup(g);
                setShowGroupModal(true);
              }}
              style={{
                padding: isMobile ? "7px 14px" : "6px 16px",
                borderRadius: 10,
                border: `1px solid ${isActive ? gColor + "50" : T.border}`,
                background: isActive ? `${gColor}15` : "transparent",
                color: isActive ? gColor : T.text3,
                fontFamily: T.mono, fontSize: 11, cursor: "pointer",
                fontWeight: isActive ? 700 : 500,
                letterSpacing: "0.04em",
                transition: "all 0.2s ease",
                display: "flex", alignItems: "center", gap: 6,
                flexShrink: 0, whiteSpace: "nowrap",
              }}
            >
              {g.name}
              {perf && perf.total > 0 && (
                <span style={{
                  fontSize: 9, fontWeight: 600,
                  color: perf.beating > perf.total / 2 ? "#34d399" : "#f87171",
                  opacity: isActive ? 1 : 0.6,
                }}>
                  {perf.beating}/{perf.total}{perf.beating > perf.total / 2 ? "\u25b2" : "\u25bc"}
                </span>
              )}
            </button>
          );
        })}
        <button
          onClick={() => { setEditingGroup(null); setShowGroupModal(true); }}
          style={{
            padding: "6px 12px", borderRadius: 10,
            border: `1px dashed ${T.border}`,
            background: "transparent", color: T.text4,
            fontFamily: T.mono, fontSize: 13, cursor: "pointer",
            fontWeight: 400, transition: "all 0.2s ease",
            flexShrink: 0,
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = T.accent; e.currentTarget.style.color = T.accent; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.color = T.text4; }}
        >
          +
        </button>
      </div>

      {/* ── CONTROLS ── */}
      <div style={{
        padding: `10px ${hPad}px`,
        borderBottom: `1px solid ${T.border}`,
        display: "flex", alignItems: "center", gap: isMobile ? 8 : 10, flexWrap: "wrap",
        background: `linear-gradient(180deg, ${T.overlay02} 0%, transparent 100%)`,
      }}>
        <div style={{
          display: "flex", gap: 2,
          background: T.glassBg,
          borderRadius: 12, padding: 3,
          border: `1px solid ${T.border}`,
          boxShadow: `inset 0 1px 2px ${T.shadow}, 0 1px 0 ${T.overlay03}`,
          flex: isMobile ? "1 1 100%" : undefined,
        }}>
          {tabOptions.map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={activeTab === key ? "apple-btn-accent" : ""}
              style={{
                padding: isMobile ? "8px 16px" : "6px 18px", borderRadius: 10, border: "none",
                background: activeTab === key
                  ? "linear-gradient(180deg, #2ee0f8 0%, #1ab8d4 100%)"
                  : "transparent",
                color: activeTab === key ? "#000" : T.text3,
                fontFamily: T.mono, fontSize: 11, cursor: "pointer",
                fontWeight: 700, letterSpacing: "0.04em",
                transition: "all 0.2s cubic-bezier(0.25, 0.46, 0.45, 0.94)",
                flex: isMobile ? 1 : undefined,
                boxShadow: activeTab === key
                  ? `0 1px 4px ${T.shadow}, inset 0 1px 0 ${T.overlay20}`
                  : "none",
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {!isMobile && <div style={{ width: 1, height: 20, background: T.border, opacity: 0.6 }} />}

        {activeGroup && (
          <button
            className="apple-btn"
            onClick={() => { setEditingGroup(activeGroup); setShowGroupModal(true); }}
            style={{
              padding: isMobile ? "8px 14px" : "6px 14px",
              fontFamily: T.mono, fontSize: 10, fontWeight: 500,
              letterSpacing: "0.04em",
              display: "flex", alignItems: "center", gap: 6,
            }}
          >
            <span style={{ fontSize: 12 }}>{"\u2699"}</span>
            {!isMobile && `${activeGroup.name} (${activeGroup.symbols.length})`}
          </button>
        )}

        {!isMobile && <div style={{ width: 1, height: 20, background: T.border, opacity: 0.6 }} />}

        {[
          { value: filterRegime, onChange: e => setFilterRegime(e.target.value), all: "All Regimes", options: Object.keys(REGIME_META) },
          { value: filterSignal, onChange: e => setFilterSignal(e.target.value), all: "All Signals", options: Object.keys(SIGNAL_META) },
        ].map((f, i) => (
          <select
            key={i}
            className="apple-select"
            value={f.value}
            onChange={f.onChange}
            style={{
              padding: isMobile ? "8px 28px 8px 12px" : "6px 28px 6px 12px",
              color: T.text2, fontFamily: T.mono, fontSize: 10, fontWeight: 500,
              cursor: "pointer", letterSpacing: "0.04em",
              flex: isMobile ? 1 : undefined,
              minWidth: 0,
              background: `${T.overlay06} url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%236e6e73'/%3E%3C/svg%3E") no-repeat right 10px center`,
            }}
          >
            <option value="ALL">{f.all}</option>
            {f.options.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        ))}

        <button
          className="apple-btn"
          onClick={triggerScan}
          style={{
            marginLeft: "auto",
            padding: isMobile ? "8px 18px" : "6px 18px",
            fontFamily: T.mono, fontSize: 10, fontWeight: 600,
            letterSpacing: "0.06em",
          }}
        >
          Refresh
        </button>
      </div>

      {/* ── ERROR ── */}
      {error && (
        <div style={{ padding: `0 ${hPad}px`, marginTop: 16 }}>
          <GlassCard style={{
            padding: "12px 18px",
            border: "1px solid rgba(248,113,113,0.15)",
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <span style={{ color: "#f87171", fontSize: 14 }}>{"\u26a0"}</span>
            <span style={{ fontSize: 11, color: "#fca5a5", fontFamily: T.mono }}>
              API Error: {error} {"\u2014"} ensure backend is running on {API_BASE}
            </span>
          </GlassCard>
        </div>
      )}

      {/* ── MAIN CONTENT ── */}
      <div style={{ paddingTop: isMobile ? 16 : 20, paddingLeft: hPad, paddingRight: hPad, paddingBottom: isMobile ? 80 : 60, position: "relative", zIndex: 1 }}>

        {showDashboard && (data4h.length > 0 || data1d.length > 0) && (
          <FadeIn>
            <SummaryBar results={activeTab === "1d" ? sorted1d : sorted4h} />
            <StatCards results={activeTab === "1d" ? sorted1d : sorted4h} isMobile={isMobile} isTablet={isTablet} />
          </FadeIn>
        )}

        {showDashboard && <ConsensusBar consensus={activeConsensus} isMobile={isMobile} />}

        {showDashboard && (
          <MarketContext globalMetrics={globalMetrics} altSeason={altSeason} sentiment={sentiment} stablecoin={stablecoin} isMobile={isMobile} />
        )}

        {showDashboard && <NotableSignals notable4h={notable4h} notable1d={notable1d} onSelect={setSelected} isMobile={isMobile} />}

        {showDashboard && <WarmingUp data={activeTab === "1d" ? sorted1d : sorted4h} onSelect={setSelected} isMobile={isMobile} />}

        {showDashboard && (
          <div style={{
            display: "flex", flexDirection: isDesktop ? "row" : "column",
            gap: isDesktop ? 20 : 16, marginTop: isMobile ? 16 : 20,
          }}>
            {(activeTab === "4h" || activeTab === "split") && (
              <FadeIn delay={500} style={{ flex: 1, minWidth: 0 }}>
                <DataTable results={sorted4h} label={activeTab === "split" ? "4H TIMEFRAME" : null}
                  sortKey={sortKey} onSort={setSortKey} selected={selected} onSelect={setSelected}
                  visibleColumns={visibleColumns} isMobile={isMobile} backtestSymbols={backtestSymbols} loading={loading} />
              </FadeIn>
            )}
            {activeTab === "split" && (
              <div style={{ width: isDesktop ? 1 : "100%", height: isDesktop ? undefined : 1, background: T.border, flexShrink: 0 }} />
            )}
            {(activeTab === "1d" || activeTab === "split") && (
              <FadeIn delay={activeTab === "split" ? 600 : 500} style={{ flex: 1, minWidth: 0 }}>
                <DataTable results={sorted1d} label={activeTab === "split" ? "DAILY TIMEFRAME" : null}
                  sortKey={sortKey} onSort={setSortKey} selected={selected} onSelect={setSelected}
                  visibleColumns={visibleColumns} isMobile={isMobile} backtestSymbols={backtestSymbols} loading={loading} />
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

        {activeTab === "chat" && (
          <FadeIn delay={300} style={{ marginTop: isMobile ? 16 : 20 }}>
            <ChatPanel isMobile={isMobile} selectedSymbol={selected?.symbol || null} />
          </FadeIn>
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
