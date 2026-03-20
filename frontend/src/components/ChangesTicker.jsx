import { useState, useEffect } from "react";
import { T, m, SIGNAL_META, REGIME_META, TRANSITION_META } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

const API_BASE = "";

function timeAgo(ts) {
  if (!ts) return "";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return `${Math.round(diff)}s`;
  if (diff < 3600) return `${Math.round(diff / 60)}m`;
  if (diff < 86400) return `${(diff / 3600).toFixed(0)}h`;
  return `${(diff / 86400).toFixed(0)}d`;
}

function chipColor(event) {
  if (event.event_type === "regime") {
    const meta = REGIME_META[event.current] || REGIME_META.FLAT;
    return meta.color;
  }
  const tt = event.transition_type || "LATERAL";
  const meta = TRANSITION_META[tt] || TRANSITION_META.LATERAL;
  return meta.color;
}

function chipGlyph(event) {
  if (event.event_type === "regime") return "\u25c6";
  const tt = event.transition_type || "LATERAL";
  const meta = TRANSITION_META[tt] || TRANSITION_META.LATERAL;
  return meta.glyph;
}

function formatValue(val, eventType) {
  if (!val) return "—";
  if (eventType === "signal") {
    const meta = SIGNAL_META[val];
    return meta ? meta.label : val;
  }
  return val;
}

export default function ChangesTicker({ timeframe = "4h", isMobile, refreshKey }) {
  const [events, setEvents] = useState([]);

  useEffect(() => {
    fetch(`${API_BASE}/api/signals/recent-unified?timeframe=${timeframe}&limit=12`)
      .then(r => r.json())
      .then(d => setEvents(d.events || []))
      .catch(() => {});
  }, [timeframe, refreshKey]);

  if (events.length === 0) return null;

  return (
    <FadeIn delay={440}>
      <GlassCard style={{
        padding: isMobile ? "8px 10px" : "8px 14px",
        marginTop: isMobile ? 8 : 10,
        marginBottom: 2,
      }}>
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          overflowX: "auto",
          WebkitOverflowScrolling: "touch",
          scrollbarWidth: "none",
          msOverflowStyle: "none",
        }} className="notable-scroll">
          {/* Label */}
          <span style={{
            fontSize: m(T.textXs, isMobile),
            color: T.text4,
            fontFamily: T.mono,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            whiteSpace: "nowrap",
            flexShrink: 0,
          }}>CHANGED</span>

          {events.map((ev, i) => {
            const color = chipColor(ev);
            const glyph = chipGlyph(ev);
            const symbol = (ev.symbol || "").replace("/USDT", "").replace("/USD", "");
            const ago = timeAgo(ev.timestamp);
            const isRegime = ev.event_type === "regime";

            return (
              <div key={`${ev.symbol}-${ev.timestamp}-${i}`} style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: isMobile ? "4px 7px" : "3px 8px",
                borderRadius: 6,
                background: `${color}0a`,
                border: `1px solid ${color}18`,
                fontSize: m(T.textXs, isMobile),
                fontFamily: T.mono,
                whiteSpace: "nowrap",
                flexShrink: 0,
              }}>
                <span style={{ color, fontSize: "0.9em" }}>{glyph}</span>
                <span style={{ color: T.text2, fontWeight: 600 }}>{symbol}</span>
                <span style={{ color: T.text4 }}>
                  {formatValue(ev.prev, ev.event_type)}
                </span>
                <span style={{ color: T.text4, fontSize: "0.8em" }}>\u2192</span>
                <span style={{ color, fontWeight: 600 }}>
                  {formatValue(ev.current, ev.event_type)}
                </span>
                {ago && (
                  <span style={{ color: T.text4, fontSize: "0.8em", marginLeft: 1 }}>
                    {ago}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </GlassCard>
    </FadeIn>
  );
}
