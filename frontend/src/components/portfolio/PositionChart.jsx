// The expanded row's chart: Hyperliquid candles from the browser (no Railway call), your levels as
// price lines, your fills as small marks (16 at most, 8 on a phone) and the scanner's 4H/1D changes
// on the top edge. 7D is 1h candles; Trip runs from the open (1h up to 10 days, then
// chartTimeframe, capped at 30 days). Charts update with setData and are never rebuilt on a refresh.
// No boxes on the price scale but each level's own price, dark with the level's colour.
import { useEffect, useMemo, useRef, useState } from "react";
import { createChart, CandlestickSeries, ColorType, CrosshairMode, LineStyle } from "lightweight-charts";
import * as hlClient from "../../services/hlClient.js";
import { useTheme } from "../../ThemeContext.jsx";
import FillMarks from "../FillMarks.js";
import { fillMarks, chartTimeframe } from "../../utils/traderBoard.js";
import { marksInput, thinMarks } from "../../utils/portfolio/fillTrips.js";
import { stamp, size as fmtSize, decimalsAt } from "../../utils/portfolio/format.js";
import { displayName } from "../../utils/portfolio/displayNames.js";
import { palette, fade } from "./chartTheme.js";
import { sigWord, sigColor } from "./ScannerCell.jsx";
import { textWidth } from "./parts.jsx";
import { DETAIL } from "./copy.js";

const H = 3600, D = 86400;
const cache = new Map();
const SIG_PX = 11;

export function chartRange(mode, openAt, nowS) {
  if (mode === "trip" && openAt) {
    const from = Math.max(openAt - 6 * H, nowS - 30 * D);
    const span = nowS - from;
    return { from, interval: span <= 10 * D ? "1h" : chartTimeframe(from, nowS) };
  }
  return { from: nowS - 7 * D, interval: "1h" };
}

async function loadCandles(coin, interval, from, to) {
  const key = `${coin}|${interval}|${Math.floor(from / 3600)}`;
  if (cache.has(key)) return cache.get(key);
  const raw = await hlClient.getCandles(coin, interval, Math.floor(from * 1000), Math.floor(to * 1000));
  const out = (raw || []).map(c => ({ time: Math.floor(c.t / 1000), open: +c.o, high: +c.h, low: +c.l, close: +c.c }));
  cache.set(key, out);
  return out;
}

// The mark's own precision (five significant figures, as Hyperliquid shows it): 79.125, 80,221, 4.4922.
const decimalsFor = mark => decimalsAt(mark);

// The scanner's changes along the top edge: each gets a tick and its word when the word fits; a
// change whose tick would cross a word already placed is left out.
export function placeSignals(list, toX, width = Infinity) {
  const out = [];
  let lastEnd = -1e9;
  for (const e of list) {
    const x = toX(e.time);
    if (x == null || x < 0 || x > width) continue;
    if (x <= lastEnd + 4) continue;                 // inside the previous word: no tick through it
    const w = 6 + textWidth(e.text, SIG_PX, "sans", 600);
    // Near the right edge the word reads leftwards from its tick, inside the plot.
    const flip = x + w > width && x - w > lastEnd + 4;
    out.push({ ...e, x, label: flip || x + w <= width, flip });
    lastEnd = flip ? x : x + w;
  }
  return out;
}

