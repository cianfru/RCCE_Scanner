import { useEffect, useMemo, useRef, useState } from "react";
import Tabs from "./Tabs.jsx";
import { T } from "../theme.js";
import { displayName, gapSeries, leanPct, orderFor, orderedRows, usd } from "../utils/cohorts.js";

const API_BASE = import.meta.env.VITE_API_URL || "";
const RANGES = [{ key: "1", label: "1D" }, { key: "7", label: "7D" }, { key: "30", label: "30D" }];
const DIMENSIONS = [
  { key: "pnl", label: "By all-time profit", title: "Groups by all-time PnL on Hyperliquid" },
  { key: "equity", label: "By account size", title: "Groups by perp account value" },
];

// Losing groups in warm tones, profitable groups in cool ones; account sizes light to dark.
// Light theme gets deeper shades so the palest lines stay visible on white.
function colorsFor(dimension) {
  const light = typeof document !== "undefined" && document.documentElement.getAttribute("data-theme") === "light";
  if (dimension === "equity") return light ? ["#6b8fbf", "#4f76ad", "#355e9a", "#1f4785"] : ["#9fb8d8", "#7d9fcc", "#5b86bf", "#3a6db3"];
  return light ? ["#9c3b28", "#b4533f", "#c86f4f", "#d08a62", "#5aa391", "#2f8f78", "#1b7a64", "#0d6552"]
    : ["#b4533f", "#cf7a5c", "#dfa27f", "#e8c3a6", "#9fd8c9", "#6fc3ad", "#3fae91", "#1f9a7c"];
}

const when = ts => {
  const d = new Date(ts * 1000);
  return `${d.getUTCDate()} ${d.toLocaleString("en-US", { month: "short", timeZone: "UTC" })} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
};

// Lean over time, -100% (all short) to +100% (all long), one line per group.
function LeanChart({ series, height = 200, aria, zeroLabel = "Balanced" }) {
  const box = useRef(null);
  const [W, setW] = useState(640);
  const [hover, setHover] = useState(null);
  useEffect(() => {
    if (!box.current || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);
  const all = series.flatMap(s => s.points);
  const ts = [...new Set(all.map(p => p.ts))].sort((a, b) => a - b);
  if (ts.length < 2) return <div ref={box} className="coh-empty">One reading so far. The chart fills in as readings arrive.</div>;
  const padL = 8, padR = 44, padT = 8, padB = 22, t0 = ts[0], t1 = ts[ts.length - 1];
  const x = t => padL + ((t - t0) / (t1 - t0 || 1)) * (W - padL - padR);
  const y = v => padT + (1 - (v + 1) / 2) * (height - padT - padB);
  const path = pts => pts.filter(p => p.v != null).map((p, i) => `${i ? "L" : "M"}${x(p.ts).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
  const onMove = e => {
    const r = e.currentTarget.getBoundingClientRect();
    const t = t0 + (((e.clientX - r.left) / r.width) * W - padL) / (W - padL - padR) * (t1 - t0);
    setHover(ts.reduce((b, c) => (Math.abs(c - t) < Math.abs(b - t) ? c : b), ts[0]));
  };
  return <div ref={box} className="coh-chart">
    <svg viewBox={`0 0 ${W} ${height}`} width={W} height={height} role="img" aria-label={aria}
      onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
      {[-1, -0.5, 0, 0.5, 1].map(v => <g key={v}>
        <line className={v === 0 ? "coh-zero" : "coh-grid"} x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} />
        <text className="coh-tick" x={W - padR + 6} y={y(v) + 4}>{v === 0 ? "0" : leanPct(v)}</text>
      </g>)}
      <text className="coh-tick" x={padL + 2} y={y(0) - 4}>{zeroLabel}</text>
      {series.map(s => <path key={s.key} d={path(s.points)} fill="none" stroke={s.color} strokeWidth={s.width || 1.5} strokeDasharray={s.dash} />)}
      <text className="coh-tick" x={padL} y={height - 6}>{when(t0)}</text>
      <text className="coh-tick" x={W - padR} y={height - 6} textAnchor="end">{when(t1)}</text>
      {hover != null && <line className="coh-cursor" x1={x(hover)} x2={x(hover)} y1={padT} y2={height - padB} />}
    </svg>
    <div className="coh-readout">
      {hover == null ? <span>Hover the chart for a reading.</span> : <>
        <b>{when(hover)}</b>
        {series.map(s => { const p = s.points.find(q => q.ts === hover); return p?.v == null ? null : <span key={s.key} style={{ color: s.color }}>{s.label} {leanPct(p.v)}</span>; })}
      </>}
    </div>
  </div>;
}

