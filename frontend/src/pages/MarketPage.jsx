import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import Tabs from "../components/Tabs.jsx";
import AsOf from "../components/AsOf.jsx";
import MarketHistoryChart from "../components/MarketHistoryChart.jsx";
import { Controls, Episodes, ForwardTest, Info, OVERLAYS, RunsChart, ageLevel, loadHistory, loadWallets }
  from "../components/MarketHistorySections.jsx";
import { COPY, RANGES, bandOn, breadthContext, dayDate, fearGreedByDay, fgSplit, inRange, monthYear, pctLabel,
         percentileOf, rowsOf, todayValues } from "../utils/marketHistory.js";
import { GROUPS, SCOPES, WCOPY, byDay, firstDay, latestOf, pct } from "../utils/walletHistory.js";
import { DCOPY } from "../utils/deriveWallets.js";
import "./market.css";

const DeriveDrawer = lazy(() => import("../components/DeriveDrawer.jsx"));
const MarketChartView = lazy(() => import("../components/MarketChartView.jsx"));

// /market: the share of coins in each regime since 2019 against BTC and Fear & Greed, with how one group of
// Hyperliquid wallets stood (long or short) at each daily close underneath, on one time axis. It replaced the
// scanner's history drawer; the consensus card's history button and the dial open it (?view=fear for the dial).
// Kept to one question at a glance (owner, 28 October 2026: "the overwhelm of data"): one wallet group at a time,
// the past-paths fan and the older studies one click away.

// A wallet group's (i): who is in it, how it is drawn, where the days come from.
const walletInfo = (wallets, g, scope) => <Info title={WCOPY.pop.title(g)} paras={WCOPY.pop.group(g, {
  rebuiltTo: wallets?.rebuilt?.to, recordedFrom: wallets?.recorded_from, overlap: wallets?.overlap?.[g.key], scope,
  crowd: wallets?.crowd })} />;

function Kpis({ data, rows, wallets, ctx, view, scope, group }) {
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
    {c && view === "breadth" && <RunAge c={c} on={ctx.on} />}
    {lastFg && <div className="mh-kpi">
      <strong>{lastFg[1]}</strong>
      <span>{COPY.kpi.fg}<Info title={COPY.pop.fgTitle} paras={COPY.pop.fg({ since: monthYear(fg[0][0]) })} /></span>
      <em>{COPY.kpi.pct(percentileOf(fg.map(v => v[1]), lastFg[1]))}</em>
    </div>}
    {GROUPS.filter(g => g.key === group).map(g => {
      const r = latestOf(wallets, g.key, scope);
      if (!r) return null;
      // A reading older than the chart's last day says its date (Outrider's rebuilt days end before the record).
      const asOf = rows.length && rows[rows.length - 1].day - r.day > 1 ? dayDate(r.day, false) : null;
      return <div key={g.key} className="mh-kpi mkt-wallet-kpi">
        <strong><b className="is-long">{pct(r.L)}</b><i aria-hidden="true">·</i><b className="is-short">{pct(r.S)}</b></strong>
        <span>{g.label}{walletInfo(wallets, g, scope)}</span>
        <em>{WCOPY.kpi.sub(g, scope)}{asOf && ` · ${asOf}`}</em>
      </div>;
    })}
    {view === "fear" && <FearSplit data={data} />}
  </div>;
}

