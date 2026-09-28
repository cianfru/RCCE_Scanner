import { useState } from "react";
import { sideBarColor, sideColor } from "../utils/traderFormat.js";
import HelpTip from "./HelpTip.jsx";
import TraderEntries from "./TraderEntries.jsx";
import WalletOpens from "./WalletOpens.jsx";
import { formatPercent } from "../utils/marketPresentation.js";
import { traderLean, longShare, usd, WALLET_CHECK_CONFIDENCE } from "../utils/traders.js";

function Split({ longPct, left, right }) {
  return <>
    <div className="tc-bar"><i style={{ width: `${longPct}%`, background: sideBarColor("long") }} /><i style={{ flex: 1, background: sideBarColor("short") }} /></div>
    <div className="tc-split"><span style={{ color: sideColor("long") }}>{left}</span><span style={{ color: sideColor("short") }}>{right}</span></div>
  </>;
}

// Tracked traders on one coin: two bars (profitable traders, all tracked wallets), the largest
// profitable holders, and the new positions one click deeper.
export default function TradersCard({ symbol, sm, traders, onShowEntries, spot }) {
  const [openings, setOpenings] = useState(false);
  const coin = (symbol || "").split("/")[0];
  const pro = traderLean(sm?.profitable);
  const proPct = longShare(pro);
  const walletsN = (sm?.long_count || 0) + (sm?.short_count || 0);
  const allPct = walletsN ? Math.round((sm.long_count / walletsN) * 100) : 50;
  const weak = (sm?.confidence ?? 0) < WALLET_CHECK_CONFIDENCE;
  const lean = sm?.trend === "BULLISH" ? "lean long" : sm?.trend === "BEARISH" ? "lean short" : "mixed";

  return (
    <section className="analysis-card tc">
      <div className="tc-head">
        <h3>Traders on {coin}{spot ? " (Hyperliquid perps)" : ""} <HelpTip title="How this is read" width={420}>
          <p>Profitable traders: the top 300 Hyperliquid wallets by monthly return that were also in profit before this month. In a rising month most are long, so a market they avoid says more than one they hold.</p>
          <p>All tracked wallets: profitable traders and the 300 largest accounts. The direction blends dollar imbalance (70%) and wallet-count imbalance (30%); dollar weight rises to 85% when the notional imbalance exceeds 50%. Above +0.15 it leans long, below −0.15 short. This is the reading the signal's tracked-wallet check uses{sm ? `; conviction now ${formatPercent(sm.confidence, { ratio: true })}, not a probability of profit` : ""}.</p>
          <p>Entries come from Hyperliquid's public fills (each trader's latest 2,000). P&amp;L is on margin. Click a trader for the fills and their other positions; Follow sends their changes to Telegram.</p>
        </HelpTip></h3>
      </div>
      <div className="tc-summary">
        <div>
          <div className="tc-label">Profitable traders</div>
          {pro.n > 0
            ? <Split longPct={proPct} left={`${pro.long} long · ${usd(sm.profitable.long_usd)}`} right={`${pro.short} short · ${usd(sm.profitable.short_usd)}`} />
            : <p className="tc-note">None hold it right now.</p>}
          {pro.n > 0 && pro.n < 3 && <p className="tc-note">Fewer than three hold it, too few to read a lean.</p>}
        </div>
        {sm && walletsN > 0 && (
          <div>
            <div className="tc-label">All tracked wallets <span className="tc-dim">· {lean}{weak ? " (weak)" : ""}</span></div>
            <Split longPct={allPct} left={`${sm.long_count} long · ${allPct}%`} right={`${sm.short_count} short · ${100 - allPct}%`} />
          </div>
        )}
      </div>
      {(traders?.entries || traders?.loading) && <TraderEntries entries={traders.entries} loading={traders.loading} onShow={onShowEntries} />}
      {traders?.opens && <>
        <button type="button" className="te-link tc-more" aria-expanded={openings} onClick={() => setOpenings(v => !v)}>{openings ? "Hide new positions" : "New positions"}</button>
        {openings && <WalletOpens opens={traders.opens} />}
      </>}
    </section>
  );
}
