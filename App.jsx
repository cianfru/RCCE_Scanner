import { useState, useEffect, useCallback } from "react";

// ─── CONFIG ───────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const REGIME_META = {
  BLOWOFF:      { color: "#ff3a3a", bg: "rgba(255,58,58,0.12)",   label: "BLOWOFF",      glyph: "▲▲" },
  DISTRIBUTION: { color: "#ff8c00", bg: "rgba(255,140,0,0.12)",   label: "DISTRIBUTION", glyph: "▲" },
  MARKUP:       { color: "#00e676", bg: "rgba(0,230,118,0.1)",    label: "MARKUP",        glyph: "↗" },
  ACCUMULATION: { color: "#40c4ff", bg: "rgba(64,196,255,0.1)",   label: "ACCUMULATION", glyph: "◆" },
  CAPITULATION: { color: "#b388ff", bg: "rgba(179,136,255,0.1)",  label: "CAPITULATION", glyph: "▼▼" },
  CONTRACTION:  { color: "#78909c", bg: "rgba(120,144,156,0.08)", label: "CONTRACTION",  glyph: "—" },
  UNKNOWN:      { color: "#455a64", bg: "rgba(69,90,100,0.06)",   label: "UNKNOWN",      glyph: "?" },
};

const SIGNAL_META = {
  STRONG_BUY: { color: "#00e676", label: "STRONG BUY", dot: "●" },
  BUY:        { color: "#69f0ae", label: "BUY",         dot: "●" },
  NEUTRAL:    { color: "#546e7a", label: "NEUTRAL",     dot: "○" },
  CAUTION:    { color: "#ffd740", label: "CAUTION",     dot: "◐" },
  TRIM:       { color: "#ff8c00", label: "TRIM",        dot: "●" },
  SELL:       { color: "#ff5252", label: "SELL",        dot: "●" },
  HARD_SELL:  { color: "#ff1744", label: "HARD SELL",   dot: "●" },
};

const REGIME_ORDER = ["BLOWOFF","DISTRIBUTION","MARKUP","ACCUMULATION","CAPITULATION","CONTRACTION","UNKNOWN"];

// ─── HELPERS ─────────────────────────────────────────────────────────────────

function fmt(val, decimals = 2, suffix = "") {
  if (val === null || val === undefined || isNaN(val)) return "—";
  return `${Number(val).toFixed(decimals)}${suffix}`;
}

function zBar(z) {
  if (z === null || z === undefined) return null;
  const clamped = Math.max(-3, Math.min(3, z));
  const pct = ((clamped + 3) / 6) * 100;
  let color = "#78909c";
  if (z <= -1) color = "#b388ff";
  else if (z <= 0) color = "#40c4ff";
  else if (z <= 1.2) color = "#00e676";
  else if (z <= 2.0) color = "#ff8c00";
  else color = "#ff3a3a";
  return { pct, color };
}

function getBaseSymbol(sym) {
  return sym.replace("/USDT", "");
}

function formatCacheAge(seconds) {
  if (!seconds) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  return `${Math.round(seconds / 60)}m ago`;
}

// ─── SUBCOMPONENTS ────────────────────────────────────────────────────────────

function ZScoreBar({ z }) {
  const bar = zBar(z);
  if (!bar) return <span style={{ color: "#546e7a" }}>—</span>;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 120 }}>
      <div style={{
        flex: 1, height: 4, background: "#1a2634", borderRadius: 2, overflow: "hidden", position: "relative"
      }}>
        <div style={{
          position: "absolute",
          left: `${Math.min(bar.pct, 50)}%`,
          width: `${Math.abs(bar.pct - 50)}%`,
          height: "100%",
          background: bar.color,
          borderRadius: 2,
          left: bar.pct >= 50 ? "50%" : `${bar.pct}%`,
        }} />
        <div style={{
          position: "absolute", left: "50%", top: 0, bottom: 0,
          width: 1, background: "#2d3f50"
        }} />
      </div>
      <span style={{ color: bar.color, fontFamily: "monospace", fontSize: 11, minWidth: 40, textAlign: "right" }}>
        {fmt(z, 2)}
      </span>
    </div>
  );
}

