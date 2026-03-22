import { useState, useEffect, useCallback, useMemo } from "react";
import { T } from "../theme.js";
import GlassCard from "./GlassCard.jsx";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── HELPERS ─────────────────────────────────────────────────────────────────

const fmt$ = (v) => {
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
};

const fmtPct = (v) => {
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M%`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K%`;
  return `${v.toFixed(0)}%`;
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

// ─── STATUS STRIP ────────────────────────────────────────────────────────────

function StatusStrip({ status }) {
  const items = [
    { label: "WALLETS", value: status.tracked_wallets || 0 },
    { label: "WITH DATA", value: status.wallets_with_data || 0 },
    { label: "SYMBOLS", value: status.consensus_symbols || 0 },
    { label: "POLLS", value: status.poll_count || 0 },
    { label: "LAST POLL", value: timeAgo(status.last_poll) },
  ];

  return (
    <div style={{
      display: "flex", flexWrap: "wrap", gap: 6,
      padding: "12px 16px",
      borderBottom: `1px solid ${T.border}`,
    }}>
      {items.map(({ label, value }) => (
        <div key={label} style={{
          display: "flex", alignItems: "center", gap: 6,
          padding: "4px 10px",
          borderRadius: 6,
          background: T.overlay04,
          border: `1px solid ${T.overlay06}`,
        }}>
          <span style={{ fontFamily: T.mono, fontSize: 12, color: T.text4, letterSpacing: "0.05em" }}>
            {label}
          </span>
          <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.text1 }}>
            {value}
          </span>
        </div>
      ))}
      {/* Live pulse indicator */}
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{
          width: 6, height: 6, borderRadius: "50%",
          background: status.initialized ? T.green : T.yellow,
          animation: status.initialized ? "pulse 2s ease-in-out infinite" : "none",
        }} />
        <span style={{ fontFamily: T.mono, fontSize: 12, color: T.text4 }}>
          {status.initialized ? "LIVE" : "WARMING UP"}
        </span>
      </div>
    </div>
  );
}

// ─── CONSENSUS BAR ───────────────────────────────────────────────────────────

function ConsensusBar({ long_count, short_count, total_tracked }) {
  const total = long_count + short_count;
  if (total === 0) return <span style={{ color: T.text4 }}>--</span>;
  const longPct = (long_count / total) * 100;
  const shortPct = (short_count / total) * 100;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", minWidth: 80 }}>
      <div style={{
        flex: 1, height: 6, borderRadius: 3,
        background: T.overlay06,
        overflow: "hidden",
        display: "flex",
      }}>
        <div style={{
          width: `${longPct}%`, height: "100%",
          background: `linear-gradient(90deg, ${T.green}90, ${T.green})`,
          borderRadius: "3px 0 0 3px",
          transition: "width 0.4s ease",
        }} />
        <div style={{
          width: `${shortPct}%`, height: "100%",
          background: `linear-gradient(90deg, ${T.red}, ${T.red}90)`,
          borderRadius: "0 3px 3px 0",
          transition: "width 0.4s ease",
        }} />
      </div>
      <span style={{ fontFamily: T.mono, fontSize: 12, color: T.text4, whiteSpace: "nowrap", minWidth: 38, textAlign: "right" }}>
        {long_count}/{short_count}
      </span>
    </div>
  );
}

// ─── CONSENSUS TABLE ─────────────────────────────────────────────────────────

