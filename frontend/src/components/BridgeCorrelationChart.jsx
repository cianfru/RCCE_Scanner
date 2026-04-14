/**
 * BridgeCorrelationChart — three vertically-stacked charts of BTC price vs HL
 * bridge net flow vs the BTC × flow divergence score that drives the alert.
 *
 *   1. BTC price (line) with markers at confirmed EXHAUSTION events
 *   2. Bridge net flow (6h window) as a signed histogram (green up / red down)
 *   3. Divergence z-score line with ±1.5σ (DIVERGING) and ±2.5σ (EXHAUSTION)
 *      threshold bands
 *
 * Each is its own independent `lightweight-charts` instance — sharing one
 * chart with multi-pane / multi-scale was unreliable across timeframes in
 * v5.1.0 (worked for 1D, broke silently for 3D / 7D / 14D). Three separate
 * charts removes every shared-scale / shared-pane failure mode at once. The
 * three time scales are synchronized via subscribeVisibleTimeRangeChange so
 * panning or zooming any one chart moves the others in lockstep.
 *
 * Powered by ``/api/hyperliquid/bridge/correlation``.
 */
import { useRef, useEffect, useState, useCallback } from "react";
import {
  createChart,
  LineSeries,
  HistogramSeries,
  ColorType,
  LineStyle,
  CrosshairMode,
  createSeriesMarkers,
} from "lightweight-charts";
import { T } from "../theme.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const RANGE_OPTIONS = [
  { hours: 24,  label: "1D" },
  { hours: 72,  label: "3D" },
  { hours: 168, label: "7D" },
  { hours: 336, label: "14D" },
];

// Pearson correlation between two equal-length numeric arrays.
function pearson(xs, ys) {
  const n = Math.min(xs.length, ys.length);
  if (n < 5) return NaN;
  let sx = 0, sy = 0;
  for (let i = 0; i < n; i++) { sx += xs[i]; sy += ys[i]; }
  const mx = sx / n, my = sy / n;
  let num = 0, dx = 0, dy = 0;
  for (let i = 0; i < n; i++) {
    const a = xs[i] - mx, b = ys[i] - my;
    num += a * b; dx += a * a; dy += b * b;
  }
  if (dx <= 0 || dy <= 0) return NaN;
  return num / Math.sqrt(dx * dy);
}

// Shared base config for each of the three sub-charts. Keeps them visually
// consistent and reduces duplication.
function baseChartOptions(width, height) {
  return {
    width,
    height,
    layout: {
      background: { type: ColorType.Solid, color: "transparent" },
      textColor: "#d1d5db",
      fontFamily: "'SF Mono', 'Fira Code', monospace",
      fontSize: 10,
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: "rgba(255,255,255,0.025)" },
      horzLines: { color: "rgba(255,255,255,0.025)" },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: "rgba(34,211,238,0.18)", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#1a1a1e" },
      horzLine: { color: "rgba(34,211,238,0.18)", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#1a1a1e" },
    },
    timeScale: {
      borderColor: "rgba(255,255,255,0.06)",
      timeVisible: true,
      secondsVisible: false,
    },
    rightPriceScale: { borderColor: "rgba(255,255,255,0.06)" },
  };
}

