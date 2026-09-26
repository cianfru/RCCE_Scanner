import Tabs from "./Tabs.jsx";
import { useState, useEffect, useMemo } from "react";
import { T, SIGNAL_META, REGIME_META, TRANSITION_META, col } from "../theme.js";

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
function fmtUsd(v) {
  if (!v && v !== 0) return "—";
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

const SIGNAL_SHORT = {
  // Heatmap cells are narrow; these are the first word of the grid's labels.
  STRONG_LONG: "STRONG", LIGHT_LONG: "LIGHT", ACCUMULATE: "ACCUM",
  REVIVAL_SEED: "REVIVE", REVIVAL_SEED_CONFIRMED: "REVIVE",
  WAIT: "", TRIM: "TRIM", TRIM_HARD: "TRIM!", RISK_OFF: "RISK", NO_LONG: "NO",
  LIGHT_SHORT: "SHORT", STRONG_SHORT: "SHORT!",
};

// "7/9" -> "7 of 9 entry checks met"; the totals differ between coins (9 or 11).
function checksText(cond) {
  const m = /^(\d+)\/(\d+)$/.exec(cond || "");
  return m ? `${m[1]} of ${m[2]} entry checks met` : "";
}

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
    fontSize: T.textXs, fontWeight: 700, color: T.text3,
    letterSpacing: "0.1em", textTransform: "uppercase",
    marginBottom: 16, fontFamily: T.mono,
  },
  table: { width: "100%", borderCollapse: "collapse", fontSize: 12, fontFamily: T.mono },
  th: {
    textAlign: "left", padding: "8px 10px",
    borderBottom: `1px solid ${T.border}`, color: T.text3,
    fontSize: T.textXs, fontWeight: 600, letterSpacing: "0.08em",
    textTransform: "uppercase", whiteSpace: "nowrap",
  },
  td: {
    padding: "7px 10px", borderBottom: `1px solid ${T.overlay04}`,
    color: T.text2, whiteSpace: "nowrap", fontSize: T.textXs,
  },
  subtitle: { color: T.text4, fontWeight: 500, marginLeft: 8, fontSize: T.textXs, letterSpacing: "0.02em", textTransform: "none" },
  empty: {
    textAlign: "center", padding: "40px 20px",
    color: T.text4, fontSize: 13, fontFamily: T.mono,
  },
};

// Flat coloured text, as the scanner's status labels.
function Badge({ color, children }) {
  return <span style={{ fontSize: T.textXs, fontWeight: 700, color }}>{children}</span>;
}

