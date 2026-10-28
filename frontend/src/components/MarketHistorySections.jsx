import { useState } from "react";
import Tabs from "./Tabs.jsx";
import HelpTip from "./HelpTip.jsx";
import { Swatch, useWidth } from "./MarketHistoryChart.jsx";
import { T } from "../theme.js";
import { apiFetch } from "../edge.js";
import { COPY, bandHead, bandShort, dayDate, episodesOf, pctLabel, runsMarks, signedPct, stripCounts, stripScale,
         yearOf } from "../utils/marketHistory.js";

// The market history page's sections under its chart (risk-on runs, episodes, forward test) and their shared
// pieces. The page itself is pages/MarketPage.jsx; it replaced the scanner's history drawer.

const cached = {};                                   // path -> { at, promise }: one fetch per hour per tab

function loadOnce(path) {
  const c = cached[path];
  if (!c || Date.now() - c.at > 3_600_000) {
    cached[path] = { at: Date.now(), promise: apiFetch(path).then(r => (r.ok ? r.json() : null)).catch(() => null) };
  }
  return cached[path].promise;
}

export const loadHistory = () => loadOnce("/api/market-history");
export const loadWallets = () => loadOnce("/api/market-history/wallets");

export const OVERLAYS = () => [                      // a function: T is repainted on theme change
  { key: "overheated", color: T.yellow, dash: "4 3" },
  { key: "downtrend", color: T.red, dash: "5 3" },
  { key: "median_z", color: "#91b9e8", axis: "z" },
  { key: "fg", color: T.orange, opacity: 0.85, scale: 100 },
];

// The info (i): method text lives here, not on the page.
export function Info({ title, paras }) {
  return <HelpTip title={title} width={320} size={13}>{paras.map((p, i) => <span key={i}>{p}</span>)}</HelpTip>;
}

const clip = (v, m = 60) => Math.max(-m, Math.min(m, v));

// A hover box over a mini chart: lines of text, placed over the column at x (px in the chart), kept inside it.
function Tip({ tip, W }) {
  if (!tip) return null;
  const left = Math.max(4, Math.min(W - 196, tip.x - 98));
  return <div className="mh-tip" style={{ left, top: tip.y }} role="status">
    {tip.lines.map((l, i) => (i === 0 ? <b key={i}>{l}</b> : <span key={i}>{l}</span>))}
  </div>;
}

// Column index under the pointer, for charts whose columns sit in equal slots from x0.
const slotAt = (e, W, x0, slot, n) => {
  const rect = e.currentTarget.getBoundingClientRect();
  const i = Math.floor((((e.clientX - rect.left) / rect.width) * W - x0) / slot);
  return i >= 0 && i < n ? i : null;
};

// Day ticks for the runs chart: a round step giving three or four lines.
const dayTicks = max => { const step = [15, 30, 60, 90, 120].find(s => max / s <= 4) || 180; const out = []; for (let v = step; v < max; v += step) out.push(v); return out; };

// Year labels under the runs chart: at the first column of each year, skipping one that would touch the last kept.
export function yearLabels(cols, cx, minGap = 34) {
  const out = [];
  cols.forEach((c, i) => {
    const yr = yearOf(c.start);
    if (i > 0 && yr === yearOf(cols[i - 1].start)) return;
    if (out.length && cx(i) - cx(out[out.length - 1][0]) < minGap) return;
    out.push([i, yr]);
  });
  return out;
}

// ------------------------------------------------------------------ risk-on runs

// The run age's warning level: how many past runs of today's type ended before today's age. Risk-on runs only
// get a level (the owner's caution when a run is old); 0 under MIN_RUNS past runs.
export function ageLevel(cycle, minRuns = 6) {
  if (!cycle?.past) return { level: 0, outlasted: 0, past: 0 };
  const outlasted = cycle.past - cycle.reached;
  const share = outlasted / cycle.past;
  const level = cycle.type !== "on" || cycle.past < minRuns ? 0 : share >= 0.9 ? 3 : share >= 0.75 ? 2 : share >= 0.5 ? 1 : 0;
  return { level, outlasted, past: cycle.past };
}

