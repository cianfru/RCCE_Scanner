// SCANNER: the 4H signal in its own colour and how long it has held (1D on hover, and "1D" when the
// daily signal points the other way); a heat bar with the entry limits (70, 85) and Trim (95).
import { SIGNAL_META } from "../../theme.js";
import { age } from "../../utils/portfolio/format.js";

export const sigWord = s => SIGNAL_META[s]?.label || String(s || "—").replaceAll("_", " ");
export const sigColor = s => SIGNAL_META[s]?.color || "var(--t-text3)";

export function HeatBar({ heat, prev, w = 56 }) {
  if (heat == null) return null;
  const at = v => `${Math.max(0, Math.min(100, v))}%`;
  return <span className="pf-hbar" style={{ width: w }} aria-hidden="true">
    <i className="pf-hbar-fill" style={{ width: at(heat) }} />
    <b style={{ left: at(70) }} /><b style={{ left: at(85) }} /><b className="pf-hbar-95" style={{ left: at(95) }} />
    {prev != null && <b className="pf-hbar-ghost" style={{ left: at(prev) }} />}
  </span>;
}

export default function ScannerCell({ row, now = Date.now(), compact = false }) {
  const ctx = row.ctx;
  if (!ctx?.h4) return <div className="pf-sc pf-none">{"—"}</div>;
  const h4 = ctx.h4, d1 = ctx.d1;
  const since = h4.since ? now / 1000 - h4.since : null;
  const against = row.checks.has("d1against");
  return <div className={`pf-sc${row.isLong ? "" : " pf-sc-short"}`} title={d1?.signal ? `1D ${sigWord(d1.signal)}` : undefined}>
    <div className="pf-sc-l1">
      <span className="pf-sig" style={{ color: sigColor(h4.signal) }}>{sigWord(h4.signal)}</span>
      {since != null && <span className="pf-t3 m">{age(since)}</span>}
      {against && <span className="pf-t1 pf-sc-1d">1D</span>}
    </div>
    {!compact && <div className="pf-sc-l2">
      <HeatBar heat={h4.heat} prev={h4.heat_prev} />
      <span className={`m pf-heat-n${h4.heat >= 95 ? " pf-heat-hot" : ""}`}>{h4.heat ?? "—"}</span>
    </div>}
  </div>;
}
