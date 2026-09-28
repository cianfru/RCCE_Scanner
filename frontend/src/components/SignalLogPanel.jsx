import Tabs from "./Tabs.jsx";
import TokenLogo from "./TokenLogo.jsx";
import { useState, useEffect, useLayoutEffect, useMemo, useRef } from "react";
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
  // Heatmap cells are narrow; these are the first word of the grid's labels (sentence case fits 12px bold).
  STRONG_LONG: "Strong", LIGHT_LONG: "Light", ACCUMULATE: "Accum",
  REVIVAL_SEED: "Revive", REVIVAL_SEED_CONFIRMED: "Revive",
  WAIT: "", TRIM: "Trim", TRIM_HARD: "Trim!", RISK_OFF: "Risk", NO_LONG: "No",
  LIGHT_SHORT: "Short", STRONG_SHORT: "Short!",
};

// "7/9" -> "7 of 9 entry checks met"; the totals differ between coins (9 or 11).
// Short (phone readout): "7/9 checks".
function checksText(cond, suffix = " met", short = false) {
  const m = /^(\d+)\/(\d+)$/.exec(cond || "");
  if (!m) return "";
  return short ? `${m[1]}/${m[2]} checks` : `${m[1]} of ${m[2]} entry checks${suffix}`;
}
// A WAIT cell: a full count would read as conviction, so it says the signal was held back anyway.
function waitChecks(cond, short = false) {
  const m = /^(\d+)\/(\d+)$/.exec(cond || "");
  if (!m) return "";
  if (m[1] === m[2]) return short ? "all met, held back" : "all checks met, held back";
  return short ? `${m[1]}/${m[2]} checks` : `${m[1]} of ${m[2]} checks`;
}
// "Sep 24" -> "24 Sep" for the readout line.
function dayText(day) {
  const m = /^([A-Za-z]{3}) (\d{1,2})$/.exec(String(day || ""));
  return m ? `${m[2]} ${m[1]}` : String(day || "");
}
// "LIGHT LONG" -> "Light long"
function sentenceLabel(sig) {
  const l = String(signalLabel(sig) || "").toLowerCase();
  return l ? l[0].toUpperCase() + l.slice(1) : "";
}

// Ticker with its logo, as in the scanner grid. The box is one fixed 16px text line whatever the
// logo (artwork, or an empty ring for a coin with none: initials would only repeat the ticker), so
// every row keeps today's 31/33px height and the ticker sits on the row's text line.
// Tables: 16px logo, 14px on phone. The heatmap (56px rows) takes an 18px logo, and on phone
// stacks a 14px logo above the ticker so its label column stays as narrow as before.
const SYM_LINE = 16;
function Sym({ symbol, compact = false, size, stack = false }) {
  const logo = size || (compact ? 14 : 16);
  if (stack) {
    return (
      <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 3, minWidth: 0 }}>
        <TokenLogo symbol={symbol} size={logo} fallback="ring" />
        <span style={{ maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", lineHeight: `${SYM_LINE}px` }}>{stripSymbol(symbol)}</span>
      </span>
    );
  }
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: compact ? 4 : 6, height: Math.max(SYM_LINE, logo), lineHeight: `${SYM_LINE}px`, verticalAlign: "top", minWidth: 0, maxWidth: "100%" }}>
      <TokenLogo symbol={symbol} size={logo} fallback="ring" />
      <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{stripSymbol(symbol)}</span>
    </span>
  );
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
  // Phone: 6px side padding instead of 10, which pays for the logo in the symbol column.
  thPhone: { padding: "8px 6px" },
  tdPhone: { padding: "7px 6px" },
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

