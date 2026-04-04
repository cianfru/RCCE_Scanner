import { useState, useEffect, useCallback } from "react";
import { T } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import StatusBar from "./onchain/StatusBar.jsx";
import AddTokenForm from "./onchain/AddTokenForm.jsx";
import TokenDetailView from "./onchain/TokenDetailView.jsx";
import TrendingView from "./onchain/TrendingView.jsx";
import AlertsView from "./onchain/AlertsView.jsx";
import WalletDrawer from "./onchain/WalletDrawer.jsx";
import { ChainBadge } from "./onchain/badges.jsx";
import { S, CHAIN_META } from "./onchain/styles.js";
import { useSharedWorker } from "../hooks/useSharedWorker.js";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── SETUP MESSAGE ──────────────────────────────────────────────────────────

function SetupMessage() {
  return (
    <GlassCard style={{ padding: "24px 20px", textAlign: "center" }}>
      <div style={{ fontSize: 28, marginBottom: 12 }}>{"\uD83D\uDD17"}</div>
      <div
        style={{
          fontFamily: T.font,
          fontSize: 14,
          fontWeight: 600,
          color: T.text1,
          marginBottom: 8,
        }}
      >
        On-Chain Intelligence
      </div>
      <div
        style={{
          fontFamily: T.mono,
          fontSize: 11,
          color: T.text3,
          lineHeight: 1.6,
          maxWidth: 480,
          margin: "0 auto",
        }}
      >
        Set one or more API keys as environment variables to enable on-chain tracking:
      </div>
      <div
        style={{
          marginTop: 12,
          padding: "12px 16px",
          borderRadius: 10,
          background: T.overlay06,
          border: `1px solid ${T.border}`,
          fontFamily: T.mono,
          fontSize: 11,
          color: T.accent,
          textAlign: "left",
          display: "inline-block",
          lineHeight: 1.8,
        }}
      >
        ETHERSCAN_API_KEY=your_key_here
        <br />
        BASESCAN_API_KEY=your_key_here
        <br />
        SOLSCAN_API_KEY=your_key_here
      </div>
      <div
        style={{
          fontFamily: T.mono,
          fontSize: 10,
          color: T.text4,
          marginTop: 12,
        }}
      >
        Free tiers available at etherscan.io, basescan.org, and solscan.io
      </div>
    </GlassCard>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN PANEL
// ═══════════════════════════════════════════════════════════════════════════════

export default function OnChainPanel({ isMobile }) {
  const isTablet = !isMobile && window.innerWidth < 1024;
  const sw = useSharedWorker();

  // ── State ──────────────────────────────────────────────────────────────
  const [status, setStatus] = useState(null);
  const [tokens, setTokens] = useState([]);
  const [activeSubTab, setActiveSubTab] = useState("add"); // "add" | contract | "trending" | "alerts"
  const [error, setError] = useState(null);

  // Per-token data (loaded for active token only)
  const [holdersData, setHoldersData] = useState(null);
  const [transfers, setTransfers] = useState([]);
  const [tokenAlerts, setTokenAlerts] = useState([]);

  // Global data
  const [alerts, setAlerts] = useState([]);
  const [trending, setTrending] = useState([]);

  // Wallet drawer
  const [selectedWallet, setSelectedWallet] = useState(null);
  // { chain, address, sourceToken }

  // ── Active token lookup ───────────────────────────────────────────────

  const activeToken =
    activeSubTab !== "add" &&
    activeSubTab !== "trending" &&
    activeSubTab !== "alerts"
      ? tokens.find((t) => t.contract === activeSubTab)
      : null;

  // ── SharedWorker integration ──────────────────────────────────────────

  // Forward active token to worker
  useEffect(() => {
    if (!sw.supported) return;
    if (activeToken) {
      sw.setOnchainToken({ chain: activeToken.chain, contract: activeToken.contract });
    } else {
      sw.setOnchainToken(null);
    }
  }, [sw.supported, sw.setOnchainToken, activeToken?.chain, activeToken?.contract]);

  // Apply worker onchain-data updates
  useEffect(() => {
    if (!sw.supported || !sw.onchainData) return;
    const d = sw.onchainData;
    if (d.status) setStatus(d.status);
    if (Array.isArray(d.tokens)) setTokens(d.tokens);
    if (Array.isArray(d.alerts)) setAlerts(d.alerts);
    if (Array.isArray(d.trending)) setTrending(d.trending);
    // Only apply per-token data if it matches the current active token
    if (activeToken && d.activeContract === activeToken.contract) {
      if (d.holdersData) setHoldersData(d.holdersData);
      if (Array.isArray(d.transfers)) setTransfers(d.transfers);
      if (Array.isArray(d.tokenAlerts)) setTokenAlerts(d.tokenAlerts);
    }
  }, [sw.supported, sw.onchainData, activeToken?.contract]);

  // ── Fallback fetch helpers (when SharedWorker unavailable) ────────────

  const fetchStatus = useCallback(async () => {
    if (sw.supported) return;
    try {
      const res = await fetch(`${API}/api/whales/status`);
      setStatus(await res.json());
    } catch (e) {
      setError(e.message);
    }
  }, [sw.supported]);

  const fetchTokens = useCallback(async () => {
    if (sw.supported) return;
    try {
      const res = await fetch(`${API}/api/whales/tokens`);
      setTokens(await res.json());
    } catch (_) {}
  }, [sw.supported]);

  const fetchTokenData = useCallback(async (token) => {
    if (sw.supported) return;
    if (!token) return;
    try {
      const [holdersRes, transfersRes, alertsRes] = await Promise.all([
        fetch(
          `${API}/api/whales/holders/${token.chain}/${encodeURIComponent(
            token.contract
          )}?min_pct=0.4&limit=50`
        ),
        fetch(
          `${API}/api/whales/transfers?chain=${
            token.chain
          }&contract=${encodeURIComponent(token.contract)}&limit=50`
        ),
        fetch(
          `${API}/api/whales/alerts?contract=${encodeURIComponent(
            token.contract
          )}&limit=20`
        ),
      ]);
      setHoldersData(await holdersRes.json());
      setTransfers(await transfersRes.json());
      setTokenAlerts(await alertsRes.json());
    } catch (_) {}
  }, [sw.supported]);

  const fetchAlerts = useCallback(async () => {
    if (sw.supported) return;
    try {
      const res = await fetch(`${API}/api/whales/alerts?limit=30`);
      setAlerts(await res.json());
    } catch (_) {}
  }, [sw.supported]);

  const fetchTrending = useCallback(async () => {
    if (sw.supported) return;
    try {
      const res = await fetch(`${API}/api/whales/trending`);
      setTrending(await res.json());
    } catch (_) {}
  }, [sw.supported]);

  // ── Initial load (fallback only) ─────────────────────────────────────

  useEffect(() => {
    if (sw.supported) return;
    fetchStatus();
    fetchTokens();
    fetchAlerts();
    fetchTrending();
  }, [sw.supported, fetchStatus, fetchTokens, fetchAlerts, fetchTrending]);

  // When tokens loaded and no active sub-tab, select first token
  useEffect(() => {
    if (tokens.length > 0 && activeSubTab === "add") {
      setActiveSubTab(tokens[0].contract);
    }
  }, [tokens]);

  // When active token changes, fetch its data (fallback only)
  useEffect(() => {
    if (sw.supported) return;
    if (activeToken) {
      fetchTokenData(activeToken);
    } else {
      setHoldersData(null);
      setTransfers([]);
      setTokenAlerts([]);
    }
  }, [sw.supported, activeToken?.contract, fetchTokenData]);

  // Fallback polling (15s) — only runs when SharedWorker unavailable
  useEffect(() => {
    if (sw.supported) return;
    const interval = setInterval(async () => {
      await fetchStatus();
      if (activeToken) {
        await fetchTokenData(activeToken);
      }
      await fetchAlerts();
    }, 15_000);
    return () => clearInterval(interval);
  }, [sw.supported, activeToken?.contract, fetchStatus, fetchTokenData, fetchAlerts]);

  // ── Actions ────────────────────────────────────────────────────────────

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
      const newToken = await res.json();
      await fetchTokens();
      // Auto-navigate to new token
      setActiveSubTab(newToken.contract || contract);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleRemoveToken = async (chain, contract) => {
    try {
      await fetch(
        `${API}/api/whales/tokens/${chain}/${encodeURIComponent(contract)}`,
        { method: "DELETE" }
      );
      await fetchTokens();
      setActiveSubTab("add");
    } catch (_) {}
  };

  const handleRefreshSupply = async () => {
    if (!activeToken) return;
    try {
      await fetch(
        `${API}/api/whales/tokens/${activeToken.chain}/${encodeURIComponent(
          activeToken.contract
        )}/refresh-supply`,
        { method: "POST" }
      );
      await fetchTokens();
      await fetchTokenData(activeToken);
    } catch (_) {}
  };

  const handleSelectWallet = (chain, address) => {
    setSelectedWallet({
      chain,
      address,
      sourceToken: activeToken?.contract || null,
    });
  };

  const handleNavigateToken = (contract) => {
    // Navigate to a token tab (if tracked)
    const found = tokens.find((t) => t.contract === contract);
    if (found) {
      setActiveSubTab(contract);
    }
  };

  // ── Setup check ────────────────────────────────────────────────────────

  const noChains = status && status.active_chains?.length === 0;

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div>
      <StatusBar status={status} />

      {error && (
        <div
          style={{
            padding: "8px 14px",
            marginBottom: 12,
            borderRadius: 10,
            background: "rgba(248,113,113,0.08)",
            border: "1px solid rgba(248,113,113,0.15)",
            fontSize: 11,
            color: "#fca5a5",
            fontFamily: T.mono,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>{error}</span>
          <span
            onClick={() => setError(null)}
            style={{ cursor: "pointer", opacity: 0.6 }}
          >
            {"\u2715"}
          </span>
        </div>
      )}

      {noChains ? (
        <SetupMessage />
      ) : (
        <>
          {/* Sub-tab bar */}
          <div
            style={{
              display: "flex",
              gap: 2,
              marginBottom: 16,
              background: T.glassBg,
              borderRadius: 12,
              padding: 3,
              border: `1px solid ${T.border}`,
              boxShadow: `inset 0 1px 2px ${T.shadow}`,
              overflowX: "auto",
              scrollbarWidth: "none",
            }}
          >
            {/* + Add button */}
            <button
              onClick={() => setActiveSubTab("add")}
              style={{
                padding: "7px 12px",
                borderRadius: 10,
                border: "none",
                background:
                  activeSubTab === "add"
                    ? "linear-gradient(180deg, #2ee0f8 0%, #1ab8d4 100%)"
                    : "transparent",
                color: activeSubTab === "add" ? "#000" : T.text3,
                fontFamily: T.mono,
                fontSize: 13,
                cursor: "pointer",
                fontWeight: 700,
                flexShrink: 0,
              }}
            >
              +
            </button>

            {/* Token tabs */}
            {tokens.map((t) => {
              const isActive = activeSubTab === t.contract;
              const meta = CHAIN_META[t.chain] || {};
              return (
                <button
                  key={`${t.chain}-${t.contract}`}
                  onClick={() => setActiveSubTab(t.contract)}
                  style={{
                    padding: "7px 14px",
                    borderRadius: 10,
                    border: "none",
                    background: isActive
                      ? "linear-gradient(180deg, #2ee0f8 0%, #1ab8d4 100%)"
                      : "transparent",
                    color: isActive ? "#000" : T.text3,
                    fontFamily: T.mono,
                    fontSize: 11,
                    cursor: "pointer",
                    fontWeight: 700,
                    letterSpacing: "0.04em",
                    transition: "all 0.2s",
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                    flexShrink: 0,
                    whiteSpace: "nowrap",
                  }}
                >
                  <span
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      background: isActive ? "#000" : meta.color || T.text4,
                      flexShrink: 0,
                    }}
                  />
                  {t.symbol || "???"}
                </button>
              );
            })}

            {/* Separator */}
            {tokens.length > 0 && (
              <div
                style={{
                  width: 1,
                  background: T.border,
                  margin: "4px 2px",
                  flexShrink: 0,
                }}
              />
            )}

            {/* Trending tab */}
            <button
              onClick={() => setActiveSubTab("trending")}
              style={{
                padding: "7px 14px",
                borderRadius: 10,
                border: "none",
                background:
                  activeSubTab === "trending"
                    ? "linear-gradient(180deg, #2ee0f8 0%, #1ab8d4 100%)"
                    : "transparent",
                color: activeSubTab === "trending" ? "#000" : T.text3,
                fontFamily: T.mono,
                fontSize: 11,
                cursor: "pointer",
                fontWeight: 700,
                letterSpacing: "0.04em",
                flexShrink: 0,
              }}
            >
              TRENDING
            </button>

            {/* Alerts tab */}
            <button
              onClick={() => setActiveSubTab("alerts")}
              style={{
                padding: "7px 14px",
                borderRadius: 10,
                border: "none",
                background:
                  activeSubTab === "alerts"
                    ? "linear-gradient(180deg, #2ee0f8 0%, #1ab8d4 100%)"
                    : "transparent",
                color: activeSubTab === "alerts" ? "#000" : T.text3,
                fontFamily: T.mono,
                fontSize: 11,
                cursor: "pointer",
                fontWeight: 700,
                letterSpacing: "0.04em",
                flexShrink: 0,
              }}
            >
              ALERTS
              {alerts.length > 0 && (
                <span
                  style={{
                    marginLeft: 6,
                    fontSize: 9,
                    padding: "1px 6px",
                    borderRadius: 10,
                    background:
                      activeSubTab === "alerts"
                        ? "rgba(0,0,0,0.15)"
                        : T.overlay10,
                    color: activeSubTab === "alerts" ? "#000" : T.accent,
                  }}
                >
                  {alerts.length}
                </span>
              )}
            </button>
          </div>

          {/* Content */}
          {activeSubTab === "add" && (
            <>
              <AddTokenForm onAdd={handleAddToken} />
              {tokens.length === 0 && (
                <div
                  style={{
                    padding: "32px 0",
                    textAlign: "center",
                    color: T.text4,
                    fontSize: 12,
                    fontFamily: T.mono,
                  }}
                >
                  Paste a token contract address above to start monitoring
                  on-chain activity.
                </div>
              )}
            </>
          )}

          {activeToken && (
            <TokenDetailView
              token={activeToken}
              holdersData={holdersData}
              transfers={transfers}
              alerts={tokenAlerts}
              isMobile={isMobile}
              onRemove={() =>
                handleRemoveToken(activeToken.chain, activeToken.contract)
              }
              onSelectWallet={handleSelectWallet}
              onRefreshSupply={handleRefreshSupply}
            />
          )}

          {activeSubTab === "trending" && (
            <TrendingView trending={trending} onTrack={handleAddToken} />
          )}

          {activeSubTab === "alerts" && (
            <AlertsView
              alerts={alerts}
              onSelectWallet={handleSelectWallet}
              onNavigateToken={handleNavigateToken}
            />
          )}
        </>
      )}

      {/* Wallet Drill-Down Drawer */}
      {selectedWallet && (
        <WalletDrawer
          chain={selectedWallet.chain}
          address={selectedWallet.address}
          sourceToken={selectedWallet.sourceToken}
          isMobile={isMobile}
          isTablet={isTablet}
          onClose={() => setSelectedWallet(null)}
          onNavigateToken={(contract) => {
            setActiveSubTab(contract);
            setSelectedWallet(null);
          }}
        />
      )}
    </div>
  );
}
