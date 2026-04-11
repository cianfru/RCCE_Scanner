import { useState, useEffect, useCallback } from "react";
import { T, heatColor, phaseColor, exhaustMeta, fmt, zBar, getBaseSymbol, getTVSymbol } from "../theme.js";
import { ZScoreBar, RegimeBadge, SignalDot } from "./badges.jsx";
import BMSBChart from "./BMSBChart.jsx";
import ConditionsScorecard from "./ConditionsScorecard.jsx";
import ConfluencePanel from "./ConfluencePanel.jsx";
import PositioningPanel from "./PositioningPanel.jsx";
import { useWallet } from "../WalletContext.jsx";
import * as hlClient from "../services/hlClient.js";

// ---------------------------------------------------------------------------
// Trade Form (renders at bottom of drawer — wallet-signed)
// ---------------------------------------------------------------------------

const LEVERAGE_PRESETS = [1, 2, 3, 5, 10, 20];

function TradeForm({ selected, api, isMobile }) {
  const { address, isConnected, walletClient, connect, error: walletError } = useWallet();
  const [side, setSide] = useState("LONG");
  const [sizeMode, setSizeMode] = useState("usd");
  const [sizeValue, setSizeValue] = useState("");
  const [leverage, setLeverage] = useState(3);
  const [loading, setLoading] = useState(false);
  const [loadingMsg, setLoadingMsg] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [accountData, setAccountData] = useState(null);

  const coin = getBaseSymbol(selected.symbol);

  // Fetch account data when wallet is connected
  useEffect(() => {
    if (!isConnected || !address) { setAccountData(null); return; }
    fetch(`${api}/api/trade/account?address=${address}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => setAccountData(d))
      .catch(() => {});
  }, [api, address, isConnected]);

  // Reset form when symbol changes
  useEffect(() => {
    setConfirm(false);
    setFeedback(null);
  }, [selected.symbol]);

  const parsedSize = parseFloat(sizeValue) || 0;
  const equity = accountData?.account_value || 0;
  const estimatedUsd = sizeMode === "usd" ? parsedSize : equity * parsedSize / 100;
  const estimatedMargin = leverage > 0 ? estimatedUsd / leverage : estimatedUsd;
  const canTrade = isConnected && estimatedUsd >= 5 && !loading;

  const handleExecute = async () => {
    if (!confirm) { setConfirm(true); return; }
    if (!walletClient) { setFeedback({ ok: false, msg: "Wallet not connected" }); return; }
    setLoading(true);
    setFeedback(null);

    try {
      // 1. Set leverage (wallet popup — skipped if cached)
      setLoadingMsg("Setting leverage...");
      await hlClient.setLeverage(walletClient, { coin, leverage, isCross: true });

      // 2. Place market order (wallet popup)
      setLoadingMsg("Awaiting signature...");
      const isBuy = side === "LONG";
      const result = await hlClient.placeMarketOrder(walletClient, {
        coin,
        isBuy,
        sizeUsd: estimatedUsd,
        slippage: 0.01,
      });

      // 3. Report to backend for trade journal
      setLoadingMsg("Logging trade...");
      await fetch(`${api}/api/trade/log`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address,
          symbol: selected.symbol,
          coin,
          side,
          size_usd: estimatedUsd,
          volume: result.volume || result.totalSz,
          leverage,
          entry_price: result.avgPx,
          order_id: String(result.oid || ""),
        }),
      });

      setFeedback({
        ok: true,
        msg: `${side} ${coin} $${estimatedUsd.toFixed(0)} @ $${result.avgPx.toFixed(2)} (${leverage}x)`,
      });
      setSizeValue("");
    } catch (e) {
      const msg = e.message || "Trade failed";
      // User rejected in wallet
      if (msg.includes("rejected") || msg.includes("denied") || msg.includes("User rejected")) {
        setFeedback({ ok: false, msg: "Signature rejected" });
      } else {
        setFeedback({ ok: false, msg });
      }
    }
    setLoading(false);
    setLoadingMsg("");
    setConfirm(false);
    setTimeout(() => setFeedback(null), 6000);
  };

  const cancelConfirm = () => setConfirm(false);

  const isLong = side === "LONG";
  const sideColor = isLong ? "#34d399" : "#f87171";
  const sideBg = isLong ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.12)";
  const sideBorder = isLong ? "rgba(52,211,153,0.3)" : "rgba(248,113,113,0.3)";

  return (
    <div style={{ marginTop: 20 }}>
      {/* Divider */}
      <div style={{ height: 1, background: T.border, marginBottom: 14 }} />
      <div style={{
        fontSize: 8, color: T.text4, letterSpacing: "0.1em",
        fontFamily: T.font, fontWeight: 500, marginBottom: 12,
        textTransform: "uppercase",
      }}>
        Manual Trade
      </div>

      {/* Wallet connection */}
      {!isConnected ? (
        <div style={{ marginBottom: 12 }}>
          <button
            onClick={connect}
            style={{
              width: "100%", padding: "10px 0", borderRadius: 10,
              border: `1px solid rgba(139,92,246,0.3)`,
              background: "rgba(139,92,246,0.08)",
              color: "#8b5cf6",
              fontSize: 11, fontFamily: T.mono, fontWeight: 700,
              cursor: "pointer", letterSpacing: "0.06em",
            }}
          >
            Connect Wallet
          </button>
          {walletError && (
            <div style={{ marginTop: 6, fontSize: 9, color: "#f87171", fontFamily: T.mono, textAlign: "center" }}>
              {walletError}
            </div>
          )}
        </div>
      ) : (
        <div style={{
          display: "flex", alignItems: "center", gap: 6, marginBottom: 12,
          fontSize: 9, fontFamily: T.mono, color: T.text4,
        }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#34d399" }} />
          {address.slice(0, 6)}...{address.slice(-4)}
        </div>
      )}

      {isConnected && <>
        {/* Side toggle */}
        <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
          {["LONG", "SHORT"].map(s => {
            const active = side === s;
            const c = s === "LONG" ? "#34d399" : "#f87171";
            return (
              <button
                key={s}
                onClick={() => { setSide(s); setConfirm(false); }}
                style={{
                  flex: 1, padding: "8px 0", borderRadius: 8,
                  border: `1px solid ${active ? c + "50" : T.border}`,
                  background: active ? c + "18" : T.overlay02,
                  color: active ? c : T.text4,
                  fontSize: 11, fontFamily: T.mono, fontWeight: 700,
                  cursor: "pointer", transition: "all 0.15s",
                  letterSpacing: "0.06em",
                }}
              >
                {s}
              </button>
            );
          })}
        </div>

        {/* Size input + mode toggle */}
        <div style={{ display: "flex", gap: 6, marginBottom: 10 }}>
          <input
            type="number"
            placeholder={sizeMode === "usd" ? "Amount (USD)" : "% of equity"}
            value={sizeValue}
            onChange={e => { setSizeValue(e.target.value); setConfirm(false); }}
            style={{
              flex: 1, padding: "8px 12px", borderRadius: 8,
              border: `1px solid ${T.border}`,
              background: T.overlay04, color: T.text1,
              fontSize: 12, fontFamily: T.mono, fontWeight: 500,
              outline: "none",
            }}
          />
          <button
            onClick={() => { setSizeMode(m => m === "usd" ? "pct" : "usd"); setConfirm(false); }}
            style={{
              padding: "8px 12px", borderRadius: 8,
              border: `1px solid ${T.border}`,
              background: T.overlay04, color: T.accent,
              fontSize: 11, fontFamily: T.mono, fontWeight: 700,
              cursor: "pointer", minWidth: 42,
            }}
          >
            {sizeMode === "usd" ? "$" : "%"}
          </button>
        </div>

        {/* Leverage presets */}
        <div style={{ display: "flex", gap: 4, marginBottom: 10 }}>
          {LEVERAGE_PRESETS.map(lev => (
            <button
              key={lev}
              onClick={() => { setLeverage(lev); setConfirm(false); }}
              style={{
                flex: 1, padding: "6px 0", borderRadius: 6,
                border: `1px solid ${leverage === lev ? "rgba(139,92,246,0.4)" : T.border}`,
                background: leverage === lev ? "rgba(139,92,246,0.12)" : T.overlay02,
                color: leverage === lev ? "#8b5cf6" : T.text4,
                fontSize: 10, fontFamily: T.mono, fontWeight: 700,
                cursor: "pointer", transition: "all 0.15s",
              }}
            >
              {lev}x
            </button>
          ))}
        </div>

        {/* Estimates */}
        {parsedSize > 0 && (
          <div style={{
            display: "flex", justifyContent: "space-between",
            padding: "6px 0", marginBottom: 8,
            fontSize: 10, fontFamily: T.mono, color: T.text3,
          }}>
            <span>Est. Cost: ${estimatedUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            <span>Margin: ${estimatedMargin.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
          </div>
        )}

        {/* Equity display */}
        {accountData && (
          <div style={{
            fontSize: 9, fontFamily: T.mono, color: T.text4, marginBottom: 10,
          }}>
            Equity: ${equity.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </div>
        )}

        {/* Execute / Confirm */}
        {!confirm ? (
          <button
            onClick={handleExecute}
            disabled={!canTrade}
            style={{
              width: "100%", padding: "10px 0", borderRadius: 10,
              border: `1px solid ${canTrade ? sideBorder : T.border}`,
              background: canTrade ? sideBg : T.overlay02,
              color: canTrade ? sideColor : T.text4,
              fontSize: 12, fontFamily: T.mono, fontWeight: 700,
              cursor: canTrade ? "pointer" : "not-allowed",
              letterSpacing: "0.06em", transition: "all 0.15s",
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? (loadingMsg || "Executing...") : `${side} ${coin}`}
          </button>
        ) : (
          <div style={{
            padding: "10px 14px", borderRadius: 10,
            border: `1px solid ${sideBorder}`,
            background: sideBg,
          }}>
            <div style={{
              fontSize: 11, fontFamily: T.mono, color: sideColor,
              fontWeight: 600, marginBottom: 8, textAlign: "center",
            }}>
              Confirm {side} {coin} ${estimatedUsd.toFixed(0)} @ {leverage}x?
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                onClick={handleExecute}
                disabled={loading}
                style={{
                  flex: 1, padding: "8px 0", borderRadius: 8,
                  border: `1px solid ${sideColor}50`,
                  background: sideColor + "25",
                  color: sideColor,
                  fontSize: 11, fontFamily: T.mono, fontWeight: 700,
                  cursor: loading ? "not-allowed" : "pointer",
                }}
              >
                {loading ? (loadingMsg || "...") : "Confirm"}
              </button>
              <button
                onClick={cancelConfirm}
                style={{
                  flex: 1, padding: "8px 0", borderRadius: 8,
                  border: `1px solid ${T.border}`,
                  background: T.overlay04, color: T.text3,
                  fontSize: 11, fontFamily: T.mono, fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Feedback */}
        {feedback && (
          <div style={{
            marginTop: 8, padding: "8px 12px", borderRadius: 8,
            border: `1px solid ${feedback.ok ? "rgba(52,211,153,0.2)" : "rgba(248,113,113,0.2)"}`,
            background: feedback.ok ? "rgba(52,211,153,0.06)" : "rgba(248,113,113,0.06)",
            fontSize: 10, fontFamily: T.mono,
            color: feedback.ok ? "#34d399" : "#f87171",
          }}>
            {feedback.ok ? "\u2713 " : "\u2717 "}{feedback.msg}
          </div>
        )}
      </>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DetailPanel
// ---------------------------------------------------------------------------

export default function DetailPanel({ selected, isMobile, isTablet, onClose, api }) {
  if (!selected) return null;

  const tvUrl = `https://www.tradingview.com/chart/?symbol=${getTVSymbol(selected.symbol)}`;
  const hlCoin = selected.symbol.split("/")[0];
  const hlUrl = `https://app.hyperliquid.xyz/trade/${hlCoin}`;

  return (
    <>
      {/* Click-outside overlay (mobile: opaque, desktop: transparent) */}
      <div
        onClick={onClose}
        style={{
          position: "fixed", inset: 0, zIndex: 199,
          background: isMobile ? T.shadowDeep : "transparent",
        }}
      />

      <div style={{
        position: "fixed", right: 0, top: 0, bottom: 0,
        left: isMobile ? 0 : undefined,
        width: isMobile ? "100%" : isTablet ? 580 : 820,
        background: T.drawerBg,
        backdropFilter: "blur(32px) saturate(1.4)", WebkitBackdropFilter: "blur(32px) saturate(1.4)",
        borderLeft: isMobile ? "none" : `1px solid ${T.border}`,
        padding: isMobile ? "20px 16px" : "28px 32px",
        overflowY: "auto", zIndex: 200,
        transition: "transform 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94)",
        boxShadow: isMobile ? "none" : `-8px 0 40px ${T.shadowDeep}`,
      }}>
        {/* Mobile drag handle */}
        {isMobile && (
          <div style={{
            width: 36, height: 4, borderRadius: 2,
            background: T.overlay15,
            margin: "0 auto 16px auto",
          }} />
        )}

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: isMobile ? 20 : 22, fontWeight: 700, color: T.text1, fontFamily: T.font, letterSpacing: "-0.02em" }}>
              {getBaseSymbol(selected.symbol)}
            </div>
            <div style={{ fontSize: 10, color: T.text4, letterSpacing: "0.06em", fontFamily: T.mono, marginTop: 4 }}>
              {selected.symbol} {"\u00b7"} {(selected.timeframe || "").toUpperCase()}
            </div>
          </div>
          <button
            className="apple-btn"
            onClick={onClose}
            style={{
              borderRadius: "50%", padding: 0,
              width: isMobile ? 36 : 28,
              height: isMobile ? 36 : 28,
              fontSize: isMobile ? 14 : 12,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >{"\u2715"}</button>
        </div>

        {/* BMSB Chart */}
        <BMSBChart
          symbol={selected.symbol}
          timeframe={selected.timeframe === "1d" ? "1d" : "4h"}
          height={isMobile ? 300 : isTablet ? 420 : 520}
          signal={selected.signal}
          regime={selected.regime}
          heat={selected.heat}
          conditions={selected.conditions_met}
          conditionsTotal={selected.conditions_total}
          exhaustionState={selected.exhaustion_state}
          floorConfirmed={selected.floor_confirmed}
          signalConfidence={selected.signal_confidence}
          momentum={selected.momentum}
        />

        {/* Regime + Signal badges */}
        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          <RegimeBadge regime={selected.regime} />
          <SignalDot signal={selected.signal} />
          {selected.signal_confidence != null && (
            <span style={{
              padding: "3px 8px", borderRadius: "20px",
              background: T.surface, border: `1px solid ${T.border}`,
              fontSize: 9, fontFamily: T.mono, fontWeight: 500,
              color: selected.signal_confidence >= 0.8 ? "#34d399" : selected.signal_confidence >= 0.5 ? "#fbbf24" : T.text3,
            }}>
              {Math.round(selected.signal_confidence * 100)}%
            </span>
          )}
        </div>

        {/* Conditions Scorecard */}
        <ConditionsScorecard
          conditions={selected.conditions_detail}
          met={selected.conditions_met}
          total={selected.conditions_total}
        />

        {/* Signal reason */}
        {selected.signal_reason && (
          <div style={{
            padding: "12px 14px", borderRadius: T.radiusSm,
            background: T.glassBg,
            border: `1px solid ${T.border}`,
            marginBottom: 14,
            backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
          }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 8, marginBottom: 6,
            }}>
              <div style={{ width: 3, height: 12, borderRadius: 2, background: T.text3, flexShrink: 0 }} />
              <span style={{ fontSize: T.textXs, color: T.text4, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 600, textTransform: "uppercase" }}>
                Signal Reason
              </span>
            </div>
            <div style={{ fontSize: T.textSm, color: T.text2, fontFamily: T.mono, lineHeight: 1.6, paddingLeft: 11 }}>
              {selected.signal_reason}
            </div>
          </div>
        )}

        {/* Signal warnings */}
        {selected.signal_warnings && selected.signal_warnings.length > 0 && (
          <div style={{
            padding: "12px 14px", borderRadius: T.radiusSm,
            background: "rgba(251,191,36,0.03)",
            border: "1px solid rgba(251,191,36,0.12)",
            marginBottom: 14,
            backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
          }}>
            {selected.signal_warnings.map((w, i) => (
              <div key={i} style={{
                fontSize: T.textXs, color: "#fbbf24", fontFamily: T.mono, lineHeight: 1.7,
                display: "flex", gap: 6, alignItems: "flex-start",
              }}>
                <span style={{ flexShrink: 0 }}>{"\u26a0"}</span>
                <span>{w}</span>
              </div>
            ))}
          </div>
        )}

        {/* Raw vs Final signal */}
        {selected.raw_signal && selected.raw_signal !== selected.signal && (
          <div style={{
            display: "flex", alignItems: "center", gap: 8, marginBottom: 12,
            fontSize: T.textXs, color: T.text4, fontFamily: T.mono,
          }}>
            <span>Raw: </span>
            <SignalDot signal={selected.raw_signal} />
            <span style={{ color: T.text4 }}>{"\u2192"}</span>
            <span>Final: </span>
            <SignalDot signal={selected.signal} />
          </div>
        )}

        {/* Agent layer override indicator */}
        {selected.agent_signal && selected.agent_signal !== selected.signal && (
          <div style={{
            display: "flex", alignItems: "center", gap: 8, marginBottom: 12,
            fontSize: T.textXs, color: "#a78bfa", fontFamily: T.mono,
          }}>
            <span>{"\U0001f916"} Agent: </span>
            <SignalDot signal={selected.signal} />
            <span style={{ color: T.text4 }}>{"\u2192"}</span>
            <SignalDot signal={selected.agent_signal} />
            {selected.agent_filters_fired && selected.agent_filters_fired.length > 0 && (
              <span style={{ color: T.text4, fontSize: T.textXs }}>
                ({selected.agent_filters_fired.join(", ")})
              </span>
            )}
          </div>
        )}

        {/* Confluence Panel */}
        <ConfluencePanel confluence={selected.confluence} />

        {/* Market Structure — Positioning + CoinGlass signals unified */}
        <PositioningPanel
          positioning={selected.positioning}
          cvdTrend={selected.cvd_trend}
          cvdDiv={selected.cvd_divergence}
          bsr={selected.buy_sell_ratio}
          vpin={selected.vpin}
          vpinLabel={selected.vpin_label}
          oiContext={selected.oi_context}
        />

        {/* Z-Score Bar */}
        <div style={{ marginBottom: 16 }}>
          <ZScoreBar z={selected.zscore} isMobile={isMobile} />
        </div>

        {/* Detailed Metrics */}
        <div style={{
          background: T.glassBg,
          border: `1px solid ${T.border}`,
          borderRadius: T.radius,
          padding: "14px 16px",
          marginBottom: 14,
          backdropFilter: "blur(20px) saturate(1.3)",
          WebkitBackdropFilter: "blur(20px) saturate(1.3)",
          boxShadow: `0 2px 12px ${T.shadow}`,
        }}>
          <div style={{
            display: "flex", alignItems: "center", gap: 8,
            marginBottom: 12, paddingBottom: 10,
            borderBottom: `1px solid ${T.overlay06}`,
          }}>
            <div style={{ width: 3, height: 14, borderRadius: 2, background: T.accent, flexShrink: 0 }} />
            <span style={{
              fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em",
              fontFamily: T.font, fontWeight: 700, textTransform: "uppercase",
            }}>
              Engine Metrics
            </span>
          </div>
          {[
            ["Z-Score", fmt(selected.zscore, 3), zBar(selected.zscore)?.color],
            ["Energy", fmt(selected.energy, 3), null],
            ["Momentum", `${selected.momentum >= 0 ? "+" : ""}${fmt(selected.momentum, 2)}%`, selected.momentum >= 0 ? "#34d399" : "#f87171"],
            ["Price", selected.price ? `$${selected.price < 1 ? fmt(selected.price, 5) : fmt(selected.price, 2)}` : "\u2014", null],
            ["Divergence", selected.divergence || "None", selected.divergence ? "#fbbf24" : null],
            [null],
            ["Heat", selected.heat != null ? Math.round(selected.heat) : "\u2014", heatColor(selected.heat)],
            ["Phase", selected.heat_phase || "\u2014", phaseColor(selected.heat_phase)],
            ["ATR Regime", selected.atr_regime || "\u2014", null],
            ["Deviation", selected.deviation_pct != null ? `${fmt(selected.deviation_pct, 2)}%` : "\u2014", null],
            [null],
            ["Exhaustion", selected.exhaustion_state || "\u2014", exhaustMeta(selected.exhaustion_state).color],
            ["Floor", selected.floor_confirmed ? "Confirmed" : "No", selected.floor_confirmed ? "#34d399" : null],
            ["Absorption", selected.is_absorption ? "Yes" : "No", selected.is_absorption ? "#67e8f9" : null],
            ["Climax", selected.is_climax ? "Yes" : "No", selected.is_climax ? "#fbbf24" : null],
            ["Effort", selected.effort != null ? fmt(selected.effort, 3) : "\u2014", null],
            ["Rel Volume", selected.rel_vol != null ? fmt(selected.rel_vol, 2) + "x" : "\u2014", null],
          ].map(([label, value, valColor], i) => {
            if (!label) return <div key={i} style={{ height: 1, background: T.overlay06, margin: "4px 0" }} />;
            return (
              <div key={label} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "7px 0",
              }}>
                <span style={{ fontSize: T.textXs, color: T.text3, fontFamily: T.font, fontWeight: 500, letterSpacing: "0.04em" }}>{label}</span>
                <span style={{ fontFamily: T.mono, fontSize: isMobile ? T.textSm : T.textBase, color: valColor || T.text1, fontWeight: 600 }}>{value}</span>
              </div>
            );
          })}
        </div>

        {/* Manual Trade Form */}
        {api && <TradeForm selected={selected} api={api} isMobile={isMobile} />}

        {/* External links */}
        <div style={{ display: "flex", gap: 8, marginTop: 20 }}>
          <a
            href={hlUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="apple-btn apple-btn-accent"
            style={{
              flex: 1, display: "block", padding: isMobile ? "14px 16px" : "12px 16px",
              borderRadius: 12, fontFamily: T.font,
              fontSize: 12, textDecoration: "none", textAlign: "center",
              letterSpacing: "0.06em", fontWeight: 700,
            }}
          >
            Trade on Hyperliquid {"\u2197"}
          </a>
          <a
            href={tvUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="apple-btn"
            style={{
              flex: 1, display: "block", padding: isMobile ? "14px 16px" : "12px 16px",
              borderRadius: 12, fontFamily: T.font,
              fontSize: 12, textDecoration: "none", textAlign: "center",
              letterSpacing: "0.06em", fontWeight: 700,
              border: `1px solid ${T.border}`, color: T.text2,
            }}
          >
            Open in TradingView {"\u2197"}
          </a>
        </div>
      </div>
    </>
  );
}
