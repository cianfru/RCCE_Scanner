// The LEVELS cell: one position's levels on one log price line (utils/portfolio/rail.js), and the
// end block: distance to liquidation and one flag.
import { useId, useRef } from "react";
import useElementWidth from "../../hooks/useElementWidth.js";
import { railModel } from "../../utils/portfolio/rail.js";
import { distTone, flagsOf } from "../../utils/portfolio/checks.js";
import { px, pct } from "../../utils/portfolio/format.js";
import { Hover, useFlash } from "./parts.jsx";
import { CHECKS, RAIL, STRIP } from "./copy.js";

const Y = 22;

export function railInput(row) {
  const ctx = row.ctx;
  const mine = ctx?.traders?.[row.side];
  return {
    isLong: row.isLong, mark: row.mark, entry: row.entry, liq: row.liq, stops: row.ordersRead ? row.stops : [], tps: row.tps,
    band: ctx?.band || null, trend: ctx?.trend ?? null, tradersEntry: mine && mine.n >= 3 ? mine.median_entry : null,
  };
}

function LevelCard({ row }) {
  const ctx = row.ctx, m = row.mark;
  const rel = v => (v && m ? pct((v / m - 1) * 100, { sign: true }) : "");
  const r = (k, v, extra) => <div className="pf-pop-row" key={k + v}><span>{k}</span><b className="m">{px(v)} <span className="pf-t3">{extra ?? rel(v)}</span></b></div>;
  const t = ctx?.traders;
  return <div className="pf-pop">
    {r(RAIL.mark, m, "")}
    {r(RAIL.entry, row.entry)}
    {row.liq ? r(RAIL.liq, row.liq) : null}
    {(row.ordersRead ? row.stops : []).map(s => r(RAIL.sl, s.px))}
    {row.tps.slice(0, 3).map(s => r(RAIL.tp, s.px))}
    {row.tps.length > 3 && <div className="pf-pop-row"><span className="pf-t3">{RAIL.tp} +{row.tps.length - 3}</span></div>}
    {ctx?.band && <div className="pf-pop-row"><span>{RAIL.band}</span><b className="m">{px(ctx.band.lo)}–{px(ctx.band.hi)} <span className="pf-t3">{RAIL.bandState[ctx.band.state] || ctx.band.state}</span></b></div>}
    {ctx?.trend ? r(RAIL.trend, ctx.trend) : null}
    {t && (t.long.median_entry || t.short.median_entry) && <div className="pf-pop-row"><span>{RAIL.tradersEntry}</span>
      <b className="m"><span className="pf-long">{px(t.long.median_entry)} <span className="pf-t3">{t.long.n}</span></span> · <span className="pf-short">{px(t.short.median_entry)} <span className="pf-t3">{t.short.n}</span></span></b></div>}
    {ctx?.swing && <>{r(RAIL.swingLow, ctx.swing.lo)}{r(RAIL.swingHigh, ctx.swing.hi)}</>}
    {ctx?.atr_1d ? <div className="pf-pop-row"><span>{RAIL.atr}</span><b className="m">{px(ctx.atr_1d)} <span className="pf-t3">{pct((ctx.atr_1d / m) * 100)}</span></b></div> : null}
  </div>;
}

