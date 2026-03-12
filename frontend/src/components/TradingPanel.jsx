import { useState, useEffect, useCallback } from "react";
import { T } from "../theme.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(ts) {
  if (!ts) return "\u2014";
  const s = typeof ts === "number" && ts > 1e12 ? ts / 1000 : ts; // handle ms or s
  const diff = (Date.now() / 1000) - s;
  if (diff < 60)   return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${(diff / 3600).toFixed(1)}h ago`;
  return `${(diff / 86400).toFixed(1)}d ago`;
}

function fmtUsd(v) {
  if (v == null) return "\u2014";
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPrice(p) {
  if (!p) return "\u2014";
  if (p >= 1000) return `$${p.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (p >= 1) return `$${p.toFixed(4)}`;
  return `$${p.toFixed(6)}`;
}

function fmtPnl(pct) {
  if (pct == null) return "\u2014";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

function pnlColor(v) {
  if (v == null || v === 0) return T.text3;
  return v > 0 ? "#34d399" : "#f87171";
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

function StatBox({ label, value, color }) {
  return (
    <div style={{ textAlign: "center", minWidth: 90 }}>
      <div style={{ ...S.value, fontSize: 18, color: color || T.text1 }}>{value}</div>
      <div style={{ ...S.label, fontSize: 9, marginTop: 2 }}>{label}</div>
    </div>
  );
}

function PositionCard({ pos, onClose, closing }) {
  const isLong = pos.side === "LONG";
  const sideColor = isLong ? "#34d399" : "#f87171";
  const sideBg = isLong ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.12)";
  const sideBorder = isLong ? "rgba(52,211,153,0.25)" : "rgba(248,113,113,0.25)";

  return (
    <div style={{ padding: "14px 20px", borderBottom: `1px solid ${T.border}` }}>
      {/* Row 1: coin + badges + PnL */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 15, fontFamily: T.mono, fontWeight: 700, color: T.text1 }}>
          {pos.coin}
        </span>
        <span style={S.badge(sideBg, sideColor, sideBorder)}>{pos.side}</span>
        <span style={S.badge("rgba(139,92,246,0.12)", "#8b5cf6", "rgba(139,92,246,0.3)")}>
          {pos.leverage}x
        </span>
        <span style={{
          marginLeft: "auto", fontSize: 14, fontFamily: T.mono, fontWeight: 700,
          color: pnlColor(pos.unrealized_pnl),
        }}>
          {pos.unrealized_pnl >= 0 ? "+" : ""}{fmtUsd(pos.unrealized_pnl)}
        </span>
      </div>

      {/* Row 2: details */}
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
        <button
          onClick={() => onClose(pos.symbol || `${pos.coin}/USDT`)}
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
// Main Component
// ---------------------------------------------------------------------------

export default function TradingPanel({ api }) {
  const [account, setAccount] = useState(null);
  const [positions, setPositions] = useState([]);
  const [history, setHistory] = useState({ trades: [], stats: {} });
  const [fills, setFills] = useState([]);
  const [closing, setClosing] = useState(null);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [accResp, posResp, histResp, fillsResp] = await Promise.all([
        fetch(`${api}/api/trade/account`).catch(() => null),
        fetch(`${api}/api/trade/positions`).catch(() => null),
        fetch(`${api}/api/trade/history`).catch(() => null),
        fetch(`${api}/api/trade/fills?limit=20`).catch(() => null),
      ]);

      if (accResp?.ok) {
        setAccount(await accResp.json());
        setError(null);
      } else {
        setError("HL_PRIVATE_KEY not configured or HL connection failed");
      }
      if (posResp?.ok) setPositions((await posResp.json()).positions || []);
      if (histResp?.ok) setHistory(await histResp.json());
      if (fillsResp?.ok) setFills((await fillsResp.json()).fills || []);
    } catch (e) {
      setError("Failed to connect to trading API");
    }
  }, [api]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const closePosition = async (symbol) => {
    if (!window.confirm(`Close ${symbol} position?`)) return;
    setClosing(symbol);
    try {
      await fetch(`${api}/api/trade/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol }),
      });
      await fetchData();
    } catch (e) {
      console.error("Close error:", e);
    }
    setClosing(null);
  };

  const stats = history.stats || {};
  const trades = history.trades || [];

  return (
    <div style={S.panel}>

      {/* ─── CONNECTION ERROR ─── */}
      {error && (
        <div style={{
          ...S.section, borderColor: "rgba(248,113,113,0.2)",
          padding: "20px", textAlign: "center",
        }}>
          <div style={{ fontSize: 12, fontFamily: T.mono, color: "#f87171", marginBottom: 6 }}>
            {error}
          </div>
          <div style={{ fontSize: 10, fontFamily: T.mono, color: T.text4 }}>
            Set HL_PRIVATE_KEY (agent wallet) in your environment to enable live trading.
          </div>
        </div>
      )}

      {/* ─── ACCOUNT OVERVIEW ─── */}
      {account && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={S.title}>Hyperliquid Account</span>
              <span style={S.badge(
                "rgba(248,113,113,0.12)", "#f87171", "rgba(248,113,113,0.3)",
              )}>LIVE</span>
            </div>
            <span style={{ fontSize: 10, fontFamily: T.mono, color: T.text4 }}>
              {account.address?.slice(0, 6)}...{account.address?.slice(-4)}
            </span>
          </div>
          <div style={{
            display: "flex", justifyContent: "space-around",
            padding: "14px 20px", gap: 16, flexWrap: "wrap",
          }}>
            <StatBox label="EQUITY" value={fmtUsd(account.account_value)} />
            <StatBox
              label="MARGIN USED"
              value={fmtUsd(account.total_margin_used)}
              color={account.total_margin_used > 0 ? "#fbbf24" : T.text3}
            />
            <StatBox label="POSITIONS" value={account.positions_count || positions.length} />
            {stats.total_trades > 0 && (
              <>
                <StatBox label="TRADES" value={stats.total_trades} />
                <StatBox
                  label="WIN RATE"
                  value={`${stats.win_rate}%`}
                  color={stats.win_rate >= 50 ? "#34d399" : stats.win_rate > 0 ? "#fbbf24" : T.text3}
                />
                <StatBox
                  label="TOTAL P&L"
                  value={fmtUsd(stats.total_pnl_usd)}
                  color={pnlColor(stats.total_pnl_usd)}
                />
              </>
            )}
          </div>
        </div>
      )}

      {/* ─── OPEN POSITIONS ─── */}
      <div style={S.section}>
        <div style={S.sectionHeader}>
          <span style={S.title}>
            Open Positions {positions.length > 0 && `(${positions.length})`}
          </span>
        </div>
        {positions.length === 0 ? (
          <div style={{
            padding: "24px 20px", textAlign: "center",
            color: T.text4, fontSize: 12, fontFamily: T.mono,
          }}>
            {account ? "No open positions" : "Connect wallet to view positions"}
          </div>
        ) : (
          positions.map(pos => (
            <PositionCard
              key={pos.coin}
              pos={pos}
              onClose={closePosition}
              closing={closing === (pos.symbol || `${pos.coin}/USDT`)}
            />
          ))
        )}
      </div>

      {/* ─── TRADE HISTORY ─── */}
      <div style={S.section}>
        <div style={S.sectionHeader}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={S.title}>
              Trade History {trades.length > 0 && `(${trades.length})`}
            </span>
            {stats.total_trades > 0 && (
              <span style={{ fontSize: 11, fontFamily: T.mono, color: T.text3 }}>
                {stats.wins}W / {stats.losses}L
                {" \u2022 "}
                <span style={{ color: pnlColor(stats.total_pnl_usd) }}>
                  {fmtUsd(stats.total_pnl_usd)}
                </span>
              </span>
            )}
          </div>
        </div>
        {trades.length === 0 ? (
          <div style={{
            padding: "24px 20px", textAlign: "center",
            color: T.text4, fontSize: 12, fontFamily: T.mono,
          }}>
            No trades yet — open a position from the scanner
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={headerCell}>Time</th>
                  <th style={headerCell}>Symbol</th>
                  <th style={headerCell}>Side</th>
                  <th style={headerCell}>Lev</th>
                  <th style={headerCell}>Signal</th>
                  <th style={headerCell}>Entry</th>
                  <th style={headerCell}>Exit</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>P&L</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => {
                  const isLong = t.side === "LONG";
                  const sideColor = isLong ? "#34d399" : "#f87171";
                  return (
                    <tr key={t.id || i} style={{
                      background: t.status === "CLOSED"
                        ? (t.pnl_pct > 0 ? "rgba(52,211,153,0.03)" : t.pnl_pct < 0 ? "rgba(248,113,113,0.03)" : "transparent")
                        : "transparent",
                    }}>
                      <td style={cellStyle}>{timeAgo(t.opened_at)}</td>
                      <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>{t.coin}</td>
                      <td style={cellStyle}>
                        <span style={S.badge(
                          isLong ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.12)",
                          sideColor,
                          isLong ? "rgba(52,211,153,0.25)" : "rgba(248,113,113,0.25)",
                        )}>{t.side}</span>
                      </td>
                      <td style={cellStyle}>
                        <span style={S.badge("rgba(139,92,246,0.12)", "#8b5cf6", "rgba(139,92,246,0.3)")}>
                          {t.leverage}x
                        </span>
                      </td>
                      <td style={{ ...cellStyle, color: T.text3 }}>{t.signal_at_trade || "\u2014"}</td>
                      <td style={cellStyle}>{fmtPrice(t.entry_price)}</td>
                      <td style={cellStyle}>{t.exit_price > 0 ? fmtPrice(t.exit_price) : "\u2014"}</td>
                      <td style={{ ...cellStyle, textAlign: "right", fontWeight: 700, color: pnlColor(t.pnl_pct) }}>
                        {t.status === "CLOSED" ? fmtPnl(t.pnl_pct) : "\u2014"}
                      </td>
                      <td style={{ ...cellStyle, textAlign: "right" }}>
                        <span style={S.badge(
                          t.status === "OPEN" ? "rgba(34,211,238,0.12)" : T.overlay04,
                          t.status === "OPEN" ? "#22d3ee" : T.text4,
                          t.status === "OPEN" ? "rgba(34,211,238,0.3)" : T.border,
                        )}>{t.status}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ─── RECENT FILLS ─── */}
      {fills.length > 0 && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>Recent Fills ({fills.length})</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={headerCell}>Time</th>
                  <th style={headerCell}>Coin</th>
                  <th style={headerCell}>Side</th>
                  <th style={headerCell}>Size</th>
                  <th style={headerCell}>Price</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>Fee</th>
                  <th style={{ ...headerCell, textAlign: "right" }}>Closed PnL</th>
                </tr>
              </thead>
              <tbody>
                {fills.map((f, i) => {
                  const isBuy = f.side === "B" || f.side?.toLowerCase() === "buy";
                  return (
                    <tr key={f.hash || i}>
                      <td style={cellStyle}>{timeAgo(f.time)}</td>
                      <td style={{ ...cellStyle, fontWeight: 700, color: T.text1 }}>{f.coin}</td>
                      <td style={cellStyle}>
                        <span style={{
                          color: isBuy ? "#34d399" : "#f87171",
                          fontWeight: 600,
                        }}>{isBuy ? "BUY" : "SELL"}</span>
                      </td>
                      <td style={cellStyle}>{f.size}</td>
                      <td style={cellStyle}>{fmtPrice(f.price)}</td>
                      <td style={{ ...cellStyle, textAlign: "right", color: T.text3 }}>
                        ${f.fee?.toFixed(4) || "0"}
                      </td>
                      <td style={{ ...cellStyle, textAlign: "right", color: pnlColor(f.closed_pnl), fontWeight: 600 }}>
                        {f.closed_pnl ? fmtUsd(f.closed_pnl) : "\u2014"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ─── STATS SUMMARY ─── */}
      {stats.total_trades > 0 && (
        <div style={S.section}>
          <div style={S.sectionHeader}>
            <span style={S.title}>Performance Stats</span>
          </div>
          <div style={{
            display: "flex", justifyContent: "space-around",
            padding: "14px 20px", gap: 16, flexWrap: "wrap",
          }}>
            <StatBox label="TOTAL TRADES" value={stats.total_trades} />
            <StatBox label="OPEN" value={stats.open_trades} color={stats.open_trades > 0 ? "#22d3ee" : T.text3} />
            <StatBox label="WIN RATE" value={`${stats.win_rate}%`}
              color={stats.win_rate >= 50 ? "#34d399" : "#fbbf24"} />
            <StatBox label="TOTAL P&L" value={fmtUsd(stats.total_pnl_usd)} color={pnlColor(stats.total_pnl_usd)} />
            <StatBox label="AVG P&L" value={fmtPnl(stats.avg_pnl_pct)} color={pnlColor(stats.avg_pnl_pct)} />
            <StatBox label="BEST" value={fmtPnl(stats.best_pnl_pct)} color="#34d399" />
            <StatBox label="WORST" value={fmtPnl(stats.worst_pnl_pct)} color="#f87171" />
          </div>
        </div>
      )}
    </div>
  );
}
