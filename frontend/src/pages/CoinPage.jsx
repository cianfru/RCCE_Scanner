import SetupPair from "../components/SetupPair.jsx";
import TokenLogo from "../components/TokenLogo.jsx";
import HelpTip from "../components/HelpTip.jsx";
import { formatPercent, formatPrice, evidenceSummary, counterEvidence, hasCoinglass, signalAgreement } from "../utils/marketPresentation.js";
import Tabs from "../components/Tabs.jsx";
import { useState, useEffect, useLayoutEffect, useMemo, useRef, useCallback } from "react";
import useFullRow from "../hooks/useFullRow.js";
import { apiFetch } from "../edge.js";
import { Star } from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";
import { col, T, REGIME_META, SIGNAL_META, heatColor, phaseColor, exhaustMeta, fmt, zBar, getBaseSymbol, getTVSymbol } from "../theme.js";
import useViewport from "../hooks/useViewport.js";
import BMSBChart from "../components/BMSBChart.jsx";
import ConditionsScorecard from "../components/ConditionsScorecard.jsx";
import PositioningPanel from "../components/PositioningPanel.jsx";
import CrossExchangePanel from "../components/CrossExchangePanel.jsx";
import CoinChat from "../components/CoinChat.jsx";
import PanelHeader from "../components/PanelHeader.jsx";
import TradersCard from "../components/TradersCard.jsx";
import useCoinTraders from "../hooks/useCoinTraders.js";
import { timeframeFrom, backHref } from "../utils/researchNavigation.js";
import useFavorites from "../hooks/useFavorites.js";
import useSetupMap from "../hooks/useSetupMap.js";
import { watchToast, pnl } from "../utils/setupMap.js";
import { useWallet } from "../WalletContext.jsx";
import useMyPositions from "../hooks/useMyPositions.js";
import { sideColor, fmtPx } from "../utils/traderFormat.js";
import { STAR_TIP, WATCH_TIP, WatchMark } from "../components/radar/shared.jsx";
import { pollWhileVisible } from "../utils/visiblePoll.js";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Timeframe agreement card
// ---------------------------------------------------------------------------