function ConsensusTable({ consensus, filter, onSymbolClick, isMobile }) {
  const [sortKey, setSortKey] = useState("positioned");
  const [sortAsc, setSortAsc] = useState(false);

  const filtered = useMemo(() => {
    let items = [...consensus];
    if (filter) {
      const q = filter.toUpperCase();
      items = items.filter(c => c.symbol.includes(q));
    }
    items.sort((a, b) => {
      let va, vb;
      switch (sortKey) {
        case "symbol": va = a.symbol; vb = b.symbol; return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        case "trend": va = a.trend; vb = b.trend; return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        case "long": va = a.long_count; vb = b.long_count; break;
        case "short": va = a.short_count; vb = b.short_count; break;
        case "notional": va = a.long_notional + a.short_notional; vb = b.long_notional + b.short_notional; break;
        case "net": va = a.net_ratio; vb = b.net_ratio; break;
        default: va = a.long_count + a.short_count; vb = b.long_count + b.short_count;
      }
      return sortAsc ? va - vb : vb - va;
    });
    return items;
  }, [consensus, filter, sortKey, sortAsc]);

  const handleSort = (key) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  };

  const cols = [
    { key: "symbol", label: "SYMBOL", w: 70 },
    { key: "trend", label: "TREND", w: 72 },
    { key: "positioned", label: "WALLETS", w: 60 },
    { key: null, label: "L / S", w: isMobile ? 100 : 140 },
    { key: "net", label: "NET", w: 50 },
    ...(!isMobile ? [{ key: "notional", label: "NOTIONAL", w: 90 }] : []),
  ];

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {cols.map(({ key, label, w }) => (
              <th
                key={label}
                onClick={key ? () => handleSort(key) : undefined}
                style={{
                  padding: "8px 10px",
                  textAlign: label === "SYMBOL" ? "left" : "center",
                  fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  color: sortKey === key ? T.accent : T.text4,
                  letterSpacing: "0.06em",
                  cursor: key ? "pointer" : "default",
                  borderBottom: `1px solid ${T.border}`,
                  whiteSpace: "nowrap",
                  minWidth: w,
                  userSelect: "none",
                }}
              >
                {label}
                {sortKey === key && (sortAsc ? " \u25B2" : " \u25BC")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filtered.map((c) => {
            const positioned = c.long_count + c.short_count;
            return (
              <tr
                key={c.symbol}
                onClick={() => onSymbolClick?.(c.symbol)}
                style={{
                  cursor: "pointer",
                  transition: "background 0.15s",
                }}
                onMouseEnter={e => e.currentTarget.style.background = T.overlay06}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}
              >
                <td style={{ padding: "8px 10px", fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.text1 }}>
                  {c.symbol}
                </td>
                <td style={{ padding: "8px 10px", textAlign: "center" }}>
                  <span style={{
                    fontFamily: T.mono, fontSize: 12, fontWeight: 700,
                    padding: "2px 8px", borderRadius: 4,
                    color: trendColor(c.trend),
                    background: `${trendColor(c.trend)}15`,
                    border: `1px solid ${trendColor(c.trend)}25`,
                  }}>
                    {c.trend}
                  </span>
                </td>
                <td style={{ padding: "8px 10px", textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text2 }}>
                  {positioned}
                </td>
                <td style={{ padding: "8px 10px" }}>
                  <ConsensusBar long_count={c.long_count} short_count={c.short_count} total_tracked={c.total_tracked} />
                </td>
                <td style={{
                  padding: "8px 10px", textAlign: "center",
                  fontFamily: T.mono, fontSize: 13, fontWeight: 600,
                  color: c.net_ratio > 0.1 ? T.green : c.net_ratio < -0.1 ? T.red : T.text3,
                }}>
                  {c.net_ratio > 0 ? "+" : ""}{(c.net_ratio * 100).toFixed(0)}%
                </td>
                {!isMobile && (
                  <td style={{ padding: "8px 10px", textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text3 }}>
                    {fmt$(c.long_notional + c.short_notional)}
                  </td>
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

// ─── ROSTER TABLE ────────────────────────────────────────────────────────────

function RosterTable({ wallets, onWalletClick, isMobile }) {
  const [sortKey, setSortKey] = useState("rank");
  const [sortAsc, setSortAsc] = useState(true);

  const sorted = useMemo(() => {
    const items = [...wallets];
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
  }, [wallets, sortKey, sortAsc]);

  const handleSort = (key) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(key === "rank"); }
  };

  const cols = [
    { key: "rank", label: "#", w: 36 },
    { key: null, label: "WALLET", w: 100 },
    { key: "av", label: "ACCT VALUE", w: 90 },
    { key: "roi", label: "ROI", w: 70 },
    ...(!isMobile ? [
      { key: "score", label: "SCORE", w: 60 },
      { key: "positions", label: "POS", w: 44 },
    ] : []),
  ];

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            {cols.map(({ key, label, w }) => (
              <th
                key={label}
                onClick={key ? () => handleSort(key) : undefined}
                style={{
                  padding: "8px 10px",
                  textAlign: label === "WALLET" || label === "#" ? "left" : "right",
                  fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  color: sortKey === key ? T.accent : T.text4,
                  letterSpacing: "0.06em",
                  cursor: key ? "pointer" : "default",
                  borderBottom: `1px solid ${T.border}`,
                  whiteSpace: "nowrap",
                  minWidth: w,
                  userSelect: "none",
                }}
              >
                {label}
                {sortKey === key && (sortAsc ? " \u25B2" : " \u25BC")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((w) => (
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
                <span style={{ fontFamily: T.mono, fontSize: 13, color: T.accent }}>
                  {truncAddr(w.address)}
                </span>
                {w.display_name && (
                  <span style={{ fontFamily: T.font, fontSize: 12, color: T.text4, marginLeft: 6 }}>
                    {w.display_name.length > 12 ? w.display_name.slice(0, 12) + "..." : w.display_name}
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
                    {w.score.toFixed(0)}
                  </td>
                  <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: w.position_count > 0 ? T.text1 : T.text4 }}>
                    {w.position_count}
                  </td>
                </>
              )}
            </tr>
          ))}
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
      padding: "8px 14px", borderRadius: 8,
      background: T.overlay04, border: `1px solid ${T.overlay06}`,
      minWidth: 70,
    }}>
      <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4, letterSpacing: "0.06em", marginBottom: 3 }}>
        {label}
      </span>
      <span style={{ fontFamily: T.mono, fontSize: 15, fontWeight: 700, color: color || T.text1 }}>
        {value}
      </span>
    </div>
  );
}

// ─── WALLET PROFILE DRAWER ──────────────────────────────────────────────────

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

  const sections = [
    { key: "positions", label: `Positions (${positions.length})` },
    { key: "trades", label: `Trades (${trades.length})` },
    { key: "coins", label: "Coin Stats" },
  ];

  return (
    <GlassCard style={{ padding: 0 }}>
      {/* Header */}
      <div style={{
        padding: "14px 16px",
        borderBottom: `1px solid ${T.border}`,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontFamily: T.mono, fontSize: 15, fontWeight: 700, color: T.accent }}>
              {truncAddr(address)}
            </span>
            {data.display_name && (
              <span style={{ fontFamily: T.font, fontSize: 13, color: T.text3 }}>
                {data.display_name}
              </span>
            )}
            {data.rank && (
              <span style={{
                fontFamily: T.mono, fontSize: 11, fontWeight: 700,
                padding: "2px 6px", borderRadius: 4,
                color: T.accent, background: `${T.accent}15`,
                border: `1px solid ${T.accent}25`,
              }}>
                #{data.rank}
              </span>
            )}
          </div>
          <div style={{ fontFamily: T.mono, fontSize: 12, color: T.text4, marginTop: 3 }}>
            {data.snapshot_count} snapshots tracked
          </div>
        </div>
        <button
          onClick={onClose}
          style={{
            width: 28, height: 28, borderRadius: 6,
            border: `1px solid ${T.border}`,
            background: T.surface, color: T.text3,
            fontSize: 15, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          {"\u2715"}
        </button>
      </div>

      {/* Stat pills */}
      <div style={{
        padding: "12px 16px",
        display: "flex", flexWrap: "wrap", gap: 6,
        borderBottom: `1px solid ${T.border}`,
      }}>
        <StatPill label="ACCT VALUE" value={fmt$(data.account_value || 0)} />
        <StatPill label="MONTHLY ROI" value={fmtPct(data.monthly_roi || 0)} color={T.green} />
        <StatPill label="SCORE" value={(data.score || 0).toFixed(0)} />
        <StatPill
          label="WIN RATE"
          value={s.total_trades > 0 ? `${s.win_rate}%` : "--"}
          color={s.win_rate > 50 ? T.green : s.win_rate > 0 ? T.red : T.text4}
        />
        <StatPill
          label="TRADES"
          value={s.total_trades || 0}
        />
        <StatPill
          label="AVG PNL"
          value={s.total_trades > 0 ? `${s.avg_pnl_pct > 0 ? "+" : ""}${s.avg_pnl_pct}%` : "--"}
          color={s.avg_pnl_pct > 0 ? T.green : s.avg_pnl_pct < 0 ? T.red : T.text4}
        />
      </div>

      {/* Best/Worst trade badges */}
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
              color: T.green, background: `${T.green}12`,
              border: `1px solid ${T.green}20`,
            }}>
              Best: {s.best_trade.coin} {s.best_trade.side} +{fmt$(Math.abs(s.best_trade.pnl))} ({s.best_trade.pnl_pct > 0 ? "+" : ""}{s.best_trade.pnl_pct}%)
            </span>
          )}
          {s.worst_trade && (
            <span style={{
              fontFamily: T.mono, fontSize: 12,
              padding: "3px 8px", borderRadius: 4,
              color: T.red, background: `${T.red}12`,
              border: `1px solid ${T.red}20`,
            }}>
              Worst: {s.worst_trade.coin} {s.worst_trade.side} -{fmt$(Math.abs(s.worst_trade.pnl))} ({s.worst_trade.pnl_pct}%)
            </span>
          )}
        </div>
      )}

      {/* Section tabs */}
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
              padding: "5px 12px", borderRadius: 5,
              border: "none",
              fontFamily: T.mono, fontSize: 12, fontWeight: 600,
              color: activeSection === key ? T.text1 : T.text4,
              background: activeSection === key ? T.overlay10 : "transparent",
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Section content */}
      <div style={{ overflowX: "auto" }}>
        {/* POSITIONS */}
        {activeSection === "positions" && (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {["COIN", "SIDE", "SIZE", "ENTRY", "PNL", "LEV"].map(h => (
                  <th key={h} style={{
                    padding: "8px 10px",
                    fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                    color: T.text4, letterSpacing: "0.06em",
                    borderBottom: `1px solid ${T.border}`,
                    textAlign: h === "COIN" || h === "SIDE" ? "left" : "right",
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => (
                <tr key={i}>
                  <td style={{ padding: "7px 10px", fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.text1 }}>
                    {p.coin}
                  </td>
                  <td style={{ padding: "7px 10px" }}>
                    <span style={{
                      fontFamily: T.mono, fontSize: 12, fontWeight: 700,
                      padding: "2px 6px", borderRadius: 3,
                      color: p.side === "LONG" ? T.green : T.red,
                      background: `${p.side === "LONG" ? T.green : T.red}15`,
                    }}>
                      {p.side}
                    </span>
                  </td>
                  <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text1 }}>
                    {fmt$(p.size_usd)}
                  </td>
                  <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text3 }}>
                    ${p.entry_px.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </td>
                  <td style={{
                    padding: "7px 10px", textAlign: "right",
                    fontFamily: T.mono, fontSize: 13, fontWeight: 600,
                    color: p.unrealized_pnl >= 0 ? T.green : T.red,
                  }}>
                    {p.unrealized_pnl >= 0 ? "+" : ""}{fmt$(Math.abs(p.unrealized_pnl))}
                  </td>
                  <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
                    {p.leverage}x
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
                    {["COIN", "SIDE", "SIZE", "ENTRY", "PNL", "STATUS"].map(h => (
                      <th key={h} style={{
                        padding: "8px 10px",
                        fontFamily: T.mono, fontSize: 12, fontWeight: 600,
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
                        <td style={{ padding: "7px 10px", fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.text1 }}>
                          {t.coin}
                        </td>
                        <td style={{ padding: "7px 10px" }}>
                          <span style={{
                            fontFamily: T.mono, fontSize: 12, fontWeight: 700,
                            padding: "2px 6px", borderRadius: 3,
                            color: t.side === "LONG" ? T.green : T.red,
                            background: `${t.side === "LONG" ? T.green : T.red}15`,
                          }}>
                            {t.side}
                          </span>
                        </td>
                        <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text1 }}>
                          {fmt$(t.size_usd)}
                        </td>
                        <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text3 }}>
                          ${t.entry_px.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </td>
                        <td style={{
                          padding: "7px 10px", textAlign: "right",
                          fontFamily: T.mono, fontSize: 13, fontWeight: 600,
                          color: t.pnl >= 0 ? T.green : T.red,
                        }}>
                          {t.status !== "OPENED" ? (
                            <>{t.pnl >= 0 ? "+" : ""}{fmt$(Math.abs(t.pnl))} <span style={{ fontSize: 11, color: T.text4 }}>({t.pnl_pct > 0 ? "+" : ""}{t.pnl_pct.toFixed(1)}%)</span></>
                          ) : (
                            <span style={{ color: T.text4 }}>--</span>
                          )}
                        </td>
                        <td style={{ padding: "7px 10px" }}>
                          <span style={{
                            fontFamily: T.mono, fontSize: 11, fontWeight: 700,
                            padding: "2px 6px", borderRadius: 3,
                            color: statusColor,
                            background: `${statusColor}15`,
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
                      <td style={{ padding: "7px 10px", fontFamily: T.mono, fontSize: 13, fontWeight: 600, color: T.text1 }}>
                        {c.coin}
                      </td>
                      <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text2 }}>
                        {c.trades}
                      </td>
                      <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.green }}>
                        {c.wins}
                      </td>
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

        {/* Empty state for positions */}
        {activeSection === "positions" && positions.length === 0 && (
          <div style={{ padding: 16, textAlign: "center", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
            No open positions
          </div>
        )}
      </div>
    </GlassCard>
  );
}

// ─── SYMBOL DETAIL DRAWER ────────────────────────────────────────────────────

function SymbolDetail({ symbol, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/api/hyperlens/positions/${symbol}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [symbol]);

  if (loading) {
    return (
      <GlassCard style={{ padding: 20 }}>
        <div style={{ fontFamily: T.mono, fontSize: 13, color: T.text4, textAlign: "center" }}>Loading...</div>
      </GlassCard>
    );
  }

  const positions = data?.positions || [];

  return (
    <GlassCard style={{ padding: 0 }}>
      <div style={{
        padding: "12px 16px",
        borderBottom: `1px solid ${T.border}`,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span style={{ fontFamily: T.mono, fontSize: 15, fontWeight: 700, color: T.text1 }}>
          {symbol}
          <span style={{ color: T.text4, fontWeight: 400, marginLeft: 8, fontSize: 11 }}>
            {positions.length} wallet{positions.length !== 1 ? "s" : ""}
          </span>
        </span>
        <button
          onClick={onClose}
          style={{
            width: 28, height: 28, borderRadius: 6,
            border: `1px solid ${T.border}`,
            background: T.surface, color: T.text3,
            fontSize: 15, cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >
          {"\u2715"}
        </button>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["WALLET", "SIDE", "SIZE", "ENTRY", "PNL", "LEV"].map(h => (
                <th key={h} style={{
                  padding: "8px 10px",
                  fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  color: T.text4, letterSpacing: "0.06em",
                  borderBottom: `1px solid ${T.border}`,
                  textAlign: h === "WALLET" || h === "SIDE" ? "left" : "right",
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {positions.map((p, i) => (
              <tr key={i}>
                <td style={{ padding: "7px 10px" }}>
                  <span style={{ fontFamily: T.mono, fontSize: 13, color: T.accent }}>
                    {truncAddr(p.address)}
                  </span>
                  <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text4, marginLeft: 4 }}>
                    {p.wallet_roi > 0 ? fmtPct(p.wallet_roi) : ""}
                  </span>
                </td>
                <td style={{ padding: "7px 10px" }}>
                  <span style={{
                    fontFamily: T.mono, fontSize: 12, fontWeight: 700,
                    padding: "2px 6px", borderRadius: 3,
                    color: p.side === "LONG" ? T.green : T.red,
                    background: `${p.side === "LONG" ? T.green : T.red}15`,
                  }}>
                    {p.side}
                  </span>
                </td>
                <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text1 }}>
                  {fmt$(p.size_usd)}
                </td>
                <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text3 }}>
                  ${p.entry_px.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </td>
                <td style={{
                  padding: "7px 10px", textAlign: "right",
                  fontFamily: T.mono, fontSize: 13, fontWeight: 600,
                  color: p.unrealized_pnl >= 0 ? T.green : T.red,
                }}>
                  {p.unrealized_pnl >= 0 ? "+" : ""}{fmt$(Math.abs(p.unrealized_pnl))}
                </td>
                <td style={{ padding: "7px 10px", textAlign: "right", fontFamily: T.mono, fontSize: 13, color: T.text4 }}>
                  {p.leverage}x
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

function TabSwitcher({ active, onChange }) {
  const tabs = [
    { key: "consensus", label: "Consensus" },
    { key: "roster", label: "Roster" },
  ];

  return (
    <div style={{
      display: "flex", gap: 2,
      padding: "4px",
      borderRadius: 8,
      background: T.overlay04,
      border: `1px solid ${T.overlay06}`,
    }}>
      {tabs.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          style={{
            flex: 1,
            padding: "6px 14px",
            borderRadius: 6,
            border: "none",
            fontFamily: T.mono, fontSize: 13, fontWeight: 600,
            color: active === key ? T.text1 : T.text4,
            background: active === key ? T.overlay10 : "transparent",
            cursor: "pointer",
            transition: "all 0.2s ease",
            letterSpacing: "0.03em",
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PANEL
// ═══════════════════════════════════════════════════════════════════════════════

export default function HyperLensPanel({ isMobile }) {
  const [tab, setTab] = useState("consensus");
  const [filter, setFilter] = useState("");
  const [status, setStatus] = useState({});
  const [consensus, setConsensus] = useState([]);
  const [roster, setRoster] = useState([]);
  const [selectedWallet, setSelectedWallet] = useState(null);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const [statusRes, consensusRes, rosterRes] = await Promise.all([
        fetch(`${API}/api/hyperlens/status`).then(r => r.json()),
        fetch(`${API}/api/hyperlens/consensus`).then(r => r.json()),
        fetch(`${API}/api/hyperlens/roster`).then(r => r.json()),
      ]);
      setStatus(statusRes);
      setConsensus(consensusRes.consensus || []);
      setRoster(rosterRes.wallets || []);
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

  // Summary stats for the header
  const bullish = consensus.filter(c => c.trend === "BULLISH").length;
  const bearish = consensus.filter(c => c.trend === "BEARISH").length;
  const neutral = consensus.filter(c => c.trend === "NEUTRAL").length;

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
              padding: "2px 8px", borderRadius: 4,
              background: T.overlay06,
            }}>
              Top {status.tracked_wallets || 0} wallets
            </span>
          </div>

          {/* Trend summary badges */}
          {consensus.length > 0 && (
            <div style={{ display: "flex", gap: 6 }}>
              {bullish > 0 && (
                <span style={{
                  fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  padding: "3px 8px", borderRadius: 4,
                  color: T.green, background: `${T.green}15`,
                  border: `1px solid ${T.green}25`,
                }}>
                  {bullish} BULL
                </span>
              )}
              {bearish > 0 && (
                <span style={{
                  fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  padding: "3px 8px", borderRadius: 4,
                  color: T.red, background: `${T.red}15`,
                  border: `1px solid ${T.red}25`,
                }}>
                  {bearish} BEAR
                </span>
              )}
              {neutral > 0 && (
                <span style={{
                  fontFamily: T.mono, fontSize: 12, fontWeight: 600,
                  padding: "3px 8px", borderRadius: 4,
                  color: T.text4, background: T.overlay06,
                  border: `1px solid ${T.overlay10}`,
                }}>
                  {neutral} FLAT
                </span>
              )}
            </div>
          )}
        </div>

        <StatusStrip status={status} />

        {/* Controls bar */}
        <div style={{
          padding: "12px 16px",
          display: "flex", alignItems: "center", gap: 10,
          flexWrap: "wrap",
        }}>
          <TabSwitcher active={tab} onChange={setTab} />

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
                background: T.overlay04,
                color: T.text1,
                outline: "none",
                width: 140,
                transition: "border-color 0.2s",
              }}
              onFocus={e => e.target.style.borderColor = T.accent}
              onBlur={e => e.target.style.borderColor = T.border}
            />
          )}
        </div>
      </GlassCard>

      {/* Detail drawer (wallet or symbol) */}
      {selectedWallet && (
        <WalletDetail address={selectedWallet} onClose={() => setSelectedWallet(null)} />
      )}
      {selectedSymbol && (
        <SymbolDetail symbol={selectedSymbol} onClose={() => setSelectedSymbol(null)} />
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
            />
          )}
          {tab === "roster" && (
            <RosterTable
              wallets={roster}
              onWalletClick={(addr) => { setSelectedWallet(addr); setSelectedSymbol(null); }}
              isMobile={isMobile}
            />
          )}
        </GlassCard>
      )}
    </div>
  );
}
