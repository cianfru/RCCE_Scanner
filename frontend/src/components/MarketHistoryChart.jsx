import { useEffect, useRef, useState } from "react";
import HelpTip from "./HelpTip.jsx";
import { T as TH } from "../theme.js";
import { COPY, FAN_H, FAN_MARKS, altTicks, btcSide, compactUsd, dayDate, fanGeometry, fanMedian, fanRange, fmtSeries,
         logTicks, monthOf, pctLabel, readoutCells, signedPct, usd } from "../utils/marketHistory.js";
import { WCOPY, shareScale } from "../utils/walletHistory.js";

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

// A small key: a line, dashed line, range mark or shaded box, then its words.
export function Swatch({ kind = "line", color = "var(--t-text2)", dash }) {
  return <svg className="mh-swatch" width="18" height="12" aria-hidden="true">
    {kind === "range" && <><line x1="9" x2="9" y1="1" y2="11" style={{ stroke: color }} /><line x1="7" x2="11" y1="1" y2="1" style={{ stroke: color }} />
      <line x1="7" x2="11" y1="11" y2="11" style={{ stroke: color }} /><rect className="mh-fan-box" x="6.5" y="3.5" width="5" height="5" style={{ fill: color }} /></>}
    {kind === "box" && <rect x="1" y="3" width="16" height="6" rx="1" style={{ fill: color, opacity: 0.3 }} />}
    {kind === "line" && <line x1="0" x2="18" y1="6" y2="6" style={{ stroke: color, strokeDasharray: dash }} />}
  </svg>;
}

