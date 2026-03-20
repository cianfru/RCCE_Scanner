import { useState, useEffect, useCallback } from "react";
import { T, SIGNAL_META, TRANSITION_META } from "../theme.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function signalColor(sig) {
  return (SIGNAL_META[sig] || SIGNAL_META.WAIT).color;
}

function signalLabel(sig) {
  return (SIGNAL_META[sig] || { label: sig }).label;
}

function transitionMeta(tt) {
  return TRANSITION_META[tt] || TRANSITION_META.LATERAL;
}

function stripSymbol(sym) {
  return (sym || "").replace("/USDT", "").replace("/USD", "");
}

// Signal short labels for heatmap cells
const SIGNAL_SHORT = {
  STRONG_LONG: "STR", LIGHT_LONG: "LIT", ACCUMULATE: "ACC",
  REVIVAL_SEED: "REV", REVIVAL_SEED_CONFIRMED: "REV",
  WAIT: "", TRIM: "TRM", TRIM_HARD: "TRM!", RISK_OFF: "OFF", NO_LONG: "NO",
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

export default function SignalLogPanel({ api, isMobile }) {
  const [timeframe, setTimeframe] = useState("4h");
  const [heatmap, setHeatmap] = useState(null);
  const [loading, setLoading] = useState(false);

  // Raw log (lazy loaded)
  const [rawExpanded, setRawExpanded] = useState(false);
  const [rawEvents, setRawEvents] = useState([]);

  const fetchData = useCallback(async () => {
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

  useEffect(() => { fetchData(); }, [fetchData]);

  // Lazy-load raw events when expanded
  useEffect(() => {
    if (!rawExpanded) return;
    fetch(`${api}/api/signals/recent?timeframe=${timeframe}&limit=50`)
      .then(r => r.json())
      .then(d => setRawEvents(d.changes || []))
      .catch(() => {});
  }, [rawExpanded, timeframe, api]);

  return (
    <div style={{ padding: 0 }}>
      {/* Header: TF toggle only */}
      <div style={{
        display: "flex", justifyContent: "flex-end",
        alignItems: "center", marginBottom: 16,
      }}>
        <div style={{ display: "flex", gap: 4 }}>
          {["4h", "1d"].map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)} style={S.pillBtn(timeframe === tf)}>
              {tf.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {loading && <div style={S.empty}>Loading...</div>}

      {/* HEATMAP */}
      {!loading && (
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

      {/* RAW LOG (collapsible) */}
      <div style={{ marginTop: 16 }}>
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
    </div>
  );
}
