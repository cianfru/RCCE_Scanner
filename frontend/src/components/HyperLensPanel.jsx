import Tabs from "./Tabs.jsx";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { createPortal } from "react-dom";
import { T } from "../theme.js";
import { useWallet } from "../WalletContext.jsx";
import GlassCard from "./GlassCard.jsx";
import { TableSkeleton } from "./Skeleton.jsx";
import { MIN_WALLETS, fmtUsd as fmt$, fmtSignedUsd, fmtSignedPct, cohortFields, trendCounts } from "../utils/hyperlens.js";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── HELPERS ─────────────────────────────────────────────────────────────────

const fmtLev = (x) => {
  if (x == null || isNaN(x)) return "--";
  return `${Number(x).toFixed(1)}x`;
};

const timeAgo = (ts) => {
  if (!ts) return "never";
  const sec = Math.floor(Date.now() / 1000 - ts);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
};

const truncAddr = (addr) => addr ? `${addr.slice(0, 6)}...${addr.slice(-4)}` : "";

const trendColor = (trend) =>
  trend === "BULLISH" ? T.green :
  trend === "BEARISH" ? T.red : T.text4;

const pctColor = (pct, invert = false) => {
  if (pct == null) return T.text4;
  const v = invert ? -pct : pct;
  if (v > 50) return T.green;
  if (v > 25) return T.yellow;
  return T.red;
};

const levColor = (lev) => {
  if (lev == null) return T.text4;
  if (lev < 5) return T.green;
  if (lev <= 15) return T.yellow;
  return T.red;
};

const riskColor = (score) => {
  if (score == null) return T.text4;
  if (score < 30) return T.green;
  if (score <= 60) return T.yellow;
  return T.red;
};

// ─── MODAL OVERLAY ───────────────────────────────────────────────────────────

// The portal lands outside App's .reflex-terminal wrapper, so it is wrapped again
// here to pick up the terminal rules (flat .terminal-status, font reset).
function ModalOverlay({ children, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return createPortal(
    <div className="reflex-terminal"><div
      role="dialog" aria-modal="true"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999,
        background: "rgba(0,0,0,0.55)", backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div style={{
        width: "100%", maxWidth: 900, maxHeight: "88vh",
        overflowY: "auto",
      }}>
        {children}
      </div>
    </div></div>,
    document.body
  );
}

// ─── SVG: LEVERAGE GAUGE ────────────────────────────────────────────────────

function LeverageGauge({ value, size = 64 }) {
  const v = value ?? 0;
  const cx = size / 2;
  const arcTop = 4;
  const r = size / 2 - 6;
  const cy = arcTop + r;  // Center of the arc semicircle
  const startAngle = Math.PI;
  const maxAngle = Math.PI;
  const maxLev = 50;
  const clamped = Math.min(v, maxLev);
  const ratio = clamped / maxLev;
  const needleAngle = startAngle + ratio * maxAngle;

  const arcPath = (from, to) => {
    const a1 = startAngle + (from / maxLev) * maxAngle;
    const a2 = startAngle + (to / maxLev) * maxAngle;
    const x1 = cx + r * Math.cos(a1);
    const y1 = cy + r * Math.sin(a1);
    const x2 = cx + r * Math.cos(a2);
    const y2 = cy + r * Math.sin(a2);
    const large = (a2 - a1) > Math.PI ? 1 : 0;
    return `M${x1.toFixed(1)},${y1.toFixed(1)} A${r},${r} 0 ${large} 1 ${x2.toFixed(1)},${y2.toFixed(1)}`;
  };

  const needleLen = r - 6;
  const nx = cx + needleLen * Math.cos(needleAngle);
  const ny = cy + needleLen * Math.sin(needleAngle);
  const svgH = cy + 16;

  return (
    <svg width={size} height={svgH} viewBox={`0 0 ${size} ${svgH}`}>
      <path d={arcPath(0, 5)} fill="none" stroke={T.green} strokeWidth="3" strokeLinecap="round" opacity="0.6" />
      <path d={arcPath(5, 15)} fill="none" stroke={T.yellow} strokeWidth="3" strokeLinecap="round" opacity="0.6" />
      <path d={arcPath(15, 50)} fill="none" stroke={T.red} strokeWidth="3" strokeLinecap="round" opacity="0.6" />
      <line x1={cx} y1={cy} x2={nx.toFixed(1)} y2={ny.toFixed(1)}
        stroke={levColor(v)} strokeWidth="1.5" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="2.5" fill={levColor(v)} />
      <text x={cx} y={cy + 14} textAnchor="middle" fill={T.text1}
        fontFamily={T.mono} fontSize="12" fontWeight="700">
        {fmtLev(v)}
      </text>
    </svg>
  );
}

// ─── RISK BADGE ──────────────────────────────────────────────────────────────

function RiskBadge({ score }) {
  if (score == null) return null;
  const color = riskColor(score);
  return (
    <span className="terminal-status" style={{
      fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700,
      color, letterSpacing: "0.04em",
    }}>
      RISK {Math.round(score)}
    </span>
  );
}

// ─── NOTIONAL BAR ───────────────────────────────────────────────────────────

function NotionalBar({ long_notional, short_notional, maxNotional }) {
  const total = (long_notional || 0) + (short_notional || 0);
  if (total === 0 || !maxNotional) return <span style={{ color: T.text4, fontFamily: T.mono, fontSize: 12 }}>--</span>;
  const pct = Math.min((total / maxNotional) * 100, 100);
  const longPct = total > 0 ? (long_notional / total) * 100 : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 70 }}>
      <div style={{
        width: "100%", height: 4, borderRadius: 2,
        background: T.overlay06, overflow: "hidden",
        display: "flex",
      }}>
        <div style={{ width: `${longPct * pct / 100}%`, height: "100%", background: T.green, transition: "width 0.3s" }} />
        <div style={{ width: `${(100 - longPct) * pct / 100}%`, height: "100%", background: T.red, transition: "width 0.3s" }} />
      </div>
      <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text3, textAlign: "center" }}>
        {fmt$(total)}
      </span>
    </div>
  );
}

// ─── SORTABLE TABLE HEADER ──────────────────────────────────────────────────

function SortTh({ label, sortKey, currentKey, asc, onSort, align = "right", w, title }) {
  const active = currentKey === sortKey;
  return (
    <th
      title={title}
      onClick={sortKey ? () => onSort(sortKey) : undefined}
      style={{
        padding: "12px 12px", textAlign: align,
        fontFamily: T.font, fontSize: T.textBase, fontWeight: 700,
        color: active ? T.accent : T.text3,
        letterSpacing: "0.08em", textTransform: "uppercase",
        cursor: sortKey ? "pointer" : "default",
        borderBottom: `2px solid ${T.border}`,
        whiteSpace: "nowrap", minWidth: w,
        userSelect: "none",
        transition: "color 0.2s",
      }}
    >
      {label}{active && (asc ? " \u25B2" : " \u25BC")}
    </th>
  );
}

// ─── STATUS STRIP ────────────────────────────────────────────────────────────

// Flat "LABEL value" pairs, like the scanner summary. Cohort sizes come from
// /status, the same lists the consensus uses.
function StatusStrip({ status, cohort }) {
  const mpCount = status.money_printer_count || 0;
  const smCount = status.smart_money_count || 0;
  const bothCount = status.elite_count || 0;

  const walletLabel = cohort === "money_printers" ? mpCount
    : cohort === "smart_money" ? smCount
    : (status.tracked_wallets || 0);

  const items = [
    { label: "WALLETS", value: walletLabel },
    { label: "ACTIVE", value: status.active_wallets || 0 },
    { label: "SYMBOLS", value: status.consensus_symbols || 0 },
    { label: "POLLS", value: status.poll_count || 0 },
    { label: "LAST POLL", value: timeAgo(status.last_poll) },
  ];
  const sep = <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>·</span>;

  return (
    <div style={{
      display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "4px 10px",
      padding: "10px 16px",
      borderTop: `1px solid ${T.overlay08}`,
      borderBottom: `1px solid ${T.overlay08}`,
    }}>
      {items.map(({ label, value }, i) => (
        <span key={label} style={{ display: "inline-flex", alignItems: "baseline", gap: 10 }}>
          {i > 0 && sep}
          <span style={{ display: "inline-flex", alignItems: "baseline", gap: 5 }}>
            <span style={{ fontFamily: T.font, fontSize: T.textXs, color: T.text4, letterSpacing: "0.08em", fontWeight: 700, textTransform: "uppercase" }}>{label}</span>
            <span style={{ fontFamily: T.mono, fontSize: T.textBase, fontWeight: 700, color: T.text1 }}>{value}</span>
          </span>
        </span>
      ))}
      {/* Cohort breakdown counts */}
      {cohort === "all" && (mpCount > 0 || smCount > 0) && (
        <span style={{ display: "inline-flex", alignItems: "baseline", gap: 10, fontFamily: T.mono, fontSize: T.textSm, color: T.text2 }}>
          {sep}
          <span>{mpCount} profitable · {smCount} large{bothCount > 0 ? ` · ${bothCount} in both` : ""}</span>
        </span>
      )}
    </div>
  );
}

// ─── CONSENSUS BAR ───────────────────────────────────────────────────────────

