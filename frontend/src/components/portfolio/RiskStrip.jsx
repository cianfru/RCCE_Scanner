// B1. The risk strip: one glass card, four cells (Equity, Liquidation, Exposure, Reflex). Each has a
// one-word label with its (i), one headline and one visual.
import { useMemo } from "react";
import { Label, Hover, Tween, LiqGlyph, pnlClass } from "./parts.jsx";
import BookThumb from "./BookThumb.jsx";
import { usd, pct, atrNum } from "../../utils/portfolio/format.js";
import { distRed, nearestLiq, reflexShares } from "../../utils/portfolio/checks.js";
import { worstMargin, PARTS } from "../../utils/portfolio/totals.js";
import { displayName } from "../../utils/portfolio/displayNames.js";
import { INFO, LABELS, STRIP, ROWS } from "./copy.js";

const VENUE_WORD = { main: STRIP.parts.perps, xyz: STRIP.parts.tradfi };

// The day's P&L (Hyperliquid's own, deposits left out: the same source as the number beside it),
// with a hairline at zero.
function Spark({ points, height = 24 }) {
  if (!points || points.length < 2) return <div className="pf-spark" style={{ height }} />;
  const W = 300, H = height;
  const vs = points.map(p => p.value);
  const lo = Math.min(0, ...vs), hi = Math.max(0, ...vs), r = hi - lo || 1;
  const t0 = points[0].time, t1 = points[points.length - 1].time, tr = t1 - t0 || 1;
  const Y = v => (H - 2 - ((v - lo) / r) * (H - 4)).toFixed(1);
  const d = points.map((p, i) => `${i ? "L" : "M"}${(((p.time - t0) / tr) * W).toFixed(1)},${Y(p.value)}`).join("");
  return <svg className="pf-spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" height={H} aria-hidden="true">
    <line x1="0" x2={W} y1={Y(0)} y2={Y(0)} className="pf-spark-0" vectorEffect="non-scaling-stroke" />
    <path d={d} fill="none" stroke="var(--t-accent)" strokeWidth="1.25" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
  </svg>;
}

function EquityCell({ totals, day, partialNames, phone }) {
  const change = day?.pnlHistory?.length ? day.pnlHistory[day.pnlHistory.length - 1].value : null;
  // The parts by value, each with a bar in proportion (the largest part fills 60 px).
  const parts = PARTS.filter(k => totals.parts[k] > 0.5).sort((a, b) => totals.parts[b] - totals.parts[a]);
  const top = parts.length ? totals.parts[parts[0]] : 1;
  const pop = <div className="pf-pop">
    {parts.map(k => <div key={k} className="pf-pop-row pf-part"><span>{STRIP.parts[k]}</span>
      <i className="pf-part-bar" style={{ width: `${Math.max(2, (totals.parts[k] / top) * 60)}px` }} /><b className="m">{usd(totals.parts[k])}</b></div>)}
    <div className="pf-pop-sep" />
    <div className="pf-pop-row"><span>{STRIP.openPnl}</span><b className={`m ${pnlClass(totals.openPnl)}`}>{usd(totals.openPnl, { sign: true })}</b></div>
    <div className="pf-pop-row"><span>{STRIP.withdrawable}</span><b className="m">{usd(totals.withdrawable)}</b></div>
  </div>;
  const info = partialNames.length ? `${INFO.equity} ${STRIP.partialInfo(partialNames.join(", "))}` : INFO.equity;
  return <div className="pf-cell pf-cell-eq">
    <div className="pf-cell-top"><Label info={info}>{LABELS.equity}</Label></div>
    <div className="pf-cell-head">
      <Hover content={pop} width={280} className="pf-head-hov" tabIndex={0} align="start">
        <Tween className="pf-big m" value={totals.equity} format={v => usd(v)} />
      </Hover>
      {totals.partial && <span className="pf-partial">{STRIP.partial}</span>}
      {change != null && <span className={`pf-chg m ${pnlClass(change)}`}>{usd(change, { sign: true })} <span className="pf-chg-u">{STRIP.h24}</span></span>}
    </div>
    <Spark points={day?.pnlHistory} height={phone ? 28 : 24} />
  </div>;
}