function ConfluenceCard({ confluence }) {
  if (!confluence) return null;

  return (
    <div style={{
      background: T.glassBg, border: `1px solid ${T.border}`,
      borderRadius: T.radius, padding: "16px 20px",
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
      <PanelHeader title={<>Timeframe agreement <HelpTip title="Confluence"><p>A 0–100 score describing how the four-hour and daily signals, regimes and supporting factors align. Higher agreement means more shared evidence across timeframes. It is not a win rate or a probability of profit.</p></HelpTip></>} />

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
// Engine values: the raw readings behind the signal, inside "Inspect the engine calculation"
// ---------------------------------------------------------------------------

function EngineValues({ data }) {
  if (data.zscore == null) return null;
  const rows = [
    ["Z-score", fmt(data.zscore, 3), zBar(data.zscore)?.color],
    ["Energy", fmt(data.energy, 3), null],
    ["Momentum", data.momentum != null ? `${data.momentum >= 0 ? "+" : ""}${fmt(data.momentum, 2)}%` : "\u2014", data.momentum == null ? null : data.momentum >= 0 ? T.green : T.red],
    ["Heat", data.heat != null ? Math.round(data.heat) : "\u2014", heatColor(data.heat)],
    ["Heat phase", data.heat_phase || "\u2014", phaseColor(data.heat_phase)],
    ["Divergence", data.divergence || "None", data.divergence ? T.yellow : null],
    ["ATR", data.atr_regime || "\u2014", null],
    ["Distance from BMSB", data.deviation_pct != null ? `${fmt(data.deviation_pct, 2)}%` : "\u2014", null],
    ["Exhaust", exhaustMeta(data.exhaustion_state).text, exhaustMeta(data.exhaustion_state).color],
    ["Floor", data.floor_confirmed ? "Confirmed" : "No", data.floor_confirmed ? T.green : null],
    ["Absorb", data.is_absorption ? "Yes" : "No", data.is_absorption ? col("#b8fff0") : null],
    ["Climax", data.is_climax ? "Yes" : "No", data.is_climax ? T.yellow : null],
    ["Effort", data.effort != null ? fmt(data.effort, 3) : "\u2014", null],
    ["Rel vol", data.rel_vol != null ? fmt(data.rel_vol, 2) + "x" : "\u2014", null],
  ];
  return <dl className="analysis-engine">
    {rows.map(([label, value, color]) => <div key={label}><dt>{label}</dt><dd style={color ? { color } : undefined}>{value}</dd></div>)}
  </dl>;
}

// ---------------------------------------------------------------------------
// CoinPage — full analysis page for a single symbol
// ---------------------------------------------------------------------------

export default function CoinPage({ scanData4h, scanData1d, urlSymbol }) {
  const navigate = useNavigate();
  const { isMobile } = useViewport();
  const location = useLocation();
  // The timeframe lives in the address (?tf=), so links and reloads keep it.
  const timeframe = timeframeFrom(location.search);
  const setTimeframe = (tf) => {
    const params = new URLSearchParams(location.search);
    params.set("tf", tf);
    navigate(`${location.pathname}?${params}`, { replace: true, state: location.state });
  };
  // Back to the scanner or Radar view this coin was opened from, at the same scroll position.
  const back = backHref(location.search);
  const backLabel = back.startsWith("/radar") ? "Radar" : "Scanner";
  const goBack = () => navigate(back, { state: { restoreScroll: location.state?.scannerScroll ?? 0 } });
  const marketKind = new URLSearchParams(location.search).get("market") === "spot" || (urlSymbol || "").includes("/USDC") ? "spot" : "perpetual";
  const [availability, setAvailability] = useState(null);
  // A failed refresh keeps the last reading and says so, with a Retry.
  const [availabilityError, setAvailabilityError] = useState(false);
  const [availabilityAttempt, setAvailabilityAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setAvailability(null); setAvailabilityError(false);
    const load = () => apiFetch(`/api/universe?timeframe=${timeframe}`).then(r => { if (!r.ok) throw new Error("Unavailable"); return r.json(); }).then(d => {
      const sym = (urlSymbol || "").toUpperCase();
      const market = (d.markets || []).find(m => m.symbol === sym) || (d.markets || []).find(m => m.base.toUpperCase() === sym && m.kind === marketKind) || (d.markets || []).find(m => m.base.toUpperCase() === sym);
      if (!cancelled) { setAvailability(market || {unlisted: true}); setAvailabilityError(false); }
    }).catch(() => { if (!cancelled) setAvailabilityError(true); });
    load(); const stop = pollWhileVisible(load, 60000);
    return () => {cancelled = true; stop();};
  }, [urlSymbol, timeframe, marketKind, availabilityAttempt]);
  const retryAvailability = <>Market availability could not refresh.{" "}<button type="button" className="te-link" onClick={() => setAvailabilityAttempt(n => n + 1)}>Retry</button></>;

  // Star (pinned in the scanner) and Watch (Telegram setup messages): the same stores as the grid and the Radar.
  const { isFav, toggle: toggleFav } = useFavorites();
  const { watched, telegram, toggleWatch } = useSetupMap(null);
  const [watchMsg, setWatchMsg] = useState("");
  useEffect(() => { if (!watchMsg) return undefined; const t = setTimeout(() => setWatchMsg(""), 3500); return () => clearTimeout(t); }, [watchMsg]);
  const onWatch = useCallback(async c => setWatchMsg(watchToast(c, await toggleWatch(c, timeframe), telegram)), [toggleWatch, timeframe, telegram]);
  const [chatOpen, setChatOpen] = useState(false);
  // The shared address's trade in this perp (connected wallet or read-only view).
  const { effectiveAddress } = useWallet();
  const { byCoin: myBy } = useMyPositions(marketKind === "perpetual" ? effectiveAddress : null);
  const mine = marketKind === "perpetual" && urlSymbol ? myBy.get(getBaseSymbol(urlSymbol.toUpperCase())) || null : null;
  const myEntry = useMemo(() => (mine?.entry ? { price: mine.entry, side: mine.side } : null), [mine?.entry, mine?.side]);


  // Find scan result matching URL symbol (the list row; its full row is laid over it below)
  const listRow = useMemo(() => {
    const scanData = timeframe === "4h" ? scanData4h : scanData1d;
    if (!scanData || scanData.length === 0) return null;
    const sym = (urlSymbol || "").toUpperCase();
    // Only rows of the requested market; never fall back to the other one.
    const rows = scanData.filter(r => (r.market_kind || "perpetual") === marketKind);
    return rows.find(r => r.symbol?.toUpperCase() === sym)
      || rows.find(r => getBaseSymbol(r.symbol).replace("/", "").toUpperCase() === sym)
      || null;
  }, [scanData4h, scanData1d, urlSymbol, timeframe, marketKind]);
  const data = useFullRow(listRow);

  // "Trade on Hyperliquid" drops "Trade on" only when the full label would push the actions off the
  // title line (a long ticker, a two-line setup pair, the 4H+1D note). When even the short label does
  // not fit, the actions take their own line and keep the full label there. Measured before paint.
  const headRef = useRef(null);
  const isWatchedNow = watched.has(getBaseSymbol(data?.symbol || ""));
  useLayoutEffect(() => {
    const head = headRef.current;
    if (!head) return undefined;
    const fit = () => {
      const tabs = head.querySelector(".coin-tabs"), acts = head.querySelector(".coin-actions");
      if (!tabs || !acts) return;
      const wrapped = () => acts.getBoundingClientRect().top >= tabs.getBoundingClientRect().bottom - 1;
      delete head.dataset.trade;
      if (!wrapped()) return;
      head.dataset.trade = "short";
      if (wrapped()) delete head.dataset.trade;
    };
    fit();
    window.addEventListener("resize", fit);
    document.fonts?.ready?.then(fit).catch(() => {});
    return () => window.removeEventListener("resize", fit);
  }, [data, timeframe, isMobile, isWatchedNow, availabilityError]);

  // Scroll to top on open
  useEffect(() => { window.scrollTo(0, 0); }, [urlSymbol]);
  // Tracked traders on this coin: loaded once, drawn on the chart and listed in the Traders card.
  const traders = useCoinTraders(data?.symbol, !!data);
  const traderApi = useRef(null);

  // Set document title
  useEffect(() => {
    if (data) {
      document.title = `${getBaseSymbol(data.symbol)} · Reflex`;
    }
    return () => { document.title = "Reflex"; };
  }, [data]);

  if (!data || availability?.unlisted || availability?.exclusion_reason) {
    return (
      <div style={{ padding: 40, textAlign: "center" }}>
        <div style={{ fontSize: 16, color: T.text3, fontFamily: T.mono, marginBottom: 16 }}>
          {availabilityError && !availability ? retryAvailability : availability?.unlisted ? `${urlSymbol} is not listed on Hyperliquid.` : availability?.exclusion_reason ? `${urlSymbol}: ${availability.exclusion_reason.replace(/\.$/, "")}. Analysis is withheld until market quality recovers.` : availability ? `Waiting for usable ${timeframe.toUpperCase()} analysis for ${urlSymbol}.` : `Checking ${urlSymbol || "market"} availability…`}
        </div>
        <button
          onClick={goBack}
          className="apple-btn"
          style={{ padding: "8px 20px", fontSize: 12, fontFamily: T.mono, borderRadius: 8 }}
        >
          {"\u2190"} Back to {backLabel}
        </button>
      </div>
    );
  }

  const coin = getBaseSymbol(data.symbol);
  // Hyperliquid-only markets have no Binance ticker for TradingView to open.
  const tvSymbol = getTVSymbol(data.symbol, data.positioning?.source === "binance");
  const starred = isFav(data.symbol);
  const isWatched = watched.has(coin);
  const against = counterEvidence(data);
  const unified = data.unified_signal && data.unified_complete !== false && data.unified_signal !== data.signal
    ? (SIGNAL_META[data.unified_signal]?.label || data.unified_signal.replaceAll("_", " ")) : null;

  return (
    <div style={{ padding: isMobile ? 16 : 24, paddingBottom: isMobile ? 80 : 96 }}>
      {/* Header */}
      <div ref={headRef} className="coin-head" style={{
        display: "flex", alignItems: "center", gap: "6px 12px", marginBottom: availabilityError ? 8 : 20, flexWrap: "wrap",
      }}>
        <button
          onClick={goBack}
          className="apple-btn"
          style={{ padding: "7px 16px", fontSize: T.textSm, fontFamily: T.font, fontWeight: 600, borderRadius: 8, flexShrink: 0 }}
        >
          {"\u2190"} {backLabel}
        </button>
        <button type="button" className="fav-star coin-star" aria-pressed={starred}
          aria-label={`${starred ? "Remove" : "Add"} ${coin} ${starred ? "from" : "to"} favorites`}
          title={STAR_TIP} onClick={() => toggleFav(data.symbol)}>
          <Star size={isMobile ? 18 : 20} strokeWidth={1.75} aria-hidden="true" {...(starred ? { color: col("#facc15"), fill: col("#facc15") } : { fill: "none" })} />
        </button>
        <TokenLogo symbol={data.symbol} size={isMobile ? 32 : 40} />
        <span style={{ fontSize: isMobile ? 24 : 32, fontWeight: 700, color: T.text1, fontFamily: T.font, letterSpacing: "-0.02em" }}>
          {coin}
        </span>
        {data.price != null && <span className="coin-price">{formatPrice(data.price, { sig: 5 })}</span>}
        <SetupPair row={data} isMobile={isMobile} transition/>
        {/* The timeframe tabs, then the actions. On desktop both join the title line (with the
            short "Hyperliquid" label when that is what fits); when the actions still do not fit
            they take a line of their own, left-aligned, and the tabs stay on the title line.
            On phones they form one second row. */}
        <div className="coin-head-actions">
          <div className="coin-tabs">
            <Tabs small label="Timeframe" items={[{ key: "4h", label: "4H" }, { key: "1d", label: "1D" }]} value={timeframe} onChange={setTimeframe} />
          </div>
          <div className="coin-actions">
            {marketKind === "perpetual" && (
              <button type="button" className="te-toggle coin-watch" aria-pressed={isWatched} title={WATCH_TIP} onClick={() => onWatch(coin)}>
                <WatchMark />{isWatched ? "Watching" : "Watch"}
              </button>
            )}
            <a className="coin-action" href={`https://app.hyperliquid.xyz/trade/${encodeURIComponent(data.market_coin || data.symbol.split("/")[0])}`}
              target="_blank" rel="noopener noreferrer" aria-label="Trade on Hyperliquid" title="Trade on Hyperliquid"><span className="coin-action-long">Trade on </span>Hyperliquid {"\u2197"}</a>
            {tvSymbol && <a className="coin-action" href={`https://www.tradingview.com/chart/?symbol=${tvSymbol}`}
              target="_blank" rel="noopener noreferrer">TradingView {"\u2197"}</a>}
          </div>
        </div>
      </div>
      {availabilityError && <p className="coin-availability-note">{retryAvailability}</p>}
      {mine && (() => {
        const r = pnl(mine, data.price);
        return <p className="coin-mytrade">
          Your trade: <b style={{ color: sideColor(mine.side) }}>{mine.side === "short" ? "Short" : "Long"}</b> from <span className="smap-mono">{fmtPx(mine.entry)}</span>
          {r != null && <> · <span className="smap-mono" style={{ color: r >= 0 ? "var(--t-profit)" : "var(--t-loss)" }}>{r >= 0 ? "+" : ""}{(100 * r).toFixed(1)}%</span></>}
        </p>;
      })()}

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
          exhaustionState={data.exhaustion_state}
          floorConfirmed={data.floor_confirmed}
          traders={traders}
          traderApi={traderApi}
          showSetup={false}
          myEntry={myEntry}
          toolbarAction={<button type="button" className="chart-ask" data-coinchat-trigger aria-expanded={chatOpen} onClick={() => setChatOpen(true)}
            title={`Ask AI about ${coin}`}><img src="/brand/reflex-ribbon-transparent.svg" alt="" width="16" height="16" />Ask AI</button>}
        />
      </div>

      <section className="analysis-evidence coin-evidence">
        <article className="analysis-card">
          <h2>Why this signal? <HelpTip title="Reading these numbers" width={380}>
            <p>Entry checks: how many of the engine's entry conditions are met now, not a win probability.</p>
            <p>Regime confidence: the cycle engine's confidence in its phase classification.</p>
            <p>Timeframe agreement: how far the 4H and daily views agree, 0 to 100.</p>
          </HelpTip></h2>
          <p className="analysis-lead">{evidenceSummary(data)}</p>
          <div className="analysis-definitions">
            <div><span>Entry checks</span><strong>{data.conditions_total > 0 ? `${data.conditions_met}/${data.conditions_total}` : "\u2014"}</strong></div>
            <div><span>Regime confidence</span><strong>{formatPercent(data.confidence)}</strong></div>
            <div><span>Timeframe agreement</span><strong>{data.confluence?.score != null ? `${Math.round(data.confluence.score)}/100` : "\u2014"}</strong></div>
          </div>
          {against.length > 0 && <div className="coin-against">
            <span>Against it now</span>
            <ul>{against.map(t => <li key={t}>{t}</li>)}</ul>
          </div>}
          <details className="analysis-method">
            <summary>Inspect the engine calculation</summary>
            {data.signal_reason && <p className="analysis-raw">{data.signal_reason}</p>}
            {unified && <p>Combined 4H and 1D decision (used for alerts and the scanner counts): {unified}.</p>}
            {data.signal_first_seen_at && <p>Signal first recorded {new Date(data.signal_first_seen_at * 1000).toLocaleString()}.</p>}
            <EngineValues data={data} />
          </details>
          <p className="analysis-ask"><button type="button" className="te-link" data-coinchat-trigger aria-expanded={chatOpen} onClick={() => setChatOpen(true)}>Ask AI about {coin}</button></p>
        </article>
        <TradersCard symbol={data.symbol} sm={data.smart_money} traders={traders} spot={marketKind === "spot"} price={data.price}
          onShowEntries={() => { traderApi.current?.showEntries?.(); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
      </section>

      {/* One click deeper: the full checklist, and every market reading. */}
      <details className="coin-more">
        <summary><span>Check the setup</span>{data.conditions_total > 0 && <small>{data.conditions_met}/{data.conditions_total} checks</small>}</summary>
        <div className="analysis-grid">
          <ConditionsScorecard conditions={data.conditions_detail} met={data.conditions_met} total={data.conditions_total}/>
          <ConfluenceCard confluence={data.confluence}/>
        </div>
      </details>
      <details className="coin-more">
        <summary><span>All market data</span><small>Funding, open interest, flow, exchanges</small></summary>
        <div className="analysis-grid">
          <PositioningPanel positioning={data.positioning} hasCoinglass={hasCoinglass(data)} cvdTrend={data.cvd_trend} cvdDiv={data.cvd_divergence} bsr={data.buy_sell_ratio} vpin={data.vpin} oiContext={data.oi_context}/>
          <CrossExchangePanel symbol={data.symbol}/>
        </div>
      </details>

      {/* Per-coin AI chat popover */}
      <CoinChat symbol={data.symbol} timeframe={timeframe} marketKind={marketKind} isMobile={isMobile} open={chatOpen} onOpenChange={setChatOpen} />
      {watchMsg && <div className="smap-toast" role="status">{watchMsg}</div>}
    </div>
  );
}
