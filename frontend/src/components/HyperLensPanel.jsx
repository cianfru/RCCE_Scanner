import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { createPortal } from "react-dom";
import { T } from "../theme.js";
import GlassCard from "./GlassCard.jsx";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── HELPERS ─────────────────────────────────────────────────────────────────

const fmt$ = (v) => {
  if (v == null || isNaN(v)) return "--";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
};

const fmtPct = (v) => {
  if (v == null || isNaN(v)) return "--";
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)}M%`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(0)}K%`;
  return `${v.toFixed(0)}%`;
};

const fmtAge = (seconds) => {
  if (!seconds || seconds <= 0) return "--";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d`;
  return `${Math.floor(seconds / 604800)}w`;
};

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

// Interpolate heatmap color: red (-1) <-> gray (0) <-> green (+1)
const heatmapColor = (ratio) => {
  if (ratio == null) return "rgba(82,82,91,0.3)";
  const clamped = Math.max(-1, Math.min(1, ratio));
  if (clamped > 0) {
    const t = clamped;
    const r = Math.round(82 * (1 - t) + 52 * t);
    const g = Math.round(82 * (1 - t) + 211 * t);
    const b = Math.round(91 * (1 - t) + 153 * t);
    const a = 0.15 + t * 0.35;
    return `rgba(${r},${g},${b},${a})`;
  } else {
    const t = Math.abs(clamped);
    const r = Math.round(82 * (1 - t) + 248 * t);
    const g = Math.round(82 * (1 - t) + 113 * t);
    const b = Math.round(91 * (1 - t) + 113 * t);
    const a = 0.15 + t * 0.35;
    return `rgba(${r},${g},${b},${a})`;
  }
};

const heatmapTextColor = (ratio) => {
  if (ratio == null) return T.text4;
  const clamped = Math.max(-1, Math.min(1, ratio));
  if (Math.abs(clamped) < 0.15) return T.text4;
  return clamped > 0 ? T.green : T.red;
};

// ─── MODAL OVERLAY ───────────────────────────────────────────────────────────

function ModalOverlay({ children, onClose }) {
  return createPortal(
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999,
        background: "rgba(0,0,0,0.65)", backdropFilter: "blur(4px)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div style={{
        width: "100%", maxWidth: 900, maxHeight: "88vh",
        overflowY: "auto",
        borderRadius: 12,
        border: `1px solid ${T.border}`,
        background: T.bg,
        boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
      }}>
        {children}
      </div>
    </div>,
    document.body
  );
}

// ─── SVG: MINI SPARKLINE ────────────────────────────────────────────────────

function MiniSparkline({ data, width = 200, height = 60, color = T.green }) {
  if (!data || data.length < 2) {
    return (
      <div style={{ width, height, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4 }}>No history</span>
      </div>
    );
  }

  const values = data.map(d => d.value ?? d.y ?? d);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = maxV - minV || 1;
  const pad = 4;
  const chartW = width - pad * 2;
  const chartH = height - pad * 2;

  const points = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * chartW;
    const y = pad + chartH - ((v - minV) / range) * chartH;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const linePath = `M${points.join(" L")}`;
  const areaPath = `${linePath} L${(pad + chartW).toFixed(1)},${(pad + chartH).toFixed(1)} L${pad},${(pad + chartH).toFixed(1)} Z`;

  const gradId = `spark-grad-${Math.random().toString(36).slice(2, 8)}`;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradId})`} />
      <path d={linePath} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
      {/* Endpoint dot */}
      {points.length > 0 && (() => {
        const last = points[points.length - 1].split(",");
        return <circle cx={last[0]} cy={last[1]} r="2.5" fill={color} />;
      })()}
    </svg>
  );
}

// ─── SVG: LEVERAGE GAUGE ────────────────────────────────────────────────────

function LeverageGauge({ value, size = 64 }) {
  const v = value ?? 0;
  const cx = size / 2;
  const cy = size / 2 + 4;
  const r = size / 2 - 6;
  const startAngle = Math.PI;
  const maxAngle = Math.PI;
  const maxLev = 50;
  const clamped = Math.min(v, maxLev);
  const ratio = clamped / maxLev;
  const needleAngle = startAngle + ratio * maxAngle;

  // Arc segments: green 0-5x, yellow 5-15x, red 15-50x
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

  const nx = cx + (r - 8) * Math.cos(needleAngle);
  const ny = cy + (r - 8) * Math.sin(needleAngle);

  return (
    <svg width={size} height={size / 2 + 12} viewBox={`0 0 ${size} ${size / 2 + 12}`}>
      <path d={arcPath(0, 5)} fill="none" stroke={T.green} strokeWidth="3" strokeLinecap="round" opacity="0.6" />
      <path d={arcPath(5, 15)} fill="none" stroke={T.yellow} strokeWidth="3" strokeLinecap="round" opacity="0.6" />
      <path d={arcPath(15, 50)} fill="none" stroke={T.red} strokeWidth="3" strokeLinecap="round" opacity="0.6" />
      {/* Needle */}
      <line x1={cx} y1={cy} x2={nx.toFixed(1)} y2={ny.toFixed(1)}
        stroke={levColor(v)} strokeWidth="2" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="3" fill={levColor(v)} />
      <text x={cx} y={cy + 10} textAnchor="middle" fill={T.text1}
        fontFamily={T.mono} fontSize="11" fontWeight="700">
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
    <span style={{
      fontFamily: T.mono, fontSize: 11, fontWeight: 700,
      padding: "2px 7px", borderRadius: 4,
      color, background: `${color}18`,
      border: `1px solid ${color}30`,
      letterSpacing: "0.03em",
    }}>
      RISK {Math.round(score)}
    </span>
  );
}

// ─── CONFIDENCE BAR ─────────────────────────────────────────────────────────

function ConfidenceBar({ confidence, trend }) {
  const pct = Math.max(0, Math.min(1, confidence || 0)) * 100;
  const color = trend === "BULLISH" ? T.green : trend === "BEARISH" ? T.red : T.text4;
  return (
    <div style={{
      width: "100%", height: 2, borderRadius: 1,
      background: T.overlay06, marginTop: 2,
    }}>
      <div style={{
        width: `${pct}%`, height: "100%", borderRadius: 1,
        background: color,
        transition: "width 0.4s ease",
      }} />
    </div>
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
      <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text3, textAlign: "center" }}>
        {fmt$(total)}
      </span>
    </div>
  );
}

// ─── SORTABLE TABLE HEADER ──────────────────────────────────────────────────

function SortTh({ label, sortKey, currentKey, asc, onSort, align = "right", w }) {
  const active = currentKey === sortKey;
  return (
    <th
      onClick={sortKey ? () => onSort(sortKey) : undefined}
      style={{
        padding: "8px 10px", textAlign: align,
        fontFamily: T.mono, fontSize: 12, fontWeight: 600,
        color: active ? T.accent : T.text4,
        letterSpacing: "0.06em",
        cursor: sortKey ? "pointer" : "default",
        borderBottom: `1px solid ${T.border}`,
        whiteSpace: "nowrap", minWidth: w,
        userSelect: "none",
      }}
    >
      {label}{active && (asc ? " \u25B2" : " \u25BC")}
    </th>
  );
}

// ─── STATUS STRIP ────────────────────────────────────────────────────────────

function StatusStrip({ status, cohort, roster }) {
  // Compute cohort counts from roster data
  const mpCount = roster.filter(w => (w.cohorts || []).includes("money_printer")).length;
  const smCount = roster.filter(w => (w.cohorts || []).includes("smart_money")).length;
  const eliteCount = roster.filter(w =>
    (w.cohorts || []).includes("money_printer") && (w.cohorts || []).includes("smart_money")
  ).length;

  const walletLabel = cohort === "all"
    ? (status.tracked_wallets || 0)
    : cohort === "money_printers" ? mpCount
    : cohort === "smart_money" ? smCount
    : cohort === "elite" ? eliteCount
    : (status.tracked_wallets || 0);

  const items = [
    { label: "WALLETS", value: walletLabel },
    { label: "WITH DATA", value: status.wallets_with_data || 0 },
    { label: "SYMBOLS", value: status.consensus_symbols || 0 },
    { label: "POLLS", value: status.poll_count || 0 },
    { label: "LAST POLL", value: timeAgo(status.last_poll) },
  ];

  return (
    <div style={{
      display: "flex", flexWrap: "wrap", gap: 6,
      padding: "10px 16px",
      borderBottom: `1px solid ${T.border}`,
    }}>
      {items.map(({ label, value }) => (
        <div key={label} style={{
          display: "flex", alignItems: "center", gap: 6,
          padding: "3px 9px", borderRadius: 6,
          background: T.overlay04, border: `1px solid ${T.overlay06}`,
        }}>
          <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4, letterSpacing: "0.05em" }}>{label}</span>
          <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.text1 }}>{value}</span>
        </div>
      ))}
      {/* Cohort breakdown counts */}
      {cohort === "all" && (mpCount > 0 || smCount > 0 || eliteCount > 0) && (
        <div style={{
          display: "flex", alignItems: "center", gap: 4,
          padding: "3px 9px", borderRadius: 6,
          background: T.overlay04, border: `1px solid ${T.overlay06}`,
        }}>
          {mpCount > 0 && (
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.green }}>{mpCount} MP</span>
          )}
          {mpCount > 0 && smCount > 0 && (
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4 }}>|</span>
          )}
          {smCount > 0 && (
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.accent }}>{smCount} SM</span>
          )}
          {smCount > 0 && eliteCount > 0 && (
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4 }}>|</span>
          )}
          {eliteCount > 0 && (
            <span style={{ fontFamily: T.mono, fontSize: 11, color: T.yellow }}>{eliteCount} Elite</span>
          )}
        </div>
      )}
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{
          width: 6, height: 6, borderRadius: "50%",
          background: status.initialized ? T.green : T.yellow,
          animation: status.initialized ? "pulse 2s ease-in-out infinite" : "none",
        }} />
        <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4 }}>
          {status.initialized ? "LIVE" : "WARMING UP"}
        </span>
      </div>
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
      <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4, whiteSpace: "nowrap", minWidth: 34, textAlign: "right" }}>
        {long_count}/{short_count}
      </span>
    </div>
  );
}

