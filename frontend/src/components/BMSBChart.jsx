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
  { key: "4h", label: "4H", limit: 120, barSpacing: 10 },   // ~20 days
  { key: "4h", label: "3M", limit: 500, barSpacing: 5 },    // ~83 days on 4h
  { key: "1d", label: "1D", limit: 180, barSpacing: 8 },    // ~6 months
  { key: "1d", label: "1Y", limit: 365, barSpacing: 4 },    // ~1 year
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
  const [activeTfIdx, setActiveTfIdx] = useState(initialTimeframe === "1d" ? 2 : 0);
  const activeTimeframe = TIMEFRAMES[activeTfIdx]?.key || "4h";
  const [showPressure, setShowPressure] = useState(false);
  const [showVolumeProfile, setShowVolumeProfile] = useState(false);
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
        barSpacing: tfConfig.barSpacing || 8,
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
    const tfConfig = TIMEFRAMES.find((t, i) => i === activeTfIdx) || TIMEFRAMES[2];
    const encoded = encodeURIComponent(symbol);
    setLoading(true);
    setError(null);

    fetch(`${API_BASE}/api/chart/${encoded}?timeframe=${tf}&limit=${tfConfig.limit}`)
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

          // ── Historical signal markers ──
          // Fetch past signal events and place arrows on the candles where they fired
          const candleTimes = new Set(data.candles.map(c => c.time));
          const snapToCandle = (ts) => {
            // Find closest candle time <= timestamp
            let best = data.candles[0]?.time || 0;
            for (const c of data.candles) {
              if (c.time <= ts) best = c.time;
              else break;
            }
            return best;
          };

          fetch(`${API_BASE}/api/signals/history?symbol=${encoded}&timeframe=${tf}&limit=200`)
            .then(r => r.ok ? r.json() : [])
            .then(events => {
              if (cancelled) return;
              const evts = Array.isArray(events) ? events : events.events || events.changes || [];
              const markers = [];

              for (const ev of evts) {
                const sig = ev.signal || ev.label;
                const mDef = SIGNAL_MARKER[sig];
                if (!mDef) continue;
                // Skip lateral/initial — only show meaningful transitions
                const tt = ev.transition_type || "";
                if (tt === "LATERAL" || tt === "INITIAL") continue;

                const evTime = ev.timestamp;
                if (!evTime) continue;
                const candleTime = snapToCandle(evTime);
                if (!candleTime) continue;

                markers.push({
                  time: candleTime,
                  position: mDef.position,
                  color: mDef.color,
                  shape: mDef.shape,
                  text: mDef.text,
                });
              }

              // Also add current signal + floor/climax on latest candle
              const last = data.candles[data.candles.length - 1];
              if (signal && SIGNAL_MARKER[signal]) {
                const m = SIGNAL_MARKER[signal];
                markers.push({ time: last.time, position: m.position, color: m.color, shape: m.shape, text: m.text });
              }
              if (floorConfirmed) {
                markers.push({ time: last.time, position: "belowBar", color: "#34d399", shape: "circle", text: "FLOOR" });
              }
              if (exhaustionState === "CLIMAX") {
                markers.push({ time: last.time, position: "aboveBar", color: "#fbbf24", shape: "circle", text: "CLIMAX" });
              }

              // Deduplicate by time+signal (keep first occurrence)
              const seen = new Set();
              const unique = markers.filter(m => {
                const key = `${m.time}:${m.text}`;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
              });

              unique.sort((a, b) => a.time - b.time);
              if (unique.length > 0) {
                try { createSeriesMarkers(candleSeries, unique); } catch (_) {}
              }
            })
            .catch(() => {});

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

        // ── CTO Line overlay data ──
        if (data.cto_fast?.length > 0) ctoFastSeries.setData(data.cto_fast);
        if (data.cto_slow?.length > 0) ctoSlowSeries.setData(data.cto_slow);

        // ── BMSB overlay data ──
        if (data.bmsb_mid?.length > 0) bmsbMidSeries.setData(data.bmsb_mid);
        if (data.bmsb_ema?.length > 0) bmsbEmaSeries.setData(data.bmsb_ema);
        if (data.bmsb_sma?.length > 0) bmsbSmaSeries.setData(data.bmsb_sma);

        // ── Regime background strip (colored bar at top) ──
        fetch(`${API_BASE}/api/signals/regime-history?symbol=${encoded}&timeframe=${tf}&limit=200`)
          .then(r => r.ok ? r.json() : [])
          .then(regimeEvents => {
            if (cancelled) return;
            const evts = Array.isArray(regimeEvents) ? regimeEvents : regimeEvents.events || [];
            if (evts.length === 0 || !data.candles?.length) return;

            const REGIME_COLORS = {
              MARKUP: "rgba(52,211,153,0.08)", BLOWOFF: "rgba(248,113,113,0.08)",
              REACC: "rgba(34,211,238,0.08)", MARKDOWN: "rgba(251,146,60,0.08)",
              CAP: "rgba(192,132,252,0.08)", ACCUM: "rgba(110,231,183,0.08)",
              ABSORBING: "rgba(216,180,254,0.08)", FLAT: "rgba(82,82,91,0.04)",
            };

            // Build regime at each candle time by replaying transitions
            const transitions = evts
              .filter(e => e.timestamp && e.regime)
              .sort((a, b) => a.timestamp - b.timestamp);

            if (transitions.length === 0) return;

            // Create a regime strip series (thin histogram at top)
            try {
              const regimeStrip = chart.addSeries(HistogramSeries, {
                priceFormat: { type: "volume" },
                priceScaleId: "regime",
                lastValueVisible: false,
                priceLineVisible: false,
              });
              chart.priceScale("regime").applyOptions({
                scaleMargins: { top: 0, bottom: 0.97 },
                drawTicks: false,
                borderVisible: false,
              });

              let currentRegime = transitions[0].prev_regime || transitions[0].regime || "FLAT";
              let tIdx = 0;

              const stripData = data.candles.map(c => {
                // Advance regime to match candle time
                while (tIdx < transitions.length && transitions[tIdx].timestamp <= c.time) {
                  currentRegime = transitions[tIdx].regime;
                  tIdx++;
                }
                return {
                  time: c.time,
                  value: 1,
                  color: REGIME_COLORS[currentRegime] || REGIME_COLORS.FLAT,
                };
              });

              regimeStrip.setData(stripData);
            } catch (_) {}
          })
          .catch(() => {});

        // ── Heat strip (colored bar below volume) ──
        if (data.heat_series?.length > 0) {
          try {
            const heatStrip = chart.addSeries(HistogramSeries, {
              priceFormat: { type: "volume" },
              priceScaleId: "heat",
              lastValueVisible: false,
              priceLineVisible: false,
            });
            chart.priceScale("heat").applyOptions({
              scaleMargins: { top: 0.92, bottom: 0.04 },
              drawTicks: false,
              borderVisible: false,
            });
            const heatData = data.heat_series.map(h => ({
              time: h.time,
              value: 1,
              color: h.value > 70 ? "rgba(248,113,113,0.25)"
                   : h.value > 40 ? "rgba(251,191,36,0.2)"
                   : "rgba(52,211,153,0.15)",
            }));
            heatStrip.setData(heatData);
          } catch (_) {}
        }

        chart.timeScale().fitContent();
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
  }, [symbol, height, signal, regime, exhaustionState, floorConfirmed, activeTfIdx]);

  // Build chart on mount and when dependencies change
  useEffect(() => {
    const cleanup = buildChart(activeTimeframe);
    return cleanup;
  }, [activeTfIdx, buildChart]);

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

        // Stops — red solid
        (data.smart_money_orders?.stops || []).forEach(o => {
          levels.push({
            price: o.price, color: "#f87171", style: LineStyle.Solid, width: 2,
            title: `STOP $${fmtSize(o.total_size_usd)}`,
          });
        });
        // Take Profits — green solid
        (data.smart_money_orders?.take_profits || []).forEach(o => {
          levels.push({
            price: o.price, color: "#34d399", style: LineStyle.Solid, width: 2,
            title: `TP $${fmtSize(o.total_size_usd)}`,
          });
        });
        // Limits — blue dashed, differentiate BUY/SELL
        (data.smart_money_orders?.limits || []).forEach(o => {
          const isBuy = (o.side || "").toUpperCase() === "BUY";
          levels.push({
            price: o.price,
            color: isBuy ? "#60a5fa" : "#c084fc",
            style: LineStyle.Dashed,
            width: 1,
            title: `${isBuy ? "BUY" : "SELL"} LMT $${fmtSize(o.total_size_usd)}`,
          });
        });
        // Book walls — dotted, subtle
        (data.order_book_walls?.bid_walls || []).forEach(w => {
          levels.push({
            price: w.price, color: "#34d39950", style: LineStyle.Dotted, width: 1,
            title: `BID WALL $${fmtSize(w.size_usd)}`,
          });
        });
        (data.order_book_walls?.ask_walls || []).forEach(w => {
          levels.push({
            price: w.price, color: "#f8717150", style: LineStyle.Dotted, width: 1,
            title: `ASK WALL $${fmtSize(w.size_usd)}`,
          });
        });
        // Liquidation clusters — yellow dashed
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

          {/* Volume Profile toggle */}
          <button
            onClick={() => setShowVolumeProfile(p => !p)}
            title={showVolumeProfile ? "Hide volume profile" : "Show volume at price levels"}
            style={{
              padding: "3px 8px",
              borderRadius: 4,
              border: `1px solid ${showVolumeProfile ? "rgba(34,211,238,0.3)" : "rgba(255,255,255,0.08)"}`,
              cursor: "pointer",
              fontFamily: T.mono,
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "0.04em",
              transition: "all 0.15s ease",
              background: showVolumeProfile ? "rgba(34,211,238,0.12)" : "transparent",
              color: showVolumeProfile ? "#22d3ee" : "rgba(255,255,255,0.3)",
            }}
          >
            VP
          </button>

          {/* Timeframe toggle */}
          <div style={{
            display: "flex", gap: 2,
            background: "rgba(255,255,255,0.04)",
            borderRadius: 6, padding: 2,
          }}>
            {TIMEFRAMES.map((tf, idx) => (
              <button
                key={`${tf.label}-${idx}`}
                onClick={() => setActiveTfIdx(idx)}
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
                  background: activeTfIdx === idx
                    ? "rgba(34,211,238,0.15)"
                    : "transparent",
                  color: activeTfIdx === idx
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
