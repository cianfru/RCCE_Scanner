import { useId, useState } from 'react';

export default function AltSeasonInfo({ gauge }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return <span className="alt-season-info" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
    <button type="button" aria-label="How alt season is calculated" aria-expanded={open} aria-describedby={open ? id : undefined}
      onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onClick={() => setOpen(true)} onKeyDown={e => e.key === 'Escape' && setOpen(false)}>i</button>
    {open && <span id={id} role="tooltip" className="alt-season-explanation">
      <strong>{gauge.label} · {gauge.score?.toFixed(1)} / 100</strong>
      <span>{gauge.alts_up} of {gauge.total_alts} scanned altcoins are in markup or re-accumulation.</span>
      <span>When market-cap data is available, the score blends bullish breadth (60%) with normalized non-Bitcoin dominance (40%). Otherwise it uses breadth alone. It is reduced when Bitcoin is bullish but fewer than 30% of alts are bullish.</span>
      <span>Active: 50–74.9. Hot: 75+. This measures the scanner’s market breadth, not 90-day outperformance against Bitcoin.</span>
    </span>}
  </span>;
}
