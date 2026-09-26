import { groupStats, SECTOR_SHORT } from "../utils/sectors.js";
import HelpTip from "./HelpTip.jsx";
import Tabs from "./Tabs.jsx";
import useSectors from "../hooks/useSectors.js";

// Which parts of the market are moving: one chip per sector (or chain), strongest
// against BTC first. Clicking a chip filters the grid and the best setups.
export default function SectorStrip({ rows, by, onByChange, value, onChange, timeframe }) {
  const sectors = useSectors();
  const groups = groupStats(rows, by, sectors?.lean);
  if (!groups.length) return null;
  const span = timeframe === "4h" ? "4d" : "24d";
  return <section className="sector-strip" aria-label="Sectors">
    <div className="sector-strip-head">
      <Tabs small label="Group by" items={[{ key: "sector", label: "Sectors" }, { key: "ecosystem", label: "Ecosystems" }]} value={by} onChange={k => { onByChange(k); onChange(null); }} />
      <HelpTip title="Sectors and ecosystems" width={380}>
        <p>Each chip is a group of markets: what the project does (sector) or the chain it lives on (ecosystem). Sorted by the group's median move over the last {span} against BTC, so the groups leading the market come first.</p>
        <p>Uptrend counts markets in the Uptrend regime; locked counts setups where the trend and an entry signal agree. Grouping is a curated label, not a signal input.</p>
        <p>The last line is where profitable traders put their money: the group's share of their positions against its share of the market's open interest (1.0x is market weight, 2.0x twice it), then the share of them positioned long. Profitable traders are the top 300 Hyperliquid wallets by monthly return that were also in profit before this month. Because they are picked by this month's result, they tend to be long in a rising month, so the weight says more than the direction.</p>
      </HelpTip>
      {value && <button type="button" className="sector-clear" onClick={() => onChange(null)}>Show all</button>}
    </div>
    <div className="sector-chips">
      {groups.map(g => {
        const active = value === g.name;
        const rel = g.vsBtc == null ? null : g.vsBtc * 100;
        return <button key={g.name} type="button" aria-pressed={active} className="sector-chip" onClick={() => onChange(active ? null : g.name)}
          title={`${g.name}: ${g.n} markets, ${g.uptrend} in Uptrend, ${g.longs} long signals, ${g.locked} locked in${g.traders.n ? `\nProfitable traders: ${g.traders.long} long / ${g.traders.short} short${g.weight != null ? `, ${g.weight.toFixed(1)}x market weight` : ""}` : ""}`}>
          <span className="sector-name">{SECTOR_SHORT[g.name] || g.name}</span>
          <span className={`sector-rel ${rel == null ? "" : rel >= 0 ? "up" : "down"}`}>{rel == null ? "—" : `${rel >= 0 ? "+" : ""}${rel.toFixed(1)}%`}</span>
          <span className="sector-meta">{g.uptrend}/{g.n} up{g.locked ? ` · ${g.locked} locked` : ""}</span>
          {sectors?.lean && <span className="sector-traders">
            <b className={g.weight == null ? "" : g.weight >= 1.25 ? "over" : g.weight <= 0.8 ? "under" : ""}>{g.weight != null ? `${g.weight.toFixed(1)}x` : "—"}</b>
            <span>{g.traders.side ? `${Math.round((100 * g.traders.long) / g.traders.n)}% long` : "few traders"}</span>
          </span>}
        </button>;
      })}
    </div>
  </section>;
}
