import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import Tabs from "../components/Tabs.jsx";
import AsOf from "../components/AsOf.jsx";
import MarketHistoryChart from "../components/MarketHistoryChart.jsx";
import { Controls, Episodes, ForwardTest, Info, OVERLAYS, RunsChart, loadHistory, loadWallets }
  from "../components/MarketHistorySections.jsx";
import { COPY, RANGES, bandOn, breadthContext, episodesOf, fearGreedByDay, fgSplit, inRange, monthYear, pctLabel,
         percentileOf, rowsOf, signedPct, todayValues } from "../utils/marketHistory.js";
import { GROUPS, SCOPES, WALLET_MODES, WCOPY, byDay, firstDay, latestOf, pct } from "../utils/walletHistory.js";
import "./market.css";

// /market: the share of coins in each regime since 2019 against BTC and Fear & Greed, with how Hyperliquid's
// smart money and whales stood (long or short) at each daily close underneath, on one time axis. It replaced the
// scanner's history drawer; the consensus card's history button and the dial open it (?view=fear for the dial).

// A wallet group's (i): who is in it, how it is drawn, where the days come from.
const walletInfo = (wallets, g, mode, scope) => <Info title={WCOPY.pop.title(g)} paras={WCOPY.pop.group(g, {
  rebuiltTo: wallets?.rebuilt?.to, recordedFrom: wallets?.recorded_from, overlap: wallets?.overlap?.[g.key], mode, scope })} />;

function Kpis({ data, rows, wallets, ctx, view, walletMode, scope }) {
  const t = data.today, c = data.cycle;
  const fg = data.fear_greed || [];
  // The chart's last day, so the KPI matches the readout under the chart (the index may have a newer day).
  const lastRow = [...rows].reverse().find(r => r.fg != null);
  const lastFg = lastRow ? [lastRow.day, lastRow.fg] : fg[fg.length - 1];
  return <div className="mh-kpis mkt-kpis">
    <div className="mh-kpi">
      <strong>{pctLabel(t.uptrend)}</strong>
      <span>{COPY.kpi.uptrend}<Info title={COPY.pop.uptrendTitle} paras={COPY.pop.uptrend({ coins: data.coins, n: t.n, since: ctx.since })} /></span>
      <em>{COPY.kpi.pct(t.percentile)}</em>
    </div>
    {c && <div className="mh-kpi" title={c.start != null ? monthYear(c.start) : undefined}>
      <strong>{COPY.kpi.day(c.day)}</strong>
      <span>{COPY.kpi.run(ctx.on)}</span>
      {ctx.on && c.below_days > 0 && <em>{COPY.kpi.under(c.below_days)}</em>}
    </div>}
    {ctx.side && <div className="mh-kpi">
      <strong className={ctx.side === "below" ? "mh-worse" : ""}>{ctx.side === "inside" ? "0%" : signedPct(ctx.dist, 0)}</strong>
      <span>{COPY.kpi.band(ctx.side)}<Info title={COPY.pop.bandTitle} paras={COPY.pop.band()} /></span>
    </div>}
    {lastFg && <div className="mh-kpi">
      <strong>{lastFg[1]}</strong>
      <span>{COPY.kpi.fg}<Info title={COPY.pop.fgTitle} paras={COPY.pop.fg({ since: monthYear(fg[0][0]) })} /></span>
      <em>{COPY.kpi.pct(percentileOf(fg.map(v => v[1]), lastFg[1]))}</em>
    </div>}
    {GROUPS.map(g => {
      const r = latestOf(wallets, g.key, scope);
      if (!r) return null;
      return <div key={g.key} className="mh-kpi mkt-wallet-kpi">
        <strong><b className="is-long">{pct(r.L)}</b><i aria-hidden="true">·</i><b className="is-short">{pct(r.S)}</b></strong>
        <span>{g.label}{walletInfo(wallets, g, walletMode, scope)}</span>
        <em>{WCOPY.kpi.sub(scope)}</em>
      </div>;
    })}
    {view === "fear" && <FearSplit data={data} />}
  </div>;
}

// Share of days at <=40, 41-69 and >=70 over the whole index history.
function FearSplit({ data }) {
  const split = fgSplit((data.fear_greed || []).map(v => v[1]));
  if (!split) return null;
  const labels = ["≤40", "41–69", "≥70"];
  return <div className="mh-split mkt-split" role="img" aria-label={labels.map((l, i) => `${l} ${split[i]}%`).join(", ")}>
    <div className="mh-split-bar">{split.map((p, i) => <i key={i} className={`s${i}`} style={{ flexGrow: p }} />)}</div>
    <div className="mh-split-labels">{split.map((p, i) => <span key={i} style={{ flexGrow: Math.max(p, 18) }}><b>{labels[i]}</b> {p}%</span>)}</div>
  </div>;
}

