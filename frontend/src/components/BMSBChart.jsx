import { useRef, useEffect, useState } from "react";
import { createChart, CandlestickSeries, LineSeries, ColorType } from "lightweight-charts";
import { T } from "../theme.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function BMSBChart({ symbol, timeframe = "1d", height = 300 }) {
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
        textColor: T.text3,
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.03)" },
        horzLines: { color: "rgba(255,255,255,0.03)" },
      },
      crosshair: {
        vertLine: { color: "rgba(34,211,238,0.3)", labelBackgroundColor: "#1a1a1a" },
        horzLine: { color: "rgba(34,211,238,0.3)", labelBackgroundColor: "#1a1a1a" },
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.06)",
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.06)",
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
        if (data.candles?.length > 0) candleSeries.setData(data.candles);
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
  }, [symbol, timeframe, height]);

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
      {/* Timeframe label */}
      <div style={{
        position: "absolute", top: 8, left: 12, zIndex: 5,
        fontSize: 9, fontFamily: T.mono, fontWeight: 600,
        color: T.text4, letterSpacing: "0.08em",
      }}>
        {timeframe.toUpperCase()} + BMSB
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
