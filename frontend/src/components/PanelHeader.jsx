import { T } from "../theme.js";

// One header for the coin page cards: accent bar, sentence-case title, optional right-hand content.
export default function PanelHeader({ title, children }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
      marginBottom: 12, paddingBottom: 10, borderBottom: `1px solid ${T.overlay06}`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
        <div style={{ width: 3, height: 14, borderRadius: 2, background: T.accent, flexShrink: 0 }} />
        <span style={{ fontSize: T.textSm, color: T.text2, fontFamily: T.font, fontWeight: 700 }}>{title}</span>
      </div>
      {children}
    </div>
  );
}

// Colour of a conditions score (met of total), the same wherever a score is shown.
export function scoreColor(met, total) {
  const share = total > 0 ? met / total : 0;
  return share >= 0.8 ? T.green : share >= 0.6 ? T.text2 : T.text3;
}
