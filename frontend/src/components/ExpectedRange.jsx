import { T } from "../theme.js";
import HelpTip from "./HelpTip.jsx";

/**
 * Next-bar range forecast — magnitude only, never direction.
 *
 * Backend field `expected_range`:
 *   { probability, label, atr_mult, expected_range_pct, current_percentile, sample_size }
 *
 * `probability` is P(next bar's true range lands in the top quartile of this
 * market's trailing 100-bar range distribution). The unconditional baseline is
 * 25%, so the bar below is drawn against that reference: anything past the
 * tick is "more violent than usual", anything short of it is "quieter".
 */

const BASELINE = 0.25;

const TONE = {
  "VERY LOW": T.text4,
  "LOW": T.text3,
  "NORMAL": T.text2,
  "ELEVATED": "#fbbf24",
  "HIGH": "#f87171",
};

export default function ExpectedRange({ data, timeframe, isMobile }) {
  if (!data || data.expected_range_pct == null) return null;

  const { probability, label, expected_range_pct, current_percentile, atr_mult, sample_size } = data;
  const color = TONE[label] || T.text2;
  // Scale so the 25% baseline sits at 40% of the track; caps at 100%.
  const fill = Math.min(100, (probability / BASELINE) * 40);
  const tick = 40;
  const tf = timeframe === "1d" ? "24h" : "4h";

  return (
    <div style={{
      background: T.glassBg,
      border: `1px solid ${T.border}`,
      borderRadius: T.radius,
      padding: "12px 16px",
      marginBottom: 14,
      backdropFilter: "blur(20px) saturate(1.3)",
      WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
        <div style={{ width: 3, height: 12, borderRadius: 2, background: color, flexShrink: 0 }} />
        <span style={{
          fontSize: T.textXs, color: T.text3, letterSpacing: "0.1em",
          fontFamily: T.font, fontWeight: 700, textTransform: "uppercase",
        }}>
          Estimated true range · next {tf}
        </span>
        <HelpTip title="Expected Range" width={360}>
          <p>
            The large percentage shows the estimated total true-range magnitude, not a ± price target. The bar below shows the probability that the next bar's true range lands in the <strong>top quartile</strong> of
            this market's own trailing 100-bar range distribution. The unconditional baseline is 25%
            (marked on the bar); volatility clusters, so a large bar raises the odds of another one.
          </p>
          <p>
            <strong>Magnitude only — it says nothing about direction.</strong> Next-bar direction was
            tested with the identical method and behaved like a coin flip. Use this for stop width and
            position sizing, not as a trade signal.
          </p>
          <p style={{ color: T.text4 }}>
            Calibrated on {sample_size ? sample_size.toLocaleString() : "—"} historical {tf} bars in this
            volatility bucket. Size expectation is {atr_mult}&times; ATR(14).
          </p>
        </HelpTip>
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
        <span style={{
          fontFamily: T.mono, fontSize: isMobile ? 20 : 24, fontWeight: 700,
          color: T.text1, lineHeight: 1,
        }}>
          {expected_range_pct.toFixed(2)}%
        </span>
        <span className="terminal-status" style={{
          padding: "3px 8px", borderRadius: "20px",
          border: `1px solid ${color}55`, background: `${color}14`,
          fontSize: 9, fontFamily: T.mono, fontWeight: 600,
          letterSpacing: "0.08em", color,
        }}>
          {label}
        </span>
      </div>

      <div style={{
        position: "relative", height: 5, borderRadius: 3,
        background: T.overlay06, overflow: "visible", marginBottom: 8,
      }}>
        <div style={{
          width: `${fill}%`, height: "100%", borderRadius: 3,
          background: color, transition: "width 200ms ease",
        }} />
        <div
          title="25% — the unconditional baseline"
          style={{
            position: "absolute", left: `${tick}%`, top: -3, bottom: -3,
            width: 1, background: T.text4,
          }}
        />
      </div>

      <div style={{
        display: "flex", justifyContent: "space-between",
        fontSize: T.textXs, fontFamily: T.mono, color: T.text4,
      }}>
        <span>P(wide bar) <span style={{ color: T.text2 }}>{Math.round(probability * 100)}%</span> vs 25% base</span>
        <span>current bar {current_percentile}th pct</span>
      </div>
    </div>
  );
}
