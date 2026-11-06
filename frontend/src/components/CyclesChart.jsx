import { useMemo, useState } from "react";
import Tabs from "./Tabs.jsx";
import { useWidth } from "./MarketHistoryChart.jsx";
import { Info } from "./MarketHistorySections.jsx";
import { CYCOPY, marketCycles } from "../utils/marketCycles.js";
import { dayDate, monthYear } from "../utils/marketHistory.js";

// The Cycles tab: every past broad downturn or broad uptrend as a line of the share of coins in uptrend from its first
// day, and below them how long each lasted. It opens on the phase the market is in, with today's line in colour and
// today's day marked on the lengths; the other phase shows its past ones, the most recent picked out. The phase switches
// by itself when the market does. Pointing at a line or a bar names it and lights both. What happened, not what comes
// next.

const pathD = (pts, x, y) => pts.map((p, i) => `${i ? "L" : "M"}${x(p.d).toFixed(1)},${y(p.v).toFixed(1)}`).join("");

export default function CyclesChart({ rows, highlight = null }) {
  const [box, W] = useWidth(900);
  const [pick, setPick] = useState(null);           // "down" | "up", or null for the phase under way
  const [hovOwn, setHov] = useState(null);         // index into past, pointed at here
  const [tip, setTip] = useState(null);            // { x, y, lines }
  const c = useMemo(() => marketCycles(rows, undefined, pick), [rows, pick]);
  const kinds = c?.now ? CYCOPY.kinds.map(k => (k.key === c.now ? { ...k, label: `${k.label} · now` } : k)) : CYCOPY.kinds;
  const tabs = <Tabs small label="Phase" items={kinds} value={c?.kind || "down"} onChange={k => { setPick(k); setHov(null); setTip(null); }} />;
  if (!c || !c.past.length) return <div ref={box} className="cyc">{tabs}</div>;
  // A past one pointed at in the tiles above lights here too, when this chart shows that phase.
  const fromTiles = highlight && highlight.kind === c.kind ? c.past.findIndex(p => p.start === highlight.start) : -1;
  const hov = hovOwn != null ? hovOwn : fromTiles >= 0 ? fromTiles : null;
  const phone = W < 560;
  const padL = 40, padR = phone ? 12 : 160, padT = 14, padB = 24;
  const H = phone ? 240 : 340;
  const today = c.today;
  const maxD = Math.max(today ? today.days : 0, ...c.past.map(p => p.days + 1));
  const xMax = Math.ceil(maxD / 30) * 30;
  const vMax = Math.max(0.6, ...c.past.flatMap(p => p.path.map(q => q.v)), ...(today ? today.path.map(q => q.v) : []));
  const yTop = Math.min(1, Math.ceil(vMax * 10) / 10);
  const x = d => padL + (d / xMax) * (W - padL - padR);      // 0 at the axis: a bar's length reads in days
  const y = v => padT + (1 - v / yTop) * (H - padT - padB);
  const ticksX = [];
  for (let d = 30; d <= xMax; d += 30) ticksX.push(d);
  const ticksY = [0, 0.2, 0.4, 0.55, 0.8, 1].filter(v => v <= yTop);
  const fmt = d => dayDate(d);
  const point = (e, lines) => {
    const r = box.current?.getBoundingClientRect();
    if (r) setTip({ x: e.clientX - r.left, y: e.clientY - r.top, lines });
  };
  const clear = () => { setHov(null); setTip(null); };
  const tLast = today?.path[today.path.length - 1];
  const latest = today ? null : c.latest;           // without today's line, the most recent past one is picked out
  const lp = latest != null ? c.past[latest] : null;
  const lEnd = lp?.path[lp.path.length - 1];
  const order = c.past.map((p, i) => i).sort((a, b) => c.past[b].days - c.past[a].days);
  const rowH = phone ? 16 : 18;
  const HB = order.length * rowH + 30;
  const labelOf = p => `${p.days} days · ${monthYear(p.start)}`;
  const cls = (base, i) => [base, hov === i && "is-hov", hov != null && hov !== i && "is-dim", latest === i && "is-last"].filter(Boolean).join(" ");

  return <div ref={box} className="cyc" onPointerLeave={clear}>
    <div className="cyc-head">
      <span>{CYCOPY.head(c.kind)}<Info title={CYCOPY.tab} paras={CYCOPY.pop(c.kind)} /></span>
      {tabs}
    </div>
    <svg className="cyc-svg" width={W} height={H} role="img"
      aria-label={`${CYCOPY.head(c.kind)}: ${c.past.length} past${today ? `, ${CYCOPY.sooner(c.sooner, c.past.length, c.kind)}; today day ${today.days}` : ""}`}>
      {ticksY.map(v => <g key={v}>
        <line className={v === 0.55 ? "cyc-line55" : "cyc-grid"} x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} />
        <text className="cyc-tick" x={padL - 6} y={y(v) + 4} textAnchor="end">{Math.round(100 * v)}%</text>
      </g>)}
      {!phone && <text className="cyc-tick" x={W - padR + 6} y={y(0.55) + 4}>{CYCOPY.end(c.kind)}</text>}
      <text className="cyc-tick" x={x(0)} y={H - 6} textAnchor="start">{CYCOPY.dayAxis}</text>
      {ticksX.map(d => <text key={d} className="cyc-tick" x={x(d)} y={H - 6} textAnchor="middle">{d}</text>)}
      {c.past.map((p, i) => <g key={p.start} className={cls("cyc-past", i)}>
        <path d={pathD(p.path, x, y)} />
        {p.path.length > 0 && <circle cx={x(p.path[p.path.length - 1].d)} cy={y(p.path[p.path.length - 1].v)} r={3} />}
        <path className="cyc-hit" d={pathD(p.path, x, y)}
          onPointerMove={e => { setHov(i); point(e, CYCOPY.tip(p, c.kind, fmt)); }} />
      </g>)}
      {lEnd && !phone && <text className="cyc-last-label" x={x(lEnd.d) + 8} y={y(lEnd.v) + (c.kind === "up" ? 14 : -8)}>
        {CYCOPY.latest(lp, monthYear)}</text>}
      {today && <g className="cyc-today">
        <path d={pathD(today.path, x, y)} />
        {tLast && <circle cx={x(tLast.d)} cy={y(tLast.v)} r={5} />}
        {tLast && <text className="cyc-today-label" x={x(tLast.d) + 9} y={y(tLast.v) + 4}>
          {CYCOPY.today(c.kind, today.days)} · {Math.round(100 * tLast.v)}%</text>}
      </g>}
    </svg>

    <div className="cyc-head cyc-head-2"><span>{CYCOPY.lasted}</span>
      {today && <em>{CYCOPY.sooner(c.sooner, c.past.length, c.kind)}</em>}</div>
    <svg className="cyc-svg" width={W} height={HB} role="img" aria-label={`${CYCOPY.lasted}: ${order.map(i => labelOf(c.past[i])).join(", ")}`}>
      {ticksX.map(d => <line key={d} className="cyc-grid" x1={x(d)} x2={x(d)} y1={4} y2={HB - 22} />)}
      {order.map((i, k) => {
        const p = c.past[i];
        const yy = 6 + k * rowH;
        return <g key={p.start} className={cls("cyc-bar", i)}
          onPointerMove={e => { setHov(i); point(e, CYCOPY.tip(p, c.kind, fmt)); }}>
          <rect className="cyc-bar-hit" x={padL} y={yy - 2} width={W - padL - padR} height={rowH} />
          <rect x={padL} y={yy + 2} width={Math.max(2, x(p.days) - padL)} height={rowH - 8} rx={2} />
          {!phone && <text className="cyc-bar-label" x={x(p.days) + 6} y={yy + rowH / 2 + 2}>{labelOf(p)}</text>}
        </g>;
      })}
      {today && <line className="cyc-today-mark" x1={x(today.days)} x2={x(today.days)} y1={0} y2={HB - 22} />}
      <text className="cyc-tick" x={x(0)} y={HB - 6} textAnchor="start">days</text>
      {ticksX.map(d => <text key={d} className="cyc-tick" x={x(d)} y={HB - 6} textAnchor="middle">{d}</text>)}
    </svg>
    {tip && <div className="mh-tip mh-hover-tip cyc-tip" role="status"
      style={{ left: Math.max(4, Math.min(W - 212, tip.x + 12)), top: tip.y + 14, width: 200 }}>
      <b>{tip.lines[0]}</b>{tip.lines.slice(1).map(l => <span key={l} className="mh-tip-row"><em>{l}</em></span>)}
    </div>}
  </div>;
}
