import SetupPair from "../components/SetupPair.jsx";
import SignalContext from "../components/SignalContext.jsx";
import TokenLogo from "../components/TokenLogo.jsx";
import HelpTip from "../components/HelpTip.jsx";
import { formatPercent, evidenceSummary, funding8hPct, hasCoinglass, signalAgreement } from "../utils/marketPresentation.js";
import Tabs from "../components/Tabs.jsx";
import TrendChart from "../components/TrendChart.jsx";
import { useState, useEffect, useMemo } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { col, T, REGIME_META, SIGNAL_META, heatColor, phaseColor, exhaustMeta, fmt, zBar, getBaseSymbol, getTVSymbol } from "../theme.js";
import useViewport from "../hooks/useViewport.js";
import BMSBChart from "../components/BMSBChart.jsx";
import ConditionsScorecard from "../components/ConditionsScorecard.jsx";
import PositioningPanel from "../components/PositioningPanel.jsx";
import CrossExchangePanel from "../components/CrossExchangePanel.jsx";
import CoinChat from "../components/CoinChat.jsx";
import { traderLean, longShare, usd } from "../utils/traders.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Generic Metric Sparkline — auto-scaled, compact
// ---------------------------------------------------------------------------

function MetricSparkline({ label, history, current, unit, colorFn }) {
  if (!history || history.length < 2) return null;

  const vals = history;
  const color = colorFn ? colorFn(current) : col(current >= vals[0] ? "#97FCE4" : "#d8a094");
  const fmtVal = (v) => {
    if (v == null) return "\u2014";
    if (unit === "%") {
      // Use more decimals for very small values (e.g. funding rates)
      const abs = Math.abs(v);
      const decimals = abs > 0 && abs < 0.01 ? 4 : 2;
      return `${v.toFixed(decimals)}%`;
    }
    if (unit === "$") return v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : `$${Math.round(v).toLocaleString()}`;
    if (unit === "x") return `${v.toFixed(3)}x`;
    return String(v);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: T.textSm, color: T.text3, fontFamily: T.mono, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>
          {label}
        </span>
        <span style={{ fontSize: T.textBase, color, fontFamily: T.mono, fontWeight: 700 }}>
          {fmtVal(current)}
        </span>
      </div>
      <TrendChart data={history} color={color} label={`${label} history`} />
      <div style={{display:'flex', justifyContent:'space-between', fontFamily:T.mono, fontSize:T.textXs, color:T.text4}}>
        <span>Low {fmtVal(Math.min(...history))}</span><span>High {fmtVal(Math.max(...history))}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Combined Confluence + Win Rate card
// ---------------------------------------------------------------------------

function ConfluenceCard({ confluence }) {
  if (!confluence) return null;

  return (
    <div style={{
      background: T.glassBg, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: "16px 20px",
      backdropFilter: "blur(20px) saturate(1.3)", WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      <ConfluenceSection confluence={confluence} />
    </div>
  );
}

// Confluence section (extracted from ConfluencePanel, no outer card wrapper)
function ConfluenceSection({ confluence }) {
  const { score, label, regime_aligned,
    regime_4h, regime_1d, signal_4h, signal_1d } = confluence;

  // The label comes from the raw points, so the bar takes the label's colour.
  const labelColor = (l) => ({ STRONG: "#34d399", MODERATE: "#facc15", WEAK: "#fb923c", CONFLICTING: "#f87171" }[l]);
  const lColor = labelColor(label) ? col(labelColor(label)) : T.text4;
  const color = lColor;
  const signalState = signalAgreement(confluence);
  const r4h = REGIME_META[regime_4h] || REGIME_META.FLAT;
  const r1d = REGIME_META[regime_1d] || REGIME_META.FLAT;
  const s4h = SIGNAL_META[signal_4h] || SIGNAL_META.WAIT;
  const s1d = SIGNAL_META[signal_1d] || SIGNAL_META.WAIT;

  return (
    <>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        marginBottom: 14, paddingBottom: 10, borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ width: 3, height: 14, borderRadius: 2, background: T.accent, flexShrink: 0 }} />
        <span style={{
          fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em",
          fontFamily: T.font, fontWeight: 700, textTransform: "uppercase",
        }}>Timeframe agreement <HelpTip title="Confluence"><p>A 0–100 score describing how the four-hour and daily signals, regimes and supporting factors align. Higher agreement means more shared evidence across timeframes. It is not a win rate or a probability of profit.</p></HelpTip></span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
        <div style={{ flex: 1, height: 5, background: T.overlay04, borderRadius: 3, overflow: "hidden" }}>
          <div style={{
            width: `${Math.min(score ?? 0, 100)}%`, height: "100%",
            background: `linear-gradient(90deg, ${color}88, ${color})`,
            borderRadius: 3, boxShadow: `0 0 8px ${color}30`, transition: "width 0.6s ease",
          }} />
        </div>
        <span style={{ fontFamily: T.mono, fontSize: T.textMd, fontWeight: 700, color, minWidth: 32, textAlign: "right" }}>
          {score != null ? Math.round(score) : "\u2014"}
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span className="terminal-status" style={{
          padding: "4px 12px", borderRadius: 20,
          background: `${lColor}15`, color: lColor,
          fontSize: T.textSm, fontFamily: T.mono, fontWeight: 700,
          letterSpacing: "0.06em", border: `1px solid ${lColor}25`,
        }}>{label || "\u2014"}</span>
        <div style={{ display: "flex", gap: 10, marginLeft: "auto" }}>
          {[["Regimes", regime_aligned ? "agree" : "differ"], ["Signals", signalState === "waiting" ? "both waiting" : signalState]].map(([lbl, state]) => (
            <span key={lbl} style={{
              fontSize: T.textSm, fontFamily: T.mono, fontWeight: 600,
              color: state === "agree" ? T.green : state === "differ" ? T.red : T.text3, display: "flex", alignItems: "center", gap: 4,
            }}>
              <span style={{ fontSize: T.textXs, color: T.text4 }}>{lbl}</span>
              {state}
            </span>
          ))}
        </div>
      </div>

      {[
        { tf: "4H", rm: r4h, regime: regime_4h, sm: s4h, signal: signal_4h },
        { tf: "1D", rm: r1d, regime: regime_1d, sm: s1d, signal: signal_1d },
      ].map(row => (
        <div key={row.tf} style={{
          display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 0",
        }}>
          <span style={{ fontSize: T.textSm, color: T.text4, fontFamily: T.mono, fontWeight: 600, letterSpacing: "0.08em", minWidth: 28 }}>
            {row.tf}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="terminal-status" style={{
              padding: "3px 10px", borderRadius: 20, background: row.rm.bg, color: row.rm.color,
              fontSize: T.textXs, fontFamily: T.mono, fontWeight: 600, letterSpacing: "0.04em", border: `1px solid ${row.rm.color}20`,
            }}>{row.regime ? row.rm.name : "\u2014"}</span>
            <span style={{ color: T.text4, fontSize: T.textSm }}>{"\u2192"}</span>
            <span style={{
              fontSize: T.textSm, fontFamily: T.mono, fontWeight: 600, color: row.sm.color,
              display: "inline-flex", alignItems: "center", gap: 4,
            }}>
              <span style={{ fontSize: T.textXs, filter: row.signal !== "WAIT" ? `drop-shadow(0 0 3px ${row.sm.color})` : "none" }}>
                {row.sm.dot}
              </span>
              {row.sm.label}
            </span>
          </div>
        </div>
      ))}
    </>
  );
}

// ---------------------------------------------------------------------------
// Metrics Panel — unified sparklines card
// ---------------------------------------------------------------------------

function MetricsPanel({ data }) {
  const pos = data.positioning || {};

  // Color functions for each metric
  const confColor = (v) => v >= 60 ? T.green : v >= 40 ? T.yellow : T.red;
  const fundColor = (v) => v < 0 ? T.green : v > 0.01 ? T.red : T.text3;  // percent per 8h
  const oiChgColor = (v) => v > 0 ? T.green : v < 0 ? T.red : T.text3;
  const lsrColor = (v) => v < 0.9 ? T.green : v > 1.2 ? T.red : T.text3;
  const bsrColor = (v) => v > 1 ? T.green : v < 1 ? T.red : T.text3;
  const spotColor = (v) => v > 0.5 ? T.green : v < 0.3 ? T.red : T.text3;

  const metrics = [
    { label: "Regime confidence", history: data.confidence_history, current: data.confidence, unit: "%", colorFn: confColor },
    // funding_history holds hourly percent; show it per 8h like the current value.
    { label: "Funding /8h", history: data.funding_history?.map(v => v * 8), current: funding8hPct(pos.funding_rate), unit: "%", colorFn: fundColor },
    { label: "Open Interest", history: data.oi_history, current: pos.oi_value, unit: "$", colorFn: null },
    { label: "OI Change", history: data.oi_change_history, current: pos.oi_change_pct, unit: "%", colorFn: oiChgColor },
    // Without CoinGlass these two hold placeholders (1.0 and 0), not readings.
    hasCoinglass(data) && { label: "LSR", history: data.lsr_history, current: pos.long_short_ratio, unit: "x", colorFn: lsrColor },
    { label: "Buy/Sell", history: data.bsr_history, current: data.buy_sell_ratio, unit: "x", colorFn: bsrColor },
    hasCoinglass(data) && { label: "Spot Ratio", history: data.spot_ratio_history, current: pos.spot_futures_ratio, unit: "x", colorFn: spotColor },
  ].filter(m => m && m.history && m.history.length >= 2);

  // Determine accent color from confidence
  const conf = data.confidence;
  const accent = conf >= 60 ? T.green : conf >= 40 ? T.yellow : T.red;

  // ── Engine scalar rows (merged from EngineMetrics) ────────────────────────
  const engineRows = [
    ["Z-Score",    fmt(data.zscore, 3),                                                          zBar(data.zscore)?.color],
    ["Energy",     fmt(data.energy, 3),                                                          null],
    ["Momentum",   `${data.momentum >= 0 ? "+" : ""}${fmt(data.momentum, 2)}%`,                  data.momentum >= 0 ? T.green : T.red],
    ["Price",      data.price ? `$${data.price < 1 ? fmt(data.price, 5) : fmt(data.price, 2)}`  : "\u2014", null],
    ["Divergence", data.divergence || "None",                                                    data.divergence ? T.yellow : null],
    ["Heat",       data.heat != null ? Math.round(data.heat) : "\u2014",                         heatColor(data.heat)],
    ["Heat phase", data.heat_phase || "\u2014",                                                  phaseColor(data.heat_phase)],
    ["ATR",        data.atr_regime || "\u2014",                                                  null],
    ["Distance from BMSB", data.deviation_pct != null ? `${fmt(data.deviation_pct, 2)}%` : "\u2014", null],
    ["Exhaust",    exhaustMeta(data.exhaustion_state).text,                                      exhaustMeta(data.exhaustion_state).color],
    ["Floor",      data.floor_confirmed ? "Confirmed" : "No",                                    data.floor_confirmed ? T.green : null],
    ["Absorb",     data.is_absorption ? "Yes" : "No",                                            data.is_absorption ? col("#b8fff0") : null],
    ["Climax",     data.is_climax ? "Yes" : "No",                                                data.is_climax ? T.yellow : null],
    ["Effort",     data.effort != null ? fmt(data.effort, 3) : "\u2014",                         null],
    ["Rel Vol",    data.rel_vol != null ? fmt(data.rel_vol, 2) + "x" : "\u2014",                 null],
  ];

  // Hide the whole card if neither sparklines nor engine scalars are available
  if (metrics.length === 0 && data.zscore == null) return null;

  return (
    <div style={{
      background: T.glassBg, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: "14px 20px",
      backdropFilter: "blur(20px) saturate(1.3)", WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        marginBottom: 12, paddingBottom: 8,
        borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ width: 3, height: 14, borderRadius: 2, background: accent, flexShrink: 0 }} />
        <span style={{ fontSize: T.textBase, color: T.text2, letterSpacing: "0.1em", fontFamily: T.mono, fontWeight: 700, textTransform: "uppercase" }}>
          Engine values
        </span>
        {metrics.length > 0 && (
          <span style={{ fontSize: T.textXs, color: T.text4, fontFamily: T.mono, marginLeft: "auto" }}>
            {metrics[0].history.length} ticks
          </span>
        )}
      </div>

      {/* Sparklines */}
      {metrics.length > 0 && (
        <div className="metric-history-grid">
          {metrics.map(m => <MetricSparkline key={m.label} {...m} />)}
        </div>
      )}

      {/* Engine scalars — compact 3-col grid */}
      {data.zscore != null && (
        <>
          {metrics.length > 0 && (
            <div style={{
              height: 1, background: T.overlay06, margin: "14px 0 12px",
            }} />
          )}
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
            rowGap: 8, columnGap: 14,
          }}>
            {engineRows.map(([label, value, valColor]) => (
              <div key={label} style={{
                display: "flex", flexDirection: "column", gap: 2,
                minWidth: 0,
              }}>
                <span style={{
                  fontSize: 12, color: T.text3, fontFamily: T.mono,
                  fontWeight: 600, letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  whiteSpace: "nowrap",
                }}>
                  {label}
                </span>
                <span style={{
                  fontSize: T.textSm, color: valColor || T.text1,
                  fontFamily: T.mono, fontWeight: 700,
                  whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                }}>
                  {value}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trader positioning: profitable traders first, then all tracked wallets
// ---------------------------------------------------------------------------

function SmartMoneyPanel({ data }) {
  const sm = data?.smart_money;
  if (!sm) return null;

  const trendColor = sm.trend === "BULLISH" ? T.green : sm.trend === "BEARISH" ? T.red : T.text4;
  const longPct = sm.long_count + sm.short_count > 0
    ? Math.round(sm.long_count / (sm.long_count + sm.short_count) * 100)
    : 50;
  const pro = traderLean(sm.profitable);
  const proPct = longShare(pro);

  return (
    <div style={{
      background: T.glassBg, border: `1px solid ${T.border}`,
      borderRadius: 12, padding: "16px 20px",
      backdropFilter: "blur(20px) saturate(1.3)", WebkitBackdropFilter: "blur(20px) saturate(1.3)",
      boxShadow: `0 2px 12px ${T.shadow}`,
    }}>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        marginBottom: 14, paddingBottom: 10,
        borderBottom: `1px solid ${T.overlay06}`,
      }}>
        <div style={{ width: 3, height: 14, borderRadius: 2, background: col("#a78bfa"), flexShrink: 0 }} />
        <span style={{ fontSize: T.textSm, color: T.text2, letterSpacing: "0.1em", fontFamily: T.font, fontWeight: 700, textTransform: "uppercase" }}>
          Trader positioning
        </span>
        <span className="terminal-status" style={{
          fontSize: T.textSm, fontWeight: 700, color: trendColor, fontFamily: T.mono,
          marginLeft: "auto", padding: "3px 10px", borderRadius: 20,
          background: `${trendColor}15`, border: `1px solid ${trendColor}28`,
        }}>
          {sm.trend}
        </span>
      </div>

      <div style={{ fontSize: T.textSm, color: T.text2, fontFamily: T.font, fontWeight: 600, marginBottom: 6 }}>Profitable traders</div>
      {pro.n > 0 ? <>
        <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", marginBottom: 8 }}>
          <div style={{ width: `${proPct}%`, background: T.green }} />
          <div style={{ flex: 1, background: T.red }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: T.textSm, fontFamily: T.mono, marginBottom: 6 }}>
          <span style={{ color: T.green }}>{pro.long} long · {usd(sm.profitable.long_usd)}</span>
          <span style={{ color: T.red }}>{pro.short} short · {usd(sm.profitable.short_usd)}</span>
        </div>
      </> : <p className="analysis-explanation">No profitable trader holds this market right now.</p>}
      <p className="analysis-explanation">Top 300 Hyperliquid wallets by monthly return, also in profit before this month. In a rising month most are long, so a market they avoid says more than one they hold.{pro.n > 0 && pro.n < 3 ? " Fewer than three hold it, too few to read." : ""}</p>
      <div style={{ fontSize: T.textSm, color: T.text2, fontFamily: T.font, fontWeight: 600, margin: "14px 0 6px", paddingTop: 12, borderTop: `1px solid ${T.overlay06}` }}>All tracked wallets <span style={{ color: T.text4, fontWeight: 400 }}>(profitable traders and large accounts)</span></div>
      <p className="analysis-explanation">The direction weights position value more heavily than wallet count, so the largest accounts dominate it. A smaller number of larger short positions can outweigh a majority of long wallets. This is the reading the signal's tracked-wallet check uses.</p>
      <details className="analysis-method"><summary>How this is calculated</summary><p>The engine blends dollar imbalance (70%) and wallet-count imbalance (30%). Dollar weight rises to 85% when the notional imbalance exceeds 50%. A blended score above +0.15 is bullish, below −0.15 bearish. Conviction also accounts for wallet participation; it is not a probability of profit.</p></details>
      {/* L/S bar */}
      <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", marginBottom: 10 }}>
        <div style={{ width: `${longPct}%`, background: T.green, transition: "width 0.3s" }} />
        <div style={{ flex: 1, background: T.red }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: T.textSm, fontFamily: T.mono, marginBottom: 10 }}>
        <span style={{ color: T.green }}>{longPct}% of wallets long</span>
        <span style={{ color: T.red }}>{100 - longPct}% short</span>
      </div>

      {/* Stats */}
      {[
        ["Wallets Long", sm.long_count, T.green],
        ["Wallets Short", sm.short_count, T.red],
        ["Directional conviction", formatPercent(sm.confidence, { ratio: true }), trendColor],
        ["Wallet-count balance", sm.net_ratio > 0 ? `+${sm.net_ratio.toFixed(2)}` : sm.net_ratio.toFixed(2), sm.net_ratio > 0 ? T.green : T.red],
      ].map(([label, val, color]) => (
        <div key={label} style={{ display: "flex", justifyContent: "space-between", padding: "7px 0" }}>
          <span style={{ fontSize: T.textSm, color: T.text3, fontFamily: T.font }}>{label}</span>
          <span style={{ fontSize: T.textBase, color, fontFamily: T.mono, fontWeight: 600 }}>{val}</span>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// CoinPage — full analysis page for a single symbol
// ---------------------------------------------------------------------------

export default function CoinPage({ scanData4h, scanData1d, urlSymbol }) {
  const navigate = useNavigate();
  const { isMobile, isTablet } = useViewport();
  const [timeframe, setTimeframe] = useState("1d");
  const location = useLocation();
  const marketKind = new URLSearchParams(location.search).get("market") === "spot" || (urlSymbol || "").includes("/USDC") ? "spot" : "perpetual";
  const [availability, setAvailability] = useState(null);
  useEffect(() => {
    let cancelled = false;
    setAvailability(null);
    const load = () => fetch(`${API_BASE}/api/universe?timeframe=${timeframe}`).then(r => r.json()).then(d => {
      const sym = (urlSymbol || "").toUpperCase();
      const market = (d.markets || []).find(m => m.symbol === sym) || (d.markets || []).find(m => m.base.toUpperCase() === sym && m.kind === marketKind) || (d.markets || []).find(m => m.base.toUpperCase() === sym);
      if (!cancelled) setAvailability(market || {exclusion_reason: "This market is not in the Hyperliquid universe."});
    }).catch(() => {});
    load(); const timer = setInterval(load, 60000);
    return () => {cancelled = true; clearInterval(timer);};
  }, [urlSymbol, timeframe, marketKind]);


  // Find scan result matching URL symbol
  const data = useMemo(() => {
    const scanData = timeframe === "4h" ? scanData4h : scanData1d;
    if (!scanData || scanData.length === 0) return null;
    const sym = (urlSymbol || "").toUpperCase();
    // Only rows of the requested market; never fall back to the other one.
    const rows = scanData.filter(r => (r.market_kind || "perpetual") === marketKind);
    return rows.find(r => r.symbol?.toUpperCase() === sym)
      || rows.find(r => getBaseSymbol(r.symbol).replace("/", "").toUpperCase() === sym)
      || null;
  }, [scanData4h, scanData1d, urlSymbol, timeframe, marketKind]);

  // Scroll to top on open
  useEffect(() => { window.scrollTo(0, 0); }, [urlSymbol]);

  // Set document title
  useEffect(() => {
    if (data) {
      document.title = `${getBaseSymbol(data.symbol)} | RCCE Scanner`;
    }
    return () => { document.title = "RCCE Scanner"; };
  }, [data]);

  if (!data || availability?.exclusion_reason) {
    return (
      <div style={{ padding: 40, textAlign: "center" }}>
        <div style={{ fontSize: 16, color: T.text3, fontFamily: T.mono, marginBottom: 16 }}>
          {availability?.exclusion_reason ? `${urlSymbol}: ${availability.exclusion_reason}. Analysis is withheld until market quality recovers.` : availability ? `Waiting for usable ${timeframe.toUpperCase()} analysis for ${urlSymbol}.` : `Checking ${urlSymbol || "market"} availability…`}
        </div>
        <button
          onClick={() => navigate(`/scanner?market=${marketKind}`)}
          className="apple-btn"
          style={{ padding: "8px 20px", fontSize: 12, fontFamily: T.mono, borderRadius: 8 }}
        >
          {"\u2190"} Back to Scanner
        </button>
      </div>
    );
  }

  const isWide = !isMobile && !isTablet;
  const coin = getBaseSymbol(data.symbol);

  return (
    <div style={{ padding: isMobile ? 16 : 24, paddingBottom: isMobile ? 80 : 96 }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", gap: 12, marginBottom: 20, flexWrap: "wrap",
      }}>
        <button
          onClick={() => navigate(`/scanner?market=${marketKind}`)}
          className="apple-btn"
          style={{ padding: "7px 16px", fontSize: T.textSm, fontFamily: T.font, fontWeight: 600, borderRadius: 8, flexShrink: 0 }}
        >
          {"\u2190"} Scanner
        </button>
        <TokenLogo symbol={data.symbol} size={isMobile ? 32 : 40} />
        <span style={{ fontSize: isMobile ? 24 : 32, fontWeight: 700, color: T.text1, fontFamily: T.font, letterSpacing: "-0.02em" }}>
          {coin}
        </span>
        <SetupPair row={data} isMobile={isMobile} transition/>
        {data.unified_signal && data.unified_complete !== false && data.unified_signal !== data.signal && (
          <span title="Combined 4H and 1D decision used for alerts and the scanner counts. It can differ from this timeframe's signal." style={{
            fontSize: T.textSm, fontFamily: T.mono, color: T.text3, whiteSpace: "nowrap",
          }}>
            4H+1D {(SIGNAL_META[data.unified_signal]?.label || data.unified_signal.replaceAll("_", " "))}
          </span>
        )}
        {data.signal_confidence != null && (
          <span className="terminal-status" style={{
            padding: "4px 12px", borderRadius: 20,
            background: T.surface, border: `1px solid ${T.border}`,
            fontSize: T.textSm, fontFamily: T.mono, fontWeight: 600,
            // A blocked WAIT is not a strong reading, however many checks pass.
            color: data.entry_blocked ? T.text3 : data.signal_confidence >= 80 ? col("#34d399") : data.signal_confidence >= 50 ? T.text2 : T.text3,
          }}>
            Checks {formatPercent(data.signal_confidence)}
          </span>
        )}
        <div style={{ marginLeft: "auto" }}>
          <Tabs small label="Timeframe" items={[{ key: "4h", label: "4H" }, { key: "1d", label: "1D" }]} value={timeframe} onChange={setTimeframe} />
        </div>
      </div>

      {/* Chart — full width */}
      <div style={{ marginBottom: 20 }}>
        <BMSBChart
          symbol={data.symbol}
          timeframe={timeframe}
          timeframeControl={false}
          height={isMobile ? 400 : 580}
          signal={data.signal}
          signalFirstSeenAt={data.signal_first_seen_at}
          signalTimeframe={data.timeframe}
          regime={data.regime}
          heat={data.heat}
          exhaustionState={data.exhaustion_state}
          floorConfirmed={data.floor_confirmed}
          momentum={data.momentum}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
          <a
            href={`https://app.hyperliquid.xyz/trade/${encodeURIComponent(data.market_coin || data.symbol.split("/")[0])}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "5px 12px", borderRadius: 8,
              fontSize: T.textSm, fontFamily: T.font, fontWeight: 600,
              color: T.text4, textDecoration: "none",
              border: `1px solid ${T.border}`, background: "transparent",
              transition: "color 0.15s, border-color 0.15s",
            }}
            onMouseEnter={e => { e.currentTarget.style.color = T.accent; e.currentTarget.style.borderColor = T.accent; }}
            onMouseLeave={e => { e.currentTarget.style.color = T.text4; e.currentTarget.style.borderColor = T.border; }}
          >
            Trade on Hyperliquid {"\u2197"}
          </a>
          <a
            href={`https://www.tradingview.com/chart/?symbol=${getTVSymbol(data.symbol)}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "5px 12px", borderRadius: 8,
              fontSize: T.textSm, fontFamily: T.font, fontWeight: 600,
              color: T.text4, textDecoration: "none",
              border: `1px solid ${T.border}`, background: "transparent",
              transition: "color 0.15s, border-color 0.15s",
            }}
            onMouseEnter={e => { e.currentTarget.style.color = T.accent; e.currentTarget.style.borderColor = T.accent; }}
            onMouseLeave={e => { e.currentTarget.style.color = T.text4; e.currentTarget.style.borderColor = T.border; }}
          >
            Open in TradingView {"\u2197"}
          </a>
        </div>
      </div>

      <section className="analysis-evidence">
        <article className="analysis-card">
          <h2>Why this signal?</h2>
          <p className="analysis-lead">{evidenceSummary(data)}</p>
          <div className="analysis-definitions">
            <div><span>Entry checks</span><strong>{formatPercent(data.signal_confidence)}</strong><p>Share of entry conditions met, not a win probability.</p></div>
            <div><span>Regime confidence</span><strong>{formatPercent(data.confidence)}</strong><p>The cycle engine’s confidence in its phase classification.</p></div>
            <div><span>Timeframe agreement</span><strong>{data.confluence?.score != null ? `${Math.round(data.confluence.score)} / 100` : '—'}</strong><p>Confluence between the 4H and daily views.</p></div>
          </div>
          {data.signal_reason && <details className="analysis-method"><summary>Inspect the engine calculation</summary><p className="analysis-raw">{data.signal_reason}</p></details>}
        </article>
        <article className="analysis-card">
          <h2>Signal context</h2>
          {data.confluence && <p className="analysis-lead">{{waiting: 'Both timeframes are waiting.', agree: 'The 4H and daily signals agree.', differ: 'The 4H and daily signals differ. Check both before interpreting the setup.'}[signalAgreement(data.confluence)]}</p>}
          <SignalContext row={data}/>
          {data.smart_money && <p>Trader positioning below shows profitable traders first, then all tracked wallets weighted by size (the reading the signal uses). These can point in different directions.</p>}
        </article>
      </section>

      <section className="analysis-section"><h2>Check the setup</h2><p className="analysis-section-caption">The conditions behind the signal and its agreement across timeframes.</p>
        <div className="analysis-grid">
          <ConditionsScorecard conditions={data.conditions_detail} met={data.conditions_met} total={data.conditions_total}/>
          <ConfluenceCard confluence={data.confluence}/>
        </div>
      </section>
      <section className="analysis-section"><h2>Positioning & counter-evidence</h2><p className="analysis-section-caption">Compare market structure, exchange data and tracked wallets.</p>
        <div className="analysis-grid analysis-grid-three">
          <PositioningPanel positioning={data.positioning} hasCoinglass={hasCoinglass(data)} cvdTrend={data.cvd_trend} cvdDiv={data.cvd_divergence} bsr={data.buy_sell_ratio} vpin={data.vpin} oiContext={data.oi_context}/>
          <CrossExchangePanel symbol={data.symbol}/>
          <SmartMoneyPanel data={data}/>
        </div>
      </section>
      <section className="analysis-section"><h2>Supporting metrics</h2><p className="analysis-section-caption">Underlying engine values for this timeframe.</p><MetricsPanel data={data}/></section>

      {/* Per-coin AI chat popover */}
      <CoinChat symbol={data.symbol} timeframe={timeframe} isMobile={isMobile} />
    </div>
  );
}