function LiquidationCell({ rows, venues, compact }) {
  const near = nearestLiq(rows, 3);
  const top = near[0];
  const red = top && distRed(top.dist);
  const worst = worstMargin(venues);
  const ratio = worst?.ratio ?? null;
  const pop = near.length ? <div className="pf-pop">{near.map(r => <div key={r.coin} className="pf-pop-row">
    <span>{displayName(r.coin).name}</span><b className="m">{pct(r.dist.pct)}{r.dist.atr != null ? ` · ${atrNum(r.dist.atr)} ${STRIP.atr}` : ""}</b></div>)}</div> : null;
  return <div className="pf-cell pf-cell-liq">
    <div className="pf-cell-top"><Label info={INFO.liquidation}>{LABELS.liquidation}</Label></div>
    <div className="pf-cell-head">
      {top ? <Hover content={pop} width={220} className="pf-head-hov" tabIndex={0}>
        <span className="pf-liq-coin">{displayName(top.coin).name}</span>
        <span className={`pf-big m${red ? " pf-red" : ""}`}>{red && <LiqGlyph h={compact ? 12 : 18} />}{pct(top.dist.pct, { digits: 0 })}</span>
        {top.dist.atr != null && !compact && <span className="pf-liq-atr m">{atrNum(top.dist.atr)} {STRIP.atr}</span>}
      </Hover> : <span className="pf-big m pf-dim">{"—"}</span>}
    </div>
    {rows.length > 0 && <div className="pf-mbar-wrap">
      <div className="pf-mbar" role="img" aria-label={`${STRIP.margin} ${ratio != null ? pct(ratio * 100, { digits: 0 }) : "—"}`}>
        {ratio != null && <i style={{ width: `${Math.min(100, ratio * 100)}%` }} className={ratio >= 0.66 ? "pf-red-bg" : ""} />}
        <b className="pf-mbar-100" aria-hidden="true" />
      </div>
      {!compact && <span className="pf-mbar-t" title={worst ? (VENUE_WORD[worst.venue] || worst.venue) : undefined}>{STRIP.margin} <span className="m">{ratio != null ? pct(ratio * 100, { digits: 0 }) : "—"}</span></span>}
    </div>}
  </div>;
}

// Diverging bar: shorts left, longs right; one block per position, width ∝ notional; the larger
// side's gross fills its half. Colour: open P&L at 35/60/90% for |ROE| under 5%, 5-20%, over 20%.
// big: the largest position's share, printed over its block's start when it is over 40%.
export function ExposureBar({ rows, onPick, height = 8, big = null }) {
  const longs = rows.filter(r => r.isLong).sort((a, b) => b.value - a.value);
  const shorts = rows.filter(r => !r.isLong).sort((a, b) => b.value - a.value);
  const gl = longs.reduce((s, r) => s + r.value, 0), gs = shorts.reduce((s, r) => s + r.value, 0);
  const scale = Math.max(gl, gs) || 1;
  const seg = (r, side) => {
    const a = Math.abs(r.roe) < 5 ? 35 : Math.abs(r.roe) <= 20 ? 60 : 90;
    const tone = r.upnl >= 0 ? "var(--t-profit)" : "var(--t-loss)";
    const share = (r.value / (gl + gs)) * 100;
    const tip = <div className="pf-pop"><div className="pf-pop-row"><span><b>{displayName(r.coin).name}</b> {r.isLong ? ROWS.long : ROWS.short}</span><b className="m">{usd(r.value)}</b></div>
      <div className="pf-pop-row"><span>{STRIP.share}</span><b className="m">{pct(share, { digits: 0 })}</b></div>
      <div className="pf-pop-row"><span>{STRIP.openPnl}</span><b className={`m ${pnlClass(r.upnl)}`}>{usd(r.upnl, { sign: true })}</b></div></div>;
    return <Hover key={r.coin} as="button" type="button" content={tip} width={200}
      className={`pf-xseg${r.venue !== "main" ? " pf-hatch" : ""}`} aria-label={`${displayName(r.coin).name} ${usd(r.value)}`}
      style={{ width: `${(r.value / scale) * 100}%`, background: `color-mix(in srgb, ${tone} ${a}%, transparent)`, color: `color-mix(in srgb, ${tone} ${a}%, transparent)` }}
      onClick={() => onPick?.(r.coin)} data-side={side} />;
  };
  // The largest block starts at the middle line: longs to its right, shorts end at it.
  const label = big ? <span className={`pf-xbig m ${big.row.isLong ? "pf-xbig-l" : "pf-xbig-s"}`}>{displayName(big.row.coin).name} {pct(big.share * 100, { digits: 0 })}</span> : null;
  return <div className="pf-xbar-wrap">
    {label}
    <div className="pf-xbar" style={{ height }}>
      <div className="pf-xhalf pf-xl">{shorts.map(r => seg(r, "short"))}</div>
      <b className="pf-xmid" aria-hidden="true" />
      <div className="pf-xhalf pf-xr">{longs.map(r => seg(r, "long"))}</div>
    </div>
  </div>;
}

