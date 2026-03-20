import { useState, useEffect } from "react";
import { T, m, SIGNAL_META } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "";

// Signals worth showing (skip WAIT, REVIVAL_SEED variants)
const DISPLAY_ORDER = ["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "TRIM", "TRIM_HARD", "RISK_OFF"];

function rateColor(rate) {
  if (rate == null) return T.text4;
  if (rate >= 65) return "#34d399";
  if (rate >= 50) return T.text2;
  return "#f87171";
}

export default function HitRateStrip({ timeframe = "4h", isMobile }) {
  const [cards, setCards] = useState([]);

  useEffect(() => {
    fetch(`${API_BASE}/api/signals/scorecard?timeframe=${timeframe}`)
      .then(r => r.json())
      .then(d => setCards(d.cards || []))
      .catch(() => {});
  }, [timeframe]);

  // Filter to signals with enough data and map by signal name
  const bySignal = {};
  for (const c of cards) {
    if (c.total >= 3 && DISPLAY_ORDER.includes(c.signal)) {
      bySignal[c.signal] = c;
    }
  }

  const items = DISPLAY_ORDER.filter(s => bySignal[s]).map(s => bySignal[s]);
  if (items.length === 0) return null;

  return (
    <FadeIn delay={370}>
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: isMobile ? 6 : 8,
        flexWrap: "wrap",
        padding: isMobile ? "8px 0 4px" : "8px 0 4px",
      }}>
        <span style={{
          fontSize: m(T.textXs, isMobile),
          color: T.text4,
          fontFamily: T.mono,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          marginRight: 4,
        }}>Hit Rate</span>
        {items.map(c => {
          const meta = SIGNAL_META[c.signal] || SIGNAL_META.WAIT;
          const rate = c.win_rate;
          const color = rateColor(rate);
          return (
            <div key={c.signal} style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              padding: isMobile ? "4px 8px" : "3px 10px",
              borderRadius: 6,
              background: `${meta.color}08`,
              border: `1px solid ${meta.color}18`,
              fontSize: m(T.textXs, isMobile),
              fontFamily: T.mono,
              whiteSpace: "nowrap",
            }}>
              <span style={{ color: meta.color, fontWeight: 600 }}>
                {meta.label}
              </span>
              <span style={{ color, fontWeight: 700 }}>
                {rate != null ? `${rate}%` : "—"}
              </span>
              <span style={{ color: T.text4, fontSize: "0.85em" }}>
                ({c.total})
              </span>
            </div>
          );
        })}
      </div>
    </FadeIn>
  );
}
