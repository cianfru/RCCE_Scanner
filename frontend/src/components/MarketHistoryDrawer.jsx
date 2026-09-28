import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Tabs from "./Tabs.jsx";
import HelpTip from "./HelpTip.jsx";
import MarketHistoryChart, { useWidth } from "./MarketHistoryChart.jsx";
import { T } from "../theme.js";
import { COPY, RANGES, bandHead, bandOn, bandShort, breadthContext, dayDate, episodesOf, fearGreedByDay, fgSplit,
         inRange, monthYear, pctLabel, percentileOf, rowsOf, runsMarks, signedPct, stripCounts, yearOf } from "../utils/marketHistory.js";

const API_BASE = import.meta.env.VITE_API_URL || "";
let cached = null;                                   // { at, promise }: one fetch per hour per tab

function loadHistory() {
  if (!cached || Date.now() - cached.at > 3_600_000) {
    cached = { at: Date.now(), promise: fetch(`${API_BASE}/api/market-history`).then(r => (r.ok ? r.json() : null)).catch(() => null) };
  }
  return cached.promise;
}

const OVERLAYS = () => [                             // a function: T is repainted on theme change
  { key: "overheated", color: T.yellow, dash: "4 3" },
  { key: "median_z", color: "#91b9e8", axis: "z" },
  { key: "fg", color: "var(--t-text3)", dash: "1 3", scale: 100 },
];

// The info (i): method text lives here, not on the page.
function Info({ title, paras }) {
  return <HelpTip title={title} width={320} size={13}>{paras.map((p, i) => <span key={i}>{p}</span>)}</HelpTip>;
}

const clip = (v, m = 60) => Math.max(-m, Math.min(m, v));

// ------------------------------------------------------------------ risk-on runs

function RunsChart({ cycle, since }) {
  const [box, W] = useWidth();
  const [hov, setHov] = useState(null);
  const m = runsMarks(cycle);
  if (!m) return null;
  const on = cycle.type === "on";
  const cols = [...m.columns, { start: cycle.start, len: cycle.day, today: true }];
  const phone = W < 520;
  const padL = 30, padR = phone ? 78 : 96, top = 6, h = 90;
  const slot = Math.min(phone ? 20 : 40, (W - padL - padR) / cols.length);
  const cw = Math.max(4, slot * 0.62);
  const maxY = Math.max(...cols.map(c => c.len), cycle.day + cycle.more) * 1.04;
  const y = v => top + (1 - v / maxY) * h;
  const cx = i => padL + i * slot + slot / 2;
  const endX = padL + cols.length * slot;
  const H = top + h + 18;
  const lines = [m.now, m.later].filter(Boolean);
  const onMove = e => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.floor((px - padL) / slot);
    setHov(i >= 0 && i < cols.length ? i : null);
  };
  const hc = hov == null ? null : cols[hov];
  return <section className="mh-section" aria-labelledby="mh-runs-title">
    <div className="mh-sec-head">
      <h3 id="mh-runs-title">{COPY.runs.head(on)}<Info title={COPY.pop.runsTitle} paras={COPY.pop.runs({ on, since })} /></h3>
      <span className="mh-hint" aria-live="off">{hc ? (hc.today ? `${dayDate(hc.start)} · ${COPY.kpi.day(hc.len)}` : COPY.runs.hover(hc.start, hc.len, hc.peak)) : ""}</span>
    </div>
    <div ref={box} className="mh-mini">
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" onPointerMove={onMove} onPointerDown={onMove}
        onPointerLeave={e => { if (e.pointerType === "mouse") setHov(null); }}
        aria-label={`${COPY.runs.head(on)}: ${m.now.text}${m.later ? `; ${m.later.text}` : ""}`}>
        <line className="mh-zero" x1={padL} x2={endX} y1={y(0)} y2={y(0)} />
        {cols.map((c, i) => c.today
          ? <rect key="today" className="mh-run-today" x={cx(i) - cw / 2} width={cw} y={y(c.len)} height={y(0) - y(c.len)} />
          : <rect key={c.start} className={c.reached ? "mh-run is-reached" : "mh-run"} x={cx(i) - cw / 2} width={cw} y={y(c.len)} height={Math.max(1, y(0) - y(c.len))} />)}
        {lines.map((l, j) => <g key={j}>
          <line className={j === 0 ? "mh-run-now" : "mh-run-later"} x1={padL} x2={endX + 4} y1={y(l.day)} y2={y(l.day)} />
          <text className="mh-tick" x={padL - 4} y={y(l.day) + 4} textAnchor="end">{l.day}</text>
          <text className="mh-line-label" x={endX + 8} y={y(l.day) + 4}>{l.text}</text>
        </g>)}
        {cols.map((c, i) => (i === 0 || yearOf(c.start) !== yearOf(cols[i - 1].start))
          && <text key={`y${i}`} className="mh-tick" x={cx(i)} y={H - 3} textAnchor="middle">{yearOf(c.start)}</text>)}
        {hov != null && <rect className="mh-run-hover" x={cx(hov) - slot / 2} width={slot} y={top} height={h} />}
      </svg>
    </div>
  </section>;
}

