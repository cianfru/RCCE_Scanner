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
import { T, REGIME_META, SIGNAL_META, heatColor, resolveToken, getBaseSymbol } from "../theme.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── Signal → marker mapping ──────────────────────────────────────────────────

const SIGNAL_MARKER = {
  STRONG_LONG:  { color: "#34d399", shape: "arrowUp",   position: "belowBar", text: "STRONG LONG" },
  LIGHT_LONG:   { color: "#6ee7b7", shape: "arrowUp",   position: "belowBar", text: "LIGHT LONG" },
  ACCUMULATE:   { color: "#22d3ee", shape: "arrowUp",   position: "belowBar", text: "ACCUMULATE" },
  REVIVAL_SEED: { color: "#67e8f9", shape: "arrowUp",   position: "belowBar", text: "REVIVAL" },
  TRIM:         { color: "#fbbf24", shape: "arrowDown", position: "aboveBar", text: "TRIM" },
  TRIM_HARD:    { color: "#f87171", shape: "arrowDown", position: "aboveBar", text: "TRIM HARD" },
  RISK_OFF:     { color: "#ef4444", shape: "arrowDown", position: "aboveBar", text: "RISK-OFF" },
  NO_LONG:      { color: "#d8b4fe", shape: "arrowDown", position: "aboveBar", text: "NO LONG" },
};

// ─── Timeframe options ────────────────────────────────────────────────────────

const TIMEFRAMES = [
  { key: "4h",  label: "4H",  limit: 500,  apiTf: "4h", barSpace: 8 },   // ~83 days of 4H candles
  { key: "1d",  label: "1D",  limit: 500,  apiTf: "1d", barSpace: 10 },  // ~500 days — enough for 200 MA + visible range
];