// The fan's key: the median line and the mark at +30 and +60 days (box: middle half of past paths; line: range).
function FanLegend({ median }) {
  const item = (kind, key) => <span key={key} className="mh-legend-item"><Swatch kind={kind} />{COPY.legend[key]}</span>;
  return <span className="mh-legend">{median && item("line", "median")}{item("range", "range")}</span>;
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

// Today's value of each line in the Uptrend panel, for its key.
const signed1 = v => `${v > 0.05 ? "+" : v < -0.05 ? "−" : ""}${Math.abs(v).toFixed(1)}`;
const overlayValue = (o, r) => (r?.[o.key] == null ? null : o.axis === "z" ? signed1(r[o.key])
  : o.key === "fg" ? String(Math.round(100 * r[o.key])) : pctLabel(r[o.key]));

/**
 * The market history page's chart. Past: BTC (log) with its weekly band, the Uptrend share (or Fear & Greed), and at
 * 3M the typical alt against today; under them, with `wallets`, one long/short panel per wallet group. With a fan: a
 * future zone out to +60 days holding what followed similar past days (median, middle half where it passed its
 * check, and the lowest-to-highest range at +30 and +60 days; the single paths show while the pointer is there).
 */
export default function MarketHistoryChart({ mode, rows, range, fan, fanPop, overlays = [], today, aria, wallets = null }) {
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
  const padL = 8, padR = 44, gap = 12, axisH = 18, topH = 14;
  const showAlt = future && range === "3m";
  // At 3M the typical-alt panel (the one series whose bands passed) takes room from the Uptrend panel.
  // A wide page gets taller panels so the chart keeps its shape.
  const k = W >= 960 ? 1.35 : 1;
  const hB = phone ? 84 : Math.round(110 * k);
  const hU = showAlt ? (phone ? 96 : Math.round(130 * k)) : (phone ? 110 : Math.round(150 * k));
  const hA = phone ? 76 : Math.round(96 * k);
  const yB0 = future ? topH : 0;
  const yU0 = yB0 + hB + gap, yA0 = yU0 + hU + gap;
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
  if (f) btcVals.push(...f.paths.btc.flat());
  const bv = btcVals.filter(v => v > 0);
  const lo = Math.min(...bv), hi = Math.max(...bv);
  const yb = v => yB0 + 4 + (1 - (Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo) || 1)) * (hB - 8);
  const yp = v => yU0 + (1 - v) * hU;                           // 0..1
  const yz = z => yp((Math.max(-3, Math.min(3, z)) + 3) / 6);   // median z on its own -3..3 scale
  // Typical-alt panel: % against today, symmetric around 0, covering every path.
  const altVals = rows.map(r => r.alt);
  if (f && showAlt) altVals.push(...f.paths.alt.flat());
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

  // One series' fan: shading for the middle half where the series passed its check, the median line, and at +30 and
  // +60 days a mark from the lowest to the highest past path. The single paths show only while the pointer is in
  // the future zone (or when there are too few runs for a median).
  function fanMarks(s) {
    if (!f) return null;
    const y = Y[s], col = C[s];
    const poly = g.polys[s];
    const med = fanMedian(f, s);
    const iMarks = FAN_MARKS.map(m => f.k.indexOf(m)).filter(i => i > 0);
    const paths = inFuture || f.too_few;
    return <g className={`mh-fan mh-fan-${s}`}>
      {poly && <path className="mh-fan-mid" style={{ fill: col }} d={area(poly.mid, p => p[0], y)} />}
      {paths && f.paths[s].map((p, j) => <path key={j} className="mh-fan-path" style={{ stroke: col }} d={knotLine(p, y)} />)}
      {iMarks.map(i => {
        const r = fanRange(f, s, i);
        if (!r) return null;
        const cx = kx(i), a = y(r.lo), b = y(r.hi);
        return <g key={i} className="mh-fan-range" style={{ stroke: col }}>
          <line x1={cx} x2={cx} y1={a} y2={b} /><line x1={cx - 3} x2={cx + 3} y1={a} y2={a} /><line x1={cx - 3} x2={cx + 3} y1={b} y2={b} />
          {r.mid && <rect className="mh-fan-box" x={cx - 3.5} width={7} y={y(r.mid[1])} height={Math.max(2, y(r.mid[0]) - y(r.mid[1]))} style={{ fill: col }} />}
        </g>;
      })}
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
  const last = rows[rows.length - 1];

  return <div ref={box} className="mh-chart">
    {future && <div className="mh-fan-cap" style={{ paddingRight: padR - 4 }}>
      {f && <FanLegend median={!f.too_few} />}
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
        {belowRuns(rows).map(([a, b]) => <rect key={a} className="mh-below" x={x(a)} width={Math.max(1, x(b) - x(a))} y={yB0} height={hB} />)}
        <path className="mh-bandfill" d={thickArea(rows.filter(r => r.bandLo != null && r.bandHi != null).map(r => [r.day, r.bandLo, r.bandHi]), p => x(p[0]), yb)} />
        <path className="mh-bandline" d={line(r => r.bandLo, yb)} />
        <path className="mh-btc" d={line(r => r.btc || null, yb)} />
        {fanMarks("btc")}
        {/* Uptrend share, or Fear & Greed */}
        {mode === "fear" && <>
          <rect className="mh-zone-greed" x={padL} width={x(Td) - padL} y={yp(1)} height={yp(0.7) - yp(1)} />
          <rect className="mh-zone-fear" x={padL} width={x(Td) - padL} y={yp(0.4)} height={yp(0) - yp(0.4)} />
        </>}
        {[0, 0.25, 0.5, 0.75, 1].map(v => <g key={v}>
          <line className="mh-grid" x1={padL} x2={W - padR} y1={yp(v)} y2={yp(v)} />
          <text className="mh-tick" x={W - padR + 6} y={yp(v) + 4}>{mode === "fear" ? Math.round(100 * v) : pctLabel(v)}</text>
        </g>)}
        {zOn && [-3, 0, 3].map(z => <text key={z} className="mh-tick mh-ztick" x={padL + 2} y={yz(z) + (z === 3 ? 10 : z === -3 ? -3 : 4)}>{z > 0 ? `+${z}` : z === 0 ? "0" : `−${-z}`}</text>)}
        {mode === "breadth" && <line className="mh-line" x1={padL} x2={x(Td)} y1={yp(0.55)} y2={yp(0.55)} />}
        {overlays.map(s => <path key={s.key} className="mh-series" d={line(r => r[s.key], s.axis === "z" ? yz : yp)}
          style={{ stroke: s.color, strokeDasharray: s.dash, strokeWidth: s.width || 1.25, opacity: s.opacity }} />)}
        {mode === "breadth"
          ? <path className="mh-series" d={line(r => r.uptrend, yp)} style={{ stroke: C.uptrend, strokeWidth: 1.75 }} />
          : <path className="mh-series" d={line(r => (r.fg == null ? null : r.fg / 100), yp)} style={{ stroke: "var(--t-accent)", strokeWidth: 1.5 }} />}
        {fanMarks("uptrend")}
        {/* The fan starts from the Uptrend + Overheated share; when Overheated fires, join it to the plotted line. */}
        {f && today?.row && Math.abs(today.uptrend - today.row.uptrend) > 0.002 &&
          <line className="mh-series" x1={x(Td)} x2={x(Td)} y1={yp(today.row.uptrend)} y2={yp(today.uptrend)} style={{ stroke: C.uptrend, strokeWidth: 1.75 }} />}
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
          right={W - padR} todayX={x(Td)} scale={shareScale(rows, [wg.key])} from={wg.from} d0={g.d0} />)}
        {/* Labels last, so their halo sits over the lines. */}
        {mode === "breadth" && <text className="mh-line-label" x={labelX} y={yp(0.55) - 4}>{COPY.riskOn}</text>}
        {mode === "fear" && <>
          <text className="mh-line-label mh-zone-label" x={labelX} y={yp(0.7) - 4}>{COPY.zones.greed}</text>
          <text className="mh-line-label mh-zone-label" x={labelX} y={yp(0.4) + 13}>{COPY.zones.fear}</text>
        </>}
        {showAlt && <text className="mh-panel-label" x={padL + 2} y={yA0 + 12}>{COPY.panel.alt}</text>}
        {/* Today, +30, +60: the lines run through every panel, named at the top */}
        {g.zone && <>
          <line className="mh-today-line" x1={x(Td)} x2={x(Td)} y1={0} y2={bottom} />
          {FAN_MARKS.map(m => <line key={m} className="mh-hair" x1={x(Td + m)} x2={x(Td + m)} y1={0} y2={bottom} />)}
          {/* Named at the top too where the zone has room (the axis under the chart always names them) */}
          {zoneW >= 150 && <>
            <text className="mh-top-label" x={x(Td) + 4} y={10}>{COPY.axis.today}</text>
            {FAN_MARKS.map(m => <text key={m} className="mh-top-label" x={x(Td + m) - 4} y={10} textAnchor="end">{COPY.axis.h(m)}</text>)}
          </>}
        </>}
        {ticks.map(t => <text key={`${t.label}-${t.day}`} className={`mh-tick${t.p < 3 ? " mh-tick-f" : ""}`} x={x(t.day)} y={H - 4} textAnchor="middle">{t.label}</text>)}
        {cursorX != null && <line className="mh-cursor" x1={cursorX} x2={cursorX} y1={0} y2={bottom} />}
      </svg>
      <span className="mh-btc-label" style={{ left: padL + 2, top: yB0 }}>{COPY.panel.btc}<HelpTip title={COPY.pop.bandTitle} width={320} size={13}>
        {COPY.pop.band().map((p, i) => <span key={i}>{p}</span>)}</HelpTip></span>
      {/* The Uptrend panel's key: each line as drawn, with today's value */}
      <span className="mh-btc-label mh-key" style={{ left: labelX, top: yU0 + 1 }}>
        <span className="mh-key-item"><Swatch color={mode === "fear" ? "var(--t-accent)" : C.uptrend} />{mode === "fear" ? COPY.panel.fg : COPY.panel.uptrend}
          <b>{mode === "fear" ? (last.fg ?? "—") : pctLabel(last.uptrend)}</b></span>
        {overlays.map(o => <span key={o.key} className="mh-key-item"><Swatch color={o.color} dash={o.dash} />{COPY.overlays[o.key]}
          <b>{overlayValue(o, last) ?? "—"}</b></span>)}
      </span>
      {wGroups.map((wg, i) => <span key={wg.key} className="mh-btc-label mh-wallet-label" style={{ left: padL + 2, top: yW0[i] - labelH - 1 }}>
        {wg.label}<span className="mh-wallet-key" aria-hidden="true"><i className="is-long" />{WCOPY.long}<i className="is-short" />{WCOPY.short}</span>
        {wg.info}</span>)}
    </div>
    <Readout mode={mode} h={h} hover={hover} fan={f} today={today} showAlt={showAlt} overlays={overlays} wallets={wallets} />
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
    for (const wg of wGroups) body.push([wg.label, WCOPY.readout(r.wallet?.[wg.key], wg)]);
    return <div className={`mh-readout-wrap mh-readout-${mode}${showAlt ? "" : " is-short"}${wGroups.length ? " has-wallets" : ""}`}><table className="mh-readout">
      <thead><tr><th scope="col" /><th scope="col">{head[0]}</th></tr></thead>
      <tbody>{body.map(([k, v]) => <tr key={k}><th scope="row">{k}</th><td><b>{v}</b></td></tr>)}</tbody>
    </table></div>;
  }
  const idx = hover?.future ? [hover.i] : [0, ...FAN_MARKS.map(m => fan?.k.indexOf(m) ?? -1).filter(i => i > 0)];
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
        <td colSpan={cols.length}><b>{WCOPY.readout(wToday[wg.key], wg)}</b></td></tr>)}
    </tbody>
  </table></div>;
}

