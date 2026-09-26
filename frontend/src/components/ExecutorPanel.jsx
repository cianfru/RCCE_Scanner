import ExecutorPerformance, { exitLabel } from "./ExecutorPerformance.jsx";
import Tabs from "./Tabs.jsx";
import { useState, useEffect, useCallback } from "react";
import { T, SIGNAL_META } from "../theme.js";
import { getAdminKey } from "../auth.js";

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
  return `${v < 0 ? "-" : ""}$${Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPnl(pct) {
  if (pct == null) return "\u2014";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function pnlColor(pct) {
  if (pct == null) return T.text3;
  return pct >= 0 ? T.green : T.red;
}

function sideBadge(side) {
  return { color: side === "LONG" ? T.green : T.red, label: side };
}

function signalColor(sig) {
  return (SIGNAL_META[sig] || SIGNAL_META.WAIT).color;
}

function signalLabel(sig) {
  if (!sig) return "\u2014";
  return SIGNAL_META[sig]?.label ?? sig.replaceAll("_", " ");
}

// "STRONG" -> "Strong confluence"
function confluenceLabel(c) {
  if (!c || c === "UNKNOWN") return null;
  const text = c.replaceAll("_", " ").toLowerCase();
  return `${text[0].toUpperCase()}${text.slice(1)} confluence`;
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
    fontSize: T.textXs,
    fontWeight: 700,
    fontFamily: T.mono,
    color: T.text2,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
  },
  // Flat text buttons; used with className="terminal-status"
  btn: {
    color: T.text1,
    fontSize: T.textXs,
    fontFamily: T.mono,
    fontWeight: 600,
    cursor: "pointer",
  },
  btnPrimary: {
    color: T.accent,
  },
  // Getter: T.red is repainted in place by applyTheme, so read it at render time
  get btnDanger() {
    return { color: T.red };
  },
  label: {
    fontSize: T.textXs,
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
  badge: (color) => ({
    display: "inline-block",
    color: color,
    fontSize: T.textXs,
    fontFamily: T.mono,
    fontWeight: 700,
    letterSpacing: "0.06em",
  }),
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ModeBadge({ mode, enabled }) {
  let color, label;
  if (!enabled && mode !== "disabled") {
    color = T.text3; label = "PAUSED";
  } else if (mode === "paper") {
    color = T.green; label = "PAPER";
  } else if (mode === "live") {
    color = T.red; label = "LIVE";
  } else {
    color = T.text4; label = "DISABLED";
  }
  return <span style={S.badge(color)}>{label}</span>;
}

function ReasonBlock({ reason, warnings }) {
  if (!reason && (!warnings || !warnings.length)) return null;
  return (
    <div style={{ marginTop: 8 }}>
      {reason && (
        <div style={{
          fontSize: T.textXs,
          fontFamily: T.mono,
          color: T.text2,
          lineHeight: 1.5,
          padding: "6px 10px",
          background: T.overlay02,
          borderRadius: 4,
          borderLeft: `2px solid ${T.accent}`,
        }}>
          {reason}
        </div>
      )}
      {warnings && warnings.length > 0 && (
        <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 3 }}>
          {warnings.map((w, i) => (
            <div key={i} style={{
              fontSize: T.textXs,
              fontFamily: T.mono,
              color: T.yellow,
              padding: "4px 10px",
              borderRadius: 4,
              borderLeft: `2px solid ${T.yellow}`,
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
// Open Position Row (Paper mode)
// ---------------------------------------------------------------------------

function PositionRow({ pos, expanded, onToggle }) {
  const currentPrice = pos.mark_price;
  const unrealizedPnl = pos.unrealized_pnl_pct;
  const confluence = confluenceLabel(pos.confluence_at_entry);
  const num = { ...cellStyle, textAlign: "right" };

  return (
    <>
      <tr>
        <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>
          <button type="button" onClick={onToggle} aria-expanded={expanded}
            title="Show price source and entry rationale"
            style={{ background: "transparent", border: 0, padding: 0, font: "inherit", color: "inherit", cursor: "pointer", borderBottom: `1px dotted ${T.text3}` }}>
            {pos.symbol.replace("/USDT", "")}
          </button>
          {pos.side === "SHORT" && <span style={{ ...S.label, marginLeft: 8, color: T.red }}>Short</span>}
        </td>
        <td style={cellStyle}>
          <span style={{ color: signalColor(pos.entry_signal), fontWeight: 600 }}>{signalLabel(pos.entry_signal)}</span>
          {confluence && <small style={{ display: "block", marginTop: 4, color: T.text3, fontSize: T.textXs }}>{confluence}</small>}
        </td>
        <td style={num}>{fmtPrice(pos.entry_price)}</td>
        <td style={num} title={fullDate(pos.mark_observed_at)}>{currentPrice ? fmtPrice(currentPrice) : "\u2014"}</td>
        <td style={num}>{fmtUsd(pos.cost_usd)}</td>
        <td style={{ ...num, color: T.text3 }} title={fullDate(pos.entry_time)}>{timeAgo(pos.entry_time)}</td>
        <td style={{ ...num, fontWeight: 700, color: pnlColor(unrealizedPnl) }}>{fmtPnl(unrealizedPnl)}</td>
        <td style={{ ...num, color: pnlColor(pos.unrealized_pnl_usd) }}>{fmtUsd(pos.unrealized_pnl_usd)}</td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={8} style={{ padding: "8px 14px 14px", background: T.overlay02, whiteSpace: "normal" }}>
            {currentPrice && pos.mark_source && <p style={{ color: T.text3, fontSize: T.textXs, lineHeight: 1.6 }}>Price source: {pos.mark_source} · {fullDate(pos.mark_observed_at)}</p>}
            {pos.valuation_issue && <p style={{ color: T.text3, fontSize: T.textXs, lineHeight: 1.6 }}>{pos.valuation_issue}</p>}
            <ReasonBlock reason={pos.entry_reason} warnings={pos.entry_warnings} />
            {!pos.entry_reason && <div style={{ fontSize: T.textXs, color: T.text3, fontFamily: T.mono }}>No rationale captured for this position</div>}
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Hyperliquid Live Position Card
// ---------------------------------------------------------------------------

function HLPositionCard({ pos }) {
  const side = sideBadge(pos.side);

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
        <span style={S.badge(side.color)}>{side.label}</span>
        <span style={S.badge(T.purple)}>{pos.leverage}x</span>
        <span style={S.badge(T.text3)}>{pos.leverage_type || "cross"}</span>
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
            <span style={{ ...S.value, color: T.red }}>{fmtPrice(pos.liquidation_price)}</span>
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
          <span style={S.badge(side.color)}>{side.label}</span>
        </td>
        <td style={cellStyle}>
          <span style={{ color: signalColor(trade.entry_signal), fontWeight: 600 }}>{signalLabel(trade.entry_signal)}</span>
          <span style={{ color: T.text4, margin: "0 4px" }}>{"\u2192"}</span>
          <span style={{ color: signalColor(trade.exit_signal), fontWeight: 600 }}>{exitLabel(trade.exit_signal)}</span>
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
          {trade.pnl_usd != null ? `${trade.pnl_usd >= 0 ? "+" : ""}${fmtUsd(trade.pnl_usd)}` : "\u2014"}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={7} style={{ padding: "8px 20px 14px", background: T.overlay02 }}>
            {trade.quality_issue && <p style={{whiteSpace:'normal',lineHeight:1.6,color:T.text2}}>{trade.quality_issue}</p>}
            <ReasonBlock reason={trade.entry_reason} warnings={trade.entry_warnings} />
            {!trade.entry_reason && (
              <div style={{ fontSize: T.textXs, color: T.text3, fontFamily: T.mono }}>
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
  fontSize: T.textXs,
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
  const [expandedPosition, setExpandedPosition] = useState(null);
  const [listTab, setListTab] = useState("open");
  const [showAllPositions, setShowAllPositions] = useState(false);
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
    // Replaces the live trading universe; the default list lives on the server.
    if (!window.confirm(`Replace the ${whitelist?.whitelist_count ?? 0} enabled pairs with the 10 default majors? The engine will stop opening trades on every other pair.`)) return;
    setWlLoading(true);
    try {
      await fetch(`${api}/api/executor/whitelist/reset`, { method: "POST" });
      await fetchData();
    } catch (e) {
      console.error("Whitelist reset error:", e);
    }
    setWlLoading(false);
  };

  const positions = status?.performance?.positions || (status?.positions ? Object.values(status.positions) : []);
  const trades = status?.performance?.included_closed_trades || rawTrades.filter(t => !t.quality_issue);
  const reversedTrades = [...trades].reverse(); // newest first
  const tradeKey = t => `${t.symbol}-${t.entry_time}-${t.exit_time}`;
  const shownPositions = positions
    .filter(pos => pos.symbol.toLowerCase().includes(positionQuery.toLowerCase()))
    .sort((a, b) => (b.unrealized_pnl_usd ?? -Infinity) - (a.unrealized_pnl_usd ?? -Infinity));
  const POSITION_CAP = 20;


  return (
    <div style={S.panel}>
      {fetchError && <p role="status" style={{color:T.text3,fontSize:12,lineHeight:1.6}}>{fetchError}</p>}
      <ExecutorPerformance performance={status?.performance} mode={status?.mode} />

      {/* ─── CONTROLS (admin key only; the server rejects changes without it) ─── */}
      {!getAdminKey() ? (
        <p style={{ color: T.text3, fontSize: 12, lineHeight: 1.6 }}>Engine controls need the admin key (Settings).</p>
      ) : (
      <details className="executor-controls" style={S.section}><summary>Engine controls and configuration</summary>
        <div style={S.sectionHeader}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={S.sectionTitle}>Executor</span>
            {status && <ModeBadge mode={status.mode} enabled={status.enabled} />}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {(!status?.initialized) && (
              <>
                <button type="button" className="terminal-status"
                  style={{ ...S.btn, ...S.btnPrimary }}
                  onClick={() => callApi("/api/executor/init")}
                  disabled={loading}
                >
                  Paper Mode
                </button>
                <button type="button" className="terminal-status"
                  style={{ ...S.btn, ...S.btnDanger }}
                  onClick={initLive}
                  disabled={loading}
                >
                  Live Mode
                </button>
              </>
            )}
            {status?.initialized && !status?.enabled && (
              <button type="button" className="terminal-status"
                style={{ ...S.btn, ...(isLive ? S.btnDanger : S.btnPrimary) }}
                onClick={() => callApi("/api/executor/enable")}
                disabled={loading}
              >
                Enable
              </button>
            )}
            {status?.initialized && status?.enabled && (
              <button type="button" className="terminal-status"
                style={S.btn}
                onClick={() => callApi("/api/executor/disable")}
                disabled={loading}
              >
                Pause
              </button>
            )}
            {status?.initialized && (
              <button type="button" className="terminal-status"
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
            <span style={{ fontSize: T.textXs, color: T.text3, marginTop: 8, display: "inline-block" }}>
              <strong style={{ color: T.accent }}>Paper</strong> simulates trades.{" "}
              <strong style={{ color: T.red }}>Live</strong> executes real orders on Hyperliquid.
            </span>
          </div>
        )}

        {/* Error display */}
        {status?.last_error && (
          <div style={{
            margin: "0 20px 14px",
            padding: "8px 12px",
            border: `1px solid ${T.red}`,
            borderRadius: 6,
            fontSize: T.textXs,
            fontFamily: T.mono,
            color: T.red,
          }}>
            Last error: {status.last_error}
          </div>
        )}
      </details>
      )}

      {/* ─── HYPERLIQUID LIVE POSITIONS ─── */}
      {isLive && status?.initialized && (
        <div style={{
          ...S.section,
          borderColor: "rgba(248,113,113,0.2)",
        }}>
          <div style={S.sectionHeader}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ ...S.sectionTitle, color: T.red }}>
                Hyperliquid Positions {hlPositions.length > 0 && `(${hlPositions.length})`}
              </span>
              <span style={S.badge(T.red)}>LIVE</span>
            </div>
            {hlAccount && (
              <span style={{ fontSize: T.textXs, fontFamily: T.mono, color: T.text3 }}>
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
              <span style={{ fontSize: T.textXs, fontFamily: T.mono, color: T.text3 }}>
                {whitelist.whitelist_count}/{whitelist.available_count} pairs active
              </span>
            </div>
            {getAdminKey() && <button type="button" className="terminal-status"
              style={{ ...S.btn, ...S.btnDanger }}
              onClick={resetWhitelist}
              disabled={wlLoading}
              title="Replace the enabled pairs with the 10 default majors"
            >
              Reset to 10 defaults
            </button>}
          </div>
          {/* Flat mono grid: enabled pairs in the accent colour, disabled pairs dimmed */}
          <div style={{
            padding: "14px 20px",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(72px, 1fr))",
            gap: "4px 12px",
          }}>
            {(whitelist.available_pairs || []).map(sym => {
              const active = whitelist.whitelist.includes(sym);
              const base = sym.replace("/USDT", "");
              return (
                <button
                  type="button"
                  key={sym}
                  onClick={() => toggleWhitelist(sym, !active)}
                  disabled={wlLoading || !getAdminKey()}   // read-only without the admin key
                  aria-pressed={active}
                  style={{
                    padding: "4px 0",
                    border: 0,
                    background: "transparent",
                    textAlign: "left",
                    color: active ? T.accent : T.text4,
                    fontSize: T.textXs,
                    fontFamily: T.mono,
                    fontWeight: active ? 600 : 400,
                    cursor: wlLoading ? "not-allowed" : getAdminKey() ? "pointer" : "default",
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

      <Tabs label="Executor lists" value={listTab} onChange={setListTab} items={[
        { key: "open", label: `${isLive ? "Tracked positions" : "Open positions"} (${positions.length})` },
        { key: "closed", label: `Closed trades (${trades.length})` },
      ]} />

      {/* ─── EXECUTOR POSITIONS (Paper / Tracked) ─── */}
      {listTab === "open" && <>
      <div className="executor-list-tools" style={{margin:"12px 0 16px"}}><input aria-label="Search open positions" placeholder="Search open positions" value={positionQuery} onChange={e=>setPositionQuery(e.target.value)} /><span style={{fontSize:12,color:T.text3}}>Sorted by unrealized P&L. Select a symbol for its price source and entry rationale.</span></div>
      <div style={S.section}>
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
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={headerCell}>Symbol</th>
                  <th style={headerCell}>Entry signal</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>Entry</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>Now</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>Capital</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>Opened</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>P&L %</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>P&L $</th>
                </tr>
              </thead>
              <tbody>
                {(showAllPositions ? shownPositions : shownPositions.slice(0, POSITION_CAP)).map(pos => (
                  <PositionRow
                    key={pos.symbol}
                    pos={pos}
                    expanded={expandedPosition === pos.symbol}
                    onToggle={() => setExpandedPosition(expandedPosition === pos.symbol ? null : pos.symbol)}
                  />
                ))}
              </tbody>
            </table>
            {shownPositions.length > POSITION_CAP && (
              <div style={{ padding: 16 }}>
                <button type="button" className="terminal-status" style={S.btn} onClick={() => setShowAllPositions(v => !v)}>
                  {showAllPositions ? `Show first ${POSITION_CAP}` : `Show all ${shownPositions.length}`}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      </>}

      {/* ─── TRADE LOG ─── */}
      {listTab === "closed" && (
      <div style={{ ...S.section, marginTop: 12 }}>
        <div style={S.sectionHeader}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <span style={S.sectionTitle}>
              Closed trades {trades.length > 0 && `(${trades.length})`}
            </span>
            {trades.length > 0 && (
              <span style={{ fontSize: T.textXs, fontFamily: T.mono, color: T.text3 }}>
                {trades.filter(t => t.pnl_usd > 0).length}W / {trades.filter(t => t.pnl_usd < 0).length}L / {trades.filter(t => t.pnl_usd === 0).length} flat
                {" \u00b7 "}
                <span style={{ color: pnlColor(status?.performance?.realized_pnl_usd) }}>
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
                {reversedTrades.slice(tradePage * 25, (tradePage + 1) * 25).map(trade => (
                  <TradeRow
                    key={tradeKey(trade)}
                    trade={trade}
                    expanded={expandedTrade === tradeKey(trade)}
                    onToggle={() => setExpandedTrade(expandedTrade === tradeKey(trade) ? null : tradeKey(trade))}
                  />
                ))}
              </tbody>
            </table>
            <div style={{padding:16,display:'flex',justifyContent:'space-between',alignItems:'center'}}><button type="button" className="terminal-status" style={S.btn} disabled={tradePage===0} onClick={()=>{setTradePage(p=>p-1);setExpandedTrade(null)}}>Previous</button><span style={S.label}>Page {tradePage+1} of {Math.ceil(trades.length/25)}</span><button type="button" className="terminal-status" style={S.btn} disabled={(tradePage+1)*25>=trades.length} onClick={()=>{setTradePage(p=>p+1);setExpandedTrade(null)}}>Next</button></div>
          </div>
        )}
      </div>
      )}
    </div>
  );
}
