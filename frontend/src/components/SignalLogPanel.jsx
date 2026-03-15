import { useState, useEffect, useCallback } from "react";
import { T, SIGNAL_META, REGIME_META, TRANSITION_META } from "../theme.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(ts) {
  if (!ts) return "\u2014";
  const diff = (Date.now() / 1000) - ts;
  if (diff < 60)   return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${(diff / 3600).toFixed(1)}h ago`;
  return `${(diff / 86400).toFixed(1)}d ago`;
}

function fullDate(ts) {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString();
}

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

function fmtPrice(p) {
  if (!p && p !== 0) return "\u2014";
  if (p >= 1000) return `$${p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (p >= 1)    return `$${p.toFixed(4)}`;
  return `$${p.toFixed(6)}`;
}

function fmtDuration(seconds) {
  if (!seconds) return "\u2014";
  const s = Math.round(seconds);
  if (s < 3600)  return `${Math.floor(s / 60)}m`;
  if (s < 86400) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return m ? `${h}h ${m}m` : `${h}h`;
  }
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  return h ? `${d}d ${h}h` : `${d}d`;
}

function stripSymbol(sym) {
  return (sym || "").replace(/\/USDT:USDT|USDT|\/USDT/g, "");
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const S = {
  panel: { padding: 0 },
  section: {
    background: T.glassBg,
    border: `1px solid ${T.border}`,
    borderRadius: 14,
    padding: "20px 24px",
    marginBottom: 16,
    boxShadow: T.glassShadow,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: 700,
    color: T.text3,
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    marginBottom: 16,
    fontFamily: T.mono,
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 16,
    flexWrap: "wrap",
    gap: 10,
  },
  pillBtn: (active) => ({
    background: active ? T.accent : T.surface,
    color: active ? "#000" : T.text3,
    border: `1px solid ${active ? T.accent : T.border}`,
    borderRadius: 6,
    padding: "4px 12px",
    fontSize: 11,
    fontWeight: 600,
    fontFamily: T.mono,
    cursor: "pointer",
    letterSpacing: "0.06em",
    transition: "all 0.15s",
  }),
  viewTab: (active) => ({
    background: active ? "rgba(34,211,238,0.12)" : "transparent",
    color: active ? T.accent : T.text3,
    border: `1px solid ${active ? "rgba(34,211,238,0.4)" : T.overlay08 || "rgba(255,255,255,0.08)"}`,
    borderRadius: 6,
    padding: "5px 14px",
    fontSize: 10,
    fontWeight: 700,
    fontFamily: T.mono,
    cursor: "pointer",
    letterSpacing: "0.08em",
    transition: "all 0.15s",
  }),
  filterBar: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
    marginBottom: 14,
    alignItems: "center",
  },
  select: {
    background: T.surface,
    color: T.text2,
    border: `1px solid ${T.border}`,
    borderRadius: 8,
    padding: "6px 10px",
    fontSize: 12,
    fontFamily: T.mono,
    cursor: "pointer",
  },
  input: {
    background: T.surface,
    color: T.text2,
    border: `1px solid ${T.border}`,
    borderRadius: 8,
    padding: "6px 10px",
    fontSize: 12,
    fontFamily: T.mono,
    width: 140,
    outline: "none",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 12,
    fontFamily: T.mono,
  },
  th: {
    textAlign: "left",
    padding: "8px 10px",
    borderBottom: `1px solid ${T.border}`,
    color: T.text3,
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    whiteSpace: "nowrap",
  },
  td: {
    padding: "7px 10px",
    borderBottom: `1px solid ${T.overlay04}`,
    color: T.text2,
    whiteSpace: "nowrap",
  },
  badge: (bg, color, border) => ({
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 6,
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: "0.04em",
    background: bg,
    color: color,
    border: `1px solid ${border}`,
  }),
  pill: (color) => ({
    display: "inline-flex",
    alignItems: "center",
    gap: 4,
    padding: "2px 10px",
    borderRadius: 20,
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "0.06em",
    background: `${color}14`,
    color: color,
    border: `1px solid ${color}25`,
  }),
  card: (borderColor) => ({
    flex: "1 1 180px",
    minWidth: 160,
    maxWidth: 260,
    background: T.surface,
    border: `1px solid ${borderColor}30`,
    borderRadius: 10,
    padding: "14px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
  }),
  cardSignal: (color) => ({
    fontSize: 11,
    fontWeight: 700,
    color: color,
    letterSpacing: "0.06em",
    fontFamily: T.mono,
  }),
  cardStat: {
    fontSize: 22,
    fontWeight: 700,
    color: T.text1,
    fontFamily: T.font,
  },
  cardLabel: {
    fontSize: 10,
    color: T.text4,
    letterSpacing: "0.06em",
    fontFamily: T.mono,
  },
  pagination: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginTop: 12,
    gap: 8,
  },
  pageBtn: (disabled) => ({
    background: disabled ? T.overlay04 : T.surface,
    color: disabled ? T.text4 : T.text2,
    border: `1px solid ${T.border}`,
    borderRadius: 8,
    padding: "6px 14px",
    fontSize: 11,
    fontFamily: T.mono,
    cursor: disabled ? "default" : "pointer",
    opacity: disabled ? 0.5 : 1,
  }),
  empty: {
    textAlign: "center",
    padding: "40px 20px",
    color: T.text4,
    fontSize: 13,
    fontFamily: T.mono,
  },
  contextPanel: {
    background: T.surface,
    border: `1px solid ${T.overlay08 || "rgba(255,255,255,0.08)"}`,
    borderRadius: 10,
    padding: "12px 16px",
    marginTop: 8,
    marginBottom: 4,
  },
  ctxTitle: {
    fontSize: 9,
    fontWeight: 700,
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    color: T.text4,
    fontFamily: T.mono,
    marginBottom: 6,
  },
  ctxRow: {
    display: "flex",
    justifyContent: "space-between",
    padding: "2px 0",
    fontSize: 11,
    fontFamily: T.mono,
  },
  ctxLabel: { color: T.text3, fontSize: 10 },
  ctxValue: { color: T.text2, fontWeight: 600 },
};

