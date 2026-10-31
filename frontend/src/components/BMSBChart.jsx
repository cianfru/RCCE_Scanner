import { useTheme } from "../ThemeContext.jsx";
import SpikeZone from "./SpikeZone.js";
import FillMarks from "./FillMarks.js";
import { fillMarks, fmtPrice, fmtStamp, KIND_WORD } from "../utils/traderBoard.js";
import { fmtUsd as fmtUsdShort } from "../utils/traderFormat.js";
import TraderEntries from "./TraderEntries.jsx";
import WalletOpens from "./WalletOpens.jsx";
import useCoinTraders from "../hooks/useCoinTraders.js";
import { candleChange, trendNote } from "../utils/chartPresentation.js";
import { signalCandleTime } from "../utils/signalTiming.js";
import HelpTip from "./HelpTip.jsx";
import RegimeIcon from "./RegimeIcon.jsx";
import Tabs from "./Tabs.jsx";
import { useRef, useEffect, useState, useCallback, useMemo } from "react";
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
import { col, T, alpha, REGIME_META, SIGNAL_META, resolveToken, getBaseSymbol } from "../theme.js";
import { sideColor } from "../utils/traderFormat.js";
import { markerTags } from "../utils/walletName.js";
import { walletColor } from "../utils/walletAvatar.js";
import { candleBars, rebuildCandles, points, latest, recorded, count } from "../utils/coinPositioning.js";
import { COIN_GROUPS, groupDefinitions } from "../utils/traderGroups.js";
import useRosterCounts from "../hooks/useRosterCounts.js";
import useViewport from "../hooks/useViewport.js";

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

// Trader sides (long sky, short pink, exits grey) come from sideColor(), shared with the tables.

const PATTERN_COLOR = { 1: "#34d399", "-1": "#f87171", 0: "#c4b5fd" };

// ─── Timeframe options ────────────────────────────────────────────────────────

// Fill marks: the side colours, ringed in the chart's background so overlapping marks stay apart.
const fillColors = () => ({ long: sideColor("long"), short: sideColor("short"), ring: resolveToken("bg") || "#0b1417", edge: "rgba(0,0,0,0.25)" });

// "#97fce4" at alpha a, for canvas colours (the chart cannot read CSS variables or color-mix).
function withAlpha(color, a) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(color).trim());
  if (!m) return color;
  const n = parseInt(m[1], 16);
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

