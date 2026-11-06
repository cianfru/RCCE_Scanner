import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import Tabs from "../components/Tabs.jsx";
import AsOf from "../components/AsOf.jsx";
import MarketHistoryChart from "../components/MarketHistoryChart.jsx";
import { Controls, Episodes, ForwardTest, Info, OVERLAYS, loadHistory, loadWallets } from "../components/MarketHistorySections.jsx";
import CyclesChart from "../components/CyclesChart.jsx";
import MarketToday from "../components/MarketToday.jsx";
import { COPY, RANGES, bandOn, breadthContext, fearGreedByDay, fgSplit, inRange, rowsOf, todayValues } from "../utils/marketHistory.js";
import { GROUPS, SCOPES, WCOPY, byDay, firstDay } from "../utils/walletHistory.js";
import { DCOPY } from "../utils/deriveWallets.js";
import "./market.css";

const DeriveDrawer = lazy(() => import("../components/DeriveDrawer.jsx"));
const MarketChartView = lazy(() => import("../components/MarketChartView.jsx"));
const MarketChart = lazy(() => import("../components/MarketChart.jsx"));

// /market: the share of coins in each regime since 2019 against BTC and Fear & Greed, with how one group of
// Hyperliquid wallets stood (long or short) at each daily close underneath, on one time axis. It replaced the
// scanner's history drawer; the consensus card's history button and the dial open it (?view=fear for the dial).
// Kept to one question at a glance (owner, 28 October 2026: "the overwhelm of data"): one wallet group at a time,
// the past-paths fan and the older studies one click away.

// A wallet group's (i): who is in it, how it is drawn, where the days come from.
const walletInfo = (wallets, g, scope) => <Info title={WCOPY.pop.title(g)} paras={WCOPY.pop.group(g, {
  rebuiltTo: wallets?.rebuilt?.to, recordedFrom: wallets?.recorded_from, overlap: wallets?.overlap?.[g.key], scope,
  crowd: wallets?.crowd })} />;

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

// The tabs, in reading order. The page opens on Cycles: where today's broad downturn (or uptrend) sits against past ones.
const VIEWS = ["cycles", "breadth", "positioning", "fear", "chart"];
const POSITIONING = ["band", "crowd", "smart", "whales"];

export default function MarketPage({ style }) {
  const location = useLocation();
  const navigate = useNavigate();
  const q = new URLSearchParams(location.search).get("view");
  const view = VIEWS.includes(q) ? q : "cycles";
  const setView = v => navigate(v === "cycles" ? "/market" : `/market?view=${v}`, { replace: true });
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
  const [hiCycle, setHiCycle] = useState(null);     // the past cycle pointed at in the tiles: { kind, start }
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
  // The tiles, Cycles and Chart read every wallet group over all markets, whatever coin the other tabs have picked.
  const allDays = useMemo(() => byDay(wallets, { scope: "all" }), [wallets]);
  const allRows = useMemo(() => joinRows(data, fg, allDays), [data, fg, allDays]);

  if (!data) return <div className="mkt" style={style}><p className="mh-muted">{failed ? COPY.unavailable : COPY.loading}</p></div>;
  const head = <>
    <MarketToday data={data} rows={allRows} wallets={wallets} onPick={setView} onHoverCycle={setHiCycle} />
    <div className="mkt-head">
      <Tabs label="View" value={view} onChange={setView}
        items={[{ key: "cycles", label: COPY.tabs.cycles }, { key: "breadth", label: COPY.tabs.breadth },
          { key: "positioning", label: COPY.tabs.positioning }, { key: "fear", label: COPY.tabs.fear }, { key: "chart", label: COPY.tabs.chart }]} />
      <span className="mkt-head-right">
        <button type="button" className="mh-link mkt-derive" aria-haspopup="dialog" onClick={() => setDerive(true)}>{DCOPY.open}</button>
        <AsOf data={data} also={wallets} />
      </span>
    </div>
  </>;
  const drawer = derive && <Suspense fallback={null}><DeriveDrawer onClose={closeDerive} /></Suspense>;
  if (view === "cycles") {
    return <div className="mkt" style={style}>{head}{drawer}<CyclesChart rows={allRows} highlight={hiCycle} /></div>;
  }
  if (view === "chart") {
    return <div className="mkt" style={style}>
      {head}
      {drawer}
      <Suspense fallback={<p className="mh-muted">{COPY.loading}</p>}><MarketChartView rows={allRows} /></Suspense>
    </div>;
  }
  if (view === "positioning") {
    return <div className="mkt" style={style}>
      {head}
      {drawer}
      <div className="mch-tools">
        <Tabs small label="Range" items={RANGES} value={range} onChange={setRange} />
        <Tabs small label={WCOPY.scopeLabel} items={SCOPES} value={scope} onChange={setScope} />
      </div>
      <Suspense fallback={<p className="mh-muted">{COPY.loading}</p>}><MarketChart rows={rows} indicators={POSITIONING} range={range} /></Suspense>
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
    {view === "fear" && <FearSplit data={data} />}
    <Controls ranges={RANGES} range={range} setRange={setRange} overlays={overlays} setOverlays={view === "breadth" ? setOverlays : null}>
      {view === "breadth" && <button type="button" className="mkt-fan-toggle" aria-pressed={fanOn} onClick={() => setFanOn(v => !v)}>
        <svg className="mh-swatch" width="18" height="12" aria-hidden="true"><path d="M1 6 L17 2 M1 6 L17 6 M1 6 L17 10" /></svg>{COPY.fanToggle}</button>}
    </Controls>
    {view === "breadth"
      ? <MarketHistoryChart mode="breadth" rows={shown} range={range} fan={fan} fanPop={fanPop} overlays={ov} fanOn={fanOn}
          today={today} wallets={walletProp} aria={aria(COPY.panel.uptrend)} />
      : <MarketHistoryChart mode="fear" rows={shown} range={range} today={today} wallets={walletProp} aria={aria(COPY.panel.fg)} />}
    {view === "breadth" && <>
      <button type="button" className="mh-link mkt-more" aria-expanded={more} aria-controls="mkt-more" onClick={() => setMore(v => !v)}>
        {more ? COPY.less : COPY.more}</button>
      {more && <div id="mkt-more">
        <Episodes data={data} band={band} setBandLabel={setBandLabel} ctx={ctx} />
        {data.forward_test && <ForwardTest ft={data.forward_test} base={data.base} />}
      </div>}
    </>}
  </div>;
}
