import { useEffect, useMemo, useState } from "react";
import HelpTip from "./HelpTip.jsx";
import { apiJson } from "../edge.js";
import { getBaseSymbol } from "../theme.js";
import { STATE_WORD, dayText, pctText, vsBtcLine } from "../utils/longsNow.js";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// The coin page's "Against BTC": the coin's daily close divided by BTC's over the last year, with the weekly band
// drawn on that ratio (/api/vs-btc, backend relative_band.py) and the days the ratio crossed it. Context.
export default function AgainstBtc({ symbol, width }) {
  const [d, setD] = useState(null);
  const coin = symbol ? getBaseSymbol(symbol) : "";
  useEffect(() => {
    setD(null);
    if (!coin || coin === "BTC" || coin.toLowerCase().startsWith("xyz:")) return undefined;
    let alive = true;
    apiJson(`/api/vs-btc?symbol=${encodeURIComponent(coin)}&days=365`).then(j => { if (alive) setD(j); }).catch(() => { if (alive) setD({ available: false }); });
    return () => { alive = false; };
  }, [coin]);
  const W = Math.max(280, Math.min(width || 900, 1400)), H = W < 600 ? 200 : 240, L = 8, R = 56, T = 12, B = 24;
  const geo = useMemo(() => {
    if (!d?.available || !d.days?.length) return null;
    const vals = [...d.ratio, ...d.lo, ...d.hi].filter(v => v != null && v > 0);
    const lmin = Math.log(Math.min(...vals)), lmax = Math.log(Math.max(...vals)), span = lmax - lmin || 1;
    const n = d.days.length;
    const X = k => L + (k / (n - 1)) * (W - L - R);
    const Y = v => T + (1 - (Math.log(v) - lmin) / span) * (H - T - B);
    const pts = (arr) => arr.map((v, k) => (v == null ? null : `${X(k).toFixed(1)},${Y(v).toFixed(1)}`));
    const r = pts(d.ratio).filter(Boolean);
    const idx = d.days.map((_, k) => k).filter(k => d.lo[k] != null && d.hi[k] != null);
    const band = [...idx.map(k => `${X(k).toFixed(1)},${Y(d.hi[k]).toFixed(1)}`), ...idx.slice().reverse().map(k => `${X(k).toFixed(1)},${Y(d.lo[k]).toFixed(1)}`)];
    const at = day => d.days.indexOf(day);
    const marks = [...(d.up || []).map(x => ["up", at(x)]), ...(d.down || []).map(x => ["down", at(x)])].filter(([, k]) => k >= 0)
      .map(([kind, k]) => ({ kind, x: X(k), y: Y(d.ratio[k]), day: d.days[k] }));
    const months = d.days.map((day, k) => ({ day, k })).filter(({ day }) => new Date(day * 86400000).getUTCDate() === 1)
      .filter((_, i, a) => a.length <= 7 || i % 2 === 0).map(({ day, k }) => ({ x: X(k), label: MONTHS[new Date(day * 86400000).getUTCMonth()] }));
    return { line: `M${r.join(" L")}`, band: band.length ? `M${band.join(" L")} Z` : null, marks, months,
      end: { x: X(n - 1), y: Y(d.ratio[n - 1]) } };
  }, [d, W, H]);
  if (!coin || coin === "BTC" || d?.available === false) return null;
  const s = d?.summary;
  return <article className="analysis-card ab-card">
    <h2>Against BTC <HelpTip title="Against BTC" width={400}>
      <p>{coin}'s daily close divided by BTC's over the last year, with the weekly band (20-week SMA and 21-week EMA) drawn on that ratio. Above the band: {coin} has been beating BTC as a trend; under it: lagging. "Since": the first close on that side after the ratio last closed on the other side.</p>
      <p>Green dots: the ratio closed above its band after two weeks or more without doing so. Red: the mirror.</p>
      <p>In past data (149 coins since 2017), coins above their band against BTC more often gave the lead back over the next one to three months, and a cross above the band did not mark a lasting lead. Context, not a signal.</p>
    </HelpTip></h2>
    {s && <p className="ab-line"><b className={s.state}>{STATE_WORD[s.state]} its band</b>
      {s.since != null && <span> since {dayText(s.since)}</span>}
      {s.chg30 != null && <span> · 30d {pctText(s.chg30)}</span>}{s.chg90 != null && <span> · 90d {pctText(s.chg90)}</span>}</p>}
    {!geo ? <div className="ab-skel shimmer-loading" style={{ height: H }} aria-hidden="true" />
      : <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="ab-chart" role="img" aria-label={`${coin} against BTC over a year, ${vsBtcLine(s)}`}>
        {geo.months.map(m => <g key={m.x}><line x1={m.x} x2={m.x} y1={T} y2={H - B} className="ab-grid" /><text x={m.x} y={H - 6} className="ab-tick" textAnchor="middle">{m.label}</text></g>)}
        {geo.band && <path d={geo.band} className="ab-band" />}
        <path d={geo.line} className={`ab-line-path ${s?.state || ""}`} />
        {geo.marks.map(m => <circle key={`${m.kind}${m.day}`} cx={m.x} cy={m.y} r="4" className={`ab-mark ${m.kind}`}><title>{`${m.kind === "up" ? "Crossed above" : "Fell below"} its band, ${dayText(m.day)}`}</title></circle>)}
        <circle cx={geo.end.x} cy={geo.end.y} r="3.5" className={`ab-end ${s?.state || ""}`} />
        <text x={geo.end.x + 8} y={geo.end.y + 4} className="ab-endlab">{coin}/BTC</text>
      </svg>}
  </article>;
}
