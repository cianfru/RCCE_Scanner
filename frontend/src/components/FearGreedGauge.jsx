import { T } from "../theme.js";

function gaugeColor(value) {
  if (value <= 25) return T.red;          // Extreme Fear
  if (value <= 45) return T.orange;       // Fear
  if (value <= 55) return T.yellow;       // Neutral
  if (value <= 75) return T.green;        // Greed
  return T.red;                           // Extreme Greed
}

function gaugeLabel(value) {
  if (value <= 25) return "Extreme Fear";
  if (value <= 45) return "Fear";
  if (value <= 55) return "Neutral";
  if (value <= 75) return "Greed";
  return "Extreme Greed";
}

export default function FearGreedGauge({ value }) {
  if (value == null) return null;

  const clamped = Math.max(0, Math.min(100, value));
  const color = gaugeColor(clamped);
  const label = gaugeLabel(clamped);

  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10,
      width: "100%",
    }}>
      {/* Label */}
      <span style={{
        fontSize: T.textSm, color: T.text3, letterSpacing: "0.08em",
        fontFamily: T.font, fontWeight: 600, textTransform: "uppercase",
        flexShrink: 0,
      }}>
        F&G
      </span>

      {/* Value number */}
      <span style={{
        fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700,
        color, minWidth: 22, textAlign: "right", flexShrink: 0,
      }}>
        {Math.round(clamped)}
      </span>

      {/* Horizontal bar */}
      <div style={{
        flex: 1, height: 5, background: T.overlay04,
        borderRadius: 2, overflow: "hidden", minWidth: 40,
      }}>
        <div style={{
          width: `${clamped}%`, height: "100%",
          background: `linear-gradient(90deg, ${color}88, ${color})`,
          borderRadius: 2,
          boxShadow: `0 0 8px ${color}30`,
          transition: "width 0.6s ease",
        }} />
      </div>

      {/* Sentiment label */}
      <span style={{
        fontSize: T.textXs, fontFamily: T.mono, fontWeight: 600,
        color, flexShrink: 0, letterSpacing: "0.04em",
      }}>
        {label}
      </span>
    </div>
  );
}
