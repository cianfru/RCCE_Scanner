import { useEffect, useMemo, useRef, useState } from "react";
import { AreaSeries, BaselineSeries, ColorType, CrosshairMode, LineSeries, LineStyle, PriceScaleMode, createChart,
         createSeriesMarkers } from "lightweight-charts";
import { useTheme } from "../ThemeContext.jsx";
import { T as TH, col, resolveToken } from "../theme.js";
import { apiFetch } from "../edge.js";
import { BCOPY, COLD, CROWD, GREED, HCOPY, HOT, INDICATORS, broadRuns, heatSeries, heatTurns, zoneOf } from "../utils/marketHeat.js";
import { RANGES, dayDate, kUsd, usd } from "../utils/marketHistory.js";
import { deriveRows } from "../utils/deriveWallets.js";

// The market history page's Chart view: one large BTC chart in the manner of a trading terminal. Indicators sit on the
// price (the weekly band, broad uptrends with their roll-over, heat turns, hot and cold days) or in panes of
// their own under it (Uptrend share, taller, Fear & Greed, the wallet groups, Market heat...), all on one time axis;
// drag and scroll to move and zoom, the range buttons to jump. Each pane names its indicator and its value at the
// crosshair (the latest day otherwise). Context, not a signal.

const DAY_S = 86_400;
const MAIN_H = () => (typeof window !== "undefined" && window.innerWidth < 640 ? 300 : Math.max(360, Math.min(560, Math.round(window.innerHeight * 0.5))));
const PANE_H = () => (typeof window !== "undefined" && window.innerWidth < 640 ? 92 : 118);
const TALL = { uptrend: 1.5 };     // the Uptrend share's pane, taller than the others
const paneH = key => Math.round(PANE_H() * (TALL[key] || 1));
const FEAR_GATE = 40;              // Fear & Greed at or below: the engine's fear gate (the dial's own line)

