import { useState, useEffect, useCallback } from "react";
import { T, SIGNAL_META, REGIME_META, TRANSITION_META } from "../theme.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtPct(pct) {
  if (pct == null) return "\u2014";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function pctColor(pct) {
  if (pct == null) return T.text4;
  return pct >= 0 ? "#34d399" : "#f87171";
}

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

function fmtDuration(seconds) {
  if (!seconds) return "\u2014";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
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
    background: T.glassBg,
    border: `1px solid ${T.border}`,
    borderRadius: 14,
    padding: "20px 24px",
    marginBottom: 16,
    boxShadow: T.glassShadow,
  },
  sectionTitle: {
    fontSize: 11, fontWeight: 700, color: T.text3,
    letterSpacing: "0.1em", textTransform: "uppercase",
    marginBottom: 16, fontFamily: T.mono,
  },
  viewTab: (active) => ({
    background: active ? "rgba(34,211,238,0.12)" : "transparent",
    color: active ? T.accent : T.text3,
    border: `1px solid ${active ? "rgba(34,211,238,0.4)" : "rgba(255,255,255,0.08)"}`,
    borderRadius: 6, padding: "5px 14px",
    fontSize: 10, fontWeight: 700, fontFamily: T.mono,
    cursor: "pointer", letterSpacing: "0.08em", transition: "all 0.15s",
  }),
  pillBtn: (active) => ({
    background: active ? T.accent : T.surface,
    color: active ? "#000" : T.text3,
    border: `1px solid ${active ? T.accent : T.border}`,
    borderRadius: 6, padding: "4px 12px",
    fontSize: 11, fontWeight: 600, fontFamily: T.mono,
    cursor: "pointer", letterSpacing: "0.06em", transition: "all 0.15s",
  }),
  card: (borderColor) => ({
    flex: "1 1 180px", minWidth: 160, maxWidth: 260,
    background: T.surface, border: `1px solid ${borderColor}30`,
    borderRadius: 10, padding: "14px 16px",
    display: "flex", flexDirection: "column", gap: 6,
  }),
  cardSignal: (color) => ({
    fontSize: 11, fontWeight: 700, color, letterSpacing: "0.06em", fontFamily: T.mono,
  }),
  cardStat: { fontSize: 22, fontWeight: 700, color: T.text1, fontFamily: T.font },
  cardLabel: { fontSize: 10, color: T.text4, letterSpacing: "0.06em", fontFamily: T.mono },
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
  badge: (bg, color, border) => ({
    display: "inline-block", padding: "2px 8px", borderRadius: 6,
    fontSize: 10, fontWeight: 600, letterSpacing: "0.04em",
    background: bg, color, border: `1px solid ${border}`,
  }),
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

  const cellSize = isMobile ? 28 : 32;
  const labelW = isMobile ? 54 : 70;

  return (
    <div style={{ overflowX: "auto", WebkitOverflowScrolling: "touch" }} className="notable-scroll">
      <table style={{ borderCollapse: "collapse", fontFamily: T.mono, fontSize: isMobile ? 9 : 10 }}>
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
                        width: cellSize, height: cellSize,
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
// Scorecard (signal performance)
// ---------------------------------------------------------------------------

function Scorecard({ cards }) {
  if (!cards || cards.length === 0) {
    return <div style={S.empty}>No signal data yet. Signals will appear after scan cycles detect transitions.</div>;
  }

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
      {cards.map((c) => {
        const color = signalColor(c.signal);
        const borderColor = c.win_rate != null
          ? (c.win_rate >= 60 ? "#34d399" : c.win_rate < 40 ? "#f87171" : T.text4)
          : T.text4;

        return (
          <div key={c.signal} style={S.card(borderColor)}>
            <div style={S.cardSignal(color)}>{signalLabel(c.signal)}</div>
            <div style={S.cardStat}>{c.win_rate != null ? `${c.win_rate}%` : "\u2014"}</div>
            <div style={S.cardLabel}>{c.win_rate != null ? "WIN RATE (7D)" : "PENDING"}</div>
            <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>COUNT</div>
                <div style={{ fontSize: 13, color: T.text2, fontWeight: 600 }}>{c.count}</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>AVG 1D</div>
                <div style={{ fontSize: 13, color: pctColor(c.avg_1d), fontWeight: 600 }}>{fmtPct(c.avg_1d)}</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>AVG 7D</div>
                <div style={{ fontSize: 13, color: pctColor(c.avg_7d), fontWeight: 600 }}>{fmtPct(c.avg_7d)}</div>
              </div>
            </div>
            {c.has_outcomes > 0 && (
              <div style={{ fontSize: 9, color: T.text4, marginTop: 2 }}>
                {c.wins}/{c.has_outcomes} wins &bull; {c.direction}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Upgrade scorecard
// ---------------------------------------------------------------------------

function UpgradeScorecard({ data }) {
  if (!data?.cards || data.cards.length === 0) {
    return <div style={S.empty}>No transition data yet.</div>;
  }

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
      {data.cards.map((c) => {
        const m = transitionMeta(c.transition_type);
        const borderColor = c.win_rate != null
          ? (c.win_rate >= 60 ? "#34d399" : c.win_rate < 40 ? "#f87171" : T.text4)
          : T.text4;

        return (
          <div key={c.transition_type} style={S.card(borderColor)}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 14, color: m.color }}>{m.glyph}</span>
              <span style={S.cardSignal(m.color)}>{m.label}</span>
            </div>
            <div style={S.cardStat}>{c.win_rate != null ? `${c.win_rate}%` : "\u2014"}</div>
            <div style={S.cardLabel}>{c.win_rate != null ? "WIN RATE (7D)" : "PENDING"}</div>
            <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>COUNT</div>
                <div style={{ fontSize: 13, color: T.text2, fontWeight: 600 }}>{c.count}</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>AVG 1D</div>
                <div style={{ fontSize: 13, color: pctColor(c.avg_1d), fontWeight: 600 }}>{fmtPct(c.avg_1d)}</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>AVG 7D</div>
                <div style={{ fontSize: 13, color: pctColor(c.avg_7d), fontWeight: 600 }}>{fmtPct(c.avg_7d)}</div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Regime durations
// ---------------------------------------------------------------------------

function RegimeDurations({ durations }) {
  if (!durations || durations.length === 0) return null;

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={S.table}>
        <thead>
          <tr>
            <th style={S.th}>REGIME</th>
            <th style={S.th}>COUNT</th>
            <th style={{ ...S.th, textAlign: "right" }}>AVG DURATION</th>
            <th style={{ ...S.th, textAlign: "right" }}>MIN</th>
            <th style={{ ...S.th, textAlign: "right" }}>MAX</th>
          </tr>
        </thead>
        <tbody>
          {durations.map((d, i) => {
            const color = regimeColor(d.regime);
            return (
              <tr key={d.regime}
                  style={{ background: i % 2 === 1 ? T.overlay02 : "transparent" }}
                  onMouseEnter={(e) => e.currentTarget.style.background = T.overlay04}
                  onMouseLeave={(e) => e.currentTarget.style.background = i % 2 === 1 ? T.overlay02 : "transparent"}>
                <td style={S.td}>
                  <span style={S.badge(`${color}18`, color, `${color}40`)}>{d.regime}</span>
                </td>
                <td style={{ ...S.td, color: T.text2, fontWeight: 600 }}>{d.count}</td>
                <td style={{ ...S.td, textAlign: "right", color: T.text1, fontWeight: 600 }}>
                  {d.avg_duration_label || "\u2014"}
                </td>
                <td style={{ ...S.td, textAlign: "right", color: T.text3 }}>{fmtDuration(d.min_duration_seconds)}</td>
                <td style={{ ...S.td, textAlign: "right", color: T.text3 }}>{fmtDuration(d.max_duration_seconds)}</td>
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

  // Heatmap data
  const [heatmap, setHeatmap] = useState(null);

  // Scorecard data
  const [scorecard, setScorecard] = useState([]);
  const [upgradeScorecard, setUpgradeScorecard] = useState(null);
  const [regimeDurations, setRegimeDurations] = useState([]);

  // Raw log (lazy loaded)
  const [rawExpanded, setRawExpanded] = useState(false);
  const [rawEvents, setRawEvents] = useState([]);

  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      if (activeView === "heatmap") {
        const res = await fetch(`${api}/api/signals/heatmap?timeframe=${timeframe}&days=14&limit=30`);
        const data = await res.json();
        setHeatmap(data);
      } else if (activeView === "scorecard") {
        const [sc, usc, rd] = await Promise.all([
          fetch(`${api}/api/signals/scorecard?timeframe=${timeframe}`).then(r => r.json()),
          fetch(`${api}/api/signals/upgrade-scorecard?timeframe=${timeframe}`).then(r => r.json()),
          fetch(`${api}/api/signals/regime-durations?timeframe=${timeframe}`).then(r => r.json()),
        ]);
        setScorecard(sc.cards || []);
        setUpgradeScorecard(usc);
        setRegimeDurations(rd?.durations || []);
      }
    } catch (e) {
      console.error("SignalLogPanel fetch error:", e);
    } finally {
      setLoading(false);
    }
  }, [api, activeView, timeframe]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Lazy-load raw events when expanded
  useEffect(() => {
    if (!rawExpanded) return;
    fetch(`${api}/api/signals/recent?timeframe=${timeframe}&limit=50`)
      .then(r => r.json())
      .then(d => setRawEvents(d.changes || []))
      .catch(() => {});
  }, [rawExpanded, timeframe, api]);

  const VIEWS = [
    ["heatmap", "HEATMAP"],
    ["scorecard", "SCORECARD"],
  ];

  return (
    <div style={{ padding: 0 }}>
      {/* Header: view tabs + TF toggle */}
      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 10,
      }}>
        <div style={{ display: "flex", gap: 6 }}>
          {VIEWS.map(([key, label]) => (
            <button key={key} onClick={() => setActiveView(key)} style={S.viewTab(activeView === key)}>
              {label}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {["4h", "1d"].map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)} style={S.pillBtn(timeframe === tf)}>
              {tf.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div style={S.empty}>Loading...</div>
      )}

      {/* HEATMAP VIEW */}
      {!loading && activeView === "heatmap" && (
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

      {/* SCORECARD VIEW */}
      {!loading && activeView === "scorecard" && (
        <>
          <div style={S.section}>
            <div style={S.sectionTitle}>Signal Performance</div>
            <Scorecard cards={scorecard} />
          </div>
          <div style={S.section}>
            <div style={S.sectionTitle}>Transition Performance</div>
            <UpgradeScorecard data={upgradeScorecard} />
          </div>
          <div style={S.section}>
            <div style={S.sectionTitle}>Regime Durations</div>
            <RegimeDurations durations={regimeDurations} />
          </div>
        </>
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
                        <td style={{ ...S.td, color: regimeColor(ev.regime), fontWeight: 600 }}>{ev.regime}</td>
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
