import { useEffect, useMemo, useRef, useState } from "react";
import { SECTOR_SHORT, traderWeight } from "../utils/sectors.js";
import { traderLean } from "../utils/traders.js";
import { raceLines } from "../utils/sectorRace.js";
import Tabs from "./Tabs.jsx";

// Race of sectors (or ecosystems) against BTC. Every group is a thin muted line;
// up to three are highlighted in fixed colours (the leaders by default, or the ones
// clicked). Beside it: where profitable traders put their money in each group.
const SLOTS = ["var(--race-1)", "var(--race-2)", "var(--race-3)"];
const RANGES = [{ key: 30, label: "30d" }, { key: 90, label: "90d" }];
const MODES = [{ key: "rel", label: "Against BTC" }, { key: "abs", label: "Price" }];
const short = name => SECTOR_SHORT[name] || name;
const pct = v => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
const fmtDate = t => new Date(t * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function useWidth() {
  const ref = useRef(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

export default function SectorRace({ data, rows, by, value }) {
  const [range, setRange] = useState(30);
  const [mode, setMode] = useState("rel");
  const [picked, setPicked] = useState([]);          // user-highlighted group names, in pick order
  const [hover, setHover] = useState(null);           // index into the visible dates
  const [ref, width] = useWidth();

  useEffect(() => setPicked([]), [by]);

  const { dates, btc, lines } = useMemo(() => raceLines(data, by, range, mode), [data, by, range, mode]);
  const leaders = lines.slice().sort((a, b) => b.last - a.last).slice(0, 3).map(l => l.name);
  // A chip picked in the strip joins the highlighted lines.
  const chosen = value && lines.some(l => l.name === value) ? [value, ...leaders.filter(n => n !== value)].slice(0, 3) : leaders;
  const shown = picked.length ? picked : chosen;
  const colorOf = name => SLOTS[shown.indexOf(name)];
  const toggle = name => setPicked(p => (p.includes(name) ? p.filter(x => x !== name)
    : [...(p.length ? p : []), name].slice(-3)));

  if (!dates.length) return <p className="race-empty">Price history is still loading.</p>;

  const H = 300, padL = 8, padR = 96, padT = 12, padB = 24;
  const W = Math.max(width, 280);
  const all = [...lines.flatMap(l => l.values), ...(mode === "abs" ? btc : [100])].filter(Number.isFinite);
  const pad = (Math.max(...all) - Math.min(...all)) * 0.06 || 1;
  const lo = Math.min(...all) - pad, hi = Math.max(...all) + pad;
  const span = hi - lo;
  const x = i => padL + (i / (dates.length - 1)) * (W - padL - padR);
  const y = v => padT + (1 - (v - lo) / span) * (H - padT - padB);
  const path = vs => vs.map((v, i) => (Number.isFinite(v) ? `${i && Number.isFinite(vs[i - 1]) ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}` : "")).join("");
  const ticks = niceTicks(lo, hi, 4);

  // Direct labels at the right edge, nudged apart so they never overlap.
  const labels = [
    ...(mode === "abs" ? [{ name: "BTC", v: btc[btc.length - 1], color: "var(--t-text1)" }] : [{ name: "BTC", v: 100, color: "var(--t-text3)" }]),
    ...shown.map(n => lines.find(l => l.name === n)).filter(Boolean).map(l => ({ name: short(l.name), v: l.last, color: colorOf(l.name) })),
  ].map(l => ({ ...l, yy: y(l.v) })).sort((a, b) => a.yy - b.yy);
  for (let i = 1; i < labels.length; i++) labels[i].yy = Math.max(labels[i].yy, labels[i - 1].yy + 14);

  const hi_ = hover == null ? null : Math.max(0, Math.min(dates.length - 1, hover));
  const onMove = e => {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    setHover(Math.round(((px - padL) / (W - padL - padR)) * (dates.length - 1)));
  };

  const weights = lines.map(l => ({ name: l.name, weight: traderWeight(data?.lean, rows, by, l.name), traders: traderLean(data?.lean?.groups?.[`${by}:${l.name}`]) }))
    .filter(w => w.weight != null).sort((a, b) => b.weight - a.weight);
  const wMax = Math.max(2, ...weights.map(w => w.weight));

  return <div className="race">
    <div className="race-controls">
      <Tabs small label="Compare" items={MODES} value={mode} onChange={setMode} />
      <Tabs small label="Range" items={RANGES} value={range} onChange={setRange} />
      {picked.length > 0 && <button type="button" className="sector-clear" onClick={() => setPicked([])}>Show leaders</button>}
    </div>
    <div className="race-body">
      <figure className="race-chart" ref={ref}>
        <figcaption className="race-legend">
          {shown.map(n => <button key={n} type="button" onClick={() => toggle(n)} title="Remove highlight">
            <i style={{ background: colorOf(n) }} />{short(n)}</button>)}
          <span><i className="race-btc" />BTC</span>
          <span className="race-hint">{picked.length ? "Click a line to swap it in" : "Leaders shown · click a line to compare"}</span>
        </figcaption>
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img"
          aria-label={`${by === "sector" ? "Sectors" : "Ecosystems"} ${mode === "rel" ? "against BTC" : "rebased to 100"} over ${range} days`}
          onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
          {ticks.map(t => <g key={t}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} className="race-grid" />
            <text x={W - padR + 6} y={y(t) + 3} className="race-tick">{Math.round(t)}</text>
          </g>)}
          {[0, Math.floor((dates.length - 1) / 2), dates.length - 1].map(i => <text key={i} x={x(i)} y={H - 6} className="race-tick"
            textAnchor={i === 0 ? "start" : i === dates.length - 1 ? "end" : "middle"}>{fmtDate(dates[i])}</text>)}
          {mode === "rel"
            ? <line x1={padL} x2={W - padR} y1={y(100)} y2={y(100)} className="race-base" />
            : <path d={path(btc)} className="race-btc-line" />}
          {lines.filter(l => !shown.includes(l.name)).map(l => <g key={l.name} className="race-muted" onClick={() => toggle(l.name)}>
            <path d={path(l.values)} className="race-hit" /><path d={path(l.values)}><title>{`${l.name}: ${pct(l.last - 100)}`}</title></path>
          </g>)}
          {shown.map(n => lines.find(l => l.name === n)).filter(Boolean).map(l => <g key={l.name} onClick={() => toggle(l.name)} className="race-on">
            <path d={path(l.values)} className="race-hit" /><path d={path(l.values)} style={{ stroke: colorOf(l.name) }} />
          </g>)}
          {labels.map(l => <text key={l.name} x={W - padR + 34} y={l.yy + 3} className="race-label" style={{ fill: l.color }}>{l.name}</text>)}
          {hi_ != null && <line x1={x(hi_)} x2={x(hi_)} y1={padT} y2={H - padB} className="race-cross" />}
        </svg>
        {hi_ != null && <div className="race-tip" style={x(hi_) > (W - padR) / 2 ? { left: Math.max(0, x(hi_) - 192) } : { left: x(hi_) + 12 }}>
          <strong>{fmtDate(dates[hi_])}</strong>
          {mode === "abs" && <div><span><i className="race-btc" />BTC</span><b>{pct(btc[hi_] - 100)}</b></div>}
          {shown.map(n => lines.find(l => l.name === n)).filter(Boolean).map(l => <div key={l.name}>
            <span><i style={{ background: colorOf(l.name) }} />{short(l.name)}</span>
            <b>{Number.isFinite(l.values[hi_]) ? pct(l.values[hi_] - 100) : "—"}</b>
          </div>)}
          <em>{mode === "rel" ? "Change against BTC since the start" : "Change since the start"}</em>
        </div>}
      </figure>
      <aside className="race-weights" aria-label="Where profitable traders are positioned">
        <h4>Profitable traders' weight</h4>
        <p>Share of their positions against share of market open interest. 1.0x is market weight.</p>
        {weights.map(w => <div key={w.name} className="race-weight" title={w.traders.n ? `${w.traders.long} long / ${w.traders.short} short` : "Fewer than 3 positioned"}>
          <span>{short(w.name)}</span>
          <span className="race-weight-bar"><i style={{ width: `${Math.min(100, (w.weight / wMax) * 100)}%` }} className={w.weight >= 1.25 ? "over" : w.weight <= 0.8 ? "under" : ""} />
            <em style={{ left: `${(1 / wMax) * 100}%` }} /></span>
          <b>{w.weight.toFixed(1)}x</b>
        </div>)}
        {!weights.length && <p>No positioning data yet.</p>}
      </aside>
    </div>
  </div>;
}

function niceTicks(lo, hi, n) {
  const step0 = (hi - lo) / n;
  const mag = 10 ** Math.floor(Math.log10(step0 || 1));
  const step = [1, 2, 5, 10].map(m => m * mag).find(s => s >= step0) || mag * 10;
  const out = [];
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) out.push(+t.toFixed(6));
  return out;
}