export default function MarketPage({ style }) {
  const location = useLocation();
  const navigate = useNavigate();
  const view = new URLSearchParams(location.search).get("view") === "fear" ? "fear" : "breadth";
  const setView = v => navigate(v === "fear" ? "/market?view=fear" : "/market", { replace: true });
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [wallets, setWallets] = useState(null);
  const [range, setRange] = useState("1y");
  const [overlays, setOverlays] = useState(["downtrend", "fg"]);
  const [walletMode, setWalletMode] = useState("z");
  const [scope, setScope] = useState("all");
  const [bandLabel, setBandLabel] = useState(null);

  useEffect(() => {
    let alive = true;
    loadHistory().then(d => { if (!alive) return; if (d) setData(d); else setFailed(true); });
    loadWallets().then(w => { if (alive && w) setWallets(w); });
    return () => { alive = false; };
  }, []);

  const fg = useMemo(() => fearGreedByDay(data), [data]);
  const walletDays = useMemo(() => byDay(wallets, { scope }), [wallets, scope]);
  const rows = useMemo(() => {
    const weekly = data?.btc_band_weekly || [];
    const alt = new Map(data?.alt_recent || []);
    return rowsOf(data).map(r => {
      const b = bandOn(weekly, r.day);
      const wallet = {};
      for (const g of GROUPS) { const w = walletDays[g.key]?.get(r.day); if (w) wallet[g.key] = w; }
      return { ...r, fg: fg.get(r.day) ?? null, bandLo: b?.[0] ?? null, bandHi: b?.[1] ?? null, alt: alt.get(r.day) ?? null, wallet };
    });
  }, [data, fg, walletDays]);

  if (!data) return <div className="mkt" style={style}><p className="mh-muted">{failed ? COPY.unavailable : COPY.loading}</p></div>;

  const ctx = breadthContext(data, { range });
  const band = data.bands.find(b => b.label === (bandLabel || data.today.band)) || data.bands[0];
  const fan = ctx.fan;
  const shownRaw = inRange(rows, range);
  const shown = view === "breadth" ? shownRaw.map(r => ({ ...r, fg: r.fg == null ? null : r.fg / 100 })) : shownRaw;
  const ov = view === "breadth" ? OVERLAYS().filter(o => overlays.includes(o.key)) : [];
  const last = rows[rows.length - 1];
  const today = view === "breadth" ? { ...todayValues(data), row: last } : { row: last };
  const walletGroups = wallets ? GROUPS.filter(g => wallets.groups?.[g.key]?.length)
    .map(g => ({ ...g, label: WCOPY.label(g, scope), info: walletInfo(wallets, g, walletMode, scope) })) : [];
  const walletProp = walletGroups.length ? { mode: walletMode, groups: walletGroups, from: firstDay(wallets) } : null;
  const fanPop = fan ? <Info title={COPY.pop.fanTitle} paras={COPY.pop.fan(ctx.fanCtx)} />
    : <Info title={COPY.pop.fanTitle} paras={COPY.pop.fanNone({ since: ctx.since })} />;
  const aria = panel => [panel, COPY.panel.btc, ...walletGroups.map(g => g.label), RANGES.find(r => r.key === range)?.label].join(", ");

  return <div className="mkt" style={style}>
    <div className="mkt-head">
      <Tabs label="View" value={view} onChange={setView}
        items={[{ key: "breadth", label: COPY.tabs.breadth }, { key: "fear", label: COPY.tabs.fear }]} />
      <AsOf data={data} also={wallets} />
    </div>
    <Kpis data={data} rows={rows} wallets={wallets} ctx={ctx} view={view} walletMode={walletMode} scope={scope} />
    <Controls ranges={RANGES} range={range} setRange={setRange} overlays={overlays} setOverlays={view === "breadth" ? setOverlays : null}>
      {walletProp && <div className="mkt-wallet-controls">
        <Tabs small label={WCOPY.scopeLabel} items={SCOPES} value={scope} onChange={setScope} />
        <Tabs small label={WCOPY.modeLabel} items={WALLET_MODES} value={walletMode} onChange={setWalletMode} />
      </div>}
    </Controls>
    {view === "breadth"
      ? <MarketHistoryChart mode="breadth" rows={shown} range={range} fan={fan} fanPop={fanPop} overlays={ov}
          selBand={{ lo: band.lo, hi: band.hi }} markers={episodesOf(data, band).map(e => e.start)} today={today}
          wallets={walletProp} aria={aria(COPY.panel.uptrend)} />
      : <MarketHistoryChart mode="fear" rows={shown} range={range} today={today} wallets={walletProp} aria={aria(COPY.panel.fg)} />}
    {view === "breadth" && <>
      {data.cycle?.runs && <RunsChart cycle={data.cycle} since={ctx.since} />}
      <Episodes data={data} band={band} setBandLabel={setBandLabel} ctx={ctx} />
      {data.forward_test && <ForwardTest ft={data.forward_test} base={data.base} />}
    </>}
  </div>;
}