const ENTRIES_KEY = "rcce-chart-entries";
const REBUILD_DOT_MIN = 25;     // wallets joining plus leaving the profitable-trader list in one candle

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
  exhaustionState,
  floorConfirmed,
  timeframeControl = true,   // false when the page owns the timeframe (coin page)
  traders = null,            // {entries, opens} when the page loads and shows the traders itself
  traderApi = null,          // ref the chart fills with {showEntries} for the page's traders card
  showSetup = true,          // false where the page header already shows the regime and signal (coin page)
  myEntry = null,            // {price, side}: the shared address's open trade, drawn as a dashed "Your entry" line
  toolbarAction = null,      // an extra control at the start of the toolbar's right cluster
  // Compact mode (trader profile): candles and volume only, a slim toolbar, one trader's fills.
  compact = false,
  fills = null,              // classified fills (/api/traders/{address}/fills), drawn as marks at their price
  focusRange = null,         // {from, to} in seconds: the view to open on (and Reset view returns to)
  entryLabel = "Your entry", // the myEntry line's label
  // Long/short bars of groups of wallets under the candles (coin page): the pane is drawn when
  // positioningPane is true; positioning is the /api/coin-positioning body (null while loading).
  positioningPane = false,
  positioning = null,
}) {
  const { mode } = useTheme();
  const resetViewRef = useRef(null);
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const pressureLinesRef = useRef([]);
  const [loading, setLoading] = useState(true);
  const [hoverCandle, setHoverCandle] = useState(null);
  const [error, setError] = useState(null);
  const [activeTimeframe, setActiveTimeframe] = useState(initialTimeframe === "1d" ? "1d" : "4h");
  useEffect(() => { setActiveTimeframe(initialTimeframe === "1d" ? "1d" : "4h"); }, [initialTimeframe]);
  const [showPressure, setShowPressure] = useState(false);
  const [pressureData, setPressureData] = useState(null);
  const [pressureLoading, setPressureLoading] = useState(false);
  const [ribbon, setRibbon] = useState(null);
  const [patterns, setPatterns] = useState([]);
  const [showPatterns, setShowPatterns] = useState(false);
  const [showTrend, setShowTrend] = useState(false);
  const [trend, setTrend] = useState(null);
  const [showRibbon, setShowRibbon] = useState(false);
  const [spike, setSpike] = useState(null);
  // Trader fills on the price: off by default (busy on large coins), the viewer's choice remembered.
  const [showEntries, setShowEntriesState] = useState(() => {
    if (compact) return false;
    try { return localStorage.getItem(ENTRIES_KEY) === "1"; } catch (_) { return false; }
  });
  const setShowEntries = useCallback(next => setShowEntriesState(prev => {
    const v = typeof next === "function" ? next(prev) : next;
    try { localStorage.setItem(ENTRIES_KEY, v ? "1" : "0"); } catch (_) { /* private mode: not remembered */ }
    return v;
  }), []);
  const [posTip, setPosTip] = useState(null);   // {x, time}: the pointer over the long/short pane
  const [posTop, setPosTop] = useState(null);   // where the long/short pane starts, px from the chart's top
  const [hoverMark, setHoverMark] = useState(null);
  const fillPrimRef = useRef(null);
  const focusRef = useRef(focusRange);
  focusRef.current = focusRange;
  const [candleTimes, setCandleTimes] = useState(null);
  const [posGroup, setPosGroup] = useState("profitable");
  const [posMeasure, setPosMeasure] = useState("n");
  const posMeasureRef = useRef("n");
  posMeasureRef.current = posMeasure;
  const posSeriesRef = useRef(null);       // {long, short, markers} in the bottom pane
  const showPos = positioningPane && !compact;
  const posH = showPos ? (height >= 500 ? 116 : 92) : 0;
  const trendSeriesRef = useRef(null);
  const ribbonSeriesRef = useRef([]);
  const spikeZoneRef = useRef(null);
  const showTrendRef = useRef(false);
  const showRibbonRef = useRef(false);
  const zoneEndRef = useRef(null);
  const patternSeriesRef = useRef([]);
  const entryMarkersRef = useRef(null);
  const entryLinesRef = useRef([]);
  const myEntryLineRef = useRef(null);

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
      height: height + posH,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: resolveToken("chartText"),
        fontFamily: "'SF Mono', 'Fira Code', monospace",
        fontSize: 12,
        attributionLogo: false,
        // The long/short pane's divider: as quiet as the grid.
        panes: { separatorColor: resolveToken("chartGrid") || "rgba(255,255,255,0.06)", separatorHoverColor: "rgba(151,252,228,0.15)", enableResize: false },
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
        rightOffset: 10,   // room for the entry-line labels right of the last candle
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

    // ── Long/short pane: wallets (or dollars) long above the line and short below it, per candle ──
    posSeriesRef.current = null;
    if (showPos) {
      const accent = resolveToken("accent") || "#97FCE4";
      const fmt = v => (posMeasureRef.current === "usd" ? fmtUsdShort(Math.abs(v)) : String(Math.round(Math.abs(v))));
      const opts = { lastValueVisible: false, priceLineVisible: false, base: 0,
        priceFormat: { type: "custom", minMove: 1, formatter: fmt } };
      const long = chart.addSeries(HistogramSeries, { ...opts, color: accent }, 1);
      const short = chart.addSeries(HistogramSeries, { ...opts, color: withAlpha(accent, 0.42) }, 1);
      try { chart.panes()[1]?.setHeight(posH); } catch (_) { /* older layouts: the pane keeps its share */ }
      // Room above the tallest bar for the pane's label.
      try { chart.priceScale("right", 1).applyOptions({ scaleMargins: { top: 0.24, bottom: 0.04 } }); } catch (_) {}
      posSeriesRef.current = { long, short, markers: createSeriesMarkers(long, []) };
    }

    // ── CTO ribbon (rendered behind BMSB; display only) ──
    const ribbonSeries = RIBBON_LINES.map(l => chart.addSeries(LineSeries, {
      color: col(RIBBON_COLOR.grey),
      lineWidth: l.width,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      visible: showRibbonRef.current,
    }));
    ribbonSeriesRef.current = ribbonSeries;

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

    // The engine's trend line (the z-score's baseline: 300-bar regression of log price).
    const trendSeries = chart.addSeries(LineSeries, { color: col("#91b9e8"), lineWidth: 1, lineStyle: LineStyle.Dashed, title: "Trend",
      lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false, visible: showTrendRef.current });
    trendSeriesRef.current = trendSeries;
    if (compact) {
      for (const ser of [ma200Series, bmsbEmaSeries, bmsbSmaSeries, bmsbMidSeries]) ser.applyOptions({ visible: false });
    }

    // ── Fetch data ──
    const tfConfig = TIMEFRAMES.find(t => t.key === tf) || TIMEFRAMES[2];
    const apiTf = tfConfig.apiTf || tf;
    const encoded = encodeURIComponent(symbol);
    setLoading(true);
    setHoverCandle(null);
    setRibbon(null);
    setPatterns([]);
    setSpike(null);
    setTrend(null);
    setCandleTimes(null);
    entryMarkersRef.current = null;
    entryLinesRef.current = [];
    zoneEndRef.current = null;
    spikeZoneRef.current = null;
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
          // The pane sits under the price pane; the date axis is below both.
          if (showPos) requestAnimationFrame(() => { if (!cancelled) { try { setPosTop(chart.paneSize(0).height + 1); } catch (_) {} } });
          candleSeriesRef.current = candleSeries;
          if (compact) {
            const prim = new FillMarks(fillColors());
            candleSeries.attachPrimitive(prim);
            fillPrimRef.current = prim;
          }

          // ── Volume data ──
          if (data.volume?.length > 0) {
            volumeSeries.setData(data.volume);
          }

          const volumes = new Map((data.volume || []).map(v => [v.time, v.value]));
          const readCandle = candle => setHoverCandle(candle ? {
            ...candle, change:candleChange(candle), volume:volumes.get(candle.time),
            live: candle.time <= Date.now()/1000 && candle.time + (apiTf === '1d' ? 86400 : 14400) > Date.now()/1000,
          } : null);
          chart.subscribeCrosshairMove(param => {
            if (cancelled) return;
            const candle = param.seriesData?.get(candleSeries);
            readCandle(candle?.open != null ? candle : null);
            if (compact) setHoverMark(param.point ? fillPrimRef.current?.hitTest(param.point.x, param.point.y) || null : null);
            if (showPos) setPosTip(param.paneIndex === 1 && param.point && param.time != null ? { x: param.point.x, time: param.time } : null);
          });
          trendSeries.setData(data.trend?.line || []);
          setTrend(data.trend ? { kind: data.trend.kind, bars: data.trend.bars } : null);
          if (data.spike) {
            setSpike(data.spike);
            const anchorIndex = data.spike.anchor_time != null ? data.candles.findIndex(c => c.time === data.spike.anchor_time) : -1;
            if (anchorIndex >= 0 && data.spike.zone) {
              // Drawn with the Trend line; the reset view then makes room for the part still ahead.
              zoneEndRef.current = anchorIndex + data.spike.zone.to_bar;
              const zone = new SpikeZone({ anchorIndex, anchorClose: data.spike.anchor_close, zone: data.spike.zone,
                colors: { fill: "rgba(207,145,133,0.08)", line: col("#cf9185"), text: col("#cf9185") } });
              zone.setVisible(showTrendRef.current);
              candleSeries.attachPrimitive(zone);
              spikeZoneRef.current = zone;
            }
          }

          // Anchor the signal to its recorded first-seen candle, never the live bar.
          const markerDef = signal && SIGNAL_MARKER[signal];
          if (markerDef) {
            const last = data.candles[data.candles.length - 1];
            const markerTime = (!signalTimeframe || signalTimeframe === apiTf)
              ? signalCandleTime(data.candles, signalFirstSeenAt, apiTf === "4h" ? 14400 : 86400)
              : null;
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
          const focus = focusRef.current;
          if (compact && focus && candleCount) {
            const times = data.candles.map(c => c.time);
            const idx = t => { const i = times.findIndex(x => x > t); return i < 0 ? times.length - 1 : Math.max(0, i - 1); };
            const a = idx(focus.from), b = idx(focus.to);
            const pad = Math.ceil(Math.max(24, b - a) * 0.08) + 2;
            chart.timeScale().setVisibleLogicalRange({ from: a - pad, to: Math.min(b + pad, times.length - 1 + 4) });
            return;
          }
          const plotWidth = Math.max(160, (containerRef.current?.clientWidth || 900) - 80);
          const preferredBars = tf === "1d" ? 150 : 180;
          const visibleBars = Math.min(preferredBars, Math.max(40, Math.floor(plotWidth / 4)));
          // Keep ~100px empty right of the last candle for the entry-line labels,
          // whatever the width: p empty bars take p / (visibleBars + p) of the plot.
          const pad = Math.max(6, Math.ceil(100 * visibleBars / Math.max(60, plotWidth - 100)));
          // With the Trend line on after a spike, extend the view to the end of the "where past spikes bottomed" zone.
          const zoneEnd = zoneEndRef.current != null && showTrendRef.current ? zoneEndRef.current + 3 : 0;
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
      // Everything tied to this chart's series goes with it, so no effect touches a disposed object.
      candleSeriesRef.current = null;
      entryMarkersRef.current = null;
      entryLinesRef.current = [];
      myEntryLineRef.current = null;
      fillPrimRef.current = null;
      posSeriesRef.current = null;
      pressureLinesRef.current = [];
      patternSeriesRef.current = [];
      // The trend-line effect runs before the rebuild on a timeframe switch; it must not reach
      // this chart's series once the chart is gone (applyOptions there schedules a paint of a
      // removed chart, which throws "Object is disposed" on the next frame).
      trendSeriesRef.current = null;
      ribbonSeriesRef.current = [];
      spikeZoneRef.current = null;
      try { chart.remove(); } catch (_) { /* ignore */ }
      chartRef.current = null;
    };
  }, [symbol, height, signal, signalFirstSeenAt, signalTimeframe, regime, exhaustionState, floorConfirmed, mode, compact, showPos, posH]);

  // Overlay toggles: the trend line (with the after-the-spike zone) and the trend ribbon, off by default.
  useEffect(() => {
    showTrendRef.current = showTrend;
    try { trendSeriesRef.current?.applyOptions({ visible: showTrend }); } catch (_) {}
    spikeZoneRef.current?.setVisible(showTrend);
    if (zoneEndRef.current != null) resetViewRef.current?.();
  }, [showTrend, activeTimeframe]);
  useEffect(() => {
    showRibbonRef.current = showRibbon;
    for (const ser of ribbonSeriesRef.current) { try { ser.applyOptions({ visible: showRibbon }); } catch (_) {} }
  }, [showRibbon, activeTimeframe]);

  useEffect(() => {
    const cleanup = buildChart(activeTimeframe);
    return cleanup;
  }, [activeTimeframe, buildChart]);

  // Long/short pane: one bar pair per candle from the group's record, dots where the
  // profitable-trader list was rebuilt.
  const tfSec = activeTimeframe === "1d" ? 86400 : 14400;
  const posSeries = showPos ? positioning?.groups?.[posGroup] : null;
  const posBars = useMemo(() => (posSeries ? candleBars(posSeries, posMeasure, tfSec, candleTimes) : []),
    [posSeries, posMeasure, tfSec, candleTimes]);
  // Dots only where the list changed a lot (the daily rebuild usually swaps a handful of wallets).
  const posRebuilds = useMemo(() => (showPos && posGroup === "profitable"
    ? rebuildCandles(positioning?.rebuilds, tfSec, candleTimes).filter(r => r.rules || r.joined + r.left >= REBUILD_DOT_MIN) : []),
    [showPos, posGroup, positioning, tfSec, candleTimes]);
  useEffect(() => {
    const s = posSeriesRef.current;
    if (!s || !candleTimes) return;
    try {
      s.long.setData(posBars.map(b => ({ time: b.time, value: b.long })));
      s.short.setData(posBars.map(b => ({ time: b.time, value: -b.short })));
      const dot = resolveToken("text4") || "#5b6b6b";
      s.markers.setMarkers(posRebuilds.map(r => ({ time: r.time, position: "aboveBar", shape: "circle", color: dot, size: 0.4 })));
    } catch (_) { /* the chart was rebuilt meanwhile; the next run fills the new one */ }
  }, [posBars, posRebuilds, candleTimes]);
  const rosterCounts = useRosterCounts();

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

  // Profitable traders holding this coin: the page passes them in (it shows them in its own
  // card); elsewhere the chart loads them itself.
  const ownTraders = useCoinTraders(symbol, showEntries && !traders);
  const entries = traders ? traders.entries : (showEntries ? ownTraders.entries : null);
  const opens = showEntries && !traders ? ownTraders.opens : null;

  useEffect(() => {
    const series = candleSeriesRef.current;
    entryLinesRef.current.forEach(pl => { try { series?.removePriceLine(pl); } catch (_) {} });
    entryLinesRef.current = [];
    try { entryMarkersRef.current?.setMarkers([]); } catch (_) {}
    if (!series || !candleTimes?.length || !entries?.traders?.length) return;
    // The candle a fill belongs to: the last candle opening at or before it.
    const barOf = t => {
      if (t < candleTimes[0]) return null;
      let lo = 0, hi = candleTimes.length - 1;
      while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (candleTimes[mid] <= t) lo = mid; else hi = mid - 1; }
      return candleTimes[lo];
    };
    const markers = [];
    // With Trader entries on: each of the largest holders' fill bursts as an arrow in their
    // avatar colour, tagged with their codename's initials. (New positions of every tracked
    // wallet are no longer drawn on the price: the long/short pane shows them per candle.)
    const tags = markerTags((entries?.traders || []).map(tr => tr.address));
    const light = mode === "light";
    for (const tr of showEntries ? entries?.traders || [] : []) {
      const tag = tags.get(String(tr.address).toLowerCase()) || tr.label;
      const color = walletColor(tr.address, light);
      for (const b of tr.bursts || []) {
        const time = barOf(b.t);
        if (time == null) continue;
        const buy = (b.kind === "open") === (b.side === "long");
        markers.push({
          time, price: b.px, position: buy ? "atPriceBottom" : "atPriceTop", shape: buy ? "arrowUp" : "arrowDown",
          color, text: b.kind === "close" ? `${tag} exit` : tag,
        });
      }
    }
    markers.sort((a, b) => a.time - b.time);
    // The markers belong to one series; after a rebuild the old one is disposed, so start anew.
    try { if (entryMarkersRef.current) entryMarkersRef.current.setMarkers(markers); else entryMarkersRef.current = createSeriesMarkers(series, markers); }
    catch (_) { entryMarkersRef.current = null; try { entryMarkersRef.current = createSeriesMarkers(series, markers); } catch (__) { return; } }
    for (const side of ["long", "short"]) {
      const sd = entries?.sides?.[side];
      if (!sd?.n || !sd.median_entry) continue;
      try {
        entryLinesRef.current.push(series.createPriceLine({
          price: sd.median_entry, color: sideColor(side), lineWidth: 1, lineStyle: LineStyle.Dashed,
          axisLabelVisible: true, title: `${sd.n} ${side} · median entry`,
        }));
      } catch (_) { /* the series was disposed by a rebuild */ }
    }
  }, [showEntries, entries, candleTimes, mode]);

  // Your entry: a thicker, longer-dashed line in the side colour, so it reads apart from the
  // traders' median-entry lines. Redrawn when the chart is rebuilt (candleTimes) or the theme changes.
  useEffect(() => {
    const series = candleSeriesRef.current;
    if (myEntryLineRef.current) { try { series?.removePriceLine(myEntryLineRef.current); } catch (_) {} myEntryLineRef.current = null; }
    if (!series || !candleTimes?.length || !myEntry?.price) return;
    try {
      myEntryLineRef.current = series.createPriceLine({
        price: myEntry.price, color: sideColor(myEntry.side === "short" ? "short" : "long"), lineWidth: 2, lineStyle: LineStyle.LargeDashed,
        axisLabelVisible: true, title: entryLabel,
      });
    } catch (_) { myEntryLineRef.current = null; }
  }, [myEntry, candleTimes, mode, entryLabel]);

  // A trader's fills (compact mode): one mark per candle, kind and side. A new focus range
  // (another position on the same coin) moves the view.
  useEffect(() => {
    const prim = fillPrimRef.current;
    if (!prim || !candleTimes?.length) return;
    prim.setMarks(fillMarks(fills || [], candleTimes), fillColors());
  }, [fills, candleTimes, mode]);
  useEffect(() => {
    if (compact && candleTimes?.length && focusRange) resetViewRef.current?.();
  }, [compact, candleTimes, focusRange?.from, focusRange?.to]);  // eslint-disable-line react-hooks/exhaustive-deps

  // Zoom from a little before the earliest burst on the chart to the latest candle.
  const firstBurst = Math.min(...(entries?.traders || []).flatMap(tr => (tr.bursts || []).map(b => b.t)));
  const showEntriesRange = Number.isFinite(firstBurst) && candleTimes?.length ? () => {
    setShowEntries(true);                       // asked for from the Traders card: draw the fills
    let i = candleTimes.findIndex(t => t > firstBurst) - 1;
    if (i < 0) i = firstBurst >= candleTimes[0] ? candleTimes.length - 1 : 0;
    const last = candleTimes.length - 1;
    chartRef.current?.timeScale().setVisibleLogicalRange({ from: Math.max(0, Math.min(i, last - 20) - 12), to: last + 4 });
  } : null;

  useEffect(() => { if (traderApi) traderApi.current = { showEntries: showEntriesRange }; });

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
  // Failed patterns stay listed but are not counted as something current.
  const activePatterns = patterns.filter(p => p.status === "forming" || p.status === "confirmed").length;

  return (
    <div className={`price-chart-panel${compact ? " price-chart-compact" : ""}`} style={{
      width: "100%",
      overflow: "hidden",
      marginBottom: compact ? 0 : 14,
      position: "relative",
    }}>
      {/* ── Top bar: info strip + timeframe toggle (compact: reset and timeframe only) ── */}
      {compact ? (
        <div className="chart-toolbar chart-toolbar-compact">
          <div className="chart-compact-left">{toolbarAction}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button type="button" className="chart-reset" disabled={loading || !!error} onClick={() => resetViewRef.current?.()} title="Back to the position's period">Reset view</button>
            {timeframeControl && (
              <Tabs small label="Chart timeframe" items={TIMEFRAMES.map(tf => ({ key: tf.key, label: tf.label }))}
                value={activeTimeframe} onChange={setActiveTimeframe} />
            )}
          </div>
        </div>
      ) : (
      <div className="chart-toolbar" style={{
        position: "relative", zIndex: 5,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "14px 18px",
        background: "linear-gradient(180deg, rgba(9,22,25,0.92) 0%, rgba(9,22,25,0.5) 70%, transparent 100%)",
      }}>
        {/* Left: info pills */}
        <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
          {/* Regime pill */}
          {showSetup && rm && (
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

          {/* Without the pills (coin page), the regime stays as a quiet anchor: icon and word only,
              so the toolbar still says what the setup is once the page header scrolls away. */}
          {!showSetup && rm && (
            <span className="chart-regime" style={{ color: rm.color }}>
              <RegimeIcon regime={regime} size={12} />
              {rm.name}
            </span>
          )}

          {/* Signal pill */}
          {showSetup && sm && signal !== "WAIT" && (
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

        </div>

        {/* Right: pressure toggle + timeframe toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {toolbarAction}
          <button type="button" className="chart-reset" disabled={loading || !!error} onClick={() => resetViewRef.current?.()} title="Return to the default candle density and latest price">Reset view</button>
          {/* Overlays: Trader entries on, the rest off until asked for. One (i) explains them all. */}
          {[
            { key: "entries", on: showEntries, set: setShowEntries, long: "Trader entries", short: "Entries" },
            { key: "levels", on: showPressure, set: setShowPressure, long: pressureLoading ? "Loading…" : "Wallet levels", short: pressureLoading ? "Loading…" : "Levels" },
            { key: "trend", on: showTrend, set: setShowTrend, long: "Trend", short: "Trend" },
            { key: "ribbon", on: showRibbon, set: setShowRibbon, long: "Ribbon", short: "Ribbon" },
            activeTimeframe === "1d" && { key: "patterns", on: showPatterns, set: setShowPatterns, long: `Patterns${activePatterns ? ` (${activePatterns})` : ""}`, short: "Patterns" },
          ].filter(Boolean).map(t => (
            <button key={t.key} type="button" onClick={() => t.set(v => !v)} aria-pressed={t.on}
              style={{
                padding: "3px 2px", border: 0, borderBottom: `2px solid ${t.on ? T.accent : "transparent"}`, borderRadius: 0,
                cursor: "pointer", fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.04em",
                background: "transparent", color: t.on ? T.text1 : T.text4,
              }}>
              <span className="chart-levels-label">{t.long}</span><span className="chart-levels-label-short">{t.short}</span>
            </button>
          ))}
          <HelpTip title="Chart layers" width={420}>
            <p>Dashed lines: the median entry of the largest profitable traders holding this coin, per side.</p>
            <p>Trader entries (off until turned on): those traders' fills, each drawn in the colour of their avatar and tagged with their name's initials (Arctic Mako is AM). Each arrow is a burst of their fills on Hyperliquid at its average price: up for buying, down for selling, tagged "exit" when it reduced the position. Information, not a signal.</p>
            <p>Wallet levels: liquidation clusters and the stop, take-profit and limit-order levels of tracked wallets. Orders can change or be cancelled.</p>
            <p>Trend: {trendNote(trend, activeTimeframe)} After a spike, the box shows where past spikes bottomed.</p>
            <p>Ribbon: four moving averages coloured by trend on closed candles: gold up, blue down, grey no clear trend.{ribbon?.current === "grey" && ribbon.last_actionable ? ` The last trend was ${ribbon.last_actionable}.` : ""} Display only; not used by signals.</p>
            {activeTimeframe === "1d" && <p>Patterns: detected chart patterns with their measured track record. Display only; never used by signals.</p>}
          </HelpTip>

          {/* Timeframe toggle, only where the chart owns its timeframe */}
          {timeframeControl && (
            <Tabs small label="Chart timeframe" items={TIMEFRAMES.map(tf => ({ key: tf.key, label: tf.label }))}
              value={activeTimeframe} onChange={setActiveTimeframe} />
          )}
        </div>
      </div>
      )}

      {/* ── Loading overlay ── */}
      {loading && (
        <div style={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: alpha(T.bg, 80), zIndex: 10,
        }}>
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
          }}>
            <div style={{
              width: 20, height: 20,
              border: `2px solid ${alpha(T.accent, 15)}`,
              borderTopColor: T.accent,
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
          background: alpha(T.bg, 90), zIndex: 10,
        }}>
          <span style={{
            color: alpha(T.red, 80), fontFamily: T.font, fontSize: 13, padding: "24px 32px", maxWidth: 560, textAlign: "center", lineHeight: 1.6,
            letterSpacing: "0.01em",
          }}>
            Chart unavailable ({error})
          </span>
        </div>
      )}

      {/* ── Chart container; the candle readout floats over it only while the pointer is on a candle ── */}
      <div style={{ position: "relative" }}>
        <div className="price-chart-canvas" ref={containerRef} style={{ width: "100%", height: height + posH }} />
        {showPos && !loading && !error && posTop != null && <PaneLabel top={posTop} group={posGroup} measure={posMeasure} />}
        {showPos && posTip && posTop != null && <PaneTip tip={posTip} top={posTop} group={posGroup} measure={posMeasure}
          bar={posBars.find(b => b.time === posTip.time)} rebuild={posRebuilds.find(r => r.time === posTip.time)}
          tf={activeTimeframe} width={containerRef.current?.clientWidth || 0} />}
        {hoverMark && <div className="candle-inspector fill-inspector" aria-label="Fill details">
          <strong style={{ color: sideColor(hoverMark.side) }}>{KIND_WORD[hoverMark.kind]} {hoverMark.side}</strong>
          <span>{fmtUsdShort(hoverMark.usd)} at <b>{fmtPrice(hoverMark.px)}</b></span>
          {hoverMark.n > 1 && <span>{hoverMark.n} fills</span>}
          <span>{fmtStamp(hoverMark.t0)}{hoverMark.t1 - hoverMark.t0 >= 600 ? ` to ${fmtStamp(hoverMark.t1)}` : ""}</span>
          {hoverMark.kind !== "open" && hoverMark.kind !== "add" && Math.abs(hoverMark.pnl) >= 1 &&
            <span style={{ color: hoverMark.pnl >= 0 ? T.green : T.red }}>{hoverMark.pnl >= 0 ? "+" : "\u2212"}{fmtUsdShort(Math.abs(hoverMark.pnl))}</span>}
        </div>}
        {hoverCandle && !hoverMark && <div className="candle-inspector" aria-label="Candle details">
          <span>{new Date(hoverCandle.time*1000).toLocaleString('en-GB',{timeZone:'UTC',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})} UTC</span>
          <strong style={{color:hoverCandle.change == null ? T.text3 : hoverCandle.change >= 0 ? col('#97FCE4') : col('#d8a094')}}>{hoverCandle.change == null ? '—' : `${hoverCandle.change>=0?'+':''}${hoverCandle.change.toFixed(2)}%`}</strong>
          {['open','high','low','close'].map(key=><span key={key}>{key[0].toUpperCase()} <b>{new Intl.NumberFormat('en',{maximumSignificantDigits:7}).format(hoverCandle[key])}</b></span>)}
          <span>Vol <b>{Number.isFinite(hoverCandle.volume) ? new Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:2}).format(hoverCandle.volume) : '—'}</b></span>
          {hoverCandle.live && <span style={{color:col('#91b9e8')}}>Live</span>}
        </div>}
      </div>
      {showPos && !error && <PositioningBar group={posGroup} setGroup={setPosGroup} measure={posMeasure} setMeasure={setPosMeasure}
        series={posSeries} bars={posBars} rebuilds={posRebuilds} hoverTime={hoverCandle?.time ?? null} counts={rosterCounts} />}
      {!loading && !error && spike && showTrend && <div style={{padding:'10px 18px',fontSize:12,color:T.text3,borderTop:`1px solid ${T.border}`,lineHeight:1.6}}>
        {spike.superseded
          ? <><strong style={{color:T.text2}}>Spike superseded</strong> · price has since closed above the spike's peak ({new Intl.NumberFormat('en',{maximumSignificantDigits:6}).format(spike.peak)}), so the trend resumed and the after-the-spike zone no longer applies.</>
          : spike.running
          ? <><strong style={{color:col('#cf9185')}}>Spike in progress</strong> · z is still above 2 (peak so far {new Intl.NumberFormat('en',{maximumSignificantDigits:6}).format(spike.peak)}). The zone appears once it ends.</>
          : spike.zone ? <><strong style={{color:col('#cf9185')}}>After the spike</strong> · {spike.zone.n} past spikes on this timeframe: half bottomed {Math.round(-100*(1 - spike.zone.top/spike.anchor_close))}% to {Math.round(-100*(1 - spike.zone.bottom/spike.anchor_close))}% below the close where the spike ended, {spike.zone.from_bar} to {spike.zone.to_bar} {activeTimeframe === '1d' ? 'days' : 'bars'} later (median {Math.round(-100*(1 - spike.zone.median_price/spike.anchor_close))}% at {spike.zone.median_bar}). {Math.round(100*spike.zone.never_fell_5pct)}% never fell 5%. Past spikes only.
            <HelpTip title="After the spike" width={380}>
              <p>A spike is the last time this coin's z-score reached 2.5; it ends when z drops back under 2. The box and the dashed path start from that bar's close, which is known at the time; the true peak is only known later.</p>
              <p>The box covers the middle half of past lows (depth and timing), measured on the study period only (to 29 March 2026). One in four past spikes fell deeper than the box, and one in four fell less.</p>
              <p>The engine blocks nothing because of this picture.</p>
            </HelpTip></>
          : <>Spike detected; no history for this timeframe yet.</>}
      </div>}
      {!traders && !loading && !error && showEntries && entries && <TraderEntries entries={entries} onShow={showEntriesRange} />}
      {!traders && !loading && !error && showEntries && opens && <WalletOpens opens={opens} />}

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

