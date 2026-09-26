import Tabs from "./Tabs.jsx";
import { useState, useEffect } from "react";
import HelpTip from "./HelpTip.jsx";
import { REGIME_META, T, m, SIGNAL_META, col } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "";

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

// Below this many events a rate or average is shown but not coloured: it is noise.
const MIN_N = 30;

function rateColor(rate, n = MIN_N) {
  if (rate == null || n < MIN_N) return T.text4;
  if (rate >= 70) return col("#34d399");
  if (rate >= 55) return col("#fbbf24");
  if (rate >= 40) return T.text3;
  return col("#f87171");
}

function edgeColor(edge, n = MIN_N) {
  if (edge == null || n < MIN_N) return T.text4;
  if (edge > 3) return col("#34d399");
  if (edge > 0) return col("#6ee7b7");
  if (edge > -3) return col("#fbbf24");
  return col("#f87171");
}

// Backend keys read as old jargon ("smart money", "whale"); say what each check measures.
const CONDITION_LABEL = {
  bullish_regime: "Uptrend or accumulation regime",
  consensus: "Market consensus supportive",
  z_range: "Z-score in range",
  no_bear_div: "No bearish divergence",
  heat_ok: "Not overheated",
  no_climax: "No exhaustion climax",
  funding_ok: "Funding not crowded",
  not_greedy: "Fear & Greed below greed",
  liquidity_ok: "Stablecoin supply not contracting",
  oi_confirms: "Open interest confirms",
  cvd_confirms: "Taker buying (CVD) confirms",
  smart_money_ok: "Top-trader L/S ok (CoinGlass)",
  macro_tailwind: "Macro tailwind (ETF flows)",
  hl_whale_aligned: "Tracked wallets agree",
  hl_not_counter: "Tracked wallets not opposed",
};
const conditionLabel = name => CONDITION_LABEL[name] || name.replace(/_/g, " ");

// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// SectionHeader — title + subtitle explanation
// ---------------------------------------------------------------------------

function SectionHeader({ title, subtitle }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{
        fontSize: T.textXs,
        color: T.text3,
        fontFamily: T.mono,
        fontWeight: 700,
        letterSpacing: "0.1em",
        textTransform: "uppercase",
      }}>
        {title}
      </div>
      {subtitle && (
        <div style={{
          fontSize: T.textXs,
          color: T.text4,
          fontFamily: T.font,
          fontWeight: 400,
          lineHeight: 1.5,
          marginTop: 4,
        }}>
          {subtitle}
        </div>
      )}
    </div>
  );
}

// Flat coloured text, as the scanner's status labels.
function GroupBadge({ group }) {
  const hue = col({ core: "#97FCE4", coinglass: "#a78bfa", hyperlens: "#fbbf24" }[group] || "#97FCE4");
  return (
    <span style={{ fontSize: T.textXs, fontFamily: T.mono, color: hue, fontWeight: 600 }}>
      {group}
    </span>
  );
}

function NoData({ label }) {
  return (
    <div style={{
      color: T.text4, fontSize: m(T.textSm, false), fontFamily: T.mono,
      padding: 24, textAlign: "center",
    }}>
      {label || "Not enough data yet"}
    </div>
  );
}

// Table header style — matches BacktestPanel
const TH = {
  padding: "6px 10px",
  color: T.text4,
  fontWeight: 600,
  fontSize: T.textXs,
  fontFamily: T.mono,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  whiteSpace: "nowrap",
};

// ---------------------------------------------------------------------------
// Section 1: Condition Predictive Value
// ---------------------------------------------------------------------------

