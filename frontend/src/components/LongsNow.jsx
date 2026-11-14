import { useMemo, useState } from "react";
import GlassCard from "./GlassCard.jsx";
import HelpTip from "./HelpTip.jsx";
import TokenLogo from "./TokenLogo.jsx";
import useSetupMap from "../hooks/useSetupMap.js";
import { Signs } from "./radar/RadarBand.jsx";
import { zText } from "../utils/radarBand.js";
import { SIGNAL_WORD, longsNow, pctText, strengthBar } from "../utils/longsNow.js";

const SHOWN = 6;

// The coins with a long signal on this timeframe, in the scanner's priority order, each with what happened around
// it: its 14-day move against the median coin, profitable traders long (and new in 24h), its distance from the
// weekly band and the heat signs lit. Context: nothing here orders or filters the signals.
export default function LongsNow({ rows, timeframe, onSelect }) {
  const tf = timeframe === "1d" ? "1d" : "4h";
  const { data } = useSetupMap(tf);
  const items = useMemo(() => longsNow(rows, data?.coins), [rows, data]);
  const [all, setAll] = useState(false);
  if (!rows?.length) return null;
  const shown = all ? items : items.slice(0, SHOWN);
  return <GlassCard className="ln-card">
    <div className="ms-eyebrow ln-eyebrow"><span className="ms-eyebrow-text">Long signals · {tf.toUpperCase()}</span>
      <HelpTip title="Long signals" width={420}>
        <p>Coins with a Strong, Light or Revival long on this timeframe, in the scanner's priority order. Perpetuals only.</p>
        <p><b>vs market 14d:</b> the coin's move over the last 14 days against the median coin on Hyperliquid.</p>
        <p><b>Traders:</b> profitable Hyperliquid traders net long in the coin; the green number opened in the last 24 hours.</p>
        <p><b>Band:</b> distance from the coin's weekly band (0 is the band, 1.6 stretched) and the four heat signs lit, as on the Radar.</p>
        <p>These describe what happened. In a test on six years of replays, ranking long signals by their move against the market did not pick better trades when many coins were long at once, so the order stays the scanner's priority.</p>
      </HelpTip>
      <span className="ms-eyebrow-meta">{items.length}</span>
    </div>
    {items.length === 0 ? <p className="ln-none">No long signals on this timeframe.</p> : <>
      <div className="ln-grid" role="table" aria-label="Long signals">
        <div className="ln-row ln-hd" role="row">
          <span role="columnheader">Coin</span><span role="columnheader">Signal</span><span role="columnheader" className="ln-r"><span className="ln-long">vs market 14d</span><span className="ln-short">vs mkt 14d</span></span>
          <span role="columnheader" className="ln-r">Traders</span><span role="columnheader" className="ln-band">Band</span>
        </div>
        {shown.map(({ row, c }) => {
          const v = c?.strength?.vs_market_pct ?? null, f = strengthBar(v);
          const pl = c?.traders?.pl || 0, n24 = c?.traders?.n24l || 0;
          return <button type="button" key={row.symbol} className="ln-row" role="row" onClick={e => onSelect?.(row, e)}>
            <span className="ln-coin" role="cell"><TokenLogo symbol={row.symbol} size={18} />{c?.coin || String(row.symbol).split("/")[0]}</span>
            <span role="cell" className={`ln-sig ${row.signal === "STRONG_LONG" ? "strong" : ""}`}>{SIGNAL_WORD[row.signal]}</span>
            <span role="cell" className="ln-str">
              <span className="ln-track" aria-hidden="true"><i className={f >= 0 ? "up" : "dn"} style={f >= 0 ? { left: "50%", width: `${50 * f}%` } : { right: "50%", width: `${-50 * f}%` }} /></span>
              <span className="ln-num">{pctText(v)}</span>
            </span>
            <span role="cell" className="ln-r ln-num">{c ? <>{pl}{n24 > 0 && <em className="ln-new"> +{n24}</em>}</> : "-"}</span>
            <span role="cell" className="ln-band">{c?.band_z ? <><span className="ln-num">{zText(c.band_z.z)}</span><Signs c={c} size={7} /></> : "-"}</span>
          </button>;
        })}
      </div>
      {items.length > SHOWN && <button type="button" className="te-link ln-more" onClick={() => setAll(a => !a)}>{all ? "Show fewer" : `All ${items.length}`}</button>}
    </>}
  </GlassCard>;
}
