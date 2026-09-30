import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  createChart, AreaSeries, ColorType, LineStyle, CrosshairMode,
} from "lightweight-charts";
import { Link } from "react-router-dom";
import { T, SIGNAL_META, col, resolveToken } from "../theme.js";
import { useTheme } from "../ThemeContext.jsx";
import { useWallet } from "../WalletContext.jsx";
import * as hlClient from "../services/hlClient.js";
import Tabs from "./Tabs.jsx";
import HelpTip from "./HelpTip.jsx";
import TokenLogo from "./TokenLogo.jsx";
import { Skeleton } from "./Skeleton.jsx";
import { RegimeBadge, SignalDot, HeatCell } from "./badges.jsx";
import { WATCH_TIP, WatchMark } from "./radar/shared.jsx";
import useSetupMap from "../hooks/useSetupMap.js";
import { compactUsd } from "../utils/money.js";
import { watchToast } from "../utils/setupMap.js";
import { sideColor, shortAddr } from "../utils/traderFormat.js";
import WalletTag from "./WalletTag.jsx";
import { pollWhileVisible } from "../utils/visiblePoll.js";
import { apiFetch } from "../edge.js";

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

// Profit and loss tokens (theme-aware CSS variables).
function pnlColor(v) {
  if (v == null || v === 0) return T.text3;
  return v > 0 ? T.profit : T.loss;
}

