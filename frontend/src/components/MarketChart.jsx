import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { AreaSeries, BaselineSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, LineStyle, LineType, PriceScaleMode,
         createChart, createSeriesMarkers } from "lightweight-charts";
import { useTheme } from "../ThemeContext.jsx";
import { T as TH, col, resolveToken } from "../theme.js";
import { apiFetch } from "../edge.js";
import { BCOPY, COLD, COUNTING_CHANGES, CROWD, GREED, HCOPY, HOT, INDICATORS, MCOPY, broadRuns, heatSeries, heatTurns,
         zoneOf } from "../utils/marketHeat.js";
import { RANGES, dayDate, kUsd, usd } from "../utils/marketHistory.js";
import { deriveRows } from "../utils/deriveWallets.js";

// The market history page's Chart view: one large BTC chart in the manner of a trading terminal. Indicators sit on the
// price (the weekly band, broad uptrends shaded, hot and cold days) or in panes of their own under it, with the marks
// on the pane they describe (the Uptrend share's turns and the typical coin's on Uptrend share, heat turns on Market heat) (Uptrend share, taller, Fear & Greed, the wallet groups, Market
// heat...), all on one time axis;
// drag and scroll to move and zoom, the range buttons to jump. Each pane names its indicator and its value at the
// crosshair (the latest day otherwise). Context, not a signal.

const DAY_S = 86_400;
const MAIN_H = () => (typeof window !== "undefined" && window.innerWidth < 640 ? 300 : Math.max(360, Math.min(560, Math.round(window.innerHeight * 0.5))));
// The price as a slim strip, for tabs where BTC is the time reference rather than the subject (owner, 6 November 2026:
// the Positioning tab read as too many panes under a big BTC chart).
const SLIM_H = () => (typeof window !== "undefined" && window.innerWidth < 640 ? 120 : 170);
const PHONE = () => typeof window !== "undefined" && window.innerWidth < 640;
const PANE_H = () => (PHONE() ? 92 : 118);
// The Uptrend share's and Market heat's panes (they carry marks) taller, and the panes that draw two readings.
const TALL = { uptrend: 1.5, heat: 1.25, traders: 1.9, groups: 1.3 };
// A pane's room above and below its 0-100 range, as shares of its height: more where marks sit off the line.
const PLAIN = { top: 0.12, bottom: 0.08 };
const MARKED = { top: 0.2, bottom: 0.14 };
const GAP_PX = 7;                  // a mark's near edge, this far off its line
// On a phone the smart money and whales legend takes two lines: that pane is taller there, its lines kept below it.
const paneH = key => Math.round(PANE_H() * (key === "groups" && PHONE() ? 1.7 : TALL[key] || 1));
const GROUPS_MARGINS = () => (PHONE() ? { top: 0.34, bottom: 0.06 } : { top: 0.16, bottom: 0.08 });
// Panes that draw two readings on one pane, so a tab can show all of them in fewer panes (owner, 6 November 2026):
// the profitable traders' long share over their positions (as a price over its volume), and smart money and whales on
// their one net-long scale (whales the thin line).
export const COMBOS = {
  traders: { label: "Profitable traders", parts: ["crowd", "positions"] },
  groups: { label: "Smart money · Whales", parts: ["smart", "whales"] },
};
// In the traders pane the share keeps the top part and the positions the bottom part, with the positions' own legend
// between them (as a share of the pane's height).
const SHARE_IN_TRADERS = { top: 0.13, bottom: 0.45 };
const BARS_IN_TRADERS = { top: 0.7, bottom: 0 };
const BARS_LEGEND_AT = 0.555;
const FEAR_GATE = 40;
const num = v => Math.round(v).toLocaleString("en-US");
// A day's profitable-trader positions (recorded days only; rebuilt days carry the share alone), and the traders
// behind them where recorded.
const posOf = r => { const w = r.wallet?.crowd; return w?.long == null || w?.short == null ? null : w; };              // Fear & Greed at or below: the engine's fear gate (the dial's own line)

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
  positions: { value: r => { const w = posOf(r); return w ? w.long + w.short : null; },
    long: r => posOf(r)?.long ?? null,
    legend: r => { const w = posOf(r); return w ? `${num(w.long + w.short)} · ${num(w.long)} long · ${num(w.short)} short${w.traders != null ? ` · ${num(w.traders)} traders` : ""}` : null; },
    kind: "stack", tone: "longshort" },
  crowd: { value: r => (r.wallet?.crowd?.L == null ? null : 100 * r.wallet.crowd.L),
    legend: r => { const w = r.wallet?.crowd; return w?.L == null ? null : `${Math.round(100 * w.L)}% long · ${Math.round(100 * w.S)}% short`; },
    kind: "baseline", base: 50, range: [0, 100], lines: [100 * CROWD], tone: "longshort" },
  fg: { value: r => r.fg, legend: r => (r.fg == null ? null : `${r.fg}`), kind: "line", range: [0, 100], lines: [GREED, FEAR_GATE], tone: "orange" },
  // The share of the market history's coins at band stretch 1.6 or more (each against its own usual distance).
  stretched: { value: r => (r.stretch?.share == null ? null : 100 * r.stretch.share),
    legend: r => { const s = r.stretch; return s?.share == null ? null : `${Math.round(100 * s.share)}% · ${s.above} of ${s.coins} coins · median ${s.median >= 0 ? "+" : ""}${s.median.toFixed(2)}`; },
    kind: "line", range: [0, 100], tone: "orange" },
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
const LABEL = { ...Object.fromEntries(INDICATORS.map(i => [i.key, i.label])),
  ...Object.fromEntries(Object.entries(COMBOS).map(([k, c]) => [k, c.label])) };
