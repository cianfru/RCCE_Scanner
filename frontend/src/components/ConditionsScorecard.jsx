import HelpTip from "./HelpTip.jsx";
import PanelHeader, { scoreColor } from "./PanelHeader.jsx";
import { T } from "../theme.js";

// Getters: T.green/T.red are repainted in place for the light theme.
const C = { get met() { return T.green; }, get unmet() { return T.red; } };

function ConditionPill({ c }) {
  return (
    <div className="condition-item" title={`${c.desc} · ${c.source || "Source unavailable"} · ${c.freshness || "Unknown freshness"}${c.observed_at ? ` · ${new Date(c.observed_at * 1000).toISOString()}` : ""}`}>
      <span aria-label={c.available === false ? 'Unknown' : c.met ? 'Met' : 'Not met'} style={{color:c.available === false ? T.text4 : c.met ? C.met : C.unmet}}>{c.available === false ? '?' : c.met ? '✓' : '✗'}</span>
      <div><strong>{c.label}</strong><p>{c.available === false ? "Data unavailable — not counted as confirmation" : c.desc}</p></div>
    </div>
  );
}

export default function ConditionsScorecard({ conditions, met, total }) {
  if (!conditions || conditions.length === 0) return null;
  const pct = total > 0 ? (met / total) * 100 : 0;
  const color = scoreColor(met, total);

  const core = conditions.filter(c => c.group !== "coinglass");
  const cg = conditions.filter(c => c.group === "coinglass");
  const coreMet = core.filter(c => c.met).length;
  const cgMet = cg.filter(c => c.met).length;

  return (
    <div style={{
      background: T.glassBg,
      border: `1px solid ${T.border}`,
      borderRadius: T.radius,
      padding: "16px 20px",
      backdropFilter: "blur(20px) saturate(1.3)",
      WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      <PanelHeader title={<>
        Entry conditions <HelpTip title="Entry conditions"><p>The individual checks used by the signal engine: regime, market consensus, price deviation, heat, funding and other available inputs. A checkmark means the condition is met in the current snapshot. Unknown inputs earn no points. The percentage shows checklist alignment, not the probability of a profitable trade.</p></HelpTip>
      </>}>
        <span style={{ fontFamily: T.mono, fontSize: T.textLg, fontWeight: 700, color }}>
          {met}/{total}
          <span style={{ fontSize: T.textSm, fontWeight: 400, color: T.text4, marginLeft: 6 }}>
            ({Math.round(pct)}%)
          </span>
        </span>
      </PanelHeader>

      {conditions.some(c => c.available === false) && (
        <p style={{ color: T.text4, marginBottom: 10 }}>
          Evidence available: {conditions.filter(c => c.available !== false).length}/{conditions.length}
        </p>
      )}
      {/* Progress bar */}
      <div style={{
        height: 5, background: T.overlay04,
        borderRadius: 3, overflow: "hidden", marginBottom: 14,
      }}>
        <div style={{
          width: `${pct}%`, height: "100%",
          // Solid fill: the score colour can be a CSS variable, which takes no alpha suffix.
          background: color,
          borderRadius: 3, transition: "width 0.4s ease",
        }} />
      </div>

      {/* Core conditions */}
      <div style={{
        fontSize: T.textSm, color: T.text4, letterSpacing: "0.02em",
        fontFamily: T.font, fontWeight: 600, textTransform: "none",
        marginBottom: 8, display: "flex", justifyContent: "space-between",
      }}>
        <span>Core engine</span>
        <span style={{ color: scoreColor(coreMet, core.length), fontFamily: T.mono }}>
          {coreMet}/{core.length}
        </span>
      </div>
      <div className="condition-list" style={{
        display: "grid", gridTemplateColumns: "repeat(2, 1fr)",
        gap: 5, marginBottom: cg.length > 0 ? 14 : 0,
      }}>
        {core.map(c => <ConditionPill key={c.name} c={c} />)}
      </div>

      {/* CoinGlass conditions */}
      {cg.length > 0 && (
        <>
          <div style={{
            fontSize: T.textSm, color: T.text4, letterSpacing: "0.02em",
            fontFamily: T.font, fontWeight: 600, textTransform: "none",
            marginBottom: 8, display: "flex", justifyContent: "space-between",
          }}>
            <span>Market context</span>
            <span style={{ color: scoreColor(cgMet, cg.length), fontFamily: T.mono }}>
              {cgMet}/{cg.length}
            </span>
          </div>
          <div className="condition-list" style={{
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
