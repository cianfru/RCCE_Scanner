import { useState, useMemo } from "react";
import { T } from "../../theme.js";
import { S } from "./styles.js";
import GlassCard from "../GlassCard.jsx";
import {
  ChainBadge,
  DirectionBadge,
  ActivityBadge,
  AddressTypeBadge,
  ClickableAddr,
} from "./badges.jsx";
import {
  fmtTokenVal,
  fmtUsd,
  fmtTime,
  fmtPct,
  fmtSupply,
  fmtChange,
  fmtChangePct,
  truncAddr,
} from "./helpers.js";

// ─── SORT HELPERS ─────────────────────────────────────────────────────────────

const SORT_KEYS = {
  pct_supply: (h) => h.pct_supply,
  balance: (h) => Math.abs(h.balance),
  net_flow_24h: (h) => h.net_flow_24h,
  tx_count_24h: (h) => h.tx_count_24h,
  change_1d: (h) => h.change_1d ?? -Infinity,
  change_7d: (h) => h.change_7d ?? -Infinity,
  change_14d: (h) => h.change_14d ?? -Infinity,
};

// ─── CHANGE CELL ──────────────────────────────────────────────────────────────

function ChangeCell({ value, pctValue }) {
  if (value === null || value === undefined) {
    return (
      <span style={{ color: T.text4, opacity: 0.5 }}>{"\u2014"}</span>
    );
  }
  const color = value > 0 ? "#34d399" : value < 0 ? "#f87171" : T.text4;
  return (
    <span style={{ color, fontWeight: value !== 0 ? 600 : 400 }}>
      {fmtChange(value)}
      {pctValue !== null && pctValue !== undefined && (
        <span
          style={{
            fontSize: 8,
            opacity: 0.7,
            marginLeft: 3,
          }}
        >
          {fmtChangePct(pctValue)}
        </span>
      )}
    </span>
  );
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
                  {!isMobile && (
                    <th
                      style={{ ...S.th, cursor: "pointer" }}
                      onClick={() => handleSort("change_1d")}
                    >
                      1D CHG{sortIcon("change_1d")}
                    </th>
                  )}
                  <th
                    style={{ ...S.th, cursor: "pointer" }}
                    onClick={() => handleSort("change_7d")}
                  >
                    7D CHG{sortIcon("change_7d")}
                  </th>
                  {!isMobile && (
                    <th
                      style={{ ...S.th, cursor: "pointer" }}
                      onClick={() => handleSort("change_14d")}
                    >
                      14D CHG{sortIcon("change_14d")}
                    </th>
                  )}
                  <th style={S.th}>TREND</th>
                </tr>
              </thead>
              <tbody>
                {sortedHolders.map((h, i) => {
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
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                          <ClickableAddr
                            addr={h.address}
                            label={h.label}
                            chain={token.chain}
                            onClick={onSelectWallet}
                          />
                          <AddressTypeBadge type={h.address_type} />
                        </span>
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
                      {!isMobile && (
                        <td style={S.td}>
                          <ChangeCell
                            value={h.change_1d}
                            pctValue={h.change_1d_pct}
                          />
                        </td>
                      )}
                      <td style={S.td}>
                        <ChangeCell
                          value={h.change_7d}
                          pctValue={h.change_7d_pct}
                        />
                      </td>
                      {!isMobile && (
                        <td style={S.td}>
                          <ChangeCell
                            value={h.change_14d}
                            pctValue={h.change_14d_pct}
                          />
                        </td>
                      )}
                      <td style={S.td}>
                        <ActivityBadge activity={h.trend || "NEW"} />
                      </td>
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
