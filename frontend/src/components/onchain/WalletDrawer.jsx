import { useState, useEffect, useCallback } from "react";
import { T } from "../../theme.js";
import { S, CHAIN_META } from "./styles.js";
import {
  ChainBadge,
  DirectionBadge,
  ActivityBadge,
} from "./badges.jsx";
import {
  truncAddr,
  fmtUsd,
  fmtTime,
  fmtTimeAgo,
  fmtTokenVal,
  fmtPct,
} from "./helpers.js";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function WalletDrawer({
  chain,
  address,
  sourceToken,
  isMobile,
  isTablet,
  onClose,
  onNavigateToken,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [labelEdit, setLabelEdit] = useState(false);
  const [labelVal, setLabelVal] = useState("");
  const [copied, setCopied] = useState(false);

  // ── Fetch wallet activity ─────────────────────────────────────────────

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `${API}/api/whales/wallet/${chain}/${encodeURIComponent(address)}?limit=50`
      );
      const json = await res.json();
      setData(json);
      setLabelVal(json.label || "");
    } catch (_) {
    } finally {
      setLoading(false);
    }
  }, [chain, address]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ── Actions ────────────────────────────────────────────────────────────

  const handleCopy = () => {
    navigator.clipboard.writeText(address);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleSaveLabel = async () => {
    try {
      await fetch(`${API}/api/whales/wallet/label`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chain, address, label: labelVal }),
      });
      setLabelEdit(false);
      fetchData();
    } catch (_) {}
  };

  // ── Derived data ──────────────────────────────────────────────────────

  const sourceActivity = data?.token_activity?.find(
    (t) => t.contract === sourceToken
  );
  const otherTokens = data?.token_activity?.filter(
    (t) => t.contract !== sourceToken
  ) || [];

  const explorerBase = CHAIN_META[chain]?.explorer || "";
  const explorerUrl = chain === "solana"
    ? `${explorerBase}/account/${address}`
    : `${explorerBase}/address/${address}`;

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <>
      {/* Backdrop (mobile) */}
      {isMobile && (
        <div
          onClick={onClose}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 199,
            background: T.shadowDeep,
          }}
        />
      )}

      <div
        style={{
          position: "fixed",
          right: 0,
          top: 0,
          bottom: 0,
          left: isMobile ? 0 : undefined,
          width: isMobile ? "100%" : isTablet ? 400 : 520,
          background: T.drawerBg,
          backdropFilter: "blur(32px) saturate(1.4)",
          WebkitBackdropFilter: "blur(32px) saturate(1.4)",
          borderLeft: isMobile ? "none" : `1px solid ${T.border}`,
          padding: isMobile ? "20px 16px" : "24px 22px",
          overflowY: "auto",
          zIndex: 200,
          transition: "transform 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94)",
          boxShadow: isMobile ? "none" : `-8px 0 40px ${T.shadowDeep}`,
        }}
      >
        {/* Mobile drag handle */}
        {isMobile && (
          <div
            style={{
              width: 36,
              height: 4,
              borderRadius: 2,
              background: T.overlay15,
              margin: "0 auto 16px auto",
            }}
          />
        )}

        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            marginBottom: 16,
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 4,
              }}
            >
              <ChainBadge chain={chain} />
              <span
                style={{
                  fontSize: 10,
                  color: T.text4,
                  fontFamily: T.mono,
                  letterSpacing: "0.04em",
                }}
              >
                WALLET
              </span>
            </div>
            <div
              style={{
                fontSize: isMobile ? 11 : 12,
                fontFamily: T.mono,
                color: T.text1,
                wordBreak: "break-all",
                lineHeight: 1.4,
              }}
            >
              {address}
            </div>

            {/* Label */}
            <div
              style={{
                marginTop: 6,
                display: "flex",
                alignItems: "center",
                gap: 6,
              }}
            >
              {labelEdit ? (
                <>
                  <input
                    value={labelVal}
                    onChange={(e) => setLabelVal(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSaveLabel()}
                    autoFocus
                    placeholder="Enter label..."
                    style={{ ...S.input, flex: "none", width: 160, fontSize: 11 }}
                  />
                  <button
                    onClick={handleSaveLabel}
                    style={{ ...S.btn, padding: "4px 10px", fontSize: 10 }}
                  >
                    Save
                  </button>
                  <button
                    onClick={() => setLabelEdit(false)}
                    style={{ ...S.btnDanger, padding: "4px 8px" }}
                  >
                    {"\u2715"}
                  </button>
                </>
              ) : (
                <>
                  {data?.label ? (
                    <span
                      style={{
                        fontSize: 12,
                        color: T.accent,
                        fontFamily: T.mono,
                        fontWeight: 600,
                      }}
                    >
                      {data.label}
                    </span>
                  ) : null}
                  <span
                    onClick={() => setLabelEdit(true)}
                    style={{
                      fontSize: 9,
                      color: T.text4,
                      fontFamily: T.mono,
                      cursor: "pointer",
                      textDecoration: "underline",
                    }}
                  >
                    {data?.label ? "edit" : "+ add label"}
                  </span>
                </>
              )}
            </div>

            {/* Copy + Explorer */}
            <div
              style={{
                marginTop: 8,
                display: "flex",
                gap: 8,
                alignItems: "center",
              }}
            >
              <span
                onClick={handleCopy}
                style={{
                  fontSize: 9,
                  color: copied ? "#34d399" : T.text4,
                  fontFamily: T.mono,
                  cursor: "pointer",
                }}
              >
                {copied ? "Copied!" : "Copy address"}
              </span>
              {explorerBase && (
                <a
                  href={explorerUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    fontSize: 9,
                    color: T.accent,
                    fontFamily: T.mono,
                    textDecoration: "none",
                  }}
                >
                  View on Explorer {"\u2197"}
                </a>
              )}
            </div>
          </div>

          <button
            onClick={onClose}
            className="apple-btn"
            style={{
              borderRadius: "50%",
              padding: 0,
              width: isMobile ? 36 : 28,
              height: isMobile ? 36 : 28,
              fontSize: isMobile ? 14 : 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            {"\u2715"}
          </button>
        </div>

        {loading ? (
          <div
            style={{
              textAlign: "center",
              padding: "40px 0",
              color: T.text4,
              fontFamily: T.mono,
              fontSize: 11,
            }}
          >
            Loading wallet data...
          </div>
        ) : (
          <>
            {/* ── Section 1: This Token ────────────────────────────── */}
            {sourceActivity && (
              <div
                style={{
                  marginBottom: 16,
                  padding: "12px 14px",
                  borderRadius: 10,
                  background: T.surface || T.overlay06,
                  border: `1px solid ${T.border}`,
                }}
              >
                <div
                  style={{
                    ...S.label,
                    marginBottom: 8,
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  THIS TOKEN
                  <span style={{ color: T.text1, fontWeight: 700, fontSize: 11 }}>
                    {sourceActivity.symbol}
                  </span>
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: "8px 16px",
                  }}
                >
                  <MetricRow
                    label="Balance"
                    value={fmtTokenVal(sourceActivity.balance)}
                  />
                  <MetricRow
                    label="% Supply"
                    value={
                      sourceActivity.pct_supply > 0
                        ? fmtPct(sourceActivity.pct_supply)
                        : "\u2014"
                    }
                    color={
                      sourceActivity.pct_supply >= 1 ? T.accent : undefined
                    }
                  />
                  <MetricRow
                    label="24H Flow"
                    value={`${sourceActivity.net_flow_24h > 0 ? "+" : ""}${fmtTokenVal(sourceActivity.net_flow_24h)}`}
                    color={
                      sourceActivity.net_flow_24h > 0
                        ? "#34d399"
                        : sourceActivity.net_flow_24h < 0
                        ? "#f87171"
                        : undefined
                    }
                  />
                  <MetricRow
                    label="Buys / Sells"
                    value={`${sourceActivity.buy_count} / ${sourceActivity.sell_count}`}
                  />
                </div>
                <div style={{ marginTop: 8 }}>
                  <ActivityBadge activity={sourceActivity.activity} />
                </div>
              </div>
            )}

            {/* ── Section 2: Cross-Token Holdings ─────────────────── */}
            {otherTokens.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ ...S.label, marginBottom: 6 }}>
                  CROSS-TOKEN HOLDINGS ({otherTokens.length})
                </div>
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                  }}
                >
                  {otherTokens.map((t) => (
                    <div
                      key={t.contract}
                      onClick={() => onNavigateToken(t.contract)}
                      style={{
                        padding: "10px 12px",
                        borderRadius: 8,
                        background: T.overlay04,
                        border: `1px solid ${T.border}`,
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        flexWrap: "wrap",
                        transition: "background 0.15s",
                      }}
                      onMouseEnter={(e) =>
                        (e.currentTarget.style.background = T.overlay06)
                      }
                      onMouseLeave={(e) =>
                        (e.currentTarget.style.background = T.overlay04)
                      }
                    >
                      <ChainBadge chain={t.chain} small />
                      <span
                        style={{
                          fontFamily: T.mono,
                          fontSize: 12,
                          fontWeight: 700,
                          color: T.text1,
                        }}
                      >
                        {t.symbol}
                      </span>
                      <span
                        style={{
                          fontFamily: T.mono,
                          fontSize: 10,
                          color: T.text3,
                        }}
                      >
                        {fmtTokenVal(t.balance)}
                      </span>
                      {t.pct_supply > 0 && (
                        <span
                          style={{
                            fontFamily: T.mono,
                            fontSize: 10,
                            color: T.accent,
                            fontWeight: 600,
                          }}
                        >
                          {fmtPct(t.pct_supply)}
                        </span>
                      )}
                      <div
                        style={{
                          marginLeft: "auto",
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        <ActivityBadge activity={t.activity} />
                        <span
                          style={{
                            fontSize: 9,
                            color: T.text4,
                            fontFamily: T.mono,
                          }}
                        >
                          {fmtTimeAgo(t.last_seen)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── Section 3: Recent Transactions ──────────────────── */}
            {data?.recent_transfers?.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ ...S.label, marginBottom: 6 }}>
                  RECENT TRANSACTIONS ({data.recent_transfers.length})
                </div>
                <div style={{ overflowX: "auto" }}>
                  <table
                    style={{ width: "100%", borderCollapse: "collapse" }}
                  >
                    <thead>
                      <tr>
                        <th style={S.th}>TIME</th>
                        <th style={S.th}>TOKEN</th>
                        <th style={S.th}>TYPE</th>
                        <th style={S.th}>AMOUNT</th>
                        {!isMobile && <th style={S.th}>USD</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent_transfers.slice(0, 30).map((tx, i) => (
                        <tr
                          key={tx.tx_hash + i}
                          style={{
                            borderBottom: `1px solid ${T.border}`,
                            background:
                              i % 2 === 0 ? "transparent" : T.overlay02,
                          }}
                        >
                          <td style={{ ...S.td, color: T.text4, fontSize: 10 }}>
                            {fmtTimeAgo(tx.timestamp)}
                          </td>
                          <td
                            style={{
                              ...S.td,
                              color: T.text2,
                              fontWeight: 600,
                            }}
                          >
                            {tx.token_symbol}
                          </td>
                          <td style={S.td}>
                            <DirectionBadge direction={tx.direction} />
                          </td>
                          <td style={{ ...S.td, color: T.text2 }}>
                            {fmtTokenVal(tx.value)}
                          </td>
                          {!isMobile && (
                            <td style={{ ...S.td, color: T.text3 }}>
                              {tx.value_usd > 0
                                ? fmtUsd(tx.value_usd)
                                : "\u2014"}
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* No activity found */}
            {(!data?.token_activity || data.token_activity.length === 0) &&
              (!data?.recent_transfers ||
                data.recent_transfers.length === 0) && (
                <div
                  style={{
                    textAlign: "center",
                    padding: "24px 0",
                    color: T.text4,
                    fontFamily: T.mono,
                    fontSize: 11,
                  }}
                >
                  No tracked token activity found for this wallet.
                </div>
              )}
          </>
        )}
      </div>
    </>
  );
}

// ─── METRIC ROW ────────────────────────────────────────────────────────────

function MetricRow({ label, value, color }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}
    >
      <span
        style={{
          fontSize: 10,
          color: T.text4,
          fontFamily: T.mono,
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontSize: 11,
          color: color || T.text1,
          fontFamily: T.mono,
          fontWeight: 600,
        }}
      >
        {value}
      </span>
    </div>
  );
}
