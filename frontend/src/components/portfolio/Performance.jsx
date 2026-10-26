// B6. Performance: the period tabs carry their own results; the chart (P&L or equity) from
// Hyperliquid's portfolio history for the whole account, resampled to one fixed step per period so
// time reads evenly across the axis; the P&L calendar on the right.
import { useEffect, useMemo, useRef, useState } from "react";
import { createChart, BaselineSeries, LineSeries, ColorType, CrosshairMode, LineStyle, createSeriesMarkers } from "lightweight-charts";
import { useTheme } from "../../ThemeContext.jsx";
import HelpTip from "../HelpTip.jsx";
import { pnlClass } from "./parts.jsx";
import PnlCalendar from "./PnlCalendar.jsx";
import { usd, pct } from "../../utils/portfolio/format.js";
import { resample, nearestPoint, extremes, PERIOD_STEP } from "../../utils/portfolio/series.js";
import { palette, fade } from "./chartTheme.js";
import { INFO, PERF } from "./copy.js";

// Max drawdown over a period: the largest fall of P&L from an earlier peak, over the account value at that peak.
export function maxDrawdown(period) {
  const pnl = period?.pnlHistory || [], av = period?.accountValueHistory || [];
  let peak = null, peakAv = null, worst = 0;
  for (let i = 0; i < pnl.length; i++) {
    if (peak == null || pnl[i].value > peak) { peak = pnl[i].value; peakAv = av[i]?.value; }
    if (peakAv > 0) worst = Math.max(worst, (peak - pnl[i].value) / peakAv);
  }
  return worst * 100;
}

const TAG_CLEAR = 40;            // px: a High/Low text this close to the Last visit line or the scale drops (the dot stays)
const VISIT_LABEL_W = 56;        // px: "Last visit" at 11px, with its 5 px offset

function PerfChart({ data, raw, mode, lastVisit, height }) {
  const box = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef({});
  const tagsRef = useRef({});
  const [layout, setLayout] = useState(0);
  const keyRef = useRef("");
  const { mode: theme } = useTheme();
  useEffect(() => {
    if (!box.current) return undefined;
    const p = palette(box.current);
    const chart = createChart(box.current, {
      width: box.current.clientWidth, height,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: p.chartText, fontFamily: "'Geist Mono', monospace", fontSize: 11, attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: p.grid } },
      crosshair: { mode: CrosshairMode.Magnet, vertLine: { color: p.cross, style: LineStyle.Dashed, labelBackgroundColor: p.bg }, horzLine: { color: p.cross, style: LineStyle.Dashed, labelBackgroundColor: p.bg } },
      timeScale: { borderColor: p.border, timeVisible: true, secondsVisible: false, rightOffset: 2 },
      rightPriceScale: { borderColor: p.border, scaleMargins: { top: 0.16, bottom: 0.12 } },
      handleScroll: { mouseWheel: false, pressedMouseMove: true }, handleScale: { mouseWheel: false, pinch: true },
    });
    const fmt = { type: "custom", formatter: v => usd(v), minMove: 0.01 };
    // No last-value box: the active period tab already shows the value.
    seriesRef.current = {
      pnl: chart.addSeries(BaselineSeries, { baseValue: { type: "price", price: 0 }, topFillColor1: fade(p.profit, 0.18), topFillColor2: fade(p.profit, 0.18),
        bottomFillColor1: fade(p.loss, 0.18), bottomFillColor2: fade(p.loss, 0.18), topLineColor: fade(p.text1, 0.8), bottomLineColor: fade(p.text1, 0.8), lineWidth: 1.5,
        priceFormat: fmt, priceLineVisible: false, lastValueVisible: false }),
      eq: chart.addSeries(LineSeries, { color: p.accent, lineWidth: 1.5, priceFormat: fmt, priceLineVisible: false, lastValueVisible: false, visible: false }),
    };
    tagsRef.current = { pnl: createSeriesMarkers(seriesRef.current.pnl, []), eq: createSeriesMarkers(seriesRef.current.eq, []) };
    chartRef.current = chart;
    keyRef.current = "";
    const ro = new ResizeObserver(() => box.current && chart.applyOptions({ width: box.current.clientWidth }));
    ro.observe(box.current);
    const relayout = () => setLayout(n => n + 1);
    chart.timeScale().subscribeVisibleLogicalRangeChange(relayout);
    chart.timeScale().subscribeSizeChange(relayout);
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; tagsRef.current = {}; };
  }, [theme, height]);

  // setData only: zoom survives a refresh (the chart is rebuilt only for a theme or a height).
  useEffect(() => {
    const s = seriesRef.current, chart = chartRef.current;
    if (!s.pnl || !data) return;
    const series = mode === "equity" ? s.eq : s.pnl;
    s.pnl.applyOptions({ visible: mode !== "equity" });
    s.eq.applyOptions({ visible: mode === "equity" });
    series.setData(data);
    const key = `${mode}|${data[0]?.time}|${data.length > 1 ? data[1].time - data[0].time : 0}`;
    if (key !== keyRef.current) { chart.timeScale().fitContent(); keyRef.current = key; }
    setLayout(n => n + 1);
  }, [data, mode, theme, height]);

  // Where things sit on screen, from the chart's own scales.
  const chart = chartRef.current;
  const plotW = chart ? chart.timeScale().width() : 0;
  const visit = lastVisit && data?.length ? nearestPoint(data, lastVisit) : null;
  const vx = chart && visit ? chart.timeScale().timeToCoordinate(visit.time) : null;

  // High and Low: a dot at each; the text drops near the Last visit line or the price scale.
  useEffect(() => {
    const tags = tagsRef.current, chart = chartRef.current;
    if (!chart || !tags.pnl) return;
    tags[mode === "equity" ? "pnl" : "eq"]?.setMarkers([]);
    const e = data?.length > 1 ? extremes(raw, data) : null;
    if (!e || !box.current) { tags[mode === "equity" ? "eq" : "pnl"]?.setMarkers([]); return; }
    const p = palette(box.current);
    const ts = chart.timeScale(), w = ts.width();
    const text = (pt, word) => {
      const x = ts.timeToCoordinate(pt.time);
      if (x == null) return "";
      if (w - x < TAG_CLEAR || x < TAG_CLEAR / 2) return "";
      if (vx != null && Math.abs(x - vx) < TAG_CLEAR) return "";
      return `${word} ${usd(pt.value)}`;
    };
    tags[mode === "equity" ? "eq" : "pnl"]?.setMarkers([
      { time: e.hi.time, position: "aboveBar", shape: "circle", size: 0.5, color: p.text3, text: text(e.hi, PERF.high) },
      { time: e.lo.time, position: "belowBar", shape: "circle", size: 0.5, color: p.text3, text: text(e.lo, PERF.low) },
    ].sort((m, n) => m.time - n.time));
  }, [data, raw, mode, vx, layout]);

  // Last visit: the line on its exact step; the label kept inside the plot, flipped left near the right edge.
  const flip = vx != null && vx + VISIT_LABEL_W > plotW;
  return <div className="pf-perf-chart" style={{ height }}>
    <div ref={box} style={{ height }} />
    {vx != null && vx >= 0 && vx <= plotW && <div className={`pf-lastvisit${flip ? " pf-lv-flip" : ""}`} style={{ left: vx }}><span>{PERF.lastVisit}</span></div>}
  </div>;
}

