import { useState, useEffect, useCallback, useMemo } from "react";
import { T } from "../theme.js";
import GlassCard from "./GlassCard.jsx";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── CHAIN COLORS ────────────────────────────────────────────────────────────
const CHAIN_META = {
  ethereum: { label: "ETH", color: "#627eea" },
  base:     { label: "BASE", color: "#0052ff" },
  solana:   { label: "SOL", color: "#9945ff" },
};

const ALERT_COLORS = {
  ACCUMULATING: "#22d3ee",
  DISTRIBUTING: "#f87171",
  NEW_WHALE:    "#34d399",
  LARGE_BUY:    "#34d399",
  LARGE_SELL:   "#f87171",
};

// ─── HELPERS ─────────────────────────────────────────────────────────────────

function truncAddr(addr) {
  if (!addr || addr.length < 12) return addr || "";
  return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
}

function fmtUsd(v) {
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

function fmtTime(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function fmtTokenVal(v) {
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toFixed(2);
}

// ─── STYLES ──────────────────────────────────────────────────────────────────

const S = {
  section: { marginBottom: 16 },
  label: { fontSize: 10, color: T.text4, fontFamily: T.mono, letterSpacing: "0.06em", fontWeight: 600 },
  input: {
    padding: "8px 12px", borderRadius: 10,
    border: `1px solid ${T.border}`, background: T.overlay06,
    color: T.text1, fontFamily: T.mono, fontSize: 12, outline: "none",
    flex: 1, minWidth: 0,
  },
  select: {
    padding: "8px 12px", borderRadius: 10,
    border: `1px solid ${T.border}`, background: T.overlay06,
    color: T.text1, fontFamily: T.mono, fontSize: 12, outline: "none",
    appearance: "none", cursor: "pointer",
  },
  btn: {
    padding: "8px 16px", borderRadius: 10, border: "none", cursor: "pointer",
    fontFamily: T.mono, fontSize: 11, fontWeight: 700, letterSpacing: "0.04em",
    background: `linear-gradient(180deg, #2ee0f8 0%, #1ab8d4 100%)`,
    color: "#000", transition: "all 0.2s",
  },
  btnDanger: {
    padding: "4px 10px", borderRadius: 8, border: "none", cursor: "pointer",
    fontFamily: T.mono, fontSize: 10, fontWeight: 600,
    background: "rgba(248,113,113,0.12)", color: "#f87171",
  },
  chip: (color) => ({
    display: "inline-flex", alignItems: "center", gap: 4,
    padding: "3px 10px", borderRadius: 20, fontSize: 9, fontWeight: 700,
    fontFamily: T.mono, letterSpacing: "0.04em",
    background: `${color}18`, color, border: `1px solid ${color}30`,
  }),
  th: {
    padding: "8px 10px", textAlign: "left", fontSize: 9, fontWeight: 700,
    color: T.text4, fontFamily: T.mono, letterSpacing: "0.08em",
    borderBottom: `1px solid ${T.borderH}`, whiteSpace: "nowrap",
  },
  td: { padding: "8px 10px", fontSize: 11, fontFamily: T.mono, whiteSpace: "nowrap" },
};

// ─── SUB-COMPONENTS ──────────────────────────────────────────────────────────

function ChainBadge({ chain }) {
  const meta = CHAIN_META[chain] || { label: chain?.toUpperCase(), color: T.text4 };
  return <span style={S.chip(meta.color)}>{meta.label}</span>;
}

function DirectionBadge({ direction }) {
  const color = direction === "BUY" ? "#34d399" : direction === "SELL" ? "#f87171" : T.text4;
  return <span style={{ ...S.chip(color), minWidth: 36, justifyContent: "center" }}>{direction}</span>;
}

function AlertTypeBadge({ type }) {
  const color = ALERT_COLORS[type] || T.text4;
  const label = type?.replace("_", " ") || "UNKNOWN";
  return <span style={S.chip(color)}>{label}</span>;
}

function AddrCell({ addr, label }) {
  return (
    <span title={addr} style={{ color: label ? T.accent : T.text2, cursor: "default" }}>
      {label || truncAddr(addr)}
    </span>
  );
}

// ─── STATUS BAR ──────────────────────────────────────────────────────────────

function StatusBar({ status }) {
  if (!status) return null;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
      marginBottom: 12, padding: "8px 14px", borderRadius: 10,
      background: T.overlay04, border: `1px solid ${T.border}`,
    }}>
      <span style={S.label}>CHAINS</span>
      {status.active_chains?.length > 0
        ? status.active_chains.map(c => <ChainBadge key={c} chain={c} />)
        : <span style={{ fontSize: 10, color: "#fbbf24", fontFamily: T.mono }}>No API keys set</span>}
      <span style={{ ...S.label, marginLeft: "auto" }}>
        {status.tracked_token_count} tokens {"\u00b7"} {status.transfer_count} txns {"\u00b7"} {status.alert_count} alerts
      </span>
      {status.last_poll && (
        <span style={{ fontSize: 9, color: T.text4, fontFamily: T.mono }}>
          Last: {fmtTime(status.last_poll)}
        </span>
      )}
    </div>
  );
}