export function RunsChart({ cycle, since }) {
  const [box, W] = useWidth();
  const [hov, setHov] = useState(null);
  const m = runsMarks(cycle);
  if (!m) return null;
  const on = cycle.type === "on";
  const cols = [...m.columns, { start: cycle.start, len: cycle.day, today: true }];
  const phone = W < 520, wide = W >= 900;
  const padL = 34, padR = 8, top = 8, h = wide ? 130 : 100;
  const slot = Math.min(phone ? 22 : wide ? 64 : 40, (W - padL - padR) / cols.length);
  const cw = Math.max(4, slot * 0.62);
  const maxY = Math.max(...cols.map(c => c.len), cycle.day + cycle.more) * 1.06;
  const y = v => top + (1 - v / maxY) * h;
  const cx = i => padL + i * slot + slot / 2;
  const endX = padL + cols.length * slot;
  const H = top + h + 18;
  const lvl = ageLevel(cycle).level;
  const onMove = e => setHov(slotAt(e, W, padL, slot, cols.length));
  const hc = hov == null ? null : cols[hov];
  const tip = hc && { x: cx(hov), y: Math.max(0, y(hc.len) - 64),
    lines: hc.today ? COPY.runs.tipToday(hc.start, hc.len, on) : COPY.runs.tip(hc.start, hc.len, hc.peak, on) };
  return <section className="mh-section" aria-labelledby="mh-runs-title">
    <div className="mh-sec-head">
      <h3 id="mh-runs-title">{COPY.runs.head(on)}<Info title={COPY.pop.runsTitle} paras={COPY.pop.runs({ on, since })} /></h3>
    </div>
    <div ref={box} className="mh-mini mh-mini-tip">
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" onPointerMove={onMove} onPointerDown={onMove}
        onPointerLeave={e => { if (e.pointerType === "mouse") setHov(null); }}
        aria-label={`${COPY.runs.head(on)}: ${COPY.runs.nowKey(cycle.day, cycle.reached, cycle.past, on)}`}>
        {dayTicks(maxY).map(v => <g key={v}>
          <line className="mh-grid" x1={padL} x2={endX} y1={y(v)} y2={y(v)} />
          <text className="mh-tick" x={padL - 4} y={y(v) + 4} textAnchor="end">{v}</text>
        </g>)}
        <text className="mh-tick" x={padL - 4} y={top + 2} textAnchor="end">{COPY.runs.axis}</text>
        <line className="mh-zero" x1={padL} x2={endX} y1={y(0)} y2={y(0)} />
        {hov != null && <rect className="mh-run-hover" x={cx(hov) - slot / 2} width={slot} y={top} height={h} />}
        {cols.map((c, i) => c.today
          ? <rect key="today" className={`mh-run-today is-l${lvl}`} x={cx(i) - cw / 2} width={cw} y={y(c.len)} height={Math.max(1, y(0) - y(c.len))} />
          : <rect key={c.start} className={c.reached ? "mh-run is-reached" : "mh-run"} x={cx(i) - cw / 2} width={cw} y={y(c.len)} height={Math.max(1, y(0) - y(c.len))} />)}
        <line className="mh-run-now" x1={padL} x2={endX} y1={y(m.now.day)} y2={y(m.now.day)} />
        {m.later && <line className="mh-run-later" x1={padL} x2={endX} y1={y(m.later.day)} y2={y(m.later.day)} />}
        {yearLabels(cols, cx).map(([i, yr]) => <text key={`y${i}`} className="mh-tick" x={cx(i)} y={H - 3} textAnchor="middle">{yr}</text>)}
      </svg>
      <Tip tip={tip} W={W} />
    </div>
    <div className="mh-keys">
      <span><svg width="18" height="8" aria-hidden="true"><line className="mh-run-now" x1="0" x2="18" y1="4" y2="4" /></svg>
        {COPY.runs.nowKey(cycle.day, cycle.reached, cycle.past, on)}</span>
      {m.later && <span><svg width="18" height="8" aria-hidden="true"><line className="mh-run-later" x1="0" x2="18" y1="4" y2="4" /></svg>
        {COPY.runs.laterKey(m.later.day, cycle.lasted_more, cycle.reached)}</span>}
    </div>
  </section>;
}

// ------------------------------------------------------------------ episodes

// Ticks for a strip symmetric around 0: a round step inside its half-height.
const stripTicks = m => { const step = [50, 40, 30, 20, 10, 5].find(s => s <= m * 0.8) || 5; return [step, -step]; };