export default function Performance({ portfolio, period, onPeriod, mode, onMode, fills, funding, fillsStart, lastVisit, phone }) {
  const tabs = PERF.periods.map(p => {
    const h = portfolio?.[p.src];
    const last = h?.pnlHistory?.length ? h.pnlHistory[h.pnlHistory.length - 1].value : null;
    return { ...p, value: last, dd: h ? maxDrawdown(h) : null };
  });
  const cur = PERF.periods.find(p => p.key === period) || PERF.periods[2];
  const raw = useMemo(() => {
    const h = portfolio?.[cur.src];
    return h ? (mode === "equity" ? h.accountValueHistory : h.pnlHistory) : null;
  }, [portfolio, cur.src, mode]);
  const data = useMemo(() => (raw ? resample(raw, PERIOD_STEP[cur.src]) : null), [raw, cur.src]);
  return <section className="pf-perf">
    <div className="pf-perf-head">
      <div className="pf-periods" role="tablist">
        {tabs.map(t => <button key={t.key} type="button" role="tab" className="te-toggle pf-period" aria-pressed={t.key === cur.key}
          title={t.dd != null ? `${PERF.maxDd} ${pct(t.dd, { digits: 1 })}` : undefined} onClick={() => onPeriod(t.key)}>
          <span className="pf-period-l">{t.label}</span> <span className={`m ${pnlClass(t.value)}`}>{t.value != null ? usd(t.value, { sign: true }) : "—"}</span>
        </button>)}
      </div>
      <div className="pf-perf-r">
        <HelpTip width={300} label={PERF.pnl}><p>{INFO.chart}</p></HelpTip>
        <span className="pf-modes">{[["pnl", PERF.pnl], ["equity", PERF.equity]].map(([k, l]) => <button key={k} type="button" className="te-toggle" aria-pressed={mode === k} onClick={() => onMode(k)}>{l}</button>)}</span>
      </div>
    </div>
    <div className="pf-perf-body">
      <PerfChart data={data} raw={raw} mode={mode} lastVisit={lastVisit} height={phone ? 200 : 240} />
      <PnlCalendar fills={fills} funding={funding} historyStart={fillsStart} lastVisit={lastVisit} phone={phone} />
    </div>
  </section>;
}