function RegimeBadge({ regime }) {
  const m = REGIME_META[regime] || REGIME_META.UNKNOWN;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      padding: "2px 8px", borderRadius: 3,
      background: m.bg, color: m.color,
      fontSize: 10, fontFamily: "monospace", fontWeight: 700,
      letterSpacing: "0.08em", border: `1px solid ${m.color}22`,
      whiteSpace: "nowrap"
    }}>
      <span style={{ fontSize: 9 }}>{m.glyph}</span>
      {m.label}
    </span>
  );
}

function SignalDot({ signal }) {
  const m = SIGNAL_META[signal] || SIGNAL_META.NEUTRAL;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5,
      color: m.color, fontFamily: "monospace", fontSize: 11, whiteSpace: "nowrap"
    }}>
      <span style={{ fontSize: 13 }}>{m.dot}</span>
      {m.label}
    </span>
  );
}

function DivergencePill({ div }) {
  if (!div) return <span style={{ color: "#2d3f50" }}>—</span>;
  const color = div === "BULLISH" ? "#00e676" : "#ff5252";
  return (
    <span style={{
      padding: "1px 6px", borderRadius: 2,
      background: `${color}18`, color,
      fontSize: 9, fontFamily: "monospace", fontWeight: 700,
      letterSpacing: "0.1em", border: `1px solid ${color}33`
    }}>
      {div}
    </span>
  );
}

function SymbolRow({ row, selected, onSelect }) {
  const base = getBaseSymbol(row.symbol);
  const rm = REGIME_META[row.regime] || REGIME_META.UNKNOWN;
  const isHighlight = ["STRONG_BUY", "BUY", "HARD_SELL", "SELL"].includes(row.signal);

  return (
    <tr
      onClick={() => onSelect(row)}
      style={{
        cursor: "pointer",
        borderBottom: "1px solid #0d1a24",
        background: selected ? "rgba(64,196,255,0.05)" : isHighlight ? `${rm.bg}` : "transparent",
        transition: "background 0.15s",
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = "#0a1520"; }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = isHighlight ? rm.bg : "transparent"; }}
    >
      <td style={{ padding: "8px 12px", fontFamily: "monospace", fontWeight: 700, color: "#cdd9e5", fontSize: 12 }}>
        {base}
      </td>
      <td style={{ padding: "8px 12px" }}>
        <RegimeBadge regime={row.regime} />
      </td>
      <td style={{ padding: "8px 12px" }}>
        <SignalDot signal={row.signal} />
      </td>
      <td style={{ padding: "8px 12px" }}>
        <ZScoreBar z={row.zscore} />
      </td>
      <td style={{ padding: "8px 12px", fontFamily: "monospace", fontSize: 11, color: "#546e7a" }}>
        {fmt(row.energy, 2)}
      </td>
      <td style={{ padding: "8px 12px", fontFamily: "monospace", fontSize: 11 }}>
        <span style={{ color: row.momentum >= 0 ? "#00e676" : "#ff5252" }}>
          {row.momentum !== null ? `${row.momentum >= 0 ? "+" : ""}${fmt(row.momentum, 1)}%` : "—"}
        </span>
      </td>
      <td style={{ padding: "8px 12px" }}>
        <DivergencePill div={row.divergence} />
      </td>
      <td style={{ padding: "8px 12px", fontFamily: "monospace", fontSize: 11, color: "#78909c" }}>
        {row.price ? `$${row.price < 1 ? fmt(row.price, 5) : fmt(row.price, 2)}` : "—"}
      </td>
    </tr>
  );
}