// Under the chart: which group the bottom pane shows, its numbers at the hovered candle (the
// latest reading otherwise), the measure, and the definitions.
const POS_MEASURES = [{ key: "n", label: "Traders", title: "Wallets on each side" }, { key: "usd", label: "$", title: "Position value on each side" }];

function PositioningBar({ group, setGroup, measure, setMeasure, series, bars, rebuilds, hoverTime, counts }) {
  const defs = groupDefinitions(counts);
  const { width } = useViewport();
  const narrow = width < 640;
  const pts = points(series, measure);
  const fmt = measure === "usd" ? fmtUsdShort : count;
  const at = hoverTime != null ? bars.find(b => b.time === hoverTime) : latest(pts);
  const rebuilt = hoverTime != null && rebuilds.find(r => r.time === hoverTime);
  let read;
  if (!series) read = <span className="chart-pos-dim">Loading…</span>;
  else if (!recorded(pts)) read = <span className="chart-pos-dim">Not recorded yet</span>;
  else if (!at) read = <span className="chart-pos-dim">No reading at this candle</span>;
  else read = <><b className="chart-pos-l">{fmt(at.long)}</b> long<span className="chart-pos-sep">·</span><b className="chart-pos-s">{fmt(at.short)}</b> short
    {rebuilt && <span className="chart-pos-dim"> · {rebuilt.rules ? "list rules changed" : "list rebuilt"}</span>}</>;
  return <div className="chart-pos-bar">
    <Tabs small label="Wallet group" items={COIN_GROUPS.map(g => ({ key: g.key, label: narrow ? g.short : g.name, title: `${g.name}: ${g.sub}` }))} value={group} onChange={setGroup} />
    <span className="chart-pos-read" aria-live="off">{read}</span>
    <span className="chart-pos-end">
      <Tabs small label="Measure" items={POS_MEASURES} value={measure} onChange={setMeasure} />
      <HelpTip title="Long and short" width={420}>
        <p>The bars under the candles: wallets (or dollars) long above the line, short below it, one pair per candle from the reading at its close; the current candle shows the latest. Each wallet counts once.</p>
        <p>{defs.profitable}</p>
        <p>{defs.winners} {defs.losers} {defs.whales}</p>
        <p>{defs.windows} {defs.sweep}</p>
        <p>Dots on Profitable traders: the list was rebuilt with {REBUILD_DOT_MIN} or more wallets joining or leaving, or its rules changed. A step there is the list changing, not trading.</p>
      </HelpTip>
    </span>
  </div>;
}

