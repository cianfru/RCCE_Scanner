import { T } from "../theme.js";

const MET_COLOR = "#34d399";
const UNMET_COLOR = "#f87171";

function scoreColor(met) {
  if (met >= 8) return MET_COLOR;
  if (met >= 5) return "#fbbf24";
  return UNMET_COLOR;
}

export default function ConditionsScorecard({ conditions, met, total }) {
  if (!conditions || conditions.length === 0) return null;
  const pct = total > 0 ? (met / total) * 100 : 0;
  const color = scoreColor(met);

  return (
    <div style={{
      background: T.surface,
      border: `1px solid ${T.border}`,
      borderRadius: T.radiusSm,
      padding: "14px 16px",
      marginBottom: 14,
    }}>
      {/* Header */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 10,
      }}>
        <span style={{
          fontSize: 9, color: T.text4, letterSpacing: "0.1em",
          fontFamily: T.mono, fontWeight: 700, textTransform: "uppercase",
        }}>
          Entry Conditions
        </span>
        <span style={{
          fontFamily: T.mono, fontSize: 14, fontWeight: 700, color,
        }}>
          {met}/{total}
        </span>
      </div>

      {/* Progress bar */}
      <div style={{
        height: 4, background: "rgba(255,255,255,0.04)",
        borderRadius: 2, overflow: "hidden", marginBottom: 12,
      }}>
        <div style={{
          width: `${pct}%`, height: "100%",
          background: color,
          borderRadius: 2, transition: "width 0.4s ease",
        }} />
      </div>

      {/* Condition pills grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        gap: 4,
      }}>
        {conditions.map(c => (
          <div
            key={c.name}
            title={c.desc}
            style={{
              display: "flex", alignItems: "center", gap: 5,
              padding: "5px 8px", borderRadius: 6,
              background: c.met ? "rgba(52,211,153,0.06)" : "rgba(248,113,113,0.04)",
              border: `1px solid ${c.met ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.10)"}`,
              cursor: "help",
              transition: "background 0.15s",
              overflow: "hidden",
              minWidth: 0,
            }}
          >
            <span style={{
              fontSize: 10, fontWeight: 700, flexShrink: 0,
              color: c.met ? MET_COLOR : UNMET_COLOR,
            }}>
              {c.met ? "\u2713" : "\u2717"}
            </span>
            <span style={{
              fontSize: 9, fontFamily: T.mono, fontWeight: 500,
              color: c.met ? T.text2 : T.text4,
              whiteSpace: "nowrap",
              flexShrink: 0,
            }}>
              {c.label}
            </span>
            <span style={{
              fontSize: 8, fontFamily: T.mono, fontWeight: 400,
              color: T.text4, marginLeft: "auto",
              whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
              minWidth: 0,
            }}>
              {c.desc}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