// ------------------------------------------------------------------ episodes

function EpisodeStrip({ eps, base, label }) {
  const [box, W] = useWidth();
  const phone = W < 520;
  const padR = phone ? 0 : 104;
  const slot = Math.min(28, (W - padR) / Math.max(1, eps.length));
  const cw = Math.max(4, slot * 0.66);
  const h = 56, H = h + 4;
  // Symmetric around 0, just wide enough for the columns; clipped at ±60 with a notch.
  const m = Math.min(60, Math.max(15, Math.abs(base ?? 0), ...eps.map(e => Math.abs(e.alt30 ?? 0))) * 1.08);
  const y = v => 2 + ((m - clip(v, m)) / (2 * m)) * h;
  return <div ref={box} className="mh-mini">
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={label}>
      {eps.map((e, i) => {
        const x0 = i * slot + (slot - cw) / 2;
        if (e.alt30 == null || e.due30) {
          return <rect key={e.start} className="mh-ep-pending" x={x0 + 0.5} width={cw - 1} y={y(0) - 4} height={8}><title>{COPY.episodes.pending(e.start)}</title></rect>;
        }
        const v = e.alt30, top = Math.min(y(0), y(v)), ht = Math.max(1, Math.abs(y(v) - y(0)));
        return <g key={e.start} className={`${base != null && v > base ? "mh-ep-better" : "mh-ep-worse"}${e.later ? " is-later" : ""}`}>
          <rect x={x0} width={cw} y={top} height={ht}><title>{COPY.episodes.column(e.start, v)}</title></rect>
          {Math.abs(v) > 60 && <line className="mh-notch" x1={x0 - 1} x2={x0 + cw + 1} y1={y(Math.sign(v) * m * 0.86)} y2={y(Math.sign(v) * m * 0.86)} />}
        </g>;
      })}
      <line className="mh-zero" x1={0} x2={W} y1={y(0)} y2={y(0)} />
      {base != null && <>
        <line className="mh-ordinary" x1={0} x2={W - (phone ? 0 : padR - 4)} y1={y(base)} y2={y(base)} />
        <text className="mh-line-label" x={W - 2} y={y(base) + 12} textAnchor="end">{COPY.episodes.ordinary(signedPct(base))}</text>
      </>}
    </svg>
  </div>;
}

