/**
 * BridgeCorrelationChart — BTC price line with confirmed EXHAUSTION markers,
 * showing how the BTC × HL-bridge-flow divergence signal has actually called
 * turning points.
 *
 * Deliberately simple: one chart, one series, 14 days of data, mouse-wheel
 * zoomable. The previous multi-pane / multi-scale layouts were unreliable
 * across timeframes in lightweight-charts v5.1.0. The story the user wants
 * is "did the signal call the top?" — that's a BTC line with the event
 * markers on it. If we later want flow / divergence visible, they can go
 * back in as proven-working overlays.
 *
 * Powered by ``/api/hyperliquid/bridge/correlation`` requested at the max
 * retention window (14 days).
 */
import { useRef, useEffect, useState, useCallback } from "react";
import {
  createChart,
  AreaSeries,
  ColorType,
  LineStyle,
  CrosshairMode,
  createSeriesMarkers,
} from "lightweight-charts";
import { T } from "../theme.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const MAX_HOURS = 336; // 14 days — the snapshot retention limit

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

export default function BridgeCorrelationChart({ height = 440 }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // ── Fetch max-retention correlation data ──────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/api/hyperliquid/bridge/correlation?hours=${MAX_HOURS}`)
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
  }, []);

  // ── Build chart whenever data changes ─────────────────────────────────────
  const buildChart = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    if (!data || !data.rows || data.rows.length === 0) return;

    if (chartRef.current) {
      try { chartRef.current.remove(); } catch (_) { /* ignore */ }
      chartRef.current = null;
    }

    const width = container.clientWidth || 800;
    const chart = createChart(container, {
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
        rightOffset: 4,
      },
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.06)",
        scaleMargins: { top: 0.05, bottom: 0.08 },
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
    });
    chartRef.current = chart;

    // Build BTC series data defensively: v5's setData silently rejects the
    // whole call on duplicates, out-of-order points, or non-finite values.
    // That's almost certainly why we were seeing axes + last-value labels
    // but no visible line.
    const seen = new Set();
    const btcLineRaw = [];
    for (const r of data.rows) {
      const price = Number(r.btc_price);
      if (!Number.isFinite(price) || price <= 0) continue;
      const t = Math.floor(Number(r.ts));
      if (!Number.isFinite(t) || t <= 0) continue;
      if (seen.has(t)) continue;
      seen.add(t);
      btcLineRaw.push({ time: t, value: price });
    }
    const btcLine = btcLineRaw.sort((a, b) => a.time - b.time);

    // Use AreaSeries rather than LineSeries — the filled area is visible
    // even at very thin line widths, which rules out "line drawn but too
    // thin to see" as a failure mode.
    const btcSeries = chart.addSeries(AreaSeries, {
      lineColor: "#fbbf24",
      topColor: "rgba(251,191,36,0.28)",
      bottomColor: "rgba(251,191,36,0.02)",
      lineWidth: 2,
      lastValueVisible: true,
      priceLineVisible: false,
      priceFormat: { type: "price", precision: 0, minMove: 1 },
      title: "BTC/USDT",
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4,
    });

    try {
      btcSeries.setData(btcLine);
      // eslint-disable-next-line no-console
      console.info("[BridgeChart] setData ok", {
        points: btcLine.length,
        first: btcLine[0],
        last: btcLine[btcLine.length - 1],
      });
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error("[BridgeChart] setData FAILED", e, {
        sample: btcLine.slice(0, 3),
        length: btcLine.length,
      });
    }

    // Explicitly enable auto-scaling on the price axis so the Y range
    // snaps to actual data bounds.
    try { btcSeries.priceScale().applyOptions({ autoScale: true }); } catch (_) { /* ignore */ }

    // EXHAUSTION markers — red TOP arrows, cyan BTM arrows. Wrapped so an
    // API hiccup here can't break the base chart.
    if (data.events && data.events.length > 0) {
      try {
        const markers = data.events
          .filter((ev) => Number.isFinite(Number(ev.ts)))
          .map((ev) => {
            const isDist = ev.direction === "DIST";
            return {
              time: Math.floor(Number(ev.ts)),
              position: isDist ? "aboveBar" : "belowBar",
              color: isDist ? "#f87171" : "#22d3ee",
              shape: isDist ? "arrowDown" : "arrowUp",
              text: isDist ? "TOP" : "BTM",
            };
          });
        createSeriesMarkers(btcSeries, markers);
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error("[BridgeChart] markers failed", e);
      }
    }

    // Force visible range to span all data — fitContent alone proved
    // unreliable inside the modal. Applied twice (immediate + deferred) to
    // catch both the synchronous-ready and layout-pending cases.
    const allTimes = btcLine.map((p) => p.time);
    const dataFrom = allTimes.length ? allTimes[0] : null;
    const dataTo   = allTimes.length ? allTimes[allTimes.length - 1] : null;
    const applyRange = () => {
      if (!chartRef.current) return;
      try { chart.timeScale().fitContent(); } catch (_) { /* ignore */ }
      if (dataFrom && dataTo && dataTo > dataFrom) {
        try { chart.timeScale().setVisibleRange({ from: dataFrom, to: dataTo }); } catch (_) { /* ignore */ }
      }
    };
    applyRange();
    const rangeT = setTimeout(applyRange, 60);

    // Resize observer keeps the chart sized to container
    const ro = new ResizeObserver(() => {
      if (chartRef.current && containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(container);

    return () => {
      clearTimeout(rangeT);
      ro.disconnect();
    };
  }, [data, height]);

  useEffect(() => {
    let cleanup;
    const raf = requestAnimationFrame(() => { cleanup = buildChart(); });
    return () => {
      cancelAnimationFrame(raf);
      if (typeof cleanup === "function") cleanup();
      if (chartRef.current) {
        try { chartRef.current.remove(); } catch (_) { /* ignore */ }
        chartRef.current = null;
      }
    };
  }, [buildChart]);

  // ── Stats + diagnostics + availability hint ───────────────────────────────
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

  let availability = null;
  if (data && data.rows && data.rows.length > 0) {
    const firstSnapshot = data.rows[0]?.ts;
    const lastSnapshot  = data.rows[data.rows.length - 1]?.ts;
    const firstDivergence = data.rows.find((r) => r.divergence_score != null)?.ts;
    const spanHours = firstSnapshot && lastSnapshot
      ? Math.round((lastSnapshot - firstSnapshot) / 3600) : 0;
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
      spanHours,
      rowCount: data.rows.length,
    };
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12, width: "100%" }}>
      {/* Stats strip */}
      {stats && (
        <div style={{
          display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
          fontFamily: T.font, fontSize: 12, color: T.text3,
        }}>
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
        </div>
      )}

      {/* Availability hint */}
      {availability && availability.snapshotSince && (
        <div style={{
          fontFamily: T.font, fontSize: 10, color: T.text4,
          fontStyle: "italic",
        }}>
          Showing {availability.spanHours}h of history
          ({availability.rowCount} snapshots) since {availability.snapshotSince}
          {availability.hasDivergence && (
            <> · Divergence tracked since {availability.divergenceSince}</>
          )}
          <span style={{ marginLeft: 6, opacity: 0.7 }}>
            — scroll/drag to zoom, will extend to 14d as history accumulates
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
            no bridge snapshots yet — chart will populate as data accumulates.
          </div>
        )}
      </div>

      {/* Legend */}
      <div style={{
        fontFamily: T.font, fontSize: 11, color: T.text4, lineHeight: 1.5,
      }}>
        <span style={{ color: "#fbbf24" }}>━━</span> BTC/USDT ·{" "}
        <span style={{ color: "#f87171" }}>▼ TOP</span> /{" "}
        <span style={{ color: "#22d3ee" }}>▲ BTM</span> = confirmed EXHAUSTION events fired by the bridge × flow divergence signal
      </div>
    </div>
  );
}
