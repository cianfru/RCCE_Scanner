import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { slotBars, count } from "../utils/coinPositioning.js";
import { usd } from "../utils/cohorts.js";
import { COIN_GROUPS } from "../utils/traderGroups.js";

const SLOT_S = 1800;
const SLOTS = 48;                 // the last 24 hours
const H4 = 4 * 3600;
const hhmm = t => new Date(t * 1000).toISOString().slice(11, 16);

// Under the coin chart: the last 24 hours of the selected group, one bar pair per half hour
// (long above the line, short below), the newest on the right. Dashed lines mark the 4-hour
// closes. The values show while a half hour is pointed at or tapped; the bar below has the latest.
export default function RecentStrip({ data, failed, group, measure }) {
  const box = useRef(null);
  const [W, setW] = useState(0);
  const [hover, setHover] = useState(null);           // the hovered slot's start time
  useLayoutEffect(() => {
    if (!box.current) return undefined;
    setW(Math.round(box.current.clientWidth));
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const series = data?.groups?.[group];
  const endT = useMemo(() => {
    const ts = Object.values(data?.groups || {}).flatMap(g => g.t || []);
    return Math.max(Math.floor(Date.now() / 1000), ...ts);
  }, [data]);
  const bars = useMemo(() => slotBars(series, measure, SLOT_S, endT, SLOTS), [series, measure, endT]);
  const filled = bars.filter(b => b.long != null);
  const peak = Math.max(0, ...filled.map(b => Math.max(b.long, b.short)));
  const top = peak || 1;
  const fmt = measure === "usd" ? usd : count;
  const tick = peak > 0 ? fmt(peak) : "";
  const name = COIN_GROUPS.find(g => g.key === group)?.name;

  const phone = W > 0 && W < 520;
  // The scale sits on the right, as the chart's scales do; its label (10px mono, about 6.2px a
  // character) sets the margin, so "$111.8M" is never cut.
  const H = phone ? 58 : 66, padL = 6, padR = tick ? Math.max(28, Math.ceil(tick.length * 6.2) + 8) : 6, labelH = 14;
  const plotW = Math.max(1, W - padL - padR);
  const slotW = plotW / SLOTS;
  const mid = (H - labelH) / 2;
  const half = mid - 3;
  const x = i => padL + i * slotW;
  const closes = bars.map((b, i) => ({ i, t: b.t })).filter(b => b.t % H4 === 0);
  const hi = hover == null ? -1 : bars.findIndex(b => b.t === hover);
  const shown = hi >= 0 ? bars[hi] : null;

  let read = " ";                                     // keeps the line's height when empty
  if (!data) read = <span className="chart-pos-dim">{failed ? "Could not load the readings" : "Loading…"}</span>;
  else if (!filled.length) read = <span className="chart-pos-dim">Not recorded yet</span>;
  else if (shown && shown.long == null) read = <span className="chart-pos-dim">No reading · {hhmm(shown.t)} UTC</span>;
  else if (shown) read = <><b className="chart-pos-l">{fmt(shown.long)}</b> long<span className="chart-pos-sep">·</span>
    <b className="chart-pos-s">{fmt(shown.short)}</b> short<span className="chart-pos-sep">·</span>{hhmm(shown.at)} UTC</>;

  const onMove = e => {
    const r = e.currentTarget.getBoundingClientRect();
    const i = Math.floor((e.clientX - r.left - padL) / slotW);
    setHover(i >= 0 && i < SLOTS ? bars[i].t : null);
  };
  const clear = () => setHover(null);

  return <div className="chart-recent">
    <div className="chart-recent-head">
      <span className="chart-recent-title">24h</span>
      <span className="chart-pos-read" aria-live="off">{read}</span>
    </div>
    <div ref={box} className="chart-recent-plot">
      {W > 0 && <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img"
        aria-label={`${name}: ${measure === "usd" ? "dollars" : "wallets"} long above the line and short below, each half hour over the last 24 hours`}
        onPointerMove={onMove} onPointerDown={onMove} onPointerCancel={clear}
        onPointerLeave={e => { if (e.pointerType === "mouse") clear(); }}>
        <rect className="chart-recent-now" x={x(SLOTS - 1)} y={0} width={slotW} height={H - labelH} />
        {closes.map(c => <line key={c.t} className="chart-recent-close" x1={x(c.i)} x2={x(c.i)} y1={0} y2={H - labelH} />)}
        {bars.map((b, i) => b.long == null ? null : <g key={b.t} opacity={hi >= 0 && hi !== i ? 0.55 : 1}>
          <rect className="chart-recent-l" x={x(i) + slotW * 0.14} width={Math.max(1, slotW * 0.72)}
            y={mid - (b.long / top) * half} height={(b.long / top) * half} />
          <rect className="chart-recent-s" x={x(i) + slotW * 0.14} width={Math.max(1, slotW * 0.72)}
            y={mid} height={(b.short / top) * half} />
        </g>)}
        <line className="chart-recent-zero" x1={padL} x2={W - padR} y1={mid} y2={mid} />
        {tick && <text className="chart-recent-tick" x={W - padR + 5} y={9} textAnchor="start">{tick}</text>}
        {tick && <text className="chart-recent-tick" x={W - padR + 5} y={H - labelH - 1} textAnchor="start">{tick}</text>}
        {closes.map(c => <text key={c.t} className="chart-recent-tick" x={Math.min(Math.max(x(c.i), 16), W - padR - 16)}
          y={H - 2} textAnchor="middle">{hhmm(c.t)}</text>)}
        {hi >= 0 && <rect className="chart-recent-hover" x={x(hi)} y={0} width={slotW} height={H - labelH} />}
      </svg>}
    </div>
  </div>;
}
