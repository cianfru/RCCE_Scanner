import { T } from "../theme.js";
const stamp = value => value ? new Date(value * 1000).toLocaleString() : "Unavailable";
const colors = { confirmed: "#34d399", emerging: "#fbbf24", blocked: "#f87171", invalidated: "#f87171", expired: "#a1a1aa", unavailable: "#a1a1aa", risk_warning: "#fb923c" };
export default function OpportunityCard({ row }) {
  const o = row?.opportunity;
  if (!o) return null;
  const cto = row.cto || {};
  const policies = Object.entries(row.cto_shadow || {});
  return <section aria-label="Opportunity status" style={{ padding: 16, marginBottom: 14, border: `1px solid ${T.border}`, borderRadius: 12, background: T.glassBg, color: T.text2 }}>
    <strong style={{ color: colors[o.status] }}>{o.status.replaceAll("_", " ").toUpperCase()}</strong>
    <span> · {o.direction || "Watching"} · {o.setup_type}</span>
    <p>{o.reason}</p>
    <p>Evidence coverage: {Math.round((o.evidence_coverage || 0) * 100)}% · CTO: {(cto.state || "unavailable").replaceAll("_", " ")} ({row.cto_mode || "shadow"})</p>
    <p>Completed candle: {stamp(o.candle_close_time)}<br/>Trigger: {stamp(o.trigger_at)} · Expires: {stamp(o.expires_at)}</p>
    <p>Invalidation: {o.invalidation_level ?? "Unavailable"}{o.invalidation_basis ? ` · ${o.invalidation_basis}` : ""}<br/>Execution: {o.execution?.reason || o.execution?.status || "Unknown"}</p>
    {o.blockers?.length > 0 && <p>Strong-entry blockers: {o.blockers.join(", ")}</p>}
    <details><summary>CTO research decisions and input freshness</summary>
      <p>Shadow variants do not change live eligibility. Scores describe alignment, not a win probability.</p>
      <ul>{policies.map(([key, value]) => <li key={key}>{key}: {value.status} — {value.reason}</li>)}</ul>
      <ul>{Object.entries(row.input_quality || {}).map(([key, value]) => <li key={key}>{key}: {value.status} · {value.source || "Unknown source"} · {stamp(value.observed_at)}</li>)}</ul>
    </details>
  </section>;
}
