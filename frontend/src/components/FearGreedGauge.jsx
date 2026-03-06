import { T } from "../theme.js";

function gaugeColor(value) {
  if (value <= 25) return "#f87171";      // Extreme Fear - red
  if (value <= 45) return "#fb923c";      // Fear - orange
  if (value <= 55) return "#facc15";      // Neutral - yellow
  if (value <= 75) return "#34d399";      // Greed - green
  return "#f87171";                        // Extreme Greed - red
}

export default function FearGreedGauge({ value, label }) {
  if (value == null) return null;

  const clamped = Math.max(0, Math.min(100, value));
  const color = gaugeColor(clamped);

  // SVG arc dimensions
  const cx = 50;
  const cy = 48;
  const r = 38;
  const strokeWidth = 6;

  // Arc from 180deg to 0deg (left to right, semi-circle)
  const startAngle = Math.PI;          // 180 degrees
  const endAngle = 0;                  // 0 degrees
  const sweepAngle = startAngle - (clamped / 100) * Math.PI;

  // Background arc path (full semi-circle)
  const bgX1 = cx + r * Math.cos(startAngle);
  const bgY1 = cy - r * Math.sin(startAngle);
  const bgX2 = cx + r * Math.cos(endAngle);
  const bgY2 = cy - r * Math.sin(endAngle);
  const bgPath = `M ${bgX1} ${bgY1} A ${r} ${r} 0 0 1 ${bgX2} ${bgY2}`;

  // Value arc path
  const valX1 = cx + r * Math.cos(startAngle);
  const valY1 = cy - r * Math.sin(startAngle);
  const valX2 = cx + r * Math.cos(sweepAngle);
  const valY2 = cy - r * Math.sin(sweepAngle);
  const largeArc = clamped > 50 ? 1 : 0;
  const valPath = `M ${valX1} ${valY1} A ${r} ${r} 0 ${largeArc} 1 ${valX2} ${valY2}`;

  // Needle endpoint
  const needleX = cx + (r - 2) * Math.cos(sweepAngle);
  const needleY = cy - (r - 2) * Math.sin(sweepAngle);

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      width: 100,
      padding: "6px 0",
    }}>
      <svg width={100} height={56} viewBox="0 0 100 56">
        {/* Background arc */}
        <path
          d={bgPath}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
        {/* Value arc */}
        {clamped > 0 && (
          <path
            d={valPath}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            style={{
              filter: `drop-shadow(0 0 4px ${color}60)`,
            }}
          />
        )}
        {/* Needle dot */}
        <circle
          cx={needleX}
          cy={needleY}
          r={2.5}
          fill={color}
          style={{
            filter: `drop-shadow(0 0 3px ${color}80)`,
          }}
        />
        {/* Value text */}
        <text
          x={cx}
          y={cy - 4}
          textAnchor="middle"
          fill={color}
          fontSize="16"
          fontWeight="700"
          fontFamily={T.mono}
        >
          {Math.round(clamped)}
        </text>
      </svg>
      {/* Label */}
      <div style={{
        fontSize: 8,
        color: T.text4,
        fontFamily: T.font,
        fontWeight: 500,
        letterSpacing: "0.1em",
        textTransform: "uppercase",
        marginTop: -2,
        textAlign: "center",
        lineHeight: 1,
      }}>
        {label || "Fear & Greed"}
      </div>
    </div>
  );
}
