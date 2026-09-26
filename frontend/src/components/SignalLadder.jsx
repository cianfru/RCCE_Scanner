import { T, col } from "../theme.js";
import HelpTip from "./HelpTip.jsx";
import { signalCounts } from "../utils/marketSummary.js";

const explanations = {
  STRONG_LONG: 'The engine finds strong weighted support for a long setup in a supportive market phase. It checks trend, price extension, heat, divergence and available positioning data. Markup setups face stricter entry rules; crowding or repeated regime changes can reduce the label to Light long.',
  LIGHT_LONG: 'A long setup has support, but it does not meet the stricter Strong long criteria or a caution reduces its strength. Reasons can include a more extended price, crowded funding, unstable market phases or weaker confirmation.',
  ACCUMULATE: 'The engine sees potential basing, absorption or reaccumulation, without full confirmation for a stronger long label. It can also result when a reaccumulation setup lacks demand confirmation. This is an early setup to investigate, not a confirmed breakout.',
  WAIT: 'No entry or exit label on this timeframe.',
  TRIM: 'The engine detects overextension or a blowoff phase that triggers its reduction rules. It also fires as a forced exit when price is far below the weekly band. This count includes Trim and the more urgent Trim hard. An exit warning on either timeframe takes priority over entry signals.',
  RISK_OFF: 'The engine identifies a markdown phase together with risk-off market consensus, triggering its defensive exit label. This is not the same as a short-entry signal. Exit warnings take priority across timeframes.',
};

// One row per signal: label, share-of-market bar, count. Each row filters the grid.
export default function SignalLadder({ rows, timeframe, scopeLabel, active, onChange }) {
  const { n, counts, other } = signalCounts(rows);
  const items = [
    ["STRONG_LONG", "Strong long", T.green],
    ["LIGHT_LONG", "Light long", T.greenDim],
    ["ACCUMULATE", "Accumulate", col("#91b9e8")],
    ["WAIT", "Wait", "var(--t-text3)"],
    ["TRIM", "Trim", T.yellow],
    ["RISK_OFF", "Risk-off", T.red],
  ];
  const tf = String(timeframe || "").toUpperCase();
  return <div className="ms-signals">
    <div className="ms-eyebrow"><span className="ms-eyebrow-text">Signals · {tf}</span>
      <HelpTip title="Signal counts" width={440}>
        {items.map(([key, label]) => <p key={key}><strong>{label}.</strong> {explanations[key]}</p>)}
        <p>Bars show each count as a share of all {n} {scopeLabel}. Counts ignore the search box. Other labels (Revival, No long, Light short) are counted in the header when present. Click a row to show only those markets in the grid.</p>
        <p>Counts use this timeframe’s own signal, the one the backtests and the 4H executor act on. The combined 4H+1D decision is shown on each coin page. Counts are not win probabilities.</p>
      </HelpTip>
      <span className="ms-eyebrow-meta">{n} {scopeLabel}{other > 0 ? ` · ${other} other` : ""}</span>
    </div>
    <div className="signal-rows" role="group" aria-label="Filter the grid by signal">
      {items.map(([key, label, color]) => {
        const c = counts[key];
        const pressed = active === key;
        const pct = n ? (100 * c) / n : 0;
        return <button key={key} type="button" className="signal-row" data-key={key} style={{ "--signal-color": color }}
          aria-pressed={pressed} disabled={!c && !pressed}
          aria-label={`${label}: ${c} of ${n} markets. Filter the grid.`}
          title={pressed ? `Showing only ${label}. Click to show all.` : `${c} of ${n} ${scopeLabel} (${Math.round(pct)}%). Click to show only these in the grid.`}
          onClick={() => onChange?.(pressed ? null : key)}>
          <span className="signal-label">{label}</span>
          <span className="signal-bar" aria-hidden="true"><i style={{ width: c ? `max(3px, ${pct}%)` : 0 }} /></span>
          <span className="signal-count">{c}</span>
        </button>;
      })}
    </div>
  </div>;
}
