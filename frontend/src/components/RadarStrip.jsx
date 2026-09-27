import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import useSetupMap from "../hooks/useSetupMap.js";
import useViewport from "../hooks/useViewport.js";
import TokenLogo from "./TokenLogo.jsx";
import { NavIcon } from "./navIcons.jsx";
import RadarThumb from "./radar/RadarThumb.jsx";
import { Crowd, Pin, Progress, hrs } from "./radar/shared.jsx";
import { SIGNAL_SHORT, picks, radarHref } from "../utils/setupMap.js";

function Tile({ x, box, onClick }) {
  const c = x.c, t = c.transition, n = c.traders?.pl || 0, arrived = x.m?.dn > 0 ? x.m.dn : 0;
  return <button type="button" className="radar-tile" onClick={onClick} aria-label={`${c.coin} on the Radar`}>
    <RadarThumb c={c} box={box} fit="trail" W={64} H={36} />
    <span className="radar-tile-top"><TokenLogo symbol={c.symbol} size={16} /><strong>{c.coin}</strong><Crowd k={c.crowd} /></span>
    <span className="radar-tile-sub">
      <span className="sig">{c.stage === "forming" && t ? <Progress t={t} /> : <>{SIGNAL_SHORT[c.signal] || c.signal}{c.trigger_at ? ` ${hrs(Date.now() / 1000 - c.trigger_at)}` : ""}</>}</span>
      <span className="trd">{n} trader{n === 1 ? "" : "s"}{arrived ? <em> +{arrived}</em> : null}</span>
    </span>
  </button>;
}

// The scanner's entry to the Radar (perps only): today's picks in the Watch box as small
// trail thumbnails, the in-box count and the watch count. Follows the pressed sector chip.
export default function RadarStrip({ results, timeframe, sector, sectorLabel }) {
  const tf = timeframe === "4h" ? "4h" : "1d";
  const { width } = useViewport();
  const phone = width < 768;
  const navigate = useNavigate();
  const { data, error, watched } = useSetupMap(tf);
  const allowed = useMemo(() => new Set((results || []).map(r => r.symbol)), [results]);
  const coins = useMemo(() => (data?.coins || []).filter(c => allowed.has(c.symbol)), [data, allowed]);
  const box = data?.box || { z: [-0.5, 1.5], n: [1, 8] };
  const top = useMemo(() => picks(coins, box), [coins, box]);
  const inBox = useMemo(() => coins.filter(c => c.zone === "watch").length, [coins]);
  const open = radarHref({ tf, sector });
  const scope = sector ? ` · ${sectorLabel || sector}` : "";
  const loading = !error && (!data || !(results || []).length);
  const n = watched.size;

  const head = <div className="radar-strip-id">
    <span className="radar-strip-title"><span className="radar-strip-glyph"><NavIcon name="radar" /></span>Radar<small>{tf.toUpperCase()}</small></span>
    {!phone && !loading && <span className="radar-strip-count"><b>{inBox}</b> in the Watch box{scope}</span>}
    {phone && !loading && <span className="radar-strip-count">· <b>{inBox}</b> in the box{scope}</span>}
  </div>;

  return <section className="radar-strip" aria-label="Radar">
    {phone ? <div className="radar-strip-row1">{head}<Link className="radar-open" to={open}>Open →</Link></div> : head}
    {loading ? <div className="radar-strip-loading shimmer-loading" aria-hidden="true" />
      : error && !data ? <p className="radar-strip-empty">The Radar is not available right now.</p>
      : top.length === 0 ? <p className="radar-strip-empty">No coin sits in the Watch box on {tf.toUpperCase()}{scope ? ` in ${sectorLabel || sector}` : ""} right now.</p>
      : <div className="radar-tiles">{top.map(x => <Tile key={x.c.coin} x={x} box={box} onClick={() => navigate(radarHref({ tf, focus: x.c.coin, sector }))} />)}</div>}
    {!phone && <div className="radar-strip-end">
      <Link className="radar-open" to={open}>Open Radar →</Link>
      {n > 0 && <span className="radar-strip-watching"><Pin size={8} color="var(--t-text3)" />Watching {n}</span>}
    </div>}
  </section>;
}

