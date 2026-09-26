import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  createChart, AreaSeries, ColorType, LineStyle, CrosshairMode,
} from "lightweight-charts";
import { T, SIGNAL_META, REGIME_META, heatColor, col, resolveToken } from "../theme.js";
import { useTheme } from "../ThemeContext.jsx";
import { useWallet } from "../WalletContext.jsx";
import * as hlClient from "../services/hlClient.js";
import Tabs from "./Tabs.jsx";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(ts) {
  if (!ts) return "—";
  const s = typeof ts === "number" && ts > 1e12 ? ts / 1000 : ts;
  const diff = (Date.now() / 1000) - s;
  if (diff < 60)   return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${(diff / 3600).toFixed(1)}h ago`;
  return `${(diff / 86400).toFixed(1)}d ago`;
}

function fmtUsd(v) {
  if (v == null) return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (isNaN(n)) return "—";
  return `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPrice(p) {
  if (!p) return "—";
  const n = typeof p === "string" ? parseFloat(p) : p;
  if (isNaN(n)) return "—";
  if (n >= 1000) return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (n >= 1) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(6)}`;
}

function fmtVlm(v) {
  if (!v) return "$0";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

function fmtBps(rate) {
  if (!rate) return "—";
  const bps = parseFloat(rate) * 10000;
  return `${bps.toFixed(2)} bps`;
}

// T.green / T.red are repainted in place by applyTheme, so read them at render time.
function pnlColor(v) {
  if (v == null || v === 0) return T.text3;
  return v > 0 ? T.green : T.red;
}

function parseNum(v) {
  if (v == null) return 0;
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? 0 : n;
}

// ---------------------------------------------------------------------------
// Scanner context helpers
// ---------------------------------------------------------------------------

const ENTRY_SIGNALS = new Set(["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "REVIVAL_SEED"]);
const EXIT_SIGNALS  = new Set(["TRIM", "TRIM_HARD", "RISK_OFF"]);

const signalLabel = sig => SIGNAL_META[sig]?.label ?? String(sig || "—").replaceAll("_", " ");
const signalColor = sig => SIGNAL_META[sig]?.color ?? T.text3;

// Whether the scanner's signal points the same way as the position.
function computeAlignment(signal, isLong) {
  if (ENTRY_SIGNALS.has(signal)) return isLong ? "ALIGNED" : "CONFLICTING";
  if (EXIT_SIGNALS.has(signal))  return isLong ? "CONFLICTING" : "ALIGNED";
  return "NEUTRAL";
}

const ALIGN_TEXT = { ALIGNED: "Agrees", CONFLICTING: "Disagrees", NEUTRAL: "No clear signal" };
const alignColor = a => a === "ALIGNED" ? T.green : a === "CONFLICTING" ? T.red : T.text3;

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const S = {
  panel: { padding: 0, maxWidth: 1200, margin: "0 auto" },
  section: {
    background: T.surface,
    border: `1px solid ${T.border}`,
    borderRadius: T.radius, marginBottom: 16, overflow: "hidden",
  },
  sectionHeader: {
    padding: "14px 20px",
    borderBottom: `1px solid ${T.border}`,
    display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap",
  },
  title: {
    fontSize: T.textSm, fontWeight: 600, fontFamily: T.font, color: T.text1,
  },
  btn: {
    padding: "6px 14px", borderRadius: 6,
    border: `1px solid ${T.border}`,
    background: "transparent",
    color: T.text1, fontSize: T.textXs, fontFamily: T.mono,
    fontWeight: 600, cursor: "pointer",
  },
  // Getter: T.red is repainted in place by applyTheme, so read it at render time
  get btnDanger() {
    return { borderColor: T.red, color: T.red };
  },
  label: { fontSize: T.textXs, fontFamily: T.font, color: T.text3, fontWeight: 500 },
  value: { fontSize: T.textSm, fontFamily: T.mono, color: T.text1, fontWeight: 600 },
  badge: (color) => ({
    display: "inline-block", padding: 0, borderRadius: 0,
    background: "transparent", color, border: "none",
    fontSize: T.textXs, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.04em",
  }),
  empty: {
    padding: "32px 24px", textAlign: "center",
    color: T.text3, fontSize: T.textXs, fontFamily: T.mono,
  },
};

const cellStyle = {
  padding: "12px 16px", fontSize: T.textXs, fontFamily: T.mono, color: T.text2,
  borderBottom: `1px solid ${T.border}`, whiteSpace: "nowrap",
};
const headerCell = {
  padding: "12px 16px", fontSize: T.textXs, fontFamily: T.font, fontWeight: 600,
  color: T.text3, borderBottom: `1px solid ${T.borderH}`, textAlign: "left",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatBox({ label, value, color, small }) {
  return (
    <div style={{ minWidth: small ? 90 : 120, padding: small ? "8px 10px" : "10px 14px" }}>
      <div style={{ fontSize: T.textXs, fontFamily: T.font, color: T.text3, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{
        fontSize: small ? 15 : 20,
        fontFamily: T.mono,
        fontWeight: 600,
        color: color || T.text1,
        lineHeight: 1.2,
      }}>
        {value}
      </div>
    </div>
  );
}

// ─── Portfolio Chart ────────────────────────────────────────────────────────

const PERIODS = [
  { key: "1D", label: "1D", sdk: "perpDay" },
  { key: "1W", label: "1W", sdk: "perpWeek" },
  { key: "1M", label: "1M", sdk: "perpMonth" },
  { key: "ALL", label: "All", sdk: "perpAllTime" },
];

function PortfolioChart({ portfolio, period, onPeriodChange, mode, onModeChange }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const { mode: themeMode } = useTheme();

  useEffect(() => {
    if (!containerRef.current || !portfolio) return;
    const sdkPeriod = PERIODS.find(p => p.key === period)?.sdk || "perpAllTime";
    const data = portfolio[sdkPeriod];
    if (!data) return;

    const series = mode === "value" ? data.accountValueHistory : data.pnlHistory;
    if (!series || series.length === 0) return;

    // Deduplicate by time (keep last value)
    const seen = new Map();
    for (const pt of series) {
      seen.set(pt.time, pt.value);
    }
    const chartData = [...seen.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([time, value]) => ({ time, value }));

    if (chartData.length === 0) return;

    // Clean up previous chart
    if (chartRef.current) {
      try { chartRef.current.remove(); } catch (_) { /* */ }
      chartRef.current = null;
    }

    const lastVal = chartData[chartData.length - 1].value;
    const isPositive = lastVal >= 0;
    // Library colours are resolved from the theme tokens; rebuilt when the theme changes.
    const border = resolveToken("border");
    const cross = resolveToken("chartCross");
    const labelBg = resolveToken("accent");

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 280,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: resolveToken("chartText"),
        fontFamily: "'Geist Mono', monospace",
        fontSize: 12,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: resolveToken("chartGrid") },
        horzLines: { color: resolveToken("chartGrid") },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: cross, width: 1, style: LineStyle.Dashed, labelBackgroundColor: labelBg },
        horzLine: { color: cross, width: 1, style: LineStyle.Dashed, labelBackgroundColor: labelBg },
      },
      timeScale: {
        borderColor: border,
        timeVisible: true, secondsVisible: false,
        rightOffset: 3, minBarSpacing: 1,
      },
      rightPriceScale: {
        borderColor: border,
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    });
    chartRef.current = chart;

    const lineColor = mode === "value"
      ? resolveToken("accent")
      : col(isPositive ? "#34d399" : "#f87171");

    const areaSeries = chart.addSeries(AreaSeries, {
      topColor: `${lineColor}2e`,
      bottomColor: "transparent",
      lineColor,
      lineWidth: 2,
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderWidth: 1,
      crosshairMarkerBorderColor: lineColor,
      priceFormat: { type: "custom", formatter: (v) => fmtUsd(v) },
    });
    areaSeries.setData(chartData);
    chart.timeScale().fitContent();

    // ResizeObserver
    const ro = new ResizeObserver(() => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      if (chartRef.current) {
        try { chartRef.current.remove(); } catch (_) { /* */ }
        chartRef.current = null;
      }
    };
  }, [portfolio, period, mode, themeMode]);

  const sdkPeriod = PERIODS.find(p => p.key === period)?.sdk || "perpAllTime";
  const vlm = portfolio?.[sdkPeriod]?.vlm;

  return (
    <div style={S.section}>
      <div style={S.sectionHeader}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={S.title}>Perps portfolio</span>
          {vlm > 0 && (
            <span style={{ fontSize: T.textXs, fontFamily: T.mono, color: T.text3 }}>
              Volume {fmtVlm(vlm)}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
          <Tabs small label="Chart value" value={mode} onChange={onModeChange}
            items={[{ key: "value", label: "Value" }, { key: "pnl", label: "P&L" }]} />
          <Tabs small label="Chart period" value={period} onChange={onPeriodChange}
            items={PERIODS.map(p => ({ key: p.key, label: p.label }))} />
        </div>
      </div>
      <div ref={containerRef} style={{ height: 280, width: "100%" }} />
    </div>
  );
}

// ─── Scanner Context Line ────────────────────────────────────────────────────

function ScannerContext({ coin, scanMap4h, scanMap1d, isLong, posWarnings }) {
  const ctx4h = scanMap4h[coin];
  const ctx1d  = scanMap1d[coin];
  if (!ctx4h) return null;

  const alignment = computeAlignment(ctx4h.signal, isLong);
  const regime = REGIME_META[ctx4h.regime];
  const sep = <span style={{ color: T.text4 }}>{"·"}</span>;

  return (
    <div style={{ marginTop: 12, paddingTop: 10, borderTop: `1px solid ${T.border}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: T.textXs, fontFamily: T.mono }}>
        <span style={{ color: T.text3, fontFamily: T.font }}>Scanner 4H</span>
        <span style={{ color: signalColor(ctx4h.signal), fontWeight: 700 }}>{signalLabel(ctx4h.signal)}</span>
        {sep}
        <span style={{ color: regime?.color ?? T.text3 }}>{regime?.name ?? ctx4h.regime}</span>
        {ctx4h.heat != null && <>{sep}<span style={{ color: T.text3 }}>Heat <span style={{ color: heatColor(ctx4h.heat), fontWeight: 700 }}>{ctx4h.heat}</span></span></>}
        {ctx1d && ctx1d.signal !== ctx4h.signal && (
          <>{sep}<span style={{ color: T.text3 }}>1D <span style={{ color: signalColor(ctx1d.signal), fontWeight: 600 }}>{signalLabel(ctx1d.signal)}</span></span></>
        )}
        <span style={{ marginLeft: "auto", color: alignColor(alignment), fontWeight: 700, fontFamily: T.font }}>
          {alignment === "NEUTRAL" ? ALIGN_TEXT.NEUTRAL : `${ALIGN_TEXT[alignment]} with this ${isLong ? "long" : "short"}`}
        </span>
      </div>

      {/* Warnings for this coin */}
      {posWarnings.length > 0 && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
          {posWarnings.map((w, i) => {
            const wc = w.severity === "critical" ? T.red : T.yellow;
            return (
              <div key={i} style={{ fontSize: T.textXs, fontFamily: T.mono, lineHeight: 1.5, color: T.text2 }}>
                <span style={{ color: wc, fontWeight: 700 }}>Warning: </span>{w.detail}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── Scanner Check (plain facts, no score) ───────────────────────────────────

function ScannerCheck({ positions, scanMap4h }) {
  if (positions.length === 0) return null;

  const rows = positions.map(ap => {
    const p      = ap.position || ap;
    const coin   = p.coin;
    const isLong = parseNum(ap.position?.szi ?? ap.szi) > 0;
    const ctx    = scanMap4h[coin];
    const liqPx  = p.liquidationPx ? parseNum(p.liquidationPx) : null;
    const liqDist = liqPx && ctx?.price ? Math.abs(ctx.price - liqPx) / ctx.price * 100 : null;
    return { coin, isLong, ctx, liqDist, alignment: ctx ? computeAlignment(ctx.signal, isLong) : null };
  });

  const covered     = rows.filter(r => r.ctx);
  const agree       = covered.filter(r => r.alignment === "ALIGNED").length;
  const disagree    = covered.filter(r => r.alignment === "CONFLICTING").length;
  const noSignal    = covered.length - agree - disagree;
  const notScanned  = rows.length - covered.length;

  // Descriptions of what the scanner shows, not instructions.
  const notes = rows.flatMap(r => {
    const side = r.isLong ? "long" : "short";
    const out = [];
    if (r.alignment === "CONFLICTING") {
      out.push({ key: `${r.coin}-sig`, color: T.red, text: `${r.coin} ${side}: scanner shows ${signalLabel(r.ctx.signal)} on 4H, against the position.` });
    }
    if (r.liqDist != null && r.liqDist < 15) {
      out.push({ key: `${r.coin}-liq`, color: r.liqDist < 8 ? T.red : T.yellow, text: `${r.coin} ${side}: liquidation price is ${r.liqDist.toFixed(1)}% from the scanner's last price.` });
    }
    return out;
  });

  return (
    <div style={S.section}>
      <div style={S.sectionHeader}>
        <span style={S.title}>Scanner check · 4H</span>
      </div>
      <div style={{ padding: "14px 20px", display: "flex", flexDirection: "column", gap: 8, fontSize: T.textXs, fontFamily: T.font, color: T.text2, lineHeight: 1.6 }}>
        <div>
          Of {rows.length} open position{rows.length === 1 ? "" : "s"}, the scanner's 4H signal{" "}
          <span style={{ color: T.green, fontWeight: 600 }}>agrees with {agree}</span>,{" "}
          <span style={{ color: disagree ? T.red : T.text2, fontWeight: 600 }}>disagrees with {disagree}</span>
          {" "}and gives no clear direction for {noSignal}.
          {notScanned > 0 && ` ${notScanned} ${notScanned === 1 ? "is" : "are"} not covered by the scanner.`}
        </div>
        {notes.map(n => (
          <div key={n.key} style={{ fontFamily: T.mono }}>
            <span style={{ color: n.color, fontWeight: 700 }}>Note: </span>{n.text}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Position Card ──────────────────────────────────────────────────────────

function PositionCard({ pos, onClose, closing, scanMap4h, scanMap1d, posWarnings }) {
  const szi = parseNum(pos.position?.szi ?? pos.szi);
  const isLong = szi > 0;
  const side = isLong ? "LONG" : "SHORT";
  const sideColor = isLong ? T.green : T.red;

  const p = pos.position || pos;
  const coin = p.coin;
  const leverage = p.leverage?.value ?? "?";
  const leverageType = p.leverage?.type === "isolated" ? "isolated" : "cross";
  const entryPx = parseNum(p.entryPx);
  const posValue = parseNum(p.positionValue);
  const unrealizedPnl = parseNum(p.unrealizedPnl);
  const roe = parseNum(p.returnOnEquity) * 100;
  const liqPx = p.liquidationPx ? parseNum(p.liquidationPx) : null;
  const marginUsed = parseNum(p.marginUsed);
  const fundingSinceOpen = parseNum(p.cumFunding?.sinceOpen);

  // Liquidation proximity
  const ctx4h = scanMap4h[coin];
  const liqDistPct = liqPx && ctx4h?.price
    ? Math.abs(ctx4h.price - liqPx) / ctx4h.price * 100
    : null;
  const liqDanger = liqDistPct !== null && liqDistPct < 15;

  // Warnings for this coin
  const coinWarnings = (posWarnings || []).filter(
    w => w.symbol === coin || w.symbol === `${coin}/USDT`
  );

  return (
    <div style={{ padding: "16px 20px", borderBottom: `1px solid ${T.border}` }}>
      {/* Row 1: Coin + side + PnL */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 16, fontFamily: T.mono, fontWeight: 700, color: T.text1 }}>
          {coin}
        </span>
        <span style={S.badge(sideColor)}>{side}</span>
        <span style={{ ...S.badge(T.text3), fontWeight: 500 }}>
          {leverage}x {leverageType}
        </span>
        {liqDanger && (
          <span style={S.badge(T.red)}>
            Liquidation {liqDistPct.toFixed(1)}% away
          </span>
        )}
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div style={{ fontSize: 16, fontFamily: T.mono, fontWeight: 700, color: pnlColor(unrealizedPnl) }}>
            {unrealizedPnl >= 0 ? "+" : ""}{fmtUsd(unrealizedPnl)}
          </div>
          <div style={{ fontSize: T.textXs, fontFamily: T.mono, color: pnlColor(roe) }}>
            ROE {roe >= 0 ? "+" : ""}{roe.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Row 2: Details */}
      <div style={{ display: "flex", gap: "8px 20px", flexWrap: "wrap", alignItems: "center" }}>
        {[
          { label: "Entry", val: fmtPrice(entryPx) },
          { label: "Size", val: Math.abs(szi).toFixed(4) },
          { label: "Value", val: fmtUsd(posValue) },
          { label: "Margin", val: fmtUsd(marginUsed) },
          ...(liqPx ? [{ label: "Liquidation", val: fmtPrice(liqPx), color: liqDanger ? T.red : undefined }] : []),
          ...(fundingSinceOpen !== 0 ? [{ label: "Funding", val: `${fundingSinceOpen >= 0 ? "-" : "+"}${fmtUsd(Math.abs(fundingSinceOpen))}`, color: pnlColor(-fundingSinceOpen) }] : []),
        ].map((d, i) => (
          <div key={i}>
            <span style={S.label}>{d.label} </span>
            <span style={{ ...S.value, color: d.color || T.text1 }}>{d.val}</span>
          </div>
        ))}
        <button
          onClick={() => onClose(coin, Math.abs(szi), isLong)}
          disabled={closing}
          style={{
            ...S.btn, ...S.btnDanger, marginLeft: "auto",
            opacity: closing ? 0.5 : 1, cursor: closing ? "not-allowed" : "pointer",
          }}
        >
          {closing ? "Closing..." : "Close"}
        </button>
      </div>

      {/* Scanner context line */}
      <ScannerContext
        coin={coin}
        scanMap4h={scanMap4h}
        scanMap1d={scanMap1d}
        isLong={isLong}
        posWarnings={coinWarnings}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mobile section tabs
// ---------------------------------------------------------------------------

const SECTION_TABS = [
  { key: "positions", label: "Positions" },
  { key: "orders",   label: "Orders" },
  { key: "fills",    label: "Fills" },
  { key: "funding",  label: "Funding" },
  { key: "fees",     label: "Fees" },
];

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function TradingPanel({ api }) {
  const { address, isConnected, walletClient, connect, error: walletError } = useWallet();

  // Core data
  const [chState, setChState]     = useState(null);
  const [xyzChState, setXyzChState] = useState(null);
  const [spotState, setSpotState] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [openOrders, setOpenOrders] = useState([]);
  const [fills, setFills]         = useState([]);
  const [funding, setFunding]     = useState([]);
  const [fees, setFees]           = useState(null);
  const [history, setHistory]     = useState({ trades: [], stats: {} });

  // Scanner context
  const [scanMap4h, setScanMap4h] = useState({});
  const [scanMap1d, setScanMap1d] = useState({});
  const [posWarnings, setPosWarnings] = useState([]);

  // UI state
  const [chartPeriod, setChartPeriod] = useState("ALL");
  const [chartMode, setChartMode]     = useState("value");
  const [activeSection, setActiveSection] = useState("positions");
  const [closing, setClosing]     = useState(null);
  const [cancelling, setCancelling] = useState(null);

  // --- Data fetching ---

  const fetchFast = useCallback(async () => {
    if (!isConnected || !address) return;
    try {
      const [state, orders, xyzState, spot] = await Promise.all([
        hlClient.getClearinghouseState(address).catch(() => null),
        hlClient.getOpenOrders(address).catch(() => null),
        hlClient.getXyzClearinghouseState(address).catch(() => null),
        hlClient.getSpotState(address).catch(() => null),
      ]);
      if (state) setChState(state);
      if (orders) setOpenOrders(orders);
      if (xyzState) setXyzChState(xyzState);
      if (spot) setSpotState(spot);
    } catch (e) { console.error("Portfolio fast fetch:", e); }
  }, [address, isConnected]);

  const fetchMedium = useCallback(async () => {
    if (!isConnected || !address) return;
    try {
      const f = await hlClient.getUserFills(address).catch(() => []);
      setFills(f || []);
    } catch (e) { console.error("Portfolio medium fetch:", e); }
  }, [address, isConnected]);

  const fetchSlow = useCallback(async () => {
    if (!isConnected || !address) return;
    try {
      const [p, fund, fe, histResp] = await Promise.all([
        hlClient.getPortfolio(address).catch(() => null),
        hlClient.getUserFunding(address).catch(() => []),
        hlClient.getUserFees(address).catch(() => null),
        fetch(`${api}/api/trade/history`).then(r => r.ok ? r.json() : { trades: [], stats: {} }).catch(() => ({ trades: [], stats: {} })),
      ]);
      if (p) setPortfolio(p);
      setFunding(fund || []);
      if (fe) setFees(fe);
      setHistory(histResp);
    } catch (e) { console.error("Portfolio slow fetch:", e); }
  }, [address, isConnected, api]);

  // Fetch scanner context + position warnings
  const fetchScannerContext = useCallback(async () => {
    try {
      const [res4h, res1d] = await Promise.all([
        fetch(`${api}/api/scan?timeframe=4h`).then(r => r.ok ? r.json() : null).catch(() => null),
        fetch(`${api}/api/scan?timeframe=1d`).then(r => r.ok ? r.json() : null).catch(() => null),
      ]);
      if (res4h?.results) {
        const map = {};
        res4h.results.forEach(r => {
          const coin = r.symbol.replace("/USDT", "").replace("/USD", "");
          map[coin] = r;
        });
        setScanMap4h(map);
      }
      if (res1d?.results) {
        const map = {};
        res1d.results.forEach(r => {
          const coin = r.symbol.replace("/USDT", "").replace("/USD", "");
          map[coin] = r;
        });
        setScanMap1d(map);
      }
    } catch (e) { console.error("Scanner fetch:", e); }
  }, [api]);

  const fetchWarnings = useCallback(async () => {
    if (!address) { setPosWarnings([]); return; }
    try {
      const res = await fetch(`${api}/api/notifications/position-warnings?address=${address}`);
      if (!res.ok) return;
      const data = await res.json();
      setPosWarnings(data.warnings || []);
    } catch (_) {}
  }, [address, api]);

  useEffect(() => {
    if (!isConnected || !address) return;
    fetchFast();
    fetchMedium();
    fetchSlow();
    fetchScannerContext();
    fetchWarnings();

    const fastInterval   = setInterval(fetchFast, 15_000);
    const medInterval    = setInterval(fetchMedium, 30_000);
    const slowInterval   = setInterval(fetchSlow, 120_000);
    const scanInterval   = setInterval(fetchScannerContext, 60_000);
    const warnInterval   = setInterval(fetchWarnings, 60_000);

    return () => {
      clearInterval(fastInterval);
      clearInterval(medInterval);
      clearInterval(slowInterval);
      clearInterval(scanInterval);
      clearInterval(warnInterval);
    };
  }, [fetchFast, fetchMedium, fetchSlow, fetchScannerContext, fetchWarnings, isConnected, address]);

  // --- Actions ---

  const closePosition = async (coin, size, isLong) => {
    if (!walletClient) return;
    if (!window.confirm(`Close ${coin} position?`)) return;
    setClosing(coin);
    try {
      const result = await hlClient.closePosition(walletClient, { coin, size, isLong, slippage: 0.02 });
      await fetch(`${api}/api/trade/log-close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: `${coin}/USDT`,
          exit_price: result.avgPx,
          close_order_id: String(result.oid || ""),
        }),
      });
      await fetchFast();
    } catch (e) {
      console.error("Close error:", e);
      alert(e.message || "Failed to close position");
    }
    setClosing(null);
  };

  const cancelOrd = async (coin, oid) => {
    if (!walletClient) return;
    setCancelling(oid);
    try {
      await hlClient.cancelOrder(walletClient, { coin, oid });
      await fetchFast();
    } catch (e) {
      console.error("Cancel error:", e);
      alert(e.message || "Failed to cancel order");
    }
    setCancelling(null);
  };

  // --- Derived data ---

  const marginSummary = chState?.crossMarginSummary || chState?.marginSummary;
  const perpsAccountValue = parseNum(marginSummary?.accountValue);
  const marginUsedVal = parseNum(marginSummary?.totalMarginUsed);
  const withdrawable  = parseNum(chState?.withdrawable);

  // xyz DEX (TradFi) account value
  const xyzMarginSummary = xyzChState?.crossMarginSummary || xyzChState?.marginSummary;
  const xyzAccountValue = parseNum(xyzMarginSummary?.accountValue);

  // Spot balances: stablecoins at face value, other tokens at the scanner's last
  // price when it has one (already fetched, no extra calls), otherwise at cost.
  const spot = useMemo(() => {
    const out = { value: 0, atCost: 0 };
    for (const b of spotState?.balances || []) {
      const total = parseNum(b.total);
      if (total === 0) continue;
      if (b.coin === "USDC" || b.coin === "USDT" || b.coin === "USDH") { out.value += total; continue; }
      const price = scanMap4h[b.coin]?.price;
      if (price > 0) { out.value += total * price; continue; }
      const ntl = parseNum(b.entryNtl);
      if (ntl > 0) { out.value += ntl; out.atCost += 1; }
    }
    return out;
  }, [spotState, scanMap4h]);

  // Positions and unrealized P&L below cover the main perps account only.
  const positions     = (chState?.assetPositions || []).filter(ap => parseNum(ap.position?.szi) !== 0);
  const totalUnrealizedPnl = positions.reduce((sum, ap) => sum + parseNum(ap.position?.unrealizedPnl), 0);
  const xyzPositionCount = (xyzChState?.assetPositions || []).filter(ap => parseNum(ap.position?.szi) !== 0).length;

  // All-time total PnL from portfolio
  const allTimePnl = portfolio?.perpAllTime?.pnlHistory;
  const totalPnl   = allTimePnl?.length > 0 ? allTimePnl[allTimePnl.length - 1].value : null;

  // Fee rates
  const takerRate = fees?.userCrossRate;
  const makerRate = fees?.userAddRate;
  const dailyVlm  = fees?.dailyUserVlm || [];
  const volume30d = dailyVlm.slice(-30).reduce((s, d) => s + parseNum(d.userCross) + parseNum(d.userAdd), 0);

  // Funding summary
  const totalFunding = funding.reduce((s, f) => s + parseNum(f.delta?.usdc), 0);

  return (
    <div style={{ ...S.panel, padding: "0 4px" }}>

      {/* ─── NOT CONNECTED ─── */}
      {!isConnected && (
        <div style={{ ...S.section, padding: "48px 24px", textAlign: "center" }}>
          <div style={{ fontSize: T.textBase, fontFamily: T.font, color: T.text3, marginBottom: 16 }}>
            Connect your wallet to view your Hyperliquid portfolio
          </div>
          <button
            onClick={connect}
            className="terminal-status"
            style={{ color: T.accent, fontSize: T.textSm, fontFamily: T.mono, fontWeight: 700, cursor: "pointer" }}
          >
            Connect wallet
          </button>
          {walletError && (
            <div style={{ marginTop: 10, fontSize: T.textXs, color: T.red, fontFamily: T.mono }}>
              {walletError}
            </div>
          )}
        </div>
      )}

      {/* ─── ACCOUNT SUMMARY BAR ─── */}
      {isConnected && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={S.title}>Hyperliquid account</span>
              <span className="terminal-status" style={S.badge(T.green)}>LIVE</span>
            </div>
            <span style={{ fontSize: T.textXs, fontFamily: T.mono, color: T.text3 }}>
              {address?.slice(0, 6)}...{address?.slice(-4)}
            </span>
          </div>
          <div style={{
            display: "flex", justifyContent: "space-around",
            padding: "16px 20px 8px", gap: 12, flexWrap: "wrap",
          }}>
            <StatBox label="Perps account value" value={fmtUsd(perpsAccountValue)} />
            {xyzChState && xyzAccountValue !== 0 && <StatBox label="TradFi (xyz) account value" value={fmtUsd(xyzAccountValue)} />}
            {spot.value > 0 && <StatBox label="Spot balances" value={fmtUsd(spot.value)} />}
            <StatBox label="Perps unrealized P&L" value={`${totalUnrealizedPnl >= 0 ? "+" : ""}${fmtUsd(totalUnrealizedPnl)}`} color={pnlColor(totalUnrealizedPnl)} />
            <StatBox label="Perps all-time P&L" value={totalPnl != null ? `${totalPnl >= 0 ? "+" : ""}${fmtUsd(totalPnl)}` : "\u2014"} color={pnlColor(totalPnl)} />
            <StatBox label="Perps withdrawable" value={fmtUsd(withdrawable)} />
            <StatBox label="Perps margin used" value={fmtUsd(marginUsedVal)} color={marginUsedVal > 0 ? T.yellow : T.text3} />
          </div>
          <p style={{ padding: "0 20px 14px", fontSize: T.textXs, color: T.text3, lineHeight: 1.6 }}>
            Positions, orders and unrealized P&L below cover the main perps account.
            {xyzPositionCount > 0 && ` ${xyzPositionCount} TradFi (xyz) position${xyzPositionCount === 1 ? " is" : "s are"} held in the separate xyz account and not listed here.`}
            {spot.value > 0 && (spot.atCost > 0
              ? ` Spot tokens are valued at the scanner's last price; ${spot.atCost} without one ${spot.atCost === 1 ? "is" : "are"} shown at cost.`
              : " Spot tokens are valued at the scanner's last price.")}
          </p>
        </div>
      )}

      {/* ─── PORTFOLIO CHART ─── */}
      {isConnected && portfolio && (
        <PortfolioChart
          portfolio={portfolio}
          period={chartPeriod}
          onPeriodChange={setChartPeriod}
          mode={chartMode}
          onModeChange={setChartMode}
        />
      )}

      {/* ─── SECTION TABS ─── */}
      {isConnected && (
        <div style={{ marginBottom: 16 }}>
          <Tabs label="Portfolio sections" value={activeSection} onChange={setActiveSection}
            items={SECTION_TABS.map(tab => ({
              key: tab.key,
              label: `${tab.label}${tab.key === "positions" && positions.length > 0 ? ` (${positions.length})` : ""}${tab.key === "orders" && openOrders.length > 0 ? ` (${openOrders.length})` : ""}`,
            }))} />
        </div>
      )}

      {/* ─── OPEN POSITIONS ─── */}
      {isConnected && activeSection === "positions" && (
        <>
          {/* Scanner check: only when there are positions + scanner data */}
          {positions.length > 0 && Object.keys(scanMap4h).length > 0 && (
            <ScannerCheck positions={positions} scanMap4h={scanMap4h} />
          )}

          <div style={S.section}>
            <div style={S.sectionHeader}>
              <span style={S.title}>
                Open perps positions {positions.length > 0 && `(${positions.length})`}
              </span>
            </div>
            {positions.length === 0 ? (
              <div style={S.empty}>No open positions</div>
            ) : (
              positions.map(ap => (
                <PositionCard
                  key={ap.position?.coin || ap.coin}
                  pos={ap}
                  onClose={closePosition}
                  closing={closing === (ap.position?.coin || ap.coin)}
                  scanMap4h={scanMap4h}
                  scanMap1d={scanMap1d}
                  posWarnings={posWarnings}
                />
              ))
            )}
          </div>
        </>
      )}

      {/* ─── OPEN ORDERS ─── */}
      {isConnected && activeSection === "orders" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>
              Open orders {openOrders.length > 0 && `(${openOrders.length})`}
            </span>
          </div>
          {openOrders.length === 0 ? (
            <div style={S.empty}>No open orders</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={headerCell}>Coin</th>
                    <th style={headerCell}>Type</th>
                    <th style={headerCell}>Side</th>
                    <th style={headerCell}>Price</th>
                    <th style={headerCell}>Trigger</th>
                    <th style={headerCell}>Size</th>
                    <th style={{ ...headerCell, textAlign: "right" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {openOrders.map((o, i) => {
                    const isBuy = o.side === "B";
                    const typeLabel = o.orderType || "Limit";
                    const typeColor = o.isTrigger ? T.yellow : T.text2;
                    return (
                      <tr key={o.oid || i}>
                        <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>{o.coin}</td>
                        <td style={cellStyle}>
                          <span style={S.badge(typeColor)}>{typeLabel}</span>
                          {o.isPositionTpsl && (
                            <span style={{ ...S.badge(T.purple), marginLeft: 8 }}>TP/SL</span>
                          )}
                        </td>
                        <td style={cellStyle}>
                          <span style={{ color: isBuy ? T.green : T.red, fontWeight: 600 }}>
                            {isBuy ? "BUY" : "SELL"}
                          </span>
                        </td>
                        <td style={cellStyle}>{fmtPrice(o.limitPx)}</td>
                        <td style={cellStyle}>{o.isTrigger ? fmtPrice(o.triggerPx) : "\u2014"}</td>
                        <td style={cellStyle}>{o.sz}</td>
                        <td style={{ ...cellStyle, textAlign: "right" }}>
                          <button
                            onClick={() => cancelOrd(o.coin, o.oid)}
                            disabled={cancelling === o.oid}
                            style={{
                              ...S.btn, ...S.btnDanger, padding: "4px 10px",
                              opacity: cancelling === o.oid ? 0.5 : 1,
                            }}
                          >
                            {cancelling === o.oid ? "..." : "Cancel"}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ─── TRADE FILLS ─── */}
      {isConnected && activeSection === "fills" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>
              Recent fills {fills.length > 0 && `(${fills.length})`}
            </span>
          </div>
          {fills.length === 0 ? (
            <div style={S.empty}>No trade fills</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={headerCell}>Time</th>
                    <th style={headerCell}>Coin</th>
                    <th style={headerCell}>Side</th>
                    <th style={headerCell}>Size</th>
                    <th style={headerCell}>Price</th>
                    <th style={{ ...headerCell, textAlign: "right" }}>Closed P&L</th>
                    <th style={{ ...headerCell, textAlign: "right" }}>Fee</th>
                  </tr>
                </thead>
                <tbody>
                  {fills.slice(0, 50).map((f, i) => {
                    const isBuy = f.side === "B";
                    const closedPnl = parseNum(f.closedPnl);
                    const fee = parseNum(f.fee);
                    return (
                      <tr key={f.tid || f.oid || i} style={{
                        background: closedPnl > 0 ? "rgba(52,211,153,0.03)" : closedPnl < 0 ? "rgba(248,113,113,0.03)" : "transparent",
                      }}>
                        <td style={cellStyle}>{timeAgo(f.time)}</td>
                        <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>{f.coin}</td>
                        <td style={cellStyle}>
                          <span style={{ color: isBuy ? T.green : T.red, fontWeight: 600 }}>
                            {isBuy ? "BUY" : "SELL"}
                          </span>
                        </td>
                        <td style={cellStyle}>{f.sz}</td>
                        <td style={cellStyle}>{fmtPrice(f.px)}</td>
                        <td style={{ ...cellStyle, textAlign: "right", fontWeight: closedPnl !== 0 ? 700 : 400, color: pnlColor(closedPnl) }}>
                          {closedPnl !== 0 ? `${closedPnl >= 0 ? "+" : ""}${fmtUsd(closedPnl)}` : "\u2014"}
                        </td>
                        <td style={{ ...cellStyle, textAlign: "right", color: T.text3 }}>
                          {fee !== 0 ? `$${Math.abs(fee).toFixed(4)}` : "\u2014"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ─── FUNDING HISTORY ─── */}
      {isConnected && activeSection === "funding" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={S.title}>Funding history</span>
              {funding.length > 0 && (
                <span style={{ fontSize: T.textXs, fontFamily: T.mono, color: pnlColor(-totalFunding) }}>
                  Total: {totalFunding >= 0 ? "-" : "+"}{fmtUsd(Math.abs(totalFunding))}
                </span>
              )}
            </div>
          </div>
          {funding.length === 0 ? (
            <div style={S.empty}>No funding payments</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={headerCell}>Time</th>
                    <th style={headerCell}>Coin</th>
                    <th style={{ ...headerCell, textAlign: "right" }}>Amount</th>
                    <th style={{ ...headerCell, textAlign: "right" }}>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {funding.slice(0, 50).map((f, i) => {
                    const amt  = parseNum(f.delta?.usdc);
                    const rate = parseNum(f.delta?.fundingRate);
                    return (
                      <tr key={f.hash || i}>
                        <td style={cellStyle}>{timeAgo(f.time)}</td>
                        <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>{f.delta?.coin}</td>
                        <td style={{ ...cellStyle, textAlign: "right", fontWeight: 600, color: pnlColor(amt) }}>
                          {amt >= 0 ? "+" : ""}{fmtUsd(amt)}
                        </td>
                        <td style={{ ...cellStyle, textAlign: "right", color: T.text3 }}>
                          {(rate * 100).toFixed(4)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ─── FEE TIER INFO ─── */}
      {isConnected && activeSection === "fees" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>Fee tier</span>
          </div>
          <div style={{
            display: "flex", justifyContent: "space-around",
            padding: "18px 20px", gap: 12, flexWrap: "wrap",
          }}>
            <StatBox label="Taker rate" value={fmtBps(takerRate)} small />
            <StatBox label="Maker rate" value={fmtBps(makerRate)} small />
            <StatBox label="30-day volume" value={fmtVlm(volume30d)} small />
            {fees?.activeReferralDiscount && parseNum(fees.activeReferralDiscount) > 0 && (
              <StatBox label="Referral discount" value={`${(parseNum(fees.activeReferralDiscount) * 100).toFixed(1)}%`} color={T.purple} small />
            )}
          </div>

          {/* Fee tiers */}
          {fees?.feeSchedule?.tiers?.vip && (
            <div style={{ padding: "0 20px 16px", overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={headerCell}>Tier</th>
                    <th style={headerCell}>Volume required</th>
                    <th style={headerCell}>Taker</th>
                    <th style={headerCell}>Maker</th>
                  </tr>
                </thead>
                <tbody>
                  {fees.feeSchedule.tiers.vip.map((tier, i) => {
                    const cutoff = parseNum(tier.ntlCutoff);
                    const isCurrentTier = volume30d >= cutoff && (
                      !fees.feeSchedule.tiers.vip[i + 1] || volume30d < parseNum(fees.feeSchedule.tiers.vip[i + 1].ntlCutoff)
                    );
                    return (
                      <tr key={i} style={{
                        background: isCurrentTier ? T.accentDim : "transparent",
                      }}>
                        <td style={{ ...cellStyle, fontWeight: isCurrentTier ? 700 : 400, color: isCurrentTier ? T.accent : T.text2 }}>
                          VIP {i}{isCurrentTier ? " (current)" : ""}
                        </td>
                        <td style={cellStyle}>{fmtVlm(cutoff)}</td>
                        <td style={cellStyle}>{fmtBps(tier.cross)}</td>
                        <td style={cellStyle}>{fmtBps(tier.add)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

    </div>
  );
}
