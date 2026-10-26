// TRADERS: profitable tracked traders long against short (linked wallets once), a caret over your
// side, and one line of what moved: who left your side in 24 h, or who opened in the last 6 h.
import { ROWS } from "./copy.js";

export default function TradersCell({ row, compact = false }) {
  const t = row.ctx?.traders;
  if (!row.covered || !t) return <div className="pf-tr pf-none">{"—"}</div>;
  const l = t.long.n || 0, s = t.short.n || 0;
  if (!l && !s) return <div className="pf-tr"><span className="m pf-t4">0 · 0</span></div>;
  const mine = row.isLong ? "long" : "short";
  let line2 = null;
  if (l + s >= 5) {
    const me = t[mine];
    if (row.checks.has("tradersleft")) line2 = <span className="pf-t1">{"−"}{me.n_day_ago - me.n} {mine} 24h</span>;
    else {
      const big = (t.long.opens_6h || 0) >= (t.short.opens_6h || 0) ? "long" : "short";
      if (t[big].opens_6h > 0) line2 = <span>+{t[big].opens_6h} {big} 6h</span>;
    }
  }
  const lw = (l / (l + s)) * 100;
  return <div className="pf-tr" title={`${ROWS.long} ${l} · ${ROWS.short} ${s}`}>
    <div className="pf-tr-l1">
      <span className="pf-split" aria-hidden="true">
        <i className="pf-split-l" style={{ width: `${lw}%` }} /><i className="pf-split-s" style={{ width: `${100 - lw}%` }} />
        <b className="pf-caret" style={row.isLong ? { left: 0 } : { right: 0 }} />
      </span>
      <span className="m"><span className="pf-long">{l}</span><span className="pf-t4"> · </span><span className="pf-short">{s}</span></span>
    </div>
    {!compact && <div className="pf-tr-l2 pf-t3">{line2}</div>}
  </div>;
}
