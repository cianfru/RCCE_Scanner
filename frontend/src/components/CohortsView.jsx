import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Tabs from "./Tabs.jsx";
import DataStatus from "./DataStatus.jsx";
import HelpTip from "./HelpTip.jsx";
import { T } from "../theme.js";
import { dayLabel, displayName, gapSeries, leanPct, orderFor, orderedRows, timeTicks, usd } from "../utils/cohorts.js";

const API_BASE = import.meta.env.VITE_API_URL || "";
const fetchJson = url => fetch(url).then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))));
const RANGES = [{ key: "1", label: "1D" }, { key: "7", label: "7D" }, { key: "30", label: "30D" }];
const DIMENSIONS = [
  { key: "pnl", label: "By all-time profit", title: "Groups by all-time PnL on Hyperliquid" },
  { key: "equity", label: "By account size", title: "Groups by perp account value" },
];

// Loss groups in warm hues (red, orange, amber, mauve), profit groups in cool ones (pale blue,
// blue, teal, green): a different hue per line so eight lines stay apart. Account sizes: one blue,
// pale to deep. Light theme gets deeper steps so every line clears the white surface.
function colorsFor(dimension) {
  const light = typeof document !== "undefined" && document.documentElement.getAttribute("data-theme") === "light";
  if (dimension === "equity") return light ? ["#86a9d9", "#5a86cc", "#2f5fb5", "#163a80"] : ["#c9dcf5", "#8db6ec", "#5690e0", "#2f66c9"];
  return light ? ["#c62f33", "#c5621c", "#9a7a0a", "#a45a88", "#5b83c4", "#2f5fd0", "#0b8a7c", "#1f8f4c"]
    : ["#e5484d", "#ef8a3c", "#d8b13a", "#c78bb0", "#8fb3e8", "#4f86ee", "#1fb3a0", "#48c774"];
}
const warmColor = () => (typeof document !== "undefined" && document.documentElement.getAttribute("data-theme") === "light" ? "#c5621c" : "#ef8a3c");