// ─── CONSENSUS TABLE (enhanced) ─────────────────────────────────────────────

// Helper to extract cohort-specific fields from a consensus entry
function getCohortFields(c, cohort) {
  if (cohort === "money_printers") {
    return {
      long_count: c.money_printer_long_count ?? c.long_count,
      short_count: c.money_printer_short_count ?? c.short_count,
      net_ratio: c.money_printer_net_ratio ?? c.net_ratio,
      trend: c.money_printer_trend ?? c.trend,
    };
  }
  if (cohort === "smart_money") {
    return {
      long_count: c.smart_money_long_count ?? c.long_count,
      short_count: c.smart_money_short_count ?? c.short_count,
      net_ratio: c.smart_money_net_ratio ?? c.net_ratio,
      trend: c.smart_money_trend ?? c.trend,
    };
  }
  // "all" or "elite" — use aggregate fields
  return {
    long_count: c.long_count,
    short_count: c.short_count,
    net_ratio: c.net_ratio,
    trend: c.trend,
  };
}

function ConsensusTable({ consensus, filter, onSymbolClick, isMobile, cohort }) {
  const [sortKey, setSortKey] = useState("positioned");
  const [sortAsc, setSortAsc] = useState(false);

  const maxNotional = useMemo(() => {
    return Math.max(...consensus.map(c => (c.long_notional || 0) + (c.short_notional || 0)), 1);
  }, [consensus]);

  const filtered = useMemo(() => {
    let items = [...consensus];
    if (filter) {
      const q = filter.toUpperCase();
      items = items.filter(c => c.symbol.includes(q));
    }
    items.sort((a, b) => {
      const aF = getCohortFields(a, cohort);
      const bF = getCohortFields(b, cohort);
      let va, vb;
      switch (sortKey) {
        case "symbol": va = a.symbol; vb = b.symbol; return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        case "trend": va = aF.trend; vb = bF.trend; return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        case "long": va = aF.long_count; vb = bF.long_count; break;
        case "short": va = aF.short_count; vb = bF.short_count; break;
        case "notional": va = (a.long_notional || 0) + (a.short_notional || 0); vb = (b.long_notional || 0) + (b.short_notional || 0); break;
        case "net": va = aF.net_ratio; vb = bF.net_ratio; break;
        case "confidence": va = a.confidence || 0; vb = b.confidence || 0; break;
        case "leverage": va = a.avg_leverage || 0; vb = b.avg_leverage || 0; break;
        default: va = aF.long_count + aF.short_count; vb = bF.long_count + bF.short_count;
      }
      return sortAsc ? va - vb : vb - va;
    });
    return items;
  }, [consensus, filter, sortKey, sortAsc, cohort]);

  const handleSort = (key) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <SortTh label="SYMBOL" sortKey="symbol" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="left" w={70} />
            <SortTh label="TREND" sortKey="trend" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={72} />
            <SortTh label="WALLETS" sortKey="positioned" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={56} />
            <th style={{ padding: "8px 10px", fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.text4, letterSpacing: "0.06em", borderBottom: `1px solid ${T.border}`, minWidth: isMobile ? 90 : 130 }}>L / S</th>
            <SortTh label="NET" sortKey="net" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={48} />
            <SortTh label="CONF" sortKey="confidence" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={48} />
            {!isMobile && (
              <>
                <SortTh label="AVG LEV" sortKey="leverage" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={60} />
                <SortTh label="NOTIONAL" sortKey="notional" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={90} />
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {filtered.map((c) => {
            const cf = getCohortFields(c, cohort);
            const positioned = cf.long_count + cf.short_count;
            return (
              <tr
                key={c.symbol}
                onClick={() => onSymbolClick?.(c.symbol)}
                style={{ cursor: "pointer", transition: "background 0.15s" }}
                onMouseEnter={e => e.currentTarget.style.background = T.overlay06}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}
              >
                <td style={{ padding: "6px 10px" }}>
                  <div style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.text1 }}>
                    {c.symbol}
                  </div>
                  <ConfidenceBar confidence={c.confidence} trend={cf.trend} />
                </td>
                <td style={{ padding: "6px 10px", textAlign: "center" }}>
                  <span style={{
                    fontFamily: T.mono, fontSize: 12, fontWeight: 700,
                    padding: "2px 8px", borderRadius: 4,
                    color: trendColor(cf.trend),
                    background: `${trendColor(cf.trend)}15`,
                    border: `1px solid ${trendColor(cf.trend)}25`,
                  }}>
                    {cf.trend}
                  </span>
                </td>
                <td style={{ padding: "6px 10px", textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text2 }}>
                  {positioned}
                </td>
                <td style={{ padding: "6px 10px" }}>
                  <ConsensusBar long_count={cf.long_count} short_count={cf.short_count} />
                </td>
                <td style={{
                  padding: "6px 10px", textAlign: "center",
                  fontFamily: T.mono, fontSize: 13, fontWeight: 600,
                  color: cf.net_ratio > 0.1 ? T.green : cf.net_ratio < -0.1 ? T.red : T.text3,
                }}>
                  {cf.net_ratio > 0 ? "+" : ""}{(cf.net_ratio * 100).toFixed(0)}%
                </td>
                <td style={{
                  padding: "6px 10px", textAlign: "center",
                  fontFamily: T.mono, fontSize: 12, color: T.text3,
                }}>
                  {c.confidence != null ? `${(c.confidence * 100).toFixed(0)}%` : "--"}
                </td>
                {!isMobile && (
                  <>
                    <td style={{
                      padding: "6px 10px", textAlign: "center",
                      fontFamily: T.mono, fontSize: 12,
                      color: levColor(c.avg_leverage),
                    }}>
                      {c.avg_leverage ? fmtLev(c.avg_leverage) : "--"}
                    </td>
                    <td style={{ padding: "6px 10px" }}>
                      <NotionalBar long_notional={c.long_notional} short_notional={c.short_notional} maxNotional={maxNotional} />
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

// ─── HEATMAP TAB ────────────────────────────────────────────────────────────

function HeatmapGrid({ consensus, onSymbolClick, cohort }) {
  const sorted = useMemo(() => {
    return [...consensus].sort((a, b) => {
      const aF = getCohortFields(a, cohort);
      const bF = getCohortFields(b, cohort);
      return (bF.long_count + bF.short_count) - (aF.long_count + aF.short_count);
    });
  }, [consensus, cohort]);

  if (sorted.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
        Waiting for consensus data...
      </div>
    );
  }

  // Bias categories
  const categories = [
    { key: "strong_bull", label: "STRONG BULL", test: (r) => r > 0.6 },
    { key: "bull", label: "BULLISH", test: (r) => r > 0.2 && r <= 0.6 },
    { key: "neutral", label: "NEUTRAL", test: (r) => r >= -0.2 && r <= 0.2 },
    { key: "bear", label: "BEARISH", test: (r) => r < -0.2 && r >= -0.6 },
    { key: "strong_bear", label: "STRONG BEAR", test: (r) => r < -0.6 },
  ];

  return (
    <div style={{ overflowX: "auto", padding: "8px 0" }}>
      {/* Column headers */}
      <div style={{
        display: "grid",
        gridTemplateColumns: `80px repeat(${categories.length}, 1fr)`,
        gap: 2, padding: "0 12px", marginBottom: 4,
      }}>
        <div />
        {categories.map(cat => (
          <div key={cat.key} style={{
            fontFamily: T.mono, fontSize: 10, fontWeight: 600,
            color: T.text4, textAlign: "center",
            letterSpacing: "0.06em", padding: "4px 2px",
          }}>
            {cat.label}
          </div>
        ))}
      </div>

      {/* Symbol rows */}
      {sorted.map((c) => {
        const cf = getCohortFields(c, cohort);
        const ratio = cf.net_ratio || 0;
        return (
          <div
            key={c.symbol}
            onClick={() => onSymbolClick?.(c.symbol)}
            style={{
              display: "grid",
              gridTemplateColumns: `80px repeat(${categories.length}, 1fr)`,
              gap: 2, padding: "1px 12px",
              cursor: "pointer",
              transition: "background 0.15s",
            }}
            onMouseEnter={e => e.currentTarget.style.background = T.overlay04}
            onMouseLeave={e => e.currentTarget.style.background = "transparent"}
          >
            {/* Symbol label */}
            <div style={{
              fontFamily: T.mono, fontSize: 12, fontWeight: 600,
              color: T.text1, padding: "6px 4px",
              display: "flex", alignItems: "center",
            }}>
              {c.symbol}
            </div>
            {/* Category cells */}
            {categories.map(cat => {
              const isActive = cat.test(ratio);
              return (
                <div key={cat.key} style={{
                  background: isActive ? heatmapColor(ratio) : T.overlay03,
                  borderRadius: 4, padding: "6px 4px",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  transition: "background 0.3s",
                  border: isActive ? `1px solid ${heatmapTextColor(ratio)}20` : "1px solid transparent",
                }}>
                  {isActive && (
                    <span style={{
                      fontFamily: T.mono, fontSize: 11, fontWeight: 700,
                      color: heatmapTextColor(ratio),
                    }}>
                      {ratio > 0 ? "+" : ""}{(ratio * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

// ─── ROSTER TABLE (enhanced) ────────────────────────────────────────────────

function RosterTable({ wallets, consensus, onWalletClick, isMobile, cohort }) {
  const [sortKey, setSortKey] = useState("rank");
  const [sortAsc, setSortAsc] = useState(true);

  // Build wallet bias from consensus top_longs/top_shorts
  const walletBias = useMemo(() => {
    const bias = {};
    for (const c of consensus) {
      for (const addr of (c.top_longs || [])) {
        if (!bias[addr]) bias[addr] = { longs: 0, shorts: 0 };
        bias[addr].longs++;
      }
      for (const addr of (c.top_shorts || [])) {
        if (!bias[addr]) bias[addr] = { longs: 0, shorts: 0 };
        bias[addr].shorts++;
      }
    }
    return bias;
  }, [consensus]);

  const sorted = useMemo(() => {
    let items = [...wallets];
    // Client-side cohort filtering
    if (cohort === "money_printers") {
      items = items.filter(w => (w.cohorts || []).includes("money_printer"));
    } else if (cohort === "smart_money") {
      items = items.filter(w => (w.cohorts || []).includes("smart_money"));
    } else if (cohort === "elite") {
      items = items.filter(w =>
        (w.cohorts || []).includes("money_printer") && (w.cohorts || []).includes("smart_money")
      );
    }
    items.sort((a, b) => {
      let va, vb;
      switch (sortKey) {
        case "rank": va = a.rank; vb = b.rank; break;
        case "av": va = a.account_value; vb = b.account_value; break;
        case "roi": va = a.roi; vb = b.roi; break;
        case "score": va = a.score; vb = b.score; break;
        case "positions": va = a.position_count; vb = b.position_count; break;
        default: va = a.rank; vb = b.rank;
      }
      return sortAsc ? va - vb : vb - va;
    });
    return items;
  }, [wallets, sortKey, sortAsc, cohort]);

  const handleSort = (key) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(key === "rank"); }
  };

  const getBias = (addr) => {
    const b = walletBias[addr];
    if (!b) return null;
    if (b.longs > 0 && b.shorts > 0) return "MIXED";
    if (b.longs > 0) return "LONG";
    if (b.shorts > 0) return "SHORT";
    return null;
  };

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <SortTh label="#" sortKey="rank" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="left" w={36} />
            <th style={{ padding: "8px 10px", fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.text4, letterSpacing: "0.06em", borderBottom: `1px solid ${T.border}`, minWidth: 100, textAlign: "left" }}>WALLET</th>
            <SortTh label="ACCT VALUE" sortKey="av" currentKey={sortKey} asc={sortAsc} onSort={handleSort} w={90} />
            <SortTh label="ROI" sortKey="roi" currentKey={sortKey} asc={sortAsc} onSort={handleSort} w={70} />
            {!isMobile && (
              <>
                <SortTh label="SCORE" sortKey="score" currentKey={sortKey} asc={sortAsc} onSort={handleSort} w={56} />
                <th style={{ padding: "8px 10px", fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.text4, letterSpacing: "0.06em", borderBottom: `1px solid ${T.border}`, minWidth: 50, textAlign: "center" }}>BIAS</th>
                <SortTh label="POS" sortKey="positions" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={44} />
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {sorted.map((w) => {
            const bias = getBias(w.address);
            const biasColor = bias === "LONG" ? T.green : bias === "SHORT" ? T.red : bias === "MIXED" ? T.yellow : T.text4;
            return (
              <tr
                key={w.address}
                onClick={() => onWalletClick?.(w.address)}
                style={{ cursor: "pointer", transition: "background 0.15s" }}
                onMouseEnter={e => e.currentTarget.style.background = T.overlay06}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}
              >
                <td style={{ padding: "7px 10px", fontFamily: T.mono, fontSize: 13, color: T.text4, textAlign: "left" }}>
                  {w.rank}
                </td>
                <td style={{ padding: "7px 10px", textAlign: "left" }}>
                  <span style={{
                    fontFamily: T.mono, fontSize: 13, color: T.accent,
                    textDecoration: "underline", textDecorationColor: "rgba(99,179,237,0.35)",
                    textUnderlineOffset: 3, cursor: "pointer",
                  }}>
                    {truncAddr(w.address)} {"\u2192"}
                  </span>
                  {w.display_name && (
                    <span style={{ fontFamily: T.font, fontSize: 12, color: T.text4, marginLeft: 6 }}>
                      {w.display_name.length > 12 ? w.display_name.slice(0, 12) + "..." : w.display_name}
                    </span>
                  )}
                  {/* Cohort badges */}
                  {(w.cohorts || []).length > 0 && (
                    <span style={{ marginLeft: 6, display: "inline-flex", gap: 3 }}>
                      {(w.cohorts || []).includes("money_printer") && (
                        <span style={{
                          fontSize: 10, padding: "1px 4px", borderRadius: 4,
                          color: T.green, background: `${T.green}15`,
                          fontFamily: T.mono, fontWeight: 600,
                        }}>{"\uD83D\uDCB0"}</span>
                      )}
                      {(w.cohorts || []).includes("smart_money") && (
                        <span style={{
                          fontSize: 10, padding: "1px 4px", borderRadius: 4,
                          color: T.accent, background: `${T.accent}15`,
                          fontFamily: T.mono, fontWeight: 600,
                        }}>{"\uD83D\uDC0B"}</span>
                      )}
                    </span>
                  )}
                </td>
                <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, fontWeight: 500, color: T.text1 }}>
                  {fmt$(w.account_value)}
                </td>
                <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.green }}>
                  {fmtPct(w.roi)}
                </td>
                {!isMobile && (
                  <>
                    <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text3 }}>
                      {(w.score || 0).toFixed(0)}
                    </td>
                    <td style={{ padding: "7px 10px", textAlign: "center" }}>
                      {bias ? (
                        <span style={{
                          fontFamily: T.mono, fontSize: 11, fontWeight: 700,
                          padding: "2px 6px", borderRadius: 3,
                          color: biasColor, background: `${biasColor}15`,
                        }}>
                          {bias}
                        </span>
                      ) : (
                        <span style={{ color: T.text4, fontFamily: T.mono, fontSize: 11 }}>--</span>
                      )}
                    </td>
                    <td style={{ padding: "7px 10px", textAlign: "center" }}>
                      {w.position_count > 0 ? (
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 3 }}>
                          <span style={{
                            fontFamily: T.mono, fontSize: 12, fontWeight: 700,
                            display: "inline-flex", alignItems: "center", justifyContent: "center",
                            width: 22, height: 22, borderRadius: "50%",
                            color: T.text1,
                            background: w.position_count >= 5 ? `${T.accent}20` : T.overlay08,
                            border: `1px solid ${w.position_count >= 5 ? T.accent : T.border}40`,
                          }}>
                            {w.position_count}
                          </span>
                          {w.tradfi_position_count > 0 && (
                            <span style={{
                              fontFamily: T.mono, fontSize: 9, fontWeight: 700,
                              padding: "1px 3px", borderRadius: 3,
                              color: "#F59E0B", background: "#F59E0B18",
                            }}>
                              +{w.tradfi_position_count} TF
                            </span>
                          )}
                        </div>
                      ) : (
                        <span style={{ color: T.text4, fontFamily: T.mono, fontSize: 12 }}>0</span>
                      )}
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ─── STAT PILL ───────────────────────────────────────────────────────────────

function StatPill({ label, value, color }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      padding: "7px 12px", borderRadius: 8,
      background: T.overlay04, border: `1px solid ${T.overlay06}`,
      minWidth: 64,
    }}>
      <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, letterSpacing: "0.06em", marginBottom: 2 }}>
        {label}
      </span>
      <span style={{ fontFamily: T.mono, fontSize: 14, fontWeight: 700, color: color || T.text1 }}>
        {value}
      </span>
    </div>
  );
}

// ─── WALLET PROFILE MODAL (major upgrade) ───────────────────────────────────

// ─── EQUITY CHART (full-width SVG like HyperTracker) ───────────────────────

function EquityChart({ data, width = 500, height = 120 }) {
  const containerRef = useRef(null);
  const [cw, setCw] = useState(width);
  useEffect(() => {
    if (containerRef.current) setCw(containerRef.current.offsetWidth);
  }, []);

  if (!data || data.length < 2) {
    return (
      <div ref={containerRef} style={{ width: "100%", height, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4 }}>Collecting equity data...</span>
      </div>
    );
  }

  const values = data.map(d => d.value ?? d);
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = maxV - minV || 1;
  const pad = { top: 8, right: 8, bottom: 20, left: 50 };
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

  // Y-axis labels
  const yLabels = [maxV, (maxV + minV) / 2, minV];

  return (
    <div ref={containerRef} style={{ width: "100%" }}>
      <svg width={cw} height={height} viewBox={`0 0 ${cw} ${height}`} style={{ display: "block" }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.2" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0.01" />
          </linearGradient>
        </defs>
        {/* Grid lines */}
        {yLabels.map((v, i) => {
          const y = pad.top + chartH - ((v - minV) / range) * chartH;
          return (
            <g key={i}>
              <line x1={pad.left} y1={y} x2={cw - pad.right} y2={y}
                stroke={T.border} strokeWidth="0.5" strokeDasharray="3,3" />
              <text x={pad.left - 4} y={y + 3} textAnchor="end" fill={T.text4}
                fontFamily={T.mono} fontSize="9">{fmt$(v)}</text>
            </g>
          );
        })}
        <path d={areaPath} fill={`url(#${gradId})`} />
        <path d={linePath} fill="none" stroke={lineColor} strokeWidth="1.5" strokeLinejoin="round" />
        {/* Endpoint dot */}
        <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="3" fill={lineColor} />
        {/* Latest value label */}
        <text x={points[points.length - 1].x} y={points[points.length - 1].y - 8}
          textAnchor="end" fill={lineColor} fontFamily={T.mono} fontSize="10" fontWeight="700">
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
      padding: "10px 14px", borderRadius: 8,
      background: T.overlay04, border: `1px solid ${T.overlay06}`,
      display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
      minWidth: 110,
    }}>
      <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, letterSpacing: "0.06em" }}>PERP BIAS</span>
      <span style={{ fontFamily: T.mono, fontSize: 14, fontWeight: 700, color: biasColor, fontStyle: "italic" }}>
        {biasLabel}
      </span>
      {/* Mini long/short bar */}
      <div style={{ width: 90, height: 4, borderRadius: 2, background: T.overlay06, overflow: "hidden", display: "flex" }}>
        <div style={{ width: `${(longVal / total) * 100}%`, height: "100%", background: T.green }} />
        <div style={{ width: `${(shortVal / total) * 100}%`, height: "100%", background: T.red }} />
      </div>
      <span style={{ fontFamily: T.mono, fontSize: 9, color: T.text4 }}>
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
      <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 600, color, minWidth: 32, textAlign: "right" }}>
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

// ─── WALLET TAG BADGES (derived like HyperTracker's Leviathan/Money Printer) ─

function WalletTags({ data }) {
  const tags = [];
  const av = data.account_value || 0;
  const roi = data.monthly_roi || 0;
  if (av >= 10e6) tags.push({ label: "Leviathan", color: "#a78bfa", emoji: "\ud83d\udc0b" });
  else if (av >= 1e6) tags.push({ label: "Whale", color: "#60a5fa", emoji: "\ud83d\udc33" });
  else if (av >= 100e3) tags.push({ label: "Dolphin", color: "#67e8f9", emoji: "\ud83d\udc2c" });
  if (roi >= 100) tags.push({ label: "Money Printer", color: T.green, emoji: "\ud83d\udcb0" });
  else if (roi >= 50) tags.push({ label: "Consistent", color: T.yellow, emoji: "\u2b50" });
  if (tags.length === 0) return null;
  return (
    <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
      {tags.map(t => (
        <span key={t.label} style={{
          fontFamily: T.mono, fontSize: 11, fontWeight: 600,
          padding: "2px 8px", borderRadius: 12,
          color: t.color, background: `${t.color}15`,
          border: `1px solid ${t.color}30`,
        }}>
          {t.emoji} {t.label}
        </span>
      ))}
    </div>
  );
}

// ─── WALLET PROFILE MODAL (HyperTracker-style layout) ──────────────────────

function WalletDetail({ address, onClose }) {
  const [data, setData] = useState(null);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState("positions");

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
    <GlassCard style={{ padding: 0 }}>
      {/* ── HEADER ROW ── */}
      <div style={{
        padding: "14px 16px 10px",
        borderBottom: `1px solid ${T.border}`,
        display: "flex", alignItems: "flex-start", justifyContent: "space-between",
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontFamily: T.mono, fontSize: 16, fontWeight: 700, color: T.accent }}>
              {truncAddr(address)}
            </span>
            {data.rank && (
              <span style={{
                fontFamily: T.mono, fontSize: 11, fontWeight: 700,
                padding: "2px 7px", borderRadius: 4,
                color: T.accent, background: `${T.accent}15`, border: `1px solid ${T.accent}25`,
              }}>
                #{data.rank}
              </span>
            )}
            <RiskBadge score={data.risk_score} />
          </div>
          {/* Full address + copy + snaps */}
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
            <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, opacity: 0.5 }}>
              {data.snapshot_count} snaps
            </span>
            <span
              style={{
                fontFamily: T.mono, fontSize: 10, color: T.text4,
                cursor: "pointer", userSelect: "all", wordBreak: "break-all",
              }}
              title="Click to copy"
              onClick={(e) => {
                e.stopPropagation();
                navigator.clipboard.writeText(address);
                const el = e.currentTarget;
                el.style.color = T.green;
                setTimeout(() => el.style.color = T.text4, 1200);
              }}
            >
              {address} \u2398
            </span>
          </div>
          {/* Tags */}
          <div style={{ marginTop: 6 }}>
            <WalletTags data={data} />
          </div>
        </div>
        <button
          onClick={onClose}
          style={{
            width: 28, height: 28, borderRadius: 6,
            border: `1px solid ${T.border}`, background: T.surface, color: T.text3,
            fontSize: 15, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}
        >
          {"\u2715"}
        </button>
      </div>

      {/* ── TWO-PANEL: LEFT (equity + gauges) + RIGHT (chart) ── */}
      <div style={{
        display: "flex", flexWrap: "wrap",
        borderBottom: `1px solid ${T.border}`,
      }}>
        {/* LEFT PANEL — Equity + Gauges */}
        <div style={{
          flex: "0 0 240px", padding: "14px 16px",
          borderRight: `1px solid ${T.border}`,
          display: "flex", flexDirection: "column", gap: 10,
        }}>
          {/* Total Equity + PnL */}
          <div>
            <div style={{ fontFamily: T.mono, fontSize: 22, fontWeight: 700, color: T.text1 }}>
              {fmt$(data.account_value || 0)}
            </div>
            <div style={{ fontFamily: T.mono, fontSize: 11, color: T.text4, letterSpacing: "0.05em", marginBottom: 4 }}>
              Total Equity
            </div>
            {/* Unrealized PnL */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span style={{
                fontFamily: T.mono, fontSize: 15, fontWeight: 700,
                color: sumPnl >= 0 ? T.green : T.red,
              }}>
                {sumPnl >= 0 ? "+" : ""}{fmt$(sumPnl)}
              </span>
              {data.account_value > 0 && (
                <span style={{
                  fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  color: sumPnl >= 0 ? T.green : T.red, opacity: 0.7,
                }}>
                  {sumPnl >= 0 ? "+" : ""}{((sumPnl / data.account_value) * 100).toFixed(2)}%
                </span>
              )}
            </div>
            <div style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, letterSpacing: "0.05em" }}>
              Unrealized PnL
            </div>
          </div>

          {/* Bias + Leverage gauges side by side */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <BiasGauge positions={positions} />
            <div style={{
              padding: "10px 14px", borderRadius: 8,
              background: T.overlay04, border: `1px solid ${T.overlay06}`,
              display: "flex", flexDirection: "column", alignItems: "center",
              minWidth: 80,
            }}>
              <LeverageGauge value={levStats.avg_leverage} size={72} />
              <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, letterSpacing: "0.06em", marginTop: -2 }}>
                Leverage
              </span>
            </div>
          </div>

          {/* PNL + ROI stats */}
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4 }}>Monthly ROI</span>
              <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.green }}>
                +{fmtPct(data.monthly_roi || 0)}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4 }}>Monthly PnL</span>
              <span style={{
                fontFamily: T.mono, fontSize: 13, fontWeight: 700,
                color: (data.monthly_pnl || 0) >= 0 ? T.green : T.red,
              }}>
                {(data.monthly_pnl || 0) >= 0 ? "+" : ""}{fmt$(data.monthly_pnl || 0)}
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4 }}>Score</span>
              <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.text1 }}>
                {(data.score || 0).toFixed(0)}
              </span>
            </div>
            {s.total_trades > 0 && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4 }}>Win Rate</span>
                  <span style={{
                    fontFamily: T.mono, fontSize: 13, fontWeight: 600,
                    color: s.win_rate > 50 ? T.green : T.red,
                  }}>
                    {s.win_rate}% ({s.wins}/{s.total_trades})
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4 }}>Avg PnL</span>
                  <span style={{
                    fontFamily: T.mono, fontSize: 13, fontWeight: 600,
                    color: s.avg_pnl_pct > 0 ? T.green : s.avg_pnl_pct < 0 ? T.red : T.text4,
                  }}>
                    {s.avg_pnl_pct > 0 ? "+" : ""}{s.avg_pnl_pct}%
                  </span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* RIGHT PANEL — Full equity chart */}
        <div style={{ flex: 1, minWidth: 280, padding: "10px 8px 6px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "0 8px 4px", flexWrap: "wrap" }}>
            <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, letterSpacing: "0.06em" }}>
              EQUITY CURVE
            </span>
            {avHistory.length >= 2 && (() => {
              const first = avHistory[0]?.value ?? avHistory[0];
              const last = avHistory[avHistory.length - 1]?.value ?? avHistory[avHistory.length - 1];
              const pnl = last - first;
              const pctChg = first > 0 ? ((pnl / first) * 100) : 0;
              const color = pnl >= 0 ? T.green : T.red;
              return (
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontFamily: T.mono, fontSize: 16, fontWeight: 700, color }}>
                    {pctChg >= 0 ? "+" : ""}{pctChg.toFixed(2)}%
                  </div>
                  <div style={{ fontFamily: T.mono, fontSize: 11, color, opacity: 0.7 }}>
                    {pnl >= 0 ? "+" : ""}{fmt$(pnl)}
                  </div>
                  <div style={{ fontFamily: T.mono, fontSize: 9, color: T.text4 }}>
                    since tracking
                  </div>
                </div>
              );
            })()}
          </div>
          <EquityChart data={avHistory} height={130} />
        </div>
      </div>

      {/* ── BEST/WORST TRADES ── */}
      {(s.best_trade || s.worst_trade) && (
        <div style={{
          padding: "8px 16px",
          display: "flex", gap: 8, flexWrap: "wrap",
          borderBottom: `1px solid ${T.border}`,
        }}>
          {s.best_trade && (
            <span style={{
              fontFamily: T.mono, fontSize: 12,
              padding: "3px 8px", borderRadius: 4,
              color: T.green, background: `${T.green}12`, border: `1px solid ${T.green}20`,
            }}>
              Best: {s.best_trade.coin} {s.best_trade.side} +{fmt$(Math.abs(s.best_trade.pnl))} ({s.best_trade.pnl_pct > 0 ? "+" : ""}{s.best_trade.pnl_pct}%)
            </span>
          )}
          {s.worst_trade && (
            <span style={{
              fontFamily: T.mono, fontSize: 12,
              padding: "3px 8px", borderRadius: 4,
              color: T.red, background: `${T.red}12`, border: `1px solid ${T.red}20`,
            }}>
              Worst: {s.worst_trade.coin} {s.worst_trade.side} -{fmt$(Math.abs(s.worst_trade.pnl))} ({s.worst_trade.pnl_pct}%)
            </span>
          )}
        </div>
      )}

      {/* ── SECTION TABS (like HyperTracker: Perps / Trades / Coin Stats) ── */}
      <div style={{
        padding: "8px 16px",
        display: "flex", gap: 2,
        borderBottom: `1px solid ${T.border}`,
      }}>
        {sections.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveSection(key)}
            style={{
              padding: "6px 14px", borderRadius: 6, border: "none",
              fontFamily: T.mono, fontSize: 13, fontWeight: 600,
              color: activeSection === key ? T.text1 : T.text4,
              background: activeSection === key ? T.overlay10 : "transparent",
              cursor: "pointer", transition: "all 0.15s",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── POSITION SUMMARY STRIP (like HyperTracker) ── */}
      {activeSection === "positions" && positions.length > 0 && (
        <div style={{
          padding: "8px 16px",
          display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center",
          borderBottom: `1px solid ${T.border}`,
          background: T.overlay04,
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
              {sumPnl >= 0 ? "+" : ""}{fmt$(Math.abs(sumPnl))}
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
                    {["TOKEN", "SIDE", "VALUE", "AVG ENTRY", "PNL/ROE", "LEV", "DIST. TO LIQ", "AGE"].map(h => (
                      <th key={h} style={{
                        padding: "8px 8px",
                        fontFamily: T.mono, fontSize: 11, fontWeight: 600,
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
                    return (
                      <tr key={i} style={{ borderBottom: `1px solid ${T.overlay06}` }}>
                        {/* TOKEN — coin name + leverage type + asset class badge */}
                        <td style={{ padding: "8px 8px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                            <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.text1 }}>
                              {p.coin}
                            </span>
                            {p.asset_class && p.asset_class !== "crypto" && (
                              <span style={{
                                fontFamily: T.mono, fontSize: 9, fontWeight: 700,
                                padding: "1px 4px", borderRadius: 3,
                                color: ({ commodity: "#F59E0B", equity: "#3B82F6", index: "#8B5CF6", fx: "#10B981", tradfi: "#6B7280" })[p.asset_class] || T.text4,
                                background: ({ commodity: "#F59E0B18", equity: "#3B82F618", index: "#8B5CF618", fx: "#10B98118", tradfi: "#6B728018" })[p.asset_class] || `${T.text4}15`,
                                textTransform: "uppercase", letterSpacing: 0.5,
                              }}>
                                {p.asset_class}
                              </span>
                            )}
                          </div>
                          <div style={{ fontFamily: T.mono, fontSize: 10, color: T.text4 }}>
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
                            <div style={{ fontFamily: T.mono, fontSize: 10, color: p.side === "LONG" ? T.green : T.red }}>
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
                            {pnl >= 0 ? "+" : ""}{fmt$(Math.abs(pnl))}
                          </div>
                          {roe != null && (
                            <div style={{
                              fontFamily: T.mono, fontSize: 10,
                              color: roe >= 0 ? T.green : T.red,
                            }}>
                              {(roe * 100).toFixed(2)}%
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
                        {/* AGE */}
                        <td style={{ padding: "8px 8px", textAlign: "right", fontFamily: T.mono, fontSize: 12, color: T.text3 }}>
                          {fmtAge(p.position_age_s)}
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
                        fontFamily: T.mono, fontSize: 11, fontWeight: 600,
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
                            <>{(t.pnl || 0) >= 0 ? "+" : ""}{fmt$(Math.abs(t.pnl || 0))} <span style={{ fontSize: 11, color: T.text4 }}>({(t.pnl_pct || 0) > 0 ? "+" : ""}{(t.pnl_pct || 0).toFixed(1)}%)</span></>
                          ) : (
                            <span style={{ color: T.text4 }}>--</span>
                          )}
                        </td>
                        <td style={{ padding: "7px 8px" }}>
                          <span style={{
                            fontFamily: T.mono, fontSize: 11, fontWeight: 700,
                            padding: "2px 6px", borderRadius: 3,
                            color: statusColor, background: `${statusColor}15`,
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
                        {c.pnl >= 0 ? "+" : ""}{fmt$(Math.abs(c.pnl))}
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

function SymbolDetail({ symbol, consensus, onClose, onWalletClick }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/api/hyperlens/positions/${symbol}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [symbol]);

  // Find consensus data for summary strip
  const cData = useMemo(() => {
    return (consensus || []).find(c => c.symbol === symbol) || {};
  }, [consensus, symbol]);

  if (loading) {
    return (
      <GlassCard style={{ padding: 20 }}>
        <div style={{ fontFamily: T.mono, fontSize: 13, color: T.text4, textAlign: "center" }}>Loading...</div>
      </GlassCard>
    );
  }

  const positions = data?.positions || [];
  const totalLongNotional = positions.filter(p => p.side === "LONG").reduce((s, p) => s + (p.size_usd || 0), 0);
  const totalShortNotional = positions.filter(p => p.side === "SHORT").reduce((s, p) => s + (p.size_usd || 0), 0);
  const totalNotional = totalLongNotional + totalShortNotional;
  const netBias = totalNotional > 0 ? ((totalLongNotional - totalShortNotional) / totalNotional * 100) : 0;

  return (
    <GlassCard style={{ padding: 0 }}>
      {/* Header */}
      <div style={{
        padding: "12px 16px",
        borderBottom: `1px solid ${T.border}`,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div>
          <span style={{ fontFamily: T.mono, fontSize: 15, fontWeight: 700, color: T.text1 }}>
            {symbol}
          </span>
          <span style={{ color: T.text4, fontWeight: 400, marginLeft: 8, fontSize: 11 }}>
            {positions.length} wallet{positions.length !== 1 ? "s" : ""}
          </span>
          {cData.trend && (
            <span style={{
              marginLeft: 8,
              fontFamily: T.mono, fontSize: 11, fontWeight: 700,
              padding: "2px 6px", borderRadius: 3,
              color: trendColor(cData.trend),
              background: `${trendColor(cData.trend)}15`,
            }}>
              {cData.trend}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          style={{
            width: 28, height: 28, borderRadius: 6,
            border: `1px solid ${T.border}`, background: T.surface, color: T.text3,
            fontSize: 15, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          {"\u2715"}
        </button>
      </div>

      {/* Summary strip */}
      <div style={{
        padding: "8px 16px",
        borderBottom: `1px solid ${T.border}`,
        display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, letterSpacing: "0.06em" }}>LONG</span>
          <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.green }}>{fmt$(totalLongNotional)}</span>
        </div>
        <div style={{ width: 1, height: 14, background: T.border }} />
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, letterSpacing: "0.06em" }}>SHORT</span>
          <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.red }}>{fmt$(totalShortNotional)}</span>
        </div>
        <div style={{ width: 1, height: 14, background: T.border }} />
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, letterSpacing: "0.06em" }}>NET BIAS</span>
          <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, color: netBias > 5 ? T.green : netBias < -5 ? T.red : T.text3 }}>
            {netBias > 0 ? "+" : ""}{netBias.toFixed(0)}%
          </span>
        </div>
        {cData.avg_leverage != null && (
          <>
            <div style={{ width: 1, height: 14, background: T.border }} />
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, letterSpacing: "0.06em" }}>AVG LEV</span>
              <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: levColor(cData.avg_leverage) }}>
                {fmtLev(cData.avg_leverage)}
              </span>
            </div>
          </>
        )}
      </div>

      {/* Positions table */}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["WALLET", "SIDE", "SIZE", "ENTRY", "PNL", "LEV", "LIQ DIST", "AGE"].map(h => (
                <th key={h} style={{
                  padding: "8px 8px",
                  fontFamily: T.mono, fontSize: 11, fontWeight: 600,
                  color: T.text4, letterSpacing: "0.06em",
                  borderBottom: `1px solid ${T.border}`,
                  textAlign: h === "WALLET" || h === "SIDE" ? "left" : "right",
                  whiteSpace: "nowrap",
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {positions.map((p, i) => (
              <tr
                key={i}
                onClick={() => onWalletClick?.(p.address)}
                style={{ cursor: onWalletClick ? "pointer" : "default", transition: "background 0.15s" }}
                onMouseEnter={e => { if (onWalletClick) e.currentTarget.style.background = T.overlay06; }}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}
              >
                <td style={{ padding: "7px 8px" }}>
                  <span style={{
                    fontFamily: T.mono, fontSize: 13, color: T.accent,
                    textDecoration: "underline", textDecorationColor: "rgba(99,179,237,0.35)",
                    textUnderlineOffset: 3, cursor: "pointer",
                  }}>
                    {truncAddr(p.address)} {"\u2192"}
                  </span>
                  {p.wallet_roi > 0 && (
                    <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4, marginLeft: 4 }}>
                      {fmtPct(p.wallet_roi)}
                    </span>
                  )}
                </td>
                <td style={{ padding: "7px 8px" }}>
                  <span style={{
                    fontFamily: T.mono, fontSize: 12, fontWeight: 700,
                    padding: "2px 6px", borderRadius: 3,
                    color: p.side === "LONG" ? T.green : T.red,
                    background: `${p.side === "LONG" ? T.green : T.red}15`,
                  }}>
                    {p.side}
                  </span>
                </td>
                <td style={{ padding: "7px 8px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text1 }}>
                  {fmt$(p.size_usd)}
                </td>
                <td style={{ padding: "7px 8px", textAlign: "right", fontFamily: T.mono, fontSize: 12, color: T.text3 }}>
                  ${(p.entry_px || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </td>
                <td style={{
                  padding: "7px 8px", textAlign: "right",
                  fontFamily: T.mono, fontSize: 13, fontWeight: 600,
                  color: (p.unrealized_pnl || 0) >= 0 ? T.green : T.red,
                }}>
                  {(p.unrealized_pnl || 0) >= 0 ? "+" : ""}{fmt$(Math.abs(p.unrealized_pnl || 0))}
                </td>
                <td style={{ padding: "7px 8px", textAlign: "right", fontFamily: T.mono, fontSize: 12, color: levColor(p.leverage) }}>
                  {p.leverage}x
                </td>
                <td style={{
                  padding: "7px 8px", textAlign: "right",
                  fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  color: pctColor(p.liq_distance_pct),
                }}>
                  {p.liq_distance_pct != null ? `${p.liq_distance_pct.toFixed(1)}%` : "--"}
                </td>
                <td style={{ padding: "7px 8px", textAlign: "right", fontFamily: T.mono, fontSize: 12, color: T.text3 }}>
                  {fmtAge(p.position_age_s)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {positions.length === 0 && (
          <div style={{ padding: 16, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
            No positions found for {symbol}
          </div>
        )}
      </div>
    </GlassCard>
  );
}

// ─── TAB SWITCHER ────────────────────────────────────────────────────────────

// ─── PRESSURE MAP ────────────────────────────────────────────────────────────

function PressureOverviewTable({ data, onSymbolSelect }) {
  const [sortKey, setSortKey] = useState("total_notional");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = useMemo(() => {
    if (!data?.symbols) return [];
    const items = [...data.symbols];
    items.sort((a, b) => {
      if (sortKey === "symbol") {
        return sortAsc ? a.symbol.localeCompare(b.symbol) : b.symbol.localeCompare(a.symbol);
      }
      const av = a[sortKey] || 0;
      const bv = b[sortKey] || 0;
      return sortAsc ? av - bv : bv - av;
    });
    return items;
  }, [data, sortKey, sortAsc]);

  const handleSort = (key) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const biasColor = (bias) => {
    if (bias > 0.3) return T.green;
    if (bias < -0.3) return T.red;
    return T.text4;
  };

  const biasLabel = (bias) => {
    if (bias > 0.5) return "STRONG BUY";
    if (bias > 0.2) return "BUY";
    if (bias < -0.5) return "STRONG SELL";
    if (bias < -0.2) return "SELL";
    return "NEUTRAL";
  };

  // Summary strip at top
  const totals = useMemo(() => {
    if (!data?.symbols) return { stops: 0, tps: 0, limits: 0, notional: 0, wallets: 0 };
    return data.symbols.reduce((acc, s) => ({
      stops: acc.stops + (s.stop_count || 0),
      tps: acc.tps + (s.tp_count || 0),
      limits: acc.limits + (s.limit_count || 0),
      notional: acc.notional + (s.total_notional || 0),
      wallets: data.total_wallets_with_orders || 0,
    }), { stops: 0, tps: 0, limits: 0, notional: 0, wallets: 0 });
  }, [data]);

  return (
    <div>
      {/* Summary strip */}
      <div style={{
        display: "flex", gap: 8, flexWrap: "wrap", padding: "12px 16px",
        borderBottom: `1px solid ${T.border}`,
      }}>
        {[
          { label: "WALLETS W/ ORDERS", value: totals.wallets, color: T.text1 },
          { label: "SYMBOLS", value: sorted.length, color: T.accent },
          { label: "STOP LOSSES", value: totals.stops, color: T.red },
          { label: "TAKE PROFITS", value: totals.tps, color: T.green },
          { label: "LIMIT ORDERS", value: totals.limits, color: T.accent },
          { label: "TOTAL NOTIONAL", value: fmt$(totals.notional), color: T.text1, isText: true },
        ].map(({ label, value, color, isText }) => (
          <div key={label} style={{
            flex: "1 1 100px", padding: "6px 10px", borderRadius: 8,
            background: `${color}08`, border: `1px solid ${color}20`,
          }}>
            <div style={{ fontFamily: T.mono, fontSize: 9, color: T.text4, letterSpacing: "0.06em" }}>{label}</div>
            <div style={{ fontFamily: T.mono, fontSize: isText ? 13 : 16, fontWeight: 700, color }}>{value}</div>
          </div>
        ))}
      </div>

      {sorted.length === 0 ? (
        <div style={{ padding: 40, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
          No pressure data available
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <SortTh label="SYMBOL" sortKey="symbol" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="left" />
                <SortTh label="STOPS" sortKey="stop_count" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                <SortTh label="TPs" sortKey="tp_count" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                <SortTh label="LIMITS" sortKey="limit_count" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                <SortTh label="WALLETS" sortKey="wallet_count" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                <SortTh label="NOTIONAL" sortKey="total_notional" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
                <SortTh label="BIAS" sortKey="net_bias" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
              </tr>
            </thead>
            <tbody>
              {sorted.map(s => (
                <tr
                  key={s.symbol}
                  onClick={() => onSymbolSelect(s.symbol)}
                  style={{ cursor: "pointer", transition: "background 0.15s" }}
                  onMouseEnter={e => e.currentTarget.style.background = T.overlay04}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <td style={{ padding: "8px 10px", fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.text1 }}>
                    {s.symbol}
                  </td>
                  <td style={{ padding: "8px 10px", fontFamily: T.mono, fontSize: 12, color: s.stop_count ? T.red : T.text4, textAlign: "right" }}>
                    {s.stop_count || "-"}
                  </td>
                  <td style={{ padding: "8px 10px", fontFamily: T.mono, fontSize: 12, color: s.tp_count ? T.green : T.text4, textAlign: "right" }}>
                    {s.tp_count || "-"}
                  </td>
                  <td style={{ padding: "8px 10px", fontFamily: T.mono, fontSize: 12, color: s.limit_count ? T.accent : T.text4, textAlign: "right" }}>
                    {s.limit_count || "-"}
                  </td>
                  <td style={{ padding: "8px 10px", fontFamily: T.mono, fontSize: 12, color: T.text3, textAlign: "right" }}>
                    {s.wallet_count || 0}
                  </td>
                  <td style={{ padding: "8px 10px", fontFamily: T.mono, fontSize: 12, color: T.text1, textAlign: "right", fontWeight: 600 }}>
                    {fmt$(s.total_notional)}
                  </td>
                  <td style={{ padding: "8px 10px", fontFamily: T.mono, fontSize: 11, fontWeight: 600, textAlign: "right", color: biasColor(s.net_bias) }}>
                    {biasLabel(s.net_bias)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PressureSummaryStrip({ data }) {
  const orders = data?.smart_money_orders || {};
  const items = [
    { label: "STOP ORDERS", count: orders.stops?.length || 0, total: (orders.stops || []).reduce((s, o) => s + (o.total_size_usd || 0), 0), color: T.red },
    { label: "TAKE PROFITS", count: orders.take_profits?.length || 0, total: (orders.take_profits || []).reduce((s, o) => s + (o.total_size_usd || 0), 0), color: T.green },
    { label: "LIMIT ORDERS", count: orders.limits?.length || 0, total: (orders.limits || []).reduce((s, o) => s + (o.total_size_usd || 0), 0), color: T.accent },
  ];

  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", padding: "12px 16px", borderBottom: `1px solid ${T.border}` }}>
      {items.map(({ label, count, total, color }) => (
        <div key={label} style={{
          flex: "1 1 120px", display: "flex", alignItems: "center", gap: 8,
          padding: "8px 12px", borderRadius: 8,
          background: `${color}08`, border: `1px solid ${color}20`,
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: "50%",
            background: color, flexShrink: 0,
          }} />
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, letterSpacing: "0.06em" }}>{label}</span>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span style={{ fontFamily: T.mono, fontSize: 16, fontWeight: 700, color }}>{count}</span>
              <span style={{ fontFamily: T.mono, fontSize: 12, color: T.text3 }}>{fmt$(total)}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function PriceLevelMap({ data }) {
  const SVG_W = 600;
  const SVG_H = 320;
  const PAD_TOP = 20;
  const PAD_BOTTOM = 20;
  const PAD_LEFT = 70;
  const PAD_RIGHT = 70;
  const CENTER_X = SVG_W / 2;
  const BAR_MAX_W = (SVG_W - PAD_LEFT - PAD_RIGHT) / 2 - 10;

  const allLevels = useMemo(() => {
    const levels = [];
    const orders = data?.smart_money_orders || {};
    (orders.stops || []).forEach(o => levels.push({ ...o, type: "SL", price: o.price, size: o.total_size_usd, side: o.side }));
    (orders.take_profits || []).forEach(o => levels.push({ ...o, type: "TP", price: o.price, size: o.total_size_usd, side: o.side }));
    (orders.limits || []).forEach(o => levels.push({ ...o, type: "LIMIT", price: o.price, size: o.total_size_usd, side: o.side }));
    const walls = data?.order_book_walls || {};
    (walls.bid_walls || []).forEach(o => levels.push({ type: "WALL", price: o.price, size: o.size_usd, side: "BUY", wallet_count: o.order_count }));
    (walls.ask_walls || []).forEach(o => levels.push({ type: "WALL", price: o.price, size: o.size_usd, side: "SELL", wallet_count: o.order_count }));
    (data?.liquidation_clusters || []).forEach(o => levels.push({ type: "LIQ", price: o.avg_price, size: o.total_size_usd, side: o.dominant_side === "LONG" ? "BUY" : "SELL", wallet_count: o.wallet_count }));
    return levels;
  }, [data]);

  if (allLevels.length === 0) {
    return (
      <div style={{ padding: 40, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
        No price levels to display
      </div>
    );
  }

  const prices = allLevels.map(l => l.price);
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const rangeP = maxP - minP || 1;
  const maxSize = Math.max(...allLevels.map(l => l.size || 0), 1);

  const priceToY = (p) => PAD_TOP + (1 - (p - minP) / rangeP) * (SVG_H - PAD_TOP - PAD_BOTTOM);

  const typeColor = (type, side) => {
    if (type === "SL") return T.red;
    if (type === "TP") return T.green;
    if (type === "LIMIT") return T.accent;
    if (type === "WALL") return T.text3;
    if (type === "LIQ") return T.yellow;
    return T.text4;
  };

  const typeLabel = (type) => {
    if (type === "SL") return "SL";
    if (type === "TP") return "TP";
    if (type === "LIMIT") return "LMT";
    if (type === "WALL") return "WALL";
    if (type === "LIQ") return "\u26A1";
    return "";
  };

  const gradId = "pressure-grad";

  return (
    <div style={{ padding: "12px 16px", borderBottom: `1px solid ${T.border}` }}>
      <div style={{ fontFamily: T.mono, fontSize: 11, color: T.text4, marginBottom: 8, letterSpacing: "0.06em" }}>
        PRICE LEVEL MAP
      </div>
      <div style={{ overflowX: "auto" }}>
        <svg width="100%" viewBox={`0 0 ${SVG_W} ${SVG_H}`} style={{ maxWidth: SVG_W }}>
          {/* Center axis */}
          <line x1={CENTER_X} y1={PAD_TOP} x2={CENTER_X} y2={SVG_H - PAD_BOTTOM}
            stroke={T.border} strokeWidth="1" strokeDasharray="4,4" opacity="0.4" />
          {/* BUY label */}
          <text x={CENTER_X - 20} y={PAD_TOP - 6} textAnchor="end" fill={T.green}
            fontFamily={T.mono} fontSize="10" fontWeight="600" opacity="0.7">BUY</text>
          {/* SELL label */}
          <text x={CENTER_X + 20} y={PAD_TOP - 6} textAnchor="start" fill={T.red}
            fontFamily={T.mono} fontSize="10" fontWeight="600" opacity="0.7">SELL</text>

          {allLevels.map((level, i) => {
            const y = priceToY(level.price);
            const barW = Math.max(8, (level.size / maxSize) * BAR_MAX_W);
            const color = typeColor(level.type, level.side);
            const isBuy = level.side === "BUY";
            const barH = Math.max(6, Math.min(16, (SVG_H - PAD_TOP - PAD_BOTTOM) / allLevels.length * 0.7));
            const opacity = level.type === "WALL" ? 0.4 : level.type === "LIQ" ? 0.85 : 0.7;
            const strokeDash = level.type === "TP" ? "4,3" : "none";

            return (
              <g key={i}>
                {/* Bar */}
                <rect
                  x={isBuy ? CENTER_X - barW - 2 : CENTER_X + 2}
                  y={y - barH / 2}
                  width={barW}
                  height={barH}
                  rx={3}
                  fill={color}
                  opacity={opacity}
                  stroke={level.type === "WALL" ? color : "none"}
                  strokeWidth={level.type === "WALL" ? 1 : 0}
                  strokeDasharray={strokeDash}
                />
                {/* Type label */}
                <text
                  x={isBuy ? CENTER_X - barW - 8 : CENTER_X + barW + 8}
                  y={y + 3.5}
                  textAnchor={isBuy ? "end" : "start"}
                  fill={color}
                  fontFamily={T.mono}
                  fontSize="9"
                  fontWeight="700"
                >
                  {typeLabel(level.type)}
                </text>
                {/* Price label */}
                <text
                  x={isBuy ? PAD_LEFT - 4 : SVG_W - PAD_RIGHT + 4}
                  y={y + 3.5}
                  textAnchor={isBuy ? "end" : "start"}
                  fill={T.text3}
                  fontFamily={T.mono}
                  fontSize="9"
                >
                  ${level.price?.toLocaleString()}
                </text>
                {/* Size label on bar */}
                {barW > 30 && (
                  <text
                    x={isBuy ? CENTER_X - barW / 2 - 2 : CENTER_X + barW / 2 + 2}
                    y={y + 3}
                    textAnchor="middle"
                    fill={T.text1}
                    fontFamily={T.mono}
                    fontSize="8"
                    fontWeight="600"
                  >
                    {fmt$(level.size)}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      {/* Legend */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 8 }}>
        {[
          { label: "SL Stop", color: T.red },
          { label: "TP Take Profit", color: T.green },
          { label: "LMT Limit", color: T.accent },
          { label: "WALL Book", color: T.text3 },
          { label: "\u26A1 Liq Cluster", color: T.yellow },
        ].map(l => (
          <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <div style={{ width: 10, height: 4, borderRadius: 2, background: l.color }} />
            <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4 }}>{l.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function PressureOrderTable({ data }) {
  const [sortKey, setSortKey] = useState("size");
  const [sortAsc, setSortAsc] = useState(false);

  const orders = useMemo(() => {
    const rows = [];
    const orders = data?.smart_money_orders || {};
    (orders.stops || []).forEach(o => rows.push({ type: "SL", side: o.side, price: o.price, size: o.total_size_usd, wallets: o.wallet_count }));
    (orders.take_profits || []).forEach(o => rows.push({ type: "TP", side: o.side, price: o.price, size: o.total_size_usd, wallets: o.wallet_count }));
    (orders.limits || []).forEach(o => rows.push({ type: "LIMIT", side: o.side, price: o.price, size: o.total_size_usd, wallets: o.wallet_count }));
    rows.sort((a, b) => {
      const av = a[sortKey] || 0;
      const bv = b[sortKey] || 0;
      if (typeof av === "string") return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortAsc ? av - bv : bv - av;
    });
    return rows;
  }, [data, sortKey, sortAsc]);

  const handleSort = (key) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const typeBadge = (type) => {
    const color = type === "SL" ? T.red : type === "TP" ? T.green : T.accent;
    return (
      <span style={{
        fontFamily: T.mono, fontSize: 10, fontWeight: 700,
        padding: "2px 6px", borderRadius: 4,
        color, background: `${color}15`, border: `1px solid ${color}25`,
        letterSpacing: "0.04em",
      }}>
        {type}
      </span>
    );
  };

  if (orders.length === 0) return null;

  return (
    <div style={{ borderBottom: `1px solid ${T.border}` }}>
      <div style={{ padding: "10px 16px 4px", fontFamily: T.mono, fontSize: 11, color: T.text4, letterSpacing: "0.06em" }}>
        ORDER DETAILS
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <SortTh label="TYPE" sortKey="type" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="left" />
              <SortTh label="SIDE" sortKey="side" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="left" />
              <SortTh label="PRICE" sortKey="price" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
              <SortTh label="SIZE" sortKey="size" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
              <SortTh label="WALLETS" sortKey="wallets" currentKey={sortKey} asc={sortAsc} onSort={handleSort} />
            </tr>
          </thead>
          <tbody>
            {orders.map((o, i) => (
              <tr key={i}>
                <td style={{ padding: "6px 10px" }}>{typeBadge(o.type)}</td>
                <td style={{
                  padding: "6px 10px", fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  color: o.side === "BUY" ? T.green : T.red,
                }}>
                  {o.side}
                </td>
                <td style={{ padding: "6px 10px", fontFamily: T.mono, fontSize: 12, color: T.text1, textAlign: "right" }}>
                  ${o.price?.toLocaleString()}
                </td>
                <td style={{ padding: "6px 10px", fontFamily: T.mono, fontSize: 12, color: T.text1, textAlign: "right", fontWeight: 600 }}>
                  {fmt$(o.size)}
                </td>
                <td style={{ padding: "6px 10px", fontFamily: T.mono, fontSize: 12, color: T.text3, textAlign: "right" }}>
                  {o.wallets}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PressureBookWalls({ walls }) {
  if (!walls || (!walls.bid_walls?.length && !walls.ask_walls?.length)) return null;

  const allWalls = [
    ...(walls.bid_walls || []).map(w => ({ ...w, side: "BID" })),
    ...(walls.ask_walls || []).map(w => ({ ...w, side: "ASK" })),
  ];
  const maxSize = Math.max(...allWalls.map(w => w.size_usd || 0), 1);

  return (
    <div style={{ borderBottom: `1px solid ${T.border}` }}>
      <div style={{ padding: "10px 16px 4px", fontFamily: T.mono, fontSize: 11, color: T.text4, letterSpacing: "0.06em" }}>
        BOOK WALLS
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ padding: "6px 10px", fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.text4, textAlign: "left", borderBottom: `1px solid ${T.border}` }}>SIDE</th>
              <th style={{ padding: "6px 10px", fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.text4, textAlign: "right", borderBottom: `1px solid ${T.border}` }}>PRICE</th>
              <th style={{ padding: "6px 10px", fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.text4, textAlign: "right", borderBottom: `1px solid ${T.border}` }}>SIZE</th>
              <th style={{ padding: "6px 10px", fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.text4, textAlign: "right", borderBottom: `1px solid ${T.border}` }}>ORDERS</th>
              <th style={{ padding: "6px 10px", fontFamily: T.mono, fontSize: 12, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}`, minWidth: 80 }}></th>
            </tr>
          </thead>
          <tbody>
            {allWalls.map((w, i) => {
              const pct = Math.min((w.size_usd / maxSize) * 100, 100);
              const color = w.side === "BID" ? T.green : T.red;
              return (
                <tr key={i}>
                  <td style={{
                    padding: "6px 10px", fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                    color,
                  }}>
                    {w.side}
                  </td>
                  <td style={{ padding: "6px 10px", fontFamily: T.mono, fontSize: 12, color: T.text1, textAlign: "right" }}>
                    ${w.price?.toLocaleString()}
                  </td>
                  <td style={{ padding: "6px 10px", fontFamily: T.mono, fontSize: 12, color: T.text1, textAlign: "right", fontWeight: 600 }}>
                    {fmt$(w.size_usd)}
                  </td>
                  <td style={{ padding: "6px 10px", fontFamily: T.mono, fontSize: 12, color: T.text3, textAlign: "right" }}>
                    {w.order_count}
                  </td>
                  <td style={{ padding: "6px 10px" }}>
                    <div style={{
                      height: 4, borderRadius: 2, background: T.overlay06,
                      overflow: "hidden",
                    }}>
                      <div style={{
                        width: `${pct}%`, height: "100%", borderRadius: 2,
                        background: color, opacity: 0.6,
                        transition: "width 0.3s",
                      }} />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PressureLiqClusters({ clusters }) {
  if (!clusters?.length) return null;

  return (
    <div style={{ padding: "12px 16px" }}>
      <div style={{ fontFamily: T.mono, fontSize: 11, color: T.text4, letterSpacing: "0.06em", marginBottom: 8 }}>
        LIQUIDATION CLUSTERS
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {clusters.map((c, i) => (
          <div key={i} style={{
            padding: "10px 14px", borderRadius: 8,
            background: `${T.yellow}08`,
            border: `1px solid ${T.yellow}20`,
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <span style={{ fontSize: 16 }}>{"\u26A1"}</span>
            <div style={{ flex: 1, fontFamily: T.mono, fontSize: 12, color: T.text2, lineHeight: 1.5 }}>
              <span style={{ fontWeight: 700, color: T.yellow }}>{c.wallet_count} wallets</span>
              {" with "}
              <span style={{ fontWeight: 700, color: T.red }}>{fmt$(c.total_size_usd)}</span>
              {" "}
              <span style={{ color: c.dominant_side === "LONG" ? T.green : T.red, fontWeight: 600 }}>{c.dominant_side}</span>
              {" positions have liquidation near "}
              <span style={{ fontWeight: 700, color: T.text1 }}>${c.avg_price?.toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PressureMap({ consensus, isMobile }) {
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [pressureData, setPressureData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchPressure = useCallback(async () => {
    try {
      const url = selectedSymbol
        ? `${API}/api/hyperlens/pressure?symbol=${selectedSymbol}`
        : `${API}/api/hyperlens/pressure`;
      const res = await fetch(url).then(r => r.json());
      setPressureData(res);
    } catch (err) {
      console.warn("Pressure fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, [selectedSymbol]);

  useEffect(() => {
    setLoading(true);
    fetchPressure();
    const interval = setInterval(fetchPressure, 15_000);
    return () => clearInterval(interval);
  }, [fetchPressure]);

  return (
    <div>

      {loading ? (
        <div style={{ padding: 40, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
          Loading pressure data...
        </div>
      ) : !selectedSymbol ? (
        <PressureOverviewTable data={pressureData} onSymbolSelect={setSelectedSymbol} />
      ) : (
        <div>
          {/* Back button */}
          <div style={{ padding: "8px 16px", borderBottom: `1px solid ${T.border}` }}>
            <button
              onClick={() => setSelectedSymbol(null)}
              style={{
                padding: "4px 10px", borderRadius: 6, border: `1px solid ${T.border}`,
                fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                color: T.text3, background: "transparent",
                cursor: "pointer", transition: "all 0.15s",
              }}
            >
              {"\u2190"} All Symbols
            </button>
            <span style={{
              marginLeft: 10, fontFamily: T.mono, fontSize: 14, fontWeight: 700,
              color: T.text1,
            }}>
              {selectedSymbol}
            </span>
          </div>

          {pressureData?.symbol ? (
            <>
              <PressureSummaryStrip data={pressureData} />
              <PriceLevelMap data={pressureData} />
              <PressureOrderTable data={pressureData} />
              <PressureBookWalls walls={pressureData.order_book_walls} />
              <PressureLiqClusters clusters={pressureData.liquidation_clusters} />
            </>
          ) : (
            <div style={{ padding: 40, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
              No pressure data for {selectedSymbol}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── TAB SWITCHER ────────────────────────────────────────────────────────────

function TabSwitcher({ active, onChange }) {
  const tabs = [
    { key: "consensus", label: "Consensus" },
    { key: "heatmap", label: "Heatmap" },
    { key: "roster", label: "Roster" },
    { key: "pressure", label: "Pressure" },
  ];

  return (
    <div style={{
      display: "flex", gap: 2, padding: "4px",
      borderRadius: 8, background: T.overlay04,
      border: `1px solid ${T.overlay06}`,
    }}>
      {tabs.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          style={{
            flex: 1, padding: "6px 14px", borderRadius: 6, border: "none",
            fontFamily: T.mono, fontSize: 13, fontWeight: 600,
            color: active === key ? T.text1 : T.text4,
            background: active === key ? T.overlay10 : "transparent",
            cursor: "pointer", transition: "all 0.2s ease",
            letterSpacing: "0.03em",
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// ─── COHORT FILTER ──────────────────────────────────────────────────────────

const COHORT_OPTIONS = [
  { key: "all", label: "ALL", color: T.text1 },
  { key: "money_printers", label: "Money Printers", color: T.green, emoji: "\uD83D\uDCB0" },
  { key: "smart_money", label: "Smart Money", color: T.accent, emoji: "\uD83D\uDC0B" },
  { key: "elite", label: "Elite", color: T.yellow, emoji: "\u2B50" },
];

function CohortFilter({ active, onChange }) {
  return (
    <div style={{
      display: "flex", gap: 4, flexWrap: "wrap",
    }}>
      {COHORT_OPTIONS.map(({ key, label, color, emoji }) => {
        const isActive = active === key;
        return (
          <button
            key={key}
            onClick={() => onChange(key)}
            style={{
              padding: "3px 10px", borderRadius: 12,
              fontFamily: T.mono, fontSize: 11, fontWeight: 600,
              color: isActive ? color : T.text4,
              background: isActive ? `${color}18` : T.overlay04,
              border: isActive ? `1px solid ${color}30` : `1px solid ${T.overlay06}`,
              cursor: "pointer", transition: "all 0.2s ease",
              letterSpacing: "0.03em",
              whiteSpace: "nowrap",
            }}
          >
            {emoji ? `${emoji} ${label}` : label}
          </button>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PANEL
// ═══════════════════════════════════════════════════════════════════════════════

export default function HyperLensPanel({ isMobile }) {
  const [tab, setTab] = useState("consensus");
  const [filter, setFilter] = useState("");
  const [cohort, setCohort] = useState("all");
  const [status, setStatus] = useState({});
  const [consensus, setConsensus] = useState([]);
  const [roster, setRoster] = useState([]);
  const [selectedWallet, setSelectedWallet] = useState(null);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const cohortParam = cohort !== "all" ? `?cohort=${cohort}` : "";
      const [statusRes, consensusRes, rosterRes] = await Promise.all([
        fetch(`${API}/api/hyperlens/status`).then(r => r.json()),
        fetch(`${API}/api/hyperlens/consensus${cohortParam}`).then(r => r.json()),
        fetch(`${API}/api/hyperlens/roster${cohortParam}`).then(r => r.json()),
      ]);
      setStatus(statusRes);
      setConsensus(consensusRes.consensus || []);
      setRoster(rosterRes.wallets || []);
    } catch (err) {
      console.warn("HyperLens fetch failed:", err);
    } finally {
      setLoading(false);
    }
  }, [cohort]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 30_000);
    return () => clearInterval(interval);
  }, [loadData]);

  const bullish = consensus.filter(c => getCohortFields(c, cohort).trend === "BULLISH").length;
  const bearish = consensus.filter(c => getCohortFields(c, cohort).trend === "BEARISH").length;
  const neutral = consensus.filter(c => getCohortFields(c, cohort).trend === "NEUTRAL").length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Header card */}
      <GlassCard style={{ padding: 0 }}>
        <div style={{
          padding: "16px 16px 12px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexWrap: "wrap", gap: 10,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{
              fontFamily: T.mono, fontSize: 13, color: T.text4,
              padding: "2px 8px", borderRadius: 4, background: T.overlay06,
            }}>
              Top {status.tracked_wallets || 0} wallets
            </span>
          </div>

          {consensus.length > 0 && (
            <div style={{ display: "flex", gap: 6 }}>
              {bullish > 0 && (
                <span style={{
                  fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  padding: "3px 8px", borderRadius: 4,
                  color: T.green, background: `${T.green}15`, border: `1px solid ${T.green}25`,
                }}>
                  {bullish} BULL
                </span>
              )}
              {bearish > 0 && (
                <span style={{
                  fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  padding: "3px 8px", borderRadius: 4,
                  color: T.red, background: `${T.red}15`, border: `1px solid ${T.red}25`,
                }}>
                  {bearish} BEAR
                </span>
              )}
              {neutral > 0 && (
                <span style={{
                  fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  padding: "3px 8px", borderRadius: 4,
                  color: T.text4, background: T.overlay06, border: `1px solid ${T.overlay10}`,
                }}>
                  {neutral} FLAT
                </span>
              )}
            </div>
          )}
        </div>

        <StatusStrip status={status} cohort={cohort} roster={roster} />

        {/* Controls bar */}
        <div style={{
          padding: "12px 16px",
          display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
        }}>
          <TabSwitcher active={tab} onChange={setTab} />
          <CohortFilter active={cohort} onChange={setCohort} />

          {tab === "consensus" && (
            <input
              type="text"
              placeholder="Filter symbol..."
              value={filter}
              onChange={e => setFilter(e.target.value)}
              style={{
                fontFamily: T.mono, fontSize: 13,
                padding: "6px 12px", borderRadius: 6,
                border: `1px solid ${T.border}`,
                background: T.overlay04, color: T.text1,
                outline: "none", width: 140,
                transition: "border-color 0.2s",
              }}
              onFocus={e => e.target.style.borderColor = T.accent}
              onBlur={e => e.target.style.borderColor = T.border}
            />
          )}
        </div>
      </GlassCard>

      {/* Modals */}
      {selectedWallet && (
        <ModalOverlay onClose={() => setSelectedWallet(null)}>
          <WalletDetail address={selectedWallet} onClose={() => setSelectedWallet(null)} />
        </ModalOverlay>
      )}
      {selectedSymbol && (
        <ModalOverlay onClose={() => setSelectedSymbol(null)}>
          <SymbolDetail
            symbol={selectedSymbol}
            consensus={consensus}
            onClose={() => setSelectedSymbol(null)}
            onWalletClick={(addr) => { setSelectedWallet(addr); setSelectedSymbol(null); }}
          />
        </ModalOverlay>
      )}

      {/* Main content */}
      {loading ? (
        <GlassCard style={{ padding: 40, textAlign: "center" }}>
          <div style={{ fontFamily: T.mono, fontSize: 13, color: T.text4 }}>Loading HyperLens...</div>
        </GlassCard>
      ) : (
        <GlassCard style={{ padding: 0 }}>
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
          {tab === "roster" && (
            <RosterTable
              wallets={roster}
              consensus={consensus}
              onWalletClick={(addr) => { setSelectedWallet(addr); setSelectedSymbol(null); }}
              isMobile={isMobile}
              cohort={cohort}
            />
          )}
          {tab === "pressure" && (
            <PressureMap
              consensus={consensus}
              isMobile={isMobile}
            />
          )}
        </GlassCard>
      )}
    </div>
  );
}