// HyperLens Cohorts view: how each group of wallets leans, now and over time.
export default function CohortsView() {
  const [dimension, setDimension] = useState("pnl");
  const [symbol, setSymbol] = useState("");
  const [days, setDays] = useState("7");
  const [now, setNow] = useState(null);
  const [hist, setHist] = useState(null);
  useEffect(() => {
    let alive = true;
    const q = `dimension=${dimension}${symbol ? `&symbol=${symbol}` : ""}`;
    const load = () => Promise.all([
      fetch(`${API_BASE}/api/cohorts?${q}`).then(r => (r.ok ? r.json() : null)),
      fetch(`${API_BASE}/api/cohorts/history?${q}&days=${days}`).then(r => (r.ok ? r.json() : null)),
    ]).then(([a, b]) => { if (alive) { setNow(a); setHist(b); } }).catch(() => {});
    load();
    const id = setInterval(load, 300_000);
    return () => { alive = false; clearInterval(id); };
  }, [dimension, symbol, days]);
  const rows = useMemo(() => orderedRows(now?.rows, dimension), [now, dimension]);
  const colors = colorsFor(dimension);
  const series = useMemo(() => orderFor(dimension).map(([k], i) => ({
    key: k, label: displayName(dimension, k), color: colors[i],
    points: (hist?.cohorts?.[k] || []).map(p => ({ ts: p.ts, v: p.bias })),
  })).filter(s => s.points.length), [hist, dimension]);  // eslint-disable-line react-hooks/exhaustive-deps
  const gaps = useMemo(() => (dimension === "pnl" ? gapSeries(hist?.cohorts) : []), [hist, dimension]);
  const div = now?.divergence;
  const zNote = rows.some(r => r.bias_z != null) ? null : "Compared with each group's own history after 3 days of readings.";
  return <div className="coh">
    <p className="coh-intro">
      How groups of Hyperliquid wallets are positioned. Lean is (long − short) ÷ (long + short) by position size: +100% all long, −100% all short.
      {now?.since ? ` Collecting since ${when(now.since)}: ${now.readings} all-market readings (every 30 minutes), ${now.symbol_readings} per-coin (every 4 hours).` : ""}
    </p>
    <div className="coh-controls">
      <Tabs small label="Group wallets" items={DIMENSIONS} value={dimension} onChange={setDimension} />
      <label className="coh-market">Market
        <select value={symbol} onChange={e => setSymbol(e.target.value)}>
          <option value="">All markets</option>
          {(now?.symbols || []).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
    </div>
    {!now?.ts ? <p className="coh-empty">{now?.note || "No readings yet."}</p> : <>
      <table className="coh-table">
        <caption className="coh-caption">{symbol || "All markets"} · {when(now.ts)}</caption>
        <thead><tr><th scope="col">Group</th><th scope="col">Positioned</th><th scope="col" className="coh-wide">Long</th><th scope="col" className="coh-wide">Short</th><th scope="col">Lean</th><th scope="col" className="coh-wide">vs usual</th></tr></thead>
        <tbody>{rows.map(r => <tr key={r.cohort}>
          <th scope="row">{r.name}</th>
          <td>{r.positioned} of {r.wallets}</td>
          <td className="coh-wide">{usd(r.long_usd)}</td><td className="coh-wide">{usd(r.short_usd)}</td>
          <td><span className="coh-bar" aria-hidden="true"><i style={{ left: r.bias >= 0 ? "50%" : `${50 + 50 * r.bias}%`, width: `${50 * Math.abs(r.bias || 0)}%`, background: r.bias >= 0 ? T.accent : "#cf7a5c" }} /></span>{leanPct(r.bias)}</td>
          <td className="coh-wide">{r.bias_z == null ? "—" : `${r.bias_z > 0 ? "+" : ""}${r.bias_z.toFixed(1)} sd`}</td>
        </tr>)}</tbody>
      </table>
      {zNote && <p className="coh-muted">"vs usual": {zNote}</p>}
      {dimension === "pnl" && div?.divergence != null && <p className="coh-gap">
        Wallets up $100K+ all-time lean <b>{leanPct(div.winners.bias)}</b>; wallets that lost money lean <b>{leanPct(div.losers.bias)}</b>.
        The gap is {Math.round(Math.abs(div.divergence) * 100)} points{div.divergence > 0 ? ", profitable wallets longer" : div.divergence < 0 ? ", losing wallets longer" : ""}.
      </p>}
      <div className="coh-section-head"><h3>Lean over time</h3><Tabs small label="Range" items={RANGES} value={days} onChange={setDays} /></div>
      <LeanChart series={series} aria={`Lean of each wallet group over ${days} days`} />
      <ul className="coh-legend">{series.map(s => <li key={s.key}><i style={{ background: s.color }} />{s.label}</li>)}</ul>
      {dimension === "pnl" && gaps.length > 0 && <>
        <h3 className="coh-h3">Profitable against losing wallets</h3>
        <LeanChart height={150} zeroLabel="Same lean" aria="Lean of profitable wallets minus lean of losing wallets"
          series={[{ key: "w", label: "Profitable", color: T.accent, points: gaps.map(g => ({ ts: g.ts, v: g.winners })) },
                   { key: "l", label: "Losing", color: "#cf7a5c", points: gaps.map(g => ({ ts: g.ts, v: g.losers })) }]} />
      </>}
      <p className="coh-muted">{now.population} Descriptive only: whether the gap between profitable and losing wallets leads price has not been tested yet; that needs about 30 days of readings.</p>
    </>}
  </div>;
}
