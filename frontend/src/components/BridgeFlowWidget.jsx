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
const POLL_INTERVAL_MS = 10 * 60 * 1000; // 10 min — macro indicator, not tick-level

function fmtUsd(v) {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : v > 0 ? "+" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

// Compact 60×18 sparkline of a signed numeric series. Color is green when
// the latest value is positive (net inflow), red when negative.
function MiniFlowSparkline({ values }) {
  if (!values || values.length < 2) return null;
  const w = 72, h = 18, pad = 1;
  const n = values.length;
  const xStep = (w - pad * 2) / Math.max(n - 1, 1);

  const max = Math.max(...values);
  const min = Math.min(...values);
  const absMax = Math.max(Math.abs(max), Math.abs(min), 1);

  // Center the zero line vertically
  const midY = h / 2;
  const yFor = (v) => midY - (v / absMax) * (h / 2 - pad);

  const points = values.map((v, i) => `${pad + i * xStep},${yFor(v)}`).join(" ");
  const latest = values[values.length - 1];
  const stroke = latest >= 0 ? "#34d399" : "#f87171";

  // Build a fill polygon back to the midline so it reads like an area chart
  const fill = `${pad},${midY} ${points} ${pad + (n - 1) * xStep},${midY}`;

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ flexShrink: 0 }}>
      {/* Zero line */}
      <line x1="0" y1={midY} x2={w} y2={midY} stroke={T.overlay12 || T.border} strokeWidth="0.5" strokeDasharray="1 2" />
      <polygon points={fill} fill={`${stroke}22`} />
      <polyline points={points} fill="none" stroke={stroke} strokeWidth="1.3" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

