// B6. Performance: the period tabs carry their own results; the chart (P&L or equity) from
// Hyperliquid's portfolio history for the whole account; the P&L calendar on the right.
import { useEffect, useMemo, useRef, useState } from "react";
import { createChart, BaselineSeries, LineSeries, ColorType, CrosshairMode, LineStyle, createSeriesMarkers } from "lightweight-charts";
import { useTheme } from "../../ThemeContext.jsx";
import HelpTip from "../HelpTip.jsx";
import { pnlClass } from "./parts.jsx";
import PnlCalendar from "./PnlCalendar.jsx";
import { usd, pct } from "../../utils/portfolio/format.js";
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

const dedupe = pts => { const m = new Map(); for (const p of pts || []) m.set(p.time, p.value); return [...m].sort((a, b) => a[0] - b[0]).map(([time, value]) => ({ time, value })); };

function PerfChart({ data, mode, lastVisit, height }) {
  const box = useRef(null);
  const chartRef = useRef(null);
  const seriesRef = useRef({});
  const tagsRef = useRef({});
  const [vx, setVx] = useState(null);
  const { mode: theme } = useTheme();
  useEffect(() => {
    if (!box.current) return undefined;
    const p = palette(box.current);
    const chart = createChart(box.current, {
      width: box.current.clientWidth, height,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: p.chartText, fontFamily: "'Geist Mono', monospace", fontSize: 11, attributionLogo: false },
      grid: { vertLines: { visible: false }, horzLines: { color: p.grid } },
      crosshair: { mode: CrosshairMode.Magnet, vertLine: { color: p.cross, style: LineStyle.Dashed, labelBackgroundColor: p.text3 }, horzLine: { color: p.cross, style: LineStyle.Dashed, labelBackgroundColor: p.text3 } },
      timeScale: { borderColor: p.border, timeVisible: true, secondsVisible: false, rightOffset: 2 },
      // The last-value label sits inside the scale's top margin, so it never hides the top tick.
      rightPriceScale: { borderColor: p.border, scaleMargins: { top: 0.16, bottom: 0.1 } },
      handleScroll: { mouseWheel: false, pressedMouseMove: true }, handleScale: { mouseWheel: false, pinch: true },
    });
    const fmt = { type: "custom", formatter: v => usd(v), minMove: 0.01 };
    seriesRef.current = {
      pnl: chart.addSeries(BaselineSeries, { baseValue: { type: "price", price: 0 }, topFillColor1: fade(p.profit, 0.18), topFillColor2: fade(p.profit, 0.18),
        bottomFillColor1: fade(p.loss, 0.18), bottomFillColor2: fade(p.loss, 0.18), topLineColor: fade(p.text1, 0.8), bottomLineColor: fade(p.text1, 0.8), lineWidth: 1.5, priceFormat: fmt, priceLineVisible: false }),
      eq: chart.addSeries(LineSeries, { color: p.accent, lineWidth: 1.5, priceFormat: fmt, priceLineVisible: false, visible: false }),
    };
    tagsRef.current = { pnl: createSeriesMarkers(seriesRef.current.pnl, []), eq: createSeriesMarkers(seriesRef.current.eq, []) };
    chartRef.current = chart;
    const ro = new ResizeObserver(() => box.current && chart.applyOptions({ width: box.current.clientWidth }));
    ro.observe(box.current);
    const place = () => setVx(v => ({ ...v, n: (v?.n || 0) + 1 }));
    chart.timeScale().subscribeVisibleTimeRangeChange(place);
    return () => { ro.disconnect(); chart.remove(); chartRef.current = null; tagsRef.current = {}; };
  }, [theme, height]);

  // setData only: zoom survives a refresh.
  const keyRef = useRef("");
  useEffect(() => {
    const s = seriesRef.current, chart = chartRef.current;
    if (!s.pnl || !data) return;
    const series = mode === "equity" ? s.eq : s.pnl;
    s.pnl.applyOptions({ visible: mode !== "equity" });
    s.eq.applyOptions({ visible: mode === "equity" });
    series.setData(data);
    // High and Low as small tags at their points.
    const tags = tagsRef.current;
    tags[mode === "equity" ? "pnl" : "eq"]?.setMarkers([]);
    if (data.length > 1 && box.current) {
      const p = palette(box.current);
      const hi = data.reduce((x, y) => (y.value > x.value ? y : x)), lo = data.reduce((x, y) => (y.value < x.value ? y : x));
      tags[mode === "equity" ? "eq" : "pnl"]?.setMarkers([
        { time: hi.time, position: "aboveBar", shape: "circle", size: 0.5, color: p.text3, text: `${PERF.high} ${usd(hi.value)}` },
        { time: lo.time, position: "belowBar", shape: "circle", size: 0.5, color: p.text3, text: `${PERF.low} ${usd(lo.value)}` },
      ].sort((m, n) => m.time - n.time));
    }
    const key = `${mode}|${data[0]?.time}`;
    if (key !== keyRef.current) { chart.timeScale().fitContent(); keyRef.current = key; }
  }, [data, mode]);

  const x = (() => {
    const chart = chartRef.current;
    if (!chart || !lastVisit || !data?.length || lastVisit < data[0].time) return null;
    const c = chart.timeScale().timeToCoordinate(data.find(d => d.time >= lastVisit)?.time ?? data[data.length - 1].time);
    return c == null ? null : c;
  })();
  return <div className="pf-perf-chart" style={{ height }}>
    <div ref={box} style={{ height }} />
    {x != null && vx !== undefined && <div className="pf-lastvisit" style={{ left: x }}><span>{PERF.lastVisit}</span></div>}
  </div>;
}

export default function Performance({ portfolio, period, onPeriod, mode, onMode, fills, funding, fillsStart, lastVisit, phone }) {
  const tabs = PERF.periods.map(p => {
    const h = portfolio?.[p.src];
    const last = h?.pnlHistory?.length ? h.pnlHistory[h.pnlHistory.length - 1].value : null;
    return { ...p, value: last, dd: h ? maxDrawdown(h) : null };
  });
  const cur = PERF.periods.find(p => p.key === period) || PERF.periods[2];
  const data = useMemo(() => {
    const h = portfolio?.[cur.src];
    return h ? dedupe(mode === "equity" ? h.accountValueHistory : h.pnlHistory) : null;
  }, [portfolio, cur.src, mode]);
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
      <PerfChart data={data} mode={mode} lastVisit={lastVisit} height={phone ? 200 : 240} />
      <PnlCalendar fills={fills} funding={funding} historyStart={fillsStart} lastVisit={lastVisit} phone={phone} />
    </div>
  </section>;
}