// A failed request is not an empty history: say so and offer a retry.
function LoadError({ onRetry }) {
  return (
    <div style={S.empty}>
      Could not load.{" "}
      <button type="button" onClick={onRetry} style={{ background: "transparent", border: 0, borderBottom: `1px solid ${T.accent}`, padding: 0, color: T.accent, fontSize: 13, fontFamily: T.mono, cursor: "pointer" }}>Retry</button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scoring for heatmap sort
// ---------------------------------------------------------------------------

function scoreBullishHistory(row) {
  if (!row || row.length === 0) return 0;
  let score = 0;
  const len = row.length;
  row.forEach((cell, i) => {
    const sig = cell?.signal || "WAIT";
    const recency = 0.3 + 0.7 * (i / Math.max(len - 1, 1));
    if (sig === "STRONG_LONG") score += 3 * recency;
    else if (sig === "LIGHT_LONG") score += 2 * recency;
    else if (BULL_SIGNALS.has(sig)) score += 1.5 * recency;
    else if (EXIT_SIGNALS.has(sig)) score -= 1 * recency;
  });
  return score;
}

// ---------------------------------------------------------------------------
// 1. HEATMAP — sorted by best historical performers
// ---------------------------------------------------------------------------

function SignalHeatmap({ data, isMobile, sortMode }) {
  const sortedSymbols = useMemo(() => {
    if (!data || !data.grid) return [];
    const syms = [...(data.symbols || Object.keys(data.grid))];
    if (sortMode === "bullish") syms.sort((a, b) => scoreBullishHistory(data.grid[b]) - scoreBullishHistory(data.grid[a]));
    else if (sortMode === "bearish") syms.sort((a, b) => scoreBullishHistory(data.grid[a]) - scoreBullishHistory(data.grid[b]));
    return syms;
  }, [data, sortMode]);

  if (!data || !data.grid || sortedSymbols.length === 0) {
    return <div style={S.empty}>No signal history yet.</div>;
  }

  // Cells fit a six-letter label at 12px; narrow screens scroll sideways.
  const cellMinSize = 46;
  const labelW = isMobile ? 60 : 76;
  // Size the table from its columns so narrow screens scroll instead of squeezing cells
  const colW = cellMinSize + 2;
  const tableW = labelW + 12 + data.days.length * colW;

  return (
    // Bounded height so the day header stays in view (sticky) down all rows.
    <div style={{ overflow: "auto", maxHeight: "70vh", WebkitOverflowScrolling: "touch" }} className="notable-scroll">
      <table style={{ borderCollapse: "collapse", fontFamily: T.mono, fontSize: T.textXs, width: tableW, minWidth: "100%", tableLayout: "fixed" }}>
        <thead>
          <tr>
            <th style={{ position: "sticky", left: 0, top: 0, zIndex: 4, background: T.selectBg, padding: "4px 6px", width: labelW, minWidth: labelW, fontSize: T.textXs, color: T.text4, textAlign: "left", borderBottom: `1px solid ${T.border}` }}></th>
            {data.days.map((day, i) => (
              <th key={i} style={{ position: "sticky", top: 0, zIndex: 3, background: T.selectBg, boxSizing: "border-box", width: colW, padding: "4px 0", textAlign: "center", fontSize: T.textXs, color: T.text4, fontWeight: 600, letterSpacing: "0.04em", borderBottom: `1px solid ${T.border}`, whiteSpace: "nowrap" }}>{day}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedSymbols.map((sym, rowIdx) => {
            const row = data.grid[sym];
            if (!row) return null;
            return (
              <tr key={sym} style={{ background: rowIdx % 2 === 1 ? T.overlay02 : "transparent" }}>
                <td style={{ position: "sticky", left: 0, zIndex: 1, background: rowIdx % 2 === 1 ? `linear-gradient(${T.overlay02}, ${T.overlay02}), ${T.selectBg}` : T.selectBg, padding: "2px 6px", fontSize: T.textXs, color: T.text2, fontWeight: 600, borderBottom: `1px solid ${T.overlay04}`, width: labelW, minWidth: labelW }}>{stripSymbol(sym)}</td>
                {row.map((cell, colIdx) => {
                  const signal = cell?.signal || "WAIT";
                  const checks = checksText(cell?.cond);
                  const meta = SIGNAL_META[signal] || SIGNAL_META.WAIT;
                  const color = meta.color;
                  const shortLabel = SIGNAL_SHORT[signal] ?? signal.split("_")[0].slice(0, 6);
                  const isWait = signal === "WAIT";
                  // The checks count lives in the tooltip: on a WAIT cell "9/9" read as full conviction.
                  const tooltip = `${stripSymbol(sym)} \u2014 ${data.days[colIdx]}: ${signalLabel(signal)}${checks ? ` \u00b7 ${checks}` : ""}`;
                  return (
                    <td key={colIdx} title={tooltip} style={{ padding: 1, borderBottom: `1px solid ${T.overlay04}` }}>
                      <div style={{ minWidth: cellMinSize, height: cellMinSize, borderRadius: 4, background: isWait ? T.overlay04 : `${color}20`, border: `1px solid ${isWait ? "transparent" : `${color}35`}`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", cursor: "default" }}>
                        {!isWait && shortLabel && <span style={{ fontSize: T.textXs, fontWeight: 700, color, lineHeight: 1 }}>{shortLabel}</span>}
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
// 2. DIVERGENCE — scanner signal vs tracked-wallet consensus disagree
// ---------------------------------------------------------------------------

// A stated rule instead of a strength cutoff no coin reached: the consensus
// leans against the scanner and at least this many tracked wallets hold the coin.
const MIN_POSITIONED_WALLETS = 10;

function DivergenceView({ data, isMobile }) {
  const divergences = useMemo(() => {
    if (!data || data.length === 0) return [];
    return data
      .filter(p => {
        const sm = p.smart_money;
        if (!sm || (sm.long_count || 0) + (sm.short_count || 0) < MIN_POSITIONED_WALLETS) return false;
        const sig = p.signal;
        // Bull signal + bearish tracked wallets
        if (BULL_SIGNALS.has(sig) && sm.trend === "BEARISH") return true;
        // Exit or waiting signal + bullish tracked wallets
        if ((EXIT_SIGNALS.has(sig) || sig === "WAIT") && sm.trend === "BULLISH") return true;
        return false;
      })
      .sort((a, b) => (b.smart_money?.confidence || 0) - (a.smart_money?.confidence || 0));
  }, [data]);

  if (divergences.length === 0) {
    return <div style={S.empty}>No coin where tracked wallets clearly oppose the scanner signal right now.</div>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={S.table}>
        <thead>
          <tr>
            <th style={S.th}>SYMBOL</th>
            <th style={S.th}>SCANNER</th>
            <th style={{ ...S.th, textAlign: "center" }}>VS</th>
            <th style={S.th}>TRACKED WALLETS</th>
            {!isMobile && <th style={{ ...S.th, textAlign: "right" }}>L / S</th>}
            {!isMobile && <th style={{ ...S.th, textAlign: "right" }}>NOTIONAL</th>}
            <th style={{ ...S.th, textAlign: "right" }} title="Consensus strength, 0 to 100: a heuristic blend of position value and wallet count, not a probability">STRENGTH</th>
          </tr>
        </thead>
        <tbody>
          {divergences.map((p, i) => {
            const sigColor = signalColor(p.signal);
            const sm = p.smart_money;
            const walletColor = sm.trend === "BULLISH" ? col("#34d399") : sm.trend === "BEARISH" ? col("#f87171") : T.text3;
            const bullSignalBearWallets = BULL_SIGNALS.has(p.signal) && sm.trend === "BEARISH";

            return (
              <tr key={p.symbol} style={{
                background: i % 2 === 1 ? T.overlay02 : "transparent",
                borderLeft: `3px solid ${bullSignalBearWallets ? col("#f87171") : col("#fbbf24")}`,
              }}>
                <td style={{ ...S.td, fontWeight: 700, fontSize: 12 }}>{stripSymbol(p.symbol)}</td>
                <td style={S.td}>
                  <Badge color={sigColor}>
                    {signalLabel(p.signal)}
                  </Badge>
                </td>
                <td style={{ ...S.td, textAlign: "center", color: T.text4 }}>against</td>
                <td style={S.td}>
                  <Badge color={walletColor}>
                    {sm.trend}
                  </Badge>
                </td>
                {!isMobile && (
                  <td style={{ ...S.td, textAlign: "right" }}>
                    <span style={{ color: col("#34d399") }}>{sm.long_count}</span>
                    <span style={{ color: T.text4 }}> / </span>
                    <span style={{ color: col("#f87171") }}>{sm.short_count}</span>
                  </td>
                )}
                {!isMobile && (
                  <td style={{ ...S.td, textAlign: "right", color: T.text3 }}>
                    <span style={{ color: col("#34d399") }}>{fmtUsd(sm.long_notional)}</span>
                    <span style={{ color: T.text4 }}> / </span>
                    <span style={{ color: col("#f87171") }}>{fmtUsd(sm.short_notional)}</span>
                  </td>
                )}
                <td style={{ ...S.td, textAlign: "right", fontWeight: 600, color: walletColor }}>
                  {Math.round(sm.confidence * 100)}
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
// 3. TRANSITIONS — recent signal + regime changes
// ---------------------------------------------------------------------------

function TransitionsView({ events, isMobile }) {
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
              <tr key={`${ev.symbol}-${ev.timestamp}-${i}`} style={{ background: i % 2 === 1 ? T.overlay02 : "transparent" }}>
                <td style={{ ...S.td, color: T.text3 }}>{ago}</td>
                <td style={{ ...S.td, fontWeight: 700, fontSize: 12 }}>{stripSymbol(ev.symbol)}</td>
                <td style={{ ...S.td, color: prevColor }}>{ev.prev_signal ? signalLabel(ev.prev_signal) : "\u2014"}</td>
                <td style={{ ...S.td, color: tt.color, fontSize: 12, textAlign: "center", padding: "7px 4px" }}>{tt.glyph}</td>
                <td style={{ ...S.td, color: sigColor, fontWeight: 600 }}>{signalLabel(ev.signal)}</td>
                <td style={S.td}>
                  <Badge color={tt.color}>{tt.label}</Badge>
                </td>
                {!isMobile && <td style={{ ...S.td, color: T.text3 }}>{ev.regime ? (REGIME_META[ev.regime]?.name || ev.regime) : "\u2014"}</td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 4. STREAKS — longest consecutive signal runs
// ---------------------------------------------------------------------------

function StreaksView({ data, isMobile }) {
  const streaks = useMemo(() => {
    if (!data || !data.grid) return [];
    const result = [];

    for (const sym of (data.symbols || Object.keys(data.grid))) {
      const row = data.grid[sym];
      if (!row || row.length === 0) continue;

      // Walk from end (most recent) backwards to find current streak
      let streakSig = null;
      let streakLen = 0;
      for (let i = row.length - 1; i >= 0; i--) {
        const sig = row[i]?.signal || "WAIT";
        if (streakSig === null) {
          streakSig = sig;
          streakLen = 1;
        } else if (sig === streakSig) {
          streakLen++;
        } else {
          break;
        }
      }

      if (streakSig && streakSig !== "WAIT" && streakLen >= 2) {
        const isBull = BULL_SIGNALS.has(streakSig);
        result.push({ symbol: sym, signal: streakSig, days: streakLen, isBull });
      }
    }

    return result.sort((a, b) => b.days - a.days);
  }, [data]);

  if (streaks.length === 0) {
    return <div style={S.empty}>No active streaks (2+ consecutive days on same signal).</div>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={S.table}>
        <thead>
          <tr>
            <th style={S.th}>SYMBOL</th>
            <th style={S.th}>SIGNAL</th>
            <th style={{ ...S.th, textAlign: "center" }}>STREAK</th>
            <th style={S.th}>TYPE</th>
          </tr>
        </thead>
        <tbody>
          {streaks.map((s, i) => {
            const sigColor = signalColor(s.signal);
            return (
              <tr key={s.symbol} style={{ background: i % 2 === 1 ? T.overlay02 : "transparent" }}>
                <td style={{ ...S.td, fontWeight: 700, fontSize: 12 }}>{stripSymbol(s.symbol)}</td>
                <td style={S.td}>
                  <Badge color={sigColor}>
                    {signalLabel(s.signal)}
                  </Badge>
                </td>
                <td style={{ ...S.td, textAlign: "center" }}>
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    fontSize: 14, fontWeight: 700,
                    color: s.isBull ? col("#34d399") : col("#f87171"),
                  }}>
                    {s.days}
                    <span style={{ fontSize: T.textXs, fontWeight: 500, color: T.text4 }}>days</span>
                  </span>
                </td>
                <td style={{ ...S.td, color: s.isBull ? col("#34d399") : col("#f87171"), fontWeight: 600 }}>
                  {s.isBull ? "\u2191 BULL" : "\u2193 EXIT"}
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
// Main Panel
// ---------------------------------------------------------------------------

export default function SignalLogPanel({ api, isMobile, scanData4h, scanData1d }) {
  const [activeView, setActiveView] = useState("heatmap");
  const [timeframe, setTimeframe] = useState("4h");
  const [heatmap, setHeatmap] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sortMode, setSortMode] = useState("bullish");
  const [transitions, setTransitions] = useState([]);
  const [heatmapError, setHeatmapError] = useState(false);
  const [transitionsError, setTransitionsError] = useState(false);
  const [reload, setReload] = useState(0);
  const retry = () => setReload(n => n + 1);

  const scanData = timeframe === "4h" ? scanData4h : scanData1d;
  const presentSignals = useMemo(() => {
    const seen = new Set();
    for (const row of Object.values(heatmap?.grid || {})) for (const cell of row || []) if (cell?.signal) seen.add(cell.signal);
    return seen;
  }, [heatmap]);

  // A late response for the previous timeframe must not overwrite the current one.
  const needsHeatmap = activeView === "heatmap" || activeView === "streaks";
  useEffect(() => {
    if (!needsHeatmap) return;
    let cancelled = false;
    setLoading(true);
    setHeatmapError(false);
    fetch(`${api}/api/signals/heatmap?timeframe=${timeframe}&days=14&limit=100`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { if (!cancelled) setHeatmap(d); })
      .catch(e => { if (!cancelled) { console.error("SignalLogPanel fetch error:", e); setHeatmap(null); setHeatmapError(true); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [needsHeatmap, api, timeframe, reload]);

  useEffect(() => {
    if (activeView !== "transitions") return;
    let cancelled = false;
    setTransitionsError(false);
    fetch(`${api}/api/signals/recent?timeframe=${timeframe}&limit=50`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { if (!cancelled) setTransitions(d.changes || []); })
      .catch(() => { if (!cancelled) { setTransitions([]); setTransitionsError(true); } });
    return () => { cancelled = true; };
  }, [activeView, timeframe, api, reload]);

  const VIEWS = [
    { key: "heatmap", label: "Heatmap" },
    { key: "divergence", label: "Divergence" },
    { key: "transitions", label: "Transitions" },
    { key: "streaks", label: "Streaks" },
  ];

  const SORTS = [
    { key: "bullish", label: "Most bullish" },
    // The 14-day grid holds long and exit signals only: this reverses the bullish score.
    { key: "bearish", label: "Least bullish" },
    { key: "default", label: "Priority" },
  ];

  return (
    <div style={{ padding: 0 }}>
      {/* Header */}
      <div style={{
        display: "flex", justifyContent: "space-between",
        alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 8,
      }}>
        <Tabs label="Signal log view" items={VIEWS} value={activeView} onChange={setActiveView} />
        <div style={{ display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap", width: isMobile ? "100%" : undefined }}>
          {activeView === "heatmap" && <Tabs small label="Sort" items={SORTS} value={sortMode} onChange={setSortMode} />}
          {activeView === "heatmap" && <span style={{ width: 1, alignSelf: "stretch", background: T.border, margin: "0 4px" }} />}
          <Tabs label="Timeframe" items={[{ key: "4h", label: "4H" }, { key: "1d", label: "1D" }]} value={timeframe} onChange={setTimeframe} />
        </div>
      </div>

      {/* HEATMAP */}
      {activeView === "heatmap" && (
        <>
          {loading && <div style={S.empty}>Loading...</div>}
          {!loading && (
            <div style={S.section}>
              <div style={S.sectionTitle}>
                Signal Evolution — 14 Days
                <span style={S.subtitle}>
                  {heatmap?.symbols?.length || 0} pairs
                </span>
              </div>
              <p style={{ margin: "-8px 0 12px", fontSize: T.textXs, color: T.text3 }}>Cells show the signal; hover a cell for the entry checks met.</p>
              {heatmapError ? <LoadError onRetry={retry} /> : <SignalHeatmap data={heatmap} isMobile={isMobile} sortMode={sortMode} />}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14, paddingTop: 12, borderTop: `1px solid ${T.overlay04}` }}>
                {/* Only signals that appear in the grid */}
                {Object.entries(SIGNAL_META).filter(([key]) => presentSignals.has(key)).map(([key, meta]) => {
                  return (
                    <div key={key} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: T.textXs, fontFamily: T.mono, color: T.text3 }}>
                      <div style={{ width: 10, height: 10, borderRadius: 2, background: key === "WAIT" ? T.overlay04 : `${meta.color}30`, border: `1px solid ${key === "WAIT" ? T.border : `${meta.color}50`}` }} />
                      {meta.label}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}

      {/* DIVERGENCE */}
      {activeView === "divergence" && (
        <div style={S.section}>
          <div style={S.sectionTitle}>
            Scanner vs tracked wallets
            <span style={S.subtitle}>
              coins where the tracked-wallet consensus (profitable traders and large accounts) leans against the scanner, with at least {MIN_POSITIONED_WALLETS} wallets positioned
            </span>
          </div>
          <DivergenceView data={scanData} isMobile={isMobile} />
        </div>
      )}

      {/* TRANSITIONS */}
      {activeView === "transitions" && (
        <div style={S.section}>
          <div style={S.sectionTitle}>
            Recent Signal Changes
            <span style={S.subtitle}>
              last 50
            </span>
          </div>
          {transitionsError ? <LoadError onRetry={retry} /> : <TransitionsView events={transitions} isMobile={isMobile} />}
        </div>
      )}

      {/* STREAKS */}
      {activeView === "streaks" && (
        <>
          {loading && <div style={S.empty}>Loading...</div>}
          {!loading && (
            <div style={S.section}>
              <div style={S.sectionTitle}>
                Signal Persistence
                <span style={S.subtitle}>
                  consecutive days on same signal
                </span>
              </div>
              {heatmapError ? <LoadError onRetry={retry} /> : <StreaksView data={heatmap} isMobile={isMobile} />}
            </div>
          )}
        </>
      )}
    </div>
  );
}