// ─── ADD TOKEN FORM ──────────────────────────────────────────────────────────

function AddTokenForm({ onAdd, activeChains }) {
  const [chain, setChain] = useState("ethereum");
  const [contract, setContract] = useState("");
  const [adding, setAdding] = useState(false);

  const handleAdd = async () => {
    if (!contract.trim()) return;
    setAdding(true);
    try {
      await onAdd(chain, contract.trim());
      setContract("");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div style={{
      display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap",
      marginBottom: 16,
    }}>
      <select
        value={chain} onChange={e => setChain(e.target.value)}
        style={{ ...S.select, width: 100 }}
      >
        {Object.entries(CHAIN_META).map(([k, v]) => (
          <option key={k} value={k}>{v.label}</option>
        ))}
      </select>
      <input
        value={contract}
        onChange={e => setContract(e.target.value)}
        onKeyDown={e => e.key === "Enter" && handleAdd()}
        placeholder="Paste token contract address..."
        style={S.input}
      />
      <button onClick={handleAdd} disabled={adding || !contract.trim()} style={{
        ...S.btn, opacity: adding || !contract.trim() ? 0.5 : 1,
      }}>
        {adding ? "Adding..." : "Track"}
      </button>
    </div>
  );
}

// ─── TOKEN CARD ──────────────────────────────────────────────────────────────

function TokenCard({ token, transfers, holders, onRemove, isMobile }) {
  const [expanded, setExpanded] = useState(true);

  // Activity summary
  const buyCount = transfers?.filter(t => t.direction === "BUY").length || 0;
  const sellCount = transfers?.filter(t => t.direction === "SELL").length || 0;
  const totalUsd = transfers?.reduce((s, t) => s + (t.value_usd || 0), 0) || 0;

  return (
    <GlassCard style={{ marginBottom: 12 }}>
      {/* Header */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: "flex", alignItems: "center", gap: 8, padding: "10px 14px",
          cursor: "pointer", borderBottom: expanded ? `1px solid ${T.border}` : "none",
        }}
      >
        <ChainBadge chain={token.chain} />
        <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.text1 }}>
          {token.symbol || "Unknown"}
        </span>
        <span style={{ fontSize: 10, color: T.text4, fontFamily: T.mono }}>
          {token.name}
        </span>
        <span style={{ fontSize: 9, color: T.text4, fontFamily: T.mono, opacity: 0.6 }}>
          {truncAddr(token.contract)}
        </span>

        {/* Activity summary strip */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
          {transfers && transfers.length > 0 && (
            <span style={{ fontSize: 9, color: T.text3, fontFamily: T.mono }}>
              <span style={{ color: "#34d399" }}>{buyCount}B</span>
              {" / "}
              <span style={{ color: "#f87171" }}>{sellCount}S</span>
              {totalUsd > 0 && ` \u00b7 ${fmtUsd(totalUsd)}`}
            </span>
          )}
          <span style={{ fontSize: 11, color: T.text4, transform: expanded ? "rotate(180deg)" : "none", transition: "0.2s" }}>
            {"\u25bc"}
          </span>
          <button
            onClick={e => { e.stopPropagation(); onRemove(); }}
            style={S.btnDanger}
          >
            {"\u00d7"}
          </button>
        </div>
      </div>

      {expanded && (
        <div style={{ padding: "10px 14px" }}>
          {/* Transfers Table */}
          {transfers && transfers.length > 0 ? (
            <div style={{ overflowX: "auto", marginBottom: holders?.length > 0 ? 14 : 0 }}>
              <div style={{ ...S.label, marginBottom: 6 }}>RECENT TRANSFERS</div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={S.th}>TIME</th>
                    {!isMobile && <th style={S.th}>FROM</th>}
                    {!isMobile && <th style={S.th}>TO</th>}
                    {isMobile && <th style={S.th}>FROM {"\u2192"} TO</th>}
                    <th style={S.th}>AMOUNT</th>
                    <th style={S.th}>USD</th>
                    <th style={S.th}>TYPE</th>
                  </tr>
                </thead>
                <tbody>
                  {transfers.slice(0, 20).map((tx, i) => (
                    <tr key={tx.tx_hash + i} style={{
                      borderBottom: `1px solid ${T.border}`,
                      background: i % 2 === 0 ? "transparent" : T.overlay02,
                    }}>
                      <td style={{ ...S.td, color: T.text4 }}>{fmtTime(tx.timestamp)}</td>
                      {!isMobile && (
                        <td style={S.td}><AddrCell addr={tx.from_addr} label={tx.from_label} /></td>
                      )}
                      {!isMobile && (
                        <td style={S.td}><AddrCell addr={tx.to_addr} label={tx.to_label} /></td>
                      )}
                      {isMobile && (
                        <td style={S.td}>
                          <AddrCell addr={tx.from_addr} label={tx.from_label} />
                          <span style={{ color: T.text4, margin: "0 4px" }}>{"\u2192"}</span>
                          <AddrCell addr={tx.to_addr} label={tx.to_label} />
                        </td>
                      )}
                      <td style={{ ...S.td, color: T.text2 }}>{fmtTokenVal(tx.value)}</td>
                      <td style={{ ...S.td, color: tx.value_usd >= 50000 ? "#fbbf24" : T.text3, fontWeight: tx.value_usd >= 50000 ? 700 : 400 }}>
                        {tx.value_usd > 0 ? fmtUsd(tx.value_usd) : "\u2014"}
                      </td>
                      <td style={S.td}><DirectionBadge direction={tx.direction} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ padding: "16px 0", textAlign: "center", color: T.text4, fontSize: 11, fontFamily: T.mono }}>
              Waiting for transfer data...
            </div>
          )}

          {/* Holders Table */}
          {holders && holders.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <div style={{ ...S.label, marginBottom: 6 }}>TOP HOLDERS</div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={S.th}>#</th>
                    <th style={S.th}>ADDRESS</th>
                    <th style={S.th}>BALANCE</th>
                    <th style={S.th}>24H FLOW</th>
                    <th style={S.th}>TXN</th>
                  </tr>
                </thead>
                <tbody>
                  {holders.slice(0, 15).map((h, i) => (
                    <tr key={h.address} style={{
                      borderBottom: `1px solid ${T.border}`,
                      background: h.is_whale ? "rgba(34,211,238,0.03)" : "transparent",
                    }}>
                      <td style={{ ...S.td, color: T.text4 }}>{i + 1}</td>
                      <td style={S.td}>
                        <AddrCell addr={h.address} label={h.label} />
                        {h.is_whale && <span style={{ marginLeft: 4, fontSize: 9 }}>{"\uD83D\uDC33"}</span>}
                      </td>
                      <td style={{ ...S.td, color: T.text2 }}>{fmtTokenVal(h.balance)}</td>
                      <td style={{
                        ...S.td,
                        color: h.net_flow_24h > 0 ? "#34d399" : h.net_flow_24h < 0 ? "#f87171" : T.text4,
                        fontWeight: h.net_flow_24h !== 0 ? 600 : 400,
                      }}>
                        {h.net_flow_24h > 0 ? "+" : ""}{fmtTokenVal(h.net_flow_24h)}
                      </td>
                      <td style={{ ...S.td, color: T.text4 }}>{h.tx_count_24h}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </GlassCard>
  );
}

// ─── ALERTS VIEW ─────────────────────────────────────────────────────────────

function AlertsView({ alerts, isMobile }) {
  if (!alerts || alerts.length === 0) {
    return (
      <div style={{ padding: "32px 0", textAlign: "center", color: T.text4, fontSize: 12, fontFamily: T.mono }}>
        No alerts yet. Track tokens to start detecting whale activity.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {alerts.map((a, i) => (
        <GlassCard key={`${a.address}-${a.timestamp}-${i}`} style={{ padding: "10px 14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <ChainBadge chain={a.chain} />
            <AlertTypeBadge type={a.alert_type} />
            <span style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, color: T.text1 }}>
              {a.token_symbol}
            </span>
            <AddrCell addr={a.address} label={a.label} />
            {a.value_usd > 0 && (
              <span style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: "#fbbf24" }}>
                {fmtUsd(a.value_usd)}
              </span>
            )}
            <span style={{ fontSize: 9, color: T.text4, fontFamily: T.mono, marginLeft: "auto" }}>
              {fmtTime(a.timestamp)}
            </span>
          </div>
          <div style={{ fontSize: 10, color: T.text3, fontFamily: T.mono, marginTop: 4 }}>
            {a.details}
          </div>
        </GlassCard>
      ))}
    </div>
  );
}

// ─── TRENDING VIEW ───────────────────────────────────────────────────────────

function TrendingView({ trending, onTrack, isMobile }) {
  if (!trending || trending.length === 0) {
    return (
      <div style={{ padding: "32px 0", textAlign: "center", color: T.text4, fontSize: 12, fontFamily: T.mono }}>
        No trending tokens detected yet. The system needs tracked tokens and whale activity to surface trends.
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {trending.map((t, i) => (
        <GlassCard key={`${t.contract}-${i}`} style={{ padding: "10px 14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <ChainBadge chain={t.chain} />
            <span style={{ fontFamily: T.mono, fontSize: 13, fontWeight: 700, color: T.text1 }}>
              {t.symbol || truncAddr(t.contract)}
            </span>
            {t.name && (
              <span style={{ fontSize: 10, color: T.text4, fontFamily: T.mono }}>{t.name}</span>
            )}
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 10, color: T.accent, fontFamily: T.mono, fontWeight: 600 }}>
                {t.whale_tx_count} whales
              </span>
              {t.whale_volume_usd > 0 && (
                <span style={{ fontSize: 10, color: "#fbbf24", fontFamily: T.mono, fontWeight: 600 }}>
                  {fmtUsd(t.whale_volume_usd)} vol
                </span>
              )}
              <button
                onClick={() => onTrack(t.chain, t.contract)}
                style={{ ...S.btn, padding: "4px 12px", fontSize: 10 }}
              >
                Track
              </button>
            </div>
          </div>
        </GlassCard>
      ))}
    </div>
  );
}

// ─── NO KEYS MESSAGE ─────────────────────────────────────────────────────────

function SetupMessage() {
  return (
    <GlassCard style={{ padding: "24px 20px", textAlign: "center" }}>
      <div style={{ fontSize: 28, marginBottom: 12 }}>{"\uD83D\uDC33"}</div>
      <div style={{ fontFamily: T.font, fontSize: 14, fontWeight: 600, color: T.text1, marginBottom: 8 }}>
        On-Chain Whale Tracker
      </div>
      <div style={{ fontFamily: T.mono, fontSize: 11, color: T.text3, lineHeight: 1.6, maxWidth: 480, margin: "0 auto" }}>
        Set one or more API keys as environment variables to enable whale tracking:
      </div>
      <div style={{
        marginTop: 12, padding: "12px 16px", borderRadius: 10,
        background: T.overlay06, border: `1px solid ${T.border}`,
        fontFamily: T.mono, fontSize: 11, color: T.accent, textAlign: "left",
        display: "inline-block", lineHeight: 1.8,
      }}>
        ETHERSCAN_API_KEY=your_key_here<br />
        BASESCAN_API_KEY=your_key_here<br />
        SOLSCAN_API_KEY=your_key_here
      </div>
      <div style={{ fontFamily: T.mono, fontSize: 10, color: T.text4, marginTop: 12 }}>
        Free tiers available at etherscan.io, basescan.org, and solscan.io
      </div>
    </GlassCard>
  );
}


// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PANEL
// ═══════════════════════════════════════════════════════════════════════════════

export default function WhalesPanel({ isMobile }) {
  const [status, setStatus] = useState(null);
  const [tokens, setTokens] = useState([]);
  const [transfers, setTransfers] = useState({});   // contract -> transfers
  const [holders, setHolders] = useState({});        // contract -> holders
  const [alerts, setAlerts] = useState([]);
  const [trending, setTrending] = useState([]);
  const [subTab, setSubTab] = useState("feed");      // feed | trending | alerts
  const [error, setError] = useState(null);

  // ── Fetch helpers ───────────────────────────────────────────────────────

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/whales/status`);
      setStatus(await res.json());
    } catch (e) { setError(e.message); }
  }, []);

  const fetchTokens = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/whales/tokens`);
      setTokens(await res.json());
    } catch (_) {}
  }, []);

  const fetchTransfers = useCallback(async (tokenList) => {
    const map = {};
    for (const t of tokenList) {
      try {
        const res = await fetch(
          `${API}/api/whales/transfers?chain=${t.chain}&contract=${encodeURIComponent(t.contract)}&limit=30`
        );
        map[t.contract] = await res.json();
      } catch (_) {
        map[t.contract] = [];
      }
    }
    setTransfers(map);
  }, []);

  const fetchHolders = useCallback(async (tokenList) => {
    const map = {};
    for (const t of tokenList) {
      try {
        const res = await fetch(
          `${API}/api/whales/holders/${t.chain}/${encodeURIComponent(t.contract)}`
        );
        map[t.contract] = await res.json();
      } catch (_) {
        map[t.contract] = [];
      }
    }
    setHolders(map);
  }, []);

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/whales/alerts?limit=30`);
      setAlerts(await res.json());
    } catch (_) {}
  }, []);

  const fetchTrending = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/whales/trending`);
      setTrending(await res.json());
    } catch (_) {}
  }, []);

  // ── Initial load + polling ──────────────────────────────────────────────

  useEffect(() => {
    fetchStatus();
    fetchTokens();
    fetchAlerts();
    fetchTrending();
  }, [fetchStatus, fetchTokens, fetchAlerts, fetchTrending]);

  // When tokens change, fetch their data
  useEffect(() => {
    if (tokens.length > 0) {
      fetchTransfers(tokens);
      fetchHolders(tokens);
    }
  }, [tokens, fetchTransfers, fetchHolders]);

  // Polling interval (15 seconds)
  useEffect(() => {
    const interval = setInterval(async () => {
      await fetchStatus();
      await fetchTokens();
      if (tokens.length > 0) {
        await fetchTransfers(tokens);
        await fetchAlerts();
      }
    }, 15_000);
    return () => clearInterval(interval);
  }, [tokens, fetchStatus, fetchTokens, fetchTransfers, fetchAlerts]);

  // ── Actions ─────────────────────────────────────────────────────────────

  const handleAddToken = async (chain, contract) => {
    try {
      const res = await fetch(`${API}/api/whales/tokens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chain, contract }),
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "Failed to add token");
        return;
      }
      setError(null);
      await fetchTokens();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleRemoveToken = async (chain, contract) => {
    try {
      await fetch(`${API}/api/whales/tokens/${chain}/${encodeURIComponent(contract)}`, { method: "DELETE" });
      await fetchTokens();
    } catch (_) {}
  };

  // ── Setup check ─────────────────────────────────────────────────────────

  const noChains = status && status.active_chains?.length === 0;

  // ── Inner tab bar ───────────────────────────────────────────────────────

  const subTabs = [["feed", "TOKEN FEED"], ["trending", "TRENDING"], ["alerts", "ALERTS"]];

  return (
    <div style={{ padding: isMobile ? 0 : 0 }}>
      <StatusBar status={status} />

      {error && (
        <div style={{
          padding: "8px 14px", marginBottom: 12, borderRadius: 10,
          background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.15)",
          fontSize: 11, color: "#fca5a5", fontFamily: T.mono,
        }}>
          {error}
        </div>
      )}

      {noChains ? (
        <SetupMessage />
      ) : (
        <>
          {/* Sub-tab bar */}
          <div style={{
            display: "flex", gap: 2, marginBottom: 16,
            background: T.glassBg, borderRadius: 12, padding: 3,
            border: `1px solid ${T.border}`,
            boxShadow: `inset 0 1px 2px ${T.shadow}`,
          }}>
            {subTabs.map(([key, label]) => (
              <button
                key={key}
                onClick={() => setSubTab(key)}
                style={{
                  padding: "7px 18px", borderRadius: 10, border: "none",
                  background: subTab === key
                    ? "linear-gradient(180deg, #2ee0f8 0%, #1ab8d4 100%)"
                    : "transparent",
                  color: subTab === key ? "#000" : T.text3,
                  fontFamily: T.mono, fontSize: 11, cursor: "pointer",
                  fontWeight: 700, letterSpacing: "0.04em",
                  transition: "all 0.2s", flex: 1,
                }}
              >
                {label}
                {key === "alerts" && alerts.length > 0 && (
                  <span style={{
                    marginLeft: 6, fontSize: 9, padding: "1px 6px", borderRadius: 10,
                    background: subTab === key ? "rgba(0,0,0,0.15)" : T.overlay10,
                    color: subTab === key ? "#000" : T.accent,
                  }}>
                    {alerts.length}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Token Feed */}
          {subTab === "feed" && (
            <>
              <AddTokenForm onAdd={handleAddToken} activeChains={status?.active_chains || []} />
              {tokens.length === 0 ? (
                <div style={{ padding: "32px 0", textAlign: "center", color: T.text4, fontSize: 12, fontFamily: T.mono }}>
                  No tokens tracked yet. Paste a contract address above to start monitoring.
                </div>
              ) : (
                tokens.map(t => (
                  <TokenCard
                    key={`${t.chain}-${t.contract}`}
                    token={t}
                    transfers={transfers[t.contract] || []}
                    holders={holders[t.contract] || []}
                    onRemove={() => handleRemoveToken(t.chain, t.contract)}
                    isMobile={isMobile}
                  />
                ))
              )}
            </>
          )}

          {/* Trending */}
          {subTab === "trending" && (
            <TrendingView
              trending={trending}
              onTrack={handleAddToken}
              isMobile={isMobile}
            />
          )}

          {/* Alerts */}
          {subTab === "alerts" && (
            <AlertsView alerts={alerts} isMobile={isMobile} />
          )}
        </>
      )}
    </div>
  );
}
