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
        display: "flex", alignItems: "center", gap: 6,
        padding: "6px 10px", borderRadius: 8,
        background: c.met ? "rgba(52,211,153,0.06)" : "rgba(248,113,113,0.04)",
        border: `1px solid ${c.met ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.10)"}`,
        cursor: "help",
        transition: "background 0.15s",
        overflow: "hidden",
        minWidth: 0,
      }}
    >
      <span style={{
        fontSize: T.textBase, fontWeight: 700, flexShrink: 0,
        color: c.met ? MET_COLOR : UNMET_COLOR,
      }}>
        {c.met ? "\u2713" : "\u2717"}
      </span>
      <span style={{
        fontSize: T.textSm, fontFamily: T.mono, fontWeight: 500,
        color: c.met ? T.text2 : T.text4,
        whiteSpace: "nowrap", flexShrink: 0,
      }}>
        {c.label}
      </span>
      <span style={{
        fontSize: T.textXs, fontFamily: T.mono, fontWeight: 400,
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

  const core = conditions.filter(c => c.group !== "coinglass");
  const cg = conditions.filter(c => c.group === "coinglass");
  const coreMet = core.filter(c => c.met).length;
  const cgMet = cg.filter(c => c.met).length;

  return (
    <div style={{
      background: T.glassBg,
      border: `1px solid ${T.border}`,
      borderRadius: 12,
      padding: "16px 20px",
      backdropFilter: "blur(20px) saturate(1.3)",
      WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      {/* Header */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 14, paddingBottom: 10,
        borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 3, height: 14, borderRadius: 2, background: T.accent, flexShrink: 0 }} />
          <span style={{
            fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em",
            fontFamily: T.font, fontWeight: 700, textTransform: "uppercase",
          }}>
            Entry Conditions
          </span>
        </div>
        <span style={{ fontFamily: T.mono, fontSize: T.textLg, fontWeight: 700, color }}>
          {met}/{total}
          <span style={{ fontSize: T.textSm, fontWeight: 400, color: T.text4, marginLeft: 6 }}>
            ({Math.round(pct)}%)
          </span>
        </span>
      </div>

      {/* Progress bar */}
      <div style={{
        height: 5, background: T.overlay04,
        borderRadius: 3, overflow: "hidden", marginBottom: 14,
      }}>
        <div style={{
          width: `${pct}%`, height: "100%",
          background: `linear-gradient(90deg, ${color}88, ${color})`,
          borderRadius: 3, transition: "width 0.4s ease",
          boxShadow: `0 0 8px ${color}30`,
        }} />
      </div>

      {/* Core conditions */}
      <div style={{
        fontSize: T.textSm, color: T.text4, letterSpacing: "0.08em",
        fontFamily: T.font, fontWeight: 600, textTransform: "uppercase",
        marginBottom: 8, display: "flex", justifyContent: "space-between",
      }}>
        <span>Core Engine</span>
        <span style={{ color: coreMet >= 7 ? MET_COLOR : coreMet >= 5 ? "#fbbf24" : UNMET_COLOR, fontFamily: T.mono }}>
          {coreMet}/{core.length}
        </span>
      </div>
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(2, 1fr)",
        gap: 5, marginBottom: cg.length > 0 ? 14 : 0,
      }}>
        {core.map(c => <ConditionPill key={c.name} c={c} />)}
      </div>

      {/* CoinGlass conditions */}
      {cg.length > 0 && (
        <>
          <div style={{
            fontSize: T.textSm, color: T.text4, letterSpacing: "0.08em",
            fontFamily: T.font, fontWeight: 600, textTransform: "uppercase",
            marginBottom: 8, display: "flex", justifyContent: "space-between",
          }}>
            <span>Market Context</span>
            <span style={{ color: cgMet >= 3 ? MET_COLOR : cgMet >= 2 ? "#fbbf24" : UNMET_COLOR, fontFamily: T.mono }}>
              {cgMet}/{cg.length}
            </span>
          </div>
          <div style={{
            display: "grid", gridTemplateColumns: "repeat(2, 1fr)",
            gap: 5,
          }}>
            {cg.map(c => <ConditionPill key={c.name} c={c} />)}
          </div>
        </>
      )}
    </div>
  );
}