// Today's run age. A risk-on run is coloured by how many past runs ended before this age: yellow past half of them,
// light red past 3 in 4, red past 9 in 10 (with 6 or more past runs). The colour flashes once when the page opens.
function RunAge({ c, on }) {
  const { level, outlasted, past } = ageLevel(c);
  return <div className={`mh-kpi mkt-age is-l${level}`} title={c.start != null ? monthYear(c.start) : undefined}>
    <strong><b className={level ? "mkt-age-num mkt-age-flash" : "mkt-age-num"}>{COPY.kpi.day(c.day)}</b></strong>
    <span>{COPY.kpi.run(on)}</span>
    {past > 0 && <em>{COPY.kpi.age(outlasted, past, on)}</em>}
    {on && c.below_days > 0 && <em>{COPY.kpi.under(c.below_days)}</em>}
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

// Market history rows joined with Fear & Greed (0-100), BTC's weekly band, the typical alt and the wallet groups.
function joinRows(data, fg, walletDays) {
  const weekly = data?.btc_band_weekly || [];
  const alt = new Map(data?.alt_recent || []);
  return rowsOf(data).map(r => {
    const b = bandOn(weekly, r.day);
    const wallet = {};
    for (const g of GROUPS) { const w = walletDays[g.key]?.get(r.day); if (w) wallet[g.key] = w; }
    return { ...r, fg: fg.get(r.day) ?? null, bandLo: b?.[0] ?? null, bandHi: b?.[1] ?? null, alt: alt.get(r.day) ?? null, wallet };
  });
}

export default function MarketPage({ style }) {
  const location = useLocation();
  const navigate = useNavigate();
  const q = new URLSearchParams(location.search).get("view");
  const view = q === "fear" || q === "chart" ? q : "breadth";
  const setView = v => navigate(v === "breadth" ? "/market" : `/market?view=${v}`, { replace: true });
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [wallets, setWallets] = useState(null);
  const [range, setRange] = useState("1y");
  const [overlays, setOverlays] = useState(["fg"]);
  const [scope, setScope] = useState("all");
  const [group, setGroup] = useState("smart");
  const [fanOn, setFanOn] = useState(false);
  const [more, setMore] = useState(false);
  const [bandLabel, setBandLabel] = useState(null);
  const [derive, setDerive] = useState(false);
  const closeDerive = useCallback(() => setDerive(false), []);

  useEffect(() => {
    let alive = true;
    loadHistory().then(d => { if (!alive) return; if (d) setData(d); else setFailed(true); });
    loadWallets().then(w => { if (alive && w) setWallets(w); });
    return () => { alive = false; };
  }, []);

  const fg = useMemo(() => fearGreedByDay(data), [data]);
  const walletDays = useMemo(() => byDay(wallets, { scope }), [wallets, scope]);
  const rows = useMemo(() => joinRows(data, fg, walletDays), [data, fg, walletDays]);
  // The Chart view reads every wallet group over all markets, whatever coin the other views have picked.
  const allDays = useMemo(() => byDay(wallets, { scope: "all" }), [wallets]);
  const chartRows = useMemo(() => (view === "chart" ? joinRows(data, fg, allDays) : []), [view, data, fg, allDays]);

  if (!data) return <div className="mkt" style={style}><p className="mh-muted">{failed ? COPY.unavailable : COPY.loading}</p></div>;
  const head = <div className="mkt-head">
    <Tabs label="View" value={view} onChange={setView}
      items={[{ key: "chart", label: COPY.tabs.chart }, { key: "breadth", label: COPY.tabs.breadth }, { key: "fear", label: COPY.tabs.fear }]} />
    <span className="mkt-head-right">
      <button type="button" className="mh-link mkt-derive" aria-haspopup="dialog" onClick={() => setDerive(true)}>{DCOPY.open}</button>
      <AsOf data={data} also={wallets} />
    </span>
  </div>;
  const drawer = derive && <Suspense fallback={null}><DeriveDrawer onClose={closeDerive} /></Suspense>;
  if (view === "chart") {
    return <div className="mkt" style={style}>
      {head}
      {drawer}
      <Suspense fallback={<p className="mh-muted">{COPY.loading}</p>}><MarketChartView rows={chartRows} /></Suspense>
    </div>;
  }

  const ctx = breadthContext(data, { range });
  const band = data.bands.find(b => b.label === (bandLabel || data.today.band)) || data.bands[0];
  const fan = ctx.fan;
  const shownRaw = inRange(rows, range);
  const shown = view === "breadth" ? shownRaw.map(r => ({ ...r, fg: r.fg == null ? null : r.fg / 100 })) : shownRaw;
  const ov = view === "breadth" ? OVERLAYS().filter(o => overlays.includes(o.key)) : [];
  const last = rows[rows.length - 1];
  const today = view === "breadth" ? { ...todayValues(data), row: last } : { row: last };
  // The groups with data in this coin scope; the panel shows the one picked (the first with data if it has none).
  const available = wallets ? GROUPS.filter(g => walletDays[g.key]?.size) : [];
  const g = available.find(x => x.key === group) || available[0];
  const walletGroups = g ? [{ ...g, label: WCOPY.label(g, scope), info: walletInfo(wallets, g, scope), from: firstDay(wallets, g.key) }] : [];
  const walletHead = g && <>
    <span className="mkt-wallet-pick">
      <Tabs small label={WCOPY.groupLabel} items={available.map(x => ({ key: x.key, label: x.label }))} value={g.key} onChange={setGroup} />
      <span className="mh-wallet-key" aria-hidden="true"><i className="is-long" />{WCOPY.long}<i className="is-short" />{WCOPY.short}</span>
      {walletInfo(wallets, g, scope)}
    </span>
    <Tabs small label={WCOPY.scopeLabel} items={SCOPES} value={scope} onChange={setScope} />
  </>;
  const walletProp = walletGroups.length ? { groups: walletGroups, head: walletHead } : null;
  const fanPop = fan ? <Info title={COPY.pop.fanTitle} paras={COPY.pop.fan(ctx.fanCtx)} />
    : <Info title={COPY.pop.fanTitle} paras={COPY.pop.fanNone({ since: ctx.since })} />;
  const aria = panel => [panel, COPY.panel.btc, ...walletGroups.map(g => g.label), RANGES.find(r => r.key === range)?.label].join(", ");

  return <div className="mkt" style={style}>
    {head}
    {drawer}
    <Kpis data={data} rows={rows} wallets={wallets} ctx={ctx} view={view} scope={scope} group={g?.key} />
    <Controls ranges={RANGES} range={range} setRange={setRange} overlays={overlays} setOverlays={view === "breadth" ? setOverlays : null}>
      {view === "breadth" && <button type="button" className="mkt-fan-toggle" aria-pressed={fanOn} onClick={() => setFanOn(v => !v)}>
        <svg className="mh-swatch" width="18" height="12" aria-hidden="true"><path d="M1 6 L17 2 M1 6 L17 6 M1 6 L17 10" /></svg>{COPY.fanToggle}</button>}
    </Controls>
    {view === "breadth"
      ? <MarketHistoryChart mode="breadth" rows={shown} range={range} fan={fan} fanPop={fanPop} overlays={ov} fanOn={fanOn}
          today={today} wallets={walletProp} aria={aria(COPY.panel.uptrend)} />
      : <MarketHistoryChart mode="fear" rows={shown} range={range} today={today} wallets={walletProp} aria={aria(COPY.panel.fg)} />}
    {view === "breadth" && <>
      {data.cycle?.runs && <RunsChart cycle={data.cycle} since={ctx.since} />}
      <button type="button" className="mh-link mkt-more" aria-expanded={more} aria-controls="mkt-more" onClick={() => setMore(v => !v)}>
        {more ? COPY.less : COPY.more}</button>
      {more && <div id="mkt-more">
        <Episodes data={data} band={band} setBandLabel={setBandLabel} ctx={ctx} />
        {data.forward_test && <ForwardTest ft={data.forward_test} base={data.base} />}
      </div>}
    </>}
  </div>;
}