const when = ts => {
  const d = new Date(ts * 1000);
  return `${dayLabel(ts)} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;
};

// Chart title with its (i), and an optional control on the right.
function ChartHead({ title, info, children }) {
  return <div className="coh-chart-head">
    <h3>{title}</h3>
    <HelpTip title={title} width={360}>{info}</HelpTip>
    {children && <div className="coh-chart-ctl">{children}</div>}
  </div>;
}

const Y_TICKS = [1, 0.5, 0, -0.5, -1];

// Lean over time, -100% (all short) to +100% (all long), one line per group. The legend doubles
// as the readout: each name carries its value at the hovered time (the latest reading otherwise).
// Hovering or tapping a name picks out its line.
function LeanChart({ series, aria }) {
  const box = useRef(null);
  const [W, setW] = useState(0);
  const [hover, setHover] = useState(null);
  const [hot, setHot] = useState(null);
  const [pinned, setPinned] = useState(null);
  useLayoutEffect(() => {
    if (!box.current) return undefined;
    setW(Math.round(box.current.clientWidth));
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);
  const ts = useMemo(() => [...new Set(series.flatMap(s => s.points.map(p => p.ts)))].sort((a, b) => a - b), [series]);
  if (ts.length < 2) return <div ref={box} className="coh-chart"><p className="coh-empty">One reading so far. The chart fills in as readings arrive.</p></div>;
  const focus = hot ?? pinned;
  const phone = W > 0 && W < 560;
  const plotH = phone ? 230 : 340;
  const padL = phone ? 44 : 50, padR = 10, padT = 10, padB = 28, H = plotH + padT + padB;
  const t0 = ts[0], t1 = ts[ts.length - 1], plotW = Math.max(1, W - padL - padR);
  const x = t => padL + ((t - t0) / (t1 - t0 || 1)) * plotW;
  const y = v => padT + (1 - (v + 1) / 2) * plotH;
  const path = pts => pts.filter(p => p.v != null).map((p, i) => `${i ? "L" : "M"}${x(p.ts).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
  const ticks = timeTicks(t0, t1, Math.max(2, Math.floor(plotW / (phone ? 70 : 150)))).filter(t => x(t.ts) > padL + 16 && x(t.ts) < W - padR - 16);
  const at = hover ?? t1;
  const valueAt = s => s.points.find(q => q.ts === at)?.v;
  const onMove = e => {
    const r = e.currentTarget.getBoundingClientRect();
    const t = t0 + ((e.clientX - r.left - padL) / plotW) * (t1 - t0);
    setHover(ts.reduce((b, c) => (Math.abs(c - t) < Math.abs(b - t) ? c : b), ts[0]));
  };
  const drawn = focus ? [...series.filter(s => s.key !== focus), ...series.filter(s => s.key === focus)] : series;
  return <div ref={box} className="coh-chart">
    <div className="coh-readout" aria-live="off">
      <span className="coh-at">{hover == null ? `Latest · ${when(at)}` : when(at)}</span>
      <ul className="coh-legend">{series.map(s => { const v = valueAt(s); return <li key={s.key}>
        <button type="button" aria-pressed={pinned === s.key} data-dim={focus && focus !== s.key ? "" : undefined}
          onMouseEnter={() => setHot(s.key)} onMouseLeave={() => setHot(null)} onFocus={() => setHot(s.key)} onBlur={() => setHot(null)}
          onClick={() => setPinned(k => (k === s.key ? null : s.key))}>
          <i style={{ background: s.color }} /><span className="coh-lg-name">{s.label}</span><b>{leanPct(v)}</b>
        </button></li>; })}</ul>
    </div>
    <div className="coh-plot" style={{ height: H }}>
      {W > 0 && <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={aria}
        onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => setHover(null)}>
        {ticks.map(t => <line key={t.ts} className="coh-vgrid" x1={x(t.ts)} x2={x(t.ts)} y1={padT} y2={padT + plotH} />)}
        {Y_TICKS.map(v => <g key={v}>
          <line className={v === 0 ? "coh-zero" : "coh-grid"} x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} />
          <text className="coh-tick" x={padL - 8} y={y(v) + 4} textAnchor="end">{leanPct(v)}</text>
        </g>)}
        {ticks.map(t => <text key={t.ts} className="coh-tick" x={x(t.ts)} y={H - 8} textAnchor="middle">{t.label}</text>)}
        {drawn.map(s => <path key={s.key} d={path(s.points)} fill="none" stroke={s.color} strokeLinejoin="round"
          strokeWidth={focus === s.key ? 2.5 : 1.75} opacity={focus && focus !== s.key ? 0.16 : 1} />)}
        {hover != null && <>
          <line className="coh-cursor" x1={x(hover)} x2={x(hover)} y1={padT} y2={padT + plotH} />
          {drawn.map(s => { const v = valueAt(s); return v == null || (focus && focus !== s.key) ? null
            : <circle key={s.key} className="coh-mark" cx={x(hover)} cy={y(v)} r={3.5} fill={s.color} />; })}
        </>}
      </svg>}
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const viewKey = useRef(null);
  useEffect(() => {
    let alive = true;
    const q = `dimension=${dimension}${symbol ? `&symbol=${symbol}` : ""}`;
    // A new group or market clears the old readings; a new range keeps them until the new ones land.
    if (viewKey.current !== q) { viewKey.current = q; setNow(null); setHist(null); setUpdatedAt(null); }
    setLoading(true);
    setError(false);
    const load = () => Promise.all([
      fetchJson(`${API_BASE}/api/cohorts?${q}`),
      fetchJson(`${API_BASE}/api/cohorts/history?${q}&days=${days}`),
    ]).then(([a, b]) => { if (alive) { setNow(a); setHist(b); setError(false); setUpdatedAt(Date.now()); } })
      .catch(() => { if (alive) setError(true); })
      .finally(() => { if (alive) setLoading(false); });
    load();
    const id = setInterval(load, 300_000);
    return () => { alive = false; clearInterval(id); };
  }, [dimension, symbol, days, attempt]);
  const rows = useMemo(() => orderedRows(now?.rows, dimension), [now, dimension]);
  const colors = colorsFor(dimension);
  const series = useMemo(() => orderFor(dimension).map(([k], i) => ({
    key: k, label: displayName(dimension, k), color: colors[i],
    points: (hist?.cohorts?.[k] || []).map(p => ({ ts: p.ts, v: p.bias })),
  })).filter(s => s.points.length), [hist, dimension]);  // eslint-disable-line react-hooks/exhaustive-deps
  const gaps = useMemo(() => (dimension === "pnl" ? gapSeries(hist?.cohorts) : []), [hist, dimension]);
  const groupedBy = dimension === "pnl" ? "all-time profit or loss on Hyperliquid" : "perp account value ($100K and up)";
  return <div className="coh">
    <p className="coh-intro">
      How groups of Hyperliquid wallets lean, long or short.{" "}
      <HelpTip title="About cohorts" width={380}>
        <p>{now?.population || "Hyperliquid leaderboard wallets with $100K+ perp equity, plus proven traders ($100K+ all-time PnL) with $10K+ perp equity. Market makers excluded."}</p>
        <p>Lean = (long − short) ÷ (long + short), by the dollar value of open positions: +100% all long, −100% all short. "vs usual" compares a group's lean with its own history, in standard deviations, once there are 3 days of readings.</p>
        <p>Readings every 30 minutes for all markets, every 4 hours per coin{now?.since ? `, since ${when(now.since)}` : ""}.</p>
      </HelpTip>
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
    {/* Status only while it matters: the first load, or a failed read (with Retry). */}
    {(error || (loading && !now)) && <DataStatus label="Cohort readings" loading={loading && !now} error={error && !loading}
      updatedAt={error && !loading ? updatedAt : null} onRetry={() => setAttempt(n => n + 1)} />}
    {!now?.ts ? (loading || error ? null : <p className="coh-empty">{now?.note || "No readings for this view yet. All-market readings arrive every 30 minutes, per-coin readings every 4 hours."}</p>) : <>
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
      <ChartHead title="Lean over time" info={<p>One line per group of wallets, grouped by {groupedBy}. Lean = (long − short) ÷ (long + short), using the dollar value of the group's open positions: +100% all long, −100% all short, 0% balanced. Hover the chart to read every group at one time; hover or tap a name to pick out its line.</p>}>
        <Tabs small label="Range" items={RANGES} value={days} onChange={setDays} />
      </ChartHead>
      <LeanChart series={series} aria={`Lean of each wallet group over ${days} days`} />
      {dimension === "pnl" && gaps.length > 0 && <>
        <ChartHead title="Profitable vs losing wallets" info={<p>Two lean lines: wallets up $100K or more all-time, and wallets with an all-time loss on Hyperliquid. Each line adds up the long and short positions of every wallet in its group, weighted by dollar value. Lines far apart mean the two groups are positioned differently. Descriptive only: whether the gap leads price has not been tested yet; that needs about 30 days of readings.</p>} />
        <LeanChart aria="Lean of wallets up $100K+ all-time and of wallets with an all-time loss"
          series={[{ key: "w", label: "Up $100K+", color: T.accent, points: gaps.map(g => ({ ts: g.ts, v: g.winners })) },
                   { key: "l", label: "Lost money", color: warmColor(), points: gaps.map(g => ({ ts: g.ts, v: g.losers })) }]} />
      </>}
    </>}
  </div>;
}
