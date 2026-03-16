import { useState, useEffect, useCallback, useRef } from "react";
import {
  createChart, AreaSeries, ColorType, LineStyle, CrosshairMode,
} from "lightweight-charts";
import { T } from "../theme.js";
import { useWallet } from "../WalletContext.jsx";
import * as hlClient from "../services/hlClient.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(ts) {
  if (!ts) return "\u2014";
  const s = typeof ts === "number" && ts > 1e12 ? ts / 1000 : ts;
  const diff = (Date.now() / 1000) - s;
  if (diff < 60)   return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${(diff / 3600).toFixed(1)}h ago`;
  return `${(diff / 86400).toFixed(1)}d ago`;
}

function fmtUsd(v) {
  if (v == null) return "\u2014";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (isNaN(n)) return "\u2014";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPrice(p) {
  if (!p) return "\u2014";
  const n = typeof p === "string" ? parseFloat(p) : p;
  if (isNaN(n)) return "\u2014";
  if (n >= 1000) return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (n >= 1) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(6)}`;
}

function fmtPnl(pct) {
  if (pct == null) return "\u2014";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function fmtVlm(v) {
  if (!v) return "$0";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

function fmtBps(rate) {
  if (!rate) return "\u2014";
  const bps = parseFloat(rate) * 10000;
  return `${bps.toFixed(2)} bps`;
}

function pnlColor(v) {
  if (v == null || v === 0) return T.text3;
  return v > 0 ? "#34d399" : "#f87171";
}

function parseNum(v) {
  if (v == null) return 0;
  const n = typeof v === "string" ? parseFloat(v) : v;
  return isNaN(n) ? 0 : n;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const S = {
  panel: { padding: 0, maxWidth: 1200, margin: "0 auto" },
  section: {
    background: T.surface, border: `1px solid ${T.border}`,
    borderRadius: T.radius, marginBottom: 16, overflow: "hidden",
  },
  sectionHeader: {
    padding: "14px 20px", borderBottom: `1px solid ${T.border}`,
    display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
  },
  title: {
    fontSize: 11, fontWeight: 700, fontFamily: T.mono, color: T.text2,
    letterSpacing: "0.08em", textTransform: "uppercase",
  },
  btn: {
    padding: "6px 14px", borderRadius: 6, border: `1px solid ${T.overlay12}`,
    background: T.overlay04, color: T.text1, fontSize: 11, fontFamily: T.mono,
    fontWeight: 600, cursor: "pointer", transition: "all 0.15s",
  },
  btnDanger: {
    background: "rgba(248,113,113,0.08)", borderColor: "rgba(248,113,113,0.2)", color: "#f87171",
  },
  label: { fontSize: 11, fontFamily: T.font, color: T.text3, fontWeight: 500 },
  value: { fontSize: 13, fontFamily: T.mono, color: T.text1, fontWeight: 600 },
  badge: (bg, color, border) => ({
    display: "inline-block", padding: "3px 10px", borderRadius: 5,
    background: bg, color, border: `1px solid ${border}`,
    fontSize: 10, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em",
  }),
  pillBtn: (active) => ({
    padding: "4px 12px", borderRadius: 5, cursor: "pointer",
    border: active ? "1px solid rgba(34,211,238,0.4)" : `1px solid ${T.overlay08}`,
    background: active ? "rgba(34,211,238,0.12)" : T.overlay04,
    color: active ? "#22d3ee" : T.text3,
    fontSize: 10, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em",
    transition: "all 0.15s",
  }),
  empty: {
    padding: "24px 20px", textAlign: "center",
    color: T.text4, fontSize: 12, fontFamily: T.mono,
  },
};

const cellStyle = {
  padding: "10px 14px", fontSize: 12, fontFamily: T.mono, color: T.text2,
  borderBottom: `1px solid ${T.border}`, whiteSpace: "nowrap",
};
const headerCell = {
  padding: "10px 14px", fontSize: 9, fontFamily: T.mono, fontWeight: 700,
  color: T.text3, letterSpacing: "0.1em", textTransform: "uppercase",
  borderBottom: `1px solid ${T.borderH}`, textAlign: "left",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatBox({ label, value, color, small }) {
  return (
    <div style={{ textAlign: "center", minWidth: small ? 70 : 90 }}>
      <div style={{ ...S.value, fontSize: small ? 14 : 18, color: color || T.text1 }}>{value}</div>
      <div style={{ ...S.label, fontSize: 9, marginTop: 2 }}>{label}</div>
    </div>
  );
}

// ─── Portfolio Chart ────────────────────────────────────────────────────────

const PERIODS = [
  { key: "1D", label: "1D", sdk: "perpDay" },
  { key: "1W", label: "1W", sdk: "perpWeek" },
  { key: "1M", label: "1M", sdk: "perpMonth" },
  { key: "ALL", label: "ALL", sdk: "perpAllTime" },
];

function PortfolioChart({ portfolio, period, onPeriodChange, mode, onModeChange }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

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

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 280,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: T.text3,
        fontFamily: "'SF Mono', 'Fira Code', monospace",
        fontSize: 10,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.02)" },
        horzLines: { color: "rgba(255,255,255,0.025)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "rgba(34,211,238,0.15)", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#1a1a1e" },
        horzLine: { color: "rgba(34,211,238,0.15)", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#1a1a1e" },
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.06)",
        timeVisible: true, secondsVisible: false,
        rightOffset: 3, minBarSpacing: 1,
      },
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.06)",
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    });
    chartRef.current = chart;

    const lineColor = mode === "value"
      ? "#22d3ee"
      : (isPositive ? "#34d399" : "#f87171");
    const topColor = mode === "value"
      ? "rgba(34,211,238,0.18)"
      : (isPositive ? "rgba(52,211,153,0.18)" : "rgba(248,113,113,0.18)");

    const areaSeries = chart.addSeries(AreaSeries, {
      topColor,
      bottomColor: "transparent",
      lineColor,
      lineWidth: 2,
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderWidth: 1,
      crosshairMarkerBorderColor: lineColor,
      priceFormat: { type: "custom", formatter: (v) => `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}` },
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
  }, [portfolio, period, mode]);

  const sdkPeriod = PERIODS.find(p => p.key === period)?.sdk || "perpAllTime";
  const vlm = portfolio?.[sdkPeriod]?.vlm;

  return (
    <div style={S.section}>
      <div style={S.sectionHeader}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={S.title}>Portfolio</span>
          {vlm > 0 && (
            <span style={{ fontSize: 10, fontFamily: T.mono, color: T.text4 }}>
              Vol: {fmtVlm(vlm)}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {/* Mode toggle */}
          <button style={S.pillBtn(mode === "value")} onClick={() => onModeChange("value")}>VALUE</button>
          <button style={S.pillBtn(mode === "pnl")} onClick={() => onModeChange("pnl")}>PnL</button>
          <div style={{ width: 1, background: T.overlay12, margin: "0 4px" }} />
          {/* Period toggle */}
          {PERIODS.map(p => (
            <button key={p.key} style={S.pillBtn(period === p.key)} onClick={() => onPeriodChange(p.key)}>
              {p.label}
            </button>
          ))}
        </div>
      </div>
      <div ref={containerRef} style={{ height: 280, width: "100%" }} />
    </div>
  );
}

// ─── Position Card ──────────────────────────────────────────────────────────

function PositionCard({ pos, onClose, closing }) {
  const szi = parseNum(pos.position?.szi ?? pos.szi);
  const isLong = szi > 0;
  const side = isLong ? "LONG" : "SHORT";
  const sideColor = isLong ? "#34d399" : "#f87171";
  const sideBg = isLong ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.12)";
  const sideBorder = isLong ? "rgba(52,211,153,0.25)" : "rgba(248,113,113,0.25)";

  const p = pos.position || pos;
  const coin = p.coin;
  const leverage = p.leverage?.value ?? "?";
  const leverageType = p.leverage?.type === "isolated" ? "ISO" : "CROSS";
  const entryPx = parseNum(p.entryPx);
  const posValue = parseNum(p.positionValue);
  const unrealizedPnl = parseNum(p.unrealizedPnl);
  const roe = parseNum(p.returnOnEquity) * 100;
  const liqPx = p.liquidationPx ? parseNum(p.liquidationPx) : null;
  const marginUsed = parseNum(p.marginUsed);
  const fundingSinceOpen = parseNum(p.cumFunding?.sinceOpen);

  return (
    <div style={{ padding: "14px 20px", borderBottom: `1px solid ${T.border}` }}>
      {/* Row 1: Coin + badges + PnL */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 15, fontFamily: T.mono, fontWeight: 700, color: T.text1 }}>{coin}</span>
        <span style={S.badge(sideBg, sideColor, sideBorder)}>{side}</span>
        <span style={S.badge("rgba(139,92,246,0.12)", "#8b5cf6", "rgba(139,92,246,0.3)")}>
          {leverage}x {leverageType}
        </span>
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div style={{ fontSize: 14, fontFamily: T.mono, fontWeight: 700, color: pnlColor(unrealizedPnl) }}>
            {unrealizedPnl >= 0 ? "+" : ""}{fmtUsd(unrealizedPnl)}
          </div>
          <div style={{ fontSize: 10, fontFamily: T.mono, color: pnlColor(roe) }}>
            ROE {roe >= 0 ? "+" : ""}{roe.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Row 2: Details */}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
        <div>
          <span style={S.label}>Entry </span>
          <span style={S.value}>{fmtPrice(entryPx)}</span>
        </div>
        <div>
          <span style={S.label}>Size </span>
          <span style={S.value}>{Math.abs(szi).toFixed(4)}</span>
        </div>
        <div>
          <span style={S.label}>Value </span>
          <span style={S.value}>{fmtUsd(posValue)}</span>
        </div>
        <div>
          <span style={S.label}>Margin </span>
          <span style={S.value}>{fmtUsd(marginUsed)}</span>
        </div>
        {liqPx && (
          <div>
            <span style={S.label}>Liq </span>
            <span style={{ ...S.value, color: "#f87171" }}>{fmtPrice(liqPx)}</span>
          </div>
        )}
        {fundingSinceOpen !== 0 && (
          <div>
            <span style={S.label}>Funding </span>
            <span style={{ ...S.value, color: pnlColor(-fundingSinceOpen) }}>
              {fundingSinceOpen >= 0 ? "-" : "+"}{fmtUsd(Math.abs(fundingSinceOpen))}
            </span>
          </div>
        )}
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
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mobile section tabs
// ---------------------------------------------------------------------------

const SECTION_TABS = [
  { key: "positions", label: "POSITIONS" },
  { key: "orders", label: "ORDERS" },
  { key: "fills", label: "FILLS" },
  { key: "funding", label: "FUNDING" },
  { key: "fees", label: "FEES" },
];

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function TradingPanel({ api }) {
  const { address, isConnected, walletClient, connect, error: walletError } = useWallet();

  // Core data
  const [chState, setChState] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [openOrders, setOpenOrders] = useState([]);
  const [fills, setFills] = useState([]);
  const [funding, setFunding] = useState([]);
  const [fees, setFees] = useState(null);
  const [history, setHistory] = useState({ trades: [], stats: {} });

  // UI state
  const [chartPeriod, setChartPeriod] = useState("ALL");
  const [chartMode, setChartMode] = useState("value");
  const [activeSection, setActiveSection] = useState("positions");
  const [closing, setClosing] = useState(null);
  const [cancelling, setCancelling] = useState(null);

  // --- Data fetching ---

  const fetchFast = useCallback(async () => {
    if (!isConnected || !address) return;
    try {
      const [state, orders] = await Promise.all([
        hlClient.getClearinghouseState(address).catch(() => null),
        hlClient.getOpenOrders(address).catch(() => null),
      ]);
      if (state) setChState(state);
      if (orders) setOpenOrders(orders);
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

  useEffect(() => {
    if (!isConnected || !address) return;
    fetchFast();
    fetchMedium();
    fetchSlow();
    const fastInterval = setInterval(fetchFast, 15_000);
    const medInterval = setInterval(fetchMedium, 30_000);
    return () => { clearInterval(fastInterval); clearInterval(medInterval); };
  }, [fetchFast, fetchMedium, fetchSlow, isConnected, address]);

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
  const accountValue = parseNum(marginSummary?.accountValue);
  const marginUsed = parseNum(marginSummary?.totalMarginUsed);
  const withdrawable = parseNum(chState?.withdrawable);
  const positions = (chState?.assetPositions || []).filter(ap => parseNum(ap.position?.szi) !== 0);
  const totalUnrealizedPnl = positions.reduce((sum, ap) => sum + parseNum(ap.position?.unrealizedPnl), 0);

  // All-time total PnL from portfolio
  const allTimePnl = portfolio?.perpAllTime?.pnlHistory;
  const totalPnl = allTimePnl?.length > 0 ? allTimePnl[allTimePnl.length - 1].value : null;

  // Fee rates
  const takerRate = fees?.userCrossRate;
  const makerRate = fees?.userAddRate;
  const dailyVlm = fees?.dailyUserVlm || [];
  const volume30d = dailyVlm.slice(-30).reduce((s, d) => s + parseNum(d.userCross) + parseNum(d.userAdd), 0);

  // Funding summary
  const totalFunding = funding.reduce((s, f) => s + parseNum(f.delta?.usdc), 0);

  return (
    <div style={S.panel}>

      {/* ─── NOT CONNECTED ─── */}
      {!isConnected && (
        <div style={{ ...S.section, padding: "40px 20px", textAlign: "center" }}>
          <div style={{ fontSize: 12, fontFamily: T.mono, color: T.text3, marginBottom: 14 }}>
            Connect your wallet to view portfolio
          </div>
          <button
            onClick={connect}
            style={{
              padding: "10px 32px", borderRadius: 10,
              border: "1px solid rgba(139,92,246,0.3)",
              background: "rgba(139,92,246,0.08)",
              color: "#8b5cf6",
              fontSize: 12, fontFamily: T.mono, fontWeight: 700,
              cursor: "pointer", letterSpacing: "0.06em",
            }}
          >
            Connect Wallet
          </button>
          {walletError && (
            <div style={{ marginTop: 8, fontSize: 10, color: "#f87171", fontFamily: T.mono }}>
              {walletError}
            </div>
          )}
        </div>
      )}

      {/* ─── ACCOUNT SUMMARY BAR ─── */}
      {isConnected && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={S.title}>Hyperliquid Portfolio</span>
              <span style={S.badge("rgba(52,211,153,0.12)", "#34d399", "rgba(52,211,153,0.3)")}>LIVE</span>
            </div>
            <span style={{ fontSize: 10, fontFamily: T.mono, color: T.text4 }}>
              {address?.slice(0, 6)}...{address?.slice(-4)}
            </span>
          </div>
          <div style={{
            display: "flex", justifyContent: "space-around",
            padding: "16px 20px", gap: 16, flexWrap: "wrap",
          }}>
            <StatBox label="ACCOUNT VALUE" value={fmtUsd(accountValue)} />
            <StatBox label="UNREALIZED PnL" value={`${totalUnrealizedPnl >= 0 ? "+" : ""}${fmtUsd(totalUnrealizedPnl)}`} color={pnlColor(totalUnrealizedPnl)} />
            <StatBox label="TOTAL PnL" value={totalPnl != null ? `${totalPnl >= 0 ? "+" : ""}${fmtUsd(totalPnl)}` : "\u2014"} color={pnlColor(totalPnl)} />
            <StatBox label="AVAILABLE" value={fmtUsd(withdrawable)} />
            <StatBox label="MARGIN USED" value={fmtUsd(marginUsed)} color={marginUsed > 0 ? "#fbbf24" : T.text3} />
          </div>
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

      {/* ─── SECTION TAB BAR (acts as filter for sections below) ─── */}
      {isConnected && (
        <div style={{
          display: "flex", gap: 4, marginBottom: 16, flexWrap: "wrap",
          padding: "0 2px",
        }}>
          {SECTION_TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveSection(tab.key)}
              style={{
                ...S.pillBtn(activeSection === tab.key),
                padding: "6px 14px", fontSize: 11,
              }}
            >
              {tab.label}
              {tab.key === "positions" && positions.length > 0 && ` (${positions.length})`}
              {tab.key === "orders" && openOrders.length > 0 && ` (${openOrders.length})`}
            </button>
          ))}
        </div>
      )}

      {/* ─── OPEN POSITIONS ─── */}
      {isConnected && activeSection === "positions" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>
              Open Positions {positions.length > 0 && `(${positions.length})`}
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
              />
            ))
          )}
        </div>
      )}

      {/* ─── OPEN ORDERS ─── */}
      {isConnected && activeSection === "orders" && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>
              Open Orders {openOrders.length > 0 && `(${openOrders.length})`}
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
                    const typeBg = o.isTrigger ? "rgba(251,191,36,0.12)" : T.overlay04;
                    const typeColor = o.isTrigger ? "#fbbf24" : T.text2;
                    const typeBorder = o.isTrigger ? "rgba(251,191,36,0.3)" : T.overlay12;
                    return (
                      <tr key={o.oid || i}>
                        <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>{o.coin}</td>
                        <td style={cellStyle}>
                          <span style={S.badge(typeBg, typeColor, typeBorder)}>{typeLabel}</span>
                          {o.isPositionTpsl && (
                            <span style={{ ...S.badge("rgba(139,92,246,0.12)", "#8b5cf6", "rgba(139,92,246,0.3)"), marginLeft: 4 }}>TP/SL</span>
                          )}
                        </td>
                        <td style={cellStyle}>
                          <span style={{ color: isBuy ? "#34d399" : "#f87171", fontWeight: 600 }}>
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
                              ...S.btn, ...S.btnDanger, padding: "4px 10px", fontSize: 10,
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
              Recent Fills {fills.length > 0 && `(${fills.length})`}
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
                    <th style={{ ...headerCell, textAlign: "right" }}>Closed PnL</th>
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
                          <span style={{ color: isBuy ? "#34d399" : "#f87171", fontWeight: 600 }}>
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
              <span style={S.title}>Funding History</span>
              {funding.length > 0 && (
                <span style={{ fontSize: 11, fontFamily: T.mono, color: pnlColor(-totalFunding) }}>
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
                    const amt = parseNum(f.delta?.usdc);
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
            <span style={S.title}>Fee Tier</span>
          </div>
          <div style={{
            display: "flex", justifyContent: "space-around",
            padding: "16px 20px", gap: 16, flexWrap: "wrap",
          }}>
            <StatBox label="TAKER RATE" value={fmtBps(takerRate)} small />
            <StatBox label="MAKER RATE" value={fmtBps(makerRate)} small />
            <StatBox label="30D VOLUME" value={fmtVlm(volume30d)} small />
            {fees?.activeReferralDiscount && parseNum(fees.activeReferralDiscount) > 0 && (
              <StatBox label="REFERRAL DISC." value={`${(parseNum(fees.activeReferralDiscount) * 100).toFixed(1)}%`} color="#8b5cf6" small />
            )}
          </div>

          {/* Fee tiers */}
          {fees?.feeSchedule?.tiers?.vip && (
            <div style={{ padding: "0 20px 16px", overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={headerCell}>Tier</th>
                    <th style={headerCell}>Volume Req</th>
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
                        background: isCurrentTier ? "rgba(34,211,238,0.06)" : "transparent",
                      }}>
                        <td style={{ ...cellStyle, fontWeight: isCurrentTier ? 700 : 400, color: isCurrentTier ? "#22d3ee" : T.text2 }}>
                          VIP {i}{isCurrentTier ? " \u2190" : ""}
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
