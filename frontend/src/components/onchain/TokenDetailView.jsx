import { useState, useMemo } from "react";
import { T } from "../../theme.js";
import { S } from "./styles.js";
import GlassCard from "../GlassCard.jsx";
import {
  ChainBadge,
  DirectionBadge,
  ActivityBadge,
  ClickableAddr,
} from "./badges.jsx";
import {
  fmtTokenVal,
  fmtUsd,
  fmtTime,
  fmtPct,
  fmtSupply,
  truncAddr,
} from "./helpers.js";

// ─── SORT HELPERS ─────────────────────────────────────────────────────────────

const SORT_KEYS = {
  pct_supply: (h) => h.pct_supply,
  balance: (h) => Math.abs(h.balance),
  net_flow_24h: (h) => h.net_flow_24h,
  tx_count_24h: (h) => h.tx_count_24h,
};

function classifyActivity(h) {
  const total = h.buy_count + h.sell_count;
  if (total === 0) return "INACTIVE";
  if (h.buy_count > 0 && h.sell_count === 0) return "ACCUMULATING";
  if (h.sell_count > 0 && h.buy_count === 0) return "DISTRIBUTING";
  if (h.buy_count > h.sell_count * 1.5 && h.net_flow > 0) return "ACCUMULATING";
  if (h.sell_count > h.buy_count * 1.5 && h.net_flow < 0) return "DISTRIBUTING";
  return "MIXED";
}

// ─── COMPONENT ────────────────────────────────────────────────────────────────

