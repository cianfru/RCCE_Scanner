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
  return `$${p.toFixed(6)}`;
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
    border: "1px solid rgba(255,255,255,0.12)",
    background: "rgba(255,255,255,0.04)",
    color: T.text1,
    fontSize: 11,
    fontFamily: T.mono,
    fontWeight: 600,
    cursor: "pointer",
    letterSpacing: "0.02em",
    transition: "all 0.15s",
  },
  btnPrimary: {
    background: "rgba(34,211,238,0.12)",
    borderColor: "rgba(34,211,238,0.3)",
    color: "#22d3ee",
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
    padding: "3px 10px",
    borderRadius: 5,
    background: bg,
    color: color,
    border: `1px solid ${border}`,
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

function StatBox({ label, value, color }) {
  return (
    <div style={{ textAlign: "center", minWidth: 90 }}>
      <div style={{ ...S.value, fontSize: 18, color: color || T.text1 }}>{value}</div>
      <div style={{ ...S.label, fontSize: 9, marginTop: 2 }}>{label}</div>
    </div>
  );
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
          background: "rgba(255,255,255,0.02)",
          borderRadius: 4,
          borderLeft: "2px solid rgba(34,211,238,0.3)",
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
// Open Position Card
// ---------------------------------------------------------------------------

function PositionCard({ pos, scanResults }) {
  const side = sideBadge(pos.side);
  // Try to find current price from scan results
  const current = scanResults.find(r => r.symbol === pos.symbol);
  const currentPrice = current?.price;
  let unrealizedPnl = null;
  if (currentPrice && pos.entry_price > 0) {
    if (pos.side === "SHORT") {
      unrealizedPnl = ((pos.entry_price - currentPrice) / pos.entry_price) * 100;
    } else {
      unrealizedPnl = ((currentPrice - pos.entry_price) / pos.entry_price) * 100;
    }
  }

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
            {fmtPnl(unrealizedPnl)}
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
            <span style={S.value}>{fmtPrice(currentPrice)}</span>
          </div>
        )}
        <div>
          <span style={S.label}>Size </span>
          <span style={S.value}>{(pos.size_pct * 100).toFixed(0)}%</span>
        </div>
        <div title={fullDate(pos.entry_time)}>
          <span style={S.label}>Opened </span>
          <span style={{ ...S.value, fontSize: 12, color: T.text2 }}>{timeAgo(pos.entry_time)}</span>
        </div>
      </div>

      {/* Row 3: Reason */}
      <ReasonBlock reason={pos.entry_reason} warnings={pos.entry_warnings} />
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
        onMouseOver={e => e.currentTarget.style.background = "rgba(255,255,255,0.04)"}
        onMouseOut={e => e.currentTarget.style.background = trade.pnl_pct > 0 ? "rgba(52,211,153,0.03)" : trade.pnl_pct < 0 ? "rgba(248,113,113,0.03)" : "transparent"}
      >
        <td style={cellStyle} title={fullDate(trade.entry_time)}>{timeAgo(trade.entry_time)}</td>
        <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>
          {trade.symbol.replace("/USDT", "")}
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
          <td colSpan={7} style={{ padding: "8px 20px 14px", background: "rgba(255,255,255,0.015)" }}>
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
  const [trades, setTrades] = useState([]);
  const [scanResults, setScanResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expandedTrade, setExpandedTrade] = useState(null);
  const [whitelist, setWhitelist] = useState(null);
  const [wlLoading, setWlLoading] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [statusResp, tradesResp, scanResp, wlResp] = await Promise.all([
        fetch(`${api}/api/executor/status`),
        fetch(`${api}/api/executor/trades`),
        fetch(`${api}/api/scan?timeframe=4h`),
        fetch(`${api}/api/executor/whitelist`).catch(() => null),
      ]);
      const statusData = await statusResp.json();
      const tradesData = await tradesResp.json();
      const scanData = await scanResp.json();
      setStatus(statusData);
      setTrades(tradesData.trades || []);
      setScanResults(scanData.results || []);
      if (wlResp?.ok) {
        const wlData = await wlResp.json();
        setWhitelist(wlData);
      }
    } catch (e) {
      console.error("Executor fetch error:", e);
    }
  }, [api]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const callApi = async (endpoint, method = "POST") => {
    setLoading(true);
    try {
      await fetch(`${api}${endpoint}`, { method });
      await fetchData();
    } catch (e) {
      console.error("Executor API error:", e);
    }
    setLoading(false);
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

  const positions = status?.positions ? Object.values(status.positions) : [];
  const reversedTrades = [...trades].reverse(); // newest first

  return (
    <div style={S.panel}>

      {/* ─── CONTROLS ─── */}
      <div style={S.section}>
        <div style={S.sectionHeader}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={S.sectionTitle}>Executor</span>
            {status && <ModeBadge mode={status.mode} enabled={status.enabled} />}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {(!status?.initialized) && (
              <button
                style={{ ...S.btn, ...S.btnPrimary }}
                onClick={() => callApi("/api/executor/init")}
                disabled={loading}
              >
                Initialize
              </button>
            )}
            {status?.initialized && !status?.enabled && (
              <button
                style={{ ...S.btn, ...S.btnPrimary }}
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
                  if (confirm("Reset all positions and trade history?")) {
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

        {/* Stats row */}
        {status?.initialized && (
          <div style={{
            display: "flex",
            justifyContent: "space-around",
            padding: "14px 20px",
            gap: 16,
            flexWrap: "wrap",
          }}>
            <StatBox label="BALANCE" value={`$${(status.paper_balance || 0).toLocaleString()}`} />
            <StatBox label="PAIRS" value={`${status.whitelist_count || 0}/${status.available_pairs || 0}`} />
            <StatBox label="TRADES" value={status.total_trades || 0} />
            <StatBox
              label="WIN RATE"
              value={status.total_trades > 0 ? `${status.win_rate}%` : "\u2014"}
              color={status.win_rate >= 50 ? "#34d399" : status.win_rate > 0 ? "#fbbf24" : T.text3}
            />
            <StatBox
              label="TOTAL P&L"
              value={status.total_trades > 0 ? fmtPnl(status.total_pnl_pct) : "\u2014"}
              color={pnlColor(status.total_pnl_pct)}
            />
            <StatBox
              label="SCANS"
              value={status.total_executions || 0}
            />
            <StatBox
              label="LAST EXEC"
              value={timeAgo(status.last_execution_time)}
            />
          </div>
        )}

        {/* Not initialized message */}
        {!status?.initialized && (
          <div style={{
            padding: "32px 20px",
            textAlign: "center",
            color: T.text3,
            fontSize: 13,
            fontFamily: T.font,
          }}>
            Click <strong style={{ color: T.accent }}>Initialize</strong> to start paper trading with Kraken CLI.
            <br />
            <span style={{ fontSize: 11, color: T.text4, marginTop: 8, display: "inline-block" }}>
              The executor will convert scanner signals into paper orders on each 5-minute scan cycle.
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
      </div>

      {/* ─── TRADING WHITELIST ─── */}
      {status?.initialized && whitelist && (
        <div style={S.section}>
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
                    border: `1px solid ${active ? "rgba(34,211,238,0.35)" : T.border}`,
                    background: active ? "rgba(34,211,238,0.08)" : "rgba(255,255,255,0.02)",
                    color: active ? "#22d3ee" : T.text4,
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
        </div>
      )}

      {/* ─── OPEN POSITIONS ─── */}
      <div style={S.section}>
        <div style={S.sectionHeader}>
          <span style={S.sectionTitle}>
            Open Positions {positions.length > 0 && `(${positions.length})`}
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
          positions.map(pos => (
            <PositionCard key={pos.symbol} pos={pos} scanResults={scanResults} />
          ))
        )}
      </div>

      {/* ─── TRADE LOG ─── */}
      <div style={S.section}>
        <div style={S.sectionHeader}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={S.sectionTitle}>
              Trade Log {trades.length > 0 && `(${trades.length})`}
            </span>
            {trades.length > 0 && (
              <span style={{ fontSize: 11, fontFamily: T.mono, color: T.text3 }}>
                {trades.filter(t => t.pnl_pct > 0).length}W / {trades.filter(t => t.pnl_pct <= 0).length}L
                {" \u2022 "}
                <span style={{ color: pnlColor(status?.total_pnl_pct) }}>
                  {fmtPnl(status?.total_pnl_pct)}
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
                  <th style={headerCell}>Time</th>
                  <th style={headerCell}>Symbol</th>
                  <th style={headerCell}>Side</th>
                  <th style={headerCell}>Signal</th>
                  <th style={headerCell}>Price</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>P&L %</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>P&L $</th>
                </tr>
              </thead>
              <tbody>
                {reversedTrades.map((trade, i) => (
                  <TradeRow
                    key={i}
                    trade={trade}
                    expanded={expandedTrade === i}
                    onToggle={() => setExpandedTrade(expandedTrade === i ? null : i)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
