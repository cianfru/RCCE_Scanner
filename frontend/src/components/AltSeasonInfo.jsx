import HelpTip from './HelpTip.jsx';

export default function AltSeasonInfo({ gauge }) {
  return <HelpTip title={`${gauge.label} · ${gauge.score?.toFixed(1)} / 100`} label="How alt season is calculated">
    <p>{gauge.alts_up} of {gauge.total_alts} scanned altcoins are in markup or re-accumulation.</p>
    <p>When market-cap data is available, the score blends bullish breadth (60%) with normalized non-Bitcoin dominance (40%). Otherwise it uses breadth alone. It is reduced when Bitcoin is bullish but fewer than 30% of alts are bullish.</p>
    <p>Active: 50–74.9. Hot: 75+. This measures the scanner’s market breadth, not 90-day outperformance against Bitcoin.</p>
  </HelpTip>;
}
