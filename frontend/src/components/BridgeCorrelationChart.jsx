/**
 * BridgeCorrelationChart — multi-pane time-series of BTC price vs HL bridge
 * net flow, plus the BTC × flow divergence score that drives the alert.
 *
 * Three vertically-stacked panes share a single time axis (TradingView-style):
 *   1. BTC price (line) with markers at confirmed EXHAUSTION events
 *   2. Bridge net flow (6h window) as a signed histogram (green up / red down)
 *   3. Divergence z-score line with ±1.5σ (DIVERGING) and ±2.5σ (EXHAUSTION)
 *      threshold bands
 *
 * Powered by ``/api/hyperliquid/bridge/correlation`` which returns one
 * fully time-aligned row per snapshot (10-min cadence). Defaults to 7 days,
 * adjustable up to 14 (the snapshot retention window).
 *
 * Backed by ``lightweight-charts`` v5 — same library as BMSBChart and the
 * HyperLens charts.
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
// Returns NaN if either array is too small or has zero variance.
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

function fmtUsd(v) {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : v > 0 ? "+" : "";
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

export default function BridgeCorrelationChart({ height = 540 }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
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

  // ── Build chart whenever data changes ─────────────────────────────────────
  const buildChart = useCallback(() => {
    if (!containerRef.current || !data || !data.rows || data.rows.length === 0) {
      return;
    }

    // Clean up previous chart
    if (chartRef.current) {
      try { chartRef.current.remove(); } catch (_) { /* ignore */ }
      chartRef.current = null;
    }

    const container = containerRef.current;
    // Inside a freshly-mounted modal the container can briefly report 0 width
    // before layout settles. Fall back to a sensible default so the chart
    // doesn't render collapsed; the ResizeObserver below will fix it once the
    // real width is known.
    const initialWidth = container.clientWidth || 800;
    const chart = createChart(container, {
      width: initialWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        // Bright label color for axis ticks — T.text3 was rendering almost
        // black against the dark modal background and was unreadable.
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
    });
    chartRef.current = chart;

    // Convert backend rows into chart points
    const rows = data.rows;
    const btcLine = rows
      .filter((r) => r.btc_price != null)
      .map((r) => ({ time: Math.floor(r.ts), value: r.btc_price }));
    const flowHist = rows.map((r) => ({
      time: Math.floor(r.ts),
      value: r.net_flow_6h,
      color: r.net_flow_6h >= 0 ? "rgba(52,211,153,0.55)" : "rgba(248,113,113,0.55)",
    }));
    const divLine = rows
      .filter((r) => r.divergence_score != null)
      .map((r) => ({ time: Math.floor(r.ts), value: r.divergence_score }));

    // ── Single-pane multi-scale layout ───────────────────────────────────
    // Three series share the same X-axis but each uses its own price scale,
    // positioned vertically via scaleMargins. This is the same proven
    // pattern BMSBChart uses (volume on its own scale at the bottom). It
    // avoids any moveToPane / pane-API quirks that were leaving series
    // crammed onto a single shared scale with incompatible magnitudes
    // (BTC ~75k vs flow ~$1M vs divergence ~3σ → BTC line goes flat at top,
    // divergence is invisible at zero, etc.).
    //
    // Vertical layout (top → bottom):
    //   BTC price       │ 0%  – 35% (default right scale)
    //   Bridge net flow │ 40% – 65% (priceScaleId: "flow")
    //   Divergence σ    │ 70% – 100% (priceScaleId: "divergence")

    // Configure scale margins BEFORE adding series — v5 needs the layout
    // intent set up first or the auto-scale picks the wrong region.
    chart.priceScale("right").applyOptions({
      scaleMargins: { top: 0.02, bottom: 0.65 },
      borderColor: "rgba(255,255,255,0.06)",
    });

    // BTC price (top region) — uses the default right scale
    const btcSeries = chart.addSeries(LineSeries, {
      color: "#fbbf24",
      lineWidth: 2,
      lastValueVisible: true,
      priceLineVisible: false,
      priceFormat: { type: "price", precision: 0, minMove: 1 },
      title: "BTC",
    });
    btcSeries.setData(btcLine);

    // EXHAUSTION markers on the BTC line — distribution = red flag down,
    // accumulation = cyan flag up. Helps eyeball whether the signal called
    // turning points on the price chart itself.
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
      try { createSeriesMarkers(btcSeries, markers); } catch (_) { /* v5 marker API */ }
    }

    // Bridge net flow (middle region) — own scale id "flow"
    const flowSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "flow",
      priceLineVisible: false,
      lastValueVisible: true,
      title: "Bridge 6h",
      base: 0,
    });
    chart.priceScale("flow").applyOptions({
      scaleMargins: { top: 0.40, bottom: 0.35 },
      borderColor: "rgba(255,255,255,0.06)",
      visible: true,
    });
    flowSeries.setData(flowHist);

    // Divergence score (bottom region) — own scale id "divergence"
    const divSeries = chart.addSeries(LineSeries, {
      color: "#a78bfa",
      lineWidth: 2,
      priceScaleId: "divergence",
      lastValueVisible: true,
      priceLineVisible: false,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      title: "Divergence σ",
    });
    chart.priceScale("divergence").applyOptions({
      scaleMargins: { top: 0.72, bottom: 0.02 },
      borderColor: "rgba(255,255,255,0.06)",
      visible: true,
    });
    divSeries.setData(divLine);

    // Threshold lines for visual reference (drawn on the divergence scale)
    [
      { value:  2.5, color: "rgba(248,113,113,0.4)", title: "+2.5σ EXHAUSTION" },
      { value:  1.5, color: "rgba(251,191,36,0.35)", title: "+1.5σ DIVERGING" },
      { value:  0.0, color: "rgba(255,255,255,0.18)" },
      { value: -1.5, color: "rgba(251,191,36,0.35)", title: "-1.5σ DIVERGING" },
      { value: -2.5, color: "rgba(34,211,238,0.4)",  title: "-2.5σ EXHAUSTION" },
    ].forEach((line) => {
      divSeries.createPriceLine({
        price: line.value,
        color: line.color,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: false,
        title: line.title || "",
      });
    });

    // Always fit content first — guarantees a sane default visible range
    // (this is what was working on every TF before auto-zoom was added).
    // Force the visible time range to cover all data. fitContent() alone
    // wasn't taking effect inside the modal — the chart was collapsing to
    // the latest moment so 137 points compressed into a 1px sliver at the
    // right edge (lines invisible). Computing the range from data.rows
    // directly and calling setVisibleRange explicitly is bulletproof.
    const allTimes = data.rows
      .map((r) => Math.floor(r.ts))
      .filter((t) => Number.isFinite(t) && t > 0);
    const dataFrom = allTimes.length ? Math.min(...allTimes) : null;
    const dataTo   = allTimes.length ? Math.max(...allTimes) : null;

    const applyRange = () => {
      if (!chartRef.current) return;
      try { chart.timeScale().fitContent(); } catch (_) { /* fallback */ }
      if (dataFrom && dataTo && dataTo > dataFrom) {
        try {
          chart.timeScale().setVisibleRange({ from: dataFrom, to: dataTo });
        } catch (_) { /* fitContent already ran */ }
      }
    };
    // Apply immediately, then again after layout settles. Two passes catch
    // both the synchronous-ready case and the layout-pending case.
    applyRange();
    const rangeTimeout = setTimeout(applyRange, 50);

    // Resize observer keeps the chart sized to container, and re-applies the
    // visible range on resize (chart sometimes loses the range when width
    // changes drastically e.g. during modal open animation).
    const ro = new ResizeObserver(() => {
      if (chartRef.current && containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
        applyRange();
      }
    });
    ro.observe(container);
    return () => {
      clearTimeout(rangeTimeout);
      ro.disconnect();
    };
  }, [data, height]);

  useEffect(() => {
    // Defer chart creation by a frame so a freshly-opened modal has settled
    // its layout (otherwise containerRef can report 0 width and the chart
    // renders collapsed).
    let cleanup;
    const raf = requestAnimationFrame(() => {
      cleanup = buildChart();
    });
    return () => {
      cancelAnimationFrame(raf);
      if (typeof cleanup === "function") cleanup();
      if (chartRef.current) {
        try { chartRef.current.remove(); } catch (_) { /* ignore */ }
        chartRef.current = null;
      }
    };
  }, [buildChart]);

  // ── Stat strip: pearson correlation + event count ─────────────────────────
  let stats = null;
  if (data && data.rows && data.rows.length >= 10) {
    const rows = data.rows.filter((r) => r.btc_price != null);
    // Pearson(BTC return, net flow 6h) over the visible window.
    // Returns over each interval rather than levels so we're correlating
    // changes, not absolute values (which would just track BTC's trend).
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

    // Strongest divergence by absolute score in the window
    let peak = null;
    for (const r of data.rows) {
      if (r.divergence_score == null) continue;
      if (!peak || Math.abs(r.divergence_score) > Math.abs(peak.divergence_score)) {
        peak = r;
      }
    }

    stats = { corr, eventCount, distEvents, accumEvents, peak };
  }

  // ── Diagnostic counts: how many points actually reach each series ────────
  // Helps tell "no data" from "data exists but chart isn't drawing".
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

  // ── "Data available since" hint ───────────────────────────────────────────
  // Figures out the earliest timestamp the chart actually has data for.
  // Two anchors: when bridge snapshots first started accumulating (sets the
  // BTC + flow line floor), and when the divergence engine had enough
  // baseline to compute scores. The latter is usually ~7d after the former.
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

      {/* Diagnostic counts — what's actually reaching each series */}
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

      {/* Data availability hint — explains why longer ranges may look sparse */}
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

      {/* Chart */}
      <div style={{ position: "relative", width: "100%", minHeight: height }}>
        <div ref={containerRef} style={{ width: "100%", height }} />
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

      {/* Legend / explainer */}
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