export default function TokenDetailView({
  token,
  holdersData,
  transfers,
  alerts,
  isMobile,
  onRemove,
  onSelectWallet,
  onRefreshSupply,
}) {
  const [sortKey, setSortKey] = useState("pct_supply");
  const [sortDesc, setSortDesc] = useState(true);

  const holders = holdersData?.holders || [];
  const totalSupply = holdersData?.total_supply || 0;
  const thresholdPct = holdersData?.whale_threshold_pct || 0.4;

  // Sort holders
  const sortedHolders = useMemo(() => {
    const fn = SORT_KEYS[sortKey] || SORT_KEYS.pct_supply;
    return [...holders].sort((a, b) => {
      const va = fn(a);
      const vb = fn(b);
      return sortDesc ? vb - va : va - vb;
    });
  }, [holders, sortKey, sortDesc]);

  // Whale addresses set (for filtering transfers)
  const whaleAddrs = useMemo(
    () => new Set(holders.map((h) => h.address)),
    [holders]
  );

  // Whale-only transfers
  const whaleTransfers = useMemo(
    () =>
      (transfers || []).filter(
        (t) => whaleAddrs.has(t.from_addr) || whaleAddrs.has(t.to_addr)
      ),
    [transfers, whaleAddrs]
  );

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDesc(!sortDesc);
    } else {
      setSortKey(key);
      setSortDesc(true);
    }
  };

  const sortIcon = (key) =>
    sortKey === key ? (sortDesc ? " \u25BC" : " \u25B2") : "";

  return (
    <div>
      {/* Header */}
      <GlassCard style={{ marginBottom: 12, padding: "12px 16px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
          }}
        >
          <ChainBadge chain={token.chain} />
          <span
            style={{
              fontFamily: T.mono,
              fontSize: 16,
              fontWeight: 700,
              color: T.text1,
            }}
          >
            {token.symbol || "Unknown"}
          </span>
          <span style={{ fontSize: 11, color: T.text4, fontFamily: T.mono }}>
            {token.name}
          </span>
          <span
            style={{
              fontSize: 9,
              color: T.text4,
              fontFamily: T.mono,
              opacity: 0.6,
            }}
          >
            {truncAddr(token.contract)}
          </span>
          <button
            onClick={onRemove}
            style={{ ...S.btnDanger, marginLeft: "auto" }}
          >
            Remove
          </button>
        </div>

        {/* Supply info */}
        <div
          style={{
            display: "flex",
            gap: 16,
            marginTop: 8,
            flexWrap: "wrap",
            fontSize: 10,
            fontFamily: T.mono,
            color: T.text3,
          }}
        >
          {totalSupply > 0 ? (
            <>
              <span>
                Supply:{" "}
                <span style={{ color: T.text2, fontWeight: 600 }}>
                  {fmtSupply(totalSupply)}
                </span>
              </span>
              <span>
                Whale threshold:{" "}
                <span style={{ color: T.accent, fontWeight: 600 }}>
                  {"\u2265"} {thresholdPct}% (
                  {fmtTokenVal(totalSupply * (thresholdPct / 100))})
                </span>
              </span>
              <span>
                Whales found:{" "}
                <span style={{ color: T.text1, fontWeight: 600 }}>
                  {holders.length}
                </span>
              </span>
            </>
          ) : (
            <span style={{ color: "#fbbf24" }}>
              Supply data unavailable.{" "}
              <span
                onClick={onRefreshSupply}
                style={{
                  color: T.accent,
                  cursor: "pointer",
                  textDecoration: "underline",
                }}
              >
                Retry fetch
              </span>
            </span>
          )}
        </div>
      </GlassCard>

      {/* Whale Holders Table */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ ...S.label, marginBottom: 6 }}>
          WHALE HOLDERS {totalSupply > 0 ? `(\u2265 ${thresholdPct}% SUPPLY)` : ""}
        </div>

        {sortedHolders.length === 0 ? (
          <div
            style={{
              padding: "20px 0",
              textAlign: "center",
              color: T.text4,
              fontSize: 11,
              fontFamily: T.mono,
            }}
          >
            {totalSupply > 0
              ? `No wallets hold \u2265 ${thresholdPct}% of supply yet.`
              : "Waiting for holder data..."}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={S.th}>#</th>
                  <th style={S.th}>ADDRESS</th>
                  <th
                    style={{ ...S.th, cursor: "pointer" }}
                    onClick={() => handleSort("balance")}
                  >
                    BALANCE{sortIcon("balance")}
                  </th>
                  {!isMobile && (
                    <th
                      style={{ ...S.th, cursor: "pointer" }}
                      onClick={() => handleSort("pct_supply")}
                    >
                      % SUPPLY{sortIcon("pct_supply")}
                    </th>
                  )}
                  <th
                    style={{ ...S.th, cursor: "pointer" }}
                    onClick={() => handleSort("net_flow_24h")}
                  >
                    24H FLOW{sortIcon("net_flow_24h")}
                  </th>
                  <th style={S.th}>ACTIVITY</th>
                  {!isMobile && (
                    <th
                      style={{ ...S.th, cursor: "pointer" }}
                      onClick={() => handleSort("tx_count_24h")}
                    >
                      TXN{sortIcon("tx_count_24h")}
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {sortedHolders.map((h, i) => {
                  const activity = classifyActivity(h);
                  return (
                    <tr
                      key={h.address}
                      style={{
                        borderBottom: `1px solid ${T.border}`,
                        background: i % 2 === 0 ? "transparent" : T.overlay02,
                      }}
                    >
                      <td style={{ ...S.td, color: T.text4 }}>{i + 1}</td>
                      <td style={S.td}>
                        <ClickableAddr
                          addr={h.address}
                          label={h.label}
                          chain={token.chain}
                          onClick={onSelectWallet}
                        />
                      </td>
                      <td style={{ ...S.td, color: T.text2 }}>
                        {fmtTokenVal(h.balance)}
                        {h.balance_usd > 0 && (
                          <span
                            style={{
                              color: T.text4,
                              fontSize: 9,
                              marginLeft: 4,
                            }}
                          >
                            ({fmtUsd(h.balance_usd)})
                          </span>
                        )}
                      </td>
                      {!isMobile && (
                        <td
                          style={{
                            ...S.td,
                            color:
                              h.pct_supply >= 2
                                ? "#fbbf24"
                                : h.pct_supply >= 1
                                ? T.accent
                                : T.text2,
                            fontWeight: h.pct_supply >= 1 ? 700 : 400,
                          }}
                        >
                          {h.pct_supply > 0 ? fmtPct(h.pct_supply) : "\u2014"}
                        </td>
                      )}
                      <td
                        style={{
                          ...S.td,
                          color:
                            h.net_flow_24h > 0
                              ? "#34d399"
                              : h.net_flow_24h < 0
                              ? "#f87171"
                              : T.text4,
                          fontWeight: h.net_flow_24h !== 0 ? 600 : 400,
                        }}
                      >
                        {h.net_flow_24h > 0 ? "+" : ""}
                        {fmtTokenVal(h.net_flow_24h)}
                      </td>
                      <td style={S.td}>
                        <ActivityBadge activity={activity} />
                      </td>
                      {!isMobile && (
                        <td style={{ ...S.td, color: T.text4 }}>
                          {h.tx_count_24h}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Whale Transfers */}
      {whaleTransfers.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ ...S.label, marginBottom: 6 }}>
            WHALE TRANSFERS ({whaleTransfers.length})
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={S.th}>TIME</th>
                  {!isMobile && <th style={S.th}>FROM</th>}
                  {!isMobile && <th style={S.th}>TO</th>}
                  {isMobile && (
                    <th style={S.th}>FROM {"\u2192"} TO</th>
                  )}
                  <th style={S.th}>AMOUNT</th>
                  <th style={S.th}>USD</th>
                  <th style={S.th}>TYPE</th>
                </tr>
              </thead>
              <tbody>
                {whaleTransfers.slice(0, 25).map((tx, i) => (
                  <tr
                    key={tx.tx_hash + i}
                    style={{
                      borderBottom: `1px solid ${T.border}`,
                      background: i % 2 === 0 ? "transparent" : T.overlay02,
                    }}
                  >
                    <td style={{ ...S.td, color: T.text4 }}>
                      {fmtTime(tx.timestamp)}
                    </td>
                    {!isMobile && (
                      <td style={S.td}>
                        <ClickableAddr
                          addr={tx.from_addr}
                          label={tx.from_label}
                          chain={token.chain}
                          onClick={onSelectWallet}
                        />
                      </td>
                    )}
                    {!isMobile && (
                      <td style={S.td}>
                        <ClickableAddr
                          addr={tx.to_addr}
                          label={tx.to_label}
                          chain={token.chain}
                          onClick={onSelectWallet}
                        />
                      </td>
                    )}
                    {isMobile && (
                      <td style={S.td}>
                        <ClickableAddr
                          addr={tx.from_addr}
                          label={tx.from_label}
                          chain={token.chain}
                          onClick={onSelectWallet}
                        />
                        <span style={{ color: T.text4, margin: "0 4px" }}>
                          {"\u2192"}
                        </span>
                        <ClickableAddr
                          addr={tx.to_addr}
                          label={tx.to_label}
                          chain={token.chain}
                          onClick={onSelectWallet}
                        />
                      </td>
                    )}
                    <td style={{ ...S.td, color: T.text2 }}>
                      {fmtTokenVal(tx.value)}
                    </td>
                    <td
                      style={{
                        ...S.td,
                        color:
                          tx.value_usd >= 50000 ? "#fbbf24" : T.text3,
                        fontWeight: tx.value_usd >= 50000 ? 700 : 400,
                      }}
                    >
                      {tx.value_usd > 0 ? fmtUsd(tx.value_usd) : "\u2014"}
                    </td>
                    <td style={S.td}>
                      <DirectionBadge direction={tx.direction} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Token-specific Alerts */}
      {alerts && alerts.length > 0 && (
        <div>
          <div style={{ ...S.label, marginBottom: 6 }}>
            TOKEN ALERTS ({alerts.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {alerts.map((a, i) => (
              <div
                key={`${a.address}-${a.timestamp}-${i}`}
                style={{
                  padding: "8px 12px",
                  borderRadius: 8,
                  background: T.overlay04,
                  border: `1px solid ${T.border}`,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  flexWrap: "wrap",
                }}
              >
                <ActivityBadge activity={a.alert_type} />
                <ClickableAddr
                  addr={a.address}
                  label={a.label}
                  chain={token.chain}
                  onClick={onSelectWallet}
                />
                {a.value_usd > 0 && (
                  <span
                    style={{
                      fontFamily: T.mono,
                      fontSize: 10,
                      color: "#fbbf24",
                      fontWeight: 600,
                    }}
                  >
                    {fmtUsd(a.value_usd)}
                  </span>
                )}
                <span
                  style={{
                    fontSize: 9,
                    color: T.text4,
                    fontFamily: T.mono,
                    marginLeft: "auto",
                  }}
                >
                  {a.details}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
