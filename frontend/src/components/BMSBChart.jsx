import { useTheme } from "../ThemeContext.jsx";
import RangeRuler from "./RangeRuler.js";
import SpikeZone from "./SpikeZone.js";
import { candleChange } from "../utils/chartPresentation.js";
import { signalCandleTime } from "../utils/signalTiming.js";
import HelpTip from "./HelpTip.jsx";
import RegimeIcon from "./RegimeIcon.jsx";
import Tabs from "./Tabs.jsx";
import { useRef, useEffect, useState, useCallback } from "react";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  ColorType,
  LineStyle,
  CrosshairMode,
  createTextWatermark,
  createSeriesMarkers,
} from "lightweight-charts";
import { col, T, REGIME_META, SIGNAL_META, heatColor, resolveToken, getBaseSymbol } from "../theme.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── Signal → marker mapping ──────────────────────────────────────────────────
// Dark-theme hues: pass through col() when drawn so light mode gets readable ones.

const SIGNAL_MARKER = {
  STRONG_LONG:  { color: "#34d399", shape: "arrowUp",   position: "belowBar", text: "STRONG LONG" },
  LIGHT_LONG:   { color: "#6ee7b7", shape: "arrowUp",   position: "belowBar", text: "LIGHT LONG" },
  ACCUMULATE:   { color: "#97FCE4", shape: "arrowUp",   position: "belowBar", text: "ACCUMULATE" },
  REVIVAL_SEED: { color: "#b8fff0", shape: "arrowUp",   position: "belowBar", text: "REVIVAL" },
  TRIM:         { color: "#fbbf24", shape: "arrowDown", position: "aboveBar", text: "TRIM" },
  TRIM_HARD:    { color: "#f87171", shape: "arrowDown", position: "aboveBar", text: "TRIM HARD" },
  RISK_OFF:     { color: "#ef4444", shape: "arrowDown", position: "aboveBar", text: "RISK-OFF" },
  NO_LONG:      { color: "#d8b4fe", shape: "arrowDown", position: "aboveBar", text: "NO LONG" },
};

// ─── CTO ribbon colours (display only) ────────────────────────────────────────
const RIBBON_COLOR = { gold: "#e3b341", blue: "#4f8fe0", grey: "#8b8f94" };
const RIBBON_LINES = [
  { key: "e32", width: 2, alpha: "" },
  { key: "e35", width: 1, alpha: "80" },
  { key: "e50", width: 1, alpha: "80" },
  { key: "e58", width: 2, alpha: "" },
];

const ENTRY_COLOR = { long: "#7dd3fc", short: "#fda4af", exit: "#8b8f94" };

