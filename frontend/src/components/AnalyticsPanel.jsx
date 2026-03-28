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

function SectionTitle({ children }) {
  return (
    <div style={{
      fontSize: T.textSm,
      color: T.text4,
      fontFamily: T.mono,
      letterSpacing: "0.08em",
      textTransform: "uppercase",
      marginBottom: 10,
      fontWeight: 600,
    }}>
      {children}
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
      fontSize: 9,
      fontFamily: T.mono,
      padding: "1px 5px",
      borderRadius: 4,
      background: c.bg,
      border: `1px solid ${c.border}`,
      color: c.text,
      textTransform: "uppercase",
      letterSpacing: "0.05em",
    }}>
      {group}
    </span>
  );
}

function NoData({ label }) {
  return (
    <div style={{ color: T.text4, fontSize: T.textSm, fontFamily: T.mono, padding: 16, textAlign: "center" }}>
      {label || "Not enough data yet"}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 1: Condition Predictive Value
// ---------------------------------------------------------------------------

function ConditionValueTable({ conditions, isMobile }) {
  if (!conditions || conditions.length === 0) return <NoData />;

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{
        width: "100%",
        borderCollapse: "collapse",
        fontFamily: T.mono,
        fontSize: m(T.textXs, isMobile),
      }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${T.border}` }}>
            {["Condition", "Grp", "True", "False", "Edge", "WR (T)", "WR (F)"].map(h => (
              <th key={h} style={{
                padding: "6px 8px",
                textAlign: h === "Condition" ? "left" : "right",
                color: T.text4,
                fontWeight: 500,
                fontSize: 10,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
              }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {conditions.map(c => (
            <tr key={c.name} style={{ borderBottom: `1px solid ${T.border}22` }}>
              <td style={{ padding: "5px 8px", color: T.text2, textAlign: "left" }}>
                {c.name.replace(/_/g, " ")}
              </td>
              <td style={{ padding: "5px 8px", textAlign: "right" }}>
                <GroupBadge group={c.group} />
              </td>
              <td style={{ padding: "5px 8px", textAlign: "right", color: T.text3 }}>
                {c.avg_7d_true != null ? `${c.avg_7d_true > 0 ? "+" : ""}${c.avg_7d_true}%` : "—"}
                <span style={{ color: T.text4, marginLeft: 4 }}>({c.true_count})</span>
              </td>
              <td style={{ padding: "5px 8px", textAlign: "right", color: T.text3 }}>
                {c.avg_7d_false != null ? `${c.avg_7d_false > 0 ? "+" : ""}${c.avg_7d_false}%` : "—"}
                <span style={{ color: T.text4, marginLeft: 4 }}>({c.false_count})</span>
              </td>
              <td style={{
                padding: "5px 8px",
                textAlign: "right",
                color: edgeColor(c.edge),
                fontWeight: 700,
              }}>
                {c.edge != null ? `${c.edge > 0 ? "+" : ""}${c.edge}%` : "—"}
              </td>
              <td style={{ padding: "5px 8px", textAlign: "right", color: rateColor(c.win_rate_true) }}>
                {c.win_rate_true != null ? `${c.win_rate_true}%` : "—"}
              </td>
              <td style={{ padding: "5px 8px", textAlign: "right", color: rateColor(c.win_rate_false) }}>
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {combos.slice(0, 10).map((combo, i) => (
        <div key={i} style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: isMobile ? "6px 8px" : "6px 12px",
          borderRadius: 8,
          background: `rgba(255,255,255,0.02)`,
          border: `1px solid ${T.border}`,
        }}>
          <span style={{
            fontSize: 10,
            fontFamily: T.mono,
            color: T.text4,
            fontWeight: 700,
            minWidth: 18,
          }}>
            #{i + 1}
          </span>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", flex: 1 }}>
            {combo.conditions.map(c => (
              <span key={c} style={{
                fontSize: 10,
                fontFamily: T.mono,
                padding: "2px 6px",
                borderRadius: 4,
                background: "#22d3ee10",
                border: "1px solid #22d3ee25",
                color: "#22d3ee",
              }}>
                {c.replace(/_/g, " ")}
              </span>
            ))}
          </div>
          <span style={{
            fontSize: m(T.textSm, isMobile),
            fontFamily: T.mono,
            color: rateColor(combo.win_rate),
            fontWeight: 700,
            minWidth: 42,
            textAlign: "right",
          }}>
            {combo.win_rate}%
          </span>
          <span style={{
            fontSize: 10,
            fontFamily: T.mono,
            color: edgeColor(combo.avg_7d),
            minWidth: 48,
            textAlign: "right",
          }}>
            {combo.avg_7d > 0 ? "+" : ""}{combo.avg_7d}%
          </span>
          <span style={{
            fontSize: 10,
            fontFamily: T.mono,
            color: T.text4,
            minWidth: 24,
            textAlign: "right",
          }}>
            n={combo.count}
          </span>
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

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{
        width: "100%",
        borderCollapse: "collapse",
        fontFamily: T.mono,
        fontSize: m(T.textXs, isMobile),
      }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${T.border}` }}>
            <th style={{ padding: "6px 8px", textAlign: "left", color: T.text4, fontSize: 10, fontWeight: 500 }}>
              Signal
            </th>
            {regimes.map(r => (
              <th key={r} style={{ padding: "6px 8px", textAlign: "center", color: T.text4, fontSize: 10, fontWeight: 500 }}>
                {r}
              </th>
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
                <td style={{ padding: "5px 8px", color: meta.color, fontWeight: 600, textAlign: "left" }}>
                  {meta.label || sig}
                </td>
                {regimes.map(r => {
                  const cell = byRegime[r];
                  if (!cell) return <td key={r} style={{ padding: "5px 8px", textAlign: "center", color: T.text4 }}>—</td>;
                  return (
                    <td key={r} style={{ padding: "5px 8px", textAlign: "center" }}>
                      <span style={{ color: rateColor(cell.win_rate), fontWeight: 600 }}>
                        {cell.win_rate}%
                      </span>
                      <span style={{ color: T.text4, fontSize: 9, marginLeft: 3 }}>({cell.count})</span>
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {buckets.map(b => (
        <div key={b.bucket} style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          fontFamily: T.mono,
          fontSize: m(T.textSm, isMobile),
        }}>
          <span style={{ color: T.text2, fontWeight: 600, minWidth: 40 }}>{b.bucket}</span>
          <div style={{
            flex: 1,
            height: 20,
            background: `rgba(255,255,255,0.03)`,
            borderRadius: 4,
            overflow: "hidden",
            position: "relative",
          }}>
            <div style={{
              width: `${(b.count / maxCount) * 100}%`,
              height: "100%",
              background: b.win_rate != null
                ? `${rateColor(b.win_rate)}30`
                : "transparent",
              borderRadius: 4,
            }} />
          </div>
          <span style={{ color: rateColor(b.win_rate), fontWeight: 700, minWidth: 40, textAlign: "right" }}>
            {b.win_rate != null ? `${b.win_rate}%` : "—"}
          </span>
          <span style={{ color: edgeColor(b.avg_7d), minWidth: 48, textAlign: "right", fontSize: T.textXs }}>
            {b.avg_7d != null ? `${b.avg_7d > 0 ? "+" : ""}${b.avg_7d}%` : "—"}
          </span>
          <span style={{ color: T.text4, minWidth: 30, textAlign: "right", fontSize: T.textXs }}>
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

function EdgeDecay({ periods, isMobile }) {
  if (!periods || periods.length === 0) return <NoData />;

  return (
    <div style={{
      display: "flex",
      gap: isMobile ? 8 : 16,
      justifyContent: "center",
    }}>
      {periods.map(p => (
        <div key={p.period} style={{
          flex: 1,
          textAlign: "center",
          padding: isMobile ? "10px 8px" : "12px 16px",
          borderRadius: 8,
          background: "rgba(255,255,255,0.02)",
          border: `1px solid ${T.border}`,
        }}>
          <div style={{
            fontSize: T.textXs,
            color: T.text4,
            fontFamily: T.mono,
            marginBottom: 6,
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}>
            {p.period}
          </div>
          <div style={{
            fontSize: isMobile ? 18 : 22,
            fontFamily: T.mono,
            fontWeight: 700,
            color: p.avg_return != null ? edgeColor(p.avg_return) : T.text4,
          }}>
            {p.avg_return != null ? `${p.avg_return > 0 ? "+" : ""}${p.avg_return}%` : "—"}
          </div>
          <div style={{
            fontSize: T.textXs,
            color: T.text4,
            fontFamily: T.mono,
            marginTop: 4,
          }}>
            {p.count > 0 ? `${p.positive_pct}% positive` : ""} (n={p.count})
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
        flex: 1,
        textAlign: "center",
        padding: isMobile ? "10px 8px" : "14px 16px",
        borderRadius: 8,
        background: `${accent}08`,
        border: `1px solid ${accent}20`,
      }}>
        <div style={{
          fontSize: T.textXs,
          color: accent,
          fontFamily: T.mono,
          fontWeight: 600,
          marginBottom: 8,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
        }}>
          {label}
        </div>
        <div style={{
          fontSize: isMobile ? 20 : 26,
          fontFamily: T.mono,
          fontWeight: 700,
          color: stats.avg_7d != null ? edgeColor(stats.avg_7d) : T.text4,
        }}>
          {stats.avg_7d != null ? `${stats.avg_7d > 0 ? "+" : ""}${stats.avg_7d}%` : "—"}
        </div>
        <div style={{ fontSize: T.textXs, color: T.text3, fontFamily: T.mono, marginTop: 4 }}>
          Win rate: <span style={{ color: rateColor(stats.win_rate), fontWeight: 600 }}>
            {stats.win_rate != null ? `${stats.win_rate}%` : "—"}
          </span>
        </div>
        <div style={{ fontSize: T.textXs, color: T.text4, fontFamily: T.mono, marginTop: 2 }}>
          n={stats.count}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: isMobile ? 8 : 16 }}>
        <Side label="With Whale" stats={ww} accent="#fbbf24" />
        <Side label="Without Whale" stats={wo} accent={T.text4} />
      </div>
      {edge_pct != null && (
        <div style={{
          textAlign: "center",
          marginTop: 10,
          fontSize: T.textSm,
          fontFamily: T.mono,
          color: edgeColor(edge_pct),
          fontWeight: 600,
        }}>
          Whale edge: {edge_pct > 0 ? "+" : ""}{edge_pct}% avg 7d
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

  const pad = isMobile ? 12 : 16;

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      {/* Timeframe toggle */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginBottom: 16,
      }}>
        {["4h", "1d"].map(t => (
          <button
            key={t}
            onClick={() => setTf(t)}
            style={{
              padding: "4px 14px",
              borderRadius: 6,
              border: `1px solid ${tf === t ? T.accent : T.border}`,
              background: tf === t ? `${T.accent}18` : "transparent",
              color: tf === t ? T.accent : T.text3,
              fontFamily: T.mono,
              fontSize: T.textSm,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {t.toUpperCase()}
          </button>
        ))}
        <span style={{
          fontSize: T.textXs,
          color: T.text4,
          fontFamily: T.mono,
          marginLeft: "auto",
        }}>
          {loading ? "Loading..." : data ? "Live signal data" : "No data"}
        </span>
      </div>

      {!loading && data && (
        <div style={{ display: "flex", flexDirection: "column", gap: isMobile ? 12 : 16 }}>
          {/* Row 1: Condition Value + Combos */}
          <GlassCard style={{ padding: pad }}>
            <SectionTitle>Condition Predictive Value</SectionTitle>
            <ConditionValueTable conditions={data.conditions} isMobile={isMobile} />
          </GlassCard>

          <GlassCard style={{ padding: pad }}>
            <SectionTitle>Top Condition Combos</SectionTitle>
            <ComboCards combos={data.combos} isMobile={isMobile} />
          </GlassCard>

          {/* Row 2: Regime + Confluence */}
          <div style={{ display: "flex", gap: isMobile ? 12 : 16, flexDirection: isMobile ? "column" : "row" }}>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionTitle>By Regime</SectionTitle>
              <RegimeScorecard data={data.regime_scorecard} isMobile={isMobile} />
            </GlassCard>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionTitle>By Conviction Level</SectionTitle>
              <ConfluenceScorecard buckets={data.confluence_scorecard} isMobile={isMobile} />
            </GlassCard>
          </div>

          {/* Row 3: Edge Decay + HyperLens */}
          <div style={{ display: "flex", gap: isMobile ? 12 : 16, flexDirection: isMobile ? "column" : "row" }}>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionTitle>Signal Edge Decay</SectionTitle>
              <EdgeDecay periods={data.edge_decay} isMobile={isMobile} />
            </GlassCard>
            <GlassCard style={{ padding: pad, flex: 1 }}>
              <SectionTitle>HyperLens Attribution</SectionTitle>
              <HyperLensAttribution data={data.hyperlens} isMobile={isMobile} />
            </GlassCard>
          </div>
        </div>
      )}

      {!loading && !data && (
        <GlassCard style={{ padding: 32, textAlign: "center" }}>
          <div style={{ color: T.text4, fontFamily: T.mono, fontSize: T.textSm }}>
            No attribution data available. Signal events with 7-day outcomes are needed.
          </div>
        </GlassCard>
      )}
    </div>
  );
}