function EpisodeStrip({ eps, base, label }) {
  const [box, W] = useWidth();
  const [hov, setHov] = useState(null);
  const phone = W < 520, wide = W >= 900;
  const padL = 34, padR = phone ? 86 : 104;             // room for the "all days" label right of the columns
  const slot = Math.min(wide ? 44 : 28, (W - padL - padR) / Math.max(1, eps.length));
  const cw = Math.max(4, slot * 0.66);
  const h = phone ? 72 : wide ? 110 : 88, H = h + 4;
  // Symmetric around 0, sized to the 90th percentile of the columns (15 to 30 points); taller ones get a notch.
  const m = stripScale(eps.filter(e => !e.due30).map(e => e.alt30), base);
  const y = v => 2 + ((m - clip(v, m)) / (2 * m)) * h;
  const endX = padL + eps.length * slot;
  const onMove = e => setHov(slotAt(e, W, padL, slot, eps.length));
  const he = hov == null ? null : eps[hov];
  const tip = he && { x: padL + hov * slot + slot / 2, y: 0,
    lines: he.alt30 == null || he.due30 ? [COPY.episodes.pending(he.start)] : COPY.episodes.tip(he, base) };
  return <div ref={box} className="mh-mini mh-mini-tip">
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={label} onPointerMove={onMove} onPointerDown={onMove}
      onPointerLeave={e => { if (e.pointerType === "mouse") setHov(null); }}>
      {stripTicks(m).map(v => <g key={v}>
        <line className="mh-grid" x1={padL} x2={endX} y1={y(v)} y2={y(v)} />
        <text className="mh-tick" x={padL - 4} y={y(v) + 4} textAnchor="end">{v > 0 ? `+${v}%` : `−${-v}%`}</text>
      </g>)}
      {hov != null && <rect className="mh-run-hover" x={padL + hov * slot} width={slot} y={0} height={H} />}
      {eps.map((e, i) => {
        const x0 = padL + i * slot + (slot - cw) / 2;
        if (e.alt30 == null || e.due30) {
          return <rect key={e.start} className="mh-ep-pending" x={x0 + 0.5} width={cw - 1} y={y(0) - 4} height={8} />;
        }
        const v = e.alt30, top = Math.min(y(0), y(v)), ht = Math.max(1, Math.abs(y(v) - y(0)));
        return <g key={e.start} className={`${base != null && v > base ? "mh-ep-better" : "mh-ep-worse"}${e.later ? " is-later" : ""}`}>
          <rect x={x0} width={cw} y={top} height={ht} />
          {Math.abs(v) > m && <line className="mh-notch" x1={x0 - 1} x2={x0 + cw + 1} y1={y(Math.sign(v) * m * 0.86)} y2={y(Math.sign(v) * m * 0.86)} />}
        </g>;
      })}
      <line className="mh-zero" x1={padL} x2={endX} y1={y(0)} y2={y(0)} />
      <text className="mh-tick" x={padL - 4} y={y(0) + 4} textAnchor="end">0</text>
      {base != null && <>
        <line className="mh-ordinary" x1={padL} x2={endX + 4} y1={y(base)} y2={y(base)} />
        <text className="mh-line-label" x={endX + 8} y={y(base) + 4}>{COPY.episodes.ordinary(signedPct(base))}</text>
      </>}
    </svg>
    <Tip tip={tip} W={W} />
  </div>;
}

// Columns hidden on a phone (Days, Uptrend, BTC 30d), so the scored ones show without side-scrolling.
const OPT_COLS = [1, 2, 3];