export default function BMSBChart({
  symbol,
  timeframe: initialTimeframe = "1d",
  height = 360,
  signal,
  regime,
  heat,
  conditions,
  conditionsTotal,
  exhaustionState,
  floorConfirmed,
  signalConfidence,
  momentum,
}) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const pressureLinesRef = useRef([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTimeframe, setActiveTimeframe] = useState(initialTimeframe === "1d" ? "1d" : "4h");
  const [showPressure, setShowPressure] = useState(false);
  const [pressureData, setPressureData] = useState(null);
  const [pressureLoading, setPressureLoading] = useState(false);

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
        fontSize: 10,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.02)" },
        horzLines: { color: "rgba(255,255,255,0.025)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "rgba(34,211,238,0.15)",
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#1a1a1e",
        },
        horzLine: {
          color: "rgba(34,211,238,0.15)",
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#1a1a1e",
        },
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.06)",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 8,
        barSpacing: (TIMEFRAMES.find(t => t.key === tf) || {}).barSpace || 8,
        minBarSpacing: 3,
      },
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.06)",
        scaleMargins: { top: 0.08, bottom: 0.18 },
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
              fontFamily: "'Inter', sans-serif",
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
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "rgba(34,197,94,0.5)",
      wickDownColor: "rgba(239,68,68,0.5)",
    });

    // ── CTO Line Advanced (rendered behind BMSB) ──
    const ctoFastSeries = chart.addSeries(LineSeries, {
      color: "#c0c0c0",
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });
    const ctoSlowSeries = chart.addSeries(LineSeries, {
      color: "#c0c0c0",
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
      title: "CTO",
    });

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
      color: "rgba(34,211,238,0.25)",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // SMA (lower band boundary)
    const bmsbSmaSeries = chart.addSeries(LineSeries, {
      color: "rgba(34,211,238,0.25)",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      crosshairMarkerVisible: false,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    // Mid (main BMSB line — solid, prominent)
    const bmsbMidSeries = chart.addSeries(LineSeries, {
      color: "#22d3ee",
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
      lastValueVisible: true,
      priceLineVisible: false,
      title: "BMSB",
    });

    // ── Fetch data ──
    const tfConfig = TIMEFRAMES.find(t => t.key === tf) || TIMEFRAMES[2];
    const apiTf = tfConfig.apiTf || tf;
    const encoded = encodeURIComponent(symbol);
    setLoading(true);
    setError(null);

    fetch(`${API_BASE}/api/chart/${encoded}?timeframe=${apiTf}&limit=${tfConfig.limit}`)
      .then(r => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then(data => {
        if (cancelled) return;

        if (data.candles?.length > 0) {
          // Auto-detect price precision for micro-cap coins (e.g. MOG at 0.0000001)
          const samplePrice = data.candles[data.candles.length - 1]?.close || 0;
          if (samplePrice > 0 && samplePrice < 0.01) {
            const decimals = Math.max(2, Math.ceil(-Math.log10(samplePrice)) + 2);
            const minMove = Math.pow(10, -decimals);
            const pf = { type: "price", precision: decimals, minMove };
            candleSeries.applyOptions({ priceFormat: pf });
            try { ctoFastSeries.applyOptions({ priceFormat: pf }); } catch(_){}
            try { ctoSlowSeries.applyOptions({ priceFormat: pf }); } catch(_){}
            try { bmsbMidSeries.applyOptions({ priceFormat: pf }); } catch(_){}
            try { bmsbEmaSeries.applyOptions({ priceFormat: pf }); } catch(_){}
            try { bmsbSmaSeries.applyOptions({ priceFormat: pf }); } catch(_){}
          }

          candleSeries.setData(data.candles);
          candleSeriesRef.current = candleSeries;

          // ── Volume data ──
          if (data.volume?.length > 0) {
            volumeSeries.setData(data.volume);
          }

          // ── Signal markers on latest candle ──
          const markerDef = signal && SIGNAL_MARKER[signal];
          if (markerDef) {
            const last = data.candles[data.candles.length - 1];
            const markers = [{
              time: last.time,
              position: markerDef.position,
              color: markerDef.color,
              shape: markerDef.shape,
              text: markerDef.text,
            }];

            if (floorConfirmed) {
              markers.push({
                time: last.time,
                position: "belowBar",
                color: "#34d399",
                shape: "circle",
                text: "FLOOR",
              });
            }
            if (exhaustionState === "CLIMAX") {
              markers.push({
                time: last.time,
                position: "aboveBar",
                color: "#fbbf24",
                shape: "circle",
                text: "CLIMAX",
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
            color: priceUp ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)",
            lineWidth: 1,
            lineStyle: LineStyle.Dotted,
            axisLabelVisible: true,
            title: "",
          });
        }

        // ── 200-day MA (computed from candle closes) ──
        if (data.candles?.length > 0) {
          // For 1D candles: 200-period MA = 200-day MA
          // For 4H candles: 200-period MA ≈ 33-day MA (useful shorter-term trend)
          const period = 200;
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

        // ── CTO Line overlay data ──
        if (data.cto_fast?.length > 0) ctoFastSeries.setData(data.cto_fast);
        if (data.cto_slow?.length > 0) ctoSlowSeries.setData(data.cto_slow);

        // ── BMSB overlay data ──
        if (data.bmsb_mid?.length > 0) bmsbMidSeries.setData(data.bmsb_mid);
        if (data.bmsb_ema?.length > 0) bmsbEmaSeries.setData(data.bmsb_ema);
        if (data.bmsb_sma?.length > 0) bmsbSmaSeries.setData(data.bmsb_sma);

        // Show most recent candles at comfortable zoom, not all crammed in
        const candleCount = data.candles?.length || 0;
        const visibleBars = tf === "1d" ? 90 : 120; // ~3 months for 1D, ~20 days for 4H
        if (candleCount > visibleBars) {
          chart.timeScale().setVisibleLogicalRange({
            from: candleCount - visibleBars,
            to: candleCount + 5,
          });
        } else {
          chart.timeScale().fitContent();
        }
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
      ro.disconnect();
      try { chart.remove(); } catch (_) { /* ignore */ }
      chartRef.current = null;
    };
  }, [symbol, height, signal, regime, exhaustionState, floorConfirmed]);

  // Build chart on mount and when dependencies change
  useEffect(() => {
    const cleanup = buildChart(activeTimeframe);
    return cleanup;
  }, [activeTimeframe, buildChart]);

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
  const momColor = momentum != null ? (momentum >= 0 ? "#22c55e" : "#ef4444") : null;

  return (
    <div style={{
      width: "100%",
      borderRadius: 12,
      overflow: "hidden",
      border: "1px solid rgba(255,255,255,0.06)",
      background: "rgba(10,10,14,0.6)",
      marginBottom: 14,
      position: "relative",
    }}>
      {/* ── Top bar: info strip + timeframe toggle ── */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, zIndex: 5,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "7px 10px",
        background: "linear-gradient(180deg, rgba(10,10,14,0.92) 0%, rgba(10,10,14,0.5) 70%, transparent 100%)",
      }}>
        {/* Left: info pills */}
        <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
          {/* Regime pill */}
          {rm && (
            <span style={{
              padding: "2px 7px", borderRadius: 10,
              background: rm.bg, color: rm.color,
              fontSize: 9, fontFamily: T.mono, fontWeight: 700,
              letterSpacing: "0.04em",
              border: `1px solid ${rm.color}20`,
              display: "inline-flex", alignItems: "center", gap: 3,
            }}>
              <span style={{ fontSize: 7 }}>{rm.glyph}</span>
              {rm.label}
            </span>
          )}

          {/* Signal pill */}
          {sm && signal !== "WAIT" && (
            <span style={{
              padding: "2px 7px", borderRadius: 10,
              background: `${sm.color}12`, color: sm.color,
              fontSize: 9, fontFamily: T.mono, fontWeight: 700,
              letterSpacing: "0.04em",
              border: `1px solid ${sm.color}18`,
              display: "inline-flex", alignItems: "center", gap: 3,
            }}>
              <span style={{ fontSize: 6 }}>{sm.dot}</span>
              {sm.label}
            </span>
          )}

          {/* Conditions */}
          {conditions != null && conditionsTotal != null && (
            <span style={{
              fontSize: 9, fontFamily: T.mono, fontWeight: 700,
              color: conditions >= 8 ? "#22c55e" : conditions >= 5 ? "#fbbf24" : "rgba(255,255,255,0.3)",
              padding: "2px 5px",
            }}>
              {conditions}/{conditionsTotal}
            </span>
          )}

          {/* Heat */}
          {heat != null && (
            <span style={{
              fontSize: 9, fontFamily: T.mono, fontWeight: 700,
              color: hColor, opacity: 0.9,
            }}>
              H:{Math.round(heat)}
            </span>
          )}

          {/* Momentum */}
          {momentum != null && (
            <span style={{
              fontSize: 9, fontFamily: T.mono, fontWeight: 600,
              color: momColor, opacity: 0.9,
            }}>
              {momentum >= 0 ? "+" : ""}{momentum.toFixed(1)}%
            </span>
          )}

          {/* Confidence */}
          {signalConfidence != null && signal !== "WAIT" && (
            <span style={{
              fontSize: 8, fontFamily: T.mono, fontWeight: 500,
              color: signalConfidence >= 0.8 ? "#22c55e" : signalConfidence >= 0.5 ? "#fbbf24" : "rgba(255,255,255,0.25)",
              opacity: 0.7,
            }}>
              {Math.round(signalConfidence * 100)}%
            </span>
          )}
        </div>

        {/* Right: pressure toggle + timeframe toggle */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {/* Pressure levels toggle */}
          <button
            onClick={() => setShowPressure(p => !p)}
            title={showPressure ? "Hide smart money levels" : "Show smart money stops/TPs/limits"}
            style={{
              padding: "3px 8px",
              borderRadius: 4,
              border: `1px solid ${showPressure ? "rgba(251,191,36,0.3)" : "rgba(255,255,255,0.08)"}`,
              cursor: "pointer",
              fontFamily: T.mono,
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "0.04em",
              transition: "all 0.15s ease",
              background: showPressure ? "rgba(251,191,36,0.12)" : "transparent",
              color: showPressure ? "#fbbf24" : "rgba(255,255,255,0.3)",
              display: "flex", alignItems: "center", gap: 3,
            }}
          >
            {pressureLoading ? "⏳" : "⚡"} SM
          </button>

          {/* Timeframe toggle */}
          <div style={{
            display: "flex", gap: 2,
            background: "rgba(255,255,255,0.04)",
            borderRadius: 6, padding: 2,
          }}>
            {TIMEFRAMES.map(tf => (
              <button
                key={tf.key}
                onClick={() => setActiveTimeframe(tf.key)}
                style={{
                  padding: "3px 10px",
                  borderRadius: 4,
                  border: "none",
                  cursor: "pointer",
                  fontFamily: T.mono,
                  fontSize: 9,
                  fontWeight: 700,
                  letterSpacing: "0.06em",
                  transition: "all 0.15s ease",
                  background: activeTimeframe === tf.key
                    ? "rgba(34,211,238,0.15)"
                    : "transparent",
                  color: activeTimeframe === tf.key
                    ? "#22d3ee"
                    : "rgba(255,255,255,0.3)",
                }}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Loading overlay ── */}
      {loading && (
        <div style={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "rgba(10,10,14,0.8)", zIndex: 10,
        }}>
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center", gap: 8,
          }}>
            <div style={{
              width: 20, height: 20,
              border: "2px solid rgba(34,211,238,0.15)",
              borderTopColor: "#22d3ee",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
            }} />
            <span style={{
              color: "rgba(255,255,255,0.3)",
              fontFamily: T.mono, fontSize: 9,
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
          background: "rgba(10,10,14,0.9)", zIndex: 10,
        }}>
          <span style={{
            color: "rgba(239,68,68,0.7)", fontFamily: T.mono, fontSize: 10,
            letterSpacing: "0.04em",
          }}>
            Chart unavailable ({error})
          </span>
        </div>
      )}

      {/* ── Chart container ── */}
      <div ref={containerRef} style={{ width: "100%", height }} />

      {/* ── CSS for spinner ── */}
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
