import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { createPortal } from "react-dom";
import { createChart, CandlestickSeries, HistogramSeries } from "lightweight-charts";
import { T } from "../theme.js";
import { useWallet } from "../WalletContext.jsx";
import GlassCard from "./GlassCard.jsx";
import { TableSkeleton } from "./Skeleton.jsx";

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
  const svgH = cy + 14;

  return (
    <svg width={size} height={svgH} viewBox={`0 0 ${size} ${svgH}`}>
      <path d={arcPath(0, 5)} fill="none" stroke={T.green} strokeWidth="3" strokeLinecap="round" opacity="0.6" />
      <path d={arcPath(5, 15)} fill="none" stroke={T.yellow} strokeWidth="3" strokeLinecap="round" opacity="0.6" />
      <path d={arcPath(15, 50)} fill="none" stroke={T.red} strokeWidth="3" strokeLinecap="round" opacity="0.6" />
      <line x1={cx} y1={cy} x2={nx.toFixed(1)} y2={ny.toFixed(1)}
        stroke={levColor(v)} strokeWidth="1.5" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="2.5" fill={levColor(v)} />
      <text x={cx} y={cy + 12} textAnchor="middle" fill={T.text1}
        fontFamily={T.mono} fontSize="10" fontWeight="700">
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
      fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700,
      padding: "4px 10px", borderRadius: 20,
      color, background: `${color}12`,
      border: `1px solid ${color}25`,
      letterSpacing: "0.04em",
      boxShadow: `0 0 8px ${color}10`,
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
      borderBottom: `1px solid ${T.overlay08}`,
      background: T.overlay02,
    }}>
      {items.map(({ label, value }) => (
        <div key={label} style={{
          display: "flex", alignItems: "center", gap: 5,
          padding: "4px 10px", borderRadius: 8,
          background: T.overlay04,
          border: `1px solid ${T.overlay06}`,
          backdropFilter: "blur(8px)",
        }}>
          <span style={{ fontFamily: T.font, fontSize: T.textXs, color: T.text4, letterSpacing: "0.08em", fontWeight: 700, textTransform: "uppercase" }}>{label}</span>
          <span style={{ fontFamily: T.mono, fontSize: T.textBase, fontWeight: 700, color: T.text1 }}>{value}</span>
        </div>
      ))}
      {/* Cohort breakdown counts */}
      {cohort === "all" && (mpCount > 0 || smCount > 0 || eliteCount > 0) && (
        <div style={{
          display: "flex", alignItems: "center", gap: 5,
          padding: "4px 10px", borderRadius: 8,
          background: T.overlay04, border: `1px solid ${T.overlay06}`,
        }}>
          {mpCount > 0 && (
            <span style={{ fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700, color: T.green }}>{mpCount} MP</span>
          )}
          {mpCount > 0 && smCount > 0 && (
            <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>·</span>
          )}
          {smCount > 0 && (
            <span style={{ fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700, color: T.accent }}>{smCount} SM</span>
          )}
          {smCount > 0 && eliteCount > 0 && (
            <span style={{ fontFamily: T.mono, fontSize: T.textXs, color: T.text4 }}>·</span>
          )}
          {eliteCount > 0 && (
            <span style={{ fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700, color: T.yellow }}>{eliteCount} Elite</span>
          )}
        </div>
      )}
      {/* LIVE indicator removed — already shown in global header */}
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
            <th style={{ padding: "12px 12px", fontFamily: T.font, fontSize: T.textBase, fontWeight: 700, color: T.text3, letterSpacing: "0.08em", textTransform: "uppercase", borderBottom: `2px solid ${T.border}`, minWidth: isMobile ? 90 : 130 }}>L / S</th>
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
          {filtered.map((c, idx) => {
            const cf = getCohortFields(c, cohort);
            const positioned = cf.long_count + cf.short_count;
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
                  <ConfidenceBar confidence={c.confidence} trend={cf.trend} />
                </td>
                <td style={{ padding: "10px 12px", textAlign: "center" }}>
                  <span style={{
                    fontFamily: T.mono, fontSize: T.textBase, fontWeight: 700,
                    padding: "4px 12px", borderRadius: 20,
                    color: trendColor(cf.trend),
                    background: `${trendColor(cf.trend)}10`,
                    border: `1px solid ${trendColor(cf.trend)}25`,
                    boxShadow: `0 0 12px ${trendColor(cf.trend)}10`,
                    letterSpacing: "0.06em",
                  }}>
                    {cf.trend}
                  </span>
                </td>
                <td style={{ padding: "10px 12px", textAlign: "center", fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700, color: T.text1 }}>
                  {positioned}
                </td>
                <td style={{ padding: "10px 12px" }}>
                  <ConsensusBar long_count={cf.long_count} short_count={cf.short_count} />
                </td>
                <td style={{
                  padding: "10px 12px", textAlign: "center",
                  fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700,
                  color: cf.net_ratio > 0.1 ? T.green : cf.net_ratio < -0.1 ? T.red : T.text3,
                }}>
                  {cf.net_ratio > 0 ? "+" : ""}{(cf.net_ratio * 100).toFixed(0)}%
                </td>
                <td style={{
                  padding: "10px 12px", textAlign: "center",
                  fontFamily: T.mono, fontSize: T.textBase, color: T.text3,
                }}>
                  {c.confidence != null ? `${(c.confidence * 100).toFixed(0)}%` : "--"}
                </td>
                {!isMobile && (
                  <>
                    <td style={{
                      padding: "10px 12px", textAlign: "center",
                      fontFamily: T.mono, fontSize: T.textBase, fontWeight: 600,
                      color: levColor(c.avg_leverage),
                    }}>
                      {c.avg_leverage ? fmtLev(c.avg_leverage) : "--"}
                    </td>
                    <td style={{ padding: "10px 12px" }}>
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
    <div style={{ overflowX: "auto", padding: "10px 0" }}>
      {/* Column headers */}
      <div style={{
        display: "grid",
        gridTemplateColumns: `80px repeat(${categories.length}, 1fr)`,
        gap: 3, padding: "0 12px", marginBottom: 6,
      }}>
        <div />
        {categories.map(cat => (
          <div key={cat.key} style={{
            fontFamily: T.font, fontSize: T.textXs, fontWeight: 700,
            color: T.text3, textAlign: "center",
            letterSpacing: "0.08em", padding: "8px 2px",
            textTransform: "uppercase",
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
              gap: 3, padding: "2px 12px",
              cursor: "pointer",
              transition: "background 0.15s",
              borderRadius: 6,
            }}
            onMouseEnter={e => e.currentTarget.style.background = T.overlay04}
            onMouseLeave={e => e.currentTarget.style.background = "transparent"}
          >
            {/* Symbol label */}
            <div style={{
              fontFamily: T.mono, fontSize: T.textBase, fontWeight: 700,
              color: T.text1, padding: "8px 4px",
              display: "flex", alignItems: "center",
            }}>
              {c.symbol}
            </div>
            {/* Category cells */}
            {categories.map(cat => {
              const isActive = cat.test(ratio);
              return (
                <div key={cat.key} style={{
                  background: isActive ? heatmapColor(ratio) : T.overlay02,
                  borderRadius: 6, padding: "7px 4px",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  transition: "all 0.3s ease",
                  border: isActive ? `1px solid ${heatmapTextColor(ratio)}25` : `1px solid ${T.overlay04}`,
                  boxShadow: isActive ? `inset 0 1px 0 ${heatmapTextColor(ratio)}08` : "none",
                }}>
                  {isActive && (
                    <span style={{
                      fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700,
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
            <th style={{ padding: "12px 12px", fontFamily: T.font, fontSize: T.textBase, fontWeight: 700, color: T.text3, letterSpacing: "0.08em", textTransform: "uppercase", borderBottom: `2px solid ${T.border}`, minWidth: 100, textAlign: "left" }}>WALLET</th>
            <SortTh label="ACCT VALUE" sortKey="av" currentKey={sortKey} asc={sortAsc} onSort={handleSort} w={90} />
            <SortTh label="ROI" sortKey="roi" currentKey={sortKey} asc={sortAsc} onSort={handleSort} w={70} />
            {!isMobile && (
              <>
                <SortTh label="SCORE" sortKey="score" currentKey={sortKey} asc={sortAsc} onSort={handleSort} w={56} />
                <th style={{ padding: "12px 12px", fontFamily: T.font, fontSize: T.textBase, fontWeight: 700, color: T.text3, letterSpacing: "0.08em", textTransform: "uppercase", borderBottom: `2px solid ${T.border}`, minWidth: 50, textAlign: "center" }}>BIAS</th>
                <SortTh label="POS" sortKey="positions" currentKey={sortKey} asc={sortAsc} onSort={handleSort} align="center" w={44} />
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {sorted.map((w, idx) => {
            const bias = getBias(w.address);
            const biasColor = bias === "LONG" ? T.green : bias === "SHORT" ? T.red : bias === "MIXED" ? T.yellow : T.text4;
            const stripeBg = idx % 2 === 1 ? T.overlay02 : "transparent";
            return (
              <tr
                key={w.address}
                onClick={() => onWalletClick?.(w.address)}
                style={{ cursor: "pointer", transition: "background 0.15s", background: stripeBg }}
                onMouseEnter={e => e.currentTarget.style.background = T.overlay06}
                onMouseLeave={e => e.currentTarget.style.background = stripeBg}
              >
                <td style={{ padding: "10px 12px", fontFamily: T.mono, fontSize: T.textBase, color: T.text4, textAlign: "left" }}>
                  {w.rank}
                </td>
                <td style={{ padding: "10px 12px", textAlign: "left" }}>
                  <span style={{
                    fontFamily: T.mono, fontSize: T.textMd, color: T.accent,
                    textDecoration: "underline", textDecorationColor: "rgba(99,179,237,0.35)",
                    textUnderlineOffset: 3, cursor: "pointer", fontWeight: 600,
                  }}>
                    {truncAddr(w.address)} {"\u2192"}
                  </span>
                  {w.display_name && (
                    <span style={{ fontFamily: T.font, fontSize: T.textBase, color: T.text4, marginLeft: 6 }}>
                      {w.display_name.length > 12 ? w.display_name.slice(0, 12) + "..." : w.display_name}
                    </span>
                  )}
                  {/* Cohort badges */}
                  {(w.cohorts || []).length > 0 && (
                    <span style={{ marginLeft: 6, display: "inline-flex", gap: 3 }}>
                      {(w.cohorts || []).includes("money_printer") && (
                        <span style={{
                          fontSize: T.textSm, padding: "2px 6px", borderRadius: 20,
                          color: T.green, background: `${T.green}12`,
                          fontFamily: T.mono, fontWeight: 600,
                        }}>{"\uD83D\uDCB0"}</span>
                      )}
                      {(w.cohorts || []).includes("smart_money") && (
                        <span style={{
                          fontSize: T.textSm, padding: "2px 6px", borderRadius: 20,
                          color: T.accent, background: `${T.accent}12`,
                          fontFamily: T.mono, fontWeight: 600,
                        }}>{"\uD83D\uDC0B"}</span>
                      )}
                    </span>
                  )}
                </td>
                <td style={{ padding: "10px 12px", textAlign: "right", fontFamily: T.mono, fontSize: T.textMd, fontWeight: 600, color: T.text1 }}>
                  {fmt$(w.account_value)}
                </td>
                <td style={{ padding: "10px 12px", textAlign: "right", fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700, color: T.green }}>
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
                          fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700,
                          padding: "3px 10px", borderRadius: 20,
                          color: biasColor, background: `${biasColor}12`,
                          border: `1px solid ${biasColor}25`,
                        }}>
                          {bias}
                        </span>
                      ) : (
                        <span style={{ color: T.text4, fontFamily: T.mono, fontSize: T.textBase }}>--</span>
                      )}
                    </td>
                    <td style={{ padding: "10px 12px", textAlign: "center" }}>
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
    const ro = new ResizeObserver(([e]) => setCw(e.contentRect.width));
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
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
  const pad = { top: 6, right: 6, bottom: 6, left: 46 };
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
              <text x={pad.left - 4} y={y + 3} textAnchor="end" fill={T.text4}
                fontFamily={T.mono} fontSize="9">{fmt$(v)}</text>
            </g>
          );
        })}
        <path d={areaPath} fill={`url(#${gradId})`} />
        <path d={linePath} fill="none" stroke={lineColor} strokeWidth="1.5" strokeLinejoin="round" />
        <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="3" fill={lineColor} />
        <text x={cw - pad.right} y={points[points.length - 1].y - 6}
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

function WalletDetail({ address, onClose, userWallet }) {
  const [data, setData] = useState(null);
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState("positions");
  const [isFollowing, setIsFollowing] = useState(false);

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
              <span style={{
                fontFamily: T.mono, fontSize: 11, fontWeight: 700,
                padding: "3px 8px", borderRadius: 20,
                color: T.accent, background: `${T.accent}12`, border: `1px solid ${T.accent}25`,
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
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          {userWallet && (
            <button
              onClick={toggleFollow}
              title={isFollowing ? "Unfollow wallet" : "Follow wallet for trade alerts"}
              style={{
                width: 30, height: 30, borderRadius: 8,
                border: `1px solid ${isFollowing ? "#fbbf2440" : T.overlay10}`,
                background: isFollowing ? "#fbbf2418" : T.overlay04,
                color: isFollowing ? "#fbbf24" : T.text3,
                fontSize: 16, cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.15s",
              }}
              onMouseEnter={e => { if (!isFollowing) { e.currentTarget.style.background = T.overlay10; e.currentTarget.style.color = "#fbbf24"; } }}
              onMouseLeave={e => { if (!isFollowing) { e.currentTarget.style.background = T.overlay04; e.currentTarget.style.color = T.text3; } }}
            >
              {isFollowing ? "\u2605" : "\u2606"}
            </button>
          )}
          <button
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
              {sumPnl >= 0 ? "+" : ""}{fmt$(sumPnl)}
              {data.account_value > 0 && (
                <span style={{ opacity: 0.7, marginLeft: 4 }}>
                  ({sumPnl >= 0 ? "+" : ""}{((sumPnl / data.account_value) * 100).toFixed(2)}%)
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
                  {pctChg >= 0 ? "+" : ""}{pctChg.toFixed(2)}%
                </span>
                <span style={{ fontFamily: T.mono, fontSize: 11, color, opacity: 0.7, marginLeft: 4 }}>
                  ({pnl >= 0 ? "+" : ""}{fmt$(pnl)})
                </span>
                <span style={{ fontFamily: T.mono, fontSize: 9, color: T.text4, marginLeft: 4 }}>
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
        display: "flex", gap: 4, flexWrap: "wrap", alignItems: "stretch",
        borderBottom: `1px solid ${T.overlay08}`,
      }}>
        {/* Bias gauge */}
        <BiasGauge positions={positions} />

        {/* Leverage */}
        <div style={{
          padding: "8px 12px", borderRadius: 8,
          background: T.overlay04, border: `1px solid ${T.overlay06}`,
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        }}>
          <LeverageGauge value={levStats.avg_leverage} size={56} />
          <span style={{ fontFamily: T.mono, fontSize: 9, color: T.text4, letterSpacing: "0.06em", marginTop: -2 }}>
            Leverage
          </span>
        </div>

        {/* Stats grid */}
        <div style={{
          flex: 1, minWidth: 180,
          padding: "6px 12px", borderRadius: 8,
          background: T.overlay04, border: `1px solid ${T.overlay06}`,
          display: "grid", gridTemplateColumns: "1fr 1fr",
          gap: "2px 16px", alignContent: "center",
        }}>
          {[
            ["ROI", `+${fmtPct(data.monthly_roi || 0)}`, T.green],
            ["PnL", `${(data.monthly_pnl || 0) >= 0 ? "+" : ""}${fmt$(data.monthly_pnl || 0)}`, (data.monthly_pnl || 0) >= 0 ? T.green : T.red],
            ["Score", (data.score || 0).toFixed(0), T.text1],
            ...(s.total_trades > 0 ? [
              ["Win", `${s.win_rate}% (${s.wins}/${s.total_trades})`, s.win_rate > 50 ? T.green : T.red],
              ["Avg", `${s.avg_pnl_pct > 0 ? "+" : ""}${s.avg_pnl_pct}%`, s.avg_pnl_pct > 0 ? T.green : s.avg_pnl_pct < 0 ? T.red : T.text4],
            ] : []),
          ].map(([label, val, color]) => (
            <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4 }}>{label}</span>
              <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color }}>{val}</span>
            </div>
          ))}
        </div>

        {/* Best/Worst trades */}
        {(s.best_trade || s.worst_trade) && (
          <div style={{
            display: "flex", flexDirection: "column", gap: 3, justifyContent: "center",
          }}>
            {s.best_trade && (
              <span style={{
                fontFamily: T.mono, fontSize: 10,
                padding: "2px 8px", borderRadius: 12,
                color: T.green, background: `${T.green}12`, border: `1px solid ${T.green}25`,
                fontWeight: 600, whiteSpace: "nowrap",
              }}>
                {s.best_trade.coin} {s.best_trade.side} +{fmt$(Math.abs(s.best_trade.pnl))} ({s.best_trade.pnl_pct > 0 ? "+" : ""}{s.best_trade.pnl_pct}%)
              </span>
            )}
            {s.worst_trade && (
              <span style={{
                fontFamily: T.mono, fontSize: 10,
                padding: "2px 8px", borderRadius: 12,
                color: T.red, background: `${T.red}12`, border: `1px solid ${T.red}25`,
                fontWeight: 600, whiteSpace: "nowrap",
              }}>
                {s.worst_trade.coin} {s.worst_trade.side} -{fmt$(Math.abs(s.worst_trade.pnl))} ({s.worst_trade.pnl_pct}%)
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── SECTION TABS (like HyperTracker: Perps / Trades / Coin Stats) ── */}
      <div style={{
        padding: "8px 16px",
        display: "flex", gap: 2,
        borderBottom: `1px solid ${T.overlay08}`,
        background: T.overlay02,
      }}>
        {sections.map(({ key, label }) => {
          const isActive = activeSection === key;
          return (
            <button
              key={key}
              onClick={() => setActiveSection(key)}
              style={{
                padding: "7px 14px", borderRadius: 8,
                border: isActive ? `1px solid ${T.accent}30` : "1px solid transparent",
                fontFamily: T.mono, fontSize: 12, fontWeight: 700,
                color: isActive ? T.accent : T.text4,
                background: isActive ? `${T.accent}12` : "transparent",
                cursor: "pointer", transition: "all 0.2s ease",
                letterSpacing: "0.03em",
              }}
            >
              {label}
            </button>
          );
        })}
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
  const longPct = totalNotional > 0 ? (totalLong / totalNotional * 100) : 50;
  const totalLongPnl = longs.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);
  const totalShortPnl = shorts.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);
  const avgLongLev = longs.length > 0 ? longs.reduce((s, p) => s + (p.leverage || 0), 0) / longs.length : 0;
  const avgShortLev = shorts.length > 0 ? shorts.reduce((s, p) => s + (p.leverage || 0), 0) / shorts.length : 0;

  // Wallet row renderer — shared between long/short columns
  const WalletRow = ({ p, compact }) => (
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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{
          fontFamily: T.mono, fontSize: 11, color: T.accent,
          cursor: "pointer", display: "flex", alignItems: "center", gap: 4,
        }}>
          {truncAddr(p.address)}
          {p.wallet_roi > 0 && (
            <span style={{
              fontSize: 9, color: T.green, fontWeight: 600,
              padding: "1px 4px", borderRadius: 3, background: `${T.green}12`,
            }}>
              {fmtPct(p.wallet_roi)} ROI
            </span>
          )}
        </span>
        <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.text1 }}>
          {fmt$(p.size_usd)}
        </span>
      </div>
      {/* Row 2: entry + pnl + leverage + age */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4 }}>
          @ ${(p.entry_px || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
        </span>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{
            fontFamily: T.mono, fontSize: 11, fontWeight: 600,
            color: (p.unrealized_pnl || 0) >= 0 ? T.green : T.red,
          }}>
            {p.pnl_pct != null ? (
              <>{p.pnl_pct >= 0 ? "+" : ""}{p.pnl_pct.toFixed(1)}%</>
            ) : (
              <>{(p.unrealized_pnl || 0) >= 0 ? "+" : ""}{fmt$(Math.abs(p.unrealized_pnl || 0))}</>
            )}
          </span>
          {p.pnl_pct != null && p.unrealized_pnl != null && (
            <span style={{ fontFamily: T.mono, fontSize: 9, color: T.text4 }}>
              {(p.unrealized_pnl || 0) >= 0 ? "+" : ""}{fmt$(Math.abs(p.unrealized_pnl || 0))}
            </span>
          )}
          <span style={{ fontFamily: T.mono, fontSize: 10, color: levColor(p.leverage) }}>
            {p.leverage}x
          </span>
          {p.liq_distance_pct != null && (
            <span style={{
              fontFamily: T.mono, fontSize: 9, color: pctColor(p.liq_distance_pct),
              padding: "1px 3px", borderRadius: 2, background: T.overlay04,
            }}>
              LIQ {p.liq_distance_pct.toFixed(0)}%
            </span>
          )}
          <span style={{ fontFamily: T.mono, fontSize: 9, color: T.text4 }}>
            {fmtAge(p.position_age_s)}
          </span>
        </div>
      </div>
    </div>
  );

  // Side column — longs or shorts
  const SideColumn = ({ side, wallets, total, totalPnl, avgLev, color }) => (
    <div style={{ flex: 1, minWidth: 280, display: "flex", flexDirection: "column" }}>
      {/* Column header */}
      <div style={{
        padding: "12px 12px 10px",
        borderBottom: `2px solid ${color}30`,
        background: `${color}06`,
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{
              fontFamily: T.mono, fontSize: 10, fontWeight: 800, letterSpacing: "0.1em",
              color, textTransform: "uppercase",
            }}>
              {side}
            </span>
            <span style={{
              fontFamily: T.mono, fontSize: 10, color: T.text4,
              padding: "1px 5px", borderRadius: 4, background: T.overlay06,
            }}>
              {wallets.length}
            </span>
          </div>
          <span style={{ fontFamily: T.mono, fontSize: 15, fontWeight: 700, color }}>
            {fmt$(total)}
          </span>
        </div>
        {/* PnL + avg leverage */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{
            fontFamily: T.mono, fontSize: 10, color: T.text4, display: "flex", alignItems: "center", gap: 4,
          }}>
            PNL
            <span style={{ fontWeight: 600, color: totalPnl >= 0 ? T.green : T.red }}>
              {totalPnl >= 0 ? "+" : ""}{fmt$(Math.abs(totalPnl))}
            </span>
          </span>
          <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, display: "flex", alignItems: "center", gap: 4 }}>
            AVG LEV
            <span style={{ fontWeight: 600, color: levColor(avgLev) }}>{avgLev.toFixed(1)}x</span>
          </span>
        </div>
      </div>
      {/* Wallet list */}
      <div style={{ overflowY: "auto", maxHeight: 420 }}>
        {wallets.map((p, i) => <WalletRow key={i} p={p} />)}
        {wallets.length === 0 && (
          <div style={{ padding: 20, textAlign: "center", fontFamily: T.mono, fontSize: 11, color: T.text4 }}>
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
        padding: "16px 20px",
        borderBottom: `1px solid ${T.overlay08}`,
        background: T.overlay02,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div style={{ width: 3, height: 20, borderRadius: 2, background: T.accent, flexShrink: 0 }} />
          <span style={{ fontFamily: T.mono, fontSize: T.textXl, fontWeight: 700, color: T.text1 }}>
            {symbol}
          </span>
          <span style={{
            fontFamily: T.mono, fontSize: T.textSm, color: T.text4, fontWeight: 600,
            padding: "3px 10px", borderRadius: 20, background: T.overlay06,
          }}>
            {positions.length} wallet{positions.length !== 1 ? "s" : ""}
          </span>
          {cData.trend && (
            <span style={{
              fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700,
              padding: "4px 12px", borderRadius: 20,
              color: trendColor(cData.trend),
              background: `${trendColor(cData.trend)}15`,
              border: `1px solid ${trendColor(cData.trend)}28`,
              boxShadow: `0 0 10px ${trendColor(cData.trend)}12`,
            }}>
              {cData.trend}
            </span>
          )}
          {cData.confidence > 0 && (
            <span style={{ fontFamily: T.mono, fontSize: T.textSm, color: T.text4 }}>
              {Math.round(cData.confidence * 100)}% conf
            </span>
          )}
        </div>
        <button
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

      {/* Tug-of-war bar — visual long vs short dominance */}
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
          <span style={{ fontFamily: T.mono, fontSize: 9, color: T.green, fontWeight: 600 }}>
            {longPct.toFixed(0)}% LONG
          </span>
          <span style={{ fontFamily: T.mono, fontSize: 9, color: T.red, fontWeight: 600 }}>
            {(100 - longPct).toFixed(0)}% SHORT
          </span>
        </div>
      </div>

      {/* Two-column layout: Longs | Shorts */}
      <div style={{
        display: "flex",
        borderTop: `1px solid ${T.overlay06}`,
      }}>
        <SideColumn
          side="LONG" wallets={longs} total={totalLong}
          totalPnl={totalLongPnl} avgLev={avgLongLev} color={T.green}
        />
        <div style={{ width: 1, background: T.overlay10, flexShrink: 0 }} />
        <SideColumn
          side="SHORT" wallets={shorts} total={totalShort}
          totalPnl={totalShortPnl} avgLev={avgShortLev} color={T.red}
        />
      </div>

      {positions.length === 0 && (
        <div style={{ padding: 24, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
          No positions found for {symbol}
        </div>
      )}
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
        borderBottom: `1px solid ${T.overlay08}`,
        background: T.overlay02,
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
            flex: "1 1 100px", padding: "8px 12px", borderRadius: 10,
            background: `${color}08`, border: `1px solid ${color}18`,
            backdropFilter: "blur(8px)",
          }}>
            <div style={{ fontFamily: T.font, fontSize: T.textXs, fontWeight: 700, color: T.text4, letterSpacing: "0.08em", textTransform: "uppercase" }}>{label}</div>
            <div style={{ fontFamily: T.mono, fontSize: isText ? T.textMd : T.textXl, fontWeight: 700, color }}>{value}</div>
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
              {sorted.map((s, idx) => {
                const stripeBg = idx % 2 === 1 ? T.overlay02 : "transparent";
                return (
                <tr
                  key={s.symbol}
                  onClick={() => onSymbolSelect(s.symbol)}
                  style={{ cursor: "pointer", transition: "background 0.15s", background: stripeBg }}
                  onMouseEnter={e => e.currentTarget.style.background = T.overlay06}
                  onMouseLeave={e => e.currentTarget.style.background = stripeBg}
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
                );
              })}
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

function PressureChart({ symbol, data }) {
  const chartRef = useRef(null);
  const containerRef = useRef(null);
  const [candles, setCandles] = useState(null);
  const [chartError, setChartError] = useState(false);

  const [volume, setVolume] = useState(null);

  // Fetch OHLCV candles for the symbol
  useEffect(() => {
    if (!symbol) return;
    // For HL-native symbols, use the CCXT format the chart API expects
    const chartSymbol = symbol.includes(":") ? symbol : `${symbol}/USDT:USDT`;
    fetch(`${API}/api/chart/${encodeURIComponent(chartSymbol)}?timeframe=4h&limit=500`)
      .then(r => r.json())
      .then(d => {
        if (d?.candles?.length) {
          setCandles(d.candles);
          setVolume(d.volume || null);
        } else {
          setChartError(true);
        }
      })
      .catch(() => setChartError(true));
  }, [symbol]);

  // Build pressure levels from data
  const levels = useMemo(() => {
    if (!data) return [];
    const result = [];
    const orders = data.smart_money_orders || {};
    const maxLimits = 20; // Only show top N limits by size to avoid clutter

    (orders.stops || []).forEach(o => result.push({
      price: o.price, type: "SL", label: `SL ${fmt$(o.total_size_usd)} (${o.wallet_count}w)`,
      color: "#F87171", lineWidth: 2, lineStyle: 0, size: o.total_size_usd,
    }));
    (orders.take_profits || []).forEach(o => result.push({
      price: o.price, type: "TP", label: `TP ${fmt$(o.total_size_usd)} (${o.wallet_count}w)`,
      color: "#34D399", lineWidth: 2, lineStyle: 0, size: o.total_size_usd,
    }));

    // Top limits only (sorted by size)
    const sortedLimits = [...(orders.limits || [])].sort((a, b) => b.total_size_usd - a.total_size_usd);
    sortedLimits.slice(0, maxLimits).forEach(o => result.push({
      price: o.price, type: "LMT", label: `LMT ${fmt$(o.total_size_usd)} (${o.wallet_count}w)`,
      color: "#60A5FA", lineWidth: 1, lineStyle: 2, size: o.total_size_usd,
    }));

    // Book walls
    const walls = data.order_book_walls || {};
    (walls.bid_walls || []).forEach(o => result.push({
      price: o.price, type: "WALL", label: `BID WALL ${fmt$(o.size_usd)} (${o.order_count})`,
      color: "#6B7280", lineWidth: 1, lineStyle: 1, size: o.size_usd,
    }));
    (walls.ask_walls || []).forEach(o => result.push({
      price: o.price, type: "WALL", label: `ASK WALL ${fmt$(o.size_usd)} (${o.order_count})`,
      color: "#6B7280", lineWidth: 1, lineStyle: 1, size: o.size_usd,
    }));

    // Liq clusters
    (data.liquidation_clusters || []).forEach(o => result.push({
      price: o.avg_price, type: "LIQ", label: `LIQ ${fmt$(o.total_size_usd)} ${o.dominant_side} (${o.wallet_count}w)`,
      color: "#FBBF24", lineWidth: 2, lineStyle: 0, size: o.total_size_usd,
    }));

    return result;
  }, [data]);

  const candleSeriesRef = useRef(null);
  const priceLinesRef = useRef([]);

  // Create chart once when candles load (don't recreate on level updates)
  useEffect(() => {
    if (!candles || !containerRef.current) return;

    renderPressureChart(candles, volume, levels, containerRef, chartRef, candleSeriesRef, priceLinesRef);

    return () => {
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        candleSeriesRef.current = null;
        priceLinesRef.current = [];
      }
    };
  }, [candles, volume]); // Only recreate on candle/volume changes

  // Update price lines when levels change (without recreating chart)
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (!series) return;

    // Remove old price lines
    priceLinesRef.current.forEach(pl => {
      try { series.removePriceLine(pl); } catch {}
    });
    priceLinesRef.current = [];

    // Add new price lines
    levels.forEach(level => {
      const pl = series.createPriceLine({
        price: level.price,
        color: level.color,
        lineWidth: level.lineWidth,
        lineStyle: level.lineStyle,
        axisLabelVisible: true,
        title: level.label,
        axisLabelColor: level.color,
        axisLabelTextColor: "#ffffff",
      });
      priceLinesRef.current.push(pl);
    });
  }, [levels]);

  if (chartError) {
    return (
      <div style={{ padding: 30, textAlign: "center", fontFamily: T.mono, fontSize: 12, color: T.text4 }}>
        Chart not available for {symbol}
      </div>
    );
  }

  if (!candles) {
    return (
      <div style={{ padding: 30, textAlign: "center", fontFamily: T.mono, fontSize: 12, color: T.text4 }}>
        Loading chart...
      </div>
    );
  }

  return (
    <div style={{ borderBottom: `1px solid ${T.border}` }}>
      <div style={{ padding: "10px 16px 4px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4, letterSpacing: "0.06em" }}>
          {symbol} — PRESSURE MAP
        </span>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {[
            { label: "SL", color: "#F87171" },
            { label: "TP", color: "#34D399" },
            { label: "LMT", color: "#60A5FA" },
            { label: "WALL", color: "#6B7280" },
            { label: "LIQ", color: "#FBBF24" },
          ].map(l => (
            <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 3 }}>
              <div style={{ width: 8, height: 3, borderRadius: 1, background: l.color }} />
              <span style={{ fontFamily: T.mono, fontSize: 9, color: T.text4 }}>{l.label}</span>
            </div>
          ))}
        </div>
      </div>
      <div ref={containerRef} style={{ width: "100%", height: 500 }} />
    </div>
  );
}

function renderPressureChart(candles, volumeData, levels, containerRef, chartRef, candleSeriesRef, priceLinesRef) {
  // Clean up previous chart
  if (chartRef.current) {
    chartRef.current.remove();
    chartRef.current = null;
  }

  const container = containerRef.current;
  if (!container) return;

  const chart = createChart(container, {
    width: container.clientWidth,
    height: 500,
    layout: {
      background: { type: "solid", color: "transparent" },
      textColor: "#9CA3AF",
      fontFamily: "'IBM Plex Mono', monospace",
      fontSize: 11,
    },
    grid: {
      vertLines: { color: "rgba(255,255,255,0.03)" },
      horzLines: { color: "rgba(255,255,255,0.03)" },
    },
    crosshair: {
      mode: 0,
      vertLine: { color: "rgba(255,255,255,0.15)", labelBackgroundColor: "#1F2937" },
      horzLine: { color: "rgba(255,255,255,0.15)", labelBackgroundColor: "#1F2937" },
    },
    rightPriceScale: {
      borderColor: "rgba(255,255,255,0.06)",
      scaleMargins: { top: 0.05, bottom: 0.05 },
    },
    timeScale: {
      borderColor: "rgba(255,255,255,0.06)",
      timeVisible: true,
      secondsVisible: false,
    },
    handleScale: {
      axisPressedMouseMove: true,
      mouseWheel: true,
      pinch: true,
    },
    handleScroll: {
      mouseWheel: true,
      pressedMouseMove: true,
      horzTouchDrag: true,
      vertTouchDrag: false,
    },
  });

  // Candlestick series (v5 API)
  const candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: "#34D399",
    downColor: "#F87171",
    borderUpColor: "#34D399",
    borderDownColor: "#F87171",
    wickUpColor: "#34D39980",
    wickDownColor: "#F8717180",
  });
  candleSeries.setData(candles);

  // Volume (v5 API)
  const volSeries = chart.addSeries(HistogramSeries, {
    priceFormat: { type: "volume" },
    priceScaleId: "vol",
  });
  chart.priceScale("vol").applyOptions({
    scaleMargins: { top: 0.85, bottom: 0 },
  });
  if (volumeData?.length) {
    volSeries.setData(volumeData);
  }

  // Save series ref for price line updates
  if (candleSeriesRef) candleSeriesRef.current = candleSeries;
  if (priceLinesRef) priceLinesRef.current = [];

  // Add initial pressure levels as price lines
  // lineStyle: 0=Solid, 1=Dotted, 2=Dashed, 3=LargeDashed
  levels.forEach(level => {
    const pl = candleSeries.createPriceLine({
      price: level.price,
      color: level.color,
      lineWidth: level.lineWidth,
      lineStyle: level.lineStyle,
      axisLabelVisible: true,
      title: level.label,
      axisLabelColor: level.color,
      axisLabelTextColor: "#ffffff",
    });
    if (priceLinesRef) priceLinesRef.current.push(pl);
  });

  // Fit content
  chart.timeScale().fitContent();

  // Resize observer
  const ro = new ResizeObserver(entries => {
    for (const entry of entries) {
      chart.applyOptions({ width: entry.contentRect.width });
    }
  });
  ro.observe(container);

  chartRef.current = chart;
  chartRef.current._ro = ro;

  // Override remove to also disconnect observer
  const origRemove = chart.remove.bind(chart);
  chart.remove = () => {
    ro.disconnect();
    origRemove();
  };
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
          <div style={{ padding: "10px 16px", borderBottom: `1px solid ${T.overlay08}`, background: T.overlay02 }}>
            <button
              onClick={() => setSelectedSymbol(null)}
              style={{
                padding: "5px 12px", borderRadius: 8, border: `1px solid ${T.overlay10}`,
                fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                color: T.accent, background: `${T.accent}08`,
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
              <PressureChart symbol={selectedSymbol} data={pressureData} />
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
        No wallets followed yet. Open a wallet profile and click the star to follow.
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
      <div style={{ fontSize: 11, fontWeight: 700, color: T.text3, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 12, fontFamily: T.mono }}>
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
              <div style={{ display: "flex", gap: 8, marginTop: 4, fontFamily: T.mono, fontSize: 10, color: T.text3 }}>
                <span>AV: {fmtUsd(w.account_value)}</span>
                <span>ROI: {w.roi ? `${Math.round(w.roi)}%` : "—"}</span>
                <span>{w.positions_count} pos</span>
              </div>
              {w.cohorts && w.cohorts.length > 0 && (
                <div style={{ display: "flex", gap: 4, marginTop: 4 }}>
                  {w.cohorts.map(c => (
                    <span key={c} style={{
                      fontSize: 8, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
                      padding: "1px 6px", borderRadius: 4, fontFamily: T.mono,
                      background: c === "elite" ? "#fbbf2415" : c === "money_printer" ? "#34d39915" : "#c084fc15",
                      color: c === "elite" ? "#fbbf24" : c === "money_printer" ? "#34d399" : "#c084fc",
                      border: `1px solid ${c === "elite" ? "#fbbf2430" : c === "money_printer" ? "#34d39930" : "#c084fc30"}`,
                    }}>{c.replace("_", " ")}</span>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); unfollow(w.address); }}
              title="Unfollow"
              style={{
                width: 28, height: 28, borderRadius: 6,
                border: `1px solid ${T.overlay10}`, background: T.overlay04,
                color: "#fbbf24", fontSize: 14, cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.15s", flexShrink: 0,
              }}
              onMouseEnter={e => { e.currentTarget.style.background = "#f8717118"; e.currentTarget.style.color = "#f87171"; }}
              onMouseLeave={e => { e.currentTarget.style.background = T.overlay04; e.currentTarget.style.color = "#fbbf24"; }}
            >
              {"\u2605"}
            </button>
          </div>
        ))}
      </div>

      {/* Recent trade events */}
      {events.length > 0 && (
        <>
          <div style={{ fontSize: 11, fontWeight: 700, color: T.text3, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 12, fontFamily: T.mono }}>
            RECENT TRADES
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono, fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={{ textAlign: "left", padding: "6px 8px", fontSize: 10, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>TIME</th>
                  <th style={{ textAlign: "left", padding: "6px 8px", fontSize: 10, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>WALLET</th>
                  <th style={{ textAlign: "left", padding: "6px 8px", fontSize: 10, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>ACTION</th>
                  <th style={{ textAlign: "left", padding: "6px 8px", fontSize: 10, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>COIN</th>
                  <th style={{ textAlign: "right", padding: "6px 8px", fontSize: 10, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>SIZE</th>
                  {!isMobile && <th style={{ textAlign: "right", padding: "6px 8px", fontSize: 10, fontWeight: 600, color: T.text4, borderBottom: `1px solid ${T.border}` }}>PnL</th>}
                </tr>
              </thead>
              <tbody>
                {events.slice(0, 30).map((ev, i) => {
                  const actionColor = ev.action === "OPENED" ? "#34d399" : ev.action === "CLOSED" ? "#f87171" : "#fbbf24";
                  const sideColor = ev.side === "LONG" ? "#34d399" : "#f87171";
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
                      <td style={{ padding: "6px 8px", color: T.text4, fontSize: 10, borderBottom: `1px solid ${T.overlay04}` }}>{ago}</td>
                      <td style={{ padding: "6px 8px", color: T.text2, fontSize: 10, fontWeight: 600, borderBottom: `1px solid ${T.overlay04}` }}>{fmtAddr(ev.wallet)}</td>
                      <td style={{ padding: "6px 8px", borderBottom: `1px solid ${T.overlay04}` }}>
                        <span style={{
                          fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                          background: `${actionColor}15`, color: actionColor, border: `1px solid ${actionColor}30`,
                        }}>{ev.action}</span>
                      </td>
                      <td style={{ padding: "6px 8px", fontWeight: 700, borderBottom: `1px solid ${T.overlay04}` }}>
                        <span style={{ color: sideColor }}>{ev.side}</span>
                        <span style={{ color: T.text2, marginLeft: 4 }}>{ev.coin}</span>
                        <span style={{ color: T.text4, fontSize: 9, marginLeft: 4 }}>{ev.leverage}x</span>
                      </td>
                      <td style={{ padding: "6px 8px", textAlign: "right", color: T.text3, borderBottom: `1px solid ${T.overlay04}` }}>{fmtUsd(ev.size_usd)}</td>
                      {!isMobile && (
                        <td style={{ padding: "6px 8px", textAlign: "right", fontWeight: 600, borderBottom: `1px solid ${T.overlay04}`,
                          color: ev.pnl >= 0 ? "#34d399" : "#f87171",
                        }}>
                          {ev.action !== "OPENED" ? `${ev.pnl >= 0 ? "+" : ""}${fmtUsd(ev.pnl)}` : "—"}
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


function TabSwitcher({ active, onChange, isMobile }) {
  const tabs = [
    { key: "favorites", label: "\u2605 Watchlist" },
    { key: "consensus", label: "Consensus" },
    { key: "heatmap", label: "Heatmap" },
    { key: "roster", label: "Roster" },
    { key: "pressure", label: "Pressure" },
  ];

  return (
    <div style={{
      display: "inline-flex", borderRadius: 8,
      border: `1px solid ${T.border}`,
      overflow: "hidden", flexShrink: 0, alignSelf: "flex-start",
    }}>
      {tabs.map(({ key, label }) => {
        const isActive = active === key;
        return (
          <button
            key={key}
            onClick={() => onChange(key)}
            style={{
              padding: isMobile ? "8px 12px" : "7px 16px", border: "none",
              background: isActive ? T.accent : "transparent",
              color: isActive ? T.bg : T.text3,
              fontFamily: T.font, fontSize: isMobile ? T.textBase : T.textSm, fontWeight: isActive ? 700 : 500,
              cursor: "pointer", letterSpacing: "0.04em",
              transition: "all 0.15s ease",
            }}
          >
            {label}
          </button>
        );
      })}
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

function CohortFilter({ active, onChange, isMobile }) {
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
              padding: isMobile ? "6px 12px" : "5px 14px", borderRadius: 20,
              fontFamily: T.font, fontSize: isMobile ? T.textBase : T.textSm, fontWeight: 600,
              color: isActive ? color : T.text4,
              background: isActive ? `${color}15` : T.overlay04,
              border: isActive ? `1px solid ${color}35` : `1px solid ${T.overlay06}`,
              boxShadow: isActive ? `0 0 12px ${color}15` : "none",
              cursor: "pointer", transition: "all 0.2s ease",
              letterSpacing: "0.04em",
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
  const { address: connectedWallet } = useWallet();
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
      <GlassCard style={{ padding: 0, overflow: "hidden" }}>
        <div style={{
          padding: isMobile ? "12px 12px 10px" : "14px 16px 12px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexWrap: "wrap", gap: isMobile ? 8 : 10,
        }}>
          {consensus.length > 0 && (
            <div style={{ display: "flex", gap: 6 }}>
              {bullish > 0 && (
                <span style={{
                  fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700,
                  padding: "5px 14px", borderRadius: 20,
                  color: T.green, background: `${T.green}15`,
                  border: `1px solid ${T.green}28`,
                  boxShadow: `0 0 12px ${T.green}12`,
                  letterSpacing: "0.06em",
                }}>
                  {bullish} BULL
                </span>
              )}
              {bearish > 0 && (
                <span style={{
                  fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700,
                  padding: "5px 14px", borderRadius: 20,
                  color: T.red, background: `${T.red}15`,
                  border: `1px solid ${T.red}28`,
                  boxShadow: `0 0 12px ${T.red}12`,
                  letterSpacing: "0.06em",
                }}>
                  {bearish} BEAR
                </span>
              )}
              {neutral > 0 && (
                <span style={{
                  fontFamily: T.mono, fontSize: T.textSm, fontWeight: 700,
                  padding: "5px 14px", borderRadius: 20,
                  color: T.text4, background: T.overlay04,
                  border: `1px solid ${T.overlay10}`,
                  letterSpacing: "0.06em",
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
          padding: isMobile ? "10px 12px" : "12px 16px",
          display: "flex", alignItems: isMobile ? "stretch" : "center",
          flexDirection: isMobile ? "column" : "row",
          gap: isMobile ? 8 : 10, flexWrap: "wrap",
        }}>
          <TabSwitcher active={tab} onChange={setTab} isMobile={isMobile} />
          <CohortFilter active={cohort} onChange={setCohort} isMobile={isMobile} />

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
              onFocus={e => { e.target.style.borderColor = T.accent; e.target.style.boxShadow = `0 0 0 2px ${T.accent}15`; }}
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
