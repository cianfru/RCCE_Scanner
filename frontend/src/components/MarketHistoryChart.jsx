import { useEffect, useRef, useState } from "react";
import HelpTip from "./HelpTip.jsx";
import { T as TH } from "../theme.js";
import { COPY, FAN_H, FAN_MARKS, altTicks, btcSide, compactUsd, dayDate, fanGeometry, fanMedian, fmtSeries, logTicks,
         monthOf, pctLabel, readoutCells, signedPct, usd } from "../utils/marketHistory.js";
import { WCOPY, Z_GUIDE, Z_SCALE } from "../utils/walletHistory.js";

// Width of an element, tracked with ResizeObserver.
export function useWidth(initial = 680) {
  const ref = useRef(null);
  const [w, setW] = useState(initial);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

export const SERIES_COLOR = () => ({ uptrend: "var(--t-accent)", btc: "var(--t-text2)", alt: TH.purple });

// Runs of days with BTC below the lower edge of its weekly band: [firstDay, lastDay + 1].
function belowRuns(rows) {
  const out = [];
  for (const r of rows) {
    if (!(r.bandLo != null && r.btc > 0 && r.btc < r.bandLo)) continue;
    const last = out[out.length - 1];
    if (last && r.day - last[1] <= 1) last[1] = r.day + 1; else out.push([r.day, r.day + 1]);
  }
  return out;
}

const pts = list => list.map(([a, b]) => `${a.toFixed(1)},${b.toFixed(1)}`).join("L");
const area = (poly, x, y) => (poly.length < 2 ? "" :
  `M${pts(poly.map(p => [x(p), y(p[1])]))}L${pts([...poly].reverse().map(p => [x(p), y(p[2])]))}Z`);
// The same area in pixels, at least `min` px tall (BTC's band is only a few px high at 3M).
function thickArea(poly, x, y, min = 3) {
  if (poly.length < 2) return "";
  const px = poly.map(p => {
    const a = y(p[1]), b = y(p[2]), mid = (a + b) / 2, half = Math.max(min / 2, Math.abs(a - b) / 2);
    return [x(p), mid + half, mid - half];
  });
  return `M${pts(px.map(p => [p[0], p[1]]))}L${pts([...px].reverse().map(p => [p[0], p[2]]))}Z`;
}

// A small flat key for the fan's lines: dashed median, dotted ordinary.
function Legend({ median }) {
  const sw = (cls, key) => <span key={key} className="mh-legend-item"><svg width="18" height="6" aria-hidden="true">
    <line className={cls} x1="0" x2="18" y1="3" y2="3" /></svg>{COPY.legend[key]}</span>;
  return <span className="mh-legend">{median && sw("mh-legend-median", "median")}{sw("mh-legend-ordinary", "ordinary")}</span>;
}

// Runs of rows where get(r) is a number: [[row, value], ...] each.
function runsOf(rows, get) {
  const out = [];
  let cur = null;
  for (const r of rows) {
    const v = get(r);
    if (v == null || !Number.isFinite(v)) { cur = null; continue; }
    if (!cur) { cur = []; out.push(cur); }
    cur.push([r.day, v]);
  }
  return out;
}

// The area between y(0) and the series, one closed path per run of values.
function areaToZero(rows, get, x, y) {
  return runsOf(rows, get).map(run => `M${x(run[0][0]).toFixed(1)},${y(0).toFixed(1)}L${pts(run.map(([d, v]) => [x(d), y(v)]))}`
    + `L${x(run[run.length - 1][0]).toFixed(1)},${y(0).toFixed(1)}Z`).join("");
}

// Share panels: the scale's half-height, a round step at or above the largest share shown (at least 20%).
export function shareScale(rows, keys) {
  let m = 0;
  for (const r of rows) for (const k of keys) { const w = r.wallet?.[k]; if (w) m = Math.max(m, w.L ?? 0, w.S ?? 0); }
  return [0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1].find(s => s >= m * 1.05) || 1;
}

// Past ticks: months at 3M and 6M, quarters at 1Y, years beyond. Future ticks: Today, +30d, +60d; overlapping labels drop.
function xTicks(range, d0, T, x, future, width, padR) {
  const past = [];
  const start = new Date(d0 * 86_400_000);
  for (let y = start.getUTCFullYear(), m = start.getUTCMonth() + 1; ; m++) {
    if (m > 11) { m = 0; y++; }
    const day = Date.UTC(y, m, 1) / 86_400_000;
    if (day > T) break;
    if (range === "3m" || range === "6m") past.push({ day, label: monthOf(day) });
    else if (range === "1y") { if (m % 3 === 0) past.push({ day, label: m === 0 ? String(y) : monthOf(day) }); }
    else if (m === 0) past.push({ day, label: String(y) });
  }
  const want = future ? [{ day: T, label: COPY.axis.today, p: 0 }, { day: T + FAN_H, label: COPY.axis.h(FAN_H), p: 1 },
    ...FAN_MARKS.filter(k => k !== FAN_H).map(k => ({ day: T + k, label: COPY.axis.h(k), p: 2 }))] : [];
  const all = [...want, ...past.map(t => ({ ...t, p: 3 }))];
  const kept = [];
  const span = t => { const w = t.label.length * 6.6 + 8; const c = x(t.day); return [c - w / 2, c + w / 2]; };
  for (const t of all.sort((a, b) => a.p - b.p)) {
    const [a, b] = span(t);
    if (b > width - padR + 40 || a < 0) continue;
    if (kept.some(k => { const [c, d] = span(k); return a < d && c < b; })) continue;
    kept.push(t);
  }
  return kept;
}

/**
 * The market history page's chart. Past: BTC (log) with its weekly band, the Uptrend share (or Fear & Greed), and at
 * 3M the typical alt against today; under them, with `wallets`, one long/short panel per wallet group. With a fan: a
 * future zone out to +60 days holding what followed similar past days.
 */
export default function MarketHistoryChart({ mode, rows, range, fan, fanPop, overlays = [], selBand, markers = [], today, aria,
                                            wallets = null }) {
  const [box, W] = useWidth();
  const [hover, setHover] = useState(null);
  const future = mode === "breadth";
  useEffect(() => {
    if (hover == null) return undefined;
    const off = e => { if (box.current && !box.current.contains(e.target)) setHover(null); };
    document.addEventListener("pointerdown", off);
    return () => document.removeEventListener("pointerdown", off);
  }, [hover, box]);
  if (rows.length < 2) return <div ref={box} className="mh-empty">{COPY.empty}</div>;

  const C = SERIES_COLOR();
  const phone = W < 520;
  const padL = 8, padR = 44, gap = 12, axisH = 18;
  const showAlt = future && range === "3m";
  // At 3M the typical-alt panel (the one series whose bands passed) takes room from the Uptrend panel.
  // A wide page gets taller panels so the chart keeps its shape.
  const k = W >= 960 ? 1.35 : 1;
  const hB = phone ? 84 : Math.round(110 * k);
  const hU = showAlt ? (phone ? 96 : Math.round(130 * k)) : (phone ? 110 : Math.round(150 * k));
  const hA = phone ? 76 : Math.round(96 * k);
  const yU0 = hB + gap, yA0 = yU0 + hU + gap;
  const marketBottom = showAlt ? yA0 + hA : yU0 + hU;
  // Wallet panels (the market history page): one per group under the market panels, each with room for its label.
  const hW = phone ? 72 : Math.round(92 * k), labelH = 16;
  const wGroups = wallets?.groups || [];
  const yW0 = wGroups.map((_, i) => marketBottom + gap + labelH + i * (hW + gap + labelH));
  const bottom = wGroups.length ? yW0[yW0.length - 1] + hW : marketBottom;
  const H = bottom + axisH;
  const Td = rows[rows.length - 1].day;
  const g = fanGeometry({ fan: future ? fan : null, T: Td, d0: rows[0].day, width: W, padL, padR, future });
  const x = g.x;
  const kx = i => x(Td + fan.k[i]);
  const f = future ? fan : null;
  const show = f?.show || {};
  const inFuture = hover?.future;

  // BTC panel, log scale over everything drawn in it.
  const btcVals = rows.flatMap(r => [r.btc, r.bandLo, r.bandHi]);
  if (f) btcVals.push(...f.paths.btc.flat(), ...(f.ordinary?.btc || []));
  const bv = btcVals.filter(v => v > 0);
  const lo = Math.min(...bv), hi = Math.max(...bv);
  const yb = v => 4 + (1 - (Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo) || 1)) * (hB - 8);
  const yp = v => yU0 + (1 - v) * hU;                           // 0..1
  const yz = z => yp((Math.max(-3, Math.min(3, z)) + 3) / 6);   // median z on its own -3..3 scale
  // Typical-alt panel: % against today, symmetric around 0, covering every path.
  const altVals = rows.map(r => r.alt);
  if (f && showAlt) altVals.push(...f.paths.alt.flat(), ...(f.ordinary?.alt || []));
  const am = Math.max(5, ...altVals.filter(v => v != null).map(Math.abs)) * 1.08;
  const ya = v => yA0 + ((am - v) / (2 * am)) * hA;
  const Y = { uptrend: yp, btc: yb, alt: ya };

  const line = (get, y) => {
    let d = "", pen = false;
    for (const r of rows) {
      const v = get(r);
      if (v == null) { pen = false; continue; }
      d += `${pen ? "L" : "M"}${x(r.day).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    }
    return d;
  };
  const knotLine = (vals, y) => {
    const p = vals.map((v, i) => (v == null ? null : [kx(i), y(v)])).filter(Boolean);
    return p.length < 2 ? "" : `M${pts(p)}`;
  };

  function fanMarks(s) {
    if (!f) return null;
    const y = Y[s], col = C[s];
    const poly = g.polys[s];
    const med = fanMedian(f, s);
    const bands = show[s] === "bands" && poly;
    const iMarks = FAN_MARKS.map(k => f.k.indexOf(k));
    return <g className={`mh-fan mh-fan-${s}`}>
      {bands && <path className="mh-fan-outer" style={{ fill: col }} d={area(poly.outer, p => p[0], y)} />}
      {bands && <path className="mh-fan-mid" style={{ fill: col }} d={area(poly.mid, p => p[0], y)} />}
      {(!bands || inFuture) && f.paths[s].map((p, j) => <path key={j} className="mh-fan-path" style={{ stroke: col }} d={knotLine(p, y)} />)}
      {s !== "uptrend" && f.ordinary?.[s] && <path className="mh-ordinary" d={knotLine(f.ordinary[s], y)} />}
      {f.paths[s].map((p, j) => iMarks.map(i => (p[i] == null ? null :
        <circle key={`${j}-${i}`} className={`mh-land${f.episodes[j]?.[3] ? " is-below" : ""}`} cx={kx(i)} cy={y(p[i])} r={2.5}
          style={{ fill: f.episodes[j]?.[3] ? "none" : col, stroke: col }} />)))}
      {med.length > 1 && <path className="mh-median" style={{ stroke: col }} d={`M${pts(med.map(([i, v]) => [kx(i), y(v)]))}`} />}
      {med.filter(([i]) => iMarks.includes(i)).map(([i, v]) => <circle key={i} className="mh-median-dot" cx={kx(i)} cy={y(v)} r={3.5} style={{ fill: col }} />)}
    </g>;
  }

  const onPoint = e => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const day = g.d0 + ((px - padL) / (W - padL - padR)) * (g.d1 - g.d0);
    if (future && fan && day > Td + 2.5) {
      const i = Math.max(1, Math.min(fan.k.length - 1, Math.round((day - Td) / (fan.k[1] - fan.k[0]))));
      setHover({ future: true, i });
      return;
    }
    let best = 0;
    for (let i = 0; i < rows.length; i++) if (Math.abs(rows[i].day - day) < Math.abs(rows[best].day - day)) best = i;
    setHover({ row: best });
  };
  const h = hover?.row != null ? rows[hover.row] : null;
  const cursorX = h ? x(h.day) : inFuture ? kx(hover.i) : null;
  const zOn = overlays.some(o => o.axis === "z");
  const labelX = padL + 2 + (zOn ? 22 : 0);
  const ticks = xTicks(range, g.d0, Td, x, future, W, padR);
  const zoneW = g.zone ? g.zone[1] - g.zone[0] : 0;
  const caption = !future ? null : f ? COPY.caption(f.episodes.length, f.runs, f.too_few) : COPY.tooFewDays;
  const capFits = caption && caption.length * 6.4 + 26 <= zoneW + padR - 4;

  return <div ref={box} className="mh-chart">
    {future && <div className="mh-fan-cap" style={{ paddingRight: padR - 4 }}>
      {f && <Legend median={!f.too_few} />}
      {capFits && <span className="mh-fan-caption">{caption}</span>}
      {fanPop}
    </div>}
    <div className="mh-chart-plot">
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={aria}
        onPointerMove={onPoint} onPointerDown={onPoint} onPointerLeave={e => { if (e.pointerType === "mouse") setHover(null); }}>
        {g.zone && <rect className="mh-zone" x={g.zone[0]} width={zoneW} y={0} height={bottom} />}
        {/* BTC */}
        {logTicks(lo, hi).map(v => <g key={v}>
          <line className="mh-grid" x1={padL} x2={W - padR} y1={yb(v)} y2={yb(v)} />
          <text className="mh-tick" x={W - padR + 6} y={yb(v) + 4}>{compactUsd(v)}</text>
        </g>)}
        {belowRuns(rows).map(([a, b]) => <rect key={a} className="mh-below" x={x(a)} width={Math.max(1, x(b) - x(a))} y={0} height={hB} />)}
        <path className="mh-bandfill" d={thickArea(rows.filter(r => r.bandLo != null && r.bandHi != null).map(r => [r.day, r.bandLo, r.bandHi]), p => x(p[0]), yb)} />
        <path className="mh-bandline" d={line(r => r.bandLo, yb)} />
        <path className="mh-btc" d={line(r => r.btc || null, yb)} />
        {fanMarks("btc")}
        {/* Uptrend share, or Fear & Greed */}
        {mode === "fear" && <>
          <rect className="mh-zone-greed" x={padL} width={x(Td) - padL} y={yp(1)} height={yp(0.7) - yp(1)} />
          <rect className="mh-zone-fear" x={padL} width={x(Td) - padL} y={yp(0.4)} height={yp(0) - yp(0.4)} />
        </>}
        {selBand && <rect className="mh-band" x={padL} width={x(Td) - padL} y={yp(Math.min(1, selBand.hi))} height={yp(selBand.lo) - yp(Math.min(1, selBand.hi))} />}
        {[0, 0.25, 0.5, 0.75, 1].map(v => <g key={v}>
          <line className="mh-grid" x1={padL} x2={W - padR} y1={yp(v)} y2={yp(v)} />
          <text className="mh-tick" x={W - padR + 6} y={yp(v) + 4}>{mode === "fear" ? Math.round(100 * v) : pctLabel(v)}</text>
        </g>)}
        {zOn && [-3, 0, 3].map(z => <text key={z} className="mh-tick mh-ztick" x={padL + 2} y={yz(z) + (z === 3 ? 10 : z === -3 ? -3 : 4)}>{z > 0 ? `+${z}` : z === 0 ? "0" : `−${-z}`}</text>)}
        {mode === "breadth" && <line className="mh-line" x1={padL} x2={W - padR} y1={yp(0.55)} y2={yp(0.55)} />}
        {overlays.map(s => <path key={s.key} className="mh-series" d={line(r => r[s.key], s.axis === "z" ? yz : yp)}
          style={{ stroke: s.color, strokeDasharray: s.dash, strokeWidth: s.width || 1.25 }} />)}
        {mode === "breadth"
          ? <path className="mh-series" d={line(r => r.uptrend, yp)} style={{ stroke: C.uptrend, strokeWidth: 1.75 }} />
          : <path className="mh-series" d={line(r => (r.fg == null ? null : r.fg / 100), yp)} style={{ stroke: "var(--t-accent)", strokeWidth: 1.5 }} />}
        {fanMarks("uptrend")}
        {/* The fan starts from the Uptrend + Overheated share; when Overheated fires, join it to the plotted line. */}
        {f && today?.row && Math.abs(today.uptrend - today.row.uptrend) > 0.002 &&
          <line className="mh-series" x1={x(Td)} x2={x(Td)} y1={yp(today.row.uptrend)} y2={yp(today.uptrend)} style={{ stroke: C.uptrend, strokeWidth: 1.75 }} />}
        {markers.filter(m => m >= g.d0 && m <= Td).map(m => <line key={m} className="mh-marker" x1={x(m)} x2={x(m)} y1={yU0 + hU - 8} y2={yU0 + hU} />)}
        {/* Typical alt vs today */}
        {showAlt && <>
          {altTicks(am).map(v => <g key={v}>
            <line className={v === 0 ? "mh-zero" : "mh-grid"} x1={padL} x2={W - padR} y1={ya(v)} y2={ya(v)} />
            <text className="mh-tick" x={W - padR + 6} y={ya(v) + 4}>{v > 0 ? `+${v}%` : v < 0 ? `−${-v}%` : "0"}</text>
          </g>)}
          <path className="mh-series" d={line(r => r.alt, ya)} style={{ stroke: C.alt, strokeWidth: 1.5 }} />
          {fanMarks("alt")}
        </>}
        {wGroups.map((wg, i) => <WalletPanel key={wg.key} group={wg} rows={rows} x={x} y0={yW0[i]} h={hW} padL={padL}
          right={W - padR} todayX={x(Td)} mode={wallets.mode} scale={wallets.mode === "share" ? shareScale(rows, wGroups.map(gg => gg.key)) : Z_SCALE}
          from={wallets.from} d0={g.d0} />)}
        {/* Labels last, so their halo sits over the lines. */}
        {mode === "breadth" && <text className="mh-line-label" x={labelX} y={yp(0.55) - 4}>{COPY.riskOn}</text>}
        {mode === "fear" && <>
          <text className="mh-line-label mh-zone-label" x={labelX} y={yp(0.7) - 4}>{COPY.zones.greed}</text>
          <text className="mh-line-label mh-zone-label" x={labelX} y={yp(0.4) + 13}>{COPY.zones.fear}</text>
        </>}
        <text className="mh-panel-label" x={labelX} y={yU0 + 14}>{mode === "fear" ? COPY.panel.fg : COPY.panel.uptrend}</text>
        {showAlt && <text className="mh-panel-label" x={padL + 2} y={yA0 + 12}>{COPY.panel.alt}</text>}
        {/* Today, +30, +60 */}
        {g.zone && <>
          <line className="mh-today-line" x1={x(Td)} x2={x(Td)} y1={0} y2={bottom} />
          {FAN_MARKS.map(k => <line key={k} className="mh-hair" x1={x(Td + k)} x2={x(Td + k)} y1={0} y2={bottom} />)}
        </>}
        {ticks.map(t => <text key={`${t.label}-${t.day}`} className={`mh-tick${t.p < 3 ? " mh-tick-f" : ""}`} x={x(t.day)} y={H - 4} textAnchor="middle">{t.label}</text>)}
        {cursorX != null && <line className="mh-cursor" x1={cursorX} x2={cursorX} y1={0} y2={bottom} />}
      </svg>
      <span className="mh-btc-label" style={{ left: padL + 2 }}>{COPY.panel.btc}<HelpTip title={COPY.pop.bandTitle} width={320} size={13}>
        {COPY.pop.band().map((p, i) => <span key={i}>{p}</span>)}</HelpTip></span>
      {wGroups.map((wg, i) => <span key={wg.key} className="mh-btc-label mh-wallet-label" style={{ left: padL + 2, top: yW0[i] - labelH - 1 }}>
        {wg.label}<span className="mh-wallet-key" aria-hidden="true"><i className="is-long" />{WCOPY.long}<i className="is-short" />{WCOPY.short}</span>
        {wg.info}</span>)}
    </div>
    <Readout mode={mode} rows={rows} h={h} hover={hover} fan={f} today={today} showAlt={showAlt} overlays={overlays} wallets={wallets} />
  </div>;
}

// The numbers under the chart: Today / +30d / +60d by default, one column while hovering.
function Readout({ mode, h, hover, fan, today, showAlt, overlays, wallets }) {
  const wGroups = wallets?.groups || [];
  const R = COPY.readout;
  const side = r => { const s = btcSide(r.btc, r.bandLo != null ? [r.bandLo, r.bandHi] : null); return s ? ` · ${R.side[s]}` : ""; };
  const cell = (s, i) => {
    if (i === 0) return <td key={i}><b>{fmtSeries(s, today[s])}</b></td>;
    const c = readoutCells(fan, s, i);
    // A paths-mode median (its bands did not pass the check) is shown muted, not as the lead number.
    return <td key={i}>{c.lead ? <b>{c.median || "—"}</b> : <i>{c.median || "—"}</i>}{c.spread && <span>{c.spread}</span>}</td>;
  };
  const ordFmt = (s, v) => (s === "alt" ? signedPct(v, 1) : fmtSeries(s, v));
  const ord = (s, i) => <td key={i}>{i === 0 ? "" : ordFmt(s, fan?.ordinary?.[s]?.[i])}</td>;
  let head, body;
  if (h || mode === "fear") {
    const r = h || today.row;
    head = [dayDate(r.day)];
    body = [[R.btc, `${usd(r.btc)}${side(r)}`]];
    if (mode === "breadth") body.push([R.uptrend, pctLabel(r.uptrend)]);
    if (mode === "fear") body.push([R.fg, r.fg ?? "—"]);
    if (showAlt && r.alt != null) body.push([R.alt, R.altVs(fmtSeries("alt", r.alt))]);
    for (const o of overlays) if (r[o.key] != null) body.push([R[o.key], o.axis === "z" ? r[o.key].toFixed(2) : o.key === "fg" ? Math.round(100 * r[o.key]) : pctLabel(r[o.key])]);
    for (const wg of wGroups) body.push([wg.label, WCOPY.readout(r.wallet?.[wg.key], wallets.mode)]);
    return <div className={`mh-readout-wrap mh-readout-${mode}${showAlt ? "" : " is-short"}${wGroups.length ? " has-wallets" : ""}`}><table className="mh-readout">
      <thead><tr><th scope="col" /><th scope="col">{head[0]}</th></tr></thead>
      <tbody>{body.map(([k, v]) => <tr key={k}><th scope="row">{k}</th><td><b>{v}</b></td></tr>)}</tbody>
    </table></div>;
  }
  const idx = hover?.future ? [hover.i] : [0, ...FAN_MARKS.map(k => fan?.k.indexOf(k) ?? -1).filter(i => i > 0)];
  const label = i => (i === 0 ? R.today : COPY.axis.h(fan.k[i]));
  const cols = fan ? idx : [0];
  const wToday = today?.row?.wallet || {};
  return <div className={`mh-readout-wrap${showAlt ? "" : " is-short"}${wGroups.length ? " has-wallets" : ""}`}><table className="mh-readout">
    <thead><tr><th scope="col" className="mh-readout-what">{fan ? R.fanHead : ""}</th>{cols.map(i => <th key={i} scope="col">{label(i)}</th>)}</tr></thead>
    <tbody>
      <tr><th scope="row">{R.uptrend}</th>{cols.map(i => cell("uptrend", i))}</tr>
      <tr><th scope="row">{R.btc}</th>{cols.map(i => cell("btc", i))}</tr>
      {fan && <tr className="mh-ord"><th scope="row">{R.ordinary}</th>{cols.map(i => ord("btc", i))}</tr>}
      {showAlt && <tr><th scope="row">{R.alt}</th>{cols.map(i => cell("alt", i))}</tr>}
      {showAlt && fan && <tr className="mh-ord"><th scope="row">{R.ordinary}</th>{cols.map(i => ord("alt", i))}</tr>}
      {/* Today only, across the columns, so the long wallet line does not widen the Today column. */}
      {wGroups.map(wg => <tr key={wg.key}><th scope="row">{wg.label}</th>
        <td colSpan={cols.length}><b>{WCOPY.readout(wToday[wg.key], wallets.mode)}</b></td></tr>)}
    </tbody>
  </table></div>;
}

// One wallet group's panel: longs above the zero line in green, shorts below it in red. Z-score mode draws each
// share's z-score (the short one negated, so more shorts reach lower) with the area filled on its own side only;
// share mode draws the long and short shares of the group's wallets.
function WalletPanel({ group, rows, x, y0, h, padL, right, todayX, mode, scale, from, d0 }) {
  const mid = y0 + h / 2, half = h / 2 - 3;
  const y = v => mid - (Math.max(-scale, Math.min(scale, v)) / scale) * half;
  const k = group.key;
  const w = r => r.wallet?.[k];
  const long = mode === "share" ? r => w(r)?.L ?? null : r => w(r)?.zL ?? null;
  const short = mode === "share" ? r => (w(r)?.S == null ? null : -w(r).S) : r => (w(r)?.zS == null ? null : -w(r).zS);
  const longFill = mode === "share" ? long : r => (long(r) == null ? null : Math.max(0, long(r)));
  const shortFill = mode === "share" ? short : r => (short(r) == null ? null : Math.min(0, short(r)));
  const path = get => runsOf(rows, get).map(run => `M${pts(run.map(([d, v]) => [x(d), y(v)]))}`).join("");
  const green = TH.green, red = TH.red;
  const ticks = mode === "share" ? [scale / 2, -scale / 2] : [Z_GUIDE, -Z_GUIDE];
  const tickText = v => (mode === "share" ? `${Math.round(100 * Math.abs(v))}%` : v > 0 ? `+${v}` : `−${-v}`);
  const firstX = from != null && from > d0 ? x(from) : null;
  return <g className="mh-wallet" data-group={k}>
    <rect className="mh-wallet-bg" x={padL} width={todayX - padL} y={y0} height={h} />
    {ticks.map(v => <g key={v}>
      <line className="mh-wallet-guide" x1={padL} x2={right} y1={y(v)} y2={y(v)} />
      <text className="mh-tick" x={right + 6} y={y(v) + 4}>{tickText(v)}</text>
    </g>)}
    <line className="mh-zero" x1={padL} x2={right} y1={mid} y2={mid} />
    <text className="mh-tick" x={right + 6} y={mid + 4}>0</text>
    <path className="mh-wallet-area" style={{ fill: green }} d={areaToZero(rows, longFill, x, y)} />
    <path className="mh-wallet-area" style={{ fill: red }} d={areaToZero(rows, shortFill, x, y)} />
    <path className="mh-wallet-line" style={{ stroke: green }} d={path(long)} />
    <path className="mh-wallet-line" style={{ stroke: red }} d={path(short)} />
    {firstX != null && firstX - padL > 150 && <text className="mh-wallet-from" x={(padL + firstX) / 2} y={mid + 4} textAnchor="middle">{WCOPY.from(from)}</text>}
    {firstX != null && <line className="mh-wallet-start" x1={firstX} x2={firstX} y1={y0} y2={y0 + h} />}
  </g>;
}