// ---------------------------------------------------------------------------
// Transition pill
// ---------------------------------------------------------------------------

function TransitionPill({ type }) {
  if (!type) return null;
  const m = transitionMeta(type);
  return (
    <span style={S.pill(m.color)}>
      <span>{m.glyph}</span>
      <span>{m.label}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Context expansion panel (engine snapshot drill-down)
// ---------------------------------------------------------------------------

function ContextPanel({ contextStr, isMobile }) {
  if (!contextStr) return <div style={{ ...S.empty, padding: 16 }}>No context data</div>;

  let ctx;
  try { ctx = JSON.parse(contextStr); } catch { return null; }

  const { rcce, heatmap, exhaustion, synthesis, market } = ctx;
  const gridCols = isMobile ? "1fr 1fr" : "1fr 1fr 1fr";

  const Dot = ({ on, color, label }) => (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <span style={{ color: on ? color : T.text4, filter: on ? `drop-shadow(0 0 3px ${color})` : "none" }}>
        {on ? "\u25cf" : "\u25cb"}
      </span>
      <span style={{ fontSize: 10, color: on ? T.text2 : T.text4 }}>{label}</span>
    </span>
  );

  const Val = ({ label, value, color }) => (
    <div style={S.ctxRow}>
      <span style={S.ctxLabel}>{label}</span>
      <span style={{ ...S.ctxValue, color: color || T.text2 }}>{value ?? "\u2014"}</span>
    </div>
  );

  return (
    <div style={{ ...S.contextPanel, display: "grid", gridTemplateColumns: gridCols, gap: 12 }}>
      {/* RCCE */}
      <div>
        <div style={S.ctxTitle}>RCCE ENGINE</div>
        <Val label="Energy" value={rcce?.energy?.toFixed?.(3) ?? rcce?.energy} />
        <Val label="Vol State" value={rcce?.vol_state} color={
          rcce?.vol_state === "HIGH" ? "#f87171" : rcce?.vol_state === "LOW" ? "#34d399" : T.text2
        } />
        <Val label="Raw Signal" value={rcce?.raw_signal} color={signalColor(rcce?.raw_signal)} />
        <Val label={"β BTC"} value={rcce?.beta_btc?.toFixed?.(2) ?? rcce?.beta_btc} />
        <Val label={"β ETH"} value={rcce?.beta_eth?.toFixed?.(2) ?? rcce?.beta_eth} />
        <Val label="ATR Ratio" value={rcce?.atr_ratio?.toFixed?.(3) ?? rcce?.atr_ratio} />
        {rcce?.regime_probabilities && (
          <div style={{ marginTop: 4 }}>
            <div style={{ ...S.ctxLabel, fontSize: 9, marginBottom: 2 }}>REGIME PROBS</div>
            {Object.entries(rcce.regime_probabilities).map(([k, v]) => (
              <div key={k} style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 1 }}>
                <div style={{
                  width: `${Math.min(100, (Number(v) || 0) * 100)}%`,
                  maxWidth: 60,
                  height: 3,
                  background: regimeColor(k.toUpperCase()),
                  borderRadius: 2,
                }} />
                <span style={{ fontSize: 9, color: T.text3 }}>
                  {k} {((Number(v) || 0) * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Heatmap */}
      <div>
        <div style={S.ctxTitle}>HEATMAP</div>
        <Val label="Direction" value={
          heatmap?.heat_direction === 1 ? "\u2191 ABOVE" :
          heatmap?.heat_direction === -1 ? "\u2193 BELOW" : "\u2014"
        } color={heatmap?.heat_direction === 1 ? "#34d399" : heatmap?.heat_direction === -1 ? "#f87171" : T.text2} />
        <Val label="Phase" value={heatmap?.heat_phase} />
        <Val label="ATR Regime" value={heatmap?.atr_regime} />
        <Val label="Deviation %" value={heatmap?.deviation_pct?.toFixed?.(2) ?? heatmap?.deviation_pct} />
        <Val label="BMSB Mid" value={heatmap?.bmsb_mid ? fmtPrice(heatmap.bmsb_mid) : "\u2014"} />
        <Val label="R3" value={heatmap?.r3?.toFixed?.(3) ?? heatmap?.r3} />

        {/* Exhaustion */}
        <div style={{ ...S.ctxTitle, marginTop: 10 }}>EXHAUSTION</div>
        <Val label="Effort" value={exhaustion?.effort?.toFixed?.(3) ?? exhaustion?.effort} />
        <Val label="Rel Vol" value={exhaustion?.rel_vol?.toFixed?.(2) ?? exhaustion?.rel_vol} />
        <Val label="Dist %" value={exhaustion?.dist_pct?.toFixed?.(2) ?? exhaustion?.dist_pct} />
        <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
          <Dot on={exhaustion?.is_absorption} color="#22d3ee" label="ABSORB" />
          <Dot on={exhaustion?.is_climax} color="#fbbf24" label="CLIMAX" />
        </div>
      </div>

      {/* Synthesis + Market */}
      <div style={isMobile ? { gridColumn: "1 / -1" } : {}}>
        <div style={S.ctxTitle}>SYNTHESIS</div>
        <Val label="Confidence" value={synthesis?.signal_confidence != null ? `${synthesis.signal_confidence}%` : null} />
        <Val label="Priority" value={synthesis?.priority_score?.toFixed?.(1) ?? synthesis?.priority_score} />
        {synthesis?.confluence && (
          <Val label="Confluence" value={`${synthesis.confluence.label || ""} (${synthesis.confluence.score || 0})`} />
        )}
        {synthesis?.positioning && (
          <>
            <Val label="Funding" value={synthesis.positioning.funding_regime} />
            <Val label="OI Trend" value={synthesis.positioning.oi_trend} />
          </>
        )}
        {synthesis?.signal_warnings?.length > 0 && (
          <div style={{ marginTop: 4 }}>
            {synthesis.signal_warnings.map((w, i) => (
              <div key={i} style={{ fontSize: 9, color: "#fbbf24", padding: "1px 0" }}>
                \u26a0 {w}
              </div>
            ))}
          </div>
        )}

        <div style={{ ...S.ctxTitle, marginTop: 10 }}>MARKET</div>
        <Val label="Consensus" value={market?.consensus} />
        <Val label="Divergence" value={market?.divergence || "None"} color={
          market?.divergence === "BEAR-DIV" ? "#f87171" :
          market?.divergence === "BULL-DIV" ? "#34d399" : T.text3
        } />
        <Val label="Asset Class" value={market?.asset_class} />

        {/* Conditions checklist (compact) */}
        {synthesis?.conditions_detail?.length > 0 && (
          <div style={{ marginTop: 6 }}>
            <div style={{ ...S.ctxLabel, fontSize: 9, marginBottom: 2 }}>CONDITIONS</div>
            {synthesis.conditions_detail.map((c, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 4, padding: "1px 0" }}>
                <span style={{ color: c.met ? "#34d399" : T.text4, fontSize: 10 }}>
                  {c.met ? "\u2713" : "\u2717"}
                </span>
                <span style={{ fontSize: 9, color: c.met ? T.text2 : T.text4 }}>
                  {c.label || c.name}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Timeline view
// ---------------------------------------------------------------------------

function TimelineView({ events, total, offset, limit, onPage, isMobile }) {
  const [expanded, setExpanded] = useState(null);

  if (!events || events.length === 0) {
    return (
      <div style={S.empty}>
        No timeline events yet. Events are logged when signals or regimes change.
      </div>
    );
  }

  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  return (
    <>
      {events.map((e, i) => {
        const isSignal = e.event_type === "signal";
        const labelColor = isSignal ? signalColor(e.label) : regimeColor(e.label);
        const prevColor = isSignal
          ? (e.prev_label ? signalColor(e.prev_label) : T.text4)
          : (e.prev_label ? regimeColor(e.prev_label) : T.text4);
        const displayLabel = isSignal ? signalLabel(e.label) : (e.label || "");
        const displayPrev = isSignal
          ? (e.prev_label ? signalLabel(e.prev_label) : "NEW")
          : (e.prev_label || "NEW");
        const isExpanded = expanded === `${e.event_type}-${e.id}`;
        const stripe = i % 2 === 1 ? T.overlay02 : "transparent";

        return (
          <div key={`${e.event_type}-${e.id}`}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: isMobile ? 8 : 12,
                padding: isMobile ? "8px 6px" : "8px 12px",
                background: stripe,
                borderBottom: `1px solid ${T.overlay04}`,
                cursor: e.context ? "pointer" : "default",
                transition: "background 0.15s",
              }}
              onClick={() => e.context && setExpanded(isExpanded ? null : `${e.event_type}-${e.id}`)}
              onMouseEnter={(ev) => ev.currentTarget.style.background = T.overlay04}
              onMouseLeave={(ev) => ev.currentTarget.style.background = stripe}
            >
              {/* Event type indicator */}
              <div style={{
                width: 6, height: 6, borderRadius: "50%",
                background: isSignal ? signalColor(e.label) : regimeColor(e.label),
                boxShadow: `0 0 6px ${isSignal ? signalColor(e.label) : regimeColor(e.label)}40`,
                flexShrink: 0,
              }} />

              {/* Type badge */}
              <span style={{
                ...S.badge(
                  isSignal ? "rgba(34,211,238,0.08)" : "rgba(192,132,252,0.08)",
                  isSignal ? T.accent : "#c084fc",
                  isSignal ? "rgba(34,211,238,0.25)" : "rgba(192,132,252,0.25)",
                ),
                fontSize: 9,
                minWidth: 42,
                textAlign: "center",
              }}>
                {isSignal ? "SIG" : "REG"}
              </span>

              {/* Timestamp */}
              <span style={{ fontSize: 10, color: T.text3, minWidth: 60, flexShrink: 0 }}
                    title={fullDate(e.timestamp)}>
                {timeAgo(e.timestamp)}
              </span>

              {/* Symbol */}
              <span style={{ fontSize: 11, color: T.text1, fontWeight: 600, fontFamily: T.mono, minWidth: 48 }}>
                {stripSymbol(e.symbol)}
              </span>

              {/* Transition: prev -> new */}
              <span style={{ display: "flex", alignItems: "center", gap: 4, flex: 1, minWidth: 0 }}>
                <span style={{ color: prevColor, fontSize: 10 }}>{displayPrev}</span>
                <span style={{ color: T.text4, fontSize: 10 }}>{"\u2192"}</span>
                <span style={{
                  ...S.badge(`${labelColor}18`, labelColor, `${labelColor}40`),
                  fontSize: 10,
                }}>{displayLabel}</span>
              </span>

              {/* Transition type pill (signal events only) */}
              {isSignal && e.transition_type && !isMobile && (
                <TransitionPill type={e.transition_type} />
              )}

              {/* Price + Z */}
              {!isMobile && (
                <span style={{ fontSize: 11, color: T.text2, fontFamily: T.mono, minWidth: 80, textAlign: "right" }}>
                  {fmtPrice(e.price)}
                </span>
              )}
              {!isMobile && (
                <span style={{ fontSize: 10, color: T.text3, fontFamily: T.mono, minWidth: 40, textAlign: "right" }}>
                  {e.zscore != null ? Number(e.zscore).toFixed(2) : "\u2014"}
                </span>
              )}

              {/* Expand indicator */}
              {e.context && (
                <span style={{ fontSize: 10, color: T.text4, transition: "transform 0.2s", transform: isExpanded ? "rotate(90deg)" : "none" }}>
                  {"\u25b8"}
                </span>
              )}
            </div>

            {/* Expanded context panel */}
            {isExpanded && (
              <div style={{ padding: isMobile ? "0 6px 8px" : "0 12px 8px" }}>
                <ContextPanel contextStr={e.context} isMobile={isMobile} />
              </div>
            )}
          </div>
        );
      })}

      {totalPages > 1 && (
        <Pagination page={page} totalPages={totalPages} total={total} offset={offset} limit={limit} onPage={onPage} />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Signals history table (enhanced)
// ---------------------------------------------------------------------------

function HistoryTable({ events, total, offset, limit, onPage, isMobile }) {
  const [expanded, setExpanded] = useState(null);

  if (!events || events.length === 0) {
    return (
      <div style={S.empty}>
        No signal history yet. Events are logged when signals change between scan cycles.
      </div>
    );
  }

  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  return (
    <>
      <div style={{ overflowX: "auto" }}>
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>TIME</th>
              <th style={S.th}>SYMBOL</th>
              <th style={S.th}>SIGNAL</th>
              <th style={S.th}>PREV</th>
              {!isMobile && <th style={S.th}>TYPE</th>}
              <th style={S.th}>REGIME</th>
              <th style={S.th}>PRICE</th>
              {!isMobile && <th style={S.th}>Z</th>}
              {!isMobile && <th style={S.th}>HEAT</th>}
              <th style={{ ...S.th, textAlign: "right" }}>1D</th>
              <th style={{ ...S.th, textAlign: "right" }}>3D</th>
              <th style={{ ...S.th, textAlign: "right" }}>7D</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e, i) => {
              const sigColor = signalColor(e.signal);
              const prevColor = e.prev_signal ? signalColor(e.prev_signal) : T.text4;
              const stripe = i % 2 === 1 ? T.overlay02 : "transparent";
              const isExpanded = expanded === e.id;

              return (
                <tr key={e.id || i}
                    style={{
                      transition: "background 0.15s",
                      cursor: e.context ? "pointer" : "default",
                      background: stripe,
                    }}
                    onClick={() => e.context && setExpanded(isExpanded ? null : e.id)}
                    onMouseEnter={(ev) => ev.currentTarget.style.background = T.overlay04}
                    onMouseLeave={(ev) => ev.currentTarget.style.background = stripe}>
                  <td style={S.td} title={fullDate(e.timestamp)}>
                    {timeAgo(e.timestamp)}
                  </td>
                  <td style={{ ...S.td, color: T.text1, fontWeight: 600 }}>
                    {stripSymbol(e.symbol)}
                  </td>
                  <td style={S.td}>
                    <span style={S.badge(`${sigColor}18`, sigColor, `${sigColor}40`)}>
                      {signalLabel(e.signal)}
                    </span>
                  </td>
                  <td style={S.td}>
                    {e.prev_signal ? (
                      <span style={{ color: prevColor, fontSize: 10 }}>
                        {signalLabel(e.prev_signal)}
                      </span>
                    ) : (
                      <span style={{ color: T.text4, fontSize: 10 }}>NEW</span>
                    )}
                  </td>
                  {!isMobile && (
                    <td style={S.td}>
                      {e.transition_type ? <TransitionPill type={e.transition_type} /> : "\u2014"}
                    </td>
                  )}
                  <td style={{ ...S.td, color: regimeColor(e.regime), fontSize: 10 }}>{e.regime}</td>
                  <td style={S.td}>{fmtPrice(e.price)}</td>
                  {!isMobile && (
                    <td style={{ ...S.td, color: T.text3 }}>
                      {e.zscore != null ? Number(e.zscore).toFixed(2) : "\u2014"}
                    </td>
                  )}
                  {!isMobile && (
                    <td style={{ ...S.td, color: T.text3 }}>
                      {e.heat != null ? e.heat : "\u2014"}
                    </td>
                  )}
                  <td style={{ ...S.td, textAlign: "right", color: pctColor(e.outcome_1d_pct) }}>
                    {fmtPct(e.outcome_1d_pct)}
                  </td>
                  <td style={{ ...S.td, textAlign: "right", color: pctColor(e.outcome_3d_pct) }}>
                    {fmtPct(e.outcome_3d_pct)}
                  </td>
                  <td style={{ ...S.td, textAlign: "right", color: pctColor(e.outcome_7d_pct) }}>
                    {fmtPct(e.outcome_7d_pct)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <Pagination page={page} totalPages={totalPages} total={total} offset={offset} limit={limit} onPage={onPage} />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Regime history table
// ---------------------------------------------------------------------------

function RegimeHistoryTable({ events, total, offset, limit, onPage, isMobile }) {
  const [expanded, setExpanded] = useState(null);

  if (!events || events.length === 0) {
    return (
      <div style={S.empty}>
        No regime transitions yet. Events are logged when regimes change between scan cycles.
      </div>
    );
  }

  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit);

  return (
    <>
      <div style={{ overflowX: "auto" }}>
        <table style={S.table}>
          <thead>
            <tr>
              <th style={S.th}>TIME</th>
              <th style={S.th}>SYMBOL</th>
              <th style={S.th}>REGIME</th>
              <th style={S.th}>PREV</th>
              <th style={S.th}>PRICE</th>
              {!isMobile && <th style={S.th}>Z</th>}
              {!isMobile && <th style={S.th}>CONF</th>}
              {!isMobile && <th style={S.th}>ENERGY</th>}
              <th style={{ ...S.th, textAlign: "right" }}>DURATION</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e, i) => {
              const rColor = regimeColor(e.regime);
              const prevColor = e.prev_regime ? regimeColor(e.prev_regime) : T.text4;
              const stripe = i % 2 === 1 ? T.overlay02 : "transparent";
              const isExpanded = expanded === e.id;

              return (
                <tr key={e.id || i}
                    style={{
                      transition: "background 0.15s",
                      cursor: e.context ? "pointer" : "default",
                      background: stripe,
                    }}
                    onClick={() => e.context && setExpanded(isExpanded ? null : e.id)}
                    onMouseEnter={(ev) => ev.currentTarget.style.background = T.overlay04}
                    onMouseLeave={(ev) => ev.currentTarget.style.background = stripe}>
                  <td style={S.td} title={fullDate(e.timestamp)}>
                    {timeAgo(e.timestamp)}
                  </td>
                  <td style={{ ...S.td, color: T.text1, fontWeight: 600 }}>
                    {stripSymbol(e.symbol)}
                  </td>
                  <td style={S.td}>
                    <span style={S.badge(`${rColor}18`, rColor, `${rColor}40`)}>
                      {e.regime}
                    </span>
                  </td>
                  <td style={S.td}>
                    {e.prev_regime ? (
                      <span style={{ color: prevColor, fontSize: 10 }}>{e.prev_regime}</span>
                    ) : (
                      <span style={{ color: T.text4, fontSize: 10 }}>INITIAL</span>
                    )}
                  </td>
                  <td style={S.td}>{fmtPrice(e.price)}</td>
                  {!isMobile && (
                    <td style={{ ...S.td, color: T.text3 }}>
                      {e.zscore != null ? Number(e.zscore).toFixed(2) : "\u2014"}
                    </td>
                  )}
                  {!isMobile && (
                    <td style={{ ...S.td, color: T.text3 }}>
                      {e.confidence != null ? `${Number(e.confidence).toFixed(0)}%` : "\u2014"}
                    </td>
                  )}
                  {!isMobile && (
                    <td style={{ ...S.td, color: T.text3 }}>
                      {e.energy != null ? Number(e.energy).toFixed(3) : "\u2014"}
                    </td>
                  )}
                  <td style={{ ...S.td, textAlign: "right", color: T.text2 }}>
                    {fmtDuration(e.duration_seconds)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <Pagination page={page} totalPages={totalPages} total={total} offset={offset} limit={limit} onPage={onPage} />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Signal scorecard
// ---------------------------------------------------------------------------

function Scorecard({ cards }) {
  if (!cards || cards.length === 0) {
    return (
      <div style={S.empty}>
        No signal data yet. Signals will appear after scan cycles detect transitions.
      </div>
    );
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
            <div style={S.cardStat}>
              {c.win_rate != null ? `${c.win_rate}%` : "\u2014"}
            </div>
            <div style={S.cardLabel}>
              {c.win_rate != null ? "WIN RATE (7D)" : "PENDING"}
            </div>

            <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>COUNT</div>
                <div style={{ fontSize: 13, color: T.text2, fontWeight: 600 }}>{c.count}</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>AVG 1D</div>
                <div style={{ fontSize: 13, color: pctColor(c.avg_1d), fontWeight: 600 }}>
                  {fmtPct(c.avg_1d)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>AVG 7D</div>
                <div style={{ fontSize: 13, color: pctColor(c.avg_7d), fontWeight: 600 }}>
                  {fmtPct(c.avg_7d)}
                </div>
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
// Upgrade / downgrade scorecard
// ---------------------------------------------------------------------------

function UpgradeScorecard({ data }) {
  if (!data?.cards || data.cards.length === 0) {
    return (
      <div style={S.empty}>
        No transition data yet. Upgrade/downgrade tracking begins with the next signal changes.
      </div>
    );
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
            <div style={S.cardStat}>
              {c.win_rate != null ? `${c.win_rate}%` : "\u2014"}
            </div>
            <div style={S.cardLabel}>
              {c.win_rate != null ? "WIN RATE (7D)" : "PENDING"}
            </div>
            <div style={{ display: "flex", gap: 12, marginTop: 4 }}>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>COUNT</div>
                <div style={{ fontSize: 13, color: T.text2, fontWeight: 600 }}>{c.count}</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>AVG 1D</div>
                <div style={{ fontSize: 13, color: pctColor(c.avg_1d), fontWeight: 600 }}>
                  {fmtPct(c.avg_1d)}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: T.text4 }}>AVG 7D</div>
                <div style={{ fontSize: 13, color: pctColor(c.avg_7d), fontWeight: 600 }}>
                  {fmtPct(c.avg_7d)}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Regime duration summary
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
                <td style={{ ...S.td, textAlign: "right", color: T.text3 }}>
                  {fmtDuration(d.min_duration_seconds)}
                </td>
                <td style={{ ...S.td, textAlign: "right", color: T.text3 }}>
                  {fmtDuration(d.max_duration_seconds)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pagination
// ---------------------------------------------------------------------------

function Pagination({ page, totalPages, total, offset, limit, onPage }) {
  return (
    <div style={S.pagination}>
      <button
        style={S.pageBtn(page <= 1)}
        disabled={page <= 1}
        onClick={() => onPage(Math.max(0, offset - limit))}
      >
        &larr; PREV
      </button>
      <span style={{ fontSize: 11, color: T.text3, fontFamily: T.mono }}>
        PAGE {page} / {totalPages} &bull; {total} events
      </span>
      <button
        style={S.pageBtn(page >= totalPages)}
        disabled={page >= totalPages}
        onClick={() => onPage(offset + limit)}
      >
        NEXT &rarr;
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

const VIEWS = [
  { key: "timeline",  label: "TIMELINE" },
  { key: "signals",   label: "SIGNALS" },
  { key: "regimes",   label: "REGIMES" },
  { key: "scorecard", label: "SCORECARD" },
];

const ALL_SIGNALS = [
  "STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED",
  "TRIM", "TRIM_HARD", "RISK_OFF", "NO_LONG", "LIGHT_SHORT",
];

const ALL_REGIMES = ["MARKUP", "BLOWOFF", "REACC", "MARKDOWN", "CAP", "ACCUM", "FLAT"];

export default function SignalLogPanel({ api, isMobile }) {
  const [activeView, setActiveView] = useState("timeline");
  const [timeframe, setTimeframe] = useState("4h");
  const [symbolFilter, setSymbolFilter] = useState("");
  const [signalFilter, setSignalFilter] = useState("");
  const [regimeFilter, setRegimeFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;

  // Data state
  const [timeline, setTimeline] = useState({ events: [], total: 0 });
  const [history, setHistory] = useState({ events: [], total: 0 });
  const [regimeHistory, setRegimeHistory] = useState({ events: [], total: 0 });
  const [scorecard, setScorecard] = useState([]);
  const [upgradeScorecard, setUpgradeScorecard] = useState(null);
  const [regimeDurations, setRegimeDurations] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const sym = symbolFilter.toUpperCase() || undefined;

      if (activeView === "timeline") {
        const params = new URLSearchParams({ timeframe, limit: LIMIT, offset });
        if (sym) params.set("symbol", sym);
        const res = await fetch(`${api}/api/signals/timeline?${params}`).then(r => r.json());
        setTimeline({ events: res.events || [], total: res.total || 0 });
      }

      if (activeView === "signals") {
        const params = new URLSearchParams({ timeframe, limit: LIMIT, offset });
        if (signalFilter) params.set("signal", signalFilter);
        if (sym) params.set("symbol", sym);
        const res = await fetch(`${api}/api/signals/history?${params}`).then(r => r.json());
        setHistory({ events: res.events || [], total: res.total || 0 });
      }

      if (activeView === "regimes") {
        const params = new URLSearchParams({ timeframe, limit: LIMIT, offset });
        if (regimeFilter) params.set("regime", regimeFilter);
        if (sym) params.set("symbol", sym);
        const res = await fetch(`${api}/api/signals/regime-history?${params}`).then(r => r.json());
        setRegimeHistory({ events: res.events || [], total: res.total || 0 });
      }

      if (activeView === "scorecard") {
        const [scRes, upRes, durRes] = await Promise.all([
          fetch(`${api}/api/signals/scorecard?timeframe=${timeframe}`).then(r => r.json()),
          fetch(`${api}/api/signals/upgrade-scorecard?timeframe=${timeframe}`).then(r => r.json()),
          fetch(`${api}/api/signals/regime-durations?timeframe=${timeframe}${sym ? `&symbol=${sym}` : ""}`).then(r => r.json()),
        ]);
        setScorecard(scRes.cards || []);
        setUpgradeScorecard(upRes);
        setRegimeDurations(durRes.durations || []);
      }
    } catch (err) {
      console.error("Signal log fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, [api, activeView, timeframe, signalFilter, regimeFilter, symbolFilter, offset]);

  useEffect(() => {
    setLoading(true);
    fetchData();
    const iv = setInterval(fetchData, 60_000);
    return () => clearInterval(iv);
  }, [fetchData]);

  // Reset offset when filters or view change
  useEffect(() => {
    setOffset(0);
  }, [activeView, timeframe, signalFilter, regimeFilter, symbolFilter]);

  return (
    <div style={S.panel}>
      <div style={S.section}>
        {/* Header: title + timeframe toggle */}
        <div style={S.header}>
          <div style={S.sectionTitle}>SIGNAL LOG</div>
          <div style={{ display: "flex", gap: 6 }}>
            {["4h", "1d"].map(tf => (
              <button key={tf} onClick={() => setTimeframe(tf)} style={S.pillBtn(timeframe === tf)}>
                {tf.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        {/* View tabs */}
        <div style={{ display: "flex", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
          {VIEWS.map(v => (
            <button key={v.key} onClick={() => setActiveView(v.key)} style={S.viewTab(activeView === v.key)}>
              {v.label}
            </button>
          ))}
        </div>

        {/* Filter bar */}
        <div style={S.filterBar}>
          <input
            style={S.input}
            type="text"
            placeholder="SYMBOL..."
            value={symbolFilter}
            onChange={e => setSymbolFilter(e.target.value)}
          />
          {activeView === "signals" && (
            <select style={S.select} value={signalFilter} onChange={e => setSignalFilter(e.target.value)}>
              <option value="">ALL SIGNALS</option>
              {ALL_SIGNALS.map(s => (
                <option key={s} value={s}>{signalLabel(s)}</option>
              ))}
            </select>
          )}
          {activeView === "regimes" && (
            <select style={S.select} value={regimeFilter} onChange={e => setRegimeFilter(e.target.value)}>
              <option value="">ALL REGIMES</option>
              {ALL_REGIMES.map(r => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          )}
          <span style={{ fontSize: 10, color: T.text4, fontFamily: T.mono }}>
            {activeView === "timeline" ? timeline.total :
             activeView === "signals" ? history.total :
             activeView === "regimes" ? regimeHistory.total :
             scorecard.length} events
          </span>
        </div>

        {/* Content by active view */}
        {loading && activeView === "timeline" && timeline.events.length === 0 ? (
          <div style={S.empty}>Loading timeline...</div>
        ) : activeView === "timeline" ? (
          <TimelineView
            events={timeline.events} total={timeline.total}
            offset={offset} limit={LIMIT} onPage={setOffset} isMobile={isMobile}
          />
        ) : null}

        {loading && activeView === "signals" && history.events.length === 0 ? (
          <div style={S.empty}>Loading signals...</div>
        ) : activeView === "signals" ? (
          <HistoryTable
            events={history.events} total={history.total}
            offset={offset} limit={LIMIT} onPage={setOffset} isMobile={isMobile}
          />
        ) : null}

        {loading && activeView === "regimes" && regimeHistory.events.length === 0 ? (
          <div style={S.empty}>Loading regimes...</div>
        ) : activeView === "regimes" ? (
          <RegimeHistoryTable
            events={regimeHistory.events} total={regimeHistory.total}
            offset={offset} limit={LIMIT} onPage={setOffset} isMobile={isMobile}
          />
        ) : null}

        {activeView === "scorecard" && (
          <>
            <div style={{ ...S.sectionTitle, marginTop: 0 }}>SIGNAL PERFORMANCE</div>
            {loading && scorecard.length === 0 ? (
              <div style={S.empty}>Loading scorecard...</div>
            ) : (
              <Scorecard cards={scorecard} />
            )}

            <div style={{ ...S.sectionTitle, marginTop: 24 }}>TRANSITION PERFORMANCE</div>
            <UpgradeScorecard data={upgradeScorecard} />

            {regimeDurations.length > 0 && (
              <>
                <div style={{ ...S.sectionTitle, marginTop: 24 }}>REGIME DURATIONS</div>
                <RegimeDurations durations={regimeDurations} />
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
