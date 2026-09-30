// Breadth since 2021: the share of scanned coins in Uptrend (weekly points), the risk-on runs
// (breadth held above the threshold) shaded, and the latest close marked with its readout.
// From /api/public/landing (history), itself from /api/market-history.
const VW = 1000, VH = 300, L = 44, R = 16, T = 40, B = 34;
const DAY = 86400000;
const year = d => new Date(d * DAY).getUTCFullYear();

export default function HistoryChart({ history }) {
  const pts = history.weekly || [];
  if (pts.length < 2) return null;
  const d0 = pts[0][0], d1 = pts[pts.length - 1][0];
  const X = d => L + ((d - d0) / Math.max(1, d1 - d0)) * (VW - L - R);
  const Y = v => T + (1 - v) * (VH - T - B);
  const last = pts[pts.length - 1];
  const line = pts.map(([d, v], i) => `${i ? "L" : "M"}${X(d).toFixed(1)},${Y(v).toFixed(1)}`).join("");
  const area = `${line}L${X(d1).toFixed(1)},${Y(0)}L${X(d0).toFixed(1)},${Y(0)}Z`;
  const cyc = history.cycle || {};
  const runs = [...(cyc.runs || []), ...(cyc.type === "on" && cyc.start != null ? [[cyc.start, cyc.day, null]] : [])];
  const years = [];
  for (let y = year(d0) + 1; y <= year(d1); y++) years.push([y, Date.UTC(y, 0, 1) / DAY]);
  const today = history.today?.uptrend ?? last[1];
  const readout = `Latest close: ${Math.round(100 * today)}% of coins in Uptrend${cyc.type === "on" && cyc.day ? ` · risk-on run, day ${cyc.day}` : ""}`;
  return <svg className="lp-hist" viewBox={`0 0 ${VW} ${VH}`} role="img" aria-label="Share of coins in Uptrend each week since May 2021, with risk-on runs shaded">
    <defs>
      <linearGradient id="lp-hist-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#97FCE4" stopOpacity=".22" /><stop offset="1" stopColor="#97FCE4" stopOpacity="0" /></linearGradient>
    </defs>
    {runs.map(([s, n], i) => <rect key={i} className={i === runs.length - 1 && cyc.type === "on" ? "lp-run now" : "lp-run"} x={X(s)} y={T} width={Math.max(2, X(s + n) - X(s))} height={VH - T - B} />)}
    {[0, 0.25, 0.5, 0.75, 1].map(v => <g key={v}><line className="lp-hist-ax" x1={L} x2={VW - R} y1={Y(v)} y2={Y(v)} /><text className="lp-hist-t" x={L - 8} y={Y(v) + 4} textAnchor="end">{Math.round(v * 100)}%</text></g>)}
    {cyc.threshold != null && <line className="lp-hist-th" x1={L} x2={VW - R} y1={Y(cyc.threshold)} y2={Y(cyc.threshold)} />}
    {years.map(([y, d]) => <text key={y} className="lp-hist-t" x={X(d)} y={VH - 10} textAnchor="middle">{y}</text>)}
    <path d={area} fill="url(#lp-hist-fill)" />
    <path d={line} fill="none" stroke="#97FCE4" strokeWidth="1.6" strokeLinejoin="round" />
    <circle cx={X(last[0])} cy={Y(last[1])} r="4.5" fill="#97FCE4" />
    <circle cx={X(last[0])} cy={Y(last[1])} r="9" fill="none" stroke="#97FCE4" strokeOpacity=".4" />
    <text className="lp-hist-read" x={L} y={22}>{readout}</text>
  </svg>;
}
