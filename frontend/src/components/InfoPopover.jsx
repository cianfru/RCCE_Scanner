import { useState, useRef, useEffect } from "react";
import ReactDOM from "react-dom";
import { T } from "../theme.js";

const COLUMN_INFO = {
  PRI: {
    title: "Priority Score",
    desc: "Composite 0\u2013100 ranking that helps identify which symbols to focus on first. Combines six weighted factors from all three engines.",
    values: [
      ["Conditions (25)", "% of entry conditions met \u2014 more conditions = stronger setup"],
      ["BMSB Prox (25)", "How close price is to the Bull Market Support Band \u2014 closer/above = better"],
      ["Floor (15)", "Binary bonus when exhaustion engine confirms a downside floor"],
      ["Momentum (15)", "Recent rate of price change \u2014 positive momentum scores higher"],
      ["Heat Room (10)", "Inverted heat score \u2014 low heat means more upside room"],
      ["Volume (10)", "Relative volume + absorption detection \u2014 higher activity scores more"],
    ],
  },
  REGIME: {
    title: "Market Regime",
    desc: "Z-score based regime detection using price deviation from statistical mean. Identifies the current market phase in the cycle.",
    values: [
      ["MARKUP", "Price trending above mean \u2014 bullish momentum"],
      ["BLOWOFF", "Extreme overextension \u2014 potential reversal zone"],
      ["RE-ACC", "Re-accumulation \u2014 pullback within uptrend"],
      ["MARKDOWN", "Price trending below mean \u2014 bearish momentum"],
      ["CAPITULATION", "Extreme underextension \u2014 panic selling"],
      ["ACCUM", "Accumulation \u2014 building base after decline"],
    ],
  },
  SIGNAL: {
    title: "Trading Signal",
    desc: "Consensus signal derived from all three engines (RCCE, Heatmap, Exhaustion) plus conditions scoring.",
    values: [
      ["STRONG LONG", "High-conviction buy \u2014 multiple engines aligned"],
      ["LIGHT LONG", "Moderate buy \u2014 some engines supportive"],
      ["ACCUMULATE", "Gradual position building opportunity"],
      ["TRIM", "Reduce exposure \u2014 signs of weakening"],
      ["TRIM HARD", "Aggressively reduce \u2014 high risk detected"],
      ["RISK OFF", "Exit entirely \u2014 conditions deteriorating"],
      ["WAIT", "No clear edge \u2014 stay sidelined"],
    ],
  },
  COND: {
    title: "Conditions Met",
    desc: "Number of entry conditions satisfied out of total checked. Higher ratio means more factors align for a trade. Conditions include trend, volume, momentum, and regime checks.",
  },
  SPARK: {
    title: "Sparkline",
    desc: "Mini price chart showing recent price action. Green means price is up, red means price is down over the displayed period.",
  },
  "Z-SCORE": {
    title: "Z-Score",
    desc: "Statistical measure of how far price deviates from its mean, in standard deviations. Range typically -3 to +3.",
    values: [
      ["> +2", "Strongly overbought \u2014 price far above mean"],
      ["+1 to +2", "Above average \u2014 moderate bullish deviation"],
      ["-1 to +1", "Near mean \u2014 neutral territory"],
      ["-2 to -1", "Below average \u2014 moderate bearish deviation"],
      ["< -2", "Strongly oversold \u2014 price far below mean"],
    ],
  },
  MOM: {
    title: "Momentum",
    desc: "Rate of change in price expressed as a percentage. Positive values indicate upward momentum, negative values indicate downward pressure.",
  },
  PRICE: {
    title: "Current Price",
    desc: "Latest price from the exchange. Updates each scan cycle (every 5 minutes).",
  },
  HEAT: {
    title: "BMSB Heat Score",
    desc: "Heatmap engine output (0-100) measuring deviation from the BMSB bands. Higher heat means price is stretched further from equilibrium.",
    values: [
      ["0\u201320", "Cool \u2014 price near bands, low deviation"],
      ["20\u201340", "Warm \u2014 moderate stretch"],
      ["40\u201360", "Hot \u2014 significant deviation building"],
      ["60\u201380", "Very hot \u2014 extended, caution warranted"],
      ["80\u2013100", "Extreme \u2014 likely reversal zone"],
    ],
  },
  DIV: {
    title: "Divergence",
    desc: "Detects when price makes new highs/lows but the oscillator does not confirm. A leading reversal signal.",
    values: [
      ["BULL", "Bullish divergence \u2014 price falling but momentum rising"],
      ["BEAR", "Bearish divergence \u2014 price rising but momentum fading"],
    ],
  },
  EXHAUST: {
    title: "Exhaustion State",
    desc: "Exhaustion engine output detecting capitulation or climactic volume events that often mark turning points.",
    values: [
      ["FLOOR", "Downside exhaustion detected \u2014 selling drying up"],
      ["CLIMAX", "Volume climax \u2014 extreme activity spike"],
      ["ABSORB", "Absorption \u2014 large orders soaking up supply/demand"],
      ["BEAR", "Bearish exhaustion conditions present"],
    ],
  },
  FUNDING: {
    title: "Funding Rate",
    desc: "Perpetual futures funding rate from the exchange. Positive means longs pay shorts (bullish crowding), negative means shorts pay longs (bearish crowding).",
  },
  OI: {
    title: "Open Interest Trend",
    desc: "Direction and behavior of open interest in perpetual futures. Reveals positioning dynamics.",
    values: [
      ["BUILDING", "OI rising \u2014 new positions being opened"],
      ["SQUZ", "Squeeze \u2014 forced liquidations likely"],
      ["LIQ", "Liquidations occurring \u2014 cascading closes"],
      ["SHORT", "Short interest dominant"],
    ],
  },
  CONF: {
    title: "Confluence Score",
    desc: "Alignment score (0-100) between 4H and 1D timeframes. Higher score means both timeframes agree on regime and signal direction.",
  },
  ENERGY: {
    title: "Energy",
    desc: "Volatility-adjusted momentum measure from the RCCE engine. Indicates the strength of the current move relative to recent volatility.",
  },
  PHASE: {
    title: "Heat Phase",
    desc: "Qualitative phase derived from the heatmap engine's deviation analysis.",
    values: [
      ["Entry", "Low heat \u2014 favorable entry zone"],
      ["Extension", "Rising heat \u2014 trend extending"],
      ["Exhaustion", "High heat \u2014 move may be exhausting"],
      ["Fading", "Heat declining \u2014 reversion underway"],
    ],
  },
  FLOOR: {
    title: "Floor Confirmed",
    desc: "Boolean flag from the exhaustion engine. When true (checkmark), a downside floor has been confirmed \u2014 selling pressure has dried up and a base is forming.",
  },
  FORMING: {
    title: "Floor Forming",
    desc: "Downside floor detection from the exhaustion engine. A checkmark means selling pressure has dried up and the engine has confirmed a base is forming — often precedes a reversal.",
  },
  PRICE: {
    title: "Current Price",
    desc: "Latest price from the exchange. Updates each scan cycle (~5 minutes).",
  },
};

