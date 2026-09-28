import { symlog, thumbExtent, trailPoints } from "../../utils/setupMap.js";
import { XS, sc } from "./shared.jsx";

// A coin's own trail against the Watch box. fit="trail" zooms to the trail, with the box as a
// tinted area and its near edges (pick cards and the scanner strip); fit="map" keeps the map's full axes.
export default function RadarThumb({ c, box, W = 96, H = 56, fit = "map" }) {
  const p = trailPoints(c) || [{ z: c.zscore, n: (c.traders?.pl || 0) - (c.traders?.ps || 0) }];
  const e = p[p.length - 1];
  if (fit !== "trail") {
    const ys = [symlog(-4), symlog(25)];
    const X = v => ((Math.max(XS[0], Math.min(XS[1], v)) - XS[0]) / (XS[1] - XS[0])) * W;
    const Y = v => H - ((Math.max(ys[0], Math.min(ys[1], symlog(v))) - ys[0]) / (ys[1] - ys[0])) * H;
    return <svg className="smap-thumb" viewBox={`0 0 ${W} ${H}`} width={W} height={H} aria-hidden="true">
      <rect x={X(box.z[0])} y={Y(box.n[1])} width={X(box.z[1]) - X(box.z[0])} height={Y(box.n[0]) - Y(box.n[1])} className="smap-box" />
      <path d={p.map((v, k) => `${k ? "L" : "M"}${X(v.z).toFixed(1)},${Y(v.n).toFixed(1)}`).join("")} fill="none" stroke={sc(c)} strokeWidth="1.6" strokeLinecap="round" strokeOpacity=".7" />
      <circle cx={X(e.z)} cy={Y(e.n)} r="3.5" fill={sc(c)} />
    </svg>;
  }
  const ext = thumbExtent(p, box);
  const X = v => ((v - ext.x[0]) / (ext.x[1] - ext.x[0])) * W;
  const Y = v => H - ((symlog(v) - ext.y[0]) / (ext.y[1] - ext.y[0])) * H;
  // The box is clamped just outside the view: an edge that is off the thumbnail draws nothing,
  // so the box reads as a tinted area with only its near edges dashed.
  const cx = v => Math.max(-2, Math.min(W + 2, v)), cy = v => Math.max(-2, Math.min(H + 2, v));
  const bx0 = cx(X(box.z[0])), bx1 = cx(X(box.z[1])), by0 = cy(Y(box.n[1])), by1 = cy(Y(box.n[0]));
  const s = p[0], color = sc(c);
  return <svg className="smap-thumb radar-thumb" viewBox={`0 0 ${W} ${H}`} width={W} height={H} aria-hidden="true">
    {bx1 > bx0 && by1 > by0 && <rect className="radar-thumb-box" x={bx0} y={by0} width={bx1 - bx0} height={by1 - by0} />}
    {p.length > 1 && <path className="radar-thumb-trail" d={p.map((v, k) => `${k ? "L" : "M"}${X(v.z).toFixed(1)},${Y(v.n).toFixed(1)}`).join("")}
      fill="none" stroke={color} strokeWidth="2" strokeOpacity=".9" strokeLinecap="round" strokeLinejoin="round" />}
    {p.length > 1 && <circle cx={X(s.z)} cy={Y(s.n)} r="2.5" fill="var(--t-bg)" stroke={color} strokeWidth="1.2" strokeOpacity=".9" />}
    <circle cx={X(e.z)} cy={Y(e.n)} r="3.5" fill={color} stroke="var(--t-bg)" strokeWidth="1" />
  </svg>;
}
