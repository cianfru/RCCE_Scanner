import { T, REGIME_META, REGIME_ORDER } from "../theme.js";

export default function SummaryBar({ results }) {
  const counts = {};
  REGIME_ORDER.forEach(r => counts[r] = 0);
  results.forEach(r => { if (counts[r.regime] !== undefined) counts[r.regime]++; });
  const total = results.length;

  return (
    <div style={{
      display: "flex", gap: 1, height: 4, borderRadius: 4, overflow: "hidden",
      background: T.overlay02,
    }}>
      {REGIME_ORDER.filter(r => counts[r] > 0).map(r => {
        const m = REGIME_META[r];
        const pct = (counts[r] / total) * 100;
        return (
          <div
            key={r}
            title={`${m.label}: ${counts[r]}`}
            style={{
              flex: pct,
              background: `linear-gradient(90deg, ${m.color}cc, ${m.color})`,
              minWidth: 2,
              boxShadow: `0 0 8px ${m.glow}`,
            }}
          />
        );
      })}
    </div>
  );
}