function InfoPopover({ info, anchor, onClose }) {
  const ref = useRef(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (anchor) {
      const r = anchor.getBoundingClientRect();
      const popW = 280;
      let left = r.left;
      if (left + popW > window.innerWidth - 12) left = window.innerWidth - popW - 12;
      if (left < 12) left = 12;
      setPos({ top: r.bottom + 6, left });
    }
  }, [anchor]);

  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onClose]);

  return ReactDOM.createPortal(
    <div ref={ref} style={{
      position: "fixed", top: pos.top, left: pos.left, zIndex: 9999,
      width: 280, padding: "14px 16px",
      background: T.popoverBg,
      backdropFilter: "blur(20px) saturate(1.4)",
      border: `1px solid ${T.border}`,
      borderRadius: T.radiusSm, boxShadow: `0 8px 32px ${T.shadowDeep}`,
      maxHeight: "70vh", overflowY: "auto",
    }}>
      <div style={{
        fontFamily: T.font, fontSize: 12, fontWeight: 700, color: T.text1,
        marginBottom: 6, letterSpacing: "0.02em",
      }}>{info.title}</div>
      <div style={{
        fontFamily: T.font, fontSize: 11, color: T.text3, lineHeight: 1.5,
        marginBottom: info.values ? 10 : 0,
      }}>{info.desc}</div>
      {info.values && (
        <div style={{
          display: "flex", flexDirection: "column", gap: 4,
          borderTop: `1px solid ${T.border}`, paddingTop: 8,
        }}>
          {info.values.map(([label, desc]) => (
            <div key={label} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
              <span style={{
                fontFamily: T.mono, fontSize: 9, fontWeight: 600, color: T.accent,
                minWidth: 70, flexShrink: 0, letterSpacing: "0.03em",
              }}>{label}</span>
              <span style={{
                fontFamily: T.font, fontSize: 10, color: T.text4, lineHeight: 1.4,
              }}>{desc}</span>
            </div>
          ))}
        </div>
      )}
    </div>,
    document.body
  );
}

export default function InfoButton({ label }) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef(null);
  const info = COLUMN_INFO[label];
  if (!info) return null;

  return (
    <span style={{ display: "inline-flex", marginLeft: 4 }}>
      <span
        ref={btnRef}
        onClick={(e) => { e.stopPropagation(); setOpen(!open); }}
        style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          width: 14, height: 14, borderRadius: "50%",
          border: `1px solid ${open ? T.accent : T.overlay15}`,
          color: open ? T.accent : T.text4,
          fontSize: 8, fontWeight: 700, fontFamily: T.font,
          cursor: "pointer", transition: "all 0.2s",
          lineHeight: 1, userSelect: "none",
        }}
        onMouseEnter={(e) => { if (!open) { e.currentTarget.style.borderColor = T.overlay30; e.currentTarget.style.color = T.text2; }}}
        onMouseLeave={(e) => { if (!open) { e.currentTarget.style.borderColor = T.overlay15; e.currentTarget.style.color = T.text4; }}}
      >i</span>
      {open && <InfoPopover info={info} anchor={btnRef.current} onClose={() => setOpen(false)} />}
    </span>
  );
}