export default function PositionChart({ row, classified, events, openAt, height = 300, phone = false, szDecimals = null }) {
  const box = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef(null);
  const marksRef = useRef(null);
  const [sigs, setSigs] = useState([]);
  const sigsRef = useRef([]);
  const placeRef = useRef(null);
  const linesRef = useRef([]);
  const [gen, setGen] = useState(0);
  const [mode, setMode] = useState(openAt ? "trip" : "7d");
  const [candles, setCandles] = useState(null);
  const [hover, setHover] = useState(null);
  const { mode: theme } = useTheme();
  const nowS = Math.floor(Date.now() / 1000);
  const range = chartRange(mode, openAt, nowS);
  const dec = decimalsFor(row.mark);

  useEffect(() => {
    let alive = true;
    setCandles(null);
    loadCandles(row.coin, range.interval, range.from, nowS).then(c => alive && setCandles(c)).catch(() => alive && setCandles([]));
    return () => { alive = false; };
  }, [row.coin, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  // Build once per coin and theme; a new height only resizes.
  useEffect(() => {
    if (!box.current) return undefined;
    const p = palette(box.current);
    const chart = createChart(box.current, {
      width: box.current.clientWidth, height,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: p.chartText, fontFamily: "'Geist Mono', monospace", fontSize: 11, attributionLogo: false },
      grid: { vertLines: { color: p.grid }, horzLines: { color: p.grid } },
      crosshair: { mode: CrosshairMode.Normal,
        vertLine: { color: p.cross, width: 1, style: LineStyle.Dashed, labelBackgroundColor: p.bg },
        horzLine: { color: p.cross, width: 1, style: LineStyle.Dashed, labelBackgroundColor: p.bg } },
      timeScale: { borderColor: p.border, timeVisible: true, secondsVisible: false, rightOffset: 4 },
      rightPriceScale: { borderColor: p.border, scaleMargins: { top: 0.14, bottom: 0.08 } },
      handleScroll: { mouseWheel: false, pressedMouseMove: true }, handleScale: { mouseWheel: false, pinch: true },
    });
    // No last-value box: the mark is its own price line (Hyperliquid's mark, as on the rail).
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "transparent", downColor: fade(p.text3, 0.85), borderUpColor: fade(p.text2, 0.9), borderDownColor: fade(p.text3, 0.85),
      wickUpColor: fade(p.text2, 0.6), wickDownColor: fade(p.text3, 0.6), priceLineVisible: false, lastValueVisible: false,
    });
    const marks = new FillMarks({ long: p.accent, short: p.accent, ring: p.bg }, { maxR: 4 });
    series.attachPrimitive(marks);
    chartRef.current = chart; seriesRef.current = series; marksRef.current = marks;
    const placeSigs = () => {
      const ts = chart.timeScale();
      setSigs(placeSignals(sigsRef.current, t => ts.timeToCoordinate(t), ts.width()));
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(placeSigs);
    placeRef.current = placeSigs;
    const ro = new ResizeObserver(() => box.current && chart.applyOptions({ width: box.current.clientWidth }));
    ro.observe(box.current);
    chart.subscribeCrosshairMove(param => {
      if (!param?.time || !param.seriesData) { setHover(null); return; }
      const bar = param.seriesData.get(series);
      setHover(bar ? { t: param.time, close: bar.close } : null);
    });
    setGen(g => g + 1);
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; seriesRef.current = null; linesRef.current = []; };
  }, [row.coin, theme]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { chartRef.current?.applyOptions({ height }); }, [height]);

  // Levels as price lines: no titles; each axis label is dark with the price in the line's colour.
  const ctx = row.ctx;
  useEffect(() => {
    const s = seriesRef.current;
    if (!s || !box.current) return;
    const p = palette(box.current);
    for (const l of linesRef.current) { try { s.removePriceLine(l); } catch { /* gone */ } }
    linesRef.current = [];
    const add = (price, color, style, axis = true, text = color) => price && linesRef.current.push(s.createPriceLine({
      price, color, lineStyle: style, lineWidth: 1, axisLabelVisible: axis, title: "", axisLabelColor: p.bg, axisLabelTextColor: text }));
    add(row.liq, p.red, LineStyle.Solid);
    add(row.entry, p.accent, LineStyle.Dashed);
    // The nearest stop and take-profit only: a ladder of orders reads in the list beside the chart.
    for (const st of (row.ordersRead ? row.stops : []).slice(0, 1)) add(st.px, p.accent, LineStyle.Dotted);
    for (const tp of row.tps.slice(0, 1)) add(tp.px, p.accent, LineStyle.Dotted);
    if (ctx?.band) { add(ctx.band.lo, p.bandline, LineStyle.Solid, false); add(ctx.band.hi, p.bandline, LineStyle.Solid, false); }
    if (ctx?.trend) add(ctx.trend, p.text3, LineStyle.Dashed, false);
    add(row.mark, fade(p.text1, 0.45), LineStyle.SparseDotted, true, p.text1);
  }, [row.liq, row.entry, row.mark, row.stops, row.tps, row.ordersRead, ctx, gen, candles]);

  // Candles, fills and signal markers: setData only.
  const times = useMemo(() => (candles || []).map(c => c.time), [candles]);
  useEffect(() => {
    const s = seriesRef.current, chart = chartRef.current;
    if (!s || !candles) return;
    s.setData(candles);
    s.applyOptions({ priceFormat: { type: "price", precision: dec, minMove: 10 ** -dec } });
    marksRef.current?.setMarks(thinMarks(fillMarks(marksInput(classified, row.coin, candles[0]?.time || 0), times), phone ? 8 : 16, { all: true }));
    const at = t => times[Math.max(0, times.findLastIndex(x => x <= t))];
    sigsRef.current = (events?.events || []).filter(e => e.kind === "signal" && candles.length && e.t >= candles[0].time)
      .map(e => ({ time: at(e.t), color: sigColor(e.to), text: `${sigWord(e.to)} ${e.tf === "4h" ? "4H" : "1D"}` }));
    chart?.timeScale().fitContent();
    placeRef.current?.();
  }, [candles, classified, events, times, row.coin, dec, phone, gen]);

  // Your size at the hovered time, from the classified fills.
  const sizeAt = useMemo(() => {
    if (!hover) return null;
    const mine = (classified || []).filter(f => f.coin === row.coin && f.t <= hover.t);
    return mine.length ? mine[mine.length - 1].after : null;
  }, [hover, classified, row.coin]);
  const sigAt = useMemo(() => {
    if (!hover || !events) return null;
    let s = events.at_start?.h4?.signal || null;
    for (const e of events.events || []) if (e.kind === "signal" && e.tf === "4h" && e.t <= hover.t) s = e.to;
    return s;
  }, [hover, events]);

  // "5 Oct 20:00 · 94.23 · 98.51 HYPE · LIGHT LONG"
  const sep = <span className="pf-sep">·</span>;
  const unit = displayName(row.coin).name;
  return <div className="pf-chart">
    <div className="pf-chart-top">
      <span className="pf-chart-modes">
        <button type="button" className="te-toggle" aria-pressed={mode === "7d"} onClick={() => setMode("7d")}>{DETAIL.d7}</button>
        <button type="button" className="te-toggle" aria-pressed={mode === "trip"} disabled={!openAt} onClick={() => setMode("trip")}>{DETAIL.trip}</button>
      </span>
      <span className="pf-chart-legend m">{hover ? <>
        <span>{stamp(hover.t * 1000)}</span>{sep}<span className="pf-t1">{hover.close.toFixed(dec)}</span>
        {sizeAt != null && <>{sep}<span>{fmtSize(Math.abs(sizeAt), szDecimals)} {unit}</span></>}
        {sigAt && <>{sep}<span className="pf-sig" style={{ color: sigColor(sigAt) }}>{sigWord(sigAt)}</span></>}
      </> : <span className="pf-t3">{range.interval.toUpperCase()}</span>}</span>
    </div>
    <div className="pf-chart-wrap">
      <div ref={box} className="pf-chart-box" style={{ height }} />
      <div className="pf-sigs" aria-hidden="true">{sigs.map((g, i) => <span key={i} className={`pf-sigm${g.flip ? " pf-sigm-flip" : ""}`} style={{ left: g.x, color: g.color }}>
        <i style={{ background: g.color }} />{g.label && <b>{g.text}</b>}</span>)}</div>
    </div>
    {candles && !candles.length && <div className="pf-chart-empty">{"—"}</div>}
  </div>;
}
