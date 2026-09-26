import { useMemo, useState } from "react";
import { SECTOR_SHORT, traderWeight } from "../utils/sectors.js";
import { pocketGrid } from "../utils/sectorRace.js";
import Tabs from "./Tabs.jsx";

// Pockets: sector x ecosystem. Each cell is the pocket's median move against BTC,
// e.g. AI on Solana. Cells with fewer than three markets are thin and dimmed.
const RANGES = [{ key: 7, label: "7d" }, { key: 30, label: "30d" }, { key: 90, label: "90d" }];
const short = name => SECTOR_SHORT[name] || name;

function tint(rel) {
  const a = Math.min(1, Math.abs(rel) / 30);
  const hue = rel >= 0 ? "var(--pocket-up)" : "var(--pocket-down)";
  return `color-mix(in srgb, ${hue} ${Math.round(8 + a * 52)}%, transparent)`;
}

export default function PocketMatrix({ data, rows, value, onSelect }) {
  const [range, setRange] = useState(30);
  const grid = useMemo(() => pocketGrid(data, range), [data, range]);
  if (!grid.rows.length) return <p className="race-empty">Not enough pockets with two or more markets yet.</p>;
  return <div className="pockets">
    <div className="race-controls">
      <Tabs small label="Range" items={RANGES} value={range} onChange={setRange} />
      <span className="race-hint">Median move against BTC. Under each: markets · profitable traders' weight. Dashed: fewer than 3 markets. Click a cell to filter.</span>
    </div>
    <div className="pockets-scroll">
      <table className="pockets-table">
        <thead><tr><th />{grid.cols.map(c => <th key={c} scope="col">{c}</th>)}</tr></thead>
        <tbody>{grid.rows.map(s => <tr key={s}>
          <th scope="row">{short(s)}</th>
          {grid.cols.map(e => {
            const c = grid.cells[`${s}|${e}`];
            if (!c) return <td key={e} className="pocket-none" />;
            const key = `${s}|${e}`;
            const w = traderWeight(data?.lean, rows, "pocket", key);
            const thin = c.n < 3;
            return <td key={e}>
              <button type="button" className={`pocket${thin ? " thin" : ""}`} aria-pressed={value === key}
                style={{ background: tint(c.rel) }} onClick={() => onSelect(value === key ? null : key)}
                title={`${s} on ${e}: ${c.coins.join(", ")}${thin ? " (thin: fewer than 3 markets)" : ""}`}>
                <b>{c.rel >= 0 ? "+" : ""}{c.rel.toFixed(1)}%</b>
                <span>{c.n}{w != null ? ` · ${w.toFixed(1)}x` : ""}</span>
              </button>
            </td>;
          })}
        </tr>)}</tbody>
      </table>
    </div>
  </div>;
}