function ConsensusBar({ long_count, short_count }) {
  const total = long_count + short_count;
  if (total === 0) return <span style={{ color: T.text4 }}>--</span>;
  const longPct = (long_count / total) * 100;
  const shortPct = (short_count / total) * 100;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", minWidth: 80 }}>
      <div style={{
        flex: 1, height: 6, borderRadius: 3,
        background: T.overlay06, overflow: "hidden", display: "flex",
      }}>
        <div style={{
          width: `${longPct}%`, height: "100%",
          background: `linear-gradient(90deg, ${T.green}90, ${T.green})`,
          borderRadius: "3px 0 0 3px", transition: "width 0.4s ease",
        }} />
        <div style={{
          width: `${shortPct}%`, height: "100%",
          background: `linear-gradient(90deg, ${T.red}, ${T.red}90)`,
          borderRadius: "0 3px 3px 0", transition: "width 0.4s ease",
        }} />
      </div>
      <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4, whiteSpace: "nowrap", minWidth: 34, textAlign: "right" }}>
        {long_count}/{short_count}
      </span>
    </div>
  );
}

// ─── CONSENSUS TABLE (enhanced) ─────────────────────────────────────────────

const NET_TITLE = "Long minus short wallets, as a share of positioned wallets. The trend weighs position size, so the two can point in different directions.";

// Rows with fewer than MIN_WALLETS positioned wallets get no trend.
function TrendCell({ trend }) {
  if (trend === "THIN") {
    return (
      <span title={`Fewer than ${MIN_WALLETS} wallets hold a position, so no trend is shown`}
        style={{ fontFamily: T.font, fontSize: T.textXs, color: T.text4, whiteSpace: "nowrap" }}>
        Too few wallets
      </span>
    );
  }
  return (
    <span className="terminal-status" style={{
      fontFamily: T.mono, fontSize: T.textBase, fontWeight: 700,
      color: trendColor(trend), letterSpacing: "0.06em",
    }}>
      {trend}
    </span>
  );
}