export function Episodes({ data, band, setBandLabel, ctx }) {
  const [all, setAll] = useState(false);
  const eps = episodesOf(data, band);                     // newest first
  const base = data.base?.["30"];
  const baseAlt = base?.alt?.median;
  const t = data.today;
  const counts = stripCounts(eps, baseAlt, data.cycle?.start);
  const shown = all ? eps : eps.slice(0, 5);
  return <section className="mh-section" aria-labelledby="mh-ep-title">
    <div className="mh-sec-head">
      <h3 id="mh-ep-title">{COPY.episodes.head(bandHead(band))}<Info title={COPY.pop.episodesTitle} paras={COPY.pop.episodes({
        alt: signedPct(baseAlt), btc: signedPct(base?.btc?.median), from: ctx.from, to: ctx.to, end: ctx.end,
        better: band.verdict?.alt?.above_base ?? 0, n: band.verdict?.episodes ?? 0, verdict: band.verdict })} /></h3>
      <span className="mh-count">{COPY.episodes.count(counts)}</span>
    </div>
    <div className="mh-bandtabs">
      <Tabs small label="Uptrend band" value={band.label} onChange={setBandLabel}
        items={data.bands.map(b => ({ key: b.label, title: bandHead(b),
          label: <>{bandShort(b)}{b.label === t.band && <><i className="mh-today-dot" aria-hidden="true" /><span className="mh-sr">{COPY.runs.now}</span></>}</> }))} />
    </div>
    <p className="mh-sub">{COPY.episodes.sub}</p>
    <EpisodeStrip eps={[...eps].reverse()} base={baseAlt} label={`${COPY.episodes.head(bandHead(band))}: ${COPY.episodes.count(counts)}`} />
    <div className="mh-table-wrap">
      <table className="mh-table">
        <thead><tr>{COPY.episodes.cols.map((c, i) => <th key={c} scope="col" className={OPT_COLS.includes(i) ? "mh-opt" : undefined}>{c}</th>)}</tr></thead>
        <tbody>
          {shown.map(e => {
            const vs = e.alt30 != null && baseAlt != null ? e.alt30 - baseAlt : null;
            return <tr key={e.start}>
              <td>{dayDate(e.start)}</td><td className="mh-opt">{e.end >= t.day ? COPY.episodes.ongoing(e.end - e.start + 1) : e.end - e.start + 1}</td><td className="mh-opt">{pctLabel(e.breadth)}</td>
              {e.due30 ? <><td className="mh-opt" /><td colSpan={3} className="mh-muted">{COPY.episodes.due(dayDate(e.due30, false))}</td></> : <>
                <td className="mh-opt">{signedPct(e.btc30)}</td><td>{signedPct(e.alt30)}</td>
                <td className={vs == null ? "" : vs > 0 ? "mh-better" : "mh-worse"}>{vs == null ? "—" : COPY.episodes.pts(vs)}</td>
                {e.due60 ? <td className="mh-muted">{COPY.episodes.due(dayDate(e.due60, false))}</td> : <td>{signedPct(e.alt60)}</td>}
              </>}
            </tr>;
          })}
        </tbody>
      </table>
    </div>
    {eps.length > 5 && <button type="button" className="mh-link" aria-expanded={all} onClick={() => setAll(a => !a)}>
      {all ? COPY.episodes.fewer : COPY.episodes.all(eps.length)}</button>}
  </section>;
}

// ------------------------------------------------------------------ forward test
// Declared 26 Sep 2026 (docs/reviews/btc-band-breadth-forward-test.md): new episodes fill the squares as their
// 60 days close; the past cases are where the idea came from.

function PastStrip({ hist, b60, label }) {
  const [box, W] = useWidth();
  const [hov, setHov] = useState(null);
  const padL = 34, padR = 104;
  const slot = Math.min(40, (W - padL - padR) / Math.max(1, hist.length));
  const cw = Math.max(4, slot * 0.6);
  const h = 72, H = h + 4;
  const m = stripScale(hist.map(x => x[5]), b60, 45);
  const y = v => 2 + ((m - clip(v, m)) / (2 * m)) * h;
  const endX = padL + hist.length * slot;
  const onMove = e => setHov(slotAt(e, W, padL, slot, hist.length));
  const tip = hov != null && { x: padL + hov * slot + slot / 2, y: 0, lines: COPY.ft.tip(hist[hov], b60) };
  return <div ref={box} className="mh-mini mh-mini-tip">
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={label} onPointerMove={onMove} onPointerDown={onMove}
      onPointerLeave={e => { if (e.pointerType === "mouse") setHov(null); }}>
      {stripTicks(m).map(v => <g key={v}>
        <line className="mh-grid" x1={padL} x2={endX} y1={y(v)} y2={y(v)} />
        <text className="mh-tick" x={padL - 4} y={y(v) + 4} textAnchor="end">{v > 0 ? `+${v}%` : `−${-v}%`}</text>
      </g>)}
      {hov != null && <rect className="mh-run-hover" x={padL + hov * slot} width={slot} y={0} height={H} />}
      {hist.map(([start, , , , , a60], i) => {
        const x0 = padL + i * slot + (slot - cw) / 2, top = Math.min(y(0), y(a60));
        return <g key={start}>
          <rect className={b60 != null && a60 < b60 ? "mh-ep-worse" : "mh-ep-better"} x={x0} width={cw}
            y={top} height={Math.max(1, Math.abs(y(a60) - y(0)))} />
          {Math.abs(a60) > m && <line className="mh-notch" x1={x0 - 1} x2={x0 + cw + 1} y1={y(Math.sign(a60) * m * 0.86)} y2={y(Math.sign(a60) * m * 0.86)} />}
        </g>;
      })}
      <line className="mh-zero" x1={padL} x2={endX} y1={y(0)} y2={y(0)} />
      <text className="mh-tick" x={padL - 4} y={y(0) + 4} textAnchor="end">0</text>
      {b60 != null && <>
        <line className="mh-ordinary" x1={padL} x2={endX + 4} y1={y(b60)} y2={y(b60)} />
        <text className="mh-line-label" x={endX + 8} y={y(b60) + 4}>{COPY.episodes.ordinary(signedPct(b60))}</text>
      </>}
    </svg>
    <Tip tip={tip} W={W} />
  </div>;
}