// Once the exchange has accepted an action, a journal failure cannot undo it (from Codex).
async function executeAndJournal(execute, journal) {
  const execution = await execute();
  try {
    const response = await journal(execution);
    if (response && !response.ok) throw new Error(`Journal HTTP ${response.status}`);
    return { execution, journalPending: false };
  } catch {
    return { execution, journalPending: true };
  }
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
const alignColor = a => a === "ALIGNED" ? T.profit : a === "CONFLICTING" ? T.loss : T.text3;

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const S = {
  panel: { padding: 0 },
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
  // Getter: read the loss token at render time
  get btnDanger() {
    return { borderColor: T.loss, color: T.loss };
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

// One figure in the account grid: compact value, the exact amount on hover, a shimmer while loading.
function StatCell({ label, value, exact, color, loading }) {
  return (
    <div className="pf-stat">
      <div className="pf-stat-label">{label}</div>
      {loading ? <Skeleton width="70%" height={22} style={{ marginTop: 2 }} />
        : <div className="pf-stat-value" title={exact} style={{ color: color || T.text1 }}>{value}</div>}
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

function PortfolioChart({ portfolio, period, onPeriodChange, mode, onModeChange, failed = false, onRetry }) {
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
      priceFormat: { type: "custom", formatter: (v) => compactUsd(v), minMove: 0.01 },
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
      <div style={{ position: "relative" }}>
        <div ref={containerRef} style={{ height: 280, width: "100%" }} />
        {!portfolio && !failed && <div className="pf-chart-skel" aria-hidden="true"><Skeleton height="100%" borderRadius={0} /></div>}
        {!portfolio && failed && <div className="pf-chart-failed" role="status"><span>The portfolio history could not load.</span>{onRetry && <button type="button" className="te-link" onClick={onRetry}>Retry</button>}</div>}
      </div>
    </div>
  );
}

// ─── Scanner check (plain facts, no score) ───────────────────────────────────

// Liquidation distance from the scanner's last price, in %, or null.
function liqDistance(ap, scanMap4h) {
  const p = ap.position || ap;
  const liqPx = p.liquidationPx ? parseNum(p.liquidationPx) : null;
  const price = scanMap4h[p.coin]?.price;
  return liqPx && price ? Math.abs(price - liqPx) / price * 100 : null;
}

// Largest positions first; equal values: the one closest to liquidation first.
function sortPositions(positions, scanMap4h) {
  const dist = ap => liqDistance(ap, scanMap4h) ?? Infinity;
  return [...positions].sort((a, b) =>
    Math.abs(parseNum(b.position?.positionValue)) - Math.abs(parseNum(a.position?.positionValue)) || dist(a) - dist(b));
}

// One sentence under the stats: how many positions the 4H signal agrees and disagrees with.
function ScannerCheck({ positions, scanMap4h }) {
  if (positions.length === 0 || Object.keys(scanMap4h).length === 0) return null;
  const rows = positions.map(ap => {
    const isLong = parseNum(ap.position?.szi ?? ap.szi) > 0;
    const ctx = scanMap4h[(ap.position || ap).coin];
    return { ctx, alignment: ctx ? computeAlignment(ctx.signal, isLong) : null };
  });
  const covered    = rows.filter(r => r.ctx);
  const agree      = covered.filter(r => r.alignment === "ALIGNED").length;
  const disagree   = covered.filter(r => r.alignment === "CONFLICTING").length;
  const noSignal   = covered.length - agree - disagree;
  const notScanned = rows.length - covered.length;
  return (
    <div className="pf-check">
      <span className="pf-check-title">Scanner check · 4H</span>
      <span>
        Of {rows.length} open position{rows.length === 1 ? "" : "s"}, the scanner's 4H signal{" "}
        <span style={{ color: T.profit, fontWeight: 600 }}>agrees with {agree}</span>,{" "}
        <span style={{ color: disagree ? T.loss : T.text2, fontWeight: 600 }}>disagrees with {disagree}</span>
        {" "}and gives no clear direction for {noSignal}.
        {notScanned > 0 && ` ${notScanned} ${notScanned === 1 ? "is" : "are"} not covered by the scanner.`}
      </span>
    </div>
  );
}

// ─── Position Card ──────────────────────────────────────────────────────────

// The grid's encodings for this coin: signal (with its context icons), regime, heat bar,
// the 1D signal when it differs, and the verdict against the position on the right.
function ScannerLine({ ctx4h, ctx1d, isLong, alignment }) {
  if (!ctx4h) return <div className="pf-scan"><span className="pf-scan-tf">4H</span><span style={{ color: T.text3 }}>Not covered by the scanner</span></div>;
  return (
    <div className="pf-scan">
      <span className="pf-scan-tf">4H</span>
      <SignalDot signal={ctx4h.signal} reason={ctx4h.signal_reason} warnings={ctx4h.signal_warnings} context={ctx4h} />
      <RegimeBadge regime={ctx4h.regime} noHistory={ctx4h.history_bars === 0} />
      <span className="pf-heat" title="Heat: how stretched the move is (0-100)"><span className="pf-scan-lbl">Heat</span><HeatCell heat={ctx4h.heat} /></span>
      {ctx1d && ctx1d.signal !== ctx4h.signal && (
        <span className="pf-scan-1d"><span className="pf-scan-tf">1D</span><span style={{ color: signalColor(ctx1d.signal), fontFamily: T.mono, fontWeight: 600 }}>{signalLabel(ctx1d.signal)}</span></span>
      )}
      <span className="pf-verdict" style={{ color: alignColor(alignment) }}>
        {alignment === "NEUTRAL" ? ALIGN_TEXT.NEUTRAL : `${ALIGN_TEXT[alignment]} with this ${isLong ? "long" : "short"}`}
      </span>
    </div>
  );
}

// Failed feeds as one line inside the account card: how many readings did not answer, which,
// whether older readings are still shown, and one Retry for all of them.
function FeedsNotice({ failed, onRetry }) {
  const names = failed.map(([name]) => name);
  const kept = failed.some(([, st]) => st.updatedAt);
  return (
    <div className="pf-feeds" role="alert">
      <span className="data-status-dot" style={{ background: T.yellow }} aria-hidden="true" />
      <span>Hyperliquid did not answer for {names.length === 1 ? names[0].toLowerCase() : `${names.length} readings`}
        {names.length > 1 && <span className="pf-feeds-names" title={names.join(", ")}> ({names.join(", ")})</span>}
        {kept ? ". Older readings are kept where there is one." : "."}</span>
      <button type="button" className="te-link" onClick={onRetry}>{names.length > 1 ? "Retry all" : "Retry"}</button>
    </div>
  );
}

// A close/cancel outcome, shown next to what was clicked and scrolled into view, so a failed
// live action is never missed (it replaces alert()).
function ActionNotice({ notice, onDismiss, inSection = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.scrollIntoView?.({ block: "nearest" });
    if (notice.tone === "error") el.focus?.({ preventScroll: true });
  }, [notice]);
  return (
    <div ref={ref} tabIndex={-1} className={inSection ? "pf-notice pf-notice-section" : "pf-notice"} role={notice.tone === "error" ? "alert" : "status"} data-tone={notice.tone}>
      <span>{notice.text}</span>
      <button type="button" className="te-link" onClick={onDismiss}>Dismiss</button>
    </div>
  );
}

function PositionCard({ pos, onClose, closing, readOnly, scanMap4h, scanMap1d, posWarnings, watching, onWatch, notice, onDismissNotice }) {
  const szi = parseNum(pos.position?.szi ?? pos.szi);
  const isLong = szi > 0;
  const side = isLong ? "long" : "short";

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

  const ctx4h = scanMap4h[coin];
  const ctx1d = scanMap1d[coin];
  const liqDistPct = liqDistance(pos, scanMap4h);
  const liqDanger = liqDistPct !== null && liqDistPct < 15;
  const liqTone = liqDistPct !== null && liqDistPct < 8 ? T.loss : T.yellow;
  const alignment = ctx4h ? computeAlignment(ctx4h.signal, isLong) : "NEUTRAL";
  // The card's flag: a left edge in the verdict's colour when the scanner takes a side.
  const flag = alignment === "ALIGNED" ? T.profit : alignment === "CONFLICTING" ? T.loss : null;

  const coinWarnings = (posWarnings || []).filter(w => w.symbol === coin || w.symbol === `${coin}/USDT`);

  return (
    <div className="pf-card" style={flag ? { boxShadow: `inset 2px 0 color-mix(in srgb, ${flag} 55%, transparent)` } : undefined} data-coin={coin}>
      {/* Row 1: logo, coin, side, leverage, liquidation tag; P&L on the right */}
      <div className="pf-card-top">
        <TokenLogo symbol={ctx4h?.symbol || `${coin}/USDT`} size={24} />
        <span className="pf-coin">{coin}</span>
        <span style={{ ...S.badge(sideColor(side)) }}>{side.toUpperCase()}</span>
        <span style={{ ...S.badge(T.text3), fontWeight: 500 }}>{leverage}x {leverageType}</span>
        {liqDanger && <span className="pf-liq" style={S.badge(T.red)}>Liquidation {liqDistPct.toFixed(1)}% away</span>}
        <div className="pf-pnl">
          <div title={fmtUsd(unrealizedPnl)} style={{ fontSize: 16, fontFamily: T.mono, fontWeight: 700, color: pnlColor(unrealizedPnl) }}>
            {compactUsd(unrealizedPnl, { sign: true })}
          </div>
          <div style={{ fontSize: T.textXs, fontFamily: T.mono, color: pnlColor(roe) }}>
            ROE {roe >= 0 ? "+" : ""}{roe.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Row 2: details, then the actions */}
      <div className="pf-card-details">
        {[
          { label: "Entry", val: fmtPrice(entryPx) },
          { label: "Size", val: Math.abs(szi).toFixed(4) },
          { label: "Value", val: compactUsd(posValue), title: fmtUsd(posValue) },
          { label: "Margin", val: compactUsd(marginUsed), title: fmtUsd(marginUsed) },
          ...(liqPx ? [{ label: "Liquidation", val: fmtPrice(liqPx), color: liqDanger ? liqTone : undefined }] : []),
          ...(fundingSinceOpen !== 0 ? [{ label: "Funding", val: `${fundingSinceOpen >= 0 ? "-" : "+"}${compactUsd(Math.abs(fundingSinceOpen))}`, title: fmtUsd(-fundingSinceOpen), color: pnlColor(-fundingSinceOpen) }] : []),
        ].map(d => (
          <div key={d.label} title={d.title}>
            <span style={S.label}>{d.label} </span>
            <span style={{ ...S.value, color: d.color || T.text1 }}>{d.val}</span>
          </div>
        ))}
        <div className="pf-card-actions">
          <Link className="te-link" to={`/radar?tf=4h&focus=${encodeURIComponent(coin)}`}>Open on Radar</Link>
          <button type="button" className="te-link pf-watch" aria-pressed={watching} title={WATCH_TIP} onClick={() => onWatch(coin)}>
            <WatchMark />{watching ? "Watching" : "Watch"}
          </button>
          {!readOnly && (
            <button type="button"
              onClick={() => onClose(coin, Math.abs(szi), isLong)}
              disabled={closing}
              style={{ ...S.btn, ...S.btnDanger, opacity: closing ? 0.5 : 1, cursor: closing ? "not-allowed" : "pointer" }}
            >
              {closing ? "Closing..." : "Close"}
            </button>
          )}
        </div>
      </div>

      {notice && <ActionNotice notice={notice} onDismiss={onDismissNotice} />}

      {/* Row 3: the scanner's reading of this coin */}
      <ScannerLine ctx4h={ctx4h} ctx1d={ctx1d} isLong={isLong} alignment={alignment} />
      {coinWarnings.map((w, i) => (
        <div key={i} className="pf-warning">
          <span style={{ color: w.severity === "critical" ? T.loss : T.yellow, fontWeight: 700 }}>Warning: </span>{w.detail}
        </div>
      ))}
    </div>
  );
}

function PositionSkeleton() {
  return (
    <div className="pf-card" aria-hidden="true">
      <div className="pf-card-top"><Skeleton width={24} height={24} borderRadius={12} /><Skeleton width={70} height={16} /><Skeleton width={46} height={12} /><div className="pf-pnl"><Skeleton width={90} height={16} /></div></div>
      <div className="pf-card-details"><Skeleton width="60%" height={12} /></div>
      <div className="pf-scan"><Skeleton width="40%" height={12} /></div>
    </div>
  );
}

function TableRowsSkeleton({ rows = 4 }) {
  return <div aria-hidden="true">{Array.from({ length: rows }, (_, i) => <div key={i} style={{ padding: "12px 16px", borderBottom: `1px solid ${T.border}` }}><Skeleton width={`${70 - i * 8}%`} height={12} /></div>)}</div>;
}

// ---------------------------------------------------------------------------
// Section tabs (Funding opens from Fills, one click deeper)
// ---------------------------------------------------------------------------

const SECTION_TABS = [
  { key: "positions", label: "Positions" },
  { key: "orders",   label: "Orders" },
  { key: "fills",    label: "Fills" },
];

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function TradingPanel({ api }) {
  const { effectiveAddress, readOnly, viewAddress, setViewAddress, walletClient, connect, error: walletError } = useWallet();
  const account = effectiveAddress;

  // Core data
  const [chState, setChState]     = useState(null);
  const [xyzChState, setXyzChState] = useState(null);
  const [spotState, setSpotState] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [openOrders, setOpenOrders] = useState([]);
  const [fills, setFills]         = useState([]);
  const [funding, setFunding]     = useState([]);

  // Scanner context
  const [scanMap4h, setScanMap4h] = useState({});
  const [scanMap1d, setScanMap1d] = useState({});
  const [posWarnings, setPosWarnings] = useState([]);

  // UI state
  const [chartPeriod, setChartPeriod] = useState("ALL");
  const [chartMode, setChartMode]     = useState("value");
  const [activeSection, setActiveSection] = useState("positions");
  const [moreStats, setMoreStats] = useState(false);
  const [closing, setClosing]     = useState(null);
  const [cancelling, setCancelling] = useState(null);
  const [viewDraft, setViewDraft] = useState("");
  const [viewError, setViewError] = useState(false);

  // Per-feed failure tracking and an account scope (from Codex): a reply that arrives after the
  // address changed is dropped, so one wallet's data never shows under another.
  const [feedState, setFeedState] = useState({});
  const accountScope = useRef(null);
  useEffect(() => {
    const scope = { account };
    accountScope.current = scope;
    return () => { if (accountScope.current === scope) accountScope.current = null; };
  }, [account]);
  const [actionNotice, setActionNotice] = useState(null);
  const recordFeed = (name, ok) => setFeedState(prev => ({ ...prev, [name]: { error: !ok, updatedAt: ok ? Date.now() : prev[name]?.updatedAt } }));
  useEffect(() => {
    setFeedState({}); setActionNotice(null); setChState(null); setOpenOrders([]); setXyzChState(null); setSpotState(null);
    setFills([]); setFunding([]); setPortfolio(null); setPosWarnings([]);
  }, [account]);

  // Watch (Telegram setup messages): the same store as the Radar and the coin page.
  const { watched, telegram, toggleWatch } = useSetupMap("4h");
  const [watchMsg, setWatchMsg] = useState("");
  useEffect(() => { if (!watchMsg) return undefined; const t = setTimeout(() => setWatchMsg(""), 3500); return () => clearTimeout(t); }, [watchMsg]);
  const onWatch = useCallback(async coin => setWatchMsg(watchToast(coin, await toggleWatch(coin, "4h"), telegram)), [toggleWatch, telegram]);

  // --- Data fetching ---

  const loadFeeds = useCallback(async requests => {
    const scope = accountScope.current;
    await Promise.all(requests.map(async ([name, load, apply]) => {
      try {
        const value = await load();
        if (value == null) throw new Error("No reading");
        if (accountScope.current !== scope) return;
        apply(value); recordFeed(name, true);
      } catch { if (accountScope.current === scope) recordFeed(name, false); }
    }));
  }, []);

  const fetchFast = useCallback(async () => {
    if (!account) return;
    await loadFeeds([
      ["Perpetual account", () => hlClient.getClearinghouseState(account), setChState],
      ["Open orders", () => hlClient.getOpenOrders(account), setOpenOrders],
      ["TradFi (xyz) account", () => hlClient.getXyzClearinghouseState(account), setXyzChState],
      ["Spot account", () => hlClient.getSpotState(account), setSpotState],
    ]);
  }, [account, loadFeeds]);

  const fetchMedium = useCallback(async () => {
    if (!account) return;
    await loadFeeds([["Trade fills", () => hlClient.getUserFills(account), f => setFills(f || [])]]);
  }, [account, loadFeeds]);

  const fetchSlow = useCallback(async () => {
    if (!account) return;
    await loadFeeds([["Portfolio history", () => hlClient.getPortfolio(account), setPortfolio]]);
  }, [account, loadFeeds]);

  // Funding payments load only while their view is open.
  const fetchFunding = useCallback(async () => {
    if (!account) return;
    await loadFeeds([["Funding", () => hlClient.getUserFunding(account), f => setFunding(f || [])]]);
  }, [account, loadFeeds]);
  useEffect(() => {
    if (activeSection !== "funding") return undefined;
    fetchFunding();
    const t = setInterval(fetchFunding, 120_000);
    return () => clearInterval(t);
  }, [activeSection, fetchFunding]);

  // Fetch scanner context + position warnings
  const fetchScannerContext = useCallback(async () => {
    try {
      const [res4h, res1d] = await Promise.all([
        apiFetch("/api/scan?timeframe=4h&view=list").then(r => r.ok ? r.json() : null).catch(() => null),
        apiFetch("/api/scan?timeframe=1d&view=list").then(r => r.ok ? r.json() : null).catch(() => null),
      ]);
      const toMap = res => {
        const map = {};
        for (const r of res.results) {
          if ((r.market_kind || "perpetual") !== "perpetual") continue;   // a perp position reads the perp row
          map[r.symbol.replace("/USDT", "").replace("/USD", "")] = r;
        }
        return map;
      };
      if (res4h?.results) setScanMap4h(toMap(res4h));
      if (res1d?.results) setScanMap1d(toMap(res1d));
    } catch (e) { console.error("Scanner fetch:", e); }
  }, [api]);

  const fetchWarnings = useCallback(async () => {
    if (!account) { setPosWarnings([]); return; }
    const scope = accountScope.current;
    try {
      const res = await fetch(`${api}/api/notifications/position-warnings?address=${account}`);
      if (!res.ok) return;
      const data = await res.json();
      if (accountScope.current === scope) setPosWarnings(data.warnings || []);
    } catch (_) {}
  }, [account, api]);

  useEffect(() => {
    if (!account) return;
    fetchFast();
    fetchMedium();
    fetchSlow();
    fetchScannerContext();
    fetchWarnings();

    const fastInterval   = setInterval(fetchFast, 15_000);
    const medInterval    = setInterval(fetchMedium, 30_000);
    const slowInterval   = setInterval(fetchSlow, 120_000);
    // Reflex server reads (the three above go to Hyperliquid): paused while hidden.
    const stopScan       = pollWhileVisible(fetchScannerContext, 60_000);
    const stopWarn       = pollWhileVisible(fetchWarnings, 60_000);

    return () => {
      clearInterval(fastInterval);
      clearInterval(medInterval);
      clearInterval(slowInterval);
      stopScan();
      stopWarn();
    };
  }, [fetchFast, fetchMedium, fetchSlow, fetchScannerContext, fetchWarnings, account]);

  // --- Actions (never on a read-only address) ---

  const closePosition = async (coin, size, isLong) => {
    if (readOnly || !walletClient) return;
    if (!window.confirm(`Close ${coin} position?`)) return;
    setClosing(coin);
    setActionNotice(null);
    try {
      const outcome = await executeAndJournal(
        () => hlClient.closePosition(walletClient, { coin, size, isLong, slippage: 0.02 }),
        result => fetch(`${api}/api/trade/log-close`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol: `${coin}/USDT`,
            exit_price: result.avgPx,
            close_order_id: String(result.oid || ""),
          }),
        }),
      );
      setActionNotice({ section: "positions", coin, tone: "ok", text: `${coin} closed. Order ${outcome.execution?.oid || "accepted"}.${outcome.journalPending ? " Journal sync pending; do not close again." : " Journal synced."}` });
      await fetchFast();
    } catch (e) {
      console.error("Close error:", e);
      setActionNotice({ section: "positions", coin, tone: "error", text: `Close could not be confirmed: ${e.message || "connection failed"}. Refresh positions and check the exchange before trying again.` });
    }
    setClosing(null);
  };

  const cancelOrd = async (coin, oid) => {
    if (readOnly || !walletClient) return;
    setCancelling(oid);
    setActionNotice(null);
    try {
      await hlClient.cancelOrder(walletClient, { coin, oid });
      await fetchFast();
    } catch (e) {
      console.error("Cancel error:", e);
      setActionNotice({ section: "orders", coin, tone: "error", text: `Cancellation could not be confirmed: ${e.message || "connection failed"}. Refresh orders before trying again.` });
    }
    setCancelling(null);
  };

  const submitView = e => {
    e.preventDefault();
    const ok = setViewAddress(viewDraft.trim());
    setViewError(!ok || !viewDraft.trim());
    if (ok && viewDraft.trim()) setViewDraft("");
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
  const positions = useMemo(() => sortPositions((chState?.assetPositions || []).filter(ap => parseNum(ap.position?.szi) !== 0), scanMap4h), [chState, scanMap4h]);
  const totalUnrealizedPnl = positions.reduce((sum, ap) => sum + parseNum(ap.position?.unrealizedPnl), 0);
  const xyzPositionCount = (xyzChState?.assetPositions || []).filter(ap => parseNum(ap.position?.szi) !== 0).length;

  // All-time total PnL from portfolio
  const allTimePnl = portfolio?.perpAllTime?.pnlHistory;
  const totalPnl   = allTimePnl?.length > 0 ? allTimePnl[allTimePnl.length - 1].value : null;

  // Funding summary
  const totalFunding = funding.reduce((s, f) => s + parseNum(f.delta?.usdc), 0);

  // Loading: a feed with neither a reading nor a failure yet.
  const pending = name => !feedState[name];
  const chLoading = !chState && pending("Perpetual account");
  const failed = Object.entries(feedState).filter(([, st]) => st.error);
  // The perps account feed failed with no reading yet: its figures are unknown, not $0.
  const chMissing = !chState && !!feedState["Perpetual account"]?.error;
  const chStale = !!chState && !!feedState["Perpetual account"]?.error;
  const dashIf = (missing, v) => (missing ? "—" : v);
  const retryAll = () => { fetchFast(); fetchMedium(); fetchSlow(); if (activeSection === "funding") fetchFunding(); };
  const dismissNotice = () => setActionNotice(null);
  // A close outcome sits inside that coin's card; once the card is gone (closed), above the cards.
  const positionsNotice = actionNotice?.section === "positions" ? actionNotice : null;
  const noticeCardShown = !!positionsNotice && !chLoading && positions.some(ap => (ap.position?.coin || ap.coin) === positionsNotice.coin);

  const signedUsd = v => compactUsd(v, { sign: true });
  const stats = [
    { label: "Account value", value: dashIf(chMissing, compactUsd(perpsAccountValue)), exact: chMissing ? undefined : fmtUsd(perpsAccountValue), color: chMissing ? T.text3 : undefined, loading: chLoading },
    { label: "Unrealized P&L", value: dashIf(chMissing, signedUsd(totalUnrealizedPnl)), exact: chMissing ? undefined : fmtUsd(totalUnrealizedPnl), color: chMissing ? T.text3 : pnlColor(totalUnrealizedPnl), loading: chLoading },
    { label: "All-time P&L", value: totalPnl != null ? signedUsd(totalPnl) : "—", exact: totalPnl != null ? fmtUsd(totalPnl) : undefined, color: pnlColor(totalPnl), loading: totalPnl == null && pending("Portfolio history") },
    { label: "Withdrawable", value: dashIf(chMissing, compactUsd(withdrawable)), exact: chMissing ? undefined : fmtUsd(withdrawable), color: chMissing ? T.text3 : undefined, loading: chLoading },
    { label: "TradFi (xyz)", value: xyzChState ? compactUsd(xyzAccountValue) : "—", exact: xyzChState ? fmtUsd(xyzAccountValue) : undefined, color: xyzAccountValue ? undefined : T.text3, loading: !xyzChState && pending("TradFi (xyz) account") },
    { label: "Spot", value: spotState ? compactUsd(spot.value) : "—", exact: spotState ? fmtUsd(spot.value) : undefined, color: spot.value ? undefined : T.text3, loading: !spotState && pending("Spot account") },
    { label: "Margin used", value: dashIf(chMissing, compactUsd(marginUsedVal)), exact: chMissing ? undefined : fmtUsd(marginUsedVal), color: marginUsedVal > 0 ? T.yellow : T.text3, loading: chLoading },
  ];
  // Three figures in view; the rest behind More.
  const mainStats = stats.filter(st => ["Account value", "Unrealized P&L", "Withdrawable"].includes(st.label));
  const moreList = stats.filter(st => !mainStats.includes(st));

  return (
    <div className="pf-page" style={S.panel}>

      {/* ─── NOT CONNECTED: connect, or look at any address read-only ─── */}
      {!account && (
        <div className="pf-connect" style={{ ...S.section, padding: "48px 24px", textAlign: "center" }}>
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
            <div style={{ marginTop: 10, fontSize: T.textXs, color: T.loss, fontFamily: T.mono }}>
              {walletError}
            </div>
          )}
          <form className="pf-view-form" onSubmit={submitView}>
            <label htmlFor="pf-view-input">or view an address (read-only)</label>
            <span className="pf-view-row">
              <input id="pf-view-input" className="smap-addr pf-view-input" value={viewDraft} placeholder="0x…" spellCheck={false} autoComplete="off"
                aria-invalid={viewError || undefined} aria-describedby={viewError ? "pf-view-error" : undefined}
                onChange={e => { setViewDraft(e.target.value); setViewError(false); }} />
              <button type="submit" className="te-link pf-view-go">View</button>
            </span>
            {viewError && <span id="pf-view-error" className="pf-view-error">Not a Hyperliquid address (0x and 40 hex characters).</span>}
          </form>
        </div>
      )}

      {/* ─── READ-ONLY BANNER ─── */}
      {readOnly && (
        <div className="pf-viewing" role="status">
          <span>Viewing <b>{shortAddr(viewAddress)}</b> <WalletTag address={viewAddress} size={20} className="pf-view-tag" /></span>
          <span className="pf-dot" aria-hidden="true">·</span>
          <span>read-only</span>
          <span className="pf-dot" aria-hidden="true">·</span>
          <button type="button" className="te-link" onClick={() => setViewAddress("")}>Stop viewing</button>
        </div>
      )}

      {/* ─── NOTICES: close/cancel outcomes and failed feeds, inline (no dialogs) ─── */}
      {actionNotice && actionNotice.section !== activeSection && <ActionNotice notice={actionNotice} onDismiss={dismissNotice} />}


      {/* ─── ACCOUNT SUMMARY ─── */}
      {account && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={S.title}>Hyperliquid account <HelpTip title="What this covers" width={380}>
                <p>Account value, unrealized P&amp;L, positions and orders cover the main perps account.{xyzPositionCount > 0 && ` ${xyzPositionCount} TradFi (xyz) position${xyzPositionCount === 1 ? " is" : "s are"} held in the separate xyz account and not listed here.`}</p>
                {spot.value > 0 && <p>{spot.atCost > 0
                  ? `Spot tokens are valued at the scanner's last price; ${spot.atCost} without one ${spot.atCost === 1 ? "is" : "are"} shown at cost.`
                  : "Spot tokens are valued at the scanner's last price."}</p>}
              </HelpTip></span>
              {/* LIVE only while the account feed answers; STALE keeps the last reading, OFFLINE has none. */}
              {chMissing ? <span className="terminal-status" style={S.badge(T.text3)} title="Hyperliquid did not answer; no reading yet">OFFLINE</span>
                : chStale ? <span className="terminal-status" style={S.badge(T.yellow)} title="Hyperliquid did not answer; showing the last reading">STALE</span>
                : <span className="terminal-status" style={S.badge(T.green)}>LIVE</span>}
            </div>
            <span style={{ fontSize: T.textXs, fontFamily: T.mono, color: T.text3 }}>
              {account.slice(0, 6)}...{account.slice(-4)}
            </span>
          </div>
          {failed.length > 0 && <FeedsNotice failed={failed} onRetry={retryAll} />}
          <div className="pf-stats">
            {mainStats.map(st => <StatCell key={st.label} {...st} />)}
            <div className="pf-stat pf-more">
              <button type="button" className="te-link" aria-expanded={moreStats} aria-controls="pf-more-stats" aria-label={moreStats ? "Fewer account figures" : "More account figures"} onClick={() => setMoreStats(v => !v)}>{moreStats ? "Less" : "More"}</button>
            </div>
            {moreStats && <div id="pf-more-stats" className="pf-stats-more">{moreList.map(st => <StatCell key={st.label} {...st} />)}</div>}
          </div>
          <ScannerCheck positions={positions} scanMap4h={scanMap4h} />
        </div>
      )}

      {/* ─── PORTFOLIO CHART ─── */}
      {account && (
        <PortfolioChart
          portfolio={portfolio}
          period={chartPeriod}
          onPeriodChange={setChartPeriod}
          mode={chartMode}
          onModeChange={setChartMode}
          failed={!!feedState["Portfolio history"]?.error}
          onRetry={fetchSlow}
        />
      )}

      {/* ─── SECTION TABS ─── */}
      {account && (
        <div style={{ marginBottom: 16 }}>
          <Tabs label="Portfolio sections" value={activeSection === "funding" ? "fills" : activeSection} onChange={setActiveSection}
            items={SECTION_TABS.map(tab => ({
              key: tab.key,
              label: `${tab.label}${tab.key === "positions" && positions.length > 0 ? ` (${positions.length})` : ""}${tab.key === "orders" && openOrders.length > 0 ? ` (${openOrders.length})` : ""}`,
            }))} />
        </div>
      )}

      {/* ─── OPEN POSITIONS ─── */}
      {account && activeSection === "positions" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>
              Open perps positions {positions.length > 0 && `(${positions.length})`}
            </span>
          </div>
          {positionsNotice && !noticeCardShown && <ActionNotice notice={positionsNotice} onDismiss={dismissNotice} inSection />}
          {chLoading ? (
            <><PositionSkeleton /><PositionSkeleton /><PositionSkeleton /></>
          ) : chMissing ? (
            <div style={S.empty}>Positions could not load. <button type="button" className="te-link" onClick={retryAll}>Retry</button></div>
          ) : positions.length === 0 ? (
            <div style={S.empty}>No open positions</div>
          ) : (
            positions.map(ap => (
              <PositionCard
                key={ap.position?.coin || ap.coin}
                pos={ap}
                onClose={closePosition}
                closing={closing === (ap.position?.coin || ap.coin)}
                readOnly={readOnly}
                scanMap4h={scanMap4h}
                scanMap1d={scanMap1d}
                posWarnings={posWarnings}
                watching={watched.has(ap.position?.coin || ap.coin)}
                onWatch={onWatch}
                notice={noticeCardShown && positionsNotice.coin === (ap.position?.coin || ap.coin) ? positionsNotice : null}
                onDismissNotice={dismissNotice}
              />
            ))
          )}
        </div>
      )}

      {/* ─── OPEN ORDERS ─── */}
      {account && activeSection === "orders" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>
              Open orders {openOrders.length > 0 && `(${openOrders.length})`}
            </span>
          </div>
          {actionNotice?.section === "orders" && <ActionNotice notice={actionNotice} onDismiss={dismissNotice} inSection />}
          {pending("Open orders") ? <TableRowsSkeleton /> : openOrders.length === 0 ? (
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
                    {!readOnly && <th style={{ ...headerCell, textAlign: "right" }}>Action</th>}
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
                        {!readOnly && <td style={{ ...cellStyle, textAlign: "right" }}>
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
                        </td>}
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
      {account && activeSection === "fills" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>
              Recent fills {fills.length > 0 && `(${fills.length})`}
            </span>
            <button type="button" className="te-link pf-sub" onClick={() => setActiveSection("funding")}>Funding payments</button>
          </div>
          {pending("Trade fills") ? <TableRowsSkeleton /> : fills.length === 0 ? (
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
      {account && activeSection === "funding" && (
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
            <button type="button" className="te-link pf-sub" onClick={() => setActiveSection("fills")}>Back to fills</button>
          </div>
          {pending("Funding") ? <TableRowsSkeleton /> : funding.length === 0 ? (
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

      {watchMsg && <div className="smap-toast" role="status">{watchMsg}</div>}
    </div>
  );
}