// The pane's own label, top left: which group, and which way is long.
function PaneLabel({ top, group, measure }) {
  const g = COIN_GROUPS.find(x => x.key === group);
  return <div className="chart-pane-label" style={{ top: top + 5 }}>
    {g?.name}<span className="chart-pane-label-more"> · {measure === "usd" ? "dollars" : "wallets"} long above the line, short below</span>
  </div>;
}

// Hovering the pane: the candle's numbers, and what a dot there means.
function PaneTip({ tip, top, group, measure, bar, rebuild, tf, width }) {
  const g = COIN_GROUPS.find(x => x.key === group);
  const fmt = measure === "usd" ? fmtUsdShort : count;
  const d = new Date(tip.time * 1000);
  const when = `${d.toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short" })}${tf === "1d" ? "" : ` ${String(d.getUTCHours()).padStart(2, "0")}:00`} UTC`;
  const left = tip.x > width - 300 ? Math.max(8, tip.x - 292) : tip.x + 14;
  return <div className="chart-pane-tip" style={{ left, top: top + 26 }} role="status">
    <span className="chart-pane-tip-head">{g?.name} · {when}</span>
    {bar ? <span><b className="chart-pos-l">{fmt(bar.long)}</b> long<span className="chart-pos-sep">·</span><b className="chart-pos-s">{fmt(bar.short)}</b> short</span>
      : <span className="chart-pos-dim">No reading for this candle</span>}
    {rebuild && <span className="chart-pane-tip-note">{rebuild.rules
      ? "Dot: the list's rules changed here. A step at the dot is the list changing, not trading."
      : `Dot: the list was rebuilt here: ${rebuild.joined} wallets joined${rebuild.left ? `, ${rebuild.left} left` : ""}. A step at the dot is the list changing, not trading.`}</span>}
  </div>;
}