function ExposureCell({ rows, equity, onPick, compact }) {
  const gl = rows.filter(r => r.isLong).reduce((s, r) => s + r.value, 0);
  const gs = rows.filter(r => !r.isLong).reduce((s, r) => s + r.value, 0);
  const net = gl - gs, gross = gl + gs;
  const top = [...rows].sort((a, b) => b.value - a.value)[0];
  const share = top && gross ? top.value / gross : 0;
  const big = !compact && top && share > 0.4 ? { row: top, share } : null;
  return <div className={`pf-cell pf-cell-x${compact ? " pf-cell-cmp" : ""}`}>
    <div className="pf-cell-top"><Label info={INFO.exposure}>{LABELS.exposure}</Label>
      {!compact && rows.length > 0 && <span className="pf-xsub m">{STRIP.gross} {usd(gross)} · {equity > 0 ? `${(gross / equity).toFixed(1)}x` : "—"}</span>}</div>
    <div className="pf-cell-head">
      {rows.length ? <><span className="pf-xnet">{net >= 0 ? STRIP.netLong : STRIP.netShort}</span>
        <Tween className="pf-big m" value={Math.abs(net)} format={v => usd(v)} /></>
        : <span className="pf-big m pf-dim">$0</span>}
    </div>
    {rows.length > 0 && <div className="pf-xwrap"><ExposureBar rows={rows} onPick={onPick} big={big} /></div>}
  </div>;
}

function ReflexCell({ rows, tf, onTf, map, compact, onRadar, ctxKnown }) {
  const s = useMemo(() => reflexShares(rows.filter(r => r.venue === "main" || r.covered), tf), [rows, tf]);
  const total = s.total || 1;
  const w = k => `${(s[k] / total) * 100}%`;
  const covered = s.total - s.uncovered;
  const withPct = ctxKnown && covered > 0 ? (s.with / s.total) * 100 : null;
  const tip = k => <div className="pf-pop"><div className="pf-pop-row"><span>{{ with: STRIP.with, against: STRIP.against, none: STRIP.noSignal, uncovered: STRIP.notCovered }[k]}</span><b className="m">{pct((s[k] / total) * 100, { digits: 0 })} · {usd(s[k])}</b></div></div>;
  return <div className={`pf-cell pf-cell-rx${compact ? " pf-cell-cmp" : ""}`}>
    <div className="pf-cell-top"><Label info={INFO.reflex} width={360}>{LABELS.reflex}</Label>
      {!compact && <span className="pf-tf">
        {["4h", "1d"].map(k => <button key={k} type="button" className="te-toggle" aria-pressed={tf === k} onClick={() => onTf(k)}>{k === "4h" ? STRIP.tf4h : STRIP.tf1d}</button>)}
      </span>}
    </div>
    <div className="pf-rx-body">
      <div className="pf-rx-main">
        {compact && withPct != null && <span className="pf-xnet">{STRIP.with}</span>}
        <div className="pf-cell-head">
          <span className="pf-big m">{withPct != null ? pct(withPct, { digits: 0 }) : "—"}</span>
          {!compact && withPct != null && <span className="pf-xnet">{STRIP.with}</span>}
        </div>
        {rows.length > 0 && <div className="pf-rbar">
          {ctxKnown && ["with", "against", "none", "uncovered"].filter(k => s[k] > 0).map(k => <Hover key={k} content={tip(k)} width={200} className={`pf-rseg pf-r-${k}`} style={{ width: w(k) }} />)}
        </div>}
      </div>
      {!compact && rows.length > 0 && <BookThumb rows={rows} map={map} onClick={onRadar} dim={!ctxKnown} />}
    </div>
  </div>;
}

export default function RiskStrip({ totals, rows, day, partialNames, tf, onTf, map, onPick, onRadar, phone, stale, ctxKnown = true }) {
  const venues = totals.venues;
  if (phone) {
    return <div className={`pf-strip-ph${stale ? " pf-stale" : ""}`}>
      <div className="pf-strip pf-strip-eq"><EquityCell totals={totals} day={day} partialNames={partialNames} phone /></div>
      <div className="pf-strip pf-strip-3">
        <LiquidationCell rows={rows} venues={venues} compact />
        <ExposureCell rows={rows} equity={totals.equity} onPick={onPick} compact />
        <ReflexCell rows={rows} tf={tf} onTf={onTf} map={map} compact onRadar={onRadar} ctxKnown={ctxKnown} />
      </div>
    </div>;
  }
  return <div className={`pf-strip${stale ? " pf-stale" : ""}`}>
    <EquityCell totals={totals} day={day} partialNames={partialNames} />
    <LiquidationCell rows={rows} venues={venues} />
    <ExposureCell rows={rows} equity={totals.equity} onPick={onPick} />
    <ReflexCell rows={rows} tf={tf} onTf={onTf} map={map} onRadar={onRadar} ctxKnown={ctxKnown} />
  </div>;
}

export { Spark };