function ConditionValueTable({ conditions, isMobile }) {
  if (!conditions || conditions.length === 0) return <NoData />;

  const fs = m(T.textXs, isMobile);
  // Phones: Condition, Edge and win rate when met only; the rest would sit off-screen.
  const full = !isMobile;

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{
        width: "100%",
        borderCollapse: "collapse",
        fontFamily: T.mono,
        fontSize: fs,
      }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${T.border}` }}>
            <th style={{ ...TH, textAlign: "left" }}>Condition</th>
            {full && <th style={{ ...TH, textAlign: "right" }}>Group</th>}
            {full && <th style={{ ...TH, textAlign: "right" }}>
              Avg 7d (True)
              <HelpTip width={240}>{"Average 7-day return when this condition was TRUE at signal time."}</HelpTip>
            </th>}
            {full && <th style={{ ...TH, textAlign: "right" }}>
              Avg 7d (False)
              <HelpTip width={240}>{"Average 7-day return when this condition was FALSE at signal time."}</HelpTip>
            </th>}
            <th style={{ ...TH, textAlign: "right" }}>
              Edge
              <HelpTip width={240}>{"Difference in average 7-day return between TRUE and FALSE. Shown only when both sides have at least 30 events; a difference is not a causal effect."}</HelpTip>
            </th>
            <th style={{ ...TH, textAlign: "right" }}>
              WR (T)
              <HelpTip width={240}>{"Win rate when condition is TRUE. A 'win' means the 7-day price moved in the signal's expected direction."}</HelpTip>
            </th>
            {full && <th style={{ ...TH, textAlign: "right" }}>WR (F)</th>}
          </tr>
        </thead>
        <tbody>
          {conditions.map(c => (
            <tr key={c.name} style={{ borderBottom: `1px solid ${T.border}22` }}>
              <td style={{ padding: "6px 10px", color: T.text2, textAlign: "left", fontWeight: 500, fontSize: fs, whiteSpace: "nowrap" }}>
                {conditionLabel(c.name)}
              </td>
              {full && <td style={{ padding: "6px 10px", textAlign: "right" }}>
                <GroupBadge group={c.group} />
              </td>}
              {full && <td style={{ padding: "6px 10px", textAlign: "right", color: T.text2, fontSize: fs }}>
                {c.avg_7d_true != null ? `${c.avg_7d_true > 0 ? "+" : ""}${c.avg_7d_true}%` : "—"}
                <span style={{ color: T.text4, marginLeft: 4, fontSize: T.textXs }}>({c.true_count})</span>
              </td>}
              {full && <td style={{ padding: "6px 10px", textAlign: "right", color: T.text3, fontSize: fs }}>
                {c.avg_7d_false != null ? `${c.avg_7d_false > 0 ? "+" : ""}${c.avg_7d_false}%` : "—"}
                <span style={{ color: T.text4, marginLeft: 4, fontSize: T.textXs }}>({c.false_count})</span>
              </td>}
              <td style={{
                padding: "6px 10px", textAlign: "right",
                color: edgeColor(c.edge), fontWeight: 700, fontSize: fs,
              }}>
                {c.edge != null && Math.min(c.true_count, c.false_count) >= MIN_N ? `${c.edge > 0 ? "+" : ""}${c.edge}%` : "—"}
              </td>
              <td style={{ padding: "6px 10px", textAlign: "right", color: rateColor(c.win_rate_true, c.true_count), fontWeight: 600, fontSize: fs }}>
                {c.win_rate_true != null ? `${c.win_rate_true}%` : "—"}
              </td>
              {full && <td style={{ padding: "6px 10px", textAlign: "right", color: rateColor(c.win_rate_false, c.false_count), fontSize: fs }}>
                {c.win_rate_false != null ? `${c.win_rate_false}%` : "—"}
              </td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 2: Top Condition Combos
// ---------------------------------------------------------------------------

function ComboCards({ combos, isMobile }) {
  if (!combos || combos.length === 0) return <NoData label="Need more signal history for combo analysis" />;

  const fs = m(T.textXs, isMobile);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {combos.slice(0, 10).map((combo, i) => (
        <div key={i} style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: isMobile ? "8px 10px" : "8px 14px",
          borderRadius: T.radiusXs,
          background: T.overlay02,
          border: `1px solid ${T.border}`,
        }}>
          <span style={{
            fontSize: fs, fontFamily: T.mono,
            color: T.text4, fontWeight: 700, minWidth: 20,
          }}>
            #{i + 1}
          </span>
          <span style={{ flex: 1, minWidth: 0, fontSize: fs, fontFamily: T.mono, color: T.text2, fontWeight: 500 }}>
            {combo.conditions.map(conditionLabel).join(" + ")}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
            <span style={{
              fontSize: m(T.textSm, isMobile), fontFamily: T.mono,
              color: rateColor(combo.win_rate, combo.count), fontWeight: 700,
            }}>
              {combo.win_rate}%
            </span>
            {combo.lift != null && (
              <span style={{
                fontSize: fs, fontFamily: T.mono,
                color: combo.count < MIN_N ? T.text4 : combo.lift > 0 ? col("#34d399") : combo.lift < -5 ? col("#f87171") : T.text4,
                fontWeight: 600,
              }}>
                {combo.lift > 0 ? "+" : ""}{combo.lift} pts{combo.baseline_wr != null ? ` vs ${combo.baseline_wr}% baseline` : ""}
              </span>
            )}
            <span style={{
              fontSize: fs, fontFamily: T.mono,
              color: edgeColor(combo.avg_7d, combo.count),
            }}>
              {combo.avg_7d > 0 ? "+" : ""}{combo.avg_7d}% avg
            </span>
            <span style={{
              fontSize: fs, fontFamily: T.mono, color: T.text4,
            }}>
              n={combo.count}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 3: Regime Scorecard
// ---------------------------------------------------------------------------

function RegimeScorecard({ data, isMobile }) {
  if (!data || Object.keys(data).length === 0) return <NoData />;

  const signals = Object.keys(data).sort((a, b) => {
    const order = ["STRONG_LONG", "LIGHT_LONG", "ACCUMULATE", "TRIM", "TRIM_HARD", "RISK_OFF"];
    return (order.indexOf(a) === -1 ? 99 : order.indexOf(a)) - (order.indexOf(b) === -1 ? 99 : order.indexOf(b));
  });

  const regimeSet = new Set();
  for (const entries of Object.values(data)) {
    for (const e of entries) regimeSet.add(e.regime);
  }
  const regimes = ["MARKUP", "ACCUM", "REACC", "BLOWOFF", "CAP", "MARKDOWN"].filter(r => regimeSet.has(r));
  const fs = m(T.textXs, isMobile);

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{
        width: "100%",
        borderCollapse: "collapse",
        fontFamily: T.mono,
        fontSize: fs,
      }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${T.border}` }}>
            <th style={{ ...TH, textAlign: "left" }}>Signal</th>
            {regimes.map(r => (
              <th key={r} title={r} style={{ ...TH, textAlign: "center" }}>{REGIME_META[r]?.name || r}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {signals.map(sig => {
            const meta = SIGNAL_META[sig] || SIGNAL_META.WAIT;
            const byRegime = {};
            for (const e of (data[sig] || [])) byRegime[e.regime] = e;
            return (
              <tr key={sig} style={{ borderBottom: `1px solid ${T.border}22` }}>
                <td style={{ padding: "6px 10px", color: meta.color, fontWeight: 600, textAlign: "left", fontSize: fs, whiteSpace: "nowrap" }}>
                  {meta.label || sig}
                </td>
                {regimes.map(r => {
                  const cell = byRegime[r];
                  if (!cell) return <td key={r} style={{ padding: "6px 10px", textAlign: "center", color: T.text4 }}>—</td>;
                  return (
                    <td key={r} style={{ padding: "6px 10px", textAlign: "center", whiteSpace: "nowrap" }}>
                      <span style={{ color: rateColor(cell.win_rate, cell.count), fontWeight: cell.count < MIN_N ? 400 : 700, fontSize: fs }}>
                        {cell.win_rate}%
                      </span>
                      <span style={{ color: T.text4, fontSize: T.textXs, marginLeft: 4 }}>({cell.count})</span>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 4: Confluence Scorecard
// ---------------------------------------------------------------------------

function ConfluenceScorecard({ buckets, isMobile }) {
  if (!buckets || buckets.length === 0) return <NoData />;

  const maxCount = Math.max(...buckets.map(b => b.count || 0), 1);
  const fs = m(T.textSm, isMobile);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {buckets.map(b => (
        <div key={b.bucket} style={{
          display: "flex", alignItems: "center", gap: 12,
          fontFamily: T.mono, fontSize: fs,
        }}>
          <span style={{ color: T.text2, fontWeight: 700, minWidth: 64, fontSize: m(T.textSm, isMobile) }}>
            {b.bucket}
          </span>
          <div style={{
            flex: 1, height: 22,
            background: T.overlay04,
            borderRadius: 5, overflow: "hidden",
          }}>
            <div style={{
              width: `${(b.count / maxCount) * 100}%`,
              height: "100%",
              background: b.win_rate != null && b.count >= MIN_N ? `${rateColor(b.win_rate)}30` : T.overlay06,
              borderRadius: 5,
            }} />
          </div>
          <span style={{
            color: rateColor(b.win_rate, b.count), fontWeight: 700,
            minWidth: 44, textAlign: "right", fontSize: fs,
          }}>
            {b.win_rate != null ? `${b.win_rate}%` : "—"}
          </span>
          <span style={{
            color: edgeColor(b.avg_7d, b.count), minWidth: 52,
            textAlign: "right", fontSize: m(T.textXs, isMobile),
          }}>
            {b.avg_7d != null ? `${b.avg_7d > 0 ? "+" : ""}${b.avg_7d}%` : "—"}
          </span>
          <span style={{
            color: T.text4, minWidth: 36,
            textAlign: "right", fontSize: m(T.textXs, isMobile),
          }}>
            n={b.count}
          </span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 5: Edge Decay
// ---------------------------------------------------------------------------

const DECAY_LABELS = {
  "0-24h": "Day 1",
  "24h-72h": "Days 2-3",
  "72h-7d": "Days 4-7",
};

function EdgeDecay({ periods, isMobile }) {
  if (!periods || periods.length === 0) return <NoData />;

  return (
    <div style={{
      display: "flex", gap: isMobile ? 10 : 16, justifyContent: "center",
    }}>
      {periods.map(p => (
        <div key={p.period} style={{
          flex: 1, textAlign: "center",
          padding: isMobile ? "12px 10px" : "16px 20px",
          borderRadius: T.radiusXs,
          background: T.overlay02,
          border: `1px solid ${T.border}`,
        }}>
          <div style={{
            fontSize: m(T.textXs, isMobile), color: T.text4,
            fontFamily: T.mono, marginBottom: 8,
            textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600,
          }}>
            {DECAY_LABELS[p.period] || p.period}
          </div>
          <div style={{
            fontSize: m(T.text2xl, isMobile),
            fontFamily: T.mono, fontWeight: 700,
            color: p.avg_return != null ? edgeColor(p.avg_return, p.count) : T.text4,
          }}>
            {p.avg_return != null ? `${p.avg_return > 0 ? "+" : ""}${p.avg_return}%` : "—"}
          </div>
          <div style={{
            fontSize: m(T.textXs, isMobile), color: T.text4,
            fontFamily: T.mono, marginTop: 6,
          }}>
            {p.count > 0 && <div style={{ whiteSpace: "nowrap" }}>{p.positive_pct}% positive</div>}
            <div>n={p.count}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 6: HyperLens Attribution
// ---------------------------------------------------------------------------

function HyperLensAttribution({ data, isMobile }) {
  if (!data) return <NoData />;

  const { with_whale: ww, without_whale: wo, edge_pct } = data;

  function Side({ label, stats, accent }) {
    return (
      <div style={{
        flex: 1, textAlign: "center",
        padding: isMobile ? "12px 10px" : "16px 20px",
        borderRadius: T.radiusXs,
        background: T.overlay02,
        border: `1px solid ${T.border}`,
      }}>
        <div style={{
          fontSize: m(T.textXs, isMobile), color: accent,
          fontFamily: T.mono, fontWeight: 700, marginBottom: 10,
          textTransform: "uppercase", letterSpacing: "0.08em",
        }}>
          {label}
        </div>
        <div style={{
          fontSize: m(T.text2xl, isMobile),
          fontFamily: T.mono, fontWeight: 700,
          color: stats.avg_7d != null ? edgeColor(stats.avg_7d, stats.count) : T.text4,
        }}>
          {stats.avg_7d != null ? `${stats.avg_7d > 0 ? "+" : ""}${stats.avg_7d}%` : "—"}
        </div>
        <div style={{
          fontSize: m(T.textSm, isMobile), color: T.text3,
          fontFamily: T.mono, marginTop: 6,
        }}>
          Win rate: <span style={{ color: rateColor(stats.win_rate, stats.count), fontWeight: 700 }}>
            {stats.win_rate != null ? `${stats.win_rate}%` : "—"}
          </span>
        </div>
        <div style={{
          fontSize: m(T.textXs, isMobile), color: T.text4,
          fontFamily: T.mono, marginTop: 3,
        }}>
          n={stats.count}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: isMobile ? 10 : 16 }}>
        <Side label="Tracked wallets agreed" stats={ww} accent={col("#fbbf24")} />
        <Side label="Did not agree" stats={wo} accent={T.text4} />
      </div>
      {edge_pct != null && (
        <div style={{
          textAlign: "center", marginTop: 12,
          fontSize: m(T.textSm, isMobile), fontFamily: T.mono,
          color: edgeColor(edge_pct, Math.min(ww.count, wo.count)), fontWeight: 700,
        }}>
          Difference: {edge_pct > 0 ? "+" : ""}{edge_pct} pts avg 7d return
          <HelpTip width={240}>{"Average 7-day return difference between the two groups; not a causal effect."}</HelpTip>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Panel
// ---------------------------------------------------------------------------

export default function AnalyticsPanel({ isMobile }) {
  const [tf, setTf] = useState("4h");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);

  // A late response for the previous timeframe must not overwrite the current one.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    fetch(`${API_BASE}/api/analytics/attribution?timeframe=${tf}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(d => { if (!cancelled) { setData(d); setLoading(false); } })
      .catch(() => { if (!cancelled) { setData(null); setError(true); setLoading(false); } });
    return () => { cancelled = true; };
  }, [tf, reload]);

  const pad = isMobile ? 14 : 20;

  return (
    <div>
      {/* Timeframe toggle */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, marginBottom: 16,
      }}>
        <Tabs label="Timeframe" items={[{ key: "4h", label: "4H" }, { key: "1d", label: "1D" }]} value={tf} onChange={setTf} />
        <span style={{
          fontSize: m(T.textXs, isMobile), color: T.text4,
          fontFamily: T.mono, marginLeft: "auto",
        }}>
          {loading ? "Loading..." : data ? "Live signal data" : error ? "" : "No data"}
        </span>
      </div>

      {!loading && data && (
        <div style={{ display: "flex", flexDirection: "column", gap: isMobile ? 14 : 18 }}>
          {/* Condition Predictive Value */}
          <GlassCard style={{ padding: pad }}>
            <SectionHeader
              title="Condition Predictive Value"
              subtitle="Average 7-day return of long signals when the condition was met vs not met (not a forecast). Edge is the difference, shown when both sides have 30 or more events; grey figures rest on fewer than 30."
            />
            <ConditionValueTable conditions={data.conditions} isMobile={isMobile} />
          </GlassCard>

          {/* Top Condition Combos */}
          <GlassCard style={{ padding: pad }}>
            <SectionHeader
              title="Top Condition Combos"
              subtitle={`Combinations of 3 conditions ranked by lift (long-signal win rate above the long baseline). Only uses conditions that vary meaningfully — always-true conditions are excluded. Best of ${data.combos?.[0]?.tested ?? "the"} tested combinations; expect lower results out of sample.`}
            />
            <ComboCards combos={data.combos} isMobile={isMobile} />
          </GlassCard>

          {/* Regime + Confluence row */}
          <div style={{ display: "flex", gap: isMobile ? 14 : 18, flexDirection: isMobile ? "column" : "row" }}>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionHeader
                title="By Regime"
                subtitle="Signal win rates broken down by the market regime active when the signal fired. Cells with fewer than 10 events are left out; grey figures rest on fewer than 30."
              />
              <RegimeScorecard data={data.regime_scorecard} isMobile={isMobile} />
            </GlassCard>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionHeader
                title="By share of entry checks met"
                subtitle="Win rate and average 7-day return of long signals, grouped by the share of entry checks met (not a forecast). Coins are scored out of different totals, so shares are compared rather than counts."
              />
              <ConfluenceScorecard buckets={data.confluence_scorecard} isMobile={isMobile} />
            </GlassCard>
          </div>

          {/* Edge Decay + HyperLens row */}
          <div style={{ display: "flex", gap: isMobile ? 14 : 18, flexDirection: isMobile ? "column" : "row" }}>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionHeader
                title="Average return by holding window"
                subtitle="Average price return of signals over each window after they fired, and the share of them that rose."
              />
              <EdgeDecay periods={data.edge_decay} isMobile={isMobile} />
            </GlassCard>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionHeader
                title="HyperLens Attribution"
                subtitle="Long signals where the tracked-wallet consensus (profitable traders and large accounts on Hyperliquid) agreed with the direction, against those where it did not."
              />
              <HyperLensAttribution data={data.hyperlens} isMobile={isMobile} />
            </GlassCard>
          </div>
        </div>
      )}

      {!loading && error && (
        <GlassCard style={{ padding: 32, textAlign: "center" }}>
          <div style={{ color: T.text4, fontFamily: T.mono, fontSize: m(T.textSm, false) }}>
            Could not load.{" "}
            <button type="button" onClick={() => setReload(n => n + 1)} style={{ background: "transparent", border: 0, borderBottom: `1px solid ${T.accent}`, padding: 0, color: T.accent, fontSize: m(T.textSm, false), fontFamily: T.mono, cursor: "pointer" }}>Retry</button>
          </div>
        </GlassCard>
      )}

      {!loading && !error && !data && (
        <GlassCard style={{ padding: 32, textAlign: "center" }}>
          <div style={{ color: T.text4, fontFamily: T.mono, fontSize: m(T.textSm, false) }}>
            No attribution data available. Signal events with 7-day outcomes are needed.
          </div>
        </GlassCard>
      )}
    </div>
  );
}
