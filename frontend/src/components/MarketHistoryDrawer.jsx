import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Tabs from "./Tabs.jsx";
import { T } from "../theme.js";
import { RANGES, bandSummary, compactUsd, dayDate, episodesOf, fearGreedByDay, inRange, logTicks, monthYear,
         percentileOf, rowsOf, signedPct } from "../utils/marketHistory.js";

const API_BASE = import.meta.env.VITE_API_URL || "";
let cached = null;                                   // { at, promise }: one fetch per hour per tab

function loadHistory() {
  if (!cached || Date.now() - cached.at > 3_600_000) {
    cached = { at: Date.now(), promise: fetch(`${API_BASE}/api/market-history`).then(r => (r.ok ? r.json() : null)).catch(() => null) };
  }
  return cached.promise;
}

const pctLabel = x => `${Math.round(100 * x)}%`;
const OVERLAYS = () => [                             // a function: T is repainted on theme change
  { key: "overheated", label: "Overheated share", color: T.yellow, dash: "4 3" },
  { key: "median_z", label: "Median z-score", color: "#91b9e8", axis: "z" },
  { key: "fg", label: "Fear & Greed", color: "var(--t-text3)", dash: "1 3" },
];

// BTC (log) over a 0-100 panel with a hover readout. Series: [{key, color, dash, axis, width}].
function HistoryChart({ rows, series, band, lines, markers, aria, axis = pctLabel }) {
  const box = useRef(null);
  const [W, setW] = useState(680);
  const [hover, setHover] = useState(null);
  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  if (rows.length < 2) return <div ref={box} className="mh-empty">No history in this range.</div>;
  const padL = 8, padR = 44, topH = 120, gap = 14, botH = 170, H = topH + gap + botH + 22;
  const d0 = rows[0].day, d1 = rows[rows.length - 1].day;
  const x = day => padL + ((day - d0) / (d1 - d0)) * (W - padL - padR);
  const btc = rows.map(r => r.btc).filter(v => v > 0);
  const lo = Math.min(...btc), hi = Math.max(...btc);
  const yb = v => 4 + (1 - (Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo) || 1)) * (topH - 8);
  const y0 = topH + gap;
  const yp = v => y0 + (1 - v) * botH;                       // v in 0..1
  const yz = z => yp((Math.max(-3, Math.min(3, z)) + 3) / 6); // z on its own -3..3 axis
  const path = (get, y) => {
    let d = "", pen = false;
    for (const r of rows) {
      const v = get(r);
      if (v == null) { pen = false; continue; }
      d += `${pen ? "L" : "M"}${x(r.day).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    }
    return d;
  };
  const yearTicks = [];
  for (let yr = new Date(d0 * 86_400_000).getUTCFullYear() + 1; ; yr++) {
    const day = Date.UTC(yr, 0, 1) / 86_400_000;
    if (day > d1) break;
    yearTicks.push({ day, label: String(yr) });
  }
  const onMove = e => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const day = d0 + ((px - padL) / (W - padL - padR)) * (d1 - d0);
    let best = 0;
    for (let i = 0; i < rows.length; i++) if (Math.abs(rows[i].day - day) < Math.abs(rows[best].day - day)) best = i;
    setHover(best);
  };
  const h = hover == null ? null : rows[hover];
  const hasZ = series.some(s => s.axis === "z");
  return <div ref={box} className="mh-chart">
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={aria}
      onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
      {logTicks(lo, hi).map(v => <g key={v}>
        <line className="mh-grid" x1={padL} x2={W - padR} y1={yb(v)} y2={yb(v)} />
        <text className="mh-tick" x={W - padR + 6} y={yb(v) + 4}>{compactUsd(v)}</text>
      </g>)}
      <path className="mh-btc" d={path(r => r.btc || null, yb)} />
      <text className="mh-panel-label" x={padL + 2} y={14}>BTC (log)</text>
      {band && <rect className="mh-band" x={padL} width={W - padL - padR} y={yp(Math.min(1, band.hi))} height={yp(band.lo) - yp(Math.min(1, band.hi))} />}
      {[0, 0.25, 0.5, 0.75, 1].map(v => <g key={v}>
        <line className="mh-grid" x1={padL} x2={W - padR} y1={yp(v)} y2={yp(v)} />
        <text className="mh-tick" x={W - padR + 6} y={yp(v) + 4}>{axis(v)}</text>
      </g>)}
      {series.map(s => <path key={s.key} className="mh-series" d={path(r => r[s.key], s.axis === "z" ? yz : yp)}
        style={{ stroke: s.color, strokeDasharray: s.dash, strokeWidth: s.width || 1.25 }} />)}
      {(lines || []).map(l => <g key={l.v}>
        <line className="mh-line" x1={padL} x2={W - padR} y1={yp(l.v)} y2={yp(l.v)} />
        <text className="mh-line-label" x={padL + 2} y={yp(l.v) - 4}>{l.label}</text>
      </g>)}
      {(markers || []).filter(m => m >= d0 && m <= d1).map(m => <line key={m} className="mh-marker" x1={x(m)} x2={x(m)} y1={y0 + botH - 8} y2={y0 + botH} />)}
      {yearTicks.map(t => <text key={t.day} className="mh-tick" x={x(t.day)} y={H - 4} textAnchor="middle">{t.label}</text>)}
      {h && <line className="mh-cursor" x1={x(h.day)} x2={x(h.day)} y1={0} y2={y0 + botH} />}
    </svg>
    <div className="mh-readout" aria-live="off">
      {h ? <>
        <b>{dayDate(h.day)}</b>
        <span>BTC {h.btc ? `$${Math.round(h.btc).toLocaleString("en-US")}` : "—"}</span>
        {series.map(s => h[s.key] == null ? null : <span key={s.key} style={{ color: s.color }}>
          {s.label} {s.axis === "z" ? h[s.key].toFixed(2) : s.key === "fg" ? h[s.key] : axis(h[s.key])}</span>)}
      </> : <span>Hover the chart for a day's reading.{hasZ ? " The z-score uses its own −3 to +3 scale." : ""}</span>}
    </div>
  </div>;
}

function BreadthTab({ data, rows, range, setRange }) {
  const [overlays, setOverlays] = useState([]);
  const [bandLabel, setBandLabel] = useState(data.today.band);
  const band = data.bands.find(b => b.label === bandLabel) || data.bands[0];
  const eps = episodesOf(data, band);
  const shown = inRange(rows, range);
  const series = [{ key: "uptrend", label: "Uptrend", color: "var(--t-accent)", width: 1.75 },
    ...OVERLAYS().filter(o => overlays.includes(o.key))];
  const t = data.today;
  const base = data.base?.["30"];
  const toggle = k => setOverlays(o => (o.includes(k) ? o.filter(x => x !== k) : [...o, k]));
  return <>
    <div className="mh-today">
      <strong>{pctLabel(t.uptrend)}</strong>
      <div>
        <p>of coins in Uptrend on {dayDate(t.day)}: higher than on {t.percentile}% of days since {monthYear(t.since)}, in the {t.band} band.</p>
        <p className="mh-muted">{data.coins} coins on Binance daily closes, run through the scanner's engine. The card counts the scanner's own markets, so the two can differ by a few points.</p>
      </div>
    </div>
    <div className="mh-controls">
      <Tabs small label="Range" items={RANGES} value={range} onChange={setRange} />
      <div className="mh-toggles" role="group" aria-label="Add to the chart">
        {OVERLAYS().map(o => <button key={o.key} type="button" aria-pressed={overlays.includes(o.key)} onClick={() => toggle(o.key)}>
          <i style={{ background: o.color }} aria-hidden="true" />{o.label}</button>)}
      </div>
    </div>
    <HistoryChart rows={shown} series={series} band={{ lo: band.lo, hi: band.hi }} lines={[{ v: 0.55, label: "55%: RISK-ON" }]}
      markers={eps.map(e => e.start)} aria={`Share of coins in Uptrend with BTC price, ${RANGES.find(r => r.key === range).label}`} />
    <section className="mh-episodes" aria-labelledby="mh-ep-title">
      <div className="mh-section-head">
        <h3 id="mh-ep-title">Last times we were here</h3>
        <Tabs small label="Uptrend band" value={band.label} onChange={setBandLabel}
          items={data.bands.map(b => ({ key: b.label, label: b.label === t.band ? `${b.label} (today)` : b.label }))} />
      </div>
      <p>{bandSummary(band)}</p>
      {base && <p className="mh-muted">An ordinary 30 days since {monthYear(t.since)}: BTC {signedPct(base.btc.median)}, typical alt {signedPct(base.alt.median)} (medians). Alts usually drift down against a flat BTC, so better than ordinary is not the same as up.</p>}
      <div className="mh-table-wrap">
        <table className="mh-table">
          <thead><tr><th scope="col">Started</th><th scope="col">Days</th><th scope="col">Uptrend</th>
            <th scope="col">BTC 30d</th><th scope="col">Typical alt 30d</th><th scope="col">vs ordinary</th><th scope="col">Typical alt 60d</th></tr></thead>
          <tbody>
            {eps.map(e => {
              const vs = e.scored && e.alt30 != null && base ? e.alt30 - base.alt.median : null;
              return <tr key={e.start}>
                <td>{dayDate(e.start)}</td><td>{e.end - e.start + 1}{e.end >= t.day ? ", ongoing" : ""}</td><td>{pctLabel(e.breadth)}</td>
                {e.scored ? <>
                  <td>{signedPct(e.btc30)}</td><td>{signedPct(e.alt30)}</td>
                  <td className={vs == null ? "" : vs > 0 ? "mh-better" : "mh-worse"}>{vs == null ? "—" : `${vs > 0 ? "better" : "worse"} ${signedPct(vs, 0).replace("%", " pts")}`}</td>
                  <td>{signedPct(e.alt60)}</td>
                </> : <td colSpan={4} className="mh-muted">Not scored (after {dayDate(data.end_day)})</td>}
              </tr>;
            })}
          </tbody>
        </table>
      </div>
      <p className="mh-muted">An episode is a run of days in the same band (gaps of up to 5 days joined); outcomes are measured from its first day. Episodes, not days, are counted because neighbouring days share the same future. Outcomes are scored only up to {dayDate(data.end_day)}, the end of the study window; later episodes are listed without them. The coin list is today's, so coins that died are missing and early years are thinner. No probabilities are shown.</p>
    </section>
  </>;
}

function FearGreedTab({ rows, range, setRange, fg }) {
  const shown = inRange(rows, range);
  const last = [...rows].reverse().find(r => r.fg != null);
  const vals = shown.map(r => r.fg).filter(v => v != null);
  const greedy = vals.length ? Math.round((100 * vals.filter(v => v >= 70).length) / vals.length) : null;
  const series = [{ key: "fgShare", label: "Fear & Greed", color: "var(--t-accent)", width: 1.5 }];
  const withShare = shown.map(r => ({ ...r, fgShare: r.fg == null ? null : r.fg / 100 }));
  return <>
    <div className="mh-today">
      <strong>{last ? last.fg : "—"}</strong>
      <div>
        <p>{last ? `Fear & Greed on ${dayDate(last.day)}: higher than on ${percentileOf([...fg.values()], last.fg)}% of days since ${monthYear([...fg.keys()][0] || last.day)}.` : "No Fear & Greed history yet."}</p>
        <p className="mh-muted">{greedy == null ? "" : `In this range it was at 70 or above on ${greedy}% of days; there the engine's Not greedy check fails on every market. `}Source: alternative.me, daily.</p>
      </div>
    </div>
    <div className="mh-controls"><Tabs small label="Range" items={RANGES} value={range} onChange={setRange} /></div>
    <HistoryChart rows={withShare} series={series} axis={v => String(Math.round(100 * v))}
      lines={[{ v: 0.7, label: "70: Not greedy fails" }, { v: 0.4, label: "40: fear gate opens" }]}
      aria="Fear and Greed index with BTC price" />
    <p className="mh-muted">The dial's bands are the scanner's own (20 / 40 / 60 / 80). At 70 or above the Not greedy check fails for every market; at 40 or below the fear gate lets Accumulate setups in Accumulation and Capitulation revivals fire. No study has tested what followed each level, so none is shown.</p>
  </>;
}

// Right-side drawer with the scanner's market history. Opens from the consensus and dial icons.
export default function MarketHistoryDrawer({ tab, onTab, onClose }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [range, setRange] = useState("3y");
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
    const onKey = e => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; prev?.focus?.(); };
  }, [onClose]);
  const fg = useMemo(() => fearGreedByDay(data), [data]);
  const rows = useMemo(() => rowsOf(data).map(r => ({ ...r, fg: fg.get(r.day) ?? null })), [data, fg]);
  return createPortal(<div className="reflex-terminal">
    <div className="mh-backdrop" onClick={onClose} />
    <aside className="mh-drawer" role="dialog" aria-modal="true" aria-labelledby="mh-title">
      <header className="mh-head">
        <h2 id="mh-title">Market history</h2>
        <button ref={closeRef} type="button" className="mh-close" onClick={onClose}>Close</button>
      </header>
      <Tabs label="History" value={tab} onChange={onTab}
        items={[{ key: "breadth", label: "Uptrend share" }, { key: "fear", label: "Fear & Greed" }]} />
      <div className="mh-body">
        {!data ? <p className="mh-muted">{failed ? "History is unavailable right now." : "Loading history…"}</p>
          : tab === "fear" ? <FearGreedTab rows={rows} range={range} setRange={setRange} fg={fg} />
            : <BreadthTab data={data} rows={rows} range={range} setRange={setRange} />}
      </div>
    </aside>
  </div>, document.body);
}