function SignalHeatmap({ data, isMobile, sortMode, picked, onPick }) {
  // Open on the newest days: narrow screens scroll back through the history instead of forward to today.
  const scrollRef = useRef(null);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [data, isMobile]);
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
  const cellMinSize = 52;
  // Desktop: logo (18) + gap + a seven-letter ticker. Phone: today's 60px, the logo stacked above the ticker.
  const labelW = isMobile ? 60 : 100;
  // Size the table from its columns so narrow screens scroll instead of squeezing cells
  const colW = cellMinSize + 2;
  const tableW = labelW + 12 + data.days.length * colW;

  return (
    // Bounded height so the day header stays in view (sticky) down all rows.
    <div ref={scrollRef} style={{ overflow: "auto", maxHeight: "70vh", WebkitOverflowScrolling: "touch" }} className="notable-scroll">
      <table style={{ borderCollapse: "collapse", fontFamily: T.mono, fontSize: T.textXs, width: tableW, minWidth: "100%", tableLayout: "fixed" }}>
        <thead>
          <tr>
            <th style={{ position: "sticky", left: 0, top: 0, zIndex: 4, background: T.selectBg, padding: "4px 6px", width: labelW, minWidth: labelW, fontSize: T.textXs, color: T.text4, textAlign: "left", borderBottom: `1px solid ${T.border}` }}></th>
            {data.days.map((day, i) => (
              <th key={i} style={{ position: "sticky", top: 0, zIndex: 3, background: T.selectBg, boxSizing: "border-box", width: colW, padding: "4px 0", textAlign: "center", fontSize: T.textXs, color: T.text4, fontWeight: 600, lineHeight: 1.25, borderBottom: `1px solid ${T.border}`, whiteSpace: "nowrap" }}>{String(day).split(" ").map((part, j) => <span key={j} style={{ display: "block" }}>{part}</span>)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedSymbols.map((sym, rowIdx) => {
            const row = data.grid[sym];
            if (!row) return null;
            return (
              <tr key={sym} style={{ background: rowIdx % 2 === 1 ? T.overlay02 : "transparent" }}>
                <td className="heat-sym" style={{ position: "sticky", left: 0, zIndex: 1, background: rowIdx % 2 === 1 ? `linear-gradient(${T.overlay02}, ${T.overlay02}), ${T.selectBg}` : T.selectBg, padding: "2px 6px", fontSize: T.textXs, color: T.text2, fontWeight: 600, borderBottom: `1px solid ${T.overlay04}`, width: labelW, minWidth: labelW, maxWidth: labelW, whiteSpace: "nowrap", overflow: "hidden" }}>{isMobile ? <Sym symbol={sym} size={14} stack /> : <Sym symbol={sym} size={18} />}</td>
                {row.map((cell, colIdx) => {
                  const signal = cell?.signal || "WAIT";
                  const checks = checksText(cell?.cond);
                  const meta = SIGNAL_META[signal] || SIGNAL_META.WAIT;
                  const color = meta.color;
                  const shortLabel = SIGNAL_SHORT[signal] ?? signal.split("_")[0].slice(0, 6);
                  const isWait = signal === "WAIT";
                  // The checks count lives in the tooltip: on a WAIT cell "9/9" read as full conviction.
                  const tooltip = `${stripSymbol(sym)} \u2014 ${data.days[colIdx]}: ${signalLabel(signal)}${checks ? ` \u00b7 ${checks}` : ""}`;
                  const isPicked = picked?.sym === sym && picked?.idx === colIdx;
                  // A button, so touch screens (no hover) can read the entry checks in the readout line.
                  return (
                    <td key={colIdx} title={tooltip} style={{ padding: 1, borderBottom: `1px solid ${T.overlay04}` }}>
                      <button type="button" className="heat-cell" aria-label={tooltip} aria-pressed={isPicked}
                        onClick={() => onPick(isPicked ? null : { sym, idx: colIdx })}
                        style={{ width: "100%", minWidth: cellMinSize, height: cellMinSize, padding: 0, font: "inherit", borderRadius: 4, background: isWait ? T.overlay04 : `${color}20`, border: `1px solid ${isWait ? "transparent" : `${color}35`}`, boxShadow: isPicked ? `inset 0 0 0 1.5px ${isWait ? T.text3 : color}` : "none", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>
                        {!isWait && shortLabel && <span style={{ fontSize: T.textXs, fontWeight: 700, color, lineHeight: 1, letterSpacing: "-0.02em" }}>{shortLabel}</span>}
                      </button>
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

// One line above the heatmap: the hint until a cell is picked, then that cell
// ("BTC · 24 Sep · Light long · 8 of 9 entry checks"; phone "8/9 checks"). Both keep one line's
// height, so picking a cell never moves the grid. The checks never shrink: on a narrow screen
// the ticker, day and signal part gives way first (the cell itself shows the signal).
const READOUT_LINE = { margin: "-8px 0 12px", height: 18, lineHeight: "18px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" };
const READOUT_PART = { minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" };
function HeatmapReadout({ data, picked, isMobile }) {
  const row = picked && data?.grid?.[picked.sym];
  if (!row) {
    return <p style={{ ...READOUT_LINE, fontSize: T.textXs, color: T.text3 }}>
      {isMobile ? "Tap a cell for its entry checks." : "Cells show the signal; hover or click a cell for the entry checks met."}
    </p>;
  }
  const cell = row[picked.idx];
  const signal = cell?.signal || "WAIT";
  const checks = signal === "WAIT" ? waitChecks(cell?.cond, isMobile) : checksText(cell?.cond, "", isMobile);
  const dot = <span style={{ color: T.text4 }}>{" \u00b7 "}</span>;
  return (
    <p role="status" style={{ ...READOUT_LINE, display: "flex", fontSize: 13, color: T.text2 }}>
      <span style={READOUT_PART}>
        {!isMobile && <span style={{ marginRight: 6, verticalAlign: "-3px", display: "inline-flex" }}><TokenLogo symbol={picked.sym} size={16} fallback="none" /></span>}
        <b style={{ fontWeight: 600, color: T.text1 }}>{stripSymbol(picked.sym)}</b>
        {dot}{dayText(data.days?.[picked.idx])}
        {dot}<span style={{ color: signal === "WAIT" ? T.text3 : signalColor(signal), fontWeight: 600 }}>{sentenceLabel(signal)}</span>
      </span>
      {checks && <span style={{ flexShrink: 0, whiteSpace: "pre" }}>{dot}{checks}</span>}
    </p>
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
  const th = isMobile ? { ...S.th, ...S.thPhone } : S.th;
  const td = isMobile ? { ...S.td, ...S.tdPhone } : S.td;

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={S.table}>
        <thead>
          <tr>
            <th style={th}>SYMBOL</th>
            <th style={th}>SCANNER</th>
            <th style={{ ...th, textAlign: "center" }}>VS</th>
            {/* Phone: the consensus strength sits beside the trend, so all columns fit without a sideways scroll. */}
            <th style={th} title={isMobile ? "Tracked-wallet consensus and its strength, 0 to 100: a heuristic blend of position value and wallet count, not a probability" : undefined}>{isMobile ? "WALLETS" : "TRACKED WALLETS"}</th>
            {!isMobile && <th style={{ ...th, textAlign: "right" }}>L / S</th>}
            {!isMobile && <th style={{ ...th, textAlign: "right" }}>NOTIONAL</th>}
            {!isMobile && <th style={{ ...th, textAlign: "right" }} title="Consensus strength, 0 to 100: a heuristic blend of position value and wallet count, not a probability">STRENGTH</th>}
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
                <td style={{ ...td, fontWeight: 700, fontSize: 12 }}><Sym symbol={p.symbol} compact={isMobile} /></td>
                <td style={td}>
                  <Badge color={sigColor}>
                    {signalLabel(p.signal)}
                  </Badge>
                </td>
                <td style={{ ...td, textAlign: "center", color: T.text4 }}>{isMobile ? <span title="against" aria-label="against" style={{ fontSize: 14, lineHeight: 1 }}>{"\u2260"}</span> : "against"}</td>
                <td style={td}>
                  <Badge color={walletColor}>
                    {sm.trend}
                  </Badge>
                  {isMobile && <span style={{ marginLeft: 6, fontWeight: 600, color: walletColor }}>{Math.round(sm.confidence * 100)}</span>}
                </td>
                {!isMobile && (
                  <td style={{ ...td, textAlign: "right" }}>
                    <span style={{ color: col("#34d399") }}>{sm.long_count}</span>
                    <span style={{ color: T.text4 }}> / </span>
                    <span style={{ color: col("#f87171") }}>{sm.short_count}</span>
                  </td>
                )}
                {!isMobile && (
                  <td style={{ ...td, textAlign: "right", color: T.text3 }}>
                    <span style={{ color: col("#34d399") }}>{fmtUsd(sm.long_notional)}</span>
                    <span style={{ color: T.text4 }}> / </span>
                    <span style={{ color: col("#f87171") }}>{fmtUsd(sm.short_notional)}</span>
                  </td>
                )}
                {!isMobile && (
                  <td style={{ ...td, textAlign: "right", fontWeight: 600, color: walletColor }}>
                    {Math.round(sm.confidence * 100)}
                  </td>
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
// 3. TRANSITIONS — recent signal + regime changes
// ---------------------------------------------------------------------------

function TransitionsView({ events, isMobile }) {
  if (!events || events.length === 0) {
    return <div style={S.empty}>No recent signal changes.</div>;
  }
  const th = isMobile ? { ...S.th, ...S.thPhone } : S.th;
  const td = isMobile ? { ...S.td, ...S.tdPhone } : S.td;

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={S.table}>
        <thead>
          <tr>
            <th style={th}>TIME</th>
            <th style={th}>SYMBOL</th>
            <th style={th}>FROM</th>
            <th style={th}></th>
            <th style={th}>TO</th>
            <th style={th}>TYPE</th>
            {!isMobile && <th style={th}>REGIME</th>}
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
                <td style={{ ...td, color: T.text3 }}>{ago}</td>
                <td style={{ ...td, fontWeight: 700, fontSize: 12 }}><Sym symbol={ev.symbol} compact={isMobile} /></td>
                <td style={{ ...td, color: prevColor }}>{ev.prev_signal ? signalLabel(ev.prev_signal) : "\u2014"}</td>
                <td style={{ ...td, color: tt.color, fontSize: 12, textAlign: "center", padding: "7px 4px" }}>{tt.glyph}</td>
                <td style={{ ...td, color: sigColor, fontWeight: 600 }}>{signalLabel(ev.signal)}</td>
                <td style={td}>
                  <Badge color={tt.color}>{tt.label}</Badge>
                </td>
                {!isMobile && <td style={{ ...td, color: T.text3 }}>{ev.regime ? (REGIME_META[ev.regime]?.name || ev.regime) : "\u2014"}</td>}
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
  const th = isMobile ? { ...S.th, ...S.thPhone } : S.th;
  const td = isMobile ? { ...S.td, ...S.tdPhone } : S.td;

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={S.table}>
        <thead>
          <tr>
            <th style={th}>SYMBOL</th>
            <th style={th}>SIGNAL</th>
            <th style={{ ...th, textAlign: "center" }}>STREAK</th>
            <th style={th}>TYPE</th>
          </tr>
        </thead>
        <tbody>
          {streaks.map((s, i) => {
            const sigColor = signalColor(s.signal);
            return (
              <tr key={s.symbol} style={{ background: i % 2 === 1 ? T.overlay02 : "transparent" }}>
                <td style={{ ...td, fontWeight: 700, fontSize: 12 }}><Sym symbol={s.symbol} compact={isMobile} /></td>
                <td style={td}>
                  <Badge color={sigColor}>
                    {signalLabel(s.signal)}
                  </Badge>
                </td>
                <td style={{ ...td, textAlign: "center" }}>
                  <span style={{
                    display: "inline-flex", alignItems: "center", gap: 4,
                    fontSize: 14, fontWeight: 700,
                    color: s.isBull ? col("#34d399") : col("#f87171"),
                  }}>
                    {s.days}
                    <span style={{ fontSize: T.textXs, fontWeight: 500, color: T.text4 }}>days</span>
                  </span>
                </td>
                <td style={{ ...td, color: s.isBull ? col("#34d399") : col("#f87171"), fontWeight: 600 }}>
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
  const [picked, setPicked] = useState(null);   // heatmap cell shown in the readout line: { sym, idx }
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
      .then(d => { if (!cancelled) { setHeatmap(d); setPicked(null); } })
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
        {/* Bottom-aligned: the small sort tabs' steel bar sits on the same line as the 4H/1D bar. */}
        <div style={{ display: "flex", gap: 4, alignItems: "flex-end", flexWrap: "wrap", width: isMobile ? "100%" : undefined }}>
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
              <HeatmapReadout data={heatmap} picked={picked} isMobile={isMobile} />
              {heatmapError ? <LoadError onRetry={retry} /> : <SignalHeatmap data={heatmap} isMobile={isMobile} sortMode={sortMode} picked={picked} onPick={setPicked} />}
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
