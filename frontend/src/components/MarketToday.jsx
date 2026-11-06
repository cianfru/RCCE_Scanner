import { useMemo } from "react";
import { Info } from "./MarketHistorySections.jsx";
import { CYCOPY, marketCycles, shareBelow } from "../utils/marketCycles.js";
import { latestOf } from "../utils/walletHistory.js";

// The market page's top row, above its tabs: where the market stands today in four tiles, each a number and a small
// picture of it; the number opens its tab. Coins in uptrend against the 55% line; the broad downturn's (or uptrend's)
// day against how long past ones lasted; Fear & Greed on its 0-100 scale; profitable traders' long and short split.

const pct = v => `${Math.round(100 * v)}%`;

function Bar({ v, marks = [], tone = "accent", label }) {
  const at = Math.max(0, Math.min(100, v));
  return <span className={`mt-bar is-${tone}`} role="img" aria-label={label}>
    <span className="mt-bar-fill" style={{ width: `${at}%` }} />
    {marks.map(m => <span key={m} className="mt-bar-mark" style={{ left: `${m}%` }} />)}
  </span>;
}

// Each past one's length as a dot on one line, today's day as a short bar on it.
function Lengths({ c }) {
  const max = Math.max(c.today.days, ...c.past.map(p => p.days));
  const x = d => `${Math.min(100, (100 * d) / max)}%`;
  return <span className="mt-lengths" role="img"
    aria-label={`Past lengths ${c.past.map(p => p.days).sort((a, b) => a - b).join(", ")} days; today day ${c.today.days}`}>
    <span className="mt-lengths-axis" />
    {c.past.map(p => <span key={p.start} className="mt-lengths-dot" style={{ left: x(p.days) }} />)}
    <span className="mt-lengths-now" style={{ left: x(c.today.days) }} />
  </span>;
}

function Tile({ label, info, tab, onPick, aria, children }) {
  return <div className="mt-tile">
    <span className="mt-label">{label}{info}</span>
    <button type="button" className="mt-body" onClick={() => onPick(tab)} aria-label={aria}>{children}</button>
  </div>;
}

export default function MarketToday({ data, rows, wallets, onPick }) {
  const c = useMemo(() => marketCycles(rows), [rows]);
  const last = rows[rows.length - 1];
  const share = data?.today?.uptrend ?? last?.uptrend;
  const below = useMemo(() => shareBelow(rows.map(r => r.uptrend), share), [rows, share]);
  const fgRow = [...rows].reverse().find(r => r.fg != null);
  const crowd = latestOf(wallets, "crowd", "all");
  return <div className="mt">
    {share != null && <Tile label="Coins in uptrend" tab="breadth" onPick={onPick} aria={`${pct(share)} of coins in uptrend. Open the Uptrend share tab`}
      info={<Info title="Coins in uptrend" paras={[
        "The share of coins the engine calls Uptrend on their daily close. At 55% or more the market is in a broad uptrend (risk-on).",
        below == null ? null : `Today's ${pct(share)} is lower than on ${Math.round(100 * (1 - below))}% of days since 2021.`,
      ].filter(Boolean)} />}>
      <strong>{pct(share)}</strong>
      <Bar v={100 * share} marks={[55]} label={`${pct(share)} of coins in uptrend; the line is 55%`} />
      <em>broad uptrend at 55%</em>
    </Tile>}
    {c && <Tile label={c.kind === "down" ? "Broad downturn" : "Broad uptrend"} tab="cycles" onPick={onPick}
      aria={`Day ${c.today.days}. ${CYCOPY.sooner(c.sooner, c.past.length, c.kind)}. Open the Cycles tab`}
      info={<Info title={c.kind === "down" ? "Broad downturn" : "Broad uptrend"} paras={CYCOPY.pop(c.kind)} />}>
      <strong>Day {c.today.days}</strong>
      <Lengths c={c} />
      <em>{CYCOPY.sooner(c.sooner, c.past.length, c.kind)}</em>
    </Tile>}
    {fgRow && <Tile label="Fear & Greed" tab="fear" onPick={onPick} aria={`Fear and Greed ${fgRow.fg}. Open its tab`}
      info={<Info title="Fear & Greed" paras={["The crypto Fear & Greed index, one reading a day: 0 is extreme fear, 100 extreme greed. The lines sit at 25 and 75."]} />}>
      <strong>{fgRow.fg}</strong>
      <Bar v={fgRow.fg} marks={[25, 75]} tone="orange" label={`Fear and Greed ${fgRow.fg} of 100; lines at 25 and 75`} />
      <em>0 fear · 100 greed</em>
    </Tile>}
    {crowd && <Tile label="Profitable traders" tab="positioning" onPick={onPick}
      aria={`Profitable traders ${pct(crowd.L)} long, ${pct(crowd.S)} short. Open the Positioning tab`}
      info={<Info title="Profitable traders" paras={["The share of the profitable traders' open positions that are long and short, on all coins, at the latest reading."]} />}>
      <strong><b className="is-long">{pct(crowd.L)}</b><i aria-hidden="true"> · </i><b className="is-short">{pct(crowd.S)}</b></strong>
      <span className="mt-split" aria-hidden="true">
        <span className="is-long" style={{ flexGrow: crowd.L }} /><span className="is-short" style={{ flexGrow: crowd.S }} />
      </span>
      <em>long · short, all coins</em>
    </Tile>}
  </div>;
}
