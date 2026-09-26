import { altBaseline, groupStats, SECTOR_SHORT } from "../utils/sectors.js";
import MemberRug from "./MemberRug.jsx";
import HelpTip from "./HelpTip.jsx";
import Tabs from "./Tabs.jsx";
import useSectors from "../hooks/useSectors.js";
import { useState } from "react";
import SectorRace from "./SectorRace.jsx";
import PocketMatrix from "./PocketMatrix.jsx";

const VIEWS = [{ key: "race", label: "Race vs BTC" }, { key: "pockets", label: "Pockets" }];

const MINUS = "\u2212";
const signed = (x, digits = 0) => `${x >= 0 ? "+" : MINUS}${Math.abs(x).toFixed(digits)}`;
const pct = x => (x === 0 ? "0%" : `${signed(x)}%`);

function chipTitle(g, span) {
  const lines = [`${g.name} · ${g.n} markets${g.small ? " (fewer than 10: read as tentative)" : ""}${g.missing ? ` (${g.missing} without price history)` : ""}`];
  if (g.tail) {
    lines.push(g.name === "Other" ? "Catch-all group, not ranked." : "Too few to rank.");
  } else if (g.shown != null) {
    lines.push(`Lead ${pct(g.shown)}: median ${signed(g.med, 1)}% vs the typical alt × ${g.n}/${g.n + 10}`);
    lines.push(`${g.ahead} of ${g.n} ahead of the typical alt`);
  }
  if (g.members.length) {
    const best = g.members[0], worst = g.members[g.members.length - 1];
    const own = m => (Number.isFinite(m.move) ? ` (itself ${pct(Math.round(100 * m.move))})` : "");
    lines.push(`Best vs typical alt: ${best.sym} ${signed(best.e)} pts${own(best)} · weakest ${worst.sym} ${signed(worst.e)} pts${own(worst)}`);
  }
  if (g.exTop) lines.push(`Without ${g.exTop.sym}: lead ${pct(g.exTop.shown)}`);
  lines.push(`Median vs BTC ${g.vsBtc == null ? "—" : `${signed(g.vsBtc, 1)}%`} · ${g.uptrend} in Uptrend · ${g.longs} long signals · ${g.locked} locked`);
  if (g.traders.n) lines.push(`Profitable traders: ${g.traders.long} long / ${g.traders.short} short${g.weight != null ? `, ${g.weight.toFixed(1)}x market weight` : ""}`);
  lines.push(`Moves over the last ${span}.`);
  return lines.join("\n");
}

function chipAria(g) {
  const pts = x => (x === 0 ? "level with the typical alt" : `${x > 0 ? "plus" : "minus"} ${Math.abs(x)} ${Math.abs(x) === 1 ? "point" : "points"}`);
  const name = SECTOR_SHORT[g.name] ? `${SECTOR_SHORT[g.name]} (${g.name})` : g.name;   // visible text first
  if (g.tail) return `${name}, ${g.n} markets, not ranked. Filter the grid.`;
  return [`${name}, ${g.n} markets${g.small ? ", fewer than 10" : ""}.`,
    g.shown != null ? `Lead ${pts(g.shown)} over the typical alt after size adjustment; median ${pts(Number(g.med.toFixed(1)))}.` : "",
    `${g.ahead} of ${g.n} ahead${g.locked ? `, ${g.locked} locked` : ""}.`,
    g.exTop ? `Without ${g.exTop.sym}, lead ${pts(g.exTop.shown)}.` : "", "Filter the grid."].filter(Boolean).join(" ");
}

