import { useEffect, useState } from "react";
import HelpTip from "./HelpTip.jsx";
import { FG_NAMES, dialRotation, fgBand, fgNote } from "../utils/marketSummary.js";

// Fear & Greed as a dial: five bands on the backend's label cuts (20/40/60/80),
// lines where the engine uses it (40: fear gate, 70: Not greedy fails), a needle.
// Monochrome on purpose: the lit band, needle and word always agree.
const BANDS = [
  "M24.00,110.00 A86,86 0 0 1 39.25,61.10",
  "M41.63,57.83 A86,86 0 0 1 81.50,28.86",
  "M85.36,27.61 A86,86 0 0 1 134.64,27.61",
  "M138.50,28.86 A86,86 0 0 1 178.37,57.83",
  "M180.75,61.10 A86,86 0 0 1 196.00,110.00",
];
const TICKS = [
  { v: 40, line: [86.51, 37.72, 80.33, 18.70], label: { left: "34.97%", top: "6.86%" } },
  { v: 70, line: [154.67, 48.51, 166.43, 32.33], label: { left: "78.59%", top: "19.53%" } },
];

export default function FearGreedDial({ value, loaded }) {
  const v = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : null;
  const band = fgBand(v);
  const note = fgNote(v, loaded);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const word = band == null ? null : FG_NAMES[band];
  const aria = v == null ? `Fear and Greed: no reading. ${note}`
    : `Fear and Greed ${Math.round(v)} of 100, ${word}. Lines at 40 and 70. ${note}`;
  return <div className="ms-dial">
    <div className="ms-eyebrow"><span className="ms-eyebrow-text">Fear &amp; Greed<span className="ms-long"> · daily</span></span>
      <HelpTip title="Fear & Greed" width={400}>
        <p>The crypto Fear &amp; Greed index from alternative.me, with CoinGlass as a fallback: 0 is extreme fear, 100 extreme greed. It updates once a day and is the same for every market and both timeframes.</p>
        <p>Bands: 0–20 Extreme fear, 21–40 Fear, 41–60 Neutral, 61–80 Greed, 81–100 Extreme greed.</p>
        <p>The two lines are where the engine uses it. Below 70 the Not greedy check passes; at 70 or above it fails for every market. It is one of nine core checks, so Strong long signals can still appear. At 40 or below the fear gate opens: Accumulate setups in the Accumulation regime and Capitulation revivals can fire. Accumulate from absorption does not need it.</p>
      </HelpTip>
    </div>
    <div className="fg-face" role="img" aria-label={aria}>
      <svg viewBox="0 0 220 120" aria-hidden="true">
        {BANDS.map((d, i) => <path key={i} d={d} className={`fg-band${i === band ? " on" : ""}`} />)}
        {TICKS.map(t => <g key={t.v}>
          <line className="fg-tick-halo" x1={t.line[0]} y1={t.line[1]} x2={t.line[2]} y2={t.line[3]} />
          <line className="fg-tick" x1={t.line[0]} y1={t.line[1]} x2={t.line[2]} y2={t.line[3]} />
        </g>)}
        {v != null && <polygon className="fg-needle" points="110,36 106.8,110 113.2,110"
          style={{ transform: `rotate(${dialRotation(ready ? v : 0)}deg)` }} />}
        <circle className="fg-hub" cx="110" cy="110" r="7" />
        <circle className="fg-hub-hole" cx="110" cy="110" r="2.5" />
      </svg>
      {TICKS.map(t => <span key={t.v} className="fg-label" aria-hidden="true" style={t.label}>{t.v}</span>)}
      <span className="fg-label fg-end" aria-hidden="true" style={{ left: "10.91%" }}>0</span>
      <span className="fg-label fg-end" aria-hidden="true" style={{ left: "89.09%" }}>100</span>
    </div>
    <div className="fg-readout"><b>{v == null ? "—" : Math.round(v)}</b>{word && <span>{word}</span>}</div>
    <p className="fg-note">{note}</p>
  </div>;
}
