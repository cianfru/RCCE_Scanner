/**
 * OptionsVolPanel — what the options market prices for BTC and ETH (Derive, via derive_scan):
 * implied volatility by expiry, the 30-day priced range, and 25-delta skew.
 *
 * Props:
 *   symbol — "BTC/USDT"
 *
 * Only recorded coins fetch; the backend keeps each body until derive_scan's next
 * snapshot (backend/options_surface.py). Context only: not part of the signal.
 */
import { useEffect, useRef, useState } from "react";
import { T } from "../theme.js";
import PanelHeader from "./PanelHeader.jsx";
import HelpTip from "./HelpTip.jsx";
import AsOf from "./AsOf.jsx";
import useViewport from "../hooks/useViewport.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const RECORDED = new Set(["BTC", "ETH"]);   // coins derive_scan records
const TENORS = ["7", "30", "90"];

const pct = (v, d = 1) => (v == null ? "—" : `${(v * 100).toFixed(d)}%`);
const usd = v => (v == null ? "—" : `$${Math.round(v).toLocaleString()}`);

// Drawn at the panel's measured width so labels and dots keep their size.
function useWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

function Curve({ curve, iv, height }) {
  const [ref, width] = useWidth();
  // Expiries under two days swing with the next fixing; they are left off the line.
  const pts = curve.filter(p => p.days >= 2 && p.days <= 200);
  if (pts.length < 2) return null;
  const W = width || 320, H = height, padL = 34, padR = 8, padT = 8, padB = 18;
  const maxDays = Math.max(...pts.map(p => p.days), 90);
  const ivs = pts.map(p => p.iv).concat(TENORS.map(t => iv[t]).filter(v => v != null));
  const lo = Math.min(...ivs), hi = Math.max(...ivs), span = Math.max(hi - lo, 0.02);
  // Square-root time axis: the near expiries are where the curve bends.
  const x = d => padL + Math.sqrt(d / maxDays) * (W - padL - padR);
  const y = v => padT + (1 - (v - lo + span * 0.1) / (span * 1.2)) * (H - padT - padB);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.days).toFixed(1)},${y(p.iv).toFixed(1)}`).join(" ");
  const label = { fontSize: 10, fontFamily: T.mono, fill: T.text3 };
  return (
    <div ref={ref} style={{ width: "100%" }}>
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img"
      aria-label={`Implied volatility by expiry: ${TENORS.map(t => `${t} days ${pct(iv[t])}`).join(", ")}`}>
      <line x1={padL} x2={W - padR} y1={H - padB} y2={H - padB} stroke={T.overlay10} />
      <text x={padL - 4} y={y(hi) + 3} textAnchor="end" style={label}>{pct(hi, 0)}</text>
      <text x={padL - 4} y={y(lo) + 3} textAnchor="end" style={label}>{pct(lo, 0)}</text>
      <path d={path} fill="none" stroke={T.accent} strokeWidth={1.5} strokeLinejoin="round" />
      {pts.map(p => <circle key={p.days} cx={x(p.days)} cy={y(p.iv)} r={1.6} fill={T.accent} opacity={0.55} />)}
      {TENORS.filter(t => iv[t] != null && Number(t) <= maxDays).map(t => (
        <g key={t}>
          <line x1={x(+t)} x2={x(+t)} y1={y(iv[t])} y2={H - padB} stroke={T.overlay15} strokeDasharray="2 2" />
          <circle cx={x(+t)} cy={y(iv[t])} r={3} fill={T.bg} stroke={T.accent} strokeWidth={1.5} />
          <text x={x(+t)} y={H - 5} textAnchor="middle" style={label}>{t}d</text>
        </g>
      ))}
    </svg>
    </div>
  );
}

function Stat({ label, value, sub }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: T.textXs, color: T.text3, fontFamily: T.font }}>{label}</div>
      <div style={{ fontSize: T.textSm, color: T.text1, fontFamily: T.mono, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      {sub && <div style={{ fontSize: T.textXs, color: T.text3, fontFamily: T.mono, fontVariantNumeric: "tabular-nums" }}>{sub}</div>}
    </div>
  );
}

export default function OptionsVolPanel({ symbol }) {
  const { isMobile } = useViewport();
  const coin = (symbol || "").toUpperCase().split("/")[0];
  const recorded = RECORDED.has(coin);
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!recorded) return;
    let cancelled = false;
    fetch(`${API_BASE}/api/options/surface/${encodeURIComponent(coin)}`)
      .then(r => (r.ok ? r.json() : null))
      .then(j => { if (!cancelled) setData(j); })
      .catch(() => { if (!cancelled) setData(null); });
    return () => { cancelled = true; };
  }, [coin, recorded]);

  if (!recorded || !data?.available) return null;
  const iv = data.iv || {};
  const rr = data.rr25_30d;
  const [lo, hi] = data.range_30d || [];

  return (
    <div style={{
      background: T.glassBg, border: `1px solid ${T.border}`, borderRadius: T.radius,
      padding: 16, marginBottom: 14,
    }}>
      <PanelHeader title={<>Options market <HelpTip title="Options market (Derive)" width={380}>
        <p>Implied volatility: the yearly price move the options market is pricing, read at the current price for each expiry. The line runs from the nearest expiry out; the rings mark 7, 30 and 90 days.</p>
        <p>Priced 30-day range: one standard deviation from the 30-day implied volatility. It is what option prices imply, not Reflex's view.</p>
        <p>Skew: 25-delta call minus put volatility. Below zero, downside protection costs more than upside.</p>
        <p>Context only. It is not part of the signal until a study shows it helps.</p>
      </HelpTip></>}>
        <AsOf data={data} />
      </PanelHeader>
      <Curve curve={data.curve || []} iv={iv} height={isMobile ? 110 : 130} />
      <div style={{
        display: "grid", gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(3, minmax(0, 1fr))",
        gap: 12, marginTop: 12,
      }}>
        <Stat label="30-day volatility" value={pct(iv["30"])} sub={`7d ${pct(iv["7"])} · 90d ${pct(iv["90"])}`} />
        <Stat label="Priced 30-day range" value={data.move_30d != null ? `±${pct(data.move_30d)}` : "—"}
          sub={lo != null ? `${usd(lo)} – ${usd(hi)}` : null} />
        <Stat label="Skew 25Δ" value={rr == null ? "—" : `${rr > 0 ? "+" : ""}${(rr * 100).toFixed(1)} pts`}
          sub={rr == null ? null : Math.abs(rr) < 0.005 ? "even" : rr < 0 ? "puts dearer" : "calls dearer"} />
      </div>
    </div>
  );
}
