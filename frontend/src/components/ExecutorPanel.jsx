import ExecutorShadow from './ExecutorShadow.jsx';
import ExecutorPerformance from "./ExecutorPerformance.jsx";
import { useState, useEffect, useCallback } from "react";
import { T, SIGNAL_META } from "../theme.js";

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

function fmtPrice(p) {
  if (!p) return "\u2014";
  if (p >= 1000) return `$${p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (p >= 1)    return `$${p.toFixed(4)}`;
  return `$${p.toLocaleString("en-US", {maximumSignificantDigits:6})}`;
}

function fmtUsd(v) {
  if (v == null) return "\u2014";
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPnl(pct) {
  if (pct == null) return "\u2014";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function pnlColor(pct) {
  if (pct == null) return T.text3;
  return pct >= 0 ? "#34d399" : "#f87171";
}

function sideBadge(side) {
  const isLong = side === "LONG";
  return {
    bg: isLong ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.12)",
    color: isLong ? "#34d399" : "#f87171",
    border: isLong ? "rgba(52,211,153,0.25)" : "rgba(248,113,113,0.25)",
    label: side,
  };
}

function signalColor(sig) {
  return (SIGNAL_META[sig] || SIGNAL_META.WAIT).color;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const S = {
  panel: {
    padding: 0,
    maxWidth: 1200,
    margin: "0 auto",
  },
  section: {
    background: T.surface,
    border: `1px solid ${T.border}`,
    borderRadius: T.radius,
    marginBottom: 16,
    overflow: "hidden",
  },
  sectionHeader: {
    padding: "14px 20px",
    borderBottom: `1px solid ${T.border}`,
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: 700,
    fontFamily: T.mono,
    color: T.text2,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
  },
  btn: {
    padding: "6px 14px",
    borderRadius: 6,
    border: `1px solid ${T.overlay12}`,
    background: T.overlay04,
    color: T.text1,
    fontSize: 11,
    fontFamily: T.mono,
    fontWeight: 600,
    cursor: "pointer",
    letterSpacing: "0.02em",
    transition: "all 0.15s",
  },
  btnPrimary: {
    background: "rgba(151,252,228,0.12)",
    borderColor: "rgba(151,252,228,0.3)",
    color: "#97FCE4",
  },
  btnLive: {
    background: "rgba(248,113,113,0.12)",
    borderColor: "rgba(248,113,113,0.3)",
    color: "#f87171",
  },
  btnDanger: {
    background: "rgba(248,113,113,0.08)",
    borderColor: "rgba(248,113,113,0.2)",
    color: "#f87171",
  },
  label: {
    fontSize: 11,
    fontFamily: T.font,
    color: T.text3,
    fontWeight: 500,
  },
  value: {
    fontSize: 13,
    fontFamily: T.mono,
    color: T.text1,
    fontWeight: 600,
  },
  badge: (bg, color, border) => ({
    display: "inline-block",
    padding: 0,
    borderRadius: 0,
    background: "transparent",
    color: color,
    border: "none",
    fontSize: 10,
    fontFamily: T.mono,
    fontWeight: 700,
    letterSpacing: "0.06em",
  }),
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ModeBadge({ mode, enabled }) {
  let bg, color, border, label;
  if (!enabled && mode !== "disabled") {
    bg = "rgba(82,82,91,0.15)"; color = T.text3; border = T.border; label = "PAUSED";
  } else if (mode === "paper") {
    bg = "rgba(52,211,153,0.12)"; color = "#34d399"; border = "rgba(52,211,153,0.3)"; label = "PAPER";
  } else if (mode === "live") {
    bg = "rgba(248,113,113,0.12)"; color = "#f87171"; border = "rgba(248,113,113,0.3)"; label = "LIVE";
  } else {
    bg = "rgba(82,82,91,0.1)"; color = T.text4; border = T.border; label = "DISABLED";
  }
  return <span style={S.badge(bg, color, border)}>{label}</span>;
}

function ReasonBlock({ reason, warnings }) {
  if (!reason && (!warnings || !warnings.length)) return null;
  return (
    <div style={{ marginTop: 8 }}>
      {reason && (
        <div style={{
          fontSize: 11,
          fontFamily: T.mono,
          color: T.text2,
          lineHeight: 1.5,
          padding: "6px 10px",
          background: T.overlay02,
          borderRadius: 4,
          borderLeft: "2px solid rgba(151,252,228,0.3)",
        }}>
          {reason}
        </div>
      )}
      {warnings && warnings.length > 0 && (
        <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 3 }}>
          {warnings.map((w, i) => (
            <div key={i} style={{
              fontSize: 10,
              fontFamily: T.mono,
              color: "#fbbf24",
              padding: "4px 10px",
              background: "rgba(251,191,36,0.06)",
              borderRadius: 4,
              borderLeft: "2px solid rgba(251,191,36,0.3)",
              lineHeight: 1.4,
            }}>
              {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Open Position Card (Paper mode)
// ---------------------------------------------------------------------------

function PositionCard({ pos }) {
  const side = sideBadge(pos.side);
  const currentPrice = pos.mark_price;
  const unrealizedPnl = pos.unrealized_pnl_pct;

  return (
    <div style={{
      padding: "14px 20px",
      borderBottom: `1px solid ${T.border}`,
      transition: "background 0.15s",
    }}>
      {/* Row 1: Symbol + badges */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 15, fontFamily: T.mono, fontWeight: 700, color: T.text1 }}>
          {pos.symbol.replace("/USDT", "")}
        </span>
        <span style={S.badge(side.bg, side.color, side.border)}>{side.label}</span>
        <span style={S.badge(
          `${signalColor(pos.entry_signal)}15`,
          signalColor(pos.entry_signal),
          `${signalColor(pos.entry_signal)}30`,
        )}>{pos.entry_signal}</span>
        {pos.confluence_at_entry && pos.confluence_at_entry !== "UNKNOWN" && (
          <span style={{ fontSize: 10, fontFamily: T.mono, color: T.text3, fontWeight: 500 }}>
            Confluence: {pos.confluence_at_entry}
          </span>
        )}
        {unrealizedPnl != null && (
          <span style={{
            marginLeft: "auto",
            fontSize: 14,
            fontFamily: T.mono,
            fontWeight: 700,
            color: pnlColor(unrealizedPnl),
          }}>
            {fmtPnl(unrealizedPnl)} <small style={{fontWeight:400}}>{fmtUsd(pos.unrealized_pnl_usd)}</small>
          </span>
        )}
      </div>

      {/* Row 2: Details */}
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center" }}>
        <div>
          <span style={S.label}>Entry </span>
          <span style={S.value}>{fmtPrice(pos.entry_price)}</span>
        </div>
        {currentPrice && (
          <div>
            <span style={S.label}>Now </span>
            <span style={S.value} title={fullDate(pos.mark_observed_at)}>{fmtPrice(currentPrice)}</span>
          </div>
        )}
        <div>
          <span style={S.label}>Entry capital </span>
          <span style={S.value}>{fmtUsd(pos.cost_usd)}</span>
        </div>
        <div title={fullDate(pos.entry_time)}>
          <span style={S.label}>Opened </span>
          <span style={{ ...S.value, fontSize: 12, color: T.text2 }}>{timeAgo(pos.entry_time)}</span>
        </div>
      </div>

      {/* Row 3: Reason */}
      {currentPrice && pos.mark_source && <p style={{color:T.text3,fontSize:11,lineHeight:1.6,marginTop:10}}>Price source: {pos.mark_source} · {fullDate(pos.mark_observed_at)}</p>}
      {pos.valuation_issue && <p style={{color: T.text3, fontSize:12, lineHeight:1.6}}>{pos.valuation_issue}</p>}
      <details style={{marginTop:12,fontSize:12,color:T.text3}}><summary style={{cursor:'pointer'}}>Entry rationale</summary><ReasonBlock reason={pos.entry_reason} warnings={pos.entry_warnings} /></details>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hyperliquid Live Position Card
// ---------------------------------------------------------------------------

function HLPositionCard({ pos }) {
  const side = sideBadge(pos.side);
  const pnlPct = pos.entry_price > 0
    ? ((pos.side === "LONG"
        ? (pos.unrealized_pnl / (Math.abs(pos.size) * pos.entry_price))
        : (pos.unrealized_pnl / (Math.abs(pos.size) * pos.entry_price))
      ) * 100)
    : null;

  return (
    <div style={{
      padding: "14px 20px",
      borderBottom: `1px solid ${T.border}`,
      transition: "background 0.15s",
    }}>
      {/* Row 1: Symbol + badges */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 15, fontFamily: T.mono, fontWeight: 700, color: T.text1 }}>
          {pos.coin}
        </span>
        <span style={S.badge(side.bg, side.color, side.border)}>{side.label}</span>
        <span style={S.badge(
          "rgba(139,92,246,0.12)",
          "#8b5cf6",
          "rgba(139,92,246,0.3)",
        )}>{pos.leverage}x</span>
        <span style={S.badge(
          "rgba(82,82,91,0.12)",
          T.text3,
          T.border,
        )}>{pos.leverage_type || "cross"}</span>
        <span style={{
          marginLeft: "auto",
          fontSize: 14,
          fontFamily: T.mono,
          fontWeight: 700,
          color: pnlColor(pos.unrealized_pnl),
        }}>
          {pos.unrealized_pnl >= 0 ? "+" : ""}{fmtUsd(pos.unrealized_pnl)}
        </span>
      </div>

      {/* Row 2: Details */}
      <div style={{ display: "flex", gap: 20, flexWrap: "wrap", alignItems: "center" }}>
        <div>
          <span style={S.label}>Entry </span>
          <span style={S.value}>{fmtPrice(pos.entry_price)}</span>
        </div>
        <div>
          <span style={S.label}>Size </span>
          <span style={S.value}>{Math.abs(pos.size).toFixed(4)}</span>
        </div>
        <div>
          <span style={S.label}>Notional </span>
          <span style={S.value}>{fmtUsd(pos.notional_value)}</span>
        </div>
        <div>
          <span style={S.label}>Margin </span>
          <span style={S.value}>{fmtUsd(pos.margin_used)}</span>
        </div>
        {pos.liquidation_price && (
          <div>
            <span style={S.label}>Liq </span>
            <span style={{ ...S.value, color: "#f87171" }}>{fmtPrice(pos.liquidation_price)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trade Log Row
// ---------------------------------------------------------------------------

function TradeRow({ trade, expanded, onToggle }) {
  const side = sideBadge(trade.side);
  return (
    <>
      <tr
        onClick={onToggle}
        style={{
          cursor: "pointer",
          background: trade.pnl_pct > 0 ? "rgba(52,211,153,0.03)" : trade.pnl_pct < 0 ? "rgba(248,113,113,0.03)" : "transparent",
          transition: "background 0.15s",
        }}
        onMouseOver={e => e.currentTarget.style.background = T.overlay04}
        onMouseOut={e => e.currentTarget.style.background = trade.pnl_pct > 0 ? "rgba(52,211,153,0.03)" : trade.pnl_pct < 0 ? "rgba(248,113,113,0.03)" : "transparent"}
      >
        <td style={cellStyle} title={fullDate(trade.exit_time)}>{timeAgo(trade.exit_time)}<small style={{display:"block",marginTop:5,color:T.text3}} title={fullDate(trade.entry_time)}>Opened {timeAgo(trade.entry_time)}</small></td>
        <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>
          {trade.symbol.replace("/USDT", "")}
          {trade.quality_issue && <small title={trade.quality_issue} style={{display:'block',fontWeight:400,color:T.text3,marginTop:5}}>Price-unit error</small>}
        </td>
        <td style={cellStyle}>
          <span style={S.badge(side.bg, side.color, side.border)}>{side.label}</span>
        </td>
        <td style={cellStyle}>
          <span style={{ color: signalColor(trade.entry_signal), fontWeight: 600 }}>{trade.entry_signal}</span>
          <span style={{ color: T.text4, margin: "0 4px" }}>{"\u2192"}</span>
          <span style={{ color: signalColor(trade.exit_signal), fontWeight: 600 }}>{trade.exit_signal}</span>
        </td>
        <td style={cellStyle}>
          {fmtPrice(trade.entry_price)}
          <span style={{ color: T.text4, margin: "0 4px" }}>{"\u2192"}</span>
          {fmtPrice(trade.exit_price)}
        </td>
        <td style={{ ...cellStyle, fontWeight: 700, color: pnlColor(trade.pnl_pct), textAlign: "right" }}>
          {fmtPnl(trade.pnl_pct)}
        </td>
        <td style={{ ...cellStyle, color: pnlColor(trade.pnl_usd), textAlign: "right" }}>
          {trade.pnl_usd != null ? `${trade.pnl_usd >= 0 ? "+" : ""}$${trade.pnl_usd.toFixed(2)}` : "\u2014"}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={7} style={{ padding: "8px 20px 14px", background: T.overlay02 }}>
            {trade.quality_issue && <p style={{whiteSpace:'normal',lineHeight:1.6,color:T.text2}}>{trade.quality_issue}</p>}
            <ReasonBlock reason={trade.entry_reason} warnings={trade.entry_warnings} />
            {!trade.entry_reason && (
              <div style={{ fontSize: 11, color: T.text4, fontFamily: T.mono }}>
                No rationale captured for this trade
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

const cellStyle = {
  padding: "10px 14px",
  fontSize: 12,
  fontFamily: T.mono,
  color: T.text2,
  borderBottom: `1px solid ${T.border}`,
  whiteSpace: "nowrap",
};

const headerCell = {
  padding: "10px 14px",
  fontSize: 9,
  fontFamily: T.mono,
  fontWeight: 700,
  color: T.text3,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  borderBottom: `1px solid ${T.borderH}`,
  textAlign: "left",
};

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function ExecutorPanel({ api }) {
  const [status, setStatus] = useState(null);
  const [rawTrades, setTrades] = useState([]);
  const [positionQuery, setPositionQuery] = useState("");
  const [tradePage, setTradePage] = useState(0);
  const [fetchError, setFetchError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expandedTrade, setExpandedTrade] = useState(null);
  const [whitelist, setWhitelist] = useState(null);
  const [wlLoading, setWlLoading] = useState(false);
  const [hlPositions, setHlPositions] = useState([]);
  const [hlAccount, setHlAccount] = useState(null);

  const isLive = status?.mode === "live";

  const fetchData = useCallback(async () => {
    try {
      const fetches = [
        fetch(`${api}/api/executor/status`),
        fetch(`${api}/api/executor/trades`),
        fetch(`${api}/api/executor/whitelist`).catch(() => null),
      ];

      const [statusResp, tradesResp, wlResp] = await Promise.all(fetches);
      if (!statusResp.ok || !tradesResp.ok) throw new Error("Executor data is unavailable");
      const statusData = await statusResp.json();
      const tradesData = await tradesResp.json();
      setFetchError(null);
      setStatus(statusData);
      setTrades(tradesData.trades || []);
      if (wlResp?.ok) {
        const wlData = await wlResp.json();
        setWhitelist(wlData);
      }

      // Fetch live HL data when in live mode
      if (statusData?.mode === "live" && statusData?.initialized) {
        try {
          const [posResp, accResp] = await Promise.all([
            fetch(`${api}/api/executor/hl/positions`).catch(() => null),
            fetch(`${api}/api/executor/hl/account`).catch(() => null),
          ]);
          if (posResp?.ok) {
            const posData = await posResp.json();
            setHlPositions(posData.positions || []);
          }
          if (accResp?.ok) {
            const accData = await accResp.json();
            setHlAccount(accData);
          }
        } catch (e) {
          console.error("HL data fetch error:", e);
        }
      }
    } catch (e) {
      setFetchError("Could not refresh executor data. Previously loaded figures may be out of date.");
      console.error("Executor fetch error:", e);
    }
  }, [api]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const callApi = async (endpoint, method = "POST", body = null) => {
    setLoading(true);
    try {
      const opts = { method };
      if (body) {
        opts.headers = { "Content-Type": "application/json" };
        opts.body = JSON.stringify(body);
      }
      await fetch(`${api}${endpoint}`, opts);
      await fetchData();
    } catch (e) {
      console.error("Executor API error:", e);
    }
    setLoading(false);
  };

  const initLive = async () => {
    const confirmed = confirm(
      "You are about to enable LIVE trading on Hyperliquid.\n\n" +
      "REAL FUNDS will be used for order execution.\n" +
      "Make sure HL_PRIVATE_KEY is set in your environment.\n\n" +
      "Continue?"
    );
    if (!confirmed) return;
    await callApi("/api/executor/init", "POST", { mode: "live", balance: 0 });
  };

  const toggleWhitelist = async (symbol, shouldAdd) => {
    setWlLoading(true);
    try {
      if (shouldAdd) {
        await fetch(`${api}/api/executor/whitelist/add`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol }),
        });
      } else {
        const encoded = encodeURIComponent(symbol);
        await fetch(`${api}/api/executor/whitelist/${encoded}`, { method: "DELETE" });
      }
      await fetchData();
    } catch (e) {
      console.error("Whitelist toggle error:", e);
    }
    setWlLoading(false);
  };

  const resetWhitelist = async () => {
    setWlLoading(true);
    try {
      await fetch(`${api}/api/executor/whitelist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbols: [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
            "ADA/USDT", "AVAX/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
          ],
        }),
      });
      await fetchData();
    } catch (e) {
      console.error("Whitelist reset error:", e);
    }
    setWlLoading(false);
  };

  const positions = status?.performance?.positions || (status?.positions ? Object.values(status.positions) : []);
  const trades = status?.performance?.included_closed_trades || rawTrades.filter(t => !t.quality_issue);
  const reversedTrades = [...trades].reverse(); // newest first


  return (
    <div style={S.panel}>
      {fetchError && <p role="status" style={{color:T.text3,fontSize:12,lineHeight:1.6}}>{fetchError}</p>}
      <ExecutorPerformance performance={status?.performance} mode={status?.mode} />
      <ExecutorShadow study={status?.shadow_study} />

      {/* ─── CONTROLS ─── */}
      <details className="executor-controls" style={S.section}><summary>Engine controls and configuration</summary>
        <div style={S.sectionHeader}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={S.sectionTitle}>Executor</span>
            {status && <ModeBadge mode={status.mode} enabled={status.enabled} />}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {(!status?.initialized) && (
              <>
                <button
                  style={{ ...S.btn, ...S.btnPrimary }}
                  onClick={() => callApi("/api/executor/init")}
                  disabled={loading}
                >
                  Paper Mode
                </button>
                <button
                  style={{ ...S.btn, ...S.btnLive }}
                  onClick={initLive}
                  disabled={loading}
                >
                  Live Mode
                </button>
              </>
            )}
            {status?.initialized && !status?.enabled && (
              <button
                style={{ ...S.btn, ...(isLive ? S.btnLive : S.btnPrimary) }}
                onClick={() => callApi("/api/executor/enable")}
                disabled={loading}
              >
                Enable
              </button>
            )}
            {status?.initialized && status?.enabled && (
              <button
                style={S.btn}
                onClick={() => callApi("/api/executor/disable")}
                disabled={loading}
              >
                Pause
              </button>
            )}
            {status?.initialized && (
              <button
                style={{ ...S.btn, ...S.btnDanger }}
                onClick={() => {
                  const msg = isLive
                    ? "Reset executor state? This clears local tracking only \u2014 live positions on Hyperliquid are NOT affected."
                    : "Reset all positions and trade history?";
                  if (confirm(msg)) {
                    callApi("/api/executor/reset");
                  }
                }}
                disabled={loading}
              >
                Reset
              </button>
            )}
          </div>
        </div>



        {/* Not initialized message */}
        {!status?.initialized && (
          <div style={{
            padding: "32px 20px",
            textAlign: "center",
            color: T.text3,
            fontSize: 13,
            fontFamily: T.font,
          }}>
            Choose a mode to start the executor.
            <br />
            <span style={{ fontSize: 11, color: T.text4, marginTop: 8, display: "inline-block" }}>
              <strong style={{ color: "#97FCE4" }}>Paper</strong> simulates trades.{" "}
              <strong style={{ color: "#f87171" }}>Live</strong> executes real orders on Hyperliquid.
            </span>
          </div>
        )}

        {/* Error display */}
        {status?.last_error && (
          <div style={{
            margin: "0 20px 14px",
            padding: "8px 12px",
            background: "rgba(248,113,113,0.06)",
            border: "1px solid rgba(248,113,113,0.15)",
            borderRadius: 6,
            fontSize: 11,
            fontFamily: T.mono,
            color: "#f87171",
          }}>
            Last error: {status.last_error}
          </div>
        )}
      </details>

      {/* ─── HYPERLIQUID LIVE POSITIONS ─── */}
      {isLive && status?.initialized && (
        <div style={{
          ...S.section,
          borderColor: "rgba(248,113,113,0.2)",
        }}>
          <div style={S.sectionHeader}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ ...S.sectionTitle, color: "#f87171" }}>
                Hyperliquid Positions {hlPositions.length > 0 && `(${hlPositions.length})`}
              </span>
              <span style={S.badge(
                "rgba(248,113,113,0.12)",
                "#f87171",
                "rgba(248,113,113,0.3)",
              )}>LIVE</span>
            </div>
            {hlAccount && (
              <span style={{ fontSize: 11, fontFamily: T.mono, color: T.text3 }}>
                {hlAccount.address?.slice(0, 6)}...{hlAccount.address?.slice(-4)}
              </span>
            )}
          </div>
          {hlPositions.length === 0 ? (
            <div style={{
              padding: "24px 20px",
              textAlign: "center",
              color: T.text4,
              fontSize: 12,
              fontFamily: T.mono,
            }}>
              No open positions on Hyperliquid
            </div>
          ) : (
            hlPositions.map(pos => (
              <HLPositionCard key={pos.coin} pos={pos} />
            ))
          )}
        </div>
      )}

      {/* ─── TRADING WHITELIST ─── */}
      {status?.initialized && whitelist && (
        <details className="executor-controls" style={S.section}><summary>Trading universe / {whitelist.whitelist_count} enabled pairs</summary>
          <div style={S.sectionHeader}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={S.sectionTitle}>Trading Whitelist</span>
              <span style={{ fontSize: 11, fontFamily: T.mono, color: T.text3 }}>
                {whitelist.whitelist_count}/{whitelist.available_count} pairs active
              </span>
            </div>
            <button
              style={S.btn}
              onClick={resetWhitelist}
              disabled={wlLoading}
            >
              Reset Default
            </button>
          </div>
          <div style={{
            padding: "14px 20px",
            display: "flex",
            flexWrap: "wrap",
            gap: 6,
          }}>
            {(whitelist.available_pairs || []).map(sym => {
              const active = whitelist.whitelist.includes(sym);
              const base = sym.replace("/USDT", "");
              return (
                <button
                  key={sym}
                  onClick={() => toggleWhitelist(sym, !active)}
                  disabled={wlLoading}
                  style={{
                    padding: "4px 10px",
                    borderRadius: 6,
                    border: `1px solid ${active ? "rgba(151,252,228,0.35)" : T.border}`,
                    background: active ? "rgba(151,252,228,0.08)" : T.overlay02,
                    color: active ? "#97FCE4" : T.text4,
                    fontSize: 11,
                    fontFamily: T.mono,
                    fontWeight: active ? 700 : 500,
                    cursor: wlLoading ? "not-allowed" : "pointer",
                    transition: "all 0.15s",
                    opacity: wlLoading ? 0.5 : 1,
                  }}
                >
                  {base}
                </button>
              );
            })}
          </div>
        </details>
      )}

      <div className="executor-list-tools" style={{marginBottom:16}}><input aria-label="Search open positions" placeholder="Search open positions" value={positionQuery} onChange={e=>setPositionQuery(e.target.value)} /><span style={{fontSize:12,color:T.text3}}>Sorted by unrealized P&L</span></div>
      {/* ─── EXECUTOR POSITIONS (Paper / Tracked) ─── */}
      <div style={S.section}>
        <div style={S.sectionHeader}>
          <span style={S.sectionTitle}>
            {isLive ? "Tracked Positions" : "Open Positions"} {positions.length > 0 && `(${positions.length})`}
          </span>
        </div>
        {positions.length === 0 ? (
          <div style={{
            padding: "24px 20px",
            textAlign: "center",
            color: T.text4,
            fontSize: 12,
            fontFamily: T.mono,
          }}>
            {status?.enabled ? "No open positions \u2014 waiting for entry signals" : "Executor paused \u2014 no positions being managed"}
          </div>
        ) : (
          positions.filter(pos => pos.symbol.toLowerCase().includes(positionQuery.toLowerCase())).sort((a,b)=>(b.unrealized_pnl_usd ?? -Infinity)-(a.unrealized_pnl_usd ?? -Infinity)).map(pos => (
            <PositionCard key={pos.symbol} pos={pos} />
          ))
        )}
      </div>

      {/* ─── TRADE LOG ─── */}
      <div style={S.section}>
        <div style={S.sectionHeader}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={S.sectionTitle}>
              Closed trades {trades.length > 0 && `(${trades.length})`}
            </span>
            {trades.length > 0 && (
              <span style={{ fontSize: 11, fontFamily: T.mono, color: T.text3 }}>
                {trades.filter(t => t.pnl_usd > 0).length}W / {trades.filter(t => t.pnl_usd < 0).length}L
                 / {trades.filter(t => t.pnl_usd === 0).length} flat
                <span style={{ color: pnlColor(status?.total_pnl_pct) }}>
                  {fmtUsd(status?.performance?.realized_pnl_usd)} realized
                </span>
              </span>
            )}
          </div>
        </div>
        {trades.length === 0 ? (
          <div style={{
            padding: "24px 20px",
            textAlign: "center",
            color: T.text4,
            fontSize: 12,
            fontFamily: T.mono,
          }}>
            No completed trades yet
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={headerCell}>Closed</th>
                  <th style={headerCell}>Symbol</th>
                  <th style={headerCell}>Side</th>
                  <th style={headerCell}>Signal</th>
                  <th style={headerCell}>Price</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>P&L %</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>P&L $</th>
                </tr>
              </thead>
              <tbody>
                {reversedTrades.slice(tradePage * 25, (tradePage + 1) * 25).map((trade, i) => (
                  <TradeRow
                    key={i}
                    trade={trade}
                    expanded={expandedTrade === i}
                    onToggle={() => setExpandedTrade(expandedTrade === i ? null : i)}
                  />
                ))}
              </tbody>
            </table>
            <div style={{padding:16,display:'flex',justifyContent:'space-between',alignItems:'center'}}><button style={S.btn} disabled={tradePage===0} onClick={()=>{setTradePage(p=>p-1);setExpandedTrade(null)}}>Previous</button><span style={S.label}>Page {tradePage+1} of {Math.ceil(trades.length/25)}</span><button style={S.btn} disabled={(tradePage+1)*25>=trades.length} onClick={()=>{setTradePage(p=>p+1);setExpandedTrade(null)}}>Next</button></div>
          </div>
        )}
      </div>
    </div>
  );
}
