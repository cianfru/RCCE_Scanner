import { Star } from "lucide-react";
import TokenLogo from "../TokenLogo.jsx";
import { col } from "../../theme.js";
import { fmtPx } from "../../utils/traderFormat.js";
import { fmtIn, nextCloses } from "../../utils/intel.js";
import { SIGNAL_SHORT, STAGES, ZONE_WORD, movement, pnl, pulseLine } from "../../utils/setupMap.js";
import { Crowd, Pin, STAR_TIP, WATCH_TIP, sc, signed, zoneColor } from "./shared.jsx";

function FocusChart({ c }) {
  const s = c.sparkline || [];
  if (s.length < 2) return null;
  const W = 300, H = 84, e = c.traders?.ple;
  let lo = Math.min(...s), hi = Math.max(...s);
  const showE = e && e > lo * 0.8 && e < hi * 1.2;
  if (showE) { lo = Math.min(lo, e); hi = Math.max(hi, e); }
  const x = k => (k / (s.length - 1)) * W, y = v => H - 4 - ((v - lo) / (hi - lo || 1)) * (H - 8);
  // Stretches to the panel's width at a fixed height (the rail, or the full-width panel below 1200px).
  return <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="smap-fchart" role="img" aria-label="Recent price with the profitable traders' median entry">
    {showE && <line x1="0" x2={W} y1={y(e)} y2={y(e)} className="smap-entry" vectorEffect="non-scaling-stroke" />}
    <path d={s.map((v, k) => `${k ? "L" : "M"}${x(k).toFixed(1)},${y(v).toFixed(1)}`).join("")} fill="none" stroke="var(--t-text2)" strokeWidth="1.6" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
  </svg>;
}

export const hlTradeUrl = (c, row) => `https://app.hyperliquid.xyz/trade/${encodeURIComponent(row?.market_coin || c.coin)}`;

// One coin followed: where it sits, how it moved, the crowd, your trade, and what to do next.
// Used in the rail (desktop and tablet) and in the phone's bottom sheet.
export function FocusBody({ c, tf, box, row, watched, mine, starred, onStar, onWatch, onClear, onDetail, onChart, titleId }) {
  const mf = movement(c, box);
  const past = c.traders?.ple ? c.price / c.traders.ple - 1 : null;
  const my = mine ? pnl(mine, c.price) : null;
  const isWatched = watched.has(c.coin);
  return <>
    <div className="smap-focus-top radar-focus-top">
      {row && <button type="button" className="radar-star" aria-pressed={starred} aria-label={starred ? `Starred: unstar ${c.coin}` : `Star ${c.coin}`}
        title={STAR_TIP} onClick={() => onStar(row.symbol)}>
        <Star size={16} strokeWidth={1.75} fill={starred ? col("#facc15") : "none"} color={starred ? col("#facc15") : "var(--t-text3)"} aria-hidden="true" />
      </button>}
      <h3 id={titleId}><TokenLogo symbol={c.symbol} size={24} /><span className="radar-focus-coin">{c.coin}</span><span className="radar-focus-px">{tf.toUpperCase()} · {fmtPx(c.price)}</span></h3>
      <button type="button" className="mh-close" onClick={onClear}>Clear</button>
    </div>
    <dl className="smap-kv smap-kv-rows">
      <div><dt>Setup</dt><dd style={{ color: sc(c) }}>{(STAGES.find(s => s.key === c.stage) || { name: "No setup" }).name} · {SIGNAL_SHORT[c.signal] || c.signal}</dd></div>
      <div><dt>Zone</dt><dd style={{ color: zoneColor(c.zone) }}>{ZONE_WORD[c.zone]}</dd></div>
      <div><dt>Crowd</dt><dd><Crowd k={c.crowd} /> {c.traders?.pl || 0} long · {c.traders?.ps || 0} short</dd></div>
      {mf && <div><dt>{tf === "1d" ? "5 days" : "24 hours"}</dt><dd>stretch {mf.p[0].z.toFixed(1)} → {mf.p[mf.p.length - 1].z.toFixed(1)} · traders {signed(mf.p[0].n)} → {signed(mf.p[mf.p.length - 1].n)}</dd></div>}
      {past != null && <div><dt>Their entry</dt><dd>{fmtPx(c.traders.ple)} · price {past >= 0 ? "+" : ""}{Math.round(100 * past)}%</dd></div>}
      {mine && <div><dt>Your trade</dt><dd>{mine.side} from {fmtPx(mine.entry)}{my != null && <> · <span className="smap-mono" style={{ color: my >= 0 ? "var(--t-profit)" : "var(--t-loss)" }}>{my >= 0 ? "+" : ""}{Math.round(100 * my)}%</span></>}</dd></div>}
      <div><dt>Next close</dt><dd>{fmtIn(nextCloses(tf, Date.now(), 1)[0] - Date.now())}</dd></div>
    </dl>
    <FocusChart c={c} />
    <div className="smap-actions">
      <button type="button" className="smap-watch" aria-pressed={isWatched} title={WATCH_TIP} onClick={() => onWatch(c.coin)}>
        <Pin color={isWatched ? "var(--t-bg)" : "var(--t-accent)"} />{isWatched ? "Watching" : "Watch"}
      </button>
      <button type="button" className="te-link" onClick={onDetail}>Full detail</button>
      {row && <button type="button" className="te-link" onClick={() => onChart(row)}>Chart</button>}
      <a className="te-link" href={hlTradeUrl(c, row)} target="_blank" rel="noopener noreferrer">Trade on Hyperliquid ↗</a>
    </div>
    {isWatched && <p className="smap-note">Telegram: enters the box · confirms Uptrend · turns crowded · leaves the box · exit signal</p>}
  </>;
}

