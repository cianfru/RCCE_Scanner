import { useState, useEffect, useCallback, useMemo } from "react";
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

const SIGNAL_SHORT = {
  STRONG_LONG: "STR", LIGHT_LONG: "LIT", ACCUMULATE: "ACC",
  REVIVAL_SEED: "REV", REVIVAL_SEED_CONFIRMED: "REV",
  WAIT: "", TRIM: "TRM", TRIM_HARD: "TRM!", RISK_OFF: "OFF", NO_LONG: "NO",
};

const BULL_SIGNALS = new Set(["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED", "REVIVAL_SEED_CONFIRMED"]);
const EXIT_SIGNALS = new Set(["TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG"]);

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
// Scoring: rank symbols by historical bullishness
// ---------------------------------------------------------------------------

function scoreBullishHistory(row) {
  if (!row || row.length === 0) return 0;
  let score = 0;
  const len = row.length;
  row.forEach((cell, i) => {
    const sig = cell?.signal || "WAIT";
    // Weight recent days more (last day = 1.0x, first day = 0.3x)
    const recency = 0.3 + 0.7 * (i / Math.max(len - 1, 1));
    if (sig === "STRONG_LONG") score += 3 * recency;
    else if (sig === "LIGHT_LONG") score += 2 * recency;
    else if (sig === "ACCUMULATE" || sig === "REVIVAL_SEED" || sig === "REVIVAL_SEED_CONFIRMED") score += 1.5 * recency;
    else if (EXIT_SIGNALS.has(sig)) score -= 1 * recency;
  });
  return score;
}

// ---------------------------------------------------------------------------
// Signal Heatmap Grid — sorted by best historical performers
// ---------------------------------------------------------------------------

