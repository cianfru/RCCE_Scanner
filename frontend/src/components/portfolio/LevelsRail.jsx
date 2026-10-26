// The LEVELS cell: one position's levels on one log price line (utils/portfolio/rail.js), and the
// end block under TO LIQ: distance to liquidation and one flag.
import { useId, useRef } from "react";
import useElementWidth from "../../hooks/useElementWidth.js";
import { railModel } from "../../utils/portfolio/rail.js";
import { distTone, flagsOf } from "../../utils/portfolio/checks.js";
import { px, pct, atrNum } from "../../utils/portfolio/format.js";
import { Hover, LiqGlyph, useFlash, textWidth } from "./parts.jsx";
import { CHECKS, RAIL, ROWS, STRIP } from "./copy.js";

const Y = 22;

export function railInput(row) {
  const ctx = row.ctx;
  const mine = ctx?.traders?.[row.side];
  return {
    isLong: row.isLong, mark: row.mark, entry: row.entry, liq: row.liq, stops: row.ordersRead ? row.stops : [], tps: row.tps,
    band: ctx?.band || null, trend: ctx?.trend ?? null, tradersEntry: mine && mine.n >= 3 ? mine.median_entry : null,
  };
}

// Prices in the card at the mark's own precision (11.425 → 9.765, not 9.7646).
const decimalsOf = s => (s.includes(".") ? s.split(".")[1].length : 0);
export const pxAt = (v, mark) => {
  if (v == null || !Number.isFinite(v)) return "—";
  const d = decimalsOf(px(mark));
  return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
};

function LevelCard({ row }) {
  const ctx = row.ctx, m = row.mark;
  const P = v => pxAt(v, m);
  const rel = v => (v && m ? pct((v / m - 1) * 100, { sign: true }) : "");
  const r = (k, v, extra) => <div className="pf-pop-row" key={k}><span>{k}</span><b className="m">{v}{extra ? <span className="pf-t3"> {extra}</span> : null}</b></div>;
  // A ladder: "×30 11.686–12.40 +2.3%" (nearest first, then the farthest; the distance is the nearest's).
  const ladder = (k, list) => {
    if (!list.length) return null;
    if (list.length === 1) return r(k, P(list[0].px), rel(list[0].px));
    const far = list.reduce((a, b) => (Math.abs(b.px - m) > Math.abs(a.px - m) ? b : a));
    return r(k, <><span className="pf-t3">×{list.length} </span>{P(list[0].px)}–{P(far.px)}</>, rel(list[0].px));
  };
  const stops = row.ordersRead ? row.stops : [];
  const t = ctx?.traders;
  const side = (word, s, cls) => (s?.median_entry ? <span><span className="pf-t3">{word} </span>{P(s.median_entry)} <span className={cls}>({s.n})</span></span> : null);
  return <div className="pf-pop">
    {r(RAIL.mark, P(m))}
    {r(RAIL.entry, P(row.entry), rel(row.entry))}
    {row.liq ? r(RAIL.liq, <><LiqGlyph h={10} /> {P(row.liq)}</>, rel(row.liq)) : r(RAIL.liq, <span className="pf-t3">{"—"}</span>)}
    {stops.length ? ladder(RAIL.sl, stops) : r(RAIL.sl, <span className="pf-t3">{RAIL.none}</span>)}
    {ladder(RAIL.tp, row.tps)}
    {ctx?.band && r(RAIL.band, `${P(ctx.band.lo)}–${P(ctx.band.hi)}`, RAIL.bandState[ctx.band.state] || ctx.band.state)}
    {ctx?.trend ? r(RAIL.trend, P(ctx.trend), rel(ctx.trend)) : null}
    {t && (t.long.median_entry || t.short.median_entry) && r(RAIL.tradersEntry, <>
      {side(ROWS.long, t.long, "pf-long")}{t.long.median_entry && t.short.median_entry ? <span className="pf-sep"> · </span> : null}{side(ROWS.short, t.short, "pf-short")}</>)}
    {ctx?.swing && <>{r(RAIL.swingLow, P(ctx.swing.lo), rel(ctx.swing.lo))}{r(RAIL.swingHigh, P(ctx.swing.hi), rel(ctx.swing.hi))}</>}
    {ctx?.atr_1d ? r(RAIL.atr, P(ctx.atr_1d), pct((ctx.atr_1d / m) * 100)) : null}
  </div>;
}

const measure = (text, size, kind) => textWidth(text, size, kind === "liq" || kind === "sl" ? "sans" : "mono", kind === "mark" ? 500 : 400);