// The positions' line inside the traders pane, where the label above already names the traders.
const positionsLine = r => { const w = posOf(r); return w ? `${num(w.long + w.short)} positions · ${num(w.long)} long · ${num(w.short)} short${w.traders != null ? ` · ${num(w.traders)} traders` : ""}` : null; };

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

export default function MarketChart({ rows, indicators, range, slim = false }) {
  const { mode } = useTheme();
  const box = useRef(null);
  const chartRef = useRef(null);
  const [hover, setHover] = useState(null);
  const [tip, setTip] = useState(null);           // the mark under the pointer: { x, y, kind, day, from }
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
  const panes = indicators.filter(k => PANES[k] || COMBOS[k]);
  const mainH = slim ? SLIM_H() : MAIN_H();
  const height = mainH + panes.reduce((a, k) => a + paneH(k), 0);

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
      const z = chart.addSeries(AreaSeries, { priceScaleId: id, lineType: LineType.WithSteps, lineVisible: false, lineColor: "rgba(0,0,0,0)", topColor: color,
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
    // Each mark carries an id; the chart names it when the pointer is on it, and `meta` says what it means. The marks sit
    // on the pane they describe (owner, 6 November 2026): the Uptrend share's turns and the typical coin's on the Uptrend
    // share, heat turns on Market heat; on the BTC price they read as if they were about BTC.
    const shareMarks = [], heatMarks = [];
    const meta = new Map();
    const pctFrom = f => (f ? { v: 100 * f.v, day: f.day } : null);    // shares (0-1) read as percent
    const shareOn = new Map(rows.map(r => [r.day, r.uptrend == null ? null : 100 * r.uptrend]));
    // Each mark sits GAP_PX clear of its line (owner, 6 November 2026: a blue arrow on the blue heat line was hard to
    // see): above the line's highest value within NEAR days of it, or below its lowest, so a steep move next to the mark
    // does not run through it. The gap is set in pixels: the pane's height and its fixed 0-100 range give the value one
    // pixel is worth. Near the pane's edge the mark comes closer to the line rather than off the pane.
    const NEAR = 5;
    const marked = { uptrend: indicators.includes("shareturns") || indicators.includes("zturns"), heat: indicators.includes("turns") };
    const margins = key => (key === "traders" ? SHARE_IN_TRADERS : key === "groups" ? GROUPS_MARGINS() : marked[key] ? MARKED : PLAIN);
    const valueOn = { uptrend: d => shareOn.get(d), heat: d => ctx.heat.get(d)?.heat };
    const offLine = (key, day, m) => {
      const vs = [];
      for (let d = day - NEAR; d <= day + NEAR; d++) { const v = valueOn[key](d); if (v != null && Number.isFinite(v)) vs.push(v); }
      if (!vs.length) return m;
      const mg = margins(key);
      const h = paneH(key) * 0.95;                          // less its share of the time axis
      const per = 100 / (h * (1 - mg.top - mg.bottom));     // value per pixel
      const far = (12 * (m.size ?? 1) + (m.text ? 14 : 0) + 2) * per;   // from the mark's near edge to its far one
      if (m.position === "aboveBar") {
        const y = Math.max(...vs);
        return { ...m, position: "atPriceTop", price: Math.max(y, Math.min(y + GAP_PX * per, 100 + mg.top * h * per - far)) };
      }
      const y = Math.min(...vs);
      return { ...m, position: "atPriceBottom", price: Math.min(y, Math.max(y - GAP_PX * per, -mg.bottom * h * per + far)) };
    };
    const mark = (list, kind, day, from, at, m) => {
      const id = `${kind}-${day}`;
      meta.set(id, { kind, day, from, at });
      list.push({ id, time: t(day), ...offLine(list === heatMarks ? "heat" : "uptrend", day, m) });
    };
    if (indicators.includes("shareturns")) {
      for (const run of ctx.broad.runs) {
        if (run.roll != null) mark(shareMarks, "rolled", run.roll, pctFrom(run.rollFrom), shareOn.get(run.roll), { position: "aboveBar", color: p.red, shape: "square", size: 0.7 });
      }
      for (const dn of ctx.broad.downs) {
        if (dn.turnUp != null) mark(shareMarks, "turned", dn.turnUp, pctFrom(dn.turnFrom), shareOn.get(dn.turnUp), { position: "belowBar", color: p.green, shape: "square", size: 0.7 });
      }
    }
    if (indicators.includes("zturns")) {
      for (const run of ctx.broad.runs) {
        if (run.zTurn != null) mark(shareMarks, "zdown", run.zTurn, null, null, { position: "aboveBar", color: p.text3, shape: "circle", size: 0.6, text: "z" });
      }
      for (const dn of ctx.broad.downs) {
        if (dn.zTurnUp != null) mark(shareMarks, "zup", dn.zTurnUp, null, null, { position: "belowBar", color: p.text3, shape: "circle", size: 0.6, text: "z" });
      }
    }
    if (indicators.includes("turns")) {
      for (const x of ctx.turns) {
        const from = { v: x.from.heat, day: x.from.day };
        const at = ctx.heat.get(x.day)?.heat;
        if (x.kind === "cooling") mark(heatMarks, "cooling", x.day, from, at, { position: "aboveBar", color: p.orange, shape: "arrowDown", size: 1 });
        else mark(heatMarks, "lifting", x.day, from, at, { position: "belowBar", color: p.cold, shape: "arrowUp", size: 1 });
      }
    }
    const paneSeries = {};

    // One indicator's series on a pane; `extra` overrides its options (another scale, a thinner line).
    const draw = (key, pane, extra = {}) => {
      const def = PANES[key];
      const [c1, c2] = tone[def.tone];
      if (def.kind === "stack") {
        // Positions as bars: all of them in the short colour, the long ones over them from zero, so each bar reads
        // long (bottom) and short (top).
        const fmt = { type: "custom", formatter: v => (v < 0 ? "" : num(v)) };
        const all = chart.addSeries(HistogramSeries, { color: hexA(c2, 0.7), priceLineVisible: false, lastValueVisible: true, priceFormat: fmt, ...extra }, pane);
        const long = chart.addSeries(HistogramSeries, { color: hexA(c1, 0.8), priceLineVisible: false, lastValueVisible: false, priceFormat: fmt, ...extra }, pane);
        const pts = rows.filter(r => def.value(r, ctx) != null);
        all.setData(pts.map(r => ({ time: t(r.day), value: def.value(r, ctx) })));
        long.setData(pts.map(r => ({ time: t(r.day), value: def.long(r) })));
        return all;
      }
      const opts = { lineWidth: 2, priceLineVisible: false, lastValueVisible: true,
        // A 0-100 pane names no value outside its range (the room left for marks above 100 and below 0).
        priceFormat: { type: "custom", formatter: v => (key === "median_z" ? v.toFixed(1)
          : def.range && (v > def.range[1] + 0.5 || v < def.range[0] - 0.5) ? "" : `${Math.round(v)}`) },
        ...(def.range ? { autoscaleInfoProvider: () => ({ priceRange: { minValue: def.range[0], maxValue: def.range[1] } }) } : {}) };
      const s = def.kind === "baseline"
        ? chart.addSeries(BaselineSeries, { ...opts, baseValue: { type: "price", price: def.base },
            topLineColor: c1, topFillColor1: hexA(c1, 0.32), topFillColor2: hexA(c1, 0.04),
            bottomLineColor: c2, bottomFillColor1: hexA(c2, 0.04), bottomFillColor2: hexA(c2, 0.32), ...extra }, pane)
        : chart.addSeries(LineSeries, { ...opts, color: c1, ...extra }, pane);
      s.setData(rows.map(r => ({ r, v: def.value(r, ctx) })).filter(o => o.v != null && Number.isFinite(o.v))
        .map(o => ({ time: t(o.r.day), value: o.v })));
      for (const price of def.lines || []) {
        s.createPriceLine({ price, color: hexA(p.text3, 0.55), lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: false });
      }
      return s;
    };
    // One pane per indicator below the price; a combined pane draws both its readings.
    const clear = "rgba(0,0,0,0)";
    panes.forEach((key, i) => {
      if (key === "traders") {
        paneSeries.crowd = draw("crowd", i + 1);
        paneSeries.positions = draw("positions", i + 1, { priceScaleId: "positions", lastValueVisible: false });
        paneSeries.positions.priceScale().applyOptions({ scaleMargins: BARS_IN_TRADERS });
      } else if (key === "groups") {
        paneSeries.smart = draw("smart", i + 1);
        paneSeries.whales = draw("whales", i + 1, { lineWidth: 1,
          topFillColor1: clear, topFillColor2: clear, bottomFillColor1: clear, bottomFillColor2: clear });
      } else paneSeries[key] = draw(key, i + 1);
    });
    const byTime = (a, b) => a.time - b.time;
    if (shareMarks.length && paneSeries.uptrend) createSeriesMarkers(paneSeries.uptrend, shareMarks.sort(byTime));
    if (heatMarks.length && paneSeries.heat) createSeriesMarkers(paneSeries.heat, heatMarks.sort(byTime));
    if (paneSeries.positions) {
      const shown = new Set(rows.filter(r => PANES.positions.value(r, ctx) != null).map(r => r.day));
      const steps = COUNTING_CHANGES.filter(c => shown.has(c.day)).map(c => {
        const id = `${c.kind}-${c.day}`;
        meta.set(id, { kind: c.kind, day: c.day, from: null, at: null });
        return { id, time: t(c.day), position: "aboveBar", color: p.text3, shape: "circle", size: 0.6 };
      });
      if (steps.length) createSeriesMarkers(paneSeries.positions, steps);
    }
    const ps = chart.panes();
    ps[0]?.setStretchFactor(mainH / PANE_H());
    for (let i = 1; i < ps.length; i++) ps[i].setStretchFactor(paneH(panes[i - 1]) / PANE_H());
    // Each pane's own scale: log for the price, linear for the indicators (set per pane, last, so neither leaks).
    chart.priceScale("right", 0).applyOptions({ mode: PriceScaleMode.Logarithmic, scaleMargins: slim ? { top: 0.24, bottom: 0.08 } : { top: 0.1, bottom: 0.06 } });
    for (let i = 1; i < ps.length; i++) {
      chart.priceScale("right", i).applyOptions({ mode: PriceScaleMode.Normal, scaleMargins: margins(panes[i - 1]) });
    }

    chart.subscribeCrosshairMove(param => {
      setHover(param?.time ? Math.round(param.time / DAY_S) : null);
      const m = param?.point && meta.get(param.hoveredObjectId);
      if (!m) { setTip(null); return; }
      // The point is measured from the top of the pane it is in: add that pane's top, so the explanation opens at the
      // pointer (owner, 6 November 2026: on a small screen it opened up on the BTC pane, out of sight). In the lower part
      // of the window it opens above the pointer, clear of the phone's tab bar.
      const box = el.getBoundingClientRect();
      const pane = chart.panes()[param.paneIndex ?? 0]?.getHTMLElement();
      const y = param.point.y + (pane ? pane.getBoundingClientRect().top - box.top : 0);
      setTip({ x: param.point.x, y, up: box.top + y > window.innerHeight * 0.55, ...m });
    });
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
  }, [rows, ctx, indicators.join(","), mode, slim]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (chartRef.current) setRange(chartRef.current, rows, range); }, [range]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { chartRef.current?.remove(); chartRef.current = null; }, []);

  if (rows.length < 2) return null;
  const byDay = new Map(rows.map(r => [r.day, r]));
  const last = rows[rows.length - 1];
  const r = (hover != null && byDay.get(hover)) || last;
  const heat = ctx.heat.get(r.day);
  const inRun = indicators.includes("runs") ? ctx.broad.days.get(r.day) : null;
  const inDown = indicators.includes("runs") ? ctx.broad.downDays.get(r.day) : null;
  let below = mainH;
  const fallback = panes.map(k => { const top = below; below += paneH(k); return top; });
  return <div className="mc">
    <div ref={box} className="mc-chart" style={{ height }} />
    {tip && <MarkTip tip={tip} width={box.current?.clientWidth || 0} />}
    <div className="mc-legend" style={{ top: tops[0] ?? 0 }}>
      <b>BTC</b><span>{usd(r.btc)}</span>
      {indicators.includes("band") && r.bandLo > 0 && <i>band {kUsd(r.bandLo)}–{kUsd(r.bandHi)}</i>}
      {inRun && <em className="mc-run">{BCOPY.day(inRun.age + 1)}{inRun.rolled ? ` · ${BCOPY.marks.rolled.toLowerCase()}` : ""}</em>}
      {inDown && <em className="mc-down">{BCOPY.downDay(inDown.age + 1)}{inDown.turned ? ` · ${BCOPY.downMarks.turned.toLowerCase()}` : ""}</em>}
      {heat && indicators.includes("zones") && zoneOf(heat.heat) && <em className={`mc-zone is-${zoneOf(heat.heat)}`}>{zoneOf(heat.heat) === "hot" ? "hot day" : "cold day"}</em>}
      <i>{dayDate(r.day)}</i>
    </div>
    {panes.map((key, i) => {
      // Not hovering: the pane's latest reading (a wallet group's feed can end a day before the market history).
      const at = legend => (hover != null ? r : [...rows].reverse().find(x => legend(x, ctx) != null) || r);
      const say = legend => legend(at(legend), ctx);
      const style = { top: tops[i + 1] ?? fallback[i] };
      if (key === "groups") {
        return <div key={key} className="mc-legend" style={style}>
          {COMBOS.groups.parts.map(k => <span key={k} className="mc-part">
            <b><LineKey thin={k === "whales"} />{LABEL[k]}</b><span>{say(PANES[k].legend) ?? "—"}</span></span>)}
        </div>;
      }
      if (key === "traders") {
        const pos = say(positionsLine);
        return <Fragment key={key}>
          <div className="mc-legend" style={style}><b>{LABEL[key]}</b><span>{say(PANES.crowd.legend) ?? "—"}</span></div>
          {pos && <div className="mc-legend mc-sub" style={{ top: style.top + Math.round(BARS_LEGEND_AT * paneH(key)) }}><i>{pos}</i></div>}
        </Fragment>;
      }
      const text = say(PANES[key].legend);
      return <div key={key} className="mc-legend" style={style}>
        <b>{LABEL[key]}</b><span>{text ?? "—"}</span>
        {key === "heat" && heat && <i className="mc-parts">{["uptrend", "fg", "traders"].filter(k => heat.parts[k] != null)
          .map(k => `${HCOPY.parts[k]} ${Math.round(heat.parts[k])}`).join(" · ")}</i>}
      </div>;
    })}
  </div>;
}

