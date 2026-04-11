/**
 * CrossExchangePanel — side-by-side funding rate + open interest across
 * Binance, Bybit, and Hyperliquid for a given coin.
 *
 * Props:
 *   symbol — "BTC/USDT"
 *
 * Fetches /api/positioning/cross-exchange/{symbol} with 60s cache on the
 * backend. Refreshes when `symbol` changes.
 */
import { useState, useEffect } from "react";
import { T } from "../theme.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtUsd(v) {
  if (v == null || v === 0) return "\u2014";
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

function fundingColor(pct8h) {
  if (pct8h == null) return T.text4;
  if (pct8h >= 0.03)  return "#f87171";  // very crowded long
  if (pct8h >= 0.01)  return "#fbbf24";  // crowded long
  if (pct8h <= -0.03) return "#34d399";  // very crowded short
  if (pct8h <= -0.01) return "#a7f3d0";  // mild crowded short
  return T.text2;
}

// Brand tint per exchange (subtle accent on the row dot)
const EX_COLOR = {
  Binance:     "#f3ba2f",
  Bybit:       "#f7a600",
  Hyperliquid: "#22d3ee",
};

// ─── Row ─────────────────────────────────────────────────────────────────────

function ExchangeRow({ ex, maxOi }) {
  const available = ex.available;
  const dot = EX_COLOR[ex.name] || T.text4;
  const fundingPct = available ? ex.funding_rate_8h_pct : null;
  const fc = fundingColor(fundingPct);
  const oi = available ? ex.open_interest_usd : 0;
  const barPct = maxOi > 0 ? (oi / maxOi) * 100 : 0;

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "100px 1fr 110px",
      alignItems: "center",
      gap: 12,
      padding: "10px 12px",
      borderRadius: 8,
      background: T.overlay02,
      border: `1px solid ${T.overlay06}`,
      opacity: available ? 1 : 0.45,
    }}>
      {/* Name + dot */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        <span style={{
          width: 8, height: 8, borderRadius: "50%",
          background: dot, flexShrink: 0,
          boxShadow: available ? `0 0 6px ${dot}66` : "none",
        }} />
        <span style={{
          fontSize: T.textSm, fontFamily: T.mono,
          color: T.text1, fontWeight: 700, letterSpacing: "0.04em",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {ex.name}
        </span>
      </div>

      {/* OI bar */}
      <div style={{ minWidth: 0 }}>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          marginBottom: 4, gap: 8,
        }}>
          <span style={{
            fontSize: 9, fontFamily: T.mono, color: T.text4,
            letterSpacing: "0.08em", textTransform: "uppercase",
          }}>
            Open Interest
          </span>
          <span style={{
            fontSize: T.textXs, fontFamily: T.mono, color: T.text2, fontWeight: 700,
          }}>
            {available ? fmtUsd(oi) : "\u2014"}
          </span>
        </div>
        <div style={{
          position: "relative", height: 4, borderRadius: 2,
          background: T.overlay06, overflow: "hidden",
        }}>
          {available && (
            <div style={{
              position: "absolute", left: 0, top: 0, bottom: 0,
              width: `${barPct}%`,
              background: dot,
              transition: "width 0.4s ease",
            }} />
          )}
        </div>
      </div>

      {/* Funding */}
      <div style={{ textAlign: "right" }}>
        <div style={{
          fontSize: 9, fontFamily: T.mono, color: T.text4,
          letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 2,
        }}>
          Funding /8h
        </div>
        <div style={{
          fontSize: T.textSm, fontFamily: T.mono,
          color: fc, fontWeight: 700,
        }}>
          {fundingPct != null ? `${fundingPct >= 0 ? "+" : ""}${fundingPct.toFixed(4)}%` : "\u2014"}
        </div>
      </div>
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────

export default function CrossExchangePanel({ symbol }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    // Path-encode the slash in the symbol
    const safe = encodeURIComponent(symbol);
    fetch(`${API_BASE}/api/positioning/cross-exchange/${safe}`)
      .then(r => {
        if (!r.ok) throw new Error(`${r.status}`);
        return r.json();
      })
      .then(j => { if (!cancelled) setData(j); })
      .catch(e => { if (!cancelled) setError(e.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol]);

  if (error || (!loading && (!data || !data.exchanges))) return null;

  const exchanges = data?.exchanges || [];
  const live = exchanges.filter(e => e.available);
  const maxOi = live.reduce((m, e) => Math.max(m, e.open_interest_usd || 0), 0);

  // Spread summary
  const spreadBp = data?.funding_spread_bp || 0;
  const spreadColor = spreadBp >= 3 ? "#f87171" : spreadBp >= 1.5 ? "#fbbf24" : T.text3;
  const dominantOi = data?.dominant_oi;

  return (
    <div style={{
      background: T.glassBg,
      border: `1px solid ${T.border}`,
      borderRadius: T.radius,
      padding: 16,
      marginBottom: 14,
      backdropFilter: "blur(20px) saturate(1.3)",
      WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 12, paddingBottom: 10,
        borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            width: 3, height: 14, borderRadius: 2,
            background: T.accent, flexShrink: 0,
          }} />
          <span style={{
            fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em",
            fontFamily: T.font, fontWeight: 700, textTransform: "uppercase",
          }}>
            Cross-Exchange
          </span>
        </div>
        {live.length > 1 && (
          <span style={{
            fontSize: T.textXs, fontFamily: T.mono, color: spreadColor,
            fontWeight: 700, letterSpacing: "0.06em",
          }}>
            SPREAD {spreadBp.toFixed(2)}bp
          </span>
        )}
      </div>

      {loading && (
        <div style={{
          textAlign: "center", padding: "16px 0",
          fontSize: T.textSm, fontFamily: T.mono, color: T.text4,
        }}>
          Loading exchanges…
        </div>
      )}

      {!loading && exchanges.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {exchanges.map(ex => (
            <ExchangeRow key={ex.name} ex={ex} maxOi={maxOi} />
          ))}
        </div>
      )}

      {!loading && dominantOi && live.length > 1 && (
        <div style={{
          marginTop: 12, paddingTop: 10,
          borderTop: `1px solid ${T.overlay06}`,
          fontSize: T.textXs, fontFamily: T.mono, color: T.text4,
          letterSpacing: "0.04em",
        }}>
          Dominant OI: <span style={{ color: T.text2, fontWeight: 700 }}>{dominantOi}</span>
          {spreadBp >= 1.5 && (
            <span style={{ marginLeft: 10, color: spreadColor }}>
              · funding arb window open
            </span>
          )}
        </div>
      )}
    </div>
  );
}
