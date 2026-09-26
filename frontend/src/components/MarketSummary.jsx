import { T, REGIME_META } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";
import HelpTip from "./HelpTip.jsx";
import FearGreedDial from "./FearGreedDial.jsx";
import SignalLadder from "./SignalLadder.jsx";
import { CONSENSUS_LINE, CONSENSUS_NOTES, regimeMix } from "../utils/marketSummary.js";

const CONSENSUS_COLORS = () => ({ "RISK-ON": T.green, EUPHORIA: T.yellow, "RISK-OFF": T.red, ACCUMULATION: T.cyan, MIXED: T.text2 });

// Market summary: consensus and regime mix | Fear & Greed dial | signal counts.
export default function MarketSummary({ regimeRows, signalRows, consensus, sentiment, timeframe, scopeLabel, spot = false,
                                        activeSignalFilter, onSignalFilter }) {
  const label = consensus?.consensus || null;
  const mix = regimeMix(regimeRows, label || "MIXED");
  const color = (label && CONSENSUS_COLORS()[label]) || "var(--t-text3)";
  const tf = String(timeframe || "").toUpperCase();
  const name = r => REGIME_META[r]?.name || r;
  const bucketName = { "RISK-ON": "Uptrend", EUPHORIA: "Overheated", "RISK-OFF": "Downtrend", ACCUMULATION: "basing" };
  let cum = 0;
  const segs = mix.order.map((r, i) => {
    const c = mix.counts[r];
    const left = (100 * cum) / mix.N;
    cum += c;
    const last = i === mix.order.length - 1;
    return { r, c, left, width: `max(3px, calc(${(100 * c) / mix.N}% - ${last ? 0 : 2}px))`, anchor: mix.anchor.includes(r) };
  });
  const aria = `Regime bar of ${mix.N} scanned markets, starting with ${name(segs[0]?.r)}; line at ${CONSENSUS_LINE}%.`;
  return <FadeIn>
    <GlassCard className="market-summary">
      <div className="ms-regime">
        <div className="ms-eyebrow"><span className="ms-eyebrow-text"><span className="ms-long">Market consensus</span><span className="ms-short">Consensus</span><span className="ms-tf"> · {tf}</span></span>
          <HelpTip title="Market consensus" width={400}>
            <p>Every scanned market, perps and spot, sits in one regime on this timeframe. The scanner names the market when one group holds more than 55% of them: RISK-ON (Uptrend), EUPHORIA (Overheated), RISK-OFF (Downtrend) or ACCUMULATION (Accumulation, Re-accumulating and Capitulation together). Otherwise it reads MIXED.</p>
            <p>The bar shows every regime, starting with the group that decides the label; the line marks 55%. The percentage is a head count of markets, not a probability or a strength score.</p>
            <p>This is the same count the engine uses, so it covers both market kinds whichever one the grid shows.</p>
            <p>Consensus is one of the nine core checks behind a long signal: it passes on RISK-ON or ACCUMULATION. Two paths read it the other way: Light long in Uptrend (moderate z) and the Re-accumulating setups need RISK-ON or MIXED. RISK-OFF also blocks most Accumulate paths (not Capitulation absorption or funding-squeeze setups) and lets Risk-off exits fire.</p>
          </HelpTip>
        </div>
        <strong className="ms-headline" style={{ "--consensus-color": color }}>{label || "Awaiting analysis"}</strong>
        {label && mix.N > 0 && <span className="ms-sub">
          {label === "MIXED"
            ? <>None above 55% · <span className="nowrap">largest: {bucketName[mix.bucket]} <b>{mix.p}%</b></span></>
            : <><b>{mix.n}</b> of <b>{mix.N}</b> {mix.anchorName} <span className="nowrap">· <b>{mix.p}%</b></span></>}
        </span>}
        {mix.N > 0 && <div className="mix-bar" role="img" aria-label={aria}>
          {segs.map(s => <i key={s.r} title={`${name(s.r)}: ${s.c} of ${mix.N} (${Math.round((100 * s.c) / mix.N)}%)`}
            style={{ left: `${s.left}%`, width: s.width, background: REGIME_META[s.r]?.color || T.text4, opacity: s.anchor ? 1 : 0.6 }} />)}
          <em className="mix-tick" /><span className="mix-tick-label" aria-hidden="true">{CONSENSUS_LINE}%</span>
        </div>}
      </div>
      <div className="ms-detail">
        {mix.N > 0 && <ul className="regime-legend">
          {segs.map(s => <li key={s.r}><i style={{ background: REGIME_META[s.r]?.color || T.text4 }} />{name(s.r)}<b>{s.c}</b></li>)}
        </ul>}
        {label && <p className="ms-note">{CONSENSUS_NOTES[label] || CONSENSUS_NOTES.MIXED}</p>}
      </div>
      <FearGreedDial value={sentiment?.fear_greed_value} loaded={sentiment != null} />
      <SignalLadder rows={signalRows} timeframe={timeframe} scopeLabel={scopeLabel} spot={spot}
        active={activeSignalFilter} onChange={onSignalFilter} />
    </GlassCard>
  </FadeIn>;
}