function StripRow({ c, mine, onClick }) {
  const r = pnl(mine, c.price);
  return <button type="button" className="smap-srow" onClick={onClick}>
    <TokenLogo symbol={c.symbol} size={16} /><strong>{c.coin}</strong><span style={{ color: zoneColor(c.zone) }}>{ZONE_WORD[c.zone]}</span>
    <span className="smap-mono">{SIGNAL_SHORT[c.signal] || c.signal}</span>
    {r != null && <span className="smap-mono" style={{ color: r >= 0 ? "var(--t-profit)" : "var(--t-loss)" }}>{r >= 0 ? "+" : ""}{Math.round(100 * r)}%</span>}
  </button>;
}

// The rail beside the map: the followed coin (or one line on how to follow one), the watch
// list, your trades, what moved, and the market-wide pulse. Never an empty box.
export default function RadarRail({ focusSlot, stripWatch, stripMine, mineOn, mineLoading, mv, pulse, onPick }) {
  const moving = [["Entering the box", mv.entering], ["Leaving the box", mv.leaving], ["Traders arriving", mv.arriving]].filter(([, xs]) => xs.length);
  const line = pulseLine(pulse);
  return <div className="radar-rail-wrap"><aside className="radar-rail" aria-label="Followed coin, watch list and movers">
    {focusSlot}
    {stripWatch.length > 0 && <section className="radar-sec">
      <h3 className="radar-sec-h"><Pin />Watching <span>({stripWatch.length})</span></h3>
      <div className="radar-rows">{stripWatch.map(c => <StripRow key={c.coin} c={c} onClick={() => onPick(c.coin)} />)}</div>
    </section>}
    {mineOn && <section className="radar-sec">
      <h3 className="radar-sec-h"><i className="radar-minekey" />My trades <span>({stripMine.length})</span></h3>
      {stripMine.length > 0
        ? <div className="radar-rows">{stripMine.map(([c, m]) => <StripRow key={c.coin} c={c} mine={m} onClick={() => onPick(c.coin)} />)}</div>
        : mineLoading ? <div className="radar-row-skel shimmer-loading" aria-hidden="true" /> : <p className="smap-note">No open perp positions on the map.</p>}
    </section>}
    {moving.length > 0 && <section className="radar-sec">
      <h3 className="radar-sec-h">Moving</h3>
      <div className="smap-movers">
        {moving.map(([label, xs]) => <div key={label} className="smap-strip"><span className="smap-slab">{label}</span>{xs.map(c =>
          <button type="button" key={c.coin} className="smap-chip" onClick={() => onPick(c.coin)}><strong>{c.coin}</strong><Crowd k={c.crowd} /></button>)}</div>)}
      </div>
    </section>}
    {line && <p className="radar-pulse" title={pulse.clusters?.length ? `Two or more on the same side: ${pulse.clusters.map(k => `${k.coin} ${k.side} ${k.n}`).join(", ")}` : undefined}>{line}</p>}
  </aside></div>;
}