export function RailSvg({ row, width, height = 44, labels = true, compact = false, visitMark = null }) {
  const hatchId = useId().replace(/:/g, "");
  const flash = useFlash(row.mark);
  if (!width || width < 40) return <svg width="100%" height={height} aria-hidden="true" />;
  const model = railModel({ ...railInput(row), visitMark, width, compact, text: { mark: px(row.mark) }, measure });
  const { m } = model;
  const y = compact ? 21 : Y;
  const pnl = row.upnl >= 0 ? "var(--t-profit)" : "var(--t-loss)";
  const tri = (x, up) => up ? `M${x - 3.5},${y - 5} L${x + 3.5},${y - 5} L${x},${y - 11} Z` : `M${x - 3.5},${y + 5} L${x + 3.5},${y + 5} L${x},${y + 11} Z`;
  const base = { mark: y - (compact ? 9 : 11), liq: y + (compact ? 13 : 19), sl: y + 19, tpMore: y - 5, slMore: y + 11 };
  return <svg className="pf-rail" width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
    <defs>
      <pattern id={hatchId} width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <line x1="0" y1="0" x2="0" y2="4" stroke="var(--rd-red)" strokeOpacity=".3" strokeWidth="2" />
      </pattern>
    </defs>
    <line x1="0" x2={width} y1={y} y2={y} className="pf-r-track" />
    {model.hatch && <rect x={model.hatch.x0} y={y - 5} width={Math.max(0, model.hatch.x1 - model.hatch.x0)} height="10" fill={`url(#${hatchId})`} />}
    {m.band && <g className="pf-r-band"><rect x={m.band.x0} y={y - 5} width={Math.max(1, m.band.x1 - m.band.x0)} height="10" />
      <line x1={m.band.x0} x2={m.band.x0} y1={y - 5} y2={y + 5} /><line x1={m.band.x1} x2={m.band.x1} y1={y - 5} y2={y + 5} /></g>}
    {model.breakX != null && <g className="pf-r-break"><line x1={model.breakX - 5} y1={y + 6} x2={model.breakX - 1} y2={y - 6} /><line x1={model.breakX + 1} y1={y + 6} x2={model.breakX + 5} y2={y - 6} /></g>}
    {m.visit != null && <rect x={m.visit - 0.5} y={y - 5} width="1" height="10" className="pf-r-visit" />}
    {m.trend != null && <line x1={m.trend} x2={m.trend} y1={y - 6} y2={y + 6} className="pf-r-trend" />}
    {m.traders != null && <path d={`M${m.traders},${y - 11.5} L${m.traders + 2.5},${y - 9} L${m.traders},${y - 6.5} L${m.traders - 2.5},${y - 9} Z`} className="pf-r-traders" fill={row.isLong ? "var(--rd-long)" : "var(--rd-short)"} />}
    {m.liq != null && <rect x={m.liq - 1} y={y - 7} width="2" height="14" className="pf-r-liq" />}
    {m.entry != null && m.mark != null && <line x1={m.entry} x2={m.mark} y1={y} y2={y} stroke={pnl} strokeWidth="3" />}
    {m.stop != null && <path d={tri(m.stop, false)} className="pf-r-sl" />}
    {m.tp != null && <path d={tri(m.tp, true)} className="pf-r-tp" />}
    {m.entry != null && <circle cx={m.entry} cy={y} r="3.5" className="pf-r-entry" />}
    {m.mark != null && <rect x={m.mark - 1} y={y - 8} width="2" height="16" className="pf-r-mark" />}
    {labels && model.labels.map(l => {
      if (l.kind === "mark") return <text key="m" x={l.x0} y={base.mark} className={`pf-r-px${flash ? ` pf-flash-${flash}` : ""}`}>{l.text}</text>;
      if (l.kind === "tpMore" || l.kind === "slMore") return <text key={l.kind} x={l.x0} y={base[l.kind]} className="pf-r-more">{l.text}</text>;
      return <text key={l.kind} x={l.x0} y={base[l.kind]} className="pf-r-lab">{l.kind === "liq" ? RAIL.liq : RAIL.sl}</text>;
    })}
  </svg>;
}

// "68% · 14 ATR" (whole ATRs from 10); "15%" where there is no ATR.
export function distanceText(dist) {
  if (!dist) return "—";
  return dist.atr != null ? `${pct(dist.pct, { digits: 0 })} · ${atrNum(dist.atr)} ${STRIP.atr}` : pct(dist.pct, { digits: 0 });
}

// The distance, red with the liquidation glyph when it is close.
export function Distance({ dist, className = "" }) {
  const tone = distTone(dist);
  return <span className={`m pf-dist pf-tone-${dist ? tone : "text4"} ${className}`}>{tone === "red" && <LiqGlyph h={11} />}{distanceText(dist)}</span>;
}

export function FlagLine({ row, quietNoStop = false }) {
  const f = flagsOf(row.checks, { quietNoStop });
  if (!f.first) return <span className="pf-flag" />;
  const cls = f.first === "stoppastliq" ? "pf-red" : f.first === "nostop" ? "pf-t4" : "pf-t2";
  const word = f.first === "nostop" ? RAIL.noStop : CHECKS[f.first].label;
  return <span className="pf-flag" title={[f.first, ...f.more].map(k => CHECKS[k].label).join(", ")}>
    {f.first === "stoppastliq" && <LiqGlyph h={10} />}<span className={cls}>{word}</span>{f.more.length > 0 && <span className="pf-t4"> +{f.more.length}</span>}
  </span>;
}

export default function LevelsRail({ row, quietNoStop, visitMark }) {
  const ref = useRef(null);
  const w = useElementWidth(ref);
  return <div className="pf-levels">
    <Hover className="pf-rail-box" content={<LevelCard row={row} />} width={340}>
      <div ref={ref} className="pf-rail-measure"><RailSvg row={row} width={w} visitMark={visitMark} /></div>
    </Hover>
    <div className="pf-end">
      <Distance dist={row.dist} />
      <FlagLine row={row} quietNoStop={quietNoStop} />
    </div>
  </div>;
}