// "#rrggbb" (or "#rgb") at an opacity, as the chart's canvas needs it; other colour strings pass through.
export function hexA(hex, a) {
  const h = String(hex).trim();
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(h);
  if (!m) return h;
  const s = m[1].length === 3 ? m[1].split("").map(c => c + c).join("") : m[1];
  const n = parseInt(s, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

// The pane indicators: the value drawn for a row, the words its legend shows, and how its pane draws it.
export const PANES = {
  heat: { value: (r, x) => x.heat.get(r.day)?.heat, legend: (r, x) => { const h = x.heat.get(r.day); return h ? `${Math.round(h.heat)}` : null; },
    kind: "baseline", base: 50, range: [0, 100], lines: [HOT, COLD], tone: "heat" },
  uptrend: { value: r => (r.uptrend == null ? null : 100 * r.uptrend), legend: r => (r.uptrend == null ? null : `${Math.round(100 * r.uptrend)}%`),
    kind: "line", range: [0, 100], lines: [55], tone: "accent" },
  crowd: { value: r => (r.wallet?.crowd?.L == null ? null : 100 * r.wallet.crowd.L),
    legend: r => { const w = r.wallet?.crowd; return w?.L == null ? null : `${Math.round(100 * w.L)}% long · ${Math.round(100 * w.S)}% short`; },
    kind: "baseline", base: 50, range: [0, 100], lines: [100 * CROWD], tone: "longshort" },
  fg: { value: r => r.fg, legend: r => (r.fg == null ? null : `${r.fg}`), kind: "line", range: [0, 100], lines: [GREED, FEAR_GATE], tone: "orange" },
  smart: { value: r => { const w = r.wallet?.smart; return w?.L == null ? null : 100 * (w.L - w.S); },
    legend: r => { const w = r.wallet?.smart; return w?.L == null ? null : `${Math.round(100 * w.L)}% long · ${Math.round(100 * w.S)}% short`; },
    kind: "baseline", base: 0, tone: "longshort" },
  whales: { value: r => { const w = r.wallet?.whales; return w?.L == null ? null : 100 * (w.L - w.S); },
    legend: r => { const w = r.wallet?.whales; return w?.L == null ? null : `${Math.round(100 * w.L)}% long · ${Math.round(100 * w.S)}% short`; },
    kind: "baseline", base: 0, tone: "longshort" },
  median_z: { value: r => r.median_z, legend: r => (r.median_z == null ? null : `${r.median_z > 0 ? "+" : ""}${r.median_z.toFixed(2)}`),
    kind: "baseline", base: 0, tone: "heat" },
  derive: { value: (r, x) => x.derive.get(r.day)?.share, legend: (r, x) => { const d = x.derive.get(r.day); return d ? `${d.l} long · ${d.s} short` : null; },
    kind: "baseline", base: 50, range: [0, 100], tone: "longshort" },
};
const LABEL = Object.fromEntries(INDICATORS.map(i => [i.key, i.label]));

let deriveCache = null;
const loadDerive = () => (deriveCache ||= apiFetch("/api/market-history/derive").then(r => (r.ok ? r.json() : null)).catch(() => null));

function palette() {
  const text1 = resolveToken("text1") || "#f5fefd";
  return {
    text1, text3: resolveToken("text3") || "#8a9a98", grid: resolveToken("chartGrid") || "rgba(255,255,255,0.05)",
    axis: resolveToken("chartText") || "#9aa", label: resolveToken("chartLabel") || "#1b2b2b", sep: resolveToken("border") || "#223",
    accent: col("#97FCE4"), green: TH.green, red: TH.red, orange: col("#fb923c"), cold: col("#7dd3fc"),
    font: `${getComputedStyle(document.documentElement).getPropertyValue("--font-geist-mono").trim() || "ui-monospace"}, monospace`,
  };
}

function tones(p) {
  return {
    heat: [p.orange, p.cold], longshort: [p.green, p.red], accent: [p.accent], orange: [p.orange],
  };
}

export default function MarketChart({ rows, indicators, range }) {
  const { mode } = useTheme();
  const box = useRef(null);
  const chartRef = useRef(null);
  const [hover, setHover] = useState(null);
  const [tops, setTops] = useState([]);
  const [derive, setDerive] = useState(null);
  const wantDerive = indicators.includes("derive");
  useEffect(() => {
    if (!wantDerive || derive) return undefined;
    let alive = true;
    loadDerive().then(d => { if (alive && d) setDerive(d); });
    return () => { alive = false; };
  }, [wantDerive, derive]);

  const ctx = useMemo(() => {
    const series = heatSeries(rows);
    const dmap = new Map();
    for (const d of deriveRows(derive, "BTC")) {
      if (d.pitL + d.pitS > 0) dmap.set(d.day, { share: (100 * d.pitL) / (d.pitL + d.pitS), l: d.pitL, s: d.pitS });
    }
    return { series, heat: new Map(series.map(s => [s.day, s])), turns: heatTurns(series), derive: dmap, broad: broadRuns(rows) };
  }, [rows, derive]);
  const panes = indicators.filter(k => PANES[k]);
  const height = MAIN_H() + panes.reduce((a, k) => a + paneH(k), 0);

  // Build the chart (again when the indicators or the theme change), keeping the visible range.
  useEffect(() => {
    const el = box.current;
    if (!el || rows.length < 2) return undefined;
    const p = palette();
    const tone = tones(p);
    const kept = chartRef.current?.timeScale().getVisibleRange();
    chartRef.current?.remove();
    const chart = createChart(el, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: p.axis, fontFamily: p.font, fontSize: 11,
        attributionLogo: false, panes: { separatorColor: p.sep, separatorHoverColor: p.sep, enableResize: false } },
      grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
      crosshair: { mode: CrosshairMode.Normal,
        vertLine: { color: hexA(p.text3, 0.5), width: 1, style: LineStyle.Dashed, labelBackgroundColor: p.label },
        horzLine: { color: hexA(p.text3, 0.5), width: 1, style: LineStyle.Dashed, labelBackgroundColor: p.label } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, rightOffset: 3, fixLeftEdge: true, fixRightEdge: true, lockVisibleTimeRangeOnResize: true },
    });
    chartRef.current = chart;
    const t = d => d * DAY_S;

    // Price pane: broad uptrends and hot and cold days behind (full-height areas on hidden scales), BTC on a log scale,
    // the weekly band, then the marks on BTC: the roll-over of each broad uptrend, heat turns.
    const fill = (id, color, on) => {
      const z = chart.addSeries(AreaSeries, { priceScaleId: id, lineVisible: false, lineColor: "rgba(0,0,0,0)", topColor: color,
        bottomColor: color, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false,
        autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 1 } }) }, 0);
      z.priceScale().applyOptions({ scaleMargins: { top: 0, bottom: 0 }, visible: false });
      z.setData(rows.map(r => ({ time: t(r.day), value: on(r.day) ? 1 : 0 })));
    };
    if (indicators.includes("runs")) fill("runs", hexA(p.accent, 0.08), d => ctx.broad.days.has(d));
    if (indicators.includes("zones")) {
      for (const zone of ["hot", "cold"]) {
        fill("zones", hexA(zone === "hot" ? p.orange : p.cold, 0.12), d => zoneOf(ctx.heat.get(d)?.heat) === zone);
      }
    }
    const usdFormat = { type: "custom", formatter: v => kUsd(v) };
    const btc = chart.addSeries(LineSeries, { color: p.text1, lineWidth: 2, priceLineVisible: false, priceFormat: usdFormat }, 0);
    btc.setData(rows.filter(r => r.btc > 0).map(r => ({ time: t(r.day), value: r.btc })));
    if (indicators.includes("band")) {
      for (const k of ["bandLo", "bandHi"]) {
        const b = chart.addSeries(LineSeries, { color: hexA(p.accent, 0.55), lineWidth: 1, lastValueVisible: false, priceLineVisible: false,
          crosshairMarkerVisible: false, priceFormat: usdFormat }, 0);
        b.setData(rows.filter(r => r[k] > 0).map(r => ({ time: t(r.day), value: r[k] })));
      }
    }
    const marks = [];
    if (indicators.includes("runs")) {
      for (const run of ctx.broad.runs) {
        if (run.roll != null) marks.push({ time: t(run.roll), position: "aboveBar", color: p.red, shape: "square", size: 0.7 });
      }
    }
    if (indicators.includes("turns")) {
      for (const x of ctx.turns) {
        marks.push(x.kind === "cooling"
          ? { time: t(x.day), position: "aboveBar", color: p.orange, shape: "arrowDown", size: 1 }
          : { time: t(x.day), position: "belowBar", color: p.cold, shape: "arrowUp", size: 1 });
      }
    }
    if (marks.length) createSeriesMarkers(btc, marks.sort((a, b) => a.time - b.time));

    // One pane per indicator below the price.
    panes.forEach((key, i) => {
      const def = PANES[key];
      const [c1, c2] = tone[def.tone];
      const opts = { lineWidth: 2, priceLineVisible: false, lastValueVisible: true,
        priceFormat: { type: "custom", formatter: v => (key === "median_z" ? v.toFixed(1) : `${Math.round(v)}`) },
        ...(def.range ? { autoscaleInfoProvider: () => ({ priceRange: { minValue: def.range[0], maxValue: def.range[1] } }) } : {}) };
      const s = def.kind === "baseline"
        ? chart.addSeries(BaselineSeries, { ...opts, baseValue: { type: "price", price: def.base },
            topLineColor: c1, topFillColor1: hexA(c1, 0.32), topFillColor2: hexA(c1, 0.04),
            bottomLineColor: c2, bottomFillColor1: hexA(c2, 0.04), bottomFillColor2: hexA(c2, 0.32) }, i + 1)
        : chart.addSeries(LineSeries, { ...opts, color: c1 }, i + 1);
      s.setData(rows.map(r => ({ r, v: def.value(r, ctx) })).filter(o => o.v != null && Number.isFinite(o.v))
        .map(o => ({ time: t(o.r.day), value: o.v })));
      for (const price of def.lines || []) {
        s.createPriceLine({ price, color: hexA(p.text3, 0.55), lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
      }
    });
    const ps = chart.panes();
    ps[0]?.setStretchFactor(MAIN_H() / PANE_H());
    for (let i = 1; i < ps.length; i++) ps[i].setStretchFactor(paneH(panes[i - 1]) / PANE_H());
    // Each pane's own scale: log for the price, linear for the indicators (set per pane, last, so neither leaks).
    chart.priceScale("right", 0).applyOptions({ mode: PriceScaleMode.Logarithmic, scaleMargins: { top: 0.1, bottom: 0.06 } });
    for (let i = 1; i < ps.length; i++) {
      chart.priceScale("right", i).applyOptions({ mode: PriceScaleMode.Normal, scaleMargins: { top: 0.12, bottom: 0.08 } });
    }

    chart.subscribeCrosshairMove(param => setHover(param?.time ? Math.round(param.time / DAY_S) : null));
    try {
      if (kept) chart.timeScale().setVisibleRange(kept);
      else setRange(chart, rows, range);
    } catch {
      setRange(chart, rows, range);
    }
    // Where each pane starts, for its legend.
    const place = () => {
      const top = el.getBoundingClientRect().top;
      setTops(chart.panes().map(pn => (pn.getHTMLElement()?.getBoundingClientRect().top ?? top) - top));
    };
    const raf = requestAnimationFrame(place);
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => requestAnimationFrame(place)) : null;
    ro?.observe(el);
    return () => { cancelAnimationFrame(raf); ro?.disconnect(); };
  }, [rows, ctx, indicators.join(","), mode]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (chartRef.current) setRange(chartRef.current, rows, range); }, [range]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { chartRef.current?.remove(); chartRef.current = null; }, []);

  if (rows.length < 2) return null;
  const byDay = new Map(rows.map(r => [r.day, r]));
  const last = rows[rows.length - 1];
  const r = (hover != null && byDay.get(hover)) || last;
  const heat = ctx.heat.get(r.day);
  const inRun = indicators.includes("runs") ? ctx.broad.days.get(r.day) : null;
  let below = MAIN_H();
  const fallback = panes.map(k => { const top = below; below += paneH(k); return top; });
  return <div className="mc">
    <div ref={box} className="mc-chart" style={{ height }} />
    <div className="mc-legend" style={{ top: tops[0] ?? 0 }}>
      <b>BTC</b><span>{usd(r.btc)}</span>
      {indicators.includes("band") && r.bandLo > 0 && <i>band {kUsd(r.bandLo)}–{kUsd(r.bandHi)}</i>}
      {inRun && <em className="mc-run">{BCOPY.day(inRun.age)}{inRun.rolled ? ` · ${BCOPY.marks.rolled.toLowerCase()}` : ""}</em>}
      {heat && indicators.includes("zones") && zoneOf(heat.heat) && <em className={`mc-zone is-${zoneOf(heat.heat)}`}>{zoneOf(heat.heat) === "hot" ? "hot day" : "cold day"}</em>}
      <i>{dayDate(r.day)}</i>
    </div>
    {panes.map((key, i) => {
      const text = PANES[key].legend(r, ctx);
      return <div key={key} className="mc-legend" style={{ top: tops[i + 1] ?? fallback[i] }}>
        <b>{LABEL[key]}</b><span>{text ?? "—"}</span>
        {key === "heat" && heat && <i className="mc-parts">{["uptrend", "fg", "traders"].filter(k => heat.parts[k] != null)
          .map(k => `${HCOPY.parts[k]} ${Math.round(heat.parts[k])}`).join(" · ")}</i>}
      </div>;
    })}
  </div>;
}

function setRange(chart, rows, key) {
  const def = RANGES.find(x => x.key === key);
  const lastDay = rows[rows.length - 1].day;
  if (!def?.days) chart.timeScale().fitContent();
  else chart.timeScale().setVisibleRange({ from: (lastDay - def.days) * DAY_S, to: lastDay * DAY_S });
}
