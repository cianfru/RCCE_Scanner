import { useState, useEffect, useCallback, useMemo } from "react";
import { T, SIGNAL_META, REGIME_META, TRANSITION_META } from "../theme.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function signalColor(sig) {
  return (SIGNAL_META[sig] || SIGNAL_META.WAIT).color;
}

function signalLabel(sig) {
  return (SIGNAL_META[sig] || { label: sig }).label;
}

function regimeColor(reg) {
  return (REGIME_META[reg] || REGIME_META.FLAT).color;
}

function transitionMeta(tt) {
  return TRANSITION_META[tt] || TRANSITION_META.LATERAL;
}

function stripSymbol(sym) {
  return (sym || "").replace("/USDT", "").replace("/USD", "");
}

function fmtPrice(p) {
  if (!p && p !== 0) return "—";
  if (p >= 1000) return `$${p.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  if (p >= 1) return `$${p.toFixed(4)}`;
  return `$${p.toFixed(6)}`;
}

function fmtConditions(met, total) {
  if (met == null || total == null) return "—";
  return `${met}/${total}`;
}

// Signal short labels for heatmap cells
const SIGNAL_SHORT = {
  STRONG_LONG: "STR", LIGHT_LONG: "LIT", ACCUMULATE: "ACC",
  REVIVAL_SEED: "REV", REVIVAL_SEED_CONFIRMED: "REV",
  WAIT: "", TRIM: "TRM", TRIM_HARD: "TRM!", RISK_OFF: "OFF", NO_LONG: "NO",
};

// Signal priority for sorting (lower = more important)
const SIGNAL_PRIORITY = {
  STRONG_LONG: 0, LIGHT_LONG: 1, ACCUMULATE: 2,
  REVIVAL_SEED: 3, REVIVAL_SEED_CONFIRMED: 3,
  TRIM_HARD: 4, RISK_OFF: 5, TRIM: 6, NO_LONG: 7, WAIT: 8,
};

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const S = {
  section: {
    background: T.glassBg, border: `1px solid ${T.border}`,
    borderRadius: 14, padding: "20px 24px",
    marginBottom: 16, boxShadow: T.glassShadow,
  },
  sectionTitle: {
    fontSize: 11, fontWeight: 700, color: T.text3,
    letterSpacing: "0.1em", textTransform: "uppercase",
    marginBottom: 16, fontFamily: T.mono,
  },
  pillBtn: (active) => ({
    background: active ? T.accent : T.surface,
    color: active ? "#000" : T.text3,
    border: `1px solid ${active ? T.accent : T.border}`,
    borderRadius: 6, padding: "4px 12px",
    fontSize: 11, fontWeight: 600, fontFamily: T.mono,
    cursor: "pointer", letterSpacing: "0.06em", transition: "all 0.15s",
  }),
  table: { width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: T.mono },
  th: {
    textAlign: "left", padding: "8px 10px",
    borderBottom: `1px solid ${T.border}`, color: T.text3,
    fontSize: 10, fontWeight: 600, letterSpacing: "0.08em",
    textTransform: "uppercase", whiteSpace: "nowrap",
    cursor: "pointer", userSelect: "none",
  },
  td: {
    padding: "7px 10px", borderBottom: `1px solid ${T.overlay04}`,
    color: T.text2, whiteSpace: "nowrap",
  },
  empty: {
    textAlign: "center", padding: "40px 20px",
    color: T.text4, fontSize: 13, fontFamily: T.mono,
  },
};

// ---------------------------------------------------------------------------
// Badge helper
// ---------------------------------------------------------------------------

function Badge({ bg, color, border, children }) {
  return (
    <span style={{
      display: "inline-block", padding: "2px 7px", borderRadius: 6,
      fontSize: 9, fontWeight: 700, letterSpacing: "0.04em",
      background: bg, color, border: `1px solid ${border}`,
    }}>{children}</span>
  );
}

// ---------------------------------------------------------------------------
// Pairs Table — ALL pairs, sortable, filterable
// ---------------------------------------------------------------------------

const SORT_OPTIONS = [
  { key: "priority", label: "PRIORITY" },
  { key: "signal", label: "SIGNAL" },
  { key: "regime", label: "REGIME" },
  { key: "zscore", label: "Z-SCORE" },
  { key: "heat", label: "HEAT" },
  { key: "conditions", label: "CONDITIONS" },
];

const SIGNAL_FILTERS = ["ALL", "ENTRY", "EXIT", "WAIT"];
const ENTRY_SIGNALS = new Set(["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"]);
const EXIT_SIGNALS = new Set(["TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"]);

function PairsTable({ data, isMobile }) {
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("priority");
  const [signalFilter, setSignalFilter] = useState("ALL");

  const sorted = useMemo(() => {
    if (!data || data.length === 0) return [];
    let out = [...data];

    // Text search
    if (search) {
      const q = search.toUpperCase();
      out = out.filter(p => stripSymbol(p.symbol).toUpperCase().includes(q));
    }

    // Signal category filter
    if (signalFilter === "ENTRY") out = out.filter(p => ENTRY_SIGNALS.has(p.signal));
    else if (signalFilter === "EXIT") out = out.filter(p => EXIT_SIGNALS.has(p.signal));
    else if (signalFilter === "WAIT") out = out.filter(p => p.signal === "WAIT");

    // Sort
    if (sortBy === "priority") out.sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0));
    else if (sortBy === "signal") out.sort((a, b) => (SIGNAL_PRIORITY[a.signal] ?? 8) - (SIGNAL_PRIORITY[b.signal] ?? 8));
    else if (sortBy === "regime") out.sort((a, b) => (a.regime || "").localeCompare(b.regime || ""));
    else if (sortBy === "zscore") out.sort((a, b) => Math.abs(b.zscore || 0) - Math.abs(a.zscore || 0));
    else if (sortBy === "heat") out.sort((a, b) => (b.heat || 0) - (a.heat || 0));
    else if (sortBy === "conditions") out.sort((a, b) => (b.conditions_met || 0) - (a.conditions_met || 0));

    return out;
  }, [data, search, sortBy, signalFilter]);

  // Summary counters
  const counts = useMemo(() => {
    if (!data) return {};
    const entry = data.filter(p => ENTRY_SIGNALS.has(p.signal)).length;
    const exit = data.filter(p => EXIT_SIGNALS.has(p.signal)).length;
    const wait = data.filter(p => p.signal === "WAIT").length;
    return { total: data.length, entry, exit, wait };
  }, [data]);

  if (!data || data.length === 0) return <div style={S.empty}>No scan data available.</div>;

  return (
    <>
      {/* Summary strip */}
      <div style={{
        display: "flex", gap: 16, marginBottom: 14, flexWrap: "wrap",
        alignItems: "center", fontFamily: T.mono, fontSize: 11,
      }}>
        <span style={{ color: T.text3 }}>{counts.total} pairs</span>
        <span style={{ color: "#34d399" }}>{counts.entry} entry</span>
        <span style={{ color: "#f87171" }}>{counts.exit} exit</span>
        <span style={{ color: T.text4 }}>{counts.wait} wait</span>
      </div>

      {/* Controls */}
      <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap", alignItems: "center" }}>
        <input
          style={{
            background: T.surface, color: T.text2, border: `1px solid ${T.border}`,
            borderRadius: 8, padding: "6px 10px", fontSize: 12, fontFamily: T.mono,
            flex: "1 1 120px", minWidth: 100, outline: "none",
          }}
          type="text" placeholder="SEARCH..." value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <div style={{ display: "flex", gap: 4 }}>
          {SIGNAL_FILTERS.map(f => (
            <button key={f} onClick={() => setSignalFilter(f)} style={S.pillBtn(signalFilter === f)}>
              {f}
            </button>
          ))}
        </div>
        <select
          style={{
            background: T.surface, color: T.text2, border: `1px solid ${T.border}`,
            borderRadius: 8, padding: "6px 10px", fontSize: 11, fontFamily: T.mono, cursor: "pointer",
          }}
          value={sortBy} onChange={e => setSortBy(e.target.value)}
        >
          {SORT_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }} className="notable-scroll">
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>SYMBOL</th>
              <th style={S.th}>SIGNAL</th>
              <th style={S.th}>REGIME</th>
              <th style={{ ...S.th, textAlign: "center" }}>COND</th>
              {!isMobile && <th style={{ ...S.th, textAlign: "right" }}>Z-SCORE</th>}
              {!isMobile && <th style={{ ...S.th, textAlign: "right" }}>HEAT</th>}
              {!isMobile && <th style={{ ...S.th, textAlign: "right" }}>PRICE</th>}
              {!isMobile && <th style={{ ...S.th, textAlign: "right" }}>PRI</th>}
            </tr>
          </thead>
          <tbody>
            {sorted.map((p, i) => {
              const sigMeta = SIGNAL_META[p.signal] || SIGNAL_META.WAIT;
              const sigColor = sigMeta.color;
              const regColor = regimeColor(p.regime);
              const heatPct = p.heat || 0;
              const heatColor = heatPct > 70 ? "#f87171" : heatPct > 40 ? "#fbbf24" : "#34d399";

              return (
                <tr key={p.symbol} style={{ background: i % 2 === 1 ? T.overlay02 : "transparent" }}>
                  <td style={{ ...S.td, fontWeight: 700, fontSize: 12 }}>
                    {stripSymbol(p.symbol)}
                  </td>
                  <td style={S.td}>
                    <Badge bg={`${sigColor}18`} color={sigColor} border={`${sigColor}40`}>
                      {signalLabel(p.signal)}
                    </Badge>
                  </td>
                  <td style={{ ...S.td, color: regColor, fontWeight: 600, fontSize: 10, letterSpacing: "0.06em" }}>
                    {p.regime}
                  </td>
                  <td style={{ ...S.td, textAlign: "center", fontSize: 10, color: T.text3 }}>
                    {fmtConditions(p.conditions_met, p.conditions_total)}
                  </td>
                  {!isMobile && (
                    <td style={{ ...S.td, textAlign: "right", fontSize: 11, color: T.text2 }}>
                      {p.zscore != null ? Number(p.zscore).toFixed(2) : "—"}
                    </td>
                  )}
                  {!isMobile && (
                    <td style={{ ...S.td, textAlign: "right" }}>
                      <span style={{
                        display: "inline-flex", alignItems: "center", gap: 4,
                        fontSize: 10, fontWeight: 600,
                      }}>
                        <span style={{
                          display: "inline-block", width: 32, height: 4,
                          borderRadius: 2, background: T.overlay04, overflow: "hidden",
                        }}>
                          <span style={{
                            display: "block", width: `${Math.min(heatPct, 100)}%`, height: "100%",
                            background: heatColor, borderRadius: 2,
                          }} />
                        </span>
                        <span style={{ color: heatColor }}>{Math.round(heatPct)}</span>
                      </span>
                    </td>
                  )}
                  {!isMobile && (
                    <td style={{ ...S.td, textAlign: "right", fontSize: 11, color: T.text3 }}>
                      {fmtPrice(p.price)}
                    </td>
                  )}
                  {!isMobile && (
                    <td style={{ ...S.td, textAlign: "right", fontSize: 10, color: T.text4 }}>
                      {p.priority_score != null ? Math.round(p.priority_score) : "—"}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div style={{ fontSize: 9, color: T.text4, fontFamily: T.mono, marginTop: 10, textAlign: "right" }}>
        {sorted.length} / {counts.total} pairs shown
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Signal Heatmap Grid
// ---------------------------------------------------------------------------

function SignalHeatmap({ data, isMobile }) {
  if (!data || !data.grid || Object.keys(data.grid).length === 0) {
    return <div style={S.empty}>No signal history yet. Data will appear after a few scan cycles.</div>;
  }

  const cellMinSize = isMobile ? 28 : 36;
  const labelW = isMobile ? 54 : 70;

  return (
    <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }} className="notable-scroll">
      <table style={{ borderCollapse: "collapse", fontFamily: T.mono, fontSize: isMobile ? 9 : 10, width: "100%", tableLayout: "fixed" }}>
        <thead>
          <tr>
            <th style={{
              position: "sticky", left: 0, zIndex: 2,
              background: T.bg, padding: "4px 6px",
              width: labelW, minWidth: labelW,
              fontSize: 9, color: T.text4, textAlign: "left",
              borderBottom: `1px solid ${T.border}`,
            }}></th>
            {data.days.map((day, i) => (
              <th key={i} style={{
                padding: "4px 2px", textAlign: "center",
                fontSize: isMobile ? 8 : 9, color: T.text4,
                fontWeight: 600, letterSpacing: "0.04em",
                borderBottom: `1px solid ${T.border}`,
                whiteSpace: "nowrap",
              }}>{day}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.symbols.map((sym, rowIdx) => {
            const row = data.grid[sym];
            if (!row) return null;
            return (
              <tr key={sym} style={{
                background: rowIdx % 2 === 1 ? T.overlay02 : "transparent",
              }}>
                <td style={{
                  position: "sticky", left: 0, zIndex: 1,
                  background: rowIdx % 2 === 1 ? T.overlay02 : T.bg,
                  padding: "2px 6px", fontSize: isMobile ? 9 : 10,
                  color: T.text2, fontWeight: 600,
                  borderBottom: `1px solid ${T.overlay04}`,
                  width: labelW, minWidth: labelW,
                }}>{stripSymbol(sym)}</td>
                {row.map((cell, colIdx) => {
                  const signal = cell?.signal || "WAIT";
                  const cond = cell?.cond || "";
                  const meta = SIGNAL_META[signal] || SIGNAL_META.WAIT;
                  const color = meta.color;
                  const shortLabel = SIGNAL_SHORT[signal] ?? "";
                  const isWait = signal === "WAIT";
                  const tooltip = `${stripSymbol(sym)} \u2014 ${data.days[colIdx]}: ${signalLabel(signal)}${cond ? ` (${cond})` : ""}`;

                  return (
                    <td key={colIdx} title={tooltip} style={{
                      padding: 1,
                      borderBottom: `1px solid ${T.overlay04}`,
                    }}>
                      <div style={{
                        minWidth: cellMinSize, height: cellMinSize,
                        borderRadius: 4,
                        background: isWait ? T.overlay04 : `${color}20`,
                        border: `1px solid ${isWait ? "transparent" : `${color}35`}`,
                        display: "flex", flexDirection: "column",
                        alignItems: "center", justifyContent: "center",
                        transition: "all 0.2s",
                        cursor: "default",
                      }}>
                        {!isWait && shortLabel && (
                          <span style={{
                            fontSize: isMobile ? 7 : 8,
                            fontWeight: 700, color,
                            lineHeight: 1,
                          }}>{shortLabel}</span>
                        )}
                        {cond && (
                          <span style={{
                            fontSize: isMobile ? 7 : 8,
                            color: isWait ? T.text4 : `${color}cc`,
                            lineHeight: 1,
                            marginTop: shortLabel && !isWait ? 1 : 0,
                          }}>{cond}</span>
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Panel
// ---------------------------------------------------------------------------

export default function SignalLogPanel({ api, isMobile, scanData4h, scanData1d }) {
  const [activeView, setActiveView] = useState("pairs");
  const [timeframe, setTimeframe] = useState("4h");
  const [heatmap, setHeatmap] = useState(null);
  const [loading, setLoading] = useState(false);

  // Raw log (lazy loaded)
  const [rawExpanded, setRawExpanded] = useState(false);
  const [rawEvents, setRawEvents] = useState([]);

  // Pick scan data based on timeframe
  const scanData = timeframe === "4h" ? scanData4h : scanData1d;

  const fetchHeatmap = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${api}/api/signals/heatmap?timeframe=${timeframe}&days=14&limit=30`);
      const data = await res.json();
      setHeatmap(data);
    } catch (e) {
      console.error("SignalLogPanel fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, [api, timeframe]);

  // Only fetch heatmap when that view is active
  useEffect(() => {
    if (activeView === "heatmap") fetchHeatmap();
  }, [activeView, fetchHeatmap]);

  // Lazy-load raw events when log view active + expanded
  useEffect(() => {
    if (activeView !== "log" || !rawExpanded) return;
    fetch(`${api}/api/signals/recent?timeframe=${timeframe}&limit=50`)
      .then(r => r.json())
      .then(d => setRawEvents(d.changes || []))
      .catch(() => {});
  }, [rawExpanded, timeframe, api, activeView]);

  const VIEWS = [
    { key: "pairs", label: "PAIRS" },
    { key: "heatmap", label: "HEATMAP" },
    { key: "log", label: "LOG" },
  ];

  return (
    <div style={{ padding: 0 }}>
      {/* Header: view tabs + TF toggle */}
      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 8,
      }}>
        <div style={{ display: "flex", gap: 6 }}>
          {VIEWS.map(v => (
            <button key={v.key} onClick={() => setActiveView(v.key)}
              style={{ ...S.pillBtn(activeView === v.key), flexShrink: 0 }}>
              {v.label}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
          {["4h", "1d"].map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)} style={S.pillBtn(timeframe === tf)}>
              {tf.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* PAIRS VIEW (default) */}
      {activeView === "pairs" && (
        <div style={S.section}>
          <div style={S.sectionTitle}>All Pairs — Current State ({timeframe.toUpperCase()})</div>
          <PairsTable data={scanData} isMobile={isMobile} />
        </div>
      )}

      {/* HEATMAP VIEW */}
      {activeView === "heatmap" && loading && <div style={S.empty}>Loading...</div>}
      {activeView === "heatmap" && !loading && (
        <div style={S.section}>
          <div style={S.sectionTitle}>Signal Evolution — Last 14 Days</div>
          <SignalHeatmap data={heatmap} isMobile={isMobile} />

          {/* Legend */}
          <div style={{
            display: "flex", flexWrap: "wrap", gap: 8,
            marginTop: 14, paddingTop: 12,
            borderTop: `1px solid ${T.overlay04}`,
          }}>
            {Object.entries(SIGNAL_META).map(([key, meta]) => {
              if (key === "REVIVAL_SEED") return null;
              return (
                <div key={key} style={{
                  display: "flex", alignItems: "center", gap: 4,
                  fontSize: 9, fontFamily: T.mono, color: T.text3,
                }}>
                  <div style={{
                    width: 10, height: 10, borderRadius: 2,
                    background: key === "WAIT" ? T.overlay04 : `${meta.color}30`,
                    border: `1px solid ${key === "WAIT" ? T.border : `${meta.color}50`}`,
                  }} />
                  {meta.label}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* LOG VIEW */}
      {activeView === "log" && (
        <div style={{ marginTop: 0 }}>
          <button
            onClick={() => setRawExpanded(!rawExpanded)}
            style={{
              background: "transparent", border: `1px solid ${T.border}`,
              borderRadius: 8, padding: "8px 16px",
              color: T.text4, fontSize: 10, fontFamily: T.mono,
              fontWeight: 600, letterSpacing: "0.08em",
              cursor: "pointer", width: "100%", textAlign: "left",
            }}
          >
            {rawExpanded ? "\u25BC" : "\u25B6"} RAW EVENT LOG ({rawEvents.length || "..."})
          </button>
          {rawExpanded && rawEvents.length > 0 && (
            <div style={{ ...S.section, marginTop: 8 }}>
              <div style={{ overflowX: "auto" }}>
                <table style={S.table}>
                  <thead>
                    <tr>
                      <th style={S.th}>TIME</th>
                      <th style={S.th}>SYMBOL</th>
                      <th style={S.th}>SIGNAL</th>
                      <th style={S.th}>PREV</th>
                      <th style={S.th}>TYPE</th>
                      <th style={S.th}>REGIME</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rawEvents.map((ev, i) => {
                      const sigColor = signalColor(ev.signal);
                      const prevColor = signalColor(ev.prev_signal);
                      const tt = transitionMeta(ev.transition_type);
                      const ago = ev.timestamp
                        ? (() => {
                            const diff = Date.now() / 1000 - ev.timestamp;
                            if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
                            if (diff < 86400) return `${(diff / 3600).toFixed(1)}h ago`;
                            return `${(diff / 86400).toFixed(1)}d ago`;
                          })()
                        : "\u2014";
                      return (
                        <tr key={`${ev.symbol}-${ev.timestamp}-${i}`}
                            style={{ background: i % 2 === 1 ? T.overlay02 : "transparent" }}>
                          <td style={{ ...S.td, color: T.text3, fontSize: 10 }}>{ago}</td>
                          <td style={{ ...S.td, fontWeight: 600 }}>{stripSymbol(ev.symbol)}</td>
                          <td style={{ ...S.td, color: sigColor, fontWeight: 600 }}>{signalLabel(ev.signal)}</td>
                          <td style={{ ...S.td, color: prevColor, fontSize: 10 }}>{ev.prev_signal ? signalLabel(ev.prev_signal) : "\u2014"}</td>
                          <td style={S.td}>
                            <span style={{ color: tt.color, fontWeight: 600 }}>{tt.glyph} {tt.label}</span>
                          </td>
                          <td style={{ ...S.td, color: signalColor(ev.regime), fontWeight: 600 }}>{ev.regime}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