// Which parts of the market are moving: one chip per sector (or chain), ranked by its
// size-adjusted lead over the typical alt. Clicking a chip filters the grid and the best setups.
export default function SectorStrip({ rows, baseRows, by, onByChange, value, onChange, timeframe }) {
  const sectors = useSectors();
  const [view, setView] = useState(null);             // null | "race" | "pockets"
  const base = altBaseline(baseRows || rows);           // zero stays the market's typical alt when a watch group is active
  const groups = groupStats(rows, by, sectors?.lean, base);
  if (!groups.length) return null;
  const span = timeframe === "4h" ? "4d" : "24d";
  const ranked = groups.filter(g => !g.tail);
  const tail = groups.filter(g => g.tail);
  const vsBtc = base.vsBtc == null ? null : `${signed(base.vsBtc, 1)}%`;
  const chip = g => {
    const active = value === g.name;
    return <button key={g.name} type="button" aria-pressed={active} className={`sector-chip${g.tail ? " tail" : ""}`}
      data-dir={g.dir} data-small={g.small && !g.tail ? "" : undefined} onClick={() => onChange(active ? null : g.name)}
      title={chipTitle(g, span)} aria-label={chipAria(g)}>
      <span className="sector-name">{SECTOR_SHORT[g.name] || g.name}<small>{g.tail ? g.rows : g.n}</small></span>
      {!g.tail && <>
        <span className="sector-rel">{g.shown == null ? "—" : pct(g.shown)}</span>
        <MemberRug members={g.members} median={g.med} D={base.D} />
        <span className="sector-meta">{g.ahead}/{g.n} ahead{g.locked ? <>{" "}<span className="nowrap">· {g.locked} locked</span></> : ""}</span>
        {g.exTop && <span className="sector-extop">ex-{g.exTop.sym} {pct(g.exTop.shown)}</span>}
        {sectors?.lean && <span className="sector-traders">
          <b className={g.weight == null ? "" : g.weight >= 1.25 ? "over" : g.weight <= 0.8 ? "under" : ""}>{g.weight != null ? `${g.weight.toFixed(1)}x` : "—"}</b>
          <span>{g.traders.side ? `${Math.round((100 * g.traders.long) / g.traders.n)}% long` : "few traders"}</span>
        </span>}
      </>}
    </button>;
  };
  return <section className="sector-strip" aria-label="Sectors">
    <div className="sector-strip-head">
      <Tabs small label="Group by" items={[{ key: "sector", label: "Sectors" }, { key: "ecosystem", label: "Ecosystems" }]} value={by} onChange={k => { onByChange(k); onChange(null); }} />
      <HelpTip title="Sectors and ecosystems" width={420}>
        <p>Each chip is a group of markets: what the project does (sector) or the chain it lives on (ecosystem). Grouping is a curated label, not a signal input.</p>
        <p>Zero is the typical alt: the median move of all {base.nAlts} markets except BTC and the RWA & Stablecoins group over the last {span}.{base.vsBtc == null ? "" : base.vsBtc >= 5 ? ` Today the typical alt is ${vsBtc} vs BTC, so most groups are ahead of BTC too; zero here removes that.` : base.vsBtc <= -5 ? ` Today the typical alt is ${vsBtc} vs BTC, so most groups are behind BTC too; zero here removes that.` : ` Today the typical alt is ${vsBtc} vs BTC.`}</p>
        <p>The number is the group's lead: its median move minus the typical alt's, in percentage points, scaled by n/(n+10) for a group of n markets. A group of 5 keeps a third of its lead, 10 keeps half, 30 three quarters. We use 10 because, over 276 past 24-day windows, the median of a few coins in a sector predicted the rest of that sector about that well. Chips are ordered by this number; ties go to the larger group.</p>
        <p>The strip has one tick per market, on the same ±{base.D}-point scale in every chip. The thin line is the typical alt, the bold mark is the group's median, and arrows at an end mark markets beyond the scale (up to three). "Ahead" counts markets that beat the typical alt. "ex-ZEC" style notes show the lead without the group's best market when that market adds 1.5 points or more.</p>
        <p>Dashed chips have fewer than 10 markets. Groups with fewer than 3 markets, and Other, come last without a rank. Locked counts setups where the trend and an entry signal agree.</p>
        <p>The last line is where profitable traders put their money: the group's share of their positions against its share of the market's open interest (1.0x is market weight, 2.0x twice it), then the share of them positioned long. Profitable traders are the top 300 Hyperliquid wallets by monthly return that were also in profit before this month. Because they are picked by this month's result, they tend to be long in a rising month, so the weight says more than the direction.</p>
        <p>Sector strength is descriptive. In our tests, 30-day sector leaders kept beating the weakest sectors over the next 10 days, but not BTC; ecosystem leadership showed nothing. That test used 30-day leadership; this chip ranking ({span}) was not tested for persistence. Race vs BTC and Pockets use daily closes against BTC, so their numbers differ from the chips.</p>
      </HelpTip>
      <p className="sector-baseline">
        <span className="ms-long">Size-adjusted lead over the typical alt{vsBtc ? <> (itself <b>{vsBtc}</b> vs BTC over <b>{span}</b>)</> : ""} · dashed: under 10 markets</span>
        <span className="ms-short">vs typical alt{vsBtc ? <> (<b>{vsBtc}</b> vs BTC, <b>{span}</b>)</> : ""} · size-adjusted · {"dashed:\u00a0under\u00a010"}</span>
      </p>
      <div className="sector-views" role="group" aria-label="Charts">
        {VIEWS.map(v => <button key={v.key} type="button" aria-pressed={view === v.key} onClick={() => setView(view === v.key ? null : v.key)}>{v.label}</button>)}
      </div>
      {value && <button type="button" className="sector-clear" onClick={() => onChange(null)}>{value.includes("|") ? `${value.replace("|", " on ")} · show all` : "Show all"}</button>}
    </div>
    <div className="sector-chips">
      {ranked.map(chip)}
      {tail.length > 0 && <span className="sector-divider" aria-hidden="true" />}
      {tail.map(chip)}
    </div>
    {view === "race" && <SectorRace data={sectors} rows={rows} by={by} value={value} leaders={ranked.slice(0, 3).map(g => g.name)} />}
    {view === "pockets" && <PocketMatrix data={sectors} rows={rows} value={value} onSelect={onChange} />}
  </section>;
}
