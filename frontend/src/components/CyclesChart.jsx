import { useMemo, useState } from "react";
import { useWidth } from "./MarketHistoryChart.jsx";
import { Info } from "./MarketHistorySections.jsx";
import { CYCOPY, marketCycles } from "../utils/marketCycles.js";
import { dayDate, monthYear } from "../utils/marketHistory.js";

// The Cycles tab: every past broad downturn (or broad uptrend) as a line of the share of coins in uptrend from its
// first day, today's in colour, and below them how long each lasted with today's day marked. Pointing at a line or a
// bar names it and lights both. What happened, not what comes next.

const pathD = (pts, x, y) => pts.map((p, i) => `${i ? "L" : "M"}${x(p.d).toFixed(1)},${y(p.v).toFixed(1)}`).join("");

export default function CyclesChart({ rows }) {
  const [box, W] = useWidth(900);
  const [hov, setHov] = useState(null);            // index into past, or "today"
  const [tip, setTip] = useState(null);            // { x, y, lines }
  const c = useMemo(() => marketCycles(rows), [rows]);
  if (!c || !c.past.length) return <div ref={box} className="cyc" />;
  const phone = W < 560;
  const padL = 40, padR = phone ? 12 : 120, padT = 14, padB = 24;
  const H = phone ? 240 : 340;
  const maxD = Math.max(c.today.days, ...c.past.map(p => p.days + 1));
  const xMax = Math.ceil(maxD / 30) * 30;
  const vMax = Math.max(0.6, ...c.past.flatMap(p => p.path.map(q => q.v)), ...c.today.path.map(q => q.v));
  const yTop = Math.min(1, Math.ceil(vMax * 10) / 10);
  const x = d => padL + (d / xMax) * (W - padL - padR);      // 0 at the axis: a bar's length reads in days
  const y = v => padT + (1 - v / yTop) * (H - padT - padB);
  const ticksX = [];
  for (let d = 30; d <= xMax; d += 30) ticksX.push(d);
  const ticksY = [0, 0.2, 0.4, 0.55, 0.8].filter(v => v <= yTop);
  const fmt = d => dayDate(d);
  const point = (e, lines) => {
    const r = box.current?.getBoundingClientRect();
    if (r) setTip({ x: e.clientX - r.left, y: e.clientY - r.top, lines });
  };
  const clear = () => { setHov(null); setTip(null); };
  const tLast = c.today.path[c.today.path.length - 1];
  const order = c.past.map((p, i) => i).sort((a, b) => c.past[b].days - c.past[a].days);
  const rowH = phone ? 16 : 18;
  const HB = order.length * rowH + 30;
  const labelOf = p => `${p.days} days · ${monthYear(p.start)}`;

  return <div ref={box} className="cyc" onPointerLeave={clear}>
    <div className="cyc-head">
      <span>{CYCOPY.head(c.kind)}<Info title={CYCOPY.tab} paras={CYCOPY.pop(c.kind)} /></span>
    </div>
    <svg className="cyc-svg" width={W} height={H} role="img"
      aria-label={`${CYCOPY.head(c.kind)}: ${c.past.length} past, ${CYCOPY.sooner(c.sooner, c.past.length, c.kind)}; today day ${c.today.days}`}>
      {ticksY.map(v => <g key={v}>
        <line className={v === 0.55 ? "cyc-line55" : "cyc-grid"} x1={padL} x2={W - padR} y1={y(v)} y2={y(v)} />
        <text className="cyc-tick" x={padL - 6} y={y(v) + 4} textAnchor="end">{Math.round(100 * v)}%</text>
      </g>)}
      {!phone && <text className="cyc-tick" x={W - padR + 6} y={y(0.55) + 4}>{CYCOPY.end(c.kind)}</text>}
      <text className="cyc-tick" x={x(0)} y={H - 6} textAnchor="start">{CYCOPY.dayAxis}</text>
      {ticksX.map(d => <text key={d} className="cyc-tick" x={x(d)} y={H - 6} textAnchor="middle">{d}</text>)}
      {c.past.map((p, i) => <g key={p.start} className={hov === i ? "cyc-past is-hov" : hov != null ? "cyc-past is-dim" : "cyc-past"}>
        <path d={pathD(p.path, x, y)} />
        {p.path.length > 0 && <circle cx={x(p.path[p.path.length - 1].d)} cy={y(p.path[p.path.length - 1].v)} r={3} />}
        <path className="cyc-hit" d={pathD(p.path, x, y)}
          onPointerMove={e => { setHov(i); point(e, CYCOPY.tip(p, c.kind, fmt)); }} />
      </g>)}
      <g className="cyc-today">
        <path d={pathD(c.today.path, x, y)} />
        {tLast && <circle cx={x(tLast.d)} cy={y(tLast.v)} r={5} />}
        {tLast && <text className="cyc-today-label" x={x(tLast.d) + 9} y={y(tLast.v) + 4}>
          {CYCOPY.today(c.kind, c.today.days)} · {Math.round(100 * tLast.v)}%</text>}
      </g>
    </svg>

    <div className="cyc-head cyc-head-2"><span>{CYCOPY.lasted}</span><em>{CYCOPY.sooner(c.sooner, c.past.length, c.kind)}</em></div>
    <svg className="cyc-svg" width={W} height={HB} role="img" aria-label={`${CYCOPY.lasted}: ${order.map(i => labelOf(c.past[i])).join(", ")}`}>
      {ticksX.map(d => <line key={d} className="cyc-grid" x1={x(d)} x2={x(d)} y1={4} y2={HB - 22} />)}
      {order.map((i, k) => {
        const p = c.past[i];
        const yy = 6 + k * rowH;
        return <g key={p.start} className={hov === i ? "cyc-bar is-hov" : "cyc-bar"}
          onPointerMove={e => { setHov(i); point(e, CYCOPY.tip(p, c.kind, fmt)); }}>
          <rect className="cyc-bar-hit" x={padL} y={yy - 2} width={W - padL - padR} height={rowH} />
          <rect x={padL} y={yy + 2} width={Math.max(2, x(p.days) - padL)} height={rowH - 8} rx={2} />
          {!phone && <text className="cyc-bar-label" x={x(p.days) + 6} y={yy + rowH / 2 + 2}>{labelOf(p)}</text>}
        </g>;
      })}
      <line className="cyc-today-mark" x1={x(c.today.days)} x2={x(c.today.days)} y1={0} y2={HB - 22} />
      <text className="cyc-tick" x={x(0)} y={HB - 6} textAnchor="start">days</text>
      {ticksX.map(d => <text key={d} className="cyc-tick" x={x(d)} y={HB - 6} textAnchor="middle">{d}</text>)}
    </svg>
    {tip && <div className="mh-tip mh-hover-tip cyc-tip" role="status"
      style={{ left: Math.max(4, Math.min(W - 212, tip.x + 12)), top: tip.y + 14, width: 200 }}>
      <b>{tip.lines[0]}</b>{tip.lines.slice(1).map(l => <span key={l} className="mh-tip-row"><em>{l}</em></span>)}
    </div>}
  </div>;
}
