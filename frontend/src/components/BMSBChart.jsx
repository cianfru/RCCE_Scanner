import { useRef, useEffect, useState } from "react";
import { createChart, CandlestickSeries, LineSeries, ColorType } from "lightweight-charts";
import { T, REGIME_META, SIGNAL_META, heatColor, resolveToken } from "../theme.js";

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

export default function BMSBChart({
  symbol,
  timeframe = "1d",
  height = 300,
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
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
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: resolveToken("chartGrid") },
        horzLines: { color: resolveToken("chartGrid") },
      },
      crosshair: {
        vertLine: { color: resolveToken("chartCross"), labelBackgroundColor: resolveToken("chartLabel") },
        horzLine: { color: resolveToken("chartCross"), labelBackgroundColor: resolveToken("chartLabel") },
      },
      timeScale: {
        borderColor: resolveToken("chartGrid"),
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: resolveToken("chartGrid"),
      },
    });
    chartRef.current = chart;

    // v5 API: chart.addSeries(SeriesType, options)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#34d399",
      downColor: "#f87171",
      borderUpColor: "#34d399",
      borderDownColor: "#f87171",
      wickUpColor: "rgba(52,211,153,0.5)",
      wickDownColor: "rgba(248,113,113,0.5)",
    });

    const bmsbMidSeries = chart.addSeries(LineSeries, {
      color: "#22d3ee",
      lineWidth: 2,
      lineStyle: 0,
      crosshairMarkerVisible: false,
      title: "BMSB",
    });

    const bmsbEmaSeries = chart.addSeries(LineSeries, {
      color: "rgba(34,211,238,0.30)",
      lineWidth: 1,
      lineStyle: 2,
      crosshairMarkerVisible: false,
    });

    const bmsbSmaSeries = chart.addSeries(LineSeries, {
      color: "rgba(34,211,238,0.20)",
      lineWidth: 1,
      lineStyle: 2,
      crosshairMarkerVisible: false,
    });

    // Fetch data
    const encoded = encodeURIComponent(symbol);
    setLoading(true);
    setError(null);

    fetch(`${API_BASE}/api/chart/${encoded}?timeframe=${timeframe}&limit=150`)
      .then(r => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then(data => {
        if (cancelled) return;
        if (data.candles?.length > 0) {
          candleSeries.setData(data.candles);

          // ── Signal marker on latest candle ──
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

            // Add exhaustion/floor markers too
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

            // Sort markers by time (required by lightweight-charts)
            markers.sort((a, b) => a.time - b.time);
            candleSeries.setMarkers(markers);
          }

          // ── BMSB mid price line ──
          if (data.bmsb_mid?.length > 0) {
            const lastMid = data.bmsb_mid[data.bmsb_mid.length - 1].value;
            candleSeries.createPriceLine({
              price: lastMid,
              color: "rgba(34,211,238,0.35)",
              lineWidth: 1,
              lineStyle: 2,
              axisLabelVisible: true,
              title: "",
            });
          }
        }

        if (data.bmsb_mid?.length > 0) bmsbMidSeries.setData(data.bmsb_mid);
        if (data.bmsb_ema?.length > 0) bmsbEmaSeries.setData(data.bmsb_ema);
        if (data.bmsb_sma?.length > 0) bmsbSmaSeries.setData(data.bmsb_sma);
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
  }, [symbol, timeframe, height, signal, regime, exhaustionState, floorConfirmed]);

  // ── Info strip data ──
  const rm = regime ? REGIME_META[regime] || REGIME_META.FLAT : null;
  const sm = signal ? SIGNAL_META[signal] || SIGNAL_META.WAIT : null;
  const hColor = heatColor(heat);
  const momColor = momentum != null ? (momentum >= 0 ? "#34d399" : "#f87171") : null;

  return (
    <div style={{
      width: "100%",
      borderRadius: T.radiusSm,
      overflow: "hidden",
      border: `1px solid ${T.border}`,
      background: T.surface,
      marginBottom: 14,
      position: "relative",
    }}>
      {/* Signal info strip */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, zIndex: 5,
        display: "flex", alignItems: "center", gap: 6,
        padding: "6px 10px",
        background: "linear-gradient(180deg, rgba(10,10,12,0.85) 0%, rgba(10,10,12,0.4) 70%, transparent 100%)",
        flexWrap: "wrap",
      }}>
        {/* Timeframe */}
        <span style={{
          fontSize: 9, fontFamily: T.mono, fontWeight: 600,
          color: T.text4, letterSpacing: "0.08em",
        }}>
          {timeframe.toUpperCase()}
        </span>

        {/* Regime pill */}
        {rm && (
          <span style={{
            padding: "2px 8px", borderRadius: "12px",
            background: rm.bg, color: rm.color,
            fontSize: 9, fontFamily: T.mono, fontWeight: 700,
            letterSpacing: "0.04em",
            border: `1px solid ${rm.color}25`,
            display: "inline-flex", alignItems: "center", gap: 3,
          }}>
            <span style={{ fontSize: 8 }}>{rm.glyph}</span>
            {rm.label}
          </span>
        )}

        {/* Signal pill */}
        {sm && signal !== "WAIT" && (
          <span style={{
            padding: "2px 8px", borderRadius: "12px",
            background: `${sm.color}15`, color: sm.color,
            fontSize: 9, fontFamily: T.mono, fontWeight: 700,
            letterSpacing: "0.04em",
            border: `1px solid ${sm.color}25`,
            display: "inline-flex", alignItems: "center", gap: 3,
          }}>
            <span style={{ fontSize: 7 }}>{sm.dot}</span>
            {sm.label}
          </span>
        )}

        {/* Conditions */}
        {conditions != null && conditionsTotal != null && (
          <span style={{
            fontSize: 9, fontFamily: T.mono, fontWeight: 700,
            color: conditions >= 8 ? "#34d399" : conditions >= 5 ? "#fbbf24" : T.text4,
          }}>
            {conditions}/{conditionsTotal}
          </span>
        )}

        {/* Heat */}
        {heat != null && (
          <span style={{
            fontSize: 9, fontFamily: T.mono, fontWeight: 700,
            color: hColor,
          }}>
            H:{Math.round(heat)}
          </span>
        )}

        {/* Momentum */}
        {momentum != null && (
          <span style={{
            fontSize: 9, fontFamily: T.mono, fontWeight: 600,
            color: momColor,
          }}>
            {momentum >= 0 ? "+" : ""}{momentum.toFixed(1)}%
          </span>
        )}

        {/* Confidence */}
        {signalConfidence != null && signal !== "WAIT" && (
          <span style={{
            fontSize: 8, fontFamily: T.mono, fontWeight: 500,
            color: signalConfidence >= 0.8 ? "#34d399" : signalConfidence >= 0.5 ? "#fbbf24" : T.text4,
            opacity: 0.7,
          }}>
            {Math.round(signalConfidence * 100)}%
          </span>
        )}
      </div>

      {loading && (
        <div style={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "rgba(9,9,11,0.7)", zIndex: 10,
          color: T.text4, fontFamily: T.mono, fontSize: 10,
        }}>
          Loading chart...
        </div>
      )}
      {error && !loading && (
        <div style={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: T.surface, zIndex: 10,
          color: "#f87171", fontFamily: T.mono, fontSize: 10,
        }}>
          Chart unavailable ({error})
        </div>
      )}
      <div ref={containerRef} style={{ width: "100%", height }} />
    </div>
  );
}