// One wallet group's panel, from zero both ways: the share long rises above the line in green, the share short
// falls below it in red. Each panel has its own scale (a round step above its largest share), named by its ticks.
function WalletPanel({ group, rows, x, y0, h, padL, right, todayX, scale, from, d0 }) {
  const mid = y0 + h / 2, half = h / 2 - 3;
  const y = v => mid - (Math.max(-scale, Math.min(scale, v)) / scale) * half;
  const k = group.key;
  const w = r => r.wallet?.[k];
  const long = r => w(r)?.L ?? null;
  const short = r => (w(r)?.S == null ? null : -w(r).S);
  const path = get => runsOf(rows, get).map(run => `M${pts(run.map(([d, v]) => [x(d), y(v)]))}`).join("");
  const green = TH.green, red = TH.red;
  const ticks = [scale / 2, -scale / 2];
  const firstX = from != null && from > d0 ? x(from) : null;
  return <g className="mh-wallet" data-group={k}>
    <rect className="mh-wallet-bg" x={padL} width={todayX - padL} y={y0} height={h} />
    {ticks.map(v => <g key={v}>
      <line className="mh-wallet-guide" x1={padL} x2={right} y1={y(v)} y2={y(v)} />
      <text className="mh-tick" x={right + 6} y={y(v) + 4}>{`${Math.round(100 * Math.abs(v))}%`}</text>
    </g>)}
    <line className="mh-zero" x1={padL} x2={right} y1={mid} y2={mid} />
    <text className="mh-tick" x={right + 6} y={mid + 4}>0</text>
    <path className="mh-wallet-area" style={{ fill: green }} d={areaToZero(rows, long, x, y)} />
    <path className="mh-wallet-area" style={{ fill: red }} d={areaToZero(rows, short, x, y)} />
    <path className="mh-wallet-line" style={{ stroke: green }} d={path(long)} />
    <path className="mh-wallet-line" style={{ stroke: red }} d={path(short)} />
    {firstX != null && firstX - padL > 120 && <text className="mh-wallet-from" x={(padL + firstX) / 2} y={mid + 4} textAnchor="middle">{WCOPY.from(from)}</text>}
    {firstX != null && <line className="mh-wallet-start" x1={firstX} x2={firstX} y1={y0} y2={y0 + h} />}
  </g>;
}
