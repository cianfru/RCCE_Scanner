import { useState, useEffect } from "react";
import { T, m, SIGNAL_META } from "../theme.js";
import GlassCard from "./GlassCard.jsx";
import FadeIn from "./FadeIn.jsx";

const API_BASE = import.meta.env.VITE_API_URL || "";

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function rateColor(rate) {
  if (rate == null) return T.text4;
  if (rate >= 70) return "#34d399";
  if (rate >= 55) return "#fbbf24";
  if (rate >= 40) return T.text3;
  return "#f87171";
}

function edgeColor(edge) {
  if (edge == null) return T.text4;
  if (edge > 3) return "#34d399";
  if (edge > 0) return "#6ee7b7";
  if (edge > -3) return "#fbbf24";
  return "#f87171";
}

// ---------------------------------------------------------------------------
// InfoTip — inline tooltip matching PositioningPanel pattern
// ---------------------------------------------------------------------------

function InfoTip({ text }) {
  const [show, setShow] = useState(false);
  return (
    <span
      style={{ position: "relative", display: "inline-flex", alignItems: "center", marginLeft: 4 }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: 14, height: 14, borderRadius: "50%",
        border: `1px solid ${show ? T.accent : T.border}`,
        color: show ? T.accent : T.text4,
        fontSize: 8, fontFamily: T.mono, fontWeight: 700,
        cursor: "help", lineHeight: 1,
      }}>
        i
      </span>
      {show && (
        <div style={{
          position: "absolute", bottom: "calc(100% + 6px)", left: "50%",
          transform: "translateX(-50%)", width: 240, padding: "10px 12px",
          background: "rgba(16,16,20,0.95)", backdropFilter: "blur(16px)",
          borderRadius: 8, border: `1px solid ${T.border}`,
          boxShadow: "0 8px 24px rgba(0,0,0,0.5)", zIndex: 9999,
        }}>
          <div style={{
            fontSize: m(T.textXs, false), color: T.text3,
            fontFamily: T.font, fontWeight: 400, lineHeight: 1.55,
          }}>
            {text}
          </div>
        </div>
      )}
    </span>
  );
}

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