function SignalHeatmap({ data, isMobile, sortMode }) {
  // Re-sort symbols by historical bullishness
  const sortedSymbols = useMemo(() => {
    if (!data || !data.grid) return [];
    const syms = [...(data.symbols || Object.keys(data.grid))];

    if (sortMode === "bullish") {
      syms.sort((a, b) => scoreBullishHistory(data.grid[b]) - scoreBullishHistory(data.grid[a]));
    } else if (sortMode === "bearish") {
      syms.sort((a, b) => scoreBullishHistory(data.grid[a]) - scoreBullishHistory(data.grid[b]));
    }
    // "default" keeps original priority_score order
    return syms;
  }, [data, sortMode]);

  if (!data || !data.grid || sortedSymbols.length === 0) {
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
          {sortedSymbols.map((sym, rowIdx) => {
            const row = data.grid[sym];
            if (!row) return null;

            // Show bullish score as a subtle indicator
            const bullScore = scoreBullishHistory(row);
            const scoreBg = bullScore > 3 ? "rgba(52,211,153,0.06)" : bullScore < -1 ? "rgba(248,113,113,0.04)" : "transparent";

            return (
              <tr key={sym} style={{
                background: rowIdx % 2 === 1 ? T.overlay02 : scoreBg,
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
// Recent Transitions — coins that just changed signal
// ---------------------------------------------------------------------------

function RecentTransitions({ events, isMobile }) {
  if (!events || events.length === 0) {
    return <div style={S.empty}>No recent signal changes.</div>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={S.table}>
        <thead>
          <tr>
            <th style={S.th}>TIME</th>
            <th style={S.th}>SYMBOL</th>
            <th style={S.th}>FROM</th>
            <th style={S.th}></th>
            <th style={S.th}>TO</th>
            <th style={S.th}>TYPE</th>
            {!isMobile && <th style={S.th}>REGIME</th>}
          </tr>
        </thead>
        <tbody>
          {events.map((ev, i) => {
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
                <td style={{ ...S.td, fontWeight: 700, fontSize: 12 }}>{stripSymbol(ev.symbol)}</td>
                <td style={{ ...S.td, color: prevColor, fontSize: 10 }}>
                  {ev.prev_signal ? signalLabel(ev.prev_signal) : "\u2014"}
                </td>
                <td style={{ ...S.td, color: tt.color, fontSize: 12, textAlign: "center", padding: "7px 4px" }}>
                  {tt.glyph}
                </td>
                <td style={{ ...S.td, color: sigColor, fontWeight: 600 }}>
                  {signalLabel(ev.signal)}
                </td>
                <td style={S.td}>
                  <span style={{
                    display: "inline-block", padding: "1px 6px", borderRadius: 4,
                    fontSize: 9, fontWeight: 700, letterSpacing: "0.04em",
                    background: `${tt.color}15`, color: tt.color,
                    border: `1px solid ${tt.color}30`,
                  }}>{tt.label}</span>
                </td>
                {!isMobile && (
                  <td style={{ ...S.td, color: T.text3, fontSize: 10 }}>{ev.regime || "\u2014"}</td>
                )}
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
  const [activeView, setActiveView] = useState("heatmap");
  const [timeframe, setTimeframe] = useState("4h");
  const [heatmap, setHeatmap] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sortMode, setSortMode] = useState("bullish");

  // Recent transitions
  const [transitions, setTransitions] = useState([]);

  const fetchHeatmap = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${api}/api/signals/heatmap?timeframe=${timeframe}&days=14&limit=100`);
      const data = await res.json();
      setHeatmap(data);
    } catch (e) {
      console.error("SignalLogPanel fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, [api, timeframe]);

  useEffect(() => {
    if (activeView === "heatmap") fetchHeatmap();
  }, [activeView, fetchHeatmap]);

  // Fetch recent transitions
  useEffect(() => {
    if (activeView !== "transitions") return;
    fetch(`${api}/api/signals/recent?timeframe=${timeframe}&limit=50`)
      .then(r => r.json())
      .then(d => setTransitions(d.changes || []))
      .catch(() => {});
  }, [activeView, timeframe, api]);

  const VIEWS = [
    { key: "heatmap", label: "HEATMAP" },
    { key: "transitions", label: "TRANSITIONS" },
  ];

  const SORTS = [
    { key: "bullish", label: "\u2191 BULL" },
    { key: "bearish", label: "\u2193 BEAR" },
    { key: "default", label: "PRIORITY" },
  ];

  return (
    <div style={{ padding: 0 }}>
      {/* Header */}
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
          {activeView === "heatmap" && SORTS.map(s => (
            <button key={s.key} onClick={() => setSortMode(s.key)}
              style={{
                ...S.pillBtn(sortMode === s.key),
                padding: "4px 8px", fontSize: 10,
              }}>
              {s.label}
            </button>
          ))}
          <span style={{ width: 1, background: T.border, margin: "0 4px" }} />
          {["4h", "1d"].map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)} style={S.pillBtn(timeframe === tf)}>
              {tf.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* HEATMAP VIEW */}
      {activeView === "heatmap" && (
        <>
          {loading && <div style={S.empty}>Loading...</div>}
          {!loading && (
            <div style={S.section}>
              <div style={S.sectionTitle}>
                Signal Evolution — 14 Days
                <span style={{ color: T.text4, fontWeight: 500, marginLeft: 8, fontSize: 10, letterSpacing: "0.02em" }}>
                  {heatmap?.symbols?.length || 0} pairs
                </span>
              </div>
              <SignalHeatmap data={heatmap} isMobile={isMobile} sortMode={sortMode} />

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
        </>
      )}

      {/* TRANSITIONS VIEW */}
      {activeView === "transitions" && (
        <div style={S.section}>
          <div style={S.sectionTitle}>
            Recent Signal Changes
            <span style={{ color: T.text4, fontWeight: 500, marginLeft: 8, fontSize: 10, letterSpacing: "0.02em" }}>
              last 50
            </span>
          </div>
          <RecentTransitions events={transitions} isMobile={isMobile} />
        </div>
      )}
    </div>
  );
}