function ConsensusTable({ consensus, filter, onSymbolClick, isMobile, cohort }) {
  const [sortKey, setSortKey] = useState("positioned");
  const [sortAsc, setSortAsc] = useState(false);

  // Average leverage exists only for all wallets, so it is hidden while a
  // cohort is selected.
  const allWallets = cohort === "all";

  const maxNotional = useMemo(() => {
    return Math.max(...consensus.map(c => {
      const f = cohortFields(c, cohort);
      return f.long_notional + f.short_notional;
    }), 1);
  }, [consensus, cohort]);

  const filtered = useMemo(() => {
    let items = [...consensus];
    if (filter) {
      const q = filter.toUpperCase();
      items = items.filter(c => c.symbol.includes(q));
    }
    // A hidden column cannot be the sort key.
    const key = !allWallets && sortKey === "leverage" ? "positioned" : sortKey;
    items.sort((a, b) => {
      const aF = cohortFields(a, cohort);
      const bF = cohortFields(b, cohort);
      let va, vb;
      switch (key) {
        case "symbol": va = a.symbol; vb = b.symbol; return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        case "trend": va = aF.trend; vb = bF.trend; return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        case "notional": va = aF.long_notional + aF.short_notional; vb = bF.long_notional + bF.short_notional; break;
        case "net": va = aF.net_wallets; vb = bF.net_wallets; break;
        case "leverage": va = a.avg_leverage || 0; vb = b.avg_leverage || 0; break;
        default: va = aF.positioned; vb = bF.positioned;
      }
      return sortAsc ? va - vb : vb - va;
    });
    return items;
  }, [consensus, filter, sortKey, sortAsc, cohort, allWallets]);

  const handleSort = (key) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const netColor = (v) => v > 0.1 ? T.green : v < -0.1 ? T.red : T.text3;

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <SortTh label="SYMBOL" sortKey="symbol" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="left" w={70} />
            <SortTh label="TREND BY SIZE" sortKey="trend" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align={isMobile ? "right" : "center"} w={96} />
            {!isMobile && (
              <>
                <SortTh label="WALLETS" sortKey="positioned" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={56} />
                <th style={{ padding: "12px 12px", fontFamily: T.font, fontSize: T.textBase, fontWeight: 700, color: T.text3, letterSpacing: "0.08em", textTransform: "uppercase", borderBottom: `2px solid ${T.border}`, minWidth: 130 }} title="Wallet count, long versus short. The trend column weighs position size, so the two can point in different directions.">WALLETS L / S</th>
                <SortTh label="NET WALLETS" title={NET_TITLE} sortKey="net" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={48} />
                {allWallets && <SortTh label="AVG LEV" sortKey="leverage" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={60} />}
                <SortTh label="NOTIONAL" sortKey="notional" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={90} />
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {filtered.map((c, idx) => {
            const cf = cohortFields(c, cohort);
            const stripeBg = idx % 2 === 1 ? T.overlay02 : "transparent";
            return (
              <tr
                key={c.symbol}
                onClick={() => onSymbolClick?.(c.symbol)}
                style={{ cursor: "pointer", transition: "background 0.2s ease", borderBottom: `1px solid ${T.overlay04}`, background: stripeBg }}
                onMouseEnter={e => e.currentTarget.style.background = T.overlay06}
                onMouseLeave={e => e.currentTarget.style.background = stripeBg}
              >
                <td style={{ padding: "10px 12px" }}>
                  <div style={{ fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700, color: T.text1 }}>
                    {c.symbol}
                  </div>
                  {/* Mobile: the wallet figures sit under the symbol instead of in off-screen columns */}
                  {isMobile && (
                    <div title={NET_TITLE} style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text3, marginTop: 2 }}>
                      L/S {cf.long_count}/{cf.short_count} · net {fmtSignedPct(cf.net_wallets * 100)} · {cf.positioned} wallets
                    </div>
                  )}
                </td>
                <td style={{ padding: "10px 12px", textAlign: isMobile ? "right" : "center" }}>
                  <TrendCell trend={cf.trend} />
                </td>
                {!isMobile && (
                  <>
                    <td style={{ padding: "10px 12px", textAlign: "center", fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700, color: T.text1 }}>
                      {cf.positioned}
                    </td>
                    <td style={{ padding: "10px 12px" }}>
                      <ConsensusBar long_count={cf.long_count} short_count={cf.short_count} />
                    </td>
                    <td style={{
                      padding: "10px 12px", textAlign: "center",
                      fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700,
                      color: netColor(cf.net_wallets),
                    }}>
                      {fmtSignedPct(cf.net_wallets * 100)}
                    </td>
                    {allWallets && (
                      <td style={{
                        padding: "10px 12px", textAlign: "center",
                        fontFamily: T.mono, fontSize: T.textBase, fontWeight: 600,
                        color: levColor(c.avg_leverage),
                      }}>
                        {c.avg_leverage ? fmtLev(c.avg_leverage) : "--"}
                      </td>
                    )}
                    <td style={{ padding: "10px 12px" }}>
                      <NotionalBar long_notional={cf.long_notional} short_notional={cf.short_notional} maxNotional={maxNotional} />
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
      {filtered.length === 0 && (
        <div style={{ padding: 24, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
          {filter ? "No matching symbols" : "Waiting for first poll..."}
        </div>
      )}
    </div>
  );
}

// ─── LEAN BY SIZE (view key "heatmap") ──────────────────────────────────────

// One diverging bar per symbol: the size-weighted lean the Consensus trend comes
// from (a trend needs more than 15% either way), so the two views cannot disagree.
function HeatmapGrid({ consensus, onSymbolClick, cohort }) {
  const { rows, thin } = useMemo(() => {
    const rows = [];
    let thin = 0;
    for (const c of consensus) {
      const f = cohortFields(c, cohort);
      if (f.positioned === 0) continue;
      if (f.trend === "THIN") { thin += 1; continue; }
      if (f.lean == null) continue;
      rows.push({ symbol: c.symbol, ...f });
    }
    rows.sort((a, b) => b.lean - a.lean);
    return { rows, thin };
  }, [consensus, cohort]);

  if (rows.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
        {thin > 0 ? `No symbol has ${MIN_WALLETS} or more wallets positioned yet.` : "Waiting for consensus data..."}
      </div>
    );
  }

  const grid = {
    display: "grid", gridTemplateColumns: "72px minmax(0, 1fr) 52px 56px",
    gap: 10, alignItems: "center", padding: "0 12px", minWidth: 320,
  };
  const head = { fontFamily: T.font, fontSize: T.textXs, fontWeight: 700, color: T.text3, letterSpacing: "0.08em", textTransform: "uppercase" };

  return (
    <div style={{ overflowX: "auto", padding: "10px 0" }}>
      <div style={{ ...grid, marginBottom: 6 }}>
        <span style={head}>Symbol</span>
        <span style={{ ...head, display: "flex", justifyContent: "space-between" }}
          title="Long minus short notional, blended with the wallet count the same way as the Consensus trend. Past 15% either way (the faint marks) the trend reads bullish or bearish.">
          <span>More short</span><span>More long</span>
        </span>
        <span style={{ ...head, textAlign: "right" }}>Lean</span>
        <span style={{ ...head, textAlign: "right" }}>Wallets</span>
      </div>
      {rows.map((r) => {
        const color = trendColor(r.trend);
        const w = Math.min(Math.abs(r.lean), 1) * 50;
        return (
          <div
            key={r.symbol}
            onClick={() => onSymbolClick?.(r.symbol)}
            style={{ ...grid, paddingTop: 6, paddingBottom: 6, cursor: "pointer", transition: "background 0.15s" }}
            onMouseEnter={e => e.currentTarget.style.background = T.overlay04}
            onMouseLeave={e => e.currentTarget.style.background = "transparent"}
          >
            <span style={{ fontFamily: T.mono, fontSize: T.textBase, fontWeight: 700, color: T.text1 }}>{r.symbol}</span>
            <div style={{ position: "relative", height: 8, background: T.overlay04 }}>
              <div style={{ position: "absolute", top: 0, bottom: 0, left: "42.5%", width: 1, background: T.overlay15 }} />
              <div style={{ position: "absolute", top: 0, bottom: 0, left: "57.5%", width: 1, background: T.overlay15 }} />
              <div style={{ position: "absolute", top: -2, bottom: -2, left: "50%", width: 1, background: T.overlay30 }} />
              <div style={{
                position: "absolute", top: 0, bottom: 0,
                left: r.lean >= 0 ? "50%" : `${50 - w}%`, width: `${w}%`,
                background: color, transition: "width 0.3s ease",
              }} />
            </div>
            <span style={{ fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700, color, textAlign: "right" }}>
              {fmtSignedPct(r.lean * 100)}
            </span>
            <span style={{ fontFamily: T.mono, fontSize: T.textSm, color: T.text3, textAlign: "right" }}>{r.positioned}</span>
          </div>
        );
      })}
      {thin > 0 && (
        <div style={{ padding: "10px 12px 0", fontFamily: T.font, fontSize: T.textXs, color: T.text4 }}>
          {thin} symbol{thin !== 1 ? "s" : ""} with fewer than {MIN_WALLETS} wallets positioned {thin !== 1 ? "are" : "is"} not shown.
        </div>
      )}
    </div>
  );
}

// ─── EQUITY CHART (full-width SVG like HyperTracker) ───────────────────────

function EquityChart({ data, width = 500, height = 120 }) {
  const containerRef = useRef(null);
  const [cw, setCw] = useState(width);
  useEffect(() => {
    if (containerRef.current) setCw(containerRef.current.offsetWidth);
    const ro = new ResizeObserver(([e]) => setCw(e.contentRect.width));
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  if (!data || data.length < 2) {
    return (
      <div ref={containerRef} style={{ width: "100%", height, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>Collecting equity data...</span>
      </div>
    );
  }

  const values = data.map(d => d.value ?? d);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = maxV - minV || 1;
  const pad = { top: 8, right: 6, bottom: 6, left: 54 };
  const chartW = cw - pad.left - pad.right;
  const chartH = height - pad.top - pad.bottom;
  const isUp = values[values.length - 1] >= values[0];
  const lineColor = isUp ? T.green : T.red;

  const points = values.map((v, i) => ({
    x: pad.left + (i / (values.length - 1)) * chartW,
    y: pad.top + chartH - ((v - minV) / range) * chartH,
  }));

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${(pad.left + chartW).toFixed(1)},${(pad.top + chartH).toFixed(1)} L${pad.left},${(pad.top + chartH).toFixed(1)} Z`;
  const gradId = `eq-${Math.random().toString(36).slice(2, 8)}`;

  // Y-axis: 3 labels
  const yLabels = [maxV, (maxV + minV) / 2, minV];

  return (
    <div ref={containerRef} style={{ width: "100%" }}>
      <svg width={cw} height={height} viewBox={`0 0 ${cw} ${height}`} style={{ display: "block" }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.18" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0.01" />
          </linearGradient>
        </defs>
        {yLabels.map((v, i) => {
          const y = pad.top + chartH - ((v - minV) / range) * chartH;
          return (
            <g key={i}>
              <line x1={pad.left} y1={y} x2={cw - pad.right} y2={y}
                stroke={T.border} strokeWidth="0.5" strokeDasharray="3,3" opacity="0.5" />
              <text x={pad.left - 4} y={y + 4} textAnchor="end" fill={T.text4}
                fontFamily={T.mono} fontSize="12">{fmt$(v)}</text>
            </g>
          );
        })}
        <path d={areaPath} fill={`url(#${gradId})`} />
        <path d={linePath} fill="none" stroke={lineColor} strokeWidth="1.5" strokeLinejoin="round" />
        <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="3" fill={lineColor} />
        <text x={cw - pad.right} y={Math.max(points[points.length - 1].y - 6, 12)}
          textAnchor="end" fill={lineColor} fontFamily={T.mono} fontSize="12" fontWeight="700">
          {fmt$(values[values.length - 1])}
        </text>
      </svg>
    </div>
  );
}

// ─── BIAS GAUGE (like HyperTracker "Perp Bias") ────────────────────────────

function BiasGauge({ positions }) {
  if (!positions || positions.length === 0) return null;
  const longVal = positions.filter(p => p.side === "LONG").reduce((s, p) => s + (p.size_usd || 0), 0);
  const shortVal = positions.filter(p => p.side === "SHORT").reduce((s, p) => s + (p.size_usd || 0), 0);
  const total = longVal + shortVal;
  if (total === 0) return null;
  const ratio = (longVal - shortVal) / total; // -1 to +1

  const biasLabel = ratio > 0.6 ? "Very Bullish" : ratio > 0.2 ? "Bullish" :
    ratio < -0.6 ? "Very Bearish" : ratio < -0.2 ? "Bearish" : "Neutral";
  const biasColor = ratio > 0.2 ? T.green : ratio < -0.2 ? T.red : T.text4;

  return (
    <div style={{
      padding: "8px 12px", borderTop: `1px solid ${T.overlay10}`,
      display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
      minWidth: 110,
    }}>
      <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4, letterSpacing: "0.06em" }}>PERP BIAS</span>
      <span style={{ fontFamily: T.mono, fontSize: 14, fontWeight: 700, color: biasColor, fontStyle: "italic" }}>
        {biasLabel}
      </span>
      {/* Mini long/short bar */}
      <div style={{ width: 90, height: 4, borderRadius: 2, background: T.overlay06, overflow: "hidden", display: "flex" }}>
        <div style={{ width: `${(longVal / total) * 100}%`, height: "100%", background: T.green }} />
        <div style={{ width: `${(shortVal / total) * 100}%`, height: "100%", background: T.red }} />
      </div>
      <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>
        L {fmt$(longVal)} / S {fmt$(shortVal)}
      </span>
    </div>
  );
}

// ─── DIST TO LIQ BAR (colored progress bar like HyperTracker) ──────────────

function LiqDistBar({ pct }) {
  if (pct == null || pct <= 0) return <span style={{ fontFamily: T.mono, fontSize: 12, color: T.text4 }}>--</span>;
  const clamped = Math.min(pct, 100);
  const color = clamped > 50 ? T.green : clamped > 25 ? T.yellow : T.red;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, minWidth: 80 }}>
      <span style={{ fontFamily: T.mono, fontSize: T.textXs, fontWeight: 600, color, minWidth: 32, textAlign: "right" }}>
        {clamped.toFixed(0)}%
      </span>
      <div style={{ flex: 1, height: 4, borderRadius: 2, background: T.overlay06, overflow: "hidden", minWidth: 40 }}>
        <div style={{
          width: `${clamped}%`, height: "100%", borderRadius: 2,
          background: color, transition: "width 0.3s",
        }} />
      </div>
    </div>
  );
}

// ─── WALLET TAGS (account size and monthly return) ──────────────────────────

function WalletTags({ data }) {
  const tags = [];
  const av = data.account_value || 0;
  const roi = data.monthly_roi || 0;
  if (av >= 10e6) tags.push({ label: "$10M+ account", color: T.text2 });
  else if (av >= 1e6) tags.push({ label: "$1M+ account", color: T.text2 });
  else if (av >= 100e3) tags.push({ label: "$100K+ account", color: T.text2 });
  if (roi >= 100) tags.push({ label: "High return", color: T.green });
  else if (roi >= 50) tags.push({ label: "Consistent", color: T.yellow });
  if (tags.length === 0) return null;
  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
      {tags.map(t => (
        <span key={t.label} style={{ fontFamily: T.mono, fontSize: T.textXs, fontWeight: 600, color: t.color }}>
          {t.label}
        </span>
      ))}
    </div>
  );
}

// ─── WALLET PROFILE MODAL (HyperTracker-style layout) ──────────────────────

function WalletDetail({ address, onClose, userWallet }) {
  const [data, setData] = useState(null);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState("positions");
  const [isFollowing, setIsFollowing] = useState(false);
  const [copied, setCopied] = useState(false);

  // Check follow state on mount
  useEffect(() => {
    if (!userWallet) return;
    fetch(`${API}/api/hyperlens/follows/check/${address}?user=${userWallet}`)
      .then(r => r.json())
      .then(d => setIsFollowing(d.following || false))
      .catch(() => {});
  }, [address, userWallet]);

  const toggleFollow = () => {
    if (!userWallet) return;
    if (isFollowing) {
      fetch(`${API}/api/hyperlens/follows/${address}?user=${userWallet}`, { method: "DELETE" })
        .then(() => setIsFollowing(false))
        .catch(() => {});
    } else {
      fetch(`${API}/api/hyperlens/follows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user: userWallet, address }),
      })
        .then(() => setIsFollowing(true))
        .catch(() => {});
    }
  };

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/api/hyperlens/wallet/${address}`).then(r => r.json()),
      fetch(`${API}/api/hyperlens/wallet/${address}/trades?limit=100`).then(r => r.json()),
    ])
      .then(([profile, tradeRes]) => {
        setData(profile);
        setTrades(tradeRes.trades || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [address]);

  if (loading) {
    return (
      <GlassCard style={{ padding: 20 }}>
        <div style={{ fontFamily: T.mono, fontSize: 13, color: T.text4, textAlign: "center" }}>Loading wallet profile...</div>
      </GlassCard>
    );
  }

  if (!data) {
    return (
      <GlassCard style={{ padding: 20 }}>
        <div style={{ fontFamily: T.mono, fontSize: 13, color: T.text4, textAlign: "center" }}>Wallet not found</div>
      </GlassCard>
    );
  }

  const s = data.stats || {};
  const positions = data.current_positions || [];
  const coinBreakdown = data.coin_breakdown || [];
  const avHistory = data.av_history || [];
  const levStats = data.leverage_stats || {};

  // Compute aggregates like HyperTracker
  const cryptoPositions = positions.filter(p => !p.asset_class || p.asset_class === "crypto");
  const tradfiPositions = positions.filter(p => p.asset_class && p.asset_class !== "crypto");
  const longValue = positions.filter(p => p.side === "LONG").reduce((s, p) => s + (p.size_usd || 0), 0);
  const shortValue = positions.filter(p => p.side === "SHORT").reduce((s, p) => s + (p.size_usd || 0), 0);
  const totalValue = longValue + shortValue;
  const sumPnl = positions.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);

  const perpsLabel = tradfiPositions.length > 0
    ? `Positions (${cryptoPositions.length} crypto + ${tradfiPositions.length} tradfi)`
    : `Perps (${positions.length})`;

  const sections = [
    { key: "positions", label: perpsLabel },
    { key: "trades", label: `Trades (${trades.length})` },
    { key: "coins", label: "Coin Stats" },
  ];

  return (
    <GlassCard style={{ padding: 0, overflow: "hidden" }}>
      {/* ── HEADER ROW ── */}
      <div style={{
        padding: "16px 16px 12px",
        borderBottom: `1px solid ${T.overlay08}`,
        background: T.overlay02,
        display: "flex", alignItems: "flex-start", justifyContent: "space-between",
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <div style={{ width: 3, height: 16, borderRadius: 2, background: T.accent, flexShrink: 0 }} />
            <span style={{ fontFamily: T.mono, fontSize: 16, fontWeight: 700, color: T.accent }}>
              {truncAddr(address)}
            </span>
            {data.rank && (
              <span className="terminal-status" style={{
                fontFamily: T.mono, fontSize: T.textXs, fontWeight: 700, color: T.accent,
              }}>
                #{data.rank}
              </span>
            )}
            <RiskBadge score={data.risk_score} />
          </div>
          {/* Full address + copy + snaps */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
            <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>
              {data.snapshot_count} snaps
            </span>
            <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4, userSelect: "all", wordBreak: "break-all" }}>
              {address}
            </span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                navigator.clipboard?.writeText(address).then(() => {
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1200);
                }).catch(() => {});
              }}
              style={{
                fontFamily: T.mono, fontSize: T.textXs, fontWeight: 600,
                color: copied ? T.green : T.accent, background: "none", border: 0,
                padding: 0, cursor: "pointer", flexShrink: 0,
              }}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          {/* Tags */}
          <div style={{ marginTop: 6 }}>
            <WalletTags data={data} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          {userWallet && (
            <button
              onClick={toggleFollow}
              title={isFollowing ? "Unfollow wallet" : "Follow wallet for trade alerts"}
              aria-pressed={isFollowing}
              style={{
                height: 30, padding: "0 4px", background: "none", border: 0,
                fontFamily: T.font, fontSize: T.textSm, fontWeight: 600,
                color: isFollowing ? T.accent : T.text3, cursor: "pointer",
              }}
            >
              {isFollowing ? "Following" : "Follow"}
            </button>
          )}
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{
              width: 30, height: 30, borderRadius: 8,
              border: `1px solid ${T.overlay10}`, background: T.overlay04, color: T.text3,
              fontSize: 14, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center",
              transition: "all 0.15s",
            }}
            onMouseEnter={e => { e.currentTarget.style.background = T.overlay10; e.currentTarget.style.color = T.text1; }}
            onMouseLeave={e => { e.currentTarget.style.background = T.overlay04; e.currentTarget.style.color = T.text3; }}
          >
            {"\u2715"}
          </button>
        </div>
      </div>

      {/* ── EQUITY CURVE (full width, tighter) ── */}
      <div style={{
        padding: "8px 12px 4px",
        borderBottom: `1px solid ${T.overlay08}`,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <span style={{ fontFamily: T.mono, fontSize: 20, fontWeight: 700, color: T.text1 }}>
              {fmt$(data.account_value || 0)}
            </span>
            <span style={{
              fontFamily: T.mono, fontSize: 13, fontWeight: 700,
              color: sumPnl >= 0 ? T.green : T.red,
            }}>
              {fmtSignedUsd(sumPnl)}
              {data.account_value > 0 && (
                <span style={{ opacity: 0.7, marginLeft: 4 }}>
                  ({fmtSignedPct((sumPnl / data.account_value) * 100, 2)})
                </span>
              )}
            </span>
          </div>
          {avHistory.length >= 2 && (() => {
            const first = avHistory[0]?.value ?? avHistory[0];
            const last = avHistory[avHistory.length - 1]?.value ?? avHistory[avHistory.length - 1];
            const pnl = last - first;
            const pctChg = first > 0 ? ((pnl / first) * 100) : 0;
            const color = pnl >= 0 ? T.green : T.red;
            return (
              <div style={{ textAlign: "right" }}>
                <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color }}>
                  {fmtSignedPct(pctChg, 2)}
                </span>
                <span style={{ fontFamily: T.mono, fontSize: T.textXs, color, marginLeft: 4 }}>
                  ({fmtSignedUsd(pnl)})
                </span>
                <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4, marginLeft: 4 }}>
                  tracked
                </span>
              </div>
            );
          })()}
        </div>
        <EquityChart data={avHistory} height={100} />
      </div>

      {/* ── STATS ROW (compact horizontal strip) ── */}
      <div style={{
        padding: "8px 12px",
        display: "flex", gap: 12, flexWrap: "wrap", alignItems: "stretch",
        borderBottom: `1px solid ${T.overlay08}`,
      }}>
        {/* Bias gauge */}
        <BiasGauge positions={positions} />

        {/* Leverage */}
        <div style={{
          padding: "8px 12px", borderTop: `1px solid ${T.overlay10}`,
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        }}>
          <LeverageGauge value={levStats.avg_leverage} size={60} />
          <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4, letterSpacing: "0.06em" }}>
            Leverage
          </span>
        </div>

        {/* Stats grid. ROI and PnL are the leaderboard's 30-day figures; ROI is
            empty when the wallet started the month with almost no equity. */}
        <div style={{
          flex: 1, minWidth: 180,
          padding: "6px 12px", borderTop: `1px solid ${T.overlay10}`,
          display: "grid", gridTemplateColumns: "1fr 1fr",
          gap: "2px 16px", alignContent: "center",
        }}>
          {[
            ["30d ROI", fmtSignedPct(data.monthly_roi), data.monthly_roi == null ? T.text4 : data.monthly_roi >= 0 ? T.green : T.red],
            ["30d PnL", fmtSignedUsd(data.monthly_pnl || 0), (data.monthly_pnl || 0) >= 0 ? T.green : T.red],
            ["Score", (data.score || 0).toFixed(0), T.text1],
            ...(s.total_trades > 0 ? [
              ["Win", `${s.win_rate}% (${s.wins}/${s.total_trades})`, s.win_rate > 50 ? T.green : T.red],
              ["Avg", fmtSignedPct(s.avg_pnl_pct, 2), s.avg_pnl_pct > 0 ? T.green : s.avg_pnl_pct < 0 ? T.red : T.text4],
            ] : []),
          ].map(([label, val, color]) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
              <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>{label}</span>
              <span style={{ fontFamily: T.mono, fontSize: T.textXs, fontWeight: 700, color }}>{val}</span>
            </div>
          ))}
        </div>

        {/* Best/Worst trades: a win is never shown as the worst trade */}
        {(() => {
          const best = s.best_trade?.pnl > 0 ? s.best_trade : null;
          const worst = s.worst_trade?.pnl < 0 ? s.worst_trade : null;
          if (!best && !worst) return null;
          return (
            <div style={{
              display: "flex", flexDirection: "column", gap: 3, justifyContent: "center",
            }}>
              {best && (
                <span style={{ fontFamily: T.mono, fontSize: T.textXs, fontWeight: 600, color: T.green, whiteSpace: "nowrap" }}>
                  Best: {best.coin} {best.side} {fmtSignedUsd(best.pnl)} ({fmtSignedPct(best.pnl_pct, 1)})
                </span>
              )}
              {worst && (
                <span style={{ fontFamily: T.mono, fontSize: T.textXs, fontWeight: 600, color: T.red, whiteSpace: "nowrap" }}>
                  Worst: {worst.coin} {worst.side} {fmtSignedUsd(worst.pnl)} ({fmtSignedPct(worst.pnl_pct, 1)})
                </span>
              )}
            </div>
          );
        })()}
      </div>

      {/* ── SECTION TABS (Perps / Trades / Coin Stats) ── */}
      <div style={{ padding: "0 12px", borderBottom: `1px solid ${T.overlay08}` }}>
        <Tabs small label="Wallet sections" items={sections} value={activeSection} onChange={setActiveSection} />
      </div>

      {/* ── POSITION SUMMARY STRIP (like HyperTracker) ── */}
      {activeSection === "positions" && positions.length > 0 && (
        <div style={{
          padding: "10px 16px",
          display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center",
          borderBottom: `1px solid ${T.overlay08}`,
          background: T.overlay02,
        }}>
          <span style={{ fontFamily: T.mono, fontSize: 12 }}>
            <span style={{ color: T.text4 }}>Long Value: </span>
            <span style={{ color: T.green, fontWeight: 600 }}>{fmt$(longValue)}</span>
          </span>
          <span style={{ color: T.text4 }}>|</span>
          <span style={{ fontFamily: T.mono, fontSize: 12 }}>
            <span style={{ color: T.text4 }}>Short Value: </span>
            <span style={{ color: T.red, fontWeight: 600 }}>{fmt$(shortValue)}</span>
          </span>
          <span style={{ color: T.text4 }}>|</span>
          <span style={{ fontFamily: T.mono, fontSize: 12 }}>
            <span style={{ color: T.text4 }}>Total: </span>
            <span style={{ color: T.text1, fontWeight: 600 }}>{fmt$(totalValue)}</span>
          </span>
          <span style={{ marginLeft: "auto", fontFamily: T.mono, fontSize: 12 }}>
            <span style={{ color: T.text4 }}>Sum PNL: </span>
            <span style={{ color: sumPnl >= 0 ? T.green : T.red, fontWeight: 700 }}>
              {fmtSignedUsd(sumPnl)}
            </span>
          </span>
        </div>
      )}

      {/* ── SECTION CONTENT ── */}
      <div style={{ overflowX: "auto" }}>
        {/* POSITIONS (HyperTracker layout: Token, Amount, Value, Avg Entry, PNL/ROE, Lev, Dist. to Liq, Age) */}
        {activeSection === "positions" && (
          <>
            {positions.length === 0 ? (
              <div style={{ padding: 16, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
                No open positions
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["TOKEN", "SIDE", "VALUE", "AVG ENTRY", "PNL/ROE", "LEV", "DIST. TO LIQ"].map(h => (
                      <th key={h} style={{
                        padding: "8px 8px",
                        fontFamily: T.mono, fontSize: T.textXs, fontWeight: 600,
                        color: T.text4, letterSpacing: "0.05em",
                        borderBottom: `1px solid ${T.border}`,
                        textAlign: h === "TOKEN" || h === "SIDE" ? "left" : h === "DIST. TO LIQ" ? "left" : "right",
                        whiteSpace: "nowrap",
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p, i) => {
                    const roe = p.return_on_equity;
                    const pnl = p.unrealized_pnl || 0;
                    const stripeBg = i % 2 === 1 ? T.overlay02 : "transparent";
                    return (
                      <tr key={i} style={{ borderBottom: `1px solid ${T.overlay06}`, background: stripeBg }}>
                        {/* TOKEN — coin name + leverage type + asset class badge */}
                        <td style={{ padding: "8px 8px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                            <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.text1 }}>
                              {p.coin}
                            </span>
                            {p.asset_class && p.asset_class !== "crypto" && (
                              <span style={{
                                fontFamily: T.mono, fontSize: T.textXs, fontWeight: 600,
                                color: T.text3, textTransform: "uppercase", letterSpacing: 0.5,
                              }}>
                                {p.asset_class}
                              </span>
                            )}
                          </div>
                          <div style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>
                            {p.leverage}x {p.leverage_type || "Cross"}{p.dex ? ` · ${p.dex}` : ""}
                          </div>
                        </td>
                        {/* SIDE */}
                        <td style={{ padding: "8px 8px" }}>
                          <span style={{
                            fontFamily: T.mono, fontSize: 12, fontWeight: 700,
                            padding: "2px 7px", borderRadius: 3,
                            color: p.side === "LONG" ? T.green : T.red,
                            background: `${p.side === "LONG" ? T.green : T.red}15`,
                          }}>
                            {p.side}
                          </span>
                        </td>
                        {/* VALUE */}
                        <td style={{ padding: "8px 8px", textAlign: "right" }}>
                          <div style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.text1 }}>
                            {fmt$(p.size_usd)}
                          </div>
                          {p.size != null && (
                            <div style={{ fontFamily: T.mono, fontSize: T.textXs, color: p.side === "LONG" ? T.green : T.red }}>
                              {p.side === "LONG" ? "+" : "-"}{Number(p.size).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                            </div>
                          )}
                        </td>
                        {/* AVG ENTRY */}
                        <td style={{ padding: "8px 8px", textAlign: "right", fontFamily: T.mono, fontSize: 12, color: T.text3 }}>
                          ${(p.entry_px || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </td>
                        {/* PNL/ROE */}
                        <td style={{ padding: "8px 8px", textAlign: "right" }}>
                          <div style={{
                            fontFamily: T.mono, fontSize: 13, fontWeight: 700,
                            color: pnl >= 0 ? T.green : T.red,
                          }}>
                            {fmtSignedUsd(pnl)}
                          </div>
                          {roe != null && (
                            <div style={{
                              fontFamily: T.mono, fontSize: T.textXs,
                              color: roe >= 0 ? T.green : T.red,
                            }}>
                              {fmtSignedPct(roe * 100, 2)}
                            </div>
                          )}
                        </td>
                        {/* LEV */}
                        <td style={{ padding: "8px 8px", textAlign: "right", fontFamily: T.mono, fontSize: 12, color: levColor(p.leverage) }}>
                          {p.leverage}x
                        </td>
                        {/* DIST. TO LIQ (progress bar) */}
                        <td style={{ padding: "8px 8px" }}>
                          <LiqDistBar pct={p.liq_distance_pct} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </>
        )}

        {/* TRADES */}
        {activeSection === "trades" && (
          <>
            {trades.length === 0 ? (
              <div style={{ padding: 24, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
                No trades detected yet — trades appear as positions open and close over time.
                <br />
                <span style={{ fontSize: 12, marginTop: 4, display: "block" }}>
                  Tracking since {data.snapshot_count} snapshots ago
                </span>
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["COIN", "SIDE", "SIZE", "ENTRY", "LEV", "PNL", "STATUS"].map(h => (
                      <th key={h} style={{
                        padding: "8px 8px",
                        fontFamily: T.mono, fontSize: T.textXs, fontWeight: 600,
                        color: T.text4, letterSpacing: "0.06em",
                        borderBottom: `1px solid ${T.border}`,
                        textAlign: h === "COIN" || h === "SIDE" || h === "STATUS" ? "left" : "right",
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t, i) => {
                    const statusColor =
                      t.status === "OPENED" ? T.accent :
                      t.status === "CLOSED" ? T.text3 :
                      t.status === "FLIPPED" ? T.yellow : T.text4;
                    return (
                      <tr key={i}>
                        <td style={{ padding: "7px 8px", fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.text1 }}>
                          {t.coin}
                        </td>
                        <td style={{ padding: "7px 8px" }}>
                          <span style={{
                            fontFamily: T.mono, fontSize: 12, fontWeight: 700,
                            padding: "2px 6px", borderRadius: 3,
                            color: t.side === "LONG" ? T.green : T.red,
                            background: `${t.side === "LONG" ? T.green : T.red}15`,
                          }}>
                            {t.side}
                          </span>
                        </td>
                        <td style={{ padding: "7px 8px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text1 }}>
                          {fmt$(t.size_usd)}
                        </td>
                        <td style={{ padding: "7px 8px", textAlign: "right", fontFamily: T.mono, fontSize: 12, color: T.text3 }}>
                          ${(t.entry_px || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: "7px 8px", textAlign: "right", fontFamily: T.mono, fontSize: 12, color: levColor(t.leverage) }}>
                          {t.leverage ? `${t.leverage}x` : "--"}
                        </td>
                        <td style={{
                          padding: "7px 8px", textAlign: "right",
                          fontFamily: T.mono, fontSize: 13, fontWeight: 600,
                          color: (t.pnl || 0) >= 0 ? T.green : T.red,
                        }}>
                          {t.status !== "OPENED" ? (
                            <>{fmtSignedUsd(t.pnl || 0)} <span style={{ fontSize: T.textXs, color: T.text4 }}>({fmtSignedPct(t.pnl_pct || 0, 1)})</span></>
                          ) : (
                            <span style={{ color: T.text4 }}>--</span>
                          )}
                        </td>
                        <td style={{ padding: "7px 8px" }}>
                          <span style={{
                            fontFamily: T.mono, fontSize: T.textXs, fontWeight: 700,
                            color: statusColor,
                          }}>
                            {t.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </>
        )}

        {/* COIN BREAKDOWN */}
        {activeSection === "coins" && (
          <>
            {coinBreakdown.length === 0 ? (
              <div style={{ padding: 24, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
                No coin stats yet — builds as trades are detected
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["COIN", "TRADES", "WINS", "WIN RATE", "PNL"].map(h => (
                      <th key={h} style={{
                        padding: "8px 10px",
                        fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                        color: T.text4, letterSpacing: "0.06em",
                        borderBottom: `1px solid ${T.border}`,
                        textAlign: h === "COIN" ? "left" : "right",
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {coinBreakdown.map((c, i) => (
                    <tr key={i}>
                      <td style={{ padding: "7px 10px", fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.text1 }}>{c.coin}</td>
                      <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text2 }}>{c.trades}</td>
                      <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.green }}>{c.wins}</td>
                      <td style={{ padding: "7px 10px", textAlign: "right" }}>
                        <span style={{
                          fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                          padding: "2px 6px", borderRadius: 3,
                          color: c.win_rate > 50 ? T.green : T.red,
                          background: `${c.win_rate > 50 ? T.green : T.red}15`,
                        }}>
                          {c.win_rate}%
                        </span>
                      </td>
                      <td style={{
                        padding: "7px 10px", textAlign: "right",
                        fontFamily: T.mono, fontSize: 13, fontWeight: 600,
                        color: c.pnl >= 0 ? T.green : T.red,
                      }}>
                        {fmtSignedUsd(c.pnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </GlassCard>
  );
}

// ─── SYMBOL DETAIL MODAL (enhanced) ─────────────────────────────────────────

const fmtPx = (v) => `$${Number(v || 0).toLocaleString(undefined, { maximumFractionDigits: v >= 100 ? 0 : 4 })}`;

function SymbolDetail({ symbol, consensus, onClose, onWalletClick, isMobile }) {
  const [data, setData] = useState(null);
  const [liqClusters, setLiqClusters] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    // Liquidation clusters come from the positions already held in memory; the
    // rest of the old Pressure payload (orders, book walls) is not polled.
    fetch(`${API}/api/hyperlens/pressure?symbol=${encodeURIComponent(symbol)}`)
      .then(r => r.json())
      .then(d => setLiqClusters(d.liquidation_clusters || []))
      .catch(() => setLiqClusters([]));
    fetch(`${API}/api/hyperlens/positions/${symbol}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [symbol]);

  const cData = useMemo(() => {
    return (consensus || []).find(c => c.symbol === symbol) || {};
  }, [consensus, symbol]);

  if (loading) {
    return (
      <GlassCard style={{ padding: 40 }}>
        <div style={{ fontFamily: T.mono, fontSize: 13, color: T.text4, textAlign: "center" }}>Loading...</div>
      </GlassCard>
    );
  }

  const positions = data?.positions || [];
  const longs = positions.filter(p => p.side === "LONG").sort((a, b) => (b.size_usd || 0) - (a.size_usd || 0));
  const shorts = positions.filter(p => p.side === "SHORT").sort((a, b) => (b.size_usd || 0) - (a.size_usd || 0));
  const totalLong = longs.reduce((s, p) => s + (p.size_usd || 0), 0);
  const totalShort = shorts.reduce((s, p) => s + (p.size_usd || 0), 0);
  const totalNotional = totalLong + totalShort;
  const longPct = totalNotional > 0 ? (totalLong / totalNotional * 100) : null;
  const totalLongPnl = longs.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);
  const totalShortPnl = shorts.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);
  const avgLongLev = longs.length > 0 ? longs.reduce((s, p) => s + (p.leverage || 0), 0) / longs.length : 0;
  const avgShortLev = shorts.length > 0 ? shorts.reduce((s, p) => s + (p.leverage || 0), 0) / shorts.length : 0;
  const trend = cData.symbol ? cohortFields(cData, "all").trend : null;

  // Wallet row renderer — shared between long/short columns
  const WalletRow = ({ p }) => (
    <div
      onClick={() => onWalletClick?.(p.address)}
      style={{
        padding: "8px 10px",
        borderBottom: `1px solid ${T.overlay06}`,
        cursor: onWalletClick ? "pointer" : "default",
        transition: "background 0.12s",
        display: "flex", flexDirection: "column", gap: 3,
      }}
      onMouseEnter={e => e.currentTarget.style.background = T.overlay06}
      onMouseLeave={e => e.currentTarget.style.background = "transparent"}
    >
      {/* Row 1: address + size */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span style={{
          fontFamily: T.mono, fontSize: T.textXs, color: T.accent,
          cursor: "pointer", display: "flex", alignItems: "center", gap: 8,
        }}>
          {truncAddr(p.address)}
          {p.wallet_roi != null && (
            <span title="The wallet's 30-day return on the Hyperliquid leaderboard" style={{ color: p.wallet_roi >= 0 ? T.green : T.red }}>
              30d {fmtSignedPct(p.wallet_roi)}
            </span>
          )}
        </span>
        <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.text1 }}>
          {fmt$(p.size_usd)}
        </span>
      </div>
      {/* Row 2: entry + pnl + leverage + distance to liquidation */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>
          @ ${(p.entry_px || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
        </span>
        <div style={{ display: "flex", gap: 8, alignItems: "center", fontFamily: T.mono, fontSize: T.textXs }}>
          <span style={{ fontWeight: 600, color: (p.unrealized_pnl || 0) >= 0 ? T.green : T.red }}>
            {p.pnl_pct != null ? fmtSignedPct(p.pnl_pct, 1) : fmtSignedUsd(p.unrealized_pnl || 0)}
          </span>
          {p.pnl_pct != null && p.unrealized_pnl != null && (
            <span style={{ color: T.text4 }}>
              {fmtSignedUsd(p.unrealized_pnl)}
            </span>
          )}
          <span style={{ color: levColor(p.leverage) }}>
            {p.leverage}x
          </span>
          {/* No liquidation price (e.g. well-collateralised cross margin) shows nothing, not 0% */}
          {p.liq_distance_pct > 0 && (
            <span title="Distance from the current price to the liquidation price" style={{ color: pctColor(p.liq_distance_pct) }}>
              LIQ {p.liq_distance_pct.toFixed(0)}%
            </span>
          )}
        </div>
      </div>
    </div>
  );

  // Side column — longs or shorts
  const SideColumn = ({ side, wallets, total, totalPnl, avgLev, color }) => (
    <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
      {/* Column header */}
      <div style={{
        padding: "12px 12px 10px",
        borderBottom: `2px solid ${color}30`,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
            <span style={{
              fontFamily: T.mono, fontSize: T.textXs, fontWeight: 800, letterSpacing: "0.1em",
              color, textTransform: "uppercase",
            }}>
              {side}
            </span>
            <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>
              {wallets.length} wallet{wallets.length !== 1 ? "s" : ""}
            </span>
          </div>
          <span style={{ fontFamily: T.mono, fontSize: 15, fontWeight: 700, color }}>
            {fmt$(total)}
          </span>
        </div>
        {/* PnL + avg leverage */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{
            fontFamily: T.mono, fontSize: T.textXs, color: T.text4, display: "flex", alignItems: "center", gap: 4,
          }}>
            PNL
            <span style={{ fontWeight: 600, color: totalPnl >= 0 ? T.green : T.red }}>
              {fmtSignedUsd(totalPnl)}
            </span>
          </span>
          <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4, display: "flex", alignItems: "center", gap: 4 }}>
            AVG LEV
            <span style={{ fontWeight: 600, color: levColor(avgLev) }}>{avgLev.toFixed(1)}x</span>
          </span>
        </div>
      </div>
      {/* Wallet list */}
      <div style={{ overflowY: "auto", maxHeight: 420 }}>
        {wallets.map((p, i) => <WalletRow key={i} p={p} />)}
        {wallets.length === 0 && (
          <div style={{ padding: 20, textAlign: "center", fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>
            No {side.toLowerCase()} positions
          </div>
        )}
      </div>
    </div>
  );

  return (
    <GlassCard style={{ padding: 0, overflow: "hidden" }}>
      {/* Header */}
      <div style={{
        padding: isMobile ? "14px 12px" : "16px 20px",
        borderBottom: `1px solid ${T.overlay08}`,
        background: T.overlay02,
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div style={{ width: 3, height: 20, borderRadius: 2, background: T.accent, flexShrink: 0 }} />
          <span style={{ fontFamily: T.mono, fontSize: T.textXl, fontWeight: 700, color: T.text1 }}>
            {symbol}
          </span>
          <span className="terminal-status" style={{
            fontFamily: T.mono, fontSize: T.textSm, color: T.text4, fontWeight: 600,
          }}>
            {positions.length} wallet{positions.length !== 1 ? "s" : ""}
          </span>
          {trend && <TrendCell trend={trend} />}
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          style={{
            width: 30, height: 30, borderRadius: 8,
            border: `1px solid ${T.overlay10}`, background: T.overlay04, color: T.text3,
            fontSize: 14, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            transition: "all 0.15s", flexShrink: 0,
          }}
          onMouseEnter={e => { e.currentTarget.style.background = T.overlay10; e.currentTarget.style.color = T.text1; }}
          onMouseLeave={e => { e.currentTarget.style.background = T.overlay04; e.currentTarget.style.color = T.text3; }}
        >
          {"✕"}
        </button>
      </div>

      {/* Tug-of-war bar — long vs short notional; nothing to draw without positions */}
      {longPct != null && (
        <div style={{ padding: "10px 16px 8px", borderBottom: `1px solid ${T.overlay08}` }}>
          <div style={{
            height: 6, borderRadius: 3, overflow: "hidden",
            background: T.overlay06, display: "flex",
          }}>
            <div style={{
              width: `${longPct}%`, height: "100%",
              background: `linear-gradient(90deg, ${T.green}90, ${T.green}60)`,
              borderRadius: "3px 0 0 3px",
              transition: "width 0.4s ease",
            }} />
            <div style={{
              width: `${100 - longPct}%`, height: "100%",
              background: `linear-gradient(90deg, ${T.red}60, ${T.red}90)`,
              borderRadius: "0 3px 3px 0",
              transition: "width 0.4s ease",
            }} />
          </div>
          <div style={{
            display: "flex", justifyContent: "space-between", marginTop: 4,
          }}>
            <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.green, fontWeight: 600 }}>
              {longPct.toFixed(0)}% LONG
            </span>
            <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.red, fontWeight: 600 }}>
              {(100 - longPct).toFixed(0)}% SHORT
            </span>
          </div>
        </div>
      )}

      {/* Longs | Shorts: side by side on desktop, stacked on a phone */}
      {positions.length > 0 && (
        <div style={{
          display: "flex", flexDirection: isMobile ? "column" : "row",
          borderTop: `1px solid ${T.overlay06}`,
        }}>
          <SideColumn
            side="LONG" wallets={longs} total={totalLong}
            totalPnl={totalLongPnl} avgLev={avgLongLev} color={T.green}
          />
          {!isMobile && <div style={{ width: 1, background: T.overlay10, flexShrink: 0 }} />}
          <SideColumn
            side="SHORT" wallets={shorts} total={totalShort}
            totalPnl={totalShortPnl} avgLev={avgShortLev} color={T.red}
          />
        </div>
      )}

      {/* Liquidation prices within 1% of each other, held by two or more wallets */}
      {liqClusters.length > 0 && (
        <div style={{ padding: "12px 16px", borderTop: `1px solid ${T.overlay08}` }}>
          <div style={{ fontFamily: T.font, fontSize: T.textXs, fontWeight: 700, color: T.text3, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}
            title="Liquidation prices within 1% of each other, shared by two or more tracked wallets">
            Liquidation clusters
          </div>
          {liqClusters.slice(0, 5).map((cl, i) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", padding: "4px 0", fontFamily: T.mono, fontSize: T.textXs, color: T.text2 }}>
              <span>{cl.min_price === cl.max_price ? fmtPx(cl.avg_price) : `${fmtPx(cl.min_price)} to ${fmtPx(cl.max_price)}`}</span>
              <span style={{ color: T.text3 }}>
                {cl.wallet_count} wallets · {fmt$(cl.total_size_usd)} ·{" "}
                <span style={{ color: cl.dominant_side === "LONG" ? T.green : T.red }}>mostly {String(cl.dominant_side).toLowerCase()}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {positions.length === 0 && (
        <div style={{ padding: 24, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
          No positions found for {symbol}
        </div>
      )}
    </GlassCard>
  );
}

// ---------------------------------------------------------------------------
// Favorites / Watchlist tab
// ---------------------------------------------------------------------------

function FavoritesTab({ userWallet, onWalletClick, isMobile }) {
  const [follows, setFollows] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!userWallet) { setLoading(false); return; }
    Promise.all([
      fetch(`${API}/api/hyperlens/follows?user=${userWallet}`).then(r => r.json()),
      fetch(`${API}/api/hyperlens/follows/events?user=${userWallet}&since=0`).then(r => r.json()),
    ])
      .then(([fRes, eRes]) => {
        setFollows(fRes.wallets || []);
        setEvents(eRes.events || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [userWallet]);

  const unfollow = (addr) => {
    fetch(`${API}/api/hyperlens/follows/${addr}?user=${userWallet}`, { method: "DELETE" })
      .then(() => setFollows(f => f.filter(w => w.address !== addr)))
      .catch(() => {});
  };

  if (!userWallet) {
    return (
      <div style={{ padding: "40px 20px", textAlign: "center", fontFamily: T.mono, color: T.text4, fontSize: 13 }}>
        Connect your wallet to use the watchlist.
      </div>
    );
  }

  if (loading) {
    return <div style={{ padding: "40px 20px", textAlign: "center", fontFamily: T.mono, color: T.text4, fontSize: 13 }}>Loading watchlist...</div>;
  }

  if (follows.length === 0) {
    return (
      <div style={{ padding: "40px 20px", textAlign: "center", fontFamily: T.mono, color: T.text4, fontSize: 13 }}>
        No wallets followed yet. Open a wallet profile and choose Follow.
      </div>
    );
  }

  const fmtAddr = (a) => a ? `${a.slice(0, 6)}...${a.slice(-4)}` : "?";
  const fmtUsd = (v) => {
    if (!v) return "$0";
    if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
    if (Math.abs(v) >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
    return `$${v.toFixed(0)}`;
  };

  return (
    <div style={{ padding: isMobile ? 12 : 16 }}>
      {/* Followed wallets */}
      <div style={{ fontSize: T.textXs, fontWeight: 700, color: T.text3, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 12, fontFamily: T.mono }}>
        FOLLOWING {follows.length} WALLET{follows.length !== 1 ? "S" : ""}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "repeat(auto-fill, minmax(280px, 1fr))", gap: 10, marginBottom: 20 }}>
        {follows.map(w => (
          <div key={w.address} style={{
            background: T.overlay02, border: `1px solid ${T.overlay08}`, borderRadius: 10,
            padding: "12px 14px", display: "flex", justifyContent: "space-between", alignItems: "center",
            cursor: "pointer", transition: "all 0.15s",
          }}
            onClick={() => onWalletClick(w.address)}
            onMouseEnter={e => { e.currentTarget.style.borderColor = T.accent; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = T.overlay08; }}
          >
            <div>
              <div style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.accent }}>{fmtAddr(w.address)}</div>
              <div style={{ display: "flex", gap: 8, marginTop: 4, fontFamily: T.mono, fontSize: T.textXs, color: T.text3 }}>
                <span>AV: {fmtUsd(w.account_value)}</span>
                <span>30d ROI: {fmtSignedPct(w.roi)}</span>
                <span>{w.positions_count} pos</span>
              </div>
              {w.cohorts && w.cohorts.some(c => c !== "elite") && (
                <div style={{ marginTop: 4, fontFamily: T.mono, fontSize: T.textXs, color: T.text3 }}>
                  {w.cohorts.filter(c => c !== "elite").map(c => ({ money_printer: "Profitable trader", smart_money: "Large account" }[c] || c)).join(" · ")}
                </div>
              )}
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); unfollow(w.address); }}
              style={{
                background: "none", border: 0, padding: "4px 0",
                fontFamily: T.font, fontSize: T.textSm, fontWeight: 600,
                color: T.text3, cursor: "pointer", flexShrink: 0,
              }}
              onMouseEnter={e => { e.currentTarget.style.color = T.red; }}
              onMouseLeave={e => { e.currentTarget.style.color = T.text3; }}
            >
              Unfollow
            </button>
          </div>
        ))}
      </div>

      {/* Recent trade events */}
      {events.length > 0 && (
        <>
          <div style={{ fontSize: T.textXs, fontWeight: 700, color: T.text3, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 12, fontFamily: T.mono }}>
            RECENT TRADES
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono, fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "6px 8px", fontSize: T.textXs, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>TIME</th>
                  <th style={{ textAlign: "left", padding: "6px 8px", fontSize: T.textXs, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>WALLET</th>
                  <th style={{ textAlign: "left", padding: "6px 8px", fontSize: T.textXs, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>ACTION</th>
                  <th style={{ textAlign: "left", padding: "6px 8px", fontSize: T.textXs, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>COIN</th>
                  <th style={{ textAlign: "right", padding: "6px 8px", fontSize: T.textXs, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>SIZE</th>
                  {!isMobile && <th style={{ textAlign: "right", padding: "6px 8px", fontSize: T.textXs, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>PnL</th>}
                </tr>
              </thead>
              <tbody>
                {events.slice(0, 30).map((ev, i) => {
                  const actionColor = ev.action === "OPENED" ? T.green : ev.action === "CLOSED" ? T.red : T.yellow;
                  const sideColor = ev.side === "LONG" ? T.green : T.red;
                  const ago = ev.timestamp
                    ? (() => {
                        const diff = Date.now() / 1000 - ev.timestamp;
                        if (diff < 3600) return `${Math.round(diff / 60)}m`;
                        if (diff < 86400) return `${(diff / 3600).toFixed(1)}h`;
                        return `${(diff / 86400).toFixed(1)}d`;
                      })()
                    : "—";
                  return (
                    <tr key={`${ev.wallet}-${ev.coin}-${ev.timestamp}-${i}`}
                        style={{ background: i % 2 === 1 ? T.overlay02 : "transparent", cursor: "pointer" }}
                        onClick={() => onWalletClick(ev.wallet)}>
                      <td style={{ padding: "6px 8px", color: T.text4, fontSize: T.textXs, borderBottom: `1px solid ${T.overlay04}` }}>{ago}</td>
                      <td style={{ padding: "6px 8px", color: T.text2, fontSize: T.textXs, fontWeight: 600, borderBottom: `1px solid ${T.overlay04}` }}>{fmtAddr(ev.wallet)}</td>
                      <td style={{ padding: "6px 8px", borderBottom: `1px solid ${T.overlay04}` }}>
                        <span style={{ fontSize: T.textXs, fontWeight: 700, color: actionColor }}>{ev.action}</span>
                      </td>
                      <td style={{ padding: "6px 8px", fontWeight: 700, borderBottom: `1px solid ${T.overlay04}` }}>
                        <span style={{ color: sideColor }}>{ev.side}</span>
                        <span style={{ color: T.text2, marginLeft: 4 }}>{ev.coin}</span>
                        <span style={{ color: T.text4, fontSize: T.textXs, marginLeft: 4 }}>{ev.leverage}x</span>
                      </td>
                      <td style={{ padding: "6px 8px", textAlign: "right", color: T.text3, borderBottom: `1px solid ${T.overlay04}` }}>{fmtUsd(ev.size_usd)}</td>
                      {!isMobile && (
                        <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 600, borderBottom: `1px solid ${T.overlay04}`,
                          color: ev.pnl >= 0 ? T.green : T.red,
                        }}>
                          {ev.action !== "OPENED" ? fmtSignedUsd(ev.pnl) : "—"}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}


// View tabs. Keys are stable; to add a view, add an entry here and a matching
// `tab === key` branch in the panel body.
const VIEW_TABS = [
  { key: "favorites", label: "Watchlist" },
  { key: "consensus", label: "Consensus" },
  { key: "heatmap", label: "Lean", title: "Size-weighted long/short lean per symbol" },
];

function TabSwitcher({ active, onChange }) {
  // Roster tab removed in "Sentiment Mode": same data is on the HL leaderboard.
  // Pressure tab removed: it needs order polling, which stays off.
  return (
    <div className="hl-view-tabs" style={{ minWidth: 0 }}>
      <Tabs label="HyperLens view" items={VIEW_TABS} value={active} onChange={onChange} />
    </div>
  );
}

// ─── COHORT FILTER ──────────────────────────────────────────────────────────

// No "Both" option: the consensus API has no per-symbol figures for wallets in
// both groups, and showing all-wallet numbers under that label would mislead.
const COHORT_OPTIONS = [
  { key: "all", label: "All wallets" },
  { key: "money_printers", label: "Profitable traders", title: "Top 300 by monthly return (at least 30% and $10K) that were also in profit before this month" },
  { key: "smart_money", label: "Large accounts", title: "The 300 largest accounts ($1M and up); profit is not checked" },
];

const BASIS_TITLE = "Wallets updated in the last 75 minutes, with at least $50K in the account and no more than 25 open positions (market makers are left out).";

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PANEL
// ═══════════════════════════════════════════════════════════════════════════════

export default function HyperLensPanel({ isMobile }) {
  const { address: connectedWallet } = useWallet();
  const [tab, setTab] = useState("consensus");
  const [filter, setFilter] = useState("");
  const [cohort, setCohort] = useState("all");
  const [status, setStatus] = useState({});
  const [consensus, setConsensus] = useState([]);
  const [selectedWallet, setSelectedWallet] = useState(null);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      // Consensus rows carry every cohort's figures, so a cohort switch needs no refetch.
      const [statusRes, consensusRes] = await Promise.all([
        fetch(`${API}/api/hyperlens/status`).then(r => r.json()),
        fetch(`${API}/api/hyperlens/consensus`).then(r => r.json()),
      ]);
      setStatus(statusRes);
      setConsensus(consensusRes.consensus || []);
    } catch (err) {
      console.warn("HyperLens fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30_000);
    return () => clearInterval(interval);
  }, [loadData]);

  const counts = trendCounts(consensus, cohort);
  const tracked = status.tracked_wallets || 0;
  const basis = status.consensus_wallets ?? consensus[0]?.total_tracked ?? null;
  const fresh = status.fresh_wallets;
  // Under 60% of wallets updated recently, the summary rests on a partial set.
  const partial = tracked > 0 && fresh != null && fresh < 0.6 * tracked;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Header card */}
      <GlassCard style={{ padding: 0, overflow: "hidden" }}>
        <div style={{
          padding: isMobile ? "12px 12px 10px" : "14px 16px 12px",
          display: "flex", flexDirection: "column", gap: 4,
        }}>
          {consensus.length > 0 && (
            <div
              title={`Symbols with ${MIN_WALLETS} or more wallets positioned, by the size-weighted trend`}
              style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "4px 14px", opacity: partial ? 0.55 : 1 }}
            >
              {[["BULLISH", T.green], ["BEARISH", T.red], ["NEUTRAL", T.text3]].map(([key, color]) => (
                <span key={key} className="terminal-status" style={{
                  fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700,
                  color, letterSpacing: "0.06em",
                }}>
                  {counts[key]} {key}
                </span>
              ))}
              {counts.THIN > 0 && (
                <span style={{ fontFamily: T.font, fontSize: T.textXs, color: T.text4 }}>
                  {counts.THIN} with too few wallets
                </span>
              )}
            </div>
          )}
          {basis != null && tracked > 0 && (
            <div title={BASIS_TITLE} style={{ fontFamily: T.font, fontSize: T.textXs, color: partial ? T.yellow : T.text3 }}>
              Based on {basis} of {tracked} tracked wallets
              {partial && `. Only ${fresh} were updated in the last 75 minutes, so these figures cover a partial set.`}
            </div>
          )}
        </div>

        <StatusStrip status={status} cohort={cohort} />

        {/* Controls bar */}
        <div style={{
          padding: isMobile ? "10px 12px" : "12px 16px",
          display: "flex", alignItems: isMobile ? "stretch" : "center",
          flexDirection: isMobile ? "column" : "row",
          gap: isMobile ? 8 : 10, flexWrap: "wrap",
        }}>
          <TabSwitcher active={tab} onChange={setTab} />
          <Tabs small label="Wallet group" items={COHORT_OPTIONS} value={cohort} onChange={setCohort} />

          {tab === "consensus" && (
            <input
              type="text"
              placeholder="Filter symbol..."
              value={filter}
              onChange={e => setFilter(e.target.value)}
              style={{
                fontFamily: T.mono, fontSize: isMobile ? T.textBase : T.textSm, fontWeight: 500,
                padding: isMobile ? "9px 12px" : "7px 12px", borderRadius: 8,
                border: `1px solid ${T.overlay10}`,
                background: T.overlay04, color: T.text1,
                outline: "none", width: isMobile ? "100%" : 140,
                transition: "all 0.2s ease",
                letterSpacing: "0.03em",
              }}
              onFocus={e => { e.target.style.borderColor = T.accent; e.target.style.boxShadow = `0 0 0 2px ${T.accentDim}`; }}
              onBlur={e => { e.target.style.borderColor = T.overlay10; e.target.style.boxShadow = "none"; }}
            />
          )}
        </div>
      </GlassCard>

      {/* Modals */}
      {selectedWallet && (
        <ModalOverlay onClose={() => setSelectedWallet(null)}>
          <WalletDetail address={selectedWallet} onClose={() => setSelectedWallet(null)} userWallet={connectedWallet} />
        </ModalOverlay>
      )}
      {selectedSymbol && (
        <ModalOverlay onClose={() => setSelectedSymbol(null)}>
          <SymbolDetail
            symbol={selectedSymbol}
            consensus={consensus}
            onClose={() => setSelectedSymbol(null)}
            onWalletClick={(addr) => { setSelectedWallet(addr); setSelectedSymbol(null); }}
            isMobile={isMobile}
          />
        </ModalOverlay>
      )}

      {/* Main content */}
      {loading ? (
        <GlassCard style={{ padding: 0, overflow: "hidden" }}>
          <TableSkeleton rows={10} cols={6} />
        </GlassCard>
      ) : (
        <GlassCard style={{ padding: 0, overflow: "hidden" }}>
          {tab === "favorites" && (
            <FavoritesTab
              userWallet={connectedWallet}
              onWalletClick={(addr) => { setSelectedWallet(addr); setSelectedSymbol(null); }}
              isMobile={isMobile}
            />
          )}
          {tab === "consensus" && (
            <ConsensusTable
              consensus={consensus}
              filter={filter}
              onSymbolClick={(sym) => { setSelectedSymbol(sym); setSelectedWallet(null); }}
              isMobile={isMobile}
              cohort={cohort}
            />
          )}
          {tab === "heatmap" && (
            <HeatmapGrid
              consensus={consensus}
              onSymbolClick={(sym) => { setSelectedSymbol(sym); setSelectedWallet(null); }}
              cohort={cohort}
            />
          )}
        </GlassCard>
      )}
    </div>
  );
}