export function RailSvg({ row, width, height = 44, labels = true, compact = false }) {
  const hatchId = useId().replace(/:/g, "");
  const flash = useFlash(row.mark);
  if (!width || width < 40) return <svg width="100%" height={height} aria-hidden="true" />;
  const model = railModel({ ...railInput(row), width });
  const { m } = model;
  const y = compact ? 19 : Y;
  const pnl = row.upnl >= 0 ? "var(--t-profit)" : "var(--t-loss)";
  const tri = (x, up) => up ? `M${x - 3.5},${y - 5} L${x + 3.5},${y - 5} L${x},${y - 11} Z` : `M${x - 3.5},${y + 5} L${x + 3.5},${y + 5} L${x},${y + 11} Z`;
  return <svg className="pf-rail" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
    <defs>
      <pattern id={hatchId} width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <line x1="0" y1="0" x2="0" y2="4" stroke="var(--rd-red)" strokeOpacity=".25" strokeWidth="2" />
      </pattern>
    </defs>
    <line x1="0" x2={width} y1={y} y2={y} className="pf-r-track" />
    {model.hatch && <rect x={model.hatch.x0} y={y - 5} width={Math.max(0, model.hatch.x1 - model.hatch.x0)} height="10" fill={`url(#${hatchId})`} />}
    {m.band && <g className="pf-r-band"><rect x={m.band.x0} y={y - 5} width={Math.max(1, m.band.x1 - m.band.x0)} height="10" />
      <line x1={m.band.x0} x2={m.band.x0} y1={y - 5} y2={y + 5} /><line x1={m.band.x1} x2={m.band.x1} y1={y - 5} y2={y + 5} /></g>}
    {model.breakX != null && <g className="pf-r-break"><line x1={model.breakX - 5} y1={y + 6} x2={model.breakX - 1} y2={y - 6} /><line x1={model.breakX + 1} y1={y + 6} x2={model.breakX + 5} y2={y - 6} /></g>}
    {m.trend != null && <line x1={m.trend} x2={m.trend} y1={y - 6} y2={y + 6} className="pf-r-trend" />}
    {m.traders != null && <line x1={m.traders} x2={m.traders} y1={y - 6} y2={y + 6} className="pf-r-traders" stroke={row.isLong ? "var(--rd-long)" : "var(--rd-short)"} />}
    {m.liq != null && <rect x={m.liq - 1} y={y - 7} width="2" height="14" className="pf-r-liq" />}
    {m.entry != null && m.mark != null && <line x1={m.entry} x2={m.mark} y1={y} y2={y} stroke={pnl} strokeWidth="3" />}
    {m.stop != null && <path d={tri(m.stop, false)} className="pf-r-sl" />}
    {m.stop != null && model.moreStops > 0 && !compact && <text x={m.stop + 6} y={y + 11} className="pf-r-more">+{model.moreStops}</text>}
    {m.tp != null && <path d={tri(m.tp, true)} className="pf-r-tp" />}
    {m.tp != null && model.moreTps > 0 && !compact && <text x={m.tp + 6} y={y - 6} className="pf-r-more">+{model.moreTps}</text>}
    {m.entry != null && <circle cx={m.entry} cy={y} r="3.5" className="pf-r-entry" />}
    {m.mark != null && <rect x={m.mark - 1} y={y - 8} width="2" height="16" className="pf-r-mark" />}
    {labels && model.labels.filter(l => !compact || l.kind !== "sl").map(l => {
      if (l.kind === "mark") {
        const anchor = l.x < 24 ? "start" : l.x > width - 24 ? "end" : "middle";
        return <text key="m" x={l.x} y={y - (compact ? 10 : 11)} textAnchor={anchor} className={`pf-r-px${flash ? ` pf-flash-${flash}` : ""}`}>{px(row.mark)}</text>;
      }
      const anchor = l.x < 14 ? "start" : l.x > width - 14 ? "end" : "middle";
      return <text key={l.kind} x={l.x} y={y + (compact ? 12.5 : 19)} textAnchor={anchor} className={`pf-r-lab${compact ? " pf-r-lab-sm" : ""}`}>{l.kind === "liq" ? RAIL.liq : RAIL.sl}</text>;
    })}
  </svg>;
}

export function distanceText(dist) {
  if (!dist) return "—";
  return dist.atr != null ? `${pct(dist.pct, { digits: 0 })} · ${dist.atr.toFixed(1)} ${STRIP.atr}` : pct(dist.pct, { digits: 0 });
}

export function FlagLine({ row }) {
  const f = flagsOf(row.checks);
  if (!f.first) return <span className="pf-flag" />;
  const cls = f.first === "stoppastliq" ? "pf-red" : f.first === "nostop" ? "pf-t3" : "pf-t1";
  const word = f.first === "nostop" ? RAIL.noStop : CHECKS[f.first].label;
  return <span className="pf-flag" title={[f.first, ...f.more].map(k => CHECKS[k].label).join(", ")}>
    <span className={cls}>{word}</span>{f.more.length > 0 && <span className="pf-t4"> +{f.more.length}</span>}
  </span>;
}

export default function LevelsRail({ row }) {
  const ref = useRef(null);
  const w = useElementWidth(ref);
  const tone = distTone(row.dist);
  return <div className="pf-levels">
    <Hover className="pf-rail-box" content={<LevelCard row={row} />} width={260}>
      <div ref={ref} className="pf-rail-measure"><RailSvg row={row} width={w} /></div>
    </Hover>
    <div className="pf-end">
      <span className={`m pf-dist pf-tone-${tone}`}>{distanceText(row.dist)}</span>
      <FlagLine row={row} />
    </div>
  </div>;
}
