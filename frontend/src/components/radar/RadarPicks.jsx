import HelpTip from "../HelpTip.jsx";
import TokenLogo from "../TokenLogo.jsx";
import RadarThumb from "./RadarThumb.jsx";
import { Crowd, Pin, Progress, hrs } from "./shared.jsx";
import { SIGNAL_SHORT } from "../../utils/setupMap.js";
import { fmtIn, nextCloses } from "../../utils/intel.js";

// One of the day's shortlist: the coin, its crowd word, its own trail against the box and
// three readings (signal and its age, traders and arrivals, the next close that matters).
export function Pick({ x, box, tf, onClick, focused = false, watched = false }) {
  const c = x.c, t = c.transition, now = Date.now();
  const left = t ? Math.max(0, t.need - Math.min(t.seen, t.need)) : 0;
  const decides = nextCloses(tf, now, Math.max(1, c.stage === "forming" ? left : 1)).pop();
  return <button type="button" className="smap-pick" aria-pressed={focused} onClick={onClick}>
    <div className="smap-pick-top">
      <strong><TokenLogo symbol={c.symbol} size={20} />{c.coin}{watched && <Pin title="Watching" />}</strong>
      <Crowd k={c.crowd} />
    </div>
    <div className="smap-pick-body"><RadarThumb c={c} box={box} fit="trail" W={96} H={56} />
      <dl className="smap-kv">
        <div><dt>Signal</dt><dd>{c.stage === "forming" && t
          ? <Progress t={t} />
          : <>{SIGNAL_SHORT[c.signal] || c.signal}{c.trigger_at ? <em> {hrs(Date.now() / 1000 - c.trigger_at)}</em> : null}</>}</dd></div>
        <div><dt>Traders</dt><dd>{c.traders?.pl || 0}{x.m?.dn > 0 ? <em className="up"> +{x.m.dn}</em> : null}</dd></div>
        <div><dt>{c.stage === "forming" ? "Decides" : "Next close"}</dt><dd>{fmtIn(decides - now).replace(/ \d+m$/, "")}</dd></div>
      </dl></div>
  </button>;
}

// "Look at these today": up to four early setups (coins in the box), ranked by the engine's
// priority plus what moved. The (i) explains the whole map.
export default function RadarPicks({ top, box, tf, focus, watched, inBox, loaded, onPick }) {
  return <section className="radar-picks" aria-labelledby="radar-picks-h">
    <div className="radar-picks-head">
      <h2 id="radar-picks-h">Look at these today <HelpTip title="Reading the Radar">
        <p>Each bubble is a coin. Left to right: how far price sits from its mean (the engine's z-score). Bottom to top: profitable Hyperliquid traders long minus short. Colour: where the setup is (forming, just fired, running, stretched, leaving).</p>
        <p>Early setups (the shaded box): a setup that has not run far, with a few profitable traders long and no crowd yet.</p>
        <p>Click a bubble to see who holds it and at what price; click the same spot again to step through coins stacked there. Trails show the last {tf === "1d" ? "5 days" : "24 hours"}; press Replay to watch them move. Size, rings and colours: the map key (i) under the map.</p>
        <p>Look at these today: early setups ranked by the engine's priority plus what moved. A shortlist for your eyes, not a forecast.</p>
      </HelpTip></h2>
      {loaded && <span className="radar-meta"><b>{inBox}</b> early setups</span>}
    </div>
    {!loaded ? <div className="smap-picks">{[0, 1, 2, 3].map(k => <div key={k} className="smap-pick radar-pick-skel shimmer-loading" aria-hidden="true" />)}</div>
      : top.length > 0 ? <div className="smap-picks">{top.map(x => <Pick key={x.c.coin} x={x} box={box} tf={tf} focused={focus === x.c.coin}
        watched={watched.has(x.c.coin)} onClick={() => onPick(x.c.coin)} />)}</div>
      : <p className="smap-note">No early setups on this timeframe right now.</p>}
  </section>;
}
