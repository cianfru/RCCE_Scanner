// Your book on the Radar, as a thumbnail (RadarThumb's axes: stretch across, profitable traders long
// minus short up on a symlog scale, the Watch box tinted), drawn straight on the card (no frame). One ring per covered perp position: area by
// notional, stroke in the side's colour, accent fill. No trails. A click opens the Radar.
import { symlog } from "../../utils/setupMap.js";
import { XS } from "../radar/shared.jsx";
import { kKey } from "../../utils/tickerRenames.js";

export default function BookThumb({ rows, map, W = 88, H = 56, onClick, dim = false }) {
  const byCoin = new Map((map?.coins || []).map(c => [c.coin, c]));
  const box = map?.box || { z: [-0.5, 1.5], n: [1, 8] };
  const ys = [symlog(-4), symlog(25)];
  const X = v => 4 + ((Math.max(XS[0], Math.min(XS[1], v)) - XS[0]) / (XS[1] - XS[0])) * (W - 8);
  const Y = v => H - 4 - ((Math.max(ys[0], Math.min(ys[1], symlog(v))) - ys[0]) / (ys[1] - ys[0])) * (H - 8);
  const dots = (rows || []).filter(r => r.venue === "main").map(r => ({ r, c: byCoin.get(kKey(r.coin)) })).filter(d => d.c && d.c.zscore != null);
  const max = Math.max(1, ...dots.map(d => d.r.value));
  return <button type="button" className={`pf-thumb${dim ? " pf-thumb-dim" : ""}`} onClick={onClick} aria-label="Radar">
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} aria-hidden="true">
      <rect x={X(box.z[0])} y={Y(box.n[1])} width={X(box.z[1]) - X(box.z[0])} height={Y(box.n[0]) - Y(box.n[1])} className="smap-box pf-thumb-box" />
      <line x1={X(0)} x2={X(0)} y1="4" y2={H - 4} className="pf-thumb-axis" />
      <line x1="4" x2={W - 4} y1={Y(0)} y2={Y(0)} className="pf-thumb-axis" />
      {dots.sort((a, b) => b.r.value - a.r.value).map(({ r, c }) => {
        const n = (c.traders?.pl || 0) - (c.traders?.ps || 0);
        const rad = 2.5 + 6.5 * Math.sqrt(r.value / max);
        return <circle key={r.coin} cx={X(c.zscore)} cy={Y(n)} r={rad} fill="color-mix(in srgb, var(--t-accent) 20%, transparent)"
          stroke={r.isLong ? "var(--rd-long)" : "var(--rd-short)"} strokeWidth="1.25" />;
      })}
    </svg>
  </button>;
}