export default function BridgeCorrelationChart({ height = 540 }) {
  const wrapperRef = useRef(null);
  const btcContainerRef = useRef(null);
  const flowContainerRef = useRef(null);
  const divContainerRef = useRef(null);
  const chartsRef = useRef({ btc: null, flow: null, div: null });

  const [hours, setHours] = useState(168);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // ── Data fetch ─────────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/api/hyperliquid/bridge/correlation?hours=${hours}`)
      .then((r) => r.json())
      .then((j) => {
        if (cancelled) return;
        setData(j);
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e));
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [hours]);

  // ── Build all three charts whenever data changes ──────────────────────────
  const buildCharts = useCallback(() => {
    const wrap = wrapperRef.current;
    const btcEl = btcContainerRef.current;
    const flowEl = flowContainerRef.current;
    const divEl = divContainerRef.current;
    if (!wrap || !btcEl || !flowEl || !divEl) return;
    if (!data || !data.rows || data.rows.length === 0) return;

    // Tear down any previous charts
    Object.values(chartsRef.current).forEach((c) => {
      if (c) { try { c.remove(); } catch (_) { /* ignore */ } }
    });
    chartsRef.current = { btc: null, flow: null, div: null };

    // Each chart gets ~1/3 of the wrapper height. Width is wrapper width
    // (with sensible fallback so we never init at 0 inside the modal).
    const totalH = height;
    const each = Math.floor((totalH - 8) / 3); // 8px gap budget
    const w = wrap.clientWidth || 800;

    // Series data
    const rows = data.rows;
    const btcLine = rows
      .filter((r) => r.btc_price != null)
      .map((r) => ({ time: Math.floor(r.ts), value: r.btc_price }));
    const flowHist = rows.map((r) => ({
      time: Math.floor(r.ts),
      value: r.net_flow_6h,
      color: r.net_flow_6h >= 0 ? "rgba(52,211,153,0.65)" : "rgba(248,113,113,0.65)",
    }));
    const divLine = rows
      .filter((r) => r.divergence_score != null)
      .map((r) => ({ time: Math.floor(r.ts), value: r.divergence_score }));

    // ── Chart 1: BTC ─────────────────────────────────────────────────────
    const btcChart = createChart(btcEl, baseChartOptions(w, each));
    chartsRef.current.btc = btcChart;
    const btcSeries = btcChart.addSeries(LineSeries, {
      color: "#fbbf24",
      lineWidth: 2,
      lastValueVisible: true,
      priceLineVisible: false,
      priceFormat: { type: "price", precision: 0, minMove: 1 },
      title: "BTC",
    });
    btcSeries.setData(btcLine);

    // EXHAUSTION markers on BTC (red TOP arrows, cyan BTM arrows)
    if (data.events && data.events.length > 0) {
      const markers = data.events.map((ev) => {
        const isDist = ev.direction === "DIST";
        return {
          time: Math.floor(ev.ts),
          position: isDist ? "aboveBar" : "belowBar",
          color: isDist ? "#f87171" : "#22d3ee",
          shape: isDist ? "arrowDown" : "arrowUp",
          text: isDist ? "TOP" : "BTM",
        };
      });
      try { createSeriesMarkers(btcSeries, markers); } catch (_) { /* v5 */ }
    }

    // ── Chart 2: Bridge flow histogram ───────────────────────────────────
    const flowChart = createChart(flowEl, baseChartOptions(w, each));
    chartsRef.current.flow = flowChart;
    const flowSeries = flowChart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceLineVisible: false,
      lastValueVisible: true,
      title: "Bridge net flow (6h)",
      base: 0,
    });
    flowSeries.setData(flowHist);

    // ── Chart 3: Divergence σ ────────────────────────────────────────────
    const divChart = createChart(divEl, baseChartOptions(w, each));
    chartsRef.current.div = divChart;
    const divSeries = divChart.addSeries(LineSeries, {
      color: "#a78bfa",
      lineWidth: 2,
      lastValueVisible: true,
      priceLineVisible: false,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      title: "Divergence σ",
    });
    divSeries.setData(divLine);

    // Threshold bands at ±1.5σ and ±2.5σ + the zero line
    [
      { value:  2.5, color: "rgba(248,113,113,0.5)" },
      { value:  1.5, color: "rgba(251,191,36,0.4)" },
      { value:  0.0, color: "rgba(255,255,255,0.18)" },
      { value: -1.5, color: "rgba(251,191,36,0.4)" },
      { value: -2.5, color: "rgba(34,211,238,0.5)" },
    ].forEach((line) => {
      divSeries.createPriceLine({
        price: line.value,
        color: line.color,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: false,
      });
    });

    // ── Time-scale synchronization ───────────────────────────────────────
    // Pan or zoom in any chart → mirror the visible range to the other two.
    // A guard flag prevents recursive callbacks ping-ponging forever.
    let syncing = false;
    const sync = (sourceChart) => (range) => {
      if (syncing || !range) return;
      syncing = true;
      try {
        Object.values(chartsRef.current).forEach((c) => {
          if (c && c !== sourceChart) {
            try { c.timeScale().setVisibleRange(range); } catch (_) { /* ignore */ }
          }
        });
      } finally { syncing = false; }
    };
    btcChart.timeScale().subscribeVisibleTimeRangeChange(sync(btcChart));
    flowChart.timeScale().subscribeVisibleTimeRangeChange(sync(flowChart));
    divChart.timeScale().subscribeVisibleTimeRangeChange(sync(divChart));

    // ── Initial visible range: span all data ─────────────────────────────
    // Compute once from the rows array (most reliable source of truth) and
    // apply to all three. Defer briefly so the layout is settled.
    const allTimes = rows
      .map((r) => Math.floor(r.ts))
      .filter((t) => Number.isFinite(t) && t > 0);
    const dataFrom = allTimes.length ? Math.min(...allTimes) : null;
    const dataTo   = allTimes.length ? Math.max(...allTimes) : null;
    const applyRange = () => {
      if (!chartsRef.current.btc) return;
      Object.values(chartsRef.current).forEach((c) => {
        if (!c) return;
        try { c.timeScale().fitContent(); } catch (_) { /* ignore */ }
        if (dataFrom && dataTo && dataTo > dataFrom) {
          try { c.timeScale().setVisibleRange({ from: dataFrom, to: dataTo }); } catch (_) { /* ignore */ }
        }
      });
    };
    applyRange();
    const rangeT = setTimeout(applyRange, 60);

    // ── Resize observer keeps all three sized to the wrapper ────────────
    const ro = new ResizeObserver(() => {
      const newW = wrap.clientWidth;
      Object.values(chartsRef.current).forEach((c) => {
        if (c) { try { c.applyOptions({ width: newW }); } catch (_) { /* ignore */ } }
      });
      applyRange();
    });
    ro.observe(wrap);

    return () => {
      clearTimeout(rangeT);
      ro.disconnect();
    };
  }, [data, height]);

  useEffect(() => {
    let cleanup;
    const raf = requestAnimationFrame(() => {
      cleanup = buildCharts();
    });
    return () => {
      cancelAnimationFrame(raf);
      if (typeof cleanup === "function") cleanup();
      Object.values(chartsRef.current).forEach((c) => {
        if (c) { try { c.remove(); } catch (_) { /* ignore */ } }
      });
      chartsRef.current = { btc: null, flow: null, div: null };
    };
  }, [buildCharts]);

  // ── Stat strip + diagnostics + availability ───────────────────────────────
  let stats = null;
  if (data && data.rows && data.rows.length >= 10) {
    const rows = data.rows.filter((r) => r.btc_price != null);
    const btcReturns = [];
    const flows = [];
    for (let i = 1; i < rows.length; i++) {
      const r0 = rows[i - 1].btc_price;
      const r1 = rows[i].btc_price;
      if (r0 > 0 && r1 > 0) {
        btcReturns.push((r1 / r0) - 1);
        flows.push(rows[i].net_flow_6h);
      }
    }
    const corr = pearson(btcReturns, flows);
    const eventCount = (data.events || []).length;
    const distEvents = (data.events || []).filter((e) => e.direction === "DIST").length;
    const accumEvents = (data.events || []).filter((e) => e.direction === "ACCUM").length;
    let peak = null;
    for (const r of data.rows) {
      if (r.divergence_score == null) continue;
      if (!peak || Math.abs(r.divergence_score) > Math.abs(peak.divergence_score)) {
        peak = r;
      }
    }
    stats = { corr, eventCount, distEvents, accumEvents, peak };
  }

  let diag = null;
  if (data && data.rows) {
    const rows = data.rows;
    diag = {
      total: rows.length,
      btcPts: rows.filter((r) => r.btc_price != null).length,
      flowPts: rows.length,
      divPts: rows.filter((r) => r.divergence_score != null).length,
      events: (data.events || []).length,
    };
  }

  let availability = null;
  if (data && data.rows && data.rows.length > 0) {
    const firstSnapshot = data.rows[0]?.ts;
    const firstDivergence = data.rows.find((r) => r.divergence_score != null)?.ts;
    const fmt = (ts) => {
      if (!ts) return null;
      const d = new Date(ts * 1000);
      return d.toLocaleString(undefined, {
        year: "numeric", month: "short", day: "2-digit",
        hour: "2-digit", minute: "2-digit",
      });
    };
    availability = {
      snapshotSince: fmt(firstSnapshot),
      divergenceSince: fmt(firstDivergence),
      hasDivergence: firstDivergence != null,
    };
  }

  const each = Math.floor((height - 8) / 3);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, width: "100%" }}>
      {/* Controls + stats */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
        fontFamily: T.font, fontSize: 12, color: T.text3,
      }}>
        <div style={{ display: "flex", gap: 6 }}>
          {RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.hours}
              onClick={() => setHours(opt.hours)}
              style={{
                padding: "4px 10px",
                borderRadius: 6,
                border: `1px solid ${hours === opt.hours ? T.text3 : T.border}`,
                background: hours === opt.hours ? "rgba(255,255,255,0.05)" : "transparent",
                color: hours === opt.hours ? T.text1 : T.text3,
                fontFamily: T.mono, fontSize: 11, fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {stats && (
          <>
            <span style={{ width: 1, height: 16, background: T.border }} />
            <span>
              <span style={{ color: T.text4 }}>Corr (Δ BTC vs flow):</span>{" "}
              <span style={{
                fontFamily: T.mono, fontWeight: 700,
                color: !isNaN(stats.corr) && Math.abs(stats.corr) > 0.2
                  ? (stats.corr > 0 ? "#34d399" : "#f87171")
                  : T.text2,
              }}>
                {isNaN(stats.corr) ? "—" : stats.corr.toFixed(2)}
              </span>
            </span>
            <span style={{ color: T.text4 }}>·</span>
            <span>
              <span style={{ color: T.text4 }}>EXH events:</span>{" "}
              <span style={{ fontFamily: T.mono, fontWeight: 700, color: T.text1 }}>
                {stats.eventCount}
              </span>
              {stats.eventCount > 0 && (
                <span style={{ color: T.text4, marginLeft: 4 }}>
                  ({stats.distEvents} top, {stats.accumEvents} btm)
                </span>
              )}
            </span>
            {stats.peak && stats.peak.divergence_score != null && (
              <>
                <span style={{ color: T.text4 }}>·</span>
                <span>
                  <span style={{ color: T.text4 }}>Peak σ:</span>{" "}
                  <span style={{
                    fontFamily: T.mono, fontWeight: 700,
                    color: stats.peak.divergence_score > 0 ? "#f87171" : "#22d3ee",
                  }}>
                    {stats.peak.divergence_score >= 0 ? "+" : ""}
                    {stats.peak.divergence_score.toFixed(1)}σ
                  </span>
                </span>
              </>
            )}
          </>
        )}
      </div>

      {/* Diagnostic counts */}
      {diag && (
        <div style={{
          fontFamily: T.mono, fontSize: 10, color: T.text3,
          marginTop: -4,
          display: "flex", gap: 12, flexWrap: "wrap",
        }}>
          <span>rows: <b style={{ color: T.text1 }}>{diag.total}</b></span>
          <span>BTC pts: <b style={{ color: diag.btcPts > 0 ? "#fbbf24" : "#f87171" }}>{diag.btcPts}</b></span>
          <span>Flow bars: <b style={{ color: diag.flowPts > 0 ? "#34d399" : "#f87171" }}>{diag.flowPts}</b></span>
          <span>Divergence pts: <b style={{ color: diag.divPts > 0 ? "#a78bfa" : T.text4 }}>{diag.divPts}</b></span>
          <span>Events: <b style={{ color: T.text1 }}>{diag.events}</b></span>
        </div>
      )}

      {/* Availability hint */}
      {availability && availability.snapshotSince && (
        <div style={{
          fontFamily: T.font, fontSize: 10, color: T.text4,
          fontStyle: "italic",
          marginTop: -4,
        }}>
          Bridge snapshots since {availability.snapshotSince}
          {availability.hasDivergence && (
            <> · Divergence available since {availability.divergenceSince}</>
          )}
          {!availability.hasDivergence && (
            <> · Divergence engine still warming up (needs 7d of baseline)</>
          )}
          <span style={{ marginLeft: 6, opacity: 0.7 }}>
            — longer ranges fill out as history accumulates
          </span>
        </div>
      )}

      {/* Three stacked chart containers */}
      <div ref={wrapperRef} style={{ position: "relative", width: "100%" }}>
        <div ref={btcContainerRef}  style={{ width: "100%", height: each, marginBottom: 4 }} />
        <div ref={flowContainerRef} style={{ width: "100%", height: each, marginBottom: 4 }} />
        <div ref={divContainerRef}  style={{ width: "100%", height: each }} />
        {loading && (
          <div style={{
            position: "absolute", inset: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: T.text3, fontFamily: T.mono, fontSize: 11,
            background: "rgba(0,0,0,0.3)",
          }}>
            loading correlation series…
          </div>
        )}
        {error && (
          <div style={{
            position: "absolute", inset: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "#f87171", fontFamily: T.mono, fontSize: 12,
          }}>
            failed to load: {error}
          </div>
        )}
        {data && data.rows && data.rows.length === 0 && !loading && !error && (
          <div style={{
            position: "absolute", inset: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: T.text4, fontFamily: T.mono, fontSize: 11, textAlign: "center",
          }}>
            no correlation data yet — bridge history needs to grow past the<br />
            7d divergence baseline before a chart can be drawn.
          </div>
        )}
      </div>

      {/* Legend */}
      <div style={{
        fontFamily: T.font, fontSize: 11, color: T.text4, lineHeight: 1.5,
      }}>
        <span style={{ color: "#fbbf24" }}>━━</span> BTC/USDT ·{" "}
        <span style={{ color: "rgba(52,211,153,0.8)" }}>▮</span> bridge inflow ·{" "}
        <span style={{ color: "rgba(248,113,113,0.8)" }}>▮</span> bridge outflow ·{" "}
        <span style={{ color: "#a78bfa" }}>━━</span> divergence σ ·{" "}
        <span style={{ color: "#f87171" }}>▼ TOP</span> /{" "}
        <span style={{ color: "#22d3ee" }}>▲ BTM</span> = confirmed EXHAUSTION events
      </div>
    </div>
  );
}
