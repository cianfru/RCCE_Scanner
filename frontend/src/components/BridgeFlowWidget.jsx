/**
 * BridgeFlowWidget — Hyperliquid L1 bridge USDC flow (Arbitrum).
 *
 * Shows net 24h flow with INFLOW / OUTFLOW / NEUTRAL label. Polls
 * /api/hyperliquid/bridge every 3 minutes (matching backend cache).
 *
 * Renders nothing when the backend reports ``available: false`` (missing
 * ETHERSCAN_API_KEY), so the row doesn't get a broken tile.
 */
import { useState, useEffect } from "react";
import { T, m } from "../theme.js";
import GlassCard from "./GlassCard.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const POLL_INTERVAL_MS = 3 * 60 * 1000;

function fmtUsd(v) {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : v > 0 ? "+" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

export default function BridgeFlowWidget({ isMobile }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/hyperliquid/bridge`);
        if (!res.ok) return;
        const j = await res.json();
        if (!cancelled) setData(j);
      } catch {
        /* swallow — widget just hides */
      }
    };
    load();
    const iv = setInterval(load, POLL_INTERVAL_MS);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  if (!data || !data.available || !data.w24h) return null;

  const w24 = data.w24h;
  const net = w24.net_usd || 0;
  const gross = (w24.inflow_usd || 0) + (w24.outflow_usd || 0);
  if (gross === 0) return null;

  const trend = data.trend || "NEUTRAL";
  const signal = data.signal || "BALANCED";

  const color =
    trend === "INFLOW"  ? "#34d399" :
    trend === "OUTFLOW" ? "#f87171" :
    T.text3;

  const borderColor =
    trend === "INFLOW"  ? "#34d39920" :
    trend === "OUTFLOW" ? "#f8717120" :
    T.border;

  const label =
    signal === "ACCUMULATING" ? "ACCUM" :
    signal === "DEPLETING"    ? "DRAIN" :
    trend === "INFLOW"        ? "INFLOW" :
    trend === "OUTFLOW"       ? "OUTFLOW" :
    "NEUTRAL";

  const bgTint =
    trend === "INFLOW"  ? "rgba(52,211,153,0.1)" :
    trend === "OUTFLOW" ? "rgba(248,113,113,0.1)" :
    "rgba(82,82,91,0.1)";

  // Tooltip summary — accessed by browsers via native title attribute.
  const title =
    `HL Bridge (Arbitrum) — USDC flows\n` +
    `1h:  ${fmtUsd(data.w1h.net_usd)} net  (${data.w1h.tx_count} tx)\n` +
    `6h:  ${fmtUsd(data.w6h.net_usd)} net  (${data.w6h.tx_count} tx)\n` +
    `24h: ${fmtUsd(w24.net_usd)} net  (${w24.tx_count} tx)\n` +
    `7d:  ${fmtUsd(data.w7d.net_usd)} net  (${data.w7d.tx_count} tx)`;

  return (
    <GlassCard style={{
      padding: isMobile ? "10px 14px" : "10px 16px",
      display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
      flex: isMobile ? "1 1 calc(50% - 4px)" : undefined,
      border: `1px solid ${borderColor}`,
    }} title={title}>
      <span style={{
        fontSize: m(11, isMobile), color: T.text3,
        letterSpacing: "0.08em", fontFamily: T.font,
        fontWeight: 600, textTransform: "uppercase",
      }}>
        HL Bridge 24h
      </span>
      <span style={{
        padding: isMobile ? "3px 10px" : "2px 10px", borderRadius: "20px",
        background: bgTint,
        color,
        fontSize: m(11, isMobile), fontFamily: T.mono, fontWeight: 700,
        letterSpacing: "0.06em",
      }}>
        {label}
      </span>
      <span style={{
        fontFamily: T.mono, fontSize: m(13, isMobile), fontWeight: 700,
        color,
      }}>
        {fmtUsd(net)}
      </span>
    </GlassCard>
  );
}