export function ForwardTest({ ft, base }) {
  const [table, setTable] = useState(false);
  const b60 = base?.["60"]?.alt?.median;
  const scored = ft.episodes.filter(e => e.h60);
  const squares = Array.from({ length: Math.max(6, ft.episodes.length) }, (_, i) => ft.episodes[i] || null);
  const hist = ft.history;
  const worse = hist.filter(h => b60 != null && h[5] < b60).length;
  const bear = hist.filter(h => h[0] < 19358).length;           // started before 1 Jan 2023
  return <section className="mh-section" aria-labelledby="mh-ft-title">
    <div className="mh-sec-head">
      <h3 id="mh-ft-title">{COPY.ft.head}<Info title={COPY.pop.ftTitle} paras={COPY.pop.ft({ declared: dayDate(ft.declared_day),
        share: Math.round(100 * ft.share), base: signedPct(b60), bear, n: hist.length })} /></h3>
      <span className="mh-squares" role="img" aria-label={COPY.ft.scored(scored.length)}>
        {squares.map((e, i) => <i key={i} title={e ? COPY.ft.square(e.start, e.h60?.alt) : undefined}
          className={!e ? "" : !e.h60 ? "is-open" : e.h60.alt < b60 ? "is-worse" : "is-better"} />)}
        <span className="mh-count">{COPY.ft.scored(scored.length)}</span>
      </span>
    </div>
    {ft.episodes.length > 0 && <div className="mh-table-wrap"><table className="mh-table">
      <thead><tr>{COPY.ft.cols.map(c => <th key={c} scope="col">{c}</th>)}</tr></thead>
      <tbody>{[...ft.episodes].reverse().map(e => <tr key={e.start}>
        <td>{dayDate(e.start)}</td><td>{e.end - e.start + 1}</td><td>{Math.round(100 * e.share)}%</td>
        <td>{e.h30 ? signedPct(e.h30.btc) : COPY.ft.pending}</td><td>{e.h30 ? signedPct(e.h30.alt) : COPY.ft.pending}</td>
        <td className={e.h60 && b60 != null ? (e.h60.alt < b60 ? "mh-worse" : "mh-better") : ""}>{e.h60 ? signedPct(e.h60.alt) : COPY.ft.pending}</td>
      </tr>)}</tbody></table></div>}
    <div className="mh-past">
      <span className="mh-past-head">{COPY.ft.past}<Info title={COPY.pop.pastTitle} paras={COPY.pop.past({ n: hist.length, base: signedPct(b60) })} />
        <span className="mh-count">{COPY.ft.worse(worse, hist.length)}</span>
        <button type="button" className="mh-link" aria-expanded={table} onClick={() => setTable(v => !v)}>{COPY.ft.table}</button></span>
      <p className="mh-sub">{COPY.ft.pastSub}</p>
      <PastStrip hist={hist} b60={b60} label={COPY.ft.worse(worse, hist.length)} />
    </div>
    {table && <div className="mh-table-wrap"><table className="mh-table">
      <thead><tr>{COPY.ft.cols.map(c => <th key={c} scope="col">{c}</th>)}</tr></thead>
      <tbody>{[...hist].reverse().map(([start, days, share, b30, a30, a60]) => <tr key={start}>
        <td>{dayDate(start)}</td><td>{days}</td><td>{Math.round(100 * share)}%</td><td>{signedPct(b30, 0)}</td><td>{signedPct(a30, 0)}</td>
        <td className={b60 != null ? (a60 < b60 ? "mh-worse" : "mh-better") : ""}>{signedPct(a60, 0)}</td>
      </tr>)}</tbody></table></div>}
  </section>;
}

// ------------------------------------------------------------------ controls

export function Controls({ ranges, range, setRange, overlays, setOverlays, children }) {
  const toggle = k => setOverlays(o => (o.includes(k) ? o.filter(x => x !== k) : [...o, k]));
  return <div className="mh-controls">
    <Tabs small label={COPY.rangeLabel} items={ranges} value={range} onChange={setRange} />
    {setOverlays && <div className="mh-toggles" role="group" aria-label={COPY.overlaysLabel}>
      {OVERLAYS().map(o => <button key={o.key} type="button" aria-pressed={overlays.includes(o.key)} onClick={() => toggle(o.key)}>
        <Swatch color={o.color} dash={o.dash} />{COPY.overlays[o.key]}</button>)}
    </div>}
    {children}
  </div>;
}