// Divergence sparkline — signed z-score series. Amber zone at ±1.5σ marks the
// DIVERGING threshold, red/cyan zone at ±2.5σ marks EXHAUSTION. Helps spot
// the *trajectory* toward a top/bottom rather than just the current reading.
function DivergenceSparkline({ values }) {
  if (!values || values.length < 2) return null;
  const w = 72, h = 18, pad = 1;
  const n = values.length;
  const xStep = (w - pad * 2) / Math.max(n - 1, 1);
  const absMax = Math.max(...values.map((v) => Math.abs(v)), 3.0); // clamp so ±2.5σ always visible
  const midY = h / 2;
  const yFor = (v) => midY - (v / absMax) * (h / 2 - pad);
  const points = values.map((v, i) => `${pad + i * xStep},${yFor(v)}`).join(" ");

  const latest = values[values.length - 1];
  const absL = Math.abs(latest);
  // Distribution (BTC up more than flow) = score > 0 → red-ish;
  // Accumulation = score < 0 → cyan-ish.
  const stroke =
    absL >= 2.5 ? (latest > 0 ? "#f87171" : "#22d3ee") :
    absL >= 1.5 ? "#fbbf24" :
    "#64748b";

  // Threshold bands
  const y15pos = yFor(1.5);
  const y15neg = yFor(-1.5);

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ flexShrink: 0 }}>
      {/* ±1.5σ bands */}
      <line x1="0" y1={y15pos} x2={w} y2={y15pos} stroke="#fbbf2433" strokeWidth="0.5" strokeDasharray="1 2" />
      <line x1="0" y1={y15neg} x2={w} y2={y15neg} stroke="#fbbf2433" strokeWidth="0.5" strokeDasharray="1 2" />
      {/* Zero line */}
      <line x1="0" y1={midY} x2={w} y2={midY} stroke={T.overlay12 || T.border} strokeWidth="0.5" />
      <polyline points={points} fill="none" stroke={stroke} strokeWidth="1.3" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export default function BridgeFlowWidget({ isMobile }) {
  const [data, setData] = useState(null);
  const [history, setHistory] = useState(null);
  const [divHistory, setDivHistory] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [snapRes, histRes] = await Promise.all([
          fetch(`${API_BASE}/api/hyperliquid/bridge`),
          fetch(`${API_BASE}/api/hyperliquid/bridge/history?hours=24`),
        ]);
        if (snapRes.ok) {
          const j = await snapRes.json();
          if (!cancelled) setData(j);
        }
        if (histRes.ok) {
          const h = await histRes.json();
          if (!cancelled) {
            setHistory(h.history || []);
            setDivHistory(h.divergence_history || []);
          }
        }
      } catch {
        /* swallow — widget just hides */
      }
    };
    load();
    const iv = setInterval(load, POLL_INTERVAL_MS);
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  if (!data || !data.available || !data.w24h) return null;

  // Prefer 24h for display, but fall back to 6h if 24h is incomplete
  // (e.g. very low bridge activity or a cold start).
  const w24 = data.w24h;
  const w6 = data.w6h || w24;
  const displayWindow = w24.complete ? w24 : w6;
  const displayLabel = w24.complete ? "24h" : "6h";
  const partial = !w24.complete;

  const net = displayWindow.net_usd || 0;
  const gross = (displayWindow.inflow_usd || 0) + (displayWindow.outflow_usd || 0);
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

  // BTC × flow divergence (may be absent during cold-start, when <4h of history)
  const div = data.divergence || null;
  const divScore = div ? Number(div.score_6h || 0) : 0;
  const divAbs = Math.abs(divScore);
  const divLabel = div ? div.label : null;
  const divDistribution = divScore > 0;
  const divColor =
    divLabel === "EXHAUSTION" ? (divDistribution ? "#f87171" : "#22d3ee") :
    divLabel === "DIVERGING"  ? "#fbbf24" :
    divLabel === "CONFIRMING" ? T.text3 :
    T.text3;
  const divShortLabel =
    divLabel === "EXHAUSTION" ? (divDistribution ? "DISTRIB" : "ACCUM") :
    divLabel === "DIVERGING"  ? "DIVERG" :
    divLabel === "CONFIRMING" ? "CONFIRM" :
    null;
  const showDiv = div && divLabel !== "NEUTRAL" && divShortLabel;

  // Tooltip summary — accessed by browsers via native title attribute.
  // Append "*" to windows that aren't complete in the current sample.
  const star = (w) => w.complete ? "" : " *";
  const divLine = div
    ? `\nBTC×Flow: ${divLabel}${div.confirmed ? " (confirmed)" : ""} — ${div.interpretation || ""}\n` +
      `  6h score ${divScore >= 0 ? "+" : ""}${divScore.toFixed(1)}σ  ` +
      `(BTC z=${Number(div.btc_return_6h_z).toFixed(1)}, flow z=${Number(div.net_flow_6h_z).toFixed(1)})`
    : "";
  const title =
    `HL Bridge (Arbitrum) — USDC flows\n` +
    `1h:  ${fmtUsd(data.w1h.net_usd)} net  (${data.w1h.tx_count} tx)${star(data.w1h)}\n` +
    `6h:  ${fmtUsd(data.w6h.net_usd)} net  (${data.w6h.tx_count} tx)${star(data.w6h)}\n` +
    `24h: ${fmtUsd(w24.net_usd)} net  (${w24.tx_count} tx)${star(w24)}\n` +
    `7d:  ${fmtUsd(data.w7d.net_usd)} net  (${data.w7d.tx_count} tx)${star(data.w7d)}\n` +
    (partial ? "\n* = sample doesn't cover the full window" : "") +
    divLine;

  // Build the 1h-net flow series (most responsive window for showing pulse)
  const flowSeries = (history || [])
    .map(row => row?.w1h?.net_usd)
    .filter(v => typeof v === "number");

  // Divergence score series for the divergence sparkline
  const divSeries = (divHistory || [])
    .map(row => row?.score_6h)
    .filter(v => typeof v === "number");

  return (
    <GlassCard style={{
      padding: isMobile ? "10px 14px" : "10px 16px",
      display: "flex", alignItems: "center", justifyContent: "center", gap: 10,
      flex: isMobile ? "1 1 calc(50% - 4px)" : undefined,
      border: `1px solid ${borderColor}`,
      flexWrap: "wrap",
    }} title={title}>
      <span style={{
        fontSize: m(11, isMobile), color: T.text3,
        letterSpacing: "0.08em", fontFamily: T.font,
        fontWeight: 600, textTransform: "uppercase",
      }}>
        HL Bridge {displayLabel}{partial ? "*" : ""}
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
      {flowSeries.length >= 2 && <MiniFlowSparkline values={flowSeries} />}

      {showDiv && (
        <>
          <span style={{
            width: 1, height: 14, background: T.border, opacity: 0.5,
          }} />
          <span style={{
            padding: "2px 8px", borderRadius: "20px",
            background: `${divColor}1a`,
            border: `1px solid ${divColor}40`,
            color: divColor,
            fontSize: m(10, isMobile), fontFamily: T.mono, fontWeight: 700,
            letterSpacing: "0.06em",
          }}>
            {divShortLabel}{div.confirmed ? "\u2713" : ""}
          </span>
          <span style={{
            fontFamily: T.mono, fontSize: m(11, isMobile), fontWeight: 600,
            color: divColor,
          }}>
            {divScore >= 0 ? "+" : ""}{divAbs >= 10 ? divScore.toFixed(0) : divScore.toFixed(1)}σ
          </span>
          {divSeries.length >= 2 && <DivergenceSparkline values={divSeries} />}
        </>
      )}
    </GlassCard>
  );
}
