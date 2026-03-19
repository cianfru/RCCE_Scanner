import { T } from "../theme.js";

const MET_COLOR = "#34d399";
const UNMET_COLOR = "#f87171";

function scoreColor(pct) {
  if (pct >= 75) return MET_COLOR;
  if (pct >= 50) return "#fbbf24";
  return UNMET_COLOR;
}

function ConditionPill({ c }) {
  return (
    <div
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
  );
}

export default function ConditionsScorecard({ conditions, met, total }) {
  if (!conditions || conditions.length === 0) return null;
  const pct = total > 0 ? (met / total) * 100 : 0;
  const color = scoreColor(pct);

  // Split conditions by group (core vs coinglass)
  const core = conditions.filter(c => c.group !== "coinglass");
  const cg = conditions.filter(c => c.group === "coinglass");
  const coreMet = core.filter(c => c.met).length;
  const cgMet = cg.filter(c => c.met).length;

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
          <span style={{ fontSize: 9, fontWeight: 400, color: T.text4, marginLeft: 6 }}>
            ({Math.round(pct)}%)
          </span>
        </span>
      </div>

      {/* Progress bar */}
      <div style={{
        height: 4, background: T.overlay04,
        borderRadius: 2, overflow: "hidden", marginBottom: 12,
      }}>
        <div style={{
          width: `${pct}%`, height: "100%",
          background: color,
          borderRadius: 2, transition: "width 0.4s ease",
        }} />
      </div>

      {/* Core conditions section */}
      <div style={{
        fontSize: 8, color: T.text4, letterSpacing: "0.08em",
        fontFamily: T.mono, fontWeight: 600, textTransform: "uppercase",
        marginBottom: 6, display: "flex", justifyContent: "space-between",
      }}>
        <span>Core Engine</span>
        <span style={{ color: coreMet >= 7 ? MET_COLOR : coreMet >= 5 ? "#fbbf24" : UNMET_COLOR }}>
          {coreMet}/{core.length}
        </span>
      </div>
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(2, 1fr)",
        gap: 4,
        marginBottom: cg.length > 0 ? 12 : 0,
      }}>
        {core.map(c => <ConditionPill key={c.name} c={c} />)}
      </div>

      {/* CoinGlass conditions section (only if present) */}
      {cg.length > 0 && (
        <>
          <div style={{
            fontSize: 8, color: T.text4, letterSpacing: "0.08em",
            fontFamily: T.mono, fontWeight: 600, textTransform: "uppercase",
            marginBottom: 6, display: "flex", justifyContent: "space-between",
          }}>
            <span>Market Context</span>
            <span style={{ color: cgMet >= 3 ? MET_COLOR : cgMet >= 2 ? "#fbbf24" : UNMET_COLOR }}>
              {cgMet}/{cg.length}
            </span>
          </div>
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, 1fr)",
            gap: 4,
          }}>
            {cg.map(c => <ConditionPill key={c.name} c={c} />)}
          </div>
        </>
      )}
    </div>
  );
}