function SummaryBar({ results }) {
  const counts = {};
  REGIME_ORDER.forEach(r => counts[r] = 0);
  results.forEach(r => { if (counts[r.regime] !== undefined) counts[r.regime]++; });

  const total = results.length;
  return (
    <div style={{ display: "flex", gap: 0, height: 6, borderRadius: 3, overflow: "hidden", marginBottom: 20 }}>
      {REGIME_ORDER.filter(r => counts[r] > 0).map(r => {
        const m = REGIME_META[r];
        const pct = (counts[r] / total) * 100;
        return (
          <div
            key={r}
            title={`${m.label}: ${counts[r]}`}
            style={{ flex: pct, background: m.color, minWidth: 2 }}
          />
        );
      })}
    </div>
  );
}

function StatCards({ results }) {
  const signals = { STRONG_BUY: 0, BUY: 0, CAUTION: 0, TRIM: 0, SELL: 0, HARD_SELL: 0 };
  results.forEach(r => { if (signals[r.signal] !== undefined) signals[r.signal]++; });

  const cards = [
    { label: "STRONG BUY", value: signals.STRONG_BUY, color: "#00e676" },
    { label: "BUY", value: signals.BUY, color: "#69f0ae" },
    { label: "CAUTION", value: signals.CAUTION, color: "#ffd740" },
    { label: "TRIM", value: signals.TRIM, color: "#ff8c00" },
    { label: "SELL", value: signals.SELL + signals.HARD_SELL, color: "#ff3a3a" },
  ];

  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
      {cards.map(c => (
        <div key={c.label} style={{
          flex: 1, padding: "10px 14px", background: "#060f18",
          border: `1px solid ${c.value > 0 ? c.color + "44" : "#0d1a24"}`,
          borderRadius: 4
        }}>
          <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "monospace", color: c.value > 0 ? c.color : "#2d3f50" }}>
            {c.value}
          </div>
          <div style={{ fontSize: 9, color: "#546e7a", fontFamily: "monospace", letterSpacing: "0.1em", marginTop: 2 }}>
            {c.label}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── MAIN APP ─────────────────────────────────────────────────────────────────

export default function App() {
  const [data4h, setData4h] = useState([]);
  const [data1d, setData1d] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scanRunning, setScanRunning] = useState(false);
  const [cacheAge, setCacheAge] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null);
  const [filterRegime, setFilterRegime] = useState("ALL");
  const [filterSignal, setFilterSignal] = useState("ALL");
  const [sortKey, setSortKey] = useState("regime");
  const [activeTab, setActiveTab] = useState("4h"); // "4h" | "1d" | "split"
  const [lastRefresh, setLastRefresh] = useState(null);

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
      setScanRunning(r4h.scan_running);
      setCacheAge(r4h.cache_age_seconds);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [fetchData]);

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 5 * 60 * 1000); // refresh every 5 min
    return () => clearInterval(interval);
  }, [loadAll]);

  const triggerScan = async () => {
    await fetch(`${API_BASE}/api/scan/refresh`, { method: "POST" });
    setScanRunning(true);
    setTimeout(loadAll, 3000);
  };

  const sortResults = (results) => {
    return [...results].sort((a, b) => {
      if (sortKey === "regime") {
        const ri = REGIME_ORDER.indexOf(a.regime) - REGIME_ORDER.indexOf(b.regime);
        if (ri !== 0) return ri;
        return (b.zscore || 0) - (a.zscore || 0);
      }
      if (sortKey === "zscore") return (b.zscore || 0) - (a.zscore || 0);
      if (sortKey === "momentum") return (b.momentum || 0) - (a.momentum || 0);
      if (sortKey === "symbol") return a.symbol.localeCompare(b.symbol);
      return 0;
    });
  };

  const sorted4h = sortResults(data4h);
  const sorted1d = sortResults(data1d);

  const SIGNALS_NOTABLE = ["STRONG_BUY", "BUY", "HARD_SELL", "SELL", "TRIM"];
  const notable4h = sorted4h.filter(r => SIGNALS_NOTABLE.includes(r.signal));
  const notable1d = sorted1d.filter(r => SIGNALS_NOTABLE.includes(r.signal));

  const TableHeader = ({ onSort, currentSort }) => (
    <thead>
      <tr style={{ borderBottom: "1px solid #0d1a24" }}>
        {[
          ["symbol", "SYMBOL"],
          ["regime", "REGIME"],
          [null, "SIGNAL"],
          ["zscore", "Z-SCORE"],
          [null, "ENERGY"],
          ["momentum", "30P ΔMOM"],
          [null, "DIV"],
          [null, "PRICE"],
        ].map(([key, label]) => (
          <th
            key={label}
            onClick={() => key && onSort(key)}
            style={{
              padding: "8px 12px", textAlign: "left",
              fontFamily: "monospace", fontSize: 10, fontWeight: 700,
              color: currentSort === key ? "#40c4ff" : "#2d4a5e",
              letterSpacing: "0.1em", cursor: key ? "pointer" : "default",
              userSelect: "none", whiteSpace: "nowrap"
            }}
          >
            {label}{key && currentSort === key ? " ▼" : ""}
          </th>
        ))}
      </tr>
    </thead>
  );

  const DataTable = ({ results, label }) => (
    <div style={{ flex: 1, minWidth: 0 }}>
      {label && (
        <div style={{
          fontFamily: "monospace", fontSize: 10, color: "#2d4a5e",
          letterSpacing: "0.15em", marginBottom: 8, paddingLeft: 12
        }}>{label}</div>
      )}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <TableHeader onSort={setSortKey} currentSort={sortKey} />
          <tbody>
            {results.length === 0 ? (
              <tr><td colSpan={8} style={{
                padding: "40px 12px", textAlign: "center",
                color: "#2d3f50", fontFamily: "monospace", fontSize: 12
              }}>
                {loading ? "SCANNING..." : "NO DATA"}
              </td></tr>
            ) : (
              results.map(row => (
                <SymbolRow
                  key={row.symbol}
                  row={row}
                  selected={selected?.symbol === row.symbol}
                  onSelect={setSelected}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div style={{
      minHeight: "100vh",
      background: "#030b12",
      color: "#cdd9e5",
      fontFamily: "'IBM Plex Mono', 'Fira Code', 'Courier New', monospace",
    }}>
      {/* Google Font */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;600;700&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { background: #030b12; }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: #060f18; }
        ::-webkit-scrollbar-thumb { background: #1a2634; border-radius: 2px; }
        tr:hover td { background: transparent !important; }
      `}</style>

      {/* Header */}
      <div style={{
        padding: "16px 24px", borderBottom: "1px solid #0d1a24",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "#060f18", position: "sticky", top: 0, zIndex: 100
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.15em", color: "#40c4ff" }}>
              RCCE SCANNER
            </div>
            <div style={{ fontSize: 9, color: "#2d4a5e", letterSpacing: "0.1em" }}>
              REFLEXIVE CRYPTO CYCLE ENGINE · {data4h.length} SYMBOLS
            </div>
          </div>
          {scanRunning && (
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "3px 10px", background: "rgba(64,196,255,0.1)",
              border: "1px solid #40c4ff44", borderRadius: 3,
              fontSize: 9, color: "#40c4ff", letterSpacing: "0.1em"
            }}>
              <span style={{ animation: "pulse 1s infinite" }}>◉</span> SCANNING
              <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }`}</style>
            </div>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {lastRefresh && (
            <span style={{ fontSize: 9, color: "#2d4a5e", letterSpacing: "0.08em" }}>
              UPDATED {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={triggerScan}
            style={{
              padding: "5px 14px", background: "transparent",
              border: "1px solid #1a2e3d", borderRadius: 3,
              color: "#546e7a", fontFamily: "monospace", fontSize: 10,
              cursor: "pointer", letterSpacing: "0.1em",
              transition: "all 0.15s"
            }}
            onMouseEnter={e => { e.target.style.borderColor = "#40c4ff44"; e.target.style.color = "#40c4ff"; }}
            onMouseLeave={e => { e.target.style.borderColor = "#1a2e3d"; e.target.style.color = "#546e7a"; }}
          >
            ↺ REFRESH
          </button>
        </div>
      </div>

      {/* Controls */}
      <div style={{
        padding: "12px 24px", borderBottom: "1px solid #0d1a24",
        display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
        background: "#040d16"
      }}>
        {/* View tabs */}
        <div style={{ display: "flex", gap: 1, background: "#060f18", borderRadius: 4, padding: 2, border: "1px solid #0d1a24" }}>
          {[["4h", "4H"], ["1d", "1D"], ["split", "SPLIT"]].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              style={{
                padding: "4px 12px", borderRadius: 3, border: "none",
                background: activeTab === key ? "#40c4ff" : "transparent",
                color: activeTab === key ? "#030b12" : "#546e7a",
                fontFamily: "monospace", fontSize: 10, cursor: "pointer",
                fontWeight: 700, letterSpacing: "0.1em",
                transition: "all 0.15s"
              }}
            >
              {label}
            </button>
          ))}
        </div>

        <div style={{ width: 1, height: 20, background: "#0d1a24" }} />

        {/* Regime filter */}
        <select
          value={filterRegime}
          onChange={e => setFilterRegime(e.target.value)}
          style={{
            padding: "4px 10px", background: "#060f18",
            border: "1px solid #0d1a24", borderRadius: 3,
            color: "#546e7a", fontFamily: "monospace", fontSize: 10,
            cursor: "pointer", letterSpacing: "0.08em"
          }}
        >
          <option value="ALL">ALL REGIMES</option>
          {Object.keys(REGIME_META).map(r => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>

        {/* Signal filter */}
        <select
          value={filterSignal}
          onChange={e => setFilterSignal(e.target.value)}
          style={{
            padding: "4px 10px", background: "#060f18",
            border: "1px solid #0d1a24", borderRadius: 3,
            color: "#546e7a", fontFamily: "monospace", fontSize: 10,
            cursor: "pointer", letterSpacing: "0.08em"
          }}
        >
          <option value="ALL">ALL SIGNALS</option>
          {Object.keys(SIGNAL_META).map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <div style={{ marginLeft: "auto", fontSize: 9, color: "#1a2e3d", letterSpacing: "0.08em" }}>
          CACHE {formatCacheAge(cacheAge)}
        </div>
      </div>

      {error && (
        <div style={{
          margin: "16px 24px", padding: "10px 14px",
          background: "rgba(255,58,58,0.1)", border: "1px solid #ff3a3a44",
          borderRadius: 4, fontSize: 11, color: "#ff7070", fontFamily: "monospace"
        }}>
          ⚠ API ERROR: {error} — ensure backend is running on {API_BASE}
        </div>
      )}

      {/* Main Content */}
      <div style={{ padding: "16px 24px" }}>

        {/* Summary */}
        {(data4h.length > 0 || data1d.length > 0) && (
          <div style={{ marginBottom: 20 }}>
            <SummaryBar results={activeTab === "1d" ? sorted1d : sorted4h} />
            <StatCards results={activeTab === "1d" ? sorted1d : sorted4h} />
          </div>
        )}

        {/* Notable Signals Alert Strip */}
        {(notable4h.length > 0 || notable1d.length > 0) && (
          <div style={{
            marginBottom: 16, padding: "10px 14px",
            background: "#040d16", border: "1px solid #0d1a24",
            borderRadius: 4, display: "flex", gap: 8, flexWrap: "wrap",
            alignItems: "center"
          }}>
            <span style={{ fontSize: 9, color: "#2d4a5e", letterSpacing: "0.1em", marginRight: 4 }}>
              NOTABLE
            </span>
            {[...notable4h.map(r => ({ ...r, tf: "4H" })), ...notable1d.map(r => ({ ...r, tf: "1D" }))
            ].filter((r, i, a) => a.findIndex(x => x.symbol === r.symbol && x.tf === r.tf) === i)
             .slice(0, 12)
             .map(r => {
               const sm = SIGNAL_META[r.signal] || SIGNAL_META.NEUTRAL;
               return (
                 <span
                   key={`${r.symbol}-${r.tf}`}
                   onClick={() => setSelected(r)}
                   style={{
                     padding: "2px 8px", borderRadius: 3, cursor: "pointer",
                     background: `${sm.color}18`, border: `1px solid ${sm.color}33`,
                     color: sm.color, fontSize: 10, fontFamily: "monospace",
                     display: "inline-flex", alignItems: "center", gap: 4
                   }}
                 >
                   {getBaseSymbol(r.symbol)}
                   <span style={{ fontSize: 8, opacity: 0.7 }}>{r.tf}</span>
                 </span>
               );
             })}
          </div>
        )}

        {/* Tables */}
        <div style={{ display: "flex", gap: 24 }}>
          {(activeTab === "4h" || activeTab === "split") && (
            <DataTable results={sorted4h} label={activeTab === "split" ? "4H TIMEFRAME" : null} />
          )}
          {activeTab === "split" && (
            <div style={{ width: 1, background: "#0d1a24", flexShrink: 0 }} />
          )}
          {(activeTab === "1d" || activeTab === "split") && (
            <DataTable results={sorted1d} label={activeTab === "split" ? "DAILY TIMEFRAME" : null} />
          )}
        </div>
      </div>

      {/* Detail Panel */}
      {selected && (
        <div style={{
          position: "fixed", right: 0, top: 0, bottom: 0, width: 280,
          background: "#060f18", borderLeft: "1px solid #0d1a24",
          padding: 20, overflowY: "auto", zIndex: 200
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: "#cdd9e5" }}>
                {getBaseSymbol(selected.symbol)}
              </div>
              <div style={{ fontSize: 9, color: "#2d4a5e", letterSpacing: "0.1em" }}>
                {selected.symbol} · {(selected.timeframe || "").toUpperCase()}
              </div>
            </div>
            <button
              onClick={() => setSelected(null)}
              style={{ background: "none", border: "none", color: "#2d4a5e", cursor: "pointer", fontSize: 16 }}
            >✕</button>
          </div>

          <div style={{ marginBottom: 16 }}>
            <RegimeBadge regime={selected.regime} />
          </div>
          <div style={{ marginBottom: 20 }}>
            <SignalDot signal={selected.signal} />
          </div>

          {[
            ["Z-SCORE", fmt(selected.zscore, 3)],
            ["ENERGY", fmt(selected.energy, 3)],
            ["MOMENTUM (30P)", `${selected.momentum >= 0 ? "+" : ""}${fmt(selected.momentum, 2)}%`],
            ["VOL NORM", fmt(selected.vol_norm, 3)],
            ["PRICE", selected.price ? `$${selected.price < 1 ? fmt(selected.price, 5) : fmt(selected.price, 2)}` : "—"],
            ["DIVERGENCE", selected.divergence || "NONE"],
          ].map(([label, value]) => (
            <div key={label} style={{ marginBottom: 12, padding: "8px 0", borderBottom: "1px solid #0d1a24" }}>
              <div style={{ fontSize: 9, color: "#2d4a5e", letterSpacing: "0.1em", marginBottom: 4 }}>{label}</div>
              <div style={{ fontFamily: "monospace", fontSize: 13, color: "#cdd9e5" }}>{value}</div>
            </div>
          ))}

          <div style={{ marginTop: 16 }}>
            <ZScoreBar z={selected.zscore} />
          </div>

          <a
            href={`https://www.tradingview.com/chart/?symbol=BINANCE:${getBaseSymbol(selected.symbol)}USDT`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "block", marginTop: 20, padding: "8px 14px",
              background: "transparent", border: "1px solid #1a2e3d",
              borderRadius: 3, color: "#546e7a", fontFamily: "monospace",
              fontSize: 10, textDecoration: "none", textAlign: "center",
              letterSpacing: "0.1em", transition: "all 0.15s"
            }}
            onMouseEnter={e => { e.target.style.borderColor = "#40c4ff44"; e.target.style.color = "#40c4ff"; }}
            onMouseLeave={e => { e.target.style.borderColor = "#1a2e3d"; e.target.style.color = "#546e7a"; }}
          >
            OPEN IN TRADINGVIEW ↗
          </a>
        </div>
      )}
    </div>
  );
}