function Episodes({ data, band, setBandLabel, ctx }) {
  const [all, setAll] = useState(false);
  const eps = episodesOf(data, band);                     // newest first
  const base = data.base?.["30"];
  const baseAlt = base?.alt?.median;
  const counts = stripCounts(eps, baseAlt);
  const shown = all ? eps : eps.slice(0, 5);
  const t = data.today;
  return <section className="mh-section" aria-labelledby="mh-ep-title">
    <div className="mh-sec-head">
      <h3 id="mh-ep-title">{COPY.episodes.head(bandHead(band))}<Info title={COPY.pop.episodesTitle} paras={COPY.pop.episodes({
        alt: signedPct(baseAlt), btc: signedPct(base?.btc?.median), from: ctx.from, to: ctx.to, end: ctx.end,
        better: band.verdict?.alt?.above_base ?? 0, n: band.verdict?.episodes ?? 0, verdict: band.verdict })} /></h3>
      <span className="mh-count">{COPY.episodes.count(counts.better, counts.worse)}</span>
    </div>
    <div className="mh-bandtabs">
      <Tabs small label="Uptrend band" value={band.label} onChange={setBandLabel}
        items={data.bands.map(b => ({ key: b.label, title: bandHead(b),
          label: <>{bandShort(b)}{b.label === t.band && <i className="mh-today-dot" aria-label="today" />}</> }))} />
    </div>
    <EpisodeStrip eps={[...eps].reverse()} base={baseAlt} label={`${COPY.episodes.head(bandHead(band))}: ${COPY.episodes.count(counts.better, counts.worse)}`} />
    <div className="mh-table-wrap">
      <table className="mh-table">
        <thead><tr>{COPY.episodes.cols.map(c => <th key={c} scope="col">{c}</th>)}</tr></thead>
        <tbody>
          {shown.map(e => {
            const vs = e.alt30 != null && baseAlt != null ? e.alt30 - baseAlt : null;
            return <tr key={e.start}>
              <td>{dayDate(e.start)}</td><td>{e.end >= t.day ? COPY.episodes.ongoing(e.end - e.start + 1) : e.end - e.start + 1}</td><td>{pctLabel(e.breadth)}</td>
              {e.due30 ? <td colSpan={4} className="mh-muted">{COPY.episodes.due(dayDate(e.due30, false))}</td> : <>
                <td>{signedPct(e.btc30)}</td><td>{signedPct(e.alt30)}</td>
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

function ForwardTest({ ft, base }) {
  const [table, setTable] = useState(false);
  const b60 = base?.["60"]?.alt?.median;
  const scored = ft.episodes.filter(e => e.h60);
  const squares = Array.from({ length: Math.max(6, ft.episodes.length) }, (_, i) => ft.episodes[i] || null);
  const hist = ft.history;
  const worse = hist.filter(h => b60 != null && h[5] < b60).length;
  const bear = hist.filter(h => h[0] < 19358).length;           // started before 1 Jan 2023
  const mw = 14 * hist.length, mh = 36;
  const mm = Math.min(60, Math.max(15, ...hist.map(x => Math.abs(x[5]))) * 1.08);
  const my = v => 1 + ((mm - clip(v, mm)) / (2 * mm)) * (mh - 2);
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
      <span className="mh-past-head">{COPY.ft.past}<Info title={COPY.pop.pastTitle} paras={COPY.pop.past({ n: hist.length, base: signedPct(b60) })} /></span>
      <svg viewBox={`0 0 ${mw} ${mh}`} width={mw} height={mh} role="img" aria-label={COPY.ft.worse(worse, hist.length)}>
        {hist.map(([start, , , , , a60], i) => {
          const top = Math.min(my(0), my(a60));
          return <rect key={start} className={b60 != null && a60 < b60 ? "mh-ep-worse" : "mh-ep-better"} x={i * 14 + 3} width={8}
            y={top} height={Math.max(1, Math.abs(my(a60) - my(0)))}><title>{COPY.episodes.column(start, a60)}</title></rect>;
        })}
        <line className="mh-zero" x1={0} x2={mw} y1={my(0)} y2={my(0)} />
        {b60 != null && <line className="mh-ordinary" x1={0} x2={mw} y1={my(b60)} y2={my(b60)} />}
      </svg>
      <span className="mh-count">{COPY.ft.worse(worse, hist.length)}</span>
      <button type="button" className="mh-link" aria-expanded={table} onClick={() => setTable(v => !v)}>{COPY.ft.table}</button>
    </div>
    {table && <div className="mh-table-wrap"><table className="mh-table">
      <thead><tr>{COPY.ft.cols.map(c => <th key={c} scope="col">{c}</th>)}</tr></thead>
      <tbody>{[...hist].reverse().map(([start, days, share, b30, a30, a60]) => <tr key={start}>
        <td>{dayDate(start)}</td><td>{days}</td><td>{Math.round(100 * share)}%</td><td>{signedPct(b30, 0)}</td><td>{signedPct(a30, 0)}</td>
        <td className={b60 != null ? (a60 < b60 ? "mh-worse" : "mh-better") : ""}>{signedPct(a60, 0)}</td>
      </tr>)}</tbody></table></div>}
  </section>;
}

// ------------------------------------------------------------------ tabs

function Controls({ range, setRange, overlays, setOverlays }) {
  const toggle = k => setOverlays(o => (o.includes(k) ? o.filter(x => x !== k) : [...o, k]));
  return <div className="mh-controls">
    <Tabs small label={COPY.rangeLabel} items={RANGES} value={range} onChange={setRange} />
    {setOverlays && <div className="mh-toggles" role="group" aria-label={COPY.overlaysLabel}>
      {OVERLAYS().map(o => <button key={o.key} type="button" aria-pressed={overlays.includes(o.key)} onClick={() => toggle(o.key)}>
        <i style={{ background: o.color }} aria-hidden="true" />{COPY.overlays[o.key]}</button>)}
    </div>}
  </div>;
}

function BreadthTab({ data, rows, range, setRange }) {
  const [overlays, setOverlays] = useState([]);
  const [bandLabel, setBandLabel] = useState(data.today.band);
  const band = data.bands.find(b => b.label === bandLabel) || data.bands[0];
  const ctx = breadthContext(data);
  const t = data.today, c = data.cycle, fan = ctx.fan;
  const shown = useMemo(() => inRange(rows, range).map(r => ({ ...r, fg: r.fg == null ? null : r.fg / 100 })), [rows, range]);
  const ov = OVERLAYS().filter(o => overlays.includes(o.key));
  const last = rows[rows.length - 1];
  const today = { uptrend: t.uptrend, btc: last?.btc, alt: 0, row: last };
  const fanPop = fan ? <Info title={COPY.pop.fanTitle} paras={COPY.pop.fan(ctx.fanCtx)} />
    : <Info title={COPY.pop.fanTitle} paras={COPY.pop.fanNone({ since: ctx.since })} />;
  return <>
    <div className="mh-kpis">
      <div className="mh-kpi">
        <strong>{pctLabel(t.uptrend)}</strong>
        <span>{COPY.kpi.uptrend}<Info title={COPY.pop.uptrendTitle} paras={COPY.pop.uptrend({ coins: data.coins, since: ctx.since })} /></span>
        <em>{COPY.kpi.pct(t.percentile)}</em>
      </div>
      {c && <div className="mh-kpi" title={dayDate(c.start)}>
        <strong>{COPY.kpi.day(c.day)}</strong>
        <span>{COPY.kpi.run(ctx.on)}</span>
        {ctx.on && c.below_days > 0 && <em>{COPY.kpi.under(c.below_days)}</em>}
      </div>}
      {ctx.side && <div className="mh-kpi">
        <strong className={ctx.side === "below" ? "mh-worse" : ""}>{ctx.side === "inside" ? "0%" : signedPct(ctx.dist, 0)}</strong>
        <span>{COPY.kpi.band(ctx.side)}<Info title={COPY.pop.bandTitle} paras={COPY.pop.band()} /></span>
      </div>}
    </div>
    <Controls range={range} setRange={setRange} overlays={overlays} setOverlays={setOverlays} />
    <MarketHistoryChart mode="breadth" rows={shown} range={range} fan={fan} fanPop={fanPop} overlays={ov}
      selBand={{ lo: band.lo, hi: band.hi }} markers={episodesOf(data, band).map(e => e.start)} today={today}
      aria={`${COPY.panel.uptrend}, ${COPY.panel.btc}, ${RANGES.find(r => r.key === range).label}`} />
    {c?.runs && <RunsChart cycle={c} since={ctx.since} />}
    <Episodes data={data} band={band} setBandLabel={setBandLabel} ctx={ctx} />
    {data.forward_test && <ForwardTest ft={data.forward_test} base={data.base} />}
  </>;
}

function FearGreedTab({ data, rows, range, setRange }) {
  const shown = inRange(rows, range);
  const all = data.fear_greed || [];
  const latest = all[all.length - 1];
  const split = fgSplit(shown.map(r => r.fg));
  const last = rows[rows.length - 1];
  const since = all.length ? monthYear(all[0][0]) : "";
  const labels = ["≤40", "41–69", "≥70"];
  return <>
    <div className="mh-kpis mh-kpis-fg">
      <div className="mh-kpi">
        <strong>{latest ? latest[1] : "—"}</strong>
        <span>{COPY.kpi.fg}<Info title={COPY.pop.fgTitle} paras={COPY.pop.fg({ since })} /></span>
        {latest && <em>{COPY.kpi.pct(percentileOf(all.map(v => v[1]), latest[1]))}</em>}
      </div>
      {split && <div className="mh-split" role="img" aria-label={labels.map((l, i) => `${l} ${split[i]}%`).join(", ")}>
        <div className="mh-split-bar">{split.map((p, i) => <i key={i} className={`s${i}`} style={{ flexGrow: p }} />)}</div>
        <div className="mh-split-labels">{split.map((p, i) => <span key={i} style={{ flexGrow: Math.max(p, 18) }}><b>{labels[i]}</b> {p}%</span>)}</div>
      </div>}
    </div>
    <Controls range={range} setRange={setRange} />
    <MarketHistoryChart mode="fear" rows={shown} range={range} today={{ row: last }} aria={`${COPY.panel.fg}, ${COPY.panel.btc}`} />
  </>;
}

// Right-side drawer with the scanner's market history. Opens from the consensus and dial icons.
export default function MarketHistoryDrawer({ tab, onTab, onClose }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [range, setRange] = useState("3m");
  const closeRef = useRef(null);
  const opener = useRef(typeof document !== "undefined" ? document.activeElement : null);
  useEffect(() => {
    let alive = true;
    loadHistory().then(d => { if (!alive) return; if (d) setData(d); else setFailed(true); });
    return () => { alive = false; };
  }, []);
  useEffect(() => {
    closeRef.current?.focus();
    const prev = opener.current;
    // Escape closes an open info popover first (HelpTip handles it), the drawer otherwise.
    const onKey = e => { if (e.key === "Escape" && !document.querySelector(".alt-season-explanation")) onClose(); };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; prev?.focus?.(); };
  }, [onClose]);
  const fg = useMemo(() => fearGreedByDay(data), [data]);
  const rows = useMemo(() => {
    const weekly = data?.btc_band_weekly || [];
    const alt = new Map(data?.alt_recent || []);
    return rowsOf(data).map(r => {
      const b = bandOn(weekly, r.day);
      return { ...r, fg: fg.get(r.day) ?? null, bandLo: b?.[0] ?? null, bandHi: b?.[1] ?? null, alt: alt.get(r.day) ?? null };
    });
  }, [data, fg]);
  return createPortal(<div className="reflex-terminal">
    <div className="mh-backdrop" onClick={onClose} />
    <aside className="mh-drawer" role="dialog" aria-modal="true" aria-labelledby="mh-title">
      <header className="mh-head">
        <h2 id="mh-title">{COPY.title}</h2>
        <button ref={closeRef} type="button" className="mh-close" onClick={onClose}>{COPY.close}</button>
      </header>
      <Tabs label="History" value={tab} onChange={onTab} items={[{ key: "breadth", label: COPY.tabs.breadth }, { key: "fear", label: COPY.tabs.fear }]} />
      <div className="mh-body">
        {!data ? <p className="mh-muted">{failed ? COPY.unavailable : COPY.loading}</p>
          : tab === "fear" ? <FearGreedTab data={data} rows={rows} range={range} setRange={setRange} />
            : <BreadthTab data={data} rows={rows} range={range} setRange={setRange} />}
      </div>
    </aside>
  </div>, document.body);
}