const fmtPx = v => new Intl.NumberFormat("en", { maximumSignificantDigits: 5 }).format(v);
const fmtUsd = v => (v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${Math.round(v / 1e3)}K` : `$${Math.round(v)}`);
const fmtWhen = t => new Date(t * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function TraderEntries({ entries, onShow }) {
  const traders = entries.traders || [];
  const coin = entries.symbol;
  const box = { padding: "10px 18px", fontSize: 12, color: T.text3, borderTop: `1px solid ${T.border}`, lineHeight: 1.6 };
  if (!traders.length) return <div style={box}>No profitable traders hold {coin} right now.</div>;
  const side = k => entries.sides?.[k] || { n: 0 };
  const summary = ["long", "short"].filter(k => side(k).n)
    .map(k => `${side(k).n} ${k}, median entry ${fmtPx(side(k).median_entry)}`).join(" · ");
  return (
    <div style={box}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "4px 16px" }}>
        <span><strong style={{ color: T.text2 }}>Profitable traders in {coin}</strong> · {summary}</span>
        {onShow && <button type="button" onClick={onShow} style={{ background: "transparent", border: 0, borderBottom: `1px solid ${T.accent}`, padding: "2px 0", color: T.accent, fontSize: 12, cursor: "pointer" }}>Show entries</button>}
      </div>
      <ul style={{ margin: "6px 0 0", padding: 0, listStyle: "none", display: "grid", gap: 4 }}>
        {traders.map(tr => (
          <li key={tr.label}>
            <span style={{ fontFamily: T.mono, fontWeight: 700, color: col(ENTRY_COLOR[tr.side]) }}>{tr.label}</span>{" "}
            {tr.side} {fmtUsd(tr.size_usd)} at {fmtPx(tr.entry_px)} average
            {tr.pnl_pct != null && <> · {tr.pnl_pct >= 0 ? "+" : ""}{Math.round(tr.pnl_pct)}% on margin</>}
            {" · "}{tr.opened_at ? `opened ${fmtWhen(tr.opened_at)}` : tr.covered_from ? `opened before ${fmtWhen(tr.covered_from)}` : tr.pending ? "" : "opening not found in their fills"}
            {tr.pending && <span style={{ color: T.text4 }}> · loading fills…</span>}
            {tr.buying_now && <strong style={{ color: T.text2 }}> · still {tr.side === "long" ? "buying" : "selling"} (timed order)</strong>}
            {(tr.bursts || []).length > 0 && (
              <div style={{ color: T.text4 }}>
                {tr.bursts_total > 4 && <span>{tr.bursts_total - 4} earlier bursts; latest: </span>}
                {tr.bursts.slice(-4).map((b, i) => (
                  <span key={i}>{i ? "; " : ""}{b.kind === "close" ? "reduced" : (b.side === "long") ? "bought" : "sold"} {fmtWhen(b.t)}
                    {b.t_end - b.t >= 600 ? ` to ${fmtWhen(b.t_end)}` : ""} at {fmtPx(b.px)} ({fmtUsd(b.usd)}{b.twap ? ", timed order" : ""})</span>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
      <div style={{ marginTop: 6, color: T.text4 }}>
        From Hyperliquid's public fills (each trader's latest 2,000). Updated {fmtWhen(entries.updated_at)}.
      </div>
    </div>
  );
}

const PATTERN_COLOR = { 1: "#34d399", "-1": "#f87171", 0: "#c4b5fd" };

// ─── Timeframe options ────────────────────────────────────────────────────────

const TIMEFRAMES = [
  { key: "4h",  label: "4H",  limit: 600,  apiTf: "4h", barSpace: 8 },   // the server loads 600 bars (~100 days); the 200-day MA needs 1D
  { key: "1d",  label: "1D",  limit: 500,  apiTf: "1d", barSpace: 10 },  // ~500 days — enough for 200 MA + visible range
];

export default function BMSBChart({
  symbol,
  timeframe: initialTimeframe = "1d",
  height = 360,
  signal,
  signalFirstSeenAt,
  signalTimeframe,
  regime,
  heat,
  exhaustionState,
  floorConfirmed,
  momentum,
  timeframeControl = true,   // false when the page owns the timeframe (coin page)
}) {
  const { mode } = useTheme();
  const resetViewRef = useRef(null);
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const pressureLinesRef = useRef([]);
  const [loading, setLoading] = useState(true);
  const [hoverCandle, setHoverCandle] = useState(null);
  const [chartRange, setChartRange] = useState(null);
  const [signalMarkerIndex, setSignalMarkerIndex] = useState(null);
  const [error, setError] = useState(null);
  const [activeTimeframe, setActiveTimeframe] = useState(initialTimeframe === "1d" ? "1d" : "4h");
  useEffect(() => { setActiveTimeframe(initialTimeframe === "1d" ? "1d" : "4h"); }, [initialTimeframe]);
  const [showPressure, setShowPressure] = useState(false);
  const [pressureData, setPressureData] = useState(null);
  const [pressureLoading, setPressureLoading] = useState(false);
  const [ribbon, setRibbon] = useState(null);
  const [patterns, setPatterns] = useState([]);
  const [showPatterns, setShowPatterns] = useState(false);
  const [showMean, setShowMean] = useState(false);
  const [spike, setSpike] = useState(null);
  const [showEntries, setShowEntries] = useState(true);
  const [entries, setEntries] = useState(null);
  const [candleTimes, setCandleTimes] = useState(null);
  const meanSeriesRef = useRef([]);
  const zoneEndRef = useRef(null);
  const patternSeriesRef = useRef([]);
  const entryMarkersRef = useRef(null);
  const entryLinesRef = useRef([]);

  const buildChart = useCallback((tf) => {
    if (!containerRef.current || !symbol) return;

    // Clean up previous chart
    if (chartRef.current) {
      try { chartRef.current.remove(); } catch (_) { /* ignore */ }
      chartRef.current = null;
    }

    let cancelled = false;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: resolveToken("chartText"),
        fontFamily: "'SF Mono', 'Fira Code', monospace",
        fontSize: 12,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: resolveToken("chartGrid") },
        horzLines: { color: resolveToken("chartGrid") },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "rgba(151,252,228,0.15)",
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: resolveToken("chartLabel"),
        },
        horzLine: {
          color: "rgba(151,252,228,0.15)",
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: resolveToken("chartLabel"),
        },
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.06)",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 10,   // room for the range label right of the last candle
        barSpacing: (TIMEFRAMES.find(t => t.key === tf) || {}).barSpace || 8,
        minBarSpacing: 3,
      },
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.06)",
        scaleMargins: { top: 0.10, bottom: 0.16 },
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    });
    chartRef.current = chart;

    // Watermark (must be attached to a pane, not the chart)
    const baseSymbol = getBaseSymbol(symbol);
    try {
      const pane = chart.panes()[0];
      if (pane) {
        createTextWatermark(pane, {
          lines: [
            {
              text: baseSymbol,
              color: "rgba(255,255,255,0.04)",
              fontSize: 48,
              fontFamily: T.font,
              fontStyle: "bold",
            },
          ],
        });
      }
    } catch (_) {
      // Watermark is cosmetic — don't crash if it fails
    }

    // ── Volume histogram (rendered first → behind candles) ──
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
      drawTicks: false,
      borderVisible: false,
    });

    // ── Candlestick series ──
    candleSeriesRef.current = null;
    pressureLinesRef.current = [];
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#528e80",
      downColor: "#a36e65",
      borderUpColor: "#97FCE4",
      borderDownColor: "#d8a094",
      wickUpColor: "rgba(151,252,228,0.65)",
      wickDownColor: "rgba(216,160,148,0.65)",
    });

    // ── CTO ribbon (rendered behind BMSB; display only) ──
    const ribbonSeries = RIBBON_LINES.map(l => chart.addSeries(LineSeries, {
      color: col(RIBBON_COLOR.grey),
      lineWidth: l.width,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    }));

    // ── 200-day MA ──
    const ma200Series = chart.addSeries(LineSeries, {
      color: "rgba(255,168,0,0.6)",
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: false,
      lastValueVisible: true,
      priceLineVisible: false,
      title: "200 MA",
    });

    // ── BMSB lines ──
    // EMA (upper band boundary)
    const bmsbEmaSeries = chart.addSeries(LineSeries, {
      color: "rgba(151,252,228,0.25)",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // SMA (lower band boundary)
    const bmsbSmaSeries = chart.addSeries(LineSeries, {
      color: "rgba(151,252,228,0.25)",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // Mid (main BMSB line — solid, prominent)
    const bmsbMidSeries = chart.addSeries(LineSeries, {
      color: col("#97FCE4"),
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      lastValueVisible: true,
      priceLineVisible: false,
      title: "BMSB",
    });

    // The engine's mean as prices: where z would be 0 and 1 (after-the-spike study).
    const meanSeries = [["z0", "Mean (z 0)", LineStyle.Dashed], ["z1", "z 1", LineStyle.Dotted]].map(([key, title, style]) =>
      [key, chart.addSeries(LineSeries, { color: col("#91b9e8"), lineWidth: 1, lineStyle: style, title,
        lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, visible: false })]);
    meanSeriesRef.current = meanSeries;

    // ── Fetch data ──
    const tfConfig = TIMEFRAMES.find(t => t.key === tf) || TIMEFRAMES[2];
    const apiTf = tfConfig.apiTf || tf;
    const encoded = encodeURIComponent(symbol);
    setLoading(true);
    setHoverCandle(null);
    setChartRange(null);
    setSignalMarkerIndex(null);
    setRibbon(null);
    setPatterns([]);
    setSpike(null);
    setCandleTimes(null);
    entryMarkersRef.current = null;
    entryLinesRef.current = [];
    zoneEndRef.current = null;
    patternSeriesRef.current = [];
    setError(null);

    fetch(`${API_BASE}/api/chart/${encoded}?timeframe=${apiTf}&limit=${tfConfig.limit}`)
      .then(async r => {
        const data = await r.json();
        if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Chart unavailable (${r.status})`);
        return data;
      })
      .then(data => {
        if (cancelled) return;

        if (data.candles?.length > 0) {
          // Auto-detect price precision for micro-cap coins (e.g. MOG at 0.0000001)
          const samplePrice = data.candles[data.candles.length - 1]?.close || 0;
          if (samplePrice > 0 && samplePrice < 1) {
            const decimals = Math.max(2, Math.ceil(-Math.log10(samplePrice)) + 3);
            const minMove = Math.pow(10, -decimals);
            const pf = { type: "price", precision: decimals, minMove };
            candleSeries.applyOptions({ priceFormat: pf });
            ribbonSeries.forEach(ls => { try { ls.applyOptions({ priceFormat: pf }); } catch(_){} });
            try { bmsbMidSeries.applyOptions({ priceFormat: pf }); } catch(_){}
            try { bmsbEmaSeries.applyOptions({ priceFormat: pf }); } catch(_){}
            try { bmsbSmaSeries.applyOptions({ priceFormat: pf }); } catch(_){}
          }

          candleSeries.setData(data.candles);
          setCandleTimes(data.candles.map(c => c.time));
          candleSeriesRef.current = candleSeries;

          // ── Volume data ──
          if (data.volume?.length > 0) {
            volumeSeries.setData(data.volume);
          }

          const volumes = new Map((data.volume || []).map(v => [v.time, v.value]));
          const latestCandle = data.candles.at(-1);
          const readCandle = candle => setHoverCandle(candle ? {
            ...candle, change:candleChange(candle), volume:volumes.get(candle.time),
            volumeUnit:data.volume_unit || baseSymbol,
            live: candle.time <= Date.now()/1000 && candle.time + (apiTf === '1d' ? 86400 : 14400) > Date.now()/1000,
          } : null);
          readCandle(latestCandle);
          chart.subscribeCrosshairMove(param => {
            if (cancelled) return;
            const candle = param.seriesData?.get(candleSeries);
            readCandle(candle?.open != null ? candle : latestCandle);
          });
          for (const [key, ser] of meanSeries) ser.setData(data.mean_lines?.[key] || []);
          if (data.spike) {
            setSpike(data.spike);
            const anchorIndex = data.spike.anchor_time != null ? data.candles.findIndex(c => c.time === data.spike.anchor_time) : -1;
            if (anchorIndex >= 0 && data.spike.zone) {
              // Room to the right so the part of the zone still ahead is visible (see reset view).
              zoneEndRef.current = anchorIndex + data.spike.zone.to_bar;
              chart.timeScale().applyOptions({ rightOffset: Math.max(10, Math.min(60, zoneEndRef.current - (data.candles.length - 1) + 3)) });
              candleSeries.attachPrimitive(new SpikeZone({ anchorIndex, anchorClose: data.spike.anchor_close, zone: data.spike.zone,
                colors: { fill: "rgba(207,145,133,0.08)", line: col("#cf9185"), text: col("#cf9185") } }));
            }
          }
          if (data.expected_range && data.expected_range.timeframe === apiTf) {
            const forecast = data.expected_range;
            setChartRange(forecast);
            candleSeries.attachPrimitive(new RangeRuler({reference:forecast.reference_price,
              percentage:forecast.expected_range_pct, lastIndex:data.candles.length-1,
              horizon:apiTf === '1d' ? '24h' : '4h'}));
          }

          // Anchor the signal to its recorded first-seen candle, never the live bar.
          const markerDef = signal && SIGNAL_MARKER[signal];
          if (markerDef) {
            const last = data.candles[data.candles.length - 1];
            const markerTime = (!signalTimeframe || signalTimeframe === apiTf)
              ? signalCandleTime(data.candles, signalFirstSeenAt, apiTf === "4h" ? 14400 : 86400)
              : null;
            // -1: looked up but outside the loaded candles. Null: no marker for this signal (e.g. WAIT).
            setSignalMarkerIndex(markerTime == null ? -1 : data.candles.findIndex(c => c.time === markerTime));
            const markers = markerTime == null ? [] : [{
              time: markerTime,
              position: markerDef.position,
              color: col(markerDef.color),
              shape: markerDef.shape,
              text: markerDef.text,
            }];

            if (floorConfirmed) {
              markers.push({
                time: last.time,
                position: "belowBar",
                color: col("#34d399"),
                shape: "circle",
                text: "FLOOR · current",
              });
            }
            if (exhaustionState === "CLIMAX") {
              markers.push({
                time: last.time,
                position: "aboveBar",
                color: col("#fbbf24"),
                shape: "circle",
                text: "CLIMAX · current",
              });
            }

            markers.sort((a, b) => a.time - b.time);
            createSeriesMarkers(candleSeries, markers);
          }

          // ── Current price line ──
          const lastCandle = data.candles[data.candles.length - 1];
          const priceUp = lastCandle.close >= lastCandle.open;
          candleSeries.createPriceLine({
            price: lastCandle.close,
            color: priceUp ? "rgba(151,252,228,0.65)" : "rgba(216,160,148,0.65)",
            lineWidth: 1,
            lineStyle: LineStyle.Dotted,
            // The series' own last-value label already marks the price on the axis.
            axisLabelVisible: false,
            title: "",
          });
        }

        // ── 200-day MA (computed from candle closes) ──
        if (data.candles?.length > 0) {
          // Always 200-day MA: 200 bars for 1D, 1200 bars for 4H (6 bars/day)
          const period = tf === "4h" ? 1200 : 200;
          const closes = data.candles.map(c => c.close);
          const maData = [];
          let sum = 0;
          for (let i = 0; i < closes.length; i++) {
            sum += closes[i];
            if (i >= period) sum -= closes[i - period];
            if (i >= period - 1) {
              maData.push({ time: data.candles[i].time, value: sum / period });
            }
          }
          if (maData.length > 0) ma200Series.setData(maData);
        }

        // ── CTO ribbon: each bar coloured by its state ──
        const lr = data.cto_ribbon;
        if (lr?.time?.length > 0) {
          RIBBON_LINES.forEach((l, k) => {
            ribbonSeries[k].setData(lr.time.map((t, i) => ({
              time: t, value: lr[l.key][i], color: `${col(RIBBON_COLOR[lr.state[i]])}${l.alpha}`,
            })));
          });
        }
        setRibbon(lr?.current ? lr : null);
        setPatterns(Array.isArray(data.patterns) ? data.patterns : []);

        // ── BMSB overlay data ──
        if (data.bmsb_mid?.length > 0) bmsbMidSeries.setData(data.bmsb_mid);
        if (data.bmsb_ema?.length > 0) bmsbEmaSeries.setData(data.bmsb_ema);
        if (data.bmsb_sma?.length > 0) bmsbSmaSeries.setData(data.bmsb_sma);

        // Denser desktop history with a readable minimum candle width on small screens.
        const candleCount = data.candles?.length || 0;
        resetViewRef.current = () => {
          candleSeries.priceScale().applyOptions({ autoScale: true });
          const plotWidth = Math.max(160, (containerRef.current?.clientWidth || 900) - 80);
          const preferredBars = tf === "1d" ? 150 : 180;
          const visibleBars = Math.min(preferredBars, Math.max(40, Math.floor(plotWidth / 4)));
          // Keep ~110px empty right of the last candle for the range ruler's label,
          // whatever the width: p empty bars take p / (visibleBars + p) of the plot.
          const pad = Math.max(6, Math.ceil(110 * visibleBars / Math.max(60, plotWidth - 110)));
          // After a spike, extend the view to the end of the "where past spikes bottomed" zone.
          const zoneEnd = zoneEndRef.current != null ? zoneEndRef.current + 3 : 0;
          const to = Math.max(candleCount + pad, zoneEnd);
          chart.timeScale().setVisibleLogicalRange({
            from: Math.max(-1, to - pad - visibleBars),
            to,
          });
        };
        resetViewRef.current();
        setLoading(false);
      })
      .catch(err => {
        if (cancelled) return;
        setError(err.message);
        setLoading(false);
      });

    // Resize handler
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      cancelled = true;
      resetViewRef.current = null;
      ro.disconnect();
      try { chart.remove(); } catch (_) { /* ignore */ }
      chartRef.current = null;
    };
  }, [symbol, height, signal, signalFirstSeenAt, signalTimeframe, regime, exhaustionState, floorConfirmed, mode]);

  // Build chart on mount and when dependencies change
  useEffect(() => {
    for (const [, ser] of meanSeriesRef.current) { try { ser.applyOptions({ visible: showMean }); } catch (_) {} }
  }, [showMean, activeTimeframe]);
  // A fresh spike turns the mean lines on: they show where the unwind is heading.
  useEffect(() => { if (spike && !spike.running && !spike.superseded) setShowMean(true); }, [spike]);

  useEffect(() => {
    const cleanup = buildChart(activeTimeframe);
    return cleanup;
  }, [activeTimeframe, buildChart]);

  // Patterns overlay (1D, off by default): necklines and anchor points, display only
  useEffect(() => {
    const chart = chartRef.current;
    patternSeriesRef.current.forEach(ps => { try { chart?.removeSeries(ps); } catch (_) {} });
    patternSeriesRef.current = [];
    if (!showPatterns || !chart || patterns.length === 0) return;
    const add = (opts, data) => {
      const ser = chart.addSeries(LineSeries, {
        lineWidth: 1, crosshairMarkerVisible: false, lastValueVisible: false, priceLineVisible: false, ...opts,
      });
      ser.setData(data);
      patternSeriesRef.current.push(ser);
      return ser;
    };
    // Patterns sharing a neckline within a few days get one combined label
    const labelled = [];
    patterns.forEach(p => {
      const g = labelled.find(q => Math.abs(q.level / p.levels[0] - 1) < 0.005 && Math.abs(q.end - p.end) <= 5 * 86400 && q.status === p.status);
      if (g) g.names.push(p.name); else labelled.push({ p, level: p.levels[0], end: p.end, status: p.status, names: [p.name] });
    });
    patterns.forEach(p => {
      const label = labelled.find(q => q.p === p);
      const color = col(PATTERN_COLOR[p.status === "failed" ? 0 : p.direction] || PATTERN_COLOR[0]);
      const pts = [];
      p.anchors.forEach(a => { if (!pts.length || a.time > pts[pts.length - 1].time) pts.push(a); });
      if (pts.length > 1) add({ color: `${color}99`, lineStyle: LineStyle.Dotted }, pts);
      p.levels.forEach((lvl, k) => {
        if (!(p.end > p.start)) return;
        const ser = add({ color, lineStyle: p.status === "forming" ? LineStyle.Dashed : LineStyle.Solid },
          [{ time: p.start, value: lvl }, { time: p.end, value: lvl }]);
        if (k === 0 && label) {
          createSeriesMarkers(ser, [{
            time: p.end, position: p.direction < 0 ? "belowBar" : "aboveBar", color, shape: "square",
            text: `${label.names.join(" + ")} · ${p.status}`,
          }]);
        }
      });
    });
  }, [showPatterns, patterns, mode]);

  // Profitable traders holding this coin: when and where they got in (Hyperliquid fills)
  useEffect(() => {
    setEntries(null);
    if (!showEntries || !symbol) return;
    let cancelled = false, timer = null, tries = 0;
    // Fills for large holders load in the background; ask again while some are pending.
    const load = () => fetch(`${API_BASE}/api/hyperlens/entries/${encodeURIComponent(getBaseSymbol(symbol))}`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (cancelled) return;
        setEntries(d);
        if (d?.pending && ++tries < 12) timer = setTimeout(load, 10000);
      })
      .catch(() => {});
    load();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [showEntries, symbol]);

  useEffect(() => {
    const series = candleSeriesRef.current;
    entryLinesRef.current.forEach(pl => { try { series?.removePriceLine(pl); } catch (_) {} });
    entryLinesRef.current = [];
    try { entryMarkersRef.current?.setMarkers([]); } catch (_) {}
    if (!showEntries || !series || !entries?.traders?.length || !candleTimes?.length) return;
    // The candle a fill belongs to: the last candle opening at or before it.
    const barOf = t => {
      if (t < candleTimes[0]) return null;
      let lo = 0, hi = candleTimes.length - 1;
      while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (candleTimes[mid] <= t) lo = mid; else hi = mid - 1; }
      return candleTimes[lo];
    };
    const markers = [];
    for (const tr of entries.traders) {
      for (const b of tr.bursts || []) {
        const time = barOf(b.t);
        if (time == null) continue;
        const buy = (b.kind === "open") === (b.side === "long");
        markers.push({
          time, price: b.px, position: buy ? "atPriceBottom" : "atPriceTop", shape: buy ? "arrowUp" : "arrowDown",
          color: col(b.kind === "close" ? ENTRY_COLOR.exit : ENTRY_COLOR[b.side]),
          text: b.kind === "close" ? `${tr.label} exit` : tr.label,
        });
      }
    }
    markers.sort((a, b) => a.time - b.time);
    if (entryMarkersRef.current) entryMarkersRef.current.setMarkers(markers);
    else entryMarkersRef.current = createSeriesMarkers(series, markers);
    for (const side of ["long", "short"]) {
      const sd = entries.sides?.[side];
      if (!sd?.n || !sd.median_entry) continue;
      entryLinesRef.current.push(series.createPriceLine({
        price: sd.median_entry, color: col(ENTRY_COLOR[side]), lineWidth: 1, lineStyle: LineStyle.Dashed,
        axisLabelVisible: true, title: `${sd.n} ${side} · median entry`,
      }));
    }
  }, [showEntries, entries, candleTimes, mode]);

  // Zoom from a little before the earliest burst on the chart to the latest candle.
  const firstBurst = Math.min(...(entries?.traders || []).flatMap(tr => (tr.bursts || []).map(b => b.t)));
  const showEntriesRange = Number.isFinite(firstBurst) && candleTimes?.length ? () => {
    let i = candleTimes.findIndex(t => t > firstBurst) - 1;
    if (i < 0) i = firstBurst >= candleTimes[0] ? candleTimes.length - 1 : 0;
    const last = candleTimes.length - 1;
    chartRef.current?.timeScale().setVisibleLogicalRange({ from: Math.max(0, Math.min(i, last - 20) - 12), to: last + 4 });
  } : null;

  // Pressure levels overlay — fetch + render price lines
  useEffect(() => {
    const series = candleSeriesRef.current;
    // Remove existing pressure lines
    pressureLinesRef.current.forEach(pl => {
      try { series?.removePriceLine(pl); } catch (_) {}
    });
    pressureLinesRef.current = [];

    if (!showPressure || !series) return;

    const coin = getBaseSymbol(symbol);
    let cancelled = false;

    const fetchAndRender = async () => {
      setPressureLoading(true);
      try {
        const resp = await fetch(`${API_BASE}/api/hyperlens/pressure?symbol=${coin}`);
        if (!resp.ok || cancelled) return;
        const data = await resp.json();
        if (cancelled) return;
        setPressureData(data);

        // Build levels from pressure data
        const levels = [];
        const fmtSize = (v) => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : v >= 1e3 ? `${(v/1e3).toFixed(0)}K` : `${v.toFixed(0)}`;

        // Cluster nearby prices within X% of each other into one level
        const clusterLevels = (items, pctThreshold = 0.5) => {
          if (!items || items.length === 0) return [];
          const sorted = [...items].sort((a, b) => a.price - b.price);
          const clusters = [];
          let cluster = { prices: [sorted[0].price], totalSize: sorted[0].total_size_usd || sorted[0].size_usd || 0, count: 1, items: [sorted[0]] };

          for (let i = 1; i < sorted.length; i++) {
            const item = sorted[i];
            const avgPrice = cluster.prices.reduce((s, p) => s + p, 0) / cluster.prices.length;
            const pctDiff = Math.abs(item.price - avgPrice) / avgPrice * 100;

            if (pctDiff <= pctThreshold) {
              // Merge into current cluster
              cluster.prices.push(item.price);
              cluster.totalSize += item.total_size_usd || item.size_usd || 0;
              cluster.count++;
              cluster.items.push(item);
            } else {
              // Close current cluster, start new one
              clusters.push(cluster);
              cluster = { prices: [item.price], totalSize: item.total_size_usd || item.size_usd || 0, count: 1, items: [item] };
            }
          }
          clusters.push(cluster);

          return clusters.map(c => ({
            price: c.prices.reduce((s, p) => s + p, 0) / c.prices.length,  // weighted avg
            totalSize: c.totalSize,
            count: c.count,
            items: c.items,
          }));
        };

        // Cluster limits by BUY/SELL
        const allLimits = data.smart_money_orders?.limits || [];
        const buyLimits = allLimits.filter(o => (o.side || "").toUpperCase() === "BUY");
        const sellLimits = allLimits.filter(o => (o.side || "").toUpperCase() !== "BUY");

        clusterLevels(buyLimits, 0.8).forEach(c => {
          levels.push({
            price: c.price, color: "#60a5fa", style: LineStyle.Dashed,
            width: c.totalSize > 100000 ? 2 : 1,
            title: `BUY ${c.count > 1 ? `${c.count}x ` : ""}$${fmtSize(c.totalSize)}`,
          });
        });
        clusterLevels(sellLimits, 0.8).forEach(c => {
          levels.push({
            price: c.price, color: "#c084fc", style: LineStyle.Dashed,
            width: c.totalSize > 100000 ? 2 : 1,
            title: `SELL ${c.count > 1 ? `${c.count}x ` : ""}$${fmtSize(c.totalSize)}`,
          });
        });

        // Stops — cluster nearby
        clusterLevels(data.smart_money_orders?.stops || [], 0.5).forEach(c => {
          levels.push({
            price: c.price, color: "#f87171", style: LineStyle.Solid, width: 2,
            title: `STOP ${c.count > 1 ? `${c.count}x ` : ""}$${fmtSize(c.totalSize)}`,
          });
        });

        // Take Profits — cluster nearby
        clusterLevels(data.smart_money_orders?.take_profits || [], 0.5).forEach(c => {
          levels.push({
            price: c.price, color: "#34d399", style: LineStyle.Solid, width: 2,
            title: `TP ${c.count > 1 ? `${c.count}x ` : ""}$${fmtSize(c.totalSize)}`,
          });
        });

        // Book walls — cluster bid and ask separately
        clusterLevels(data.order_book_walls?.bid_walls || [], 0.3).forEach(c => {
          levels.push({
            price: c.price, color: "#34d39950", style: LineStyle.Dotted,
            width: c.totalSize > 10e6 ? 2 : 1,
            title: `BID ${c.count > 1 ? `${c.count}x ` : ""}$${fmtSize(c.totalSize)}`,
          });
        });
        clusterLevels(data.order_book_walls?.ask_walls || [], 0.3).forEach(c => {
          levels.push({
            price: c.price, color: "#f8717150", style: LineStyle.Dotted,
            width: c.totalSize > 10e6 ? 2 : 1,
            title: `ASK ${c.count > 1 ? `${c.count}x ` : ""}$${fmtSize(c.totalSize)}`,
          });
        });

        // Liquidation clusters — already pre-clustered by backend
        (data.liquidation_clusters || []).forEach(c => {
          levels.push({
            price: c.avg_price, color: "#fbbf24", style: LineStyle.Dashed, width: 1,
            title: `LIQ ${c.dominant_side} $${fmtSize(c.total_size_usd)}`,
          });
        });

        // Render price lines on the candle series
        const s = candleSeriesRef.current;
        if (!s || cancelled) return;
        levels.forEach(level => {
          try {
            const pl = s.createPriceLine({
              price: level.price,
              color: level.color,
              lineWidth: level.width,
              lineStyle: level.style,
              title: level.title,
              axisLabelVisible: true,
            });
            pressureLinesRef.current.push(pl);
          } catch (_) {}
        });
      } catch (err) {
        if (!cancelled) console.warn("Pressure fetch failed:", err);
      } finally {
        if (!cancelled) setPressureLoading(false);
      }
    };

    fetchAndRender();
    return () => { cancelled = true; };
  }, [showPressure, symbol, activeTimeframe]);

  // ── Info strip data ──
  const rm = regime ? REGIME_META[regime] || REGIME_META.FLAT : null;
  const sm = signal ? SIGNAL_META[signal] || SIGNAL_META.WAIT : null;
  const hColor = heatColor(heat);
  const momColor = momentum != null ? (momentum >= 0 ? T.green : T.red) : null;
  // Failed patterns stay listed but are not counted as something current.
  const activePatterns = patterns.filter(p => p.status === "forming" || p.status === "confirmed").length;

  return (
    <div className="price-chart-panel" style={{
      width: "100%",
      overflow: "hidden",
      marginBottom: 14,
      position: "relative",
    }}>
      {/* ── Top bar: info strip + timeframe toggle ── */}
      <div className="chart-toolbar" style={{
        position: "relative", zIndex: 5,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "14px 18px",
        background: "linear-gradient(180deg, rgba(9,22,25,0.92) 0%, rgba(9,22,25,0.5) 70%, transparent 100%)",
      }}>
        {/* Left: info pills */}
        <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
          {/* Regime pill */}
          {rm && (
            <span className="terminal-status" style={{
              padding: "2px 7px", borderRadius: 0,
              background: rm.bg, color: rm.color,
              fontSize: T.textXs, fontFamily: T.mono, fontWeight: 700,
              letterSpacing: "0.04em",
              border: `1px solid ${rm.color}20`,
              display: "inline-flex", alignItems: "center", gap: 3,
            }}>
              <RegimeIcon regime={regime} size={10} />
              {rm.name}
            </span>
          )}

          {/* Signal pill */}
          {sm && signal !== "WAIT" && (
            <span className="terminal-status" style={{
              padding: "2px 7px", borderRadius: 0,
              background: `${sm.color}12`, color: sm.color,
              fontSize: T.textXs, fontFamily: T.mono, fontWeight: 700,
              letterSpacing: "0.04em",
              border: `1px solid ${sm.color}18`,
              display: "inline-flex", alignItems: "center", gap: 3,
            }}>
              {sm.label}
            </span>
          )}

          {/* CTO ribbon state (display only): flat text, explained in a tip touch users can open */}
          {ribbon && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
              <span style={{ fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.04em", color: col(RIBBON_COLOR[ribbon.current]) }}>
                CTO {ribbon.current.toUpperCase()}
              </span>
              <HelpTip title="CTO ribbon" width={300}>
                <p>Four moving averages coloured by trend state on closed candles: gold is an uptrend, blue a downtrend, grey no clear trend.{ribbon.current === "grey" && ribbon.last_actionable ? ` The last trend was ${ribbon.last_actionable}.` : ""}</p>
                <p>Display only; not used by signals.</p>
              </HelpTip>
            </span>
          )}

          {/* Heat */}
          {heat != null && (
            <span style={{ fontFamily: T.mono, fontWeight: 700, color: hColor }}>
              Heat {Math.round(heat)}
            </span>
          )}

          {/* Momentum */}
          {momentum != null && (
            <span style={{ fontFamily: T.mono, fontWeight: 600, color: momColor }}>
              Momentum {momentum >= 0 ? "+" : ""}{momentum.toFixed(1)}%
            </span>
          )}
        </div>

        {/* Right: pressure toggle + timeframe toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <button type="button" className="chart-reset" disabled={loading || !!error} onClick={() => resetViewRef.current?.()} title="Return to the default candle density and latest price">Reset view</button>
          {/* Pressure levels toggle */}
          <button
            onClick={() => setShowPressure(p => !p)}
            aria-pressed={showPressure}
            title="Toggle tracked liquidation levels, stops, take-profits and limit orders"
            style={{
              padding: "3px 2px", border: 0, borderBottom: "2px solid transparent", borderRadius: 0,
              cursor: "pointer", fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.04em",
              background: "transparent", color: T.text4,
              display: "flex", alignItems: "center", gap: 3,
            }}
          >
            {pressureLoading ? "Loading…" : <><span className="chart-levels-label">Wallet levels</span><span className="chart-levels-label-short">Levels</span></>}
          </button>

          <HelpTip title="Wallet levels"><p>Shows available liquidation clusters and the stop, take-profit and limit-order levels of tracked wallets in this market. These levels can highlight potential pressure areas; orders and positions can change or be cancelled.</p></HelpTip>

          <button
            onClick={() => setShowMean(m => !m)}
            aria-pressed={showMean}
            title="Show the price where the engine's z-score would be 0 (its mean) and 1"
            style={{
              padding: "3px 2px", border: 0, borderBottom: `2px solid ${showMean ? T.accent : "transparent"}`, borderRadius: 0,
              cursor: "pointer", fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.04em",
              background: "transparent", color: showMean ? T.text1 : T.text4,
            }}
          >
            Mean lines
          </button>
          <HelpTip title="Mean lines"><p>The dashed line is the price at which this coin's z-score would be 0, the engine's mean. The dotted line is z = 1. They move with the coin. After a spike, prices have usually unwound toward the mean: z was back under 1 within about 18 days in 91% of past daily spikes. It is a reference, not a target.</p></HelpTip>

          <button
            onClick={() => setShowEntries(v => !v)}
            aria-pressed={showEntries}
            title="Show when and where the profitable traders holding this coin bought or sold"
            style={{
              padding: "3px 2px", border: 0, borderBottom: `2px solid ${showEntries ? T.accent : "transparent"}`, borderRadius: 0,
              cursor: "pointer", fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.04em",
              background: "transparent", color: showEntries ? T.text1 : T.text4,
            }}
          >
            <span className="chart-levels-label">Trader entries</span><span className="chart-levels-label-short">Entries</span>
          </button>
          <HelpTip title="Trader entries"><p>Profitable traders (see HyperLens) who hold this coin now, labelled A, B, C by position size. Each arrow is a burst of their fills on Hyperliquid, placed at its average price: up for buying, down for selling, grey for exits. The dashed line is the median entry price per side. Fills come from Hyperliquid's public record and refresh every 10 minutes. Who holds a coin, and where they got in, is information, not a signal.</p></HelpTip>

          {activeTimeframe === "1d" && (
            <button
              onClick={() => setShowPatterns(p => !p)}
              aria-pressed={showPatterns}
              title="Toggle detected chart patterns with their measured track record. Display only; never used by signals."
              style={{
                padding: "3px 2px", border: 0, borderBottom: "2px solid transparent", borderRadius: 0,
                cursor: "pointer", fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.04em",
                background: "transparent", color: T.text4,
              }}
            >
              Patterns{activePatterns ? ` (${activePatterns})` : ""}
            </button>
          )}

          {/* Timeframe toggle, only where the chart owns its timeframe */}
          {timeframeControl && (
            <Tabs small label="Chart timeframe" items={TIMEFRAMES.map(tf => ({ key: tf.key, label: tf.label }))}
              value={activeTimeframe} onChange={setActiveTimeframe} />
          )}
        </div>
      </div>

      {/* ── Loading overlay ── */}
      {loading && (
        <div style={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "rgba(9,22,25,0.8)", zIndex: 10,
        }}>
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
          }}>
            <div style={{
              width: 20, height: 20,
              border: "2px solid rgba(151,252,228,0.15)",
              borderTopColor: "#97FCE4",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
            }} />
            <span style={{
              color: T.text4,
              fontFamily: T.mono, fontSize: T.textXs,
              letterSpacing: "0.1em",
            }}>
              LOADING
            </span>
          </div>
        </div>
      )}

      {/* ── Error overlay ── */}
      {error && !loading && (
        <div style={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "rgba(9,22,25,0.9)", zIndex: 10,
        }}>
          <span style={{
            color: "rgba(239,68,68,0.7)", fontFamily: T.font, fontSize: 13, padding: "24px 32px", maxWidth: 560, textAlign: "center", lineHeight: 1.6,
            letterSpacing: "0.01em",
          }}>
            Chart unavailable ({error})
          </span>
        </div>
      )}

      <div className="candle-inspector" aria-label="Candle details" style={{padding:'8px 18px',minHeight:44,borderBottom:`1px solid ${T.border}`,fontFamily:T.mono,fontSize:T.textXs,color:T.text3,display:'flex',flexDirection:'column',gap:7}}>
        {hoverCandle ? <>
          <div style={{display:'flex',gap:12,flexWrap:'wrap',alignItems:'center'}}>
            <span>{new Date(hoverCandle.time*1000).toLocaleString('en-GB',{timeZone:'UTC',day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'})} UTC · {activeTimeframe.toUpperCase()}</span>
            <strong style={{color:hoverCandle.change == null ? T.text3 : hoverCandle.change >= 0 ? col('#97FCE4') : col('#d8a094')}}>Candle {hoverCandle.change == null ? '—' : `${hoverCandle.change>=0?'+':''}${hoverCandle.change.toFixed(2)}%`}</strong>
            <span>Volume {Number.isFinite(hoverCandle.volume) ? new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:2}).format(hoverCandle.volume) : '—'} {hoverCandle.volumeUnit}</span>
            {hoverCandle.live && <span style={{color:col('#91b9e8')}}>Live candle</span>}
          </div>
          <div style={{display:'flex',gap:12,flexWrap:'wrap'}}>{['open','high','low','close'].map(key=><span key={key}>{key[0].toUpperCase()} <span style={{color:T.text2}}>{new Intl.NumberFormat('en',{maximumSignificantDigits:7}).format(hoverCandle[key])}</span></span>)}</div>
        </> : <span>Move over a candle to inspect its change and volume.</span>}
      </div>

      {/* ── Chart container ── */}
      <div className="price-chart-canvas" ref={containerRef} style={{ width: "100%", height }} />
      {!loading && !error && <div style={{padding:'10px 18px',fontSize:T.textXs,color:T.text3,borderTop:`1px solid ${T.border}`,lineHeight:1.6}}>
        {chartRange ? <><strong style={{color:col('#91b9e8')}}>Estimated true range {chartRange.expected_range_pct.toFixed(2)}% · next {activeTimeframe === '1d' ? '24h' : '4h'} candle</strong>
          {chartRange.probability != null && <span style={{marginLeft:8}}>{Math.round(chartRange.probability*100)}% chance of an unusually wide candle (usual: 25%)</span>} <HelpTip title="Range ruler" width={360}>
          <p>The ruler's full height represents the estimated true-range magnitude ({chartRange.atr_mult} × ATR14). It is centred on the reference price for illustration; its ends are not forecast highs or lows.</p>
          <p>Chance of a top-quartile range: {Math.round(chartRange.probability*100)}%, compared with a 25% baseline. This is not directional confidence or a price containment interval.</p>
          <p>Reference: {chartRange.reference_price}. Calculated {new Date(chartRange.as_of*1000).toISOString()} from the last closed candle, the same input as the coin page's range card.</p>
        </HelpTip><span style={{marginLeft:8}}>Magnitude only</span></> : 'Range estimate unavailable for these chart data.'}
      </div>}
      {!loading && !error && spike && <div style={{padding:'10px 18px',fontSize:12,color:T.text3,borderTop:`1px solid ${T.border}`,lineHeight:1.6}}>
        {spike.superseded
          ? <><strong style={{color:T.text2}}>Spike superseded</strong> · price has since closed above the spike's peak ({new Intl.NumberFormat('en',{maximumSignificantDigits:6}).format(spike.peak)}), so the trend resumed and the after-the-spike zone no longer applies.</>
          : spike.running
          ? <><strong style={{color:col('#cf9185')}}>Spike in progress</strong> · z is still above 2 (peak so far {new Intl.NumberFormat('en',{maximumSignificantDigits:6}).format(spike.peak)}). The zone appears once it ends.</>
          : spike.zone ? <><strong style={{color:col('#cf9185')}}>After the spike</strong> · {spike.zone.n} past spikes on this timeframe: half bottomed {Math.round(-100*(1 - spike.zone.top/spike.anchor_close))}% to {Math.round(-100*(1 - spike.zone.bottom/spike.anchor_close))}% below the close where the spike ended, {spike.zone.from_bar} to {spike.zone.to_bar} {activeTimeframe === '1d' ? 'days' : 'bars'} later (median {Math.round(-100*(1 - spike.zone.median_price/spike.anchor_close))}% at {spike.zone.median_bar}). {Math.round(100*spike.zone.never_fell_5pct)}% never fell 5%. Not a forecast.
            <HelpTip title="After the spike" width={380}>
              <p>A spike is the last time this coin's z-score reached 2.5; it ends when z drops back under 2. The box and the dashed path start from that bar's close, which is known at the time; the true peak is only known later.</p>
              <p>The box covers the middle half of past lows (depth and timing), measured on the study period only (to 29 March 2026). One in four past spikes fell deeper than the box, and one in four fell less.</p>
              <p>The engine blocks nothing because of this picture. See Mean lines for where the engine's own mean sits today.</p>
            </HelpTip></>
          : <>Spike detected; no history for this timeframe yet.</>}
      </div>}
      {!loading && !error && showEntries && entries && <TraderEntries entries={entries} onShow={showEntriesRange} />}
      {!loading && !error && signal && <div style={{display:"flex",alignItems:"center",justifyContent:"flex-start",flexWrap:"wrap",gap:"8px 20px",padding:"12px 18px",borderTop:`1px solid ${T.border}`,color:T.text3,fontSize:12,lineHeight:1.6}}>
        <span>{signalTimeframe && signalTimeframe !== activeTimeframe ? `The current signal belongs to ${signalTimeframe.toUpperCase()}; switch back to see its origin.` : signalFirstSeenAt ? `First recorded ${new Date(signalFirstSeenAt * 1000).toLocaleString()}${signalMarkerIndex === -1 ? " · outside the loaded candle history" : ""}` : "Signal origin time unavailable; no historical marker is inferred."}</span>
        {signalMarkerIndex != null && signalMarkerIndex >= 0 && <button type="button" onClick={() => chartRef.current?.timeScale().setVisibleLogicalRange({from:Math.max(0,signalMarkerIndex-20),to:signalMarkerIndex+20})} style={{background:"transparent",border:0,borderBottom:`1px solid ${T.accent}`,padding:"4px 0",color:T.accent,fontSize:12,cursor:"pointer"}}>Show signal origin</button>}
      </div>}

      {!loading && !error && showPatterns && activeTimeframe === "1d" && (
        <div style={{padding:"12px 18px",borderTop:`1px solid ${T.border}`,color:T.text3,fontSize:12,lineHeight:1.6}}>
          {patterns.length === 0 ? <p style={{margin:0}}>No patterns forming, confirmed or failed in the last 180 days.</p> : (
            <ul style={{margin:0,padding:0,listStyle:"none",display:"grid",gap:6}}>
              {patterns.map((p, i) => (
                <li key={i}>
                  <span style={{color: col(PATTERN_COLOR[p.status === "failed" ? 0 : p.direction] || PATTERN_COLOR[0]), fontFamily:T.mono, fontWeight:700}}>
                    {p.name} · {p.status} · {new Date(p.end * 1000).toLocaleDateString()}
                  </span>{" "}
                  {p.track_record}
                </li>
              ))}
            </ul>
          )}
          <p style={{margin:"8px 0 0"}}>Measured on 40 coins, Oct 2021 to Mar 2026. Recognition works; no pattern showed an edge over a plain breakout. Display only; patterns never trigger or block a signal.</p>
        </div>
      )}

      {/* ── CSS for spinner ── */}
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