// A line's weight in a legend, as the pane draws it: thick, or thin.
function LineKey({ thin }) {
  return <svg className="mc-key" width="14" height="6" viewBox="0 0 14 6" aria-hidden="true">
    <line x1="0" y1="3" x2="14" y2="3" stroke="currentColor" strokeWidth={thin ? 1 : 2.5} /></svg>;
}

// The glass box naming the mark under the pointer, beside it (to its left near the right edge).
function MarkTip({ tip, width }) {
  const c = MCOPY[tip.kind];
  const from = tip.from ? { v: tip.from.v, d: dayDate(tip.from.day) } : null;
  const left = tip.x + 270 > width ? Math.max(4, tip.x - 270) : tip.x + 14;
  return <div className="mc-tip" role="tooltip" style={tip.up ? { left, top: tip.y - 14, transform: "translateY(-100%)" } : { left, top: tip.y + 14 }}>
    <b>{c.title}</b><i>{dayDate(tip.day)}</i>
    <p>{c.body(from, tip.at)}</p>
  </div>;
}

function setRange(chart, rows, key) {
  const def = RANGES.find(x => x.key === key);
  const lastDay = rows[rows.length - 1].day;
  if (!def?.days) chart.timeScale().fitContent();
  else chart.timeScale().setVisibleRange({ from: (lastDay - def.days) * DAY_S, to: lastDay * DAY_S });
}