function GroupBadge({ group }) {
  const colors = {
    core: { bg: "#22d3ee10", border: "#22d3ee30", text: "#22d3ee" },
    coinglass: { bg: "#a78bfa10", border: "#a78bfa30", text: "#a78bfa" },
    hyperlens: { bg: "#fbbf2410", border: "#fbbf2430", text: "#fbbf24" },
  };
  const c = colors[group] || colors.core;
  return (
    <span style={{
      fontSize: T.textXs,
      fontFamily: T.mono,
      padding: "2px 6px",
      borderRadius: 4,
      background: c.bg,
      border: `1px solid ${c.border}`,
      color: c.text,
      textTransform: "uppercase",
      letterSpacing: "0.05em",
      fontWeight: 600,
    }}>
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
  fontSize: 9,
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
            <th style={{ ...TH, textAlign: "right" }}>Group</th>
            <th style={{ ...TH, textAlign: "right" }}>
              Avg 7d (True)
              <InfoTip text="Average 7-day return when this condition was TRUE at signal time." />
            </th>
            <th style={{ ...TH, textAlign: "right" }}>
              Avg 7d (False)
              <InfoTip text="Average 7-day return when this condition was FALSE at signal time." />
            </th>
            <th style={{ ...TH, textAlign: "right" }}>
              Edge
              <InfoTip text="Difference in avg 7-day return between TRUE and FALSE. Positive means this condition predicts better outcomes." />
            </th>
            <th style={{ ...TH, textAlign: "right" }}>
              WR (T)
              <InfoTip text="Win rate when condition is TRUE. A 'win' means the 7-day price moved in the signal's expected direction." />
            </th>
            <th style={{ ...TH, textAlign: "right" }}>WR (F)</th>
          </tr>
        </thead>
        <tbody>
          {conditions.map(c => (
            <tr key={c.name} style={{ borderBottom: `1px solid ${T.border}22` }}>
              <td style={{ padding: "6px 10px", color: T.text2, textAlign: "left", fontWeight: 500, fontSize: fs }}>
                {c.name.replace(/_/g, " ")}
              </td>
              <td style={{ padding: "6px 10px", textAlign: "right" }}>
                <GroupBadge group={c.group} />
              </td>
              <td style={{ padding: "6px 10px", textAlign: "right", color: T.text2, fontSize: fs }}>
                {c.avg_7d_true != null ? `${c.avg_7d_true > 0 ? "+" : ""}${c.avg_7d_true}%` : "—"}
                <span style={{ color: T.text4, marginLeft: 4, fontSize: T.textXs }}>({c.true_count})</span>
              </td>
              <td style={{ padding: "6px 10px", textAlign: "right", color: T.text3, fontSize: fs }}>
                {c.avg_7d_false != null ? `${c.avg_7d_false > 0 ? "+" : ""}${c.avg_7d_false}%` : "—"}
                <span style={{ color: T.text4, marginLeft: 4, fontSize: T.textXs }}>({c.false_count})</span>
              </td>
              <td style={{
                padding: "6px 10px", textAlign: "right",
                color: edgeColor(c.edge), fontWeight: 700, fontSize: fs,
              }}>
                {c.edge != null ? `${c.edge > 0 ? "+" : ""}${c.edge}%` : "—"}
              </td>
              <td style={{ padding: "6px 10px", textAlign: "right", color: rateColor(c.win_rate_true), fontWeight: 600, fontSize: fs }}>
                {c.win_rate_true != null ? `${c.win_rate_true}%` : "—"}
              </td>
              <td style={{ padding: "6px 10px", textAlign: "right", color: rateColor(c.win_rate_false), fontSize: fs }}>
                {c.win_rate_false != null ? `${c.win_rate_false}%` : "—"}
              </td>
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
          background: "rgba(255,255,255,0.02)",
          border: `1px solid ${T.border}`,
        }}>
          <span style={{
            fontSize: fs, fontFamily: T.mono,
            color: T.text4, fontWeight: 700, minWidth: 20,
          }}>
            #{i + 1}
          </span>
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap", flex: 1 }}>
            {combo.conditions.map(c => (
              <span key={c} style={{
                fontSize: fs, fontFamily: T.mono,
                padding: "3px 8px", borderRadius: 5,
                background: "#22d3ee10", border: "1px solid #22d3ee25",
                color: "#22d3ee", fontWeight: 500,
              }}>
                {c.replace(/_/g, " ")}
              </span>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
            <span style={{
              fontSize: m(T.textSm, isMobile), fontFamily: T.mono,
              color: rateColor(combo.win_rate), fontWeight: 700,
            }}>
              {combo.win_rate}%
            </span>
            <span style={{
              fontSize: fs, fontFamily: T.mono,
              color: edgeColor(combo.avg_7d),
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
              <th key={r} style={{ ...TH, textAlign: "center" }}>{r}</th>
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
                <td style={{ padding: "6px 10px", color: meta.color, fontWeight: 600, textAlign: "left", fontSize: fs }}>
                  {meta.label || sig}
                </td>
                {regimes.map(r => {
                  const cell = byRegime[r];
                  if (!cell) return <td key={r} style={{ padding: "6px 10px", textAlign: "center", color: T.text4 }}>—</td>;
                  return (
                    <td key={r} style={{ padding: "6px 10px", textAlign: "center" }}>
                      <span style={{ color: rateColor(cell.win_rate), fontWeight: 700, fontSize: fs }}>
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
          <span style={{ color: T.text2, fontWeight: 700, minWidth: 44, fontSize: m(T.textSm, isMobile) }}>
            {b.bucket}
          </span>
          <div style={{
            flex: 1, height: 22,
            background: "rgba(255,255,255,0.03)",
            borderRadius: 5, overflow: "hidden",
          }}>
            <div style={{
              width: `${(b.count / maxCount) * 100}%`,
              height: "100%",
              background: b.win_rate != null ? `${rateColor(b.win_rate)}30` : "transparent",
              borderRadius: 5,
            }} />
          </div>
          <span style={{
            color: rateColor(b.win_rate), fontWeight: 700,
            minWidth: 44, textAlign: "right", fontSize: fs,
          }}>
            {b.win_rate != null ? `${b.win_rate}%` : "—"}
          </span>
          <span style={{
            color: edgeColor(b.avg_7d), minWidth: 52,
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
          background: "rgba(255,255,255,0.02)",
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
            color: p.avg_return != null ? edgeColor(p.avg_return) : T.text4,
          }}>
            {p.avg_return != null ? `${p.avg_return > 0 ? "+" : ""}${p.avg_return}%` : "—"}
          </div>
          <div style={{
            fontSize: m(T.textXs, isMobile), color: T.text4,
            fontFamily: T.mono, marginTop: 6,
          }}>
            {p.count > 0 ? `${p.positive_pct}% positive` : ""}
            {p.count > 0 && " · "}n={p.count}
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
        background: `${accent}08`,
        border: `1px solid ${accent}20`,
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
          color: stats.avg_7d != null ? edgeColor(stats.avg_7d) : T.text4,
        }}>
          {stats.avg_7d != null ? `${stats.avg_7d > 0 ? "+" : ""}${stats.avg_7d}%` : "—"}
        </div>
        <div style={{
          fontSize: m(T.textSm, isMobile), color: T.text3,
          fontFamily: T.mono, marginTop: 6,
        }}>
          Win rate: <span style={{ color: rateColor(stats.win_rate), fontWeight: 700 }}>
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
        <Side label="With Whale" stats={ww} accent="#fbbf24" />
        <Side label="Without Whale" stats={wo} accent={T.text4} />
      </div>
      {edge_pct != null && (
        <div style={{
          textAlign: "center", marginTop: 12,
          fontSize: m(T.textSm, isMobile), fontFamily: T.mono,
          color: edgeColor(edge_pct), fontWeight: 700,
        }}>
          Whale edge: {edge_pct > 0 ? "+" : ""}{edge_pct}% avg 7d
          <InfoTip text="The additional average 7-day return gained when HyperLens whale consensus confirmed the signal direction." />
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

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/api/analytics/attribution?timeframe=${tf}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [tf]);

  const pad = isMobile ? 14 : 20;

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      {/* Timeframe toggle */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, marginBottom: 16,
      }}>
        {["4h", "1d"].map(t => (
          <button
            key={t}
            onClick={() => setTf(t)}
            style={{
              padding: "5px 16px", borderRadius: 6,
              border: `1px solid ${tf === t ? T.accent : T.border}`,
              background: tf === t ? T.accentDim : "transparent",
              color: tf === t ? T.accent : T.text3,
              fontFamily: T.mono, fontSize: m(T.textSm, isMobile),
              fontWeight: 600, cursor: "pointer", letterSpacing: "0.06em",
            }}
          >
            {t.toUpperCase()}
          </button>
        ))}
        <span style={{
          fontSize: m(T.textXs, isMobile), color: T.text4,
          fontFamily: T.mono, marginLeft: "auto",
        }}>
          {loading ? "Loading..." : data ? "Live signal data" : "No data"}
        </span>
      </div>

      {!loading && data && (
        <div style={{ display: "flex", flexDirection: "column", gap: isMobile ? 14 : 18 }}>
          {/* Condition Predictive Value */}
          <GlassCard style={{ padding: pad }}>
            <SectionHeader
              title="Condition Predictive Value"
              subtitle="Average 7-day return when each condition is TRUE vs FALSE. Higher edge means the condition is a stronger predictor of good outcomes."
            />
            <ConditionValueTable conditions={data.conditions} isMobile={isMobile} />
          </GlassCard>

          {/* Top Condition Combos */}
          <GlassCard style={{ padding: pad }}>
            <SectionHeader
              title="Top Condition Combos"
              subtitle="Best-performing combinations of 3 conditions. Shows win rate when ALL conditions in the combo are met simultaneously."
            />
            <ComboCards combos={data.combos} isMobile={isMobile} />
          </GlassCard>

          {/* Regime + Confluence row */}
          <div style={{ display: "flex", gap: isMobile ? 14 : 18, flexDirection: isMobile ? "column" : "row" }}>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionHeader
                title="By Regime"
                subtitle="Signal win rates broken down by the market regime active when the signal fired."
              />
              <RegimeScorecard data={data.regime_scorecard} isMobile={isMobile} />
            </GlassCard>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionHeader
                title="By Conviction Level"
                subtitle="Performance grouped by how many conditions were met. Higher conviction should correlate with better outcomes."
              />
              <ConfluenceScorecard buckets={data.confluence_scorecard} isMobile={isMobile} />
            </GlassCard>
          </div>

          {/* Edge Decay + HyperLens row */}
          <div style={{ display: "flex", gap: isMobile ? 14 : 18, flexDirection: isMobile ? "column" : "row" }}>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionHeader
                title="Signal Edge Decay"
                subtitle="How signal returns distribute over time. Shows whether alpha concentrates in the first day or spreads evenly across the week."
              />
              <EdgeDecay periods={data.edge_decay} isMobile={isMobile} />
            </GlassCard>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionHeader
                title="HyperLens Attribution"
                subtitle="Compares performance of signals where HyperLens whale consensus confirmed the direction vs those without whale confirmation."
              />
              <HyperLensAttribution data={data.hyperlens} isMobile={isMobile} />
            </GlassCard>
          </div>
        </div>
      )}

      {!loading && !data && (
        <GlassCard style={{ padding: 32, textAlign: "center" }}>
          <div style={{ color: T.text4, fontFamily: T.mono, fontSize: m(T.textSm, false) }}>
            No attribution data available. Signal events with 7-day outcomes are needed.
          </div>
        </GlassCard>
      )}
    </div>
  );
}
